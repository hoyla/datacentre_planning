"""Tests for the Barbour ABI construction-projects adapter.

Unit tests cover the cell coercions, row mapping, and the two-tier ref
matcher. The integration test drives the full ingest (snapshot + project
upsert + application linking) against dcp_test with a synthetic workbook,
including the idempotent-rerun contract.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from dcp import repo
from dcp.sources import barbour


# ---------------------------------------------------------------------------
# Cell coercions
# ---------------------------------------------------------------------------


def test_as_id_strips_float_artifact():
    assert barbour._as_id("12871423.0") == "12871423"
    assert barbour._as_id(12871423.0) == "12871423"
    assert barbour._as_id("T/153") == "T/153"
    assert barbour._as_id(None) is None


def test_as_number_treats_zero_as_absent():
    # Barbour uses 0.0 as its empty marker for Value / areas — a genuine zero
    # (a zero-value construction project) doesn't occur in this data.
    assert barbour._as_number("0.0") is None
    assert barbour._as_number(0) is None
    assert barbour._as_number("3642300.0") == 3642300.0
    assert barbour._as_number("garbage") is None


def test_as_date_handles_datetime_and_iso_strings():
    assert barbour._as_date(datetime(2026, 6, 10, 0, 0)) == date(2026, 6, 10)
    assert barbour._as_date("2025-09-16 00:00:00") == date(2025, 9, 16)
    assert barbour._as_date(None) is None
    assert barbour._as_date("not a date") is None


def test_clean_drops_placeholder_dots():
    # Barbour's Status column uses '. ' as its empty marker.
    assert barbour._clean(". ") is None
    assert barbour._clean(" x ") == "x"


# ---------------------------------------------------------------------------
# Row mapping
# ---------------------------------------------------------------------------

HEADERS = [
    "Ptno", "Title", "Stage summary", "Devtype", "Details",
    "Site1", "Site2", "Site3", "Site4", "Pcode",
    "Longitude", "Latitude", "Value", "Floor_area", "Site_area",
    "Authority", "planning_ref", "planning_link",
    "Plan_date", "Decision date", "Start_date", "Completion_date",
    "Barbour_ABI_link", "PnEmail_Client",
]


def _make_row(**overrides):
    base = {h: None for h in HEADERS}
    base.update(overrides)
    return tuple(base[h] for h in HEADERS)


def _ix():
    return {h: i for i, h in enumerate(HEADERS)}


def test_row_to_project_maps_promoted_columns():
    row = _make_row(
        **{
            "Ptno": "12871423.0",
            "Title": "COTTAM 1GW CAMPUS",
            "Stage summary": "Pre Planning",
            "Site1": "Former Cottam Power Station",
            "Site2": "Retford",
            "Pcode": "DN22 0QQ",
            "Longitude": "-0.935937",
            "Latitude": "53.280062",
            "Value": "12000000000.0",
            "planning_ref": "25/03310/REM",
            "Plan_date": datetime(2025, 9, 16),
            "Barbour_ABI_link": "https://app.barbour-abi.com/app/project/12871423",
            "PnEmail_Client": "someone@example.com",
        }
    )
    p = barbour._row_to_project(row, _ix())
    assert p["external_ref"] == "12871423"
    assert p["title"] == "COTTAM 1GW CAMPUS"
    assert p["address"] == "Former Cottam Power Station, Retford"
    assert p["longitude"] == pytest.approx(-0.935937)
    assert p["value_gbp"] == pytest.approx(12e9)
    assert p["plan_date"] == date(2025, 9, 16)
    # Un-promoted columns travel verbatim in raw_metadata, dates ISO-ified.
    assert p["raw_metadata"]["PnEmail_Client"] == "someone@example.com"
    assert p["raw_metadata"]["Plan_date"] == "2025-09-16T00:00:00"


def test_row_to_project_returns_none_without_ptno():
    assert barbour._row_to_project(_make_row(Title="NO ID"), _ix()) is None


# ---------------------------------------------------------------------------
# Ref matching
# ---------------------------------------------------------------------------

APP_REFS = [
    (1, "Cherwell/25/03310/REM"),
    (2, "EastRiding/16/02800/STPLF"),
    (3, "Slough/T/153"),
    (4, "Newport/15/0231"),
    (5, "Cardiff/15/0231"),
]


def test_match_suffix_boundary():
    ids, method = barbour.match_applications("25/03310/REM", APP_REFS)
    assert ids == [1] and method == "ref_suffix"
    # A bare ref must match at a '/' boundary, not mid-string:
    ids, _ = barbour.match_applications("3310/REM", APP_REFS)
    assert ids == []


def test_match_is_case_insensitive():
    ids, method = barbour.match_applications("t/153", APP_REFS)
    assert ids == [3] and method == "ref_suffix"


def test_match_normalised_tier():
    # Separator drift (dots vs slashes) falls through to the normalised tier.
    ids, method = barbour.match_applications("25.03310.REM", APP_REFS)
    assert ids == [1] and method == "ref_normalised"


def test_match_ambiguous_returns_all_candidates():
    ids, method = barbour.match_applications("15/0231", APP_REFS)
    assert sorted(ids) == [4, 5] and method == "ref_suffix"


def test_match_no_hit():
    ids, method = barbour.match_applications("FIND A TENDER REF:2025/S", APP_REFS)
    assert ids == [] and method is None


# ---------------------------------------------------------------------------
# Integration: full ingest against dcp_test
# ---------------------------------------------------------------------------


def _write_workbook(path: Path, rows: list[dict]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = barbour.SHEET_NAME
    ws.append(HEADERS)
    for r in rows:
        base = {h: None for h in HEADERS}
        base.update(r)
        ws.append([base[h] for h in HEADERS])
    wb.save(path)


@pytest.mark.integration
def test_ingest_end_to_end(db_conn, tmp_path):
    planit_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x"
    )
    app_id = repo.upsert_application(
        db_conn, source_id=planit_id,
        app={"name": "Cherwell/25/03310/REM", "description": "dc"},
        discovered_via=["dc_keyword"],
    )

    xlsx = tmp_path / "barbour.xlsx"
    _write_workbook(xlsx, [
        {"Ptno": "111.0", "Title": "LINKED", "planning_ref": "25/03310/REM"},
        {"Ptno": "222.0", "Title": "UNMATCHED", "planning_ref": "99/9999/ZZZ"},
        {"Ptno": "333.0", "Title": "PREPLANNING"},
    ])

    summary = barbour.ingest(db_conn, path=xlsx)
    assert summary["rows_total"] == 3
    assert summary["projects_upserted"] == 3
    assert summary["linked"] == 1 and summary["links_new"] == 1
    assert summary["unmatched_refs"] == 1
    assert summary["no_ref"] == 1
    assert summary["snapshots_new"] == 1

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT p.external_ref, pa.application_id, pa.match_method "
            "FROM project_applications pa JOIN projects p ON p.id = pa.project_id"
        )
        links = cur.fetchall()
    assert links == [("111", app_id, "ref_suffix")]

    # Rerun on the unchanged file: snapshot dedups, projects refresh in
    # place, links no-op — the whole pass is idempotent.
    again = barbour.ingest(db_conn, path=xlsx)
    assert again["snapshots_new"] == 0
    assert again["projects_upserted"] == 3
    assert again["links_new"] == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM projects")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT count(*) FROM project_applications")
        assert cur.fetchone()[0] == 1


@pytest.mark.integration
def test_ingest_never_links_ambiguous_refs(db_conn, tmp_path):
    planit_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x"
    )
    for council in ("Newport", "Cardiff"):
        repo.upsert_application(
            db_conn, source_id=planit_id,
            app={"name": f"{council}/15/0231", "description": "dc"},
            discovered_via=["dc_keyword"],
        )

    xlsx = tmp_path / "barbour.xlsx"
    _write_workbook(xlsx, [{"Ptno": "444.0", "Title": "AMBIG", "planning_ref": "15/0231"}])

    summary = barbour.ingest(db_conn, path=xlsx)
    assert summary["ambiguous_refs"] == 1
    assert summary["linked"] == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM project_applications")
        assert cur.fetchone()[0] == 0
