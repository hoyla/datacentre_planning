# Regenerating the release

Written 2026-08-10 evening mid-flight and updated after the 2.1 run on
2026-08-11, for whoever runs the regeneration — including me in a fresh
session. It assumes nothing about what you remember.

Read [HISTORY.md](../HISTORY.md) for why the pipeline is shaped this
way and [ROADMAP.md](../ROADMAP.md) for what is outstanding. This covers
only the regeneration chain and what is easy to get wrong in it. (There
was a SESSION_HANDOVER.md here until 2026-08-22; it was folded into
those two, which were the documents it kept duplicating.)

---

## State — the base is 2.11, released; figures move, so read stamps, not this file

Current state lives in two places, deliberately not here: the
[ROADMAP](../ROADMAP.md) header for the corpus counts, and
`scripts/corpus_stats.py` for the figures that move while the
corroboration pass runs. Release runs themselves are recorded in
[HISTORY](../HISTORY.md) — v2.7, the 2.9 evening, v2.10, v2.11 —
including each run's debrief. What stays in this section is only what remains
true between releases.

**The deploy is `cloudrun/deploy.sh` — not a merge.** This document
said for months that merging the release branch published it, which
stopped being true on 2026-08-26 when the EdgeOne middleware became a
pure redirect: it serves nothing, so nothing in git reaches a reader.
Merging the release PR records what was published; running the script
is what publishes it (Luke corrected this during the 2.10 deploy,
2026-08-29).

**The corpus moves under the artefacts, so every figure in a build is
a snapshot.** The corroboration read writes to the database
continuously, and rebuilding an artefact against an unchanged codebase
moves cells — the 2.2 workbook rebuild shifted sixteen on Sites with
no code change behind them. Two consequences. **Before quoting a
figure from an artefact, check its stamp**; every one carries a
generation time and a pipeline commit. And when a release needs a
clean boundary, stop the reader first — or do what 2.7 did, and take
the boundary when the corpus has stopped moving on its own.

**Two lessons from the 2.7 run that change how you read the steps
below.** Step 1 is not optional bookkeeping: the corroboration read
had left 4,117 figures unadjudicated, nothing downstream can see a
figure nobody has asked about, and only the step order caught it. And
step 5's contradicted-sites count is worth reading rather than
counting — the third one it reported was a 2013 offshore-wind
substation's 99.9 MW rendering as a data centre's grid connection on
the largest site in the corpus, which no gate would ever have flagged.

The next regeneration starts at step 0 and the steps run in the order
they are written: 0 to 15, top to bottom.

**Step 0 is new on 2026-08-26.** The materialise was never in this
document — `grep -n materialise` returned nothing — and it is the step
that decides which applications exist at all as far as every later
step is concerned. That omission is the process half of the incomplete
Drive archive; the code half is now two guards inside
`build_drive_staging.py`.

Step 7 comes before step 9 deliberately: `build_drive_staging.py`
copies the release artefacts into the Drive root, so building the tree
before the exports stages the *previous* release's workbook and
database.

**And check which release folder it took.** Its `--release-dir` used
to default to a hardcoded `phase2_build`, so the 2.1 run staged phase
2's workbook and database beside 2.1's per-site files and said so in a
line nobody would think to doubt. It now defaults to the most recently
written `data/exports/*_build` and prints which one it chose.

**The largest figures, stated carefully, because getting this wrong is
the standing hazard of this dataset** (re-verified 2026-08-30).
Largest disclosed IT load is **Elsham Wolds at 1,000 MW**; largest
total site demand is **Northumberland Energy Park (Cambois) at
1,100 MW** — and Cambois restates its 1,100 across three of its own
applications, so summing a site's figures triples it.

The largest single row carrying `verdict='site_capacity'` is **1,200
MW at Camilla Road, and it is a `thermal_input`** — fuel entering a
plant, two to three times the electricity leaving it. An earlier
version of this table called it the dataset's largest site capacity,
which was wrong, and wrong in exactly the way the
`thermal_not_electrical` correction exists to prevent.
**`verdict='site_capacity'` alone does not mean "an electrical
capacity".** It means the figure is about this development;
`quantity_type` says what kind of quantity it is, and `thermal_input`
and `energy_storage` are both in there. Filter on both, always. The
three exports do; a `max(value_mw)` typed at a psql prompt does not.

