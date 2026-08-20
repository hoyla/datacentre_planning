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
# Companies House filed accounts
#
# These come from scans with no text layer, transcribed by eye from the
# rendered page. The guarantee that matters is that every transcribed
# figure still appears in the OCR of the page it cites — a cheap, offline
# stand-in for the quote round-trip the text-layer sources get.

def test_every_filed_figure_appears_on_its_cited_page():
    assert cc.verify_ch_quotes() == []


def test_filed_batch_is_valid():
    assert cc.validate_ch(cc.load_ch_claims(), cc.load_ch_matches()) == []


def test_units_convert_only_where_they_mean_the_same_thing():
    assert cc.mw_of(48.78, "MW") == 48.78
    assert cc.mw_of(800, "kW") == 0.8
    # Energy is not power, however much a megawatt column would like it.
    assert cc.mw_of(280597, "MWh") is None


def test_printed_units_are_preserved_not_normalised():
    by_name = {c.claim_name: c for c in cc.load_ch_claims()}
    uc = by_name["Cody Park (under construction)"]
    assert (uc.value, uc.unit) == (800, "kW"), \
        "the page says 800kW; storing 0.8 MW would overwrite the source"


def test_company_level_claims_are_never_matched_to_a_site():
    claims = cc.load_ch_claims()
    company_level = {c.claim_name for c in claims if c.company_level}
    assert company_level, "expected SECR consumption to be company-level"
    matched = {m["claim_name"] for m in cc.load_ch_matches()}
    assert not (company_level & matched)


def test_a_wrong_digit_is_caught():
    claims = list(cc.load_ch_claims())
    good = next(c for c in claims if c.claim_name == "Cody Park")
    from dataclasses import replace
    bad = replace(good, value=48.79)  # one digit out
    assert cc.verify_ch_quotes([bad])


# ---------------------------------------------------------------------------
# Operator websites
#
# The weakest-authority source, and the one most likely to move under us:
# a marketing page can change any day. The quote check is what turns that
# from silent drift into a failing test.

def test_every_operator_quote_is_still_in_its_snapshot():
    assert cc.verify_operator_quotes() == []


def test_operator_batch_is_valid():
    assert cc.validate_operator(cc.load_operator_claims(),
                                cc.load_operator_matches()) == []


def test_operator_terms_are_preserved_not_translated():
    """"Total Capacity" and "IT load" are not synonyms; the store keeps
    whichever word the operator used."""
    terms = {c.attrs["operator_term"] for c in cc.load_operator_claims()}
    assert {"Total Capacity", "IT load"} <= terms


def test_operator_quantities_all_carry_a_caveat():
    """Operators publish IT figures and grid figures, and the two are not
    the same quantity — CyrusOne states 90 MW of IT capacity and 160 MVA
    of supply for one site. Whatever type a claim takes, the panel must
    have a line explaining it."""
    for c in cc.load_operator_claims():
        assert c.quantity_type in cc.QUANTITY_CAVEATS, c.claim_name


def test_mva_never_becomes_megawatts():
    """Converting MVA to MW needs a power factor none of these operators
    publishes. The apparent-power figures must reach the store with no
    derived MW at all."""
    mva = [c for c in cc.load_operator_claims() if c.unit == "MVA"]
    assert mva, "expected grid-supply claims in MVA"
    for c in mva:
        assert cc.mw_of(c.value, c.unit) is None, c.claim_name


def test_a_changed_page_fails_rather_than_drifts():
    claims = list(cc.load_operator_claims())
    from dataclasses import replace
    moved = replace(claims[0], quote='"name": "Total Capacity", "value": "999"')
    assert cc.verify_operator_quotes([moved])


def test_the_unit_error_is_documented_but_not_loaded():
    """Greystoke publishes 384 GW where two other pages say 384 MW. It is
    recorded as a finding and kept out of the claims, because loading it
    would poison every aggregate it reached."""
    doc = cc.load_operator_document()
    noted = doc.get("noted", [])
    assert any("384 GW" in n["subject"] for n in noted)
    values = {(c.claim_name, c.value, c.unit)
              for c in cc.load_operator_claims()}
    assert ("Humber Tech Park", 384.0, "MW") in values
    assert not any(u == "GW" for _, _, u in values)


