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

## WP-A — Make the snapshot store append-only — **DONE 2026-09-01**

Built as specced, with one departure recorded below: the same-day
suffix is `_2` and not `-2`, because `-` sorts *before* `.` and a
`-2` name would have sorted ahead of the day's first reading —
breaking the "lexicographic sort must equal chronological order"
requirement stated in the same bullet. `_` sorts after `.` and keeps
it. The resolver sorts on the parsed `(date, sequence)` rather than on
the raw name, so the property holds however the store is filled.

**Decided** (Luke, 2026-09-01; defect recorded in ROADMAP by PR #311):
`capacity_claims` keeps every reading of a claim, but
`scripts/fetch_operator_snapshots.py` wrote one file per slug and
overwrote it, so a superseded reading's evidence survived only in git
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

**Met.** All 81 files dated and none legacy, pinned by
`test_every_committed_snapshot_is_dated`; the fetcher's skip decision
is `held_digest` against `snapshot_path`, tested without a network;
`verify_operator_quotes`, `green_claims.verify_quotes` and
`require_held_snapshots` all pass against the migrated store; suite
1,181 passed, 1 skipped (1,167 collected on `main` before this, so the
15 new tests are the whole delta). **A re-run of the fetcher against
the live pages has not been made** — it needs the network and would
write a new dated file wherever a page has genuinely moved since
2026-08-30, which is a fetch to run deliberately rather than as a
test. The no-op property is asserted by test instead.

---

## WP-B — Sync the snapshot store to Drive — **DONE 2026-09-01**

Built as specced. The one open choice — new table or committed ledger —
was settled as a **committed YAML ledger**,
`data/external_sources/operator_snapshots_drive.yaml`, read by
`dcp/snapshot_drive.py`. The reasoning: `document_drive_files` is a
table because a document *is* a database row and its id is the key,
where a snapshot is a file in this repository cited by name from
committed YAML. Its Drive id is a fact about a committed artefact, so it
travels with it in git, survives a database rebuilt from migrations, and
is reviewable as a diff.

Folder `1NqIVr0y1aITvgAmQahatM3E4aCpBThlG`, `operator_snapshots` under
the handover root, in `dcp.drive.SNAPSHOTS_FOLDER_ID`. All 81 snapshots
uploaded and verified; re-running uploads nothing.

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

**Met, and checked at the far side rather than from the log.** Listing
the folder through the API: 81 files on Drive, 81 in the ledger, 81 held
locally, no name in any one of the three absent from the other two, and
every ledger id and md5 equal to what Drive reports and to the local
bytes. `files.get` on the folder returns the handover root as its only
parent. A second run reports "nothing to do".

---

## WP-C — Link snapshots from the reader and workbook — **DONE 2026-09-01, rendering awaits Luke**

**Decided in shape, Luke reviews the rendering**: each operator claim
(and green claim) renders a link to *our copy* — the Drive snapshot —
beside the source URL it already shows, exactly as documents carry the
Drive copy beside the register link. "Every finding is sourced" then
holds for the claims channel without a reporter needing to know the
repo layout. One emphasis difference, deliberate: for documents our
copy is the title link and "register" the quieter second, because
councils withdraw documents; for claims the published page stays the
primary link, because it is the citable source, and "our copy" is the
labelled second. Same pair, led by what a reporter cites.

*Spec sharpened 2026-09-01 by a Fable session after verifying WP-A, B
and D at the far side (store 84/84 dated, ledger 84/84 with every md5
matching local bytes, both quote gates clean, suite 1,207 green). The
premises below were read out of the code that day — re-grep before
trusting; line numbers drift.*

- An operator claim's `source_locator` **is** its snapshot slug —
  `load_operator_claims` sets `locator=c["snapshot"]`. NESO rows carry
  "row N", Companies House rows a filing locator, so resolving by slug
  naturally excludes them: resolve, and render nothing where
  resolution fails. Never guess a link.
- Two readings of one claim are two `capacity_claims` rows (the
  content key includes `value_original` and `as_at`), each carrying
  its own `as_at` and slug — per-row resolution is exactly what the
  append-only store was built for.
- Green claims (`operator-green-claims.yaml`) carry a slug and **no
  `as_at`** — they assert the current page, so they take the
  newest-file arm.
- The surfaces are five, not two: the site page's "Other power
  indicators" panel (the `site_claims` loop's `src` line, ~3781); the
  Operators tab's `_op_source` (~5086); the green-claims table's
  `_green_row` (~5275, which links the quote to `source_url`); the
  workbook's "Capacity claims" sheet (~1935) and "Figures by
  audience" sheet (~2013). Enumerate by grepping `source_url` in
  `scripts/export_reader.py` and `scripts/export_handover.py` rather
  than trusting this list.
- `dcp/snapshot_drive.py` already has `load_ledger()` and
  `url_for(filename)`; `dcp.drive.file_url` is the one viewer-URL
  shape. Do not hand-build a viewer URL — the two exporters that
  still do are a recorded ROADMAP item, not a pattern. No import
  cycle: `snapshot_drive` imports only `drive`, so it can lazily
  import the resolver from `capacity_claims`.

**The resolution rule, and why the quote is part of it.** A pure date
rule is not enough. The superseded CyrusOne LON1 reading (8.72 MW)
still stands as a `capacity_claims` row and **carries no `as_at` at
all**; it is in that table only, not in `operator-claims.yaml`, which
holds current readings. The store holds only the 2026-08-30 file that
reads 9 MW. So any date-only fallback would link the 8.72 row to
evidence stating 9 — the working-link-to-the-wrong-evidence failure
this whole chain exists to prevent. *(This paragraph read `as_at`
2026-08-20 until the row was checked against the database on
2026-09-01; corrected here rather than below, because a wrong figure
left standing with its correction ninety lines down is the thing
AGENTS rule 1 is about.)*

The discriminator is the claim's own verbatim quote, which is
in `attrs->>'quote'` on every operator and green claim: **a claim
links the file nearest its `as_at` in which its quote actually
appears, whitespace-normalised both sides as the gate does, and links
nothing otherwise.** Candidate order: newest dated file ≤ `as_at`,
then the post-`as_at` files oldest first (a reading routinely predates
the next re-fetch: CyrusOne LON1's current 9 MW is `as_at` 2026-08-28
against `cyrusone-lon1.2026-08-30.txt`, and the quote verifies there);
no `as_at` → newest first, then older. This also means
`verify_operator_quotes` does not change: its job is detecting that a
page has moved under the *current* YAML readings, which
verify-against-newest does exactly, and the link's honesty is
guaranteed by construction rather than by sharing the gate's
resolution.

Build, in one branch:

1. **The candidate order.** `snapshot_candidates(slug, as_at,
   snapshot_dir=OPERATOR_SNAPSHOT_DIR) -> list[Path]` in
   `dcp/capacity_claims.py` beside `snapshot_path`, returning held
   files in the nearness order above. Order by the parsed
   `(date, seq)` — `_snapshot_order` — never the raw name.
2. **One link helper, used by every surface.** In
   `dcp/snapshot_drive.py`: `copy_url(slug, as_at, quote) -> str |
   None` — first candidate whose text contains the
   whitespace-normalised quote (reuse `_norm_ws`), then filename →
   ledger id → `drive.file_url`. None when no candidate contains the
   quote **or** the winning file has no ledger entry: a claim must
   never render a guessed link — the `document_drive_files` argument,
   one layer up. Lazy-import from `capacity_claims`; no cycle exists
   in that direction. 84 small files read at most once each per
   build — cache reads per filename within the helper if the build
   feels it, and not before.
3. **The quote reaches the export.** `load_site_claims` and
   `load_claim_rows` add `cl.attrs->>'quote'` to their SELECTs. **If
   this step turns up a conflict the spec did not anticipate, stop
   and say so before working around it** (AGENTS rule 4).
4. **Reader wiring.** Beside each existing source link, when
   `copy_url` resolves: `· <a …>our copy</a>`, the document idiom's
   own vocabulary. Site claims panel: on the `src` line. Operators
   tab: appended to `_op_source`'s bits. Green table: after the
   linked quote (green claims pass `as_at=None`).
5. **Workbook wiring.** "Capacity claims" gains "Our copy (Drive)"
   after "Source URL"; same on "Figures by audience" (its comment at
   ~1980 explains what its Source column already points at — read it
   first). Column widths, and a dictionary entry for each new column
   in the same PR — the dictionary blocks start ~887.
6. **Tests.** The candidate order against a store holding several
   dated files and a same-day `_2` (as_at before / between / after
   the range, and None); `copy_url` picks the older file when only it
   contains the quote, returns None when no candidate does (the
   8.72 MW ghost-row case, which is the test that matters), and None
   for an unledgered file and an unknown slug; a built-page test on
   the `test_no_link_in_the_built_page_points_at_a_filesystem`
   pattern — every our-copy href in the built bytes names a file id
   present in the committed ledger.
7. **`release_diff.py` expectations**: claim-panel link counts rise;
   nothing falls. Say so in the PR body, with the grep list.

**Out of scope, deliberately**: the DuckDB's claims tables (a
follow-up if wanted — say so in the PR rather than folding it in);
the `site_facilities.py` relative-path defaults (ROADMAP's "latent
trap" — two lines, its own branch, and a good first branch for an
executor session); folding `export_handover.py` and
`export_duckdb.py`'s hand-built viewer URLs into `drive.file_url`
(ROADMAP, its own change).

