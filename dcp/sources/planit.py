"""PlanIt API adapter (planit.org.uk).

Two passes per index run:
  1. /api/areas/  → populate councils table + build area_name → gss_code map.
  2. /api/applics/ → sweep applications matching the DC keyword union, since 2018.

Raw page responses land in source_snapshots, deduped by (source_id, url, content_sha256).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
from collections.abc import Callable, Iterator
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
    cached: bool = False


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
        cache_get: Callable[[str], bytes | None] | None = None,
    ):
        self.base = base
        self.delay = delay_seconds
        self.backoff = backoff_seconds  # base; doubles per attempt
        self.max_retries = max_retries
        self.cache_get = cache_get
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=90.0)
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
        if self.cache_get is not None:
            cached = self.cache_get(url)
            if cached is not None:
                log.debug("cache hit: %s", url)
                return PageResponse(url=url, raw=cached, data=json.loads(cached), cached=True)
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

    def iter_areas(self, *, pg_sz: int = 100) -> Iterator[PageResponse]:
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
        search: str | None = DC_KEYWORDS,
        developer: str | None = None,
        auth: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        sort: str = "-start_date",
        pg_sz: int = 100,
    ) -> Iterator[PageResponse]:
        """Iterate /api/applics/ pages. Any combination of `search` (description
        text), `developer` (applicant/agent fields), `auth` (council name) and
        the date range may be supplied. Pass `search=None` to disable the
        description filter."""
        page = 1
        while True:
            params: dict = {"pg_sz": pg_sz, "page": page, "sort": sort, "select": APPS_SELECT}
            if search is not None:
                params["search"] = search
            if developer is not None:
                params["developer"] = developer
            if auth is not None:
                params["auth"] = auth
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            resp = self.get("/applics/json", params)
            yield resp
            if len(resp.data.get("records", [])) < pg_sz:
                return
            page += 1

    def iter_by_spatial(
        self,
        *,
        lat: float,
        lng: float,
        krad: float,
        pg_sz: int = 200,
    ) -> Iterator[PageResponse]:
        """Iterate /api/applics/ pages within a `krad` km radius of (lat, lng)."""
        page = 1
        while True:
            params = {
                "lat": lat, "lng": lng, "krad": krad,
                "pg_sz": pg_sz, "page": page,
                "select": APPS_SELECT,
            }
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
    resume: bool = True,
) -> dict:
    """Run a full index pass. Returns a summary dict.

    If `resume` is True (default), URLs already captured in source_snapshots are
    served from the cached bytes and not re-fetched. Useful after a 429 wall:
    the prior pages are skipped and only the missing tail is requested.
    """
    summary = {
        "areas_pages": 0,
        "areas_pages_cached": 0,
        "councils_upserted": 0,
        "application_pages": 0,
        "application_pages_cached": 0,
        "applications_upserted": 0,
        "snapshots_new": 0,
    }
    area_name_to_gss: dict[str, str] = {}

    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=SOURCE_NAME, kind="aggregator", base_url=BASE)

        cache_get = None
        if resume:
            def cache_get(url: str) -> bytes | None:
                return repo.find_cached_response(conn, source_id=source_id, key=url)

        with PlanItClient(delay_seconds=delay_seconds, cache_get=cache_get) as client:
            log.info("areas pass: starting (resume=%s)", resume)
            for resp in client.iter_areas():
                summary["areas_pages"] += 1
                if resp.cached:
                    summary["areas_pages_cached"] += 1
                else:
                    if repo.record_snapshot(
                        conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw
                    ):
                        summary["snapshots_new"] += 1
                for area in resp.data.get("records", []):
                    gss = repo.upsert_council(conn, area)
                    if gss:
                        summary["councils_upserted"] += 1
                        if area.get("area_name"):
                            area_name_to_gss[area["area_name"]] = gss
                conn.commit()

            log.info(
                "applications pass: starting (since=%s, until=%s, limit=%s)",
                since, until, limit,
            )
            seen = 0
            for resp in client.iter_applications(start_date=since, end_date=until):
                summary["application_pages"] += 1
                if resp.cached:
                    summary["application_pages_cached"] += 1
                else:
                    if repo.record_snapshot(
                        conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw
                    ):
                        summary["snapshots_new"] += 1
                for app in resp.data.get("records", []):
                    council_gss = area_name_to_gss.get(app.get("area_name") or "")
                    repo.upsert_application(
                        conn, source_id=source_id, app=app, council_gss=council_gss,
                        discovered_via=["dc_keyword"],
                    )
                    summary["applications_upserted"] += 1
                    seen += 1
                    if limit is not None and seen >= limit:
                        conn.commit()
                        return summary
                conn.commit()

    return summary


def _load_area_gss_map(conn) -> dict[str, str]:
    """Build a current `area_name → gss_code` map from councils.notes (populated by the
    main index pass). Used by the operator and spatial sweeps to link applications
    to councils without re-running the areas pass."""
    out: dict[str, str] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT gss_code, notes FROM councils")
        for gss, notes in cur.fetchall():
            if notes and isinstance(notes, dict):
                an = notes.get("area_name")
                if an:
                    out[an] = gss
    return out


def index_by_developers(
    *,
    terms: list[str],
    co_search: str | None = DC_KEYWORDS,
    auth: str | None = None,
    limit_per_term: int | None = None,
    delay_seconds: float = 2.5,
    resume: bool = True,
) -> dict:
    """Phase 1d: sweep PlanIt by developer-name terms (matches applicant/agent
    address+company fields).

    **Important data-quality caveat (confirmed 2026-05-12):** PlanIt's
    `developer` search alone times out on their backend (>45s upstream
    timeout), and the `applicant_name`/`applicant_company` fields are
    mostly populated as "See source" — meaning only `agent_company` and
    `agent_address` reliably match. So this sweep is *narrower* than the
    name suggests: it catches applications where the *agent* matches a
    known developer/operator name, not necessarily where the *applicant*
    does.

    To stay under PlanIt's backend timeout, either `co_search` (a
    description-text co-filter) or `auth` (council name) must be
    supplied. Default behaviour combines `developer` with our DC keyword
    union — this still adds value by catching applications by known DC
    agents whose descriptions match DC terms even when the principal
    keyword sweep misses them. Pass `co_search=None` and provide `auth`
    for a per-council operator sweep instead.

    For broader operator-name discovery, source-portal scraping is
    needed (Phase 2 / per-portal adapters) — PlanIt's coverage of
    applicant data is too patchy.
    """
    if co_search is None and auth is None:
        raise ValueError(
            "index_by_developers needs either co_search or auth to avoid PlanIt's "
            "developer-only backend timeout"
        )
    summary = {
        "terms": len(terms),
        "pages": 0,
        "pages_cached": 0,
        "applications_upserted": 0,
        "snapshots_new": 0,
        "per_term": {},
    }

    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=SOURCE_NAME, kind="aggregator", base_url=BASE)
        area_to_gss = _load_area_gss_map(conn)
        cache_get = None
        if resume:
            def cache_get(url: str) -> bytes | None:
                return repo.find_cached_response(conn, source_id=source_id, key=url)

        with PlanItClient(delay_seconds=delay_seconds, cache_get=cache_get) as client:
            for term in terms:
                term_summary = {"pages": 0, "applications": 0}
                seen = 0
                stopped = False
                for resp in client.iter_applications(
                    search=co_search, developer=term, auth=auth if auth else None,
                ):
                    summary["pages"] += 1
                    term_summary["pages"] += 1
                    if resp.cached:
                        summary["pages_cached"] += 1
                    else:
                        if repo.record_snapshot(
                            conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw
                        ):
                            summary["snapshots_new"] += 1
                    for app in resp.data.get("records", []):
                        council_gss = area_to_gss.get(app.get("area_name") or "")
                        repo.upsert_application(
                            conn, source_id=source_id, app=app, council_gss=council_gss,
                            discovered_via=[f"operator:{term}"],
                        )
                        summary["applications_upserted"] += 1
                        term_summary["applications"] += 1
                        seen += 1
                        if limit_per_term is not None and seen >= limit_per_term:
                            stopped = True
                            break
                    conn.commit()
                    if stopped:
                        break
                summary["per_term"][term] = term_summary
                log.info("operator sweep done: %r → %s", term, term_summary)

    return summary


# Energy-generation keyword lexicon used by the spatial colocated sweep. Tweak in
# response to triage feedback — re-running process_colocated() with a different
# lexicon re-derives keyword_hits from the cached spatial responses without any
# new API calls.
ENERGY_KEYWORDS = (
    # primary generation
    "energy centre", "gas turbine", "CHP", "combined heat and power",
    "power station", "gas-fired", "gas fired", "biomass",
    "hydrogen", "fuel cell", "anaerobic digestion", "energy from waste", "EfW",
    "gas reciprocating engine", "reciprocating engine",
    # storage / behind-the-meter
    "BESS", "battery energy storage", "battery storage", "behind-the-meter",
    "energy reserve",
    # connection / infrastructure (noisy — flag but expect to filter)
    "substation", "grid connection",
)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _keyword_hits(text: str | None, keywords: tuple[str, ...] = ENERGY_KEYWORDS) -> list[str]:
    if not text:
        return []
    t = text.lower()
    return sorted({k for k in keywords if k.lower() in t})


PRIMARY_ANCHOR_APP_TYPES = ("Outline", "Full")


def fetch_colocated(
    *,
    radius_km: float = 1.0,
    limit_anchors: int | None = None,
    delay_seconds: float = 2.5,
    resume: bool = True,
    anchor_filter: str = "dc_keyword",
    app_types: tuple[str, ...] = PRIMARY_ANCHOR_APP_TYPES,
) -> dict:
    """Phase 1c (fetch half): for each DC anchor application, fetch all PlanIt
    applications within radius_km of its location and persist the raw response in
    source_snapshots. Filtering / candidate-link insertion is a separate pass
    (see process_colocated) so vocabulary changes don't require re-fetching.

    Only anchors whose `discovered_via` contains `anchor_filter` AND whose
    `raw_metadata.app_type` is in `app_types` are swept — defaults filter to
    Outline / Full DC keyword anchors only, excluding Conditions / Amendment
    discharges that share coordinates with their parent (we already fetch
    the parent's neighbours once).

    Anchors are deduplicated by (lat, lng): multiple application records at
    the same site share the same spatial cache, so we fetch once per unique
    location and let process_colocated() resolve all matching anchors.
    """
    summary = {"anchors_attempted": 0, "anchors_done": 0, "pages": 0,
               "pages_cached": 0, "snapshots_new": 0, "anchors_skipped_no_loc": 0,
               "unique_locations": 0}

    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=SOURCE_NAME, kind="aggregator", base_url=BASE)
        cache_get = None
        if resume:
            def cache_get(url: str) -> bytes | None:
                return repo.find_cached_response(conn, source_id=source_id, key=url)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, application_ref, lat, lng FROM (
                    SELECT DISTINCT ON ((raw_metadata->>'location_x'), (raw_metadata->>'location_y'))
                           id, application_ref,
                           (raw_metadata->>'location_y')::float AS lat,
                           (raw_metadata->>'location_x')::float AS lng,
                           date_received
                    FROM applications
                    WHERE %s = ANY(discovered_via)
                      AND raw_metadata->>'location_x' IS NOT NULL
                      AND raw_metadata->>'location_y' IS NOT NULL
                      AND raw_metadata->>'app_type' = ANY(%s)
                    ORDER BY (raw_metadata->>'location_x'), (raw_metadata->>'location_y'),
                             date_received DESC NULLS LAST, id
                ) deduped
                ORDER BY date_received DESC NULLS LAST, id
                """,
                (anchor_filter, list(app_types)),
            )
            anchors = cur.fetchall()
            summary["unique_locations"] = len(anchors)

        if limit_anchors is not None:
            anchors = anchors[:limit_anchors]

        with PlanItClient(delay_seconds=delay_seconds, cache_get=cache_get) as client:
            for anchor_id, ref, lat, lng in anchors:
                summary["anchors_attempted"] += 1
                if lat is None or lng is None:
                    summary["anchors_skipped_no_loc"] += 1
                    continue
                try:
                    for resp in client.iter_by_spatial(lat=lat, lng=lng, krad=radius_km):
                        summary["pages"] += 1
                        if resp.cached:
                            summary["pages_cached"] += 1
                        else:
                            if repo.record_snapshot(
                                conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw
                            ):
                                summary["snapshots_new"] += 1
                    summary["anchors_done"] += 1
                    conn.commit()
                except Exception as e:
                    log.warning("spatial fetch failed for anchor %s (%s): %s", anchor_id, ref, e)
                    conn.rollback()

    return summary