# ---------------------------------------------------------------------------
# Rendering support: both artefacts draw wording from the module, so the
# vocabulary has to cover everything the schema admits.

def test_every_schema_quantity_has_a_label():
    # Migration 021's CHECK constraint vocabulary, verbatim.
    schema_vocab = {
        "it_load", "grid_connection", "total_site", "onsite_generation",
        "cooling", "energy_storage", "thermal_input",
        "built_capacity", "metered_consumption", "announced_capacity"}
    assert set(cc.QUANTITY_LABELS) == schema_vocab


def test_contracted_capacity_caveat_names_what_it_is_not():
    caveat = cc.QUANTITY_CAVEATS["grid_connection"]
    for absent in ("not what is built", "not what the site draws"):
        assert absent in caveat


def test_both_panels_state_their_provenance():
    """The two panels sit side by side and both are megawatts, so each has
    to say where its numbers come from rather than leave it to a heading."""
    assert "planning documents" in cc.DECLARED_POWER_NOTE
    assert "outside the planning system" in cc.INDICATORS_NOTE
    assert "not directly comparable" in cc.INDICATORS_NOTE


def test_every_external_quantity_has_a_caveat():
    """Any quantity that can reach the indicators panel must carry a line
    saying what it is — a new source type must not arrive silently."""
    external = {"grid_connection", "built_capacity", "announced_capacity",
                "metered_consumption"}
    assert external <= set(cc.QUANTITY_CAVEATS)
    assert set(cc.QUANTITY_CAVEATS) <= set(cc.QUANTITY_LABELS)


@pytest.mark.integration
def test_site_claim_loaders_round_trip(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sites (site_key, classification, radius_km) "
            "VALUES ('rt-site', 'ours_only', 0.5) RETURNING id")
        site_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO capacity_claims
                (source_key, claim_name, quantity_type, value_original,
                 unit_original, value_mw, as_at, source_url, source_locator,
                 attrs)
            VALUES ('neso_ea_register', 'RT DC', 'grid_connection',
                    250, 'MW', 250, '2025-06-11', 'https://example', 'row 9',
                    '{"connection_point": "Somewhere 400kV",
                      "existing_connection_date": "2031-10-31"}')
            RETURNING id
            """)
        claim_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO capacity_claims
                (source_key, claim_name, quantity_type, value_original,
                 unit_original, value_mw, as_at, source_url, source_locator)
            VALUES ('neso_ea_register', 'Unmatched DC', 'grid_connection',
                    90, 'MW', 90, '2025-06-11', 'https://example', 'row 10')
            """)
        cur.execute(
            """
            INSERT INTO capacity_claim_matches
                (claim_id, site_id, method, confidence, evidence, matched_by)
            VALUES (%s, %s, 'name_identity', 'strong',
                    'Round-trip evidence long enough for the validator.',
                    'hand:test')
            """, (claim_id, site_id))

        by_site = cc.load_site_claims(cur)
        assert list(by_site) == ["rt-site"]
        (claim,) = by_site["rt-site"]
        assert claim["value_mw"] == 250
        assert claim["connection_point"] == "Somewhere 400kV"
        assert claim["connection_date"] == "2031-10-31"
        assert claim["confidence"] == "strong"

        rows = cc.load_claim_rows(cur)
        assert len(rows) == 2
        matched = next(r for r in rows if r["claim_name"] == "RT DC")
        unmatched = next(r for r in rows if r["claim_name"] == "Unmatched DC")
        assert matched["site_key"] == "rt-site"
        assert unmatched["site_key"] is None and unmatched["confidence"] is None

        # A retired match drops out of both loaders' live views.
        cur.execute("UPDATE capacity_claim_matches SET retired_at = now()")
        assert cc.load_site_claims(cur) == {}
        assert all(r["site_key"] is None for r in cc.load_claim_rows(cur))


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
