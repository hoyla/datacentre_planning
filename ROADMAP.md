# Roadmap

What is still to do. Everything already built and decided — including
the approaches tried and rejected, which are worth knowing before
re-proposing them — is in [HISTORY.md](HISTORY.md).

Current state: **429 sites** (plus 26 pre-planning), **1,709
applications** in the site universe, **55,678 documents**. Findings and
adjudication counts move while the corroboration pass runs and are
deliberately not restated here — `scripts/corpus_stats.py` prints them,
and each release states the boundary it was stamped at.

**Reading is complete for phase 2.1**, stamped 2026-08-11 with the
Studio reader stopped so the boundary is clean: 37,992 of 38,005 prose
documents read. Two other numbers belong beside that one and are stated
in the reader rather than folded into it — 4,204 documents in the
repetitive classes are sampled out at one in five by policy, not
backlog, and 231 are held but contain no words at all, confirmed blank
by two independent OCR engines. Every capacity figure that existed at
the boundary is adjudicated.

---

## Regenerating a release

The chain, its ordering constraints and the traps are in
[docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md). Two steps
must precede the artefacts: adjudication corrections (enforced in code
by `dcp/adjudication_gate.py`) and the Drive staging rebuild that picks
up the new CSV adjudication columns.

## Phase 2 — the tail of the collecting

- **The acquisition tail.** 108 applications are being worked now. Of
  those recorded unreadable, a host-by-host probe found **20 reachable
  without a browser, across eleven unrelated bespoke portals** — roughly
  one adapter per two applications, which is poor value. The larger and
  cheaper bloc is **31 that route through the browser**, using tooling
  that already works: 15 behind AWS WAF (the Coventry signature), 8 on
  LPAssure serving `UnsupportedWebBrowser`, 8 Salesforce needing a
  harvested document listing. Needs a human at the keyboard.
  Genuinely hard: 5 behind CAPTCHA, 7 refusing with 403/500/503
  regardless of user-agent, 1 Incapsula.
- **Re-list the corpus to find historical partial fetches.** A short
  fetch used to be recorded as complete. New ones are caught, but past
  ones are not measurable from the manifests, which record what was
  stored and not what was offered. Re-listing the document pages of the
  applications that hold documents would settle it. **Do this before
  anyone quotes per-site document counts.**

## Phase 3 — the second opinion

- **Second-model comparison across the corpus.** A subset is dual-read
  already. Where two models disagree, both readings are kept and the
  disagreement is the finding; the comparison is the deliverable.
- **Water adjudication**, once reading is complete — whether the sites
  disclosing consumption support anything firmer than the cooling method
  reported today. **119 sites as at the 2.1 boundary**, and the number
  has moved twice: HISTORY records 93 at phase 1 and the data dictionary
  said 76 through phase 2, both measured before the reading that
  followed them. Three hardcoded figures for one quantity, drifting
  apart — measure it at the time rather than quoting any of them, and
  see the note below about making it computed.

## Coverage gaps worth closing

Prompted by the **Devon Data Campus** (Xlinks, North Devon), a scheme
with an active public campaign of which the corpus holds *nothing*: zero
matches for Xlinks, Valeon, Alverdiscott or Devon Data Campus. Three
gaps, in rising order of effort:

1. **Operator watch-list sweep** (cheap). Add Xlinks and Valeon, review
   the list generally, run a name-based PlanIt sweep. Catches an
   application when it is validated rather than when we next look.
2. **Pre-application and screening entries.** Councils publish EIA
   screening and scoping requests, and Scottish PANs, *before* any
   application exists. Our universe starts at submission, so this class
   is structurally invisible. Decide whether pre-planning entries become
   first-class universe members or a separate watch table.
3. **Section 35 Directions / NSIP discovery.** The energy layer is
   ingested, but a data centre attaching itself to an NSIP power project
   is still invisible on both sides of the join. Xlinks'
   Morocco–UK interconnector lands at Alverdiscott, which is plausibly
   *why* a data campus is proposed there. An NSIP spans hundreds of
   kilometres and many authorities, which the 1 km clustering rule
   handles badly — it wants its own node type and evidence-based rather
   than proximity-based association.

`adjacent_power` holds only ~15 applications universe-wide, which is
implausibly few and consistent with power schemes near campuses being
absent from the corpus rather than misclassified.