**Done when**: every rendered operator/green claim whose evidence is
a held snapshot carries a working Drive link resolving to the file
its quote verifies in, counts verified in the release diff, and Luke
has seen the rendering before it ships — include the rendered claim
block for site 529 (Iron Mountain) or CyrusOne LON1's site in the PR
so that review has something to look at.

**Met on the build; the review is Luke's and is the one part left.**
80 of the 81 operator rows in the database and all six green claims
resolve, on all five surfaces — every committed YAML claim resolves,
the unresolved row being the database-only 8.72 MW ghost; the release
diff against a build of
`main` shows site-panel links 69,082 → 69,125, two workbook columns
and two dictionary entries added, nothing fallen. Full account in
HISTORY, "A claim links its own evidence".

**The worked example was wrong; the rule was right.** The spec's
bolded rule — a claim links the file nearest its `as_at` in which its
quote actually appears, and links nothing otherwise — is exactly what
was built, and the candidate order with it. What did not hold is the
CyrusOne LON1 example that rule rests on, in two ways, both read off
the database rather than reasoned about. **The paragraph itself is
corrected above**; this is what the corrections changed:

- **The row carries no `as_at`**, where the spec said 2026-08-20. So
  it takes the no-date arm and is offered the whole store
  newest-first, not the 2026-08-20 neighbourhood the example implies.
  It still links nothing, because no held file contains its quote —
  which is the point, and is why the rule survives a wrong premise
  about its own example.
