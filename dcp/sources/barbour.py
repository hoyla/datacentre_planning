"""Barbour ABI construction-projects adapter.

Source: a Barbour ABI xlsx export supplied by the Guardian data-journalism
team (licensed for use; credit Barbour ABI in published output). Not an API —
the workbook is ingested from disk and snapshotted verbatim into
source_snapshots first, so the ingest is reproducible even if the file moves.

Barbour's unit of record is the construction *project*, not the planning
application: the export mixes pre-planning schemes with no application yet,
live applications, under-construction sites, built estates with pre-2018
references, and construction contracts (fit-outs, civil works, tenders) that
will never have a substantive planning application. Rows land in the
`projects` table with the full source row in raw_metadata; the ref-matching
pass links each project to already-ingested `applications` rows via
`project_applications` (never auto-linking ambiguous bare refs).

Known data hazards, observed in the 2026-08 export:
- `planning_link` rots — councils migrate portals (Harlow's communitymap
  domain no longer resolves; Havering and Slough moved). Treat
  `authority_name` + `planning_ref` as the durable key, the link as a hint.
- The sheet's own coverage column ("Luke has?") is unreliable — matching is
  done fresh against our own refs.
- `planning_ref` sometimes holds a "FIND A TENDER REF:..." procurement id,
  which is not a planning reference and will simply not match.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl

from dcp import db, repo

log = logging.getLogger(__name__)

SOURCE_NAME = "barbour_abi"
SHEET_NAME = "Data Centres"


def _clean(v: Any) -> str | None:
    """Cell value → stripped string, with None for empty/placeholder cells."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s not in (".", ". ") else None


def _as_number(v: Any) -> float | None:
    """Cell value → float, treating Barbour's 0.0 placeholder as absent."""
    if v is None:
        return None
    try:
        n = float(str(v).strip())
    except ValueError:
        return None
    return n if n != 0.0 else None


def _as_id(v: Any) -> str | None:
    """Numeric-looking id cell ('12871423.0' or 12871423.0) → '12871423'."""
    s = _clean(v)
    if s is None:
        return None
    if re.fullmatch(r"\d+(\.0+)?", s):
        return s.split(".")[0]
    return s


def _as_date(v: Any) -> date | None:
    """Cell value → date. openpyxl yields datetime for date-formatted cells;
    ISO-formatted strings are accepted as a fallback."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _jsonable(v: Any) -> Any:
    """Raw-row value → something JSONB can hold, verbatim in spirit."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _row_to_project(row: tuple, ix: dict[str, int]) -> dict[str, Any] | None:
    """Map a worksheet row to the shape expected by repo.upsert_project.

    Returns None for blank rows or rows with no Ptno (nothing to key on).
    The full row travels in raw_metadata keyed by the original headers, so
    the 300+ un-promoted columns (role blocks, category codes, precision
    flags) stay queryable without schema changes.
    """

    def cell(name: str) -> Any:
        return row[ix[name]] if name in ix and ix[name] < len(row) else None

    external_ref = _as_id(cell("Ptno"))
    if external_ref is None:
        return None

    address = ", ".join(
        s for s in (_clean(cell(c)) for c in ("Site1", "Site2", "Site3", "Site4")) if s
    ) or None

    raw = {name: _jsonable(row[i]) for name, i in ix.items() if i < len(row)}

    return {
        "external_ref": external_ref,
        "title": _clean(cell("Title")),
        "stage_summary": _clean(cell("Stage summary")),
        "dev_type": _clean(cell("Devtype")),
        "description": _clean(cell("Details")),
        "address": address,
        "postcode": _clean(cell("Pcode")),
        "longitude": _as_number(cell("Longitude")),
        "latitude": _as_number(cell("Latitude")),
        "value_gbp": _as_number(cell("Value")),
        "floor_area": _as_number(cell("Floor_area")),
        "site_area": _as_number(cell("Site_area")),
        "authority_name": _clean(cell("Authority")),
        "planning_ref": _clean(cell("planning_ref")),
        "planning_link": _clean(cell("planning_link")),
        "plan_date": _as_date(cell("Plan_date")),
        "decision_date": _as_date(cell("Decision date")),
        "start_date": _as_date(cell("Start_date")),
        "completion_date": _as_date(cell("Completion_date")),
        "url": _clean(cell("Barbour_ABI_link")),
        "raw_metadata": raw,
    }


