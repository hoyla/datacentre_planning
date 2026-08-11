# Roadmap

What is still to do. Everything already built and decided — including
the approaches tried and rejected, which are worth knowing before
re-proposing them — is in [HISTORY.md](HISTORY.md).

Current state: **429 sites** (plus 26 pre-planning), **1,709
applications** in the site universe, **55,678 documents**, **454,011
findings** (20,450 duplicate rows archived by migration 012). Phase 1
is published and closed, stamped at the boundary acquisition stopped
at.

Reading coverage is the open question: 18,645 distinct documents are
read — an earlier figure here, 22,611, summed per-model reads and so
double-counted the dual-read subset — but 4,836 more were skipped by an
extractor gap now fixed, 2,082 are not PDFs and were unreadable until
the format loaders landed, and 58 sites holding 8,212 documents have
had nothing read at all.

---

## Regenerating the phase 2 release

The chain, its ordering constraints and the traps are in
[docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md). Two steps
must precede the artefacts: adjudication corrections (enforced in code
by `dcp/adjudication_gate.py`) and the Drive staging rebuild that picks
up the new CSV adjudication columns.

## Finishing Phase 1

The handover is out. These close it properly.

- **Re-stamp and regenerate.** Acquisition restarted after the first
  boundary, so the release is stamped when collecting stops.
  `scripts/phase1_finalise.sh` waits for the sweep and the Drive sync,
  re-stamps `phase1_snapshot.json`, rebuilds workbook, DuckDB and reader,
  syncs Drive and updates the Sheet. It stops short of the PR that
  deploys `index.html`.
- **Verify the Drive repair.** The document tree was rebuilt after a
  duplicate archive was found; confirm by sampling files' parents, not by
  trusting the sync counters. Then the duplicate folder
  `1UxxGmbiEI-9lR8DPJnEzonBj6OR6OpQe` can be deleted — an outward-facing
  deletion, so Luke's call.
- **Re-probe the password gate** after the next deploy:
  `scripts/probe_gate.sh <url>`. 22 paths plus a forged cookie,
  unauthenticated from outside — a browser session cannot show you this.
  Passed on 2026-08-10 against the current deployment; the reader is
  rebuilt on merge, so it needs running again after the regeneration.
- **16 bad-chunk documents and 7 sites holding unread documents.** Small,
  but they turn into "why does this site say nothing" later.

## Phase 2 — finish the collecting, then the reading

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
- **Deep-read the remainder.** Two thirds of the corpus is unread and
  the Anthropic budget is spent; the plan is OpenAI credits. Everything
  downstream already marks unread sites, so this raises figures rather
  than changing shape.
- **Re-extract the 1,112 stale caches.** Done in code, not yet run: the
  extractor now reads Word, RTF, workbooks, OpenDocument, Outlook, mail,
  HTML and images, and the corpus runner re-reads anything cached with
  `engine: "skipped"`. It needs a pass of `extract_text_corpus.py` to
  take effect, and the deep-read cohort will grow by the 2,082
  non-PDF documents it makes readable. Six remain unreadable: binary
  pre-2007 Excel and PowerPoint.
- **Decide whether scanned PDF pages want orientation detection too.**
  Standalone images are now OCR'd with `--psm 1` because photographs
  arrive sideways; PDF pages stay on `--psm 3`. Councils scan sideways
  as well, so the same fix may apply — but ~5% of 55,678 documents have
  already been OCR'd on the old setting, so this is a measurement first
  (how many cached OCR pages look rotated) and a re-run second.
- **Show synthetic pagination as what it is.** A finding from a `.docx`
  now carries a section index, not a page number, and the cache says so
  in `pagination`. The reader still labels every `evidence_page` as a
  page. Small change, but it is a provenance claim.
- **Salvage the 14 documents lost to parse failure.** Of 380
  parse-failed rows, 368 still produced findings — the failure is a
  truncated tail. The 14 that yielded nothing include two VIRTUS
  supporting statements. `deepread_escalate.py` is the path.
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
- **Water adjudication**, once reading is complete — whether the 93
  sites disclosing consumption support anything firmer than the cooling
  method reported today.

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

- **Promote `associated_id` to a typed `applications.parent_ref`
  column.** Parent-backfill confirmed the field is reliable; a typed
  column makes family navigation a join rather than JSONB extraction.
- **CI on GitHub Actions.** `pytest -m "not integration"` on every push,
  plus `node --test` for the edge middleware. Feasible now the repo is
  public and Apache 2.0.
- **Four sites report a total site demand below their IT load.** All four
  are correct — the figures come from different applications at
  multi-building sites, and each figure names its source application in
  the reader. Worth adjudicating by hand rather than changing the
  rollup rule.

---

## Parked

Deferred consciously. Return when journalism need warrants.

### Postponed past the phase 2 release (2026-08-10 evening)

Cut so the phase 2 handover could go out this evening with the deep-read
in place. None is abandoned; each is a known, scoped piece of work.

- **The acquisition tail.** 31 browser-routed applications, 20 across
  bespoke portals, 13 genuinely hard — a slow process needing a human at
  the keyboard, and not worth holding the release for.
- **Salvage the 14 parse-failure documents**, two VIRTUS supporting
  statements among them. `deepread_escalate.py` is the path.
- **Synthetic pagination labelling.** A `.docx` finding carries a
  section index the reader still calls a page. A provenance nicety, not
  a blocker.
- **Scanned-page orientation detection.** Measurement first, re-run
  second; ~5% of the corpus was OCR'd on the old setting.
- **Coverage gaps** — Northern Ireland (whole nation, one adapter),
  pre-application/screening entries, Section 35 / NSIP, the operator
  watch-list.
- **Phase 3, the second opinion.** The Studio is building the dual-read
  tier-A corpus and `scripts/compare_readers.py` exists; the corpus-wide
  comparison and water adjudication are the next release's deliverable,
  not this one.

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
