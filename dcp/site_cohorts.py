"""Named cohorts: sites that share a measurable property, and nothing more.

READER_REDESIGN_PLAN §6. The design handoff proposed a Signals page of
cohorts, and its cohorts were defined by example — counts typed into a
prototype, several of them wrong at the grain level (22 "read in full
and silent" where the corpus holds 135; 18 two-audience sites where
there are 3) and one of them unsafe (standby below 10% of stated load,
which counted rooftop PV and one engine of a hundred and twelve). This
module is the cohorts as queries, so that a count on the page is the
number of rows a click produces and nothing else.

Rules a cohort has to meet to be registered here:

**The title states a property, never a cause.** "Demand stated above
the connection" is a fact about two figures in the documents. "Sites
planning to run on gas" is a diagnosis, and the reading that diagnosed
Amazon Didcot as grid-dependent from one engine's spec sheet is in
HISTORY as the worst error this dataset has produced.

**Limits are required, and the build fails without them.** Every cohort
is computed from adjudicated figures with known blind spots — a figure
can be a floor on a partly-read site, a per-unit rating, an export
limit filed as a connection. The limits text is where those are
stated, on the card, beside the count, every time.

**Counts are computed, never literal.** A cohort is `compute(conn)`; a
number typed into a template is the prototype's mistake repeated.

**A cohort may withhold itself.** Where the inputs it needs are not yet
adjudicated — `generation_exceeds_load` cannot be computed honestly
until the generation batch has said which figures are fleets and which
plant is standby — it returns no members and a reason, and the card
says so. The same refusal `scripts/sweep_null_capacity.py` makes while
figures await adjudication.

**Hand-checks sit beside the rule, never inside it.** A person's
verdict on a cohort member lives in `data/priors/cohort_checks.yaml`,
keyed by site; the rule does not read it. A check on a site the rule
does not select is reported as a disagreement, not hidden, because that
is exactly the case that says the rule is wrong.

Registry order is the page order and is explicit. No cohort ranks its
members; they come out sorted by site key.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from dcp import site_profile
from dcp import campus_scope, capacity_claims, site_scale

ROOT = Path(__file__).resolve().parent.parent
CHECKS_PATH = ROOT / "data" / "priors" / "cohort_checks.yaml"

# The ratio two cohorts turn on. 1.5 rather than 1.0 because the figures
# being compared are adjudicated from prose and routinely differ by a
# phase, a rounding or a building; a site whose stated demand is 10%
# above its connection has told us nothing, one at 150% has.
RATIO = 1.5

CHECK_VERDICTS = frozenset({"holds", "does_not_hold"})


class CohortError(ValueError):
    """A cohort or a check is malformed. Raised at import or at load."""


@dataclass(frozen=True)
class Member:
    site_key: str
    # The figures the rule used, as the rule used them — what a reader
    # needs to see to check the membership from the workbook.
    evidence: dict


@dataclass(frozen=True)
class CohortResult:
    members: tuple[Member, ...]
    # Why the cohort has no members, when that is a refusal rather than
    # an empty set. Empty string when the cohort was computed.
    withheld: str = ""
    # Facts about the computation a reader should see beside the count:
    # how many candidates were excluded and why.
    notes: tuple[str, ...] = ()

    def __post_init__(self):
        # A refusal that also returns members is two answers to one
        # question, and the page would print the count beside the reason.
        # No cohort is withheld today, which is why this is asserted here
        # rather than left to a browser test that can only run when one
        # is.
        if self.withheld and self.members:
            raise CohortError(
                f"a withheld result carries {len(self.members)} members")

    @property
    def site_keys(self) -> set[str]:
        return {m.site_key for m in self.members}


@dataclass(frozen=True)
class Cohort:
    key: str
    title: str                      # states the property, never a cause
    family: str                     # coverage | power | generation
    definition: str                 # prose a reader can follow
    rule: str                       # the computation, in one sentence
    limits: str                     # required; see __post_init__
    # The handoff's tone for this signal: red where a figure is absent or
    # contradicted, amber where one exists but is incomplete, slate where
    # the row is a note about method rather than about the site. A
    # property of the cohort, not of the page, so every surface that
    # draws it draws the same one.
    tone: str                       # red | amber | slate
    # The card's headline, as the handoff writes it: a sentence stating
    # the count and the property. "{n} sites " + the title read as
    # "Four sites demand stated above the grid connection", because a
    # title is a noun phrase and a headline is a sentence. The template
    # carries the count where it belongs; nothing else substitutes.
    headline: str                   # must contain "{n}"
    order: int
    rule_version: str
    compute: Callable = field(repr=False)

    def __post_init__(self):
        if not self.limits or not self.limits.strip():
            raise CohortError(f"cohort {self.key!r} has no limits text")
        if not self.title or not self.definition or not self.rule:
            raise CohortError(f"cohort {self.key!r} is missing its text")
        if self.tone not in ("red", "amber", "slate"):
            raise CohortError(f"cohort {self.key!r} has tone {self.tone!r}")
        if "{n}" not in (self.headline or ""):
            raise CohortError(
                f"cohort {self.key!r} has no count slot in its headline")


@dataclass(frozen=True)
class Check:
    site_key: str
    cohort: str
    verdict: str                    # holds | does_not_hold
    checked_by: str
    date: str
    note: str = ""


# ---------------------------------------------------------------------------
# Inputs, loaded once
# ---------------------------------------------------------------------------

SITE_FIGURES_SQL = """
WITH adj AS (
  SELECT DISTINCT ON (finding_id) finding_id, verdict, quantity_type,
         value_mw, application_id
  FROM power_adjudication
  ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC, id DESC),
