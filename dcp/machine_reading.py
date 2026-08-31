"""A machine's reading of one site's documents: inputs, prompt, gate.

READER_REDESIGN_PLAN §7b–c. The first place a model writes prose a
reporter sees per site, and so the place the project's rules about
machine output are at their strictest:

- **It reads the documents, not only the panels.** The input is the
  site's adjudicated figures with their quotes, its external claims with
  their match strength, its coverage, its generation profile, its
  parties and its cohort memberships — and the text of its tier-A
  documents: the planning statement, the energy statement, the officer
  report, the statutory consultees' letters. The EA letters that started
  this investigation are in that set.
- **Every figure carries a verbatim quote, and the quote is verified
  against the cached source text before the reading is stored.** The
  findings gate, reused (scripts/verify_findings.py's fragment match).
  A reading that fails is WITHHELD for that site with a one-line
  reason: never rendered, never fatal to the build.
- **No cross-site comparison, no ranking, no intent, no advice.** The
  prompt says so; the gate checks the parts of that it can — a sentence
  that names another site's key, or the words the rules forbid.
- **Idempotent on the input.** The hash is over exactly what the model
  was shown; a site whose inputs are unchanged is not re-read.

This module is the pure part: building the input, rendering the prompt,
checking the output. scripts/machine_reading_openai.py is the route that
submits, collects and stores.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dcp import extract
from dcp.deepread_select import classify_kind, score_page
from dcp.site_aliases import displayed

ROOT = Path(__file__).resolve().parent.parent

# 1.0 was run on Watford Bypass and read well, but named its sources by
# the council's filing label — "Supporting Documents" — and so called the
# Energy and Sustainability Statement the Environmental Statement. 1.1
# labels every page with the document's register filename instead. Under
# 1.1 the gate passed eleven of the twenty sample sites and refused nine,
# every refusal a real breach: a figure with no quote ("1 generator",
# "250MW"), a quote copied from memory rather than the page, "plans to".
# 1.2 tells the model each of those in the words the gate uses.
# reading-1.4 (2026-08-31): section 3 asks explicitly for adjudicated
# figures whose quantity type contradicts their own quote. The prompt
# already said "where the structured facts and the pages disagree, say
# so", and gpt-5 acted on it — catching an `energy_storage: 50 MW` on
# Elsham read from "Energy Centre (generation no greater than 50MW)
# including energy storage", where the number is the generation cap and
# no storage capacity is stated anywhere. Terra did not. Elsham carries
# six such rows. The model sees each figure's type beside its quote, so
# it is the cheapest place in the pipeline to catch a mis-typing the
# correction rules missed.
PROMPT_VERSION = "reading-1.4"

# The gate has a version of its own, in the table's key, because it is
# a judgement too. gate-1.0 refused Watford for a dropped comma and
# Didcot for the word "should" in a question about which figure governs;
# gate-1.1 lets punctuation differ between a quote and its page, searches
# every document the site holds when the cited one does not contain a
# quote (recording the correction), and forbids advice by its phrases
# rather than by the word "should". Every word and figure in a quote
# must still match, in order.
#
# gate-2.0 (2026-08-23, Luke's decision): the paragraph is the unit, not
# the reading. A reading carries thirty to forty quotes and the model
# slips on roughly one in a hundred, so gating the whole reading made a
# third of the sample fail every run — a different third each time.
# Now each paragraph is judged alone: the ones whose quotes and figures
# verify render, and a failed one is withheld with its reason where it
# would have stood. Nothing unverified renders, and one slip no longer
# costs the thirty-nine verified quotes around it. A reading is refused
# outright only when it is empty or every paragraph fails.
#
# Two narrower changes ride along. Intent verbs are allowed in the
# questions section alone — "does the applicant intend to run the
# engines at night?" asks about intent, it does not assert it; every
# other section still refuses them. And a quote that runs across a page
# break now verifies: registers' documents carry running headers, and
# Watford's BREEAM quote was refused for the header sitting mid-sentence
# where the page turned. Lines that repeat across a document's pages are
# stripped and the pages joined before the last attempt at a match.
#
# gate-1.2 (2026-08-23): whitespace inside the page text is not evidence
# either. Two of the twenty-site sample's five refusals were extraction
# artefacts — "the general buildi ng services" on Ocean Estates' page,
# a doubled space on Rover Way's — against quotes that read the page
# correctly. HISTORY already records the rule ("a literal space never
# matches PDF text"); the gate now applies it: after the punctuation
# pass, the fragments and the page are compared with all whitespace
# removed, every word and figure still required in order.
# gate-2.1 (2026-08-31): the squash above takes the findings gate's
# 25-character minimum. An unguarded whitespace-blind match admits a
# three-character quote against any page, which is a substring lottery
# rather than verification; the threshold is set from the distribution of
# real recoveries (median 122 characters, first percentile 26), so it
# costs 0.7% of them. Bumped alongside the move to gpt-5.6-terra, which
# re-reads every site regardless.
GATE_VERSION = "gate-2.1"

# The text budget per site, in characters. ~120k tokens: enough for a
# planning statement, an energy statement, an officer report and the
# consultee letters in full on a mid-sized application; Amazon Didcot's
# 259 tier-A documents are 19.6 million characters and have to be
# selected from. Pages are chosen by the deep-read's own relevance
# score so that the selection is the methodology's, not a regex written
# here.
TEXT_BUDGET_CHARS = 480_000
PAGE_CHARS_CAP = 6_000          # a page longer than this is a table dump

# Document kinds the reading wants first, most-wanted first. A document
# matching an earlier pattern outranks one matching a later pattern, and
# both outrank the tier-B prose that no pattern names. Consultee letters
# sit above the applicant's own statements deliberately: they are the
# independent reading of the scheme, and the EA's are why this project
# exists.
KIND_PRIORITY: tuple[str, ...] = (
    r"environment agency|statutory consultee|consult(ee|ation) response",
    r"officer report|committee report|decision notice|decision\b",
    r"planning statement|supporting (information|statement)",
    r"energy|sustainab|utilit|infrastructure",
    r"environmental statement|es (chapter|volume)|screening|scoping",
    r"design and access|application form|s106|section 106",
)
_KIND_RES = tuple(re.compile(p, re.IGNORECASE) for p in KIND_PRIORITY)


def kind_rank(kind: str | None) -> int:
    """0 for the most wanted kind, len(KIND_PRIORITY) for unnamed prose."""
    for i, rx in enumerate(_KIND_RES):
        if kind and rx.search(kind):
            return i
    return len(KIND_PRIORITY)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class Page:
    document_id: int
    application_ref: str
    kind: str
    page: int
    text: str


@dataclass
class SiteInput:
    site_key: str
    name: str
    panel: dict                                 # the structured facts
    pages: list[Page] = field(default_factory=list)
    documents_considered: int = 0
    documents_read: int = 0
    # Every cached page of every document the site holds, for the gate:
    # a quote may come from a page that was not sent, and that is still
    # a verbatim quote from the site's documents.
    cache: dict[int, list[str]] = field(default_factory=dict)

    @property
    def input_hash(self) -> str:
        h = hashlib.sha256()
        h.update(json.dumps(self.panel, sort_keys=True, default=str).encode())
        for p in self.pages:
            h.update(f"\n{p.document_id}:{p.page}\n".encode())
            h.update(p.text.encode())
        return h.hexdigest()


FIGURES_SQL = """
WITH adj AS (
  SELECT DISTINCT ON (finding_id) finding_id, verdict, quantity_type,
         value_mw, is_maximum, application_id, document_id
  FROM power_adjudication
  ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC, id DESC)
