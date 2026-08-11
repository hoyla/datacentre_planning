"""Choose what the deep-read actually sends to a model.

Reading every page of every document is not affordable and not
necessary. Measured 2026-08-06: granite4.1:30b takes ~118s for one
12,000-character document, so the 27,240-document corpus would need
roughly 890 hours. Even a tenfold speedup leaves days of continuous
running, and most of that time would be spent reading site-location
plans and near-identical objection letters.

Three reductions, in order of how much they save and how little they
cost:

1. **Skip drawings.** A location plan, elevation or floor plan carries
   no extractable prose. 23% of the corpus, discarded outright.
2. **Tier the rest.** Statutory consultee responses, planning and energy
   statements, officer reports and screening opinions are read in full —
   they are where disclosures live. Public objection letters (1,900+ of
   them, largely repetitive) are *sampled*, because their value is
   aggregate sentiment rather than unique fact, and the sample size is
   recorded so the sampling is visible in the methodology rather than
   hidden.
3. **Page-filter the long ones.** A 200-page Environmental Statement
   might mention generators on six pages. Pages are scored against the
   power and environmental lexicons (dcp/signals.py plus the power terms
   below) and only candidate pages — with a little context either side —
   are sent. This is where the bulk of the saving comes from, and it is
   deterministic and reproducible: the same document always yields the
   same pages.

Nothing here decides *what is true*; it decides *what to look at*. Every
page not sent is recorded as not-sent, so coverage can be stated
honestly: "we read the pages matching these terms, in these documents,
and sampled these others" is a defensible methodology; "we read
everything" would not be true.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dcp import signals

# Documents whose content is graphical. Matched against the recorded
# document `kind`; anything unmatched is treated as prose (inclusive by
# default, per the project's false-positive-over-false-negative rule).
DRAWING_KINDS = re.compile(
    r"drawing|elevation|section\b|floor plan|site location plan|location plan|"
    r"block plan|masterplan|photograph|photo\b|montage|visualisation|"
    r"street scene|survey plan|topographic|boundary plan|red line", re.I)

# Statutory instruments, tested BEFORE the drawing rule and nothing else.
#
# `DRAWING_KINDS` contains `section\b` for architectural sections, and it
# was tested first, so "Section 106 Agreement" came back `skip` — a
# drawing — though TIER_A_KINDS lists `section 106` explicitly and was
# plainly written to catch it. 58 documents recording planning
# obligations were never read, while "S106 Agreement" took the intended
# path: whether an obligation was read turned on how the council
# abbreviated it.
#
# Deliberately not fixed by reordering the two rules wholesale. Measured
# over the corpus, that moves 68 documents and 10 of them are genuine
# drawings pulled into the read tier by an incidental word — "Water
# Treatment Plans, Sections and Elevations", "NOISE ... LOCATION PLAN",
# "Drawing - Decision". Nor by excluding numbers from `section\b`, which
# un-skips "Section 1", "Section 01" and "Section 03" — those ARE
# numbered architectural sections.
#
# What is true is narrower than either: a named statutory instrument is
# never a drawing, whatever else its title says. That is this pattern,
# and it moves 60 documents, 58 of them the s106 agreements.
LEGAL_INSTRUMENT_KINDS = re.compile(
    r"\bs\.?10[68]\b|\bsection 10[68]\b|\bsection 73\b|"
    r"unilateral undertaking|planning obligation", re.I)

# Read in full: where power, environmental and consenting facts are stated.
TIER_A_KINDS = re.compile(
    r"planning statement|design and access|environmental statement|es (chapter|volume)|"
    r"energy|sustainab|air quality|noise|flood risk|drainage|ecolog|heritage|"
    r"transport (assessment|statement)|officer report|committee report|"
    r"decision notice|decision\b|screening|scoping|consult(ee|ation) response|"
    r"statutory consultee|environment agency|water|utilities|infrastructure|"
    r"supporting (information|statement)|application form|s106|section 106", re.I)

# Sampled rather than read exhaustively: many near-identical documents
# whose value is aggregate rather than individual.
TIER_C_KINDS = re.compile(
    r"objection|public comment|neighbour (comment|response)|petition|"
    r"background paper|correspondence", re.I)

# Power terms — the environmental families come from dcp/signals.py so the
# two stay in step.
POWER_TERMS = (
    "generator", "generation", "gas engine", "gas turbine", "chp",
    "combined heat and power", "energy centre", "diesel", "fuel storage",
    "fuel tank", "substation", "grid connection", "private wire", "bess",
    "battery", "megawatt", "mw", "mva", "kva", "backup power", "standby",
    "resilience", "uninterruptible", "ups", "load", "power demand",
    "emergency power", "peak demand", "connection agreement",
)
_POWER_RE = re.compile(
    "|".join(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])" for t in POWER_TERMS),
    re.I)


@dataclass
class DocumentPlan:
    """What the deep-read will do with one document."""
    application_ref: str
    sha: str
    kind: str | None
    tier: str                      # 'A' | 'B' | 'C' | 'skip'
    reason: str
    pages_total: int = 0
    pages_selected: list[int] = field(default_factory=list)
    sampled_out: bool = False

    @property
    def will_read(self) -> bool:
        return self.tier != "skip" and not self.sampled_out


def classify_kind(kind: str | None) -> tuple[str, str]:
    """`(tier, reason)` from the document kind alone.

    Order is load-bearing. Statutory instruments are tested first
    because their titles collide with the drawing vocabulary; see
    LEGAL_INSTRUMENT_KINDS. Everything after that is drawings, then
    tier A, then the sampled repetitive classes.
    """
    if kind and LEGAL_INSTRUMENT_KINDS.search(kind):
        return "A", "statutory instrument"
    if kind and DRAWING_KINDS.search(kind):
        return "skip", "graphical document"
    if kind and TIER_A_KINDS.search(kind):
        return "A", "statement/report/consultee response"
    if kind and TIER_C_KINDS.search(kind):
        return "C", "repetitive class — sampled"
    return "B", "unclassified prose"


def score_page(text: str) -> int:
    """How many distinct relevant terms a page mentions."""
    if not text:
        return 0
    power = len(set(m.group(0).lower() for m in _POWER_RE.finditer(text)))
    env = sum(len(v) for v in signals.environmental_signals(text).values())
    return power + env


# Per-tier selection settings, measured against 5,421 real pages
# (2026-08-07). The threshold stays at 1 everywhere: raising it to 2
# halves the pages sent but drops any page whose only relevant content is
# a single term — a page reading "1.5 MW" scores 1 — and in this
# investigation a missed disclosure costs far more than a wasted read.
# The saving comes from context instead, which is padding rather than
# evidence: Tier A (statements, consultee responses, officer reports)
# keeps a page either side so a figure is not orphaned from its heading;
# lower tiers take hit pages only. Result: 58% -> 43% of pages, with no
# document reduced to nothing at any setting tried.
TIER_SETTINGS: dict[str, dict] = {
    "A": {"min_score": 1, "context": 1},
    "B": {"min_score": 1, "context": 0},
    "C": {"min_score": 1, "context": 0},
}


# A ceiling on how much text one document may send, in characters.
#
# The scorer has no notion of how big a page is, and some pages are very
# big: a 32-sheet xlsx emissions tracker (Hillingdon/18399/APP/2025/1412)
# scored every sheet as a hit — each mentions NOx, emissions and load —
# and produced 2,075,466 characters, which the runner turned into 204
# sequential model calls and about half an hour on one document. 542
# cached extractions exceed 400,000 characters and between them hold 448
# million, so this is a class, not a case.
#
# Collapsing near-identical pages was tried first and rejected. Line-level
# similarity does find the 24 duplicate year-sheets, but on a soil
# analytical report it also finds 118 of 208 pages "duplicate": same
# laboratory letterhead, same determinand rows, differing only in sample
# ids and measured values. Those numbers are the evidence. A rule that
# cannot tell "same layout, no data" from "same layout, different data"
# has no business deleting pages.
#
# So: cap, keep the highest-scoring pages within it, and record the rest
# as not sent.
#
# The number was first set at 120,000 on the assumption that ten chunks
# was ample for any real document. It was not: measured over 60 large
# documents the *median* selection is 162,781 characters, so 120,000 sat
# below the middle of the distribution and bound on 67% of them. It was
# taking 230 selected pages of a SUPPORTING INFORMATION down to 58, a
# committee report from 135 to 40, and a Revised Environmental Statement
# from 83 to 41 — an Environmental Statement being exactly where
# disclosures live. A threshold calibrated on one pathological workbook
# was cutting the documents this investigation exists to read.
#
# Recalibrated on the distribution instead:
#
#     median 162,781 · p90 419,076 · p95 647,335 · p99 732,786
#     the xlsx tracker that started this: 2,075,466
#
# 1,000,000 sits above p99 and below the outliers, and binds on 1 in 60
# large documents rather than 40. The cost that actually matters is
# sequential model calls: at the runner's 12,000-character chunk a
# capped document is ~83 calls, a few minutes, against the 204 calls and
# half an hour that prompted this.
MAX_SELECTED_CHARS = 1_000_000


def select_pages(pages: list[str], *, tier: str, context: int | None = None,
                 min_score: int | None = None, always_read_first: int = 2,
                 max_pages: int | None = None,
                 max_chars: int | None = MAX_SELECTED_CHARS) -> list[int]:
    """Indices of pages worth sending.

    Short documents are sent whole — filtering a four-page letter saves
    nothing and risks dropping the one line that matters. Longer ones are
    scored per page, with `context` pages either side of a hit included
    so a figure separated from its heading is not orphaned. The opening
    pages are always read: they carry the description of development,
    the applicant, and the document's own summary.

    `max_chars` bounds the total text returned. When it binds, pages are
    dropped lowest-score-first — never truncated mid-page, because half a
    page produces quotes that fail the verbatim gate against the whole
    one. The opening pages survive regardless. Pass None to disable.
    """
    settings = TIER_SETTINGS.get(tier, TIER_SETTINGS["B"])
    if context is None:
        context = settings["context"]
    if min_score is None:
        min_score = settings["min_score"]
    n = len(pages)
    if n <= 6:
        return list(range(n))
    keep: set[int] = set(range(min(always_read_first, n)))
    scored = [(i, score_page(p)) for i, p in enumerate(pages)]
    hits = [i for i, s in scored if s >= min_score]
    if max_pages is not None and len(hits) > max_pages:
        hits = [i for i, _s in sorted(
            ((i, s) for i, s in scored if s >= min_score),
            key=lambda kv: -kv[1])[:max_pages]]
    for i in hits:
        for j in range(max(0, i - context), min(n, i + context + 1)):
            keep.add(j)

    if max_chars is not None and sum(len(pages[i]) for i in keep) > max_chars:
        # Opening pages are not negotiable — they carry the description
        # of development and the applicant, and a document reduced to
        # nothing is worse than one reduced to its summary.
        floor = set(range(min(always_read_first, n)))
        budget = max_chars - sum(len(pages[i]) for i in floor)
        by_score = sorted((i for i in keep if i not in floor),
                          key=lambda i: (-score_page(pages[i]), i))
        kept = set(floor)
        for i in by_score:
            if len(pages[i]) <= budget:
                kept.add(i)
                budget -= len(pages[i])
        return sorted(kept)

    return sorted(keep)


def selection_was_capped(pages: list[str], selected: list[int],
                         max_chars: int | None = MAX_SELECTED_CHARS) -> bool:
    """Whether `max_chars` bound, so the caller can say so out loud.

    Coverage is stated over what was actually read, so a document that
    hit the ceiling has to be recorded differently from one read whole —
    the same reason drawings and sampled objection letters are counted
    separately rather than quietly.
    """
    if max_chars is None:
        return False
    full = select_pages(pages, tier="A", max_chars=None)
    return (sum(len(pages[i]) for i in full) > max_chars
            and len(selected) < len(full))


def plan_documents(docs: list[dict], *, sample_rate: int = 5) -> list[DocumentPlan]:
    """Tier a set of documents and mark which repetitive ones are sampled.

    `docs` are dicts with at least `application_ref`, `sha`, `kind`.
    Sampling is deterministic (every Nth within its application) so a
    re-run reads the same documents — reproducibility matters more here
    than statistical purity, and the sampled-out ones are recorded.
    """
    plans: list[DocumentPlan] = []
    seen_c: dict[str, int] = {}
    for d in docs:
        tier, reason = classify_kind(d.get("kind"))
        plan = DocumentPlan(application_ref=d["application_ref"], sha=d["sha"],
                            kind=d.get("kind"), tier=tier, reason=reason)
        if tier == "C":
            k = d["application_ref"]
            idx = seen_c.get(k, 0)
            seen_c[k] = idx + 1
            if idx % sample_rate != 0:
                plan.sampled_out = True
                plan.reason = f"repetitive class — not in 1-in-{sample_rate} sample"
        plans.append(plan)
    return plans


# Every document attached to a live site, in ONE canonical order. The
# order is part of the contract: plan_documents samples every Nth tier-C
# row *of what it is handed*, so two callers that filter differently
# before planning disagree about which fifth was ever meant to be read.
UNIVERSE_DOCS_SQL = """
SELECT d.id, a.application_ref, d.content_sha256, d.kind
FROM documents d
JOIN applications a ON a.id = d.application_id
WHERE EXISTS (SELECT 1 FROM site_members m
              JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
              WHERE m.application_id = d.application_id
                AND m.retired_at IS NULL)
