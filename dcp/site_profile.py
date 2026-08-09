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
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
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


@dataclass(frozen=True)
class GeneratorProfile:
    count: int | None
    fuels: list[tuple[str, int]]   # (label, mentions), most-mentioned first
    is_chp: bool
    caveat: str

    @property
    def fuel_label(self) -> str:
        """Dominant fuel first, with genuinely-present others named.

        Fuels below a fraction of the leader are summarised as
        'also referenced' rather than listed as though installed.
        """
        if not self.fuels:
            return ""
        top_label, top_n = self.fuels[0]
        parts = [f"{top_label} ({top_n})"]
        minor = []
        for label, n in self.fuels[1:]:
            if n >= top_n * FUEL_SECONDARY_FLOOR:
                parts.append(f"{label} ({n})")
            else:
                minor.append(label)
        out = ", ".join(parts)
        if minor:
            out += f"; also referenced: {', '.join(minor)}"
        return f"{out} — CHP" if self.is_chp else out


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
    caveat = ("Highest count disclosed across this site's documents; "
              "phases may be described separately. Not adjudicated for "
              "attribution, unlike the capacity figures — generator counts "
              "are rarely quoted as market context, which capacity "
              "routinely is.")
    return GeneratorProfile(max(usable), fuels, is_chp, caveat)


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
# it collapses to 76 of 429 sites. Building a "water use MW-equivalent"
# column on that would imply a precision the documents do not contain, and
# would invite exactly the comparison it cannot support.
#
# So two honest things are reported instead. Cooling METHOD is categorical
# and reasonably covered (119 sites) — and it is the question that actually
# determines water demand, since an air-cooled hall and an evaporative one
# differ by orders of magnitude. And the *absence* is reported as a finding
# in its own right: that only 18% of sites disclose anything about water
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
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    top_label, top_n = ranked[0]
    parts = [f"{top_label} ({top_n})"]
    minor = []
    for label, n in ranked[1:]:
        if n >= top_n * COOLING_SECONDARY_FLOOR:
            parts.append(f"{label} ({n})")
        else:
            minor.append(label)
    out = ", ".join(parts)
    if minor:
        out += f"; also referenced: {', '.join(minor)}"
    return out, ("Cooling technologies named in this site's documents, with "
                 "mention counts. Applications routinely compare options "
                 "before choosing, so more than one method may appear.")


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
# only state that counts as analysed: no_text and parse_failed are
# attempts, and treating an attempt as coverage is how an access problem
# gets mistaken for a null finding.
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


def _parties_for_sites(conn) -> dict[str, dict]:
    """Applicant and adviser names per site, ranked by how often named.

    Ranked rather than listed for the same reason as the finding families:
    a site's documents mention many organisations, and the one named forty
    times is the developer while the one named twice is a consultee's
    consultant. The count travels with the name so a reader can see which
    is which.

    Authorities are re-routed here rather than trusted from the family:
    the family came from the model's signal_type label, which put 1,536
    councils and development corporations among the advisers.
    """
    from collections import defaultdict
    from dcp import entities

    per_site: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int)))
    display: dict[str, str] = {}

    with conn.cursor() as cur:
        cur.execute(PARTIES_SQL)
        for site_key, family, value_text in cur.fetchall():
            e = entities.parse_entity(value_text)
            if e is None:
                continue
            display.setdefault(e.key, e.display)
            bucket = "authority" if e.is_authority else (
                "applicant" if family == "party_applicant" else
                "adviser" if family == "party_adviser" else "other")
            per_site[site_key][bucket][e.key] += 1

    def render(counts: dict[str, int], top: int = 3) -> str:
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
        return ", ".join(f"{display[k]} ({n})" for k, n in ranked)

    return {site_key: {
        "applicants": render(b.get("applicant", {})),
        "advisers": render(b.get("adviser", {})),
        "authorities": render(b.get("authority", {}), top=2),
    } for site_key, b in per_site.items()}


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

    for site_key, parties in _parties_for_sites(conn).items():
        profiles.setdefault(site_key, {}).update(parties)
    return profiles