gen_adj AS (
  SELECT DISTINCT ON (finding_id) finding_id, figure_basis, plant_type
  FROM generation_adjudication
  ORDER BY finding_id, inserted_at DESC, id DESC)
SELECT s.site_key,
       max(adj.value_mw) FILTER (WHERE adj.quantity_type = 'it_load')
           AS it_load_mw,
       max(adj.value_mw) FILTER (WHERE adj.quantity_type = 'total_site')
           AS total_site_mw,
       max(adj.value_mw) FILTER (WHERE adj.quantity_type = 'grid_connection')
           AS grid_mw,
       -- Standby-shaped plant only, matching export_handover's app_power:
       -- the generation rung's premise is that standby plant is sized to
       -- the load, and plant adjudicated prime_combustion, renewable or
       -- storage runs for export (or is not generation at all) and says
       -- nothing about the site's own demand. Mixed and unclear keep
       -- today's behaviour — exclusion needs a positive adjudication.
       max(adj.value_mw) FILTER (WHERE adj.quantity_type = 'onsite_generation'
           AND coalesce(g.figure_basis, '') <> 'not_generation'
           AND coalesce(g.plant_type, '') NOT IN
               ('prime_combustion', 'renewable', 'storage'))
           AS generation_mw
FROM adj
LEFT JOIN gen_adj g ON g.finding_id = adj.finding_id
JOIN site_members sm ON sm.application_id = adj.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL
  AND adj.verdict = 'site_capacity' AND adj.value_mw IS NOT NULL
GROUP BY s.site_key
"""

# Candidate figures no route has adjudicated, per site: the blocker
# that makes a silence provisional.
PENDING_FIGURES_SQL = """
SELECT s.site_key, count(*)
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN findings f ON f.application_id = sm.application_id
WHERE s.retired_at IS NULL
  AND lower(coalesce(f.value_unit, '')) IN ('mw', 'mva', 'gw', 'kva', 'kw')
  AND NOT EXISTS (SELECT 1 FROM power_adjudication pa
                  WHERE pa.finding_id = f.id)
