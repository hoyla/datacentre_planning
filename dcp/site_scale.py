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
    "operator_claim": "Derived from a figure the operator publishes about "
                      "its own campus — a first-party statement to "
                      "customers, NOT a disclosure to the planning "
                      "authority. The Sites sheet's power caveat names the "
                      "planning record's own position for this site.",
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


def load_site_floorspace(conn) -> dict[str, float]:
    """Building floorspace per site key, as the median of what is stated.

    Lives here rather than in an exporter because two artefacts feed it
    to `power_estimate` and they must not disagree about what a site's
    floor area is. They did: the reader passed None from the day it was
    written, so 43 sites carried an estimated figure in the workbook and
    read "no capacity disclosed" in the web view, while the data
    dictionary both artefacts render described the estimate as though
    both produced it.

    The median, not the maximum: a site's documents state floorspace
    many times over — per building, per phase, gross and net — and the
    largest is usually the whole development quoted in an early
    document. The bounds drop obvious nonsense at both ends; the signal
    types that carry land parcels are excluded upstream, in
    FLOORSPACE_SIGNAL_TYPES.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY f.value_number)
            FROM findings f
            JOIN site_members sm ON sm.application_id = f.application_id
                 AND sm.retired_at IS NULL
            JOIN sites s ON s.id = sm.site_id AND s.retired_at IS NULL
            WHERE f.value_number IS NOT NULL
              AND f.value_number BETWEEN 500 AND 400000
              AND lower(f.value_unit) IN ('sqm','m2','sq m','square metres',
                                          'square meters')
              AND f.signal_type = ANY(%s)
            GROUP BY s.site_key""", (list(FLOORSPACE_SIGNAL_TYPES),))
        return {k: float(v) for k, v in cur.fetchall() if v}


# The bases that rest on something a person wrote down about this
# development — three disclosures and one inference from plant that is
# sized to the load. "Estimated from floorspace" is deliberately absent:
# it is this project's own arithmetic, and it does not belong in a count
# compared against a register of contracted connections. Both artefacts
# read this tuple, because they used to keep the distinction in two
# places and only one of them applied it.
DISCLOSED_BASES = ("Disclosed IT load", "Disclosed total site demand",
                   "Grid connection capacity", "Standby generation capacity")


# The operator rung's basis string, kept out of DISCLOSED_BASES above
# on purpose: a first-party campus figure is published to customers,
# not disclosed to a planning authority, so it must not join a count
# compared against Ofgem's queue or a chart headed "from the site's
# documents". It is not a floorspace estimate either — filing it there
# would call an operator's own statement this project's arithmetic —
# so every consumer that splits figures by provenance carries it as a
# third class. See docs/PLAN_OPERATOR_RUNG.md.
OPERATOR_BASIS = "Operator-stated campus figure"

# The two rungs a first-party figure may never displace on its own.
# Anything below them — a connection, standby plant, a floorspace
# estimate, or no figure at all — is reached only if this rung is
# empty, which is what "a rung between the disclosed rungs and the
# grid rung" means mechanically. Displacing a stated load needs a hand
# adjudication naming the claim (campus_scope.yaml).
STATED_LOAD_BASES = ("Disclosed IT load", "Disclosed total site demand")


@dataclass(frozen=True)
class OperatorClaim:
    """A first-party campus figure, already matched and quote-verified.

    Carried rather than looked up so the ladder stays a pure function:
    eligibility is `capacity_claims.rung_claim`'s job and displacement
    is `campus_scope`'s, and both are decided before this is called.
    """
    value_mw: float
    claim_name: str
    operator: str = ""
    operator_term: str = ""
    as_at: str = ""
    # A sentence the scope adjudication supplies for this site — the
    # facility roster's denominator, the wrinkle it must carry
    # unresolved. Written by a person, never computed.
    note: str = ""


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


