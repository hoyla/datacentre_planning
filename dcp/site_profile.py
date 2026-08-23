"""Per-site derived signals, shared by every consumer of the dataset.

The workbook and the web view must present the same numbers for the same
reasons. If each derives "does this site need an EIA" or "how many
generators" from the findings in its own way, the two will disagree
somewhere and the disagreement will surface in front of the reporting
team — at which point neither can be trusted. So the rationale lives
here once, and both call it.

Everything in this module is deterministic: given the same findings it
returns the same answer, with no API call. That keeps it cheap to re-run,
auditable by reading the rules, and safe to apply to a corpus that is
still growing under the corroboration pass.

Two derivations so far, chosen because they are well covered and carry
real editorial weight:

- **EIA status.** The Sites sheet previously guessed at this from
  reference suffixes and document filenames, and said so. The deep-read
  found explicit screening and scoping language in 349 applications, so
  a heuristic can become a fact.
- **Backup generation.** The distinctive data-centre externality: how
  many diesel engines, of what total capacity, on what fuel. Elsham
  Wolds alone discloses 650 generator stacks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# EIA status
# ---------------------------------------------------------------------------
#
# Ordered: an outcome beats a process step. "EIA screening opinion
# concluded EIA not required" contains both, and the conclusion is what a
# reader needs — reporting it as "screening requested" would be true and
# useless. Within outcomes, "required" is tested before "not required"
# only where the phrasing is unambiguous, since most negative statements
# embed the positive one.

_EIA_RULES: tuple[tuple[str, str, str], ...] = (
    ("eia_not_required",
     r"eia (is )?not required|environmental statement not required|"
     r"not (an )?eia development|screening opinion.{0,30}not required|"
     r"no (eia|environmental impact assessment) (is )?required|"
     r"not schedule 1|does not constitute eia development",
     "EIA not required"),
    ("eia_required",
     r"accompanied by an environmental statement|"
     r"determined to be eia development|is eia development|"
     r"environmental statement (has been |is )?(submitted|provided|prepared)|"
     r"eia (is )?required|environmental impact assessment (is )?required",
     "EIA required — Environmental Statement submitted"),
    ("scoping",
     r"scoping opinion|scoped (in|out) of eia|scoping report",
     "EIA scoping under way"),
    ("screening_requested",
     r"screening opinion (request|requested|sought)|"
     r"request for (an )?eia screening|regulation 6",
     "EIA screening requested — outcome not recorded"),
)

_EIA_COMPILED = tuple((k, re.compile(p, re.I), lbl) for k, p, lbl in _EIA_RULES)

# Where a site's documents say different things — common, since a site
# accumulates applications over years — this is the order of precedence.
# A site that ever required an ES is an EIA site regardless of what a
# later condition discharge says.
_EIA_PRECEDENCE = ("eia_required", "eia_not_required", "scoping",
                   "screening_requested")


def eia_status_for(texts) -> tuple[str | None, str | None]:
    """(key, label) for a site, from its EIA-family finding texts."""
    seen: set[str] = set()
    for t in texts:
        if not t:
            continue
        for key, pattern, _label in _EIA_COMPILED:
            if pattern.search(t):
                seen.add(key)
    for key in _EIA_PRECEDENCE:
        if key in seen:
            return key, dict((k, l) for k, _p, l in _EIA_RULES)[key]
    return None, None


# ---------------------------------------------------------------------------
# Backup generation
# ---------------------------------------------------------------------------

# Generation types, measured across the corpus rather than assumed. The
# v1 phase found gas generators alongside diesel, and the full corpus
# bears that out: diesel dominates (3,168 mentions) but CHP (635), HVO
# (404), gas engines and turbines (346), hydrogen and fuel cells (217)
# and biomass (210) are all present.
#
# Reported as a SET, never reduced to one value. A site running diesel
# standby behind a gas CHP plant is a different proposition from either
# alone, and picking a winner would erase the distinction that makes it
# interesting — the transition from diesel to HVO, or the presence of
# permanent generation rather than backup, is often the story.
_FUEL_RULES: tuple[tuple[str, str, str], ...] = (
    ("hvo", r"\bhvo\b|hydrotreated vegetable oil|renewable diesel",
     "HVO"),
    ("gas", r"\bgas[- ]fired\b|natural gas|\bcng\b|\blng\b|"
            r"gas (engine|turbine|reciprocating)|reciprocating engine",
     "Gas"),
    ("diesel", r"\bdiesel\b|\bgas ?oil\b|red diesel", "Diesel"),
    ("hydrogen", r"hydrogen|fuel cell", "Hydrogen / fuel cell"),
    ("biomass", r"biomass|biogas|anaerobic digest", "Biomass / biogas"),
)
_FUEL_COMPILED = tuple((k, re.compile(p, re.I), lbl) for k, p, lbl in _FUEL_RULES)

# Combined heat and power is a technology rather than a fuel, and worth
# flagging separately: it implies permanent generation and a heat
# offtake, not standby plant, which changes both the emissions picture
# and who the counterparties are.
_CHP_RE = re.compile(r"\bchp\b|combined heat and power|heat (offtake|network)",
                     re.I)


def fuels_for(texts) -> tuple[list[tuple[str, int]], bool]:
    """([(fuel label, mentions)], chp_flag), ordered by mentions.

    Counted rather than merely detected. An energy statement that weighs
    hydrogen and biomass before settling on diesel mentions all three, and
    a presence test would report the site as running five fuels — the same
    trap the finding-families column fell into. Mention counts separate
    the fuel a site uses from the fuels it considered, and let a reader
    see which is which instead of trusting the classifier.
    """
    counts: dict[str, int] = {}
    chp = 0
    for t in texts:
        if not t:
            continue
        if _CHP_RE.search(t):
            chp += 1
        for _key, pattern, label in _FUEL_COMPILED:
            if pattern.search(t):
                counts[label] = counts.get(label, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    # CHP claimed on a single passing mention is usually a comparison to
    # someone else's scheme; require corroboration.
    return ranked, chp >= 2


# Counts above this are treated as suspect rather than dropped: the
# largest genuine disclosure in the corpus is 650 stacks at a ~1GW site,
# so anything far beyond that is more likely a misparse than a scheme.
GENERATOR_COUNT_CEILING = 1000


# A fuel mentioned once or twice against a dominant one is usually an
# option the applicant weighed, not plant they are installing.
FUEL_SECONDARY_FLOOR = 0.15


# What the bracketed numbers on a ranked label are counting. They are
# mentions in the documents, and nothing else on the same panel is — the
# generator count beside them is plant. A reporter read "Standby
# generators: 109" against "Diesel (147), HVO (39)" and reasonably asked
# how 147 diesel generators and 39 HVO ones fit inside 109. Both numbers
# were right and neither said what it was of.
#
# So the leading bracket carries the noun and the rest inherit it: naming
# it once establishes the kind for the whole line, where repeating it four
# times would bury the fuels it is meant to qualify. Every artefact gets
# this — the workbook's dictionary already promised "mention counts" and
# only the dictionary said so.
MENTION_NOUN = "mentions"


def ranked_label(ranked, floor: float, *, noun: str = MENTION_NOUN) -> str:
    """`Top (147 mentions), Next (39); also referenced: Rare`.

    `ranked` is (label, count) most-mentioned first. Entries below
    `floor` × the leader are summarised as 'also referenced' rather than
    listed with a number, because a thing named once against a dominant
    alternative is usually an option weighed rather than plant installed
    — and printing its count invites a comparison the evidence will not
    carry.

    One implementation for fuels, cooling methods and party names: they
    are the same claim about the same kind of number, and when the
    wording of that claim changes it should not change in only two of the
    three places.

    Callers must rank on `(-count, label)`, not on `-count` alone. Python
    sorts stably, so a bare count leaves labels tied on the same count in
    whatever order the rows arrived from the database — and two builds of
    one database then print "also referenced: Heat reuse / offtake,
    Air-cooled" and "…: Air-cooled, Heat reuse / offtake". A tie in a
    sort key is the same defect as a tie in an ORDER BY; see
    tests/test_export_ordering.py for why that matters here.
    """
    if not ranked:
        return ""
    top_label, top_n = ranked[0]
    parts = [f"{top_label} ({top_n} {noun})"]
    minor = []
    for label, n in ranked[1:]:
        if n >= top_n * floor:
            parts.append(f"{label} ({n})")
        else:
            minor.append(label)
    out = ", ".join(parts)
    if minor:
        out += f"; also referenced: {', '.join(minor)}"
    return out


@dataclass(frozen=True)
class GeneratorProfile:
    count: int | None
    fuels: list[tuple[str, int]]   # (label, mentions), most-mentioned first
    is_chp: bool
    caveat: str

    @property
    def fuel_label(self) -> str:
        """Dominant fuel first, with genuinely-present others named."""
        out = ranked_label(self.fuels, FUEL_SECONDARY_FLOOR)
        return f"{out} — CHP" if self.is_chp and out else out


def generator_profile(counts, fuel_texts) -> GeneratorProfile:
    """Standby generator count and fuel for a site.

    The maximum is taken rather than the median, because a site's
    documents describe phases as well as the whole scheme and the question
    being asked is how many engines end up on the site. Unlike capacity
    figures, generator counts carry little market-context risk — forecasts
    and policy targets are written in megawatts, not in engines — so these
    are used without an adjudication pass. The caveat records that.
    """
    usable = [int(c) for c in counts
              if c is not None and 0 < c <= GENERATOR_COUNT_CEILING]
    fuels, is_chp = fuels_for(fuel_texts)
    if not usable:
        return GeneratorProfile(
            None, fuels, is_chp,
            "Generation type named but no count disclosed." if fuels else "")
    caveat = ("The count is plant: the highest number of generators "
              "disclosed in any one of this site's documents, so phases "
              "described separately are not added together. The bracketed "
              "numbers beside each fuel count something else — passages in "
              "the documents naming that fuel — and the two do not "
              "reconcile arithmetically. Not adjudicated for attribution, "
              "unlike the capacity figures: generator counts are rarely "
              "quoted as market context, which capacity routinely is.")
    return GeneratorProfile(max(usable), fuels, is_chp, caveat)


# ---------------------------------------------------------------------------
# The generation figure: one machine, or the fleet?
# ---------------------------------------------------------------------------
#
# The on-site generation column takes the largest adjudicated
# `onsite_generation` figure on the site. Adjudication answers *whose*
# figure it is and, since 2026-08-10, what *kind* of quantity — but not
# whether the number describes one engine or all of them, and the
# documents state both. Amazon Didcot recorded 2.9 MW from "Mechanical
# Generator - 2,873 kW", one unit's specification, while the same
# documents say "38 no. 2,640kW generator units per building"; the
# dataset then described the site as having life-safety backup only,
# close to the opposite of what the application says. Watford Bypass
# today shows 3.2 MW above "112 units".
#
# Nothing here multiplies. A count and a rating from the documents are
# reported beside each other, and the figure is labelled for what the
# passage that states it says it is: a per-unit rating, or the figure as
# stated. A proper answer — per unit, fleet total or site total, for
# every generation row — is a batch adjudication question and is planned
# as one (docs/READER_REDESIGN_PLAN.md §4.1e); this is the deterministic
# label that stops the number being read as the site's generation until
# then. It only fires when a passage states a count or "each" *and* the
# rating it gives matches the stored figure, so it cannot promote a total
# to a unit rating: "1.5–3 MW per unit (7.5–15 MW total)" stored as 15
# stays "as stated".

GENERATION_FIGURE_SQL = """
WITH adj AS (
  SELECT DISTINCT ON (finding_id) finding_id, verdict, quantity_type, value_mw,
         application_id
  FROM power_adjudication
  ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC, id DESC)
