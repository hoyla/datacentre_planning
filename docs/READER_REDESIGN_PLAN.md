# Reader redesign — sequencing plan

Written 2026-08-23 after reviewing the design handoff in
`design_handoff_datacentre_reader/` (the "story finder" prototype, v2),
Luke's follow-up on a who's-behind-it column, and three constraints he
set the same day: the OpenAI API budget is not a constraint, so reading
and summarising can be thrown at it freely; the workbook and DuckDB
stay granular and carry no machine-generated interpretation; and the
work ships as a staged series of usable releases, not one outcome at the
end.

So the plan is five increments, **each a numbered release that lands
beside its predecessor** (2.3 → 2.7), each small enough for a few
sessions, each leaving the reader better and the exports consistent. It
runs in parallel with the content research lane in
[SCALE_RANKING_RESEARCH.md](SCALE_RANKING_RESEARCH.md), so §1 is about
not colliding. The review's verdicts are summarised in §2 so a fresh
session does not re-derive them; the evidence is in the memory note
`reader-redesign-review-2026-08-23` and the queries it names.

Untracked on purpose until Luke has read it.

**Progress, 2026-08-24 (end of day).** Ten PRs merged: #101 (the
Barbour fixed slots, gate-1.2, gate-2.0), #102 (checkpoint-4 markdown,
`--no-readings`), #103 (the generation prompt and batch route), #104 (the
scorer split), #105 (§4.1c), #106 (the thermal-output correction), #107
and #108 (company numbers, the CRO register, the loader guards), #109
(the alias confirmations), #110 (the withheld-reason fix). Open: **#111**.

**Two checkpoints are closed.** Checkpoint 4: Luke read the sample and
accepted it, subject to the withheld-line fix that became #110.
Checkpoint 2: eight of the ten alias members are confirmed with company
numbers, two deliberately left proposed — "Microsoft UK Limited" cannot
be told from Microsoft Limited on one line of evidence, and "UK Court
Lane DC Limited" is not shown to be Corscale's.

