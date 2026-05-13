"""Planning Inspectorate NSIP register adapter (Phase 1e).

Source: https://national-infrastructure-consenting.planninginspectorate.gov.uk/api/applications-download
Format: text/csv, no auth, no rate limit observed, ~280 projects total.

DC universe is currently tiny — Wapseys Wood (SDC M40 Campus, EN0110030) is the
only confirmed DC NSIP project as of May 2026, classified under "EN01 -
Generating Stations" (instructive: DCs may be filed as generating stations
rather than as a separate type). We screen all rows for DC keywords in
Description / Project name to catch future cases regardless of type code.

See data/nsip_research/findings.md for the full source characterisation and
design notes (gov.uk Section 35 Directions watcher is a separate, weekly thing
not implemented here — build when journalism warrants).
"""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass

import httpx

from dcp import db, repo

log = logging.getLogger(__name__)

SOURCE_NAME = "nsip"
CSV_URL = (
    "https://national-infrastructure-consenting.planninginspectorate.gov.uk/"
    "api/applications-download"
)
PROJECT_URL_TEMPLATE = (
    "https://national-infrastructure-consenting.planninginspectorate.gov.uk/projects/{ref}"
)
USER_AGENT = "datacentre_planning research (luke.hoyland@gmail.com)"

# Same DC keyword union as PlanIt — scan description + project name. We don't
# filter by application type code because Wapseys Wood proves DCs can be filed
# as 'EN01 - Generating Stations' rather than under a DC-specific code.
DC_KEYWORDS = (
    "data centre", "data center", "data hall", "hyperscale",
    "datacentre", "colocation", "data park",
)


def _is_dc_relevant(row: dict) -> bool:
    blob = " ".join((row.get(k) or "") for k in ("Project name", "Description")).lower()
    return any(k in blob for k in DC_KEYWORDS)


def _parse_gps(s: str | None) -> tuple[float | None, float | None]:
    """The CSV's GPS column is leading-quoted to preserve the negative sign in CSV viewers,
    e.g. \"'-0.5945505216141749, 51.58726008957555\". Returns (lng, lat) — note order:
    the CSV gives longitude first, then latitude (matching the Easting/Northing column
    order)."""
    if not s:
        return None, None
    s = s.lstrip("'").strip()
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 2:
        return None, None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None, None


def _csv_row_to_app(row: dict) -> dict:
    """Map a CSV row into the shape expected by repo.upsert_application."""
    lng, lat = _parse_gps(row.get("GPS co-ordinates"))
    project_ref = row["Project reference"]
    return {
        "name": project_ref,  # NSIP project_ref is globally unique within the source
        "uid": project_ref,
        "description": row.get("Description") or row.get("Project name"),
        "address": row.get("Location"),
        "app_state": row.get("Stage"),
        "app_type": row.get("Application type"),
        "start_date": row.get("Date of application") or None,
        "decided_date": row.get("Date of decision") or None,
        "url": PROJECT_URL_TEMPLATE.format(ref=project_ref),
        "area_name": row.get("Region"),
        "location_x": lng,
        "location_y": lat,
        "other_fields": {
            "applicant_name": row.get("Applicant name"),
            "easting": row.get("Grid reference - Easting"),
            "northing": row.get("Grid reference - Northing:"),
            "anticipated_submission_period": row.get("Anticipated submission period"),
            "date_application_accepted": row.get("Date application accepted"),
            "date_examination_started": row.get("Date Examination started"),
            "examining_authority_close": row.get("Examining Authority's anticipated close of examination"),
            "date_examination_closed": row.get("Date Examination closed"),
            "date_recommendation": row.get("Date of recommendation"),
            "date_withdrawn": row.get("Date withdrawn"),
        },
    }


@dataclass
class _Response:
    url: str
    raw: bytes


def _fetch_csv(delay_seconds: float = 2.0) -> _Response:
    """Polite GET of the NSIP CSV download."""
    log.info("fetching NSIP CSV from %s", CSV_URL)
    r = httpx.get(CSV_URL, headers={"User-Agent": USER_AGENT}, timeout=60.0)
    r.raise_for_status()
    time.sleep(delay_seconds)
    return _Response(url=CSV_URL, raw=r.content)


def index(*, limit: int | None = None) -> dict:
    """Fetch the NSIP CSV, filter for DC-relevant rows, upsert into applications."""
    summary = {"rows_total": 0, "rows_dc_relevant": 0, "upserted": 0, "snapshots_new": 0}
    resp = _fetch_csv()
    rows = list(csv.DictReader(io.StringIO(resp.raw.decode("utf-8-sig"))))
    summary["rows_total"] = len(rows)

    with db.connect() as conn:
        source_id = repo.ensure_source(
            conn, name=SOURCE_NAME, kind="nsip",
            base_url="https://national-infrastructure-consenting.planninginspectorate.gov.uk/",
        )
        if repo.record_snapshot(
            conn, source_id=source_id, key=resp.url, raw_bytes=resp.raw
        ):
            summary["snapshots_new"] += 1

        dc_rows = [r for r in rows if _is_dc_relevant(r)]
        summary["rows_dc_relevant"] = len(dc_rows)
        if limit is not None:
            dc_rows = dc_rows[:limit]

        for row in dc_rows:
            app = _csv_row_to_app(row)
            repo.upsert_application(
                conn, source_id=source_id, app=app,
                council_gss=None,  # NSIP bypasses LPAs
                discovered_via=["nsip_register"],
            )
            summary["upserted"] += 1
        conn.commit()

    return summary
