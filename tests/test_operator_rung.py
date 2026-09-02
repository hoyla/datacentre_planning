"""The operator rung: which figure ranks a site, and on whose authority.

The contract under test is `docs/PLAN_OPERATOR_RUNG.md`, decided by
Luke on 2026-09-01. A first-party campus figure sits between the
disclosed rungs and the grid rung; it never displaces a *stated* load
except where a hand adjudication in `campus_scope.yaml` names the
claim; and every guard that keeps a marketing page out of a ranked
cell lives in `capacity_claims.rung_claim`, tested here one at a time.

The rung's ordering matters more than its arithmetic, so most of these
assert which basis won rather than which number did.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dcp import campus_scope as csc
from dcp import capacity_claims as cc
from dcp import site_scale
from dcp.site_scale import OperatorClaim, power_estimate


def _claim(**over) -> dict:
    """A claim as `load_site_claims` produces it: eligible by default."""
    base = {
        "claim_name": "Example campus",
        "value_mw": 100.0,
        "quantity_type": "announced_capacity",
        "source_key": "operator_website",
        "confidence": "strong",
        "component_of": None,
        "operator": "Example Operator",
        "operator_term": "IT load",
        "as_at": "2026-08-30",
    }
    return {**base, **over}


# ---------------------------------------------------------------------------
# Where the rung sits
# ---------------------------------------------------------------------------

class TestRungOrdering:
    def test_it_does_not_displace_a_disclosed_it_load(self):
        est = power_estimate(it_load_mw=24.0,
                             operator_claim=OperatorClaim(112.5, "c"))
        assert est.basis == "Disclosed IT load"
        assert est.value_mw == 24.0

    def test_it_does_not_displace_a_disclosed_total_site_demand(self):
        est = power_estimate(total_site_mw=40.0,
                             operator_claim=OperatorClaim(112.5, "c"))
        assert est.basis == "Disclosed total site demand"

    def test_it_stands_above_a_grid_connection(self):
        est = power_estimate(grid_mw=50.0,
                             operator_claim=OperatorClaim(112.5, "c"))
        assert est.basis == site_scale.OPERATOR_BASIS
        assert est.value_mw == 112.5

    def test_it_stands_above_standby_generation(self):
        est = power_estimate(generation_mw=33.792,
                             operator_claim=OperatorClaim(71.0, "c"))
        assert est.basis == site_scale.OPERATOR_BASIS

    def test_it_stands_above_a_floorspace_estimate(self):
        est = power_estimate(floorspace_sqm=90_000,
                             operator_claim=OperatorClaim(300.0, "c"))
        assert est.basis == site_scale.OPERATOR_BASIS

    def test_it_fills_an_empty_ladder(self):
        """Luke, 2026-09-01: a rung catches what would fall past it.

        Saunderton is the case — this project's own benchmark campus,
        self-auditing to the decimal, ranking on nothing at all.
        """
        est = power_estimate(prose_held=10, prose_read=10,
                             operator_claim=OperatorClaim(78.0, "c"))
        assert est.basis == site_scale.OPERATOR_BASIS
        assert est.value_mw == 78.0

    def test_it_fills_a_cell_on_a_site_holding_no_documents(self):
        """Decided the same day: our acquisition gap is not a reason to
        withhold a first-party figure — it is where one earns its keep."""
        est = power_estimate(has_documents=False,
                             operator_claim=OperatorClaim(9.0, "c"))
        assert est.basis == site_scale.OPERATOR_BASIS

    def test_a_scope_adjudication_displaces_a_disclosed_load(self):
        est = power_estimate(it_load_mw=24.0, operator_displaces=True,
                             operator_claim=OperatorClaim(112.5, "c"))
        assert est.basis == site_scale.OPERATOR_BASIS
        assert est.value_mw == 112.5

    def test_no_claim_leaves_the_ladder_exactly_as_it_was(self):
        for kw in ({"it_load_mw": 24.0}, {"grid_mw": 50.0},
                   {"floorspace_sqm": 90_000}, {"has_documents": False},
                   {"prose_held": 10, "prose_read": 10}):
            assert power_estimate(**kw) == power_estimate(
                **kw, operator_claim=None)


# ---------------------------------------------------------------------------
# What the cell says
# ---------------------------------------------------------------------------

class TestRungCaveat:
    def test_the_basis_line_names_the_planning_figure_it_stands_above(self):
        """Decision 2 is conditional on this: a reader must see that the
        planning record's own figure is smaller and narrower."""
        est = power_estimate(it_load_mw=24.0, operator_displaces=True,
                             operator_claim=OperatorClaim(
                                 112.5, "c", "VIRTUS", "IT load", "2026-08-30"))
        assert "24 MW" in est.caveat
        assert "disclosed IT load" in est.caveat, \
            "the basis keeps its capitals: not 'disclosed it load'"

    def test_it_names_the_operator_and_the_operators_own_term(self):
        est = power_estimate(grid_mw=1.0, operator_claim=OperatorClaim(
            148.0, "c", "Vantage Data Centers", "critical IT load"))
        assert "Vantage Data Centers" in est.caveat
        assert "critical IT load" in est.caveat

    def test_an_undated_claim_does_not_render_an_empty_date(self):
        """Five committed operator claims carry no `as_at`, Vantage
        Cardiff's among them (measured 2026-09-01)."""
        est = power_estimate(grid_mw=1.0,
                             operator_claim=OperatorClaim(148.0, "c", "V"))
        assert "as at" not in est.caveat
        assert "None" not in est.caveat

    def test_it_says_a_marketing_page_can_be_rewritten(self):
        """The channel's own caution, which travels with every figure —
        CyrusOne LON1 went 8.72 to 9 MW in eight days."""
        est = power_estimate(grid_mw=1.0,
                             operator_claim=OperatorClaim(9.0, "c"))
        assert "rewritten without notice" in est.caveat
        assert "not to the planning authority" in est.caveat

    @pytest.mark.parametrize("kw,expected", [
        ({"has_documents": False}, "gap in this project's collection"),
        ({"prose_held": 10, "prose_read": 0}, "not yet analysed"),
        ({"prose_held": 10, "prose_read": 10}, "read in full"),
        ({"prose_held": 10, "prose_read": 4}, "reading is incomplete"),
    ])
    def test_it_names_which_kind_of_planning_silence(self, kw, expected):
        """Luke's condition on firing over an empty ladder: keep the
        read-and-silent versus documents-not-held distinction "in the
        caveat, not in whether the rung fires". Our silence is not
        theirs, which is the no-dash rule.
        """
        est = power_estimate(operator_claim=OperatorClaim(78.0, "c"), **kw)
        assert est.basis == site_scale.OPERATOR_BASIS
        assert expected in est.caveat

    def test_a_scope_note_reaches_the_cell(self):
        est = power_estimate(it_load_mw=24.0, operator_displaces=True,
                             operator_claim=OperatorClaim(
                                 112.5, "c", note="Three of five disclose."))
        assert "Three of five disclose." in est.caveat


