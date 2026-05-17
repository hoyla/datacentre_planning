# Roadmap

Where the project stands, what's next, what's parked, and what's open.

For *how the system is shaped*, see [ARCHITECTURE.md](ARCHITECTURE.md).
For *why we're doing this and what's been published*, see [prior_art.md](prior_art.md).
For *post-publication flip mechanics*, see [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md).

Last meaningful update: 2026-05-16 (evening — Phase 4 deep-read pipeline + editorial cohorts shipped).

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

### Phase 3 — document fetch (May 15–16)

- **Idox document-fetch adapter** (`8f6de70`, `16d9889`, 2026-05-15). `dcp fetch-docs --source idox` walks worklist apps in rank order, downloads every direct-PDF link from the documents tab, stores bytes under `data/raw/idox/<application_ref>/<sha[:16]>.<ext>`, records metadata in the `documents` table (UNIQUE on application_id + content_sha256 for idempotency). Per-app `_manifest.json` is the hand-over signal. Error-classification surfaces ssl_chain_failure / dns_failure / withdrawn_from_view / no_documents_or_unparseable distinctly.
- **SSL chain fix via OS native trust store** (`16d9889`). Many council Idox installs send only the leaf cert; `truststore` delegates to the OS TLS APIs which perform AIA chasing automatically. Unblocks Tower Hamlets, Northumberland (Cambois Foxglove case), Glasgow, and other broken-chain councils — full PKI validation preserved, only the chain reconstruction is delegated.
- **Wider top-100 worklist sweep completed** (2026-05-16, ~14h wall-clock). 79 apps fully successful, 21 classified-skips (15 `no_documents_or_unparseable`, 4 `withdrawn_from_view`, 1 `dns_failure`, 1 `RuntimeError`). 3,032 documents downloaded across 3,104 found; **9.3 GB on disk**. Corpus mix: 2,849 PDFs + 52 .msg consultee emails + 52 .docx + 13 .xlsm + 12 .rtf + 10 .jpg + 15 misc Office files. The .msg files are exactly the EA-letter / consultee-response category Aisha flagged as editorially critical — generator counts and fuel detail that the application form alone omits.
- **Ocella adapter** (`ddf6cf2`, 2026-05-16). `dcp fetch-docs --source ocella` covers the second-largest UK council-portal product (Hillingdon, Havering, and others). Documents are reached via a POST to `showDocuments?reference=<ref>&module=pl`, parsing `<a href ="viewDocument?file=...&module=pl">` anchors (the literal space in `href =` is a parser hazard worth noting). Storage / manifest / dedup mirrors the Idox adapter exactly. Top-30 Ocella sweep landed 812 documents across 27 apps (3 Havering scoping-request skips); the Hillingdon Ark Project Union cluster is now fully indexed.
- **Manual ingest tooling** (`144c89d`, 2026-05-16). `scripts/ingest_manual_docs.py` + `dcp/sources/manual.py` cover the long tail of portals without an adapter (NorthLincs custom, Slough Agile, Runnymede PlanningExplorer, Manchester / Charnwood / Neath / Cherwell / WestLothian / Broxbourne / Warrington bespoke). Operator drops files in `data/raw/fully_manual/<app-dirname>/`, runs the script with `--source manual --application-ref ...`, gets hard-linked bytes at the canonical `data/raw/manual/<ref>/<sha[:16]>.<ext>` path + a refreshed manifest. Filename → kind label heuristic preserves readability. Hard links (or copy fallback on EXDEV) keep disk usage flat.

### Phase 4 — structured extraction (May 16)

- **Deep-read extractor + delta classifier shipped** (`7c0082f` through `45359f1`, 2026-05-16). End-to-end pipeline:
  - `dcp/extract.py` — pypdf per-page text cache at `data/raw_text/<source>/<application_ref>/<sha[:16]>.pages.json` + regex pre-pass for MW / generator-count / fuel-storage candidates.
  - `dcp/findings.py` — append-only query (latest per `(application_id, document_id, signal_type, model)`, mirroring triage versioning) + delta classifier sorting each finding into NEW DISCLOSURE / REFINEMENT / CONFIRMATION categories. CONFIRMATIONS (facts already in the description) are dropped from the markdown as noise; xlsx still surfaces their count for audit.
  - `repo.record_finding` helper completes the schema's append-only family alongside `record_triage` / `record_document`.
  - **The LLM stage is replaceable.** This round used Claude Code's vision-capable Read tool as the human-in-loop extractor (model column reads `claude-opus-4-7+read-tool`); a future Anthropic SDK + Sonnet 4.6 batch round (or any other model) writes to `findings` under a different `model` string so the rounds coexist for audit.

