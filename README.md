# UK Data Centre Planning

A systematic national dataset of UK data-centre planning applications,
built for investigative journalism at the Guardian. It answers questions
the planning system records but does not collect: how much power these
sites will draw, what generation they propose on site, how they will be
cooled, and who is behind them.

**What it holds :** at the 2.9 boundary (2026-08-27), 499 sites
plus 25 known only at pre-planning stage, 2,034 in-scope planning
applications, 57,001 documents from council registers — 53,049 of them
staged for Drive at that boundary, the rest belonging to applications
reviewed and found not to be data centres — and a layer of 197
nationally significant energy projects for adjacency. 
_Last updated 27 August 2026_

The output is a handover package, not a live service: a reader, a
workbook, a queryable database, and the source documents themselves.

- [AGENTS.md](AGENTS.md) — what to read before working on a given part of
  this, and the three rules that stop the same mistakes recurring. Routing
  only; it restates nothing. Start there if you are picking work up.
- [ROADMAP.md](ROADMAP.md) — what is still to do.
- [HISTORY.md](HISTORY.md) — what has been built and decided, including
  what was tried and rejected.
- [ARCHITECTURE.md](ARCHITECTURE.md) — schema, pipeline philosophy, the
  seven principles the design is held to.
- [docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md) — how to reach the
  council registers that ordinary HTTP cannot.
- [docs/MAC_STUDIO.md](docs/MAC_STUDIO.md) — the machine that runs the
  long *corroboration* reads: how to reach it, start it, and tell whether
  it is actually working. Which reader gets which work is ARCHITECTURE's
  standing policy, not this file's; the local model is never a first
  read.
- [docs/MODELS.md](docs/MODELS.md) — which model reads what, and
  why: the comparisons that were run, the decisions made on them, and
  the ones still open. The roster with counts is ARCHITECTURE's.
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
  four model families, all behind the same verbatim-quote gate, and
  every finding records which one produced it: GPT-5 on OpenAI batch
  (52%), Sonnet (25%), Qwen 3.6 under MLX locally (23%), and GPT-5.6
  (<1%, from escalations).
- Reading the corpus twice, so that disagreements between models can be
  kept rather than resolved, is built and part-run — the corroboration
  pass has covered a substantial minority of its in-scope documents and
  is currently stopped — but the deliverable, the corpus-wide
  comparison in which a disagreement is the finding, **has not been
  produced**. ROADMAP holds the live fraction; it moves.
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
node --test tests/middleware.test.mjs  # the EdgeOne redirect
```

`.githooks/pre-push` refuses a push to a branch whose pull request has
merged, or is ready for review, printing the recovery. Draft PRs and
branches without one are unaffected.

## Building the handover

```bash
scripts/materialise_sites.py          # first: nothing else sees an unmapped application
scripts/export_handover.py --out data/exports/phase2_build/dc_handover_phase2.xlsx
scripts/export_duckdb.py   --out data/exports/phase2_build/dc_phase2.duckdb
scripts/export_reader.py   --out data/exports/phase2_build/reader.html \
                           --phase 2 --publish index.html
scripts/build_drive_staging.py        # assemble the Drive tree
scripts/drive_sync.py --sync data/exports/drive_staging --prune
scripts/record_drive_ids.py --verify-bytes   # where each document landed, by id
scripts/sync_snapshots_drive.py       # the claims channel's evidence, and its ids
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

**And the materialise must run before all of them.** A document is
staged if and only if its application has a live `site_members` row, so
an application the site map has not seen is not a stale row in the
handover — it is absent from it, and absent from the sync's candidate
set, and therefore invisible to the sync's `skipped` and `failed`
counters alike. `build_drive_staging.py` refuses to build against a site
map older than the universe, and prints the documents it did not stage
whether or not it refuses. See step 0 of
[docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md).

`--prune` is needed whenever staged files have been renamed: the sync
uploads by path and never deletes, so a rename otherwise leaves the old
name on Drive beside the new one. It bins nothing at the tree root —
released artefacts accumulate on purpose. Dry-run it first.

`scripts/phase1_finalise.sh` runs that chain in dependency order once
acquisition and the Drive sync have finished.

**Drive is addressed by ID, never by name.** The OAuth scope is
`drive.file`, so the tool can only see files it created — a name lookup
finds nothing and silently creates a second archive. The root folder ID
lives once, in [dcp/drive.py](dcp/drive.py), imported by both the sync
and the reader's links.