def match_applications(
    planning_ref: str, app_refs: list[tuple[int, str]]
) -> tuple[list[int], str | None]:
    """Match a bare provider ref against our (id, application_ref) universe.

    Our refs are 'Council/ref' (PlanIt convention); Barbour's are bare. Two
    tiers: exact suffix match ('/'-boundary, case-insensitive), then a
    normalised match with separators stripped. Returns (matched_ids, method).
    More than one hit → ([ids], method) too — the caller decides not to link
    ambiguous matches, but gets the candidates for reporting.
    """
    want = planning_ref.upper()
    hits = [i for i, r in app_refs if r.upper() == want or r.upper().endswith("/" + want)]
    if hits:
        return hits, "ref_suffix"
    norm = re.sub(r"[^A-Z0-9]", "", want)
    if norm:
        hits = [
            i for i, r in app_refs
            if re.sub(r"[^A-Z0-9]", "", (r.split("/", 1)[1] if "/" in r else r).upper()) == norm
        ]
        if hits:
            return hits, "ref_normalised"
    return [], None


def ingest(conn, *, path: Path, limit: int | None = None) -> dict:
    """Core ingest against an open connection (separable for tests).

    Snapshot the workbook, upsert every project row, then link projects to
    already-ingested applications by planning_ref. Idempotent: re-running on
    an unchanged file dedups the snapshot, refreshes project rows in place,
    and no-ops existing links.
    """
    summary = {
        "rows_total": 0,
        "projects_upserted": 0,
        "linked": 0,
        "links_new": 0,
        "ambiguous_refs": 0,
        "unmatched_refs": 0,
        "no_ref": 0,
        "snapshots_new": 0,
    }

    raw_bytes = path.read_bytes()
    source_id = repo.ensure_source(
        conn, name=SOURCE_NAME, kind="commercial",
        base_url="https://barbour-abi.com/",
    )
    if repo.record_snapshot(
        conn, source_id=source_id, key=f"file:{path.name}", raw_bytes=raw_bytes
    ):
        summary["snapshots_new"] += 1

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    ix = {h: i for i, h in enumerate(header) if h is not None}

    with conn.cursor() as cur:
        cur.execute("SELECT id, application_ref FROM applications")
        app_refs = [(r[0], r[1]) for r in cur.fetchall()]

    for row in rows:
        if not any(c is not None for c in row):
            continue
        project = _row_to_project(row, ix)
        if project is None:
            continue
        summary["rows_total"] += 1
        if limit is not None and summary["projects_upserted"] >= limit:
            break
        project_id = repo.upsert_project(conn, source_id=source_id, project=project)
        summary["projects_upserted"] += 1

        ref = project["planning_ref"]
        if not ref:
            summary["no_ref"] += 1
            continue
        matched_ids, method = match_applications(ref, app_refs)
        if not matched_ids:
            summary["unmatched_refs"] += 1
        elif len(matched_ids) > 1:
            # Same bare ref exists in more than one council — a human call,
            # never an auto-link. Surfaced in the summary for manual curation.
            summary["ambiguous_refs"] += 1
            log.warning("ambiguous ref %r matches %d applications; not linking",
                        ref, len(matched_ids))
        else:
            summary["linked"] += 1
            if repo.link_project_application(
                conn, project_id=project_id, application_id=matched_ids[0],
                match_method=method,
            ):
                summary["links_new"] += 1

    conn.commit()
    return summary


def index(*, path: Path, limit: int | None = None) -> dict:
    """CLI entry point: open a connection and run the ingest."""
    with db.connect() as conn:
        return ingest(conn, path=path, limit=limit)