Two durable rules distilled from the 2.1 run's West London episode
(the full story is in this file's git history at 2026-08-11, and the
correction's reasoning lives beside the rule):

- **`contradicted_by_own_document`** is pinned to one value and one
  sentence in `correct_adjudications.py`, because the general rule —
  demote a figure whose document holds one five times smaller amid
  need/demand language — was measured at 64 matches and wrong on
  about 62. Need and demand are the ordinary vocabulary of a capacity
  statement.
- **Do not "fix" a site whose IT load exceeds its own stated total.**
  At multi-building sites the two figures routinely come from
  different applications and different scopes; the check is called
  `components-differ` and says so. Only a magnitude as extreme as
  West London's was worth reading.

---

## The chain, in order

The order is not cosmetic. Two steps must precede the artefacts or the
handover ships wrong numbers, and one of them is enforced in code.

The numbers now run in the order the steps run in: 0 to 15, top to
bottom, with three lettered steps inserted where their timing demands:
4a (the machine readings, 2026-09-01), 11a (the operator snapshots,
2026-09-01) and 13a (the search bundles, added 2026-08-29 because being
"off the chain, optional" is how the notebook went three releases stale
and Pinpoint four). They did not until 2026-08-26, when the chain read 0, 1–4, 7, 5,
6, 8, 9 and a reader had to hold the map in their head — which HISTORY
records catching a bug for exactly once, and is not a system. Only 0, 1,
2 and 7 kept their old numbers; anything citing another number from
before that date is citing the old scheme.

### 0. Materialise the sites — before anything reads the universe

```sh
scripts/materialise_sites.py --dry-run    # look at what would move
scripts/materialise_sites.py
```

**This step was missing from this document until 2026-08-26, and its
absence is half of why the Drive archive was incomplete.** Nothing else
in the chain puts an application into a site, and *everything*
downstream reads the universe through `site_members`: the workbook, the
reader, the DuckDB file, and `build_drive_staging.py`, which stages a
document if and only if its application has a live membership row.

An application with no membership is not a slightly-wrong row. It is
absent — from the tree, therefore from the sync's candidate set,
therefore from both the sync's `skipped` and its `failed` counters. On
2026-08-21 that was 3,679 documents held for 143 applications discovered
on 2026-08-07, and the sync that day reported 50,406 candidates, 0
failed, 0 skipped. Every number was true. None of them could see the
gap.

Run it after anything that changes the universe — a discovery sweep, new
triage verdicts, new project links, an edit to
`data/priors/site_partitions.yaml` — and before the exports. It is
idempotent, prints what it would change before changing it, and stops
rather than orphaning a hand-adjudicated capacity claim (re-point the
claim in `data/external_sources/*.yaml`, run
`scripts/load_capacity_claims.py`, then re-run this).

`build_drive_staging.py` now refuses to build when this step is
outstanding — it compares `max(sites.materialised_at)` against the
newest `applications.first_seen_at` and `projects.first_seen_at` — so
skipping it is an error rather than a silent omission. It deliberately
does **not** look at `documents.fetched_at`: a refetch rewrites that on
applications mapped weeks ago, and a guard that fails on every refetch
gets passed rather than read.

### 1. Collect the adjudication batch

```sh
scripts/adjudicate_openai.py --collect
```

Then check nothing was lost to truncation, because that has already
happened once:

```sh
scripts/adjudicate_openai.py --dry-run --reasoning-effort medium
```

If that still reports thousands of unadjudicated figures, the batch
truncated. The first attempt at this used `--reasoning-effort high` with
an 8,000-token ceiling and **155 of 436 requests returned nothing at
all**, having spent 96% of the budget on reasoning. Reasoning tokens are
output tokens; the ceiling has to cover both. It is now 16,000, and
`medium` is the setting that works. Resubmit the remainder if needed —
the cohort query only offers figures with no adjudication, so re-running
is safe and cheap.

### 2. Correct the adjudications — MANDATORY

```sh
scripts/correct_adjudications.py --dry-run   # look first
scripts/correct_adjudications.py
scripts/correct_adjudications.py --dry-run   # must now report 0
```

Every adjudication pass reproduces the same six quantity-kind errors,
because the prompt that produces them is unchanged (`power-1.0`). The
tail carried 337 battery figures, 153 thermal inputs, 52 energy-shaped
quotes and 44 temporary supplies into an adjudicator with no vocabulary
for any of them.

**The three exports refuse to run until this has been done**
([dcp/adjudication_gate.py](../dcp/adjudication_gate.py)). If a build
stops with a wall of text about a 251,859 MW site, this is the step you
skipped. There is an override flag; it is deliberately tedious to type
and you should not need it.

### 3. Adjudicate the generation figures

```sh
scripts/adjudicate_generation.py --batch --submit
```

Resumable on `(finding_id, model, prompt_version)`, so a re-run asks
only for what is missing and a failed chunk costs one request rather
than the pass.

This answers what each on-site generation figure *describes* — one
machine or a fleet, standby or prime, electrical or thermal — and
without it three things downstream are wrong rather than merely absent.
`dcp.site_profile.generation_figure` falls back to reading the quote,
which is what put "50 x 3.3 MWt Generators" on a site as 165 MW of
electricity; the `generation_exceeds_load` cohort refuses to compute at
all; and the site page's generation line cannot say whether a number is
a per-unit rating.

The current pass is `gpt-5/generation-2.5`, 1,667 figures. A new prompt
version re-adjudicates the whole corpus by construction — no figure
carries the new version — so bumping it is a deliberate spend, not a
side effect of an edit.

### 4. Audit how findings are filed

```sh
psql "$DATABASE_URL" -f migrations/025_finding_label_audit.sql   # once
scripts/audit_labels.py --batch            # measure, spends nothing
scripts/audit_labels.py --batch --submit
```

Asks a second model one question about every finding a reader will see:
does the family fit the text? 18.2% of the 10,605 rendered findings do
not, which is why a site's evidence could lead with landscape prose
filed under a power family.

Also resumable. A flagged row is **moved** on the page, marked with
where it was filed, and a `not_a_finding` row is withheld — neither is
deleted, and both counts print at the end of the export. The reader
re-checks every verdict's citation against the finding's own text
before acting on it (`dcp/spans.py`), so a verdict whose span is not
in the text moves nothing.

The exports run without this: no verdicts stored means nothing moves,
and the build says so. It is not gated like step 2 because a missing
audit leaves the page as it was, where a missing correction puts wrong
numbers on it.

**That reasoning fails after a re-gate**, and the 2026-08-31 re-gate is
the first time it has. It holds while the cohort is the one already
audited. When a run reinstates findings — 15,679 of them, there — a
missing audit does not leave the page as it was. Measured that day, the
reader renders 13,679 findings across 357 sites and 326 of those (91%)
are at the 40-per-site cap, so a reinstated row reaches a page mostly by
displacing one that was on it. What it wins the slot on is length:
within a family `FINDINGS_SQL` orders by adjudicated-as-this-site's
first, then `length(value_text) DESC`. That is the ranking whose earlier
version put a landscape paragraph labelled `it_load` at the top of a
site's evidence four times over. So run this step in the same pass as
the write, before the build.

It is cheap to run again: `do_batch` skips every finding already audited
under the same model and prompt version, so the ask is only the rows
that newly render — and `--batch` without `--submit` prices that before
anything is sent.

**Keep the pair as it is** (`gpt-5`, `label-1.0`) unless a full
re-audit is what you want. The skip is keyed on model *and* prompt
version, so moving the audit onto a newer reading model — `gpt-5.6-terra`
is the live temptation — silently turns an incremental run into all
18,209 rows again.

### 4a. Submit the machine readings now, collect them before step 12

```sh
scripts/machine_reading_openai.py --submit --model gpt-5 --reasoning-effort medium
# ... later, any time before the step-12 rebuild:
scripts/machine_reading_openai.py --collect
```

The readings were never a numbered step, and at 2.11 that nearly cost
half an hour of wall-clock for nothing. Their inputs are the *corpus*
— adjudicated figures, claims and matches, cohort membership, the
documents — not the build, so they are ready to submit the moment
steps 0–4 have settled the corpus, and `_already()` keys on the input
hash, so a bare `--submit` reads only the sites whose inputs moved
(47 at 2.11, ≈4.3M input tokens, for the new matches and the cohort
whose definition #333 rewrote). The batch turnaround is 15–35 minutes,
which the reports, the backup and the step-7 exports absorb entirely;
only the step-12 build needs the readings in the database, because
that is the one that publishes `index.html`.

**Pass `--model gpt-5` every time.** The script's default is
`gpt-5.6-terra`, and docs/MODELS.md records why that model is not the
one the readings run on: at the same prompt it states about a quarter of the
figures, and `LATEST_SQL` would render it. A bare `--submit` would
reintroduce that regression on every site whose inputs moved.

**Then, once the collect is in, check that every rendered reading still
describes its site** — per release, decided 2026-09-02, which closes
the ROADMAP's question of whether this runs per release or per batch:

```sh
scripts/verify_reading_freshness.py --dry-run   # names the stale sites, writes nothing
scripts/verify_reading_freshness.py             # marks them withheld, append-only
```

`--collect` compares each site's input hash at collection with the one
it was submitted under, and until this step nothing checked again
afterwards — so a reading collected on Monday still rendered on Friday
against documents that arrived on Wednesday. The script rebuilds every
site's input and re-hashes it, which costs about 8 seconds a site and
~35 minutes for the corpus (measured 2026-08-27); that is why it is a
step here and not a build-time guard, and why the build's own check is
liveness alone (`load_latest(live_only=True)`). A site whose input has
moved gets a new row under the model tag `freshness-check`, carrying
the current hash, no reading and a withheld reason, so the reader shows
its panel as withheld with the reason rather than rendering a stale
reading — the same path a gate refusal takes, and re-runs are no-ops.
If it names sites, either re-submit them (a bare `--submit` will pick
them up, their hash having moved) and collect again before step 12, or
let the marker stand for this release and say so in step 15.

### 5. Look at what moved

```sh
scripts/consumption_integrity.py
scripts/generation_integrity.py
scripts/review_large_capacities.py --min-mw 100
scripts/sweep_null_capacity.py
```

Reports land in `data/reports/` (gitignored — they name sites and quote
documents). You are looking for:

- **contradicted** sites — a grid connection materially below stated
  demand. Two are genuine and known — **Watford Bypass and Ferrybridge
  C** (this said "West London" until 2026-09-01; West London left the
  list when the export-limit rule landed, and Ferrybridge C has stood
  in its place since at least the 2026-08-28 report, its grid 100 MW
  equalling its storage 100 MW, which reads like a battery connection
  typed as the data centre's and is a person's row); more than that
  means something new to read.
- **generation-understated** — a single machine's rating standing in for
  a fleet. Five known.
- The null-capacity sweep prints **PROVISIONAL** and refuses to give a
  quotable number while any candidate figure is unadjudicated. If it
  still says that after step 2, step 1 did not finish.

### 6. Back up before rebuilding

```sh
scripts/backup_db.py
```

Encrypted, verified, uploaded. Needs `DCP_BACKUP_PASSPHRASE` in `.env`.
The database is the only irreplaceable artefact — documents are mostly
re-fetchable, the interpretive layer is not. This machinery was used in
anger once already today, to recover 248 rows from a migration that
demoted more than it should have.

### 7. Rebuild the artefacts — BEFORE step 9 stages them

**Check the sync ledger is populated first.** Both the reader and the
workbook read their Drive links out of
`data/exports/.drive_sync_state.json`, and a site missing from it gets no
link and the words *"not yet synced to Drive"*. Building before the
first-ever sync is fine, because there is nothing to link to yet.
Building against an *absent* ledger is not: it produces artefacts that
tell every reader their documents are missing, and nothing about them
looks broken.

That happened on 2026-08-21. `data/exports/` had been cleaned between
releases, taking the staging tree and the ledger with it, and the 2.2
reader shipped saying "not yet synced to Drive" on 416 of 430 sites —
all of which were on Drive. The order in this heading is still right;
the assumption underneath it is that a previous sync's ledger survives.
Check it does:

```sh
python -c "import json;d=json.load(open('data/exports/.drive_sync_state.json'));\
r=[v for k,v in d['folders'].items() if k.endswith('/sites')][0];\
print(sum(1 for k in d['folders'] if k.startswith(r+'/')),'site folders')"
```

If that is far below the site count, run steps 9 and 10 first to rebuild
the ledger, then come back and build the artefacts. Rebuilding a lost
ledger costs about an hour of API calls and no upload bandwidth — the
md5s all match, so nothing is re-sent.

First carry the pagination into the database, or every citation from a
Word file, a workbook or a deck goes out calling its section a page:

```sh
scripts/backfill_pagination.py --dry-run   # then without, to write
```

Idempotent, reads the text caches, and only matters after new documents
have been extracted — but it is cheap and running it out of order is the
kind of mistake that ships. 1,470 documents in the corpus divide
themselves into something other than pages, and 17,724 findings cite one
of those divisions.

```sh
scripts/export_handover.py --out data/exports/phase<N>_build/dc_handover_phase<N>.xlsx
scripts/export_duckdb.py   --out data/exports/phase<N>_build/dc_phase<N>.duckdb
scripts/export_reader.py   --out data/exports/phase<N>_build/reader.html \
                           --phase <N> --publish index.html
```

**Pass `--phase` for a new release.** The title, header, stamp and the
database's own filename in the reader all read from it. Since the R7
change of 2026-09-01 it defaults to the newest release folder's phase
rather than to 1 (which used to stamp the front page "phase 1 release"),
and when you are building the *next* release the newest folder is the
previous one, so the default is wrong by exactly one step.

**Name the artefacts for the phase that produced them.** Phase 1
published `dc_handover_phase1.xlsx` and `dc_phase1.duckdb` into this same
Drive folder. Rebuilding under those names replaces a published artefact
with different numbers behind an unchanged name, which is the one thing
an append-only record is supposed to prevent. Luke chose on 2026-08-11 to
ship phase 2 alongside and leave phase 1 in place.

A trap worth knowing, because it cost the local phase 1 workbook: the
workbook writer **truncates the existing inode**, so a rebuild over the
old name is seen instantly by every hard link in the staging tree. The
DuckDB writer replaces the file instead, which is why the phase 1
database survived and the phase 1 workbook did not. The only genuine
phase 1 workbook now lives on Drive.

Each of these calls the adjudication gate first, so if step 2 was
skipped they stop rather than shipping.

### 8. Diff against the last release — BEFORE anything is deployed

```sh
scripts/release_diff.py data/exports/<new_build> --against data/exports/<previous_build>
```

It counts what a reader can reach — links per site panel, rows per view,
tabs, section and box headings, the filter controls, the header stamp's
own numbers, plus sheets and columns in the workbook and tables and rows
in the database file — and prints anything that **fell**. Nothing else
in the chain notices a regression of that shape, because none of it
changes a figure: a panel that lost its Drive links, a view that lost a
column, a heading that stopped rendering all leave every number correct.

This found four regressions in 2.2 that review had not, and it has cried
wolf twice since — once when a heading gained an `id` its pattern did
not allow for, once when a panel boundary moved. **Fix the detector when
that happens rather than reading past it.** A guard nobody trusts is
worse than none: it went blind to the whole filter bar for a build after
the bar moved out of the sites view, and would have reported nothing at
all if a control really had gone.

A FELL line is not automatically a fault. Deliberate removals show up
here too — the "Exclude unknown MW consumption" control went on purpose
in 2.7 — so read each one and be able to say which it is.

### 9. Rebuild the Drive staging tree — AFTER steps 0, 2 and 7, never before

```sh
scripts/build_drive_staging.py
```

**It now rebuilds clean rather than updating in place**, so the move-aside
that used to be folklore is gone: the tree is written to
`data/exports/drive_staging.building` and swapped in, and anything that
has left a site leaves the tree with it. That matters beyond tidiness —
`drive_sync.py` can only recognise a re-filed document as a *move* when
its old path has gone, and until 2026-08-26 the old path never went. The
Interxion folder held 45 application directories for a site with 16.

A full clean rebuild takes about a minute and costs nothing on disk: the
documents are hard links into `data/raw`, so both trees exist at once for
the price of directory entries. The one thing carried across the swap is
a *published* artefact at the tree root — an earlier release's workbook
and database stay beside the current one's, because a citation of them
has to keep resolving, and `drive_sync.py --prune` already declines to
touch the root for the same reason.

**It also states its own shortfall and exits non-zero on it.** Every run
prints the documents it did **not** stage, grouped by the application's
latest triage verdict, and fails unless every one of them is triaged
`not_dc`. That is the only verdict that means "out of the handover on
purpose"; an untriaged application is named individually rather than
tolerated. A pass looks like

```
   documents held but not staged, by latest triage verdict:
     ok not_dc             3,808 documents across   70 application(s)
```

and a failure names what is missing and how much of it. Replayed against
the 2026-08-21 state it reports *3,584 documents held for 139 in-universe
applications are not in this tree*. Nothing in the sync could have said
that, then or now: the sync can only describe the tree it was handed.

If it fails, the fix is upstream — step 0, or a triage verdict — not a
flag. `--allow-stale-site-map` exists for the map guard and takes a
reason you can state out loud.

**Adjacent power is staged beside the sites, not excused** (2026-09-02).
Issue #252 removed the `adjacent_power` class from site membership on
2026-08-30, and the first staging build after it — the 2.11 run —
found 744 held documents across 28 such applications with nowhere to
go, four of them cited by a machine reading. They now go under
`adjacent_power/<application>/` at the tree root, next to `sites/` and
`operator_snapshots/` (Luke: "next to, rather than inside, sites") —
"no membership" meaning no membership *on a live site*, since a
membership row on a site the materialise has retired stays unretired
and read as a membership until 2026-09-02, which left four
applications' documents with no Drive home at all —
each folder's `_index.md` naming the sites the scheme stands beside
and how that is known. The shortfall counts them as staged only once
the build has actually written them, so an adjacent-power application
that failed to stage still fails the run; `record_drive_ids.py` and
`verify_drive_sample.py` read the folder name from the builder, so
those documents get their ids recorded and can be sampled like any
other. **Which applications belong there is decided once**, in
`dcp.adjacent_power.staged_applications`, and read by the builder, the
recorder and the verifier alike — the three carried their own copies of
the rule until 2026-09-02 and the copies agreed with each other while
disagreeing with the materialise (#349). The rule also brings a scheme's
own paperwork with it: a discharge, amendment or variation whose parent
is an adjacent-power application and which is in no site is filed
beside its parent, its index naming the parent and the sites the parent
stands beside. Triage calls such paperwork `not_dc`, correctly, and the
shortfall used to read that as "excluded by decision" while the parent
had a folder — Union Park's four discharges and one at Hallen, 50
documents. A pass now prints an `adjacent power: N applications, M
documents` line beside the site count, and a `zero-byte documents
in the tree` line naming any document held as an empty file — three are
known, from before the fetch guard existed, and a fourth is news (see
`repo.zero_byte_files`). The folder's Drive id is
`dcp.drive.ADJACENT_POWER_FOLDER_ID`, read back from the sync ledger on
2026-09-02, so anything that links the class as a whole addresses it by
id, the way `sites/` and `operator_snapshots/` are.

The per-site findings CSV carries four adjudication columns (*whose
figure is this?*, quantity type, adjudicated MW, quantity note). Built
before step 2, those columns carry uncorrected verdicts — a battery
rating labelled as this site's generation, in the artefact most likely
to be opened in Excel and sorted by the biggest number.

**And after step 7**, because this script copies the release's workbook,
database and reader into the Drive root. Run before them and the root
gets the previous release's artefacts beside the current release's
per-site files, which is how a reader ends up with a workbook and a
reader that disagree. The dependency is on `--release-dir`, which no
longer names a phase: it defaults to the most recently written
`data/exports/*_build` and prints which one it chose. (It did default to
a hardcoded `phase2_build`; `tests/test_release_defaults.py` now forbids
that shape anywhere.)

The rename **is now built**: the two per-site files carry the site in
their own filenames —

    _findings — <site_key> — <site name>.csv
    _site_report — <site_key> — <site name>.md

so they stay identifiable in anything that flattens the tree, a
NotebookLM collection above all. The site key is in there as well as the
name because display names are not unique — four sites are called
"Reading Quarry Berrys Lane Burghfield".

The matching **prune step in the sync is also built** (`--prune`, step
6). Renaming without it leaves 692 stale twins beside their successors.
Do both together or neither.

### 10. Sync to Drive, then verify at the far side

```sh
scripts/drive_sync.py --sync data/exports/drive_staging --prune --dry-run
scripts/drive_sync.py --sync data/exports/drive_staging --prune
```

**Nothing reconciles tree against ledger against Drive at the end of a
sync, and that is deliberate** (moved here from the ROADMAP
2026-08-30; the fix this qualifies shipped 2026-08-26 — HISTORY, "The
corrections that landed between 2.9 and 2.10"). On 08-21 all three
agreed while 3,679 documents were missing, so such a check would have
passed; the guard sits between the *universe* and the staging tree,
which is the only place this class of failure is visible. Expect the
guards' first run after corpus movement to fail — that is the guards
working, not crying wolf. `data/exports/drive_staging.pre-clean` is
the primary evidence of the original episode and stays until a full
guarded sync has been observed clean.

**`--workers` now defaults to 12.** It used to default to 1, and on
2026-08-29 that ran a 58,799-file sync for **9h16m to reach 54%** before
anyone noticed — the flag existed, its own help said 8-16 was safe, and
nobody passed it. The sync is latency-bound: one HTTPS round-trip per
file against a per-user quota near 12,000 requests/minute, so the
sequential path was leaving the quota almost entirely unused. Restarted
with 12 workers it finished the remainder in minutes. Pass `--workers 1`
if you want the old behaviour.

**Killing a sync mid-run is safe only with the ledger copied first.**
`Sync.save` writes `.drive_sync_state.json` with a plain `write_text`
every 50 changes, so a kill during that write truncates the record every
link in the next build depends on — the 2.2 failure mode. Copy it, kill,
confirm the live file still parses, then restart; the sync compares
md5s, so nothing already uploaded is re-sent.

`--prune` moves to the Drive bin every file this tool uploaded whose
local copy has gone — the stale twins left by the step 9 rename. It
works from the upload ledger, because the grant is `drive.file` and the
API cannot list the folder's contents: there is no far side to diff
against, only the record of what this tool put there. That cuts the safe
way, since a file this tool never uploaded is invisible to it and cannot
be binned by it. It refuses outright if the prune set exceeds half the
tree, on the grounds that a staging build that died halfway looks
exactly like a wholesale rename.

Two things it will not touch. Released artefacts at the tree root —
phase 1's workbook stays beside phase 2's, so a citation of the older
one keeps resolving. And anything it did not upload. Files are trashed,
never deleted, so a wrong prune is a restore from the bin rather than a
re-upload of 70GB.

```sh
scripts/verify_drive_sample.py --sample 30 --phase <N>   # the release you are shipping
```

That is the check, now a script rather than a described intention.
**Its sample frame is the universe, not the ledger** — changed
2026-08-26, and the change is the point. It used to draw its sample from
`.drive_sync_state.json`, which is written from the staging tree, so its
frame was the tree and no sample it could ever draw contained a document
that never reached the tree. It now samples rows from `documents` whose
application has a live site, derives the path the builder would give
each one (through the builder's own naming function, so the check cannot
disagree with the build), and follows the whole chain:

    the database says we hold it
      → is it in the staging tree, at that path?
        → is it in the upload ledger?
          → does Drive have it, those bytes, under the handover root?

Any link that breaks is a failure named as the link that broke, so
"never staged" and "staged but never uploaded" and "uploaded to the
wrong parent" are three different sentences.

Release artefacts are still checked from the ledger — they have no row
in `documents` to sample — and always, because checking only random
files would pass while the one thing everybody opens sat in the wrong
folder. `--phase` tells it which release is yours, so an older release's
artefacts are reported without failing the run.

Expect failures if the corpus has moved since step 9. A document fetched
after the tree was built, or one whose `kind` a re-list changed, is
genuinely not at its expected path — which is the check working. Rebuild
and re-sync rather than reading past it.

It found on 2026-08-11 that **phase 1's and phase 2's workbooks and
databases sit outside the handover root**, in
`1udCAR_bD5ghLO4qJOBThXqmSPSlzb3wT`. Phase 1's was already known; phase
2's was not. Worth knowing before hunting for them to archive. Under
`drive.file` the tool cannot read that folder's own metadata, only its
id — it did not create it.

The original wording of this step, kept because it is the reason the
script exists: confirm by fetching a sample **through the API by file id** —
name, parent folder, byte size and md5 against local. This is what found
that the phase 1 artefacts sit outside the handover root; the sync's own
counters would never have shown it. Do not trust the
sync's own counters: they looked fine on the day half the tree went into
a duplicate archive. There is a worked example of the far-side check in
the session transcript; the principle is that the ledger is the near
side and the API is the far side.

### 11. Record where each document landed — AFTER step 10, before rebuilding

```sh
scripts/record_drive_ids.py --dry-run          # what would be recorded
scripts/record_drive_ids.py --verify-bytes     # ~3 min, reads 138 GB
```

Writes the Drive file id of every uploaded document into
`document_drive_files`, which is where the reader and the workbook read
document links from. Skip it and every document synced for the first
time falls back to a register link — a link that rots, on the documents
most likely to matter, because they are the new ones.

`--verify-bytes` hashes each local file and refuses any id whose md5
disagrees with what the ledger says it uploaded. It costs three minutes
and it is the difference between a link that is probably right and one
that is checked. Run it.

The step is append-only and idempotent: re-running over an unchanged
ledger inserts nothing, and a document re-uploaded elsewhere gains a row
rather than losing the one that already resolves.

**Why this is not just a lookup at export time.** It used to be. The
export rebuilt each document's expected staging path — site stem,
application reference, and a number counting the application's documents
in `fetched_at, id` order — and looked that path up in the ledger. It
was correct, and 120 of 120 sampled links verified content-addressed
against the local bytes. But every input to that derivation can move,
and when one does the lookup either finds nothing, silently dropping a
link, or finds the neighbouring file: a working link to the wrong
document, under a citation naming a different one. The first is
annoying. The second puts a real quote against a real but different
source, which is the failure principle 7 exists to prevent, and it is
invisible from the outside.

A Drive id survives the file being moved or renamed on Drive. A derived
path does not survive anything being renamed here. So the id is captured
once, checked, and read back by key.

### 11a. Put any new operator snapshots on Drive — before step 12

```sh
scripts/sync_snapshots_drive.py --dry-run
scripts/sync_snapshots_drive.py
```

The claims channel's evidence is a committed snapshot of an operator's
page, and "our copy" has to mean Drive for a claim the way it does for a
document. This uploads any snapshot with no Drive id yet and records the
id in `data/external_sources/operator_snapshots_drive.yaml`.

**Cheap and additive.** The store is append-only, so a dated snapshot
never changes after upload: there is no rename to chase and no prune to
get wrong. A run with nothing new says so and stops.

**Before step 12, not after**, for the same reason step 11 is: the build
that publishes `index.html` reads the ledger, and a snapshot uploaded
after it renders with no link to our copy until the next release.

It never resolves a folder by name and never creates one as a side
effect. `dcp.drive.SNAPSHOTS_FOLDER_ID` is the destination; a 404 on it
stops the run rather than making a second folder. If that folder is ever
genuinely lost, `--create-folder` makes a new one and prints the id to
paste into `dcp/drive.py` — a deliberate two-step act, because creating
a folder as a side effect of a sync is how a second copy of the whole
archive came to exist.

Every id is read back from Drive and its md5 checked against the local
bytes before it is recorded. An upload that fails either check is
reported and not written, and the script exits non-zero.

### 12. Rebuild the artefacts against the new ledger, and re-sync them

**If a new notebook is being made, its URL must be in `dcp/drive.py`
before this build** — `NOTEBOOK_URL` is compiled into the reader, and
this is the build that publishes `index.html`.

**Do it at the start of the chain, not here.** A notebook's URL is
fixed when it is created and does not change as sources are added, so
Luke creates it **empty** before anything is built and supplies the URL
then (his solution, 2026-08-28). The apparent circularity — bundle
needs step 9, notebook needs bundle, reader needs notebook — dissolves:
only the *sources* wait on the bundle, and they can be uploaded at
leisure, even after deployment.

This stop remains as the backstop for when that was not done. The
failure is silent: last release's notebook still exists and still
opens, so a reader built without the update looks entirely correct and
sends the reporter to a stale corpus.


```sh
scripts/export_reader.py   --out data/exports/<build>/reader.html --phase <N> --publish index.html
scripts/export_handover.py --out data/exports/<build>/dc_handover_phase<N>.xlsx
scripts/drive_sync.py --sync data/exports/drive_staging
```

The reader prints what it found on the way past:

```
Our copy on Drive: 52,908 documents have a recorded Drive file id, covering every cited document
```

If that line names a number of cited documents with no id, step 11 did
not run or did not finish.

**One extra pass, and it converges.** The reader and the workbook read
their Drive links out of `.drive_sync_state.json`, so an artefact built
at step 7 carries the ledger as it stood *before* step 10 — and any
folder or findings CSV that step 10 created for the first time has no id
in it. Those render as "not yet synced to Drive" while sitting on Drive,
which is the failure mode of 2.2 in miniature: a link a reporter can see
is missing, about a file that is there.

The ordering is not a mistake to be fixed by moving step 7 later: step 9
has to copy the artefacts into the tree in order to upload them, so they
must exist first. The resolution is to build twice. It terminates
because re-uploading three files creates no new folders, so the second
sync finds everything else cached and the ledger does not move again.

**On the day this step was written, it fixed nothing** — and that is
worth keeping, because the reasoning looked sound. Five sites said "not
yet synced to Drive" after the first pass, the ledger lag explained it
neatly, and rebuilding against the new ledger changed the count by
zero. The cause was elsewhere: `site_stem` truncates a site key to 40
characters *after* sanitising it, and every lookup normalised the whole
key, so a long key could never match its own folder. That is fixed in
`export_handover._folder_key`.

The step still belongs here — an artefact built at step 7 genuinely
does carry the older ledger, and a folder created for the first time by
step 10 genuinely has no id in it. But the measurement that motivated
it was evidence for a different bug, and a step justified by the wrong
number is one somebody will quietly drop when the number stops
appearing. Run it because the ordering makes it necessary, not because
of five sites.

No `--prune` on the second sync: nothing has left the tree since step
10 pruned it, and a prune set computed against a tree nobody rebuilt is
a prune set nobody checked.

### 13. The Google Sheet

```sh
scripts/sheet_sync.py --dry-run     # what would change; writes nothing
scripts/sheet_sync.py
```

The Sheet is updated in place, never replaced: added and removed columns
are reconciled first, so the widths and wrapping somebody set by hand
carry across with them. Two shapes it cannot carry, and now **refuses**
on (exit 1, `--allow-drift` to override) rather than warning and
continuing:

- **A tab in the workbook that the Sheet does not have.** It is skipped,
  because a tab created by the API arrives unformatted; create it by
  hand once, format it, and it is then kept.
- **Reordered columns.** A move is a delete plus an insert, which
  discards the formatting of the column moved, so the reconciliation
  declines it and names the columns instead. The values would still be
  internally consistent, which is exactly why nothing would look wrong.

**Diff the site-key column against the Sheet before running this.** The
sync writes positionally — row N of the export lands on row N of the
Sheet, nothing keyed by site — so if the site list has changed order or
membership, a human's cell comment stays at its coordinates while a
different site slides underneath it. Luke confirmed on 2026-08-10 that
nobody has annotated the Sheet yet, so this cycle is safe; that will not
be true forever.

### 13a. The search bundles — notebook, Pinpoint and Giant

```sh
scripts/export_notebook_bundle.py --max-words 300000
scripts/export_pinpoint_bundle.py \
    --already-uploaded data/exports/pinpoint_bundle/_manifest.csv --jobs 12
```

**What the Pinpoint/Giant bundle contains, and why — the standing
policy** (moved here from the ROADMAP 2026-08-30; the decisions are
Luke's, 2026-08-28). Both tools take the same input, and it is **not**
the Drive `sites` folder: it is the derivative bundle from
`export_pinpoint_bundle.py`. Pinpoint has no folders — the namespace
is flat and zipped uploads are unsupported — so structure is discarded
by design and each filename carries `<site> — <application> — ` in
front of it. The bundle is a reduction, 130.6GB in 50,615 files down
to ~64GB in 42,647, under Pinpoint's 100GB-per-user quota:

- **Drawings are dropped deliberately — for Giant too** (5,536 files,
  9.5GB). Not a contradiction with `extract_text_corpus.py`, which
  extracts every drawing because plant layouts carry specifications
  prose never states: the two tools want different things. Giant's
  value is a hit *in context* with somewhere meaningful to jump to,
  and OCR of a plan yields scattered label fragments supporting
  neither. Extraction wants every scrap; full-text search wants
  documents that read. The drawing content is not lost — the deep
  read reads it and its findings surface on the site page. Giant has
  no quota and takes the reduced bundle anyway, for consistency: two
  search tools answering one query differently, with nothing on
  either page to explain why, would be worse. This means the drawings
  question is **one decision governing both** and must be revisited
  for both together or not at all.
- **Exact duplicates are removed by content hash** (2,432 files), and
  **types are sniffed rather than trusted**, which recovered ~450
  files including 237 Outlook messages of kind *Consultee Comment* —
  tier A, the class the methodology says disclosures live in.
- **The residual to keep in mind**: a reporter using Giant as a
  completeness check can still infer "not in the documents" from a
  drawing-only disclosure that never reaches it. The reader is where
  that content lives; the two must not be presented as
  interchangeable.

**These are in the chain now** (Luke, 2026-08-29). They were "off the
chain, optional, local", which is how the notebook came to be three
releases stale and Pinpoint and Giant four — nobody skipped them, they
were simply never on the list anybody worked through.

**Both must run after step 9**, which rebuilds the staging tree they
read. Run either against the previous release's tree and it produces a
bundle that looks current and is not.

**The notebook bundle has two ceilings that pull against each other.**
600 sources, and a per-source word limit that is 500,000 on paper and
lower in practice. A smaller `--max-words` buys safer documents and
spends the file allowance; a larger one does the reverse. Both numbers
are printed at the end of the run — check them every release.

2.10 went out at `--max-words 480000` and Gemini Notebook **failed on
roughly a tenth of the files, all of them the largest** (Luke,
2026-08-29). Two causes, both now fixed:

- the budget counted only the findings table, so part 1 — which also
  carries the site report — came out at **500,962 words**, over the
  notional limit;
- every site was exported, datacentre or not.

The default is now datacentre-classed sites only, which is what pays for
the smaller budget, and `--max-words` is a whole-document ceiling. At
300,000 that gives **428 sites → 584 documents, largest 299,807 words**.

**Excluding the other classes is worth less than it looks.** The 84
non-datacentre sites are 4.9% of the words: exclusion is worth about one
step of budget, 480,000 down to 300,000, and no more. It also costs the
**48 disguise suspects**, whose class description begins "no application
here is stated as a datacentre, and at least one could not be ruled
out — kept for exactly that reason". They remain in Drive, Pinpoint, the
workbook and the reader; it is only the notebook that stops answering
questions about them. `--classes all` puts them back, at a budget of
about 450,000. Decide it per release rather than inheriting it.

**584 of 600 leaves 16 documents of headroom.** The corpus only grows,
so this will need re-deciding — the next lever is accepting a larger
budget, or splitting the corpus across two notebooks.

**The bundle arrives pre-divided into upload folders** of 50, because
that is Gemini Notebook's per-upload limit — `01` … `12`. Upload each in
turn. `--batch-size 0` writes them flat.

**Uploading adds sources; it never replaces them.** A notebook that
already holds a previous release's documents must be emptied first, or
it ends up holding two versions of every site with nothing on the page
to say which is current.

**The reader counts 533 sites and this exports 428.** Both are right:
533 is 512 live sites plus 21 Barbour catalogue records for pre-planning
schemes, which have no planning application and so no documents to
export; of the 512, 428 are classed as datacentres.

**The Pinpoint bundle takes `--already-uploaded`**, pointing at the
manifest of what is already linked into Pinpoint. It skips those
documents before conversion — the manifest alone is enough, so the
previous bundle's 64GB does not need to be on disk — and numbers what
remains into fresh tranches after the highest the manifest records. At
2.10 that was tranche 4.

**Note that this command reads the file it overwrites.** The run writes
`_manifest.csv` at the end, so a crash after that write destroys the
record of which tranche each earlier document went out in — which is
what happened on the first 2.10 attempt. The script now copies the old
one to `_manifest.csv.prev` before writing. If both are somehow lost,
the tranche assignment is a pure function of the journalled rows and can
be replayed: filter `_journal.jsonl` to rows whose output is no longer
in `files/`, sort by `(site, application, pinpoint_filename)` and run
the same fill loop. That reproduced 12,709 / 14,022 / 15,555 exactly on
2026-08-29.

**Only the new tranche is built into `upload/`.** Earlier tranches stay
in the manifest — that is the record of what went out when — but their
files are deleted from `files/` once they are in Pinpoint, so they are
excluded from tranching and from the hard-link stage. If a run reports
`!! N files are in the manifest but not in files/`, the tranche it just
built is short and must not be uploaded.

**Both uploads are manual and are Luke's.** The bundles land locally;
nothing here touches Drive, the notebook or Pinpoint. And if a NEW
notebook is being made rather than added to, its URL must be in
`dcp/drive.py` before step 12 — see the stop there.

**Giant takes the same bundle as Pinpoint**, by choice rather than
constraint: it has no quota limit, but two search tools answering one
query differently, with nothing on either page to explain the
difference, is worse than one corpus reduced in a documented way.

### 14. Deploy and probe

**One surface, and it is not automatic.** The reader lives on Cloud
Run behind Guardian sign-in, and it changes only when someone runs its
script; it serves whatever `index.html` sits at the root of the
checkout it is run from, committed or not.

**EdgeOne publishes nothing.** Since 2026-08-26 its middleware is a
signpost — every path 302s to the Cloud Run host and it serves neither
the page nor the dataset. Merging a release PR therefore deploys
*nothing*; it records in git what was published. Three documents said
otherwise until 2026-08-29, including this one, because the middleware
changed and the deploy step did not.

```sh
./cloudrun/deploy.sh          # see cloudrun/CLOUDRUN.md
```

Run it from a checkout whose root `index.html` is the release you mean.
That is the whole coupling: no branch, no tag, no commit is consulted.
The script verifies the live deployment refuses anonymous access before
declaring success, so a failure there is the gate holding rather than
the deploy failing.

**What runs automatically, and what does not** (as of 2026-09-02).
`.github/workflows/checks.yml` runs on every push to every branch: the
no-database test suite, the two browser suites driving the committed
`index.html`, and the middleware tests. It publishes nothing and holds
no secret. No workflow deploys — the "publish button" (build, probe,
then wait for Luke's approval in a GitHub Environment) is designed on
the ROADMAP under Smaller things and is not built — so the deploy is
this step, by hand, every release. The one-time IAP wiring is
[cloudrun/CLOUDRUN.md](../cloudrun/CLOUDRUN.md); the script never
touches it.

Then the EdgeOne signpost. The probe still earns its place, but what
it proves has changed: not that a gate refuses content, but that the
redirect serves none. A deployment that serves nothing cannot leak the
dataset the way the double-slash bypass once did:

```sh
scripts/probe_gate.sh https://dc-review-gdn-hoyla.edgeone.app
```

22 paths plus a forged session cookie, unauthenticated from outside. A
browser with a session cannot show you this: `//index.html` once skipped
the middleware entirely and served the whole 7.4 MB dataset with a 200.
Exit 0 means every path was refused.

It proves the gate, not the deployment. The probe is refused like anyone
else, so it cannot tell you *what* was published — only that nothing is
reachable without a session. Checking the content needs a browser with
one.

Ran clean for phase 2 on 2026-08-10: 22 paths, all 303, forged cookie
rejected.

### 15. Tell the reporting team

Say what moved, what is still a floor, and that disagreements between
readers are kept rather than resolved. The reader's front page carries
the caveats; the note should point at them rather than restate them.

Each release writes its own list at this step. The three that phase 2
carried are kept as the shape of what belongs there:

- **Coverage is now stated over prose.** If anyone saw the earlier "78%"
  or "201 of 455 sites not fully read", those counted drawings the deep
  read skips by design. The prose figure is 99%, and 38 sites have
  anything outstanding.
- **`max_disclosed_mw` is gone from the DuckDB.** It has been replaced by
  four adjudicated columns and `power_figures_excluded`. Any query
  written against the phase 1 database needs adjusting.
- **The phase 1 artefacts are still on Drive and still carry the old
  column**, with West London Technology Park at 298,000 MW in it. They
  were kept deliberately so earlier citations keep resolving. A note
  beside them is worth more than withdrawing them.

---

## Still outstanding — Luke's, not the runner's

- ~~**Build and upload the notebook bundle.**~~ Step 13a of the chain
  since 2026-08-29. The 2.10 notebook was created empty on 2026-08-28
  and filled from the rebuilt bundle; 2.11 needed nothing added. What
  stays true: the upload is Luke's and manual, and a new notebook's URL
  must be in `dcp/drive.py` before step 12.
- **The Google Sheet's title.** Written of the phase-1 Sheet, which was
  titled `DC_handover_v2_phase1`; 2.8 replaced the Sheet
  (`WORKBOOK_SHEET_URL` in `dcp/drive.py`), so check the current one's
  title before acting. Renaming is safe: `sheet_sync.py` resolves the
  spreadsheet by id and only prints the title. The **tab** names are
  matched against the workbook's sheet names and must not change.
- **`dc_handover_phase1.xlsx` is not in the phase 1 archive folder** with
  its database; it is in a third folder. Both are untrashed and keep
  their file ids, so citations resolve either way.
- **The local phase 1 workbook no longer exists.** The workbook writer
  truncates its inode, so rebuilding under the phase 1 name overwrote it
  through the staging hard link. The Drive copy is the only one left,
  which is why `--prune` exempts the tree root.

---

## What is already done and needs no repeating

- Deep-read across the readable site universe, on OpenAI batch.
- Findings deduplicated (20,450 archived) and made idempotent by a unique
  index; the runner commits each document's findings and log row in one
  transaction.
- Six families of quantity-kind error corrected, with standing checks.
- Per-site findings CSVs built and synced (they need rebuilding for the
  adjudication columns, not inventing).
- Encrypted database backups, used successfully for a real recovery.
- The reader's phase 2 presentation changes: source-documents wording,
  "Coming shortly", methodology, dictionary, and an **Assistant's notes**
  tab.
- **Coverage is now stated over prose, not over every document held**
  (2026-08-11). The old headline read "37,991 of 48,191 analysed (78%)"
  and "201 of 455 sites are not yet fully read", which counted 5,751
  drawings the deep read skips by design and the objection letters it
  samples on purpose. Both were true and both read as a job a third
  done. Over the prose the deep read is actually for it is 36,743 of
  36,983 (99%), and 38 sites have any prose outstanding. The split comes
  from the methodology's own `deepread_select.classify_kind` — tier
  `skip` graphical, tier `C` sampled, A and B prose — via
  `site_profile.load_coverage_detail`, so the reader and the workbook
  cannot drift on which rows are provisional. The undivided ratio is
  still shown, next to what it excludes.
- **The reader's package section links to the tabs.** A user read the
  "this page" badge as "everything is on the screen in front of you" and
  missed the other tabs entirely; the badge now says "this web portal"
  and each named component is a link.

## Decisions outstanding — Luke's, not the runner's

- **Ocean Estates and Manor Farm** cluster applications from different
  planning authorities. Site definition, not a data fix.
- **`power-1.1`** is committed but inert. Selecting it re-adjudicates the
  whole corpus (~$20–40) and it is **unvalidated** — the 229-figure
  ground-truth set exists to test it against the known-bad cases first.
- **Repository visibility.** The cohorts file, the DC01 lead and the
  operator watch-list sit in a public repo.

## Traps, each of which cost time today

- **Run operational commands from up-to-date `main`.** A collect run from
  a feature branch forked minutes before a fix mis-tagged 122,235
  findings. Branches are for editing; main is the runtime.
- **PostgreSQL regex: `\y` is the word boundary, `\b` is a backspace.**
  A predicate written with `\b` matches nothing, silently. It demoted 261
  rows instead of 116 and needed a restore.
- **Never a literal space before a digit in a predicate.** PDF text reads
  `"Substation       25.4m²"`. Use `\s+`.
- **Summing overlapping predicates is not counting distinct rows.**
- **Escape `%` in the adjudication prompt.** It is applied with
  `%`-formatting, and the prompt cites `"80%% - 480W"` as an example.
- **`git add` failing with "did not match any files" means the file is on
  another branch.** Do not drop it from the commit; go and find it. That
  is how `sweep_null_capacity.py` went missing for six hours.
- **A lock error or a `.wal` beside a DuckDB file means a writer may be
  ALIVE — check before touching anything.** `lsof <file>` names the
  process holding it; if one exists, wait for it, and if none does, open
  the file with duckdb so the WAL is replayed and merged — deleting the
  WAL discards committed work, and deleting "the stale file" can pull it
  out from under a running export. Both happened on 2026-08-27, minutes
  apart, to the same 2.9 build: the lock the release diff hit was the
  export still writing, and the "stale" WAL removed to clear it was
  live. `export_duckdb.py` now builds to a `.building` sibling and
  renames on completion, so a database at its final name is finished by
  construction and a `.building` file says exactly what it is — but the
  check-for-a-writer habit is the general form, and it applies to
  anything a lock protects.
### The notebook bundle, in detail (the step is 13a, not off the chain)

```sh
scripts/export_notebook_bundle.py            # -> data/exports/notebook_bundle/
```

Step 13a of the chain since 2026-08-29. It writes a local folder for
hand-uploading to a Gemini Notebook and touches nothing else — not
Drive, not the database, not the staging tree it reads. **It exports
datacentre-classed sites only by default** (`--classes all` for the
rest), which is what pays for the per-document word budget; the
disguise suspects, the procedural-only and adjacent-power sites and the
no-planning-record rows stay on Drive, in Pinpoint, in the workbook and
in the reader, and are not in the notebook.

One document per datacentre-classed site: the site report as written,
then that site's findings as a markdown table beneath it. The Drive tree keeps them
apart, which is right for a folder and wrong for a notebook — 429 sites
would arrive as 726 sources against a 600 limit, and a CSV uploaded as a
source reads poorly.

It reads the staging tree rather than the database on purpose, so the
report prose has exactly one implementation and the notebook cannot
drift from the Drive folder. **Run it after step 9**, which is the step
that rebuilds that tree — an earlier note here said step 5, which would
weld in the *previous* release's prose and produce a bundle that looks
current and is not.

#### Replacing or refreshing the notebook

Two paths, and the choice is made before anything is built.

**Replace — a new notebook.** What 2.10 did. Saved notes are lost, so
prefer it when they are stale anyway.

1. Create the notebook **empty** and take its URL. A notebook's URL is
   fixed at creation and does not change as sources are added, so this
   can be done before the chain starts.
2. Put it in `NOTEBOOK_URL` in `dcp/drive.py` **before step 12**, the
   build that publishes `index.html`. Doing it at step 1 is easiest.
3. Build the bundle after step 9; upload before deployment.

**Refresh — add to the notebook already in use.** Keeps the notes, and
the URL never changes, so nothing in the code moves.

Use `--only KEY [KEY …]` or `--only-from FILE` to build just the sites
being added. The prune is suppressed when filtering, because a partial
build must not delete the sites it was not asked for.

**Only ever add a site the notebook does not already hold.** Uploading
a document for a site already in it adds a *second* source rather than
replacing the first, and the notebook then holds two versions of one
site with nothing on the page to say which is current — worse than the
staleness being fixed. To update a site already present, delete its
source first.

**Working out what is new is the hard part, and the database cannot
tell you.** `sites.materialised_at` is rewritten for every site on
every materialisation, so it records the last run and not creation —
after a materialisation all 508 sites read the same date. Two workable
routes:

- read the notebook's own source list and diff against it, which is
  exact; or
- diff site keys against a previous release's DuckDB in
  `data/exports/phase<N>_build/`, which under-counts if that release
  postdates the last upload. Under-counting leaves a site stale rather
  than duplicated, which is the safe direction. As measured on
  2026-08-28: the 2.2 build held 430 sites against 508 live, 95 added
  and 17 gone.

The 17 gone are the other half of a refresh: sites the notebook still
holds that no longer exist. They do not disappear on their own, and
nothing but deleting their sources will remove them.

Big sites are **split, never truncated**: a source is capped near
500,000 words and one site holds 130,092 findings. Parts are budgeted by
word count rather than row count — a row-based cap set from an estimated
40 words per row put 49 documents over the limit, because the real
average is ~52 and varies with quote length. 429 sites become 506
documents. Every part repeats the site name, the key, its part number
and a line saying every row belongs to that site: one document is always
one site, but a model retrieving a row from the middle of a
400,000-word table has only what is on the page.

