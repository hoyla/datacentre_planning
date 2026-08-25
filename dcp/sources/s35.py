"""Gov.uk Section 35 Directions watcher (the nsip_research "Adapter 2").

A Section 35 Direction is the earliest public signal that a project is
headed for the NSIP regime: it precedes the DCO application — and hence
the NSIP register row that dcp/sources/nsip.py ingests — by months. Data
centres became eligible for direction in January 2026; by August 2026
three DC campuses held directions (Wapseys Wood in March, Ampthill
Road/Quest Park in June, New Barn Road Dartford in July) while the
register carried only the first. The other two were invisible to every
adapter until this one. See data/nsip_research/findings.md for the
source characterisation and the bridge problem (an S35 stub gains its
PINS project ref only when the DCO is later filed).

Discovery is the gov.uk Search API; each DC-relevant hit's publication
page is then fetched from the Content API (title, dates, attachment
metadata) and upserted as a stub application with
discovered_via=['s35_direction']. No filter_format parameter: the
directions are published as format 'decision', not 'publication', so
the format filter sketched in the May research would have excluded all
three. Non-DC hits (guidance pages, pipelines, rail terminals) fall to
the same DC keyword screen the register adapter uses.

Attachment PDFs are not fetched here — their titles/URLs/sizes land in
raw_metadata.other_fields.attachments and the page JSON is snapshotted,
so acquisition can follow up without re-discovering anything.
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from dcp import db, repo
from dcp.sources.nsip import DC_KEYWORDS, USER_AGENT

log = logging.getLogger(__name__)

SOURCE_NAME = "s35_directions"
SEARCH_URL = "https://www.gov.uk/api/search.json"
SEARCH_QUERY = '"section 35 direction"'
SEARCH_FIELDS = "title,link,content_id,public_timestamp,format,description"
SEARCH_PAGE_SIZE = 100
CONTENT_URL_TEMPLATE = "https://www.gov.uk/api/content{base_path}"
PUBLIC_URL_TEMPLATE = "https://www.gov.uk{base_path}"


def _is_dc_relevant(*texts: str | None) -> bool:
    blob = " ".join(t or "" for t in texts).lower()
    return any(k in blob for k in DC_KEYWORDS)


def _slug(base_path: str) -> str:
    """The last path segment of a gov.uk base_path is the publication's
    stable human-readable slug — our application_ref for the stub."""
    return base_path.rstrip("/").rsplit("/", 1)[-1]


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str | None) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html or "")).strip()


def _page_to_app(page: dict) -> dict:
    """Map a gov.uk Content API publication page into the shape expected
    by repo.upsert_application."""
    base_path = page["base_path"]
    details = page.get("details") or {}
    body_text = _strip_html(details.get("body"))
    description = ". ".join(
        x for x in (page.get("title"), page.get("description")) if x
    )
    if body_text:
        description = f"{description}. {body_text[:1500]}"
    first_published = page.get("first_published_at") or ""
    return {
        "name": _slug(base_path),
        "uid": _slug(base_path),
        "description": description,
        # The title is the only location the source gives; there is no
        # structured address field to promote.
        "address": None,
        "app_state": "Section 35 Direction",
        "app_type": details.get("document_type_label") or page.get("document_type"),
        "start_date": first_published[:10] or None,  # publication date of the direction
        "decided_date": None,
        "url": PUBLIC_URL_TEMPLATE.format(base_path=base_path),
        "other_fields": {
            "content_id": page.get("content_id"),
            "base_path": base_path,
            "first_published_at": page.get("first_published_at"),
            "public_updated_at": page.get("public_updated_at"),
            "attachments": [
                {
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "content_type": a.get("content_type"),
                    "file_size": a.get("file_size"),
                }
                for a in details.get("attachments", [])
            ],
        },
    }


def _get(url: str, params: dict | None = None) -> httpx.Response:
    r = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT},
                  timeout=60.0, follow_redirects=True)
    r.raise_for_status()
    return r


def _search_all(delay_seconds: float) -> tuple[list[tuple[str, bytes]], list[dict]]:
    """Page through the Search API. Returns ([(snapshot_key, raw_bytes)...],
    [result dict...])."""
    snapshots: list[tuple[str, bytes]] = []
    results: list[dict] = []
    start = 0
    while True:
        params = {
            "q": SEARCH_QUERY,
            "count": SEARCH_PAGE_SIZE,
            "start": start,
            "order": "-public_timestamp",
            "fields": SEARCH_FIELDS,
        }
        resp = _get(SEARCH_URL, params=params)
        snapshots.append((str(resp.url), resp.content))
        payload = resp.json()
        page_results = payload.get("results", [])
        results.extend(page_results)
        total = payload.get("total", 0)
        start += len(page_results)
        if not page_results or start >= total:
            return snapshots, results
        time.sleep(delay_seconds)


def index(*, limit: int | None = None, resume: bool = True,
          delay_seconds: float = 2.0) -> dict:
    """Poll gov.uk for Section 35 Directions and upsert DC-relevant stubs.

    The search response is always fetched live (it is the poll); the
    per-publication Content API pages are served from the snapshot cache
    when `resume` is true, so a re-run is free until gov.uk publishes
    something new. Re-runs are no-ops on unchanged content throughout
    (content-hash dedup on snapshots, ON CONFLICT upsert on applications).
    """
    summary = {"results_total": 0, "results_dc_relevant": 0,
               "pages_fetched": 0, "pages_from_cache": 0,
               "upserted": 0, "snapshots_new": 0}
    search_snapshots, results = _search_all(delay_seconds)
    summary["results_total"] = len(results)

    dc_results = [r for r in results
                  if _is_dc_relevant(r.get("title"), r.get("description"))]
    summary["results_dc_relevant"] = len(dc_results)
    if limit is not None:
        dc_results = dc_results[:limit]

    with db.connect() as conn:
        source_id = repo.ensure_source(
            conn, name=SOURCE_NAME, kind="s35", base_url="https://www.gov.uk/",
        )
        for key, raw in search_snapshots:
            if repo.record_snapshot(conn, source_id=source_id, key=key,
                                    raw_bytes=raw):
                summary["snapshots_new"] += 1

        for result in dc_results:
            content_url = CONTENT_URL_TEMPLATE.format(base_path=result["link"])
            raw = repo.find_cached_response(
                conn, source_id=source_id, key=content_url) if resume else None
            if raw is not None:
                summary["pages_from_cache"] += 1
            else:
                log.info("fetching %s", content_url)
                raw = _get(content_url).content
                summary["pages_fetched"] += 1
                if repo.record_snapshot(conn, source_id=source_id,
                                        key=content_url, raw_bytes=raw):
                    summary["snapshots_new"] += 1
                time.sleep(delay_seconds)
            page = json.loads(raw)
            app = _page_to_app(page)
            repo.upsert_application(
                conn, source_id=source_id, app=app,
                council_gss=None,  # a section 35 direction bypasses the LPA
                discovered_via=["s35_direction"],
            )
            summary["upserted"] += 1
        conn.commit()

    return summary