4. **Generator capacity that accretes through follow-on applications.**
   Found while cross-checking the Capacity Market sites against planning
   records — see §5 of
   [docs/EXTERNAL_DATA_SOURCES.md](docs/EXTERNAL_DATA_SOURCES.md). At 672
   Galvin Road, Slough, four generators arrived in 2023 on their own minor
   consent, years after the data centre permission; at Hemel Hempstead a
   2003 application is simply "Construction of single storey building to
   house generator". None states a figure in MW. This is the Yorkshire
   Energy Park pattern at building scale, and it means a sweep anchored on
   the main consent **systematically undercounts installed generation**.
   The fix is to link follow-on applications back to their parent site,
   which the co-location sweep should do anyway. Two naming-invisibility
   cases turned up in the same search — a data centre consented under use
   class B8, and one as "fibre exchange (Sui Generis)" — which belong with
   the existing invisibility-flag work.

**Northern Ireland is a coverage gap, not just a missing adapter.** PlanIt
does not cover NI at all, so the only NI applications we hold arrived by
other routes — seven, from Derry & Strabane and Causeway Coast & Glens.
They sit on `planningregister.planningsystemni.gov.uk`, which is a
Next.js application: the page carries only an id and the documents come
from an API call made in the browser. Finding that endpoint needs a
session with the network tab open, after which an adapter is
straightforward. Worth doing — it is the whole of NI, not seven
applications.

**Read the 58 Section 106 agreements the tiering used to skip.** The
classification is fixed — `LEGAL_INSTRUMENT_KINDS` is now tested before
the drawing rule, so a statutory instrument is never a drawing whatever
its title says, and `tests/test_tier_ordering.py` asserts every phrase
`TIER_A_KINDS` names can actually be reached. What is *not* done is the
consequence.

Those 58 documents are now classified as prose and are unread, which is
the honest position rather than the previous one where they counted as
drawings. Coverage moves from 36,744 of 36,983 (99.35%) to 36,744 of
37,041 (99.2%). **They want reading and the artefacts regenerating
before the coverage figure is quoted again** — phase 2.1 shipped before
this and is accurate to its own definition; this changes the definition.

They are worth the read rather than a reclassification for tidiness:
s106 agreements are where planning obligations, community payments and
infrastructure commitments are written down, which is investigative
material. 438 MB of it, and the same rule would have dropped them from
the Pinpoint collection too.

**A zero-byte document is held, counted and read as though it were a
document.** Three exist in the corpus, found while building the Pinpoint
bundle because an empty file is conspicuous in an export and invisible
everywhere else:

| document | application | site |
|---|---|---|
| `005 - Section 106 Agreement.pdf` | Wakefield 23/00100/S7301 | Ferrybridge C |
| `011 - Consultation Response.pdf` | Warwick W/23/1025 | Warwick Hospital |
| `018 - Supporting Documents.pdf` | Medway MC/21/0979 | Kingsnorth |

**They cannot be re-fetched, and the fault is not ours.** With a session
cookie and referer all three return HTTP 200, `Content-Type:
application/pdf`, and a body of zero bytes, from the councils' own
servers. Without the cookie Idox answers 404, which is what made this
look at first like a stale-URL problem; it is not. The Wakefield s106 is
still listed on the documents tab, dated 09 Jan 2025, at exactly the URL
we hold. Luke confirmed the same result in a browser. The original fetch
was correct and faithfully stored what the portal served.

The defect is that nothing notices. An empty file passes the fetcher,
lands in the canonical store, is hard-linked into staging, is counted in
the corpus totals, and reaches the deep read as a document held and
readable — where it yields nothing, indistinguishably from a document
that genuinely says nothing. Two of these three are consultee responses
and one is an s106; on kind alone they are exactly the material the
investigation is looking for, so "we hold it and it was silent" is the
worst available failure mode.

Three pieces of work, smallest first:

1. **Guard at fetch.** A zero-length body is a failed fetch, not a
   document: record the failure against the application and leave no
   file, so a re-run retries rather than treating emptiness as done.
2. **Sweep the corpus.** `find -size -1c` over the canonical store is the
   whole check. Three today; nothing would flag a fourth.
3. **Say so in the artefacts.** Where a document is held but empty, the
   site report and the coverage detail should show it as unavailable
   from the source rather than as read — the same honesty the coverage
   split already applies to drawings and sampled objection letters.

Worth raising with the three councils as well: a listed document that
downloads as nothing is a public-access failure independent of this
investigation.

## Smaller things

- **Re-measure the 1.71 kW/m² floor-area factor.** It drives the
  published power estimate for every site with no disclosed capacity. An
  ad-hoc query on 2026-08-11 suggested it may have moved — 88 sites now
  disclose both a capacity and a floorspace figure, against the 53 it was
  calibrated on — but with different signal matching from the original,
  so this is a flag and nothing more. Reproduce the original criteria
  from git history first, then re-run, then decide.