SELECT adj.quantity_type, adj.value_mw, adj.is_maximum, a.application_ref,
       f.document_id, f.evidence_page, f.evidence_text, f.signal_type
FROM adj
JOIN findings f ON f.id = adj.finding_id
JOIN applications a ON a.id = adj.application_id
JOIN site_members sm ON sm.application_id = adj.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL AND s.site_key = %s
  AND adj.verdict = 'site_capacity' AND adj.value_mw IS NOT NULL
ORDER BY adj.quantity_type, adj.value_mw DESC, f.id
"""

CLAIMS_SQL = """
SELECT cl.claim_name, cl.value_mw, cl.quantity_type,
       coalesce(cl.attrs->>'operator', ''), coalesce(cl.attrs->>'operator_term', ''),
       cl.source_key, m.confidence, m.method, m.evidence
FROM capacity_claim_matches m
JOIN capacity_claims cl ON cl.id = m.claim_id
JOIN sites s ON s.id = m.site_id
WHERE s.retired_at IS NULL AND s.site_key = %s AND m.retired_at IS NULL
ORDER BY cl.value_mw DESC NULLS LAST, cl.claim_name, cl.id
"""

DOCS_SQL = """
SELECT d.id, a.application_ref, coalesce(d.kind, ''), d.content_sha256,
       coalesce(d.page_count, 0), coalesce(d.url, '')
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN applications a ON a.id = sm.application_id
JOIN documents d ON d.application_id = a.id
WHERE s.retired_at IS NULL AND s.site_key = %s AND d.bytes_path IS NOT NULL
ORDER BY d.id
"""

APPS_SQL = """
SELECT a.application_ref, coalesce(a.status, ''), a.date_received,
       a.date_decided, coalesce(a.description, ''), coalesce(c.name, '')
