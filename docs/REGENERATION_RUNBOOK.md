# Regenerating the phase 2 release

Written 2026-08-10 evening, mid-flight, for whoever runs the
regeneration — including me in a fresh session. It assumes nothing about
what you remember.

Read [SESSION_HANDOVER.md](SESSION_HANDOVER.md) for the phase 1 context
and [HISTORY.md](../HISTORY.md) for why the pipeline is shaped this way.
This covers only the regeneration chain and what is easy to get wrong in
it.

---

## State when this was written

| | |
|---|---|
| Branch | `adjudication-tail-ceiling`, 7 commits ahead of main |
| Documents | 55,678 held, **40,279 read** (was 18,645 this morning) |
| Findings | 1,019,389 rows / ~878,651 distinct passages |
| Adjudications | 6,916 |
| OpenAI spend | ~£528 + ~$14 of adjudication, inside the £600 ceiling |
| In flight | One batch: `batch_6a7a15db82a88190b819396b916b662d`, 150/158 |

**The deep-read is complete across the readable site universe.** There is
no tier D. What remains is adjudication of the tail and then the
regeneration itself.

---

## The chain, in order

The order is not cosmetic. Two steps must precede the artefacts or the
handover ships wrong numbers, and one of them is enforced in code.

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

### 3. Look at what moved

```sh
scripts/consumption_integrity.py
scripts/generation_integrity.py
scripts/review_large_capacities.py --min-mw 100
scripts/sweep_null_capacity.py
```

Reports land in `data/reports/` (gitignored — they name sites and quote
documents). You are looking for:

- **contradicted** sites — a grid connection materially below stated
  demand. Two are genuine and known (Watford Bypass, West London); more
  than that means something new to read.
- **generation-understated** — a single machine's rating standing in for
  a fleet. Five known.
- The null-capacity sweep prints **PROVISIONAL** and refuses to give a
  quotable number while any candidate figure is unadjudicated. If it
  still says that after step 2, step 1 did not finish.

### 4. Back up before rebuilding

```sh
scripts/backup_db.py
```

Encrypted, verified, uploaded. Needs `DCP_BACKUP_PASSPHRASE` in `.env`.
The database is the only irreplaceable artefact — documents are mostly
re-fetchable, the interpretive layer is not. This machinery was used in
anger once already today, to recover 248 rows from a migration that
demoted more than it should have.

### 5. Rebuild the Drive staging tree — AFTER step 2, never before

```sh
scripts/build_drive_staging.py
```

The per-site `_findings.csv` now carries four adjudication columns
(*whose figure is this?*, quantity type, adjudicated MW, quantity note).
Built before step 2, those columns carry uncorrected verdicts — a
battery rating labelled as this site's generation, in the artefact most
likely to be opened in Excel and sorted by the biggest number.

Still outstanding here, requested but not built: **site names in the
`_findings.csv` and `_site_report.md` filenames**, so the files stay
identifiable inside a NotebookLM collection. That rename needs a **prune
step in the sync** — `drive_sync.py` uploads by path and never deletes,
so renaming without pruning leaves ~700 stale twins beside their
successors. Do both together or neither.

### 6. Sync to Drive, then verify at the far side

```sh
scripts/drive_sync.py --sync data/exports/drive_staging
```

Then confirm by fetching a sample **through the API by file id** —
name, parent folder, and byte size against local. Do not trust the
sync's own counters: they looked fine on the day half the tree went into
a duplicate archive. There is a worked example of the far-side check in
the session transcript; the principle is that the ledger is the near
side and the API is the far side.

### 7. Rebuild the artefacts

```sh
scripts/export_handover.py --out data/exports/phase1_build/dc_handover_phase1.xlsx
scripts/export_duckdb.py   --out data/exports/phase1_build/dc_phase1.duckdb
scripts/export_reader.py   --out data/exports/phase1_build/reader.html \
                           --phase 2 --publish index.html
```

**Pass `--phase 2`.** The title, header and stamp all read from it; the
default is still 1.

Each of these calls the adjudication gate first, so if step 2 was
skipped they stop rather than shipping.

### 8. The Google Sheet

```sh
scripts/sheet_sync.py
```

**Diff the site-key column against the Sheet before running this.** The
sync writes positionally — row N of the export lands on row N of the
Sheet, nothing keyed by site — so if the site list has changed order or
membership, a human's cell comment stays at its coordinates while a
different site slides underneath it. Luke confirmed on 2026-08-10 that
nobody has annotated the Sheet yet, so this cycle is safe; that will not
be true forever.

### 9. Deploy and probe

Merging the PR is what deploys `index.html` via EdgeOne. Then:

```sh
scripts/probe_gate.sh https://dc-review-gdn-hoyla.edgeone.app
```

22 paths plus a forged session cookie, unauthenticated from outside. A
browser with a session cannot show you this: `//index.html` once skipped
the middleware entirely and served the whole 7.4 MB dataset with a 200.
Exit 0 means every path was refused.

### 10. Tell the reporting team

Say what moved, what is still a floor, and that disagreements between
readers are kept rather than resolved. The reader's front page carries
the caveats; the note should point at them rather than restate them.

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
