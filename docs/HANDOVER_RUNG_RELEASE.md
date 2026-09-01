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
R3 any time, R4 last. R2 is the only large package.

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

## WP-R4 — Release 2.11

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
