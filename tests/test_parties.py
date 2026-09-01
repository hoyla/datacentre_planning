"""Who is behind it: what may become the operator, and what may not.

The first version of this ranked the organisations a site's documents
name and called the top one "Applicant / operator". That made Savills
the applicant on seventeen sites, because Savills writes the planning
statements, and CityFibre a party on seventy-three, because a utilities
section lists whose ducts are in the road. These tests are the rules
that replaced it, written as the cases that went wrong.

Unit tests: `site_parties` takes no connection, so every case here is
the arrangement of sources it is about rather than whatever the corpus
holds today.
"""

from __future__ import annotations

import pytest

from dcp import organisations, site_profile
from dcp.site_profile import site_parties

# A confirmed group, built here rather than read from the priors file:
# the file's contents are a person's decisions and will change, and a
# test that fails when Luke confirms a group is a test about the wrong
# thing.
ARK = organisations.Group("Ark Data Centres", "", (
    organisations.Member(
        "Ark Estates 5 Ltd", "spv_of", "confirmed",
        (organisations.Evidence("reporter", ref="test"),)),
    organisations.Member(
        "Ark Data Centres Ltd", "same_organisation", "confirmed",
        (organisations.Evidence("reporter", ref="test"),)),
))
ARK_INDEX = organisations.alias_index([ARK])
NO_ALIASES: dict = {}


def _p(result, role):
    return [p for p in result["parties"] if p.role == role]


# ---------------------------------------------------------------------------
# What the documents alone cannot do
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,mentions", [
    ("Savills", 214),          # writes the planning statement
    ("Barton Willmore", 96),   # ditto
    ("CityFibre", 73),         # named in a utilities section
])
def test_a_much_mentioned_name_does_not_become_the_operator(name, mentions):
    """The operator is an identity claim, and mentions cannot make one.

    Unchanged since 2.4 and the reason this file exists: `end_user` and
    `operator_group` say a company runs this site, which is an assertion
    across documents, and the only route to it is a confirmed alias.
    """
    out = site_parties((), [("party_applicant", name, mentions)],
                       ["Slough Borough Council"], NO_ALIASES)
    assert out["operator_group"] == ""
    assert out["end_user"] == ""
    assert name in out["named_in_documents"]
    assert f"{mentions} mentions" in out["named_in_documents"]


@pytest.mark.parametrize("name,mentions", [
    ("CityFibre", 73),
    ("CSE52 Limited", 8),
])
def test_a_document_stated_applicant_may_fill_the_applicant_field(name, mentions):
    """...but the applicant is a different claim, and weaker.

    Luke, 2026-08-26, relaxing the rule for this field only. Barbour
    states a role for 164 of 494 sites, so reading it from Barbour alone
    printed a dash — meaning "unknown" in this reader — on 330 sites,
    179 of which had an applicant stated in their own documents.

    The distinction: `end_user` asserts who runs a site across every
    document. `applicant_of_record` repeats what one application's own
    form says about itself, so no cross-document identity resolution is
    involved and no alias is needed to license it. CityFibre is the test
    of that rather than a counter-example — it holds 65 singleton sites
    of its own works, "external alterations to install generator and
    fresh air vents" at telephone exchanges, and its evidence reads
    "Applicant: CityFibre", a form field.

    The value must name its source, because the panel mixes registers.
    """
    out = site_parties((), [("party_applicant", name, mentions)],
                       ["Slough Borough Council"], NO_ALIASES)
    assert out["applicant_of_record"] == f"{name} (documents)"
    assert out["operator_group"] == ""
    assert out["end_user"] == ""


def test_barbour_still_wins_the_applicant_field_when_it_states_one():
    """The documents fill the field; they do not overrule the register."""
    barbour = (("PTNO-1", "Client", "Ark Data Centres Ltd"),)
    out = site_parties(barbour, [("party_applicant", "Savills", 214)],
                       (), NO_ALIASES)
    assert out["applicant_of_record"].endswith("(Barbour)")
    assert "Savills" not in out["applicant_of_record"]


