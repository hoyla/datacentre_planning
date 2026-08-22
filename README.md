# UK Data Centre Planning

A systematic national dataset of UK data-centre planning applications,
built for investigative journalism at the Guardian. It answers questions
the planning system records but does not collect: how much power these
sites will draw, what generation they propose on site, how they will be
cooled, and who is behind them.

**What it holds today:** 429 sites plus 26 known only at pre-planning
stage, 1,709 planning applications, 55,678 documents from council
registers, and a layer of 197 nationally significant energy projects for
adjacency. The analysed and findings counts are deliberately not repeated
here: the corroboration pass is still writing rows, so they move — and a
hand-copied number in a readme is a number that is wrong by the following
morning, as this one was, by roughly a factor of two.
`scripts/corpus_stats.py` prints the current figures, and every published
release states the boundary it was stamped at.

The output is a handover package, not a live service: a reader, a
workbook, a queryable database, and the source documents themselves.

- [ROADMAP.md](ROADMAP.md) — what is still to do.
- [HISTORY.md](HISTORY.md) — what has been built and decided, including
  what was tried and rejected.
- [ARCHITECTURE.md](ARCHITECTURE.md) — schema, pipeline philosophy, the
  seven principles the design is held to.
- [docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md) — how to reach the
  council registers that ordinary HTTP cannot.
- [docs/MAC_STUDIO.md](docs/MAC_STUDIO.md) — the machine that runs the
  long deep-reads: how to reach it, start it, and tell whether it is
  actually working.
- [docs/BACKUP.md](docs/BACKUP.md) — the database is the part that
  cannot be re-fetched. How it is dumped, encrypted, verified and
  rehearsed, and where the copies live.
- [docs/EXTERNAL_DATA_SOURCES.md](docs/EXTERNAL_DATA_SOURCES.md) — the
  other datasets that claim to measure data-centre capacity, what each
  one's MW actually is, and why none of them can be merged into a column
  here. Read before proposing a triangulation source.
- [docs/SCALE_RANKING_RESEARCH.md](docs/SCALE_RANKING_RESEARCH.md) —
  how to rank the 304 sites with no power figure well enough to choose
  fifty for manual corroboration, and a survey of sources not yet
  tried, each marked checked or unverified. Candidates for the
  EXTERNAL_DATA_SOURCES process, not conclusions.
- [DATA-LICENSING.md](DATA-LICENSING.md) — per-source upstream terms.
  Barbour ABI data is licensed and **requires credit** in published
  output.

---

## The principle everything else follows from

**Ingest broadly, analyse second.** A corpus assembled to prove a point
cannot produce a null finding. Applications are collected on a
deliberately wide definition and the editorial judgement applied
afterwards, to structured facts — so *these consented data centres
disclose no power figure at all* is a result the dataset can reach, and
not only the dramatic ones.

That finding has been **re-verified, and the re-verification is the
thing to cite rather than any number written here.** The original figure
of 71 sites was measured before the extractor could read Word, Outlook
and spreadsheet documents, and the regex sweep behind it was never
committed — a cohort that could contain documents nobody had read yet,
checked by an analysis nobody could re-run. Both are fixed:
`scripts/sweep_null_capacity.py` builds the cohort from reading coverage,
separates sites genuinely stating nothing from sites merely unread,
prints the residue it cannot classify instead of waving it away, and
refuses to be authoritative while candidate figures await adjudication.
It writes a dated report naming every site and quoting every match it
could not classify. That report is local — `data/reports/` is not
tracked, because it quotes consultation material — so the citable object
is the script, and a published claim should rest on a run of it made
against the corpus as it stood, not on a number copied out of an earlier
one.

Two consequences run through the code:

**Every number walks back to a document.** Aggregate → site →
application → document → verbatim quote, with the portal URL, the fetch
timestamp and the model that read it. Every extracted quote is checked
against its source text before it is stored; quotes that fail are
rejected rather than corrected.

**An absence is never silently a zero.** A blocked portal and a council
that publishes nothing look identical to a scraper and mean opposite
things. Everything that can be empty records *why* it is empty, and
partly-read sites mark their findings as floors that further reading can
raise.

---

## Stack

- Python 3.12, Postgres, raw `psycopg2` — no ORM.
- Append-only throughout: `source_snapshots` preserves every fetch,
  interpretations add rows rather than overwriting, and content hashes
  make re-runs no-ops.
- Claude Sonnet 5 catalogues the universe. The deep read is split across
  three model families, all behind the same verbatim-quote gate, and
  every finding records which one produced it: GPT-5 on OpenAI batch
  (54%), Sonnet (34%), and Qwen 3.6 under MLX locally (12%).
- Reading the tier-A corpus twice, so that disagreements between models
  can be kept rather than resolved, is built but **not yet done** — it
  stopped at the 2.1 boundary and the corpus-wide comparison is the next
  release's deliverable.
- Document corpus on the local filesystem, mirrored to Google Drive by
  site and application.
