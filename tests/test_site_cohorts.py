"""Cohorts are rules with limits, computed, and checked beside not inside.

Unit tests over `dcp.site_cohorts` with hand-built inputs, so every
case is the arrangement of figures it is about. What they assert is the
module's contract rather than the corpus's counts: every cohort has
limits or the build fails; counts come from compute, never from text;
the registry order is explicit; a hand-check on a site the rule does
not select is reported rather than hidden; and a cohort that cannot be
computed honestly says so instead of returning an empty set.
"""

from __future__ import annotations

import pytest

from dcp import site_cohorts as sc
from dcp.site_profile import GenerationFigure, GeneratorProfile


def _inputs(sites=(), figures=None, coverage=None, pending=None,
            generators=None, generation=None):
    return sc.Inputs(list(sites), figures or {}, coverage or {},
                     pending or {}, generators or {}, generation or {})


def _cov(held, read):
    return {"held": held, "read": read, "prose_held": held,
            "prose_read": read, "graphical": 0, "sampled_held": 0,
            "sampled_read": 0}


# ---------------------------------------------------------------------------
# The registry's contract
# ---------------------------------------------------------------------------

def test_every_cohort_has_limits_and_a_property_title():
    for c in sc.REGISTRY:
        assert c.limits.strip(), c.key
        assert c.definition.strip() and c.rule.strip(), c.key
        assert c.family in sc.FAMILIES


def test_a_cohort_without_limits_cannot_be_built():
    with pytest.raises(sc.CohortError):
        sc.Cohort(key="x", title="t", family="power", definition="d",
                  rule="r", limits="   ", tone="red", headline="{n} sites",
                  order=9, rule_version="0",
                  compute=lambda i: sc.CohortResult(()))


def test_a_cohort_must_carry_one_of_the_handoff_tones():
    """The tone is a property of the signal, not of the page drawing it.

    The design handoff assigns each signal red, amber or slate, and both
    the table and the site page read it off the registry — so an invented
    fourth tone, or a missing one, has to fail at import rather than
    render as an unstyled pill somewhere.
    """
    with pytest.raises(sc.CohortError):
        sc.Cohort(key="x", title="t", family="power", definition="d",
                  rule="r", limits="l", tone="purple", headline="{n} sites",
                  order=9, rule_version="0",
                  compute=lambda i: sc.CohortResult(()))
    assert {c.tone for c in sc.REGISTRY} <= {"red", "amber", "slate"}


def test_a_headline_must_have_somewhere_to_put_the_count():
    """The card's headline is a sentence, not the title with a number.

    "{n} sites " plus a title read "Four sites demand stated above the
    grid connection", because a title is a noun phrase. The registry
    carries the sentence and the slot the count goes in; a headline
    without the slot would render the same text on every build whatever
    the rule selected, which is the one thing a count must not do.
    """
    with pytest.raises(sc.CohortError):
        sc.Cohort(key="x", title="t", family="power", definition="d",
                  rule="r", limits="l", tone="red",
                  headline="four sites do the thing", order=9,
                  rule_version="0", compute=lambda i: sc.CohortResult(()))
    for c in sc.REGISTRY:
        assert "{n}" in c.headline, c.key


def test_registry_order_is_explicit_and_ascending():
    orders = [c.order for c in sc.REGISTRY]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)
    assert [c.key for c in sc.REGISTRY][0] == "read_in_full_silent"


def test_no_cohort_title_names_a_cause():
    """A title states what the documents say, not why."""
    for c in sc.REGISTRY:
        low = c.title.lower()
        for word in ("intends", "plans to", "because", "grid-dependent",
                     "life-safety", "dependent"):
            assert word not in low, (c.key, word)


# ---------------------------------------------------------------------------
# read_in_full_silent
# ---------------------------------------------------------------------------

