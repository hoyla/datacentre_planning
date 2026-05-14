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

46 tests total (10 unit + 28 integration + 8 triage), all green.

---

## Next

**Immediate (next session): two phases queued in order.**

### 1. Parent-application backfill (Luke's 2026-05-14 architectural insight)

Procedural follow-on applications (variations of conditions, NMAs, conditions discharges, reserved matters following an outline) point to substantive *parent* permissions. The triage rubric correctly classifies them as "unrelated" because the procedural application itself adds no new content — but we haven't been *acting* on the pointer to the parent. This causes the only repeatable miss across all 5 evaluated models (#6 Saunderton: the 2022 variation captured, the 2008 parent permission `08/05740/FULEA` is pre-2018 and outside our keyword-sweep window, but explicitly referenced from the variation we already have).

Design:
- Query `applications` for distinct `associated_id` values on procedural records (PlanIt populates this field).
- Cross-check against existing `applications.application_ref` (with council-prefix normalisation: e.g. `EPF/1165/22` vs `EppingForest/EPF/1165/22`).
- For missing parents, fetch from PlanIt via `id_match` or description-search; ingest with `discovered_via=['parent_backfill:<child_ref>']`.
- Regex fallback for description-embedded parent refs where PlanIt's `associated_id` is empty.

Implementation: ~half a day. No new schema needed — `discovered_via` array column already supports the new tag. Pre-2018 backfill of important cases falls out as a bonus.

### 2. Production triage sweep

Run `granite4.1:30b` triage over the full 1,549-application universe (post-backfill so the parents are included). ~4 hours wall-clock at 9.2s/app. Outputs ranked deep-read worklist for Aisha. Should be left to run unattended; the eval harness is hardened (incremental JSONL writes, resume support, per-call timeout, parse-retry).

### Optional but adjacent: operator-prior `discovered_via` tag

Wire a `discovered_via:foxglove_top10` flag onto the ten Foxglove applications (or similar pattern for other known operator priors). Bypasses the only failure mode the LLM can't fix from description alone. ~30 min of work.

**Soon (after the two phases above):**

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

- **Triage rubric scope.** Are we primarily hunting *primary on-site gas* (sharper, rarer) or *outsized backup-but-grid-services capacity* (more common, softer story)? Both? Decided with Aisha at next session.
- **"energy centre" sweep.** 9,061 PlanIt hits — far too noisy for direct ingestion, but the term *is* the coded-language signal. Either run as a separate triage-heavy pass or rely on the in-document signal during deep-read. Probably both.
- **Operator-name searches (Phase 1b).** Google, Meta, Microsoft, Blackstone, QTS, Greystoke, Vantage etc. via PlanIt's `developer=` parameter. Catches applications without DC keywords in description. Worth running once before triage to expand the universe.
- **Findings export shape.** Markdown + xlsx for journalist hand-off (meridian pattern) feels right. Whether to also stand up a FastAPI portal for browsing depends on whether Aisha (or the wider data desk) needs it. Defer until asked.
- **CI.** GitHub Actions or other? Worth setting up once a second engineer joins. Tests are already CI-shaped (`-m "not integration"` for offline runs).
- **Public-data ethics for personal-data fields.** Householder applications can include applicant names. Current schema stores raw values; redaction belongs at the export stage. Sanity-check before publishing any aggregate that touches personal fields.
- **PlanIt rate-limit politics.** PlanIt is donation-supported and friendly; we are a heavy user. Worth reaching out to them at some point — both as good citizenship and because they may have insights about coverage gaps.

---

## Pipeline phase reference

| Phase | Status | Description |
|---|---|---|
| 0 — Scaffolding | ✅ Done | Package, schema, CLI, tests, docker-compose. |
| 1a — PlanIt index | ✅ Done | National DC application metadata. |
| 1b — Operator-name sweep | ⏳ Soon | `developer=` parameter sweep for operator-coded applications. |
| 2 — Triage | ⏳ Next | LLM classification, signal flagging. |
| 3 — Document fetch | ⏳ After triage | Source-portal document download for matched applications. |
| 4 — Structured extraction | ⏳ After fetch | Text extraction, OCR fallback, evidence-quoted findings. |
| 5 — Multimodal pass | ⏳ Eventual | Claude vision on site plans / blueprints. |
| 6 — Reporter export | ⏳ Eventual | Markdown summary + xlsx + (optional) FastAPI portal. |