# ---------------------------------------------------------------------------
# Eligibility — one guard at a time
# ---------------------------------------------------------------------------

class TestEligibility:
    def test_a_single_eligible_claim_is_returned(self):
        assert cc.rung_claim([_claim()])["claim_name"] == "Example campus"

    def test_a_register_claim_is_never_eligible(self):
        """Third-party aggregates stay tier-and-count (Luke, 2026-08-20)."""
        assert cc.rung_claim([_claim(source_key="neso_ea_register")]) is None

    def test_a_filed_accounts_claim_is_never_eligible(self):
        assert cc.rung_claim([_claim(source_key="companies_house")]) is None

    def test_an_operator_grid_figure_is_panel_only(self):
        """Decision 5: `announced_capacity` only."""
        assert cc.rung_claim([_claim(quantity_type="grid_connection")]) is None

    def test_a_tentative_match_never_ranks(self):
        assert cc.rung_claim([_claim(confidence="tentative")]) is None

    def test_a_facility_component_is_not_a_site_figure(self):
        assert cc.rung_claim([_claim(component_of="Example campus")]) is None

    def test_two_distinct_claims_fall_back_to_panel_only(self):
        """The Global Switch lesson: which of a building's own figures a
        campus total may add is a judgement per facility, not
        arithmetic — so two competing claims wait for a person."""
        assert cc.rung_claim([_claim(claim_name="A"),
                              _claim(claim_name="B")]) is None

    def test_components_are_excluded_before_the_count(self):
        """Kao Harlow: one campus total above four facility figures is
        one claim, not five. Untestable before `component_of` existed."""
        rows = [_claim(claim_name="Kao Data Harlow campus", value_mw=71.0)] + [
            _claim(claim_name=f"KLON-0{i}", value_mw=8.8,
                   component_of="Kao Data Harlow campus") for i in range(1, 5)]
        assert cc.rung_claim(rows)["claim_name"] == "Kao Data Harlow campus"

    def test_two_readings_of_one_claim_fold_to_the_later(self):
        """The append-only fold: a claim re-read is one claim, not two."""
        rows = [_claim(value_mw=8.72, as_at="2026-08-20"),
                _claim(value_mw=9.0, as_at="2026-08-28")]
        assert cc.rung_claim(rows)["value_mw"] == 9.0
        assert cc.rung_claim(list(reversed(rows)))["value_mw"] == 9.0

    def test_an_undated_reading_loses_to_a_dated_one(self):
        rows = [_claim(value_mw=1.0, as_at=None),
                _claim(value_mw=2.0, as_at="2026-08-28")]
        assert cc.rung_claim(rows)["value_mw"] == 2.0

    def test_a_claim_with_no_value_is_not_eligible(self):
        assert cc.rung_claim([_claim(value_mw=None)]) is None

    def test_no_claims_at_all(self):
        assert cc.rung_claim([]) is None