SELECT s.site_key, adj.value_mw, f.evidence_text
FROM adj
JOIN findings f ON f.id = adj.finding_id
JOIN site_members sm ON sm.application_id = adj.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL
  AND adj.verdict = 'site_capacity'
  AND adj.quantity_type = 'onsite_generation'
  AND adj.value_mw IS NOT NULL AND adj.value_mw > 0
"""

# "26 no. 28000kW", "11no 3072 kW", "171 no. 2,000 kWe", "32 x 2.5MW",
# "650 no. 2,480 kW back-up diesel generators", and — with words between
# the count and the rating — "112 No. standby generators (likely to be
# 3.2MWe". The words are bounded so a count in one clause cannot reach a
# rating in the next.
_COUNT_RATING_RE = re.compile(
    r"(?<![\d.,])(\d{1,4})\s*(?:no\.?|nr\.?|x|×)\s*[,\s]*"
    r"(?:[A-Za-z()\-/,' ]{0,60}?)"
    r"([\d,]+(?:\.\d+)?)\s*(MWe?|kWe?)\b", re.I)
# "26 4 MW generators", "38 2,640kW generator units": a count, a rating and
# a plant noun, with no "no." between. The noun is required so a page
# number followed by a figure cannot qualify.
_COUNT_RATING_NOUN_RE = re.compile(
    r"(?<![\d.,])(\d{1,4})\s+([\d,]+(?:\.\d+)?)\s*(MWe?|kWe?)\s*"
    r"(?:\([^)]*\)\s*)?(?:standby |back-?up |diesel |gas |emergency )*"
    r"(?:generators?|gensets?|engines?|units?|sets?)\b", re.I)
# "2.4 MW each", "3.2MWe per unit", "2.5 MW (prime) per generator".
_FIGURE_THEN_EACH_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(MWe?|kWe?|megawatts?|kilowatts?)\s*(?:\([^)]*\)\s*)?"
    r"(?:each|apiece|per (?:unit|generator|engine|set|genset|machine))\b", re.I)
# "each system providing 104 megawatts", "each generator rated at 2.5 MW".
# At most four words between, so "each roof would allow for a large
# array that could yield up to 1.5 MW" does not qualify.
_EACH_THEN_FIGURE_RE = re.compile(
    r"\b(?:each|every)\s+(?:[A-Za-z-]+\s+){0,4}?([\d,]+(?:\.\d+)?)\s*"
    r"(MWe?|kWe?|megawatts?|kilowatts?)\b", re.I)

# How close a stated rating must be to the stored figure to be the same
# number written twice. Unit conversion and rounding account for the rest.
_RATING_TOLERANCE = 0.02


def _to_mw(number: str, unit: str) -> float:
    value = float(number.replace(",", ""))
    return value / 1000 if unit.lower().startswith("k") else value


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= _RATING_TOLERANCE * max(a, b)


def _per_unit_evidence(quote: str, value_mw: float) -> tuple[bool, int | None]:
    """Does this passage present `value_mw` as one unit's rating?

    Returns (per_unit, count). The count is None when the passage says
    "each" without saying how many.
    """
    per_unit, count = False, None
    for n, rating in _fleets_disclosed(quote):
        if _same(rating, value_mw):
            per_unit = True
            count = max(count or 0, n)
    if not per_unit:
        for rx in (_FIGURE_THEN_EACH_RE, _EACH_THEN_FIGURE_RE):
            for m in rx.finditer(quote):
                if _same(_to_mw(m.group(1), m.group(2)), value_mw):
                    per_unit = True
    return per_unit, count


def _fleets_disclosed(quote: str) -> list[tuple[int, float]]:
    """Every (count, unit MW) pair a passage states, multiplied by nobody."""
    out = []
    for rx in (_COUNT_RATING_RE, _COUNT_RATING_NOUN_RE):
        for m in rx.finditer(quote):
            n, rating = int(m.group(1)), _to_mw(m.group(2), m.group(3))
            if n >= 2 and rating > 0:
                out.append((n, rating))
    return out


@dataclass(frozen=True)
class GenerationFigure:
    value_mw: float | None      # the headline figure: the largest adjudicated
    basis: str                  # "per unit", "as stated", or "" with no figure
    unit_mw: float | None       # a per-unit rating the documents state
    unit_count: int | None      # units disclosed at that rating, if stated
    note: str                   # reader-facing qualification, or ""


def generation_figure(rows) -> GenerationFigure:
    """Label the site's generation figure by what its own passages say.

    `rows` are (value_mw, evidence_text) pairs for every adjudicated
    on-site generation figure on the site, in any order; the result does
    not depend on the order (see test_reproducible_ordering for why that
    matters here).
    """
    rows = sorted(((float(v), q or "") for v, q in rows if v),
                  key=lambda r: (-r[0], r[1]))
    if not rows:
        return GenerationFigure(None, "", None, None, "")
    headline = rows[0][0]
    fleets = sorted({f for _, q in rows for f in _fleets_disclosed(q)},
                    key=lambda f: (-(f[0] * f[1]), -f[0], -f[1]))
    # Arithmetic outranks vocabulary. If some passage gives a count and a
    # rating whose product is the headline, the headline is that total
    # however another sentence phrases it — "26 generator systems each
    # system providing 104 megawatts" sits beside "26 4 MW generators",
    # and 104 is the fleet, not the engine.
    for n, rating in fleets:
        if _same(n * rating, headline):
            note = (f"As stated: the total of {n:,} units of {rating:g} MW, which "
                    "the documents give both ways.")
            # The columns carry the largest fleet disclosed, which may be
            # a different one: Elsham's 50 MW is twenty gas engines, and
            # the same passage goes on to "up to 650 no. 2,480 kW back-up
            # diesel generators".
            largest = fleets[0]
            if largest != (n, rating) and largest[0] * largest[1] > headline:
                note += (f" They also disclose {largest[0]:,} units of "
                         f"{largest[1]:g} MW, not multiplied.")
            return GenerationFigure(headline, "as stated", largest[1], largest[0], note)
    # Several passages can state the headline figure; any one of them
    # saying "N no." or "each" settles what it is.
    per_unit, count = False, None
    for value, quote in rows:
        if not _same(value, headline):
            continue
        pu, n = _per_unit_evidence(quote, value)
        per_unit = per_unit or pu
        if n:
            count = max(count or 0, n)
    if per_unit:
        how_many = (f"the documents disclose {count:,} units of {headline:g} MW"
                    if count else
                    f"the documents describe units of {headline:g} MW each and do not "
                    "say how many in the same passage")
        return GenerationFigure(
            headline, "per unit", headline, count,
            f"A per-unit rating, not the site's generation: {how_many}. Not "
            "multiplied — a count and a rating are reported beside each other, "
            "never combined into a total.")
    # The figure stands as stated. If some passage also describes a fleet
    # by count and rating, say so beside it rather than let the larger
    # implied number go unmentioned — or be computed silently.
    if fleets:
        n, rating = fleets[0]
        return GenerationFigure(
            headline, "as stated", rating, n,
            f"As stated in the documents. They also disclose {n:,} units of "
            f"{rating:g} MW, not multiplied.")
    return GenerationFigure(headline, "as stated", None, None, "")


# ---------------------------------------------------------------------------
# Cooling and water
# ---------------------------------------------------------------------------
#
# Water is the most contested externality of a data centre after power, and
# the corpus does NOT support an adjudicated consumption figure. The
# water/cooling finding families look enormous — 34,274 findings across 193
# sites — but they are dominated by flood and drainage engineering that
# every development produces: rainfall depths in mm, pipe runs in m,
# "design discharge rate 3.6 l/s for a 30-year event", attenuation volumes.
#
# Filtered to figures that describe what a facility would actually consume,
# it collapses to 119 of 429 sites (76 when this was written on 2026-08-10;
# the phase 2.1 reading raised it). Building a "water use MW-equivalent"
# column on that would imply a precision the documents do not contain, and
# would invite exactly the comparison it cannot support.
#
# So two honest things are reported instead. Cooling METHOD is categorical
# and reasonably covered (119 sites) — and it is the question that actually
# determines water demand, since an air-cooled hall and an evaporative one
# differ by orders of magnitude. And the *absence* is reported as a finding
# in its own right: that only 28% of sites disclose anything about water
# consumption is itself worth a reporter's attention.

# Methods are counted, never reduced to one. An energy statement that
# compares adiabatic against air-cooled before choosing mentions both, and
# a presence test would report the site as using every technology it
# considered — the mistake the finding-families column made before it was
# ranked by volume.
_COOLING_RULES: tuple[tuple[str, str], ...] = (
    ("Water-cooled / chilled water", r"water[- ]cooled|chilled water|chiller"),
    ("Air-cooled", r"air[- ]cooled|air cooling|dry cooler"),
    ("Adiabatic / evaporative", r"adiabatic|evaporative|cooling tower"),
    ("Free cooling", r"free[- ]cooling|free air"),
    ("Heat reuse / offtake", r"heat (re-?use|recovery|offtake|network)|district heat"),
    ("Closed loop", r"closed[- ]loop|sealed system"),
    ("Immersion / liquid", r"immersion cool|liquid cool|direct[- ]to[- ]chip"),
)
_COOLING_COMPILED = tuple((l, re.compile(p, re.I)) for l, p in _COOLING_RULES)

# Signal types that describe consumption or abstraction, as opposed to the
# drainage engineering that dominates the family.
CONSUMPTION_SIGNAL_RE = re.compile(
    r"consum|demand|usage|potable|abstract|cooling_water|wue|evapor", re.I)

# A method mentioned once against a dominant one is usually an option the
# applicant weighed, not plant they are installing.
COOLING_SECONDARY_FLOOR = 0.2


def cooling_profile(texts) -> tuple[str, str]:
    """(method label, caveat) for a site, from its cooling-related text."""
    counts: dict[str, int] = {}
    for t in texts:
        if not t:
            continue
        for label, pattern in _COOLING_COMPILED:
            if pattern.search(t):
                counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "", ""
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked_label(ranked, COOLING_SECONDARY_FLOOR), (
        "Cooling technologies named in this site's documents, counted by "
        "how many passages name each — not by how much plant is installed. "
        "Applications routinely compare options before choosing, so more "
        "than one method may appear, and the count is what separates the "
        "method used from the methods considered.")


COOLING_TEXTS_SQL = """
SELECT s.site_key,
       array_agg(f.value_text) FILTER (WHERE f.value_text IS NOT NULL) AS texts,
       count(*) FILTER (WHERE f.signal_type ~* %s)                     AS consumption_findings,
       count(*)                                                        AS water_findings