FROM sites s
JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
JOIN applications a ON a.id = sm.application_id
LEFT JOIN councils c ON c.gss_code = a.council_gss
WHERE s.retired_at IS NULL AND s.site_key = %s
ORDER BY a.date_received NULLS LAST, a.application_ref
"""


def _pages_for(ref: str, sha: str) -> list[str]:
    path = extract.cache_path_for("documents", ref, sha)
    if not path.exists():
        return []
    try:
        return [p or "" for p in (json.loads(path.read_text()).get("pages") or [])]
    except Exception:
        return []


def select_pages(docs: list[tuple], budget: int = TEXT_BUDGET_CHARS
                 ) -> tuple[list[Page], dict[int, list[str]], int]:
    """The pages to send, within the budget, and every cached page.

    `docs` are (id, ref, kind, sha, page_count, url). Tier C (objections,
    sampled by design) and the graphical tier are never sent. Within the
    rest, documents are taken in KIND_PRIORITY order and pages within a
    document by the deep-read's relevance score, highest first, with a
    document's first page always eligible because that is where it says
    what it is. A page over PAGE_CHARS_CAP is cut at the cap: a
    thousand-row table is not prose.
    """
    cache: dict[int, list[str]] = {}
    ranked: list[tuple[int, int, int, Page]] = []   # (kind rank, -score, doc, page)
    considered = 0
    for doc_id, ref, kind, sha, _n, url in docs:
        tier, _ = classify_kind(kind)
        # The page header names the document by its register filename,
        # not its kind: councils file nearly everything as "Supporting
        # Documents", and a model told only that called the Energy and
        # Sustainability Statement "the Environmental Statement" (1.0,
        # Watford). The kind still decides the tier and the priority.
        title = document_title(url, kind)
        pages = _pages_for(ref, sha)
        if pages:
            cache[doc_id] = pages
        if tier in ("skip", "C") or not pages:
            continue
        considered += 1
        rank = min(kind_rank(kind), kind_rank(title))
        for i, text in enumerate(pages, 1):
            if not text.strip():
                continue
            score = score_page(text) + (1 if i == 1 else 0)
            if score <= 0:
                continue
            ranked.append((rank, -score, doc_id, Page(
                doc_id, ref, title, i, text[:PAGE_CHARS_CAP])))
    ranked.sort(key=lambda t: (t[0], t[1], t[2], t[3].page))
    chosen: list[Page] = []
    used = 0
    for _r, _s, _d, page in ranked:
        if used + len(page.text) > budget:
            continue
        chosen.append(page)
        used += len(page.text)
    # Sent in document order, page order, so the model reads a document
    # as a document rather than as a relevance-sorted shuffle.
    chosen.sort(key=lambda p: (p.document_id, p.page))
    return chosen, cache, considered


def load_site_input(conn, site_key: str, *, profile: dict,
                    coverage: dict, cohorts: list,
                    budget: int = TEXT_BUDGET_CHARS) -> SiteInput:
    """Everything the model is shown for one site.

    `profile` is the site's entry from site_profile.load_site_profiles,
    `coverage` its entry from load_coverage_detail, `cohorts` the list
    from site_cohorts.compute_all — all loaded once by the caller, since
    each is a corpus-wide query.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT display_name FROM sites WHERE site_key = %s "
                    "AND retired_at IS NULL", (site_key,))
        row = cur.fetchone()
        # The name the model is told the site has, and so the name it
        # writes back in prose a reporter reads. It has to be the name
        # the reader shows: a derived title carrying a figure the
        # documents contradict — "250MW DATA CENTRE" against a stated
        # 400 MW connection — is contamination, not context.
        name = displayed(site_key, row[0] if row else None)
        cur.execute(FIGURES_SQL, (site_key,))
        figures = [{
            "quantity": q, "value_mw": float(mw), "is_maximum": mx,
            "application_ref": ref, "document_id": doc, "page": page,
            "quote": (quote or "").strip(), "label": label}
            for q, mw, mx, ref, doc, page, quote, label in cur.fetchall()]
        cur.execute(CLAIMS_SQL, (site_key,))
        claims = [{
            "claim": nm, "value_mw": None if mw is None else float(mw),
            "quantity": q, "published_by": by, "published_as": as_,
            "source": src, "match_confidence": conf, "match_method": meth,
            "match_evidence": ev}
            for nm, mw, q, by, as_, src, conf, meth, ev in cur.fetchall()]
        cur.execute(APPS_SQL, (site_key,))
        apps = [{"ref": ref, "status": st, "received": str(rec or ""),
                 "decided": str(dec or ""), "description": desc[:600],
                 "council": council}
                for ref, st, rec, dec, desc, council in cur.fetchall()]
        cur.execute(DOCS_SQL, (site_key,))
        docs = cur.fetchall()

    prof = profile or {}
    memberships = []
    for c in cohorts:
        for m in c.result.members:
            if m.site_key == site_key:
                memberships.append({"cohort": c.cohort.title,
                                    "definition": c.cohort.definition,
                                    "evidence": m.evidence})

    pages, cache, considered = select_pages(docs, budget)
    panel = {
        "site_key": site_key, "name": name,
        "applications": apps,
        "adjudicated_figures": figures,
        "external_claims": claims,
        "coverage": dict(coverage or {}),
        "generation": {
            "figure_basis": prof.get("gen_figure_basis", ""),
            "figure_note": prof.get("gen_figure_note", ""),
            "generator_count": prof.get("generator_count"),
            "generator_fuel": prof.get("generator_fuel", ""),
            "generator_caveat": prof.get("generator_caveat", "")},
        "parties": {k: prof.get(k, "") for k in (
            "end_user", "applicant_of_record", "operator_group", "advisers",
            "named_in_documents", "authority", "parties_source")},
        "cohorts": memberships,
    }
    return SiteInput(site_key, name, panel, pages, considered,
                     len({p.document_id for p in pages}), cache)


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

