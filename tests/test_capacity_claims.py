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
    would poison every aggregate it reached.

    The guard targets that misprint, not the unit: a gigawatt-scale
    figure is a legitimate claim where a page genuinely states one —
    Quest Park's "Secured Grid connection ~ 1 GW" is a grid ambition
    recorded as printed — so the ban is on 384 arriving in GW, and on
    any single claim exceeding UK-peak-demand scale, not on GW itself.
    """
    doc = cc.load_operator_document()
    noted = doc.get("noted", [])
    assert any("384 GW" in n["subject"] for n in noted)
    values = {(c.claim_name, c.value, c.unit)
              for c in cc.load_operator_claims()}
    assert ("Humber Tech Park", 384.0, "MW") in values
    assert not any(u == "GW" and v >= 10 for _, v, u in values), (
        "a tens-of-gigawatts claim is beyond any single UK site and is "
        "almost certainly a unit error — record it under `noted` instead")


# ---------------------------------------------------------------------------
# Rendering support: both artefacts draw wording from the module, so the
# vocabulary has to cover everything the schema admits.

def test_every_schema_quantity_has_a_label():
    # Migration 030's CHECK constraint vocabulary, verbatim (021 as
    # widened by 022 and 030).
    schema_vocab = {
        "it_load", "grid_connection", "total_site", "onsite_generation",
        "cooling", "energy_storage", "thermal_input",
        "built_capacity", "metered_consumption", "announced_capacity",
        "let_capacity", "scheme_capacity", "investment_property_fair_value"}
    assert set(cc.QUANTITY_LABELS) == schema_vocab


def test_scheme_capacity_is_not_a_grid_connection():
    """The premise migration 030 asserts, in a place a reader meets it.

    A reserved grid connection is headroom the network agreed to supply;
    a valuation assumption is what an external valuer priced and an
    auditor signed. Court Lane states 140 MW of reserved connection in
    its planning documents and 103.3 MW in its accounts, and the two do
    not contradict each other — they measure different things. The
    caveat has to say so, because the panel puts them side by side.
    """
    caveat = cc.QUANTITY_CAVEATS["scheme_capacity"]
    assert "grid connection" in caveat
    assert "built capacity" in caveat


def test_a_valuation_is_money_and_never_becomes_megawatts():
    """Pounds have no megawatt equivalent, and the derivation must not
    invent one — the same rule that keeps MWh out of value_mw."""
    assert cc.mw_of(205_000_000, "GBP") is None
    gbp = [c for c in cc.load_ch_claims() if c.unit == "GBP"]
    assert gbp, "expected at least one valuation claim"
    for c in gbp:
        assert c.quantity_type == "investment_property_fair_value"
        assert cc.mw_of(c.value, c.unit) is None, c.claim_name


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
                "metered_consumption", "let_capacity", "thermal_input",
                "scheme_capacity", "investment_property_fair_value"}
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


# ---------------------------------------------------------------------------
# component_of: which realm a figure belongs to (issue #247)
# ---------------------------------------------------------------------------

def _claim(name, value, parent=None):
    from dcp.capacity_claims import FiledClaim
    return FiledClaim(
        source_key="operator_website", company_name="X", company_number="",
        claim_name=name, quantity_type="announced_capacity", value=value,
        unit="MW", stage=None, as_at=None, locator="snap", quote="q",
        url="https://example.com", company_level=False,
        # A real held snapshot so the quote check runs rather than
        # raising; these fixtures test the component rules, and the
        # quote rule has its own tests above.
        attrs={"component_of": parent, "snapshot": "cyrusone-lon1"})


def test_a_component_naming_no_claim_fails():
    from dcp import capacity_claims as cc
    problems = cc.validate_operator(
        [_claim("Facility A", 10, parent="No Such Campus")], [])
    assert any("names no claim" in p for p in problems)


def test_a_component_naming_itself_fails():
    from dcp import capacity_claims as cc
    problems = cc.validate_operator([_claim("A", 10, parent="A")], [])
    assert any("names itself" in p for p in problems)


def test_components_do_not_nest():
    from dcp import capacity_claims as cc
    problems = cc.validate_operator([
        _claim("Campus", 100),
        _claim("Building", 40, parent="Campus"),
        _claim("Floor", 10, parent="Building")], [])
    assert any("do not nest" in p for p in problems)


def test_reconciliation_reports_and_never_fails():
    """An operator whose arithmetic does not close is a finding, not an
    error — VIRTUS Slough states 145.5 against 132.2 of its own rows."""
    from dcp import capacity_claims as cc
    rows = cc.reconcile_components([
        _claim("Campus", 100),
        _claim("A", 60, parent="Campus"),
        _claim("B", 25, parent="Campus")])
    assert len(rows) == 1
    r = rows[0]
    assert r["components"] == 2 and r["component_sum_mw"] == 85
    assert r["gap_mw"] == 15 and r["reconciles"] is False
    # A gap raises nothing and is reported by no validator.
    problems = cc.validate_operator([
        _claim("Campus", 100), _claim("A", 60, parent="Campus")], [])
    assert not [p for p in problems if "component" in p]


def test_an_exact_campus_reconciles():
    from dcp import capacity_claims as cc
    rows = cc.reconcile_components([
        _claim("Campus", 78),
        _claim("A", 9.5, parent="Campus"), _claim("B", 22.5, parent="Campus"),
        _claim("C", 16, parent="Campus"), _claim("D", 30, parent="Campus")])
    assert rows[0]["reconciles"] is True and rows[0]["gap_mw"] == 0


def test_the_real_file_marks_its_campus_components():
    """Every VIRTUS and Kao facility figure in the file names the campus
    total it is part of, so nothing sums a component into its parent."""
    from dcp import capacity_claims as cc
    rows = {r["parent"]: r for r in cc.reconcile_components()}
    assert "VIRTUS Stockley Park campus" in rows
    assert rows["VIRTUS Stockley Park campus"]["components"] >= 3


# ---------------------------------------------------------------------------
# The append-only snapshot store (WP-A of docs/HANDOVER_SNAPSHOT_CHAIN.md)
#
# The store was overwrite-in-place while the claims it evidences were
# append-only, so a superseded reading pointed at a file no longer
# containing its quote. These pin the two halves of the fix: one
# resolver that answers "which file evidences this claim", and a
# fetcher that adds a file only when something changed.

def _snap(dirpath, name, digest="a" * 64, body="the page says 9 MW"):
    (dirpath / name).write_text(
        f"# url: https://example.com\n\n# fetched: 2026-08-30\n\n"
        f"# sha256(html): {digest}\n\n## STRUCTURED\n\n(none)\n\n"
        f"## VISIBLE TEXT\n\n{body}")
    return dirpath / name


def test_the_resolver_returns_the_newest_dated_snapshot(tmp_path):
    _snap(tmp_path, "op-site.2026-08-20.txt")
    newest = _snap(tmp_path, "op-site.2026-08-28.txt")
    _snap(tmp_path, "op-site.2026-08-14.txt")
    assert cc.snapshot_path("op-site", tmp_path) == newest


def test_a_same_day_second_reading_sorts_after_the_first(tmp_path):
    """`_2` and not `-2`: a dash sorts before the dot and would make the
    day's second reading look older than its first."""
    _snap(tmp_path, "op-site.2026-08-28.txt")
    second = _snap(tmp_path, "op-site.2026-08-28_2.txt")
    assert cc.snapshot_path("op-site", tmp_path) == second