**§4.1e and §4.1c are done, and they moved the page.** All 1,667
generation figures are adjudicated under `gpt-5/generation-2.5`; the
rollup's label is computed from them. **Twenty-nine of seventy-two sites
changed**: seven lost a generation figure entirely (1,053 MW off the
page, Rover Way's battery among them), ten moved from "as stated" to
"not settled", seven to "per unit". A figure that leaves is counted
where it stood, with the reason.

**The prompt plateaued at ~89% and the metric changed.** Luke: better
unclear than wrong, "something that improves one thing from unclear but
gets another thing wrong is worse than unclear plus correct or even
unclear plus unclear". `--score` now reports right / abstained / wrong
but withholding / **wrong and asserted**, and versions are ranked on the
last. 2.5 ran the batch.

**Companies House, corrected for the third time.** Chasing the Corscale
alias led to UK Court Lane DC Ltd's accounts, which state that its
£205,000,000 valuation assumes "successful delivery of a 103.3 MW
hyperscale data centre" — against Barbour's 140 MW. The 2026-08-20
survey tested operators and their property companies and concluded
"mostly a null"; **single-asset SPVs disclose capacity by construction**,
because the scheme IS the investment property. ROADMAP has the sweep.

**The face is half done, and the plan was ahead of the delivery.** §5e
scheduled the prototype's type and spacing tokens for 2.4 and 2.4 did
not bring them, so #111 is two increments late rather than 2.7 work: the
site page is one reading column instead of a seven-card jigsaw, the type
has a 13px floor and a 16px body (deliberately larger than the handoff's
15/14/13/12), the site cell carries name, councils, key and proposal,
signals are stacked in one neutral pill, and the power basis rides on
the figure in weight and a mark rather than colour. **Still untouched:
§8a the start page, §8c the map colouring, the palette (nothing
Guardianesque yet), and the handoff's reading bar.**

Google Fonts are fine to use — Luke, and the licences were never the
issue; §8b's "no Google Fonts" line should read "no LINKED web fonts",
since a vendored woff2 subset costs tens of KB against 11 MB and removes
the third-party request. The reader is served from EdgeOne, not opened
from Drive; an earlier note here said otherwise and was wrong.

**Tomorrow, in order:**

1. **Luke: `data/label_audit_sample/label-1.0_sheet.csv`** — sixty rows,
   fill `verdict` and `suggested_family`, then
   `scripts/audit_labels.py --score`. This gates the batch, and the
   stakes are higher than they look: on a random slice of 120 rendered
   findings, **16.7% are flagged as filed under a family that does not
   fit**, which is ~1,770 of the 10,605 rows a reader sees. A wrong flag
   moves a real quote under a wrong heading, which is why `--score`
   counts flagged-wrongly apart from flag-missed.
2. If it scores well: apply migration 025, `--batch --submit` (266
   requests), then rebuild — a flagged row is DEMOTED to the family the
   audit says fits and marked "[filed as X]", never dropped (Luke's
   decision, against §7a's "exclude").
3. **The release.** 2.3–2.6 as one release. `scripts/release_diff.py`
   exists and counts links per site, tabs, views, rows and sheets
   against the last release — run it before publishing, because today
   moved 29 sites' figures and merged a table column. `index.html` is
   written last and is the only step that deploys.
4. **2.7 proper:** the start page (§8a), the map (§8c), the palette, the
   reading bar. Two open questions for the palette: Guardian blue for
   structure is compatible with "colour reserved for verification
   state", but the handoff's red-for-Signals is not; and the reading bar
   is specified as colour-by-completeness, which only works if
   read-completeness counts as a verification state (it arguably does).
5. Lane R, when Luke wears that hat: the export-limit correction, and
   the Rover Way class, which the generation batch has now enumerated.

---

## 1. Two lanes, and what each owns

**Lane R — research** (Luke's other sessions, per SCALE_RANKING_RESEARCH
§2): letters and asks, `scripts/rank_for_outreach.py`, the floorspace
sweep, the zero-byte guard, acquisition captures, partition adjudication,
new claims loaders, the EA/Section 35 watcher. It owns
`dcp/site_scale.py`, `dcp/capacity_claims.py`, `dcp/ea_permits.py`,
`dcp/sources/*`, `scripts/fetch_*`, `scripts/correct_adjudications.py`,
`data/priors/site_partitions.yaml`, `data/external_sources/*`, and the
research docs.

**Lane B — build** (this plan): `scripts/export_reader.py`,
`scripts/export_handover.py` and `scripts/export_duckdb.py` (new columns
and tables only), `dcp/site_profile.py`, the new modules named below,
their tests, and `docs/REGENERATION_RUNBOOK.md`.

**Shared, with a rule each:**

| File | Rule |
|---|---|
| `data/priors/organisation_aliases.yaml` (new, 2.4) | Append-only entries; either lane may add a group or evidence. Schema fixed before anyone writes to it. |
| `data/priors/cohort_checks.yaml` (new, 2.5) | Same. Research's hand-checks of a cohort member land here, keyed by `site_key`. |
| `scripts/correct_adjudications.py` | Lane R owns it. Lane B's corrections (§4.1d, §4.1e) are filed as named rules there by agreement, never by a side edit. |
| `dcp/site_scale.py` | Lane B reads `power_estimate` and never edits the module; a new basis label is a one-line PR agreed first. |
| `scripts/adjudicate_power.py` (the shared prompt and schema) | Any new adjudication question (§4.1e) extends the one prompt file all routes import, under a new prompt version, never a second copy. |
| `HISTORY.md`, `ROADMAP.md` | Each lane appends under its own heading; never rewrite the other's section in the same PR. |
| `index.html` | **Never regenerated except in a release PR.** EdgeOne builds from main, so merging a generator change deploys nothing; writing `--publish index.html` does. Every other build goes to `--out` under scratch or a `*_build` folder. |
| The database | Append-only, so builds are safe at any time; but a build made while the corroboration read or a correction run is writing is a snapshot of a moving corpus. Stamp and diff; do not quote. |

Site keys are the join everywhere. A partition split in lane R (site 61's
seven campuses) changes keys, which re-points cohort memberships and
alias evidence. Memberships are **computed at build time and never
stored**; the only stored site references are in the two YAMLs, and a
check (§4.2c) asserts every `site_key` they name still exists.

Three things lane R tells lane B before doing: a partition split, a
change to `power_estimate`'s ladder, a new quantity type (the indicators
panel asserts a caveat per type).

Branching: one short-lived branch per numbered step, rebased on main
before the PR, draft PRs pushed freely, ready PRs only after the checks
in §4.2 pass. Push rules by PR state apply (`.githooks/pre-push`).

---

## 2. What the review decided (summary)

Adopted from the handoff: a Signals page of named cohorts; cohort chips;
a dedicated site page instead of a row expansion; a labelled machine
panel per site; the coverage-as-boundary sidebar; the package cards at
the bottom of Start; the type scale and spacing. Added by Luke: a
who's-behind-it column with organisation badges that act as filters.

Rejected, with the evidence: the "standby below 10% of stated load"
cohort (flags Elsham Wolds on 50 MW of gas while "up to 650 no. 2,480 kW
back-up diesel generators" sits unmultiplied; flags Watford on one of
"112 No. standby generators"; counts rooftop PV as generation); the PINS
≤1 km co-location definition (13 sites, 8 of them Slough Trading Estate
units beside Slough Multifuel); the single "Power on record" column (the
2026-08-20 decision: no external MW on a sortable row); the signed
Reporter's note; the hidden `interest` ranking; the template digest;
mention-count-derived party badges (Savills would be the applicant on 17
rows, CityFibre on 73).

True counts, 2026-08-23: fully read and silent **141** (not 22); demand
> 1.5× connection **4** by rule, **2** hand-checked; like-for-like
two-audience sites **3** (not 18); generation > 1.5× stated load from
the site's own figures **9**; floorspace-estimated **43** (not 7);
register-publishes-nothing **36 sites** (the 80 is applications).

---

## 3. Standing rules for the whole plan

### 3.1 The OpenAI API is the reading engine

The budget is not a constraint. Wherever a step needs judgement over
text — summarising a site's documents, deciding whether a generation
figure is per unit or a fleet, proposing that one company is another's
subsidiary, checking whether a finding's label matches its text — the
default is an OpenAI batch on the `scripts/adjudicate_openai.py` pattern:
submit / collect, results stored append-only under a model tag and
prompt version, idempotent on an input hash, and **every figure the
model emits carries a verbatim quote verified against the cached source
text before it is stored** — the same gate the findings pass. The
project's preference for deterministic extraction where judgement is not
needed stands; this rule is for where it is.

What that opens up, by increment: 2.3 — a batch adjudication of every
`onsite_generation` row for *per unit vs fleet* and *standby vs
renewable*, which is what makes the generation rollup honest and is the
prerequisite for ever reinstating a standby cohort; and a batch audit of
finding labels against their text, stored alongside and consumed by the
findings panel. 2.4 — batch-proposed alias evidence: the model reads the
"applicant / on behalf of / a subsidiary of" passages and proposes
parent–subsidiary links **with the quote**, for a human to confirm into
the YAML; it proposes, it never writes the map. 2.6 — the per-site
machine reading reads the site's tier-A documents directly (planning
statement, energy statement, officer report, the statutory consultees'
letters — the EA letters that started this investigation), not only the
panels, because the quote gate makes that safe. Anything else that turns
out to be "read a lot of text and say what it says" goes the same way.

