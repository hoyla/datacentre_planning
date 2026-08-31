# Handover: work packages ready for an Opus 5 session

Written 2026-08-31 by a Fable 5 session, at Luke's request, so the next
stretch of work can run on Opus 5. Each package is scoped to be executed
from this document plus the files it names — the handoff is the spec;
do not re-litigate its decisions mid-build, and raise a blocking
contradiction with Luke rather than resolving it silently.

**ROADMAP.md remains the source of truth for what is left.** This
document is a session plan over it, not a second roadmap; where the two
disagree, the ROADMAP wins.

## Status, same day

- **WP0 — landed.** Luke committed and merged the alias fold himself as
  PR #283 (07:34, 2026-08-31) before the session began. Its Vantage ↔
  Next Generation Data leftover was then assessed and needs **no
  change** — see the package for the measurement. The Kao Harlow merge
  is still open.
- **WP1 — phase 1 complete**, PR #284:
  `docs/NESO_UNMATCHED_TRIAGE.md`. 61 of the 106 are not data-centre
  schemes; 29 are actionable. Phase 2 (writing matches and `considered`
  entries) has not started.
- **WP2, WP3, WP4 — not started.**

Standing disciplines that apply to every package (from `~/.claude`
global instructions and ROADMAP.md):

- Append-only with audit trail; never mutate original source material.
  Inferred values sit alongside originals with their evidence.
