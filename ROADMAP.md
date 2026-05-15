# Roadmap

Where the project stands, what's next, what's parked, and what's open.

For *how the system is shaped*, see [ARCHITECTURE.md](ARCHITECTURE.md).
For *why we're doing this and what's been published*, see [prior_art.md](prior_art.md).
For *post-publication flip mechanics*, see [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md).

Last meaningful update: 2026-05-15 (late afternoon — Phase 3 fetch in flight).

---

## Done

### Phase 0 — scaffolding (May 12)

- **Phase 0 scaffolding** (`d53974e`). Python 3.12 package, raw-psycopg2 DB layer, FakeBackend + Ollama LLM split, CLI skeleton, append-only schema, docker-compose for Postgres.
- **Prior-art baseline** (`3e6f579`). `prior_art.md` collects published research with cross-reference benchmarks; Foxglove top-10 transcribed verbatim.
- **Seed-case hands-on walkthrough** (`290f246`). Wapseys Wood / Yorkshire Energy Park / Loughton seed cases.
- **PlanIt API exploration** (`78d5150`). 20.1M applications across 417 UK councils; `/api/areas/` doubles as national portal inventory; 2018+ is the defensible good-data window.
- **End-to-end validated** (`90d709c`). Docker Postgres on port 5433; migration applies cleanly; CLI runs against real DB.

### Phase 1 — index (May 12–14)

- **Phase 1a — PlanIt index adapter** (`1d962c2`). Two-pass (areas + applications), polite rate-limiting, exponential 429 backoff, cache-based resume.
- **Full v1 sweep ingested.** 1,549 applications, 401 GSS-mapped councils, 2018-01 → 2026-05.
- **Phase 1c — spatial colocated sweep + Phase 1d — operator-name sweep** (`fe1a2a7`, `f4c3145`, `ae8d8d7`). Migration 002 adds `discovered_via TEXT[]` + `colocated_candidates` table. Two-step spatial design surfaces the Yorkshire Energy Park `EastRiding/16/02800/STPLF` smoking gun (21 MW gas-fired, filed six years before the DC at the same site). 217 apps tagged by local agent-data backfill.
- **Phase 1e — NSIP CSV adapter** (`8f28bc8`). Wapseys Wood ingested (only current DC NSIP project; expected to grow under 2026 regulations).
- **Phase 1f — Parent-application backfill** (`d4cf377`, 2026-05-14). 67 parents fetched, 41 pre-2018. The Saunderton smoking-gun `Wycombe/08/05740/FULEA` recovered. Bare-ref fallback handles the council-reorganisation case (child under `Bucks/`, parent under legacy `Wycombe/`). Tagged `discovered_via=['parent_backfill:<child_ref>']`.

### Phase 2 — triage (May 13–15)

- **Triage Stage 1 designed + evaluated, model selected** (`bfd8ca4`, refined `9980bbe`). Rubric distilled from 30 labelled applications; five-model comparison; **granite4.1:30b chosen** (28/29 = 97%, 9.2s/app).
- **Production triage path wired** (`92f75ac`, 2026-05-14). `dcp triage` reads pending apps from DB, calls `granite4.1:30b`, writes versioned verdicts to the `triage` table. Migration 003 reshapes the schema to match the post-eval rubric (categorical `confidence`, `worth_deep_read`, `signals[]`, `why`). Resume contract is per-model.
- **Full triage sweep completed** (2026-05-15, ~9h wall-clock). 1,832 apps, 0 errors. Final verdict mix: 683 DC · 136 adjacent · 965 unrelated · 48 unknown.
- **Council reorganisation handling** (`289035d`, 2026-05-15). Migration 004 fixes the TEXT-vs-JSONB bug on `councils.notes` (which had been silently writing NULL `council_gss` for spatial/operator/parent-backfill paths) + adds the `council_aliases` table. 317 NULL `council_gss` rows resolved (Wycombe / ChilternSouthBucks / AylesburyVale → Buckinghamshire E06000060; Kettering / Wellingborough → North Northamptonshire E06000061; 269 direct council matches + 48 alias matches). 97 deliberately unmapped (OPDC, LLDC, joint-planning services where the constituent council isn't in PlanIt's areas listing).
- **Foxglove top-10 operator-prior tag** (`471f177`, 2026-05-15). 23 applications across 10 families tagged `discovered_via:foxglove_top10` so the export filter surfaces them even when triage correctly classifies a procedural follow-on as 'unrelated'. Tracked YAML at `data/priors/foxglove_top10.yaml`; idempotent loader at `scripts/tag_priors.py`.
- **Targeted council-backfill retriage** (`ab721a1`, 2026-05-15). 277 apps retriaged with proper council context after migration 004 resolved their NULL `council_gss`. 18 verdict / deep-read changes (6.5%); net worklist size 818 → 815. The Halton Tesco-CHP-removal case flipped adjacent→unrelated without any explicit polarity rule.