### 3.2 The workbook and the DuckDB stay granular, and carry no interpretation

- **No machine-generated text in either export.** The machine readings
  (2.6) live in the reader only. `export_duckdb.py` does not export
  `site_machine_readings`; the workbook has no column for it.
- **One column per kind of thing, never combined.** A quantity type, a
  Barbour role, a cohort, an alias group: each is its own column or its
  own row in a long-format sheet. Nothing merges two energy finding
  types, two roles or two rules into one cell.
- **Long format for the new material.** A `Parties` sheet (`site_key,
  role, organisation, source, source_ref`) and a `Cohorts` sheet
  (`site_key, cohort, rule_version, hand_checked, checked_by, date`)
  rather than a column per role or a column per cohort on Sites. Sites
  gains only one-value-per-site facts: `operator_group`,
  `applicant_of_record`, `parties_source`, and the per-unit generation
  label from 2.3. The same three tables go to the DuckDB
  (`parties`, `cohorts`, `organisation_aliases` with their evidence).
- **An inferred value sits beside its original, never in its place.**
  `operator_group` is a column next to the raw organisation string, with
  the evidence one lookup away; `signal_family` and any label audit
  (3.1) sit beside `signal_type`, which is never rewritten.
- **Every new column has a dictionary row generated from the same
  definition the reader uses**, so the two cannot drift.