def test_the_resolver_falls_back_to_the_pre_migration_name(tmp_path):
    legacy = _snap(tmp_path, "op-site.txt")
    assert cc.snapshot_path("op-site", tmp_path) == legacy


def test_a_dated_snapshot_beats_a_legacy_one(tmp_path):
    _snap(tmp_path, "op-site.txt")
    dated = _snap(tmp_path, "op-site.2026-08-28.txt")
    assert cc.snapshot_path("op-site", tmp_path) == dated


def test_the_resolver_does_not_answer_for_a_slug_it_holds_nothing_for(tmp_path):
    _snap(tmp_path, "op-site.2026-08-28.txt")
    assert cc.snapshot_path("op-other", tmp_path) is None


def test_one_slug_is_not_matched_by_a_longer_one(tmp_path):
    """`virtus-saunderton` and `virtus-saunderton-spec-sheet` are two
    pages, and the glob must not confuse them."""
    _snap(tmp_path, "op-site-spec-sheet.2026-09-01.txt")
    mine = _snap(tmp_path, "op-site.2026-08-30.txt")
    assert cc.snapshot_path("op-site", tmp_path) == mine
    assert cc.snapshot_path("op-site-spec-sheet", tmp_path).name.startswith(
        "op-site-spec-sheet.")


def test_every_committed_snapshot_is_dated():
    """The migration is complete, so the resolver's legacy fallback is
    a review aid rather than something the store depends on."""
    import re
    stray = sorted(
        p.name for p in cc.OPERATOR_SNAPSHOT_DIR.glob("*.txt")
        if not re.search(r"\.\d{4}-\d{2}-\d{2}(_\d+)?\.txt$", p.name))
    assert stray == []


# ---------------------------------------------------------------------------
# The campus self-audits (WP-D, and the Saunderton gap it found)
#
# A campus total whose own breakdown checks it is the benchmark for when
# a sum can ever be trusted, so the store has to be able to measure that
# rather than leave it asserted in prose.

def test_the_two_self_auditing_campuses_reconcile_against_their_own_rows():
    rows = {r["parent"]: r for r in cc.reconcile_components()}
    saunderton = rows["VIRTUS Saunderton Campus"]
    assert saunderton["components"] == 4
    assert saunderton["gap_mw"] == 0 and saunderton["reconciles"] is True
    iron = rows["Iron Mountain London campus (Slough)"]
    assert iron["components"] == 3
    assert iron["parent_mw"] == 61 and iron["component_sum_mw"] == 60.7


