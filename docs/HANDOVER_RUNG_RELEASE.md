# Handover: the operator rung, and release 2.11

> A plan over ROADMAP.md, not a second roadmap — the third of its kind,
> on the pattern of the SPENT `HANDOVER_SNAPSHOT_CHAIN.md`. Written
> 2026-09-02 for an Opus executor session, with every premise below
> verified against the code and the live corpus on 2026-09-01/02
> (re-grep before trusting; line numbers drift). **The design of record
> is [PLAN_OPERATOR_RUNG.md](PLAN_OPERATOR_RUNG.md), decided by Luke on
> all seven points — do not re-litigate any of them**; where this file
> and that one disagree, that one wins. ROADMAP stays the inbox: when a
> package lands, its ROADMAP item updates in the same PR; when all are
> landed or abandoned, mark this file SPENT.

Standing disciplines:

- Read [AGENTS.md](../AGENTS.md) first, and follow its rule 4: before
  going to find out how anything *outside this repository* behaves,
  say so in one line and let Luke see it. Everything internal is
  pre-answered below or answerable by reading this repo.
- One change, one branch, each fresh from `main`; PR per package; PRs
  join board `gh project item-add 1 --owner hoyla --url <pr-url>`; no
  labels; no AI-attribution trailers; stage files explicitly, never
  `-A`.
- The pre-push hook refuses pushes to ready or merged PRs; follow its
  printed recovery verbatim. Never pipe a state-changing command
  through `tail`/`head`.
- Verify environment before acting: `git branch --show-current`, PR
  states fresh from `gh`, figures re-derived live. Postgres is Docker
  on port 5433 (`docker compose up -d postgres` if down; exit 255 =
  machine slept). `DATABASE_URL` comes from `.env` (`set -a && source
  .env && set +a` before ad-hoc scripts).
- **Two stop points are Luke's and cannot be worked around**: he
  reviews the rung's rendering before anything deploys (decisions 2
  and 4 are conditionally decided on exactly that), and the release
  itself follows the candidate-then-release PR discipline, both PRs
  his to merge.

