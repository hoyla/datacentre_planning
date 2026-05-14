# Roadmap

Where the project stands, what's next, what's parked, and what's open.

For *how the system is shaped*, see [ARCHITECTURE.md](ARCHITECTURE.md).
For *why we're doing this and what's been published*, see [prior_art.md](prior_art.md).

Last meaningful update: 2026-05-14.

---

## Done

- **Phase 0 scaffolding** (`d53974e`). Python 3.12 package, raw-psycopg2 DB layer, FakeBackend + Ollama LLM split, CLI skeleton, append-only schema, docker-compose for Postgres.
- **Prior-art baseline** (`3e6f579`). `prior_art.md` collects published research with cross-reference benchmarks for our own findings to reconcile against; Foxglove top-10 transcribed verbatim from the report PDF.
- **Seed-case hands-on walkthrough** (`290f246`). Wapseys Wood (Section 35 Direction, 300 MW + "energy centre"), Yorkshire Energy Park (CHP turbines on natural gas, marketed zero-carbon, hydrogen-conditional — textbook finding from a 3-page Energy Statement), Loughton (Salesforce portal — blocked at static fetch, later resolved via PlanIt).
- **PlanIt API exploration** (`78d5150`). 20.1M applications across 417 UK councils; `/api/areas/` doubles as national portal inventory; 2,120 applications match `"data centre"`; 2018+ is the defensible good-data window.
- **PlanIt index adapter** (`1d962c2`). Two-pass (areas + applications), polite rate-limiting, exponential 429 backoff (`40a0659`), cache-based resume (`7fa68d6`). Mock-transport unit tests cover paging, caching, and delay enforcement.
- **End-to-end validated** (`90d709c`). Docker Postgres on port 5433 (avoiding collision with Homebrew local PG); migration applies cleanly; CLI runs against real DB.
- **Full v1 sweep ingested.** 1,549 applications, 401 councils with GSS code and portal type, spanning 2018-01 → 2026-05. Foxglove cases visible: Cambois/Blyth outline, Loughton outline (`EPF/1165/22`) + related variations, Virtus Saunderton (under legacy `ChilternSouthBucks` district name).
- **Integration test suite** (`a12708d`). 16 SQL-path tests against a separate `dcp_test` database, transaction-rollback per-test isolation, gated by `@pytest.mark.integration`.
- **Phase 1c (spatial colocated sweep) + Phase 1d (operator-name sweep)** (`fe1a2a7`, refined `f4c3145`, `ae8d8d7`). Migration 002 adds `discovered_via TEXT[]` plus the `colocated_candidates` table. Two-step spatial design (fetch caches, process re-derives links from current keyword lexicon — vocabulary iteration costs no API calls). Operator-name caveats documented: PlanIt's developer-only queries time out on their backend and applicant_* fields are mostly empty, so practical matching is via `agent_company` / `agent_address`. Local backfill of operator tags from cached agent data (no API budget) tagged 217 applications.
- **Foxglove top-10 colocated candidates derived** (this session, `8f28bc8` and ancestors). The original spatial spike's 8 cached JSON responses were imported into `source_snapshots`, then `process_colocated` derived 338 candidate links across 14 anchors. Yorkshire Energy Park's neighbours include the smoking-gun `EastRiding/16/02800/STPLF` ("Erection of a gas-fired energy reserve facility of up to 21MW capacity comprising of 14 gas reciprocating engine generators"), filed six years before the DC, plus a 2024 hydrogen production facility and multiple BESS applications — confirming the structural multi-fuel cluster pattern.
- **Phase 1e (NSIP CSV adapter)** (`8f28bc8`). Built on the day's research (`1613414`). One DC project currently in the NSIP register: Wapseys Wood (`EN0110030`, Slough Holdings UK Limited, "EN01 - Generating Stations" classification, pre-application, anticipated DCO submission January 2027). Captured with full official description spelling out the on-site 250–350MW gas energy centre alongside the 300MW DC. The "EN01" classification is structurally important — DCs may be filed as generating stations rather than as a separate type.
- **Triage Stage 1 designed, evaluated, model selected** (`bfd8ca4`, refined `9980bbe`). Rubric distilled from Luke's labelling of 30 applications. Five models compared on the labelled set: granite4.1:8b (24/29, 4.3s/app), granite4.1:30b (28/29, 9.2s/app), mistral-small3.2:24b (26/29), gemma4:e4b (27/29), qwen3.6 (25/29, 60s/app). **Production choice: granite4.1:30b** — IBM's JSON-tuning advantage scales (calibration discipline + reasoning capacity), and bigger non-granite models lose calibration. Only repeatable miss across all five models is #6 Saunderton, which is architecturally recoverable via parent-backfill (see Next).
- **Privacy** (`d467bfb`). Repo flipped to PRIVATE on GitHub 2026-05-14 to halt pre-publication exposure. `data/` mostly gitignored; only `data/operators.yaml` and `data/triage_labelling/rubric.md` remain tracked.

