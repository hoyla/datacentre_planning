"""Integration tests for council-reorganisation handling.

Migration 004 fixes the TEXT-vs-JSONB bug on `councils.notes` and adds the
`council_aliases` table. The backfill function walks NULL `council_gss`
applications and matches them against either a current council (via
`notes->area_name`) or an alias entry. Tests confirm both paths fire and
that unmapped MDC-style names stay NULL by design.
"""

from __future__ import annotations

import pytest

from dcp import repo


pytestmark = pytest.mark.integration


def _seed_council(db_conn, gss, name, area_name):
    """Use the public upsert_council path so we exercise the same Json adapter
    the production code uses — proves the JSONB column is the right type."""
    repo.upsert_council(db_conn, {
        "gss_code": gss, "long_name": name, "area_name": area_name,
        "is_planning": True, "scraper_type": "Idox",
        "planning_url": f"https://example.invalid/{gss}",
    })


def _seed_app(db_conn, source_id, ref, area_name):
    return repo.upsert_application(
        db_conn, source_id=source_id,
        app={
            "name": ref, "uid": ref.split("/", 1)[-1],
            "area_name": area_name, "description": "x",
            "address": "x", "postcode": None,
            "start_date": "2024-01-01", "decided_date": None,
            "app_state": "Undecided", "app_type": "Outline", "app_size": "Large",
            "url": "https://example.invalid/app",
        },
    )


def _seed_alias(db_conn, alias_name, gss_code, kind):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO council_aliases (alias_name, gss_code, kind) VALUES (%s, %s, %s)",
            (alias_name, gss_code, kind),
        )