PROMPT = """\
You are reading the planning documents for ONE proposed or consented UK
data centre, for an investigative journalism project. Your reading will
be shown to reporters, collapsed and labelled as a machine's reading of
this site's documents — not as a finding.

You are given two things. First, the STRUCTURED FACTS this project has
already established about the site: its applications; the power figures
its documents state, each adjudicated as describing this site and each
with the verbatim quote it came from; the figures outside sources
publish about it; how much of its paperwork has been read; what its
generation plant looks like; who is behind it; and which named cohorts
it falls into. Second, PAGES from the site's own documents — planning
and energy statements, officer reports, statutory consultees' letters —
selected for relevance and labelled with the document and page they came
from.

Write three sections.

1. "what_the_documents_say" — what the documents say about this site's
   scale, its power, its on-site generation, and who is behind it. State
   it as the documents state it, with the document's own words. Where
   two documents disagree, say so and quote both. Where the structured
   facts and the pages disagree, say so.

2. "questions" — the questions the documents raise and who could answer
   them: a figure stated once and never again; a connection smaller than
   the load; a generation fleet described but never summed; a consultee
   asking something the applicant does not answer; a condition whose
   discharge is not in the file. Name the party that could answer each
   one — the applicant, the council, the grid operator, the Environment
   Agency — as a fact about who holds the information, not as an
   instruction to anyone.

3. "not_determined" — what could not be determined from what you were
   given: figures absent from the pages, documents referred to but not
   held, things the structured facts mark as unread or provisional.
   Include here any adjudicated figure above whose quantity type does
   not match its own quote: a thermal input typed as generation, a
   battery's rating typed as this site's power, an export limit typed
   as a connection, an annual energy figure typed as a power one, or a
   figure typed as storage on a quote that states a generation limit.
   Say which type the quote supports, and quote it. State it as an
   observation about the figure you were given, not as a correction to
   it and not as advice.

RULES. These are not style preferences; a reading that breaks one is
discarded — the whole reading, for this site, not the sentence.

- Every number with a unit that you write — MW, MVA, kW, GW, MWh, m2,
  sqm, hectares, £, and every COUNT of plant ("112 generators", "1
  generator", "two engines" written as a numeral) — must appear in a
  quote attached to the SAME paragraph. Write the number the way the
  quote writes it: if the quote says "49.9MW", do not write "50 MW" or
  "sub-50MW"; if it says "5MW", do not write "5,000 kW". A paragraph
  that states a figure the quotes beside it do not contain discards the
  reading.
- Every quote must be copied EXACTLY from the PAGES shown below, or
  from a structured fact above — never from memory of the document,
  never tidied. The same characters, the same line of figures. Copy
  from the passage in front of you and check it is there. Cite the
  document id and page for a page quote. An adjudicated power figure
  above is printed with the document and page it was read from: quote
  it and you cite those, exactly as you would a page quote. Cite the
  application reference alone only for a fact that has no document —
  an application's description, its status, its dates. A quote that is
  not on the page it cites discards the reading.
- Describe this site only. Do not compare it with any other site, do
  not rank it, do not say it is large or small for its kind, do not
  refer to "other sites" or "most data centres".
- Do not infer intent. Say what the documents state a plant is for when
  they state it; never write that the applicant "wants", "plans to",
  "intends", "proposes to" in your own voice, or "is really" doing
  anything. Write "the planning statement states that" and quote it.
- Do not advise. No "reporters should", "worth investigating", "the
  story here", "a red flag". State; do not recommend.
- Do not add knowledge from outside the documents and facts given. If
  you know something about this operator or this site from elsewhere,
  it does not belong here.
- Plain British English. Short paragraphs. No headings inside a
  section. No bullet points.

Return strict JSON:
{"sections": {
   "what_the_documents_say": [{"text": "...", "quotes": [{"quote": "...",
        "document_id": 123, "page": 4} | {"quote": "...",
        "application_ref": "..."}]}, ...],
   "questions": [ ...same shape... ],
   "not_determined": [ ...same shape... ]}}
No prose outside the JSON.

STRUCTURED FACTS
%(facts)s

PAGES
%(pages)s
"""

_QUOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "quote": {"type": "string"},
        "document_id": {"type": ["integer", "null"]},
        "page": {"type": ["integer", "null"]},
        "application_ref": {"type": ["string", "null"]},
    },
    "required": ["quote", "document_id", "page", "application_ref"],
    "additionalProperties": False,
}
_PARA_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "quotes": {"type": "array", "items": _QUOTE_SCHEMA},
    },
    "required": ["text", "quotes"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "object",
            "properties": {
                "what_the_documents_say": {"type": "array", "items": _PARA_SCHEMA},
                "questions": {"type": "array", "items": _PARA_SCHEMA},
                "not_determined": {"type": "array", "items": _PARA_SCHEMA},
            },
            "required": ["what_the_documents_say", "questions", "not_determined"],
            "additionalProperties": False,
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}

SECTION_TITLES = {
    "what_the_documents_say": "What the documents say",
    "questions": "The questions the documents raise, and who could answer them",
    "not_determined": "What could not be determined",
}


def render_facts(panel: dict) -> str:
    """The structured facts, as text the model can quote from."""
    out = [f"Site: {panel['name']} ({panel['site_key']})", ""]
    out.append("Applications:")
    for a in panel["applications"]:
        out.append(f"  - {a['ref']} ({a['council']}; status: {a['status'] or 'unknown'}; "
                   f"received {a['received'] or '?'}; decided {a['decided'] or '—'})")
        if a["description"]:
            out.append(f"    description: {a['description']}")
    out.append("")
    out.append("Power figures adjudicated as this site's own (each with its quote):")
    if not panel["adjudicated_figures"]:
        out.append("  (none — no figure in the documents has been adjudicated "
                   "as this site's capacity)")
    for f in panel["adjudicated_figures"]:
        out.append(f"  - {f['quantity']}: {f['value_mw']:g} MW"
                   f"{' (stated as a maximum)' if f['is_maximum'] else ''}"
                   f" — application {f['application_ref']}, document {f['document_id']}"
                   f"{', page ' + str(f['page']) if f['page'] else ''}"
                   f"; label {f['label']}")
        out.append(f"    quote: \"{' '.join(f['quote'].split())}\"")
    out.append("")
    out.append("Figures published outside the planning system and matched to this site:")
    if not panel["external_claims"]:
        out.append("  (none)")
    for c in panel["external_claims"]:
        mw = f"{c['value_mw']:g} MW" if c["value_mw"] is not None else "no figure"
        out.append(f"  - {c['claim']}: {mw}, {c['quantity']}, published by "
                   f"{c['published_by']} as \"{c['published_as']}\" ({c['source']}); "
                   f"match {c['match_confidence']} by {c['match_method']}: "
                   f"{c['match_evidence']}")
    out.append("")
    cov = panel.get("coverage") or {}
    if cov:
        out.append(f"Coverage: {cov.get('prose_read', 0)} of {cov.get('prose_held', 0)} "
                   f"prose documents analysed; {cov.get('graphical', 0)} drawings "
                   f"not read by design; {cov.get('sampled_read', 0)} of "
                   f"{cov.get('sampled_held', 0)} repetitive documents sampled.")
    else:
        out.append("Coverage: no documents held.")
    g = panel["generation"]
    out.append(f"Generation profile: figure basis '{g['figure_basis'] or 'none'}'"
               f"{'; ' + g['figure_note'] if g['figure_note'] else ''}; "
               f"generator count {g['generator_count'] or 'not disclosed'}; "
               f"fuel {g['generator_fuel'] or 'not named'}.")
    p = panel["parties"]
    out.append(f"Parties: end user {p['end_user'] or '—'}; applicant of record "
               f"{p['applicant_of_record'] or '—'}; confirmed group "
               f"{p['operator_group'] or '—'}; advisers {p['advisers'] or '—'}; "
               f"also named in documents {p['named_in_documents'] or '—'}; "
               f"planning authority {p['authority'] or '—'} (source: {p['parties_source']}).")
    if panel["cohorts"]:
        out.append("Cohorts this site falls into (rules over the adjudicated figures):")
        for m in panel["cohorts"]:
            out.append(f"  - {m['cohort']}: {m['definition']} Figures used: "
                       + "; ".join(f"{a}={b}" for a, b in m["evidence"].items()))
    return "\n".join(out)


