"""Integration tests for dcp.repo against a real Postgres (dcp_test database).

These tests cover the SQL paths that the unit tests can't reach: ON CONFLICT
dedup, content-hash idempotency, the find_cached_response ordering and
status_code filter, and the upsert_council guard conditions.
"""

from __future__ import annotations

import pytest

from dcp import repo

pytestmark = pytest.mark.integration


@pytest.fixture
def planit_source_id(db_conn):
    return repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://www.planit.org.uk/api"
    )


# ---------------------------------------------------------------------------
# ensure_source
# ---------------------------------------------------------------------------


def test_ensure_source_is_idempotent(db_conn):
    a = repo.ensure_source(db_conn, name="planit", kind="aggregator", base_url="https://x")
    b = repo.ensure_source(db_conn, name="planit", kind="aggregator", base_url="https://x")
    assert a == b


def test_ensure_source_updates_base_url_on_conflict(db_conn):
    repo.ensure_source(db_conn, name="planit", kind="aggregator", base_url="https://old")
    repo.ensure_source(db_conn, name="planit", kind="aggregator", base_url="https://new")
    with db_conn.cursor() as cur:
        cur.execute("SELECT base_url FROM sources WHERE name = 'planit'")
        assert cur.fetchone()[0] == "https://new"


# ---------------------------------------------------------------------------
# record_snapshot
# ---------------------------------------------------------------------------


def test_record_snapshot_first_insert_returns_true(db_conn, planit_source_id):
    inserted = repo.record_snapshot(
        db_conn, source_id=planit_source_id, key="https://x/p1", raw_bytes=b'{"a": 1}'
    )
    assert inserted is True


def test_record_snapshot_same_content_dedups(db_conn, planit_source_id):
    repo.record_snapshot(
        db_conn, source_id=planit_source_id, key="https://x/p1", raw_bytes=b'{"a": 1}'
    )
    again = repo.record_snapshot(
        db_conn, source_id=planit_source_id, key="https://x/p1", raw_bytes=b'{"a": 1}'
    )
    assert again is False
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM source_snapshots WHERE source_id = %s",
            (planit_source_id,),
        )
        assert cur.fetchone()[0] == 1


def test_record_snapshot_different_content_creates_new_row(db_conn, planit_source_id):
    repo.record_snapshot(
        db_conn, source_id=planit_source_id, key="https://x/p1", raw_bytes=b'{"a": 1}'
    )
    diff = repo.record_snapshot(
        db_conn, source_id=planit_source_id, key="https://x/p1", raw_bytes=b'{"a": 2}'
    )
    assert diff is True
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM source_snapshots WHERE source_id = %s",
            (planit_source_id,),
        )
        assert cur.fetchone()[0] == 2


# ---------------------------------------------------------------------------
# upsert_council
# ---------------------------------------------------------------------------


def test_upsert_council_skips_missing_gss(db_conn):
    result = repo.upsert_council(
        db_conn, {"area_name": "X", "is_planning": True, "gss_code": None}
    )
    assert result is None
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM councils")
        assert cur.fetchone()[0] == 0


def test_upsert_council_skips_non_planning(db_conn):
    result = repo.upsert_council(
        db_conn,
        {"area_name": "X", "gss_code": "E12345678", "is_planning": False},
    )
    assert result is None


def test_upsert_council_inserts_valid_area(db_conn):
    gss = repo.upsert_council(
        db_conn,
        {
            "gss_code": "E06000057",
            "long_name": "Northumberland County Council",
            "area_name": "Northumberland (County)",
            "scraper_type": "Idox",
            "planning_url": "https://publicaccess.northumberland.gov.uk/online-applications/",
            "total": 104972,
            "min_date": "2000-01-05",
            "max_date": "2026-05-11",
            "is_planning": True,
        },
    )
    assert gss == "E06000057"
    with db_conn.cursor() as cur:
        cur.execute("SELECT name, portal_kind, base_url FROM councils WHERE gss_code = %s", (gss,))
        name, portal_kind, base_url = cur.fetchone()
        assert name == "Northumberland County Council"
        assert portal_kind == "idox"  # lowercased
        assert base_url.startswith("https://publicaccess.northumberland.gov.uk")


def test_upsert_council_updates_on_conflict(db_conn):
    repo.upsert_council(
        db_conn,
        {"gss_code": "E06000057", "area_name": "Old", "is_planning": True,
         "scraper_type": "Idox", "planning_url": "https://old"},
    )
    repo.upsert_council(
        db_conn,
        {"gss_code": "E06000057", "area_name": "New", "long_name": "New Council",
         "is_planning": True, "scraper_type": "Arcus", "planning_url": "https://new"},
    )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT name, portal_kind, base_url FROM councils WHERE gss_code = 'E06000057'"
        )
        name, portal_kind, base_url = cur.fetchone()
        assert name == "New Council"
        assert portal_kind == "arcus"
        assert base_url == "https://new"


