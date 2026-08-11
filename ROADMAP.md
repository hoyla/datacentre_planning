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

**Section 106 agreements are tiered as drawings and never read.**
`classify_kind` in [dcp/deepread_select.py](dcp/deepread_select.py) tests
`DRAWING_KINDS` before `TIER_A_KINDS`, and `DRAWING_KINDS` contains
`section\b`. So a document whose kind is "Section 106 Agreement" matches
the drawing rule and returns `skip`, even though `TIER_A_KINDS` lists
`s106|section 106` explicitly and was plainly written to catch it — the
ordering decides, and the tier-A rule is never reached. `"S106
Agreement"` takes the intended path and comes back `A`, so whether an
obligation is read at all turns on how the authority abbreviated it.

Counted over the staged corpus, **57 documents (438 MB) whose kind
mentions s106, section 106, a unilateral undertaking or a planning
obligation are classified `skip`**, against 62 that reach tier A. The
premise this rests on is that s106 agreements are prose worth reading:
they are where planning obligations, community payments and
infrastructure commitments are actually written down, which is
investigative material rather than graphical. `"Section 73 Application"`
— variation of conditions — falls the same way.

The fix is ordering, not vocabulary: test `TIER_A_KINDS` first, or
exclude the s106 forms from `section\b`. It changes coverage figures, so
it wants the 57 re-read and `load_coverage_detail` recomputed rather than
just the regex changed. Found 2026-08-11 while sizing the skip tier for
the Pinpoint upload, where the same rule would have dropped these
documents from the collection too.

## Audit tonight's new rules against prior learnings — DONE

Carried out 2026-08-11; findings in
[docs/RULES_AUDIT.md](docs/RULES_AUDIT.md). One rule of six failed, one
is inert, and the instruction below cited a HISTORY note that does not
exist.

**The failure:** the corroboration bands in `consumption_integrity.py`
and `generation_integrity.py` called 0.8–1.5 the classic
full-redundancy pattern, "sized to carry the load". Measured across the
47 sites disclosing both figures, that band holds 13 of them; the median
ratio is 0.75 and the modal case, 20 sites, is below half. The labels
now describe the ratio instead of diagnosing the engineering. The
thresholds are kept as divisions.

**Still open from it:** the ratios compare figures that may come from
different applications at multi-building sites — the same scope trap
recorded below under Smaller things — and neither script says so. The
extremes run 0.00 to 100.00, which is what that looks like.

The standing lesson holds and is why this was worth doing: inventing a
validation rule means asserting a domain fact, and this project's domain
facts are already written down, often as hard-won negative results. On
2026-08-10 a check asserted that a site's IT load cannot exceed its
stated total; this file already recorded four sites where it does and
all four are correct. It would have led a fresh session to "correct"
three correct figures.

**And when a claim is retracted, sweep every place it was asserted.**
The impossible-components claim was corrected in the code and in the
runbook, and left standing in the pull request description — the one
artefact a reviewer actually reads — until Luke found it there too. That
was the third instance in one evening of fixing the thing in front of me
and not its neighbours: the per-site CSVs bypassed adjudication while the
workbook had it, DuckDB omitted it entirely, and a retraction reached two
of four places. A claim lives in code, comments, commit messages, PR
bodies, the runbook, HISTORY, and the reader's own methodology and
dictionary text. `git grep` the distinctive phrase, not the file you
happen to have open.
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
- **Environment Agency public register.** Industrial installations and
  combustion plant, as triangulation against permitted on-site capacity.
  Before adding this or any other outside source, read
  [docs/EXTERNAL_DATA_SOURCES.md](docs/EXTERNAL_DATA_SOURCES.md): the
  commercial directories, the NESO registers and the Capacity Market were
  each tested against this corpus on 2026-08-10 and the finding was that
  no external MW can become a column, because none of them measures the
  quantity a planning application states — and Data Center Map's
  planned-site figures are read off the same planning documents, so they
  would corroborate us with our own numbers. The two things there worth
  actually doing are requests, not downloads: an EIR request to NESO for
  the project-level demand connection queue, and an FoI to DESNZ/EA for
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