def render_pages(pages: list[Page]) -> str:
    if not pages:
        return "(no document pages: this site holds no readable prose documents)"
    out = []
    for p in pages:
        out.append(f"=== document {p.document_id} | {p.application_ref} | "
                   f"{p.kind or 'untitled'} | page {p.page} ===")
        out.append(p.text)
        out.append("")
    return "\n".join(out)


def render_prompt(inp: SiteInput) -> str:
    return PROMPT % {"facts": render_facts(inp.panel),
                     "pages": render_pages(inp.pages)}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def _verify_helpers():
    spec = importlib.util.spec_from_file_location(
        "verify_findings", ROOT / "scripts" / "verify_findings.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_findings"] = mod  # dataclasses looks itself up here
    spec.loader.exec_module(mod)
    return mod


_VF = None


# Punctuation that may differ between a model's copy and the page: the
# marks between words, and a full stop that is not a decimal point.
_PUNCT_RE = re.compile(r"[,;:()\[\]\"'’‘“”]|(?<!\d)\.(?!\d)")


def quote_in_text(quote: str, text: str) -> bool:
    """The findings gate's fragment match: normalised, ellipsis-aware.

    With one relaxation the findings gate does not have. Watford's 1.1
    reading was refused for "Affinity Water is still to confirm the
    amount of water" against a page that reads "Affinity Water, is still
    to confirm" — a dropped comma. Every word and every figure must
    still match, in order; punctuation between them need not. A quote
    that verifies only this way is still a verbatim run of the words on
    the page, and it is the words and the figures that a reader checks.
    """
    global _VF
    if _VF is None:
        _VF = _verify_helpers()
    frags = [_VF._normalise(f) for f in _VF._quote_fragments(quote)]
    if not frags:
        return False
    page = _VF._normalise(text)
    if _VF._all_fragments_in_order(page, frags):
        return True
    strip = lambda t: " ".join(_PUNCT_RE.sub(" ", t).split())
    if _VF._all_fragments_in_order(strip(page), [strip(f) for f in frags]):
        return True
    # The page's own spaces are not evidence: "buildi ng" is "building".
    #
    # Routed through `verify_findings.fragments_present` since 2026-08-31,
    # which applies the same relaxation behind a 25-character minimum. It
    # was unguarded here and absent from the findings gate, so a very
    # short quote could verify against almost any page. Taking the guard
    # tightens this gate and therefore needs GATE_VERSION to move, which
    # marks every site for a re-read — done here because the move to
    # gpt-5.6-terra re-reads them all anyway, which is the accumulation
    # rule in ROADMAP working as intended: park a change that cannot
    # justify a re-read on its own, then land it with one that can.
    return _VF.fragments_present(strip(page), [strip(f) for f in frags])


# A number with a unit, as the rules define it. Thousands separators and
# decimals are part of the number; the unit may be glued on ("168MW").
FIGURE_RE = re.compile(
    r"(?<![\w.])(£?\d[\d,]*(?:\.\d+)?)[\s-]*"
    r"(?:(?:MWe?|MVA|MWth?|kWe?|kVA|GWe?|MWh|kWh|GWh|m2|m²|sqm|sq\s*m|"
    r"square metres?|hectares?|ha|%)\b"
    # A count of plant, with one adjective allowed between the number and
    # the noun: "112 standby generators", "20 gas engines".
    r"|(?:[A-Za-z-]+\s+)?(?:generators?|engines?|units?)\b)",
    re.IGNORECASE)

FORBIDDEN = (
    # cross-site comparison and ranking. "largest" is not here: "the
    # largest figure in the file" is a statement about this site's
    # documents, and the rule is about other sites.
    r"\bother (data centre )?sites?\b", r"\bmost data cent(re|er)s\b",
    r"\bcompared (to|with) other\b", r"\branks?\b", r"\bamong the (largest|biggest|smallest)\b",
    r"\b(one of the|the) (largest|biggest|smallest)( \w+)? (in|of) (the|its)\b",
    r"\b(typical|unusual|unusually) (for|of) (a|the) (data centre|scheme|site)",
    r"\breally\b", r"\bsecretly\b",
    # advice, by its phrases. A question may say "which figure should
    # govern"; a reading may not say what anyone should do about it.
    r"\b(reporters?|journalists?|readers?|you) (should|could|might|need)\b",
    r"\bworth (investigating|asking|looking|pursuing|checking)\b", r"\bred flag\b",
    r"\bthe story\b", r"\breporters?\b", r"\bjournalists?\b", r"\bwe recommend\b",
)
# Asserting intent is forbidden; asking about it is what the questions
# section is FOR. These apply everywhere except that section.
FORBIDDEN_ASSERTIONS = (
    r"\bintends?\b", r"\bintention\b", r"\bwants?\b", r"\bplans? to\b",
)
_FORBIDDEN_RES = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN)
_ASSERTION_RES = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN_ASSERTIONS)


