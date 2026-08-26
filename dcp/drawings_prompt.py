"""What the vision model is asked, and the shape it must answer in.

One instruction runs through all of it: **transcribe, count, locate --
do not interpret and do not calculate.** The value of a drawing to this
investigation is that a manufacturer's general arrangement says "1500kVA
WILSON T2 ECOTRANS 33000/400V" in a title block. The danger is that a
model asked for "the transformer capacity" answers "1.5 MW", which is
a unit conversion nobody checked, on a quantity (kVA) that is not
megawatts and does not convert to them without a power factor. So the
schema has no numeric column at all. `value_text` is a string, and it is
whatever is written on the sheet.

The second instruction is that a null answer is an answer. Most sheets
in the corpus are elevations and location plans and carry nothing; the
pilot needs to know how many, because "we looked at 28 drawings and 19
carried no rating" is the result that decides whether a scale-up is
worth anything. A model that pads with plausible ratings destroys that
number, so the prompt says so in as many words and the schema lets the
list be empty.

The third is provenance. Every item has to carry the drawing number from
the title block and where on the sheet it was read, because an aggregate
claim in this project has to be drillable back to the thing it came
from, and "somewhere on a drawing" is not drillable.

drawings-1.1 adds two rules, both from defects the pilot produced
(data/drawings_pilot/drawings-pilot-1.0_review.csv, 2026-08-26):

**A table cell without its column header is not a transcription.** The
pilot read FG Wilson's generator output-ratings table and returned
`kVA 135 150`, with the note that the two numbers "appear under Prime
and Standby respectively". That note is the only thing separating a
continuous rating from a standby one -- a distinction this
investigation turns on -- and it lived in free text no consumer reads.
So every cell is now its own item and `column_header` is a required
field: `135` under `Prime`, `150` under `Standby`, two rows, each
saying which column it came from.

**A count may only be made from the overview.** The pilot returned "4"
gensets for a genset platform, counted off tile 3 -- a crop, which cut
the fourth machine. Counting symbols on a tile counts the symbols the
crop happened to include, and there is no way to tell that from a count
of the whole sheet. Counting is therefore restricted to image 0, the
whole-sheet overview; the runner enforces it (`enforce_count_provenance`)
rather than trusting the instruction, and a count that arrives claiming
a tile is demoted to `other` with the reason recorded, never dropped.
"""

from __future__ import annotations

PROMPT_VERSION = "drawings-1.1"

SYSTEM = """\
You transcribe engineering annotations from UK planning-application \
drawings. You are a transcriber, not an analyst. You never convert \
units, never sum quantities, never estimate, and never state a figure \
that is not written on the sheet in front of you."""

