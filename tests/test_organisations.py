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


def test_the_seed_changes_nothing_until_confirmed():
    """Every seeded member is proposed, so today's builds see an empty index."""
    groups = org.load_groups()
    assert org.alias_index(groups) == {}
    assert "0 confirmed" in org.summary(groups)
