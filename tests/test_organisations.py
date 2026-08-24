"""The alias file is a set of claims about who is who, and claims need rules.

Three things are held: the committed file loads and every member in it
carries evidence; a malformed or unevidenced entry is refused at load
rather than silently ignored; and nothing proposed reaches a build until
a person has confirmed it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dcp import organisations as org


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "aliases.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p


def _member(name, *, relation="same_organisation", status="confirmed", evidence=None):
    return {"name": name, "relation": relation, "status": status,
            "evidence": evidence if evidence is not None else
            [{"source": "barbour", "ref": "12345678", "date": "2026-08-23"}]}


def test_the_committed_file_loads_and_every_member_has_evidence():
    groups = org.load_groups()
    assert groups, "the seed file is empty"
    for g in groups:
        for m in g.members:
            assert m.evidence, f"{g.group} / {m.name} has no evidence"
            assert m.relation in org.RELATIONS and m.status in org.STATUSES


def test_a_member_without_evidence_is_refused(tmp_path):
    p = _write(tmp_path, {"groups": [{"group": "X", "members": [
        {"name": "X Holdings Ltd", "relation": "same_organisation",
         "status": "proposed", "evidence": []}]}]})
    with pytest.raises(org.AliasError, match="no evidence"):
        org.load_groups(p)


def test_evidence_needs_something_a_person_can_open(tmp_path):
    p = _write(tmp_path, {"groups": [{"group": "X", "members": [
        _member("X Holdings Ltd", evidence=[{"source": "barbour", "note": "trust me"}])]}]})
    with pytest.raises(org.AliasError, match="ref or a quote"):
        org.load_groups(p)


def test_one_name_one_group(tmp_path):
    p = _write(tmp_path, {"groups": [
        {"group": "A", "members": [_member("Shared Name Ltd")]},
        {"group": "B", "members": [_member("Shared Name Limited")]},   # same canonical key
    ]})
    with pytest.raises(org.AliasError, match="one name, one group"):
        org.load_groups(p)


def test_relation_and_status_are_closed_sets(tmp_path):
    p = _write(tmp_path, {"groups": [{"group": "X", "members": [
        _member("X Holdings Ltd", relation="owns")]}]})
    with pytest.raises(org.AliasError, match="relation must be"):
        org.load_groups(p)
    p = _write(tmp_path, {"groups": [{"group": "X", "members": [
        _member("X Holdings Ltd", status="probably")]}]})
    with pytest.raises(org.AliasError, match="status must be"):
        org.load_groups(p)


def test_only_confirmed_members_reach_the_index(tmp_path):
    p = _write(tmp_path, {"groups": [{"group": "Ark Data Centres", "members": [
        _member("Ark Data Centres Ltd", status="confirmed"),
        _member("Ark Estates 5 Ltd", relation="spv_of", status="proposed"),
    ]}]})
    groups = org.load_groups(p)
    index = org.alias_index(groups)
    assert org.group_for("Ark Data Centres Limited", index).group == "Ark Data Centres"
    assert org.group_for("Ark Estates 5 Ltd", index) is None
    everything = org.alias_index(groups, confirmed_only=False)
    assert org.group_for("Ark Estates 5 Ltd", everything).group == "Ark Data Centres"


def test_matching_goes_through_the_canonical_key_and_no_further(tmp_path):
    p = _write(tmp_path, {"groups": [{"group": "Vantage Data Centers", "members": [
        _member("Vantage Data Centers Ltd")]}]})
    index = org.alias_index(org.load_groups(p))
    # Spelling and legal form: the key already treats these as one name.
    assert org.group_for("Vantage Data Centres Limited", index) is not None
    assert org.group_for("Applicant is Vantage Data Centers", index) is not None
    # "UK" is a legal-form marker the key strips, like "Ltd"; still one name.
    assert org.group_for("Vantage Data Centers UK", index) is not None
    # A different name is a different company until someone says otherwise.
    assert org.group_for("Vantage Data Centers Europe", index) is None
    assert org.group_for("VDC LHR11 Limited", index) is None


def test_only_confirmed_members_reach_a_build():
    """The invariant, over whatever the file happens to hold.

    This replaced a test asserting the seed index was EMPTY, which was
    true only while nobody had confirmed anything: it failed the moment
    Luke confirmed his first member on 2026-08-24, which is a test
    pinning a date rather than a rule. What must hold is that a proposed
    member never reaches a build and a confirmed one always does.
    """
    groups = org.load_groups()
    index = org.alias_index(groups)
    for g in groups:
        for m in g.members:
            if m.status == "confirmed":
                assert index.get(m.key) is not None, \
                    f"{m.name} is confirmed and absent from the index"
            else:
                assert m.key not in index, \
                    f"{m.name} is {m.status} and reached the index"


def test_a_confirmed_member_carries_its_evidence_and_number():
    """Whatever is confirmed in the file is checkable: a person can open
    what it cites, and a join key names the register it belongs to."""
    for g in org.load_groups():
        for m in g.members:
            if m.status != "confirmed":
                continue
            assert m.evidence, f"{m.name} is confirmed with no evidence"
            assert any(e.ref or e.quote for e in m.evidence), \
                f"{m.name} cites nothing a person can open"
            if m.company_number:
                assert m.register in org.REGISTERS, \
                    f"{m.name} has a number in no named register"


# ---------------------------------------------------------------------------
# Companies House numbers, because they are a join key
# ---------------------------------------------------------------------------
# Luke, 2026-08-24: the newsroom's data journalists tie many datasets
# together on the CH company ID. A number buried in an evidence `ref`
# cannot be selected, exported or joined, so it is a field; and a
# mistyped one attaches a site to the wrong company without complaining,
# so its format is checked.

def test_a_company_number_is_read_onto_the_group_and_the_member(tmp_path):
    path = _write(tmp_path, {"groups": [{
        "group": "Microsoft", "company_number": "01624297",
        "members": [dict(_member("Microsoft MSFT MCIO Limited",
                                 status="proposed"),
                         company_number="09788396")]}]})
    g = org.load_groups(path)[0]
    assert g.company_number == "01624297"
    assert g.members[0].company_number == "09788396"


def test_a_scottish_number_is_accepted_and_upper_cased(tmp_path):
    path = _write(tmp_path, {"groups": [{
        "group": "A Group",
        "members": [dict(_member("Some Scottish Company Limited"),
                         company_number="sc123456")]}]})
    assert org.load_groups(path)[0].members[0].company_number == "SC123456"


@pytest.mark.parametrize("bad", ["1234567", "123456789", "ABC12345",
                                 "12 345 678"])
def test_a_malformed_company_number_is_refused(tmp_path, bad):
    path = _write(tmp_path, {"groups": [{
        "group": "A Group",
        "members": [dict(_member("Ark Data Centres Limited"),
                         company_number=bad)]}]})
    with pytest.raises(org.AliasError) as exc:
        org.load_groups(path)
    assert "is not a companies_house number" in str(exc.value)


def test_a_member_without_a_number_is_still_valid(tmp_path):
    """Most names in the documents are not companies at all, and a
    number nobody has looked up yet is no reason to refuse a group."""
    path = _write(tmp_path, {"groups": [{
        "group": "A Group", "members": [_member("Ark Data Centres Limited")]}]})
    assert org.load_groups(path)[0].members[0].company_number == ""


def test_a_repeated_key_is_refused_rather_than_silently_dropped(tmp_path):
    """Found 2026-08-24, when Luke added a Companies House lookup beside
    a Barbour reference by writing a second `evidence:` block. PyYAML
    keeps the last of two identical keys and says nothing, so the
    Barbour reference stopped existing while the file still showed it.
    An append-only record cannot be one where appending deletes."""
    path = tmp_path / "aliases.yaml"
    path.write_text("""