def test_a_name_mentioned_once_does_not_reach_the_applicant_field():
    """The extractor returns phrases as well as names.

    "Applicant CSE52 Limited" and "Burges Salmon LLP representing the
    applicant" each parse as their own organisation and arrive once,
    where the real name arrives repeatedly. Without the floor the field
    reads as three companies where the documents name one.
    """
    out = site_parties((), [("party_applicant", "Applicant CSE52 Limited", 1)],
                       (), NO_ALIASES)
    assert out["applicant_of_record"] == ""


def test_a_document_name_reaches_the_operator_only_through_a_confirmed_alias():
    findings = [("party_applicant", "Ark Estates 5 Ltd", 100),
                ("party_adviser", "Savills", 214)]
    without = site_parties((), findings, (), NO_ALIASES)
    assert without["operator_group"] == ""
    assert "Ark Estates 5 Ltd" in without["named_in_documents"]

    withalias = site_parties((), findings, (), ARK_INDEX)
    assert withalias["operator_group"] == "Ark Data Centres"
    # The raw name is not rewritten: it is a row of its own, beside the
    # group, with the mention count that found it.
    row = [p for p in withalias["parties"] if p.name == "Ark Estates 5 Ltd"]
    assert row and row[0].group == "Ark Data Centres"
    assert row[0].source == "documents"
    # And Savills is still only a name the documents use often.
    assert "Savills" in withalias["named_in_documents"]


def test_a_name_below_the_floor_is_dropped_and_counted():
    findings = [("party_applicant", "Applicant", 1),
                ("party_adviser", "Applicants' transport consultants", 1),
                ("party_adviser", "Pegasus Group", 4)]
    out = site_parties((), findings, (), NO_ALIASES)
    assert out["named_in_documents"] == "Pegasus Group (4 mentions)"
    assert out["parties_named_once"] == 2
    assert all(p.name != "Applicant" for p in out["parties"])


def test_a_confirmed_alias_is_exempt_from_the_floor():
    """A person has already decided who this is; one mention is enough."""
    out = site_parties((), [("party_applicant", "Ark Data Centres Ltd", 1)],
                       (), ARK_INDEX)
    assert out["operator_group"] == "Ark Data Centres"
    assert out["parties_named_once"] == 0


# ---------------------------------------------------------------------------
# What Barbour states
# ---------------------------------------------------------------------------

DIDCOT = (
    ("12890752", "End user", "Amazon UK Services Limited"),
    ("12890752", "Planner", "Lichfields"),
    ("12660337", "Bidder", "Laing O'Rourke Delivery Limited Head Office"),
)


def test_a_stated_end_user_outranks_a_much_mentioned_applicant():
    out = site_parties(DIDCOT,
                       [("party_applicant", "RWE Generation UK PLC", 271)],
                       ["South Oxfordshire District Council"], NO_ALIASES)
    # The name, and the register that states it: every value in this
    # panel names its source, because the panel mixes registers and a
    # reader cannot otherwise tell Barbour's word from the documents'.
    assert out["end_user"] == "Amazon UK Services Limited (Barbour)"
    assert "RWE" in out["named_in_documents"]
    assert out["parties_source"] == "Barbour project record and documents"


def test_an_adviser_role_is_an_adviser_and_the_rest_are_kept_apart():
    out = site_parties(DIDCOT, (), (), NO_ALIASES)
    assert out["advisers"] == "Lichfields (Barbour)"
    assert [p.barbour_role for p in _p(out, "other")] == ["Bidder"]
    # Every Barbour party reaches the long-format rows, whatever its
    # role: the sheet is what the site row is a summary of.
    assert len(out["parties"]) == len(DIDCOT)


def test_the_barbour_reference_travels_with_the_name():
    out = site_parties(DIDCOT, (), (), NO_ALIASES)
    assert {p.source_ref for p in out["parties"]} == {"12890752", "12660337"}
    assert all(p.source == "barbour" for p in out["parties"])