### Phase 3 — document fetch (May 15)

- **Idox document-fetch adapter** (`8f6de70`, `16d9889`, 2026-05-15). `dcp fetch-docs --source idox` walks worklist apps in rank order, downloads every direct-PDF link from the documents tab, stores bytes under `data/raw/idox/<application_ref>/<sha[:16]>.<ext>`, records metadata in the `documents` table (UNIQUE on application_id + content_sha256 for idempotency). Per-app `_manifest.json` is the hand-over signal. Error-classification surfaces ssl_chain_failure / dns_failure / withdrawn_from_view / no_documents_or_unparseable distinctly.
- **SSL chain fix via OS native trust store** (`16d9889`). Many council Idox installs send only the leaf cert; `truststore` delegates to the OS TLS APIs which perform AIA chasing automatically. Unblocks Tower Hamlets, Northumberland (Cambois Foxglove case), Glasgow, and other broken-chain councils — full PKI validation preserved, only the chain reconstruction is delegated.
- **Wider top-100 worklist sweep completed** (2026-05-16, ~14h wall-clock). 79 apps fully successful, 21 classified-skips (15 `no_documents_or_unparseable`, 4 `withdrawn_from_view`, 1 `dns_failure`, 1 `RuntimeError`). 3,032 documents downloaded across 3,104 found; **9.3 GB on disk**. Corpus mix: 2,849 PDFs + 52 .msg consultee emails + 52 .docx + 13 .xlsm + 12 .rtf + 10 .jpg + 15 misc Office files. The .msg files are exactly the EA-letter / consultee-response category Aisha flagged as editorially critical — generator counts and fuel detail that the application form alone omits.

### Phase 6 — reporter export (May 15)