- **35 apps with findings**, ~225 findings total. Geographic / operator coverage of the headline cases:
  - **Yorkshire Energy Park family** (STPLF gas reserve, YEP DC, Saltend hybrid gas+BESS, Meld Energy hydrogen hub).
  - **Greystoke Land's three sites** (Humber Tech Park, Elsham Tech Park, West London Tech Park — same Future-tech M&E consultant signature across all three).
  - **Ark "Project Union"** (parent + 2022 expansion + condition-discharge follow-ons).
  - **Longcross campus** (former DERA site — same Hurley Palmer Flatt + Phlorum + Auricl consultant trio as Project Union).
  - **Newham Bidder Street** (Foster & Partners, ~£11M s106 incl. £2.67M carbon offset).
  - **Thurrock Lakeside hyperscale** (Global Infrastructure UK Ltd, 12-year 100 MW Moray West offshore-wind PPA).
  - **WestLothian AI** (250 MW AI-named DC + Section 36 BESS).
  - **Havering Council-led LDO** (up to 400,000 sqm, combustion plant explicitly excluded).
  - **Milton Keynes Energy Network** (13.7 km pipe network feeding 6 named civic anchors).
  - **Neath WBE Margam** (12 MW DC private-wired to existing on-site biomass plant).
  - Four worklist false-positives cleanly disambiguated (residential CHP, pallet kiln, waste-depot BESS pair).
  - Six confirmed cross-borough duplicates tagged so they no longer compete for primary worklist slots.

- **Output integration — markdown + xlsx restructured around editorial themes** (`1043234`, `45359f1`, 2026-05-16). The flat rank-ordered list under-weighted substantive findings and over-weighted procedural follow-ons; the export now opens with hand-picked **Editorial highlights**, organises cards into **Editorial cohorts** (operator clusters, spatial groupings, planning-route patterns), and lists the filtered-out apps in a separate audit section. Cohort structure is a single source of truth at `data/priors/cohorts.yaml`; loader at `scripts/tag_cohorts.py` stamps `cohort:<name>` and `exclude:<reason>` tags via `repo.append_discovered_via`; module-cached lookup at `dcp/cohorts.py`. Cards demote to h3/h4 inside cohort sections; HTML anchors enable highlights and cross-references to link directly to full cards. The xlsx companion gains **Highlight / Primary cohort / Also-in cohorts** columns plus a separate **Filtered** sheet — Aisha can filter on `Highlight=yes` or any single cohort directly in Excel.

### Phase 6 — reporter export (May 15)