class TestRungInputs:
    def test_a_displacement_naming_this_claim_licenses_it(self):
        d = {"S": csc.Displacement("S", "Example campus", 100.0, "note")}
        claim, displaces = cc.rung_inputs("S", [_claim()], d)
        assert displaces is True
        assert claim.note == "note"

    def test_a_displacement_naming_a_different_claim_does_not(self):
        """A stale pin must not licence whatever claim happens to be
        eligible now — the entry is an adjudication about one figure."""
        d = {"S": csc.Displacement("S", "Some other campus", 100.0)}
        _claim_, displaces = cc.rung_inputs("S", [_claim()], d)
        assert displaces is False

    def test_no_displacement_for_this_site(self):
        _c, displaces = cc.rung_inputs("S", [_claim()], {})
        assert displaces is False


# ---------------------------------------------------------------------------
# The prior's contract
# ---------------------------------------------------------------------------

def _scope_file(tmp_path: Path, entry: dict) -> Path:
    p = tmp_path / "campus_scope.yaml"
    p.write_text(yaml.safe_dump({"campuses": [entry]}))
    return p


def _reviewed(**over) -> dict:
    base = {
        "site_key": "PTNO-1",
        "scope": "distinct_facilities",
        "total": "withhold",
        "reason": "Because the evidence says so.",
        "power_cell": {"operator_claim": "Example campus",
                       "expected_value_mw": 100.0},
    }
    return {**base, **over}


class TestScopePrior:
    def test_the_real_file_loads_and_every_entry_is_wellformed(self):
        scopes = csc.load_scopes()
        assert scopes, "the committed prior is not empty"
        assert all(e["scope"] in csc.SCOPES for e in scopes.values())

    def test_the_defaults_are_absolute(self):
        """The R3 lesson, applied at birth rather than after."""
        assert csc.SCOPE_PATH.is_absolute()

    def test_the_real_displacements_load(self):
        d = csc.load_displacements()
        assert set(d) == {"PTNO-12301553", "PTNO-12489438", "PTNO-12216044"}
        assert d["PTNO-12301553"].expected_value_mw == 112.5
        assert d["PTNO-12489438"].expected_value_mw == 148.0
        # VIRTUS Slough, reviewed 2026-09-02: the planning record states
        # nothing, so this one fills an empty ladder rather than
        # displacing a figure.
        assert d["PTNO-12216044"].expected_value_mw == 145.5

    def test_a_dead_site_key_fails_the_build(self):
        with pytest.raises(ValueError, match="not live"):
            csc.require_live({"PTNO-GONE": {}}, {"PTNO-1"})

    def test_an_unknown_claim_fails_the_build(self):
        d = {"S": csc.Displacement("S", "Missing campus", 100.0)}
        with pytest.raises(ValueError, match="no live claim named"):
            csc.require_claims_unmoved(d, {"S": [_claim()]})

    def test_a_moved_value_fails_the_build(self):
        """The pin is the value, not the date — five committed claims
        carry no `as_at` at all, so a date pin is unenforceable on
        exactly the site it was written for."""
        d = {"S": csc.Displacement("S", "Example campus", 100.0)}
        with pytest.raises(ValueError, match="now reads 112.5"):
            csc.require_claims_unmoved(d, {"S": [_claim(value_mw=112.5)]})

    def test_an_unmoved_value_passes(self):
        d = {"S": csc.Displacement("S", "Example campus", 100.0)}
        csc.require_claims_unmoved(d, {"S": [_claim()]})

    def test_a_power_cell_on_an_unreviewed_entry_is_refused(self, tmp_path):
        """The displacement is the review's conclusion; it cannot
        precede it."""
        p = _scope_file(tmp_path, _reviewed(scope="unreviewed"))
        with pytest.raises(ValueError, match="scope is still unreviewed"):
            csc.load_displacements(p)

    def test_a_displacement_without_a_written_reason_is_refused(self,
                                                                tmp_path):
        p = _scope_file(tmp_path, _reviewed(reason="  "))
        with pytest.raises(ValueError, match="no reason written"):
            csc.load_displacements(p)

    def test_a_power_cell_missing_its_pin_is_refused(self, tmp_path):
        p = _scope_file(tmp_path,
                        _reviewed(power_cell={"operator_claim": "c"}))
        with pytest.raises(ValueError, match="expected_value_mw"):
            csc.load_displacements(p)

    def test_an_unknown_scope_value_is_refused(self, tmp_path):
        p = _scope_file(tmp_path, _reviewed(scope="probably_fine"))
        with pytest.raises(ValueError, match="not one of"):
            csc.load_scopes(p)

    def test_a_missing_file_loads_empty(self, tmp_path):
        assert csc.load_scopes(tmp_path / "absent.yaml") == {}


