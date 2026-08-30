"""Adjacent power relates to sites; it does not belong to one.

The tests here are on `resolve_token`, because that is where this module
failed on its first run and failed *quietly*: a token that does not
resolve raises nothing, it just yields no documentary row, and the record
drops to bare proximity with nothing to say what was lost. Four records
with recorded provenance were demoted to distance that way.

Distance is tested too, but distance is the part that cannot go wrong
silently — a wrong number is visible.
"""

from __future__ import annotations

from dcp.adjacent_power import _metres, resolve_token

SITE_OF_APP = {"Ealing/250949FUL": "PTNO-12842719"}
SITE_OF_PROJECT = {"12135970": "PTNO-12135970"}


def _resolve(token):
    return resolve_token(token, site_of_app=SITE_OF_APP,
                         site_of_project=SITE_OF_PROJECT)


def test_energy_national_names_a_site_directly():
    assert _resolve("energy_national:PTNO-12179784") == ("PTNO-12179784", "discovery")


def test_a_site_key_token_can_be_a_site_stem_not_only_a_ptno():
    """`energy_national:` carries whatever key the site had — both forms
    occur in the corpus, and neither is special-cased."""
    assert _resolve("energy_national:SITE-Newport/25/0983") == (
        "SITE-Newport/25/0983", "discovery")


def test_spatial_names_an_application_and_must_be_resolved():
    """The failure this module shipped with: compared against site keys,
    `spatial:Ealing/250949FUL` matches nothing and says nothing."""
    assert _resolve("spatial:Ealing/250949FUL") == ("PTNO-12842719", "cohort")


def test_barbour_names_a_ptno_and_must_be_resolved():
    assert _resolve("barbour:12135970") == ("PTNO-12135970", "cohort")


def test_an_unresolvable_reference_attaches_nothing():
    """A sweep from a record that no longer sits in a live site. Not an
    error — the relationship genuinely is not there any more."""
    assert _resolve("spatial:Somewhere/99/9999") == (None, None)
    assert _resolve("barbour:00000000") == (None, None)


def test_a_cohort_is_a_set_of_sites_and_so_attaches_to_none():
    assert _resolve("cohort:ark_project_union") == (None, None)


def test_a_keyword_sweep_carries_no_relationship():
    """15 of the 48 arrived this way and have only distance to go on."""
    assert _resolve("dc_keyword") == (None, None)


def test_distance_is_metres_between_two_pins():
    """VIRTUS Stockley Park to the South Mimms campus.

    Checked against the components rather than against the function it is
    testing: 0.1887 degrees of latitude is 21.0 km, 0.2388 of longitude at
    51.6 degrees north is 16.5 km, and the hypotenuse of those is 26.7 km.
    """
    d = _metres(51.499504, -0.454247, 51.688189, -0.21547)
    assert 26_500 < d < 27_000


def test_a_pin_is_no_distance_from_itself():
    assert _metres(51.5, -0.45, 51.5, -0.45) < 1
