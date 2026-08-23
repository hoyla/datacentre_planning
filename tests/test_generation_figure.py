"""One machine or the fleet: the label on the generation figure.

Every quote here is from the corpus as it stood on 2026-08-23, so the
cases are the sites the rule was written against rather than examples
invented to pass. The two that matter most are the negative ones: a
total that mentions "per unit" must stay "as stated", and a bare
specification with no count and no "each" must not be guessed at.
"""

from __future__ import annotations

from dcp.site_profile import generation_figure

WATFORD = [
    (3.2, "likely to be 3.2MWe Rolls Royce MTU DS4000 20V4000 G94LF"),
    (3.2, "112 No.  standby generators (likely to be 3.2MWe Rolls Royce MTU "
          "DS4000 20V4000 G94LF )"),
]
ELSHAM = [
    (50.0, "20 no. 2,499 kW natural gas engines with a combined capacity of just "
           "under 50 MW electrical power"),
    (49.9, "The on-site energy generation from the Energy Centre hereby approved "
           "shall not exceed 49.9MW."),
    (2.499, "comprising 20 no. 2,499 kW natural gas engines with a combined "
            "capacity of just under 50 MW electrical power, and up to 650 no. "
            "2,480 kW back-up diesel generators."),
    (2.48, "up to 650 no. 2,480 kW back-up diesel generators."),
]
HILLINGDON = [
    (2.0, "A 171 no. 2,000 kWe (2,500 kVa) diesel generators will operate to "
          "supply backup power to the site during power"),
]
CHILTERN = [
    (4.0, "The power reservation for the site is 100MW, therefore considering an "
          "N+1 configuration for standby  generators, 26no. 4MW generators have "
          "been considered as a worst case provision."),
    (3.3, "MV Energy Centre (including 15 no.  3.3Mw standby diesel fire "
          "generators and diesel storage)"),
]
CHESTERFIELD_TOTAL = [
    (15.0, "estimated output from that site of 1.5–3 MW per unit (7.5–15 MW "
           "total), comparable to a small hospital or university"),
]
DIDCOT_BARE_SPEC = [
    (2.873, "Mechanical Generator - 2,873 kW"),
]
PV_ROOF = [
    (1.5, "The approx. area of each roof would allow for a large array that "
          "could yield up to 1,5 MW"),
]
NORTH_AYRSHIRE_EACH = [
    (2.4, "the emergency backup generators (2.4 MW each) will have an integrated "
          "belly tank holding sufficient fuel for 4"),
]
EACH_SYSTEM_BUT_THE_ARITHMETIC_SAYS_TOTAL = [
    (104.0, "the generators would be configured as 26 generator systems each "
            "system providing 104 megawatts (MW) in an N+1 configuration."),
    (104.0, "up to 26 4 MW generators would be installed on the rooftop of the "
            "proposed Data Centre in Plot B"),
    (4.0, "we need 25 x 4 MW (N) generators to meet the load and one more as a "
          "spare to allow for maintenance"),
]


def test_watford_is_a_per_unit_rating_with_its_count():
    g = generation_figure(WATFORD)
    assert g.basis == "per unit"
    assert g.value_mw == 3.2 and g.unit_mw == 3.2 and g.unit_count == 112
    assert "112 units of 3.2 MW" in g.note
    assert "Not multiplied" in g.note


def test_elsham_stands_as_stated_with_the_fleet_named_beside_it():
    g = generation_figure(ELSHAM)
    assert g.basis == "as stated"
    assert g.value_mw == 50.0
    # The 50 MW is twenty gas engines, and the note says so; the columns
    # carry the largest fleet disclosed, which is the diesel one — named,
    # never multiplied.
    assert "total of 20 units of 2.499 MW" in g.note
    assert (g.unit_count, g.unit_mw) == (650, 2.48)
    assert "650 units of 2.48 MW, not multiplied" in g.note
    assert "1,612" not in g.note and "1612" not in g.note


def test_count_then_words_then_rating():
    g = generation_figure(HILLINGDON)
    assert g.basis == "per unit" and g.unit_count == 171 and g.unit_mw == 2.0


def test_count_no_rating_in_a_clause_of_its_own():
    g = generation_figure(CHILTERN)
    assert g.basis == "per unit" and g.unit_count == 26


def test_a_total_that_mentions_per_unit_stays_as_stated():
    g = generation_figure(CHESTERFIELD_TOTAL)
    assert g.basis == "as stated"
    assert g.unit_mw is None and g.note == ""


def test_a_bare_specification_is_not_guessed_at():
    g = generation_figure(DIDCOT_BARE_SPEC)
    assert g.basis == "as stated" and g.note == ""


def test_each_roof_is_not_each_generator():
    g = generation_figure(PV_ROOF)
    assert g.basis == "as stated"


def test_each_after_the_figure():
    g = generation_figure(NORTH_AYRSHIRE_EACH)
    assert g.basis == "per unit" and g.unit_count is None
    assert "do not say how many" in g.note


def test_arithmetic_outranks_vocabulary():
    """"each system providing 104 megawatts" beside "26 4 MW generators"."""
    g = generation_figure(EACH_SYSTEM_BUT_THE_ARITHMETIC_SAYS_TOTAL)
    assert g.basis == "as stated"
    assert (g.unit_count, g.unit_mw) == (26, 4.0)
    assert "total of 26 units of 4 MW" in g.note


def test_each_before_the_figure_within_a_few_words():
    g = generation_figure([(104.0, "26 generator systems each system providing "
                                   "104 megawatts (MW)")])
    assert g.basis == "per unit" and g.unit_mw == 104.0


def test_no_rows_no_figure():
    g = generation_figure([])
    assert g.value_mw is None and g.basis == "" and g.note == ""


def test_order_of_rows_does_not_matter():
    for rows in (WATFORD, ELSHAM, CHILTERN, EACH_SYSTEM_BUT_THE_ARITHMETIC_SAYS_TOTAL):
        rotations = [rows[i:] + rows[:i] for i in range(len(rows))]
        results = {generation_figure(r) for r in rotations}
        assert len(results) == 1, results