- **That reading is not in `operator-claims.yaml` at all**, only in
  `capacity_claims`. So the YAML-level test asserts every committed
  claim resolves, and the ghost row is pinned by a fixture test
  instead — the shape of the tests, not just their fixtures, follows
  from this.

ROADMAP carried the same rule date-first, and is corrected there.

One extension beyond the spec's step 3, same shape and same purpose:
`operator_disclosure.load_divergences` gained `cl.as_at` as well as
the quote it already selected, because the "Figures by audience" sheet
is built from it and would otherwise have resolved without a date
while its four sibling surfaces resolved with one.

**Out of scope and still open**, as the spec directed: the DuckDB's
claims tables, `site_facilities.py`'s relative-path defaults, and the
two exporters' hand-built viewer URLs. All three are on ROADMAP.

---

## WP-D — Hold Iron Mountain's pages, then let its roster carry figures — **DONE 2026-09-01**

Three pages held (campus, `lon-1`, `lon-3`; `lon-2` 404s as expected),
five quote-verified claims, five matches to site 529, and all three
facilities carrying an `operator_roster` identity.
`reconcile_components()` reports the campus at 61 vs 60.7.

Two things the spec did not anticipate:

- **`ironmountain-lon1` was not a registered slug.** The spec said the
  three pages were "slugs the fetcher already registers"; only the
  campus and `lon-3` were. Added to `PAGES`.
