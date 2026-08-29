# Roadmap

What is still to do. Everything already built and decided — including
the approaches tried and rejected, which are worth knowing before
re-proposing them — is in [HISTORY.md](HISTORY.md).

Current state: **496 sites** (plus 25 pre-planning), **2,034
applications** in the site universe, **58,262 documents and moving**
(the 2026-08-27 acquisition sweep resumed after the release boundary
and is still running). Findings and adjudication counts move while the
corroboration pass runs and are deliberately not restated here —
`scripts/corpus_stats.py` prints them, and each release states the
boundary it was stamped at.

**2.9 released** (PR #165, merged 2026-08-27 14:15; artefacts in
`data/exports/phase2.9_build/`, reader stamped 14:45). The corpus has
moved on considerably behind it — three site merges, 13,138 deep-read
findings and 238 machine readings collected the same evening — so the
next release is not a rebuild of the same corpus. Whether the Cloud
Run deployment has been run for 2.9 is not recorded here and is not
checkable from the repo: `cloudrun/deploy.sh` is the only thing that
changes what readers see behind Guardian sign-in. EdgeOne is a
signpost: PR #135 merged 2026-08-27, so it redirects and the shared
password is retired.

**Reading is complete for phase 2.1**, stamped 2026-08-11 with the
Studio reader stopped so the boundary is clean: 37,992 of 38,005 prose
documents read. The Phase 3 corroboration read continues on the Studio
and is roughly 60% through its 48,191 in-scope documents. Two other numbers belong beside that one and are stated
in the reader rather than folded into it — 4,204 documents in the
repetitive classes are sampled out at one in five by policy, not
backlog, and 231 are held but contain no words at all, confirmed blank
by two independent OCR engines. Every capacity figure that existed at
the boundary is adjudicated.

---

## Regenerating a release

The chain, its ordering constraints and the traps are in
[docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md). Two steps
must precede the artefacts: adjudication corrections (enforced in code
by `dcp/adjudication_gate.py`) and the Drive staging rebuild that picks
up the new CSV adjudication columns.

## Deferred to 2.9

Decided on 2026-08-26, while 2.8 was being assembled. Each is scoped
and none is blocked on anything but sequencing — they are held back so
2.8 ships the corpus work rather than growing to hold everything found
alongside it.

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

- **The "31 browser-routed applications" mostly dissolved on
  measurement** (2026-08-27) — the notes had aged past their premise.
  Broxbourne's LPAssure bloc: all 27 applications already hold
  documents. Coventry: 26 of 29 already hold documents (3 empty; its
  completeness is still unmeasured because the relist audit skips the
  host by name). Northern Ireland: no longer browser work at all — the
  adapter exists (HISTORY, 2026-08-27). What genuinely remains after
  the 2026-08-27 sweep finishes: **24 NEC, 3 Northgate, ~14 bespoke**
  — and the Northgate three are three different situations, probed the
  same day: Liverpool migrated to a Tascomi register
  (lar.liverpool.gov.uk answers; the northgate host is dead), Hackney's
  host refuses connections entirely (find where its register lives
  now), and Birmingham gates scripted clients with 403/503 (a real
  browser passes — the one genuine human-at-keyboard job left, and its
  Hackney application is a conditions detail on the Interxion site's
  energy-centre emissions). Re-measure the residue from
  `acquisition_outcome` once the sweep completes; do not re-quote these
  counts without doing so.

## Phase 2 — the tail of the collecting

- **The acquisition tail, remeasured 2026-08-27 and shrinking as this
  is written.** The standing counts (108 being worked, 31
  browser-routed) had aged badly — see the Deferred-to-2.9 note above
  for what dissolved. The day's real finding was larger than any of
  them: **159 outstanding applications were reachable with adapters
  that already existed** and had simply never been swept — dominated by
  the energy-adjacency blocs discovered on 2026-08-07 (Southwark 24,
  Camden 21, Bristol, Brent…) whose fetch never ran. That sweep resumed
  after the 2.9 boundary and was still running overnight on 2026-08-27,
  into the S's with **42 applications left after the one in hand, 23 of
  them Southwark**; every application writes its outcome row, so the
  honest residue is a query on `acquisition_outcome` after it
  completes, not a number written here. Note the run in flight predates
  PR #183, so its per-application ceiling is still the broken one —
  expect it to have spent hours on single Southwark applications. The genuinely-hard classes (CAPTCHA, hard 403/500/503,
  Incapsula) still stand.
