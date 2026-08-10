"""Scale and character of a site, derived from evidence already held.

The reporting team needs to tell a 1GW campus from a server cupboard, and
a merchant data centre from a university building that happens to contain
one. Stated capacity answers that where it exists — but it exists for only
137 of 429 sites, and for 71 sites the full document set genuinely never
states a figure (verified, not assumed: a regex sweep of those sites'
cached page text finds MW-like patterns in 2% of documents, and those are
manhole annotations and EV charger ratings).

So scale has to be inferred from what we do hold, with the basis recorded
alongside the answer. Three sources, strongest first:

  1. **Stated capacity** (power_adjudication) — a figure the documents
     attribute to this development.
  2. **Floor area** — a decent proxy and far better covered (168 sites).
     Deliberately banded rather than converted to MW: the kW/m2 ratio
     varies by more than an order of magnitude between a white-space hall
     and a shell-and-core shed, so a conversion would manufacture
     precision that isn't there.
  3. **Description language** — "six air conditioning units" and "4 no.
     data centre buildings" are not the same animal, and the wording
     carries that reliably.

Everything here is deterministic: same inputs, same answer, no API call,
auditable by reading the rules. That follows the project's standing
preference for deterministic extraction over model judgement wherever
judgement is not actually required — and it means the model budget can be
spent on the genuinely ambiguous remainder instead of the easy majority.

Character and scale are kept as separate axes because they answer
different questions. A university server room and a hyperscale campus can
both be "a data centre"; only one is a story about grid impact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- character: what kind of facility is this? --------------------------
# Ordered; first match wins. Patterns run against the concatenated
# descriptions of a site's applications, lowercased.

# A purpose-built data centre is full of "data halls", "plant rooms" and
# "equipment rooms" — those words say nothing about whether the facility
# is ancillary. Only wording that implies IT space *inside someone else's
# building* counts here. ("data room" was tried and removed: it matched
# "two data centre buildings containing data rooms", a hyperscale scheme.)
_ANCILLARY = re.compile(
    r"server room|comms? room|communications room|server cabinet|"
    r"rack room|ancillary (data|server|it)|"
    r"serving the (existing )?(building|site|office|hospital|school|"
    r"university|premises)", re.I)

# Unambiguous evidence that the data centre IS the development: tested
# before ancillary, so incidental interior wording cannot demote a campus.
_STRONG_STANDALONE = re.compile(
    r"(erection|construction|development|delivery) of .{0,40}"
    r"(data cent|data stor|datacent)|"
    r"\d+\s*(no\.?|x)\s*data cent|data cent(re|er) (campus|buildings?|"
    r"park|facility|development)|hyperscale|colocation|co-location|"
    r"technical services centre", re.I)

_INSTITUTIONAL = re.compile(
    r"universit|college|school|hospital|nhs\b|academy|campus building|"
    r"civic|town hall|library|research (institute|facility|centre)|"
    r"laborator", re.I)

_TELECOMS = re.compile(
    r"telephone exchange|telecoms? exchange|bt exchange|"
    r"telecommunications (centre|facility|installation)|"
    r"mobile (mast|base station)|radio (mast|station)", re.I)

_ENABLING_ONLY = re.compile(
    r"^(?=.*\b(substation|switchgear|transformer|grid connection|"
    r"cable route|electricity infrastructure)\b)"
    r"(?!.*\b(data cent|data stor|server hall|technical services)\b)", re.I)

_STANDALONE = re.compile(
    r"data cent|data stor|datacent|server hall|technical services centre|"
    r"colocation|co-location|hyperscale|digital infrastructure", re.I)


@dataclass(frozen=True)
class Character:
    key: str
    label: str
    note: str


CHARACTERS = {
    "ancillary_server_room": Character(
        "ancillary_server_room", "Ancillary server/comms room",
        "IT space serving another occupier on the site, not a facility in "
        "its own right. Low grid significance."),
    "institutional_facility": Character(
        "institutional_facility", "Institutional facility with IT space",
        "University, hospital or civic building containing a data or "
        "server room. Serves the host organisation."),
    "telecoms_facility": Character(
        "telecoms_facility", "Telecoms exchange or installation",
        "Telecoms rather than compute; often reclassified as a data "
        "centre later, so worth tracking separately."),
    "enabling_infrastructure": Character(
        "enabling_infrastructure", "Power/enabling works only",
        "Substation, grid connection or cabling with no data-centre "
        "building in the application."),
    "standalone_datacentre": Character(
        "standalone_datacentre", "Standalone data centre",
        "Purpose-built or converted facility where the data centre is the "
        "primary use."),
    "unclear": Character(
        "unclear", "Unclear from description",
        "Description does not establish the facility's character."),
}


def character_for(text: str | None) -> str:
    """Facility character from the site's description text.

    Ancillary and institutional are tested before standalone because such
    descriptions almost always *also* contain the words "data centre" —
    "installation of six air conditioning units to serve the data centre"
    is an ancillary works application, not a data centre application, and
    testing standalone first would swallow it.
    """
    if not text:
        return "unclear"
    t = text.lower()
    if _STRONG_STANDALONE.search(t):
        return "standalone_datacentre"
    if _ANCILLARY.search(t):
        return "ancillary_server_room"
    if _INSTITUTIONAL.search(t) and not re.search(
            r"\b(hyperscale|colocation|co-location)\b", t):
        return "institutional_facility"
    if _TELECOMS.search(t):
        return "telecoms_facility"
    if _STANDALONE.search(t):
        return "standalone_datacentre"
    if _ENABLING_ONLY.search(t):
        return "enabling_infrastructure"
    return "unclear"


# --- scale: how big is it? ----------------------------------------------
# Bands rather than point values. The MW bands follow how the industry and
# the grid talk about size; the floor-area bands are calibrated to UK
# planning practice, where a sub-1,000 m2 "data centre" is essentially
# always a room inside something else.

MW_BANDS = (
    (500.0, "very_large_500mw_plus", "500 MW and above — campus scale"),
    (100.0, "large_100_500mw", "100–500 MW"),
    (20.0, "medium_20_100mw", "20–100 MW"),
    (5.0, "small_5_20mw", "5–20 MW"),
    (0.0, "very_small_under_5mw", "Under 5 MW"),
)

AREA_BANDS = (
    (50000.0, "very_large_50k_sqm_plus", "50,000 m² and above"),
    (10000.0, "large_10k_50k_sqm", "10,000–50,000 m²"),
    (2000.0, "medium_2k_10k_sqm", "2,000–10,000 m²"),
    (500.0, "small_500_2k_sqm", "500–2,000 m²"),
    (0.0, "very_small_under_500_sqm", "Under 500 m² — room scale"),
)

_AREA_TO_SQM = {
    "sqm": 1.0, "m2": 1.0, "sq m": 1.0, "square metres": 1.0,
    "square meters": 1.0, "sqft": 0.092903, "ft2": 0.092903,
    "square feet": 0.092903,
}


def band(value: float, bands) -> tuple[str, str]:
    for threshold, key, label in bands:
        if value >= threshold:
            return key, label
    return bands[-1][1], bands[-1][2]


def scale_from_mw(mw: float) -> tuple[str, str]:
    return band(mw, MW_BANDS)


def scale_from_area_sqm(sqm: float) -> tuple[str, str]:
    return band(sqm, AREA_BANDS)


def area_to_sqm(value: float, unit: str | None) -> float | None:
    if unit is None:
        return None
    factor = _AREA_TO_SQM.get(unit.strip().lower())
    return value * factor if factor else None


# The basis is reported with every band so a reader knows how much weight
# it carries. A band derived from floor area is a reasonable indication of
# physical scale; it is not a capacity figure and must not be presented as
# one.
BASIS_NOTE = {
    "stated_capacity": "Derived from a capacity figure the documents "
                       "attribute to this development.",
    "floor_area": "Derived from floor area — an indication of physical "
                  "scale, NOT a power capacity.",
    "description": "Inferred from the application description only; no "
                   "capacity or area figure available.",
    "none": "No scale evidence found in the documents held.",
}


# Significance order for rolling per-application characters up to a site.
# A site is described by the most substantial thing proposed there: a
# campus that also has a condition-discharge application for a comms room
# is a standalone data centre site, not an ancillary one. Rolling up by
# *max significance* rather than by concatenating descriptions avoids both
# failure modes — one small application dragging a campus down, and one
# stray mention of "data centre" promoting a university server room.
_SIGNIFICANCE = {
    "standalone_datacentre": 5,
    "telecoms_facility": 4,
    "institutional_facility": 3,
    "enabling_infrastructure": 2,
    "ancillary_server_room": 1,
    "unclear": 0,
}


def rollup_character(characters) -> str:
    """The site-level character from its applications' characters."""
    best, best_rank = "unclear", -1
    for c in characters:
        rank = _SIGNIFICANCE.get(c, 0)
        if rank > best_rank:
            best, best_rank = c, rank
    return best


