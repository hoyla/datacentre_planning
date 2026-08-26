"""Tests for the Companies House scheme-SPV sweep.

Two committed files and one module. `companies-house-spvs.yaml` is the
hand-adjudicated half — which company is which scheme — and every
assertion in it has to carry evidence and a confidence a reader can
weigh. `companies-house-ownership.yaml` is generated, and the thing worth
asserting about it is that the negatives were measured rather than
inherited: that the charges endpoint was actually asked, and that a
company which has filed no accounts is recorded as disclosing nothing
rather than left looking like a gap in the sweep.
"""

from __future__ import annotations

import re

import pytest
import yaml

from dcp import capacity_claims as cc
from dcp import companies_house as ch

CONFIDENCE = {"confirmed", "probable", "tentative"}
# Eight digits, or two letters and six. Overseas entities are OE plus six
# digits and Scottish companies SC plus six, both of which fit the second
# form; the aliases loader already enforces the same shape.
NUMBER = re.compile(r"^(\d{8}|[A-Z]{2}\d{6})$")

# The site records the materialisation work has flagged as over-merged.
# A mapping through one of them is a lead, not an attribution, however
# good the company evidence is.
CLUSTER_SITES = {5, 59, 61, 444}


@pytest.fixture(scope="module")
def spvs():
    return yaml.safe_load(ch.SPV_REGISTER_PATH.read_text())


@pytest.fixture(scope="module")
def ownership():
    path = ch.EXTERNAL / "companies-house-ownership.yaml"
    return yaml.safe_load(path.read_text())


# ---------------------------------------------------------------------------
# The hand-adjudicated register

def test_every_company_number_is_well_formed(spvs):
    """A mistyped company number does not fail loudly — it silently
    attaches a scheme to the wrong company. Same rule the aliases loader
    applies, because these numbers are join keys the newsroom uses."""
    for c in spvs["companies"]:
        assert NUMBER.match(c["company_number"]), c


def test_every_assertion_carries_evidence_and_a_confidence(spvs):
    for c in spvs["companies"]:
        assert c["confidence"] in CONFIDENCE, c["registered_name"]
        assert len(c.get("evidence", "").strip()) >= 40, c["registered_name"]


def test_a_cluster_site_is_never_asserted_without_a_caution(spvs):
    """Site 61 carries 308 applications across about six campuses. Naming
    the campus is not the same as naming the site record, and an entry
    that maps to one of these must say so rather than let a reader read
    it as a clean attribution."""
    for c in spvs["companies"]:
        if c.get("site_id") in CLUSTER_SITES:
            assert c.get("caution"), c["registered_name"]
            assert c["confidence"] != "confirmed", c["registered_name"]


def test_unresolved_names_are_recorded_not_dropped(spvs):
    """A name that resolves to nothing is a finding about the record. The
    next person should not have to rediscover that the search was run."""
    unresolved = spvs["unresolved"]
    assert len(unresolved) >= 5
    for u in unresolved:
        assert u["where"] and u["searched"]
        assert len(u["result"].strip()) >= 40, u["name"]
    names = {u["name"] for u in unresolved}
    # Two applicants of record that exist in the planning file and not on
    # the register at all — the shape of failure this list is for.
    assert "Avalon DC Limited" in names
    assert "BGO Code Propco Limited" in names


def test_no_company_appears_twice(spvs):
    numbers = [c["company_number"] for c in spvs["companies"]]
    assert len(numbers) == len(set(numbers))


# ---------------------------------------------------------------------------
# The generated ownership record

def test_charges_were_probed_for_every_company(ownership):
    """`has_charges` on the company profile read false for 44 of the 49
    companies here that do carry charges. Gating the request on it would
    have recorded 44 negatives that were never measured — the probe has
    to be able to see before an absence means anything."""
    for c in ownership["companies"]:
        assert c["charges_probed"] is True, c["company_name"]


def test_a_company_with_no_accounts_says_so(ownership):
    """Filing nothing is a disclosure of nothing, with a date. It is not
    the same as a company this sweep failed to read."""
    for c in ownership["companies"]:
        assert c["discloses_nothing_no_accounts_filed"] == (
            not c["accounts_filed"]), c["company_name"]
    silent = [c for c in ownership["companies"]
              if c["discloses_nothing_no_accounts_filed"]]
    assert silent, "expected some companies to have filed no accounts"


