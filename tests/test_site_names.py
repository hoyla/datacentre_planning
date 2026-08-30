"""Site names in title case, without destroying the ones already cased.

430 sites carry a name; 178 of them arrive entirely in capitals from the
register or from Barbour and the rest do not, so the list reads as two
datasets stapled together. The design handoff sets headlines in sentence
case, and this is the display rule that gets them there.

Nothing here touches the database: `sites.display_name` keeps the
register's own spelling, which is what the workbook, the CSVs and any
citation use.
"""

from __future__ import annotations

from dcp.proposal import title_case


def test_a_shouting_name_comes_back_in_title_case():
    assert (title_case("SAUNDERTON DATA CENTRE - 4 VIRTUS DATA CENTRES")
            == "Saunderton Data Centre - 4 VIRTUS Data Centres")


def test_a_name_the_register_already_cased_is_untouched():
    """A blanket .title() would flatten these; only capitals are changed."""
    for name in ("Land East Of South Mimms Services, St Albans Road",
                 "North Weald Airfield, Merlin Way, North Weald Bassett",
                 "Durning Hall Earlham Grove Forest Gate London E7 9AB"):
        assert title_case(name) == name


def test_a_shouting_run_inside_a_cased_name_is_fixed():
    assert (title_case("Units 4 To 7 Bellway Estate NEWCASTLE UPON TYNE NE12 9SW")
            == "Units 4 To 7 Bellway Estate Newcastle Upon Tyne NE12 9SW")


def test_tokens_carrying_a_digit_are_left_alone():
    """Postcodes, plot numbers and capacities: 1GW is not 1gw."""
    assert title_case("ELSHAM WOLDS 1GW DATA CENTRE") == "Elsham Wolds 1GW Data Centre"
    assert title_case("A41 WATFORD BYPASS") == "A41 Watford Bypass"


def test_initialisms_stay_initialisms():
    assert title_case("SAUNDERTON DC LONDON") == "Saunderton DC London"
    assert title_case("PHASE II - EIA SCREENING") == "Phase II - EIA Screening"


def test_a_brand_keeps_the_capitals_it_writes_itself():
    """VIRTUS is not shouting, it is the operator's own spelling.

    The example here used to be the other way round — "VIRTUS DC LONDON"
    became "Virtus DC London", with VIRTUS standing as the shouted word
    against DC as the initialism. That was an assumption about a name
    rather than a fact about it: the operator's site and this corpus's
    own group label both write VIRTUS (Luke, 2026-08-30).
    """
    assert title_case("VIRTUS DC LONDON") == "VIRTUS DC London"
    assert (title_case("VIRTUS DATA CENTRES - LONDON 5 DATA CENTRE")
            == "VIRTUS Data Centres - London 5 Data Centre")


def test_small_words_lower_case_except_first():
    assert (title_case("LAND SOUTH EAST OF UNIT 6")
            == "Land South East of Unit 6")
    assert title_case("OF MICE") == "Of Mice"


def test_punctuation_inside_a_word_survives():
    assert title_case("KING'S CROSS - DATA-CENTRE") == "King's Cross - Data-Centre"


def test_empty_and_none_are_empty():
    assert title_case("") == ""
    assert title_case(None) == ""