FROM findings f
JOIN site_members sm ON sm.application_id = f.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL
  AND (f.signal_family IN ('water','cooling')
       OR f.value_text ~* 'cool|chiller|adiabatic|immersion')
GROUP BY s.site_key
"""


# ---------------------------------------------------------------------------
# Coverage — what we hold, what has been analysed, and why anything is absent
# ---------------------------------------------------------------------------
#
# The dataset's absences carry as much editorial weight as its contents,
# and they are not one thing. "No capacity figure" can mean the documents
# were read and disclose nothing (a fact about the applicant), that the
# documents have not been analysed yet (a fact about this pipeline), that
# no documents could be retrieved (a fact about the council's portal), or
# that no application exists yet (a fact about the project's stage). The
# workbook and the web view must distinguish these identically, so the
# vocabulary lives here.

# Portals we can see but deliberately do not fetch from. Coventry answers
# HTTP 202 with an empty body to any non-browser client (AWS WAF);
# replaying a browser's token would be bypassing bot protection, so the
# gap is recorded instead of worked around.
KNOWN_BLOCKED_HOSTS: dict[str, str] = {
    "planandregulatory.coventry.gov.uk":
        "portal uses bot protection; documents not retrievable",
}

# Individual register entries that are not public.
KNOWN_LOGIN_REQUIRED_REFS: dict[str, str] = {
    "Wiltshire/PL/2022/09577": "register entry requires a consultee login",
}


def provisional(docs_held: int, docs_read: int) -> tuple[bool, str]:
    """(is provisional, how to say so) for a partially-read site.

    Every findings-derived value is a floor, not a measurement. The
    largest capacity in the documents we have read is the largest we know
    of, and reading the rest can only raise it — a campus promoted as 1GW
    shows 500MW here because that is the biggest figure in the 40% of its
    documents that have been analysed, not because the promoter's number
    is wrong.

    The same asymmetry applies to every field assembled by counting
    findings: generator counts, cooling methods, fuels, applicant and
    adviser names, EIA status, finding subjects. All can grow; none can
    shrink. Presenting them unmarked invites a reader to treat a floor as
    a total, which is the one misreading this dataset can least afford.

    **Pass the prose counts, not every document held.** A site whose only
    outstanding documents are elevations and near-identical objection
    letters is not partially read — the methodology skips the first and
    samples the second, deliberately, and no amount of further reading
    will change that. Counting them made 201 of 302 sites provisional
    when 38 had any prose outstanding, which tells a reporter the dataset
    is a third finished when its readable material is 99% read. That is
    not a cautious error: a caveat that fires on almost every row is
    indistinguishable from noise, and the 38 rows where it matters get
    lost among the 163 where it does not.
    """
    if not docs_held or docs_read >= docs_held:
        return False, ""
    pct = 100 * docs_read // docs_held
    if docs_read == 0:
        return True, ("none of this site's readable documents have been analysed "
                      "yet — findings-derived values are absent, not zero")
    return True, (f"prior to complete deep read — from the {pct}% of readable "
                  f"documents ({docs_read} of {docs_held}) analysed so far; "
                  f"further reading can raise this figure but not lower it")


PROVISIONAL_MARK = "(prior to complete deep read)"


def capacity_status(*, pre_application: bool, docs_held: int, docs_read: int,
                    power_value_mw, power_basis: str) -> tuple[str, str]:
    """(key, label) saying what the power columns' emptiness — or figure —
    actually means. Ordered so the strongest available statement wins.
    """
    if pre_application:
        return ("pre_application",
                "Pre-application — no public planning material exists yet")
    if docs_held == 0:
        return ("no_documents", "No documents held")
    if power_value_mw is not None:
        if power_basis.startswith("Estimated"):
            return ("inferred_floor_area",
                    "No capacity disclosed — figure inferred from floor area")
        return ("disclosed", "Capacity disclosed in documents")
    if docs_read == 0:
        return ("not_yet_analysed",
                f"Documents held ({docs_held}), none analysed yet")
    if docs_read < docs_held:
        return ("partially_analysed",
                f"No figure found so far — {docs_read} of {docs_held} "
                "documents analysed")
    return ("read_none_disclosed",
            "All documents analysed — no capacity disclosed")


def provisional_statement(docs_held: int, docs_read: int) -> str:
    """The same fact as `provisional`, written to stand on its own.

    `provisional` returns a clause meant to be appended to a caveat that
    already names the figure ("Disclosed IT load (prior to complete deep
    read) — from the 73% …"). Reused as a panel heading it read as its own
    footnote: the marker, then a dash, then the marker again.

    A panel is not a footnote to anything — it is always on screen, and it
    is stating a fact about this site — so it gets its own sentence.
    Returns "" when the site is fully read.
    """
    if not docs_held or docs_read >= docs_held:
        return ""
    if docs_read == 0:
        return ("None of this site's documents have been analysed yet. Every value "
                "below drawn from the documents is absent rather than zero: the "
                "documents are held and readable, but nothing has been extracted "
                "from them.")
    pct = 100 * docs_read // docs_held
    return (f"{docs_read:,} of this site's {docs_held:,} readable documents ({pct}%) "
            f"have been analysed. Every value below drawn from the documents — "
            f"capacity, generator counts, cooling method, the names involved — is the "
            f"largest or fullest found so far. Further reading can raise these figures "
            f"and cannot lower them.")


# Why a site holds no documents. The distinction that matters is between
# work not yet done and work finished with a null result: a council that
# publishes nothing has been checked, and counting it as a gap makes the
# dataset look permanently incomplete. Keyed on the acquisition outcome
# recorded against the site's applications.
NO_DOCUMENT_REASONS: dict[str, str] = {
    "pre_application": (
        "No planning application has been submitted for this site, so there is no "
        "public register entry and no documents to hold. Everything known about it "
        "comes from Barbour ABI project intelligence. Capacity, cooling, water and "
        "generation are unknowable until an application is made — blank here means "
        "nothing has been published, not that the scheme is small."),
    "none_published": (
        "The council's register has been checked and publishes no documents for "
        "this site's applications. This is a finished check, not an outstanding "
        "task: some authorities publish only the decision, and older applications "
        "predate routine document publication. The application details on the "
        "register are still the citable source."),
    "no_adapter": (
        "This council runs planning-portal software the pipeline cannot yet read. "
        "The documents exist on the council's own register — the Source links below "
        "reach them — but they have not been retrieved into this archive. This is "
        "an acquisition gap, and a later release closes it."),
    "portal_blocked": (
        "This council's portal blocks automated clients. Documents can be retrieved "
        "by hand where a site warrants it, and several have been; the rest have "
        "not. The Source links below reach the register directly."),
    "login_required": (
        "The documents sit behind an account on the council's system and are not "
        "publicly retrievable."),
    "error": (
        "Retrieval was attempted and failed — a timeout, a moved page, or a portal "
        "outage. These are recorded as retryable rather than settled, and a later "
        "pass will try again."),
    "untried": (
        "These applications have not been attempted yet. They are queued for the "
        "next acquisition pass, so their absence here says nothing about whether "
        "the council publishes documents."),
}


def no_documents_reason(outcomes) -> tuple[str, str]:
    """(short label, explanation) for a site holding no documents.

    Takes the acquisition outcomes recorded across the site's
    applications. Where they disagree — some checked, some untried — the
    outstanding work is reported ahead of the finished work, because a
    site that is part-checked is not a site that has been checked.
    """
    seen = {o or "untried" for o in (outcomes or ())} or {"untried"}
    for key in ("untried", "error", "no_adapter", "portal_blocked",
                "login_required", "none_published", "pre_application"):
        if key in seen:
            label = {
                "untried": "Not yet retrieved",
                "error": "Retrieval failed — will retry",
                "no_adapter": "Portal not yet readable",
                "portal_blocked": "Portal blocks automated access",
                "login_required": "Documents behind a login",
                "none_published": "Register publishes no documents",
                "pre_application": "No application submitted yet",
            }[key]
            return label, NO_DOCUMENT_REASONS[key]
    return "Not yet retrieved", NO_DOCUMENT_REASONS["untried"]


def acquisition_status(*, pre_application: bool, docs_held: int,
                       hosts, refs) -> str:
    """One line on whether the source material could be, and was, obtained.

    States facts about retrieval only; what to do about a gap is the
    reader's call, not this column's.
    """
    if pre_application:
        return "No public application exists yet (pre-planning stage)"
    blocked = sorted({KNOWN_BLOCKED_HOSTS[h] for h in (hosts or ())
                      if h in KNOWN_BLOCKED_HOSTS})
    login = sorted({KNOWN_LOGIN_REQUIRED_REFS[r] for r in (refs or ())
                    if r in KNOWN_LOGIN_REQUIRED_REFS})
    notes = blocked + login
    if docs_held == 0:
        return notes[0].capitalize() if notes else "No documents fetched yet"
    if notes:
        return f"Documents held; some applications not retrievable ({'; '.join(notes)})"
    return "Documents held"


# Per-site document counts against the deep-read ledger. 'read' is the
# only state that counts as analysed: no_text, not_extracted and
# parse_failed are attempts, and treating an attempt as coverage is how
# an access problem gets mistaken for a null finding. 'not_extracted' is
# the sharpest case — the document was never put through the text
# extractor, so counting it as analysed would assert that a document
# nobody has read contains nothing.
DEEPREAD_COVERAGE_SQL = """
SELECT s.site_key,
       count(DISTINCT d.id) AS docs_held,
       count(DISTINCT d.id) FILTER (WHERE r.document_id IS NOT NULL) AS docs_read
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN documents d ON d.application_id = sm.application_id
LEFT JOIN (SELECT DISTINCT document_id FROM deepread_log
           WHERE read_state = 'read') r ON r.document_id = d.id