- **Make the data dictionary's corpus statistics computed.** The count of
  sites disclosing water consumption exists as three hardcoded figures
  written at three moments — HISTORY 93, the dictionary 76, live 119 —
  and only the last is true. One function taking a connection, called by
  both exporters, kills the class. Until then, measure before quoting any
  dictionary statistic.

- **Promote `associated_id` to a typed `applications.parent_ref`
  column.** Parent-backfill confirmed the field is reliable; a typed
  column makes family navigation a join rather than JSONB extraction.
- **`deepread_log.pages_sent` counts a page once per chunk, not once.** A
  page split across chunks is recorded once per chunk it appears in, so
  the array is a send log rather than a set of pages: document 52945 has
  148 entries for 32 distinct pages, and 21 rows currently hold more
  entries than `pages_total`. Nothing divides by it today — the runners
  only write it, and the log line's `[148/32 pages]` is the sole visible
  symptom — so this is latent rather than wrong. It becomes wrong the
  moment any coverage figure is computed from `array_length`, which is
  the obvious way to use the column. Either store distinct pages or make
  the ambiguity impossible to misread; do it before a consumer needs it,
  not after one has published from it.
- **Improve the automated test surface.** The suite is good at internal
  consistency and blind to two things, and almost every defect found on
  2026-08-11 sat in one of the gaps. Worth doing properly rather than
  adding a test per bug — the recurring shape of these is *fixed the
  symptom, missed the cause*.

  **Nothing drives the built artefact.** The reader's card links did
  nothing in a shipped release; a chip took its own flex column and
  squashed the map into a third of the width; an energy checkbox went
  dead inside a projection. All three were invisible in review and
  obvious within seconds of opening the page. A build-and-drive smoke
  test — generate the reader, load it headless, click the things a
  reporter clicks, assert what they do — would have caught every one.
  It would also have caught the two prose definitions on one page, which
  survived a full test run and was found by reading the output.

  **Nothing asserts that a stated number matches the data it describes.**
  The count of sites disclosing water consumption existed as three
  hardcoded figures written at three moments — 93, 76 and 119 — and
  every one passed. Same for the findings-inflation percentage. A test
  that recomputes each statistic the dictionary quotes and compares it
  to the string would make that class impossible; making them computed
  (above) is the better fix, and the test is what stops the next one
  being hardcoded.

  **The pattern to copy** is `tests/test_release_defaults.py`: it asserts
  a *rule* over the whole tree — no default may name a release — rather
  than one instance, and it was verified by reintroducing the bug and
  watching it fail. `tests/test_adjudication_gate.py` is the
  counter-example worth understanding: it asserts the corrector and the
  gate agree, and nothing asserts either is right, which is how the
  thermal-output hole survived.

- **CI on GitHub Actions.** `pytest -m "not integration"` on every push,
  plus `node --test` for the edge middleware. Feasible now the repo is
  public and Apache 2.0. Pairs with the item above: the tests only stop
  a regression if something runs them.
- **Four sites report a total site demand below their IT load.** All four
  are correct — the figures come from different applications at
  multi-building sites, and each figure names its source application in
  the reader. Worth adjudicating by hand rather than changing the
  rollup rule.

---

## Parked

Deferred consciously. Return when journalism need warrants.

### Queued behind the consumption-context line