def test_councils_notes_is_jsonb_after_migration(db_conn):
    """Regression guard: the migration converts notes to JSONB so JSON path
    operators (and `isinstance(notes, dict)` from psycopg2) work."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'councils' AND column_name = 'notes'"
        )
        assert cur.fetchone()[0] == "jsonb"


def test_upsert_council_persists_dict_round_trip(db_conn):
    """The Json adapter writes a dict to JSONB and a SELECT returns a dict —
    the bug that motivated migration 004 was that this round-trip silently
    produced a string when the column was TEXT."""
    _seed_council(db_conn, "E06000057", "Northumberland", "Northumberland (County)")
    with db_conn.cursor() as cur:
        cur.execute("SELECT notes FROM councils WHERE gss_code = 'E06000057'")
        notes = cur.fetchone()[0]
    assert isinstance(notes, dict)
    assert notes["area_name"] == "Northumberland (County)"


def test_backfill_council_gss_matches_current_council(db_conn):
    """Direct match: an application's area_name equals a council's notes->area_name."""
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    _seed_council(db_conn, "E06000057", "Northumberland", "Northumberland (County)")
    _seed_app(db_conn, source_id, "Northumberland/24/04112/OUTES", "Northumberland (County)")

    out = repo.backfill_council_gss(db_conn)
    assert out["matched_council"] == 1
    assert out["matched_alias"] == 0
    assert out["remaining_null"] == 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT council_gss FROM applications WHERE application_ref = %s",
            ("Northumberland/24/04112/OUTES",),
        )
        assert cur.fetchone()[0] == "E06000057"


def test_backfill_council_gss_via_alias_for_legacy_district(db_conn):
    """Legacy-district match: 2008 Wycombe parent should resolve to Buckinghamshire
    via `council_aliases`."""
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    # Current unitary exists; legacy district does not.
    _seed_council(db_conn, "E06000060", "Buckinghamshire Council", "Buckinghamshire (Unitary)")
    _seed_alias(db_conn, "Wycombe", "E06000060", "legacy_district")
    _seed_app(db_conn, source_id, "Wycombe/08/05740/FULEA", "Wycombe")

    out = repo.backfill_council_gss(db_conn)
    assert out["matched_council"] == 0
    assert out["matched_alias"] == 1
    assert out["remaining_null"] == 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT council_gss, raw_metadata->>'area_name' "
            "FROM applications WHERE application_ref = %s",
            ("Wycombe/08/05740/FULEA",),
        )
        gss, raw_area = cur.fetchone()
    # GSS is set to current Bucks unitary; raw area_name preserved (principle 3).
    assert gss == "E06000060"
    assert raw_area == "Wycombe"


def test_backfill_council_gss_leaves_unmapped_mdc_null(db_conn):
    """OPDC/LLDC are intentionally NOT aliased — they're planning authorities
    but not local councils. Backfill must leave them NULL with the MDC name
    intact in `raw_metadata` for downstream filtering."""
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    _seed_council(db_conn, "E06000060", "Buckinghamshire Council", "Buckinghamshire (Unitary)")
    _seed_app(db_conn, source_id, "OldOakParkRoyal/24/0001", "Old Oak Park Royal")

    out = repo.backfill_council_gss(db_conn)
    assert out["matched_council"] == 0
    assert out["matched_alias"] == 0
    assert out["remaining_null"] == 1

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT council_gss, raw_metadata->>'area_name' "
            "FROM applications WHERE application_ref = %s",
            ("OldOakParkRoyal/24/0001",),
        )
        gss, raw_area = cur.fetchone()
    assert gss is None
    assert raw_area == "Old Oak Park Royal"


def test_backfill_council_gss_does_not_overwrite_existing(db_conn):
    """Already-populated council_gss must not be touched, even if it differs
    from what an alias would map. Append-only semantics protect prior decisions."""
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    _seed_council(db_conn, "E06000057", "Northumberland", "Northumberland (County)")
    _seed_council(db_conn, "E06000060", "Buckinghamshire", "Bucks (Unitary)")
    # App with a deliberate (perhaps wrong, perhaps right) prior assignment
    repo.upsert_application(
        db_conn, source_id=source_id,
        app={
            "name": "X/1", "uid": "1", "area_name": "Northumberland (County)",
            "description": "x", "address": "x", "postcode": None,
            "start_date": "2024-01-01", "decided_date": None,
            "app_state": "Undecided", "app_type": "Outline", "app_size": "Large",
            "url": "https://example.invalid/app",
        },
        council_gss="E06000060",
    )
    out = repo.backfill_council_gss(db_conn)
    assert out["matched_council"] == 0  # the WHERE council_gss IS NULL clause skipped this row
    with db_conn.cursor() as cur:
        cur.execute("SELECT council_gss FROM applications WHERE application_ref = 'X/1'")
        assert cur.fetchone()[0] == "E06000060"


def test_load_area_gss_map_includes_aliases(db_conn):
    """The map used by spatial/operator/parent-backfill sweeps must include
    alias entries so newly-fetched applications under legacy area_names get
    the right GSS at insert time, not just via the backfill pass."""
    from dcp.sources import planit
    _seed_council(db_conn, "E06000060", "Buckinghamshire", "Buckinghamshire (Unitary)")
    _seed_alias(db_conn, "Wycombe", "E06000060", "legacy_district")
    _seed_alias(db_conn, "Chiltern South Bucks", "E06000060", "joint_planning")
    m = planit._load_area_gss_map(db_conn)
    assert m["Buckinghamshire (Unitary)"] == "E06000060"
    assert m["Wycombe"] == "E06000060"
    assert m["Chiltern South Bucks"] == "E06000060"


def test_load_area_gss_map_aliases_dont_overwrite_council_match(db_conn):
    """If an alias_name happens to collide with a council's notes->area_name,
    prefer the direct council match. The alias is a fallback, not a override."""
    from dcp.sources import planit
    _seed_council(db_conn, "E06000057", "Northumberland", "Northumberland (County)")
    _seed_council(db_conn, "E99999999", "Test Other", "Test Other Area")
    # Adversarial: an alias entry uses the same area_name but points elsewhere
    _seed_alias(db_conn, "Northumberland (County)", "E99999999", "joint_planning")
    m = planit._load_area_gss_map(db_conn)
    assert m["Northumberland (County)"] == "E06000057"  # council match wins