def _flow_text(pages: list[str]) -> str:
    """A document's pages as one text, running headers stripped.

    A line that appears, normalised, on at least three pages and at
    least half of them is furniture — "REF LON02A-… Date of issue" — and
    a sentence that crosses a page break has it sitting in the middle.
    Deterministic, and applied only here at match time: the cache is
    never rewritten.
    """
    from collections import Counter
    seen = Counter()
    for page in pages:
        for line in {" ".join(ln.split()).lower() for ln in page.splitlines() if ln.strip()}:
            seen[line] += 1
    floor = max(3, (sum(1 for p in pages if p.strip()) + 1) // 2)
    headers = {ln for ln, n in seen.items() if n >= floor}
    kept = []
    for page in pages:
        kept.append("\n".join(ln for ln in page.splitlines()
                               if " ".join(ln.split()).lower() not in headers))
    return "\n".join(kept)


def _num_key(s: str) -> str:
    return s.replace("£", "").replace(",", "").strip()


@dataclass(frozen=True)
class GateResult:
    ok: bool                      # at least one paragraph stands
    reason: str = ""              # set only when the whole reading is refused
    figures_checked: int = 0
    quotes_checked: int = 0
    paragraphs_passed: int = 0
    paragraphs_withheld: int = 0


def _paragraph_problem(sec: str, para: dict, inp: SiteInput, flows: dict,
                       panel_quotes: set, facts_text: str) -> str | None:
    """Why this paragraph may not render, or None. Marks nothing itself."""
    text = para.get("text") or ""
    rules = _FORBIDDEN_RES if sec == "questions" else _FORBIDDEN_RES + _ASSERTION_RES
    for rx in rules:
        m = rx.search(text)
        if m:
            return f"uses '{m.group(0)}', which the rules forbid"
    others = {k for k in re.findall(r"\b(?:SITE-|PTNO-)[A-Za-z0-9/]+", text)
              if k != inp.site_key}
    if others:
        return f"names another site ({min(others)})"

    def flow(doc_id):
        if doc_id not in flows:
            flows[doc_id] = _flow_text(inp.cache[doc_id])
        return flows[doc_id]

    verified: list[str] = []
    for q in para.get("quotes") or []:
        quote = (q.get("quote") or "").strip()
        if not quote:
            continue
        doc_id, page = q.get("document_id"), q.get("page")
        ok = False
        if doc_id and doc_id in inp.cache:
            pages = inp.cache[doc_id]
            order = ([page - 1, page - 2, page] if page else []) + \
                    list(range(len(pages)))
            ok = any(0 <= p < len(pages) and quote_in_text(quote, pages[p])
                     for p in order)
            # A sentence that crosses a page break has the document's
            # running header sitting in the middle of it; match against
            # the joined, header-stripped flow before giving up.
            ok = ok or quote_in_text(quote, flow(doc_id))
        if not ok and (q.get("application_ref") or not doc_id):
            ok = (" ".join(quote.split()) in panel_quotes
                  or quote_in_text(quote, facts_text))
        if not ok:
            # A real quote under the wrong citation is still a verbatim
            # run of the site's own documents. Search every cached
            # document; where it is found, the citation is corrected IN
            # the reading and the correction recorded beside it, so the
            # panel links the document the words are actually in and
            # the model's error stays visible.
            for other_id, pages in inp.cache.items():
                if other_id == doc_id:
                    continue
                for pno, ptext in enumerate(pages, 1):
                    if quote_in_text(quote, ptext):
                        q["cited_document_id"] = doc_id
                        q["document_id"], q["page"] = other_id, pno
                        ok = True
                        break
                if not ok and quote_in_text(quote, flow(other_id)):
                    q["cited_document_id"] = doc_id
                    q["document_id"], q["page"] = other_id, None
                    ok = True
                if ok:
                    break
        if not ok:
            return (f"quote not found in document {doc_id or '—'} or any "
                    f"other the site holds: \"{quote[:80]}\"")
        verified.append(quote)
    joined = " ".join(verified)
    for m in FIGURE_RE.finditer(text):
        n = _num_key(m.group(1))
        if not re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])",
                         joined.replace(",", "")):
            return f"the figure '{m.group(0)}' is not in any quote attached to it"
    return None


# What a refusal may say on a page, as opposed to what it records.
#
# Luke, 2026-08-24, on the withheld line: the reason the gate writes
# names the model's own words, and for the commonest failure — a quote
# that is in none of the site's documents — those words are a misquote
# or an invention. One of the eight withheld paragraphs in the sample
# put "29.9 L/s" in front of a reporter inside the sentence explaining
# that it could not be verified, and two more printed "3.3 MWt" while
# saying no quote contains it. The gate's own rule is that every
# number-with-unit must appear in a verified quote; the refusal message
# was the one place that rule did not hold.
#
# So the stored reason keeps everything — it is the audit trail, and the
# sample markdown a person checks against still shows it in full — and
# the reader is given the failure and the document, never the words.
_QUOTE_NOT_FOUND = re.compile(
    r'^quote not found in document (.+?) or any other the site holds: ".*"$',
    re.S)
_FIGURE_UNQUOTED = re.compile(r"^the figure '.*' is not in any quote "
                              r"attached to it$", re.S)