GROUP BY s.site_key
"""

LIVE_SITES_SQL = """
SELECT site_key FROM sites WHERE retired_at IS NULL ORDER BY site_key
"""


@dataclass
class Inputs:
    """Everything the registry's rules read, fetched once per build."""
    sites: list[str]
    figures: dict[str, dict]                 # site_key -> the four MW
    coverage: dict[str, dict[str, int]]      # site_profile.load_coverage_detail
    pending: dict[str, int]                  # site_key -> unadjudicated figures
    generators: dict[str, site_profile.GeneratorProfile]
    generation: dict[str, site_profile.GenerationFigure]
    # Only the scale cohort reads this, and only to reach
    # site_scale.power_estimate — the same ladder the sites table ranks
    # on, so a site is above the threshold here exactly when the table
    # shows it above the threshold. Defaulted so the rules that do not
    # need it can still be exercised with hand-built inputs.
    floorspace: dict[str, float] = field(default_factory=dict)
    # The operator rung's inputs, read by the scale cohort alone and
    # defaulted for the same reason `floorspace` is: a rule exercised
    # with hand-built inputs must not have to supply them. Empty means
    # no site has an eligible first-party claim, which is the corpus's
    # own state for all but a handful.
    claims: dict[str, list[dict]] = field(default_factory=dict)
    displacements: dict = field(default_factory=dict)


def load_inputs(conn) -> Inputs:
    figures: dict[str, dict] = {}
    generators: dict[str, site_profile.GeneratorProfile] = {}
    gen_rows: dict[str, list] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(LIVE_SITES_SQL)
        sites = [r[0] for r in cur.fetchall()]
        cur.execute(SITE_FIGURES_SQL)
        for key, it, tot, grid, gen in cur.fetchall():
            figures[key] = {
                "it_load_mw": None if it is None else float(it),
                "total_site_mw": None if tot is None else float(tot),
                "grid_mw": None if grid is None else float(grid),
                "generation_mw": None if gen is None else float(gen)}
        cur.execute(PENDING_FIGURES_SQL)
        pending = {k: int(n) for k, n in cur.fetchall()}
        cur.execute(site_profile.GENERATOR_SQL)
        for key, counts, texts in cur.fetchall():
            generators[key] = site_profile.generator_profile(
                counts or (), texts or ())
        cur.execute(site_profile.GENERATION_FIGURE_SQL)
        for key, mw, quote, basis, plant, count, rating in cur.fetchall():
            gen_rows[key].append((mw, quote, basis, plant, count,
                                  float(rating) if rating else None))
    generation = {k: site_profile.generation_figure(v)
                  for k, v in gen_rows.items()}
    with conn.cursor() as cur:
        claims = capacity_claims.load_site_claims(cur)
    return Inputs(sites, figures, site_profile.load_coverage_detail(conn),
                  pending, generators, generation,
                  site_scale.load_site_floorspace(conn),
                  claims, campus_scope.load_displacements())


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

def _stated_load(f: dict) -> float | None:
    """The larger of IT load and total site, both adjudicated.

    Both rather than the reader's fallback order (IT load first). The
    reader wants one headline and prefers the better-defined quantity;
    a ratio wants the site's own largest statement of what it will
    draw, and for Northumberland Energy Park that is 1,100 MW of total
    site against 72 MW of IT load — a different answer to "does demand
    exceed the connection".
    """
    vals = [v for v in (f.get("it_load_mw"), f.get("total_site_mw"))
            if v is not None]
    return max(vals) if vals else None