def test_read_in_full_and_silent_counts_prose_not_drawings():
    """A site whose only unread documents are drawings has been read."""
    cov = {"S1": {"held": 10, "read": 4, "prose_held": 4, "prose_read": 4,
                  "graphical": 6, "sampled_held": 0, "sampled_read": 0}}
    r = sc.read_in_full_silent(_inputs(["S1"], coverage=cov))
    assert r.site_keys == {"S1"}


def test_a_site_with_an_adjudicated_capacity_is_not_silent():
    r = sc.read_in_full_silent(_inputs(
        ["S1"], figures={"S1": {"it_load_mw": 40.0}},
        coverage={"S1": _cov(3, 3)}))
    assert r.site_keys == set()


def test_a_site_with_figures_awaiting_adjudication_is_excluded_and_counted():
    r = sc.read_in_full_silent(_inputs(
        ["S1", "S2"], coverage={"S1": _cov(3, 3), "S2": _cov(3, 3)},
        pending={"S2": 4}))
    assert r.site_keys == {"S1"}
    assert r.notes and "1 further site" in r.notes[0]


def test_a_partly_read_site_is_not_in_the_cohort():
    r = sc.read_in_full_silent(_inputs(["S1"], coverage={"S1": _cov(5, 4)}))
    assert r.site_keys == set()


def test_a_site_with_no_prose_is_not_read_in_full():
    """Zero of zero is not 'read'; it is nothing to read."""
    cov = {"S1": {"held": 3, "read": 0, "prose_held": 0, "prose_read": 0,
                  "graphical": 3, "sampled_held": 0, "sampled_read": 0}}
    r = sc.read_in_full_silent(_inputs(["S1"], coverage=cov))
    assert r.site_keys == set()


# ---------------------------------------------------------------------------
# demand_exceeds_connection
# ---------------------------------------------------------------------------

def test_demand_uses_the_larger_of_it_and_total():
    """Northumberland: 72 MW of IT load, 1,100 MW total, 99.9 MW grid."""
    r = sc.demand_exceeds_connection(_inputs(["N"], figures={"N": {
        "it_load_mw": 72.0, "total_site_mw": 1100.0, "grid_mw": 99.9}}))
    assert r.site_keys == {"N"}
    ev = r.members[0].evidence
    assert ev["load_quantity"] == "total_site"
    assert ev["ratio"] == round(1100 / 99.9, 2)


def test_demand_just_above_the_connection_is_not_enough():
    r = sc.demand_exceeds_connection(_inputs(["S"], figures={"S": {
        "it_load_mw": 130.0, "grid_mw": 100.0}}))
    assert r.site_keys == set()


def test_no_connection_figure_means_no_membership():
    r = sc.demand_exceeds_connection(_inputs(["S"], figures={"S": {
        "it_load_mw": 500.0, "grid_mw": None}}))
    assert r.site_keys == set()


# ---------------------------------------------------------------------------
# generation_no_fuel
# ---------------------------------------------------------------------------

def test_generation_by_count_with_no_fuel_qualifies():
    r = sc.generation_no_fuel(_inputs(["S"], generators={
        "S": GeneratorProfile(12, [], False, "")}))
    assert r.site_keys == {"S"}


def test_generation_by_figure_with_no_fuel_qualifies():
    r = sc.generation_no_fuel(_inputs(["S"], generation={
        "S": GenerationFigure(12.0, "as stated", None, None, "")}))
    assert r.site_keys == {"S"}
    assert r.members[0].evidence["generation_basis"] == "as stated"


def test_a_named_fuel_disqualifies():
    r = sc.generation_no_fuel(_inputs(["S"], generators={
        "S": GeneratorProfile(12, [("Diesel", 4)], False, "")}))
    assert r.site_keys == set()


def test_no_generation_at_all_is_not_in_the_cohort():
    r = sc.generation_no_fuel(_inputs(["S"], generators={
        "S": GeneratorProfile(None, [], False, "")}))
    assert r.site_keys == set()


