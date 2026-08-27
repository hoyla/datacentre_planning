# Roadmap

What is still to do. Everything already built and decided — including
the approaches tried and rejected, which are worth knowing before
re-proposing them — is in [HISTORY.md](HISTORY.md).

Current state: **494 sites** (plus 25 pre-planning), **2,034
applications** in the site universe, **56,860 documents**. Findings and
adjudication counts move while the corroboration pass runs and are
deliberately not restated here — `scripts/corpus_stats.py` prints them,
and each release states the boundary it was stamped at.

**2.8 shipped on 2026-08-26** and reaches readers at the Cloud Run
deployment behind Guardian sign-in, which changes only when
`cloudrun/deploy.sh` is run. EdgeOne, which builds from git, is a
signpost rather than a surface: PR #135 merged on 2026-08-27, so it
redirects and the shared password is retired. What 2.8 contains is in
HISTORY. No release is in flight.

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

- **The 31 browser-routed applications.** The largest and cheapest bloc
  of the acquisition tail, using tooling that already works: 15 behind
  AWS WAF (the Coventry signature), 8 on LPAssure serving
  `UnsupportedWebBrowser`, 8 Salesforce needing a harvested document
  listing. Needs a human at the keyboard, so it is scheduled rather than
  queued. See the acquisition tail below for the rest of that class.

- **`relist_refetch.py` now has a per-application deadline**
  (2026-08-27). Not `fetch_outstanding.py`'s SIGALRM — that only works
  in the main thread and the refetch runs worker shards — but a
  `threading.Timer` that closes the shard's clients at the ceiling
  (900s, the same default), so the stalled read that sat twenty
  minutes on an open idle connection on 2026-08-26 raises into the
  error path instead. A timed-out application is recorded as a
  retryable `error`, never settled, and the next application builds
  fresh clients. Resuming the outstanding tranches
  (`--tranche rest`, then `--tranche glasgow`) can now be left
  unattended.

## Phase 2 — the tail of the collecting

- **The acquisition tail.** 108 applications are being worked now. Of
  those recorded unreadable, a host-by-host probe found **20 reachable
  without a browser, across eleven unrelated bespoke portals** — roughly
  one adapter per two applications, which is poor value. The larger and
  cheaper bloc is **31 that route through the browser**, using tooling
  that already works: 15 behind AWS WAF (the Coventry signature), 8 on
  LPAssure serving `UnsupportedWebBrowser`, 8 Salesforce needing a
  harvested document listing. Needs a human at the keyboard.
  Genuinely hard: 5 behind CAPTCHA, 7 refusing with 403/500/503
  regardless of user-agent, 1 Incapsula.
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
- **The site 61 split is materialised and its claims are re-matched.**
  Ten partitions (2026-08-27, HISTORY has the account) plus a follow-up
  the first materialise exposed: four Ealing out-of-borough
  consultations with no coordinates sat as unlocatable singleton sites
  (213–215 for Tudor Works — the "three separate site records" that
  blocked the Colt claim — and 405 for Nestlé), dissolved into their
  campuses via coordinate priors. 499 live sites. Six claim matches
  loaded the same day: Ark's 99 MW re-matched to site 61 (its
  2026-08-21 retirement entry records the release condition it met),
  the four Union Park SPV figures (24 built / 48 under construction /
  24 subject-to-planning / £839.79m), and Colt London 4's 31 MW to
  site 75. What is left: the next artefact build and Drive staging
  rebuild pick all of this up through the normal runbook order —
  seven new site folders, members leaving the Union Park folder,
  nothing bespoke.

- **A site's display name is the address of whichever application sorts
  first**, which bears no relation to what anyone calls the place. The
  Wapseys case is fixed by accident rather than design — the key
  dissolved into `PTNO-12913776`, "SDC M40 CAMPUS - 300MW DATA CENTRE
  CAMPUS" — but the defect stands and has now bitten twice more: West
  Burton Power Station renders as "Land East Of Gainsborough Road
  Bole", and the Blyth offshore-wind site as "Land North Of Blyth
  Powerstation Cambois". A site nobody can find by its own name is a
  site a reporter concludes is missing, which is exactly what happened
  when the Guardian asked about Wapseys Wood.

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