def read_in_full_silent(inputs: Inputs) -> CohortResult:
    """Prose read in full; no figure adjudicated as this site's capacity.

    Prose, not every document. The methodology skips drawings and
    samples objection letters on purpose, and a site whose only unread
    documents are elevations has been read. Counting every document
    gives 65 sites; counting what the deep-read is for gives 134, with
    11 more waiting on adjudication (2026-08-23). One definition
    (HISTORY, "one definition of intended-to-be-read"), and it is the
    reader's. `scripts/sweep_null_capacity.py` calls this.

    A site with capacity-unit findings nobody has adjudicated is not
    silent; it is waiting. Those are excluded and counted.
    """
    members, waiting = [], 0
    for key in inputs.sites:
        c = inputs.coverage.get(key)
        if not c or not c["prose_held"] or c["prose_read"] < c["prose_held"]:
            continue
        if inputs.figures.get(key):
            continue
        if inputs.pending.get(key):
            waiting += 1
            continue
        members.append(Member(key, {
            "prose_documents_read": c["prose_read"],
            "prose_documents_held": c["prose_held"],
            "documents_held": c["held"]}))
    notes = ()
    if waiting:
        notes = (f"{waiting} further site{'s' if waiting != 1 else ''} "
                 "read in full but holding capacity-unit findings not yet "
                 "adjudicated: excluded until they are.",)
    return CohortResult(tuple(members), notes=notes)


def demand_exceeds_connection(inputs: Inputs) -> CohortResult:
    """Stated load more than 1.5 times the stated grid connection."""
    members = []
    for key in inputs.sites:
        f = inputs.figures.get(key)
        if not f or f.get("grid_mw") is None:
            continue
        load = _stated_load(f)
        if load is None or load <= f["grid_mw"] * RATIO:
            continue
        members.append(Member(key, {
            "stated_load_mw": load,
            "load_quantity": ("total_site" if load == f.get("total_site_mw")
                              else "it_load"),
            "grid_connection_mw": f["grid_mw"],
            "ratio": round(load / f["grid_mw"], 2)}))
    return CohortResult(tuple(members))


def generation_no_fuel(inputs: Inputs) -> CohortResult:
    """On-site generation disclosed by figure or by count; no fuel named.

    One definition, stated: a site is in if it has an adjudicated
    on-site generation figure OR a generator count in its documents, and
    its documents name no fuel at all — not diesel, gas, HVO, hydrogen
    or biofuel. Measured 2026-08-23: 9 sites with a figure, 27 with a
    count, 34 with either.
    """
    members = []
    for key in inputs.sites:
        g = inputs.generators.get(key)
        fig = inputs.generation.get(key)
        has_count = bool(g and g.count)
        if not (has_count or fig):
            continue
        if g and g.fuel_label:
            continue
        members.append(Member(key, {
            "generation_mw": fig.value_mw if fig else None,
            "generation_basis": fig.basis if fig else "",
            "generator_count": g.count if g else None}))
    return CohortResult(tuple(members))


# A generation figure is comparable with a load only where the
# adjudication says it describes a total. A per-unit rating is one
# machine — JVC discloses sixteen units of 3.2 MW, and multiplying is
# the mistake this cohort was withheld to avoid — and `unclear` is the
# adjudicator saying the passage does not settle which.
_TOTAL_BASES = {"installation_total", "site_total", "stated_group_total"}
# The margin. Not "larger than": a site whose generation matches its load
# to within a third is a site with standby cover for what it draws, which
# is ordinary. This asks for generation half again as large.
_GENERATION_MARGIN = 1.5