# ---------------------------------------------------------------------------
# generation_exceeds_load
#
# Withheld from 2026-08-23 until gpt-5/generation-2.5 had adjudicated what
# each generation figure describes. The two sites named in that
# withholding are the cases these assertions are built from.
# ---------------------------------------------------------------------------

def _gen(mw, basis, plant="standby_combustion"):
    return GenerationFigure(mw, "as stated", None, None, "", plant,
                            basis_key=basis)


def test_a_withheld_result_cannot_also_carry_members():
    """The contract behind the Signals card's refusal.

    Nothing is withheld today — generation_exceeds_load was, and is not
    since 2026-08-25 — so the browser test that renders a withheld card
    skips. This holds the shape of the thing whether or not any rule is
    currently using it.
    """
    with pytest.raises(sc.CohortError):
        sc.CohortResult((sc.Member("S", {}),), withheld="not computed")
    r = sc.CohortResult((), withheld="not computed")
    assert r.site_keys == set() and r.withheld


def test_generation_half_again_the_load_qualifies():
    r = sc.generation_exceeds_load(_inputs(
        ["S"], figures={"S": {"it_load_mw": 100.0}},
        generation={"S": _gen(228.0, "stated_group_total")}))
    assert r.site_keys == {"S"}
    ev = r.members[0].evidence
    assert ev["ratio"] == 2.28
    assert ev["load_quantity"] == "it_load"
    assert ev["plant_type"] == "standby_combustion"


def test_generation_merely_matching_the_load_does_not():
    """Standby cover for what a site draws is ordinary, not a signal."""
    r = sc.generation_exceeds_load(_inputs(
        ["S"], figures={"S": {"it_load_mw": 100.0}},
        generation={"S": _gen(140.0, "site_total")}))
    assert r.site_keys == set()


def test_a_per_unit_rating_is_never_multiplied_into_a_total():
    """JVC Business Park: sixteen units of 3.2 MW against a 75 MW load.

    The withheld rule multiplied a count by a rating and selected it on
    165 MW, which is the thermal figure the same documents give. A
    per-unit figure is not comparable with a load at all.
    """
    r = sc.generation_exceeds_load(_inputs(
        ["JVC"], figures={"JVC": {"it_load_mw": 75.0}},
        generation={"JVC": _gen(3.2, "per_generator")}))
    assert r.site_keys == set()
    assert r.notes and "one machine's rating" in r.notes[0]


def test_a_figure_the_adjudicator_could_not_settle_is_excluded():
    r = sc.generation_exceeds_load(_inputs(
        ["S"], figures={"S": {"it_load_mw": 10.0}},
        generation={"S": _gen(1000.0, "unclear")}))
    assert r.site_keys == set()


def test_a_site_with_no_generation_figure_left_cannot_qualify():
    """Rover Way: seven figures, every one read as not generation.

    site_profile.generation_figure returns no value at all in that case,
    and a site with none is not in the cohort — the withheld rule had it
    on 1,000 MW of "energy capacity" attributed to no plant.
    """
    r = sc.generation_exceeds_load(_inputs(
        ["ROVER"], figures={"ROVER": {"it_load_mw": 10.0}},
        generation={"ROVER": GenerationFigure(None, "", None, None, "")}))
    assert r.site_keys == set()


def test_the_larger_of_the_two_loads_is_the_one_compared():
    """The conservative choice: a bigger load makes membership harder."""
    r = sc.generation_exceeds_load(_inputs(
        ["S"], figures={"S": {"it_load_mw": 6.0, "total_site_mw": 27.16}},
        generation={"S": _gen(50.0, "site_total", "unclear")}))
    assert r.site_keys == {"S"}
    assert r.members[0].evidence["load_quantity"] == "total_site"
    assert r.members[0].evidence["load_mw"] == 27.2