- **Nothing checks for figures that were never adjudicated.** The
  corrections gate examines adjudications that exist and cannot see a
  figure nobody has asked about; `sweep_null_capacity.py` only reports
  sites with no capacity at all. 2.7 came within one runbook step of
  shipping 4,117 unadjudicated figures from the corroboration read. A
  cheap pre-build assertion — "the adjudication tail is empty, or say
  how large it is" — belongs in `dcp/adjudication_gate.py` beside the
  corrections check.

  **The number to assert on is 299, and "15,220" is the wrong one.**
  Both were measured on 2026-08-26 and they answer different questions.
  `adjudicate_power.load_candidates` excludes only what
  `claude-sonnet-5`/`power-1.0` has already done, because that script
  *is* the Sonnet route and the exclusion is its resume contract —
  "what have I not done", not "what has nobody done". Read as a measure
  of corpus completeness it is misleading by fifty times:

  | | |
  |---|---|
  | power-unit findings in the corpus | 19,194 |
  | with no adjudication from **claude-sonnet-5** | 15,220 |
  | with no adjudication from **any model** | **299** |

  Adjudications on record: `openai:gpt-5:medium` 11,870,
  `claude-sonnet-5` 3,974, `openai:gpt-5:high` 1,937,
  `claude-sonnet-5+subagent` 1,114. The corpus is adjudicated; it is
  mostly adjudicated by a model other than the one whose resume query
  gets quoted. A pre-build assertion must count rows with no verdict
  from **any** model, or it will report a five-figure backlog before
  every release and be ignored within two.

  Of the real 299: 205 sit on sites that already carry an adjudicated
  capacity (the cheap OpenAI batch route, measured at $0.05 input and
  $3.25 worst case), and 61 are consequential — on sites with no
  capacity at all, where a verdict moves a headline rather than
  refining it, which is the subagent route's stated scope. Not every
  row is a site capacity waiting to be claimed: several are plainly
  not-this-site, such as an operator describing "over two gigawatts of
  critical power capacity under customer contract in Europe and North
  America". That is why the assertion should report the size rather
  than demand a zero.

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

**Built 2026-08-26.** Items 1–4 below are done; what they produced, and
what they overturned, is recorded in EXTERNAL_DATA_SOURCES §6 and in
`data/external_sources/companies-house-spvs.yaml` (which company is
which scheme) and `companies-house-ownership.yaml` (who lends and who
owns). Migration 030 added `scheme_capacity` and
`investment_property_fair_value`, and `scripts/load_capacity_claims.py`
runs again — it had been rolling back **every batch from every source**,
not just this one. Three results worth carrying forward:

- **The 103.3-against-140 gap was not a gap.** Site 81's own
  environmental statement states "Total IT Load - 103.32 MW" and "Total
  Data Centre Load – 139.5 MW" in one table on page 10, and a reserved
  140 MW grid connection on page 27. The accounts quote the IT load. The
  rule survives in a sharper form: never compare an external megawatt to
  a planning megawatt without first establishing that they measure the
  same thing — here that took one join and overturned the headline.
- **A single-asset SPV does not always name a capacity.** Segro Pure
  Premier Park Data Centre Limited is the same shape as Court Lane and
  states none across 25 pages. Of 52 filers whose accounts category
  could carry an investment-property note, ten mention megawatts at all
  and four said something new.
- **The ownership half is the durable half.** The charges register had
  to be *probed* rather than inferred from the profile's `has_charges`
  flag, which read false for 44 of the 49 companies that carry charges.

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

The original four, for the record:

1. **Name the SPVs we already hold.** Barbour's client-of-record slot is
   full of them — `UK Court Lane DC Limited`, `VDC LHR11 Limited` — and
   `data/priors/organisation_aliases.yaml` is already the place a person
   records what a name turned out to be. A list of scheme SPVs with
   company numbers is the input to everything below and costs a query
   plus a person's judgement.
2. **Pull their filing history** (`CH_API_KEY` is in `.env`; the sweep
   is small — tens of companies, not thousands). Accounts for the
   capacity assumption and the going-concern position; the charges
   register for who lends, which is the most honest statement of who
   owns; the confirmation statement for shareholders.
3. **Load what they say as claims, never as columns.** The precedent is
   settled (§7.1): an external figure goes in beside the planning data
   with its own quantity type and its provenance, never into a site
   column that implies it measures the same thing. `scheme_capacity` is
   a new type and needs one — and **the two claims are already in the
   YAML without it**, which is what has been breaking
   `scripts/load_capacity_claims.py` outright since the SPV work. See
   the Phase 2 item above; that migration unblocks every source, not
   just this one.
4. **Report the disagreements.** Where an SPV's audited assumption
   differs from the planning record or from Barbour — 103.3 against 140
   here — that gap is a finding, and averaging or preferring one silently
   would destroy it.

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