- **Parent-application backfill** (this session, 2026-05-14). 67 new parents fetched, **41 pre-2018** — directly addressing the keyword-sweep window gap. The Saunderton smoking-gun `Wycombe/08/05740/FULEA` is recovered (the only repeatable miss across all five evaluated triage models). Bare-ref fallback in `_fetch_parent` handled the council-reorganisation case (child under `Bucks/`, parent under legacy `Wycombe/`). New 2007–2008 cluster of 10 parents, four of which are explicit DC permissions (Saunderton, Elean Business Park, Newport Celtic Lakes, Bury Green Farm). Tagged `discovered_via=['parent_backfill:<child_ref>']`.

- **Production triage path wired** (this session). `dcp triage` reads pending apps from the DB, calls `triage_application` with `granite4.1:30b`, writes versioned verdicts to the `triage` table. Migration 003 reshaped the `triage` table (categorical `confidence`, added `worth_deep_read`/`signals[]`/`why`) to match the post-eval prompt output. Resume contract is per-model — rerunning with a different model overlays a second opinion. Smoke-tested on 5 apps; full sweep running unattended.

71 tests total (parent-backfill + triage path each added new files), all green.

---

## Next

### Optional but adjacent: operator-prior `discovered_via` tag

Wire a `discovered_via:foxglove_top10` flag onto the ten Foxglove applications (or similar pattern for other known operator priors). Bypasses the only failure mode the LLM can't fix from description alone. ~30 min of work.

### Reporter export from triage output

Once the full sweep finishes, surface the ranked deep-read worklist for Aisha. Likely: a markdown summary + xlsx export, filtered to `verdict in ('DC', 'adjacent') AND worth_deep_read in ('yes', 'maybe')`, ordered by signal strength + recency.

**Soon (after the items above):**

- **Council reorganisation handling.** Pre-2020 applications under legacy district names (Wycombe, Chiltern South Bucks, etc.) currently land with NULL `council_gss`. Either map legacy GSS codes into `councils`, or normalise on the join. ~50 records affected.
- **Document-fetch adapter for matched applications.** Once triage produces matches, download the source-portal documents (Idox canonical + `/newplanningaccess/` variant cover ~half the universe; Arcus and others follow).
- **Promote `associated_id` to a typed column.** Once parent-backfill confirms the field is reliable, promoting it from `raw_metadata` to a dedicated `applications.parent_ref` column makes family-navigation queries a direct join. ~30 minutes of schema work.

---

## Parked

Items consciously deferred — return when journalism need warrants.

- ~~**The four unidentified Foxglove cases.**~~ **Three of four resolved 2026-05-12** in [data/prior_art_sources/foxglove_reconciliation.md](data/prior_art_sources/foxglove_reconciliation.md): International Trading Estate (GTR) = `Ealing/250949FUL`, 103MW Court Lane = `ChilternSouthBucks/PL/22/4145/OA` (Iver), G-Park Docklands (probable) = `TowerHamlets/PA/22/01140/A1`. Only DC01 remains unidentified — defer to operator-name sweep.