Order: R1 first (the rung's verification reads the database), R2 next,
R3/R5/R6/R7 any time **but all before R4**, R4 last. R2 is the only
large package.

*Status, 2026-09-02: R1 run (claims 264 → 273, matched 80 → 94,
verified against a build); R2 merged (#333) with the rendering review
passed; R3 merged (#331) and its sweep-sibling behind it (#332); R5
merged (#335); R6 built and open as #336, verified — its five tests
fail against the unfixed script, and the real 2.10-against-2.9 diff
run from outside the repository root finds both priors files. R7
below was found by #336's sweep and specced after it.*

---

## WP-R1 — Run the claims loader

`scripts/load_capacity_claims.py`, per its section of
[REGENERATION_RUNBOOK.md](REGENERATION_RUNBOOK.md) — read that
document **in full**, traps included, before running anything from it.
No API spend; idempotent.

What it should pick up, measured 2026-09-01: **nine operator claims
not yet in the database** (VIRTUS LONDON15–18 at Saunderton; the five
Iron Mountain claims), the `component_of` attrs on existing rows (the
loader's `DO UPDATE SET attrs` refreshes them), the five NESO matches
from the 2026-08-31 triage (Cato and Quest Park at `strong`, the two
Bro Tathan rows and Cottam Giga at `probable`), and the five Iron
Mountain matches to site 529.

**Done when**: the loader's own summary reports the inserts; a query
over `capacity_claims` joined to live matches shows the Iron Mountain
campus claim matched to site 529 and the Saunderton facility claims
present with `component_of`; and `operator_website` rows rise by nine
(81 → 90, the 81 including the CyrusOne 8.72 MW ghost that is in the
database only — see HISTORY, "A claim links its own evidence").

---

## WP-R2 — Implement the rung (decisions 1–5)

Everything about *what* to build is in
[PLAN_OPERATOR_RUNG.md](PLAN_OPERATOR_RUNG.md), including the exact
cell and basis-line wording of decisions 2 and 4 and the guards under
"The proposal". This package is the *where and how*, pre-verified.

**Premises, verified 2026-09-01/02:**

- The ladder is `dcp/site_scale.power_estimate` (~line 343), returning
  `PowerEstimate(value_mw, basis, confidence, caveat)` — **no weight
  field**. The reader derives the weight class from *confidence* at
  `scripts/export_reader.py` ~4024: `{High: w-stated, Medium:
  w-implied, Low: w-implied, Indicative: w-modelled}`. **The rung is
  Medium but must render its own `w-operator` class, so the class can
  no longer come from confidence alone** — either `PowerEstimate`
  gains a weight (or basis-key) field, or the mapping keys on basis.
  Pick one, and check `tests/test_design_conformance.py` and the
  caveat-coverage test for what they pin.
- Three consumers call the ladder and must agree: the reader,
  `site_cohorts.load_inputs`/`at_least_100mw` (`dcp/site_cohorts.py`
  ~231/~450), and the workbook (grep `site_scale` in
  `scripts/export_handover.py` — the 2.2 lesson was precisely that the
  reader and workbook disagreed for 43 sites when only one called it).
- The cohort registry entry (~line 613) carries `rule_version
  "2026-08-25.1"`. **The rung changes membership, so bump it.** The
  entry's `definition` prose narrates the ladder ("a disclosed IT load
  or total site demand first, then …") and must gain the rung; the
  `limits` prose gains decision 3's remedy sentence; the notes gain
  the operator-rung member count, on the floorspace-count precedent.
- **Eligibility lives in one function** (suggest
  `dcp/capacity_claims.py`, beside the loaders): matched, top-level
  (no `component_of`), `announced_capacity`, confidence `strong` or
  `probable`, latest reading per `claim_name`, and **exactly one
  distinct eligible `claim_name` for the site — otherwise the site is
  ineligible and panel-only** (the Global Switch lesson; the design
  says which figure is a per-facility judgement, not arithmetic).
- **Displacement entries pin claim name + expected value, not
  `as_at`.** The plan says pin by `claim_name` + `as_at`, but
  Cardiff's claim ("Vantage Cardiff campus", 148, term "critical IT
  load") carries **`as_at: None`** — measured, not assumed. So the
  entry pins `claim_name` and `expected_value_mw`, and the loader
  fails the build when the latest reading's value differs: the
  operator's figure moved, and the scope decision was about the old
  figure. That is *stronger* than the date pin and honours the same
  intent; note the departure in the PR the way WP-A noted `_2`.
- The displacement prior extends `data/priors/campus_scope.yaml`.
  Current schema per entry: `site_key / projects / proposed / scope /
  total / barbour_titles` (+ `reason` on reviewed ones); **all 35 are
  `unreviewed` and nothing reads the file yet — the loader is new
  code**, on the `site_aliases.yaml` contract: an unknown site key
  fails the build, an unknown claim name fails it, a moved value fails
  it. Two entries to write, with evidence in the `reason` the way
  `site_partitions.yaml` entries carry it:
  - `PTNO-12301553` (VIRTUS Stockley Park): planning's best is a
    disclosed IT load of 24 (the *VIRTUS LONDON7* commissioning
    milestone; site also holds total_site 22, generation 46.2);
    operator claim "VIRTUS Stockley Park campus", 112.5, `as_at`
    2026-08-30, roster five facilities of which three disclose on
    three bases (`site_facilities.yaml`, `reconcile_components()`).
    **Carry the LONDON5/LONDON7 wrinkle, do not resolve it** — the
    plan's Part 2 says how.
  - `PTNO-12489438` (Vantage Cardiff): planning's best is a disclosed
    IT load of 67.2 (also total_site 60, generation 50.44); operator
    claim "Vantage Cardiff campus", 148, "critical IT load", match
    evidence already written in `operator-claims.yaml`.
- **Docs the change makes stale — grep and carry in the same PR**:
  `planning-derived` in `scripts/export_handover.py` (~lines 20, 28,
  909, 959, 1733, 1957 — read each; the sentence "a register figure
  never becomes a site's number" stays true, the wider "the Sites
  sheet's power columns stay planning-derived only" does not); the
  ladder narrations (grep `standby-implied`, `Estimated from
  floorspace`, `Disclosed IT load` across `scripts/`, `dcp/`,
  `README.md`, `ARCHITECTURE.md` and the workbook dictionary); and
  ROADMAP's capacity-model section, whose #250 item this closes.
- **Expected artefact movement, for the PR body and the release
  diff**: exactly four sites-table cells change — East Havering
  580 → 600 and Westerhill 150 → 300 on the default rung (both off a
  floorspace estimate), Stockley 24 → 112.5 and Cardiff 67.2 → 148 on
  displacement — and `at_least_100mw` gains exactly those last two.
  Nothing falls. Any other movement means a guard is loose; stop and
  say so.

**Tests**: rung ordering units (default slot below the two disclosed
rungs; displacement above them only via a loaded entry; ineligible
cases — tentative match, two claim names, component, grid-kind);
loader guards (dead key, unknown claim, moved value — each must fail
loudly); the caveat-coverage test extended to the new basis; a
built-page check that the four cells carry the `w-operator` class (the
`oursnap` pattern in `tests/test_reader_smoke.py`); and an integration
assertion that Stockley and Cardiff are cohort members when the
entries load — assert the two names, not a count, so corpus movement
elsewhere cannot flake it.

**Done when**: suite green including the new tests; a built reader
shows the four cells as specified; the workbook agrees with the
reader on all four; the stale docs are carried; **and Luke has
reviewed the rendering** — put the four rendered cells and one full
site-page basis line in the PR body, as WP-C did. Expect rendering
tweaks after his review; they are part of this package, not scope
creep.

---

## WP-R3 — The `site_facilities.py` path fix (own branch, small)

ROADMAP's "latent trap noticed during the WP-A work": the module
defaults its priors path and snapshot directory to *working-directory
relative* paths, and `load_facilities` returns `{}` when the file is
absent — so a build run from anywhere but the repo root silently
drops the facility layer and every downstream guard passes vacuously.
Two lines: resolve both defaults against the package root, as
`capacity_claims` and `green_claims` already do. Add a test that
loads from a changed working directory and still sees the six sites
(pin the mechanism — absolute paths — rather than the count six,
which grows). Strike the ROADMAP paragraph in the same PR. Worth
landing before R4, since the release build leans on the facility
layer's guards.

---

## WP-R5 — `dcp/sites.py` resolves its data directory against the package root

The worst instance of the working-directory class, measured by #332
and recorded in ROADMAP rather than folded in: `build_clusters`
defaults `data_dir` to `Path("data")` (~line 107), the coordinate-pin
and partition loaders under it return empty for absent files, and
both guards beside them check only the keys they are handed. From the
repository root: 29 `ref` pins, 2 `ptno` pins, 476 partitioned
applications, 34 partitioned projects; from `/tmp`: none of each,
guards green. A materialise run from the wrong directory **re-merges
the campuses the partitions exist to keep apart and changes site
keys**, reporting clean — the Wapseys Wood pin back, at clustering
time. `scripts/materialise_sites.py` and
`scripts/split_union_park_ite.py` both call it without `data_dir`.

The shape differs from #331/#332, which is why it was not folded in:
`data_dir` is a **threaded parameter**, passed explicitly by three test
modules (`test_site_partitions`, `test_project_coord_prior`,
`test_materialise_preflight` — this file and ROADMAP both said four;
`test_map`'s `data_dir` hits belong to the module #332 already fixed).
So the fix is to the *default only* — `ROOT =
Path(__file__).resolve().parent.parent` and `data_dir: Path = ROOT /
"data"` — and every explicit passer is untouched. Grep the callers of
`build_clusters(` to confirm none needs a change.

Tests on #332's pattern, each verified to fail against the unfixed
module: the default is absolute; the pin and partition loaders return
the same *key sets* from a `monkeypatch.chdir` directory as from the
root (mechanism, never counts — and the loaders can be exercised
without a database, so no integration marker is needed). Strike
ROADMAP's "the same relative-path trap survives in `dcp/sites.py`"
paragraph in the same PR.

**Must land before R4**: the runbook's step 0 is the materialise.

---

## WP-R6 — `release_diff.py` cannot silently skip its own checks

`scripts/release_diff.py` ~line 56 builds `PRIORS_WITH_SITE_KEYS`
from two working-directory-relative paths (`cohort_checks.yaml`,
`organisation_aliases.yaml`) — and `check_priors` (~line 282) opens
with `if not path.exists(): continue`. **Run from the wrong directory
it does not fail; it silently skips the dangling-site-key check and
reports nothing** — a guard that stops guarding, on the one tool the
"diff against the previous release" discipline rests on, in the class
HISTORY names: "a guard that stops guarding is worse than none".

Two changes, one branch:

1. Resolve both paths against the package root, same form as
   everywhere else.
2. **The `continue` itself is the deeper defect — make the skip
   loud.** A priors file this repository commits should never be
   absent at diff time; if one is, that is a fact the report must
   state, not elide. Print a line into the report ("priors file not
   found — check skipped") at minimum; erroring out is defensible too,
   since both files are committed. Executor's choice, stated in the
   PR.

Check how `release_diff` is tested (grep `release_diff` under
`tests/`) and add the absolute-path assertion plus a test that a
missing priors file is *visible* in the report rather than silent,
each verified to fail against the unfixed script. Sweep the rest of
the script for further relative reads while in there —
`grep -n 'Path("' scripts/release_diff.py` — and name anything found
rather than silently fixing or skipping it.

**Must land before R4**: R4's diff is only as good as this tool.

---

## Two more named by #332's sweep, smaller and later

- **`scripts/barbour_superset.py` (~line 84) is a third reader of
  `inferred_coords.yaml`**, with its own inline parse. Route it
  through `map._load_inferred_coords` so the prior has one reader;
  own tiny branch, after R4 is fine.
- **`dcp/sources/salesforce_pr.py` (~line 43) writes `LIST_CACHE`
  under `data/priors/`** — a cache in a priors directory, misleading
  about what is curated. Moving it touches the harvest flow and
  orphans the existing file, so this is a note for Luke rather than a
  fix: decide the location, then move it deliberately.

---

## WP-R7 — The release chain finds `data/exports` from the package root — **DONE 2026-09-02**

Found by #336's sweep and named there rather than folded in, rightly:
different module, different consumers, and it reaches the release chain
itself. Verified 2026-09-02 by reading all three sites:

- **`dcp/release.py` ~line 34: `EXPORTS = Path("data/exports")`.**
  `release_dirs()` globs it, so from any other directory it returns
  empty and `latest_release_dir()` returns `None`. Two consumers turn
  that into a wrong answer rather than an error:
  - **`scripts/export_reader.py` ~line 2473**: `--out` falls back to
    `data/exports/phase1_build/reader.html` and `--phase` to `"1"`.
    The reader is then stamped "phase 1" in its title, header and
    database filename, and written into a folder several releases old
    — **and the comment three lines above it already describes this
    exact outcome**, having nearly shipped it during the 2.1
    regeneration from a different cause.
  - **`scripts/build_drive_staging.py` ~line 763**:
    `latest_release_dir(Path("data/exports/phase1_build"))` silently
    takes the phase-1 fallback, which is the "tree carries the previous
    release's workbook and database" failure README warns about. It at
    least prints the folder it chose.

**The rule, stated so it can be vetoed rather than assumed.** #332's
brief let output locations stay working-directory-relative, and for a
one-off tool's `--out` that is right. `data/exports` is not that: the
whole chain — `release_dirs()`, the phase derivation, the Drive sync
ledger, the staging tree, the release diff — presumes it is *one*
location, the repository's, and reads from it to decide what to build
and where. **So for the release chain it resolves against the package
root exactly as the priors do, with every `--out`/`--release-dir`
override still honoured.** Genuine one-off tool outputs
(`probe_user_agents`, `map_spot_check`, `export_notebook_bundle`'s
defaults, `dcp/cli.py`'s `--out` defaults, `map.build_map`'s
`output_dir`) are outside this package: name them, do not touch them.

Build, in one branch:

1. `ROOT = Path(__file__).resolve().parent.parent` in `dcp/release.py`
   and `EXPORTS = ROOT / "data" / "exports"`. That alone stops the
   wrong-directory case; the rest is what the sweep showed still sits
   beside it.
2. **The two fallbacks.** Express them through `release.EXPORTS`
   rather than a literal, and then decide — **executor's choice,
   stated in the PR** — whether a bare run with *no* release folder at
   all (a fresh clone) should still default to phase "1", or refuse
   until `--phase` is passed. The project's own phrase for the second
   is that a phase is not a thing to guess; README's build chain
   passes `--phase` explicitly anyway. Read
   `tests/test_release_defaults.py` **in full first**: it asserts a
   rule over the whole tree — no default may name a release — and
   whatever it currently tolerates about these two fallbacks is the
   constraint any rewrite must satisfy.
3. **The Drive sync ledger is read by three scripts through three
   relative literals** — `scripts/drive_sync.py` ~50 `STATE_PATH`,
   `scripts/export_handover.py` ~361 `DRIVE_LEDGER`,
   `scripts/verify_drive_sample.py` ~65 — for one file,
   `data/exports/.drive_sync_state.json`. One constant, resolved
   against the root, in the module that already owns Drive constants
   (`dcp/drive.py`), and the three read it. Before changing them,
   establish what each consumer does when the ledger is absent —
   silent degrade or loud failure — and say which in the PR; the
   silent ones are the point.
4. `scripts/build_drive_staging.py` ~782 globs `Path("data/exports")`
   for workbooks and ~416 defaults the staging dir relatively; both
   through `release.EXPORTS`. `scripts/sheet_sync.py` ~57 names a
   phase-1 workbook relatively — same treatment as the reader's
   fallback in step 2.
5. Trivial, same branch: `tests/test_chunking.py` ~7 loads
   `Path("scripts/deepread_run.py")` relatively, so its collection
   depends on the working directory — use the `Path(__file__)` form
   `tests/test_release_diff.py` already uses.

**Tests, each verified to fail against the unfixed code**: `EXPORTS`
is absolute; `release_dirs()` returns the same set from a
`monkeypatch.chdir` directory as from the root — **against a `tmp_path`
exports tree built by the test and injected via monkeypatch, never the
real one**, because `data/exports` is gitignored and CI has no release
folders at all; the reader's and staging's derived defaults agree with
`release.latest_release_dir()` from another directory; and no
`Path("data/exports` literal remains in the release-chain scripts —
the sweep kept as an assertion, R6's pattern.

**Must land before R4**: R4 runs every one of these scripts, in order,
and the first of them stamps the phase.

**Met, and with one decision taken as the spec left open.** The two
fallbacks refuse rather than guess: `release.current_release_dir()`
and `release.current_phase()` stop with a message naming the flag to
pass when no release folder exists, and `phase1_build`/phase "1" no
longer appear anywhere as a default — nor does the staging build's
exports-wide workbook glob that stood in for a missing folder, which
its own comment recorded as the three-dated-spreadsheets confusion.
The ledger is `dcp.drive.SYNC_LEDGER`, read by all three scripts; a
sync starting from no ledger now says so on stderr, since a lost
ledger and a first sync look identical and mean every file goes up
again. Absent-ledger behaviour as measured: the sync silently started
from nothing (the dangerous one), the workbook silently rendered
blank Drive cells, the verifier raised. And the defaults test that
should have caught all three fallbacks — `tests/test_release_defaults.py`
— was itself working-directory-relative *and* read only the one line
carrying `default=`, which every offender had stepped around by
putting the named release on the next line; it now resolves against
the root and follows a statement's continuation lines, verified to
fail on the reintroduced fallbacks. Nine new tests in
`tests/test_release_paths.py`, each shown to fail against the unfixed
code, behaviour against an injected `tmp_path` exports tree.

---

## WP-R4 — Release 2.11 — **run 2026-09-01/02, release PR pending**

*Steps 0–13a run from `main` in order; the account, the numbers and
the two guards that caught the release's own tooling are in HISTORY
("v2.11 — the operator rung, and the release the guards earned").
What the run added to the chain: step 4a (readings submitted once the
corpus settles, collected before step 12, `--model gpt-5` always) and
the adjacent-power tree (#338). Left for Luke: merge the candidate PR,
merge the release PR carrying `index.html`, run `cloudrun/deploy.sh`,
upload Pinpoint tranche 5, delete the nine retired sites' sources from
the notebook, and the reporting-team note.*

**The process is [REGENERATION_RUNBOOK.md](REGENERATION_RUNBOOK.md),
read in full, traps and already-done sections included.** This package
is only what is 2.11-specific:

- **The release-diff will be the largest since 2.7 and must be read,
  not skimmed.** The corpus delta since 2.10: the re-gate's 14,111
  reinstated findings with their adjudication, correction, generation
  and label-audit passes; the machine readings re-run on
  `gpt-5`/`reading-1.4` (figure rate up 54%); the adjacent-power box
  (#252); the operator-pages fold; `component_of`; the WP-C our-copy
  links (166 in the reader, two workbook columns); the new claims and
  matches from R1; and the rung's four cells and +2 cohort members.
  Everything should rise or be explained; **anything that falls needs
  an explanation before the candidate PR is opened**, per
  `feedback_diff_against_previous_release`.
- **Pre-release checks**: the dead-host HEAD probe over the reader's
  register hosts (~208; ROADMAP's list of 26 is a snapshot — re-probe
  rather than trust it, and keep 403s distinct from dead); confirm
  the "Changes waiting for a re-read" accumulation list in ROADMAP is
  still empty; `power-1.1` stays inert.
- **`sheet_sync` needs a check before it runs**: the workbook gained
  an "Our copy (Drive)" column on two sheets (PR #324) and the rung
  may touch headers further. Read `scripts/sheet_sync.py` and
  establish whether column *additions* reconcile safely — the 2.8
  precedent replaced the Sheet when tabs changed, and replacement
  loses annotations. If reconciliation cannot add columns, **stop and
  put the replace-versus-refresh choice to Luke** rather than picking.
- **Machine readings**: read `dcp/machine_reading.py`'s input
  assembly and establish whether claims or matches enter the
  `input_hash` — if they do, R1 and R2 moved a handful of sites
  (529 at least) and the build's liveness check plus the runbook's
  own re-read policy decide what happens; state the moved count
  before proposing any spend (the measured cost is ~$0.10 a site).
- **The stop points**: the changes PR is named "Release 2.11
  candidate" (`feedback_release_candidate_vs_release`); the release
  PR carrying `index.html` is separate, later, and only after Luke's
  review passes; deploys are `cloudrun/deploy.sh` after his go, never
  a side effect of merging.

**Optional small item, own branch, cheap**: the Start Here page's
Gemini Notebook card still claims "Every site's report" while the
bundle exports datacentre-classed sites only — ROADMAP ("Smaller
things") has the exact location (~`export_reader.py` line 5832) and
the fix shape: state the actual scope with a generated count, name
where the rest lives. Reader-facing, so it belongs in a release that
is already touching the page.

---

## Done when

R1's counts verified, R2 shipped with Luke's rendering review passed,
R3 merged, and 2.11 released and deployed on his go — at which point
this file is marked SPENT, ROADMAP's rung and #250 items close, and
what remains of the capacity-model effort (the 33 unreviewed
campuses, #248's computed-figures labelling, the Slough scope
question) continues in ROADMAP as the ongoing review.
