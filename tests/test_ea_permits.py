"""Tests for the Environment Agency permit claims.

Anchors first: the committed register snapshot must reproduce the counts
recorded in data/external_sources/README.md, so a silently-replaced file
cannot change what the artefacts say. Then the two things that could
publish a wrong megawatt figure without anybody noticing — the
coordinate transform, checked against the Ordnance Survey's own worked
example, and the reader that turns a permit's prose into a number,
checked against the three sentence shapes that have actually broken it.
Then the claims contract: thermal input never acquires an electrical
megawatt value, every quote is still on the page it cites, and every
permit that yields a figure is either matched or explicitly considered
and set aside.
"""

from __future__ import annotations

import pytest
import yaml

from dcp import capacity_claims as cc
from dcp import ea_permits as ea


# ---------------------------------------------------------------------------
# Snapshot anchors

def test_register_row_count():
    assert len(ea.load_register()) == 5198


def test_candidate_count_and_generators():
    cands = ea.candidates()
    assert len(cands) == 97
    # Every candidate authorises combustion plant. Without that filter a
    # short operator token pulls in a poultry farm and a waste transfer
    # station, both of which are in the rejected list.
    assert all(c.row.is_combustion for c in cands)
    assert all(c.generators for c in cands)


def test_rejected_names_are_not_candidates():
    """The false positives recorded in the operator file stay excluded."""
    rejected = yaml.safe_load(ea.OPERATORS_PATH.read_text())["rejected"]
    holders = {c.row.name.lower() for c in ea.candidates()}
    for entry in rejected:
        name = entry["name"].split(",")[0].split("(")[0].strip().lower()
        assert not any(name in h for h in holders), entry["name"]


def test_combustion_filter_excludes_gasification():
    row = ea.RegisterRow(
        permission_number="EPR/TEST", name="x", activity=(
            "Gasification Or Liquefaction Of (I) Coal, Or (Ii) Other Fuels "
            "> 20 Megawatts Or More -  1.2 Part A (1) C) 2017"),
        document_url="", site_address="", postcode="", grid_reference="",
        easting=None, northing=None, local_authority="",
        permission_date=None)
    assert not row.is_combustion


# ---------------------------------------------------------------------------
# Geography

def test_osgb_matches_the_ordnance_survey_worked_example():
    """OS's own worked example, TG 51409 13177, is published in OSGB36;
    the ~100 m offset here is the datum shift to WGS84, not an error."""
    lat, lon = ea.osgb_to_wgs84(651409.903, 313177.270)
    assert ea.km_between(lat, lon, 52.6575703, 1.7179216) < 0.15


def test_osgb_places_a_permit_where_the_permit_says_it_is():
    """Ark's Cody Park permit prints its own grid reference, 484310
    153997, and its postcode, GU14 0LH in Farnborough."""
    lat, lon = ea.osgb_to_wgs84(484310, 153997)
    assert 51.27 < lat < 51.29
    assert -0.80 < lon < -0.78


# ---------------------------------------------------------------------------
# Reading a permit. Each of these is a sentence shape that has produced a
# wrong figure at some point in building this.

def test_total_is_not_the_first_rating_in_a_total_worded_sentence():
    """Ark Spring Park writes the fleet and the total as one sentence.
    Taking the first megawatt figure after the word "total" published a
    120 MWth site as 3.9."""
    page = ("The total thermal input of the 33 standby generators is 5 "
            "generators of 3.9 MWth and 10 generators of 2.7 MWth 12 "
            "generators of 3.6MWth and 6 generators of 5.1 MWth "
            "(approximately 120MWth in total).")
    r = ea.read_permit_text([page], "t", "EPR/TEST")
    assert r.total_mwth == 120.0
    assert r.engines_total_mwth == 120.3
    assert "agrees" in r.corroboration


def test_engine_list_spanning_bullets_is_read_whole():
    """Colt Welwyn lists its fleet as semicolon-separated bullets. Reading
    only the first bullet reported 165.6 MWth for a 266.54 MWth site."""
    page = ("The standby emergency generators comprise: - 30 generators at "
            "5.52MWth; - 4 generators at 4.49MWth; - 2 generators at "
            "3.69MWth; - 9 generators at 2.30MWth; - 30 generators at "
            "1.83MWth.")
    r = ea.read_permit_text([page], "t", "EPR/TEST")
    assert r.engines_total_mwth == 266.54
    assert r.total_mwth == 266.54  # no stated total; the sum is the claim
    assert "states no total" in r.corroboration


def test_unit_running_into_the_next_word_still_counts():
    """Equinix Slough prints "13 X 5.714 MWthgenerators" and "2 X 6.857th
    MWth". Both groups were dropped, and 331.084 read as 243.088."""
    page = ("Comprising; Data centre LD10, 2 X 0.967 MWth and 13 X 5.714 "
            "MWthgenerators and 2 X 6.857th MWth generators. The total "
            "installed capacity is 90.0 MWth.")
    r = ea.read_permit_text([page], "t", "EPR/TEST")
    assert r.engines_total_mwth == pytest.approx(89.9, abs=0.2)


def test_a_multi_site_permit_says_so():
    page = ("Operation of 64 emergency standby generators across four sites "
            "with a total thermal input of approximately 265.64 MWth.")
    r = ea.read_permit_text([page], "t", "EPR/TEST")
    assert r.total_mwth == 265.64
    assert r.covers_sites == "four"