def generation_exceeds_load(inputs: Inputs) -> CohortResult:
    """On-site generation half again as large as the load the site states.

    Withheld from 2026-08-23 until the generation batch had run, because
    the rule computed on raw figures selected nine sites and at least two
    of them wrongly: JVC Business Park's 165 MW was "50 x 3.3 MWt
    Generators", which is heat, and Rover Way's 1,000 MW was an "energy
    capacity" the quote attributed to no plant at all.

    `gpt-5/generation-2.5` has since adjudicated 1,667 figures for what
    each one describes, and it settles both — JVC's headline is now a
    per-unit 3.2 MW with the 165 set aside as not generation, and every
    one of Rover Way's seven figures is set aside the same way, so
    neither site can enter. The rule reads that adjudication rather than
    the quotes, which is what it was waiting for.

    A figure's plant type does not decide membership: standby plant
    larger than the load is the finding, not a disqualification. It
    travels with each member so a reader can see which kind it is.
    """
    members, skipped, bounded = [], 0, 0
    for key in inputs.sites:
        gen = inputs.generation.get(key)
        if not gen or not gen.value_mw:
            continue
        if gen.basis_key not in _TOTAL_BASES:
            skipped += 1
            continue
        # A ceiling is not a measurement. Yorkshire Energy Park states
        # "generation totalling less than 50 MW" in every passage it
        # gives, on-site and off-site together, because above 50 MW a
        # generating station in England needs a DCO rather than local
        # permission. Its own energy centre is 13.5 MW against a 27 MW
        # load, so on this rule the site was in the cohort backwards
        # (Luke, 2026-08-25: drop it). 855 findings across 51 sites state
        # a sub-50 bound, so this is a behaviour rather than one row.
        if gen.bounded:
            bounded += 1
            continue
        f = inputs.figures.get(key, {})
        loads = [(v, q) for q, v in
                 (("it_load", f.get("it_load_mw")),
                  ("total_site", f.get("total_site_mw"))) if v]
        if not loads:
            continue
        # The larger of the two, which is the conservative one: a bigger
        # load makes membership harder to reach, never easier.
        load, quantity = max(loads)
        if gen.value_mw < _GENERATION_MARGIN * load:
            continue
        members.append(Member(key, {
            "generation_mw": round(gen.value_mw, 1),
            "load_mw": round(load, 1),
            "load_quantity": quantity,
            "ratio": round(gen.value_mw / load, 2),
            "generation_basis": gen.basis_key,
            "plant_type": gen.plant_type or "not settled"}))
    notes = []
    if skipped:
        notes.append(
            f"{skipped} further sites disclose a generation figure that the "
            f"adjudication reads as one machine's rating, or does not settle. "
            f"Those are not comparable with a load and are excluded rather "
            f"than multiplied.")
    if bounded:
        notes.append(
            f"{bounded} more give their generation as a ceiling — \u201cless "
            f"than 50 MW\u201d, \u201ccapped at 50 MW\u201d — which says "
            f"where a scheme sits relative to the consenting threshold rather "
            f"than how large its plant is, and cannot be compared with a load.")
    return CohortResult(tuple(members), notes=tuple(notes))


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def at_least_100mw(inp: Inputs) -> CohortResult:
    """Sites whose best available figure reaches 100 MW.

    Not like the other four. They ask what the documents do or do not
    say; this asks how big the thing is, and its answer can rest on a
    floorspace estimate — arithmetic this project performed, not a
    number anybody disclosed. That is worth having (Luke, 2026-08-25:
    "no reader will care that it's derived using a slightly different
    mechanism") but it must not be invisible, so every member records
    the basis and the confidence that put it here, and the notes say how
    many are here on an estimate.

    A site with no figure is not a member. That is not a claim it is
    smaller than 100 MW — see `limits`.
    """
    members, inferred, on_operator = [], 0, 0
    for key in inp.sites:
        f = inp.figures.get(key, {})
        cov = inp.coverage.get(key, {})
        _claim, _displaces = capacity_claims.rung_inputs(
            key, inp.claims.get(key, []), inp.displacements)
        est = site_scale.power_estimate(
            it_load_mw=f.get("it_load_mw"),
            total_site_mw=f.get("total_site_mw"),
            grid_mw=f.get("grid_mw"),
            generation_mw=f.get("generation_mw"),
            floorspace_sqm=inp.floorspace.get(key),
            has_documents=bool(cov.get("held")),
            prose_held=cov.get("prose_held"),
            prose_read=cov.get("prose_read"),
            operator_claim=_claim, operator_displaces=_displaces)
        if est.value_mw is None or est.value_mw < 100:
            continue
        if est.confidence == "Indicative":
            inferred += 1
        if est.basis == site_scale.OPERATOR_BASIS:
            on_operator += 1
        members.append(Member(key, {
            "power_mw": round(est.value_mw, 1),
            "basis": est.basis,
            "confidence": est.confidence or ""}))
    notes: tuple[str, ...] = ()
    if inferred:
        notes += (f"{inferred} of these {len(members)} are here on a figure "
                  f"inferred from floorspace rather than disclosed. Each row "
                  f"carries its basis and confidence.",)
    if on_operator:
        notes += (f"{on_operator} of these {len(members)} stand on an "
                  f"operator-stated campus figure rather than on the "
                  f"planning record. Every row says so, and names the "
                  f"planning record's own figure beside it.",)
    return CohortResult(tuple(members), notes=notes)


