"""What a site's class asserts, and what it refuses to assert.

Unit tests over dcp.site_class with hand-built members. The class is
about to decide how every row in the sites list is rendered, so the
rules that could quietly mislead a reporter are tested one by one: that
a disguise suspect is never demoted to adjacency, that a later
`not_dc` reading beats an older v1 `DC`, that a Barbour record with no
planning application is not filed as procedural, and that an
unrecognised verdict stops the build rather than falling into the
residual class.

Issue #159; the spec is in the ROADMAP.
"""

from __future__ import annotations

import pytest

from dcp import site_class as sc


def _m(ref: str, dc: str | None = None, v1: str | None = None) -> sc.Member:
    return sc.Member(ref, dc, v1)


# --- the classes themselves ------------------------------------------

@pytest.mark.parametrize("verdict", sorted(sc.DC_POSITIVE))
def test_every_dc_positive_verdict_makes_a_datacentre(verdict):
    """new_build and expansion_refurb are uncontroversial;
    pre_application and enabling_works are in by decision (ROADMAP,
    agreed 2026-08-27) because a site whose only application is a
    datacentre pre-app is a datacentre site in the pipeline."""
    assert sc.classify("S", [_m("a/1", verdict)]).key == sc.DATACENTRE


def test_a_v1_dc_counts_where_dc_build_has_not_spoken():
    assert sc.classify("S", [_m("a/1", None, "DC")]).key == sc.DATACENTRE


def test_a_later_not_dc_beats_an_older_v1_dc():
    """The two rubrics are generations of the same judgement, not two
    opinions to be split: dc_build read the application later, and the
    clustering already trusts it for membership."""
    assert sc.classify("S", [_m("a/1", "not_dc", "DC")]).key == \
        sc.PROCEDURAL_ONLY


def test_dc_build_unknown_is_the_disguise_suspect_class():
    assert sc.classify("S", [_m("a/1", "unknown")]).key == sc.DISGUISE_SUSPECT


def test_a_v1_unknown_does_not_make_a_disguise_suspect():
    """v1 used `unknown` for sparse descriptions generally, not for the
    large-single-use-building suspicion dc_build means by it."""
    assert sc.classify("S", [_m("a/1", None, "unknown")]).key == \
        sc.PROCEDURAL_ONLY


@pytest.mark.parametrize("member", [
    _m("a/1", "adjacent_power"),
    _m("a/1", None, "adjacent"),
])
def test_adjacency_in_either_rubric_is_adjacent_power(member):
    assert sc.classify("S", [member]).key == sc.ADJACENT_POWER


@pytest.mark.parametrize("member", [
    _m("a/1", "procedural"),
    _m("a/1", "not_dc"),
    _m("a/1"),                       # in the universe, never triaged
])
def test_the_residual_class_holds_what_nothing_else_claims(member):
    assert sc.classify("S", [member]).key == sc.PROCEDURAL_ONLY


# --- precedence -------------------------------------------------------

def test_one_datacentre_member_makes_the_site_a_datacentre():
    """A campus is a campus even when most of its applications are
    conditions discharges, which is the ordinary shape of a big site."""
    site = sc.classify("S", [_m("a/1", "procedural"), _m("a/2", "procedural"),
                             _m("a/3", "new_build")])
    assert site.key == sc.DATACENTRE


def test_a_disguise_suspect_is_never_demoted_to_adjacency():
    """The order exists for this case. Filing a site with an unexplained
    large building as 'adjacent power' would grey out the very thing the
    investigation is looking for — 'unclear beats wrong'."""
    site = sc.classify("S", [_m("a/1", "adjacent_power"), _m("a/2", "unknown")])
    assert site.key == sc.DISGUISE_SUSPECT


def test_precedence_runs_datacentre_suspect_adjacency_procedural():
    members = [_m("a/1", "procedural"), _m("a/2", "adjacent_power"),
               _m("a/3", "unknown"), _m("a/4", "new_build")]
    assert sc.classify("S", members).key == sc.DATACENTRE
    assert sc.classify("S", members[:3]).key == sc.DISGUISE_SUSPECT
    assert sc.classify("S", members[:2]).key == sc.ADJACENT_POWER
    assert sc.classify("S", members[:1]).key == sc.PROCEDURAL_ONLY


# --- the site with no planning application ---------------------------

def test_a_barbour_record_with_no_application_is_not_procedural():
    """19 live sites are Barbour project records with no planning
    application at all (measured 2026-08-27). Greying out 'NEXT
    GENERATION DATA - DATA CENTRE EXTENSION' as procedural would be a
    plain error; asserting it a datacentre would adopt Barbour's
    categorisation as ours. The class says what is true instead."""
    site = sc.classify("S", [], project_refs=("12131674",))
    assert site.key == sc.BARBOUR_ONLY
    assert site.project_refs == ("12131674",)
    assert "no verdict" in site.description


def test_a_site_with_nothing_at_all_does_not_claim_a_finding():
    assert sc.classify("S", []).key == sc.PROCEDURAL_ONLY


# --- provenance -------------------------------------------------------