- **`scripts/release_diff.py` reports the column and sheet delta** of
  every build against the last release, and a column that disappears
  fails the check.

### 3.3 Every increment is a release

Each increment below ends with the regeneration runbook, the release
diff, the smoke and determinism checks, `--publish` in the release PR,
`probe_gate.sh` after the merge, and a HISTORY entry. Releases are
versioned beside their predecessors on Drive. An increment that is not
ready to release is not merged to main in a half state; it stays on its
branch.

---

## 4. Increment 2.3 — honest ground

*The 2.2 reader with its known wrong things fixed, plus the instruments
every later increment is diffed against. Same design. ~2 sessions plus
one batch turnaround.*

### 4.1 Fixes

- **a. Assistant's notes.** The "grid-dependent by design" paragraph
  diagnoses engineering that RULES_AUDIT §2 removed from the labels on
  2026-08-11. Rewrite to describe the ratio and name the per-unit trap.
  Lane B, text only.
- **b. "What the documents say" ranking.** `FINDINGS_SQL` ranks by text
  length after family, which promotes mislabelled rows (Watford: `it_load`
  findings whose text is landscape prose). Prefer findings with a
  `site_capacity` adjudication, then round-robin across families,
  tie-break `f.id`; once 4.1e's label audit exists, exclude rows it
  flags. Keep the build deterministic (`test_export_ordering`).
- **c. Per-unit generation presented as site generation.** The Declared
  power rollup takes `max(value_mw)` over `onsite_generation`; where that
  row is `is_maximum = false` and a fleet count exists, the panel shows
  "3.2 MW" above "112 units". Until 4.1e lands, label it per-unit
  ("3.2 MWe per unit · up to 112 units disclosed · not multiplied") in
  reader and workbook alike. Do not multiply.
- **d. Kingsnorth's 49.9 MW is an export limit.** "Maximum MW export =
  49.9 MW (at unity power factor)" is stored as `grid_connection`, so the
  2.2 like-for-like "340 vs 49.9, 6.81×" compares export with import.
  Lane B measures how many `grid_connection` rows carry "export" in the
  quote; lane R files the named correction rule; the Operators tab is
  re-checked.
- **e. Generation adjudication batch (3.1).** Every `onsite_generation`
  `site_capacity` row asked two questions under a new prompt version in
  the shared prompt file: is this figure per unit, a fleet total, or a
  site total; and is the plant standby combustion, prime/continuous
  combustion, renewable, or storage. Stored as adjudication rows beside
  the existing ones, consumed by the rollup (4.1c's label becomes
  computed), by the workbook as two new columns, and later by the
  cohorts. Measured on a hand-checked sample before the full batch, as
  the subagent route was. Alongside it, **the label audit**: a batch over
  the findings families the reader shows, flagging rows whose family does
  not match the text, stored as a separate table and never touching
  `signal_type`.