def test_contact_details_never_leave_raw_metadata():
    """The role blocks carry people; only the organisations come out."""
    meta = {"Role_4": "Client", "CyName_4": "Ark Estates 5 Ltd",
            "Fname_4": "A", "Lname_4": "Person", "Title_4": "Director",
            "CyAddr1_4": "1 Somewhere", "CyURL_4": "www.example.com",
            "CyFax_4": "01234 567890"}
    assert site_profile.barbour_parties(meta, "12879308") == [
        ("12879308", "Client", "Ark Estates 5 Ltd")]


def test_a_role_without_a_company_is_not_a_party():
    assert site_profile.barbour_parties(
        {"Role_4": "Client", "Fname_4": "A"}, "x") == []


def test_the_principal_client_lives_in_a_fixed_slot():
    """Barbour's record for Saunderton, as it stands: the client is in
    `CyName_Client`, no numbered slot says Client, and the first version
    of this function returned nothing for it."""
    meta = {"CyName_Client": "Avalon DC Limited", "CyAddr1_Client": "1 Somewhere",
            "CyEmail_Client": "x@example.com",
            "Role_4": "Planner", "CyName_4": "Turley",
            "Role_5": "Civil engineer", "CyName_5": "WSP"}
    out = site_profile.barbour_parties(meta, "10234430")
    assert out[0] == ("10234430", "Client", "Avalon DC Limited")
    assert ("10234430", "Planner", "Turley") in out
    assert not any("example.com" in x or "Somewhere" in x for t in out for x in t)


def test_a_client_in_both_slots_is_one_party():
    meta = {"CyName_Client": "Interxion", "Role_4": "Client", "CyName_4": "Interxion",
            "Role_5": "Client", "CyName_5": "Goldacre Ventures"}
    out = site_profile.barbour_parties(meta, "11891737")
    assert [n for _, r, n in out if r == "Client"] == ["Interxion", "Goldacre Ventures"]


# ---------------------------------------------------------------------------
# The authority, and absence
# ---------------------------------------------------------------------------

def test_the_authority_is_the_register_not_a_finding():
    out = site_parties((), [("party_adviser", "Slough Borough Council", 40)],
                       ["Hertsmere Borough Council"], NO_ALIASES)
    assert out["authority"] == "Hertsmere Borough Council"
    # A council named in the documents is not demoted to an adviser
    # either; it is simply not a party to the scheme.
    assert "Slough" not in out["named_in_documents"]


def test_a_site_spanning_two_registers_names_both():
    out = site_parties((), (), ["Vale of White Horse District Council",
                                "South Oxfordshire District Council"],
                       NO_ALIASES)
    assert out["authority"] == ("Vale of White Horse District Council, "
                                "South Oxfordshire District Council")


def test_absence_says_so():
    out = site_parties((), (), (), NO_ALIASES)
    assert out["parties_source"] == site_profile.PARTIES_ABSENT
    assert out["operator_group"] == out["end_user"] == ""
    assert out["parties"] == ()


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

def _rotations(seq):
    return [list(seq[i:]) + list(seq[:i]) for i in range(len(seq))]


def test_the_result_does_not_depend_on_the_order_rows_arrive_in():
    """`array_agg` is unordered, and a release is checked by diffing."""
    barbour = list(DIDCOT)
    findings = [("party_adviser", "Ethos Engineering", 12),
                ("party_adviser", "Tetra Tech Limited", 12),
                ("party_applicant", "RWE Generation UK PLC", 12)]
    seen = set()
    for b in _rotations(barbour):
        for f in _rotations(findings):
            out = site_parties(b, f, ["Cherwell District Council"], NO_ALIASES)
            seen.add((out["end_user"], out["advisers"],
                      out["named_in_documents"],
                      tuple((p.role, p.name) for p in out["parties"])))
    assert len(seen) == 1, seen


