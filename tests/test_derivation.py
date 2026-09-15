"""A figure we assemble is not a figure a source states (#248, migration 035).

The three admissible derivations, the two the decision refused, and the
write-time guard — each pinned on a quote from the corpus."""
import pytest

from dcp import derivation as dv


def test_a_stated_figure_is_stated_as_written_or_repaired():
    assert dv.stated(19.9, None, "reduced in output to a total of 19-9MW")
    assert dv.stated(0.05, None, "TEMPORARY CHW PUMP 1 50kW")
    assert dv.stated(12.0, None, "Target per floor DDT E6 12MW")
    assert dv.stated(1720.71, 1720.71, "1720,71 kW")
    assert not dv.stated(138.05, None, "1 x 1.25MWe and 57 x 2.4MWe diesel generators")


def test_every_fleet_in_the_quote_summed_is_a_derivation():
    d = dv.derive(29, "the emergency power generation at the site includes "
                      "10no 2.9MW generator sets in acoustic enclosures")
    assert d is not None and d.operation == "fleet_sum"
    assert d.text == "10 × 2.9 MW = 29 MW" and d.cls == "A"
    d = dv.derive(34.8, "Standby power is proposed to be provided by 6 No. 5.8MW, "
                        "11kV, dual-feed, dual-fuel generators")
    assert d is not None and d.text == "6 × 5.8 MW = 34.8 MW"


def test_a_count_in_words_times_a_rating_is_a_derivation():
    d = dv.derive(1.0, "The new building would include two 500kW data halls")
    assert d is not None and d.operation in ("fleet_sum", "product")
    assert d.text.endswith("= 1 MW") and d.reading == "repaired"


def test_a_value_that_needs_an_operand_from_beyond_the_quote_is_not_derived():
    # "1 x 1.25MWe and 57 x 2.4MWe" reaches 138.05; the corpus stored 140.35.
    assert dv.derive(140.35, "1 x 1.25MWe and 57 x 2.4MWe diesel generators") is None


def test_a_sum_of_stated_figures_is_a_derivation():
    d = dv.derive(107, "57 MW from Iver and 50 MW from Laleham")
    assert d is not None and d.operation == "sum"
    assert d.text == "57 MW + 50 MW = 107 MW"
    assert d.cls == "B"


def test_a_midpoint_and_a_scaling_are_not_derivations():
    assert dv.derive(95, "c. 90-100 MW") is None
    assert dv.classify(95, "c. 90-100 MW").startswith("C.")
    assert dv.derive(49.5, "9.9 MW per hall") is None
    assert dv.classify(49.5, "9.9 MW per hall").startswith("C.")


def test_a_value_from_beyond_the_quote_is_the_residue():
    assert dv.derive(258.5, "94 diesel backup generators") is None
    assert dv.classify(258.5, "94 diesel backup generators").startswith("D.")


def test_the_guard_passes_a_stated_value_untouched():
    v, r, d = dv.guard("site_capacity", 12.0, 12.0, "a 12MW IT load", "stated")
    assert (v, r, d) == ("site_capacity", "stated", None)


def test_the_guard_passes_a_derivable_value_with_its_derivation():
    v, r, d = dv.guard("site_capacity", 107.0, 107.0,
                       "57 MW from Iver and 50 MW from Laleham", "sum")
    assert v == "site_capacity" and r == "sum" and d is not None and d.operation == "sum"


def test_the_guard_stores_an_underived_value_as_unclear_and_keeps_the_reasoning():
    v, r, d = dv.guard("site_capacity", 258.5, 258.5,
                       "94 diesel backup generators", "the model's sentence")
    assert v == "unclear" and d is None
    assert r.startswith(dv.REFUSED_PREFIX) and r.endswith("the model's sentence")


def test_the_guard_leaves_other_verdicts_alone():
    assert dv.guard("not_this_site", 258.5, 258.5, "94 generators", "x") == ("not_this_site", "x", None)
    assert dv.guard("site_capacity", None, None, "94 generators", "x") == ("site_capacity", "x", None)


@pytest.mark.integration
def test_a_derivation_is_recorded_once_per_version(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.figure_derivations')")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT id, finding_id, value_mw FROM power_adjudication "
                    "WHERE verdict = 'site_capacity' AND value_mw IS NOT NULL LIMIT 1")
        row = cur.fetchone()
        if row is None:
            pytest.skip("no adjudication in the test database")
        adj_id, fid, mw = row
        d = dv.Derivation("sum", [{"value": 1, "unit": "MW"}], "1 MW = 1 MW")
        assert dv.record(cur, adjudication_id=adj_id, finding_id=fid, value_mw=mw, d=d)
        assert not dv.record(cur, adjudication_id=adj_id, finding_id=fid, value_mw=mw, d=d)
        db_conn.rollback()
