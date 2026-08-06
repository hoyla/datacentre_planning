# Roadmap

Where the project stands, what's next, what's parked, and what's open.

For *how the system is shaped*, see [ARCHITECTURE.md](ARCHITECTURE.md).
For *why we're doing this and what's been published*, see [prior_art.md](prior_art.md).
For *post-publication flip mechanics*, see [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md).

Last meaningful update: 2026-08-02 (Barbour ABI ingest — the start of the v2 "datacentre build" dataset).

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

### Phase 8 — Barbour ABI ingest, v2 dataset kickoff (Aug 2)

Direction agreed with Luke 2026-08-02: **one database, new dataset.** The v2
focus narrows to datacentre *build* applications (v1 was DCs + adjacent power
sources); it ships as a new universe within the existing DB rather than a
fresh one. Barbour ABI data is licensed for use with credit; pre-2018 "Built"
estates are in scope this time; role-block PII is handled by the Guardian
data journalists under the editorial code.

- **Migration 005** — `projects` (commercial construction-intelligence
  records, Barbour `Ptno` as external_ref, verbatim row in raw_metadata) +
  `project_applications` (many-to-many, `match_method` per link, ambiguous
  bare refs never auto-linked).
- **Barbour adapter** (`dcp/sources/barbour.py`, `dcp index --source barbour
  --file <xlsx>`). Snapshot-first, idempotent. Inaugural ingest of the
  2026-08 export: **253 projects, 149 auto-linked to existing applications
  (ref_suffix), 60 unmatched refs, 44 no-ref rows** (pre-planning schemes +
  fit-out/civil contracts + tender notices). The sheet's own "Luke has?"
  coverage column was wrong in 89 cases — always re-derive coverage.
- **Gap post-mortem** (`scripts/barbour_gap_postmortem.py`) — classified all
  60 unmatched refs via PlanIt `id_match` lookups (cached in
  source_snapshots, authority-checked because bare refs collide
  nationally). Result: **31 pre-2018** (window artefact, now in scope),
  **13 no-DC-keywords** (descriptions never say "data centre" — reserved
  matters / generic B2-B8 wording; incl. Graven Hill 435MW, Google Waltham
  Cross, LCY20, NTT LON2-A), **7 tender notices**, **5 not in PlanIt**
  (Slough T/-era refs, Hounslow, Wirral, and Cambois 25/02911/REM — recent,
  PlanIt lag), **3 authority quirks** (MidKent shared service ×2, one
  Barbour authority error), and just **1 genuine in-window keyword escape**
  (Fife/26/01243/PPP, started 2026-04-29 — likely PlanIt scrape lag at
  sweep time). Verdict: the v1 sweep methodology held up; the gap is
  overwhelmingly the 2018 window plus keyword-blind descriptions. Report at
  `data/new_lists/barbour_gap_postmortem.md`.

- **OCR fallback for scanned-only pages** (`dcp/extract.py`, 2026-08-02).
  Measured on the Barbour-round fetch: ~5% of documents have no text layer
  (mostly clean typed council forms — e.g. the Fife notice recording that
  Queensway Park Data Centres Ltd commenced development Dec 2020). Pages
  whose pypdf text is under 25 chars now fall back to OCR via pypdfium2 +
  a **non-generative engine** (deliberate: the OCR text is the
  verbatim-quote verification substrate and must fail noisily, never
  fluently — a VLM's plausible hallucination would let invented quotes
  verify). Default engine `tesseract` (empirically better spacing/reading
  order on English forms); `rapidocr` available as alternative. Per-page
  OCR use recorded in the cache (`ocr_pages`) + engine string
  (`pypdf+tesseract`) for audit.

**146 tests total**, all green.

---

## Next

### Done 2026-08-05/06 — acquisition campaign, adapters, single store

The 2026-08-03 queue below is largely discharged; what actually happened:

- **Acquisition campaign complete.** 605-application cohort (DC-verdict,
  zero documents) swept host-parallel; corpus **7.4k → 27k documents**,
  DC-verdict applications holding documents **99 → 501 of 705**. Manifests
  at `data/raw/_dc_campaign_*.json`.