def public_reason(reason: str) -> str:
    """The refusal, with the model's unverified words taken out.

    Every branch names what went wrong and where to look. What none of
    them do is repeat a quote that verified against nothing, or a figure
    no quote contains — a reader scanning the page takes away a number,
    not a caveat.
    """
    reason = (reason or "").strip()
    m = _QUOTE_NOT_FOUND.match(reason)
    if m:
        doc = m.group(1)
        where = (f"document {doc}" if doc != "—" else "the document it cites")
        return (f"it rests on a quote that is not in {where}, nor in any "
                f"other document this site holds")
    if _FIGURE_UNQUOTED.match(reason):
        return "it states a figure that none of its own quotes contains"
    # 'uses X, which the rules forbid' and 'names another site (KEY)' say
    # nothing the documents did not; they stand as written.
    return reason


def gate(reading: dict, inp: SiteInput) -> GateResult:
    """Judge each paragraph alone; refuse the reading only when nothing stands.

    A paragraph that fails gains `withheld: <reason>` in the reading
    itself — beside the model's words, the way a corrected citation is
    recorded — and the renderer shows the reason where the paragraph
    would have stood. A paragraph that passes contributes its counts.
    """
    sections = (reading or {}).get("sections") or {}
    figures_checked = quotes_checked = passed = withheld = 0
    panel_quotes = {" ".join(f["quote"].split()) for f in inp.panel["adjudicated_figures"]}
    facts_text = render_facts(inp.panel)
    flows: dict[int, str] = {}
    first_reason = ""
    for sec, paras in sections.items():
        for i, para in enumerate(paras or []):
            problem = _paragraph_problem(sec, para, inp, flows,
                                         panel_quotes, facts_text)
            if problem:
                para["withheld"] = problem
                withheld += 1
                first_reason = first_reason or f"{sec} paragraph {i + 1}: {problem}"
            else:
                para.pop("withheld", None)
                passed += 1
                quotes_checked += sum(1 for q in para.get("quotes") or []
                                      if (q.get("quote") or "").strip())
                figures_checked += sum(1 for _ in FIGURE_RE.finditer(
                    para.get("text") or ""))
    if passed == 0:
        reason = ("the reading is empty" if withheld == 0 else
                  f"all {withheld} paragraphs withheld — first: {first_reason}")
        return GateResult(False, reason, 0, 0, 0, withheld)
    return GateResult(True, "", figures_checked, quotes_checked, passed, withheld)


# ---------------------------------------------------------------------------
# Storage helpers shared by the route and the build
# ---------------------------------------------------------------------------

# The latest judgement of each site, whatever version made it — not the
# latest that passed. A site read again under a newer prompt and refused
# by the gate must show as withheld, not fall back to the reading the
# newer one replaced: the earlier reading passed an earlier gate, and
# rendering it would mean a refusal quietly restored the thing it
# refused. Measured when this was the other way round: 18 sites
# rendered where 15 had passed.
LATEST_SQL = """
SELECT DISTINCT ON (site_key) site_key, model, prompt_version, reading,
       documents_read, pages_read, inserted_at, gate_version, withheld_reason
FROM site_machine_readings
ORDER BY site_key, inserted_at DESC, id DESC
"""

# The model tag a freshness marker is written under. Not a model at all:
# it keeps the marker out of the unique key a real reading occupies
# (site_key, model, prompt_version, input_hash, gate_version), so
# marking a site stale can never block the genuine reading of that same
# input from being stored later.
FRESHNESS_MODEL = "freshness-check"

RETIRED_REASON = (
    "the site record this reading was written for has since been merged "
    "into another or retired")

STALE_REASON = (
    "the site's documents or established facts have changed since this "
    "reading was written")

LIVE_KEYS_SQL = "SELECT site_key FROM sites WHERE retired_at IS NULL"


def load_latest(conn, *, live_only: bool = True
                ) -> tuple[dict[str, dict], dict[str, str]]:
    """(readings that passed, reasons for those that did not).

    One query, split here: both halves are the same "latest row per
    site", so a site cannot appear in both.

    `live_only` drops readings whose site no longer exists. A site key
    is retired when its cluster merges into another — three did on
    2026-08-27 — and the reading written for it describes a record that
    is gone. This is the only freshness check cheap enough to run on
    every build: rebuilding one site's input to re-hash it costs ~8s,
    so verifying the corpus's 258 readings would add 35 minutes to a
    build. The rest of the check therefore runs offline and records its
    verdict, in `scripts/verify_reading_freshness.py`.
    """
    passed: dict[str, dict] = {}
    withheld: dict[str, str] = {}
    live: set[str] | None = None
    if live_only:
        with conn.cursor() as cur:
            cur.execute(LIVE_KEYS_SQL)
            live = {r[0] for r in cur.fetchall()}
    with conn.cursor() as cur:
        cur.execute(LATEST_SQL)
        for key, model, pv, reading, nd, npg, at, gv, why in cur.fetchall():
            if live is not None and key not in live:
                # Not surfaced as a withheld reason: there is no site
                # page left to carry one, and a reason attached to a
                # dissolved key would be a row a reporter cannot reach.
                continue
            if why:
                withheld[key] = why
            elif reading:
                passed[key] = {"model": model, "prompt_version": pv,
                               "reading": reading, "documents_read": nd,
                               "pages_read": npg, "inserted_at": at,
                               "gate_version": gv}
    return passed, withheld


FIGURE_SOURCES_SQL = """
WITH adj AS (
  SELECT DISTINCT ON (finding_id) finding_id, verdict, application_id
  FROM power_adjudication
  ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC, id DESC)
SELECT s.site_key, f.evidence_text, f.document_id, f.evidence_page
FROM adj
JOIN findings f ON f.id = adj.finding_id
JOIN site_members sm ON sm.application_id = adj.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL AND adj.verdict = 'site_capacity'
  AND f.document_id IS NOT NULL AND f.evidence_text IS NOT NULL
"""