# ---------------------------------------------------------------------------
# Downstream: the rung must not be mistaken for a disclosure
# ---------------------------------------------------------------------------

class TestDownstream:
    def test_the_operator_basis_is_not_a_disclosed_basis(self):
        """It must stay out of the count compared against Ofgem's queue
        and out of any chart headed "from the site's documents"."""
        assert site_scale.OPERATOR_BASIS not in site_scale.DISCLOSED_BASES

    def test_capacity_status_does_not_call_it_disclosed_in_documents(self):
        from dcp.site_profile import capacity_status
        key, label = capacity_status(
            pre_application=False, docs_held=50, docs_read=50,
            power_value_mw=112.5, power_basis=site_scale.OPERATOR_BASIS)
        assert key == "operator_stated"
        assert "disclosed in documents" not in label

    def test_capacity_status_prefers_it_to_no_documents_held(self):
        """A site we hold nothing for can still carry a first-party
        figure, and calling that "No documents held" would hide the
        number its row is ranked on."""
        from dcp.site_profile import capacity_status
        key, _label = capacity_status(
            pre_application=False, docs_held=0, docs_read=0,
            power_value_mw=9.0, power_basis=site_scale.OPERATOR_BASIS)
        assert key == "operator_stated"


# ---------------------------------------------------------------------------
# The cohort
# ---------------------------------------------------------------------------

class TestCohortAdmission:
    """`at_least_100mw` admits on the rung (decision 3).

    Built from the two adjudicated displacements as they are committed,
    with each site's own planning figures as measured on 2026-09-01, so
    an edit to `campus_scope.yaml` that broke either one fails here.
    Named sites rather than a count, so movement elsewhere in the corpus
    cannot flake it.
    """

    # (site_key, planning it_load, the claim's MW) — measured live. VIRTUS
    # Slough (2026-09-02) has no planning figure at all: the empty-ladder
    # case, where the rung fills rather than displaces.
    CASES = {"PTNO-12301553": (24.0, 112.5), "PTNO-12489438": (67.2, 148.0),
             "PTNO-12216044": (None, 145.5)}

    def _inputs(self, with_rung: bool):
        from dcp import site_cohorts as sc
        keys = list(self.CASES)
        figures = {k: {"it_load_mw": it} for k, (it, _mw) in self.CASES.items()}
        coverage = {k: {"held": 10, "prose_held": 10, "prose_read": 10}
                    for k in keys}
        claims = {k: [_claim(claim_name=csc.load_displacements()[k].claim_name,
                             value_mw=mw)]
                  for k, (_it, mw) in self.CASES.items()}
        return sc.Inputs(keys, figures, coverage, {}, {}, {}, {},
                         claims if with_rung else {},
                         csc.load_displacements() if with_rung else {})

    def test_neither_site_qualifies_on_its_planning_figure(self):
        from dcp import site_cohorts as sc
        members = sc.at_least_100mw(self._inputs(with_rung=False)).members
        assert [m.site_key for m in members] == []

    def test_both_qualify_once_the_displacements_load(self):
        from dcp import site_cohorts as sc
        members = sc.at_least_100mw(self._inputs(with_rung=True)).members
        assert sorted(m.site_key for m in members) == sorted(self.CASES)

    def test_each_member_carries_the_basis_that_admitted_it(self):
        from dcp import site_cohorts as sc
        members = sc.at_least_100mw(self._inputs(with_rung=True)).members
        assert all(m.evidence["basis"] == site_scale.OPERATOR_BASIS
                   for m in members)

    def test_the_notes_count_the_members_standing_on_the_rung(self):
        """The floorspace-count precedent: a cohort must say how many of
        its members rest on something other than a disclosure."""
        from dcp import site_cohorts as sc
        notes = sc.at_least_100mw(self._inputs(with_rung=True)).notes
        assert any("operator-stated campus figure" in n for n in notes)
        n_cases = len(self.CASES)
        assert any(n.startswith(f"{n_cases} of these {n_cases}") for n in notes)


def test_the_cohort_rule_version_moved_with_the_membership_change():
    """A rule that changes who is in the cohort changes its version."""
    from dcp.site_cohorts import REGISTRY
    cohort = next(c for c in REGISTRY if c.key == "at_least_100mw")
    assert cohort.rule_version != "2026-08-25.1"
    assert "operator" in cohort.definition
    assert "operator publishes a campus figure" in cohort.limits