INSTRUCTIONS = """\
You are shown one drawing sheet from a UK planning application. The \
first image is the whole sheet, reduced -- image 0, the overview. The \
images after it are overlapping tiles of the same sheet at full \
resolution, numbered from 1, each labelled with its position in the \
tile grid. Read the tiles for detail; use the overview to understand \
the layout, to find the title block, and -- this is the only place it \
may be done -- to COUNT things. A tile is a crop: whatever is drawn \
across its edge is cut, so counting on a tile counts the crop and not \
the sheet.

CONTEXT (for orientation only -- never treat it as a source; if it \
disagrees with the sheet, the sheet wins):
  Application: {application_ref}
  Description: {description}
  Document title as filed: {title}

TRANSCRIBE, IN FULL AND VERBATIM, every annotation on this sheet that \
states any of the following:

1. An electrical, thermal or cooling rating in any unit: kW, MW, MVA, \
   kVA, kWe, MWe, MWth, kV, V, A, Hz, GWh, MWh, kWh.
2. A capacity or volume: litres, L, m3, m^3, gallons -- fuel tanks, oil \
   tanks, bunds, water storage.
3. An equipment schedule, parts list, ratings table or any other \
   tabulated data. Transcribe EVERY row of it, in the order it appears \
   on the sheet, including item numbers and quantities. Do not \
   summarise it and do not transcribe only the rows that look \
   relevant. One item per CELL, each carrying its column header -- see \
   the column-header rule below.
4. A manufacturer's name, model number or type designation for plant: \
   generators, transformers, switchgear, UPS, chillers, CRAC/CRAH \
   units, air-conditioning units, engines, tanks.
5. A count of plant items -- how many generators, transformers, \
   chillers, tanks, cable ways the sheet shows or labels. If the sheet \
   says "4no. generators", that is a stated count: transcribe it \
   wherever you read it, tile or overview, because you are reading a \
   label and not counting anything. If there is no such label and you \
   are counting symbols yourself, you may do it ONLY on image 0, the \
   overview, you must set `tile_index` to 0, and you must say in \
   `note` that you counted symbols on the overview rather than read a \
   label. A symbol count made on any tile will be rejected.

RULES, all of which matter more than completeness:

- **Verbatim.** `value_text` is exactly the characters on the sheet, \
  including the unit, the spacing and any "no.", "x" or "off". Write \
  `2no. 3MVA` if that is what it says. Never write `6 MVA`. Never write \
  `2 x 3MVA` as `23MVA`. If a figure is broken across lines, join it \
  with a single space and say so in `note`.
- **A cell carries its column header, or it is not a transcription.** \
  Where a value sits in a table, a schedule or a ratings block, give \
  ONE ITEM PER CELL and put that cell's column heading, verbatim, in \
  `column_header`. Never flatten a row of cells into one string: a \
  generator ratings row reading `kVA | 135 | 150` under the headings \
  `Prime` and `Standby` is TWO items -- `135` with `column_header` \
  `Prime`, and `150` with `column_header` `Standby` -- and never one \
  item reading `kVA 135 150`. The header is not a note about the \
  figure; it is half of what the figure means, and a continuous rating \
  and a standby rating are different quantities. Put the row's own \
  label (`kVA`, `400V, 50 Hz`, item number) in `location_on_sheet`, \
  verbatim. If a value is not in a table, set `column_header` to the \
  empty string. If the table's column heading is missing, illegible or \
  you are not sure which column the cell sits under, say exactly that \
  in `column_header` (for example `[unreadable]` or `[column not \
  determinable]`) -- guessing which column a number is under is the \
  worst available answer.
- **No arithmetic.** Do not multiply a count by a rating. Do not convert \
  kVA to MW, kV to MW, MWth to MWe, or litres to anything. Do not total \
  a schedule. If the sheet itself states a total, transcribe the total \
  as its own item and say in `note` that the sheet states it.
- **No inference.** Do not say what the equipment is for, whether it is \
  standby or prime, or what the site's capacity is. If the sheet does \
  not say, it is not here.
- **Nothing found is the right answer when nothing is there.** Most \
  planning drawings are elevations, floor plans and location plans that \
  carry no rating of any kind. If this is one of them, return an empty \
  `items` list and set `sheet_summary` to what the sheet actually shows. \
  Do not pad. An invented or half-guessed figure is far worse for this \
  work than an empty list.
- **Say when you cannot read it.** If lettering is too small, too faint \
  or too degraded to read with confidence, set that item's `legibility` \
  to `partial` or `illegible` and transcribe as much as you are sure of, \
  marking the uncertain part with [?]. If the whole sheet is illegible, \
  say so in `sheet_summary` and set `sheet_illegible` true.

PROVENANCE. For every item:
- `sheet_ref`: the drawing number from the title block, verbatim (e.g. \
  `WPS16014-MGA-100`), plus the sheet's own title if it has one. If \
  there is no title block on any tile, use the empty string.
- `location_on_sheet`: where you read it, in the sheet's own terms -- \
  `title block`, `parts list, item 1`, `electrical ratings table`, \
  `north elevation`, `plan view, generator yard`.
- `column_header`: the verbatim heading of the column the value sits \
  under, for anything read from a table or schedule. Empty string when \
  the value is not tabulated.
- `tile_index`: the number of the tile you read it from. If it spans \
  tiles, give the tile where it is most complete. `0` means you read it \
  on the overview, and `0` is mandatory for a count you made by \
  counting symbols.

Return only the JSON object the schema describes."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sheet_ref", "sheet_summary", "sheet_illegible",
                 "drawing_kind", "items"],
    "properties": {
        "sheet_ref": {
            "type": "string",
            "description": "Drawing number from the title block, verbatim. "
                           "Empty string if there is none."},
        "sheet_summary": {
            "type": "string",
            "description": "One or two sentences on what the sheet shows. "
                           "Descriptive only."},
        "sheet_illegible": {"type": "boolean"},
        "drawing_kind": {
            "type": "string",
            "enum": ["single_line_diagram", "equipment_general_arrangement",
                     "equipment_schedule", "plant_layout", "floor_plan",
                     "elevation", "section", "site_layout", "location_plan",
                     "services_layout", "detail", "other"],
            "description": "What kind of drawing this is, so a scale-up can "
                           "be targeted at the kinds that carry ratings."},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_kind", "value_text", "equipment",
                             "quantity", "column_header", "sheet_ref",
                             "location_on_sheet", "tile_index", "legibility",
                             "note"],
                "properties": {
                    "item_kind": {
                        "type": "string",
                        "enum": ["rating", "schedule", "count", "volume",
                                 "model_no", "other"]},
                    "value_text": {
                        "type": "string",
                        "description": "Verbatim, exactly as written, "
                                       "including units."},
                    "equipment": {
                        "type": "string",
                        "description": "What the annotation labels, in the "
                                       "sheet's own words. Empty if unlabelled."},
                    "quantity": {
                        "type": "string",
                        "description": "The quantity as written ('4no.', "
                                       "'x2'). Empty if none is stated."},
                    "column_header": {
                        "type": "string",
                        "description": "Verbatim heading of the column this "
                                       "cell sits under ('Prime', 'Standby', "
                                       "'400V 50Hz'). Empty string when the "
                                       "value is not from a table. Say so "
                                       "explicitly ('[unreadable]') rather "
                                       "than guessing."},
                    "sheet_ref": {"type": "string"},
                    "location_on_sheet": {"type": "string"},
                    "tile_index": {"type": "integer"},
                    "legibility": {
                        "type": "string",
                        "enum": ["clear", "partial", "illegible"]},
                    "note": {
                        "type": "string",
                        "description": "Anything the transcription needs "
                                       "qualifying with. Empty if none."},
                },
            },
        },
    },
}


# A count made by counting symbols is only as good as the field of view
# it was made in, and a tile is a crop. The pilot's "4" gensets came off
# tile 3 of a genset platform whose fourth machine the crop had cut.
# The instruction says overview-only; this is the enforcement, because
# an instruction the storage does not check is a preference.
#
# Demotion, not deletion: the item becomes `other`, keeps its verbatim
# value and its tile, and carries the reason in its note. A reader
# looking at the row can still see what the model saw; what they cannot
# do is read it as a count of the sheet. A count the model says it read
# off a *label* is untouched wherever it read it -- transcribing "4no.
# generators" is reading, not counting.
COUNT_DEMOTION_NOTE = (
    "[demoted from count: symbol count made on tile {tile}, not the "
    "whole-sheet overview — a tile is a crop and may cut items "
    "(drawings-1.1)]")

# Phrases in which the model says the figure came off a label rather
# than from its own counting. The prompt asks it to say so in `note`;
# the pilot's own rows show it does, in these words.
_COUNTED_MYSELF = ("counted", "counting", "count of symbols",
                   "symbols rather than", "rather than reading",
                   "rather than read")


def counted_by_model(item: dict) -> bool:
    """Did the model count symbols itself, rather than read a stated count?

    A stated quantity ("4no. generators", "2NO. MOBILE GENERATOR
    CONNECTION BOXES") is a transcription and may be read anywhere. The
    tile restriction is only about the model doing arithmetic with its
    own eyes.

    The note decides, and it decides FIRST. The pilot's genset count
    filled `quantity` with "4" -- its own tally, not a quantity written
    on the sheet -- while saying plainly in the note that it had
    "counted four distinct genset symbols ... rather than reading a
    stated quantity". A rule that read `quantity` first would have
    called that a transcription and let it through, which is the exact
    row this exists to catch.

    With both silent the answer is yes, deliberately: an item filed as a
    count with no quantity written on the sheet and no account of where
    the number came from is the model's own tally by elimination, and on
    a tile that is the unsafe case.
    """
    note = (item.get("note") or "").lower()
    if any(p in note for p in _COUNTED_MYSELF):
        return True
    return not (item.get("quantity") or "").strip()


def enforce_count_provenance(items: list[dict]) -> tuple[list[dict], int]:
    """Demote symbol counts that were made on a tile. Returns (items, n)."""
    out: list[dict] = []
    demoted = 0
    for it in items:
        it = dict(it)
        if it.get("item_kind") == "count" and counted_by_model(it):
            try:
                tile = int(it.get("tile_index") or 0)
            except (TypeError, ValueError):
                tile = 0
            if tile != 0:
                it["item_kind"] = "other"
                note = COUNT_DEMOTION_NOTE.format(tile=tile)
                it["note"] = f"{note} {it.get('note') or ''}".strip()
                demoted += 1
        out.append(it)
    return out, demoted


def render(application_ref: str, description: str, title: str) -> str:
    return INSTRUCTIONS.format(
        application_ref=application_ref,
        description=(description or "")[:600] or "(none recorded)",
        title=title or "(untitled)")