- **Historical partial fetches are now measured. The refetch is not
  done.** A short fetch used to be recorded as complete, and the
  manifests could not show it because they record what was stored and
  not what was offered. `scripts/relist_audit.py` settles the question by
  re-listing and comparing; the comparison lands in
  `document_listing_audit` (migration 026), append-only and idempotent on
  the listing's own content hash, with the full offered set kept beside
  every count. It obtains listings and never downloads a document: the
  deliverable is a measurement and a prioritised list, and which of it is
  worth the portal traffic is an editorial decision.

  Three passes, cheapest first. `--pass snapshot` parses the
  documents-tab HTML already in `source_snapshots` — the very page each
  short fetch was working from — at no portal cost, and covered 1,166
  applications on its own. `--pass harvest` does the same for the
  browser-harvested Salesforce listings (64). `--pass live` re-lists the
  rest through the project's own adapters at 10s spacing, one client per
  host, round-robin so a slow council costs only its own queue.

  **As measured on 2026-08-26: 1,554 of 1,696 applications that hold
  documents, and 2,260 documents the registers offered that the corpus
  does not hold, across 219 applications.** The raw offered-minus-stored
  difference is 2,846, and two structural over-counts are subtracted from
  it: 74 documents held under a twin application (seventeen portal URLs
  each serve two application references for the same case —
  Cambridge/SouthCambs, a Reading reference in two spellings — so one
  listing describes both and the fetch filed each document under
  whichever row it reached first), and 512
  where the register listed one file under two URLs and `documents`,
  unique on `(application_id, content_sha256)`, stored it once. The
  shortfall is concentrated — 3 applications lose more than 100
  documents, 28 lose 21–100, and 99 lose exactly one — and it is not
  only drawings: 175 of the absent documents are filed
  `Report/ Statement`, the class where power disclosures live.

  **2,260 is an upper bound on URLs, not a count of missing content, and
  the refetch proved it.** Fetching 3,083 of those documents produced
  only 1,173 new rows: **1,910, or 62%, were byte-identical to a
  document already held under the same application at a different URL.**
  The audit subtracted 512 such cases; the real number is more than
  three times that, because a register that lists one file under two
  URLs is far commoner than the sample suggested. Buckinghamshire
  `PL/24/0754/OA` downloaded 170 documents and created no rows at all;
  Hillingdon `78343/APP/2025/719` downloaded 219 and created none.
  Quote "2,260 URLs the registers offered that we had not fetched",
  never "2,260 documents missing" — and note the recovery rates below
  are against URLs for the same reason.

  **1,380 of the 2,260 are now held (61%), and 249 of the 291
  reports/statements (86%)** — the class that mattered. Northumberland
  Energy Park recovered 176 of 177, Green Tech 171 of 179, Catalyst 135
  of 136, Telehouse North Two 93 of 104. What is left is deliberate:
  Union Park keeps 157 unfetched because that tranche was cut in favour
  of the Northumberland reports (30 Hillingdon applications at 25–35
  minutes each, on one host, with Union Park behind the partition
  blocker anyway), and Gilmorehill's 491 were never attempted — a
  university masterplan's drawings. Resuming is one command and costs
  nothing already done: `scripts/relist_refetch.py --tranche rest`, then
  `--tranche glasgow`.

  229 per-document failures, each with a reason: 158 HTTP 403 from
  Greater Cambridge (a blanket refusal on file downloads), 85 server
  disconnects from Northumberland that all recovered on the retry pass,
  39 404s for documents withdrawn since the May listing, and 18
  persistent 504s from Tower Hamlets — including two energy strategy
  reports that failed identically an hour apart, which is a genuine
  portal failure on exactly the class we want.

  Worst affected, which is the reporter-facing number at risk — and the
  document type matters as much as the count, because a site short of
  drawings has lost far less than a site short of statements:

  | site | absent / offered | mostly |
  |---|---|---|
  | Northumberland Energy Park (`PTNO-12785975`) | 177 / 552 | **161 reports and statements** |
  | Green Tech Business Park (`PTNO-12578951`) | 179 / 500 | 158 drawings |
  | Catalyst Business Park, Widnes (`PTNO-12906175`) | 136 / 382 | 133 plans |
  | Telehouse North Two (`PTNO-12058499`) | 104 / 1,030 | **50 reports**, 23 plans |
  | Union Park / North Hyde Gardens (`PTNO-12511337`) | 160 / 3,062 | mixed, across 34 applications |
  | Gilmorehill campus (`PTNO-12104907`) | 491 / 1,565 | drawings; a university masterplan, not the investigation |

  The full list is `data/reports/relist_refetch_list.csv`, one row per
  absent document, ordered by site.

  What is left:

  - **The refetch pass itself.** Nothing has been re-downloaded. The
    obvious first cut is the reports and statements, not the drawings.
  - **142 applications are still unmeasured**, holding 3,381 documents:
    107 on portals with no listing-only path (44 bespoke, 35 Northgate,
    28 NEC), 26 on Coventry, skipped by name because it is AWS
    WAF-protected, 7 Wychavon applications whose host reset the
    connection three times and was abandoned, 1 Manchester timeout, and
    1 Salesforce register with no harvested listing. Errors are
    retryable — re-running `--pass live` picks them up. The rest need
    either an adapter or a browser, and the adapter only has to produce
    a listing, which is a much smaller job than a fetcher.
  - **29 applications hold documents against an empty listing.** Newport
    was the bulk of these until its separate docstore was wired into the
    audit; what remains is mostly manual harvests, whose documents carry
    `file://` URLs no listing can match.

  **Still true: do not quote a per-site document count without checking
  this table.** A count of held documents is a floor until the site's
  applications are measured and their shortfall is either refetched or
  stated.
- **The site 61 split is done** — drawn, materialised, singletons
  dissolved, six claim matches loaded (HISTORY, 2026-08-27, two
  entries). Its artefact and Drive pickup shipped in 2.9; nothing of
  it remains.

- **The sites list now says which of its rows are datacentres** (issue
  #159, PR #178, HISTORY 2026-08-27) — derived, filterable and
  rendered, so the original item is done. What it leaves for 2.10 is
  narrower and editorial: two of the classification's rules were
  decided in the building of it and deserve a reporter's eye, since
  each changes what the list asserts about real rows. That a Barbour
  project title naming a data centre settles the class (21 sites), and
  that `pre_application` and `enabling_works` count as
  datacentre-positive. Both are one constant each in
  `dcp/site_class.py` to revisit.

- **Replace "The rest of the package" block with a computed scale
  panel** (issue #166 holds the request; shape agreed with Luke
  2026-08-27). The block is duplicative — a button pointing at content
  one scroll away — and what the start page actually lacks is scale at
  a glance. The replacement: "The scale of what the documents
  disclose", every figure computed at build and never typed, every row
  linked to the query or cohort that produces it, caveats in the
  panel's own words (covers only the minority of sites stating
  figures; floors from an incomplete read). Candidate rows: total
  disclosed capacity across the N disclosing sites; standby generator
  units where documents state counts, with the diesel/gas split where
  fuel is named; total standby MW; total contracted grid connections.
  Comparators only where a published source states one — Ofgem's 73 GW
  queue is in External aggregates with its paragraph number — never
  invented. The 12.73-GW-is-twelve-million-households correction that
  settled the framing is the argument in one line: computed and
  citable beats vivid and wrong.

