# Handover: the snapshot chain and its consumers

> A plan over ROADMAP.md, not a second roadmap: written 2026-09-01 so
> an Opus session can execute work whose design was settled in a Fable
> session that ran short of credits. **ROADMAP.md stays the inbox** —
> when a package lands, its ROADMAP item is updated in the same PR and
> the package below gets a DONE marker; when all are landed or
> abandoned, mark this file SPENT at the top the way
> `docs/HANDOVER_OPUS5.md` is. Everything here was agreed with Luke on
> 2026-08-31/2026-09-01; where a package says "decided", do not
> re-litigate it — the reasoning is in ROADMAP and the PR threads it
> cites (#310–#316).

Standing disciplines (they all bit within the last day):

- One change, one branch, each fresh from `main`; PR per package; PRs
  join board `gh project item-add 1 --owner hoyla --url <pr-url>`; no
  labels; no AI-attribution trailers.
- The pre-push hook refuses pushes to ready or merged PRs. Follow its
  printed recovery verbatim (draft → push → ready, or cherry-pick to a
  fresh branch). **Never pipe a state-changing command through
  `tail`/`head`** — a truncated refusal looks like a network error.
- `data/external_sources/neso-ea-register.xlsx` shows as modified in
  the working tree: that is Luke's own readability re-save,
  deliberately uncommitted. **Never `git add` it**; stage files
  explicitly, never `-A`.
- Verify environment before acting: `git branch --show-current`, PR
  states fresh from `gh`, figures re-derived live. Postgres is Docker
  on port 5433 (`docker compose up -d postgres` if down; exit 255 =
  machine slept).
- A probe must be shown able to see what it looks for. Yesterday's
  three failures were all truncated probes read as absence (a `head`
  on a psql result, a 2,500-char page read, a 429 read as
  page-missing). Related: content hidden in collapsed `<details>`
  accordions is in raw HTML but NOT in rendered text — prefer
  tag-stripping over `innerText` when capturing pages.

---

## WP-A — Make the snapshot store append-only

**Decided** (Luke, 2026-09-01; defect recorded in ROADMAP by PR #311):
`capacity_claims` keeps every reading of a claim, but
`scripts/fetch_operator_snapshots.py` writes one file per slug and
overwrites it, so a superseded reading's evidence survives only in git
(CyrusOne LON1, 8.72 → 9 MW). **Naming decided: `<slug>.<date>.txt`**
— date over content-hash because these are reporter-facing evidence
files heading for Drive, and a date sorts and means something where a
hash does not. The sha256 stays in the file header. A same-day second
change appends `-2` (then `-3`); lexicographic sort must equal
chronological order.

Build, in one branch:

1. **One resolver, used everywhere.** Add to `dcp/capacity_claims.py`
   beside `OPERATOR_SNAPSHOT_DIR`:

   ```python
   def snapshot_path(slug, snapshot_dir=OPERATOR_SNAPSHOT_DIR):
       """Newest held snapshot for a slug, or None."""
       dated = sorted(snapshot_dir.glob(f"{slug}.*.txt"))
       if dated:
           return dated[-1]
       legacy = snapshot_dir / f"{slug}.txt"   # pre-migration name
       return legacy if legacy.exists() else None
   ```

   Route every existing resolution through it — the full inventory,
   verified by grep on 2026-09-01 (re-grep before trusting):
   - `dcp/capacity_claims.py` `load_operator_claims` (~line 330, URL
     header read) and `verify_operator_quotes` (~line 389).
   - `dcp/green_claims.py` `snapshot_url` (~line 155) and
     `verify_quotes` (~line 194) — import the resolver lazily inside
     the function, matching the repo's lazy-import idiom.
   - `dcp/site_facilities.py` `require_held_snapshots` (~line 188).
   Nothing else reads snapshot paths; `scripts/export_reader.py`
   touches snapshots only through these modules.

2. **The fetcher skips unchanged content.** In `snapshot()`: fetch
   bytes, hash them, resolve the newest existing file for the slug,
   parse its `# sha256(html):` **or** `# sha256(pdf):` header (both
   exist since PR #310), and if equal, print "unchanged" and write
   nothing — an unchanged re-fetch must be a byte-level no-op
   (principle 5). Otherwise write `<slug>.<YYYY-MM-DD>.txt`, suffixing
   `-2` if that name exists. Update the module docstring, which
   currently promises overwrite-in-place ("a failed page leaves its
   previous snapshot in place" stays true and gets truer).

3. **Migrate the 81 committed files** in the same PR: for each
   `<slug>.txt`, read its `# fetched: <date>` header and `git mv` to
   `<slug>.<date>.txt`. Script it; do not hand-move 81 files. Keep the
   legacy fallback in the resolver anyway — it makes the migration
   safe to review rather than load-bearing.

4. **Tests.** The resolver picks the newest of several dated files and
   falls back to legacy; the fetcher's skip decision (extract it as a
   pure function so no network is needed); `verify_operator_quotes`
   and `green_claims.verify_quotes` still pass against the migrated
   store; `tests/test_capacity_claims.py`'s component fixtures
   reference snapshot `cyrusone-lon1` and must keep passing.

5. **Carry the docs**: ROADMAP's "snapshot store is mutable" item
   (search "The snapshot store is mutable") gets its step 1 marked
   done; `data/priors/site_facilities.yaml`'s header mentions
   snapshots — check it needs no change (it names slugs, not paths).

**Done when**: the store holds only dated files, a re-run of the
fetcher writes nothing new, all quote verification passes, and the
suite is green (`pytest -m "not integration" -q`; 1,162 passed at last
run).

---

## WP-B — Sync the snapshot store to Drive

**Decided**: snapshots get their own folder on Drive beside `sites`
(Luke's framing: evidence files journalists may need to look at, so
"our copy" means Drive, consistent with every other evidence class).
**Blocked on WP-A** — syncing the mutable store would put an "our
copy" link on evidence a claim no longer matches.

Constraints that are settled law here, not choices:

- **Drive is addressed by ID, never by name or path**
  (`dcp/drive.py` holds the root `FOLDER_ID`; the memory and README
  both record the duplicate-archive incident). Create the snapshots
  folder through the pipeline, store its ID as a constant in
  `dcp/drive.py`, and `files.get` the created ID back, stopping on
  404 — under the `drive.file` scope a name query cannot see hand-made
  folders and would silently create a duplicate.
- **Record per-file Drive IDs at upload, keyed by snapshot filename**,
  on the `document_drive_files` precedent (append-only; recorded at
  the moment of upload, verified, read back by key; the derivation
  deleted rather than kept as fallback). Whether that is a new table
  or a committed ledger file is the implementer's proposal — but the
  reader must be able to resolve `<slug>.<date>.txt` → Drive ID
  without deriving anything.
- The scope stays `drive.file`. Never widen it.
- Dated files never change after upload (WP-A guarantees it), so the
  sync is pure addition — simpler than `drive_sync.py`'s
  rename-and-prune problem. Reuse its client machinery, not
  necessarily its ledger.

**Done when**: every dated snapshot has a Drive ID recorded, re-running
the sync uploads nothing, and the folder is visible under the handover
root.

---

## WP-C — Link snapshots from the reader and workbook

**Decided in shape, Luke reviews the rendering**: each operator claim
(and green claim) renders a link to *our copy* — the Drive snapshot —
beside the source URL it already shows, exactly as documents carry the
Drive copy beside the register link. "Every finding is sourced" then
holds for the claims channel without a reporter needing to know the
repo layout.

- Resolution: claim → `snapshot` slug → newest dated file **at claim
  `as_at`** where the claim has one (the whole point of WP-A is that
  older readings keep older evidence; a claim read 2026-08-20 links
  the snapshot that existed then, not today's), else newest overall.
  Put that rule in `snapshot_path` or a sibling, tested.
- Wire into `scripts/export_reader.py`'s claims panel (the
  `site_claims` loop, ~line 3722) and the workbook's claims sheet;
  both read through `load_site_claims`, which may need the slug added
  to its SELECT (`cl.source_locator` already carries it — verify).
- `release_diff.py` will report the new links; expected direction is
  a rise in claim-panel link counts and nothing falling.

**Done when**: every rendered operator/green claim carries a working
Drive link to the snapshot supporting it, counts verified in the
release diff, and Luke has seen the rendering before it ships.

---

## WP-D — Hold Iron Mountain's pages, then let its roster carry figures

Independent of A–C. All context: ROADMAP "Iron Mountain: the block is
a bot block" (search that phrase — the FAQ passage is quoted there
verbatim), plus the site_facilities Iron Mountain entry and PR #314.

- `ironmountain.com` 429s **site-wide** to scripted clients; a real
  browser passes. Route: the browser-assisted capture
  (`scripts/browser_receiver.py`, rules in `docs/PORTAL_NOTES.md`) or
  any capture that saves **raw HTML** — then produce the snapshot with
  the fetcher's own `visible_text()`/`structured()` functions so the
  format matches the store. **Never capture via rendered text**: the
  per-facility figures sit in a collapsed `<details>` accordion that
  `innerText` silently omits — that exact mistake produced a wrong
  "published nowhere" finding on 2026-09-01.
- Pages, as slugs the fetcher already registers: the London campus
  page, `lon-1`, `lon-3` (LON-2 has no page — 404 — and needs none).
- Then, per what each page states (campus FAQ: LON-1 8.7 MW / LON-2
  27 / LON-3 25 / campus 61; lon-1 page: 8.75 MW; lon-3 page: 25):
  claims in `operator-claims.yaml` with `component_of` linking
  facility rows to the campus claim, quote-verified, matched to site
  529 (verify live first). **The 8.7-vs-8.75 and the three
  conflicting floor areas are recorded as what each page states — the
  divergence is the finding, never averaged.** LON-2's 27 MW note
  should cite the 2021 investor-relations corroboration (URL in
  ROADMAP/PR #313).
- Then the facility prior: LON-1 gains an `operator_roster` identity
  (it is currently absent with its reason in the entry's note —
  rewrite that note), and the three facilities gain claim-referencing
  attributions. `reconcile_components()` should then show Iron
  Mountain beside Saunderton as self-auditing (60.7 vs 61, rounding).

**Done when**: three snapshots held, claims loaded and verified,
roster attributions in, `reconcile_components()` reports the campus,
and the site_facilities note no longer says the figures are uncitable.

---

## WP-E — The ladder-rung design document (proposal only; decision is Luke's)

Unchanged in scope from ROADMAP ("Operator pages and typed standing —
what remains", first bullet) and the SPENT `HANDOVER_OPUS5.md` WP4
spec, which is still the fullest statement of what the document must
answer. What is **new since that spec was written**, and must be
consumed as inputs:

- The WP2 measurement (HISTORY/ROADMAP, PR #308): exactly **two sites
  today cross the 100 MW line on a first-party operator figure**
  (Stockley 24 → 112.5, Cardiff 67.2 → 148), a third (VIRTUS Slough,
  ranked on nothing vs 145.5) when its campus scope resolves; the
  register channel adds zero, so tier-and-count loses nothing there.
- `component_of` and `reconcile_components()` (PR #312): the rung
  design must say which realm's figure fills the cell — a campus
  total and its facility components are different rungs, never
  summed together.
- The facility prior and its seeds (#309/#310/#314/#316), including
  the two self-auditing campuses (Saunderton exact; Iron Mountain
  pending WP-D) as the benchmark for when `total: sum` is trustable.
- The audiences finding: count corporate-states/consultation-silent
  from `operator_pages.yaml` kinds and put the number in the document.

**Done when**: a `docs/` design document is PR'd ending in decision
points for Luke, with no implementation.

---

## Small items, each its own branch if picked up

- Run `scripts/load_capacity_claims.py` at the next release per the
  runbook — it picks up the five NESO matches (#307), the Saunderton
  facility claims (#310) and the `component_of` attrs (#312; the
  loader's `DO UPDATE SET attrs` refreshes existing rows).
- The Kingsnorth 47,405 kW leading/lagging pair is still a person's
  row (ROADMAP).
- ROADMAP's "8.7 + 27 + 25 = 60.7" for Iron Mountain predates the
  campus-page FAQ being read; it was right, but its original source
  was never established — WP-D's snapshots make it citable and moot.