ORDER BY a.application_ref, d.id
"""


def universe_plan(conn) -> dict[int, DocumentPlan]:
    """`{document_id: DocumentPlan}` for every document in the site universe.

    The single answer to "was this document ever meant to be read", for
    everyone who needs to know — the read cohorts and the coverage
    figures the reader publishes.

    It exists because the read cohort and the coverage figures had
    drifted apart. The cohort query filtered to one model's backlog
    *before* planning, so `plan_documents` sampled a different fifth of
    the repetitive tier than the global policy had — an unread-only
    cohort pulled in ~900 objections the policy had set aside, as an
    artefact of filter ordering rather than anyone's decision.

    A correction, because the first version of this docstring overstated
    it: the reader's headline coverage figure was never wrong. It comes
    from site_profile.load_coverage_detail, which has always split the
    repetitive tier out and reported it separately. What was wrong was
    narrower — the per-application analysis table counted every
    non-drawing document as prose, so it over-stated how many
    applications had reading outstanding. Both now agree that prose means
    tiers A and B, and that tier C is a category of its own.

    Both now ask this. `plan.will_read` is the denominator of any honest
    coverage claim; `plan.sampled_out` is a separate, statable number,
    never silently folded into either side.
    """
    with conn.cursor() as cur:
        cur.execute(UNIVERSE_DOCS_SQL)
        rows = cur.fetchall()
    docs = [{"application_ref": r[1], "sha": r[2], "kind": r[3]} for r in rows]
    return {r[0]: plan for r, plan in zip(rows, plan_documents(docs))}