- The published reader is one self-contained HTML file — no CDN, no
  build step, no runtime dependency beyond map tiles.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env

docker compose up -d postgres
for m in migrations/*.sql; do psql "$DATABASE_URL" -f "$m"; done

git config core.hooksPath .githooks   # push safety, see below
pytest                                 # full suite
pytest -m "not integration"            # no Postgres required
node --test tests/middleware.test.mjs  # the edge password gate
```

`.githooks/pre-push` refuses a push to a branch whose pull request has
merged, or is ready for review, printing the recovery. Draft PRs and
branches without one are unaffected.

## Building the handover

```bash
scripts/export_handover.py --out data/exports/phase2_build/dc_handover_phase2.xlsx
scripts/export_duckdb.py   --out data/exports/phase2_build/dc_phase2.duckdb
scripts/export_reader.py   --out data/exports/phase2_build/reader.html \
                           --phase 2 --publish index.html
scripts/build_drive_staging.py        # assemble the Drive tree
scripts/drive_sync.py --sync data/exports/drive_staging --prune
scripts/sheet_sync.py                 # refresh the Sheet, keeping its formatting
```

The artefacts carry the phase that produced them, and each release lands
beside its predecessor on Drive rather than on top of it, so a citation
of the phase 1 workbook keeps resolving. `--phase` is not cosmetic: the
title, the header, the stamp and the database's own filename in the
reader all read from it, and it still defaults to 1.

**The exports must run before `build_drive_staging.py`**, which copies
the release into the Drive root. Built the other way round, the tree
carries the previous release's workbook and database beside the current
release's per-site files.

`--prune` is needed whenever staged files have been renamed: the sync
uploads by path and never deletes, so a rename otherwise leaves the old
name on Drive beside the new one. It bins nothing at the tree root —
released artefacts accumulate on purpose. Dry-run it first.

`scripts/phase1_finalise.sh` runs that chain in dependency order once
acquisition and the Drive sync have finished.

**Drive is addressed by folder ID, never by name.** The OAuth scope is
`drive.file`, so the tool can only see files it created — a name lookup
finds nothing and silently creates a second archive. The ID lives once,
in [dcp/drive.py](dcp/drive.py), imported by both the sync and the
reader's links.

## Collecting

```bash
dcp index --source planit            # national keyword sweep
dcp index --source barbour --file <xlsx>   # licensed, credit required
scripts/fetch_outstanding.py --dry-run     # what is still to retrieve
scripts/fetch_outstanding.py               # retrieve it
```

Acquisition is strictly sequential at ≥2.5s per host, one HTTP client per
host so one council's rate-limit backoff cannot throttle the sweep,
round-robin across hosts, a three-strike circuit breaker, and a
wall-clock ceiling per application. An application is only recorded
complete when every document its register listed actually arrived; a
short fetch is `partial` and re-queued.

Portals that block automated clients are documented in
[docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md) and retrieved with a browser
where the site warrants it. No access control is ever circumvented, and
no human-verification challenge is answered.

## The published reader

`scripts/export_reader.py --publish index.html` writes the page to the
repository root, which is what the EdgeOne deployment serves. The
methodology and data dictionary are generated *inside* it from the same
queries as the data, so there are deliberately no markdown copies
alongside to fall out of step.

`middleware.js` is EdgeOne edge middleware matching every route, so the
page and its embedded dataset need a session before anything is served —
unlike a password prompt written into the page, where the data has
already reached the browser by the time it asks. Two variables are set in
the EdgeOne dashboard and never in the repository:

| Variable | Purpose |
|---|---|
| `DC_READER_PASSWORD` | shared password, 12 characters or more |
| `DC_READER_SESSION_SECRET` | cookie signing key, 32 or more |

Missing or too short and it answers 503. It fails closed deliberately: an
unset variable must never mean *serve it to anyone*.

**Probe it from outside after every deploy**, because a browser with a
session cannot show you this — a double slash once skipped the middleware
entirely and EdgeOne served the whole dataset with a 200 to anyone who
typed the extra slash:

```bash
scripts/probe_gate.sh https://<the-deployment>
```

22 paths — the bypass class, traversal and percent-encoded forms — plus a
forged session cookie. Exit 0 if every one is refused.

**The gate protects the deployment, not the repository.** EdgeOne builds
from git, so the reader is committed — and this repository is public, so
that file is readable from GitHub whatever the middleware does. The gate
stops a link being passed around; it is not a confidentiality control.
The material is public-register data plus credited Barbour ABI, which is
why that trade is acceptable here.

## Licence

Apache 2.0 for the code, © 2026 Guardian News & Media Ltd. Upstream data
carries its own terms — see [DATA-LICENSING.md](DATA-LICENSING.md).
Barbour ABI data is licensed for this use and requires attribution in
published output. Consultation responses are reproduced as councils
published them and contain objectors' names and addresses; personal
contact details are excluded throughout.
