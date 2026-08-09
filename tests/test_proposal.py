"""Tests for the one-line proposal extracted from a planning description.

This column is read by reporters and is quoted verbatim, so the failure
that matters is not an exception — it is a plausible-looking sentence
that describes the wrong thing. The cases below are real shapes from the
corpus: procedural preambles, the substantive clause buried after a
planning reference, and ancillary works competing with the scheme
itself.

Scores are ordinal, so nothing here asserts a number; the assertions are
about which clause wins and whether the caller is told it is procedural.
"""

from __future__ import annotations

from dcp import proposal


def test_lifts_the_clause_after_a_planning_reference():
    """The substance usually sits after the reference, with no delimiter."""
    text = ("Reserved matters application pursuant to outline permission "
            "14/1190/OUT The re-development of the site to provide up to "
            "25,020 sqm data centre (use class B8) floorspace")
    got, descriptive = proposal.summarise([text])
    assert got.startswith("The re-development of the site")
    assert "Reserved matters" not in got
    assert descriptive


def test_lifts_the_clause_after_a_semicolon():
    text = ("Discharge of condition 20 - wildlife management plan - pursuant "
            "to 13/00531/MAJOR; Hybrid planning application comprising 1) "
            "application for full planning permission for the development of "
            "two data centres and a gatehouse with associated highway works")
    got, descriptive = proposal.summarise([text])
    assert got.startswith("Hybrid planning application")
    assert descriptive


def test_prefers_the_scheme_over_ancillary_works_at_the_same_site():
    """A 28-item count is not scale.

    "Installation of 28no 2m high lighting protection finials … of existing
    data centre" once beat "Demolition … and the construction of a Data
    Centre" because it carried more numbers. Quantity now means floor area
    or capacity, and works to an *existing* facility are demoted.
    """
    ancillary = ("Installation of 28no 2m high lighting protection finials at "
                 "roof level of existing data centre that will exceed the SPZ "
                 "height limit of 23m")
    scheme = ("Demolition of 188, 190 and 200 Bath Road and the construction "
              "of a Data Centre with ancillary office space, together with "
              "landscaping and boundary treatments")
    got, _ = proposal.summarise([ancillary, scheme])
    assert got.startswith("Demolition of 188")


def test_demolition_of_existing_buildings_is_not_ancillary():
    """Clearing an existing building starts a redevelopment.

    The ancillary rule demoted every "demolition of existing buildings and
    erection of …" below the minor applications at the same site until it
    learned the difference.
    """
    scheme = ("Outline planning application for phased development involving "
              "demolition of existing buildings and the erection of new "
              "flexible use employment floorspace of 45,000 sqm")
    minor = "Erection of a single storey cycle store at the existing building"
    got, _ = proposal.summarise([scheme, minor])
    assert got.startswith("Outline planning application for phased")


def test_flags_a_site_with_nothing_but_procedure_on_record():
    """Some sites really are known only through condition discharges.

    The caller has to be able to say so rather than presenting procedural
    text as a summary of the development.
    """
    got, descriptive = proposal.summarise(["Discharge of condition 7 - Sample Panel"])
    assert not descriptive
    assert "Discharge of condition 7" in got


def test_result_is_always_a_substring_of_the_source():
    """Verbatim is the whole contract: the cell has to be quotable.

    `tidy` may change the case of the first character or close a bracket,
    so the untidied clause is what must appear in the original.
    """
    texts = [
        "Consultation from Slough Borough Council re: Demolition and "
        "redevelopment to comprise on plot (B) a data centre of up to "
        "96,000 sqm gross",
        "Variation of Condition 3 (parameters plan) of planning permission "
        "22/00123/FUL - Erection of a Data Centre with office space",
    ]
    for t in texts:
        got, _ = proposal.summarise([t])
        assert got in t, f"{got!r} is not verbatim in {t!r}"


def test_strips_register_housekeeping():
    text = ("Reserved matters application requesting consideration of "
            "appearance for construction of an off-grid data centre "
            "(pursuant to outline approval 16/06850/MAO) - AMENDED PLANS "
            "RECEIVED")
    got, _ = proposal.summarise([text])
    assert "AMENDED PLANS" not in got


def test_handles_empty_and_missing_input():
    assert proposal.summarise([]) == ("", False)
    assert proposal.summarise([None, ""]) == ("", False)


def test_tidy_sentence_cases_a_shouting_description():
    """Councils shout. 'PARTIAL DISCHARGE OF CONDITION 10' is not a title."""
    assert proposal.tidy("ERECTION OF TWO STOREY DATA CENTRE BUILDINGS") == (
        "Erection of two storey data centre buildings")
    assert proposal.tidy("erection of a data centre").startswith("Erection")
    # Mixed case is left alone: it carries the council's own capitalisation.
    assert proposal.tidy("Erection of a Data Centre (Use Class B8)") == (
        "Erection of a Data Centre (Use Class B8)")


def test_tidy_closes_a_bracket_the_split_left_open():
    assert proposal.tidy("Erection of a data centre (Use Class B8").endswith(")")