def _planning_estimate(*, it_load_mw=None, total_site_mw=None,
                       grid_mw=None, generation_mw=None,
                       floorspace_sqm=None, has_documents=True,
                       prose_held: int | None = None,
                       prose_read: int | None = None) -> PowerEstimate:
    """The ladder over the planning record alone, with no claims in it.

    Separated from `power_estimate` so the operator rung can state what
    the planning record's own best figure is — which decision 2 of
    docs/PLAN_OPERATOR_RUNG.md requires on the page, not as styling —
    and so anything that needs the planning-only answer can ask for it
    directly rather than inferring it from an absence.

    Best available capacity for ranking, with its qualifications.

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
            "backup plant, not a demand figure, and some sites over-provide. "
            "Plant adjudicated as intended to run, renewable or storage is "
            "not counted here: it generates for export and says nothing "
            "about this site's own demand.")

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


def _planning_silence(planning: PowerEstimate) -> str:
    """Whose silence the empty planning record represents.

    Luke, 2026-09-01, deciding that the rung fires on an empty ladder:
    keep the read-and-silent versus documents-not-held distinction "in
    the caveat, not in whether the rung fires". A reader must not take
    our acquisition gap for the operator's reticence, which is the
    no-dash rule — our silence is not their silence — applied to the
    sentence that now sits under a first-party figure.
    """
    if planning.basis == "No documents held":
        return ("no planning documents have been obtained for this site, so "
                "the planning record is silent because of a gap in this "
                "project's collection rather than in the applicant's "
                "disclosure")
    if planning.basis == "Not yet analysed":
        return ("this site's documents are held but not yet analysed, so the "
                "planning record has not been asked")
    if "read in full" in planning.caveat:
        return ("the readable documents held for this site were read in full "
                "and disclose no capacity figure at all")
    if planning.basis == "No capacity disclosed":
        return ("the documents read so far disclose no capacity figure, and "
                "reading is incomplete")
    return f"the planning record's own best figure is {planning.basis.lower()}"


def power_estimate(*, it_load_mw=None, total_site_mw=None,
                   grid_mw=None, generation_mw=None,
                   floorspace_sqm=None, has_documents=True,
                   prose_held: int | None = None,
                   prose_read: int | None = None,
                   operator_claim: OperatorClaim | None = None,
                   operator_displaces: bool = False) -> PowerEstimate:
    """The ladder, with the operator rung in it.

    The rung sits between the disclosed rungs and the grid rung
    (docs/PLAN_OPERATOR_RUNG.md, decision 1), so it is reached by any
    site whose planning record does not state a load of its own —
    including one that states nothing at all, because a rung inserted
    at a position catches everything that would otherwise fall past it
    (Luke, 2026-09-01). Displacing a *stated* load needs a hand
    adjudication naming the claim, which is `operator_displaces`
    (decision 2); nothing computes it.

    `operator_claim` is already matched, quote-verified, top-level and
    sole — `capacity_claims.rung_claim` decides that, and passing one
    here is the caller asserting it did.
    """
    planning = _planning_estimate(
        it_load_mw=it_load_mw, total_site_mw=total_site_mw, grid_mw=grid_mw,
        generation_mw=generation_mw, floorspace_sqm=floorspace_sqm,
        has_documents=has_documents, prose_held=prose_held,
        prose_read=prose_read)
    if operator_claim is None:
        return planning
    if not operator_displaces and planning.basis in STATED_LOAD_BASES:
        return planning

    who = operator_claim.operator or "the operator"
    term = (f", which it calls \u201c{operator_claim.operator_term}\u201d"
            if operator_claim.operator_term else "")
    dated = (f", as at {operator_claim.as_at}" if operator_claim.as_at else "")
    # Only the leading character: "Disclosed IT load" must not become
    # "disclosed it load".
    _basis = planning.basis[:1].lower() + planning.basis[1:]
    against = (f"The planning record's own best figure is {_basis} of "
               f"{planning.value_mw:g} MW."
               if planning.value_mw is not None else
               f"On the planning record, {_planning_silence(planning)}.")
    note = f" {operator_claim.note}" if operator_claim.note else ""
    return PowerEstimate(
        float(operator_claim.value_mw), OPERATOR_BASIS, "Medium",
        f"Published by {who} about its own facilities{term}{dated}, and held "
        f"here as a dated snapshot. A statement to customers, not to the "
        f"planning authority: an operator states capacity in order to sell "
        f"it, and a marketing page can be rewritten without notice. "
        f"{against}{note}")