# ---------------------------------------------------------------------------
# One rankable power figure, with its qualifications alongside
# ---------------------------------------------------------------------------
#
# Capacity is how data centres get ranked, so the workbook needs a single
# sortable column. But the figures behind it differ enormously in what
# they mean and how much they can bear: a disclosed IT load is a fact
# about the building, a grid connection is contracted headroom that may
# never be drawn, standby generation is sized to full load but is not
# demand, and a floor-area estimate is an inference. Publishing those in
# one column with no qualification would let a reporter rank a site on an
# inference against another's measured figure without noticing.
#
# So: one number, and immediately beside it the basis, a confidence, and
# a plain-English caveat. Sorting works; the caveat travels with the cell
# rather than living in a methodology note nobody opens.
#
# FLOOR_AREA_KW_PER_SQM is measured from this corpus, not borrowed from
# industry guidance: across the 53 sites holding BOTH a disclosed capacity
# and a building floorspace figure, the median is 1.71 kW/m2 and the
# central mass sits between 1.6 and 1.9. The interquartile range
# (1.29-3.26) implies roughly a two-fold uncertainty, which the caveat
# states. Site areas and land parcels are excluded from that calibration
# — including them produced absurdities like 117 km2 of "floor area".
FLOOR_AREA_KW_PER_SQM = 1.71
FLOOR_AREA_SPREAD = "roughly a factor of two either way"

