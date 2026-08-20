"""Tests for the NESO EA Register capacity claims.

Anchors first: the committed snapshot must reproduce the figures recorded
in data/external_sources/README.md at extraction (119 demand rows,
49,440 MW, the named spot rows), so a corrupted or silently-updated file
cannot change what the artefacts say. Then the matches batch: every match
must name a real demand claim at the row it says, carry the constrained
confidence vocabulary, and hold evidence a reader could weigh — validated
in code here and by constraint in migration 021. The integration test
proves the loader's contract: re-running on the same inputs inserts
nothing, and retiring a match is a timestamp, not a delete.
"""

from __future__ import annotations

import psycopg2
import pytest

from dcp import capacity_claims as cc


def _claims():
    return cc.load_register_demand_claims()


def _matches():
    return cc.load_matches()


# ---------------------------------------------------------------------------
# Snapshot anchors (data/external_sources/README.md, recorded at extraction)

def test_demand_row_count_and_total():
    claims = _claims()
    assert len(claims) == 119
    assert round(sum(c.value_mw for c in claims)) == 49440


def test_spot_rows():
    by_row = {c.excel_row: c for c in _claims()}
    walpole = max(_claims(), key=lambda c: c.value_mw)
    assert walpole.claim_name == "Walpole Flexible Generation"
    assert walpole.value_mw == 2550
    iver2 = by_row[722]
    assert iver2.claim_name == "Iver 2 Ark Estates"
    assert iver2.value_mw == 435
    assert iver2.connection_point == "Uxbridge Moor (Iver B 132kV)"
    # The misspelling is the source's own and must survive ingestion.
    assert by_row[723].claim_name == "Mecure Data Centre"


def test_locator_names_the_excel_row():
    c = next(c for c in _claims() if c.excel_row == 272)
    assert c.source_locator == "row 272"


# ---------------------------------------------------------------------------
# The matches batch

def test_batch_is_valid():
    assert cc.validate_matches(_claims(), _matches()) == []


def test_every_match_has_defensible_fields():
    for m in _matches():
        assert m.confidence in cc.CONFIDENCE_VOCAB
        assert len(m.evidence) >= 40, m.claim_name
        assert m.matched_by.startswith("hand:"), m.claim_name


def test_validation_catches_a_wrong_row():
    claims = _claims()
    good = _matches()[0]
    bad = cc.Match(excel_row=999999, claim_name=good.claim_name,
                   site_id=good.site_id, method=good.method,
                   confidence=good.confidence, evidence=good.evidence,
                   matched_by=good.matched_by)
    problems = cc.validate_matches(claims, [bad])
    assert any("no demand claim" in p for p in problems)


def test_validation_catches_a_renamed_claim():
    claims = _claims()
    good = _matches()[0]
    bad = cc.Match(excel_row=good.excel_row, claim_name="Something Else",
                   site_id=good.site_id, method=good.method,
                   confidence=good.confidence, evidence=good.evidence,
                   matched_by=good.matched_by)
    problems = cc.validate_matches(claims, [bad])
    assert any("does not match register" in p for p in problems)


# ---------------------------------------------------------------------------
# Loader contract, against the migrated test database

@pytest.mark.integration
def test_claims_insert_is_idempotent_and_matches_retire_not_delete(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacity_claims
                (source_key, claim_name, quantity_type, value_original,
                 unit_original, value_mw, as_at, source_url, source_locator)
            VALUES ('neso_ea_register', 'Test DC', 'grid_connection',
                    100, 'MW', 100, '2025-06-11', 'https://example', 'row 6')
            ON CONFLICT DO NOTHING
            """)
        cur.execute(
            """
            INSERT INTO capacity_claims
                (source_key, claim_name, quantity_type, value_original,
                 unit_original, value_mw, as_at, source_url, source_locator)
            VALUES ('neso_ea_register', 'Test DC', 'grid_connection',
                    100, 'MW', 100, '2025-06-11', 'https://example', 'row 6')
            ON CONFLICT DO NOTHING
            """)
        cur.execute("SELECT count(*) FROM capacity_claims "
                    "WHERE source_key = 'neso_ea_register'")
        assert cur.fetchone()[0] == 1

        cur.execute(
            "INSERT INTO sites (site_key, classification, radius_km) "
            "VALUES ('test-site', 'ours_only', 0.5) RETURNING id")
        site_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM capacity_claims "
                    "WHERE claim_name = 'Test DC'")
        claim_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO capacity_claim_matches
                (claim_id, site_id, method, confidence, evidence, matched_by)
            VALUES (%s, %s, 'name_identity', 'strong',
                    'A test match with evidence long enough to be weighed.',
                    'hand:test')
            """, (claim_id, site_id))

        # A second live match for the same claim must be refused ...
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute(
                """
                INSERT INTO capacity_claim_matches
                    (claim_id, site_id, method, confidence, evidence,
                     matched_by)
                VALUES (%s, %s, 'place_and_scale', 'tentative',
                        'A competing live match that the schema must refuse.',
                        'hand:test')
                """, (claim_id, site_id))
    db_conn.rollback()

    # ... but retiring the first makes room for a successor, and the
    # retired row survives as history.
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacity_claims
                (source_key, claim_name, quantity_type, value_original,
                 unit_original, value_mw, as_at, source_url, source_locator)
            VALUES ('neso_ea_register', 'Test DC', 'grid_connection',
                    100, 'MW', 100, '2025-06-11', 'https://example', 'row 6')
            RETURNING id
            """)
        claim_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO sites (site_key, classification, radius_km) "
            "VALUES ('test-site-2', 'ours_only', 0.5) RETURNING id")
        site_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO capacity_claim_matches
                (claim_id, site_id, method, confidence, evidence, matched_by)
            VALUES (%s, %s, 'name_identity', 'strong',
                    'First assertion, later found to be wrong by someone.',
                    'hand:test')
            """, (claim_id, site_id))
        cur.execute(
            "UPDATE capacity_claim_matches SET retired_at = now(), "
            "retired_reason = 'superseded in test' WHERE claim_id = %s",
            (claim_id,))
        cur.execute(
            """
            INSERT INTO capacity_claim_matches
                (claim_id, site_id, method, confidence, evidence, matched_by)
            VALUES (%s, %s, 'address_and_substation', 'probable',
                    'Second assertion standing on different written evidence.',
                    'hand:test')
            """, (claim_id, site_id))
        cur.execute(
            "SELECT count(*) FILTER (WHERE retired_at IS NULL), count(*) "
            "FROM capacity_claim_matches WHERE claim_id = %s", (claim_id,))
        live, total = cur.fetchone()
        assert (live, total) == (1, 2)
