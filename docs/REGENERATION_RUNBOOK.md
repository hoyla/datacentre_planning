# Regenerating the release

Written 2026-08-10 evening mid-flight and updated after the 2.1 run on
2026-08-11, for whoever runs the regeneration — including me in a fresh
session. It assumes nothing about what you remember.

Read [SESSION_HANDOVER.md](SESSION_HANDOVER.md) for the phase 1 context
and [HISTORY.md](../HISTORY.md) for why the pipeline is shaped this way.
This covers only the regeneration chain and what is easy to get wrong in
it.

---

## State — phase 2.1 regenerated, 2026-08-11

**Every step is done except the deploy, which happens when the release
branch merges** — EdgeOne builds from git, so writing `index.html` is not
publishing it. The gate probe is only meaningful after that merge.

The next regeneration starts at step 1 again; read the steps for the
order, which is 1–4, then 7, then 5, then 6, 8, 9.

Step 7 comes before step 5 deliberately: `build_drive_staging.py` copies
the release artefacts into the Drive root, so building the tree before
the exports stages the *previous* release's workbook and database.

**And check which release folder it took.** Its `--release-dir` used to
default to a hardcoded `phase2_build`, so the 2.1 run staged phase 2's
workbook and database beside 2.1's per-site files and said so in a line
nobody would think to doubt. It now defaults to the most recently
written `data/exports/*_build` and prints which one it chose.

| | |
|---|---|
| Reading | **stopped for a clean boundary** — the Studio reader was killed with TERM so nothing was written under the exports |
| Documents | 55,678 held; **36,744 prose analysed (99%)**, 0 applications with reading outstanding |
| Excluded on purpose | 5,751 drawings, 1,248 of 5,457 objection letters sampled, 226 held but wordless |
| Findings | 1,027,946 rows over 884,495 distinct passages |
| Adjudications | **14,780** — every capacity figure at the boundary is adjudicated |
| Release | `data/exports/phase2.1_build/`, artefacts named `phase2.1` |
| Drive | 2.1 artefacts synced; phase 1 and phase 2 artefacts still at the root, Luke archiving the phase 2 pair by hand |
| Backup | `dcp_2026-08-11T1130.dump.gpg`, 134 MB, verified, on Drive |
| Deployed | **not yet — on merge** |

**Versioning was set aside deliberately this time.** The rule is that a
release lands beside its predecessor so a citation of the phase 2
workbook keeps resolving. For 2.1 Luke overrode it knowing the user
state: the Google Sheet is being refreshed in place anyway, nobody is
using the phase 2 workbook or database, and the person who wants the
database has not opened any version. The cost, stated once because it is
invisible until someone hits it: a citation of "the phase 2 workbook" no
longer resolves to the file that produced those numbers.

**The largest figures, stated carefully, because getting this wrong is
the standing hazard of this dataset.** Largest disclosed IT load is
**Elsham Wolds at 1,000 MW**; largest total site demand is
**Northumberland Energy Park (Cambois) at 1,100 MW**.

The largest single row carrying `verdict='site_capacity'` is **1,200 MW
at Camilla Road, and it is a `thermal_input`** — fuel entering a plant,
two to three times the electricity leaving it. An earlier version of this
table called it the dataset's largest site capacity, which was wrong, and
wrong in exactly the way the `thermal_not_electrical` correction exists
to prevent. **`verdict='site_capacity'` alone does not mean "an
electrical capacity".** It means the figure is about this development;
`quantity_type` says what kind of quantity it is, and `thermal_input` and
`energy_storage` are both in there. Filter on both, always. The three
exports do; a `max(value_mw)` typed at a psql prompt does not.

What happened in steps 1–4:

- **Adjudication is complete.** The final batch ran at `medium` effort
  with a 16,000-token ceiling: 158 of 158 finished cleanly, no
  truncation, $5.91. 18 figures across 7 applications remain
  unadjudicated — findings that arrived after the cohort was built, not
  worth a batch.
