# The operator rung — how a first-party figure may fill the declared-power cell

> **Status: decided (Luke, 2026-09-01) and built (PR #333) — see the
> answers on each decision point at the end, including the
> empty-ladder extension to decision 1 and the value pin that
> replaced decision 2's date pin. The rendering review that decisions
> 2 and 4 were conditional on passed on 2026-09-02.** This is WP-E of
> [HANDOVER_SNAPSHOT_CHAIN.md](HANDOVER_SNAPSHOT_CHAIN.md), executing
> the standing decision of 2026-08-30 — *typed standing, not equal
> standing*. Every measurement in it was made against the live corpus
> on 2026-09-01, with the module or query named; re-measure before
> implementing, because the corpus moves.

The question: whether, and how, a figure an operator publishes about
its own facilities may fill a site's declared-power cell — the number
the sites table sorts on and `at_least_100mw` admits on — at a
labelled weight, rather than living only in the claims panel.

---

## Decisions already made — do not relitigate

- **Typed standing, not equal standing** (Luke, 2026-08-30, HISTORY
  "The operator pages day"): first-party operator statements about
  their own facilities *may* become a labelled rung; third-party
  aggregates (DC Byte, Baxtel, DCM, the registers) stay tier-and-count
  only. This document designs the rung; it does not reopen whether one
  may exist.
- **No raw MW on scannable rows** (Luke, 2026-08-20): scoped to
  third-party aggregates, whose megawatts measure different quantities
  per provider. A named paragraph below says why the rung does not
  reopen it.
- **A claim says which realm it belongs to** (PR #312,
  `component_of` / `reconcile_components()`): a campus total and its
  facility components are different claims. A component is never added
  to the total it is part of, and the sites table counts top-level
  claims only. The rung must keep that line.
- **No summed campus totals** (issue #247, rejected twice — ROADMAP,
  "Approaches tried and rejected"): phases are subsets, schemes
  restate themselves (Cambois: 1,100 MW three times, summing to
  3,300), and the Global Switch test (2026-09-01) showed even the
  cleanest case fails — each building states figures of several kinds,
  and which of a building's own figures a total may add is a judgement
  per facility, not arithmetic.
- **Planning figures never enter `capacity_claims`** (Luke, ROADMAP):
  the channels stay distinct, because the reader depends on the
  distinction.
- **The evidence chain is built** (WP-A/B/C): every operator figure is
  quote-verified against an append-only, dated snapshot, held on Drive
  with its id in a committed ledger, and rendered with an "our copy"
  link resolved from the claim's own quote. A rung figure inherits all
  of that for free — the chain is a precondition this document no
  longer needs to design.
- **The register channel adds zero line-crossers** (measured for #250,
  2026-08-31): tier-and-count costs the registers nothing, so nothing
  below concerns them.

## The ladder as it stands

`dcp/site_scale.power_estimate` (read 2026-09-01), which both the
sites table's ranking and `at_least_100mw` run on:

| rung | basis | confidence | weight class |
|---|---|---|---|
| 1 | Disclosed IT load | High | `w-stated` |
| 2 | Disclosed total site demand | High | `w-stated` |
| 3 | Grid connection capacity | Medium | `w-implied` |
| 4 | Standby generation capacity (plant_type-honouring) | Low | `w-implied` |
| 5 | Estimated from floorspace | Indicative | `w-modelled`, ≈ glyph |

Rungs 1–2 are what the planning record disclosed about the
development's own load. Rung 3 is contracted headroom. Rung 4 is an
inference from backup plant. Rung 5 is arithmetic this project
performed — `w-modelled` exists precisely to mark that, and is the
precedent for a labelled rung carrying an authority statement.

## What the operator channel holds

Measured 2026-09-01 from `load_operator_claims()`: 89 committed
claims — 68 top-level (51 `announced_capacity`, 17 `grid_connection`)
and 21 facility components under five campus totals. The operator's
own word for the quantity is kept per claim (`Total IT power`,
`critical IT load`, `Total Capacity`, …); the dominant kind is an IT
load, which is also what ladder rung 1 holds, so the like-for-like
comparison the cell invites is usually the right one — and the basis
line states the kind either way.

Ten top-level claims stand at 100 MW or more. Matched to sites and
ranked through the live ladder (2026-09-01):

| claim | MW | site ranks today | basis |
|---|---|---|---|
| East Havering (Digital Reef) | 600 | 580 | **floorspace estimate** |
| Ravenscraig (Apatura) | 550 | 550 | disclosed IT load |
| Humber Tech Park | 384 | 384 | disclosed IT load |
| Westerhill (Bishopbriggs) | 300 | 150 | **floorspace estimate** |
| Freeport (Apatura) | 250 | 250 | disclosed IT load |
| Ada Docklands | 210 | 210 | disclosed IT load |
| Former Mercure Hotel | 200 | 168 | disclosed IT load |
| Vantage Cardiff | 148 | **67.2** | disclosed IT load |
| VIRTUS Slough | 145.5 | — | unmatched, scope open (3 of 7) |
| VIRTUS Stockley Park | 112.5 | **24** | disclosed IT load |

Three classes fall out of that table, and they want three different
treatments:

1. **Corroboration** (Ravenscraig, Humber, Freeport, Ada, Mercure):
   the site already ranks at or above the line on its own planning
   disclosure. The operator figure belongs in the claims panel, where
   it already is; where the two diverge (Mercure: 200 against 168) the
   divergence is the finding, never a cell change.
2. **Authority repair** (East Havering, Westerhill): the site ranks on
   a **floorspace estimate** — our arithmetic, the ladder's weakest
   rung — while a first-party statement of the same order sits in the
   panel. On any reading, what the operator states about its own
   scheme outranks what we computed from its floor area.
3. **Scope repair** (Stockley, Cardiff — and Slough once its scope
   resolves): the site ranks on a genuine High-rung planning
   disclosure that the facility layer shows describes **one facility
   of a campus** — Stockley's 24 MW is LONDON7's commissioning
   milestone standing for five facilities. The planning figure is not
   weak; it is narrower than the row it stands on.

**The decisive measurement is that the two sites the rung was raised
for are both in class 3.** Stockley and Cardiff rank on *disclosed IT
load at High confidence*. A rung positioned anywhere below the
disclosed rungs therefore fixes neither of them; a rung positioned
above the disclosed rungs would let a marketing page displace the
planning record on every one of the class-1 sites too. Position alone
cannot express the design — the problem is scope, not authority.

## The proposal: a default position, plus adjudicated displacement

Two parts, one rung.

**Part 1 — the rung's default position: between the disclosed rungs
and the grid rung.** Where a site's best planning figure is rung 3 or
below (grid, standby-implied, floorspace) and a matched, snapshot-
backed, top-level `announced_capacity` operator claim exists, the cell
takes the operator figure:

> value **Operator-stated campus figure** · Medium ·
> "Published by ⟨operator⟩ about its own facilities, as at ⟨as_at⟩,
> held as a dated snapshot. A statement to customers, not to the
> planning authority; the planning record's own best figure is
> ⟨basis: value⟩."

This is automatic in the same sense the existing rungs are — no new
adjudication, because the hand-made match with written evidence *is*
the adjudication, exactly as a hand match already puts the claim on
the site's panel. Guards: top-level claims only (a component is a
building, not the site's figure); match confidence `strong` or
`probable` (`tentative` stays panel-only); the latest reading per
claim (the append-only fold); more than one distinct top-level claim
on a site → panel-only until a person says which (the Global Switch
lesson). Effect today: East Havering 580 → 600 and Westerhill
150 → 300, both replacing our arithmetic with the operator's own
statement — and in both cases the corporate page states the figure
while the consultation site is silent, so the basis line surfaces the
two-audiences finding on the row itself.

**Part 2 — displacement above a disclosed planning figure only by
hand adjudication, recorded in the campus-scope review.** Where the
planning figure is rung 1–2 but describes a strict subset of the
operator's campus, a `campus_scope.yaml` entry (the 35-campus review
this feeds) may name the operator claim — by `claim_name` and
`as_at`, so a reload cannot silently swap the figure — and record the
evidence: the roster that gives the denominator, the facility the
planning figure belongs to, and the reconciliation state. Only then
does the cell take the operator figure:

> 112.5 **Operator-stated campus figure** · Medium ·
> "VIRTUS states 112.5 MW IT load across the campus's five
> facilities, as at 2026-08-30. The planning record's own largest
> figure is 24 MW — LONDON7's 2021 commissioning milestone — and
> 3 of 5 facilities disclose, on 3 different bases."

One wrinkle travels with the Stockley example and the entry must
carry it rather than resolve it: the 24 MW comes from a document
titled *VIRTUS LONDON7*, but VIRTUS's own roster puts 24 on LONDON5
and 32.5 on LONDON7 — possibly the right number on the wrong
building, held unresolved on both attributions in
`site_facilities.yaml`. The basis line states what the document says
and the prior's note carries the doubt; only a document or the
operator can settle it, and the displacement does not depend on which
building the 24 belongs to.

Nothing heuristic decides this. The measured reasons: 29 of the 35
multi-project sites hold adjudicated figures of two or more quantity
kinds (the Stockley incomparability is the corpus norm, measured
2026-08-31); the crude classifier failed to place 17 of 35; and the
class needing displacement is **two sites today**, three when Slough's
scope resolves — hand adjudication over that class costs an evening,
and #247 already rejected every automatic alternative. The scope
entry is the same kind of object as a partition: adjudicated, written
evidence, failing the build if it names a dead site key or an unknown
claim.