def test_a_site_stating_no_load_is_not_in_the_cohort():
    """Nothing to exceed. Most of the corpus states no load at all."""
    r = sc.generation_exceeds_load(_inputs(
        ["S"], figures={"S": {"grid_mw": 40.0}},
        generation={"S": _gen(500.0, "site_total")}))
    assert r.site_keys == set()


def test_plant_type_does_not_decide_membership():
    """Standby plant larger than the load is the finding, not a reason to
    drop the site — but which kind it is travels with it."""
    for plant in ("standby_combustion", "prime_combustion", "renewable"):
        r = sc.generation_exceeds_load(_inputs(
            ["S"], figures={"S": {"it_load_mw": 50.0}},
            generation={"S": _gen(346.0, "installation_total", plant)}))
        assert r.site_keys == {"S"}, plant
        assert r.members[0].evidence["plant_type"] == plant


# ---------------------------------------------------------------------------
# Hand-checks
# ---------------------------------------------------------------------------

def _checks_file(tmp_path, body):
    p = tmp_path / "cohort_checks.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_checks_load_and_validate(tmp_path):
    p = _checks_file(tmp_path, """
checks:
  - site_key: S1
    cohort: demand_exceeds_connection
    verdict: holds
    checked_by: someone
    date: 2026-08-10
""")
    [c] = sc.load_checks(p)
    assert c.site_key == "S1" and c.verdict == "holds"


@pytest.mark.parametrize("body,fragment", [
    ("checks:\n  - site_key: S1\n    cohort: not_a_cohort\n    verdict: holds\n"
     "    checked_by: x\n    date: 2026-01-01\n", "cohort must be one of"),
    ("checks:\n  - site_key: S1\n    cohort: demand_exceeds_connection\n"
     "    verdict: maybe\n    checked_by: x\n    date: 2026-01-01\n",
     "verdict must be one of"),
    ("checks:\n  - site_key: S1\n    cohort: demand_exceeds_connection\n"
     "    verdict: holds\n", "needs checked_by and date"),
    ("checks:\n  - site_key: S1\n    cohort: demand_exceeds_connection\n"
     "    verdict: holds\n    checked_by: x\n    date: 2026-01-01\n"
     "  - site_key: S1\n    cohort: demand_exceeds_connection\n"
     "    verdict: holds\n    checked_by: y\n    date: 2026-01-02\n",
     "listed twice"),
])
def test_a_malformed_check_is_rejected(tmp_path, body, fragment):
    with pytest.raises(sc.CohortError) as exc:
        sc.load_checks(_checks_file(tmp_path, body))
    assert fragment in str(exc.value)


def test_the_committed_checks_file_loads():
    checks = sc.load_checks()
    assert checks, "the seed checks from HISTORY should be present"
    assert all(c.cohort in {x.key for x in sc.REGISTRY} for c in checks)


def test_a_check_outside_the_cohort_is_reported_not_hidden():
    cohort = sc.by_key("demand_exceeds_connection")
    result = sc.CohortResult((sc.Member("IN", {}),))
    checks = (sc.Check("IN", cohort.key, "holds", "x", "2026-01-01"),
              sc.Check("OUT", cohort.key, "holds", "x", "2026-01-01"),
              sc.Check("IN2", cohort.key, "does_not_hold", "x", "2026-01-01"))
    c = sc.Computed(cohort, result, checks)
    assert c.confirmed == 1
    assert [k.site_key for k in c.outside] == ["OUT", "IN2"]


def test_a_disputed_member_is_counted_separately():
    cohort = sc.by_key("demand_exceeds_connection")
    result = sc.CohortResult((sc.Member("A", {}), sc.Member("B", {})))
    checks = (sc.Check("A", cohort.key, "holds", "x", "2026-01-01"),
              sc.Check("B", cohort.key, "does_not_hold", "x", "2026-01-01"))
    c = sc.Computed(cohort, result, checks)
    assert c.confirmed == 1
    assert [k.site_key for k in c.disputed] == ["B"]
    assert c.outside == ()