- **Reporter export pair: markdown narrative + xlsx** (`fdac237`). `dcp export --top N` produces `data/exports/worklist_<date>.md` (top-N curated cards with full triage context) and `data/exports/worklist_<date>.xlsx` (all 815 worklist entries as a sortable / filterable Excel table). Shared query/render helpers in `dcp/worklist.py` so the preview script and the formal export render identical cards. Latest-verdict-per-app via `DISTINCT ON (application_id) ORDER BY inserted_at DESC` so retriage runs supersede earlier verdicts without losing the audit trail.
- **Worklist UX humanisation + polarity decision** (`a5787a6`). Per-card "Why this is on the worklist" explanation translates the `discovered_via` tags into reader prose (spatial neighbours render with the anchor's description + address; operator/parent_backfill/foxglove all expanded). Rubric Editorial Principle 6 records the decision not to filter on polarity — *"removal of legacy gas turbine to install new hydrogen fuel cell array"* is editorially the *story*, so we don't drop it.
- **Editorial map** (`22b7cb8`). `dcp map` produces three artefacts: HTML (Folium/Leaflet, primary), GeoJSON (QGIS / kepler.gl), KML (Guardian graphics team / Google Earth). Worklist points coloured by verdict, sized by Tier-1 signal count; OSM `power=plant` overlay in fossil / biomass+waste / nuclear / renewable / storage buckets; click popups show distance to nearest fossil/biomass/nuclear plant. **Headline finding from the proximity precompute: 58% of worklist DC applications sit within 5 km of a fossil/biomass/nuclear plant.** OSM source bundled (`data/priors/osm/uk_power_plants.geojson`, ODbL-licensed, 3,987 features).

### Publication prep (May 14–15)

- **Privacy** (`d467bfb`). Repo flipped to PRIVATE on GitHub 2026-05-14 to halt pre-publication exposure.
- **Methodology trail tracked under data/** (`c0065cf`, 2026-05-15). Gitignore widened to track the seed-case + findings docs, the PlanIt API sample fixture, the prior-art reconciliation, and the per-model eval reports. PII scan completed. Raw documents, exports, point-in-time JSONL outputs, and the round_01 labelled sample stay blocked.
- **Publication-ready scaffolding** (`e4fe9fd`). `LICENSE`, `CITATION.cff`, `DATA-LICENSING.md`, README "Reproducing the dataset" section (11-step rebuild sequence). [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md) captures the flip-day work.
- **Apache 2.0 relicence; copyright Guardian News & Media Ltd.** (`1963d63`, 2026-05-15). This is a Guardian journalism project; copyright belongs to GNM with Luke Hoyland as author. Apache 2.0 matches Guardian's open-source convention.

### Story-readiness pass + v1.0 release pipeline (May 16–17)

- **Pre-publication QA across the eight-item story-readiness checklist** (see [investigation context memory] and the `Self-scrutiny/` folder in each release). All eight items + the item-6 adjacent follow-on resolved as of 2026-05-17:
  1. **Quote verification** (`scripts/verify_findings.py`) — every `evidence_text` quote re-opened against the cached page text; 146 verbatim + 1 adjacent + 29 cross-page + 10 vision-verified-against-scanned-source pass. Zero unresolved fails. Re-runnable as a pre-export gate.
  2. **Privacy sweep** — no householder applications in the worklist; 34 residential-shaped addresses all verified as commercial DC sites; ten named individuals across the cards all in professional / public-officer capacities.
  3. **"How to read this" companion doc** — covers absence-of-findings caveats, NEW DISCLOSURE vs REFINEMENT vs CONFIRMATION categories, source-PDF backreferencing, URL durability, Foxglove cross-check. Now also embedded in the integrated viewer's `Read this first` panel.
  4. **Corpus stats in export header** — `scripts/corpus_stats.py` factored into shared `dcp/corpus_stats.py` module; the `dcp export` "At a glance" header now carries date range + by-source breakdown + filter counts + document corpus size + findings sample size. Same numbers travel with the document.
  5. **Foxglove formal reconciliation** — all 9 resolved families present in the worklist with every ref accounted for; structural quirks (procedural follow-ons preserved via the safety-net tag; 2008 parents below their procedural variations in rank) documented.
  6. **Map address spot-check** (`scripts/map_spot_check.py`) — top-50 pins reverse-geocoded via Nominatim; pin positions within tolerable margin, zero council-office geocodes detected.
  7. **Source-doc handover** — handled separately by Luke.
  8. **URL durability** — folded into the "How to read this" companion doc and the integrated viewer intro.
- **Inferred-coords backfill for missing pins** (`data/priors/inferred_coords.yaml`). 11 top-61 worklist applications had no `location_x/y` in the raw PlanIt record (including 2 editorial highlights — Havering/Z0001.24 and MiltonKeynes/PLN/2024/2768) and were therefore absent from the map. Inferred coords now live alongside the raw record (per principle 3, never mutating source material); `dcp/map.py` falls back to the priors lookup when raw coords are null and flags inferred pins distinctly (`inferred_coords: true` in geojson + `⚑` badge in popups + viewer cards).
- **`dcp release --version` — one-shot release-folder orchestrator** (`dcp/release.py`). Produces `data/exports/datacentre_energy_review_v<version>_<date>/` containing the integrated viewer (headline), the text-only markdown, the spreadsheet, the standalone map, the "How to read this" companion, plus `Map data/` (geojson + kml + OSM power-plants context) and `Self-scrutiny/` (the four QA artefacts above). All journalist-facing prose strings purged of "app" in favour of "application" (memory rule). Versioning is manual — bump deliberately per published release.
- **Integrated viewer** (`dcp/reader.py`). Single self-contained HTML file: split-screen Leaflet map + chaptered card list (editorial highlights → cohorts → other ranked), with bidirectional click sync (card → map flyTo + popup; pin → card scrollIntoView + flash), search-across-fields (⌘K), filter chips (verdict / deep-read / Foxglove / has-findings / inferred-coords), and a `Read this first` intro panel that embeds the at-a-glance stats, the editorial-highlight one-liners, the how-to-read briefing, the methodology, and the companion-file pointers. Built for Aisha + two colleagues on M4 Air-class machines; ~2.3 MB; opens straight from `file://`. Original artefacts retained in the same folder for grep / spreadsheet / external GIS use cases.

**126 tests total**, all green.

---

## Next

### Immediate (this/next session)

- **Findings extraction across the remaining with-docs apps.** Top-100 doc coverage now sits at **94/100 with docs + 5/100 tagged duplicates = 99/100 resolved**; 35 apps have findings. The Hillingdon condition-discharge tail (Ark Project Union family — ~20 apps) is mostly procedural and yields modest findings each; the Glasgow university-campus cluster (rank ~40-67) hasn't been touched and may need a Glasgow cohort. **Editorially valuable next batches**: any 100+ MW app not yet covered, anything in the AI / Council-led LDO cohorts, anything with substantive consultee response content (`.msg` files in the Idox bundles).

- **Long-tail portal adapters** for the worklist apps still without docs. The 2 remaining genuine gaps in the top-100 (Slough's 2026 SMI which is too new to have docs anywhere, and a handful of mid-rank apps on portals not yet sampled — Arcus, EnterpriseStore, PlanningExplorer for some councils). When journalism need warrants a fuller sweep, build the Arcus adapter first (Milton Keynes, Epping Forest) — Arcus is reasonably common across UK councils.

- **Idox adapter improvement — handle OMT-viewer `docKey=` links.** Current adapter conservatively skips these, missing site plans / elevations / drawings (~half the doc set for many apps). The user's manual STPLF backfill recovered 16 such docs that the automated fetch missed. Worth re-running the Idox top-100 sweep after the fix.

### Soon

- **Promote `associated_id` to a typed `applications.parent_ref` column.** Parent-backfill confirmed the field is reliable; a typed column makes family-navigation queries a direct join instead of JSONB extraction. ~30 min of schema + retrofill work.

- **CI on GitHub Actions** (now feasible since the project is Apache 2.0 and tracked). Run `pytest -m "not integration"` on every push. ~1–2h.

- **Triage round 2 with refined rubric** (depending on Aisha's editorial-narrowing decision — see Open Questions below). Either narrow to *primary on-site gas* (sharper, rarer story) or *outsized backup-but-grid-services capacity* (more common, softer story), and re-run with the tighter prompt. The cohort-driven export now provides editorial filtering even without retriaging, so this is less urgent than it was pre-Phase-4.

---

## Parked

Items consciously deferred — return when journalism need warrants.

- **DC01 (the one unidentified Foxglove case).** Foxglove's report names a 320 MW DC outline approved 2025-02 with implausibly low emissions but no council / developer / address. Three of the four originally-unidentified Foxglove cases have been resolved; DC01 is the remaining one. Most likely identifiable once we sweep operator-name expansions for hyperscaler-affiliated SPVs.

- **Salesforce adapter.** Originally planned for Epping Forest's Loughton case, but PlanIt's Arcus scraper covers Epping Forest, so the Salesforce frontend can be ignored. Revisit only if we encounter a Salesforce-only council not in PlanIt.

- **NSIP / Section 35 Directions adapter (gov.uk-search-API half).** The NSIP CSV is built; the gov.uk Section 35 Directions discovery half is research-only (see `data/nsip_research/findings.md`). Build when journalism warrants or when a second DC Section 35 Direction appears.

- **Direct council-portal index adapters** (beyond what PlanIt covers). MHCLG "Find a Planning Application" is the alternative national source. Not urgent given PlanIt's depth; useful as a cross-validation source pre-publication.

- **`other_fields` normalisation.** PlanIt records carry applicant_name, agent_company, applicant_address in JSON inside `raw_metadata`. Worth promoting to dedicated columns if we run a meaningful operator-name sweep beyond what's already done.

- **Pre-2018 broader-keyword backfill.** PlanIt's coverage thins sharply before 2018. The parent-backfill already pulled in pre-2018 substantive parents; a separate broader-keyword sweep would catch pre-2018 cases that don't have a child in our window. Worth a separate sweep if the story angle needs it.

- **Document corpus mirror.** `data/raw/` is local-only and growing (~12 GB after the Phase 4 + manual-ingest round). Candidates for a public reproducibility mirror: zenodo (DOI, academic-friendly, CC-BY), S3 (paid, more control), academictorrents. Decide once corpus stabilises in size and publication-day workflow is clear. See [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md).

- **Phase 5 — multimodal pass.** Originally planned as Claude vision on site plans / elevations for the matched subset. **Downgraded to a conditional, probably-won't-do.** The Phase 4 sweep confirmed nearly all PDFs in the corpus have text layers, so the regex pre-pass + Read-tool extraction already surfaces what's labelled. Vision would only add value if (a) labels are rasterised into a drawing tile rather than the PDF text layer, *and* (b) we have an app where we suspect on-site generation but text extraction came up empty. Anything an applicant genuinely wants to conceal won't be in the drawings at all. Revisit only if a specific app hits both conditions. If pursued, the multimodal pass writes to the same `findings` table under a different `model` string (e.g. `claude-opus-4-7+vision-batch`).

---

## Open questions

Things we haven't decided yet, with current thinking where there is one.

- **Triage rubric scope.** The current prompt leans inclusive across both *primary on-site gas* and *outsized backup-but-grid-services capacity* (`worth_deep_read='yes'/'maybe'` on either signal). Now that the cohort export provides editorial filtering downstream of triage, the urgency on narrowing has dropped. Still worth a conversation with Aisha about whether to re-run a tighter rubric or just continue iterating cohort definitions.
- **"energy centre" sweep.** 9,061 PlanIt hits — far too noisy for direct ingestion, but the term *is* the coded-language signal (granite4.1:30b already extracts it as a signal when it appears). Either run as a separate triage-heavy pass or rely on the in-document signal during deep-read. Probably both.
- **Findings extraction at scale.** The current 35-app set was extracted human-in-the-loop via Claude Code's Read tool. A systematic top-100 → top-300 sweep would need either (a) continued in-session iteration (cheap, slow, judgement-rich), (b) Anthropic SDK + Sonnet 4.6 batch (faster, repeatable, less rich), or (c) a hybrid where SDK does a first pass and human-in-loop refines the editorially-loudest. Worth picking a path before the next big push.
- ~~**Browse UI shape (if any).**~~ **Resolved 2026-05-17.** The integrated viewer in `dcp/reader.py` is the static-site answer to this question — single-file HTML with bidirectional card-and-map sync, search, and filters. No server, no build step, no dynamic deps. Matches the access pattern as predicted.
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
| 3 — Document fetch | ✅ Top-100 done | Idox + Ocella sweeps; manual ingest covers the long-tail portals. Top-100 doc coverage 94/100 + 5 duplicates resolved = 99/100. |
| 4 — Structured extraction | ✅ v1 Done | Text-cache + regex pre-pass + delta classifier; 35 apps with findings, ~225 findings total under model `claude-opus-4-7+read-tool`. Editorial highlights + cohorts + filtered audit list shipped in the markdown + xlsx export. |
| 5 — Multimodal pass | 🚫 Probably won't do | Originally planned vision pass on site plans / elevations. PDFs are overwhelmingly text-layered, so vision adds little; concealed plant won't appear in drawings at all. Revisit only if a specific app needs it. |
| 6 — Reporter export | ✅ Done (v2) | Markdown + xlsx restructured around editorial cohorts, highlights, and filtered-out audit list; KML + interactive HTML map with OSM power-plant overlay unchanged. |
| 7 — v1.0 release pipeline | ✅ Done (2026-05-17) | `dcp release --version` orchestrates a versioned per-release folder with the integrated viewer (split-screen card + map) as the headline artefact, plus the text-only / xlsx / standalone-map companions in `Map data/` and `Self-scrutiny/` subfolders. All eight story-readiness checklist items resolved. |
