# Roadmap

Where the project stands, what's next, what's parked, and what's open.

For *how the system is shaped*, see [ARCHITECTURE.md](ARCHITECTURE.md).
For *why we're doing this and what's been published*, see [prior_art.md](prior_art.md).

Last meaningful update: 2026-05-12.

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

24 tests total (8 unit + 16 integration), all green. Code at `a12708d` on `main` (https://github.com/hoyla/datacentre_planning).

---

## Next

**Immediate (next session):** triage rubric design.

Ideally collaborative with Aisha. We have 1,549 real applications to test prompts against, plus three hand-validated exemplar cases (Yorkshire Energy Park, Wapseys Wood, Loughton). Aim:

- Define the *signal types* we want extracted (initial list in `data/seed_cases/walkthrough_findings.md`).
- Draft Stage-1 prompt — application description + consultee senders → classify (DC / adjacent / unrelated / unknown) and flag "worth deep reading".
- Spike Stage-2 prompt — Energy Statement / officer report / consultee letters → structured extraction with evidence-text capture.
- Run prompts against the seed cases first, then a sample from the ingested universe, iterate.

**Soon:**

- **Council reorganisation handling.** Pre-2020 applications under legacy district names (Wycombe, Chiltern South Bucks, etc.) currently land with NULL `council_gss`. Either map legacy GSS codes into `councils`, or normalise on the join. ~50 records affected in v1 sweep.
- **Document-fetch adapter for matched applications.** Once triage produces matches, we need to download the source-portal documents (Idox canonical and the `/newplanningaccess/` variant cover ~half the universe; Arcus and others follow). The Energy Statement document type from East Riding maps cleanly into the existing schema (`documents.kind`).
- **Foxglove top-10 reconciliation.** Programmatic check that all ten Foxglove cases are present in our `applications` universe. Three are confirmed (Cambois, Saunderton, Loughton-adjacent); the others either match under different keywords or surface a coverage gap.

---

## Parked

Items consciously deferred — return when journalism need warrants.

- **The four unidentified Foxglove cases.** DC01, International Trading Estate (GTR), G-Park Docklands (GLP), 103MW Court Lane. Three are the implausibly-low-emissions outliers in Foxglove's table and would make strong "developer figure understates kit" leads. Note in [data/seed_cases/foxglove_top10.md](data/seed_cases/foxglove_top10.md).
- **Salesforce adapter.** Originally planned for Epping Forest's Loughton case, but PlanIt's Arcus scraper covers Epping Forest, so the Salesforce frontend can be ignored. Revisit only if we encounter a Salesforce-only council not in PlanIt.
- **NSIP / Section 35 Directions adapter.** The Planning Inspectorate route catches the biggest DCs (300+ MW). Currently the only NSIP case in our universe is the Bucks 2026 application surfacing in PlanIt; broader NSIP coverage needs a separate adapter. Wapseys Wood Section 35 PDF cached for reference.
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