- **Saunderton was not reconciling either.** ROADMAP calls it the exact
  self-audit and this document names it as WP-E's benchmark, but its
  four facility claims carried no `component_of`, so it never appeared
  in `reconcile_components()` at all. Fixed here, because WP-D's own
  stated outcome is "Iron Mountain beside Saunderton as self-auditing"
  and that could not be true while Saunderton was absent. It now
  reports 78.0 vs 78.0, exact.

The harvest route is generalised rather than one-off:
`fetch_operator_snapshots.py --from-file` stores browser-captured bytes
through the same `render()` a direct fetch uses, and records
`# obtained: browser` in the header. docs/PORTAL_NOTES.md carries the
rules.

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

**Met, all five.** `verify_operator_quotes`, `validate_operator`,
`require_held_snapshots` and `require_known_claims` all clean; the
site_facilities note now records the pages as held and carries the
page-versus-page divergence rather than the reason nothing could be
cited.

---

## WP-E — The ladder-rung design document — **DONE 2026-09-01, decisions await Luke**

**Met**: the proposal is
[docs/PLAN_OPERATOR_RUNG.md](PLAN_OPERATOR_RUNG.md), ending in seven
decision points and implementing nothing. It consumed every input
below, re-measured on 2026-09-01 rather than quoted — and one
measurement reshaped the design: the two sites the rung was raised
for both rank on *disclosed IT load at High confidence*, so no ladder
position fixes them; the answer is a default rung above the inferred
rungs plus hand-adjudicated scope displacement above disclosed ones.
The measurement also found a class nobody had enumerated: two sites
ranking ≥100 MW on a floorspace estimate while holding a first-party
figure of the same order, which the default rung repairs.

*The original spec, for the record:*

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
  the two self-auditing campuses as the benchmark for when
  `total: sum` is trustable — **both now measured, not asserted**
  (WP-D): `reconcile_components()` reports five campuses, Saunderton
  78.0 against 78.0 exact and Iron Mountain 61 against 60.7, with
  Kao, Slough and Stockley beside them. Re-run it for the document's
  numbers rather than quoting these.
- The audiences finding: count corporate-states/consultation-silent
  from `operator_pages.yaml` kinds and put the number in the document.
- **The Global Switch test** (2026-09-01, ROADMAP under #247): the
  "first constructible total" premise failed on measurement — each
  building states figures of more than one kind, and the proposed
  80 + 35 added a feasibility ceiling to a scheme headline while each
  building's other figure went unused. So the rung design must answer
  **which of a building's own figures a campus total may add** — a
  judgement per facility, recorded in the roster, never arithmetic.
- **The #250 measurement bounds the stakes** (2026-08-31, ROADMAP):
  the invisible class is exactly two sites today (Stockley, Cardiff),
  a third (Slough) pending its scope decision, and the register
  channel adds zero line-crossers — so the rung buys correctness on a
  handful of prominent sites, not a re-ranking of the corpus. The
  document should say so, because it sets how much complexity the
  design can justify.

**Done when**: a `docs/` design document is PR'd ending in decision
points for Luke, with no implementation. The decision points it must
reach, at minimum: what the labelled weight says and how it sits in
the ladder (the `w-modelled` precedent); whether a campus total and a
facility figure are different rungs (they are different realms —
`component_of` decided that for claims; the rung must not undo it);
whether `at_least_100mw` admits on a first-party figure with the
basis named, and what the cohort's `limits` then says; what renders
when operator and planning figures disagree (the divergence is the
finding); and the Pulsant estate — whether a facility with no
planning record can exist in the corpus at all before a site record
does.

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