- **127 corrections applied**, and that number is the answer to "would a
  replay reintroduce the errors": across 9,692 newly adjudicated figures
  the unchanged prompt recreated 43 storage-as-generation, 47 headerless
  table rows, 32 thermal inputs, 3 equipment labels and 2 temporary
  supplies. About 1.3%, all caught mechanically. Re-run is a no-op and
  the export gate is satisfied.
- **The correction script had a bug that only fired tonight**: rule notes
  were interpolated into SQL and one contains an apostrophe. It had run
  clean before only because that rule matched zero rows. Now bound as a
  parameter.
- **The West London figure was read, and it was wrong.** Resolved
  2026-08-11; nothing further to do. The quote is paragraph 32 of the
  PL/21/4429/OA appeal decision: "the urgent need for data centres up
  until 2027 (this proposal would contribute of 2240MW towards this
  need)". The text layer is not damaged — the sentence is simply broken
  ("contribute of") in the Inspector's summary of the Council's case.
  The same document settles it three times over: paragraph 59, "The
  total power requirement of the appeal proposal is anticipated to be
  147MW"; paragraph 37, "The 147MW, which the appeal proposal will
  deliver"; paragraph 59 again, "would deliver around 147MW towards the
  anticipated demand of 1730MW in the SAZ". The nearest real 2,2xx
  figure in the document is the appellant's London forecast of
  2,248MW–3,082MW at paragraph 21. So 2240 belongs to the need side of
  that sentence, not the contribution.

  Demoted to `unclear`, not to `market_context`: what the document rules
  out is that this is the proposal's capacity, not what the number
  counts. The adjudicator had itself reached `unclear` on one of its
  three passes over the same sentence. The site now reads 155 MW
  disclosed IT load and 342 MW theoretical maximum, and no longer holds
  the dataset's largest figure — see the state table above for what
  does, and for why the largest `site_capacity` row is not it.

  **A general rule was written for this and rejected on measurement.**
  "Demote a site_capacity figure whose document also holds one five
  times smaller, where the quote talks of need, demand or a forecast"
  matched 64 rows and was wrong on about 62: "Maximum power demand ≈ 450
  MW", "210MW IT capacity" and "an IT capacity of around 72 MW towards
  demand in the SAZ" are all real capacities. Need and demand are the
  ordinary vocabulary of a capacity statement. The correction is
  therefore pinned to the value and the sentence, is named
  `contradicted_by_own_document`, and lives in
  `correct_adjudications.py` rather than a migration because a
  re-adjudication would recreate it.

A caution about how it was found, because the first version of this
runbook got it wrong. The report flags four sites where IT load exceeds
the site's own stated total, and an earlier draft called that
*impossible*. It is not: ROADMAP already records that at multi-building
sites the two figures routinely come from different applications and
different scopes, and all four flagged sites are cross-application.
**Do not "fix" the other three.** The check is now called
`components-differ` and says so; only the magnitude of the West London
gap made it worth reading.

Everything else from step 3, for reference: 2 contradicted sites (both
known and genuine), 5 generation-understated, 2 clustering artefacts,
21 corroborated, 37 uncorroborated. Generation: 1,846 verdicts across 99
sites, **71% naming no fuel**, 61 of 99 sites disclosing none at all.
Null-capacity sweep: 65 fully-read sites with no capacity figure, 57 of
them with no power-unit text anywhere.

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

### 5. Rebuild the Drive staging tree — AFTER steps 2 and 7, never before

```sh
scripts/build_drive_staging.py
```

The per-site findings CSV carries four adjudication columns (*whose
figure is this?*, quantity type, adjudicated MW, quantity note). Built
before step 2, those columns carry uncorrected verdicts — a battery
rating labelled as this site's generation, in the artefact most likely
to be opened in Excel and sorted by the biggest number.

**And after step 7**, because this script copies the release's workbook,
database and reader into the Drive root. Run before them and the root
gets the previous release's artefacts beside the current release's
per-site files, which is how a reader ends up with a workbook and a
reader that disagree. The dependency is on `--release-dir`, which
defaults to `data/exports/phase2_build` and must be bumped with the
phase.

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

### 6. Sync to Drive, then verify at the far side

```sh
scripts/drive_sync.py --sync data/exports/drive_staging --prune --dry-run
scripts/drive_sync.py --sync data/exports/drive_staging --prune
```