def figure_sources(conn) -> dict[str, dict[str, tuple[int, int | None]]]:
    """site_key -> normalised figure quote -> (document_id, page).

    The prompt tells the model to cite the application reference, not a
    document, for a quote it copied from the structured facts — and the
    gate verifies those against `panel_quotes` and stops, so nothing
    ever puts a document back. The reader then renders 212 of the
    corpus's 11,244 quotes as unlinked text, concentrated on the sites
    whose evidence is richest in adjudicated figures: 23 of South
    Mimms's 33.

    The document is not inferred from the words. An adjudicated figure
    *is* a finding, the quote *is* that finding's `evidence_text`, and
    the finding already carries the document it was read from — so this
    identifies which figure the model copied and follows provenance
    that was established when the finding was gated. The same exact
    normalised equality the gate used to verify the quote is the test
    used here.

    **A quote whose text is the evidence of findings on more than one
    document is dropped, not guessed.** Sixteen are, and picking either
    document would assert a source over an equally good one — the
    failure principle 7 exists to prevent. They keep the citation they
    have.
    """
    by_site: dict[str, dict[str, set[tuple[int, int | None]]]] = {}
    with conn.cursor() as cur:
        cur.execute(FIGURE_SOURCES_SQL)
        for site_key, ev, doc_id, page in cur.fetchall():
            key = " ".join((ev or "").split())
            if key:
                by_site.setdefault(site_key, {}).setdefault(key, set()).add(
                    (int(doc_id), page))
    out: dict[str, dict[str, tuple[int, int | None]]] = {}
    for site_key, quotes in by_site.items():
        resolved = {}
        for quote, hits in quotes.items():
            if len({d for d, _ in hits}) == 1:
                resolved[quote] = sorted(hits, key=lambda h: (h[1] is None, h[1]))[0]
        out[site_key] = resolved
    return out


CITED_DOCS_SQL = """
SELECT d.id, d.url, coalesce(d.kind, ''), a.application_ref
FROM documents d JOIN applications a ON a.id = d.application_id
WHERE d.id = ANY(%s)
"""


def cited_documents_by_id(conn, ids) -> dict[int, dict]:
    """The same shape as `cited_documents`, for documents named by id.

    A quote resolved through `figure_sources` points at a document no
    reading cited by id, so it is absent from `cited_documents` and the
    panel would fall back to unlinked text having just found the link.
    """
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    out: dict[int, dict] = {}
    with conn.cursor() as cur:
        cur.execute(CITED_DOCS_SQL, (ids,))
        for doc_id, url, kind, ref in cur.fetchall():
            out[doc_id] = {"url": url or "", "title": document_title(url, kind),
                           "application_ref": ref}
    return out


def document_title(url: str, kind: str) -> str:
    """A readable name for a cited document, from its register filename.

    Council registers file nearly everything as "Supporting Documents";
    the filename in the URL is where the title is — ENERGY___SUSTAINABILITY
    _STATEMENT_HFP-BWE-XX-XX-RP-Z-000001_P02-1976228.pdf. Tidied, not
    interpreted: underscores to spaces, the extension and the register's
    trailing id dropped, and the kind kept as the fallback.
    """
    from urllib.parse import parse_qs, unquote_plus, urlparse
    # The filename is not always the last path segment. Ocella portals
    # (Hillingdon among them) carry it in a query parameter, with
    # backslash-separated folders inside the value:
    #   viewDocument?file=dv_pl_files%5C75111_APP_2025_739%5C<name>.pdf&module=pl
    # rsplit("/") on that returns the whole query string, which rendered
    # 90 characters of raw URL as a document title in the reading panel
    # (Luke, 2026-08-28). Parse the URL, prefer a file-ish parameter,
    # and take the basename across both slash directions; unquote_plus
    # because query values encode spaces as +.
    parts = urlparse(url or "")
    candidate = parts.path.rsplit("/", 1)[-1]
    if parts.query:
        qs = parse_qs(parts.query)
        for k in ("file", "filename", "document", "doc"):
            if qs.get(k) and qs[k][0]:
                candidate = qs[k][0]
                break
    name = re.split(r"[\\/]", unquote_plus(candidate))[-1]
    name = re.sub(r"\.(pdf|docx?|msg|rtf)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"-\d{6,}$", "", name)              # the register's id
    name = re.sub(r"^[A-Z0-9]+_[A-Z0-9]+_[A-Z]+-", "", name)   # 25_1781_FUL-
    name = re.sub(r"_+", " ", name).strip()
    # A name that still reads as plumbing is worse than the kind: a
    # label with query syntax in it looks like a path-keyed link and
    # sends a reader hunting for a bug that is not there.
    if len(name) < 4 or "?" in name or "=" in name:
        return kind or "document"
    return name[:90]


def cited_documents(conn, readings: dict[str, dict]) -> dict[int, dict]:
    """document_id -> {url, title, application_ref} for every document a
    reading cites, so the panel can link a quote to the file it is from."""
    ids: set[int] = set()
    for r in readings.values():
        for paras in ((r.get("reading") or {}).get("sections") or {}).values():
            for para in paras or []:
                for q in para.get("quotes") or []:
                    if q.get("document_id"):
                        ids.add(int(q["document_id"]))
    if not ids:
        return {}
    out: dict[int, dict] = {}
    with conn.cursor() as cur:
        cur.execute(CITED_DOCS_SQL, (sorted(ids),))
        for doc_id, url, kind, ref in cur.fetchall():
            out[doc_id] = {"url": url or "", "title": document_title(url, kind),
                           "application_ref": ref}
    return out