REGISTRY: tuple[Cohort, ...] = (
    Cohort(
        key="read_in_full_silent",
        headline=(
            "{n} sites whose files were read in full state no capacity "
            "at all"),
        tone="red",
        title="Read in full, and silent on capacity",
        family="coverage",
        definition=(
            "Every prose document held for the site has been analysed, and "
            "no figure in any of them has been adjudicated as this site's own "
            "power capacity — IT load, total site load, grid connection or "
            "on-site generation."),
        rule=(
            "prose_read >= prose_held and prose_held > 0; no power_adjudication "
            "row with verdict site_capacity on any member application; no "
            "capacity-unit finding awaiting adjudication."),
        limits=(
            "Silence in the documents held, which is not the same as silence. "
            "The register may publish a subset of what was submitted; a "
            "capacity can be stated in a document the council never put "
            "online, or in a drawing, which the deep-read skips by design. "
            "A figure can also be present and not yet adjudicated, in which "
            "case the site is excluded here until it is. Sites with a "
            "floor-area estimate are in this cohort: an estimate is this "
            "project's inference, not the applicant's disclosure."),
        order=1, rule_version="2026-08-23.1",
        compute=read_in_full_silent),
    Cohort(
        key="demand_exceeds_connection",
        headline=(
            "{n} sites state a demand materially above the connection "
            "their own documents describe"),
        tone="red",
        title="Demand stated above the grid connection",
        family="power",
        definition=(
            "The site's own documents state a load — IT load or total site "
            "load — more than one and a half times the grid connection they "
            "also state."),
        rule=(
            f"max(it_load_mw, total_site_mw) > {RATIO} × grid_connection_mw, "
            "all three adjudicated site_capacity, each the largest such figure "
            "across the site's applications."),
        limits=(
            "The two figures can come from different applications at the "
            "same site, and so describe different buildings or phases rather "
            "than one scheme's shortfall. A grid figure can be an export "
            "limit filed as a connection (Kingsnorth's 49.9 MW is one; see "
            "ROADMAP) or a phase-one offer beside a full-build load. A site "
            "can also be two schemes clustered by proximity — Ocean Estates "
            "merges a Salford application with a Trafford one. Hand-checks "
            "are recorded per site below and are the only thing here that "
            "says a membership holds."),
        order=2, rule_version="2026-08-23.1",
        compute=demand_exceeds_connection),
    Cohort(
        key="generation_no_fuel",
        headline=(
            "{n} sites describe on-site generation without naming a "
            "fuel or a plant type"),
        tone="amber",
        title="Generation disclosed, fuel not named",
        family="generation",
        definition=(
            "The documents disclose on-site generation — by an adjudicated "
            "figure, or by a count of generators — and nowhere name what it "
            "runs on."),
        rule=(
            "An adjudicated onsite_generation figure or a generator count > 0 "
            "from the generator profile, and an empty fuel label from the same "
            "profile (no diesel, gas, HVO, hydrogen or biofuel term in the "
            "generator passages)."),
        limits=(
            "Fuel is detected by term in the passages the deep-read extracted, "
            "not by reading every document, so a fuel named once in an "
            "appendix can be missed; the count disclosed may be one building's "
            "rather than the site's; and a count of zero is not disclosure of "
            "none. The figure, where there is one, is labelled by "
            "generation_figure as one machine's rating or as stated, and the "
            "per-unit cases are not multiplied."),
        order=3, rule_version="2026-08-23.1",
        compute=generation_no_fuel),
    Cohort(
        key="generation_exceeds_load",
        headline=(
            "{n} sites disclose on-site generation half again as large as "
            "the load they state"),
        tone="amber",
        title="Generation larger than the load",
        family="generation",
        definition=(
            "The site's own adjudicated on-site generation figure is more than "
            "one and a half times its stated load."),
        rule=(
            f"generation_mw >= {_GENERATION_MARGIN} \u00d7 max(it_load_mw, "
            "total_site_mw), over generation figures the adjudication reads "
            "as a total for an installation, a stated group or the site — "
            "never a per-unit rating, and never one it could not settle."),
        limits=(
            "Nothing here is a finding about intent. A standby fleet sized to "
            "carry the whole load qualifies, and so it should — that is a "
            "property of the documents — but it is not evidence that anyone "
            "means to run it. The plant type travels with each site for that "
            "reason, and where the documents do not say how the plant is "
            "meant to run it says so rather than guessing. Sites whose "
            "generation figure is one machine's rating are excluded, not "
            "multiplied by a count found elsewhere; the number excluded that "
            "way is printed beside this rule. So are the sites whose figure "
            "is a ceiling — \u201cgeneration totalling less than 50 MW\u201d "
            "— which says where a scheme sits relative to the consenting "
            "threshold above which a generating station needs a DCO, not how "
            "large its plant is. And a site absent from here may still hold "
            "generation larger than its load: it may state no load at all, "
            "which most of the corpus does not."),
        order=4, rule_version="2026-08-25.1",
        compute=generation_exceeds_load),
    Cohort(
        key="at_least_100mw",
        tone="slate",
        title="100 MW or more",
        headline=("{n} sites are at one hundred megawatts or more on the "
                  "best figure available for them"),
        family="power",
        definition=(
            "The best available capacity for the site reaches 100 MW. Best "
            "available is the same ladder the sites table ranks on: a "
            "disclosed IT load or total site demand first, then a campus "
            "figure the operator publishes about its own facilities, then a "
            "contracted grid connection or a standby-implied figure, and "
            "last a figure inferred from floorspace. An operator figure may "
            "also stand above a disclosed one, but only where a hand "
            "adjudication has recorded that the planning figure describes a "
            "single facility of the campus and has named the claim that "
            "replaces it. The 100 MW line is the industry's "
            "own, not this project's: IBM's working definition of a "
            "hyperscale data centre puts it at 100 MW or more "
            "(https://www.ibm.com/think/topics/hyperscale-data-center). The "
            "older formal definition — 5,000 servers in 10,000 square feet "
            "— is unusable against planning records, because server counts "
            "change too quickly for applicants to state them; power is the "
            "quantity these documents actually disclose."),
        rule=(
            "site_scale.power_estimate(...).value_mw >= 100, over the "
            "adjudicated figures for the site plus its floorspace."),
        limits=(
            "A site that is not here has not been shown to be smaller than "
            "100 MW. Most of the corpus discloses no capacity at all, and an "
            "undisclosed figure is an absence in the record rather than a "
            "small number. A campus of several facilities can also be absent "
            "because its figures are per-facility and no defensible total "
            "exists: where the documents disclose different kinds of quantity "
            "for different facilities — an average operational load, a "
            "commissioning milestone, a design capacity — nothing can be "
            "summed, and the site ranks on its largest single figure. Where "
            "the operator publishes a campus figure and a hand adjudication "
            "has accepted it, the site ranks on that figure instead, "
            "labelled, with the planning record's own figure named beside "
            "it — which is how Stockley Park's five facilities now rank on "
            "VIRTUS's own 112.5 MW rather than on the 24 MW commissioning "
            "milestone of one of them. A campus with no such adjudication "
            "keeps the older behaviour. This is also the one cohort whose "
            "membership can "
            "rest on arithmetic — a floorspace estimate is this project's "
            "inference, not an applicant's disclosure, and it is the weakest "
            "class of figure in the release; the count of members standing "
            "on one is printed beside this rule, and every row says which "
            "basis put it there."),
        order=5, rule_version="2026-09-01.1",
        compute=at_least_100mw),
)