def test_the_deciding_members_are_the_ones_that_produced_the_class():
    """A reporter asking why a row is greyed gets references, not an
    assertion (principle 7)."""
    site = sc.classify("S", [_m("a/1", "procedural"), _m("a/2", "unknown"),
                             _m("a/3", "unknown")])
    assert [m.application_ref for m in site.deciding] == ["a/2", "a/3"]


def test_the_residual_class_shows_every_member_as_deciding():
    """`procedural_only` is the absence of anything stronger, so the
    evidence for it is the whole membership."""
    site = sc.classify("S", [_m("a/1", "procedural"), _m("a/2", "not_dc")])
    assert len(site.deciding) == 2


def test_the_fold_prefers_dc_build_over_v1():
    assert _m("a/1", "new_build", "DC").folded == "new_build"
    assert _m("a/1", None, "DC").folded == "DC"
    assert _m("a/1").folded is None


# --- failing loudly ---------------------------------------------------

@pytest.mark.parametrize("member", [
    _m("a/1", "datacentre_ish"),
    _m("a/1", None, "PROBABLY"),
])
def test_an_unrecognised_verdict_stops_the_build(member):
    """A new rubric arriving must not fall quietly into the residual
    class, where a whole generation of verdicts would be invisible."""
    with pytest.raises(sc.SiteClassError, match="unknown"):
        sc.classify("S", [member])


def test_every_class_has_a_label_and_a_description():
    for key in sc.CLASS_ORDER:
        assert sc.CLASS_LABELS[key]
        assert len(sc.CLASS_DESCRIPTIONS[key]) > 40


def test_counts_covers_every_class_even_at_zero():
    """A class missing from the counts would read as a class that does
    not exist, rather than one nothing matched today."""
    out = sc.counts({"S": sc.classify("S", [_m("a/1", "new_build")])})
    assert set(out) == set(sc.CLASS_ORDER)
    assert out[sc.DATACENTRE] == 1 and out[sc.ADJACENT_POWER] == 0


# --- the catalogue as evidence ---------------------------------------

def test_a_barbour_title_naming_a_datacentre_settles_the_class():
    """A disguise suspect's definition begins 'no application here is
    stated as a datacentre'. When the site's own catalogue record says
    DATA CENTRE that precondition is false, and the first build showed
    the contradiction on the page: 'John Innes — Norwich Bioscience
    Institutes DATA CENTRE', badged Disguise suspect."""
    site = sc.classify("S", [_m("a/1", "unknown")],
                       ("12761990",),
                       (("12761990", "JOHN INNES - NORWICH BIOSCIENCE "
                                     "INSTITUTES DATA CENTRE"),))
    assert site.key == sc.DATACENTRE
    assert site.decided_by_catalogue
    assert "12761990" in site.provenance and "DATA CENTRE" in site.provenance


@pytest.mark.parametrize("title", [
    "NEXT GENERATION DATA - DATA CENTRE EXTENSION",
    "KAO PARK  HARLOW - PROJECT NOBEL DATACENTRE CAMPUS",
    "SOMEWHERE - DATA CENTER",
])
def test_the_catalogue_test_reads_the_variant_spellings(title):
    assert sc.classify("S", [], ("1",), (("1", title),)).key == sc.DATACENTRE


@pytest.mark.parametrize("title", [
    "STUDENT LOANS COMPANY - OFFICE REFURBISHMENT",
    "ALLEYNS SCHOOL - PROJECT CRUCIBLE",
])
def test_a_barbour_record_that_claims_nothing_stays_unclaimed(title):
    """Barbour's harvest is a sector sweep, so having a project record
    is not the same claim as being called a data centre. These keep the
    honest class rather than inheriting an assertion."""
    site = sc.classify("S", [], ("1",), (("1", title),))
    assert site.key == sc.BARBOUR_ONLY
    assert not site.catalogue_dc


def test_a_dc_positive_application_is_not_credited_to_the_catalogue():
    """`decided_by_catalogue` marks the sites that need the catalogue to
    be datacentres, so the reader can say which evidence carried it."""
    site = sc.classify("S", [_m("a/1", "new_build")], ("1",),
                       (("1", "SOMEWHERE - DATA CENTRE"),))
    assert site.key == sc.DATACENTRE
    assert not site.decided_by_catalogue
    assert "a/1" in site.provenance


def test_provenance_names_the_applications_and_counts_the_rest():
    site = sc.classify("S", [_m(f"a/{i}", "procedural") for i in range(7)])
    assert "a/0" in site.provenance and "and 3 more" in site.provenance


def test_a_catalogue_decided_site_does_not_describe_itself_as_two_things():
    """The generic datacentre description opens 'at least one
    application here is a datacentre proposal', which sat one sentence
    from a provenance line saying no application states one. A reader
    should never be shown both."""
    site = sc.classify("S", [_m("a/1", "unknown")], ("1",),
                       (("1", "SOMEWHERE - DATA CENTRE"),))
    assert site.decided_by_catalogue
    assert "at least one application" not in site.display_description.lower()
    assert "catalogue" in site.display_description.lower()
    ordinary = sc.classify("S", [_m("a/1", "new_build")])
    assert ordinary.display_description == ordinary.description