1. **Guard at fetch.** A zero-length body is a failed fetch, not a
   document: record the failure against the application and leave no
   file, so a re-run retries rather than treating emptiness as done.
2. **Sweep the corpus.** `find -size -1c` over the canonical store is the
   whole check. Three today; nothing would flag a fourth.
3. **Say so in the artefacts.** Where a document is held but empty, the
   site report and the coverage detail should show it as unavailable
   from the source rather than as read — the same honesty the coverage
   split already applies to drawings and sampled objection letters.

Worth raising with the three councils as well: a listed document that
downloads as nothing is a public-access failure independent of this
investigation.

## From the reader redesign — for the adjudication corrections

Found 2026-08-23 while reviewing the reader redesign
(docs/READER_REDESIGN_PLAN.md §4.1d); the correction belongs in
`scripts/correct_adjudications.py` as a named rule, so it is recorded
here rather than applied from the build lane.

- **Export limits stored as grid connections.** Of 810 `grid_connection`
  rows adjudicated `site_capacity`, 16 across 4 sites quote an *export*
  figure. Kingsnorth (`SITE-Medway/MC/21/0979`) is the one that reached a
  headline: "Maximum MW export = 49.9 MW (at unity power factor)" is the
  49.9 MW energy-from-waste hub's export, and the same offer letter gives
  the site "an import capacity of 5,000 kVA". So the 2.2 like-for-like
  "340 MW to the grid operator, 49.9 MW to the planning authority, 6.81×"
  compares export with import, and the planning-side figure to put
  beside the register row is 5 MVA, not 49.9 MW. Also export: Yorkshire
  Energy Park's "permission … to export 21MWe" (`PTNO-12628941`, 21 and
  9 MW rows) and `PTNO-12669230`'s "18 MW of import capacity 10.5MW of
  export capacity" (the 18 is right, the 10.5 is not). Measure before
  adopting, as ever: `evidence_text ~* '\m(export|exporting|exported)\M'`
  on `grid_connection` rows is the candidate predicate, and at 16 rows a
  hand pass over the list is cheaper than a clever one. Re-check the
  Operators tab's like-for-like after.

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
  published one. Two candidate causes worth eliminating before looking
  further afield: the `DISTINCT ON (document_id) … ORDER BY document_id,
  recorded_at DESC, id DESC` in `_drive_document_map`, where every row
  from a single recorder run shares one `recorded_at` and the tiebreak
  falls to `id` — deterministic on inspection, but it is new; and
  anything in the reader iterating a `set` or a `dict` built from one.
  Cheapest next step is to have the test keep both builds on failure
  rather than only naming a line, so a single reproduction is enough.

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

- **The acquisition tail.** 31 browser-routed applications, 20 across
  bespoke portals, 13 genuinely hard — a slow process needing a human at
  the keyboard, and not worth holding the release for.
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

- **DC01, the unidentified Foxglove case.** A 320 MW outline approved
  2025-02 with implausibly low emissions and no council, developer or
  address. Three of four originally-unidentified cases are resolved;
  this is the fourth. Most likely falls out of an operator-name sweep
  for hyperscaler-affiliated SPVs.
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
  copy — reference stems and the applicant of record in the documents
  as the boundary evidence, every member assigned so nothing is left
  to spatial chance. Sites 5, 23, 59 and 11 are what remain, and the
  permits carry their evidence.
- **Requests outstanding, and requests never sent.** NESO and Ofgem were
  written to on 2026-08-12 and replies are due around 10 September. Three
  more are worth sending and have not been: a CCA site-level consumption
  FoI to DESNZ/EA, EIR requests to the DNOs, and an EIR request to NESO
  for the project-level demand connection queue. Each runs ~28 days, so
  starting them is cheap and waiting is the whole cost. EIR is the right
  frame for the DNOs — address the *licensed* plc, not the management
  company, and note that section 105 of the Utilities Act is
  near-absolute under FOIA but disapplied for environmental information
  by EIR regulation 5(6).
- **UKPN's gated datasets are unpulled.** The Large Demand List and
  "Data Centres by Local Authority" sit behind Luke's portal login;
  anonymous access returns headers only, so nobody else can fetch them.
- **Two VIRTUS filings are still not retrievable.** Accounts made up to
  31 December 2025, filed on 19 and 20 August 2026; the Companies House
  document API had no images for them as of 2026-08-21. Worth retrying —
  the property company (09840065) is the one that states capacity, not
  the operating company.
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
