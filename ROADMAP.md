# Roadmap

What is still to do. Everything already built and decided — including
the approaches tried and rejected, which are worth knowing before
re-proposing them — is in [HISTORY.md](HISTORY.md).

Current state: **501 sites** (plus 7 pre-planning; 508 rows in the
reader), **1,978 applications** in the site universe, **60,142
documents** — the counts 2.11 was stamped at (HISTORY, 2026-09-01/02),
unchanged since the evening of 2026-08-30, whose falls were deliberate
(the Kao merge, the adjacent-power chain, the pre-planning dedup).
Findings and adjudication counts move while the corroboration pass
runs and are deliberately not restated here — `scripts/corpus_stats.py`
prints them, and each release states the boundary it was stamped at.

**The base is 2.11, released** (Luke, 2026-09-02, PR #341; HISTORY,
"v2.11 — the operator rung, and the release the guards earned").
Artefacts in `data/exports/phase2.11_build/`, which is the baseline
the next build's release diff is read against. Cloud Run serves
whatever `index.html` `cloudrun/deploy.sh` was last run against — the
deploy is the script, not the merge.

**2.11 was the site / facility / campus effort** (Luke, 2026-08-31,
redefining it: "the focus of 2.11 has evolved into the effort to make
sense of the site/facility/campus issues") — the capacity-model section
below. What it shipped: the ladder rung, which closed #250's two
measured cases; #247's facility prior, built and consumed; the
adjacent-power relationship (#252); and, as its preliminary, the
verbatim gate's whitespace fix and re-gate, which ran on 2026-08-31 so
that the campus work reads a corpus holding the recovered figures
(HISTORY, "The re-gate reinstated the findings the gate had wrongly
rejected"). **What carries forward** is the rest of that section: #248,
the 35-campus review (33 entries still `unreviewed`), #247's general
case — a campus with no published roster still shows one building's
figure — and the partitions the review owes. The over-merged site
records still hold the Premier Park and DataVita claims under
`considered:`.

**Model choices.** The decisions in force, the comparisons behind them
and the measurement lessons are in [docs/MODELS.md](docs/MODELS.md);
the roster with counts is ARCHITECTURE's "Which model runs which
task"; the terra experiment of 2026-08-31 and the return to
`gpt-5`/`reading-1.4` are HISTORY. What is still to decide, each
detailed under "Open" in that file:

- **A prompt A/B on terra before it is tried again for the readings**
  (Luke proposed it 2026-08-31; unscheduled). Scored on the sites where
  terra demonstrably lost figures, in both directions — figures
  recovered *and* quantity-type flags retained — and against the
  `reading-1.4` outcome, not the old baseline.
- **A durable machine-reading model.** `gpt-5` is legacy at OpenAI; the
  return to it was a deferral.
- **Whether the script's `--model` default follows the decision.** It
  is still `gpt-5.6-terra`; the runbook says pass `--model gpt-5` every
  time. One line, Luke's call.
- **`gpt-5.6-sol` as a deep reader**, untested.
- **Which reader re-extracts what the local model read** (Phase 3,
  below): the 2026-08-28 choice is the default position, not a decision.

## Changes waiting for a re-read they cannot justify on their own

**The policy** (Luke, 2026-08-31). A full re-read has to clear one of
two bars: *what we hold is dangerously misleading and needs
correcting*, or *the re-read brings a very important new revelation*.
Neither is met today. And spending, then discovering a further problem
that needs another re-read, is the outcome to avoid — so improvements
that would each individually mark the corpus stale **accumulate here
without being enacted**, and go in together when something crosses the
bar.

**Keep the tiers apart, because they are not the same money.** Batching
a cheap change behind an expensive threshold is its own waste.

| tier | what it re-runs | recorded cost |
|---|---|---|
| re-adjudication | `power_adjudication` over existing findings | **~$20–40** (runbook, "Decisions outstanding") |
| machine-reading re-submit | ~359 sites, ~26M input and ~3M output tokens | **~$34, measured 2026-08-31** |
| full deep re-read | 48,191 documents | the ~$1,000 class; nothing in the repo records it |

Only the third is what the policy above is really about, and **nothing
currently on the table needs it.** The gate fix applies to future reads
and recovers past ones offline; the re-gate reads nothing; adjudication
is tier 1. Say which tier a parked item needs, so a cheap one is not
held behind an expensive one's threshold.

**Scoping a machine-reading re-read, when one is warranted** (established
2026-08-31). Three cuts, in order of defensibility, each measured before
spending: sites whose `input_hash` has moved — their stored reading
describes a different document set, the one real staleness rather than a
version-string one, and the cut a bare `--submit` already applies
because `_already()` keys on the hash; sites whose citations are still
unlinked after `mreading.figure_sources` has run — it resolves quotes
copied from the structured facts to their document at export time, so
an older reading already renders linked and a re-read buys the model
citing natively plus the cases `figure_sources` drops because the text
stands on more than one document; and the datacentre-classed subset
rather than the whole.

**One downstream cost the re-gate did create, and it was tier 1.** A
recovered finding carrying a capacity figure reaches a site's power
panel only through `power_adjudication`, so the recoveries with a
numeric power unit joined the adjudication tail — 385 figures after
dedup, one batch, under $6 all in (HISTORY, 2026-08-31). Work a
re-gate implies rather than work it avoids, and the precedent for the
next one.

**Accumulating now:**

- ~~**The guard on the machine-reading gate's squash**~~ and
  ~~**`reading-1.3`**~~ — **both enacted 2026-08-31**, riding on the
  move to terra, which re-reads every site anyway. `GATE_VERSION` is now
  `gate-2.1`. This is the accumulation rule working as designed: park a
  change that cannot justify a re-read on its own, then land it with one
  that can. **The list is empty; check it is still empty before the
  submit runs**, because a change landing after that has missed the
  boat.
- **`power-1.1`** (tier 1, ~$20–40, so it does *not* need to wait for
  the others). Committed but inert and unvalidated; the 229-figure
  ground-truth set exists to test it against the known-bad cases first.

**Enacting rule:** when the bar is met, re-read once with everything on
this list applied, and check the list is empty before submitting. A
change landed after the submit starts has missed the boat and waits for
the next one.

**The Phase 3 corroboration read is roughly 60% through its 48,191
in-scope documents** (the 2.1 prose read completed 2026-08-11;
HISTORY). Two numbers belong beside coverage claims: 4,204 documents
in the repetitive classes are sampled at one in five by policy, not
backlog, and 231 are held but contain no words at all, confirmed blank
by two independent OCR engines. Every capacity figure that existed at
the 2.1 boundary is adjudicated.

---

## Regenerating a release

The chain, its ordering constraints and the traps are in
[docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md). Two steps
must precede the artefacts: adjudication corrections (enforced in code
by `dcp/adjudication_gate.py`) and the Drive staging rebuild that picks
up the new CSV adjudication columns.

## The capacity model — what a site's power figure means

Opened 2026-08-30 out of one question from Luke: why does VIRTUS
Stockley Park, a campus of five facilities, show 24 MW? The answer took
most of a day and turned into four issues, one of which corrects output
that is live now. **Read this section before touching site capacity;
the detail and the evidence are in the issues, and the reasoning that
produced each decision is in their comment threads.**

#252 was sequenced first because it changed which figures a site
holds; it shipped 2026-08-30, so the remaining three read a settled
membership.

### 1. #252 — adjacent power relates to a site, it does not belong to one

**Shipped end to end on 2026-08-30** — the veto at all three of the
clusterer's admission paths, the relationship table, the reader's
"Adjacent power" box (documentary rows as entries, proximity as a
count), eight sites retired, zero adjacent-power memberships verified
remaining, and the ladder's generation rung honouring `plant_type` so
export plant no longer stands in for load. The full account — the
survivor check that corrected "seven figures go" to two, the two extra
admission doors found by running it, the Kingsnorth follow-up that
dissolved on measurement — is in HISTORY ("Adjacent power leaves
membership", 2026-08-30) and on the issue with its queries.

What survives it here:

- **The two university leads, tracked as leads and not as sites**
  (Luke's call): `Plymouth/20/01477/MOR` — a generator "serving the
  University's relocated data centre", University of Plymouth, Drake
  Circus — and `WestNorthamptonshire/N/2018/1565` — a DRUPS "to
  support the Newton Data Centre", University of Northampton, Avenue
  Campus. Each is the only trace the corpus holds of the data centre
  it serves; both records stay in `applications` and in the
  relationship table's history. A future sweep of either university's
  register is the follow-up.
- **"Site X shares grid infrastructure with Site Y" remains
  deliberately unattempted.** A proximity row is a candidate, never a
  claim — the sentence needs the applications to name the same
  substation or connection point, and that extraction is the open
  design question, not the tables.
- **The family-reference tie is a candidate fourth relationship
  basis.** Fifteen of the ejected records are family-known to their
  neighbouring site (a discharge citing the substation consent it
  discharges against) and that documentary tie is recorded nowhere;
  only the three Barbour-linked records carry a cohort row.
- **Two procedural singletons stand as tracked warts of the typed
  `parent_ref` gap**: `Barnet/26/0696/CON` and
  `Hillingdon/71554/APP/2025/2436`, each the paperwork of a vetoed
  energy scheme, stranded because family edges cannot see typed
  parents.
- **The `not_dc` live-member leak**: membership does not track verdict
  changes, and figures can stand on members whose latest verdict is
  `not_dc` (Hallen's did). Small, verdict-tracking in kind.
- Six adjacent-power records attach to no site at all: keyword-swept,
  no coordinates. Unchanged by any of this.
- **The class has a Drive home since 2026-09-02** — `adjacent_power/`
  beside `sites/`, one folder per application with an `_index.md`
  naming the sites it stands beside. Found by the 2.11 staging build,
  the first after the veto: 744 held documents across 28 applications
  had nowhere to go and a `--prune` sync would have binned them, four
  of them cited by machine readings. Since 2026-09-02 the reader's
  "Adjacent power" box links the class's Drive folder
  (`dcp.drive.ADJACENT_POWER_FOLDER_ID`, read back from the sync ledger)
  and each entry its own folder once synced, beside the register link.
- Hayes Bridge's doubled N+N 300 (the "Not in an issue" note below)
  still stands.

### 2. #247 — a campus load figure from one building is shown as the site's

Stockley Park displayed 24 MW until the operator rung displaced it on
2026-09-01 — it now ranks on VIRTUS's 112.5 MW campus figure, labelled,
and the general case below is unchanged for every campus without a
published roster. The 24 is ours and correctly cited —
but it is a **commissioning milestone**, from a document titled *VIRTUS
LONDON7*: "We expect Data halls 1, 2, 3, 4, 6, 7, 10 to be handed over
to the client by the end of 2021 … power capacity of 24MW". VIRTUS
publishes LONDON7 at 32.5 MW.

**Decided: no campus total renders.** The campus holds
installation-specific figures for three of five facilities and **no two
are the same kind of quantity** — LONDON5 an average operational load
(6.613 MW, 2018), LONDON7 a partial handover (24 MW, 2021), LONDON14 a
design capacity (22 MW, 2023). A floor requires adding like to like. The
three render per facility with their kinds stated, and the
incomparability is left visible **because it is the finding**.

**The finding, which needs no code and may be the most valuable thing
here:** no document has ever stated this campus's load on a common
basis, across five facilities built on one site over at least seven
years, and the planning system did not require it. The same holds at
VIRTUS Slough. That is a question for the operator and for Hillingdon.

**Facility identity comes from the document, not the application.** Stem
`37977` holds papers naming both LONDON5 and LONDON7. Only 8 of 434
documents name a facility, in four spellings. A naive filename pattern
is dangerous: matching on the whole URL made a Central Bedfordshire
SharePoint path `/sites/LPPSCasework/DC50/` look like a facility 1,673
times.

**Summing is wrong in most cases.** Within a facility, phases are
subsets (LONDON14's 22 MW is two 11 MW phases). Across applications, a
scheme restates its own capacity — Cambois carries 1,100 MW in three
applications and sums to 3,300.

**The sites-table cell, agreed:** keep the number so sorting and ranking
survive, drop it to `w-implied` weight because it is not a disclosed
*campus* figure, and let the basis line name the facility and the
coverage — "LONDON7 only · 3 of 5 facilities disclose, on 3 different
bases". Rejected: showing no number, which drops the site out of sorting
and out of `at_least_100mw`.

**`data/priors/campus_scope.yaml` (merged, PR #251) lists all 35
multi-project sites**, every entry `unreviewed`, with a deliberately
crude `proposed` classification that decides nothing and failed to place
17 of them. The four kinds are distinct facilities, phases of one
scheme, a masterplan beside its own components, and co-located
operators — and summing is right in at most one.

**The review will grow, not shrink.** `PTNO-12058499` turned out to be
three operators plus a fourth scheme: Telehouse (North Two, West 2,
South), Global Switch (House, London South), Republic, and the Astoria
Way change-of-use at E14 9FT. Luke: "It's three." Partitioning it into
four creates **two new multi-facility campuses** each needing a scope
decision. Global Switch was proposed as the first constructible total
in the corpus — two facilities, one operator, both figures `it_load`,
80 + 35. **Tested against the corpus 2026-09-01 (Luke asked for it) and
the premise does not hold.** Each building states two figures of
different kinds, and the pair the hypothesis adds is the wrong one from
each:

| facility | figure | what the document calls it |
|---|---|---|
| London East (Global Switch House, `TowerHamlets/PA/24/01932/A1`) | **74** | the design: "Building Total 74MW", "74MW of IT capacity split across nine floors" |
| | 80 | a ceiling: "upgraded to *feasibly accommodate up to* 80MW IT load" |
| London South (`TowerHamlets/PA/21/02777/A1`) | **35** | the scheme: "a new build 35MW multi-story data centre, expanding on the existing Global Switch Ltd London East" |
| | 30 | a floor: "shall provide *at least* 30MW IT power" |

So 80 + 35 adds a feasibility ceiling to a scheme headline while each
building's other figure goes unused; that one application alone carries
nine distinct `it_load` values. It is still a better case than Stockley
Park — one operator, one campus, every figure an IT load rather than an
average against a milestone against a design capacity — so the question
it tests is sharpened rather than answered: **which of a building's own
figures is the one a campus total may add**, which is a judgement per
facility, not arithmetic. Recording those four with their kinds is what
a facility roster is for.

**The site is not ready to carry one**: `PTNO-12058499` holds 21
applications across five distinct buildings — Global Switch House, East
India Dock House, Mulberry Place Town Hall, the Docklands Travelodge and
1 Paul Julius Close — which is the partition this section already owes.

**A design gap the test found, not yet built.** A site holding several
operators' campuses cannot say so: `site_facilities.yaml` maps a site to
a flat list of facilities, so Global Switch's two, Telehouse's three and
Republic's would sit in one list with nothing recording which campus
each belongs to — losing the distinction the four definitions draw. An
optional `campus:` per facility would fix it. **Not added**: an unread
field is a decision for the review rather than for the file, which is
why PR #305 was closed.

**Iron Mountain: the block is a bot block, the arithmetic was right,
and the pages disagree with each other** (2026-09-01, after Luke asked
which URL was being used and then found the passage two probes had
missed).

*Two wrong readings preceded this one and are worth keeping. The first
said the pages were unreachable, on two 429s. The second said LON-2's
27 MW was "published nowhere", having read the campus page through a
browser. Both are the probe-that-could-not-see error, and this file's
own figures were right the whole time.*

**The URLs in `fetch_operator_snapshots.py` are correct.**
`ironmountain.com` returns **429 site-wide, its own homepage
included**, so this is a bot block wearing a rate limit's status code
and **"retry with backoff" can never work** — the same shape as the
Camden and Portsmouth 403s recorded elsewhere here.

**Why a browser is the wrong instrument, which is the durable
lesson.** The per-facility figures live in the campus page's FAQ,
inside a collapsed `<details>` accordion. Collapsed `<details>`
content is in the DOM but is *not* rendered text, so `innerText` — and
therefore any browser-rendered capture — silently omits it, which is
how the second wrong reading happened. `visible_text()` in the
snapshot fetcher strips tags from the **raw HTML** and evaluates no
collapse state, so **it would have captured the passage**. The
snapshot format is right and the browser view is the narrower one;
where a page hides figures behind accordions or tabs, prefer the
HTML-stripping capture.

**What the campus page states**, verbatim from that FAQ:

> LON-1 offers 17,000 square meters (183,000 square feet) and 8.7 MW,
> originally a Credit Suisse facility that has been upgraded to
> current standards. LON-2 is a greenfield data center with 27 MW
> built for hyperscale requirements. LON-3 is currently under
> construction, with a planned capacity of 25 MW and 5,220 square
> meters for 2026.

So **8.7 + 27 + 25 = 60.7 against a stated 61 MW** — this file's
figure all along, and a second self-auditing campus after Saunderton,
its 0.3 being rounding of the same kind as Kao's 0.2.

**LON-2's figure is corroborated outside the marketing channel**
(Luke, 2026-09-01): Iron Mountain's own investor-relations
announcement, *"Iron Mountain Expands EMEA Data Center Footprint With
New 27 Megawatt Facility Build in London"* (2021,
investors.ironmountain.com), states the 27 MW in a communication to
investors and dates the build. That is a stronger authority than a
location page, and it means the only facility with no page of its own
is the best-evidenced of the three.

**The new finding is that Iron Mountain's own pages contradict each
other**, which only appeared because both were read:

| | campus page FAQ | the facility's own page |
|---|---|---|
| LON-1 power | 8.7 MW | 8.75 MW (printed once as "8,75 MW") |
| LON-1 area | 17,000 m² (183,000 sq ft) | 10,400 m² (112,000 sq ft) in prose, "14.000" in its stat block |
| LON-3 area | 5,220 m² | 5,200 m² |

Three areas for one building across two pages, and 183,000 against
112,000 square feet is a 63% divergence rather than a rounding — the
pages do not say whether one is gross building area and the other
technical space, and only the operator can settle it. **LON-2 has no
facility page at all** (404); it exists only in that FAQ paragraph and
in the investor announcement.

**Held, and the roster written, 2026-09-01.** The three pages were
captured through the browser-assisted route
(`scripts/browser_receiver.py`, docs/PORTAL_NOTES.md) and stored by
`fetch_operator_snapshots.py --from-file`, so the *fetcher's* text
extraction produced the snapshot rather than the browser's, per the
lesson above — which is what the prior's held-copy contract was
protecting. What that turned into: five quote-verified claims (the
61 MW campus total, its three FAQ components, and LON-1's divergent
8.75 from its own page), five matches to site 529, and every one of
the three facilities carrying an `operator_roster` identity beside its
planning or Barbour one. `reconcile_components()` now measures the
campus at 61 against 60.7.

*The block is Vercel Attack Challenge Mode — the 429 carries
`x-vercel-mitigated: challenge` — which is why backoff can never
reach it and why the answer was an instrument change rather than
patience.*

Two substation applications at *Land to West of East India Dock House*
belong to none of the four and are what raised #252.

**Also unresolved here:** Stockley Park's 22 MW is adjudicated as both
`it_load` and `total_site` from the same document, and must resolve to
one before it can be summed or compared.

**The missing object is the facility, not a sharper site** (assessed
with Luke, 2026-08-30 evening, after the adjacent-power work and the
operator-pages fold). Four definitions, written down so they stop
being re-litigated:

> A **site** is the planning record's unit of aggregation — the
> cluster of applications and projects that belong together
> documentarily and spatially — not an asset. A **facility** is the
> asset: one building or installation with one operator, one identity
> (LONDON7, KLON-03), and figures of stated kinds. A **campus** is an
> operator's own aggregation of facilities, which is a claim about
> sites, never a redefinition of one — VIRTUS's Slough campus is seven
> facilities where our site holds three, and the site must stay
> derivable from the planning record. A **scope** decision lives at
> the facility↔site mapping: which facilities a site holds, and
> whether their figures roll up.

Site-load vs campus-load was never a boundary problem; it is an
attribution problem. Figures attach to applications, applications
aggregate to sites, and the thing a figure is actually *about* — the
facility — exists nowhere in the model. That is the same disease #252
just cured for substations: membership (or site-attribution) because
the model has nowhere else to put it. The same recipe applies — do
not sharpen the container, add the missing relation with its
evidence.

**The proposal: a facility prior**, `site_adjacent_power`'s sibling —
hand-curated on the `site_aliases.yaml` contract (a dead site key
fails the build; every entry carries its source). Per site: the
facility roster with the source that names it, and per facility any
figure attribution a document supports. Two sources of identity, kept
distinct: planning documents where they name a facility (8 of 434 at
Stockley — sparse, hand-adjudicated), and operator rosters where
published (snapshot-backed claims since 2026-08-30). What the
operator channel now supplies, per campus where a roster exists:

- **The denominator, sourced.** "3 of 5 facilities disclose" needed a
  sourced count of 5; VIRTUS's roster is that source, with a snapshot
  behind it.
- **A self-auditing calibration case.** Saunderton: 9.5 + 22.5 + 16 +
  30 against a stated "Campus Total of 78 MW" — exact. The operator
  whose arithmetic checks itself is the benchmark for when
  `total: sum` can ever be trusted.
- **A discrepancy worth putting to the operator.** VIRTUS Slough
  states 145.5 MW against 132.2 summed from its own seven rows.
- **The attribution wrinkle a roster cannot resolve.** Planning gives
  Stockley 24 MW from LONDON7's 2021 handover; VIRTUS puts 24 on
  LONDON5 and 32.5 on LONDON7 — possibly the right number on the
  wrong building, and only a document or the operator can settle it.

**Two cautions that bound the layer.** The roster gives campus
*structure*, never planning-figure *attribution* — planning figures
stay site-attributed unless a document names the facility or a hand
adjudication does. And the quantity-kind discipline survives intact: a
sum needs like kinds on same-layer figures, whichever layer they sit
on.

**Built, 2026-08-31**: `data/priors/site_facilities.yaml` with
`dcp/site_facilities.py` on the `site_aliases.yaml` contract, both
cautions enforced by the loader rather than remembered — an
attribution references a claim or a planning document and can never
carry a value of its own, and a roster-sourced planning attribution
cannot be written at all. Seeded with Kao Harlow (KLON-01–04), VIRTUS
Slough (the seven-facility roster beside the three-facility site),
Saunderton (four of four facilities, the only complete and
self-auditing roster in the file — see the same day's spec-sheet
ingest), Stockley Park (the
LONDON5/LONDON7 wrinkle held unresolved on both attributions) and
Hayes (LON6/7/8 on Barbour titles, a third identity-source kind the
build vocabulary carries). The reader build validates liveness
and held copies; nothing renders from the prior yet — "3 of 5
facilities disclose" is a later consumer. The ladder rung was designed
and built on 2026-09-01 ([docs/PLAN_OPERATOR_RUNG.md](docs/PLAN_OPERATOR_RUNG.md))
and reads the claims and `campus_scope.yaml`, not this prior.

### 3. #250 — a campus ranked on one facility falls below a line it would clear

The mirror of #247 and **the invisible half**. A wrong amber pill invites
a check; a site simply absent from `at_least_100mw` invites nothing.

Luke's reason for raising its priority: "hyperscale" is a live news
issue, so `at_least_100mw` is not one cohort among several — it is the
answer to the question a reader arrives with, and its definition takes
the 100 MW line from the industry rather than from this project.

**A cause we can act on: 147 capacity claims with a figure match no
site** (re-measured 2026-08-30 evening, after the #255 review
hand-matched most of the operator channel — Vantage Cardiff's 148 MW,
the original headline example here, now attaches to a site that ranks
on it):

| source | claims | matched | unmatched with a figure |
|---|---|---|---|
| NESO EA register | 119 | 13 | **106** |
| operator website | 81 | 43 | 35 |
| Companies House | 22 | 10 | 6 |
| EA permit | 42 | 14 | 0 |

*The NESO row moved on 2026-08-31, when the outcomes were written into
the matches file: **18 matched, 101 unmatched**, and every examined row
now carries a match or a `considered` reason.*

The NESO EA register was the live work, and was triaged 2026-08-31 —
**`docs/NESO_UNMATCHED_TRIAGE.md` is the row-by-row result.** What it
establishes, before anything is proposed:

- **61 of the 106 are not data-centre schemes**, and never will be. The
  register lists transmission demand customers of every kind; the
  cohort is dominated by hydrogen electrolysis, rail traction supply,
  carbon capture, steel and battery storage. They belong in
  `considered` with a reason, not in a backlog.
- **24 of the 106 had already been adjudicated** in the matches file's
  own `considered` section on 2026-08-20, and the triage re-examined
  them blind because its probe looked for a `row:` key where the file
  uses `rows:`. Several earlier judgements are better and stand — the
  Iver rows especially ("no Ark scheme at Iver anywhere in the corpus…
  a null worth reporting, not matching"). **One is overturned**: Quest
  Park is recorded there as having no corpus site in the right place,
  and site 83 holds 435 documents. (Writing the outcomes found a
  second, Cottam Giga — see the outcome note below.)
- **29 rows are actionable**, but only six of those candidates are new,
  three of them strong: Cato, Relode Immingham against Humber Tech Park,
  and Bro Tathan against Vantage's CWL2. Ten more are real schemes the
  corpus does not hold at all — leads, not matching failures.
  **Outcome, 2026-08-31: two of the three survived contact with the
  evidence.** Cato and both Bro Tathan rows are matched, alongside
  Quest Park and Cottam Giga — each of those two overturning a
  2026-08-20 null, Cottam's site having been in the corpus since
  2026-08-02. Relode Immingham is **not** matched, and is not a
  data-centre scheme as such: "Relode" appears nowhere in the corpus
  and resolves at Companies House to Relode Energy Limited (15568908),
  whose own site identifies it as the "Power Park" developer —
  gigawatt-scale multi-customer supply hubs (eHGV charging, port
  shore-power, e-fuels) whose stated markets also include data
  centres. The same identity claims the register's four anonymous
  "Power Park" rows: 3,830 MW across the five, a third hub-portfolio
  family beside the two GEC ones, with the same undeclared-consumer
  standing. Ratcliffe's null was upheld the same way: the one
  Ratcliffe on Soar corpus site is a battery scheme on its own
  applications' text.
- **The "Green Energy Centre" portfolios are the thing worth pursuing,
  and they are not gas.** An earlier version of this bullet said four of
  them held a gas connection and a demand connection at once, following
  §3 of `docs/EXTERNAL_DATA_SOURCES.md`; **both were wrong and are
  corrected** — 52 TEC rows across 42 schemes, not one carrying any gas
  term, plant types combining `Demand`, storage, solar and wind. What
  stands: nineteen of those schemes hold 8,660 MW of transmission
  demand in the Existing Agreements register, thirty of the 52 TEC rows
  carry `Demand` in their plant type, almost every scheme is named after
  its substation, and **none has a planning application in this corpus**.
  Ethos Green says publicly that its centres colocate data centres (a
  5 GW agreement with Frontier Power); the registers do not say so, and
  the import-leg-of-a-hybrid explanation fits the coding equally well.
  Untested either way — which is the open question, not a finding.
- **A developer's name and the planning record's name are different
  things** (Luke, 2026-08-31: "Quest Pit is the true location; Quest
  Park is the operator rebrand"). The register carries the rebrand, the
  planning file keeps the ground's own name — so a name search across
  the two has a systematic blind spot, failing towards confident
  negatives.
- **Search `site_aliases.yaml` alongside the derived names.** The fix
  for the above is already curated: the alias file holds both names in
  one string — "Quest Park Data Centre, Quest Pit"; "Cato Data Centre
  campus, Auchtertool, Fife (ILI Group)" — and either would have matched
  the register outright. A derived name is what a source called a place;
  an alias is what a person established it *is*. Any future name search
  against this corpus that skips the 56 aliases re-derives that work
  badly, which is what two passes of the triage did before Luke pointed
  it out. **Cato is the strongest new candidate to come out of it**: a
  named site, a named operator (ILI Group), and a contracted 600 MW
  against the architect's 600 MW recorded below — though the site's own
  documents state both a 600 MW and an 850 MW `it_load`, so the
  convergence is three quantity types landing on one number, not three
  sources agreeing. Its 1,200 MW `thermal_input` row carries a standing
  warning in `docs/REGENERATION_RUNBOOK.md`.
- **19 rows are Ethos Green "Green Energy Centres"**, 8,660 MW, held
  apart from both buckets: those hubs colocate data centres with
  generation and storage by design — Ethos has a joint development
  agreement with Frontier Power for up to 5GW of colocated capacity —
  so a GEC row is demand whose consumer is undeclared, not demand that
  is known to be something else.

So the earlier framing was wrong twice, and both corrections are in the
triage document: Global Switch London East 87 MW and London South 70 MW
are **not in this register at all** (they are `operator_website` claims,
and belong to the operator channel's 35), and "any of the 106, matched,
could move a site across the line" is true of 29. The remaining
operator-channel 35 are mostly the sheet's "not yet" and keyless rows,
tracked there.

**What is left on #250, now the triage has run:**

- ~~**Write the outcomes.**~~ **Done, 2026-08-31.** Every one of the
  106 examined rows now carries an outcome in
  `neso-ea-register-matches.yaml`: five new matches (Cato and Quest
  Park at `strong`; the two Bro Tathan rows and Cottam Giga at
  `probable`), an addendum on the 2026-08-20 class entry recording the
  two overturns and the Ratcliffe upholding, and `considered` entries
  for everything else — the 19 GECs held apart, 36 rows naming their
  own non-data-centre technology, 17 whose name identifies nothing
  (the four "Power Park" rows and CEG LP2 at Culham JET flagged inside
  that entry), four new coverage leads, the five Relode "Power Park"
  rows identified as a third hub-portfolio family (see the outcome
  note above), and Bryn Coch and Waltham abstained with the test that
  would settle each written down. **Loaded 2026-09-01**: the five
  matches and nine operator claims are in the database, and
  `component_of` reached the store with them.
- ~~**The under-ranking itself.**~~ **Closed 2026-09-01 by the
  operator rung** (the item under "Operator pages and typed standing"
  has the account). Both invisible sites now rank on their operator's
  own campus figure, labelled: Stockley Park 24 → 112.5 and Vantage
  Cardiff 67.2 → 148, and `at_least_100mw` gains exactly those two.
  What is *not* closed is the general case — a campus with no
  published roster, or one whose scope nobody has adjudicated, keeps
  today's behaviour and stays invisible for the reason this section
  describes. The 33 remaining `unreviewed` entries in
  `campus_scope.yaml` are that residue.
- ~~**State the exclusion in the cohort's own `limits`.**~~ **Done
  2026-08-31 evening** (commit 81d286f): `at_least_100mw.limits` in
  `dcp/site_cohorts.py` now says a multi-facility campus can be absent
  because its figures are per-facility and no defensible total exists,
  Stockley example included, with `rule_version` untouched — limits
  prose is not the rule. This item still read "still not done" a day
  later; caught 2026-09-01 while the rung design read the cohort.
- ~~**Measure how many sites the under-ranking actually affects**~~
  **Measured, 2026-08-31**, against the live corpus through
  `site_cohorts.load_inputs` (the ladder that actually feeds the
  ranking) and `capacity_claims.load_site_claims`, folded to the
  latest reading per claim. Of the 35 multi-project sites in
  `campus_scope.yaml`: **8 already rank at or above 100 MW**, and
  **the invisible class is exactly two sites** — VIRTUS Stockley Park
  (ranks 24.0 MW against the operator's 112.5) and Vantage Cardiff
  (67.2 against 148), both already matched, snapshotted, first-party
  claims. **A third joins when its scope question resolves**: VIRTUS
  Slough ranks on nothing while its campus page's 145.5 MW sits in
  the store unmatched — correctly, because the site claims three
  facilities and VIRTUS rosters seven, the open question in
  `campus_scope.yaml`. The register channel adds zero line-crossers,
  so tier-and-count costs it nothing. Eight more sites sit at
  60–100 MW (London Digital Park 89, Telehouse North Two 80, Brent
  Cross 75, Longcross 73.6, Premier Park 72, Cardiff 67.2, Cody Park
  60, former Akzo Nobel 60) — for all but Cardiff no operator campus
  figure of 100 MW or more exists, so a ladder rung would not inflate
  the cohort. Five of the 35 rank on nothing at all. And **29 of the
  35 hold adjudicated figures of two or more quantity kinds** — the
  Stockley incomparability is the corpus norm, which is the
  measurement backing #247's facility-prior direction over any
  summing. Re-measure rather than re-quote; the numbers move with the
  corpus.

### 4. #248 — a figure we assemble is not a figure a source states

**Not speculative: 234 of 9,747 site-capacity figures (2.4%) hold a
value that appears nowhere in their own quote.** They were computed —
"Wind Generation of 3 no. 900kW turbines" → 2.7 MW; "4no 25kw split
units and 2no 7.1Kw" → 0.1142 MW; "1 x 1.25MWe and 57 x 2.4MWe diesel
generators" → 140.35 MW.

The arithmetic is right in each. That is not the issue. They render
exactly as a figure a document states, with a verbatim quote beneath
that does not contain the number, and a reporter checking one finds the
components and no total — with no way to tell a disclosure from our
multiplication.

The reader's weight ladder already has a rung for this in spirit:
`w-modelled` with a `≈` glyph, used for a floorspace estimate because it
is "arithmetic on an area rather than anything anyone published". A
figure multiplied out of a unit count is the same kind of thing and does
not carry the mark.

**First thing to establish:** how many of the 234 are a plain unit-count
multiplication (defensible, needs a label) versus something looser. The
generation cohort's existing exclusion of per-unit ratings is the
nearest precedent for where the line sits.

### Approaches tried and rejected, so they are not re-proposed

- **Summing a campus's figures into a total.** Rejected twice, for two
  different reasons. Arithmetically, phases are subsets of their own
  facility and a scheme restates its capacity across its own
  applications (Cambois: 1,100 MW three times, summing to 3,300).
  Editorially, Stockley Park's three facility figures are an average, a
  milestone and a design capacity — a floor needs like added to like.
- **Deriving facility identity from document filenames.** Sparse (8 of
  434 documents), inconsistent across operators (`LONDON7`, `BUILDING2`,
  `LON14`), and actively dangerous: matching the whole URL turned a
  council's SharePoint folder into a facility 1,673 times. Facility
  names belong in a prior, hand-adjudicated.
- **Routing planning-document figures into `capacity_claims`.** Proposed
  early and wrong — Luke: "capacity claims come principally from the
  applications, and we already have them, and we're already displaying
  them." The per-application figure panels already carry document, page,
  quote and gate line. `capacity_claims` is for figures published
  *outside* the planning system, and mixing the channels would lose the
  distinction the reader depends on.
- **Showing no number in the sites-table capacity cell for a
  multi-facility campus.** More honest in isolation, but it drops the
  site out of sorting and out of `at_least_100mw` — which, given
  hyperscale is the question readers arrive with, hides the biggest
  sites behind their own complexity.
- **A computed rule for withholding the generation-exceeds-load ratio.**
  "More than one application with a load figure" fires on 35 sites and
  would be wrong on most of them, because the usual cause is one scheme
  restating itself. What distinguishes Stockley Park is a document
  naming a facility, which exists corpus-wide for 8 documents. Hand
  adjudication, not a heuristic.
- **`at_least_100mw` admitting a campus on a summed figure.** Not
  rejected outright but parked: it needs #250's matching work first,
  because an operator's published campus figure may make the question
  moot. **It did, for rostered campuses** — the operator rung
  (2026-09-01) admits a published campus figure, labelled, with no
  summing; what stays parked is the campus with no roster, which is the
  35-campus review's residue.

### How to continue the 35-campus review

`data/priors/campus_scope.yaml` holds every multi-project site with
`scope: unreviewed`. Nothing reads it, so an unreviewed site keeps
today's behaviour — the largest single figure, framed as a floor. A
reviewed entry sets `scope` and `total` and carries a `reason` written
as evidence, the way `site_partitions.yaml` entries do.

Luke's method, and it worked: **take them one at a time and discuss
each**, because they are not one kind of thing and the classifier
cannot tell them apart. The first one consumed a long stretch and
produced a four-way partition, a modelling issue and no scope decision —
so budget accordingly, and note the honest counter-argument that a
targeted pass over the largest sites may deliver more than an exhaustive
one.

**Two axes, independent, and easy to conflate.** A *partition*
(`site_partitions.yaml`) decides which site a record belongs to. A
*scope* (`campus_scope.yaml`) decides how a site presents its power.
Partitioning `PTNO-12058499` did not resolve it — it created two new
multi-facility campuses that each need a scope decision.

**Revised method after the operator-pages fold** (2026-08-30 evening,
and see the facility-layer note under #247): for a campus whose
operator publishes a roster, the review is no longer classify from
scratch — it is **confirm the operator's roster against the planning
record, facility by facility**, a much cheaper pass. The roster gives
the facility list, the per-facility figures on one basis, and often a
campus total that can be checked against its own rows (Saunderton's
checks exactly; Slough's is 13 MW over). The scope entry then records
which facilities the site holds, which the roster names beyond it, and
whether a total is constructible. Start with the campuses whose
rosters landed as snapshot-backed claims: VIRTUS Stockley Park and
Slough, Kao Harlow, Ark's parks, the CyrusOne pairs. Global Switch
was the first `total: sum` test case and failed it on 2026-09-01 (#247
above: each building states two `it_load` figures of different kinds,
74/80 and 35/30, and 80 + 35 adds the wrong one from each), so it now
tests the sharper question — which of a building's own figures a total
may add; sites with no published roster keep the one-at-a-time method.

### Traps this work hit, recorded so the next session does not

- **A probe that cannot see the thing it is looking for.** This happened
  repeatedly and cost real time. `ORDER BY value_mw DESC` puts NULLs
  first in Postgres and hid every figure on a site. Joining `sites`
  without `retired_at IS NULL` made 45 applications look like they were
  in several live sites at once (they were not: 0). Matching facility
  names against the whole URL matched a SharePoint path. Swallowing an
  exception from the wrong page-cache accessor reported "130 documents
  have no cached text" when all 130 had text. **Check what the probe
  could have seen before believing what it did not find.**
- **A token that resolves to nothing fails silently.** `spatial:` holds
  an application reference and `barbour:` a Ptno — neither is a site
  key. Compared against site keys they raise nothing, match nothing, and
  quietly demote a documentary relationship to bare distance. Four
  records were affected before the tests caught it.
- **A guard can test the wrong thing and look like no guard at all.**
  The reader *did* skip a pre-planning row whose key matched a site key —
  which catches a project anchoring its own site and misses one that is
  a member of a *different* site, which was the entire bug.
- **`--dry-run` on `drive_sync.py` describes only the prune.** It errors
  without `--prune` and returns before any upload analysis, so there is
  no preview of what will be uploaded.
- **The Drive tree and the reader do not contain the same things.** A
  pre-planning row exists in the reader and has no Drive folder at all,
  because staging is built from documents. Predicting one from the other
  is a mistake.
- **Test bounds fitted to whatever the code returned test nothing.** A
  distance assertion was guessed at 24–26 km and failed at 26.7; the
  fix was to derive it from the components, not to widen the bound.

### Not in an issue, and worth someone's time

- **The N+N question is closed.** Redundancy handling is correct
  throughout — "5 MW N+1" → 5.0, "1125 kW N+1" → 1.125. But Hayes Bridge
  (`PTNO-12831113`) has the *same sentence* — "The campus will be served
  by 2No (N+N) 150MW 66kV connections" — adjudicated at both 150 and
  300 MW, and `max()` takes the wrong one. The same document set states
  the development requires 250 MW. One site, not a pattern, but it is
  wrong on the page.
- **`PTNO-12831113` (Hayes) still carries the doubled 300 MW and three
  named facilities (LON6, LON7, LON8)** — its 24 adjacent-power
  members and the 150 MW substation figure left with the #252 chain,
  so what remains here is the N+N adjudication above and a campus
  worth an early slot in the facility-roster review.

## Operator pages and typed standing — what remains

The build-out shipped 2026-08-30 (HISTORY, "The operator pages day"):
the prior and labelled reader links, the snapshots with the five
paired consultation-site silences held, the claims fold, the alias
fold, and the decision over it all — **typed standing, not equal
standing**: first-party operator statements may become a labelled
ladder rung; third-party aggregates stay tier-and-count. What is
still to do:

- **A claim now says which realm it belongs to** (built 2026-09-01).
  `component_of` on an operator claim names the claim it is part of,
  so a facility figure inside a campus total is legible as one source
  itemised rather than as corroboration: the sites table counts
  top-level claims only, and the panel labels each component. The
  ladder rung has to answer the same question — a campus total and a
  facility figure are different rungs, not two readings of one — and
  `capacity_claims.reconcile_components()` is the measurement to
  design against. As measured 2026-09-01, and it now measures five
  campuses rather than four: Saunderton 78.0 against 78.0 exact,
  Iron Mountain 61.0 against 60.7, Kao 71.0 against 71.2, Slough
  145.5 against 132.2, and Stockley 112.5 against 72.5 because two of
  five facilities disclose nothing. A gap is never an error —
  Slough's is a question for the operator, Stockley's is a
  denominator, and Kao's and Iron Mountain's are integer campus
  figures over decimal facilities.

  *Saunderton was asserted exact here from 2026-08-31 and was not being
  measured: its four facility claims carried no `component_of`, so the
  benchmark campus never entered `reconcile_components()` at all. Found
  and fixed on 2026-09-01 while building the Iron Mountain roster
  against it. A number quoted in three prose files and computed nowhere
  is the class this file's own rule about computed statistics exists
  for.*

- ~~**Design the ladder rung and the cohort-admission rule**~~ —
  **designed and built 2026-09-01**; the design of record is
  [docs/PLAN_OPERATOR_RUNG.md](docs/PLAN_OPERATOR_RUNG.md), decided by
  Luke on all seven points, and decisions 1 to 5 are implemented.
  `site_scale.OPERATOR_BASIS` is the rung, `capacity_claims.rung_claim`
  its eligibility, `campus_scope.yaml` its displacement adjudications,
  and all three consumers read it through `capacity_claims.rung_inputs`
  so the reader, the workbook and the cohort cannot disagree. **Eight
  sites-table cells change and nothing falls**; `at_least_100mw` goes
  42 → 44, gaining Stockley Park and Vantage Cardiff.

  **The rung also fires where the planning record states nothing at
  all** (Luke, 2026-09-01, deciding a question the seven decision
  points had not reached: a rung inserted at a position catches
  everything that would otherwise fall past it). That adds Saunderton,
  Kao's KLON-06 at Slough and CyrusOne LON3 to the two floorspace
  sites the design predicted. The read-and-silent versus
  documents-not-held distinction is kept **in the caveat, not in
  whether the rung fires** — coverage is stated beside a figure here,
  never encoded in whether one ranks.

  **Two counts moved for a reason worth recording**: the design
  predicted four changed cells and the build produced eight. Three
  extra are the empty-ladder decision above; the fourth is Kao Data
  Harlow, and it was WP-R1 of the same handover that caused it —
  `component_of` reached the database an hour before this was
  measured, so a site that had looked like five competing claims
  became one campus total and passed the sole-claim guard. A
  prediction made before its own dependency ran.

  **The Stockley wrinkle travels with the displacement and is not
  resolved by it**: VIRTUS puts 24 MW on LONDON5 and 32.5 on LONDON7,
  so the 24 the table showed — from a document titled LONDON7 — may be
  the right number on the wrong building. Held unresolved on both
  attributions in `site_facilities.yaml` and stated in the scope
  entry's own reason; the displacement does not depend on which
  building it belongs to. A third displacement joins when VIRTUS
  Slough's scope resolves, which is still open in
  `campus_scope.yaml`.

  The `w-operator` rendering review passed on 2026-09-02
  (PLAN_OPERATOR_RUNG.md). Still open: decision 6 (the Pulsant class),
  explicitly expected to be revisited rather than settled — the
  audiences finding those pages belong to is counted in the design
  document (39 pages, 29 corporate,
  10 consultation, 5 sites holding both, five for five
  corporate-states and consultation-silent).
- **The review sheet stays the tracker for its "not yet" rows**
  (`data/operator_pages_review/operator_pages_review.xlsx`): two
  unconfirmed identifications (nLighten Hoddesdon, Digital Realty
  LHR17/Link Park), Global Switch London South (waits for the #247
  partition), and the keyless tier-4 estate — the Pulsant twelve being
  the standing example of facilities that will only ever rank on the
  operator rung, because legacy colocation fit-outs leave no planning
  application to hold.
- ~~**The VIRTUS Saunderton datasheet PDF is unsnapshotted**~~ —
  **done 2026-09-01.** `fetch_operator_snapshots.py` sniffs the PDF
  magic bytes and extracts text with pypdf, so a spec sheet is a page
  like any other; the sheet is snapshotted and its four facility
  figures are claims, matched, quote-verified. The rung can have them.
  What the sheet gives that no HTML page in the survey does: its path
  carries a publication date and a version marker
  (`.../2026/04/15/...-v2.pdf`), so the disclosure is dated by its
  own source rather than only by our read.

### Actions still open from the review sheet

- **VIRTUS Slough campus scope**: VIRTUS rosters LONDON3, 4, 9, 10,
  11, 12 and 19 as its Slough campus; `PTNO-12216044` currently claims
  three of them. A `campus_scope.yaml` question, and the operator
  channel's first direct input to the 35-campus review above.
- ~~**Vantage ↔ Next Generation Data organisation alias**~~ (Luke's
  question on sheet T3-04) — **assessed 2026-08-31 and not written**:
  no organisation-name field anywhere in the corpus contains "Next
  Generation Data"; it survives only in three Barbour project titles
  whose projects already name Vantage as client and end user, so a
  member keyed on it would match nothing (HISTORY, the NESO triage
  entry).
- **The Cato architect's site states 600 MW**
  (graemenicholls.com/cato-data-centre, snapshotted) — a claims lead
  from a source kind the claims channel does not yet name: neither
  operator nor register, but the scheme's own architect.
- **CyrusOne LON2 (Prologis Park, West Drayton) is a separate site**
  from the VIRTUS Prologis Park campus — they share an estate, not a
  scheme (sheet T4-02). A note for whenever that site is created.
- **CyrusOne LON1 is in the corpus under Zenium's name, inside
  VIRTUS's site, and wants a partition** (2026-09-01, Luke holding the
  decision: "I will sort out the partitioning later"). Barbour project
  `12216044` is `12 Liverpool Road` / `London One`, which is the
  address CyrusOne publishes for LON1 — but it is a member of
  `PTNO-12216044`, VIRTUS's Slough campus at 75 Buckingham Avenue,
  joined on nothing but the shared SL1 4QZ postcode: all three Barbour
  records in that site carry one identical coordinate, the postcode
  centroid. It also lends the site its key and derived name, being the
  lowest Ptno of the three. Ejecting it overturns
  `site_partitions.yaml`'s `virtus-zenium-slough-campus`, which lists
  it deliberately. The full evidence, and the acquisition question the
  partition turns on, are the `considered:` entries in
  `operator-claims.yaml` — do not re-derive them.
- **Put the Zenium entities through the Companies House sweep.** The
  partition above turns on who acquired what, and two files here
  disagree: `site_partitions.yaml` says VIRTUS acquired the campus
  from Zenium, `environment-agency-permit-operators.yaml` says
  CyrusOne bought Zenium's UK estate. **Both can be right if the
  estate was broken up and sold asset by asset** (Luke, 2026-09-01),
  which is the hypothesis to test first, and the corporate shape is
  consistent with it: the one Zenium company the corpus holds is
  `ZENIUM UK2 LIMITED` — a numbered per-asset SPV — and the permits
  "still stand in the Zenium companies' names", plural. A permit stays
  put when a company's shares are sold and must be transferred when
  the building alone is, so undisturbed permits across numbered SPVs
  show the buildings changed hands as companies — which fits a
  piecemeal break-up and fits one buyer taking every SPV equally well;
  the filings, not the permits, say which.
  **No Zenium appears in `companies-house-spvs.yaml` or
  `organisation_aliases.yaml`**, so the sweep built for exactly this
  class — single-asset SPVs, whose filings state the asset and its
  owner by construction — has never been pointed at it. The numbering
  bounds the set. Cheaper than the title register and it settles the
  partition.

## Acquisition decisions waiting on a person

Deferred at 2.8 (2026-08-26) and still standing — 2.9 and 2.10 have
both shipped since, so the old section title ("Deferred to 2.9") had
aged into a lie. Each is scoped; what blocks each is a decision, not
work.

- **Re-fetch the 52 applications whose `none_published` was awarded on a
  page that refused.** Established 2026-08-26 without touching a portal,
  by re-reading the documents-tab HTML the original fetch had already
  snapshotted: 49 are Idox serving *"Permission Denied — You do not have
  permission to view the page"* with **HTTP 200** and full site chrome,
  so a scraper sees an ordinary page with no document links; 3 are
  Brighton returning 212-byte bodies, also with a 200. Selby alone is 18,
  then Exeter, Derby and Doncaster at 5 each. 106 of the 128 settled
  verdicts carry the detail `no_documents_or_unparseable` and every one
  was written on **2026-08-08**, before the mapping was tightened on the
  9th — after which the same condition produced `error` instead. So the
  population is bounded and historical, not a live leak. The verdicts
  are settled, so re-fetching means writing new outcome rows over them:
  a decision about the acquisition record, which is why nothing has
  touched them. `no_documents_or_unparseable` is itself a conflated
  name — the adapter sets it whenever `len(links) == 0`, whether the
  page was a register or a refusal.

- **The browser-routed residue: 24 NEC, 3 Northgate, ~14 bespoke** (as
  probed 2026-08-27; the "31 browser-routed" notes they replaced had
  aged past their premise and are recorded in the dissolution
  measurement of that day). The Northgate three are three different
  situations: Liverpool migrated to a Tascomi register
  (lar.liverpool.gov.uk answers; the northgate host is dead), Hackney's
  host refuses connections entirely (find where its register lives
  now), and Birmingham gates scripted clients with 403/503 — a real
  browser passes, the one genuine human-at-keyboard job left, and its
  Hackney application is a conditions detail on the Interxion site's
  energy-centre emissions. Coventry's completeness is still unmeasured
  because the relist audit skips the host by name. Re-measure the
  residue from `acquisition_outcome` once the 2026-08-27 sweep's
  outcomes are settled; do not re-quote these counts without doing so.

## Phase 2 — the tail of the collecting

- **The acquisition tail, as measured 2026-08-30 late evening: 290
  in-universe applications hold no documents.** By latest
  `acquisition_outcome`: **119 `none_published`** (the register lists
  nothing — the refused-page class in "Acquisition decisions waiting
  on a person" sits inside this), **94 `no_adapter`**, **74 `error`**
  (retryable — re-running the fetch picks them up), and one each of
  `login_required`, `portal_blocked` and never-attempted. The
  measurement is one query — universe members with no `documents` row,
  grouped by latest outcome — so re-measure rather than re-quote. The
  genuinely-hard classes (CAPTCHA, hard 403/500/503, Incapsula) still
  stand; the 2026-08-27 sweep history that used to sit here is in
  HISTORY.
- **The relist refetch: two deferred tranches and the unmeasured
  residue** (the audit and the recovery it drove are in HISTORY,
  2026-08-26 — including why "2,260" was URLs, never missing
  documents). Still to do:

  - **Resume the refetch**: `scripts/relist_refetch.py --tranche
    rest`, then `--tranche glasgow` — idempotent, costs nothing
    already done. Deliberately deferred: Union Park's 157 (cut in
    favour of the Northumberland reports) and Gilmorehill's 491 (a
    university masterplan's drawings). The full absent-document list
    is `data/reports/relist_refetch_list.csv`.
  - **142 applications are still unmeasured**, holding 3,381
    documents: 107 on portals with no listing-only path (44 bespoke,
    35 Northgate, 28 NEC), 26 on Coventry (skipped by name — AWS
    WAF), 7 Wychavon, 1 Manchester timeout, 1 unharvested Salesforce.
    Errors are retryable via `--pass live`; the rest need an adapter
    that only has to produce a listing, a much smaller job than a
    fetcher.
  - **29 applications hold documents against an empty listing** —
    mostly manual harvests whose `file://` URLs no listing can match.
  - Known refusals that stand: Greater Cambridge's blanket 403 on
    file downloads (158), Tower Hamlets' persistent 504s including
    two energy strategy reports.

  **Still true: do not quote a per-site document count without
  checking `document_listing_audit`.** A count of held documents is a
  floor until the site's applications are measured and their
  shortfall is either refetched or stated.
- **Two site-classification rules deserve a reporter's eye** (the
  mechanism itself shipped — issue #159, PR #178, HISTORY 2026-08-27).
  Each was decided in the building and changes what the list asserts
  about real rows: that a Barbour project title naming a data centre
  settles the class (21 sites), and that `pre_application` and
  `enabling_works` count as datacentre-positive. Both are one constant
  each in `dcp/site_class.py` to revisit.



- **Northumberland Energy Park holds four unrelated schemes.**
  `PTNO-12785975` clusters 35 applications spanning the Blyth offshore
  wind connection, Britishvolt's battery plant, JDR's subsea cable
  factory and the data centre. 2.7 partitioned out only the 2013 wind
  substation, because only its figure was actively misleading (see
  HISTORY). The rest is the site-61 problem in a second location, and
  the same remedy applies: adjudicated boundaries with written
  evidence. The applicant of record separates these cleanly — but read
  the descriptions before ejecting anything, per the stem-1331 lesson
  above.


- **A Section 35 direction has no project ref until its DCO is filed.**
  The bridge problem from `data/nsip_research/findings.md`: the watcher
  keys a stub on the gov.uk publication slug, the register keys on
  `EN0110030`-style refs, and nothing reconciles them when the DCO
  finally arrives months later. Today it is handled by one curated
  Barbour link and the fact that a human noticed. A composite key —
  applicant, location, capacity — was the proposed answer and is
  unbuilt. Until then, **re-run `dcp index --source s35` weekly**
  (idempotent, free on no change) so a fourth direction is noticed the
  week it publishes rather than the day a story runs.

## Phase 3 — the second opinion

- **Re-extract what the local model read.** The label audit
  (`gpt-5/label-1.0`, 10,602 rendered findings, 2026-08-25) settles a
  question the hand sample could not: holding the family constant, the
  local `mlx` extractor misfiles far more often than `claude-sonnet-5`,
  and worst in the families this release is about.

  | family | claude-sonnet-5 | mlx |
  |---|---|---|
  | `power_demand` | 9% | **68%** |
  | `power_generation` | 9% | **34%** |
  | `power_grid` | 12% | **25%** |
  | `cooling` | 2% | **19%** |
  | *all audited* | 11.3% | 28.4% |

  Seventeen of twenty families are worse on `mlx`; three
  (`application_admin`, `land_quality`, `site_identity`) are not. It is
  25.4% of the corpus — 307,432 findings.

  **This does not touch any megawatt figure.** A capacity reaches a
  site's power panel through `power_adjudication`, keyed on the finding
  rather than on its family, so a misfiled row still carries its figure
  to the right place: 81 of the 1,928 flagged rows hold an adjudicated
  site capacity and every one keeps it. The cost is to browsing a site's
  evidence, and the audit already moves those rows on the page. What
  re-extraction would buy is the material that was never extracted well
  enough to be filed at all, which the audit cannot see.

  *Percentages and counts here are as measured on 2026-08-25 against
  10,605 verdicts; what a given build renders moves with the corpus —
  2.7 moved 1,862 rows and withheld 187. Compare shapes, not digits,
  and see "make the corpus statistics computed" under Smaller things.*

- **A signal for the 50 MW consenting threshold.** Above 50 MW a
  generating station in England needs a DCO rather than local planning
  permission, and **855 findings across 51 sites** state a sub-50 bound —
  "generation totalling less than 50 MW", "capped at 50 MW", "49.9".
  Yorkshire Energy Park says it in every passage it gives. That is a
  behaviour, not noise, and it is the same shape as Kingsnorth's 49.9.

  `generation_exceeds_load` now excludes those figures, because a ceiling
  cannot be compared with a load. Turning them into a signal of their own
  is the more interesting move, and it needs the bound adjudicated as a
  property of the figure rather than matched on the quote — the pattern
  in `dcp/site_profile._BOUND_RE` is good enough to exclude a figure from
  a comparison and not good enough to build a cohort on.

- **Second-model comparison across the corpus.** A subset is dual-read
  already. Where two models disagree, both readings are kept and the
  disagreement is the finding; the comparison is the deliverable.
- **Water adjudication**, once reading is complete — whether the sites
  disclosing consumption support anything firmer than the cooling method
  reported today. **119 sites as at the 2.1 boundary**, and the number
  has moved twice: HISTORY records 93 at phase 1 and the data dictionary
  said 76 through phase 2, both measured before the reading that
  followed them. Three hardcoded figures for one quantity, drifting
  apart — measure it at the time rather than quoting any of them, and
  see the note below about making it computed.

## The scheme SPVs at Companies House

Found 2026-08-24 while checking whether "UK Court Lane DC Limited"
belongs in the Corscale alias group. It does not — but its accounts
state that the £205m valuation of its one asset assumes "successful
delivery of a 103.3 MW hyperscale data centre", against Barbour's 140 MW
for the same project. See EXTERNAL_DATA_SOURCES §6, corrected twice
before and now a third time: **operators disclose capacity by choice,
single-asset SPVs disclose it by construction**, because the scheme is
the investment property and FRS 102 makes the directors state what the
valuation assumes.

The sweep itself is built and its findings recorded
(EXTERNAL_DATA_SOURCES §6; mappings in `companies-house-spvs.yaml`
and `companies-house-ownership.yaml`). Still open:

1. **Sites 59 and 5 still block the Premier Park and DataVita
   matches.** Premier Park's £147.8m and the DataVita figures stay
   under `considered:` in `companies-house-claims.yaml` because their
   site records are over-merged clusters (and DataVita's needs a
   person to establish which building the figure describes). Union
   Park's four claims were unblocked by the site 61 split and matched
   on 2026-08-27.
2. **Eleven names could not be resolved to a company**, listed under
   `unresolved:` in `companies-house-spvs.yaml` — including "Avalon DC
   Limited" and "BGO Code Propco Limited", both of which are somebody's
   applicant of record and neither of which exists on the register.
   Worth a person's eye rather than another search.
3. **Confirm the proposed alias-group members.** The sweep resolved
   names to numbers with evidence; folding the confirmed ones into
   `data/priors/organisation_aliases.yaml` is a person's decision at a
   release checkpoint, not a session's.

The class is bounded and the reward is high: a per-scheme capacity that
an external valuer priced and an auditor signed, a solvency signal the
planning file never carries, and an ownership chain that the PSC
register is structurally unable to show.

**Surfacing it in the reader is specced in
[docs/PLAN_OWNERSHIP.md](docs/PLAN_OWNERSHIP.md)** (agreed with Luke,
2026-08-26). Increment 1 is a three-state tier — UK-controlled /
overseas-controlled / not disclosed — on the site page's existing "Who
is behind it" rows, with the chain as drillable text beneath it and the
dark link named rather than blank. Flags, logos and a start-page world
map are sketched there as increment 2, each behind a stated gate: the
first of them is normalising `registered_in`, which today spells one US
registry four ways and records a listing venue as a jurisdiction. The
43% non-UK figure is a session-old measurement over that un-normalised
field and is not publishable as it stands.

## Coverage gaps worth closing

- **Elsham Wolds states three power figures that do not reconcile with
  each other** (found 2026-08-31, and verified against the cached page
  text rather than taken from the reading that surfaced it). The Energy
  & Sustainability Statement in `NorthLincs/PA/2025/643`, page 15 of 40,
  prints in one table:

  > Maximum Power Demand ≈1,000 MW · Assumed Operational Diversity 50%
  > of maximum · **Operational Power Demand 84 MW** · 8,760 hours/year ·
  > Annual Energy Consumption 3,679,200,000 kWh

  **The 1,000 MW is not in question and this item does not put it in
  question** (Luke, 2026-08-31). It is corroborated well beyond this
  table: the applications state it in their own words — "The Proposed
  Development is for a Data Centre Park with the IT Load capacity of up
  to 1000MW" — the Guardian reported it in March 2026, one of the
  articles that led this project to devote more resources to the
  hyperscale subject, and the construction trade press repeats it at
  15 facilities and £7.5bn.

  **What does not reconcile are the rows derived from it.** Fifty per
  cent of 1,000 MW is 500 MW, not 84. Eighty-four megawatts over 8,760
  hours is 736 GWh, not the 3,679 GWh printed beneath it. The annual
  energy figure divided by the hours implies **≈420 MW average draw** —
  which is an unremarkable utilisation for a 1 GW nameplate, and is the
  number the carbon arithmetic on that page actually rests on.

  So the honest reading is a defect in one table, not a doubt about the
  scheme: the 84 MW row and the 50% line reconcile with neither the
  maximum above them nor the energy total below them. It is worth
  recording because **a reader of that table takes away 84 MW**, and
  because the 420 MW implied by the energy figure is the operative
  number for emissions and appears nowhere as a stated figure. Only the
  applicant can say which was meant.


- **The "Green Energy Centre" portfolios: 8,660 MW of transmission
  demand, and not one planning application** (measured 2026-08-31).
  The largest single hole the corpus has, and the one where what is
  missing is not a document but a whole class of scheme.

  What the two NESO artefacts hold between them. In the **TEC register**,
  52 rows across 42 distinct schemes, 57–2,050 MW cumulative, and **30 of
  the 52 carry `Demand` in their `Plant Type`** alongside energy storage
  and solar. In the **Existing Agreements register**, nineteen of the
  same schemes appear as `Transmission Connected Demand` totalling
  8,660 MW — Buntington 850, Hockliffe 850, Navenby 580, East Claydon,
  Hawthorn Pit, Overton and Feckenham 500 each, down to Botley and
  Bramford 2 at 200.

  Three things make it worth a look rather than a note. **The schemes are
  named after the substations they connect at** — Navenby GEC at Navenby,
  Drakelow at Drakelow, Pelham at Pelham — which is what grid-capacity
  acquisition looks like before a site has been chosen or named. **They
  are two SPV families**: twenty customers of the form "⟨substation⟩ NG
  Limited" and twelve schemes suffixed "(Ethos Green)", which is a
  Companies House thread of exactly the kind
  `organisation_aliases.yaml` and `companies-house-spvs.yaml` exist for.
  And **none of the nineteen has a planning application anywhere in this
  corpus** — checked against site display names, member application and
  project text, and the curated aliases.

  **The open question, and it is genuinely open.** Ethos Green Energy
  publicly describes its Green Energy Centres as integrated hubs of
  renewable generation, long-duration storage *and colocated data
  centres*, and has announced a joint development agreement with
  Frontier Power for up to 5 GW of colocated data-centre capacity. So
  the `Demand` leg may be a data centre. **The registers do not say so**,
  and the competing explanation in `docs/EXTERNAL_DATA_SOURCES.md` §3 —
  that a `Demand` plant type is the import leg of a storage-and-solar
  hybrid — fits the plant-type coding equally well and has never been
  tested against these schemes. Either answer is worth having: 8,660 MW
  of colocated data-centre demand invisible to every data-centre search
  is a story, and a confident null is the kind of counter-evidence the
  first principle exists to protect.

  **What would settle it**, cheapest first: the SPVs' Companies House
  filings, since a single-asset SPV's accounts and its SIC code state
  what the asset is; the developers' own scheme pages and any
  consultation material, which is where the operator channel already
  reads capacity; and a targeted planning sweep on the substation names,
  which is a bounded list of nineteen localities rather than a national
  trawl. **Do not sum the 8,660 MW into anything** — the TEC and EA rows
  are different agreements over the same schemes and the quantity types
  differ, which is the whole discipline of the claims channel.

  A caution recorded because it already cost a correction: an earlier
  version of this item said these schemes held a *gas* connection,
  following §3's placing of them inside its gas rows. They do not; no
  GEC row carries any gas term. Where a claim about these rests on a
  coded field, name the field.

- **Two external sources reach the workbook and not the reader, and
  "Provenance" appears in neither.** Luke asked during the 2.10 release
  whether he had missed the Published aggregates and Sources tables in
  the reader; he had not — they are workbook-only. The workbook carries
  an **External aggregates** sheet (62 rows) and a **Provenance** sheet
  (20 rows), each with its dictionary entry. The reader carries a
  subset, woven into the methodology prose rather than tabulated:

  | source | in the reader |
  |---|---|
  | Ofgem Curate | yes — the banded queue table, linked, para 2.8 cited |
  | NESO Call for Input | yes — linked in prose |
  | DESNZ sub-national consumption | yes — linked, and the per-site line |
  | UKPN Large Demand List | **no** |
  | UKPN Data Centre Demand Profiles | **no** |

  So three of five external sources reach someone reading the web page,
  and the word "Provenance" — the sheet recording where each external
  figure came from — appears nowhere in it. That cuts against the rule
  the rest of the reader keeps: every number drillable to its source.
  A reporter who works from the reader alone cannot see two of the
  sources the release rests on, or the record of where any of them came
  from.

  Not a defect in what is shown — everything shown is cited — but an
  asymmetry nobody chose. The fix is a section on the methodology page
  listing all five with their locators, generated from
  `dcp/external_aggregates.SOURCES` so it cannot drift from the
  workbook's own sheet. Deferred past 2.10 because the artefacts were
  built and diffed when it surfaced.

- ~~**Link the snapshots from the reader and workbook.**~~ **All three
  steps shipped 2026-09-01**, the day Luke asked about linking
  snapshots from the reader: the store is append-only, every snapshot
  is on Drive under `operator_snapshots` with its file id in
  `data/external_sources/operator_snapshots_drive.yaml`, and the claims
  now render the link (HISTORY, "The snapshot store becomes
  append-only", "The snapshots reach Drive" and "A claim links its own
  evidence"). Kept here for the resolution rule, which is not what this
  item predicted, and for the two follow-ons below.

  **Step 3 shipped 2026-09-01** (HISTORY, "A claim links its own
  evidence"). Each operator and green claim renders a link to our copy
  beside the source URL it already shows, on five surfaces: the site
  panel's claims box, the Operators tab, the green-claims table, and
  the workbook's Capacity claims and Figures by audience sheets. The
  emphasis is deliberately the mirror of a document's — the published
  page stays the primary link because it is what a story cites, and our
  copy is the labelled second.

  **The resolution rule turned out to be the quote, not the date**, and
  that is the correction this item most needed. It was written here as
  *a claim links the snapshot that existed at its `as_at`*, which is
  necessary and not sufficient: the store holds no file for a reading
  taken before it became append-only, so CyrusOne LON1's 8.72 MW row —
  which carries no `as_at` at all, and which stands in
  `capacity_claims` only rather than in `operator-claims.yaml` — would
  have fallen through any date rule onto the 2026-08-30 file that
  reads 9 MW. Those two facts about the row were read off the database
  rather than taken from the spec, which asserted an `as_at` of
  2026-08-20 that the row does not carry. A claim now links the
  nearest held file *in which its own verbatim quote appears*, on the
  gate's own whitespace normalisation, and links nothing otherwise. As
  built: `capacity_claims.snapshot_candidates` orders the store around a
  reading's date and `snapshot_drive.copy_url` picks the file the quote
  is actually in. 80 of the 81 operator rows in the database resolve;
  the one that does not is that 8.72 MW row, which is what the design
  is for. Every committed YAML claim resolves — the two populations
  differ, because the YAML holds current readings only and the ghost
  row is in the database alone.

  Luke reviews the rendering before it ships. The spec was WP-C of
  [docs/HANDOVER_SNAPSHOT_CHAIN.md](docs/HANDOVER_SNAPSHOT_CHAIN.md);
  ROADMAP stays the inbox.

  **Not done here, and named rather than folded in**: the DuckDB's
  claims tables carry no such column, so a reporter working from the
  database still reaches only the source URL.

  ~~**And the Drive viewer URL is built in three places.**~~ Folded
  into `dcp.drive.file_url` / `folder_url` / `file_url_sql` on
  2026-09-02, and `tests/test_drive_url_one_shape.py` refuses a fourth.

- **26 applications link to a register host that no longer answers,
  and they would ship in 2.10 that way** (probed 2026-08-28: every host
  the reader links to, 208 of them behind 2,033 linked applications).
  194 answer normally. **11 do not answer at all** — publicaccess.
  wycombe, planpa.peterborough, planning.stoke, pa.chilternandsouthbucks,
  pa.manchester, planning.hounslow, planapp.bracknell-forest,
  planning.hackney, communitymap.harlow, planning.coventry,
  northgate.liverpool — six of which no longer resolve in DNS at all.
  eppingforestdcpr.force.com returns 404. Camden and Portsmouth return
  403, which is a bot challenge rather than a dead host: those links
  still work for a person in a browser and must not be treated as dead.

  Found because Luke reported one URL from a hand-download list as
  missing; the host had been retired under it.

  **Three of the 26 hold documents, and all three are wholly on Drive**
  — EppingForest/EPF/1165/22 (46), Manchester/132638/FO/2022 (15),
  EppingForest/EPF/1136/19 (2). For those the rule already applies:
  link our copy, keep the register link beside it for citation, never
  suppress. The other 23 hold nothing, so the dead link is the entire
  record of them and the honest treatment is to say the register link
  no longer resolves rather than render a link that fails silently.

  The check is worth keeping rather than repeating by hand: one HEAD
  per distinct host, ~208 requests, cheap enough to run before every
  release. Distinguish "did not answer" from 401/403 — conflating them
  would mark Camden's 23 live-but-challenged applications as dead.

  **Deferred past 2.10 by Luke, 2026-08-28, and recorded here so the
  work does not need re-deriving.** Re-probed 2026-09-01 before the
  2.11 build, over 205 hosts behind 1,967 linked applications, with
  `truststore` injected so incomplete certificate chains do not read
  as dead (a first pass without it reported forty-odd "dead" hosts
  that were nothing of the kind — the probe could not see): **16
  dead** (the ten below that still resolve nowhere or time out, plus
  Dundee's idoxwam host on a handshake timeout, Worcester, Wychavon and
  Wokingham resetting the connection, Leeds timing out, and Selby on
  an **expired certificate**), **5 challenged** (Camden and Portsmouth
  as before; Sefton, South Oxfordshire and Vale of White Horse newly
  answering 403 to a scripted HEAD), and nine other non-2xx answers
  (Birmingham 503, Epping Forest 404, South Tyneside 500, Barnsley 405
  to HEAD, Neath Port Talbot, Rhondda Cynon Taf and Newport 404). The
  resets and timeouts may be transient or bot-shaped; the DNS failures
  and the expired certificate are not. Still deferred; the 26, as
  probed on 2026-08-28 — a host that answers again later is a fix, not
  a regression, so re-probe before acting rather than trusting this
  list:

    publicaccess.wycombe.gov.uk — Wycombe/08/05740/FULEA, Wycombe/22/06872/VCDN, Wycombe/24/07967/OUT, Wycombe/25/06079/MINAMD, Wycombe/25/06382/MINAMD
    planning.stoke.gov.uk — Stoke/65328/FUL, Stoke/65376/FUL, Stoke/65426/FUL, Stoke/65465/FUL
    planpa.peterborough.gov.uk — Peterborough/08/01079/FUL, Peterborough/08/01225/FUL, Peterborough/18/00937/R4FUL, Peterborough/18/01340/R4FUL
    eppingforestdcpr.force.com — EppingForest/EPF/1136/19 (2 docs, on Drive), EppingForest/EPF/1165/22 (46 docs, on Drive)
    pa.chilternandsouthbucks.gov.uk — ChilternSouthBucks/PL/20/0646/ADJ, ChilternSouthBucks/PL/22/3403/FA
    pa.manchester.gov.uk — Manchester/132638/FO/2022 (15 docs, on Drive), Manchester/137424/FO/2023
    planning.hounslow.gov.uk — Hounslow/C/2020/0555, Hounslow/C/2020/0865
    communitymap.harlow.gov.uk — Harlow/HW/PL/16/00243
    northgate.liverpool.gov.uk — Liverpool/PL/INV/1646/21
    planapp.bracknell-forest.gov.uk — Bracknell/17/01227/OUT
    planning.coventry.gov.uk — Coventry/FUL/2021/1299
    planning.hackney.gov.uk — Hackney/2020/1287

- **One address, two postcodes: a three-line check that would have
  caught the British Museum merge without anyone reading a document.**
  The premise, established 2026-08-28: a postcode inside a council's
  register can simply be wrong, and the 1 km spatial rule propagates it
  faithfully. Camden records 25 British Museum applications at
  **WC1E 7JW** (Gower Street, by UCL) and 3 at the museum's own
  **WC1B 3DG / WC1B 8DG**. The wrong value put the museum on top of
  "UCL Interim Data Centre" (PTNO-12087852) and 21 of its applications
  became members of a data-centre site — fixed by partition in PR #197,
  but only because Luke read the documents.

  The generalisable signal is the corpus contradicting itself: the same
  address string carrying two different outward codes. Measured over
  875 distinct address strings it flags **3**, of which one is the real
  error; "Reading Quarry Berrys Lane Burghfield" (RG30 ×7, RG7 ×5) is
  benign, a quarry genuinely spanning West Berkshire, Reading and
  Wokingham and already split across three sites, and "Broadwater Farm
  Estate" is one application each side. Three flags to review is free,
  so this is worth wiring in as a build-time warning rather than a
  script someone remembers to run.

  **Two traps, both hit while writing it.** Compare the FULL outward
  code: `WC1E` and `WC1B` both truncate to `WC1`, and a first version
  that truncated found nothing — the check could not see the case it
  was built for. And normalise a leading "The": Camden writes both
  "British Museum …" and "The British Museum …", which key differently
  and hide the contradiction. A third approach — comparing members
  against the postcode of the Barbour project the site is named after —
  was measured and **rejected**: the UCL project is itself WC1E 6BT, so
  members and anchor agree and the check sails past. It flags 7 sites,
  none of them this one.

- **The verbatim gate's whitespace fix and the re-gate both ran on
  2026-08-31 and shipped in 2.11** (HISTORY, "The re-gate reinstated
  the findings the gate had wrongly rejected"). One question survives
  unmeasured: whether the whitespace-artefact rejection rate differs by
  document class. It is **not** the PARSE FAIL energy-report gap
  recorded elsewhere — `read_state = 'parse_failed'` means the model's
  JSON came back truncated and was salvaged, unrelated to how the PDF
  extracted.

- **Equinix's UK estate is largely absent from the corpus: three of
  fifteen facilities have a planning record** (measured 2026-08-28
  from equinix.com, prompted by Luke). Eleven London IBX sites — LD3
  (Coronation Road, NW10 7PH), LD4 (2 Buckingham Avenue, SL1 4NB),
  LD5 (8 Buckingham Avenue, SL1 4AX), LD6 (352 Buckingham Avenue,
  SL1 4PF), LD7 (1 Banbury Avenue, SL1 4LH), LD8 (Harbour Exchange
  Square, E14 9GE), LD9 (Powergate Business Park, NW10 6PW), LD10 and
  LD13x (both 13 Liverpool Road, SL1 4QZ), LD11x (765/767 Henley
  Road, SL1 4JW), LD14 (Banbury Avenue) — and four in Manchester:
  MA1 (Williams House, M15 6SE), MA3 (Joule House, 76 Trafford Wharf
  Road, M17 1HE), MA4 (Synergy House, M15 6SY), MA5 (Agecroft
  Commerce Park, Swinton, M27 8BX).

  Only **LD14**, **LD9** (`OldOakParkRoyal/22/0093/DELEAL`, "Powergate
  Business Park, Unit 2, Volt Avenue") and **MA5**
  (`Salford/20/75336/FUL`, "conversion of 2 existing warehouses into
  data centres") verify by address. Match by postcode alone and the
  count looks like seven — SL1 4PF returns Iron Mountain's 110
  Buckingham Avenue for LD6, SL1 4QZ returns Zenium at number 12 for
  LD10 and LD13x — which is the same trap the site 23 partition had to
  avoid, and a warning against postcode joins in this corridor
  generally.

  **Two of the nine site-23 permits are now placeable and neither has
  a planning record**: EPR/LP3303PR ("Equinix Slough Campus Data
  Centre", 331.084 MWth) is at SL1 4AX, which is LD5 at 8 Buckingham
  Avenue; EPR/CP3409BH ("LD11x", 96 MWth) is at SL1 4JW, which is
  765/767 Henley Road. That is 427 MWth of permitted standby plant at
  addresses the planning corpus has never seen.

  The likeliest cause is the indexing window — council registers are
  indexed mostly from 2018 and these are older builds — which would
  make it a general undercount of *operating* capacity rather than an
  Equinix-specific miss. Worth testing against another long-established
  operator before it is described that way in print.

Prompted by the **Devon Data Campus** (Xlinks, North Devon), a scheme
with an active public campaign of which the corpus holds almost nothing:
zero matches for Xlinks, Valeon or Devon Data Campus. The single
Alverdiscott match is `EN010164`, carried by the NSIP **energy layer**
(`discovered_via={nsip_energy}`) — the withdrawn 3.6GW interconnector,
context rather than the campus. That is the adjacency layer doing its
job and it is also the measure of the gap: the grid connection is
visible and the data centre proposed at it is not. Three gaps, in rising
order of effort:

1. **Operator watch-list sweep** (cheap). Add Xlinks and Valeon, review
   the list generally, run a name-based PlanIt sweep. Catches an
   application when it is validated rather than when we next look.
2. **Pre-application and screening entries.** Councils publish EIA
   screening and scoping requests, and Scottish PANs, *before* any
   application exists. Our universe starts at submission, so this class
   is structurally invisible. Decide whether pre-planning entries become
   first-class universe members or a separate watch table.
3. **NSIP-to-campus association.** The Section 35 half of this item
   shipped on 2026-08-25 — the watcher finds directions the week they
   publish (HISTORY) — but the energy layer is ingested and a data
   centre attaching itself to an NSIP power project is still invisible
   on both sides of the join. Xlinks'
   Morocco–UK interconnector lands at Alverdiscott, which is plausibly
   *why* a data campus is proposed there. An NSIP spans hundreds of
   kilometres and many authorities, which the 1 km clustering rule
   handles badly — it wants its own node type and evidence-based rather
   than proximity-based association.

(The "~15 adjacent_power applications universe-wide" this item once
cited was itself the undercount it predicted: the energy-adjacency
sweeps took the class to 48 records, now held in the
`site_adjacent_power` relationship table rather than in membership —
see the capacity-model section. The structural point stands: power
schemes near campuses enter the corpus only when a sweep looks for
them.)

4. **Generator capacity that accretes through follow-on applications.**
   Found while cross-checking the Capacity Market sites against planning
   records — see §5 of
   [docs/EXTERNAL_DATA_SOURCES.md](docs/EXTERNAL_DATA_SOURCES.md). At 672
   Galvin Road, Slough, four generators arrived in 2023 on their own minor
   consent, years after the data centre permission; at Hemel Hempstead a
   2003 application is simply "Construction of single storey building to
   house generator". None states a figure in MW. This is the Yorkshire
   Energy Park pattern at building scale, and it means a sweep anchored on
   the main consent **systematically undercounts installed generation**.
   The fix is to link follow-on applications back to their parent site,
   which the co-location sweep should do anyway. Two naming-invisibility
   cases turned up in the same search — a data centre consented under use
   class B8, and one as "fibre exchange (Sui Generis)" — which belong with
   the existing invisibility-flag work.

**Northern Ireland: the adapter exists; the coverage sweep does not.**
The network-tab session happened on 2026-08-27 and found something
better than an endpoint: an anonymous TerraQuest REST API behind a
public tenant header (`dcp/sources/ni_planning.py`, and
docs/PORTAL_NOTES.md for the route map — including that a missing
header answers `200 null`, which reads exactly like an absent
application). The applications we already hold are fetched through it
and `fetch_outstanding.py` dispatches the family. What remains is the
*coverage* half: PlanIt does not index NI, so NI applications only
enter the universe by other routes. A discovery sweep against the
register's own search API is the remaining work, and it is the whole
of Northern Ireland, not the dozen applications we happened to hold.

**Read the 58 Section 106 agreements the tiering used to skip.** The
classification is fixed — `LEGAL_INSTRUMENT_KINDS` is now tested before
the drawing rule, so a statutory instrument is never a drawing whatever
its title says, and `tests/test_tier_ordering.py` asserts every phrase
`TIER_A_KINDS` names can actually be reached. What is *not* done is the
consequence.

Those 58 documents are now classified as prose and are unread, which is
the honest position rather than the previous one where they counted as
drawings. Coverage moves from 36,744 of 36,983 (99.35%) to 36,744 of
37,041 (99.2%). **They want reading and the artefacts regenerating
before the coverage figure is quoted again** — phase 2.1 shipped before
this and is accurate to its own definition; this changes the definition.

They are worth the read rather than a reclassification for tidiness:
s106 agreements are where planning obligations, community payments and
infrastructure commitments are written down, which is investigative
material. 438 MB of it, and the same rule would have dropped them from
the Pinpoint collection too.

**A zero-byte document is held, counted and read as though it were a
document.** Three exist in the corpus, found while building the Pinpoint
bundle because an empty file is conspicuous in an export and invisible
everywhere else:

| document | application | site |
|---|---|---|
| `005 - Section 106 Agreement.pdf` | Wakefield 23/00100/S7301 | Ferrybridge C |
| `011 - Consultation Response.pdf` | Warwick W/23/1025 | Warwick Hospital |
| `018 - Supporting Documents.pdf` | Medway MC/21/0979 | Kingsnorth |

**They cannot be re-fetched, and the fault is not ours.** With a session
cookie and referer all three return HTTP 200, `Content-Type:
application/pdf`, and a body of zero bytes, from the councils' own
servers. Without the cookie Idox answers 404, which is what made this
look at first like a stale-URL problem; it is not. The Wakefield s106 is
still listed on the documents tab, dated 09 Jan 2025, at exactly the URL
we hold. Luke confirmed the same result in a browser. The original fetch
was correct and faithfully stored what the portal served.

The defect is that nothing notices. An empty file passes the fetcher,
lands in the canonical store, is hard-linked into staging, is counted in
the corpus totals, and reaches the deep read as a document held and
readable — where it yields nothing, indistinguishably from a document
that genuinely says nothing. Two of these three are consultee responses
and one is an s106; on kind alone they are exactly the material the
investigation is looking for, so "we hold it and it was silent" is the
worst available failure mode.

What remains (the fetch guard is done and test-pinned; the corpus
sweep re-run 2026-08-27 still finds exactly the three):

1. ~~**A durable home for the sweep**~~ — **done 2026-09-02**:
   `repo.zero_byte_files` is the check, the staging build runs it over
   the tree it just wrote and prints what it found every release, and
   `scripts/corpus_stats.py` reports the database's view of the same
   fact. A fourth empty document announces itself at step 9.
2. **Say so in the artefacts.** Where a document is held but empty,
   the site report and the coverage detail should show it as
   unavailable from the source rather than as read — the same honesty
   the coverage split already applies to drawings and sampled
   objection letters.

Worth raising with the three councils as well: a listed document that
downloads as nothing is a public-access failure independent of this
investigation.

## From the reader redesign — for the adjudication corrections

Found 2026-08-23 while reviewing the reader redesign
(docs/READER_REDESIGN_PLAN.md §4.1d); the correction belongs in
`scripts/correct_adjudications.py` as a named rule, so it is recorded
here rather than applied from the build lane.

- **A person's row from the export-limit rule** (the rule itself
  shipped 2026-08-27; HISTORY): **Kingsnorth's 47,405 kW figures** —
  the same value at leading and lagging power factor in one connection
  table, against the offer letter's 5,000 kVA import — stand as that
  site's largest grid figure, and no predicate can say which direction
  the site's connection is. Settle it by hand, then re-check the
  Operators tab's like-for-like, which still quotes the
  register-vs-planning comparison this family fed.
## Smaller things

- **Pipeline upload of the search bundles to Drive.** The shape is
  decided (Luke, 2026-08-29, measured rather than inherited): never
  write into a folder the pipeline did not create; always create a
  fresh per-release child, which both bundles' tranche/replace
  patterns already suit; keep the `drive.file` scope — widening it
  hands a document-mover visibility of the whole of Luke's Drive to
  solve a file-copying problem. What is left is the build: create the
  per-release folder, upload, and guard the name-collision hazard by
  `files.get`-ing the created id back and stopping on 404 (under
  `drive.file`, `Sync.folder`'s name query cannot see hand-made
  folders and would quietly create a duplicate beside one — the
  duplicate-archive mechanism, still live). Destinations the pipeline
  does not create belong in `dcp/drive.py` as ID constants, never
  resolved by name. One step stays manual whatever happens: a notebook
  holding a previous release must be emptied or replaced, and the new
  notebook's URL must reach `NOTEBOOK_URL` before step 12.

- **The materialise leaves membership rows unretired when it retires
  a site** (found 2026-09-02 while verifying the reader's adjacent-power
  links; 65 rows on 63 applications, measured). `dcp/sites.py` retires a
  site that no longer emerges from the clustering and does not touch its
  `site_members`, so a row on a dead site still reads `retired_at IS
  NULL`. Where the application is also a member of a live site nothing
  is affected. Where it is not — four adjacent-power applications
  retired with their sites by #252, 144 documents — every "membership-
  less" test read it as a member: not staged under `adjacent_power/`,
  in no live site's folder, and its old folders pruned at 2.11, so the
  documents had **no Drive home** until the three queries (the staging
  build, the id recorder, the sample verifier) were taught to require a
  live site (PR #346; pinned by a test over all three). They return at
  the next staging build and sync. The durable fix is in the materialise
  — retire the rows with the site, as the revive path already retires
  stale ones — and it is a data change to make deliberately, with the
  65 rows listed first.

- **`drive_sync.py`: the batching half is still open** (the
  concurrency half closed 2026-08-29 — `--workers` now defaults to 12;
  HISTORY). The Drive batch endpoint takes 100 calls per request,
  which would beat any number of threads, and the ledger's own write
  is still a non-atomic `write_text` every 50 changes — worth making
  atomic before anyone relies on killing a sync safely. The design
  constraint stands: parallelise the API calls, never the ledger
  writes.

- **Four editorial questions from the signal-family repair** (the
  repair itself — the missing-family backfill across 557,747 OpenAI
  and 49,039 local findings, and the snake_case token-boundary fix —
  shipped 2026-08-26; HISTORY, "The corrections that landed between
  2.9 and 2.10"). All four are left for the data and visuals teams,
  because each changes what a family means rather than how a token is
  delimited:

  - **`author` in `party_adviser` captures "authority".** party_adviser
    is declared first, so `party_authority`'s own
    `local_planning_authority` token can never win: **11,706 rows
    carrying "authorit" are filed as `party_adviser`**,
    `local_planning_authority` (2,980 rows) among them. The largest
    single misfile in the vocabulary, and nothing to do with the
    boundary.
  - **`ward` is the one token deliberately left broken.** Correcting it
    recruits 41 rows of `upward_light_ratio`,
    `seaward_boundary_distance` and `outward_hdv_peak` against 21 rows
    of electoral wards — the only token where the correction takes in
    more labels it was not written for than labels it was. Doing it
    properly needs a *leading* boundary as well, which would also stop
    it matching today's `upward`: a change of scope.
  - **2,183 rows sit in a family the mapper no longer derives.** The
    re-derivation was scoped to `unclassified`, so rows the broken
    boundary had filed elsewhere stayed where they were —
    `chp_emissions_standard` in `air_quality_emissions` rather than
    `power_generation`, `eia_document_reference` in `application_admin`
    rather than `eia_process`. Re-deriving all `derived` rows would move
    a net +501 into the two panel families and 56 out; the script has no
    flag for that scope yet, deliberately, because it overwrites
    families that are currently visible to readers.
  - **`land_quality` and `application_admin` do not classify as their
    own names.** Neither claims a token containing "land" or "admin".
    Recorded in the test as known gaps rather than papered over.

- **The deep-read's evidence quotes are snippets, not sentences.**
  Found by Luke while hand-checking the generation sample: row after row
  arrived as a fragment — "Total Installed Capacity (Megawatts) 0.21",
  "and 42.56kW (delivering c.46.1MWh/yr) at Units 2-8" — where the
  sentence around it was what settled the question. §4.1e worked around
  it by sending the passage as well as the quote, and the sample's
  hand-checker had to read the passage to answer at all. The fix belongs
  upstream, in the deep-read prompt: ask for the whole sentence a figure
  sits in, so a quote that reaches a reader carries its own meaning.
  Nothing already stored changes; the passage stays the belt to the
  sentence's braces.
- **Re-measure the 1.71 kW/m² floor-area factor.** It drives the
  published power estimate for every site with no disclosed capacity. An
  ad-hoc query on 2026-08-11 suggested it may have moved — 88 sites now
  disclose both a capacity and a floorspace figure, against the 53 it was
  calibrated on — but with different signal matching from the original,
  so this is a flag and nothing more. Reproduce the original criteria
  from git history first, then re-run, then decide.
- **Make the data dictionary's corpus statistics computed.** The count of
  sites disclosing water consumption exists as three hardcoded figures
  written at three moments — HISTORY 93, the dictionary 76, live 119 —
  and only the last is true. One function taking a connection, called by
  both exporters, kills the class. Until then, measure before quoting any
  dictionary statistic.

- **Promote `associated_id` to a typed `applications.parent_ref`
  column.** Parent-backfill confirmed the field is reliable; a typed
  column makes family navigation a join rather than JSONB extraction.
- **`deepread_log.pages_sent` counts a page once per chunk, not once.** A
  page split across chunks is recorded once per chunk it appears in, so
  the array is a send log rather than a set of pages: document 52945 has
  148 entries for 32 distinct pages, and 21 rows currently hold more
  entries than `pages_total`. Nothing divides by it today — the runners
  only write it, and the log line's `[148/32 pages]` is the sole visible
  symptom — so this is latent rather than wrong. It becomes wrong the
  moment any coverage figure is computed from `array_length`, which is
  the obvious way to use the column. Either store distinct pages or make
  the ambiguity impossible to misread; do it before a consumer needs it,
  not after one has published from it.
- **Improve the automated test surface.** When this was written the
  suite was good at internal consistency and blind to three things, and
  almost every defect found on 2026-08-11 sat in one of the gaps. Two
  of the three are closed — `tests/test_reader_smoke.py` drives the
  built reader in a browser, and CI drives the committed one on every
  push (HISTORY, 2026-08-27); `tests/test_build_determinism.py` builds
  the reader twice against a Postgres snapshot and asserts the two are
  identical apart from the stamp (HISTORY, 2.8). The third is open.
  Worth doing properly rather than adding a test per bug — the
  recurring shape of these is *fixed the symptom, missed the cause*.

  ~~**Nothing drives the built artefact.**~~ *Closed by
  `test_reader_smoke.py`; the paragraph stays as the reason it exists.*
  The reader's card links did nothing in a shipped release; a chip took its own flex column and
  squashed the map into a third of the width; an energy checkbox went
  dead inside a projection. All three were invisible in review and
  obvious within seconds of opening the page. A build-and-drive smoke
  test — generate the reader, load it headless, click the things a
  reporter clicks, assert what they do — would have caught every one.
  It would also have caught the two prose definitions on one page, which
  survived a full test run and was found by reading the output.

  **Nothing asserts that a stated number matches the data it describes.**
  The count of sites disclosing water consumption existed as three
  hardcoded figures written at three moments — 93, 76 and 119 — and
  every one passed. Same for the findings-inflation percentage. A test
  that recomputes each statistic the dictionary quotes and compares it
  to the string would make that class impossible; making them computed
  (above) is the better fix, and the test is what stops the next one
  being hardcoded.

  ~~**A build is not yet asserted to be a function of its inputs.**~~
  *Closed by `test_build_determinism.py`; the trap below is why it is
  an integration test against the real corpus.* Two
  builds of one database differed on 42 lines until 2026-08-22 (HISTORY:
  *A build has to be a function of its inputs*), and they now differ only
  on the generation timestamp. Nothing holds that. The check is cheap and
  the discipline already exists — diffing a build against the last
  release — so a test that builds the reader twice against a fixed
  snapshot and asserts the two are identical apart from the stamp would
  close it. Note the trap found while fixing it: an integration test on a
  small fixture does *not* catch this, because Postgres returns a handful
  of tied rows in insertion order regardless. It has to be at scale, or
  it has to read the query.

  **The pattern to copy** is `tests/test_release_defaults.py`: it asserts
  a *rule* over the whole tree — no default may name a release — rather
  than one instance, and it was verified by reintroducing the bug and
  watching it fail. `tests/test_adjudication_gate.py` is the
  counter-example worth understanding: it asserts the corrector and the
  gate agree, and nothing asserts either is right, which is how the
  thermal-output hole survived.

- **The publish button.** The second of the two workflows sketched with
  Luke on 2026-08-26. The first — checks on every push — is built and
  green as of 2026-08-27, and what it caught on its first run against a
  clone from nothing is in HISTORY. The order between them was the
  whole point: the first automation in a repo with none should be one
  that checks, not one that publishes.

  **Workflow 2 — build, verify, then wait for a click.** On a push to
  `main` touching `index.html`: build the Cloud Run image, run
  `deploy.sh`'s anonymous-access probe, and stop at a **GitHub
  Environment with Luke as a required reviewer**. Approving deploys.

  Gate the *deploy job only*, not the whole workflow, so that by the
  time the click is asked for the image exists and the gate has been
  proven fail-closed. That is approving a verified release rather than
  authorising work that has not happened yet.

  Four details decide whether it is safe:

  - **Workload Identity Federation, never a service-account key.** The
    repo is public and the GCP project is Luke's personal one. Pin the
    trust policy to this repository *and* to `refs/heads/main`.
  - **`on: push` with `paths: [index.html]`, never `pull_request`.** A
    fork PR able to run this workflow would hand strangers a deploy.
    The path filter also means an unchanged `index.html` carried along
    by a code merge triggers nothing at all.
  - **The condition this waited on has already happened.** The bullet
    used to read "it gets safer once EdgeOne retires — today merging
    *is* publishing, because EdgeOne builds from git". Since 2026-08-26
    EdgeOne's middleware is a pure redirect and publishes nothing, so a
    merge is already only a commit and the single route to readers is
    `cloudrun/deploy.sh` (runbook step 14). `index.html` can therefore
    live in the repo like any other file rather than staying
    uncommitted in order to stay unpublished — which is how a
    `reset --hard` silently discarded a built payload on 2026-08-26.
  - **The probe must fail the job.** `deploy.sh` already exits non-zero
    when the live service answers anonymously, so this costs nothing.
- **Four sites report a total site demand below their IT load.** All four
  are correct — the figures come from different applications at
  multi-building sites, and each figure names its source application in
  the reader. Worth adjudicating by hand rather than changing the
  rollup rule.

- **A story lead the corpus can already evidence: who qualifies their
  "100% renewable" claim, and who does not** (Luke's idea, measured
  2026-08-28 across the snapshot store and the EA permits; the full
  working is in this file's git history at that date). The asymmetry:
  **Ark and Kao name their standby fuel (HVO) beside the green claim;
  VIRTUS, Vantage and CyrusOne make an unqualified claim while holding
  permits for 1,259 MWth across 190 engines.** Guards that must travel
  with it: "100% renewable" conventionally describes procured grid
  electricity, so an unqualified claim is not false — the question is
  what it omits; permits are only required at 50 MWth, so **no permit
  found is not no generators** (Pulsant's whole estate sits under the
  threshold) and the no-permit rows are never evidence of a cleaner
  operator; permit MWth is thermal input, not emissions; and the
  snapshot store is curated, so absence from it is not absence of a
  claim. The sharper finding underneath: the standard permit cap is
  **500 hours' emergency use a year, per installation** — never
  engines × hours — and the emission-limit regime does not bite below
  exactly that line, so the permit is written to it. Three actions:

  1. **Send the drafted EIR for the actual run-hour returns**
     (`docs/requests/2026-08_ea_standby_generator_run_hours_eir.md`) —
     the Agency holds annual returns and outage notifications, and reg
     12(9) means emissions information cannot be withheld as
     commercially confidential.
  2. **Read, don't count, the generation findings at the no-permit
     green claimants** — direction decides meaning: Greystoke's West
     London Technology Park carries 379 diesel mentions stated as
     reliance ("significant number of diesel back-up generators … 30
     years"), while Apatura's ten are proposals to avoid diesel.
  3. The CAR adapter below, which corroborates the EIR with dated
     inspection records.

- **Harvest Environment Agency Compliance Assessment Reports** (found
  2026-08-28 when Luke asked whether run hours were already published
  — they are not, but this is). Public Registers Online publishes CARs
  for Installations since 18 August 2025, free at a predictable path
  (`/public-register/documents/installations/compliance/EPR_<STEM>/…`),
  recording what an officer found on site — the CAR for EPR/QP3434DR
  (Brick Lane Data Centre, inspected 28/10/2025) states that three
  standby generators ran during a UPS replacement, with a noise
  complaint following: *actual* generator operation, dated, from a
  public source. Coverage is thin and growing — several data-centre
  permits still show "No document published" — and CARs are inspection
  reports, not annual returns, so they corroborate the run-hours EIR
  rather than replace it. Worth an adapter on the
  `fetch_ea_permits.py` pattern, re-run periodically as the register
  fills.

---

## Parked

Deferred consciously. Return when journalism need warrants.

### Queued behind the consumption-context line

- **LA-level consumption choropleth on the reader map ("plan 2",
  agreed 2026-08-12).** A toggleable layer shading each local authority
  by the change in its large-user (half-hourly non-domestic) electricity
  consumption 2019→2024, with the sites drawn on top. The signal is
  strong and already measured: against a national fall of 9%, Slough is
  +60% and Hillingdon +36% — the two largest absolute risers in Great
  Britain — while the null cases render too (Docklands −15%, Hertsmere
  flat despite 260 MVA committed in UKPN's queue), which is pipeline
  versus consumption on one map. Ships only after
  [docs/PLAN_CONSUMPTION_CONTEXT.md](docs/PLAN_CONSUMPTION_CONTEXT.md)
  ("plan 1"): the per-site sentence proves the numbers, the
  council→authority mapping and the caveat language before anything is
  painted. Constraints decided up front: local-authority granularity is
  forced, not chosen — DESNZ publishes half-hourly consumption only as
  LA rollups and the per-MSOA rows exclude it entirely; the layer
  describes the authority's consumption, never the site's; the series
  ends 2024 and says so; simplified LA boundary geometry must fit the
  single-file reader's payload budget. The data is already committed in
  `data/external_sources/` (provenance in its README).

### Postponed past the phase 2 and 2.1 releases

None is abandoned; each is a known, scoped piece of work.

- **The acquisition tail.** Counts superseded on 2026-08-27 — see
  "Phase 2 — the tail of the collecting" above for what dissolved and
  what the sweep found; the honest residue is a query on
  `acquisition_outcome` after it completes.
- **Scanned-page orientation detection — closed on evidence, not done.**
  The theory was that councils scan sideways and `--psm 3` misses it. The
  231 documents that OCR'd to nothing were the obvious test cohort, and
  Apple Vision — which detects orientation itself — read them as blank
  too. They are photographs and line drawings with no text in them, so
  there is nothing for a better OCR pass to find. Reopen only with a
  document that demonstrably has readable text nobody is reading.
- **Coverage gaps** — Northern Ireland (whole nation, one adapter),
  pre-application/screening entries, the operator watch-list. (Section
  35 / NSIP is no longer on this list: the watcher is built and running,
  see HISTORY 2026-08-25.)
- **Phase 3, the second opinion.** `scripts/compare_readers.py` exists.
  The dual-read ran 17–24 August and has stopped again on its own — the
  last finding written was 2026-08-24, which is what gave 2.7 a clean
  boundary without killing anything. Its 4,117 power figures are
  adjudicated as of 2026-08-26. What it has *not* produced is the
  deliverable: the corpus-wide comparison, where two models disagree and
  the disagreement is the finding. That and water adjudication remain
  the next release's work.

### Longer-standing

- **DC01 — identified (2026-08-28), follow-up remains.** DC01UK, land
  east of South Mimms Services, Hertsmere: our PTNO-12809263, outline
  Hertsmere/24/1152/OUTEI approved 23 January 2025 (NCE, supplied by
  Luke; 162 corpus findings name DC01). All four originally-unidentified
  Foxglove cases are now resolved. What remains is the journalism the
  reconciliation flagged: Foxglove's 6,056 tCO2e/yr for 320 MW is the
  most implausibly low emissions figure on their list, and the site's
  own documents (400 MW, beside Barbour's 250 and Foxglove's 320) are
  the place to test it.
- **Document corpus mirror.** `data/raw/` is local-only and growing.
  Zenodo (DOI, CC-BY) is the leading candidate for a reproducibility
  mirror. Decide once the corpus stops moving.
- **`other_fields` normalisation.** PlanIt carries applicant and agent
  fields inside `raw_metadata`; promote to columns if a bigger
  operator-name sweep happens.
- **Pre-2018 broader-keyword backfill.** PlanIt thins sharply before
  2018. Parent-backfill already pulled in substantive pre-2018 parents; a
  separate sweep would catch cases with no child in our window.
- **Environment Agency permits — the tail, not the source.** The
  register and 42 permit claims — 7,439 MWth — landed on 2026-08-22
  (HISTORY, and `docs/EXTERNAL_DATA_SOURCES.md` §6). Three things are
  left. **Fifty-five candidates have no permit publication on gov.uk**,
  mostly MCP registrations, which are lighter-touch and may not be
  published at all; whether the Environment Agency will supply them on
  request has not been asked. **Eleven claims are not fully
  self-corroborating** — three state a total with no breakdown to check
  it against, four state one their breakdown disagrees with, and four
  state none at all — and reading their schedules would settle each one.
  **Thirty-four claims are unmatched**, and most are unmatched because a
  site record covers a whole estate rather than because the permit is
  obscure, so the matching is blocked behind the partitioning below
  rather than behind anything about the permits.
- **Site partitioning, now with evidence.** The permits are the sharpest
  partition evidence the project has, because each one names a campus and
  gives its grid reference. Nine permits from seven operators,
  1,430 MWth, fall inside site 23 alone, which is the only site record on
  the whole Slough Trading Estate. Site 5 holds Interxion, Global Switch and
  Telehouse; site 59 holds Vantage and Colt as well as Microsoft; site 11
  holds Amazon and NTT. Each of these is listed under `considered`, with
  the reason, in `environment-agency-permit-matches.yaml`. The mechanism
  is `data/priors/site_partitions.yaml`, honoured by `dcp/sites.py`,
  and it works at corridor scale: the site 61 split (ten campuses,
  2026-08-27, see Phase 2 above and HISTORY) is the worked example to
  copy. **Site 23 is now done** — eleven campuses, 2026-08-28 — which
  leaves 5, 59 and 11.

  **Site 37 was examined and needs no partition** (2026-08-28), which
  is worth recording because it was briefly listed as a target here on
  a postcode match. `PTNO-12301553` holds 30 applications across two
  Hillingdon stems 1,002 m apart — 37977 at Prologis Park West London,
  Horton Road, Yiewsley, and 18399 at Unit D, Prologis Park, Stockley
  Road, West Drayton — and the applicant of record in *both* is
  VIRTUS, with Prologis UK Ltd as landlord. VIRTUS's own page calls
  the whole thing one place: "The VIRTUS Data Centre Campus at
  Stockley Park … comprises of four facilities", listing LONDON5,
  LONDON6, LONDON7, LONDON8 and LONDON14. By the same rule that keeps
  Iron Mountain's LON-1 to LON-3 together over 810 m, this is one
  campus and the site record is right.

  The reason it looked like a target is instructive: CyrusOne
  publishes LON2 at "DC2 Prologis Park Heathrow, Stockley Road, West
  Drayton, UB7 9FN", the same postcode as stem 18399 — but **no
  application in the corpus names CyrusOne at that postcode or in
  that site** (checked directly). CyrusOne DC2 is a coverage gap on
  the same business park, not a second operator inside the site
  record. Postcode proximity suggested a partition that the operator
  evidence then refused, which is the trap the permit-matches file
  warns about — reference stems and the applicant of record in the documents
  as the boundary evidence, every member assigned so nothing is left
  to spatial chance. Sites 5, 59 and 11 are what remain (23 was done
  on 2026-08-28, eleven campuses), and the permits carry their
  evidence.

  **The partition unit is the campus, not the building** (Luke,
  2026-08-28, with the operator's own pages as the source). Iron
  Mountain's London campus page states "Our campus features three
  facilities — LON-1, LON-2, and LON-3", and the LON-3 page places it
  on a "Secure 2.5-acre site in Slough Trading Estate, part of LON-1,
  LON-2, LON-3 campus". So 110 and 111 Buckingham Avenue — 232 m apart
  and separate Barbour projects (PTNO-12468506, PTNO-12833153) — are
  distinct data centres that belong in **one** partition, not two. A
  partition drawn per building would fragment a campus as surely as
  the 1 km radius has welded seven of them together, and the site 61
  split exists precisely because fragmentation blocked a capacity
  claim.

  Two facts to carry into the drawing. The campus discloses **61 MW**
  across the three facilities (8.7 + 27 + 25 = 60.7, the rarest thing
  in this survey: a total its own breakdown checks). And the postcodes
  **conflict** — Iron Mountain gives LON-3 at "111 Buckingham Avenue
  Slough, SL1 4PF", while Barbour has 111 Buckingham Avenue at SL1 4PN
  and puts SL1 4PF on 110. Postcode is a matching key, so one of the
  two is wrong and the conflict has to be resolved rather than
  averaged.
- **Requests outstanding, and three drafted awaiting Luke's send.**
  NESO and Ofgem were written to on 2026-08-12 and replies are due
  around 10 September. The three never-sent requests are now drafted in
  [docs/requests/](docs/requests/) (2026-08-27): the CCA site-level
  consumption FoI/EIR to the Environment Agency copied to DESNZ, the
  NESO EIR for the project-level demand connection queue, and the DNO
  EIR template with its fourteen-licensee address list. Each carries
  the reg 5(6) answer to section 105 pre-emptively, and each runs ~28
  days from sending — waiting is still the whole cost, and only the
  sending remains.
- **UKPN's gated datasets are unpulled.** The Large Demand List and
  "Data Centres by Local Authority" sit behind Luke's portal login;
  anonymous access returns headers only, so nobody else can fetch them.
- **The VIRTUS property company's accounts are still not retrievable,
  and the filing moved.** Retried 2026-08-27: the 19 and 20 August
  filings no longer appear in 09840065's filing history — replaced by a
  single group-accounts filing dated 2026-08-26, which has no document
  image yet either. Keep retrying; the property company is the one that
  states capacity, not the operating company.
- **A fifth operator tranche would be cheap** (the fourth landed
  2026-08-30 — thirteen pages including the consultation sites, with
  claims; HISTORY, "The operator pages day"). Colt is no longer
  blocked: Tudor Works and Hayes Bridge Retail Park are their own
  sites as of 2026-08-27 and the London 4 claim is matched, so a Colt
  tranche (London 5–8) now has records to land on. ~~Iron Mountain's
  pages have never had a snapshot~~ — **held 2026-09-01** via the
  browser harvest, so the 61 MW calibration case now rests on pages
  this project holds, and `--from-file` is the route for the next
  operator a challenge page blocks.
- **Multimodal pass over drawings.** Rejected in v1 and still rejected:
  PDFs are overwhelmingly text-layered, and concealed plant will not be
  in the drawings. Revisit only for a specific application where both
  conditions fail.

---

## Open questions

- **Does the Google Sheet stay the annotatable copy?** It is a
  conversion, not the file the pipeline writes, so it drifts from the
  workbook unless `scripts/sheet_sync.py` is run. That is deliberate —
  the point is that people can comment on it — but it means two
  artefacts claim to be the workbook.
- **Do pre-planning schemes become first-class universe members?** See
  the coverage gaps above. Affects site counts, so worth settling before
  a number goes in print.
- **PlanIt rate-limit politics.** PlanIt is donation-supported and
  friendly, and we are a heavy user. It now 429s far more aggressively
  than in May — assume an hourly quota and plan sweeps at ≥10 s spacing.
  A courtesy email is overdue.
- **Public-data ethics for personal fields.** Householder applications
  can carry applicant names. The schema stores raw values and redaction
  happens at export; the pre-publication sweep needs re-running against
  any new aggregate that touches personal fields.