WHERE s.retired_at IS NULL
GROUP BY s.site_key
"""


def load_coverage(conn) -> dict[str, tuple[int, int]]:
    """site_key -> (documents held, documents analysed)."""
    with conn.cursor() as cur:
        cur.execute(DEEPREAD_COVERAGE_SQL)
        return {k: (held, read) for k, held, read in cur.fetchall()}


COVERAGE_DETAIL_SQL = """
SELECT s.site_key, d.id, d.kind, (r.document_id IS NOT NULL) AS was_read
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN documents d ON d.application_id = sm.application_id
LEFT JOIN (SELECT DISTINCT document_id FROM deepread_log
           WHERE read_state = 'read') r ON r.document_id = d.id
WHERE s.retired_at IS NULL
"""


def load_coverage_detail(conn) -> dict[str, dict[str, int]]:
    """site_key -> coverage split by what the methodology does with each document.

    "Documents analysed" over "documents held" is an honest ratio and a
    misleading headline. It counts a site-location plan, which the
    deep-read skips because it has no prose in it, exactly like an unread
    planning statement, which is a real gap. Measured 2026-08-10 the two
    are worth 5,751 and 662 documents respectively, so the undivided
    figure reads 78% when the material that can actually carry a
    disclosure is 98% read, and it marks 201 sites as not fully read when
    52 of them have any prose outstanding.

    The split is not a presentational choice; it is the methodology's own
    (`deepread_select.classify_kind`), which is why it is computed from
    that function rather than from a regex written here. Tier `skip` is
    graphical, tier `C` is the repetitive classes that are deliberately
    sampled rather than read exhaustively, and A and B are the prose the
    deep-read is actually for.

    Keys per site: `held`, `read`, `prose_held`, `prose_read`,
    `graphical`, `sampled_held`, `sampled_read`.
    """
    from dcp.deepread_select import classify_kind

    out: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, int]] = set()
    with conn.cursor() as cur:
        cur.execute(COVERAGE_DETAIL_SQL)
        for key, doc_id, kind, was_read in cur.fetchall():
            # One application can belong to more than one site; a document
            # counts once per site, never twice within one.
            if (key, doc_id) in seen:
                continue
            seen.add((key, doc_id))
            c = out.setdefault(key, {"held": 0, "read": 0, "prose_held": 0,
                                     "prose_read": 0, "graphical": 0,
                                     "sampled_held": 0, "sampled_read": 0})
            tier, _ = classify_kind(kind)
            c["held"] += 1
            c["read"] += bool(was_read)
            if tier == "skip":
                c["graphical"] += 1
            elif tier == "C":
                c["sampled_held"] += 1
                c["sampled_read"] += bool(was_read)
            else:
                c["prose_held"] += 1
                c["prose_read"] += bool(was_read)
    return out


# ---------------------------------------------------------------------------
# Queries — one place, so consumers cannot drift on what they select
# ---------------------------------------------------------------------------

EIA_TEXTS_SQL = """
SELECT s.site_key, array_agg(DISTINCT f.value_text)
FROM findings f
JOIN site_members sm ON sm.application_id = f.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE f.signal_family = 'eia_process' AND f.value_text IS NOT NULL
  AND s.retired_at IS NULL