- Every finding carries provenance: source, reference, date.
- One change, one branch, each branched fresh from main. Commit and
  open a PR per package (Luke pointing an Opus session at this document
  is the instruction to commit each package's work when done); never
  push to main directly, and no labels needed in this repo.
- "Unclear" beats wrong: abstain and say why rather than force a match
  or a label.
- Fold append-only tables to the latest row via the pipeline's own
  accessors before quoting any count.
- Never edit `data/operator_pages_review/operator_pages_review.xlsx`
  while a LibreOffice `.~lock…#` file sits beside it; read it with
  openpyxl.

Sequencing: WP0 first (it is corpus state the others read). WP1 and WP3
are independent of each other and can run in either order. WP2 is
independent and cheap. WP4 is last — it consumes what WP1–WP3 produce,
and its decision belongs to Luke.

---

## WP0 — Land the uncommitted alias fold from the 2026-08-30 review

**State:** the working tree holds uncommitted edits to
`data/priors/site_aliases.yaml` (+89/−12: eleven new operator-named
aliases and three renames, each citing its operator-pages-review row)
and `data/priors/organisation_aliases.yaml` (+26: the Greystoke Land
group with Elsham and Humber Tech Park SPVs, Companies House PSC
evidence). These are the alias fold from the issue #255 review sheet
and were left unlanded when the 2026-08-30 session ended.

**Task:** branch from main, verify both files still parse and any
alias/prior validation the build runs passes (dead site keys fail the
build — that is the contract working, not an obstacle), commit as one
change, open a PR titled for what it is (the alias fold from the
operator pages review). Do not mix anything else into it.

**Also in this package's neighbourhood, but each its own branch/PR
if done at all:**

- ~~The Vantage ↔ Next Generation Data *organisation* alias (sheet
  T3-04)~~ — **assessed 2026-08-31: no change warranted.** Luke's cell
  asked a question ("should we put in an organisation alias?") and the
  answer is no. Measured: **zero** organisation-name fields anywhere in
  the corpus contain "Next Generation Data" (a `jsonb_each_text` sweep
  of every `CyName_*` Barbour role field). NGD survives only in three
  Barbour *project titles*, which this file explicitly does not govern
  — "the raw name is never rewritten". All three of those projects
  already name *Vantage Data Centres Limited* as client and end user,
  which already resolves to the Vantage Data Centers group, so the
  grouping the question wanted already happens. A member keyed
  `nextgenerationdata` would match nothing and assert a referent the
  corpus does not hold. The acquisition context is already recorded
  where it is useful: the `operator_pages.yaml` entry for
  `PTNO-12489438` says "NGD — the company Vantage acquired — is the
  Barbour title".
- The review sheet's first work-queue action: merge `PTNO-12839274`
  into the Kao Harlow campus (`PTNO-12240972`) on Kao's own KLON-01–04
  roster. This is a site-partition/merge decision — check how
  `data/priors/site_partitions.yaml` and `duplicates.yaml` express
  merges before proposing a mechanism, and put the premise in the
  entry's source text.

**Done when:** the alias-fold PR is open and the working tree is clean.

---

## WP1 — Diagnose the NESO register's 106 unmatched demand claims

**The ROADMAP's own framing (section "#250", table dated 2026-08-30):**
119 demand rows in the NESO Existing Agreements Register, 13 matched to
sites, 106 unmatched with a figure. Among the unmatched: Global Switch
London East 87 MW and London South 70 MW. Any matched claim could move
a site across the 100 MW line or give it a figure where it shows none.
The instruction that binds this package: **establish why they are
unmatched before proposing anything.** Address mismatch (the original
VIRTUS Slough case) is one diagnosed cause and will not be the only one
across 106 rows.

**Key facts about the mechanism:** there is no automatic matcher.
Matching is hand adjudication recorded in
`data/external_sources/neso-ea-register-matches.yaml` — read its header
comment first; it defines the confidence vocabulary (`strong` /
`probable` / `tentative`, enforced by migration 021), the `considered`
section for rows examined and NOT matched with the reason, and the
rule that a claim with no match is a normal permanent state. The
register itself is `data/external_sources/neso-ea-register.xlsx`
(header row 5; demand rows are `Transmission Connected Demand`,
compared case-insensitively — see `dcp/capacity_claims.py`). Every
figure is contracted transmission connection capacity — a ceiling, not
IT load, not built capacity.

**Phase 1 — the taxonomy (deliverable before any matching):** examine
all 106 unmatched demand rows and classify each by why it is unmatched.
Expected causes, to be confirmed not assumed:

- **Not a data-centre scheme at all.** The register lists transmission
  demand customers of every kind. A steelworks or electrolyser is
  correctly unmatched forever — these belong in `considered` with that
  reason, not in a backlog.
- **A data-centre scheme with no planning presence in the corpus**
  (pre-application, NSIP, or simply not yet filed). Correctly
  unmatched today; worth listing as leads.
- **A corpus site under a different name** — the register's customer
  or project name does not resemble the site's derived name or alias.
  These are the matchable ones.
- **Address/geography mismatch** — the VIRTUS Slough pattern.
- **Already in `considered`** — do not re-litigate those; note them.

Deliverable: a table (counts per cause, with the row-level detail
behind it) reported to Luke before phase 2 begins. Do not slice the
cohort for speed; sweep all 106.

**Phase 1 outcome (2026-08-31, PR #284):** done —
`docs/NESO_UNMATCHED_TRIAGE.md`. 61 of the 106 are not data-centre
schemes; 19 are Ethos Green "Green Energy Centres" whose consumer is
undeclared; the rest split into candidates, leads and unidentifiable
rows. **Read the document rather than these figures** — it went through
four passes and the counts moved each time.

Three things in it bear on phase 2 more than any count:

- **24 rows were already adjudicated** in the matches file's own
  `considered` section on 2026-08-20, and the triage re-examined them
  blind because its probe looked for a `row:` key where the file uses
  `rows:`. Several earlier judgements are better and stand; the Iver
  rows are withdrawn on the strength of theirs. Only six candidates are
  new, three of them strong: Cato, Relode Immingham, Bro Tathan.
- **Search `site_aliases.yaml` in any name matching.** It is where the
  developer's name and the planning record's name are reconciled, and
  skipping it is what made two passes report Quest Park and Cato absent.
- **Two ROADMAP corrections** fell out, including that Global Switch is
  not in this register at all.

The most reportable finding is not a match: four "Green Energy Centre"
schemes hold a gas generation connection in the TEC register *and* a
transmission demand connection here.

**Phase 2 — write the defensible outcomes:** for rows where evidence
supports a match, add entries to the `matches` section in the existing
style — `row`, `claim_name`, `site_id`, `method`, `confidence`,
`matched_by: hand:claude-opus-5:<date>`, and written `evidence` that
names what identifies the site and what the figure does not mean.
Every row examined and not matched gets a `considered` entry with the
reason. Where a match is genuinely arguable either way, abstain and
flag it for Luke — a tentative match with honest evidence is
permitted (consumers render tentative as leads), a forced one is not.

**Done when:** the taxonomy table is delivered, the YAML holds an
outcome (match or considered) for every examined row, and a PR is
open. Note in the PR body how many of the 106 turned out to be
data-centre schemes at all — that number is itself a finding.

---

## WP2 — #250's measurement, and the cheap honest fix

Issue #250 (open): a multi-installation campus ranks on one
installation's figure, so it can sit below the 100 MW line invisibly —
absent from `at_least_100mw` with nothing inviting a check. The issue
names three candidate remedies and says option 3 — **state the
exclusion in the cohort's `limits` field** — is cheap and honest and
should probably happen regardless. It has not happened yet.

**Task A (small, its own PR):** add a sentence to the `limits` of the
`at_least_100mw` cohort in `dcp/site_cohorts.py` (registry entry near
line 613) saying a multi-installation campus may be absent because its
figures are per-installation and no defensible total exists. Match the
register's existing prose voice. Leave `rule_version` alone unless the
rule itself changes — limits prose is not the rule — but check how
past limits-only edits were versioned before deciding (grep HISTORY).

**Task B (measurement, report not code):** the issue's "first thing to
establish" — how many multi-installation campuses hold
per-installation figures, and how many sit near enough to 100 MW for
the under-ranking to matter. Inputs: `data/priors/campus_scope.yaml`
(the 35 multi-project sites, all `unreviewed`), the operator rosters
in `data/priors/operator_pages.yaml`, and `site_scale.power_estimate`
(what actually feeds the ranking). Deliverable: a short written
report — counts, the near-line sites by name, and which of #250's
remedies the numbers argue for. No behaviour change in this task.

**Done when:** the limits PR is open and the measurement report is
delivered to Luke.

---

## WP3 — The facility prior, seeded from operator rosters

**The proposal (ROADMAP, "The missing object is the facility"):** a
hand-curated prior, `site_adjacent_power`'s sibling, on the
`site_aliases.yaml` contract — a dead site key fails the build, every
entry carries its source. Per site: the facility roster with the
source that names it; per facility: any figure attribution a document
supports. Two sources of facility identity, kept distinct and both
recorded: planning documents that name a facility (sparse,
hand-adjudicated), and operator rosters where published
(snapshot-backed claims exist since 2026-08-30 in
`data/priors/operator_pages.yaml` and the claims fold).

**Two cautions that bound the layer (verbatim from ROADMAP, they are
the design):** the roster gives campus *structure*, never
planning-figure *attribution* — planning figures stay site-attributed
unless a document names the facility or a hand adjudication does. And
a sum needs like kinds on same-layer figures, whichever layer they sit
on.

**Relationship to `campus_scope.yaml`:** that prior holds the
scope/total *decision* for the 35 multi-project sites; the facility
prior holds the *roster*. A roster is evidence a scope decision can
cite; do not collapse the two files into one.

**Scope of this package:** schema + loader/validation + seed entries.
No reader rendering yet — "3 of 5 facilities disclose" is a later
consumer.

1. **Schema:** propose it in the file's header comment in the
   `campus_scope.yaml` style (the premise stated in visible text).
   Fields per facility: identity (e.g. `LONDON7`, `KLON-03`),
   `identity_source` (operator_roster | planning_document, with URL or
   document ref and date), and optional figure attributions, each with
   quantity kind and the document that supports the attribution.
2. **Loader/validation:** a `dcp/` module mirroring how
   `site_aliases.py` validates (dead key fails the build; enforce the
   identity-source vocabulary).
3. **Seed entries**, each from an existing snapshot-backed source:
   - Kao Harlow (`PTNO-12240972`): KLON-01–04 from Kao's own page.
   - VIRTUS Slough (`PTNO-12216044`): VIRTUS rosters LONDON3, 4, 9,
     10, 11, 12, 19 as its Slough campus; the site currently claims
     three. Record the roster; the scope question stays in
     `campus_scope.yaml`.
   - VIRTUS Saunderton: four facilities, 9.5 + 22.5 + 16 + 30 against
     a stated campus total of 78 MW — the self-auditing benchmark.
     Note: the per-facility datasheet PDF is unsnapshotted (the
     fetcher takes HTML only); record figures only where an HTML
     snapshot or other held source states them.
   - Stockley Park: record the wrinkle, do not resolve it — planning
     gives 24 MW from LONDON7's 2021 handover document; VIRTUS puts
     24 on LONDON5 and 32.5 on LONDON7. Both attributions, both
     sources, flagged as unresolved.
   - Hayes (`PTNO-12831113`): three named facilities LON6, LON7, LON8.
   - The Pulsant twelve stay out for now — facility pages with no
     corpus site to key on; they are the operator-rung-only test case
     for WP4, not roster entries here.

**Done when:** the prior file, loader, validation and seeds are on a
branch with a PR open, and the build fails if a seeded site key dies.

---

## WP4 — The ladder-rung design (proposal only; the decision is Luke's)

**Standing decision (2026-08-30, "typed standing, not equal
standing"):** first-party operator statements about their own
facilities may become a labelled rung on the declared-power ladder and
may be admissible to `at_least_100mw` with the basis named;
third-party aggregates (DC Byte, Baxtel, DCM, registers) stay
tier-and-count only. Conditions that travel with it: operator pages
snapshotted at claim time; and the planning-disclosure finding
survives elevation — "no document ever stated this campus's load on a
common basis" stays reportable.

**Task:** a design document (docs/, PR'd like any change) that puts
the options and a recommendation in front of Luke. It must answer:

- How a first-party operator figure fills the declared-power cell at
  a labelled weight — what the label says, how it sits against the
  existing rungs (including `w-modelled`'s precedent of marking
  arithmetic the project performed), and what the row renders when
  operator and planning figures disagree (the divergence is the
  finding, not an error to reconcile).
- Whether `at_least_100mw` admits a site on an operator figure with
  the basis named, and what the member row and cohort notes then
  carry. The no-raw-MW-on-scan-rows ruling (2026-08-20) was scoped to
  third-party aggregates; its comparability reasoning still deserves a
  named paragraph explaining why a labelled first-party rung does not
  reopen it.
- The Pulsant estate as the test case: twelve facility pages, zero
  planning candidates — what a site that will only ever rank on the
  operator rung looks like, and whether it can exist in the corpus at
  all before a site record does.
- What WP1's outcome changes: NESO matches are third-party register
  claims and stay tier-and-count, but a newly matched site may then
  also hold an operator figure — say how the rungs stack.

**Inputs it must cite:** the Stockley wrinkle (WP3 records it), the
audiences finding (the `page_kind` field makes corporate-states /
consultation-silent countable — count it and put the number in the
document), and WP2's measurement.

**Explicitly out of scope:** implementing the rung. The document ends
with the decision points listed for Luke, not with code.

---

## Small items also open (each its own branch if picked up)

- The Cato architect's 600 MW (graemenicholls.com, snapshotted): a
  claims lead from a source kind the claims channel does not yet name —
  neither operator nor register but the scheme's own architect. Needs
  a `source` vocabulary decision before it can land; flag, don't force.
- CyrusOne LON2 (Prologis Park, West Drayton) is a separate site from
  the VIRTUS Prologis Park campus — a note for whenever that site is
  created (sheet T4-02); no action until then.
- Hayes `PTNO-12831113` N+N adjudication: the same sentence
  adjudicated at both 150 and 300 MW and `max()` takes the wrong one;
  the document set states 250 MW. One site, wrong on the page.
