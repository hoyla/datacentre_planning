"""Tests for the DESNZ consumption-context module.

Two families of guarantee. The anchors: the committed CSV must reproduce
the figures recorded in data/external_sources/README.md when it was
extracted (national −9%, Slough +60%, Hillingdon +36%), so a corrupted or
re-ingested file cannot silently change what the artefacts say. The
mapping: council prefixes and Barbour authority names resolve to current
DESNZ authorities across the known hard cases — Welsh dual names,
2019–2023 reorganisations, shared planning services, Northern Ireland —
and every hand-entered alias points at an authority that actually holds
both headline years.
"""

from __future__ import annotations

import re

from dcp import consumption_context as cc


def _series():
    return cc.load_series()


# ---------------------------------------------------------------------------
# Anchors (data/external_sources/README.md, recorded at extraction)

def test_national_anchor_minus_nine_percent():
    nat = cc.national_change(_series())
    assert round(nat) == -9
    # The underlying totals, not only the ratio: ≈134.2 → ≈121.5 TWh.
    s = _series()
    y0 = sum(y[2019] for y in s.values() if 2019 in y and 2024 in y)
    y1 = sum(y[2024] for y in s.values() if 2019 in y and 2024 in y)
    assert abs(y0 / 1e9 - 134.2) < 0.15, y0
    assert abs(y1 / 1e9 - 121.5) < 0.15, y1


def test_slough_and_hillingdon_anchors():
    s = _series()
    assert round(cc.change_pct(s["Slough"])) == 60
    assert round(cc.change_pct(s["Hillingdon"])) == 36


# ---------------------------------------------------------------------------
# Series shape

def test_welsh_dual_names_fold_onto_english_name():
    s = _series()
    # "Newport / Casnewydd" rows (2015–2024) fold onto the bare name the
    # 2010–2014 rows use, giving one continuous series.
    assert "Newport / Casnewydd" not in s
    newport = s["Newport"]
    assert 2010 in newport and 2024 in newport
    assert cc.context_sentence("Newport", s) is not None


def test_legacy_districts_end_in_2014_and_get_no_sentence():
    s = _series()
    # DESNZ backcasts current geography to 2015; abolished districts
    # exist only 2010–2014 and must yield None, not a crash or a figure.
    for legacy in ("Aylesbury Vale", "Selby", "Sedgemoor", "Wycombe"):
        assert max(s[legacy]) == 2014
        assert cc.change_pct(s[legacy]) is None
        assert cc.context_sentence(legacy, s) is None


def test_every_alias_targets_an_authority_with_both_years():
    s = _series()
    targets = set(cc.PREFIX_ALIASES.values()) | set(cc.BARBOUR_ALIASES.values())
    for shared in cc.PREFIX_SHARED.values():
        targets.update(shared)
    for name in targets:
        assert name in s, f"alias target {name!r} not a DESNZ authority"
        assert cc.change_pct(s[name]) is not None, \
            f"alias target {name!r} lacks a {cc.BASE_YEAR}/{cc.END_YEAR} pair"


# ---------------------------------------------------------------------------
# Mapping

def test_reorganised_districts_map_to_current_authority():
    assert cc.authority_for(["ChilternSouthBucks"]) == "Buckinghamshire"
    assert cc.authority_for(["Wycombe"]) == "Buckinghamshire"
    assert cc.authority_for(["Selby"]) == "North Yorkshire"
    assert cc.authority_for(["Barrow"]) == "Westmorland and Furness"
    assert cc.authority_for(["Sedgemoor"]) == "Somerset"


def test_camel_case_prefixes_derive_without_aliases():
    assert cc.authority_for(["CentralBedfordshire"]) == "Central Bedfordshire"
    assert cc.authority_for(["NewcastleUponTyne"]) == "Newcastle upon Tyne"
    assert cc.authority_for(["NewcastleUnderLyme"]) == "Newcastle-under-Lyme"
    assert cc.authority_for(["StAlbans"]) == "St Albans"


def test_renamed_and_awkward_authorities():
    assert cc.authority_for(["City"]) == "City of London"
    assert cc.authority_for(["Hull"]) == "Kingston upon Hull, City of"
    assert cc.authority_for(["BCP"]) == "Bournemouth, Christchurch and Poole"
    assert cc.authority_for(["Edinburgh"]) == "City of Edinburgh"