- **LA-level consumption choropleth on the reader map ("plan 2",
  agreed 2026-08-12).** A toggleable layer shading each local authority
  by the change in its large-user (half-hourly non-domestic) electricity
  consumption 2019→2024, with the sites drawn on top. The signal is
  strong and already measured: against a national fall of 9%, Slough is
  +60% and Hillingdon +36% — the two largest absolute risers in Great
  Britain — while the null cases render too (Docklands −15%, Hertsmere
  flat despite 260 MVA committed in UKPN's queue), which is pipeline
  versus consumption on one map. Ships only after
  [docs/PLAN_CONSUMPTION_CONTEXT.md](docs/PLAN_CONSUMPTION_CONTEXT.md)
  ("plan 1"): the per-site sentence proves the numbers, the
  council→authority mapping and the caveat language before anything is
  painted. Constraints decided up front: local-authority granularity is
  forced, not chosen — DESNZ publishes half-hourly consumption only as
  LA rollups and the per-MSOA rows exclude it entirely; the layer
  describes the authority's consumption, never the site's; the series
  ends 2024 and says so; simplified LA boundary geometry must fit the
  single-file reader's payload budget. The data is already committed in
  `data/external_sources/` (provenance in its README).

### Postponed past the phase 2 and 2.1 releases

None is abandoned; each is a known, scoped piece of work.

- **The acquisition tail.** 31 browser-routed applications, 20 across
  bespoke portals, 13 genuinely hard — a slow process needing a human at
  the keyboard, and not worth holding the release for.
- **Scanned-page orientation detection — closed on evidence, not done.**
  The theory was that councils scan sideways and `--psm 3` misses it. The
  231 documents that OCR'd to nothing were the obvious test cohort, and
  Apple Vision — which detects orientation itself — read them as blank
  too. They are photographs and line drawings with no text in them, so
  there is nothing for a better OCR pass to find. Reopen only with a
  document that demonstrably has readable text nobody is reading.
- **Coverage gaps** — Northern Ireland (whole nation, one adapter),
  pre-application/screening entries, Section 35 / NSIP, the operator
  watch-list.
- **Phase 3, the second opinion.** `scripts/compare_readers.py` exists
  and the Studio has been building the dual-read tier-A corpus; it was
  stopped for the 2.1 boundary and needs restarting. The corpus-wide
  comparison and water adjudication are the next release's deliverable.

### Longer-standing

- **DC01, the unidentified Foxglove case.** A 320 MW outline approved
  2025-02 with implausibly low emissions and no council, developer or
  address. Three of four originally-unidentified cases are resolved;
  this is the fourth. Most likely falls out of an operator-name sweep
  for hyperscaler-affiliated SPVs.
- **Document corpus mirror.** `data/raw/` is local-only and growing.
  Zenodo (DOI, CC-BY) is the leading candidate for a reproducibility
  mirror. Decide once the corpus stops moving.
- **`other_fields` normalisation.** PlanIt carries applicant and agent
  fields inside `raw_metadata`; promote to columns if a bigger
  operator-name sweep happens.
- **Pre-2018 broader-keyword backfill.** PlanIt thins sharply before
  2018. Parent-backfill already pulled in substantive pre-2018 parents; a
  separate sweep would catch cases with no child in our window.
- **Environment Agency permits — the tail, not the source.** The
  register and 42 permit claims — 7,439 MWth — landed on 2026-08-22
  (HISTORY, and `docs/EXTERNAL_DATA_SOURCES.md` §6). Three things are
  left. **Fifty-five candidates have no permit publication on gov.uk**,
  mostly MCP registrations, which are lighter-touch and may not be
  published at all; whether the Environment Agency will supply them on
  request has not been asked. **Eleven claims are not fully
  self-corroborating** — three state a total with no breakdown to check
  it against, four state one their breakdown disagrees with, and four
  state none at all — and reading their schedules would settle each one.
  **Thirty-four claims are unmatched**, and most are unmatched because a
  site record covers a whole estate rather than because the permit is
  obscure, so the matching is blocked behind the partitioning below
  rather than behind anything about the permits.
- **Site partitioning, now with evidence.** The permits are the sharpest
  partition evidence the project has, because each one names a campus and
  gives its grid reference. Nine permits from seven operators,
  1,430 MWth, fall inside site 23 alone, which is the only site record on
  the whole Slough Trading Estate. Site 5 holds Interxion, Global Switch and
  Telehouse; site 59 holds Vantage and Colt as well as Microsoft; site 11
  holds Amazon and NTT. `data/external_sources/ea-permit-matches.yaml`
  lists each of these under `considered` with the reason.
- **Still not sent, and still cheap:** an EIR request to NESO for the
  project-level demand connection queue, and an FoI to DESNZ/EA for
  site-level CCA consumption. Both have lead times, so starting them is
  cheap and waiting is the cost.
- **Multimodal pass over drawings.** Rejected in v1 and still rejected:
  PDFs are overwhelmingly text-layered, and concealed plant will not be
  in the drawings. Revisit only for a specific application where both
  conditions fail.

---

## Open questions

- **Does the Google Sheet stay the annotatable copy?** It is a
  conversion, not the file the pipeline writes, so it drifts from the
  workbook unless `scripts/sheet_sync.py` is run. That is deliberate —
  the point is that people can comment on it — but it means two
  artefacts claim to be the workbook.
- **Do pre-planning schemes become first-class universe members?** See
  the coverage gaps above. Affects site counts, so worth settling before
  a number goes in print.
- **PlanIt rate-limit politics.** PlanIt is donation-supported and
  friendly, and we are a heavy user. It now 429s far more aggressively
  than in May — assume an hourly quota and plan sweeps at ≥10 s spacing.
  A courtesy email is overdue.
- **Public-data ethics for personal fields.** Householder applications
  can carry applicant names. The schema stores raw values and redaction
  happens at export; the pre-publication sweep needs re-running against
  any new aggregate that touches personal fields.