The same rule reaches down to individual documents.
`scripts/record_drive_ids.py` writes the Drive file ID of every uploaded
document into `document_drive_files` after each sync, and the reader and
workbook read document links from there. Nothing derives a location.
The export used to rebuild a document's expected staging path — site
stem, application reference, and a number counting the application's
documents in `fetched_at, id` order — and look that path up in the sync
ledger. It was correct, and verified content-addressed against the local
bytes. But rename a site or renumber an application's documents and the
lookup either finds nothing, silently dropping a link, or finds the
neighbouring file: a working link to the wrong document, under a
citation naming a different one. A Drive ID survives a file being moved
or renamed; a derived path survives nothing being renamed here.

**And it reaches the claims channel's evidence.** An operator's page has
no register behind it, so a capacity claim rests on a snapshot of the
page as it read on the day the figure was taken — held here, append-only
and dated, and since 2026-09-01 on Drive too, in `operator_snapshots`
under the handover root. `scripts/sync_snapshots_drive.py` uploads and
records each file's ID in
`data/external_sources/operator_snapshots_drive.yaml`, so "our copy"
means Drive for a claim exactly as it does for a document rather than
meaning a file in this repository.

**A claim links the file its own quote is in, not the newest one.** The
store keeps every reading of a page and `capacity_claims` keeps every
reading of a claim, and the two do not line up: CyrusOne LON1 read
8.72 MW on 20 August 2026 and 9 MW eight days later, with no
announcement on the page. Resolving a link by slug and date would put
the older row against evidence stating the newer figure. So each claim
links the nearest held snapshot in which its verbatim quote actually
appears, and links nothing otherwise — which is the honest answer for
that 8.72 MW row, whose own evidence was overwritten before the store
became append-only.

**Documents link to our copy first, with the register beside it.** A
council can withdraw a document from its register, renumber it, move the
portal or gate it, and all four have happened here — so the copy this
project holds is what the document title links to. The register keeps a
link of its own, because a figure that reaches print has to be
attributable to the public source. 512 documents also carry a `file://`
URL naming a path on the machine that ingested them; 401 of those
shipped as anchors in the 2.8 reader, and
`tests/test_reader_smoke.py::test_no_link_in_the_built_page_points_at_a_filesystem`
now reads the built bytes so that cannot recur.

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
repository root, which is what both deployments below serve. The
methodology and data dictionary are generated *inside* it from the same
queries as the data, so there are deliberately no markdown copies
alongside to fall out of step.

**Cloud Run (primary): Guardian Google sign-in.** The reader is served
from a private Cloud Run service behind Identity-Aware Proxy, so any
`@guardian.co.uk` account signs in with its normal Google login — no
shared password to distribute. Deploys are manual — no CI touches it:
after each export, `./cloudrun/deploy.sh`. The step-by-step runbook, the
one-time IAP wiring, the gotchas inherited from the meridian and tribunal
deployments, and the anonymous-access probes are all in
[cloudrun/CLOUDRUN.md](cloudrun/CLOUDRUN.md).

**EdgeOne (legacy): a redirect.** It serves nothing — every path 302s
to the Cloud Run URL above, so links colleagues saved keep working while
they drain. `middleware.js` is that redirect, and it is deliberately
unauthenticated: gating it would make someone type the old password to
be told where the reader went, and the destination fails closed anyway.
Deleting the deployment is a separate decision, once the bookmarks have
moved.

The shared-password gate the redirect replaced — HMAC-signed sessions,
the double-slash bypass it survived, the 22-path probe — lives in this
file's git history and in `middleware.js`'s own comments; nothing here
describes it as current because nothing about it is. The probe that
matters now is Cloud Run's: `cloudrun/deploy.sh` checks after every
deploy that the service refuses anonymous access, and fails the deploy
if it does not.

**Access control protects the deployment, not the repository.** This
repository is public and the reader is committed, so `index.html` is
readable from GitHub whatever the deployment does. Sign-in stops a link
being passed around; it is not a confidentiality control. The material
is public-register data plus credited Barbour ABI, which is why that
trade is acceptable here.

## Licence

Apache 2.0 for the code, © 2026 Guardian News & Media Ltd. Upstream data
carries its own terms — see [DATA-LICENSING.md](DATA-LICENSING.md).
Barbour ABI data is licensed for this use and requires attribution in
published output. Consultation responses are reproduced as councils
published them and contain objectors' names and addresses; personal
contact details are excluded throughout.