def test_northern_ireland_returns_none_without_error():
    for ni in ("CausewayGlens", "DerryStrabane"):
        assert cc.authority_for([ni]) is None
        assert cc.unrecognised([ni]) == ()  # recognised, deliberately unmapped


def test_mdc_crown_dependency_and_nsip_refs_return_none():
    assert cc.authority_for(["OldOakParkRoyal"]) is None
    assert cc.authority_for(["LondonLegacy"]) is None
    assert cc.authority_for(["Jersey"]) is None
    assert cc.authority_for(["EN0110030"]) is None
    assert cc.unrecognised(["OldOakParkRoyal", "EN0110030"]) == ()


def test_section_35_slugs_are_not_councils():
    # The watcher uses the gov.uk publication slug as the application_ref,
    # and a slug has no "/" — so the whole of it arrives here as a prefix.
    # A direction bypasses the local planning authority by construction,
    # so it is recognised-and-unmapped, never a name to add to the table.
    for slug in (
        "data-centre-campus-wapseys-wood-buckinghamshire-section-35-direction-planning-act-2008",
        "data-centre-campus-ampthill-road-bedford-in-central-bedfordshire-section-35-direction-planning-act-2008",
        "data-centre-campus-new-barn-road-dartford-section-35-direction-planning-act-2008",
    ):
        assert cc.authority_for([slug]) is None
        assert cc.unrecognised([slug]) == ()


def test_multi_council_site_needs_barbour_to_break_the_tie():
    councils = ["Slough", "Bucks"]
    assert cc.authority_for(councils) is None
    assert cc.authority_for(councils, "Slough (Phone: 01753 552288)") == "Slough"
    # Barbour may select among the candidates, never introduce a new one.
    assert cc.authority_for(councils, "Hillingdon (Phone: 01895 250111)") is None


def test_shared_planning_service_prefixes():
    assert cc.authority_for(["BromsgroveRedditch"]) is None
    assert cc.authority_for(
        ["BromsgroveRedditch"], "Bromsgrove (Phone: 01527 873232)") == "Bromsgrove"
    assert cc.authority_for(["SouthNorfolkBroadland"]) is None


def test_barbour_only_site_maps_on_barbour_name_alone():
    assert cc.authority_for([], "Wiltshire Council (Phone: 0300 456 0100)") == \
        "Wiltshire"
    assert cc.authority_for(None, "Windsor & Maidenhead (Phone: 01628 683800)") \
        == "Windsor and Maidenhead"
    assert cc.authority_for([], "St Alban (Phone: 01727 866100)") == "St Albans"
    # County councils are minerals/waste authorities; the district is
    # unrecorded, so no authority may be inferred.
    assert cc.authority_for([], "Essex County Council (Phone: 0345 743 0430)") \
        is None


def test_unknown_prefix_is_reported_not_swallowed():
    assert cc.authority_for(["Atlantis"]) is None
    assert cc.unrecognised(["Slough", "Atlantis"]) == ("Atlantis",)


# ---------------------------------------------------------------------------
# The sentence

def test_sentence_round_trips_its_own_numbers():
    s = _series()
    sent = cc.context_sentence("Slough", s)
    assert sent is not None
    m = re.search(r"authority (rose|fell) (\d+)% between 2019 and 2024, "
                  r"while nationally it (rose|fell) (\d+)%", sent)
    assert m, sent
    la_pct = int(m.group(2)) * (1 if m.group(1) == "rose" else -1)
    nat_pct = int(m.group(4)) * (1 if m.group(3) == "rose" else -1)
    assert la_pct == round(cc.change_pct(s["Slough"]))
    assert nat_pct == round(cc.national_change(s))


def test_sentence_wording_is_the_agreed_form():
    sent = cc.context_sentence("Slough")
    assert sent == (
        "Large-user electricity consumption in this site's local authority "
        "rose 60% between 2019 and 2024, while nationally it fell 9% "
        "(DESNZ sub-national statistics; large users are "
        "half-hourly-metered non-domestic consumers, which includes data "
        "centres).")


def test_sentence_never_written_for_unmapped_authority():
    assert cc.context_sentence("Atlantis") is None


def test_note_names_the_inferred_authority_and_series_end():
    note = cc.context_note("Buckinghamshire")
    assert "Buckinghamshire" in note
    assert "2024" in note
    # Journalist-facing text writes "authority" in full, never "LA".
    assert not re.search(r"\bLA\b", note)