FAMILIES = ("coverage", "power", "generation")


def _validate_registry() -> None:
    keys = [c.key for c in REGISTRY]
    if len(set(keys)) != len(keys):
        raise CohortError("duplicate cohort key in REGISTRY")
    orders = [c.order for c in REGISTRY]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        raise CohortError("REGISTRY order must be explicit, unique and ascending")
    for c in REGISTRY:
        if c.family not in FAMILIES:
            raise CohortError(f"cohort {c.key!r}: family {c.family!r} unknown")


_validate_registry()


def by_key(key: str) -> Cohort:
    for c in REGISTRY:
        if c.key == key:
            return c
    raise KeyError(key)


# ---------------------------------------------------------------------------
# Hand-checks
# ---------------------------------------------------------------------------

def load_checks(path: Path = CHECKS_PATH) -> list[Check]:
    """Read and validate cohort_checks.yaml. Raises CohortError."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    out: list[Check] = []
    known = {c.key for c in REGISTRY}
    seen: set[tuple[str, str]] = set()
    for i, raw in enumerate((doc or {}).get("checks") or []):
        where = f"check {i + 1}"
        if not isinstance(raw, dict):
            raise CohortError(f"{where}: must be a mapping")
        site_key = str(raw.get("site_key") or "").strip()
        cohort = str(raw.get("cohort") or "").strip()
        verdict = str(raw.get("verdict") or "").strip()
        by = str(raw.get("checked_by") or "").strip()
        date = str(raw.get("date") or "").strip()
        if not site_key:
            raise CohortError(f"{where}: needs a site_key")
        where = f"check {site_key}/{cohort}"
        if cohort not in known:
            raise CohortError(f"{where}: cohort must be one of {sorted(known)}")
        if verdict not in CHECK_VERDICTS:
            raise CohortError(f"{where}: verdict must be one of "
                              f"{sorted(CHECK_VERDICTS)}, got {verdict!r}")
        if not by or not date:
            raise CohortError(f"{where}: needs checked_by and date")
        if (site_key, cohort) in seen:
            raise CohortError(f"{where}: listed twice")
        seen.add((site_key, cohort))
        out.append(Check(site_key, cohort, verdict, by, date,
                         str(raw.get("note") or "")))
    return out


@dataclass(frozen=True)
class Computed:
    cohort: Cohort
    result: CohortResult
    checks: tuple[Check, ...]           # for this cohort, any site

    @property
    def confirmed(self) -> int:
        keys = self.result.site_keys
        return sum(1 for c in self.checks
                   if c.verdict == "holds" and c.site_key in keys)

    @property
    def disputed(self) -> tuple[Check, ...]:
        """Checks that say does_not_hold on a member: the rule selected
        a site a person has looked at and rejected."""
        keys = self.result.site_keys
        return tuple(c for c in self.checks
                     if c.verdict == "does_not_hold" and c.site_key in keys)

    @property
    def outside(self) -> tuple[Check, ...]:
        """Checks on sites the rule does not select — reported, not hidden."""
        keys = self.result.site_keys
        return tuple(c for c in self.checks if c.site_key not in keys)


def compute_all(conn, checks: list[Check] | None = None) -> list[Computed]:
    """Every registered cohort, in registry order, members by site key."""
    inputs = load_inputs(conn)
    checks = load_checks() if checks is None else checks
    out: list[Computed] = []
    for c in REGISTRY:
        r = c.compute(inputs)
        r = CohortResult(tuple(sorted(r.members, key=lambda m: m.site_key)),
                         r.withheld, r.notes)
        out.append(Computed(c, r, tuple(k for k in checks if k.cohort == c.key)))
    return out