### 4.2 Instruments

- **a. Build-and-drive smoke test.** ROADMAP asks for it and every
  shipped reader regression so far was visual or interactive and
  invisible to the suite. Build to scratch (9 s), load headless, assert:
  every tab shows a view; a site opens; each chip changes the count and
  the map's sidebar agrees; deep links land; card links fire; no console
  errors. Playwright for Python is the candidate — **install
  unverified**; mark `integration`; fixture is the live database.
- **b. Build determinism test.** Build twice against one snapshot, diff
  apart from the stamp. Also in ROADMAP.
- **c. `scripts/release_diff.py`.** Scripts the check currently done by
  eye (it found four regressions in 2.2): tabs, site rows, links per
  site, section headings, chip labels; workbook sheets, rows, columns;
  DuckDB tables and row counts — against the last `*_build` folder.
  Non-zero exit on any count that fell. Plus the YAML reference check
  for the two priors files once they exist.

**Checkpoint (Luke):** the sample for 4.1e's generation questions before
the full batch. **Deliverable:** release 2.3 — fewer wrong numbers, a
correct Kingsnorth row, and the regression instruments. Lane R gains the
per-unit/fleet and standby/renewable columns for its ranking.

---

## 5. Increment 2.4 — who is behind it

*The column Luke asked for, in the existing design. ~3 sessions. The
first increment lane R can feed.*

- **a. `dcp/organisations.py` + `data/priors/organisation_aliases.yaml`.**
  Groups by evidence, never by similarity — `entities.canonical_key`
  stays the only automatic normalisation. Entry: `group`, `members` (raw
  strings as the documents or Barbour write them), `evidence` (list of
  `{source, ref, quote, note, date}`). Seeded from Barbour's
  client→end-user pairs (stated relationships: Colliers → Amazon Data
  Services Ireland, VDC LHR11 → Vantage, Segro → Zenium / Iron Mountain)
  and the names on `data/operators.yaml`. Tests: no raw string in two
  groups; every group has evidence; a member without a source is
  rejected. **Schema first, in its own small PR**, so lane R can write
  to it from day one.
- **b. Alias proposals by batch (3.1).** A batch over party findings and
  the documents' "on behalf of / subsidiary of / trading as" passages,
  proposing links with verbatim quotes into a proposals file. A human
  moves a proposal into the YAML or rejects it with a reason; the
  proposals file is never read by a build.
- **c. `site_profile` parties, second version.** Barbour role blocks
  first (Client, End user, Planner/Agent, Architect, M&E engineer —
  names only; the contact fields never leave `raw_metadata`); findings-
  derived names admitted to the operator field only through the alias
  map, otherwise staying in the adviser/other lists with the
  mention-count hedge; authority from the site's councils, not from
  party findings. Output: `operator_group`, `applicant_of_record`,
  `end_user`, `parties_source`, `advisers`, `authority`; absence is
  "not established from the sources held". Tests: Savills or Barton
  Willmore cannot become an operator without an alias; CityFibre
  likewise; a Barbour end user outranks a findings applicant; the
  rotation property from `test_reproducible_ordering` holds.
- **d. Exports (3.2).** The `Parties` sheet and the three Sites columns;
  the `parties` and `organisation_aliases` tables in the DuckDB;
  dictionary rows.
- **e. Reader.** The who's-behind-it column on the existing table —
  operator group badge, "via <applicant of record>" where they differ,
  source on hover; badges are filters, using the existing chip mechanism
  with state in the URL; a "who's behind it" chip group for the top-N
  groups by site count; advisers as a facet, not badges. The type and
  spacing tokens from the prototype come in here for the table, since
  the column change touches the CSS anyway.