# ---------------------------------------------------------------------------
# upsert_application
# ---------------------------------------------------------------------------


def _app_record(ref: str, **overrides):
    rec = {
        "name": ref,
        "uid": ref.split("/", 1)[-1],
        "area_name": "Northumberland (County)",
        "description": "Outline DC at former power station site",
        "address": "Cambois",
        "postcode": None,
        "start_date": "2024-11-28",
        "decided_date": None,
        "app_state": "Undecided",
        "app_type": "Outline",
        "app_size": "Large",
        "url": "https://publicaccess.northumberland.gov.uk/online-applications/...",
    }
    rec.update(overrides)
    return rec


def test_upsert_application_inserts(db_conn, planit_source_id):
    repo.upsert_application(
        db_conn,
        source_id=planit_source_id,
        app=_app_record("Northumberland/24/04112/OUTES"),
        council_gss=None,
    )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT description, status, date_received FROM applications "
            "WHERE source_id = %s AND application_ref = %s",
            (planit_source_id, "Northumberland/24/04112/OUTES"),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "Outline DC at former power station site"
        assert row[1] == "Undecided"


def test_upsert_application_dedups_on_ref_and_updates_description(db_conn, planit_source_id):
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("Northumberland/24/04112/OUTES", description="v1"),
    )
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("Northumberland/24/04112/OUTES", description="v2"),
    )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), max(description) FROM applications "
            "WHERE source_id = %s AND application_ref = %s",
            (planit_source_id, "Northumberland/24/04112/OUTES"),
        )
        count, description = cur.fetchone()
        assert count == 1
        assert description == "v2"


def test_upsert_application_council_gss_only_set_when_provided(db_conn, planit_source_id):
    """The ON CONFLICT clause uses COALESCE so a later upsert without a gss doesn't blank it."""
    repo.upsert_council(
        db_conn,
        {"gss_code": "E06000057", "area_name": "Northumberland (County)", "is_planning": True},
    )
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/123"),
        council_gss="E06000057",
    )
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/123"),
        council_gss=None,
    )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT council_gss FROM applications WHERE application_ref = %s", ("X/123",)
        )
        assert cur.fetchone()[0] == "E06000057"


# ---------------------------------------------------------------------------
# find_cached_response
# ---------------------------------------------------------------------------


def test_find_cached_response_missing_returns_none(db_conn, planit_source_id):
    assert repo.find_cached_response(
        db_conn, source_id=planit_source_id, key="https://nope"
    ) is None


def test_find_cached_response_returns_most_recent_success(db_conn, planit_source_id):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_snapshots
              (source_id, key, content_sha256, raw_bytes_inline, status_code, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (planit_source_id, "https://x", "hashA", b'{"v": 1}', 200, "2026-01-01 10:00:00+00"),
        )
        cur.execute(
            """
            INSERT INTO source_snapshots
              (source_id, key, content_sha256, raw_bytes_inline, status_code, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (planit_source_id, "https://x", "hashB", b'{"v": 2}', 200, "2026-02-01 10:00:00+00"),
        )
    assert repo.find_cached_response(
        db_conn, source_id=planit_source_id, key="https://x"
    ) == b'{"v": 2}'


def test_find_cached_response_ignores_non_200(db_conn, planit_source_id):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_snapshots
              (source_id, key, content_sha256, raw_bytes_inline, status_code, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (planit_source_id, "https://x", "hashOK", b'{"ok": true}', 200, "2026-01-01"),
        )
        cur.execute(
            """
            INSERT INTO source_snapshots
              (source_id, key, content_sha256, raw_bytes_inline, status_code, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (planit_source_id, "https://x", "hash429", b'rate limited', 429, "2026-02-01"),
        )
    # The 429 row is newer but find_cached_response should ignore it and return the 200 body.
    assert repo.find_cached_response(
        db_conn, source_id=planit_source_id, key="https://x"
    ) == b'{"ok": true}'


def test_find_cached_response_isolated_by_source(db_conn, planit_source_id):
    other_id = repo.ensure_source(db_conn, name="other", kind="aggregator", base_url="https://o")
    repo.record_snapshot(
        db_conn, source_id=other_id, key="https://shared", raw_bytes=b'other'
    )
    assert repo.find_cached_response(
        db_conn, source_id=planit_source_id, key="https://shared"
    ) is None


# ---------------------------------------------------------------------------
# discovered_via (migration 002)
# ---------------------------------------------------------------------------


def test_upsert_application_records_discovered_via(db_conn, planit_source_id):
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/1"),
        discovered_via=["dc_keyword"],
    )
    with db_conn.cursor() as cur:
        cur.execute("SELECT discovered_via FROM applications WHERE application_ref = %s", ("X/1",))
        assert cur.fetchone()[0] == ["dc_keyword"]