GROUP BY s.site_key
"""

GENERATOR_SQL = """
SELECT s.site_key,
       array_agg(f.value_number) FILTER (
           WHERE f.value_number IS NOT NULL
             AND (f.value_unit IS NULL OR f.value_unit = '')
             AND f.signal_type ~ 'generator')                AS counts,
       array_agg(DISTINCT f.value_text) FILTER (
           WHERE f.value_text IS NOT NULL)                   AS texts
FROM findings f
JOIN site_members sm ON sm.application_id = f.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL
  AND (f.signal_type ~ 'generator' OR f.signal_type ~ 'fuel')
GROUP BY s.site_key
"""


PARTIES_SQL = """
SELECT s.site_key, f.signal_family, f.value_text
FROM findings f
JOIN site_members sm ON sm.application_id = f.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL
  AND f.signal_family LIKE 'party_%'
  AND f.value_text IS NOT NULL
"""

# Barbour role blocks reach a site two ways — a project materialised as
# a site member in its own right, and a project matched to one of the
# site's applications — and a site can hold both. UNION rather than
# UNION ALL so a project reached both ways is one project.
BARBOUR_ROLES_SQL = """
SELECT s.site_key, p.external_ref, p.raw_metadata
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN projects p ON p.id = sm.project_id
WHERE s.retired_at IS NULL AND p.raw_metadata IS NOT NULL
UNION
SELECT s.site_key, p.external_ref, p.raw_metadata
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN project_applications pa ON pa.application_id = sm.application_id
JOIN projects p ON p.id = pa.project_id
WHERE s.retired_at IS NULL AND p.raw_metadata IS NOT NULL
"""

# The authority is the register the application sits in, so it comes
# from the council the application is filed with — not from a party
# finding that happened to name a council. Barbour's authority is the
# fallback for the pre-planning rows, which have no application and so
# no register.
SITE_AUTHORITY_SQL = """
SELECT s.site_key,
       array_agg(DISTINCT c.name)
           FILTER (WHERE c.name IS NOT NULL)              AS councils,
       array_agg(DISTINCT p.authority_name)
           FILTER (WHERE p.authority_name IS NOT NULL)    AS barbour_authorities