**Checkpoint (Luke):** the seed alias groups (ownership claims), and the
column on real rows — the first time the party data is visible, it will
show its errors, which is the point. **Deliverable:** release 2.4 —
filter by Virtus, Ark, Greystoke, by end user, by authority and region;
the same facts in the workbook's `Parties` sheet.

---

## 6. Increment 2.5 — cohorts and chips

*The Signals page and the content chips, in the existing design. ~3
sessions.*

- **a. `dcp/site_cohorts.py` + `data/priors/cohort_checks.yaml`.** A
  `Cohort` has `key`, `title` (states the property, never a cause),
  `family`, `definition` (prose and rule), `limits` (**required; the
  build fails if empty**), `order`, `rule_version`, and `compute(conn) ->
  set[site_key]`. Four to start:

  | key | compute | hand-checks |
  |---|---|---|
  | `read_in_full_silent` | the logic of `scripts/sweep_null_capacity.py`, refactored into a function the script also calls, keeping its refusal to print while figures await adjudication | the script's own classification |
  | `demand_exceeds_connection` | stated load (IT or total) / stated connection > 1.5, both `site_capacity`, with the cross-application scope caveat | `cohort_checks.yaml` (2 today) |
  | `generation_no_fuel` | one definition, chosen and printed | — |
  | `generation_exceeds_load` | on-site generation / stated load > 1.5 from the site's own adjudicated figures, **using 2.3's fleet-total and combustion-only rows** | `cohort_checks.yaml` |

  Not built: `standby_below_10pct` — revisit only once 2.3's batch has
  separated per-unit and renewable rows and the result has been
  hand-checked against Elsham, Watford and Didcot; `two_audiences` — 3
  sites; link to the Operators tab's like-for-like instead. Tests: every
  cohort has limits; counts computed, never literal; registry order
  explicit; a hand-check on a site outside the computed cohort is
  reported, not hidden.
- **b. Exports (3.2).** The `Cohorts` sheet and table; dictionary rows
  with the rule text. No cohort columns on Sites.
- **c. Reader.** The "what the documents say" chip group beside the
  existing coverage chips and 2.4's who's-behind-it group; and a
  **Signals tab** — one card per registry entry: title, family, computed
  count, hand-checked count, definition, limits, open-in-table, CSV.
  Registry order; no ranking of sites anywhere. Assistant's notes keeps
  what is not now a cohort.

**Checkpoint (Luke):** the four titles, definitions and limits texts —
editorial claims that will sit on every row. **Deliverable:** release
2.5 — the Signals page and three chip groups, each cohort reproducible
from the workbook's `Cohorts` sheet.

---

## 7. Increment 2.6 — the site page and the machine reading

*The structural change, and the first place a model writes prose a
reporter sees per site. ~3–4 sessions plus batch turnaround.*

- **a. Site page.** The expanded row becomes a view with the existing
  `#site-<key>` deep link; back returns to the Sites state (chips,
  search, sort). Every 2.2 panel survives; "What the documents say"
  groups by family with counts and show-all, excluding rows the 2.3
  label audit flags; links per site ≥ 2.2's, asserted by `release_diff`.