# Signal types that denote building floorspace. `site_area` and bare
# `development_scale` are deliberately absent: they routinely carry land
# parcels, and a land area run through the kW/m2 factor produces a
# gigawatt figure for a shed.
FLOORSPACE_SIGNAL_TYPES = (
    "floor_area", "floorspace", "building_area", "building_floor_area",
    "gross_internal_area", "total_floorspace", "data_centre_floor_area",
    "data_centre_floorspace", "data_centre_area", "building_footprint",
    "building_size", "gia", "total_floor_area", "proposed_floorspace",
)


@dataclass(frozen=True)
class PowerEstimate:
    """A rankable figure plus everything needed to read it honestly."""
    value_mw: float | None
    basis: str          # short label for the column
    confidence: str     # High | Medium | Low | Indicative | None
    caveat: str         # plain English, sits beside the number


def _round_sensibly(mw: float) -> float:
    """Round so an inference never looks like a measurement."""
    if mw < 10:
        return round(mw, 1)
    if mw < 100:
        return float(round(mw / 5) * 5)
    return float(round(mw / 10) * 10)


def power_estimate(*, it_load_mw=None, total_site_mw=None,
                   grid_mw=None, generation_mw=None,
                   floorspace_sqm=None, has_documents=True,
                   prose_held: int | None = None,
                   prose_read: int | None = None) -> PowerEstimate:
    """Best available capacity for ranking, with its qualifications.

    Preference order runs from what the documents say about the building's
    own load down to what can be inferred from its size. Each step down is
    a real loss of authority, which the confidence and caveat record.

    `prose_held` / `prose_read` let the no-capacity caveat state how much of
    the site's document set that absence is based on. Without them the
    caveat stays silent on coverage — it must never claim a full reading
    it cannot see.

    **Pass the prose counts.** Given every document held, this hedges on
    sites whose prose was read in full and whose only outstanding files
    are drawings the deep read skips by design — and the hedge displaces
    a finding. "Read in full and discloses neither a capacity figure nor
    a floorspace, which for a consented data centre is itself notable" is
    a result; "reading is incomplete, treat the absence as provisional"
    says the work is unfinished when it is not. The first is reportable
    and the second is not, so the distinction is editorial, not cosmetic.
    """
    if it_load_mw:
        return PowerEstimate(
            float(it_load_mw), "Disclosed IT load", "High",
            "Stated in the application documents as this development's IT "
            "load. Excludes cooling and other overhead, so total site "
            "demand will be higher.")

    if total_site_mw:
        return PowerEstimate(
            float(total_site_mw), "Disclosed total site demand", "High",
            "Stated as the development's total demand, including cooling "
            "and overhead. Not directly comparable with IT-load figures, "
            "which are smaller for the same building.")

    if grid_mw:
        return PowerEstimate(
            float(grid_mw), "Grid connection capacity", "Medium",
            "The connection capacity sought or contracted, which is "
            "headroom rather than consumption — operators commonly secure "
            "more than they draw, and phased sites draw it over years.")

    if generation_mw:
        return PowerEstimate(
            float(generation_mw), "Standby generation capacity", "Low",
            "Inferred from on-site standby generation, which is normally "
            "sized to carry full load and so approximates it — but it is "
            "backup plant, not a demand figure, and some sites over-provide.")

    if floorspace_sqm and floorspace_sqm >= 500:
        est = _round_sensibly(floorspace_sqm * FLOOR_AREA_KW_PER_SQM / 1000)
        return PowerEstimate(
            est, "Estimated from floorspace", "Indicative",
            f"No capacity disclosed. Estimated from {floorspace_sqm:,.0f} m² "
            f"of building floorspace at {FLOOR_AREA_KW_PER_SQM} kW/m², the "
            f"median across the 53 sites in this dataset that disclose "
            f"both. Expect {FLOOR_AREA_SPREAD}; use for ranking, not for "
            f"quotation.")

    if not has_documents:
        return PowerEstimate(
            None, "No documents held", "None",
            "No planning documents have been obtained for this site, so "
            "neither a capacity nor a size can be established. Absence "
            "here reflects the document gap, not a small site.")

    # "Read in full" is a claim about coverage, so it is only made when
    # the coverage numbers are in hand and say so. The published reader
    # once asserted it on 173 sites whose own banner said reading was
    # incomplete — including the 58 where nothing had been read at all.
    if prose_held and prose_read is not None and prose_read >= prose_held:
        return PowerEstimate(
            None, "No capacity disclosed", "None",
            "The readable documents held for this site were read in full and "
            "disclose neither a capacity figure nor a building floorspace. For "
            "a consented or pending data centre that is itself notable. "
            "(Drawings and sampled objection letters are excluded by the "
            "reading method, not outstanding.)")

    if prose_held and prose_read == 0:
        return PowerEstimate(
            None, "Not yet analysed", "None",
            "None of this site's readable documents have been analysed "
            "yet, so no capacity figure could have been found. The absence "
            "reflects the reading gap, not the documents.")

    if prose_held and prose_read is not None:
        return PowerEstimate(
            None, "No capacity disclosed", "None",
            f"Of the {prose_held:,} readable documents held for this site, "
            f"{prose_read:,} have been analysed so far and none discloses a "
            "capacity figure or a building floorspace. Reading is "
            "incomplete: treat the absence as provisional, not established.")

    return PowerEstimate(
        None, "No capacity disclosed", "None",
        "The documents read for this site disclose neither a capacity "
        "figure nor a building floorspace.")