FROM sites s
LEFT JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
LEFT JOIN applications a ON a.id = sm.application_id
LEFT JOIN councils c ON c.gss_code = a.council_gss
LEFT JOIN projects p ON p.id = sm.project_id
WHERE s.retired_at IS NULL
GROUP BY s.site_key
"""

# Barbour writes an authority as "Name (Phone: 0300 500 8080)".
_AUTHORITY_PHONE_RE = re.compile(r"\s*\(Phone:[^)]*\)\s*$", re.I)

# Role blocks are numbered columns: Role_4/CyName_4 … Role_13/CyName_13
# in the records seen so far. The range is generous on purpose — a
# record with more parties should widen the sheet, not silently drop
# the tail.
BARBOUR_ROLE_SLOTS = range(1, 40)

# Barbour writes a project's principal parties into three FIXED slots —
# `CyName_Client`, `CyName_Architect`, `CyName_Contractor` — and every
# further party into numbered slots with a `Role_n` beside the name. The
# first version of this function read only the numbered slots, and so
# read the client on 16 of 253 projects: the sixteen that happen to
# carry a *second* client there. The other 232 clients — Ark Data
# Centres on Watford Bypass, Avalon DC Limited on Saunderton — were
# never seen, and the site row said "not established" for a site whose
# client Barbour states. Measured 2026-08-23: 248 projects name a client
# in the fixed slot; none of the sixteen numbered clients repeats it.
BARBOUR_FIXED_SLOTS = (("Client", "CyName_Client"),
                       ("Architect", "CyName_Architect"),
                       ("Contractor", "CyName_Contractor"))


def barbour_parties(raw_metadata: dict, ref: str = "") -> list[tuple[str, str, str]]:
    """(project ref, role, organisation) from one Barbour record.

    Names only. The same blocks carry a named individual, their job
    title and their direct line for each party; those stay in
    raw_metadata, where they are already, and never reach an export.

    Fixed slots first, then the numbered ones, so the principal client
    leads the list where order matters; a name that appears in both is
    reported once.
    """
    meta = raw_metadata or {}
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(role, name):
        role, name = str(role).strip(), str(name).strip()
        if role and name and (role, name) not in seen:
            seen.add((role, name))
            out.append((ref, role, name))

    for role, field_name in BARBOUR_FIXED_SLOTS:
        if meta.get(field_name):
            add(role, meta[field_name])
    for n in BARBOUR_ROLE_SLOTS:
        role, name = meta.get(f"Role_{n}"), meta.get(f"CyName_{n}")
        if role and name:
            add(role, name)
    return out


# ---------------------------------------------------------------------------
# Who is behind it, second version (READER_REDESIGN_PLAN §5c)
# ---------------------------------------------------------------------------
#
# The first version counted names in findings and ranked them. It is a
# fair description of what a site's documents talk about and a poor
# description of who is behind the site: Savills is the most-named
# organisation on seventeen sites because Savills writes the planning
# statements, and CityFibre appears on seventy-three because a utilities
# section lists whose ducts are in the road. Ranked as "Applicant /
# operator", both read as the developer.
#
# So this version prefers a source that states the relationship rather
# than one that can only count it. Barbour ABI's project records carry
# role blocks — Client, End user, Planner, Agent, Architect, M&E engineer
# — written by a construction-intelligence firm whose business is knowing
# who is building what. Those are used as stated, names only: the same
# blocks carry named individuals, their job titles and their direct
# lines, and none of that leaves raw_metadata.
#
# A name from the documents may still reach the operator field, but only
# through data/priors/organisation_aliases.yaml, where a person has
# confirmed that this name belongs to a known group with evidence
# attached. Everything else the documents name stays in the advisers
# line with its mention count showing, which is the honest description
# of what that number is.
#
# The planning authority comes from the site's councils — the register
# the application actually sits in — and never from a party finding. The
# family put 1,536 councils and development corporations among the
# advisers, and re-routing them by name was always a patch over reading
# the wrong source.

# Barbour's own role vocabulary, mapped onto the three things a reader
# is asking about. Sixty-three distinct roles appear in the corpus;
# these are the ones that answer "who is behind it", and the rest reach
# the workbook's long-format Parties sheet rather than the site row.
BARBOUR_END_USER_ROLES = ("End user",)
BARBOUR_APPLICANT_ROLES = ("Client",)
BARBOUR_ADVISER_ROLES = ("Planner", "Agent", "Architect", "Mech.& Elec Engineer")

PARTIES_ABSENT = "Not established from the sources held"

# How many times the documents must name an organisation before it is
# reported as named at all.
#
# The party findings hold 36,245 site-and-name pairs and 30,092 of them
# are a single mention. At that level the extraction is not naming a
# party: "Applicant", "Applicants' transport consultants", "Agent
# contact Mr Rhoades, Lucion Delta Simons" and a hundred other fragments
# are what a one-mention row looks like. Reporting them would put four
# times more noise than signal into a sheet whose whole purpose is to be
# scanned, and would attach a number — 1 — to names that a reader would
# reasonably read as a finding.
#
# Twice is not a claim that a name is right; it is the point below which
# the count says nothing. The excluded rows are neither destroyed nor
# hidden: every one is a findings row in the database and in the
# per-site findings CSV, and the number dropped is reported per site so
# the cap is visible rather than silent. Names carried by a confirmed
# alias are exempt — a person has already decided who they are.
DOCUMENT_NAME_FLOOR = 2


@dataclass(frozen=True)
class Party:
    """One organisation, one role, one source — a row of the Parties sheet.

    `name` is the raw string as its source writes it and is never
    rewritten; `group` is the alias group beside it, empty until a
    person has confirmed one.
    """
    role: str            # 'end_user' | 'applicant' | 'adviser' | 'other'
    name: str
    group: str
    source: str          # 'barbour' | 'documents'
    source_ref: str      # Barbour project ref, or the mention count
    barbour_role: str = ""   # exactly as Barbour writes it


def _dedupe(names):
    """Raw names, first spelling kept, one per canonical key."""
    from dcp import entities
    seen, out = set(), []
    for n in names:
        n = (n or "").strip()
        if not n:
            continue
        key = entities.canonical_key(n)
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def site_parties(barbour_rows, findings_counts, councils, alias_index) -> dict:
    """Who is behind one site, and where each name came from.

    `barbour_rows` are (project_ref, barbour_role, name) as Barbour
    writes them; `findings_counts` are (family, name, mentions) already
    counted; `councils` are the names of the registers the site's
    applications sit in; `alias_index` is dcp.organisations.alias_index
    over confirmed members.

    Pure: no database, so the rules can be tested against the cases they
    were written for rather than against whatever the corpus holds
    today.
    """
    from dcp import entities, organisations

    def group_of(name: str) -> str:
        g = organisations.group_for(name, alias_index)
        return g.group if g else ""

    by_role: dict[str, list[str]] = {"end_user": [], "applicant": [],
                                     "adviser": []}
    refs: dict[str, str] = {}
    barbour_role_of: dict[str, str] = {}
    other: list[tuple[str, str, str]] = []   # (ref, barbour_role, name)
    for ref, brole, name in barbour_rows:
        brole = (brole or "").strip()
        name = (name or "").strip()
        if not name:
            continue
        if brole in BARBOUR_END_USER_ROLES:
            role = "end_user"
        elif brole in BARBOUR_APPLICANT_ROLES:
            role = "applicant"
        elif brole in BARBOUR_ADVISER_ROLES:
            role = "adviser"
        else:
            other.append((str(ref or ""), brole, name))
            continue
        by_role[role].append(name)
        refs.setdefault(name, str(ref or ""))
        barbour_role_of.setdefault(name, brole)

    end_users = _dedupe(by_role["end_user"])
    applicants = _dedupe(by_role["applicant"])
    b_advisers = _dedupe(by_role["adviser"])

    # Findings, ranked the way the panel has always ranked them, and
    # kept in that lane. The only route out of it is a confirmed alias.
    ranked_advisers: list[tuple[str, int]] = []
    admitted: list[str] = []
    admitted_counts: dict[str, int] = {}
    named_once = 0
    # A name the documents call the applicant outranks one they merely
    # name often — but only among names a person has already confirmed
    # belong to a group. Nothing here promotes a name on its count.
    for family, name, mentions in sorted(
            findings_counts,
            key=lambda r: (r[0] != "party_applicant", -r[2], r[1])):
        name = (name or "").strip()
        if not name:
            continue
        e = entities.parse_entity(name)
        if e is not None and e.is_authority:
            # The register the application sits in says this, and says it
            # without a mention count.
            continue
        if group_of(name):
            admitted.append(name)
            admitted_counts[name] = mentions
            continue
        if mentions < DOCUMENT_NAME_FLOOR:
            named_once += 1
            continue
        ranked_advisers.append((name, mentions))

    # The operator: what Barbour states, else a document name a person
    # has already confirmed belongs to a group. Never a name whose only
    # claim is being mentioned often.
    operator_name = (end_users[0] if end_users else
                     applicants[0] if applicants else
                     admitted[0] if admitted else "")
    operator_group = group_of(operator_name)

    parties: list[Party] = []
    for name in end_users:
        parties.append(Party("end_user", name, group_of(name), "barbour",
                             refs.get(name, ""), barbour_role_of.get(name, "")))
    for name in applicants:
        parties.append(Party("applicant", name, group_of(name), "barbour",
                             refs.get(name, ""), barbour_role_of.get(name, "")))
    for name in b_advisers:
        parties.append(Party("adviser", name, group_of(name), "barbour",
                             refs.get(name, ""), barbour_role_of.get(name, "")))
    for ref, brole, name in other:
        parties.append(Party("other", name, group_of(name), "barbour",
                             ref, brole))
    for name in admitted:
        if any(p.name == name for p in parties):
            continue
        parties.append(Party(
            # Not "end_user": Barbour states an end user, while this is a
            # name from the documents that a person has tied to a group.
            "operator" if name == operator_name else "named_in_documents",
            name, group_of(name), "documents",
            f"{admitted_counts[name]} mentions"))
    for name, mentions in ranked_advisers:
        if any(p.name == name for p in parties):
            continue
        parties.append(Party("named_in_documents", name, "", "documents",
                             f"{mentions} mentions"))

    from_barbour = bool(end_users or applicants or b_advisers or other)
    from_docs = bool(ranked_advisers or admitted)
    source = ("Barbour project record and documents" if from_barbour and from_docs
              else "Barbour project record" if from_barbour
              else "Documents, by mention count" if from_docs
              else PARTIES_ABSENT)

    # Two lines, not one. Barbour's advisers are stated and carry no
    # count; the organisations the documents name are a different claim
    # and get a line that says so, with the count showing. Putting them
    # together under "advisers" would tell a reader that Ark Estates 5
    # Ltd advises on the Watford Bypass scheme, when it is the developer
    # — and putting them under "applicant" is the error this version
    # exists to undo.
    return {
        "operator_group": operator_group,
        # The one name the badge and its filter key are built from.
        # Not a column: `end_user` names every end user Barbour records
        # for the site, and a badge that read "Global Switch, Telehouse
        # Europe" would filter on a key belonging to neither company.
        "operator_primary": operator_name,
        "operator_others": max(0, len(end_users or applicants) - 1),
        "end_user": ", ".join(end_users),
        "applicant_of_record": ", ".join(applicants),
        "advisers": ", ".join(b_advisers),
        "named_in_documents": ranked_label(ranked_advisers[:3], 0),
        "authority": ", ".join(_dedupe(councils or ())),
        "parties_source": source,
        "parties_named_once": named_once,
        "parties": tuple(parties),
    }


def _parties_for_sites(conn) -> dict[str, dict]:
    """Who is behind every site, from Barbour first and documents second.

    The rules are in `site_parties`, which takes no connection; this
    function is the three queries that feed it. The alias index is read
    once and covers confirmed members only, so a proposal sitting in the
    YAML changes nothing about a build.
    """
    from collections import defaultdict
    from dcp import entities, organisations

    index = organisations.alias_index(organisations.load_groups())

    barbour: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    counts: dict[str, dict[tuple[str, str], int]] = defaultdict(
        lambda: defaultdict(int))
    display: dict[str, str] = {}
    authority: dict[str, list[str]] = {}

    with conn.cursor() as cur:
        cur.execute(BARBOUR_ROLES_SQL)
        for site_key, ref, meta in cur.fetchall():
            barbour[site_key].extend(barbour_parties(meta, str(ref or "")))

        cur.execute(PARTIES_SQL)
        for site_key, family, value_text in cur.fetchall():
            e = entities.parse_entity(value_text)
            if e is None:
                continue
            display.setdefault(e.key, e.display)
            counts[site_key][(family, e.key)] += 1

        cur.execute(SITE_AUTHORITY_SQL)
        for site_key, councils, barbour_authorities in cur.fetchall():
            names = list(councils or [])
            if not names:
                names = [_AUTHORITY_PHONE_RE.sub("", a)
                         for a in (barbour_authorities or [])]
            authority[site_key] = sorted(n for n in names if n)

    out: dict[str, dict] = {}
    for site_key in set(barbour) | set(counts) | set(authority):
        findings_counts = [(family, display[key], n)
                           for (family, key), n
                           in counts.get(site_key, {}).items()]
        p = site_parties(barbour.get(site_key, ()), findings_counts,
                         authority.get(site_key, ()), index)
        # `parties` travels in the profile but is not a column: it is
        # the long-format rows the workbook's Parties sheet and the
        # DuckDB's parties table are built from, one row per
        # organisation per role, which is what §3.2 asks for instead of
        # a column per role on the site.
        out[site_key] = p
    return out


def load_site_profiles(conn) -> dict[str, dict]:
    """Every derived signal in this module, keyed by site_key.

    Both the workbook and the web view call this, so a change to a rule
    reaches both at once and neither can quietly diverge.
    """
    profiles: dict[str, dict] = {}
    with conn.cursor() as cur:
        cur.execute(EIA_TEXTS_SQL)
        for site_key, texts in cur.fetchall():
            key, label = eia_status_for(texts or ())
            profiles.setdefault(site_key, {})["eia_status"] = key
            profiles[site_key]["eia_status_label"] = label

        cur.execute(GENERATOR_SQL)
        for site_key, counts, texts in cur.fetchall():
            gp = generator_profile(counts or (), texts or ())
            p = profiles.setdefault(site_key, {})
            p["generator_count"] = gp.count
            p["generator_fuel"] = gp.fuel_label
            p["generator_is_chp"] = gp.is_chp
            p["generator_caveat"] = gp.caveat

        cur.execute(COOLING_TEXTS_SQL, (CONSUMPTION_SIGNAL_RE.pattern,))
        for site_key, texts, n_consumption, n_water in cur.fetchall():
            label, caveat = cooling_profile(texts or ())
            p = profiles.setdefault(site_key, {})
            p["cooling_method"] = label
            p["cooling_caveat"] = caveat
            p["water_findings"] = n_water
            # Deliberately a count of evidence, not a figure: see the note
            # above on why consumption is not adjudicated.
            p["water_consumption_findings"] = n_consumption
            p["water_evidence"] = (
                f"{n_consumption} consumption/abstraction findings"
                if n_consumption else
                ("No water consumption disclosed "
                 f"({n_water} water findings, all drainage or flood related)"
                 if n_water else ""))

    from collections import defaultdict
    gen_rows: dict[str, list] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(GENERATION_FIGURE_SQL)
        for site_key, value_mw, quote in cur.fetchall():
            gen_rows[site_key].append((value_mw, quote))
    for site_key, rows in gen_rows.items():
        g = generation_figure(rows)
        p = profiles.setdefault(site_key, {})
        p["gen_figure_basis"] = g.basis
        p["gen_unit_mw"] = g.unit_mw
        p["gen_unit_count"] = g.unit_count
        p["gen_figure_note"] = g.note

    for site_key, parties in _parties_for_sites(conn).items():
        profiles.setdefault(site_key, {}).update(parties)
    return profiles