**What the rung never does, in either part:** sum anything (the
campus figure is the operator's own top-level statement, and
`reconcile_components()` is the audit of it, not the source of it);
take a facility component as a site figure; displace a disclosed
planning figure without a scope entry; rank a `tentative` match; or
touch sites with no operator claim, which is almost all of them.

## Why this does not reopen the no-raw-MW ruling

The 2026-08-20 ruling barred raw megawatts from scannable rows for
third-party aggregates because their figures measure different
quantities per provider — a DC Byte MW and a Baxtel MW are not the
same unit of account, and a sortable column would assert they were.
The rung's figure is different on every axis the ruling turned on: it
is first-party (the operator about its own asset), singular (one
claim, not an aggregate), quantity-kind-named (the operator's own
term is stored and shown), dated (the `as_at` and the snapshot), and
labelled (its own weight class, never dressed as a planning figure).
The typed-standing decision recorded this as a revision of the
ruling's *scope*, not its reasoning — the reasoning is comparability,
and the label is how the ladder has always handled incomparability
(`w-modelled` marks our arithmetic the same way).

The channel's own caution stays visible: a marketing page can be
rewritten without notice — CyrusOne's LON1 figure went from 8.72 to
9 MW in eight days, which is why the snapshot chain exists — and an
operator states capacity to sell it, which is a reason it states more
than planning does, not a reason to disbelieve it. The caveat carries
both sentences.

## Cohort admission

