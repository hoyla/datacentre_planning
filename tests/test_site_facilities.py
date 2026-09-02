"""The facility prior: the relation is validated, never the values.

The contract under test (dcp/site_facilities.py, issue #247): every
facility carries a citable identity source; an attribution references
exactly one of a claim or a planning document and never restates a
figure; a dead site key or a dangling claim reference fails loudly.
The claim-reference check runs here against the real claims files, so
CI enforces it on every push even though no exporter consumes the
prior yet.
"""

from pathlib import Path

import pytest
import yaml

from dcp import site_facilities as sf


def _write(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "site_facilities.yaml"
    p.write_text(yaml.safe_dump(payload))
    return p


def _entry(**overrides) -> dict:
    base = {
        "site_key": "PTNO-1",
        "facilities": [{
            "id": "LONDON7",
            "identity": [{
                "source": "operator_roster",
                "url": "https://example.com/campus",
                "date": "2026-08-30",
                "snapshot": "example-campus",
            }],
            "attributions": [{
                "kind": "announced capacity",
                "claim": "EXAMPLE LONDON7",
            }],
        }],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# The real file
# ---------------------------------------------------------------------------

def test_the_real_prior_loads_and_every_entry_is_wellformed():
    loaded = sf.load_facilities()
    assert loaded, "the seeded prior should not load empty"
    assert "PTNO-12301553" in loaded, "Stockley Park is the worked case"


def test_the_worked_case_holds_its_conflict_unresolved():
    """Stockley's LONDON7 carries both the operator figure and the
    planning milestone — the wrinkle is recorded, not resolved."""
    stockley = sf.load_facilities()["PTNO-12301553"]
    london7 = next(f for f in stockley["facilities"] if f["id"] == "LONDON7")
    kinds = {"claim" if a.get("claim") else "document"
             for a in london7["attributions"]}
    assert kinds == {"claim", "document"}


def test_every_claim_reference_in_the_real_file_resolves():
    from dcp import capacity_claims as cc
    known = {c.claim_name for c in cc.load_operator_claims()}
    known |= {c.claim_name for c in cc.load_register_demand_claims()}
    known |= {c.claim_name for c in cc.load_ch_claims()}
    sf.require_known_claims(sf.load_facilities(), known)


def test_a_dangling_claim_reference_fails_loudly():
    with pytest.raises(ValueError, match="references claims"):
        sf.require_known_claims(
            {"PTNO-1": {"facilities": [{
                "id": "X",
                "attributions": [{"kind": "k", "claim": "NO SUCH CLAIM"}],
            }], "note": ""}},
            {"A REAL CLAIM"})


# ---------------------------------------------------------------------------
# Liveness — the site_aliases contract
# ---------------------------------------------------------------------------

def test_a_dead_site_key_fails_the_build():
    with pytest.raises(ValueError, match="not live"):
        sf.require_live({"PTNO-DEAD": {"facilities": [], "note": "n"}},
                        {"PTNO-ALIVE"})


def test_live_keys_pass():
    sf.require_live({"PTNO-1": {"facilities": [], "note": "n"}}, {"PTNO-1"})


# ---------------------------------------------------------------------------
# The loader refuses what the design forbids
# ---------------------------------------------------------------------------

def test_a_restated_value_is_rejected(tmp_path):
    e = _entry()
    e["facilities"][0]["attributions"][0]["value_mw"] = 32.5
    with pytest.raises(ValueError, match="ever restated"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_an_attribution_needs_exactly_one_reference(tmp_path):
    e = _entry()
    e["facilities"][0]["attributions"][0]["document_sha256"] = "abc123"
    e["facilities"][0]["attributions"][0]["application"] = "X/1"
    with pytest.raises(ValueError, match="exactly one"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))

    e2 = _entry()
    del e2["facilities"][0]["attributions"][0]["claim"]
    with pytest.raises(ValueError, match="exactly one"):
        sf.load_facilities(_write(tmp_path, {"sites": [e2]}))


def test_a_document_attribution_names_its_application(tmp_path):
    e = _entry()
    e["facilities"][0]["attributions"][0] = {
        "kind": "design capacity", "document_sha256": "abc123"}
    with pytest.raises(ValueError, match="names no application"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_an_unknown_identity_source_fails(tmp_path):
    e = _entry()
    e["facilities"][0]["identity"][0]["source"] = "press_release"
    with pytest.raises(ValueError, match="known sources"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_an_identity_source_missing_its_locator_fails(tmp_path):
    e = _entry()
    del e["facilities"][0]["identity"][0]["date"]
    with pytest.raises(ValueError, match="missing date"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_a_facility_without_identity_fails(tmp_path):
    e = _entry()
    e["facilities"][0]["identity"] = []
    with pytest.raises(ValueError, match="no\\s+identity source"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_a_duplicate_facility_id_fails(tmp_path):
    e = _entry()
    e["facilities"].append(dict(e["facilities"][0]))
    with pytest.raises(ValueError, match="twice"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_an_empty_entry_must_explain_itself(tmp_path):
    e = {"site_key": "PTNO-1", "facilities": []}
    with pytest.raises(ValueError, match="must explain"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))
    e["note"] = "the roster is unciteable until the datasheet is held"
    loaded = sf.load_facilities(_write(tmp_path, {"sites": [e]}))
    assert loaded["PTNO-1"]["facilities"] == []


def test_an_attribution_without_a_kind_fails(tmp_path):
    e = _entry()
    del e["facilities"][0]["attributions"][0]["kind"]
    with pytest.raises(ValueError, match="no kind"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_an_operator_roster_must_name_its_snapshot(tmp_path):
    """A url alone is not a source of record: the page can change and
    no register stands behind it."""
    e = _entry()
    del e["facilities"][0]["identity"][0]["snapshot"]
    with pytest.raises(ValueError, match="missing snapshot"):
        sf.load_facilities(_write(tmp_path, {"sites": [e]}))


def test_an_unheld_snapshot_fails_loudly():
    with pytest.raises(ValueError, match="not held"):
        sf.require_held_snapshots({"PTNO-1": {"facilities": [{
            "id": "X",
            "identity": [{"source": "operator_roster",
                          "url": "https://example.com",
                          "date": "2026-08-30",
                          "snapshot": "no-such-snapshot"}],
        }], "note": ""}})


def test_every_snapshot_the_real_file_names_is_held():
    sf.require_held_snapshots(sf.load_facilities())


def test_the_planning_reference_is_a_content_hash_not_a_drive_id():
    """The durable address is the hash; the Drive id is a fact about
    one upload of it, and lives in document_drive_files."""
    stockley = sf.load_facilities()["PTNO-12301553"]
    hashes = [src["document_sha256"]
              for f in stockley["facilities"]
              for src in f.get("identity") or []
              if src["source"] == "planning_document"]
    assert hashes, "the worked case cites planning documents"
    for h in hashes:
        assert len(h) == 16 and all(c in "0123456789abcdef" for c in h), h


def test_a_missing_file_loads_empty(tmp_path):
    assert sf.load_facilities(tmp_path / "absent.yaml") == {}


def test_the_defaults_are_absolute_so_a_build_cannot_lose_the_layer():
    """Both defaults resolve against the package root, not the cwd.

    The mechanism is pinned rather than the site count, which grows.
    A relative default is invisible from inside the module: the loader
    returns {} for an absent file by design, so the layer disappears
    and every guard downstream then passes with nothing to check.
    """
    assert sf.FACILITIES_PATH.is_absolute()
    assert sf.SNAPSHOT_DIR.is_absolute()


def test_the_prior_loads_the_same_from_another_working_directory(
        tmp_path, monkeypatch):
    """The failure this is for: a build run from anywhere else.

    Measured before the fix — six sites from the repository root, zero
    from elsewhere, with `require_live` and `require_held_snapshots`
    both passing vacuously over the empty result.
    """
    from_root = sf.load_facilities()
    assert from_root, "the committed prior is not empty"

    monkeypatch.chdir(tmp_path)
    assert set(sf.load_facilities()) == set(from_root)
    sf.require_held_snapshots(sf.load_facilities())


def test_an_empty_load_cannot_satisfy_require_live(tmp_path, monkeypatch):
    """The vacuous pass is the reason the relative default mattered.

    `require_live` checks the keys it is handed against the live set,
    so a load that returned nothing agreed with *any* corpus — including
    one holding none of these sites. From another directory it must now
    raise, exactly as it does from the root.
    """
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="not live"):
        sf.require_live(sf.load_facilities(), set())



# ---------------------------------------------------------------------------
# Where a facility is, with the source that says so (2026-09-02)
# ---------------------------------------------------------------------------

def _located(**loc) -> dict:
    fac = _entry()["facilities"][0]
    fac["location"] = loc
    return _entry(facilities=[fac])


def test_a_location_needs_a_source_and_a_date(tmp_path):
    p = _write(tmp_path, {"sites": [_located(address="1 Example Road")]})
    with pytest.raises(ValueError, match="missing source, date"):
        sf.load_facilities(p)


def test_a_location_must_say_where(tmp_path):
    p = _write(tmp_path, {"sites": [_located(source="a charge", date="2026-09-02")]})
    with pytest.raises(ValueError, match="says nothing about where"):
        sf.load_facilities(p)


def test_one_coordinate_without_the_other_fails(tmp_path):
    p = _write(tmp_path, {"sites": [_located(source="s", date="2026-09-02", lat=51.5)]})
    with pytest.raises(ValueError, match="one coordinate without the other"):
        sf.load_facilities(p)


def test_swapped_coordinates_are_caught(tmp_path):
    p = _write(tmp_path, {"sites": [_located(source="s", date="2026-09-02",
                                             lat=-0.62, lon=51.52)]})
    with pytest.raises(ValueError, match="not in the UK"):
        sf.load_facilities(p)


def test_an_unknown_location_key_fails(tmp_path):
    p = _write(tmp_path, {"sites": [_located(source="s", date="2026-09-02",
                                             postcode="SL1 4PN", mw=6.6)]})
    with pytest.raises(ValueError, match="unknown keys"):
        sf.load_facilities(p)


def test_a_postcode_alone_with_its_source_is_enough(tmp_path):
    p = _write(tmp_path, {"sites": [_located(source="permit EPR/X", date="2026-09-02",
                                             postcode="SL1 4HA")]})
    loaded = sf.load_facilities(p)
    assert loaded["PTNO-1"]["facilities"][0]["location"]["postcode"] == "SL1 4HA"


def test_rows_say_not_yet_found_rather_than_leaving_a_blank(tmp_path):
    p = _write(tmp_path, {"sites": [_entry()]})
    rows = sf.facility_rows(sf.load_facilities(p))
    assert rows[0]["location_status"] == "not yet found"
    assert rows[0]["address"] == "" and rows[0]["claims"] == ["EXAMPLE LONDON7"]


def test_the_real_file_seeds_slough_london10_with_its_source():
    rows = {(r["site_key"], r["facility"]): r
            for r in sf.facility_rows(sf.load_facilities())}
    l10 = rows[("PTNO-12216044", "LONDON10")]
    assert l10["location_status"] == "recorded"
    assert l10["postcode"] == "SL1 4PN" and "Companies House" in l10["location_source"]
    assert rows[("PTNO-12216044", "LONDON4")]["location_status"] == "not yet found" \
        if ("PTNO-12216044", "LONDON4") in rows else True