`--prune` moves to the Drive bin every file this tool uploaded whose
local copy has gone — the stale twins left by the step 5 rename. It
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
scripts/verify_drive_sample.py --sample 30 --phase 2.1
```

That is the check, now a script rather than a described intention. It
fetches each file by id from the upload ledger and compares name, size
and md5 against the local copy, then walks the parent chain to confirm
it reaches the handover root. Release artefacts are always included on
top of the random sample, because checking only random files would pass
while the one thing everybody opens sat in the wrong folder. `--phase`
tells it which release is yours, so an older release's artefacts are
reported without failing the run.

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

### 7. Rebuild the artefacts — BEFORE step 5 stages them

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
scripts/export_handover.py --out data/exports/phase2.1_build/dc_handover_phase2.1.xlsx
scripts/export_duckdb.py   --out data/exports/phase2.1_build/dc_phase2.1.duckdb
scripts/export_reader.py   --out data/exports/phase2.1_build/reader.html \
                           --phase 2.1 --publish index.html
```

**Pass `--phase 2`.** The title, header, stamp and the database's own
filename in the reader all read from it; the default is still 1.

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

### 7a. The notebook bundle — optional, local, off the chain

```sh
scripts/export_notebook_bundle.py            # -> data/exports/notebook_bundle/
```

Not part of the release. It writes a local folder for hand-uploading to
a Gemini Notebook and touches nothing else — not Drive, not the
database, not the staging tree it reads.

One document per site: the site report as written, then that site's
findings as a markdown table beneath it. The Drive tree keeps them
apart, which is right for a folder and wrong for a notebook — 429 sites
would arrive as 726 sources against a 600 limit, and a CSV uploaded as a
source reads poorly.

It reads the staging tree rather than the database on purpose, so the
report prose has exactly one implementation and the notebook cannot
drift from the Drive folder. Run it after step 5.

Big sites are **split, never truncated**: a source is capped near
500,000 words and one site holds 130,092 findings. Parts are budgeted by
word count rather than row count — a row-based cap set from an estimated
40 words per row put 49 documents over the limit, because the real
average is ~52 and varies with quote length. 429 sites become 506
documents. Every part repeats the site name, the key, its part number
and a line saying every row belongs to that site: one document is always
one site, but a model retrieving a row from the middle of a
400,000-word table has only what is on the page.

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

It proves the gate, not the deployment. The probe is refused like anyone
else, so it cannot tell you *what* was published — only that nothing is
reachable without a session. Checking the content needs a browser with
one.

Ran clean for phase 2 on 2026-08-10: 22 paths, all 303, forged cookie
rejected.

### 10. Tell the reporting team

Say what moved, what is still a floor, and that disagreements between
readers are kept rather than resolved. The reader's front page carries
the caveats; the note should point at them rather than restate them.

For this release specifically, three things belong in that note:

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

## Still outstanding after the phase 2 release — Luke's, not the runner's

- **Upload the notebook bundle.** 506 documents sit in
  `data/exports/notebook_bundle/` (step 7a). The Gemini Notebook is
  linked from the reader already, so until they are uploaded the link
  leads somewhere emptier than the page implies.
- **The Google Sheet is still titled `DC_handover_v2_phase1`.** Renaming
  it is safe: `sheet_sync.py` resolves the spreadsheet by the id in
  `WORKBOOK_SHEET_URL` and only prints the title. The **tab** names are
  matched against the workbook's sheet names and must not change.
- **`dc_handover_phase1.xlsx` is not in the phase 1 archive folder** with
  its database; it is in a third folder. Both are untrashed and keep
  their file ids, so citations resolve either way.
- **The local phase 1 workbook no longer exists.** The workbook writer
  truncates its inode, so rebuilding under the phase 1 name overwrote it
  through the staging hard link. The Drive copy is the only one left,
  which is why `--prune` exempts the tree root.
- **A backup postdating the corrections has not been taken.** The most
  recent verified dump predates them. Two adjudication rows changed and
  the rule that changed them is in `correct_adjudications.py`, so it is
  reproducible rather than fragile — but the next `backup_db.py` should
  not be skipped.

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