- **Reporter export pair: markdown narrative + xlsx** (`fdac237`). `dcp export --top N` produces `data/exports/worklist_<date>.md` (top-N curated cards with full triage context) and `data/exports/worklist_<date>.xlsx` (all 815 worklist entries as a sortable / filterable Excel table). Shared query/render helpers in `dcp/worklist.py` so the preview script and the formal export render identical cards. Latest-verdict-per-app via `DISTINCT ON (application_id) ORDER BY inserted_at DESC` so retriage runs supersede earlier verdicts without losing the audit trail.
- **Worklist UX humanisation + polarity decision** (`a5787a6`). Per-card "Why this is on the worklist" explanation translates the `discovered_via` tags into reader prose (spatial neighbours render with the anchor's description + address; operator/parent_backfill/foxglove all expanded). Rubric Editorial Principle 6 records the decision not to filter on polarity — *"removal of legacy gas turbine to install new hydrogen fuel cell array"* is editorially the *story*, so we don't drop it.
- **Editorial map** (`22b7cb8`). `dcp map` produces three artefacts: HTML (Folium/Leaflet, primary), GeoJSON (QGIS / kepler.gl), KML (Guardian graphics team / Google Earth). Worklist points coloured by verdict, sized by Tier-1 signal count; OSM `power=plant` overlay in fossil / biomass+waste / nuclear / renewable / storage buckets; click popups show distance to nearest fossil/biomass/nuclear plant. **Headline finding from the proximity precompute: 58% of worklist DC applications sit within 5 km of a fossil/biomass/nuclear plant.** OSM source bundled (`data/priors/osm/uk_power_plants.geojson`, ODbL-licensed, 3,987 features).

### Publication prep (May 14–15)

- **Privacy** (`d467bfb`). Repo flipped to PRIVATE on GitHub 2026-05-14 to halt pre-publication exposure.
- **Methodology trail tracked under data/** (`c0065cf`, 2026-05-15). Gitignore widened to track the seed-case + findings docs, the PlanIt API sample fixture, the prior-art reconciliation, and the per-model eval reports. PII scan completed. Raw documents, exports, point-in-time JSONL outputs, and the round_01 labelled sample stay blocked.
- **Publication-ready scaffolding** (`e4fe9fd`). `LICENSE`, `CITATION.cff`, `DATA-LICENSING.md`, README "Reproducing the dataset" section (11-step rebuild sequence). [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md) captures the flip-day work.
- **Apache 2.0 relicence; copyright Guardian News & Media Ltd.** (`1963d63`, 2026-05-15). This is a Guardian journalism project; copyright belongs to GNM with Luke Hoyland as author. Apache 2.0 matches Guardian's open-source convention.

**126 tests total**, all green.

---

## Next

### Immediate (this/next session)

- **Phase 4 — structured extraction.** Documents are landing; we can start parsing PDFs (text-layer + OCR fallback via pypdf/pdfplumber, both already deps) and surfacing power-related signals into `findings`. Two-stage extraction per the seed walkthrough — (a) description + consultee senders, (b) per-document evidence-quoted extraction. Probably the highest-value next thing once Aisha's started reading.

- **Per-portal document-fetch adapters** for the long tail. Idox covers a big slice of the worklist; Ocella / Arcus / Salesforce / Civica / Tascomi / bespoke each need their own adapter when the worklist requires it. Per-portal effort scales: a clean adapter is ~half-day each; the documents-list HTML varies but the orchestrator / storage / manifest layer is reusable.

### Soon

- **Promote `associated_id` to a typed `applications.parent_ref` column.** Parent-backfill confirmed the field is reliable; a typed column makes family-navigation queries a direct join instead of JSONB extraction. ~30 min of schema + retrofill work.

- **CI on GitHub Actions** (now feasible since the project is Apache 2.0 and tracked). Run `pytest -m "not integration"` on every push. ~1–2h.

- **Triage round 2 with refined rubric** (depending on Aisha's editorial-narrowing decision — see Open Questions below). Either narrow to *primary on-site gas* (sharper, rarer story) or *outsized backup-but-grid-services capacity* (more common, softer story), and re-run with the tighter prompt.

---

## Parked

Items consciously deferred — return when journalism need warrants.

- **DC01 (the one unidentified Foxglove case).** Foxglove's report names a 320 MW DC outline approved 2025-02 with implausibly low emissions but no council / developer / address. Three of the four originally-unidentified Foxglove cases have been resolved; DC01 is the remaining one. Most likely identifiable once we sweep operator-name expansions for hyperscaler-affiliated SPVs.

- **Salesforce adapter.** Originally planned for Epping Forest's Loughton case, but PlanIt's Arcus scraper covers Epping Forest, so the Salesforce frontend can be ignored. Revisit only if we encounter a Salesforce-only council not in PlanIt.

- **NSIP / Section 35 Directions adapter (gov.uk-search-API half).** The NSIP CSV is built; the gov.uk Section 35 Directions discovery half is research-only (see `data/nsip_research/findings.md`). Build when journalism warrants or when a second DC Section 35 Direction appears.

- **Direct council-portal index adapters** (beyond what PlanIt covers). MHCLG "Find a Planning Application" is the alternative national source. Not urgent given PlanIt's depth; useful as a cross-validation source pre-publication.

- **`other_fields` normalisation.** PlanIt records carry applicant_name, agent_company, applicant_address in JSON inside `raw_metadata`. Worth promoting to dedicated columns if we run a meaningful operator-name sweep beyond what's already done.

- **Pre-2018 broader-keyword backfill.** PlanIt's coverage thins sharply before 2018. The parent-backfill already pulled in pre-2018 substantive parents; a separate broader-keyword sweep would catch pre-2018 cases that don't have a child in our window. Worth a separate sweep if the story angle needs it.

- **Document corpus mirror.** `data/raw/` is local-only and growing (~2 GB at top-100). Candidates for a public reproducibility mirror: zenodo (DOI, academic-friendly, CC-BY), S3 (paid, more control), academictorrents. Decide once corpus stabilises in size and publication-day workflow is clear. See [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md).

---

## Open questions

Things we haven't decided yet, with current thinking where there is one.

- **Triage rubric scope.** The current prompt leans inclusive across both *primary on-site gas* and *outsized backup-but-grid-services capacity* (`worth_deep_read='yes'/'maybe'` on either signal). Now that the full sweep is in, decide with Aisha whether to narrow to one of these and re-run the universe under a tighter rubric for ranking.
- **"energy centre" sweep.** 9,061 PlanIt hits — far too noisy for direct ingestion, but the term *is* the coded-language signal (granite4.1:30b already extracts it as a signal when it appears). Either run as a separate triage-heavy pass or rely on the in-document signal during deep-read. Probably both.
- **FastAPI portal for browsing.** Markdown + xlsx + KML + interactive map cover the current hand-off shape well. A FastAPI portal would matter only if Aisha (or the wider data desk) wants point-and-click filtering on the full 815-app universe beyond what Excel can give them. Defer until asked.
- **Public-data ethics for personal-data fields.** Householder applications can include applicant names. Current schema stores raw values; redaction belongs at the export stage. Pre-publication sanity-check completed on the methodology-trail tracked files; needs to run again on any aggregate that touches personal fields.
- **PlanIt rate-limit politics.** PlanIt is donation-supported and friendly; we are a heavy user. Worth reaching out to them at some point — both as good citizenship and because they may have insights about coverage gaps. Now particularly relevant: the document-fetch stage hits *council portals* directly, not PlanIt, but the operator-name sweep + spatial sweep do hit PlanIt heavily.

---

## Pipeline phase reference

| Phase | Status | Description |
|---|---|---|
| 0 — Scaffolding | ✅ Done | Package, schema, CLI, tests, docker-compose. |
| 1a — PlanIt index | ✅ Done | National DC application metadata (1,832 in universe including parent-backfill). |
| 1c — Spatial colocated sweep | ✅ Done | 338 candidate links across 14 anchors. |
| 1d — Operator-name sweep | ✅ Done | 217 apps tagged by local agent-data backfill. |
| 1e — NSIP CSV adapter | ✅ Done | All ~280 projects ingested; one current DC (Wapseys Wood). |
| 1f — Parent-application backfill | ✅ Done | 67 parents fetched, 41 pre-2018. |
| 2 — Triage | ✅ Done | `granite4.1:30b` over the full universe; 683 DC + 136 adjacent + 965 unrelated + 48 unknown (post-retriage). |
| 3 — Document fetch | ✅ Top-100 done | Idox top-100 sweep complete (79 apps cleanly fetched, 9.3 GB corpus); long-tail per-portal adapters (Ocella / Arcus / Salesforce) pending. |
| 4 — Structured extraction | ⏳ Next | Text extraction + OCR fallback; evidence-quoted findings into `findings` table. |
| 5 — Multimodal pass | ⏳ Eventual | Claude vision on site plans / blueprints for matched subset. |
| 6 — Reporter export | ✅ Done (v1) | Markdown + xlsx + KML + interactive HTML map with OSM power-plant overlay. Iterate per Aisha's feedback. |