def test_no_registrable_person_is_a_statement_not_an_empty_register(ownership):
    """An overseas LP is not a registrable relevant legal entity, so the
    PSC page of a US-parented scheme reads as a statement. Recording it as
    an empty list would lose the disclosure."""
    flagged = [c for c in ownership["companies"]
               if c["reads_as_no_registrable_person"]]
    assert flagged
    for c in flagged:
        assert c["psc"]["statements"], c["company_name"]


def test_shareholders_reach_the_companies_the_psc_register_cannot(ownership):
    """The confirmation statement answers "who holds the shares" for
    companies whose PSC page says nobody has significant control. If the
    generated file lost that, the ownership half of this sweep would be
    back to the register that cannot see."""
    dark = [c for c in ownership["companies"]
            if c["reads_as_no_registrable_person"]]
    named = [c for c in dark if c["shareholders"]]
    assert named, "no company with a silent PSC page names a shareholder"
    court = next(x for x in ownership["companies"]
                 if x["company_number"] == "14045228")
    assert court["reads_as_no_registrable_person"]
    assert court["shareholders"][0]["holder"] == "UK COURT LANE DC HOLDINGS, LP"


def test_an_empty_shareholder_list_is_explained_by_the_form(ownership):
    """Overseas entities and LLPs do not file a CS01 at all, so an empty
    shareholder list for one of them is the form not existing rather than
    a filing this sweep could not read."""
    empty = [c for c in ownership["companies"] if not c["shareholders"]]
    no_form = [c for c in empty
               if c["type"] in {"registered-overseas-entity", "llp"}]
    assert len(no_form) >= 15
    # And every overseas entity discloses through the other route.
    for c in ownership["companies"]:
        if c["type"] == "registered-overseas-entity":
            assert c["psc"]["persons"] or c["psc"]["statements"], \
                c["company_name"]


def test_the_worked_example_is_intact(ownership):
    """UK Court Lane DC Ltd: no registrable person, and a charges register
    that names two lenders where the PSC page names nobody."""
    c = next(x for x in ownership["companies"]
             if x["company_number"] == "14045228")
    assert c["reads_as_no_registrable_person"]
    lenders = {p for ch_ in c["charges"] for p in ch_["persons_entitled"]}
    assert any("Nfo Holdings" in n for n in lenders)
    assert any("Trimont" in n for n in lenders)


# ---------------------------------------------------------------------------
# What the sweep changed in the claims store

def test_court_lane_is_reconciled_not_averaged():
    """The 103.3 MW and the 140 MW are different quantities, and the note
    says which. Neither figure is adjusted toward the other."""
    claims = {c.claim_name: c for c in cc.load_ch_claims()}
    court = claims["Court Lane Industrial Estate, Iver"]
    assert court.value == 103.3
    assert court.quantity_type == "scheme_capacity"
    note = court.attrs["note"]
    assert "103.32" in note and "139.5" in note and "140MW" in note
    assert "IT load" in note


def test_the_new_sources_are_all_scanned_filings():
    doc = cc.load_ch_document()
    keys = {s["key"] for s in doc["sources"]}
    assert {"ark_estates_2_fy2025", "hfd_datavita_fy2025",
            "vantage_uk_fy2025",
            "segro_pure_premier_park_fy2025"} <= keys
    for s in doc["sources"]:
        assert s["scanned"] is True, s["key"]


def test_vantage_states_a_capacity_after_all():
    """The 2026-08-20 survey listed Vantage among five operators
    disclosing none. Its FY2025 accounts carry a SECR IT load, and it is
    loaded as a company total because that is what it is."""
    claims = {c.claim_name: c for c in cc.load_ch_claims()}
    v = claims["Vantage Data Centers UK Limited — total IT load"]
    assert v.value == 41.19 and v.unit == "MW"
    assert v.company_level is True
    assert v.quantity_type == "it_load"


def test_a_pipeline_that_depends_on_a_consent_is_kept_separate():
    """Ark Estates 2 states three tranches in one sentence. Summing them
    would state a total the company did not state, and would hide that
    24 MW of it needs a permission the company does not have."""
    claims = {c.claim_name: c for c in cc.load_ch_claims()}
    built = claims["Union Park"]
    subject = claims["Union Park (subject to planning permission)"]
    assert built.value == 24 and built.stage == "built"
    assert subject.value == 24
    assert "planning permission" in subject.stage


def test_the_negative_result_is_recorded_with_its_method():
    """Segro Pure Premier Park is the counter-example to the Court Lane
    generalisation, so how hard we looked has to travel with it."""
    noted = cc.load_ch_document()["noted"]
    seg = next(n for n in noted
               if n["source"] == "segro_pure_premier_park_fy2025")
    assert "no capacity figure" in seg["subject"]
    for term in ("MW", "megawatt"):
        assert term in seg["reason"]