- **b. `scripts/machine_reading_openai.py` (3.1).** Input per site: the
  panel data (figures with quotes and application refs, external claims
  with match strength and caveats, coverage, the generation profile with
  2.3's per-unit and combustion verdicts, parties, cohort memberships)
  **and the text of the site's tier-A documents** — planning statement,
  energy statement, officer report, statutory consultee letters. Output
  in three sections: what the documents say about scale, power,
  generation and who is behind it; the questions the documents raise and
  who could answer them; what could not be determined. Prompt rules: no
  cross-site comparison or ranking, no intent language, no handling
  advice, and every figure carries a verbatim quote. Stored in
  `site_machine_readings` (`site_key, model, prompt_version,
  input_hash, text, inserted_at`), append-only, idempotent; regenerated
  when a site's input changes, which a release does. Not exported.
- **c. The quote gate for prose.** Every number-with-unit in a reading
  must be backed by a quote that verifies against the cached source text
  (the findings gate, reused); a reading that fails is **withheld for
  that site** with a one-line reason, never rendered, never fatal to the
  build. Withheld count printed and diffed.
- **d. Sample review.** Twenty sites spanning the bases (Watford, Elsham,
  Kingsnorth, Saunderton, Garrison, a floorspace-only site, a Barbour-only
  pre-planning row, a Slough estate record…). Submit the batch at the
  start of the increment; turnaround is up to 24 h.
- **e. Reader.** The panel renders collapsed, labelled as what it is —
  "a machine's reading of this site's documents, generated by <model> on
  <date>; not a finding" — only where a reading exists and passed the
  gate. The label states; it does not instruct.

**Checkpoint (Luke):** the twenty-site sample before any reading
renders. **Deliverable:** release 2.6 — a page per site, grouped
evidence, and a gated machine reading on every site with documents.

---

## 8. Increment 2.7 — the new face

*Start page, sidebar, package, and the visual reconciliation. ~2–3
sessions.*

- **a. Start page.** Intro; the two-ways-in card; pitfalls (from the
  notes tab, verbatim); the coverage-as-boundary sidebar from the
  existing "About these numbers" content plus "read twice"; package cards
  at the bottom.
- **b. Visual reconciliation.** The tokens introduced in 2.4 applied
  everywhere they are not yet: type scale, spacing, square cards, 4 px
  rules, no shadows; system serif/sans stacks — no Google Fonts, no
  licensed faces in a public repo; one neutral colour for cohort and
  organisation pills, colour reserved for verification state; tables
  scroll in their own container, never the page.
- **c. Map.** Chips colour the map's markers by the active cohort; the
  sidebar states how many filtered sites are unlocatable and absent.

**Deliverable:** release 2.7 — the redesign complete, with every prior
increment's artefacts still resolving on Drive.

---

## 9. Sequence, dependencies, sizing

```
2.3  fixes a–d ──┐
     batch e ────┤──► instruments a–c ──► release 2.3
                 │
2.4  aliases schema (first, tiny PR) ──► batch proposals ──► parties v2 ──► exports ──► column+chips ──► release 2.4
                 │                                            (needs 2.3 per-unit label)
2.5  cohorts module ──► exports ──► chips + Signals tab ──► release 2.5
     (needs 2.3e for generation_exceeds_load; needs 2.4 chip mechanism)
2.6  site page ──► reading batch (submit early) ──► gate ──► sample ──► panel ──► release 2.6
     (needs 2.3 label audit; 2.4 parties and 2.5 cohorts as inputs)
2.7  start page ──► visual reconciliation ──► map ──► release 2.7
```

Strictly ordered at the release level — each increment assumes the last
has shipped — but inside an increment the batch work runs while the code
is written, and 2.4's alias schema lands first so lane R can start
writing evidence during 2.3.

What lane R can do at any time without waiting: write evidence into the
two YAMLs once their schemas exist; file 4.1d; hand-check cohort members
as `rank_for_outreach.py` surfaces them; hand-check the 2.3 generation
sample.

Rough sizing in sessions — builds and tests are measured (9 s, 574 tests
in 25 s); Playwright and batch turnaround are not: 2.3 ≈ 2, 2.4 ≈ 3,
2.5 ≈ 3, 2.6 ≈ 3–4, 2.7 ≈ 2–3. Each number includes its release.

---

## 10. Checkpoints that need Luke

1. 2.3: the hand-checked sample for the generation adjudication batch.
2. 2.4: the seed alias groups; the who's-behind-it column on real rows.
3. 2.5: the four cohort titles, definitions and limits texts.
4. 2.6: the twenty-site machine-reading sample.
5. Every release: the release diff.

Everything else runs without a question.
