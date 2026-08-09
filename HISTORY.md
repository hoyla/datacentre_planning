# History

What has been built and decided, in order. The [roadmap](ROADMAP.md)
holds only what is still to do.

This is kept because the *reasons* matter more than the results: several
approaches here were tried and rejected, and knowing that saves someone
re-running them. Where a decision was reversed, the reversal is recorded
next to it rather than replacing it.

---

## v1 — the first investigation (May 2026)

Built with Aisha Down at the Guardian. The question: do data-centre
planning applications disclose on-site power generation that contradicts
public renewable marketing?

**Universe.** 1,894 UK applications, 2007–2026, from the PlanIt national
index — a broad keyword sweep, then operator-name expansion, a spatial
sweep around known sites, and a parent-application backfill that walked
PlanIt's `associated_id` chain to recover pre-2018 permissions referenced
by later procedural filings.

**Triage.** `granite4.1:30b` locally over the whole universe against a
written rubric, chosen after a five-model comparison — IBM's JSON tuning
plus 30b reasoning gave roughly 97% verdict accuracy at ~9s per
application. Verdicts are versioned per `(application_id, model,
inserted_at)`, so a second model overlays rather than overwrites.

**Documents and extraction.** Idox and Ocella adapters, with a manual
ingest path for one-off portals; ~99% coverage of the top-100 worklist.
Findings extracted human-in-the-loop, every evidence quote verified
verbatim against the cached page text before it entered the store.

**Release.** `dcp release` produced a versioned folder whose headline
artefact was a single-file HTML reader with a split card-and-map view,
plus text-only, xlsx and standalone-map companions. All eight
story-readiness items resolved; v1.0 shipped 2026-05-17.

**Rejected in v1, and why:**

- *Phase 5, a multimodal pass over site plans.* Nearly every PDF in the
  corpus has a text layer, so vision added little — and anything an
  applicant genuinely wants to conceal will not be in the drawings.
- *A browse UI.* The static single-file reader answered the access
  pattern without a server, and still does.

---

## v2 — the second dataset (August 2026)

### Barbour ABI, and what it exposed (Aug 2)

Cross-referencing the universe against Barbour ABI's licensed
construction-project data — 253 projects, ~200 linked to applications
with per-link match provenance — showed the keyword-built universe had
been missing whole classes of scheme. 62 previously-missed applications
were ingested and pre-2018 "Built" estates came into scope.

The gap ran both ways and was enumerated in both directions rather than
assumed. That reconciliation is what motivated everything below.

### The dc_build universe (Aug 3)

A new rubric — *is this a data-centre build application* — with eight
project classes, replacing v1's four. Five adjudication rules came out of
a conversational adjudication of 16 contested rows, the load-bearing one
being **classify the instrument, not the scheme it describes**.

Architecture locked after a trial: **Sonnet catalogues metadata**,
**every candidate site gets deep-read** — triage demoted from gatekeeper
to cataloguer, because the ground-truth exercise found 10 cases in 50
that could not be resolved from the description at all.

**Prompt v2.2 tried and rejected.** Widening the model's signal
vocabulary cost two points against the adjudicated set (45/50 versus
v2.1's 47/50), and the entire loss was on the rows that depend on the
association rule. Reverted. The requirement was met better by extracting
environmental subjects **deterministically** from descriptions
([dcp/signals.py](dcp/signals.py)) — reproducible, free, and no risk to a
validated prompt.

### Acquisition (Aug 5–9)

Adapters in coverage order — Idox, Ocella, Agile, Arcus, Salesforce —
then five councils that each blocked differently and were each solved
and documented in [docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md):

| Council | Obstacle | Recovered |
|---|---|---|
| Coventry | AWS WAF; driven through a browser rather than scraped | 254 |
| White Horse | Documents on a migrated register | 884 |
| Runnymede | `ViewDocument?id=`; `DownloadFile` is a decoy | 982 |
| Broxbourne | Document list needs an explicit `pageSize` | 534 |
| Slough | Legacy PHP store; a `Referer` header was all it wanted | 164 |

Two habits are now enforced in code rather than remembered. **One client
per host**: a shared client let one council's 429 backoff (4s → 45s)
throttle every other council in a sweep. **An application is never marked
complete unless every listed document arrived** — 21 were wrongly settled
during a block, which is precisely the silent failure the pipeline exists
to avoid.

### Deep-read at scale (Aug 7–9)

18,645 documents read, 462,221 findings, every evidence quote
machine-verified against its source before insertion. A second model
re-reads a subset independently; where the two disagree, both readings
are kept and the disagreement is the finding.

**Power adjudication** was the most consequential correction. Taking the
largest MW figure in a site's documents produces nonsense, because
planning statements argue for approval by citing the market: under that
rule a Slough application reported 30 GW (a national storage target) and
a Chiltern one 22,700 MW (a Savills forecast). Every figure is now
adjudicated for *whose* it is, and only those the documents attribute to
the development itself are admitted. **Of the twenty-two largest figures
in the corpus, all twenty-two describe something other than the site they
appear in.**

**A re-read of the sites lacking a capacity figure was investigated and
rejected** — a useful negative result. Most hold no documents at all (an
acquisition gap, not an extraction one); **71 were read in full and
genuinely never state a capacity**. A regex sweep of their cached text
finds MW-like patterns in 2% of documents, all false positives — manhole
annotations, kWh/m² targets, EV charger ratings. That consented data
centres disclose no power figure is itself a finding.

**Water was reduced to cooling method, not volume.** The water findings
are dominated by the drainage and flood engineering every development
produces; only 93 sites disclose anything about consumption. A volume
would imply a precision the applications do not contain.

### The Phase 1 handover (Aug 9)

Three artefacts over one corpus: a **workbook** (61 columns, with a
column-by-column dictionary), a **DuckDB** file for people whose question
is not in a column, and a **reader** — one self-contained HTML page with
sites, applications, the energy layer, a map, the methodology and the
data dictionary, published behind an edge password gate.

Everything findings-derived on a partly-read site is marked as a floor
that can rise. Every "no documents" carries the reason it has none, from
the recorded acquisition outcome, so *checked and empty* stays distinct
from *never tried*.

**Corpus boundary.** Frozen at 08:50 to get the handover out, then
deliberately unfrozen when acquisition restarted the same evening. The
release is stamped when collecting actually stopped;
`data/exports/phase1_snapshot.json` records both boundaries and why the
first was superseded.

---

## Lessons that changed how the code is written

Each of these was learned by getting it wrong, and each is now enforced
by something other than memory.

**Verify at the far side, not the near side.** Claiming Drive was correct
after looking at the local staging tree; claiming Pages was fine after
looking at the repo. Both were wrong, and both were caught later by
checking the actual endpoint. The password gate looked perfect in a
browser until an unauthenticated request from outside found
`//index.html` served the whole dataset.

**A correction deserves a durable form.** Two instructions — use the
Drive folder *ID*, never push to a merged branch — were in memory, were
repeated, and were broken anyway. They are now a constant the sync
defaults to ([dcp/drive.py](dcp/drive.py)) and a hook that refuses the
push ([.githooks/pre-push](.githooks/pre-push)).

**An empty result is not a null finding.** A blocked page and a council
that publishes nothing look identical to a scraper and mean opposite
things. Everything that can fail this way now records *why* it is empty.

**Silent partial success is worse than failure.** A fetch that retrieved
some documents was recorded as complete, and the queue only asked for
applications holding *none* — so a partly-retrieved application could
never come back. Short fetches are now `partial` and re-queued.