- **Phase 1c — spatial sweep for co-located energy applications.** Hypothesis (Luke's): DC developers may not file the gas/CHP that powers them; the energy side is a parallel planning record under a different applicant, findable only by geographic proximity. **Spike completed 2026-05-12** ([data/colocated_energy_spike/findings.md](data/colocated_energy_spike/findings.md)) — hypothesis confirmed by Yorkshire Energy Park's `EastRiding/16/02800/STPLF` (21 MW gas-fired, 14 gas-reciprocating-engine generators), filed six years before the DC at the same site under a different reference, never mentioning "data centre". Signal-to-noise in dense urban areas is low without filtering. **Recommend building** with structural filters (exclude pure-substation, residential masterplan CHP, anchor-self conditions discharges) — ~6–10h polite wall-clock to sweep the full 1,549-DC universe at 1km radius.
- **Phase 1d — operator-name sweep.** PlanIt's `developer=` param searches across applicant/agent address and company. Three motivations now stacking up: catches DC01 (the unidentified Foxglove case); catches applications with neutral descriptions where the operator name is the give-away; and (post-spike) may catch parallel energy-side filings by DC operators' affiliated SPVs more cleanly than spatial proximity alone (Yorkshire Energy Park's earlier 21MW plant was filed by an entity whose name we'd want to check against Hull Eco Park Ltd / Vic Coupland).
- **Salesforce adapter.** Originally planned for Epping Forest's Loughton case, but PlanIt's Arcus scraper covers Epping Forest, so the Salesforce frontend can be ignored. Revisit only if we encounter a Salesforce-only council not in PlanIt.
- **NSIP / Section 35 Directions adapter (Phase 1e).** Research done 2026-05-13 — see [data/nsip_research/findings.md](data/nsip_research/findings.md). The Planning Inspectorate publishes a **machine-readable CSV** of all ~280 NSIP projects at https://national-infrastructure-consenting.planninginspectorate.gov.uk/api/applications-download (no auth, 213 KB, verified). Section 35 Directions are scattered gov.uk publications discoverable via the gov.uk search API. Two-adapter design proposed; ~half-day of engineering. DC universe currently tiny (Wapseys Wood is the only confirmed DC Section 35 Direction) but expected to grow as 2026 regulations take effect. Build when journalism warrants or when a second DC Section 35 Direction appears.
- **Idox / Civica / Tascomi / Ocella direct adapters.** Not needed for index stage (PlanIt covers most councils). Will be needed for the document-fetch stage where PlanIt only gives application metadata.
- **MHCLG "Find a Planning Application" national service.** A second national-coverage source that could cross-validate PlanIt. Not urgent given PlanIt's depth.
- **Geospatial / map output.** Application points + council polygons are derivable from existing data. Authoritative council boundaries from ONS BoundaryLine, not PlanIt's `borders`. Publication-output question, not ingestion.
- **`other_fields` normalisation.** PlanIt records carry applicant_name, agent_company, applicant_address in a JSON blob inside `raw_metadata`. Worth promoting to dedicated columns when the search-by-developer use case (Phase 1b operator-name sweep) becomes active.
- **Pre-2018 backfill.** PlanIt's coverage thins sharply before 2018. Worth a separate sweep with broader keyword set if the story angle needs it.

---

## Open questions

Things we haven't decided yet, with current thinking where there is one.

- **Triage rubric scope.** The current prompt leans inclusive across both *primary on-site gas* and *outsized backup-but-grid-services capacity* (`worth_deep_read='yes'/'maybe'` on either signal). After the first full triage sweep lands, decide with Aisha whether to narrow to one of these and re-run the universe under a tighter rubric for ranking.
- **"energy centre" sweep.** 9,061 PlanIt hits — far too noisy for direct ingestion, but the term *is* the coded-language signal (granite4.1:30b already extracts it as a signal when it appears). Either run as a separate triage-heavy pass or rely on the in-document signal during deep-read. Probably both.
- **Findings export shape.** Markdown + xlsx for journalist hand-off (meridian pattern) feels right. Whether to also stand up a FastAPI portal for browsing depends on whether Aisha (or the wider data desk) needs it. Defer until asked.
- **CI.** GitHub Actions or other? Worth setting up once a second engineer joins. Tests are already CI-shaped (`-m "not integration"` for offline runs).
- **Public-data ethics for personal-data fields.** Householder applications can include applicant names. Current schema stores raw values; redaction belongs at the export stage. Sanity-check before publishing any aggregate that touches personal fields.
- **PlanIt rate-limit politics.** PlanIt is donation-supported and friendly; we are a heavy user. Worth reaching out to them at some point — both as good citizenship and because they may have insights about coverage gaps.

---

## Pipeline phase reference

| Phase | Status | Description |
|---|---|---|
| 0 — Scaffolding | ✅ Done | Package, schema, CLI, tests, docker-compose. |
| 1a — PlanIt index | ✅ Done | National DC application metadata (1,549 in-window apps). |
| 1c — Spatial colocated sweep | ✅ Done | Two-step fetch/process; 338 candidate links across 14 anchors. |
| 1d — Operator-name sweep | ✅ Done | `developer=` parameter sweep; 217 apps tagged by local agent-data backfill. |
| 1e — NSIP CSV adapter | ✅ Done | All ~280 projects ingested; one current DC (Wapseys Wood). |
| 1f — Parent-application backfill | ✅ Done | 67 parents fetched, 41 pre-2018. Saunderton 2008 parent recovered. |
| 2 — Triage | ⏳ Running | `granite4.1:30b` over the full 1,832-app universe; first sweep in flight. |
| 3 — Document fetch | ⏳ After triage | Source-portal document download for matched applications. |
| 4 — Structured extraction | ⏳ After fetch | Text extraction, OCR fallback, evidence-quoted findings. |
| 5 — Multimodal pass | ⏳ Eventual | Claude vision on site plans / blueprints. |
| 6 — Reporter export | ⏳ Next after triage | Markdown summary + xlsx, filtered to triage matches. |