- **Four new portal adapters**: Agile (JSON API behind an Angular shell;
  also the only source giving structured applicant/agent names), Arcus
  (two register generations, two disclaimer mechanisms — terms reviewed
  and accepted 2026-08-06), Salesforce public registers and the Newport
  external docstore (both hybrid: browser-harvested listings, plain-HTTP
  bytes). Amazon Didcot (10 applications, 609 documents) came in via
  Arcus; Newport yielded 895 documents its Idox tab reports as an error.
- **Single document store.** `data/raw/documents/<application_ref>/` with
  one manifest per application; acquisition method recorded per document
  rather than encoded in the directory path. `data/raw/manual/` is the
  inbox for hand-obtained bundles (`scripts/ingest_inbox.py`).
- **Sites materialised** (migration 006): 391 sites with stable keys.
- **Still blocked, needs manual acquisition**: Northgate (403 to any
  client), NEC/LPAssure (human check), Wychavon (TLS-fingerprint block —
  all 7 applications since obtained by hand, 305 documents). Priority
  manual list: Elsham Wolds 1GW (£10bn), Gwynedd Ferodo, Anglesey,
  Epping Forest.

### Handover design (agreed with Luke, 2026-08-06)

Audience is the Guardian **data and visuals teams**, not a single
reporter: the deliverable standard is *well-defined data*, not good
examples. Structure agreed:

1. **Source documents to a Guardian-owned Google Drive**, organised by
   site, with human-readable derived filenames (the canonical store keeps
   content-hash names) and each folder's manifest rendered as a readable
   index. Regenerable by sync, never a one-off upload.
2. **The handover workbook** (`scripts/export_handover.py`) as the
   interface: Sites and Applications tabs linked by `site_key`, generated
   from the database, never hand-maintained; annotations live in a
   separate tab so regeneration cannot clobber them.
3. **Per-site markdown reports**, generated from the same data, doubling
   as NotebookLM source material.
4. **Pinpoint / NotebookLM** as *lead generators only* — anything found
   there re-enters the dataset through the verification gate (document,
   quote, round-trip check), never directly.
5. **The viewer last**, as a visualisation and exploration tool for the
   reporting teams — explicitly not a source of truth.
6. **Data dictionary and methodology** ([docs/data_dictionary.md](docs/data_dictionary.md),
   [docs/methodology.md](docs/methodology.md)) at the Drive root *and* as
   website pages.
7. **Versioned releases** mirroring the v1 convention; additive, nothing
   overwritten, so "which version did you query?" always has an answer.
8. **Queryable export** (DuckDB/SQLite) alongside the workbook, for
   journalists who want to run their own queries.

Publication-grade validation (a stratified adjudication of sweep output)
may be run by the data team themselves — so exports must carry
**adjudication affordances**: every verdict travels with the rubric,
prompt version, enrichment flag and the exact rendered input the model
saw (`triage.raw_response`), plus the class definitions as a data
dictionary.

### Immediate (this/next session) — v2 dataset pipeline

