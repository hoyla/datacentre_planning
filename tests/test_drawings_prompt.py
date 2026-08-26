"""The two rules drawings-1.1 added, and why they are code and not prose.

Both come from defects the drawings-pilot-1.0 batch actually produced,
so each is tested against the shape the pilot returned rather than an
invented one.
"""

from __future__ import annotations

from dcp import drawings_prompt as dp


def _item(**kw):
    base = {"item_kind": "rating", "value_text": "", "equipment": "",
            "quantity": "", "column_header": "", "sheet_ref": "",
            "location_on_sheet": "", "tile_index": 1, "legibility": "clear",
            "note": ""}
    base.update(kw)
    return base


# --- counts may only be made on the overview ------------------------------
#
# The pilot returned "4" gensets for doc 41447's genset platform, counted
# off tile 3 -- a crop, which cut the fourth machine. The note it wrote is
# the one reproduced here.

PILOT_TILE_COUNT = _item(
    item_kind="count", value_text="4", equipment="GENSET PLATFORM",
    # `quantity` carries the model's OWN tally here, not a figure
    # written on the sheet -- which is why the note has to be read
    # before the quantity.
    quantity="4",
    tile_index=3, location_on_sheet="GENSET PLATFORM end elevation",
    note="Counted four distinct genset symbols in the end elevation "
         "rather than reading a stated quantity.")


def test_symbol_count_on_a_tile_is_demoted():
    out, n = dp.enforce_count_provenance([PILOT_TILE_COUNT])
    assert n == 1
    assert out[0]["item_kind"] == "other"
    assert "demoted from count" in out[0]["note"]
    # The reason names the tile, so the demotion is drillable.
    assert "tile 3" in out[0]["note"]
    # Nothing is destroyed: the value and its provenance survive.
    assert out[0]["value_text"] == "4"
    assert out[0]["tile_index"] == 3
    assert "Counted four distinct genset symbols" in out[0]["note"]


def test_symbol_count_on_the_overview_survives():
    it = dict(PILOT_TILE_COUNT, tile_index=0)
    out, n = dp.enforce_count_provenance([it])
    assert n == 0
    assert out[0]["item_kind"] == "count"


def test_a_stated_quantity_is_read_not_counted_and_survives_on_a_tile():
    """"2NO. MOBILE GENERATOR CONNECTION BOXES" is a label, not a count.

    Transcribing a quantity the sheet states is reading; the crop
    problem does not apply to it, and demoting it would throw away the
    class of count that is actually reliable.
    """
    it = _item(item_kind="count", value_text="2NO. MOBILE GENERATOR "
               "CONNECTION BOXES", quantity="2NO.", tile_index=13,
               note="Annotation is arranged across three lines on the "
                    "sheet and has been joined with single spaces.")
    out, n = dp.enforce_count_provenance([it])
    assert n == 0
    assert out[0]["item_kind"] == "count"


def test_enforcement_does_not_mutate_the_model_answer():
    items = [dict(PILOT_TILE_COUNT)]
    dp.enforce_count_provenance(items)
    assert items[0]["item_kind"] == "count"


def test_non_counts_pass_through_untouched():
    it = _item(value_text="1500kVA", tile_index=4)
    out, n = dp.enforce_count_provenance([it])
    assert n == 0 and out[0] == it


def test_a_count_that_explains_nothing_is_treated_as_the_models_own():
    """No stated quantity, no account of where the number came from.

    By elimination that is the model's own tally, and on a tile the
    unsafe case. Silence must not be the way through the gate.
    """
    it = _item(item_kind="count", value_text="3", equipment="chillers",
               quantity="", note="", tile_index=6)
    out, n = dp.enforce_count_provenance([it])
    assert n == 1 and out[0]["item_kind"] == "other"


# --- a table cell carries its column header -------------------------------


def test_column_header_is_a_required_field_of_every_item():
    item_schema = dp.SCHEMA["properties"]["items"]["items"]
    assert "column_header" in item_schema["required"]
    assert "column_header" in item_schema["properties"]
    # strict json_schema: every property must be required, or the request
    # is rejected before the model ever sees the sheet.
    assert set(item_schema["required"]) == set(item_schema["properties"])


def test_the_prompt_names_the_prime_standby_failure():
    """The rule is stated with the case that produced it, not abstractly."""
    text = dp.INSTRUCTIONS
    assert "column_header" in text
    assert "Prime" in text and "Standby" in text
    assert "ONE ITEM PER CELL" in text


def test_the_prompt_restricts_counting_to_the_overview():
    assert "overview" in dp.INSTRUCTIONS
    assert "A tile is a crop" in dp.INSTRUCTIONS


def test_prompt_version_moved_off_the_pilot():
    """The version tags the rows, so it must change when the rules do.

    `drawings-pilot-1.0` names the 110 transcriptions Luke reviewed;
    reusing it would file answers from a different prompt under his
    verdict.
    """
    assert dp.PROMPT_VERSION == "drawings-1.1"


def test_render_carries_the_context_through():
    out = dp.render("Fife/18/01692/FULL", "19.9MW gas peaking plant", "SLD")
    assert "Fife/18/01692/FULL" in out
    assert "19.9MW gas peaking plant" in out
    assert "SLD" in out
