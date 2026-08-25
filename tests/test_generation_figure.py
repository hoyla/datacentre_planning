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


# ---------------------------------------------------------------------------
# §4.1e: where the adjudication has answered, it decides
# ---------------------------------------------------------------------------
# Each row is (value_mw, quote, figure_basis, plant_type, unit_count,
# unit_rating_mw). The pattern rules above read only the quote; these
# read the passage, and 17 of 72 sites' headline figure changed meaning
# when they did.

def test_a_battery_filed_as_energy_capacity_is_not_the_site_s_generation():
    """Rover Way: 1,000 MW against 'battery storage' on a planning form."""
    g = generation_figure([
        (1000.0, "Energy capacity:1000 Megawatts", "not_generation",
         "storage", None, None)])
    assert g.value_mw is None and g.basis == ""
    assert g.excluded_n == 1 and g.excluded_mw == 1000.0
    assert "1000 MW" in g.note and "not generation" not in g.note.lower()[:20]
    assert "no generation figure is shown" in g.note


def test_a_withheld_figure_is_counted_beside_the_one_that_stands():
    g = generation_figure([
        (300.0, "a collective combustion installation of more than 300mw of "
                "heat output", "not_generation", "unclear", None, None),
        (50.0, "20 no. 2,499 kW natural gas engines with a combined capacity "
               "of just under 50 MW", "stated_group_total", "prime_combustion",
         20, 2.499)])
    assert g.value_mw == 50.0 and g.basis == "as stated"
    assert g.excluded_n == 1 and g.excluded_mw == 300.0
    assert "1 further figure" in g.note and "300 MW" in g.note
    assert "plant intended to run" in g.note


def test_the_adjudicated_per_unit_rating_carries_its_count():
    g = generation_figure([
        (3.2, "112 No. standby generators (likely to be 3.2MWe)",
         "per_generator", "standby_combustion", 112, 3.2)])
    assert g.basis == "per unit" and g.unit_count == 112
    assert g.plant_type == "standby_combustion"
    assert "Not multiplied" in g.note and "standby combustion" in g.note


def test_an_unsettled_figure_says_so_rather_than_as_stated():
    g = generation_figure([
        (46.9, "Total: 46.9 MW", "unclear", "unclear", None, None)])
    assert g.basis == "not settled"
    assert "does not settle" in g.note
    assert "do not say how the plant is intended to run" in g.note


def test_an_unadjudicated_row_still_gets_the_pattern_label():
    """The corpus grows daily, so a figure adjudicated since the last
    batch must not lose its label."""
    g = generation_figure(WATFORD)
    assert g.basis == "per unit" and g.unit_count == 112


def test_the_adjudication_outranks_the_pattern_rules():
    """Watford's quote states a count and a rating, which the pattern
    rules read as per-unit; an adjudication that read the passage and
    said otherwise wins."""
    g = generation_figure([
        (3.2, "112 No.  standby generators (likely to be 3.2MWe Rolls Royce "
              "MTU DS4000 20V4000 G94LF )", "stated_group_total",
         "standby_combustion", None, None)])
    assert g.basis == "as stated"


# ---------------------------------------------------------------------------
# A ceiling is not a capacity
# ---------------------------------------------------------------------------

def test_a_figure_given_as_a_ceiling_is_marked_bounded():
    """"less than 50 MW" says where a scheme sits relative to the 50 MW
    consenting threshold, not how large its plant is."""
    for quote in ("generation totalling less than 50 MW",
                  "Energy generation capped at 50 MW across on-site and "
                  "off-site elements",
                  "total generation not exceeding 50MW",
                  "on-site generation below 50 MW"):
        g = generation_figure([(50.0, quote, "site_total",
                                   "prime_combustion", None, None)])
        assert g.bounded, quote
        assert "ceiling" in g.note


def test_up_to_is_not_a_ceiling_in_this_sense():
    """In planning "up to X" is the maximum being consented, which is the
    figure — unlike "less than X", which says only that the true number
    is somewhere below a threshold."""
    g = generation_figure([(50.0, "up to 50 MW of on-site generation",
                               "site_total", "prime_combustion", None, None)])
    assert not g.bounded


def test_an_ordinary_figure_is_not_bounded():
    g = generation_figure([(228.0, "In total, 76 of these generators would "
                               "be required", "stated_group_total",
                               "standby_combustion", None, None)])
    assert not g.bounded