**Recommended: `at_least_100mw` admits on the rung, with the basis
named and the count printed.** Hyperscale is the question readers
arrive with, and the two sites the rung lifts — Stockley to 112.5,
Cardiff to 148 — are precisely the rows a reader would wrongly
conclude are small. The cohort already has the machinery: floorspace-
estimate members are counted and named in the notes, and the same
treatment applies ("N members stand on an operator-stated campus
figure; every row says so"). The `limits` text updates in the same
change: the sentence explaining that a multi-facility campus may be
absent because no defensible total exists gains its remedy — "where
the operator publishes a campus figure and a hand adjudication has
accepted it, the site ranks on that figure, labelled".

Measured effect today: membership rises by exactly two. The register
channel adds zero, and no site in the 60–100 band holds an operator
campus figure of 100 MW or more except Cardiff (measured for #250,
2026-08-31).

## The Pulsant question — facilities with no planning record at all

The review sheet's tier-4 estate: twelve Pulsant facility pages with
no planning candidate anywhere, an estate whose own disclosure totals
22.12 MW of IT load — legacy colocation fit-outs that never needed a
planning application the sweep could see. The Equinix survey
(2026-08-28) measured the same class at 12 of 15 facilities absent,
so this is a large population, not a wrinkle.

**Recommended: they do not become sites.** A site is the planning
record's unit of aggregation (the four definitions, 2026-08-30); a
facility invisible to planning is a *finding about planning* — the
operating-capacity undercount the Equinix item already frames — and
it is reportable from the Operators tab, which lists these estates
with their figures and snapshots today. Creating page-anchored site
rows would change what every row in the table asserts, re-founding
part of the corpus on a marketing channel, and the `no_planning_record`
precedent does not carry: a Barbour project is a construction-
intelligence record of a real build, held under licence with
per-field provenance; an operator page is the operator's own
description of itself. What is lost by this choice, stated honestly:
no map pin, no cohort membership, no site page for an operating
facility a reader may search for — the alias file cannot help,
because there is no site to alias. If the journalism comes to need
these as rows, the honest route is a new row *class* with its own
declared basis, not quiet admission through the existing one.

## Interaction with the other channels

None, by construction. Register claims stay tier-and-count (and add
zero line-crossers). Companies House scheme-capacity figures stay in
the claims panel — an SPV's accounts state what a valuation assumes,
which is a different kind of claim again; if a rung for it is ever
wanted, it is a separate decision against this document's template.
The architect channel (Cato's 600 MW) still lacks a source-kind
vocabulary and is tracked in ROADMAP; nothing here admits it.

## What this note deliberately does not propose

- Any implementation: no field names, no code, no migration. The
  build follows the decisions, not the other way round.
- Summing facility figures into campus totals, under any conditions.
- Any heuristic displacement of a planning figure.
- A rung for third-party, register, filed-accounts or architect
  figures.
- Changing the claims panel, the Operators tab, or the green-claims
  table, which already render the channel correctly.
- Re-reading anything: the rung consumes claims that exist, matched
  and snapshot-backed.

## Decision points — decided, Luke, 2026-09-01

1. **Does the rung exist at the default position** — operator-stated
   campus figure between the disclosed rungs and the grid rung,
   filling the cell only where planning's best is grid, standby or
   floorspace? Effect today: East Havering 580 → 600, Westerhill
   150 → 300. *Recommended: yes.*

   **Decided: yes — and extended to the empty ladder** (Luke,
   2026-09-01, deciding a case this point's enumeration had not
   reached: three sites hold an eligible first-party figure while
   their planning record states nothing at all). The rung fires there
   too — a rung inserted at a position catches everything that would
   otherwise fall past it — with the read-and-silent versus
   documents-not-held distinction kept **in the caveat, not in
   whether the rung fires**: coverage is stated beside a figure here,
   never encoded in whether one ranks, and our silence must never
   read as the operator's. That took the build from the four
   predicted cells to eight, adding Saunderton, Kao's KLON-06 and
   CyrusOne LON3 (the fourth extra, Kao Harlow, was WP-R1 loading
   `component_of` an hour before the measurement).
2. **May a campus-scope adjudication displace a disclosed planning
   figure** — the Stockley/Cardiff class, hand-entered, claim named
   by `claim_name` + `as_at`, evidence written? Effect today: two
   sites. *Recommended: yes, and this is the part that actually
   answers #250.*

   **Decided: yes, conditional on the rendering** — "so long as we
   make an effort in the user interface to make this clear to
   readers". A reader must see that the planning record's own figure
   is smaller and narrower, not merely that a number exists; the
   basis line carrying planning's own figure is a requirement, not a
   styling choice, and Luke reviews the rendering before it ships.

   **One departure from this point's mechanism, made in the build and
   kept**: the pin is `claim_name` + `expected_value_mw`, not
   `claim_name` + `as_at` — five of the eligible committed claims,
   Vantage Cardiff's among them, carry no `as_at` at all (measured
   2026-09-01), so the date pin was unenforceable on the very site it
   was written for. A value pin holds whether or not a reading is
   dated and fails in the direction that matters: the operator's
   figure moved, so the adjudication has not been made about the new
   one.

   **The rendering condition is met** (Luke, 2026-09-02, on the built
   page: "It looks exactly as I imagined").
3. **Does `at_least_100mw` admit on the rung**, with the count
   printed and `limits` updated? Effect today: +2 members.
   *Recommended: yes.*

   **Decided: yes.**
4. **What the weight class is called and how the cell reads** — a new
   `w-operator` class at Medium, cell text "Operator-stated campus
   figure", basis line naming the operator's own term, the `as_at`,
   and the planning record's own best figure. *Recommended as
   drafted; the rendering is yours to adjust.*

   **Decided: proceed as proposed**, with Luke's real verdict
   reserved for the rendered page — "I'll probably respond properly
   once I've seen it." The rendering review settles 2 and 4
   together.

   **Settled: the review passed** (Luke, 2026-09-02: "It looks
   exactly as I imagined"). One rendering choice made in the build
   and approved with it: the provenance charts went from two classes
   to three, because an operator figure filed under either "from the
   site's documents" or "estimated from floorspace" would be false on
   the chart whose subject is provenance — a scoped revision of the
   two-way ruling from issue #151, approved by Luke the same day.
5. **Which quantity kinds are rung-eligible** — `announced_capacity`
   only, with operator `grid_connection` figures staying panel-only,
   or should an operator grid figure be allowed to feed the existing
   grid rung? *Recommended: `announced_capacity` only, until a case
   needs otherwise.*

   **Decided: as recommended.**
6. **The Pulsant class** — Operators-tab-only as recommended, or a
   new declared row class for operating facilities with no planning
   record? *Recommended: Operators-tab-only, revisited if the
   journalism needs the rows.*

   **Decided: Operators-tab-only today, and explicitly expected to
   be revisited — not a settled boundary.** Luke's reasoning,
   recorded because it names the principle: authority belongs to
   sources, not to the planning register as such. "Getting the
   Barbour stuff into the corpus was useful, even before we managed
   to match (most of) them to planning applications. So we may judge
   other sources to be authoritative also. But not yet." A named
   candidate trigger: the NESO EIR reply (due ~10 September 2026) —
   "if our EIR to NESO comes back with lots of granular details
   about datacentre projects that we haven't got planning
   applications for, we would believe them." When a source earns
   that standing, the route is the one this document sketches: a new
   row class with its own declared basis, never quiet admission
   through the existing one.
7. **Sequencing** — the displacement entries (decision 2) are also
   the first outputs of the 35-campus review, so implementing the
   rung before the review means the review's confirm-the-roster pass
   lands directly into a mechanism that renders it. *Recommended:
   rung first, review entries as they come.*

   **Decided: agreed** — and extended: 2.11 may release once WP-E is
   implemented, before the full 35-campus review, whose remaining
   entries render as they land. The review was never a release gate;
   an unreviewed campus keeps today's behaviour.