def test_a_permit_stating_nothing_yields_nothing():
    r = ea.read_permit_text(["This permit authorises the operation of "
                             "emergency standby diesel generators."],
                            "t", "EPR/TEST")
    assert r.total_mwth is None


def test_generator_count_is_not_read_out_of_a_decimal():
    page = ("The combustion plant comprises 21 x 8.877 MWth gas oil fuelled "
            "standby generators, with an aggregated total combustion "
            "capacity on-site of approximately 186.417 MWth.")
    r = ea.read_permit_text([page], "t", "EPR/TEST")
    assert r.generator_count == 21


# ---------------------------------------------------------------------------
# The claims contract

def test_thermal_input_never_becomes_electrical_megawatts():
    """MWth does not convert to MW; it implies a range in MW, and that is
    an inference for a reporter to make in the open, not a conversion for
    a loader to do quietly."""
    assert cc.mw_of(260.0, "MWth") is None
    for c in ea.load_ea_claims():
        assert c.unit == "MWth"
        assert c.quantity_type == "thermal_input"
        assert cc.mw_of(c.value, c.unit) is None


def test_thermal_input_carries_a_caveat_and_a_label():
    assert "thermal_input" in cc.QUANTITY_CAVEATS
    assert "thermal_input" in cc.QUANTITY_LABELS
    assert "not electricity delivered" in cc.QUANTITY_CAVEATS["thermal_input"]


def test_the_caveat_sources_its_thermal_to_electrical_range():
    """An earlier version of this caveat told the reader to divide by
    "roughly 2.4 to 2.5", a figure taken from a handover and traceable to
    no source at all. The one permit stating both quantities gives 1.6 to
    2.4 MWe against an average 5.1 MWth — a spread of about two to three
    times, not a constant. The caveat has to name where that comes from
    and has to give a range, because a reader who divides by a single
    number gets a false precision this data cannot support.
    """
    caveat = cc.QUANTITY_CAVEATS["thermal_input"]
    assert "Telehouse" in caveat
    assert "two and three times" in caveat
    # And the sentence it rests on is in the store, not just in prose.
    telehouse = next(c for c in ea.load_ea_claims()
                     if c.attrs["permission_number"] == "EPR/SP3237JU")
    assert "1.6 megawatt electrical" in "".join(
        ea.permit_pages(telehouse.attrs["document_stem"])
    ) or not ea.have_permit_text()


def test_the_caveat_does_not_assume_the_fleet_equals_the_load():
    """Five permits state redundancy and each says the fleet is bigger
    than the site needs; the earlier caveat asserted that of all 42."""
    caveat = cc.QUANTITY_CAVEATS["thermal_input"]
    assert "redundancy" in caveat
    assert "N+1" in caveat
    stated = [c for c in ea.load_ea_claims() if c.attrs["redundancy"]]
    assert stated, "the reading must capture redundancy where it is stated"


def test_every_quote_is_still_on_the_page_it_cites():
    assert ea.verify_ea_quotes() == []


def test_the_batch_validates():
    claims = ea.load_ea_claims()
    assert ea.validate_ea(claims, ea.load_ea_matches()) == []


def test_claim_count_and_total():
    """The anchors recorded in data/external_sources/README.md. A
    silently-replaced snapshot, or a reader that quietly stops matching a
    sentence shape, moves one of these."""
    claims = ea.load_ea_claims()
    assert len(claims) == 42
    assert round(sum(c.value for c in claims)) == 7439
    assert max(c.value for c in claims) == 925.0


def test_variation_notices_and_the_agencys_typo_are_both_read():
    """Six figures come from a variation notice, which supersedes the
    permit it varies. A seventh — VIRTUS Slough, 180.5 MWth — is titled
    "Pemit" on gov.uk, and classifying on the word "permit" alone loses
    it."""
    kinds = {}
    for c in ea.load_ea_claims():
        kinds[c.attrs["document_kind"]] = kinds.get(c.attrs["document_kind"],
                                                    0) + 1
    assert kinds == {"permit": 35, "variation": 6, "other": 1}
    slough = next(c for c in ea.load_ea_claims()
                  if c.attrs["permission_number"] == "EPR/BP3945QX")
    assert slough.value == 180.5


def test_a_variation_says_so_in_its_stage():
    for c in ea.load_ea_claims():
        varied = c.stage.endswith(", as varied")
        assert varied == (c.attrs["document_kind"] == "variation")


def test_every_claim_is_matched_or_explicitly_set_aside():
    """A permit that was looked at and not attached to a site is a
    decision, and it is written down. Silence would be indistinguishable
    from not having looked."""
    doc = yaml.safe_load(ea.MATCHES_PATH.read_text())
    accounted = {m["claim_name"] for m in doc["matches"]}
    accounted |= {n for g in doc["considered"] for n in g["claims"]}
    assert {c.claim_name for c in ea.load_ea_claims()} <= accounted


def test_attribution_travels_with_every_claim():
    """The Environment Agency Conditional Licence requires it, so it is
    on the claim rather than in a document somebody has to remember."""
    for c in ea.load_ea_claims():
        assert c.attrs["attribution"] == ea.ATTRIBUTION
        assert "Environment Agency" in ea.ATTRIBUTION


def test_manifest_and_claims_agree_about_documents():
    manifest = ea.load_manifest()
    for c in ea.load_ea_claims():
        entry = manifest[c.attrs["permission_number"].rsplit("/", 1)[-1].lower()]
        stems = {d["stem"] for d in entry["documents"]}
        assert c.attrs["document_stem"] in stems