def test_append_discovered_via_tags_existing_refs(db_conn, planit_source_id):
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/1"), discovered_via=["dc_keyword"],
    )
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/2"), discovered_via=["dc_keyword"],
    )
    touched = repo.append_discovered_via(
        db_conn, application_refs=["X/1", "X/2", "X/NOTHERE"], tag="foxglove_top10",
    )
    assert touched == 2  # missing refs are silent no-ops
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT application_ref, discovered_via FROM applications "
            "WHERE application_ref IN ('X/1', 'X/2') ORDER BY application_ref"
        )
        rows = cur.fetchall()
    assert sorted(rows[0][1]) == ["dc_keyword", "foxglove_top10"]
    assert sorted(rows[1][1]) == ["dc_keyword", "foxglove_top10"]


def test_append_discovered_via_is_idempotent(db_conn, planit_source_id):
    """Re-running with the same tag doesn't duplicate the entry."""
    repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("X/1"),
        discovered_via=["dc_keyword"],
    )
    for _ in range(3):
        repo.append_discovered_via(
            db_conn, application_refs=["X/1"], tag="foxglove_top10",
        )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT discovered_via FROM applications WHERE application_ref = 'X/1'"
        )
        assert sorted(cur.fetchone()[0]) == ["dc_keyword", "foxglove_top10"]


def test_upsert_application_appends_discovered_via_on_conflict(db_conn, planit_source_id):
    """Same app discovered via two paths keeps both lineages, deduped."""
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/1"),
        discovered_via=["dc_keyword"],
    )
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/1"),
        discovered_via=["operator:Google"],
    )
    repo.upsert_application(
        db_conn, source_id=planit_source_id,
        app=_app_record("X/1"),
        discovered_via=["dc_keyword"],  # duplicate of first
    )
    with db_conn.cursor() as cur:
        cur.execute("SELECT discovered_via FROM applications WHERE application_ref = %s", ("X/1",))
        via = sorted(cur.fetchone()[0])
        assert via == ["dc_keyword", "operator:Google"]


def test_upsert_application_returns_row_id(db_conn, planit_source_id):
    aid = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("X/1"),
    )
    assert isinstance(aid, int) and aid > 0
    same = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("X/1"),
    )
    assert same == aid  # idempotent on conflict


# ---------------------------------------------------------------------------
# colocated_candidates (migration 002)
# ---------------------------------------------------------------------------


def test_upsert_colocated_candidate_inserts(db_conn, planit_source_id):
    anchor = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("anchor/1"),
    )
    cand = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("cand/1"),
    )
    repo.upsert_colocated_candidate(
        db_conn, anchor_app_id=anchor, candidate_app_id=cand,
        distance_m=420.5, radius_used_km=1.0, keyword_hits=["gas turbine", "CHP"],
    )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT distance_m, radius_used_km, keyword_hits FROM colocated_candidates "
            "WHERE anchor_app_id = %s",
            (anchor,),
        )
        d, r, hits = cur.fetchone()
        assert round(d, 1) == 420.5
        assert r == 1.0
        assert sorted(hits) == ["CHP", "gas turbine"]


def test_upsert_colocated_candidate_dedups_and_refreshes_keyword_hits(
    db_conn, planit_source_id
):
    anchor = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("anchor/1"),
    )
    cand = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("cand/1"),
    )
    repo.upsert_colocated_candidate(
        db_conn, anchor_app_id=anchor, candidate_app_id=cand,
        distance_m=500.0, radius_used_km=1.0, keyword_hits=["substation"],
    )
    # Re-run with new keyword set after lexicon refinement
    repo.upsert_colocated_candidate(
        db_conn, anchor_app_id=anchor, candidate_app_id=cand,
        distance_m=500.0, radius_used_km=1.0,
        keyword_hits=["gas turbine", "energy reserve"],
    )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), keyword_hits FROM colocated_candidates "
            "WHERE anchor_app_id = %s GROUP BY keyword_hits",
            (anchor,),
        )
        row = cur.fetchone()
        assert row[0] == 1  # one row only
        assert sorted(row[1]) == ["energy reserve", "gas turbine"]


def test_colocated_candidate_rejects_self_link(db_conn, planit_source_id):
    """The CHECK (anchor != candidate) constraint guards against bad spatial joins."""
    a = repo.upsert_application(
        db_conn, source_id=planit_source_id, app=_app_record("anchor/1"),
    )
    with pytest.raises(Exception):
        repo.upsert_colocated_candidate(
            db_conn, anchor_app_id=a, candidate_app_id=a,
            distance_m=0.0, radius_used_km=1.0, keyword_hits=["gas turbine"],
        )