- **Ingest the missed applications.** From the post-mortem classes: fetch
  the in-PlanIt misses via `id_match` (tag
  `discovered_via=['barbour:<Ptno>']`), and portal-resolve the
  not-in-PlanIt tail (incl. Jersey — outside PlanIt's coverage entirely).
- **Pre-2018 "Built" backfill.** Now in scope (decision 2026-08-02). The
  ~29 legacy estates with pre-2018 refs (Google Waltham Cross, Telehouse,
  Interxion, Virtus London, Cody Park...) need PlanIt/portal ingestion and
  document-availability assessment — councils purge old documents, so
  record gaps honestly rather than dropping rows.
- **`dc_build` universe + rubric.** New triage rubric ("is this a datacentre
  build application") under a new model string; universe membership tagged
  via `discovered_via` (or a first-class `universes` table if tags strain).
  The v2 release pipeline exports only that universe.
- **Agile Applications adapter** — 12 Barbour links point at
  `planning.agileapplications.co.uk` (Slough among them); it was already
  the top long-tail portal. Then SwiftLG (9) and PlanningExplorer (8).

### Locked 2026-08-03 (adjudication session) — v2 execution order

The dc_build trial ran end-to-end and was adjudicated conversationally
(16 contested rows; rules and scores in
[data/triage_labelling/rubric_dc_build.md](data/triage_labelling/rubric_dc_build.md)).
Architecture locked: **Sonnet 5 catalogues metadata** (~$15 one-off,
42/50 vs granite-enriched 39/50), **local granite + Claude Code
escalation deep-reads documents** behind the verbatim-quote gate, and
**100% of candidate DC sites get deep-read** — triage demoted from
gatekeeper to cataloguer. Queue for the next session:

1. Relaunch the idempotent Barbour-round retry fetch (session-bound).
2. Idox `docKey=` OMT-viewer fix, then the acquisition campaign: 400
   Idox/Ocella applications fetchable today (606 of 705 DC-verdict
   applications lack documents); adapters in coverage order Agile (64)
   → Arcus (41) → Salesforce/Northgate/NEC (27); bespoke 73 by site
   value. Status-refresh pass rides along (a stale 'Undecided' hid a
   Bedford refusal); "documents unobtainable" tracked as an outcome
   class (LCY20: £200M, zero public documents — FOI candidate).
3. Prompt v2.1 (fold the five adjudication rules), then the Sonnet
   catalogue sweep over the full universe.
4. Geocode the 74 unlocatable sites; add the 2.5 km review band (5 km /
   evidence-only on linear terminology) to the superset script.
5. Per-site deep read rolls as coverage completes.

**Prompt v2.2 tried and rejected (2026-08-06).** Widening the model's
signal vocabulary to environmental subjects, and widening
`worth_deep_read` to match, cost two points on the adjudicated set:
45/50 against v2.1's 47/50, with the loss entirely on the
invisible-from-description rows that depend on the association rule
(9/10 → 7/10). Visible rows were unchanged at 38/40. Reverted to v2.1.

The requirement was met a better way: environmental subjects are
extracted **deterministically** from descriptions ([dcp/signals.py](dcp/signals.py))
— reproducible, free, and carrying no risk to a validated prompt. Eight
families (water, air, designated sites, ecology, flood/drainage, land
quality, noise, heat). Like the EIA indicator this is a **floor**:
descriptions are terse and the substantive environmental content lives
in the documents, which deep-read covers.

**Adjacency investigation — the bottleneck is ingestion, not the prompt.**
The reporting team asked whether the parties behind nearby power
generation are connected to the data-centre developers. No prompt can
classify an application that was never ingested, and the universe was
built from data-centre keyword searches: a peaker or BESS a kilometre
from a campus that never says "data centre" may be absent entirely (the
YEP gas reserve is the canonical case, caught by luck of another
discovery path). [scripts/sweep_site_energy.py](scripts/sweep_site_energy.py)
searches the energy lexicon around all 391 sites at the 2.5 km review
band, tagging finds `discovered_via='site_energy:<site_key>'`. Party
data itself falls out of deep-read; a partial view exists today from
Agile's structured fields.

### Pondering (Luke, 2026-08-02, pre-decision — superseded above where they overlap)

Raised after the Barbour reconciliation; to decide together before the next
big push:

- **Corpus re-fetch.** Not a blanket re-download — the archive is
  content-hashed and append-only, so re-runs only add. But: (a) the ~62
  newly ingested applications have no documents; (b) the Idox OMT-viewer
  `docKey=` fix would roughly double the drawing/plan coverage for many
  already-fetched applications; (c) live applications have accumulated new
  consultee documents since May. Recommended order: fix Idox docKey → re-run
  fetch across the enlarged dc_build worklist → Agile adapter → the 4
  portal-only captures (Slough SPZ ×2, Cambois REM, Wirral).
- **Re-extraction round 2 (all documents, smarter lexicon).** Append-only
  findings make this cheap and safe (new model string; v1 rows retained).
  New signal vocabulary learned since v1: "technical services centre"
  (2008-era coding, LCY20), B8/B2-shed framing, SPZ/LDO/scoping consenting
  routes, grid-connection companions, plus Barbour's per-site MW/value
  priors to validate extraction against. Scale decision still open: batch
  SDK first-pass + human-in-loop review of the loudest findings is the
  leading option (quote round-trip verification automated at insert, per
  the established rule).
- **Reporter spreadsheet exports with dual provenance links** — every row
  linking both the archived file (`documents.bytes_path`) and the live
  portal URL (`documents.url`), with the archive as the durable copy and
  portal links best-effort. Mostly an export-layer change; the schema
  already carries both.

### Carried over from v1

- **Findings extraction across the remaining with-docs apps.** Top-100 doc coverage now sits at **94/100 with docs + 5/100 tagged duplicates = 99/100 resolved**; 35 apps have findings. The Hillingdon condition-discharge tail (Ark Project Union family — ~20 apps) is mostly procedural and yields modest findings each; the Glasgow university-campus cluster (rank ~40-67) hasn't been touched and may need a Glasgow cohort. **Editorially valuable next batches**: any 100+ MW app not yet covered, anything in the AI / Council-led LDO cohorts, anything with substantive consultee response content (`.msg` files in the Idox bundles).

- **Long-tail portal adapters** for the worklist apps still without docs. The 2 remaining genuine gaps in the top-100 (Slough's 2026 SMI which is too new to have docs anywhere, and a handful of mid-rank apps on portals not yet sampled — Arcus, EnterpriseStore, PlanningExplorer for some councils). When journalism need warrants a fuller sweep, build the Arcus adapter first (Milton Keynes, Epping Forest) — Arcus is reasonably common across UK councils.

- **Idox adapter improvement — handle OMT-viewer `docKey=` links.** Current adapter conservatively skips these, missing site plans / elevations / drawings (~half the doc set for many apps). The user's manual STPLF backfill recovered 16 such docs that the automated fetch missed. Worth re-running the Idox top-100 sweep after the fix.

### Pre-planning and non-council consenting routes (raised 2026-08-06)

Prompted by the **Devon Data Campus** (Xlinks, North Devon —
[devondatacampus.com](https://www.devondatacampus.com/), BBC coverage
Aug 2026): a scheme with an active public-engagement campaign of which
the corpus holds **nothing at all**. Zero matches for Xlinks, Valeon,
Alverdiscott or Devon Data Campus; the only Devon data-centre records we
hold are Exeter College's built teaching facility and two small Plymouth
items. Three distinct gaps, in rising order of effort:

1. **Operator watch-list sweep** (cheap). Add Xlinks and Valeon — and
   review the list generally — then run a name-based PlanIt sweep on
   `developer`. Catches the application the day it is validated rather
   than whenever we next look. Same mechanism as the existing
   operator-name expansions.

2. **Direct council-register checks** for pre-application and screening
   entries (Torridge, North Devon here). Councils routinely publish EIA
   screening and scoping requests, and Scottish PANs, *before* any
   application exists — our universe starts at submission, so this class
   is structurally invisible to us. Worth deciding whether pre-planning
   entries become first-class universe members or a separate watch table.

3. **NSIP ingestion from the Planning Inspectorate** (the structural
   fix). Nationally significant infrastructure is consented by PINS, not
   councils, so it never appears in PlanIt at all. Xlinks' Morocco–UK
   interconnector — whose UK landing point at Alverdiscott is plausibly
   *why* a data campus is proposed there — is an NSIP, as is the
   already-noted `EN0110030` data-centre campus reference we hold with no
   council URL. Any data centre attaching itself to an NSIP power project
   is currently invisible on both sides of the join. Design question to
   settle first: an NSIP is a single "project" spanning hundreds of
   kilometres and many authorities, which the 1 km spatial clustering
   rule handles badly — likely wants its own node type and
   evidence-based (not proximity-based) association.

This also sharpens the **adjacency** work: `adjacent_power` currently
holds only ~15 applications universe-wide, which is implausibly few and
consistent with power schemes near campuses being absent from the
corpus rather than merely misclassified.

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
- **PlanIt rate-limit politics.** PlanIt is donation-supported and friendly; we are a heavy user. Worth reaching out to them at some point — both as good citizenship and because they may have insights about coverage gaps. Now particularly relevant: the document-fetch stage hits *council portals* directly, not PlanIt, but the operator-name sweep + spatial sweep do hit PlanIt heavily. **Observed 2026-08-02: PlanIt now 429s far more aggressively than during the May sweeps** — ~21 requests at 2.5 s spacing exhausted the quota, and the full 60/120/240/480 s backoff ladder still hit 429s. Assume an hourly quota; plan sweeps at ≥10 s spacing with cool-off resumes (the snapshot cache makes resumes free). Strengthens the case for the courtesy email before the next big sweep.

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
| 8 — Barbour ABI ingest / v2 kickoff | ✅ Ingest done (2026-08-02) | Migration 005 (`projects` + `project_applications`), Barbour adapter, inaugural ingest (253 projects / 149 linked), gap post-mortem. Next: missed-application ingestion, pre-2018 Built backfill, `dc_build` universe + rubric, Agile adapter. |