# Uttlesford/UTT/23/2686/FUL as the corpus holds it, cut to the names
# that matter. Michael Bingham — "Associate Planner at Murray Planning"
# in the documents that name him — is filed twice as the applicant and
# twice as the adviser, and it was that 2–2 that made two builds of one
# snapshot disagree about who the scheme was applied for by.
UTTLESFORD = [
    ("party_applicant", "CityFibre", 14),
    ("party_applicant", "Michael Bingham", 2),
    ("party_adviser", "Michael Bingham", 2),
    ("party_applicant", "R8 Tool Hire Ltd", 2),
    ("party_adviser", "Murray Planning Associates Ltd", 5),
    ("party_applicant", "Murray Planning Associates Ltd", 2),
]


def test_the_panel_does_not_depend_on_the_order_the_findings_arrive_in():
    """One name, two families, the same count in each.

    The order test above it uses three distinct names, so no name is
    contested and the rule that decides a contest is never reached.
    This is the arrangement that got past it: `site_parties` was handed
    a list built from a dictionary, whose order is the order Postgres
    returned the rows in, and the family that won a tie was whichever
    of the two was iterated first. Two builds of one snapshot disagreed
    on Redcar/R/2022/0351/FF and Uttlesford/UTT/23/2686/FUL, 2026-09-01.

    Permutations rather than rotations: a rotation of six rows reaches
    six of the 720 orders, and the pair that has to swap need not be
    adjacent.
    """
    import itertools
    seen = {
        (out["applicant_of_record"], out["advisers"],
         out["named_in_documents"],
         tuple((p.role, p.name) for p in out["parties"]))
        for order in itertools.permutations(UTTLESFORD)
        for out in [site_parties((), list(order), (), NO_ALIASES)]
    }
    assert len(seen) == 1, seen


def test_a_name_the_documents_call_applicant_and_adviser_alike_is_an_adviser():
    """A tie is the documents failing to say which, so take the weaker.

    `applicant_of_record` answers "who is behind this scheme" and is the
    strongest claim on the panel; `advisers` says a firm acted for
    whoever is. Filing a tie as the applicant is therefore the expensive
    way to be wrong, and the corpus agrees: of the ~36 names whose two
    counts tie at or above the floor and at the name's own maximum
    (measured twice, 2026-09-01), essentially all are advisers, agents
    or case officers — "BUJ Architects", "Mr D Chadwick, Chadwick Town
    Planning Limited", "Matthew Payne, Consultant Engineer" — with one
    developer-shaped compound string the arguable exception, so the
    direction rests on the cost asymmetry plus the overwhelming
    majority, not on unanimity.

    The comment this replaces said ties went to the family declared
    first in `signal_families`, which is applicant. That order decides
    which regex claims a raw label, and had never been the rule here.
    """
    out = site_parties((), UTTLESFORD, (), NO_ALIASES)
    assert out["applicant_of_record"] == "CityFibre, R8 Tool Hire Ltd (documents)"
    assert "Michael Bingham" in out["advisers"]
    assert "Michael Bingham" not in out["applicant_of_record"]
    # The count is untouched by where the name is shown: it is one
    # organisation the documents name four times, not two named twice.
    assert "Michael Bingham (4)" in out["named_in_documents"]


def test_the_family_that_names_an_organisation_most_still_wins():
    """The tie order breaks ties; it does not overrule a count.

    Murray Planning Associates Ltd is named as the adviser five times
    and as the applicant twice, so it is an adviser — and would be under
    either direction of the tie-break, which is what makes it the check
    that the direction is only reached on a tie.
    """
    out = site_parties((), UTTLESFORD, (), NO_ALIASES)
    assert "Murray Planning Associates Ltd" in out["advisers"]
    assert "Murray Planning" not in out["applicant_of_record"]


def test_one_organisation_in_two_roles_is_two_rows_not_one_merged():
    """The long format keeps roles apart; §3.2 forbids combining them."""
    rows = (("1", "Mech.& Elec Engineer", "Black & White Engineering Ltd."),
            ("1", "Energy Consultant", "Black & White Engineering Ltd."))
    out = site_parties(rows, (), (), NO_ALIASES)
    assert len(out["parties"]) == 2
    assert {p.role for p in out["parties"]} == {"adviser", "other"}
