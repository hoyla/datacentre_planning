"""PlanIt API adapter (planit.org.uk).

Two passes per index run:
  1. /api/areas/  → populate councils table + build area_name → gss_code map.
  2. /api/applics/ → sweep applications matching the DC keyword union, since 2018.

Raw page responses land in source_snapshots, deduped by (source_id, url, content_sha256).
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from dcp import db, repo

log = logging.getLogger(__name__)

SOURCE_NAME = "planit"
BASE = "https://www.planit.org.uk/api"
USER_AGENT = "datacentre_planning research (luke.hoyland@gmail.com)"

# Direct DC-keyword union. "energy centre" is excluded — 9k+ noisy hits; needs a separate
# triage-heavy sweep later. See data/planit_exploration/findings.md.
DC_KEYWORDS = (
    '"data centre" OR "data center" OR "data hall" OR '
    'hyperscale OR datacentre OR colocation OR "data park"'
)

AREAS_SELECT = (
    "area_name,long_name,gss_code,parent_name,in_region,scraper_type,scraper_name,"
    "planning_url,total,min_date,max_date,is_planning,has_planning"
)
APPS_SELECT = (
    "name,uid,altid,area_id,area_name,scraper_name,address,postcode,description,"
    "app_type,app_size,app_state,associated_id,start_date,decided_date,consulted_date,"
    "last_changed,last_scraped,url,link,location_x,location_y,other_fields"
)


@dataclass
class PageResponse:
    url: str
    raw: bytes
    data: dict


class PlanItClient:
    """Polite HTTP client. Enforces an inter-request delay and backs off on 429."""

    def __init__(
        self,
        *,
        base: str = BASE,
        user_agent: str = USER_AGENT,
        delay_seconds: float = 2.5,
        backoff_seconds: float = 60.0,
        max_retries: int = 4,
    ):
        self.base = base
        self.delay = delay_seconds
        self.backoff = backoff_seconds  # base; doubles per attempt
        self.max_retries = max_retries
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30.0)
        self._next_request_at = 0.0

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "PlanItClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self._next_request_at:
            time.sleep(self._next_request_at - now)

    def get(self, path: str, params: dict) -> PageResponse:
        url = f"{self.base}{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(self.max_retries):
            self._wait()
            r = self.client.get(url)
            self._next_request_at = time.monotonic() + self.delay
            if r.status_code == 429:
                wait = self.backoff * (2 ** attempt)
                log.warning("429 from PlanIt (attempt %d/%d); backing off %.0fs",
                            attempt + 1, self.max_retries, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return PageResponse(url=url, raw=r.content, data=r.json())
        raise RuntimeError(f"persistent 429s after {self.max_retries} retries: {url}")

    def iter_areas(self, *, pg_sz: int = 200) -> Iterator[PageResponse]:
        page = 1
        while True:
            resp = self.get("/areas/json", {"pg_sz": pg_sz, "page": page, "select": AREAS_SELECT})
            yield resp
            if len(resp.data.get("records", [])) < pg_sz:
                return
            page += 1

    def iter_applications(
        self,
        *,
        search: str = DC_KEYWORDS,
        start_date: str | None = None,
        end_date: str | None = None,
        sort: str = "-start_date",
        pg_sz: int = 200,
    ) -> Iterator[PageResponse]:
        page = 1
        while True:
            params = {
                "search": search,
                "pg_sz": pg_sz,
                "page": page,
                "sort": sort,
                "select": APPS_SELECT,
            }
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            resp = self.get("/applics/json", params)
            yield resp
            if len(resp.data.get("records", [])) < pg_sz:
                return
            page += 1


def index(
    *,
    since: str = "2018-01-01",
    until: str | None = None,
    limit: int | None = None,
    delay_seconds: float = 2.5,
) -> dict:
    """Run a full index pass. Returns a summary dict."""
    summary = {
        "areas_pages": 0,
        "councils_upserted": 0,
        "application_pages": 0,
        "applications_upserted": 0,
        "snapshots_new": 0,
    }
    area_name_to_gss: dict[str, str] = {}

    with PlanItClient(delay_seconds=delay_seconds) as client, db.connect() as conn:
        source_id = repo.ensure_source(conn, name=SOURCE_NAME, kind="aggregator", base_url=BASE)

        log.info("areas pass: starting")
        for resp in client.iter_areas():
            summary["areas_pages"] += 1
            if repo.record_snapshot(conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw):
                summary["snapshots_new"] += 1
            for area in resp.data.get("records", []):
                gss = repo.upsert_council(conn, area)
                if gss:
                    summary["councils_upserted"] += 1
                    if area.get("area_name"):
                        area_name_to_gss[area["area_name"]] = gss
            conn.commit()

        log.info(
            "applications pass: starting (since=%s, until=%s, limit=%s)", since, until, limit
        )
        seen = 0
        for resp in client.iter_applications(start_date=since, end_date=until):
            summary["application_pages"] += 1
            if repo.record_snapshot(conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw):
                summary["snapshots_new"] += 1
            for app in resp.data.get("records", []):
                council_gss = area_name_to_gss.get(app.get("area_name") or "")
                repo.upsert_application(
                    conn, source_id=source_id, app=app, council_gss=council_gss
                )
                summary["applications_upserted"] += 1
                seen += 1
                if limit is not None and seen >= limit:
                    conn.commit()
                    return summary
            conn.commit()

    return summary