def test_a_zone_ceiling_is_not_loaded_as_a_site_figure():
    """DataVita's 500 MW covers a designated zone including land beyond
    any application here. Loading it matched would put it on a site page;
    loading it unmatched would put it in any total that summed the store."""
    doc = cc.load_ch_document()
    assert any("500 MW" in n["subject"] for n in doc["noted"])
    values = {(c.claim_name, c.value) for c in cc.load_ch_claims()}
    assert not any(v == 500 for _n, v in values)


# ---------------------------------------------------------------------------
# The acquisition module's own traps

def test_a_change_of_accounting_date_is_not_accounts():
    """AA01 sits one letter and one digit from AA in the filing history
    and is a change of accounting reference date. Including it fetched
    eight one-page forms in place of eight sets of accounts."""
    assert "AA01" not in ch.ACCOUNTS_TYPES
    assert {"AA", "AAMD"} == ch.ACCOUNTS_TYPES
    history = [{"type": "AA01", "date": "2025-04-23"},
               {"type": "AA", "action_date": "2024-12-31", "date": "2025-06-01"}]
    assert ch.latest_accounts(history)["type"] == "AA"


def test_latest_accounts_is_by_period_not_by_filing_date():
    """A company can file two years' accounts on consecutive days, and
    the later filing may be the earlier year."""
    history = [
        {"type": "AA", "action_date": "2024-12-31", "date": "2026-08-02"},
        {"type": "AA", "action_date": "2023-12-31", "date": "2026-08-03"},
    ]
    assert ch.latest_accounts(history)["action_date"] == "2024-12-31"


def test_a_shareholder_block_is_parsed_not_guessed():
    """The confirmation statement's text layer is what makes shareholders
    cheap — no OCR, so no silently misread character. The parser takes the
    section verbatim and records anything it cannot split as unparsed
    rather than dropping it."""
    from scripts.ch_fetch_confirmations import shareholders
    text = (
        "                             Full details of Shareholders\n"
        "The details below relate to individuals/corporate bodies that were\n"
        "shareholders during the review period\n"
        "\n"
        "Shareholding 1:         7 ORDINARY shares held as at the date of\n"
        "                        this confirmation statement\n"
        "Name:                   UK COURT LANE DC HOLDINGS, LP\n"
        "\n"
        "Shareholding 2:         39951 A ORDINARY shares held as at the date\n"
        "                        of this confirmation statement\n"
        "Name:                   NEON SEQUENCE (IVER) SCSP\n"
        "\n"
        "Shareholding 3:         1600000 DEFERRED A SHARES OF $1.00 EACH\n"
        "Name:                   THE INVESTMENT AND DEVELOPMENT OFFICE OF THE\n"
        "                        GOVERNMENT OF RAS AL KHAIMAH\n"
        "\n"
        "     Confirmation Statement\n")
    out = shareholders(text)
    assert len(out) == 3, "a wrapped description must not split an entry"
    assert out[0]["holder"] == "UK COURT LANE DC HOLDINGS, LP"
    assert "7 ORDINARY shares" in out[0]["description"]
    assert out[1]["holder"] == "NEON SEQUENCE (IVER) SCSP"
    # A holder name that wraps must not be truncated at the line break:
    # "…OFFICE OF THE" reads as a parse artefact and hides a sovereign
    # shareholder.
    assert out[2]["holder"] == (
        "THE INVESTMENT AND DEVELOPMENT OFFICE OF THE "
        "GOVERNMENT OF RAS AL KHAIMAH")


def test_a_statement_with_no_shareholder_section_yields_nothing():
    """"confirmation-statement-with-no-updates" carries no shareholder
    block at all. Returning an empty list is right; inventing one from the
    statement of capital would not be."""
    from scripts.ch_fetch_confirmations import shareholders
    assert shareholders(
        "Statement of Capital (Share Capital)\nORDINARY\n1\n") == []


def test_psc_summary_distinguishes_ceased_from_current():
    psc = {
        "items": [{"name": "Formation Agent Ltd", "kind": "corporate-entity",
                   "ceased_on": "2022-05-19"}],
        "statements": [{"statement":
                        "no-individual-or-entity-with-signficant-control",
                        "ceased_on": None}],
    }
    out = ch.summarise_psc(psc)
    assert out["reads_as_no_registrable_person"] is True