groups:
  - group: Amazon
    members:
      - name: Amazon UK Services Limited
        relation: same_organisation
        status: proposed
        evidence:
          - source: barbour
            ref: "12549436"
        evidence:
          - source: companies_house
            ref: "03223028"
""", encoding="utf-8")
    with pytest.raises(org.AliasError) as exc:
        org.load_groups(path)
    assert "given twice" in str(exc.value)
    assert "another item to the existing list" in str(exc.value)


def test_two_sources_on_one_member_both_survive(tmp_path):
    """The shape that edit should have taken."""
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon UK Services Limited", status="proposed"),
                         company_number="03223028",
                         evidence=[
                             {"source": "barbour", "ref": "12549436",
                              "note": "Client on Amazon Data Centre Didcot."},
                             {"source": "companies_house", "ref": "03223028",
                              "note": "Looked up on Lurch (Guardian company "
                                      "and land-ownership tool)."}])]}]})
    m = org.load_groups(path)[0].members[0]
    assert [e.source for e in m.evidence] == ["barbour", "companies_house"]
    assert m.company_number == "03223028"


def test_an_irish_cro_number_is_accepted_with_its_register(tmp_path):
    """Luke, 2026-08-24: "Irish companies; CRO names are 6 digits."
    Amazon Data Services Ireland is in this file, and a six-digit CRO
    number is a well-formed nothing in Companies House."""
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon Data Services Ireland Ltd"),
                         company_number="561234", register="cro")]}]})
    m = org.load_groups(path)[0].members[0]
    assert m.company_number == "561234" and m.register == "cro"


def test_a_cro_number_filed_as_companies_house_is_refused(tmp_path):
    """The collision this guards: six digits is valid at the CRO and
    malformed at Companies House, and a consumer joining on Companies
    House IDs must never be handed one silently."""
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon Data Services Ireland Ltd"),
                         company_number="561234")]}]})
    with pytest.raises(org.AliasError) as exc:
        org.load_groups(path)
    assert "is not a companies_house number" in str(exc.value)


def test_a_number_with_no_register_named_is_companies_house(tmp_path):
    """Every entry in the file predates the register field, and they are
    all Companies House numbers."""
    path = _write(tmp_path, {"groups": [{
        "group": "Ark",
        "members": [dict(_member("Ark Data Centres Limited"),
                         company_number="04958786")]}]})
    m = org.load_groups(path)[0].members[0]
    assert m.register == "companies_house"


def test_an_unknown_register_is_refused(tmp_path):
    path = _write(tmp_path, {"groups": [{
        "group": "Ark",
        "members": [dict(_member("Ark Data Centres Limited"),
                         company_number="04958786", register="delaware")]}]})
    with pytest.raises(org.AliasError) as exc:
        org.load_groups(path)
    assert "register 'delaware' is not one of" in str(exc.value)


def test_evidence_must_name_the_register_the_number_is_in(tmp_path):
    """Luke, 2026-08-24, on a worked example for an Irish company: "in
    your example 'source: companies_house' is not true — the source is
    the cro". A provenance line that misnames its own source sends a
    reader to a register that has never heard of the company."""
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon Data Services Ireland Ltd",
                                 evidence=[{"source": "companies_house",
                                            "ref": "561234"}]),
                         company_number="561234", register="cro")]}]})
    with pytest.raises(org.AliasError) as exc:
        org.load_groups(path)
    assert "cites 'companies_house'" in str(exc.value)


def test_the_cro_is_its_own_source(tmp_path):
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon Data Services Ireland Ltd",
                                 evidence=[{"source": "cro", "ref": "561234",
                                            "note": "Looked up on Lurch."}]),
                         company_number="561234", register="cro")]}]})
    m = org.load_groups(path)[0].members[0]
    assert m.evidence[0].source == "cro" and m.register == "cro"


def test_a_document_may_evidence_a_number_in_any_register(tmp_path):
    """Only a source that speaks for a company register is checked; a
    planning document quoting the company number is fine either way."""
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon Data Services Ireland Ltd",
                                 evidence=[{"source": "document", "ref": "14235",
                                            "quote": "company number 561234"}]),
                         company_number="561234", register="cro")]}]})
    assert org.load_groups(path)[0].members[0].register == "cro"


def test_an_overseas_entity_id_is_its_own_register(tmp_path):
    """Found on VDC LHR11 Limited, 2026-08-24. An OE id comes from the
    Register of Overseas Entities — the post-2022 regime for foreign
    entities owning UK land — and will not join to a company number."""
    path = _write(tmp_path, {"groups": [{
        "group": "Vantage Data Centers",
        "members": [dict(_member("VDC LHR11 Limited"),
                         company_number="OE003126", register="roe")]}]})
    m = org.load_groups(path)[0].members[0]
    assert m.company_number == "OE003126" and m.register == "roe"


def test_companies_house_evidences_the_overseas_register_too(tmp_path):
    """Companies House maintains the ROE as well as its own register, so
    a Companies House lookup is honest evidence for either."""
    path = _write(tmp_path, {"groups": [{
        "group": "Vantage Data Centers",
        "members": [dict(_member("VDC LHR11 Limited",
                                 evidence=[{"source": "companies_house",
                                            "ref": "OE003126"}]),
                         company_number="OE003126", register="roe")]}]})
    assert org.load_groups(path)[0].members[0].register == "roe"


def test_an_oe_id_also_validates_as_a_companies_house_number(tmp_path):
    """Unlike a CRO number, an OE id is a Companies House identifier: it
    resolves at /company/OE003126 and shares the shape of SC, NI and OC
    numbers. `register: roe` records that the holder is a foreign entity;
    it is not there to stop a bad join, because the join is fine."""
    path = _write(tmp_path, {"groups": [{
        "group": "Vantage Data Centers",
        "members": [dict(_member("VDC LHR11 Limited"),
                         company_number="OE003126")]}]})
    m = org.load_groups(path)[0].members[0]
    assert m.company_number == "OE003126"
    assert m.register == "companies_house"      # the namespace it is in


def test_a_member_may_carry_a_note(tmp_path):
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon UK (Head Office)"),
                         note="A Barbour label rather than a company.")]}]})
    assert "Barbour label" in org.load_groups(path)[0].members[0].note


@pytest.mark.parametrize("bad_key", ["compnay_number", "evidance", "status_"])
def test_an_unknown_key_is_refused_rather_than_ignored(tmp_path, bad_key):
    """A key this loader does not read is a key whose content does not
    exist. `note:` was dropped that way before it was a field, and a
    typo is dropped the same way — leaving a file that looks right and a
    build that behaves as though the line were never written."""
    path = _write(tmp_path, {"groups": [{
        "group": "Amazon",
        "members": [dict(_member("Amazon UK Services Limited"),
                         **{bad_key: "x"})]}]})
    with pytest.raises(org.AliasError) as exc:
        org.load_groups(path)
    assert bad_key in str(exc.value) and "ignore" in str(exc.value)