- **Site name aliases are built; the curation is standing work.** The
  mechanism from issue #169 landed 2026-08-27: `data/priors/
  site_aliases.yaml` (alias beside the derived name, per-entry source,
  a dead key fails the build), displayed everywhere with the derived
  default kept on the site's own page, and two columns on the workbook's
  Sites sheet. Seeded with the three known cases — West Burton, the
  Blyth substation, Maydown Road Derry. What remains is editorial and
  continuous: name a site when its derived name misleads, in the yaml,
  with the source.

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

- **The three Section 35 campuses are sites with nothing in them.**
  Quest Park, Dartford and the Wapseys stub carry **0 documents and 0
  findings** each. The watcher (HISTORY 2026-08-25) makes the *fact* of
  a direction visible and deliberately does not fetch its attachments;
  the eleven PDFs were cached by hand into
  `data/seed_cases/{wapseys_wood,quest_park,dartford_ebbsfleet}/` so
  acquisition could follow up, and acquisition never did. **So the
  figures those documents contain are not in the corpus**: QuestPit's
  1GW campus / 720MW IT load, powered by on-site gas until a grid
  connection it does not expect before 2034, and Dartford's 300MW /
  240MW IT with a firm Gate 2 NGET allocation, exist only as loose files
  and prose in a pull request. A reporter searching the reader for
  either finds a named site and no evidence — which is the same failure,
  in a new form, as the one that made the Guardian's team conclude we
  were missing Wapseys Wood.

  The path exists and is short: copy each bundle into the application's
  `Manual/` folder and run `scripts/ingest_manual_docs.py`, then the
  normal read. Wapseys is the exception that proves it matters — its
  register sibling `EN0110030` sits in the same site with 6 documents
  and 2,815 findings, which is why that site reads properly and the
  other two do not.

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

- **`scripts/load_capacity_claims.py` was broken from the SPV work until
  2026-08-26; fixed.** `companies-house-claims.yaml` gained claims with
  `quantity_type: scheme_capacity` and `investment_property_fair_value`,
  and no migration had added either value to the
  `capacity_claims_quantity_known` CHECK constraint — so the loader
  aborted on a check violation and rolled the whole batch back, taking
  **every source** with it, NESO and the Environment Agency permits
  included. Migration 030 adds both types with the reasoning for each,
  and the loader now runs: 10 claims inserted, 234 → 242 in the store.
  The reason it had been left was that applying the migration also loads
  the pending SPV figures; those are now loaded, with the Court Lane
  matches already adjudicated and six new ones held back under
  `considered:` because their site records are over-merged clusters.

- **The incomplete Drive archive is explained, and the fix is in.**
  The cause, established 2026-08-26: `build_drive_staging.py` stages a
  document only if its application has a live `site_members` row. 143
  applications discovered 2026-08-07 (`discovered_via: energy_national`),
  whose 3,679 documents were fetched on 08-08/09, had no site membership
  until the materialise of 2026-08-25. Their files were therefore never
  in the staging tree, never in the 2026-08-21 sync's candidate set, and
  invisible to that sync's `skipped` and `failed` alike. **The 08-21 sync
  was complete and correct over the tree it was given** — 50,406
  candidates, 0 failed, 0 skipped in `data/drive_sync.log`, and the
  arithmetic closes exactly against the later runs. The ledger-loss
  episode of 2026-08-21 is **exonerated**; it was the obvious suspect and
  it was not this.

  What is now in code: `build_drive_staging.py` prints the documents it
  did not stage, grouped by the application's latest triage verdict, and
  exits non-zero unless every one of them is triaged `not_dc`. Replayed
  against the 08-21 state it reports *3,584 documents held for 139
  in-universe applications are not in this tree*. It also refuses to
  build when `max(sites.materialised_at)` predates the newest
  `applications.first_seen_at` or `projects.first_seen_at`, and
  `verify_drive_sample.py` now samples the universe rather than the
  ledger — its old frame was derived from the tree and so was
  structurally incapable of finding a document that never reached it.

  What is left. **The materialise had never been in the runbook** and now
  is (step 0) — the process half of the same defect. Nothing reconciles
  tree against ledger against Drive at the end of a sync, and that is a
  deliberate omission rather than an oversight: on 08-21 all three
  agreed, so such a check would have passed. The only place this class
  of failure is visible is between the *universe* and the tree, which is
  where the guard now sits. And the first real run of the new guards
  will fail until the corpus stops moving — the refetch pass has already
  added documents and changed document kinds since the tree was built,
  which is the guards working, not crying wolf.
  `data/exports/drive_staging.pre-clean` is the primary evidence and
  stays until this closes.

- **`build_drive_staging.py` now removes what has left a site.** Closed
  2026-08-26 as part of the above. It was additive: after a re-partition
  the old site folder kept the application directories that had moved
  away, so the same document existed under two site folders and
  `drive_sync.py` could not read the move as a move, because it only
  recognises one when the old path has gone. Found 2026-08-25 when the
  Interxion folder held 45 application directories for a site with 16.
  The tree is now written to a `.building` sibling and swapped in, so the
  clean rebuild is what the script does rather than something you had to
  know to do by hand; measured at 65 seconds for 494 sites and 52,000
  documents, and free on disk because the documents are hard links into
  `data/raw`. The tree root is deliberately still additive — a published
  workbook or database from an earlier phase is carried across the swap,
  because a citation of it has to keep resolving, which is the same rule
  `drive_sync.py --prune` already follows.

- **The pre-build tail assertion is built** (2026-08-27, HISTORY):
  every export prints the count of power-unit findings with no verdict
  from any model, beside the corrections gate. Report-only by design,
  and empty at the 2.9 build.
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

**Built 2026-08-26.** The original four items — name the SPVs, pull
their filings, load what they say as claims never columns, report the
disagreements — are done; what they produced and overturned (the
103.3-against-140 gap that was two quantities in one table, the SPV
that states no capacity across 25 pages, the charges register that had
to be probed because `has_charges` read false for 44 of 49 charged
companies) is recorded in EXTERNAL_DATA_SOURCES §6, with the mappings
in `companies-house-spvs.yaml` and `companies-house-ownership.yaml`.

Still open, and now better specified:

5. **Sites 59 and 5 still block the Premier Park and DataVita
   matches.** Premier Park's £147.8m and the DataVita figures stay
   under `considered:` in `companies-house-claims.yaml` because their
   site records are over-merged clusters (and DataVita's needs a
   person to establish which building the figure describes). Union
   Park's four claims were unblocked by the site 61 split and matched
   on 2026-08-27.
6. **Eleven names could not be resolved to a company**, listed under
   `unresolved:` in `companies-house-spvs.yaml` — including "Avalon DC
   Limited" and "BGO Code Propco Limited", both of which are somebody's
   applicant of record and neither of which exists on the register.
   Worth a person's eye rather than another search.
7. **Confirm the proposed alias-group members.** The sweep resolved
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

- **Pinpoint and Giant are missing content by construction, not only by
  age.** Both take the same input, and it is **not** the Drive `sites`
  folder: it is the derivative bundle from
  `scripts/export_pinpoint_bundle.py` (Luke, 2026-08-28). Pinpoint has
  no folders — the namespace is flat and zipped uploads are unsupported
  — so structure is discarded by design and each filename carries
  `<site> — <application> — ` in front of it instead. Neither repository
  cares about that. Both care about **completeness**, and the bundle is
  a reduction: 130.6GB in 50,615 files down to ~64GB in 42,647, under
  Pinpoint's 100GB-per-user quota.

  **The drawings are dropped deliberately, and for Giant too** — 5,536
  files, 9.5GB, on the grounds that they carry no extractable prose.
  That looks at first like a contradiction with
  `extract_text_corpus.py`, which extracts every drawing precisely
  because "a proposed site plan often labels the energy centre, an
  elevation may annotate a generator enclosure, and plant layouts carry
  specifications that never appear in prose at all". It is not.

  The two tools want different things. Giant's value is returning a hit
  **in context** — the surrounding text — and taking the reporter to the
  exact place, page 278 of a long document if that is where it is
  (Luke, 2026-08-28). A drawing supports neither: OCR of a plan yields
  scattered label fragments, so even a matching drawing returns a result
  with no readable context and nowhere meaningful to jump to. Extraction
  wants every scrap of text because a figure may appear only there;
  full-text search wants documents that read. Both are right for their
  layer, and the drawing content is not lost to the project — the
  deep-read reads it and its findings surface on the site page.

  **Giant has no quota limit and takes the reduced bundle anyway**,
  Luke's decision, for consistency. Two search tools answering one query
  differently, with nothing on either page to explain the difference,
  would be worse than a single corpus reduced in a documented way — and
  on the drawings the reduction is right for Giant on its own merits.

  The residual worth watching: a reporter using Giant as a completeness
  check can still infer "not in the documents" from a drawing-only
  disclosure that never reaches it. The reader is where that content
  lives, so the two must not be presented as interchangeable.

  The other two reductions look sound and are worth keeping if this is
  revisited: exact duplicates removed by content hash (2,432 files), and
  types sniffed rather than trusted, which recovered ~450 files
  including 237 Outlook messages of kind *Consultee Comment* — tier A,
  the class the methodology says disclosures live in.

  **Staleness sits on top of that.** The last upload was 2026-08-12 and
  4,464 documents have arrived since, with more in 2.10.

  **Giant has no such quota, and takes the reduced bundle anyway** —
  Luke's decision, 2026-08-28, for consistency. It is the right call:
  two search tools answering the same query differently, with nothing on
  either page to explain why, is worse than one corpus that is reduced
  in a documented way. But it means the drawings are absent from Giant
  to match a constraint that does not apply to it, so the drawings
  question is **one decision governing both** and must be revisited for
  both together or not at all.

  **The delta is computable, and does not need guessing.** Luke still
  has the uploaded bundle and its `_manifest.csv` on the previous laptop
  (2026-08-28). That manifest carries one row per bundled file with
  `sha256`, `site`, `application`, `kind`, `tier`, `action` and
  `staging_path` — so:

  - `manifest.sha256` against `documents.content_sha256` gives exactly
    what Pinpoint and Giant hold and, by omission, what they do not;
  - `action` and `kind` separate the deliberate exclusions (drawings,
    hash duplicates) from the genuine gap, so staleness can be measured
    without re-litigating the reductions.

  Get that file off the old laptop before it becomes the thing nobody
  can find — it is the only record of what was uploaded, and the bundle
  it describes is not reproducible from here: the corpus has moved on by
  4,464 documents, so re-running the script now produces a different
  bundle.

  **Explicitly deferred past 2.10 by Luke.** When picked up: compute the
  delta from the manifest, and fold re-upload into the release chain
  rather than leaving it to be remembered.
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
  work does not need re-deriving.** The 26, as probed on that date —
  a host that answers again later is a fix, not a regression, so
  re-probe before acting rather than trusting this list:

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

- **About 37% of the verbatim gate's rejections are correct quotes,
  lost to whitespace artefacts in the extracted text — roughly 17,000
  findings** (measured 2026-08-28 on a random sample of 900 of the
  46,709 `quote_failed_verification*` escalations, every one with
  cached page text). The premise, which the code already half-accepts:
  pypdf splits words at line breaks and around units, so the page text
  says "acro ss the site", "d ata centres", "c ooling", "sust ainable",
  "940 µ g/m 3", "600m 3". A model that quotes the passage correctly
  then fails a gate comparing it against the broken text.
  `verify_findings._PLURAL_SPLIT_RE` already repairs exactly this, but
  only for a trailing `s` after a 4+ letter word — one letter of
  twenty-six — and its own comment names the cases it does not cover
  ("energ y generation", "centr e of").

  Classified against the cached page text, the sample of 900 splits:
  62.7% genuinely absent under any normalisation (the gate working —
  paraphrase or invention), **32.0% present if whitespace is ignored
  entirely**, 5.1% present after generalising the single-letter split
  repair, 0.1% on a page that was never sent. Median rejected-quote
  length in the recoverable class is 120 characters, so these are not
  short fragments matching by accident.

  Two reasons this is worth doing before more reading is bought.
  First, the loss is silent: a rejected finding is counted as a failed
  gate, which reads as the model behaving badly rather than as
  evidence discarded. Second, **recovery is free** — the escalation
  log carries the whole finding payload beside its sha and page, so
  the rejected quotes can be re-gated offline and reinstated without
  re-spending a penny of API budget. The fix is a whitespace-
  insensitive containment test with a minimum-length guard (the gate
  is hallucination protection and must not become a substring lottery
  for three-character quotes), plus generalising the split repair
  beyond `s`.

  **Scheduled as the key part of 2.11** (Luke, 2026-08-28). It is the
  largest single quality gain available and it costs no API spend: the
  escalation log carries the whole finding beside its sha and page, so
  the rejected quotes are re-gated offline and reinstated. Do the
  re-gate and the gate fix together — a fixed gate without a re-gate
  leaves the 17,000 discarded, and a re-gate without the fix means
  doing it again next release.

  **Not** an explanation of the PARSE FAIL energy-report gap recorded
  elsewhere: `read_state = 'parse_failed'` means the model's JSON
  response was truncated and salvaged, which is unrelated to how the
  PDF extracted. Whether the whitespace-artefact rate also differs by
  document class is a separate, unmeasured question.

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
3. **Section 35 Directions / NSIP discovery.** The energy layer is
   ingested, but a data centre attaching itself to an NSIP power project
   is still invisible on both sides of the join. Xlinks'
   Morocco–UK interconnector lands at Alverdiscott, which is plausibly
   *why* a data campus is proposed there. An NSIP spans hundreds of
   kilometres and many authorities, which the 1 km clustering rule
   handles badly — it wants its own node type and evidence-based rather
   than proximity-based association.

`adjacent_power` holds only ~15 applications universe-wide, which is
implausibly few and consistent with power schemes near campuses being
absent from the corpus rather than misclassified.

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

Three pieces of work, smallest first:

1. **Guard at fetch — DONE.** `repo.record_document` refuses the empty
   hash and every adapter checks the body before writing; both halves
   are pinned by `tests/test_zero_byte_guard.py`.
2. **Sweep the corpus — re-run 2026-08-27: still exactly the three.**
   `find -size -1c` over `data/raw/documents` is the whole check
   (three empty Companies House OCR page files also surface — blank
   pages, a different and benign thing). Nothing runs it on a
   schedule; a durable home — corpus_stats, or a test over the store —
   is still wanted so a fourth would announce itself.
3. **Say so in the artefacts — still open.** Where a document is held
   but empty, the site report and the coverage detail should show it
   as unavailable from the source rather than as read — the same
   honesty the coverage split already applies to drawings and sampled
   objection letters.

Worth raising with the three councils as well: a listed document that
downloads as nothing is a public-access failure independent of this
investigation.

## From the reader redesign — for the adjudication corrections

Found 2026-08-23 while reviewing the reader redesign
(docs/READER_REDESIGN_PLAN.md §4.1d); the correction belongs in
`scripts/correct_adjudications.py` as a named rule, so it is recorded
here rather than applied from the build lane.

- **The export-limit rule is built and applied** (2026-08-27,
  HISTORY): 23 rows demoted, value-adjacency not vocabulary, one
  pinned instance. What remains is a person's row: **Kingsnorth's
  47,405 kW figures** — the same value at leading and lagging power
  factor in one connection table, against the offer letter's 5,000 kVA
  import — now stand as that site's largest grid figure, and no
  predicate can say which direction the site's connection is. Settle
  it by hand, then re-check the Operators tab's like-for-like, which
  still quotes the register-vs-planning comparison this family fed.
## From the reader redesign — waiting on a checkpoint

2.4 work whose next step is a person's, recorded here so the build lane
does not have to remember it. (The generation batch that sat here has
run — 1,667 figures under `gpt-5/generation-2.5`, migration 024 applied,
and the workbook columns and cohorts that consume it are in 2.7. See
HISTORY.)

- **Confirming the rest of the alias groups.** Eight of the ten seeded
  members are confirmed and one is still `proposed`, which is enough for
  `operator_group` to reach **15 sites** — Vantage, Colt, Amazon,
  Microsoft. It is not enough to be a filter anyone would trust: 305
  sites appear in `parties` and 290 of them still fall back to Barbour's
  end user or client. Confirming a group is what makes "Ark Estates 5
  Ltd" and "Ark Data Centres Ltd" one name, and what lets an
  organisation named only in a document reach the operator field at all.
  The site 61 split (HISTORY, 2026-08-27) shows what a confirmed group
  is worth: applicant of record separated ten campuses cleanly where
  coordinates could not.

## Smaller things

- **The search bundles could be uploaded to Drive by the pipeline, and
  the `drive.file` scope is not the obstacle it looks like.** Today step
  13a leaves `notebook_bundle/` and `pinpoint_bundle/upload/tranche_N/`
  sitting locally, and Luke moves them to Drive by hand before pushing
  them out to Notebook, Pinpoint and Giant. He has been comfortable
  doing that because the sync can only see folders it created — which is
  true, and is not the whole picture.

  **Measured 2026-08-29, because the assumption was worth testing rather
  than inheriting.** Handing the token a folder ID does *not* make the
  folder visible: `files.get` on the notebook bundle folder, the pinpoint
  bundle folder and even `dcp/drive.py`'s own `FOLDER_ID` all return
  **404 — not created by this app**. An ID is not a key.

  **But writing into an invisible folder by ID works, and the archive is
  the proof.** `SITES_FOLDER_ID` is visible, `ownedByMe`, created
  2026-08-07 — and its `parents` is exactly the handover root that
  answers 404. The sync created a folder inside a folder it cannot see.
  So `drive.file` blocks *listing and reading*, not *writing to a known
  parent*, and this can be built without widening the scope.

  **Which is the point: do not widen the scope.** It was chosen
  deliberately (`scripts/drive_sync.py`, "this tool can create and
  manage only the files and folders it itself uploads"), and the
  alternative hands a document-mover visibility of the whole of Luke's
  Drive — personal and Guardian alike — to solve a file-copying problem.
  A capability that broad is not worth an ergonomic gain this small.

  **Writing blind is avoidable, and the shape that avoids it is Luke's
  (2026-08-29): never write into a folder we did not create — always
  create a fresh per-release child.** Both bundles already work that
  way, for reasons that have nothing to do with Drive.

  - **Pinpoint and Giant grow by tranche.** Each release adds
    `tranche_N`, never revisiting an earlier one. If the pipeline
    *creates* that folder inside the bundle parent, it owns it: listable,
    `md5Checksum` available, complete knowledge of its own additions.
    The parent stays invisible and never needs reading, because tranches
    are append-only by construction.
  - **The notebook is replaced wholesale, not updated.** Re-tuning
    `--max-words` moves every part boundary, so a re-fit is a new set of
    files and a new notebook rather than an edit. Luke is therefore
    naming the Drive parent after the release — `notebook_bundle_2.10`,
    renamed by hand on 2026-08-29 — so each future release creates its
    own top-level folder and has total visibility of the whole tree,
    not merely of a child.

  So the trio of costs that writing blind would impose — a ledger as the
  sole record, idempotency without `md5Checksum`, no post-hoc
  verification — **does not arise** under this shape. It would only
  arise if we wrote into a folder somebody else made.

  **Which makes the real hazard a name collision, not blindness.**
  `Sync.folder(name, parent)` resolves by name: it queries for a folder
  of that name under that parent and creates one if the query comes back
  empty. Under `drive.file` that query can only ever see folders the app
  itself created, so it is structurally incapable of finding one made or
  renamed by hand — it will quietly create a second folder beside it,
  and Drive permits duplicate names, so nothing complains. That is the
  duplicate-archive mechanism, still live.

  **So the convention only holds while the pipeline is the sole creator
  of release folders.** Pre-creating one by hand and expecting the
  pipeline to fill it is the failure case. Guard it rather than
  documenting it: after `folder()` creates one, `files.get` the id back
  and stop if it 404s.

  **Where the IDs go.** Any destination the pipeline does *not* create —
  the pinpoint bundle parent — belongs in `dcp/drive.py` as a named
  constant beside `FOLDER_ID` and `SITES_FOLDER_ID`, never resolved by
  name, never retyped, per that module's opening warning. Folders the
  pipeline creates need no constant: it learns their ids on creation.
  Renaming is safe either way, since an id survives a rename — which is
  the whole reason the ID-only rule exists.

  **One step stays manual whatever happens**: a notebook that already
  holds a previous release must be emptied first, because uploading adds
  sources rather than replacing them — and on the per-release naming
  above the answer is usually a new notebook instead, whose URL must
  reach `NOTEBOOK_URL` before step 12, as the runbook already requires.

  Raised by Luke 2026-08-29 — "perhaps we should streamline that process
  eventually" — and narrowed by him the same day to the per-release
  folder shape above.

- **The Start Here page's Gemini Notebook card claims more than the
  notebook holds.** The card says "Every site's report and its full
  findings table, one document per site". Since PR #230 that is not
  true: `export_notebook_bundle.py` exports only sites classed
  `datacentre`, 428 of the 512 in the staging tree. Left out are 48
  disguise suspects, 23 procedural-only sites, 9 adjacent-power sites
  and 4 with no planning record.

  **The premise, stated because the card is asserting it either way.**
  The filter is not an editorial judgement about what is worth reading;
  it is what pays for a smaller per-document word budget. Gemini
  Notebook takes 600 sources and rejects sources that are too large, and
  at 2.10's size those two limits could not both be met with every site
  in. The measured cost of *not* filtering is one step of budget —
  450,000 words a document rather than 300,000 — because the 84
  excluded sites are only 4.9% of the words.

  **Why it needs saying on the card rather than in the methodology.**
  The absent class that matters is the disguise suspects, whose own
  description is "no application here is stated as a datacentre, and at
  least one could not be ruled out — kept for exactly that reason". A
  reporter who asks the notebook about large unnamed single-use
  buildings gets nothing back, and nothing reads as *there are none*.
  That is the same failure as a dash in a table: our silence presenting
  as theirs. The card immediately below it makes the gap worse by
  contrast — Pinpoint holds **all** sites' source documents, so the two
  cards now differ in coverage as well as in kind, and the page says
  only the latter.

  **What to change.** In `scripts/export_reader.py`, the Gemini Notebook
  card's `what` paragraph (around line 5832): replace "Every site's
  report" with a statement of the actual scope, and name where the rest
  can be found — the site folders and Pinpoint both hold them. The
  count should be generated, not typed: the reader already computes
  `site_classes` via `sclass.compute_all` and tallies
  `rendered_classes`, so the number of datacentre-classed sites is
  already in hand at build time and will follow the corpus.

  Raised by Luke 2026-08-29, the day the filter landed.

- **`drive_sync.py` is latency-bound, not quota-bound, and the 2.9
  reorganisation paid for it.** There is no deliberate delay in the
  sync — the only sleep is error backoff — but it is a single thread
  paying one HTTPS round-trip per file, ~43 moves/minute against a
  Drive per-user quota near 12,000 requests/minute. The site 61 split
  moved ~5,400 files and took hours that batching (the Drive batch
  endpoint takes 100 calls per request) or modest concurrency would
  cut to minutes. The design constraint to respect: `Sync.state` is a
  plain dict saved per file with no locking, and it is the record that
  makes syncs resumable and moves recognisable — parallelise the API
  calls, not the ledger writes. Found mid-release 2026-08-27 and
  deliberately not patched mid-run.

  **Half closed 2026-08-29.** The concurrency existed all along behind
  `--workers`, defaulting to 1; the default is now 12 (Luke's call,
  after a 58,799-file sync spent 9h16m reaching 54% because nobody
  passed the flag). What remains open is the batching: the Drive batch
  endpoint takes 100 calls per request, which would beat any number of
  threads, and the ledger's own write is still a non-atomic
  `write_text` every 50 changes — worth making atomic before anyone
  relies on killing a sync safely.

- **Readings are now checked for freshness, but not at render time —
  the exact check costs more than a build (done 2026-08-27).**
  `mreading.load_latest` returned the newest stored reading per site
  key with no check that the site's input still matched; the
  input-hash discipline existed only at generation. Measured on the
  day: **4 of 258 rendered readings were already stale**, one of them
  keyed to a site retired by that morning's merges.

  Rebuilding one site's input to re-hash it costs **8.2 seconds** —
  `select_pages` reads and scores every cached page — so verifying 258
  readings would add about **35 minutes** to a build that takes ten.
  Nothing cheaper is sound, either: `documents_read` and `pages_read`
  are the only stored numbers that could be compared, and recomputing
  *them* also needs `select_pages`. So the check is split by what each
  half costs.

  **Cheap half, every build.** `load_latest(live_only=True)` drops a
  reading whose site key is no longer live — free, exact, and the case
  that matters most, since the reading describes a record a reporter
  cannot open.

  **Exact half, offline.** `scripts/verify_reading_freshness.py`
  rebuilds every input, compares the hash, and records the verdict
  append-only: a site whose input has moved gets a *new* row carrying
  the current hash, no reading, and a withheld reason, so the reader
  shows the panel as withheld by the path a gate refusal already
  takes. The marker is written under the model tag `freshness-check`
  so it can never occupy the unique key a genuine reading of that same
  input would need. Re-runs are no-ops.

  What remains: deciding where the offline check belongs in the
  release chain — it is not yet in the runbook, because 35 minutes is
  a real cost and whether it runs per release or per batch is an
  editorial call, not a build one.

- **`test_two_builds_of_one_snapshot_are_identical` failed once and has
  not since.** Seen 2026-08-26 during a full-suite run, immediately
  after the Drive-id work; the failure was the two-builds comparison,
  not the snapshot assertion above it. Nine subsequent runs — three
  full-suite, six of the test alone — all passed, so the detail of
  *which* lines differed was never captured, and that is the thing to
  fix first: the failure message names the first differing line, but
  only in the run that fails.

  Not dismissed as noise. A build that is deterministic 90% of the time
  is a build whose diff against the previous release cannot be trusted,
  and that diff is the check standing between a regression and a
  published one.

  **Both original candidates are now largely eliminated, and a third
  found (2026-08-27).** The `DISTINCT ON (document_id) … ORDER BY
  document_id, recorded_at DESC, id DESC` in `_drive_document_map` is
  deterministic on inspection. Set-ordering can be ruled out by
  argument rather than inspection: the two builds are separate
  processes with independent `PYTHONHASHSEED`, so anything depending on
  set iteration order would fail nearly every run rather than one in
  ten — and the one set-iteration that reaches an exporter
  (`site_profile` building `out` from `set(barbour) | set(counts) |
  set(authority)`) has a single consumer, which sorts.

  The likelier cause is that **the snapshot pins the database but the
  reader also reads a file**. `_drive_folder_map`,
  `_drive_application_map` and `_drive_findings_map` all read
  `data/exports/.drive_sync_state.json`, and every Drive link in the
  page comes from it; `drive_sync` rewrites that ledger once per file
  while it runs, and `DCP_PG_SNAPSHOT` cannot pin a file on disk. Two
  builds either side of a sync read different inputs. That fits the one
  observed failure, which arrived immediately after the Drive-id work.

  The test now measures rather than assumes: it fingerprints the ledger
  by content before and after both builds and voids the comparison with
  a reason if it moved, the same discipline the database fingerprint
  already applies — and where it did not move, the failure message says
  so, so the ledger cannot be blamed for a difference it did not cause.
  Both builds, both normalised texts and a capped unified diff are kept
  in `data/exports/determinism_failure/` on any failure, so one
  reproduction is enough. What remains is to see a failure with the
  ledger held: if one comes, the evidence will be on disk.

- **Every OpenAI finding was missing its family, and two panels select on
  nothing else.** Found 2026-08-26. The INSERT in
  `scripts/deepread_escalate_openai.py` omitted `signal_family` and
  `family_source` from its column list, so all **557,747** findings from
  the three OpenAI runs carried `signal_family` NULL — 46% of the corpus.
  `claude-sonnet-5` had 0 NULL of 346,647, which is why nothing looked
  wrong. `site_profile.EIA_TEXTS_SQL` (`signal_family = 'eia_process'`)
  and `PARTIES_SQL` (`signal_family LIKE 'party_%'`) filter on that
  column alone, and NULL matches neither — silently — so no OpenAI
  finding had ever reached either panel. The water/cooling query has an
  `OR value_text ~*` arm and was only partly affected. Fixed at source
  and backfilled the same day (`scripts/backfill_signal_family.py`,
  derived from `signal_type`, `family_source = 'derived'`, originals
  untouched). The EIA-process panel went **190 → 234 sites**, parties
  **296 → 304 sites** and 97,088 → 202,223 rows.

  The two things left after that were both done on 2026-08-26:

  - **The 49,039 local-model findings from 2026-08-07/09 are
    backfilled.** NULL for a different reason — written before migration
    009 added the column — and cured by the same command,
    `--model-like 'mlx:%'`. 3.9% landed in `unclassified`. No finding in
    the corpus now carries a NULL `signal_family`, on any model.
  - **`\b` cannot end a snake_case token, and the family patterns were
    full of it.** `_` is a word character, so `eia\b` never matched
    `eia_status` and the family `eia_process` did not classify as
    `eia_process`. Corrected for `eia`, `suds`, `chp`, `ups`, `hvo`,
    `dno`, `kv`, `mva`, `pue`, `mw`, `crac`, `crah`, `sac`, `spa`,
    `bng`, `scr`, `cemp`, `lpa`, `gia` and `gea` by writing the boundary
    over the characters a label token is actually made of
    (`signal_families.TOK_END` / `TOK_START`) — a change to how a token
    is delimited, not to which tokens a family claims. The derivation
    was then re-run over the rows it had left `unclassified`, under a
    new `--rederive-unclassified` scoped to `family_source = 'derived'`
    so that a model's own answer can never be overruled by a regex.
    **13,991 rows left `unclassified`**: +5,292 `eia_process`, +3,845
    `flood_drainage`, +1,466 `power_generation`, +1,023 `power_demand`,
    +997 `ecology_biodiversity`, +546 `party_authority`. In the
    artefacts, the EIA panel went **234 → 239 sites** and the parties
    panel **202,223 → 209,875 rows** (304 sites, unchanged). The rule is
    asserted over the whole vocabulary in `tests/test_signal_families.py`
    — including that the boundary was corrected rather than deleted,
    which is the easier and more damaging repair.

  Four editorial questions came out of the measurement. All are left for
  the data and visuals teams, because each changes what a family means
  rather than how a token is delimited:

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

- **The sites table's sort glyph wraps onto a line of its own.** The
  ↕ every sortable header carries is a `th:after` pseudo-element, so it
  sits after the heading text and the `?` dictionary link — but the
  per-column `min-width`s in the sites-table CSS were sized to the
  heading text without it. On the headers that already wrap,
  "Who's behind it" and "External power indicators", the glyph lands on
  a line by itself under the heading instead of beside it. Account for
  the glyph when sizing the columns, or bind it to the heading's last
  word so it can never break alone.

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
- **Improve the automated test surface.** The suite is good at internal
  consistency and blind to two things, and almost every defect found on
  2026-08-11 sat in one of the gaps. Worth doing properly rather than
  adding a test per bug — the recurring shape of these is *fixed the
  symptom, missed the cause*.

  **Nothing drives the built artefact.** The reader's card links did
  nothing in a shipped release; a chip took its own flex column and
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

  **A build is not yet asserted to be a function of its inputs.** Two
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
  - **It gets safer once EdgeOne retires.** Today merging *is*
    publishing, because EdgeOne builds from git. After PR #135 and the
    deployment's deletion, a merge is only a commit and the single
    route to readers is the approved click. `index.html` can then live
    in the repo like any other file rather than staying uncommitted in
    order to stay unpublished — which is how a `reset --hard` silently
    discarded a built payload on 2026-08-26.
  - **The probe must fail the job.** `deploy.sh` already exits non-zero
    when the live service answers anonymously, so this costs nothing.
- **Four sites report a total site demand below their IT load.** All four
  are correct — the figures come from different applications at
  multi-building sites, and each figure names its source application in
  the reader. Worth adjudicating by hand rather than changing the
  rollup rule.

- **A story lead the corpus can already evidence: who qualifies their
  "100% renewable" claim, and who does not** (Luke's idea, measured
  2026-08-28). Eight operators in the snapshot store make a green
  claim — "Powered by 100% renewable resources", "100% renewable
  energy powered", net-zero commitments. Five of them also hold
  Environment Agency permits for standby combustion, and the
  difference between them is in the wording:

    operator   permits   MWth   engines   claim names its generators?
    VIRTUS           4   832.5      121   no
    Ark              3   476.1      114   yes — "supported by HVO"
    Vantage          1   225.7       37   no
    CyrusOne         1   201.3       32   no
    Kao              1   152.3       25   yes — HVO named
    Apatura, Greystoke, Pulsant: green claim, no permit found

  **Ark and Kao name their standby fuel beside the green claim;
  VIRTUS, Vantage and CyrusOne make an unqualified claim while holding
  permits for 1,259 MWth across 190 engines.**

  **A permit is only required at 50 MWth and above, which limits what
  the bottom three rows can mean** (Luke, 2026-08-28; confirmed in the
  permit data). The permitted activity is written in the permits
  themselves as "Combustion; Any Fuel =>50MW - 1.1 A(1) a)", with two
  entries reading "Medium Combustion Plant collectively =>50MW" —
  individually small engines that aggregate past the threshold. Below
  it a site falls to the MCP regime: registration rather than a
  bespoke permit, lighter touch, and possibly not published at all
  (see the Environment Agency item above). So **no permit found is not
  no generators** — it may only mean the installation is under 50
  MWth. Pulsant is the clearest case: its whole disclosed estate is
  22.12 MW of IT load, which would not reach the threshold however it
  is aggregated. The table's bottom three rows are therefore not
  evidence of a cleaner operator, and must never be read as such.

  Five caveats belong with it, and without them this is a cheap
  gotcha rather than a finding. "100% renewable" conventionally
  describes *procured grid electricity*, so an unqualified claim is
  not false — the question is what it omits. Standby plant runs for
  testing and outages, so its output is small against a site's grid
  draw; the point is disclosure, not equivalence. Permit MWth is
  thermal input capacity, not emissions. And the snapshot store is
  curated, so an operator absent from the table may simply have no
  page snapshotted — absence here is not absence of a claim.

  **The run-hour limit is in the permits, and it is 500 hours a year**
  (read 2026-08-28 from the 85 permit PDFs the project holds; 42
  permit stems carry the condition). The standard wording is "The
  activities shall not operate for more than 500 hours in emergency
  use per annum", and the Environment Agency spells out that this is
  an installation-level cap, not a per-engine one: "500 hours is for
  the installation as a whole, meaning that as soon as one generator
  starts operating the hours count towards the 500 hours". So the
  honest sentence is *"permitted to run for up to 500 hours a year"*
  per site — never engines multiplied by hours, which the permits
  explicitly forbid as a reading.

  And the number is not arbitrary. The same documents state that
  "Emission limit values (ELVs) to air are not applicable to MCPs
  operating less than 500 hours per year" — the cap sits exactly at
  the threshold below which air-emission limits do not bite. That is
  the sharper story than the green claims themselves: an operator can
  hold hundreds of megawatts of standby diesel and stay outside the
  emission-limit regime by staying under 500 hours, and the permit
  is written to that line.

  **Below the threshold, the planning documents catch what the permits
  cannot** (Luke, 2026-08-28). Sites matched to a green-claiming
  operator can be searched for their own disclosures of on-site fossil
  generation, and that reaches the operators with no permit at all:
  Greystoke's West London Technology Park carries 379 findings
  mentioning diesel and 156 gas, and its documents say so plainly —
  "given the significant number of diesel back-up generators, and the
  lifetime associated with the operation of the proposed development
  (i.e. 30 years)". Abbots Langley and one other Greystoke site carry
  the same pattern at smaller scale.

  **The direction of the mention decides its meaning, so the counts are
  a route to evidence and never the evidence.** Apatura's Westerhill
  shows why: its ten diesel findings are proposals to *avoid* diesel —
  "The BESS would reduce (or ideally) eliminate the practical need for
  the data centre to utilise and rely upon diesel backup generators."
  A count that treated those as disclosure of diesel reliance would
  have the story backwards. Ark's sites, which do hold permits, carry
  heavy HVO mentions alongside the diesel, consistent with the
  qualified claim its website makes.

  Two next steps, one of them now drafted. **The actual run hours are
  obtainable**: 29 permits' decision documents state that "Reporting of
  standby generator maintenance run hours is required annually and any
  electrical outages (planned or grid failures regardless of duration)
  require both annual reporting and immediate notification of the
  Environment Agency", and permit conditions require the operator to
  record "the type and quantity of fuel used and the total annual
  operating hours for each MCP" and "the number of runs for each of the
  generators". The Agency therefore holds the returns, and an EIR
  request for them is drafted at
  `docs/requests/2026-08_ea_standby_generator_run_hours_eir.md` —
  including the reg 12(9) point that information on emissions cannot be
  withheld as commercially confidential, which matters because the
  decision document for EPR/QP3434DR records the Agency accepting a
  confidentiality claim and excluding "financial and operational data"
  from the public register.

- **A public document class the project does not yet harvest:
  Environment Agency Compliance Assessment Reports** (found 2026-08-28
  when Luke asked whether run hours were already published — they are
  not, but this is). Public Registers Online has published CARs for
  **Installations since 18 August 2025**, free to download at a
  predictable path
  (`/public-register/documents/installations/compliance/EPR_<STEM>/…`),
  and they record what an Environment Agency officer found on site.
  The CAR for EPR/QP3434DR — Brick Lane Data Centre, Interxion Carrier
  Hotel Limited, inspected 28/10/2025 — states that "Emergency
  operation of the standby generators and operation for testing/
  maintenance was discussed", and that "during the … UPS replacement
  from 30 September to 3 October 2025, operation of three standby
  generators was required", with a noise complaint following.

  That is *actual* generator operation, dated, from a public source —
  the thing the corpus has never held. Coverage is thin and growing:
  the scheme is weeks old, several data-centre permits still show "No
  document published" against Compliance, and CARs are inspection
  reports rather than annual returns, so they corroborate the EIR
  above rather than replace it. Worth an adapter on the same pattern
  as `fetch_ea_permits.py`, and worth re-running periodically as the
  register fills. Second: read the generation
  findings at the no-permit sites rather than counting them, which is
  what turns Greystoke's 379 mentions into a number of generators.

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
  to spatial chance. Sites 5, 23, 59 and 11 are what remain, and the
  permits carry their evidence.

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
  [docs/requests/](requests/) (2026-08-27): the CCA site-level
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
- **A fourth operator tranche would be cheap.** Add URLs to `PAGES` in
  `scripts/fetch_operator_snapshots.py`, run it, add curated claims with
  verbatim quotes. Colt is no longer blocked: Tudor Works and Hayes
  Bridge Retail Park are their own sites as of 2026-08-27 and the
  London 4 claim is matched, so a Colt snapshot tranche (London 5–8)
  now has records to land on.
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