def process_colocated(
    *,
    radius_km: float = 1.0,
    keywords: tuple[str, ...] = ENERGY_KEYWORDS,
    anchor_filter: str = "dc_keyword",
) -> dict:
    """Phase 1c (process half): read cached spatial responses from source_snapshots,
    apply the energy-keyword filter, upsert matched candidates into applications
    (tagged via 'spatial:<anchor_ref>') and create colocated_candidates links.

    This is the loop to re-run when the keyword lexicon changes — no API hits.
    """
    summary = {"anchors_processed": 0, "candidates_inserted": 0,
               "candidates_skipped_no_keywords": 0, "candidates_skipped_self": 0}

    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=SOURCE_NAME, kind="aggregator", base_url=BASE)
        area_to_gss = _load_area_gss_map(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, application_ref,
                       (raw_metadata->>'location_y')::float AS lat,
                       (raw_metadata->>'location_x')::float AS lng
                FROM applications
                WHERE %s = ANY(discovered_via)
                  AND raw_metadata->>'location_x' IS NOT NULL
                  AND raw_metadata->>'location_y' IS NOT NULL
                ORDER BY id
                """,
                (anchor_filter,),
            )
            anchors = cur.fetchall()

        for anchor_id, anchor_ref, anchor_lat, anchor_lng in anchors:
            # Find cached pages for this anchor by URL pattern. Spatial URLs
            # contain lat= and lng= literals matching the anchor.
            url_like = f"%lat={anchor_lat}&lng={anchor_lng}&krad={radius_km}%"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT raw_bytes_inline FROM source_snapshots
                    WHERE source_id = %s AND status_code = 200
                      AND key LIKE %s
                      AND raw_bytes_inline IS NOT NULL
                    ORDER BY fetched_at ASC
                    """,
                    (source_id, url_like),
                )
                pages = [bytes(r[0]) for r in cur.fetchall()]
            if not pages:
                continue
            summary["anchors_processed"] += 1

            import json as _json
            seen_refs: set[str] = set()
            for raw in pages:
                data = _json.loads(raw)
                for rec in data.get("records", []):
                    cand_ref = rec.get("name")
                    if not cand_ref:
                        continue
                    if cand_ref == anchor_ref:
                        summary["candidates_skipped_self"] += 1
                        continue
                    if cand_ref in seen_refs:
                        continue
                    seen_refs.add(cand_ref)

                    hits = sorted(set(
                        _keyword_hits(rec.get("description")) + _keyword_hits(rec.get("address"))
                    ))
                    if not hits:
                        summary["candidates_skipped_no_keywords"] += 1
                        continue

                    cand_lat = rec.get("location_y")
                    cand_lng = rec.get("location_x")
                    distance_m = None
                    if cand_lat is not None and cand_lng is not None:
                        distance_m = _haversine_m(anchor_lat, anchor_lng, float(cand_lat), float(cand_lng))

                    council_gss = area_to_gss.get(rec.get("area_name") or "")
                    cand_id = repo.upsert_application(
                        conn, source_id=source_id, app=rec, council_gss=council_gss,
                        discovered_via=[f"spatial:{anchor_ref}"],
                    )
                    repo.upsert_colocated_candidate(
                        conn,
                        anchor_app_id=anchor_id,
                        candidate_app_id=cand_id,
                        distance_m=distance_m,
                        radius_used_km=radius_km,
                        keyword_hits=hits,
                    )
                    summary["candidates_inserted"] += 1
            conn.commit()

    return summary