def test_a_facility_figure_from_a_second_page_is_not_a_component():
    """Iron Mountain states LON-1 at 8.7 MW in the campus FAQ its 61 MW
    total is built from, and 8.75 MW on the facility's own page. Both are
    held — the divergence is the finding — but only the FAQ figure is a
    component, or the building would be counted twice and the 60.7-vs-61
    self-audit would break."""
    by_name = {c.claim_name: c for c in cc.load_operator_claims()}
    faq = by_name["Iron Mountain LON-1 (campus FAQ)"]
    page = by_name["Iron Mountain LON-1 (facility page)"]
    assert faq.attrs["component_of"] == "Iron Mountain London campus (Slough)"
    assert page.attrs["component_of"] is None
    assert (faq.value, page.value) == (8.7, 8.75)


# ---------------------------------------------------------------------------
# Which held file evidences *this reading* (WP-C)
#
# `snapshot_path` answers "what does the page say now", which is what the
# quote gates want. A link beside a claim needs the other question, and
# the two have different answers the moment a page changes: CyrusOne LON1
# read 8.72 MW on 2026-08-20 and 9 MW on 2026-08-28, both rows still
# stand, and pointing the older one at today's file would be a working
# link to evidence that contradicts it.

def _dated(dirpath, slug, *dates):
    return [_snap(dirpath, f"{slug}.{d}.txt") for d in dates]


def test_candidates_before_a_reading_come_newest_first(tmp_path):
    """The evidence a reading was actually made against, closest first."""
    import datetime as dt
    _dated(tmp_path, "op-site", "2026-08-14", "2026-08-20", "2026-08-28")
    got = cc.snapshot_candidates("op-site", dt.date(2026, 8, 28), tmp_path)
    assert [p.name for p in got] == [
        "op-site.2026-08-28.txt", "op-site.2026-08-20.txt",
        "op-site.2026-08-14.txt"]


def test_later_files_follow_earlier_ones_oldest_first(tmp_path):
    """A reading routinely predates the next re-fetch, so the file after
    it is the next-best evidence — but only after every file that
    existed when the reading was taken has been offered."""
    import datetime as dt
    _dated(tmp_path, "op-site", "2026-08-14", "2026-08-30", "2026-09-04")
    got = cc.snapshot_candidates("op-site", dt.date(2026, 8, 20), tmp_path)
    assert [p.name for p in got] == [
        "op-site.2026-08-14.txt", "op-site.2026-08-30.txt",
        "op-site.2026-09-04.txt"]


def test_a_reading_after_every_file_still_sees_them_all(tmp_path):
    import datetime as dt
    _dated(tmp_path, "op-site", "2026-08-14", "2026-08-20")
    got = cc.snapshot_candidates("op-site", dt.date(2026, 9, 30), tmp_path)
    assert [p.name for p in got] == [
        "op-site.2026-08-20.txt", "op-site.2026-08-14.txt"]


def test_a_same_day_second_reading_is_ordered_by_its_sequence(tmp_path):
    """`_2` sorts after the day's first file, and a claim dated that day
    is offered the later one first — the same `(date, seq)` key
    `snapshot_path` sorts on, never the raw name."""
    import datetime as dt
    _snap(tmp_path, "op-site.2026-08-28.txt")
    _snap(tmp_path, "op-site.2026-08-28_2.txt")
    got = cc.snapshot_candidates("op-site", dt.date(2026, 8, 28), tmp_path)
    assert [p.name for p in got] == [
        "op-site.2026-08-28_2.txt", "op-site.2026-08-28.txt"]


def test_no_date_offers_the_whole_store_newest_first(tmp_path):
    """A green claim asserts the page as it reads now and carries no
    `as_at`, so the newest reading is the one it means."""
    _dated(tmp_path, "op-site", "2026-08-14", "2026-08-30")
    got = cc.snapshot_candidates("op-site", None, tmp_path)
    assert [p.name for p in got] == [
        "op-site.2026-08-30.txt", "op-site.2026-08-14.txt"]


def test_a_locator_that_is_not_a_slug_resolves_to_nothing(tmp_path):
    """Most claims in the store are not operator claims: the register's
    locator is "row 47" and a filing's is "page 12". They must find no
    candidate rather than be matched by a glob that reads them as a
    pattern."""
    _snap(tmp_path, "op-site.2026-08-30.txt")
    assert cc.snapshot_candidates("row 47", None, tmp_path) == []
    assert cc.snapshot_candidates("page [1]", None, tmp_path) == []
    assert cc.snapshot_candidates("../op-site", None, tmp_path) == []
    assert cc.snapshot_candidates("", None, tmp_path) == []


def test_one_slug_is_not_offered_a_longer_slugs_files(tmp_path):
    _snap(tmp_path, "op-site-spec-sheet.2026-09-01.txt")
    _snap(tmp_path, "op-site.2026-08-30.txt")
    assert [p.name for p in cc.snapshot_candidates("op-site", None, tmp_path)] \
        == ["op-site.2026-08-30.txt"]
