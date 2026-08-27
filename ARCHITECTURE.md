# Architecture

The shape of the system as it is: the schema, the pipeline, and the
design principles it is held to. This document describes what exists —
*what is still to do* lives in [ROADMAP.md](ROADMAP.md), and what was
built and decided, including what was tried and rejected, in
[HISTORY.md](HISTORY.md).
For *why a journalism investigation needs this*, see [prior_art.md](prior_art.md) and `data/seed_cases/walkthrough_findings.md`.

---

## Philosophy

Seven principles, in order of importance:

1. **Ingest broadly, analyse second.** Don't bake the hypothesis into the extraction. Decisions about what's worth a story happen downstream of structured facts, not upstream of them. We need to be able to surface null findings and counter-evidence, not just dramatic ones.
2. **Defensibility.** The reporting must be defensible end-to-end — every aggregate claim must be drillable back to the underlying source material so a journalist (and where necessary, a reader) can see exactly how a conclusion was reached. This is the editorial reason behind several of the engineering principles that follow.
3. **Never mutate original source material.** Where normalisation or probable links are needed (e.g. council-name canonicalisation, fuzzy-matching applicants to operators, mapping legacy district names to current GSS codes), store the normalised / inferred value *alongside* the original — never overwrite. The raw response and the raw record are the canonical references the rest of the system points back to.
4. **Append-only with audit trail.** `source_snapshots` preserves every raw fetch. `triage` and `findings` are versioned by `inserted_at` rather than overwritten. Reruns add rows; nothing is destroyed. This makes re-analysis with refined prompts cheap and reproducible, and is the engineering corollary of (2) and (3).
5. **Idempotent at every stage.** Reruns are no-ops on unchanged content. PKs and unique constraints (`(source_id, application_ref)`, `(source_id, key, content_sha256)`, etc.) are the dedup contract. Cache-based resume means a partial sweep can be completed without re-fetching captured pages.
6. **Look at the data before committing infra.** Hands-on exploration of every new source (manual API calls, sample documents) before adapter code is written. The seed-case walkthrough and the PlanIt exploration both produced design changes that wouldn't have come out of upfront planning.
7. **Provenance is non-negotiable.** Every claim in `findings` carries a document reference, evidence text, page number, model name, and timestamp. Reporters can't use what we can't back to a quotable source. Aggregate outputs (markdown summaries, xlsx exports, any future static-site build) must always link or cite back to the underlying `findings` / `documents` / `applications` rows, never present numbers without provenance.

---

## The pipeline

```
INDEX  →  TRIAGE  →  DEEP-READ  →  SITES  →  ADJUDICATION  →  RELEASE
```

Each stage is idempotent and resumable. Each writes to a separate table
family. They communicate only through Postgres, not in-memory state — so
a stage can be re-run in isolation without re-doing earlier work. The
first three build the corpus; the last three turn it into the thing a
reporter opens, and their ordering constraints and traps are the
regeneration runbook
([docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md)).

### 1. Index

Per source, paginate the recent-applications feed (or equivalent), upsert structured metadata into `applications`, preserve the raw response in `source_snapshots`.

Implemented: PlanIt (`dcp/sources/planit.py`, including the parent-application backfill and operator/spatial sweeps), NSIP CSV (`dcp/sources/nsip.py`), Barbour ABI xlsx (`dcp/sources/barbour.py` — file-based, `dcp index --source barbour --file <xlsx>`; ingests construction projects into `projects` and links them to applications by reference), and the Section 35 watcher (`dcp index --source s35` — the gov.uk publication feed, keyed on publication slug, deliberately fetching the *fact* of a direction rather than its attachments; HISTORY 2026-08-25).

### 2. Triage

For each application without a recent triage verdict under the current
rubric, ask an LLM to classify it. Verdicts are versioned per
`(application_id, model, inserted_at)` **and per rubric**: the v1 rubric
(is this a data centre; model granite4.1:30b, prompt frozen 2026-05-14)
and the dc_build rubric (the truth-based classes: `new_build`,
`expansion_refurb`, `built`, `adjacent_power`, `procedural`, `unknown`,
`not_dc`; model claude-sonnet-5) coexist as generations, and universe
membership reads the latest verdict *per rubric* — an application is
in-universe if either generation calls it datacentre-related, which
under dc_build is every class except `not_dc`. `procedural` and
`unknown` are kept deliberately: a conditions discharge belongs to its
parent's site, and a disguise suspect is precisely what must not be
dropped. The rubric lives in `data/triage_labelling/rubric.md`; the
five adjudication rules and the trial that chose the sweep
configuration are in HISTORY (2026-08-03).

### 3. Deep-read

For triage matches, fetch the full document bundle from the source portal (or aggregator's links), dedupe by content hash, extract text (OCR fallback when no text layer), surface power-related signals into `findings`.

Two-stage extraction per the seed walkthrough:
- **Stage 1** (cheap): from description + consultee senders alone, before opening any document. Northern Gas Networks as a consultee → high gas-infrastructure prior.
- **Stage 2** (per-document): structured fact extraction with evidence-text capture. Generator counts, fuel type, rated capacity, on-site CHP mentions, fuel-storage hours.

A multimodal pass (Claude vision on site plans and elevations) was originally planned as Phase 5; rejected after the Phase 4 sweep — see [HISTORY.md](HISTORY.md). Vision can only see what's drawn and labelled; concealed plant won't appear in the drawings, and labelled plant is already text-extractable.

**Document-fetch adapters**, one module per portal family under
`dcp/sources/`, all dispatched by `scripts/fetch_outstanding.py` (which
works from `acquisition_outcome` rather than from the absence of
documents, so a settled negative leaves the queue and a transient error
stays in it):

- **Idox** ([dcp/sources/idox.py](dcp/sources/idox.py)) — canonical and `/newplanningaccess/` variants; SSL chain reconstruction via `truststore` unblocks councils sending incomplete chains. The polite-client base the other adapters share.
- **Ocella** ([dcp/sources/ocella.py](dcp/sources/ocella.py)) — Hillingdon, NorthLincs and others.
- **Agile**, **Arcus**, **aifusion**, **Salesforce** ([dcp/sources/](dcp/sources/)) — the 2026-08 portal families; Salesforce fetches against browser-harvested listings, Arcus handles both disclaimer variants.
- **Northern Ireland** ([dcp/sources/ni_planning.py](dcp/sources/ni_planning.py)) — the whole-nation register via its own anonymous API (2026-08-27; docs/PORTAL_NOTES.md has the route map).
- **Newport docstore** (`scripts/fetch_newport_docstore.py`) — documents held off the documents tab.
- **Manual** (`scripts/ingest_manual_docs.py` + [dcp/sources/manual.py](dcp/sources/manual.py)) — for one-off portals: files dropped per application, hashed, recorded via `repo.record_document`, **preserving any adapter-recorded URL** rather than overwriting with `file://`.
- **Browser-assisted** (`scripts/browser_receiver.py`) — a loopback sink for portals that only serve a real browser; the page POSTs each document to it. Rules and per-portal routes in [docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md).

Per-application `_manifest.json` is the hand-over signal across every
transport, and `repo.record_document` is the single gate every path
passes through — which is where the zero-byte guard lives (an empty
body is a failed fetch, never a document).

#### Reading at scale — the current shape

The corpus is deep-read by three model families, every finding behind
the same **verbatim-quote gate**: an extracted quote must appear in the
document's cached text or the finding is rejected, which makes the gate
— not the model — the hallucination protection. Each finding records
its model; the three coexist in the append-only store (GPT-5 on the
OpenAI Batch API, Claude Sonnet, and Qwen under MLX on the Studio).
Standing policy (2026-08-26): **the local reader is a phase-3 second
opinion and never the first read of anything** — the label audit
measured it misfiling the power families at up to 68% against Sonnet's
9%. New content's first read is `scripts/deepread_escalate_openai.py
--cohort first_read`; the Studio runs the corroboration pass
(`scripts/deepread_run.py`), whose deliverable — the corpus-wide
comparison where a disagreement is the finding — is still owed
(ROADMAP). Findings carry a `signal_family` (derived where a model
did not supply one, `family_source` saying which), and a label audit
(`finding_label_audit`) demotes misfiled rows at render with a "[filed
as X]" marker — moves, never deletes.

#### Stage-2 extraction as first built (v1, kept for the record)

The `findings` table (migration 001) holds one row per `(application_id, document_id, signal_type, model, inserted_at)`, with `value_text` / `value_number` / `value_unit` for structured facts, `evidence_text` + `evidence_page` for the supporting quote, and the model name for auditability. Append-only / versioned — re-extraction with a refined prompt adds rows; nothing is destroyed.

**Document formats in the corpus** (from the inaugural top-100 sweep):
- ~2,850 PDFs (dominant; text-layer present on most modern ones, OCR fallback needed for older / scanned-only).
- ~52 `.msg` Outlook emails (consultee responses — the EA-letter category Aisha flagged as editorially critical). Needs `extract_msg` or `mail-parser` dep.
- ~50 `.docx` / `.doc` / `.rtf` (Word / RTF — pypdf doesn't handle; need `python-docx` and `striprtf`).
- ~10 `.xlsm` / `.xlsx` (rare — likely emissions or capacity calculation worksheets; `openpyxl` already a dep).
- ~10 image files (JPEGs of site-plan extracts; not currently processed — see the multimodal-pass note below).

PDF parsing alone covers ~92% of files; long-tail loaders are still a follow-on.

**Extraction pipeline** ([dcp/extract.py](dcp/extract.py) + [dcp/findings.py](dcp/findings.py)):

1. **Per-file text extraction** — pypdf for PDFs, cached at `data/raw_text/<source>/<application_ref>/<sha[:16]>.pages.json` (page-indexed JSON). Pages with no usable text layer (~5% of the corpus, measured Aug 2026 — scanned council forms plus image-only pages *inside* text-layered documents) fall back to OCR: pypdfium2 rendering at 300 DPI + tesseract by default (RapidOCR as the alternative engine). Both engines are deliberately **non-generative** — the OCR text is the substrate the quote-verification gate checks against, and it must fail noisily (garbage characters) rather than fluently (a VLM's plausible hallucination would let an invented quote verify). OCR'd page numbers are recorded per document in the cache (`ocr_pages`) and surfaced in the verification report. LLM step is decoupled from parsing — either can be re-run. Backfill across pre-existing caches: `scripts/ocr_backfill.py`.
2. **Regex pre-pass** — `extract.find_candidates` surfaces high-signal sentences against patterns for MW capacity (`\d+(\.\d+)?\s*(MW|kVA|kW)\b`), generator counts (`\d+\s*(diesel|gas|emergency|standby|back[- ]up)\s+generators?\b`), and fuel storage hours / litres / tonnes. Deterministic; produces candidate windows for the LLM step.
3. **LLM extraction** — in v1, human-in-loop via Claude Code's Read tool acting as the LLM (`model=claude-opus-4-7+read-tool`); superseded by the batch readers above. The Read tool opens the cached page-JSON, the model identifies structured facts + the literal evidence quote + the page number, and `scripts/extract_findings.py` records them via `repo.record_finding`. The same shape (decoupled from parsing, cached text inputs, append-only rows) makes a later switch to a batch SDK pass a drop-in.
4. **Delta classifier** ([dcp/findings.py](dcp/findings.py): `classify()`) — compares each finding against the application's `triage.signals` array and the description text. Three categories per the original design:

   | Category | What it is | Rendered? |
   |---|---|---|
   | **NEW DISCLOSURE** | Quantitative facts or named kit absent from the description (e.g. "18 × Caterpillar 3516B diesel generators, 45 MW peak"). The editorial signal. | Yes |
   | **REFINEMENT** | Qualitative signals the description hinted at, sharpened with documents (e.g. "energy centre" → "12 MW gas-fired CHP, twin Jenbacher J620 engines"). | Yes |
   | **CONFIRMATION** | Findings that match a triage signal exactly. | Omitted as noise |

   A short refinement-vocab set (`facility_classification`, `plant_configuration`, `grid_services_role`, `fuel_type_detail`) drives the qualitative side; quantitative findings (MW, generator counts, fuel volumes) default to NEW DISCLOSURE.

5. **Multimodal pass on site plans / elevations** — originally planned as Phase 5; rejected (see [HISTORY.md](HISTORY.md)). The Phase 4 sweep confirmed PDFs in the corpus are overwhelmingly text-layered, so the regex pre-pass + Read-tool extraction already surfaces labelled kit. Vision can only see what's drawn and labelled; concealed plant won't be in the drawings at all.

**Provenance discipline (principle 7)**: every `findings` row carries the source `document_id`, the exact `evidence_text` quote, the page number where it appeared, the model that extracted it, and the timestamp. The reporter export links each rendered finding back to the source filename + page; aggregate counts (e.g. "disclosed MW" in the xlsx) are derivable from the underlying rows.

**Resume / idempotency**: parallel to the triage path. Re-extraction with a refined model name adds rows; the export reads the latest per `(application_id, document_id, signal_type, model)` tuple.

### 4. Sites

A *site* is the unit the investigation reasons about: a cluster of
applications and Barbour projects joined by project links, family edges
(`associated_id`, with a stricter description fallback), or spatial
proximity within 1 km. `dcp/sites.py` builds the clusters and
`scripts/materialise_sites.py` writes them to `sites` /
`site_members` — stable keys (`PTNO-<lowest Ptno>`, else
`SITE-<first ref>`), recomputable membership, retire-and-revive rather
than delete. Two hand-adjudicated priors correct what the radius cannot
see, both failing the run on an unknown reference rather than weakening
silently: `data/priors/site_partitions.yaml` (campus boundaries —
partitioned nodes take no spatial edge outside their partition, while
documentary edges extend it, and a documentary edge joining two
partitions is surfaced, never resolved) and
`data/priors/inferred_coords.yaml` (coordinate priors, each with its
derivation). `preflight()` states what a materialise would change —
including any hand-matched claim it would orphan — before it changes
it.

### 5. Adjudication

Extraction asks what a document says; adjudication asks **whose figure
it is**. `power_adjudication` holds one verdict per finding per model
(`site_capacity` / `not_this_site` classes / `unclear`), append-only,
multi-model. On top of it sit the corrections
(`scripts/correct_adjudications.py`: named, idempotent rules that
demote quantity-type errors — energy-not-power, storage, thermal,
export limits — each mirrored in `dcp/adjudication_gate.py`, which
every export calls and which refuses to build over uncorrected rows
and reports the adjudication tail); the generation-figure adjudication
(basis, plant type, unit counts); and the external **capacity claims**
(`capacity_claims` / `capacity_claim_matches`: figures from Companies
House filings, operator pages, the NESO register and Environment
Agency permits, loaded as claims beside the planning data — never into
site columns — with hand matches carrying method, confidence and
evidence, and quote-verification against committed snapshots).

### 6. Release

The handover is four artefacts over one corpus, regenerated per release
by the runbook chain: the **reader** (one self-contained HTML file —
sites, applications, energy projects, map, machine readings behind
their own quote gate, methodology and data dictionary generated inside
it from the same queries as the data), the **workbook**, the **DuckDB
file**, and the **Drive tree** (per-site folders of source documents
with generated site reports and findings CSVs, hard-linked from the
canonical store, rebuilt clean and swapped so re-partitions move
folders rather than duplicating them). Documents link to our Drive copy
first with the register beside it, addressed by recorded file ID
(`document_drive_files`), never by derived path. Releases land beside
their predecessors so citations keep resolving; `scripts/release_diff.py`
diffs each build against the last release before anything deploys. The
published reader is served from Cloud Run behind Guardian sign-in;
EdgeOne redirects. CI runs the no-database test suite and drives the
committed reader on every push (`.github/workflows/checks.yml`).

The v1 editorial output — the markdown/xlsx pair, cohorts and the
integrated viewer — is in HISTORY; its append-only store and
provenance discipline are what everything above still runs on.


## Schema

Current schema is migrations 001–030 applied in order. The early ones in detail: [002_discovery_tracking.sql](migrations/002_discovery_tracking.sql) (the `discovered_via` array and the `colocated_candidates` table), [003_triage_columns.sql](migrations/003_triage_columns.sql) (Stage-1 rubric refresh — added `worth_deep_read`, `signals[]`, `why`; converted `confidence` from REAL to TEXT to match the categorical rubric), [004_council_aliases.sql](migrations/004_council_aliases.sql) (JSONB `councils.notes` + the `council_aliases` reorganisation map) and [005_projects.sql](migrations/005_projects.sql) (the `projects` + `project_applications` pair for commercial construction-intelligence records — see "Projects vs applications" below). Tables and their relationships:

```
sources        ──┐
                 │
councils         │ (gss_code FK)
                 │
                 ▼
source_snapshots │ raw audit log
                 │
                 ▼
applications     │ (source_id, application_ref) UNIQUE; (council_gss) FK
                 │
                 ▼
documents        │ (application_id, content_sha256) UNIQUE
                 │
                 ▼
triage           │ append-only, versioned per inserted_at
findings         │ append-only, versioned per inserted_at; signal_family
                 │ + family_source since 009

projects         │ (source_id, external_ref) UNIQUE — commercial construction-
                 │ intelligence records (Barbour ABI); full source row in raw_metadata
project_applications │ many-to-many link to applications, match_method per link

sites            │ stable site_key; retire-and-revive, never delete (006)
site_members     │ application/project membership, joined_via, retired_at

power_adjudication    │ whose figure is it — per finding per model,
                      │ append-only; unit_note carries correction markers (008)
finding_label_audit   │ misfiled-family verdicts; demotes at render (025)
site_machine_readings │ per-site readings behind their own quote gate,
                      │ keyed on input hash (§7b–e)
capacity_claims       │ external figures as claims, never columns (021, 030)
capacity_claim_matches│ hand matches: method, confidence, evidence, retirable
deepread_log          │ what was sent to which reader, per document
acquisition_outcome   │ per-attempt fetch verdicts; the outstanding queue
document_listing_audit│ offered-vs-held per application (026)
document_drive_files  │ the Drive file ID of every uploaded document
```

### Projects vs applications

Barbour ABI's unit of record is the construction *project*, not the planning
application — one campus maps to several applications (outline + reserved
matters + variations), and some projects map to none (pre-planning schemes,
fit-out/civil-works contracts, tender notices). So projects live in their own
table and link to `applications` via `project_applications`, with
`match_method` recording how each link was made (`ref_suffix` /
`ref_normalised` / `manual`). Ambiguous bare-ref matches (the same council
reference format in two councils) are never auto-linked — they surface in the
adapter summary for manual curation. Barbour's own portal links rot (councils
migrate portals), so `authority_name` + `planning_ref` is the durable join
key and `planning_link` is treated as a hint. Barbour data is licensed for
use with credit; the role-block contact PII in `raw_metadata` is held under
the Guardian editorial code.

Key invariants:

- `source_snapshots(source_id, key, content_sha256)` — same content fetched again = no-op insert. Different content (e.g. updated page) creates a new row.
- `applications(source_id, application_ref)` UNIQUE. ON CONFLICT updates description / dates / status / url / raw_metadata, refreshes `last_seen_at`, preserves `first_seen_at` and existing non-null `council_gss` (COALESCE).
- `documents(application_id, content_sha256)` UNIQUE — same document fetched twice doesn't duplicate.
- `triage`, `findings` are versioned, never updated. Latest by `inserted_at` is current; historical rows kept for prompt-revision comparison.
- Editorial filters (`exclude:<reason>`, `duplicate_of:<primary_ref>`, `cohort:<name>`) live as tags in the `applications.discovered_via` array — never as in-place mutations of the verdict or row. The triage verdict stays untouched (principle 3); the export reads the tags to filter and group at render time.

`raw_metadata JSONB` on `applications` carries source-specific fields we don't promote to columns (PlanIt's `app_type`, `app_size`, `associated_id`, `other_fields`, etc.). Same approach on `councils.notes`.

---

## Source adapters

Convention: one module per source under `dcp/sources/`. Each implements an `index()` function taking common kwargs (`since`, `until`, `limit`, `delay_seconds`, `resume`) and returning a summary dict. CLI dispatches via `--source <name>`.

The orchestrator pattern (see [dcp/sources/planit.py](dcp/sources/planit.py)):

1. Open a DB connection and ensure the source row exists (`repo.ensure_source`).
2. If `resume=True`, wire a `cache_get` closure that consults `source_snapshots` before any HTTP fetch.
3. Run any preparatory pass (e.g. PlanIt's areas pass to populate councils).
4. Iterate the main fetch (paged), upsert applications, record snapshots, commit per page.

Adding a new source means:

- A new module under `dcp/sources/<name>.py`.
- A wire-up branch in `dcp/cli.py`'s `index` command.
- Unit tests against mock transport (HTTP client) + integration tests against `dcp_test` if the adapter has new SQL paths.

### Parent-application backfill

A complement to the primary sweeps: procedural follow-on applications (variations of conditions, NMAs, conditions discharges, reserved matters) carry a pointer to a *parent* permission via PlanIt's `associated_id` field (and via description text). The triage rubric correctly classifies procedurals as "unrelated" because they add no new substantive content — but the pointer to the parent IS substantive content, and the parent may not be in our universe (especially if pre-2018, outside the keyword-sweep window).

The backfill pass walks `applications` for distinct `associated_id` values, cross-checks against existing `application_ref` (with council-prefix normalisation: `EPF/1165/22` vs `EppingForest/EPF/1165/22`), and fetches missing parents via PlanIt's `id_match` or a description-search. Captured parents are tagged `discovered_via=['parent_backfill:<child_ref>']`.

Same `discovered_via` array column already supports this; no schema change needed.

---

## Storage

- **Postgres** for all structured state. Raw `psycopg2` (no ORM) — matches the project conventions; queries are short and explicit.
- **`source_snapshots.raw_bytes_inline` (BYTEA)** for cached API responses — small JSON pages (~50–250 KB). Inline keeps the DB self-contained, simplifies the resume mechanism.
- **`data/`** is mostly **gitignored** (since 2026-05-14) for editorial confidentiality. Tracked exceptions: `data/operators.yaml` (operator/agent name list driving the Phase 1d sweep) and `data/triage_labelling/rubric.md` (the distilled triage methodology). Everything else — research writeups, eval outputs, cached source-portal responses, labelling samples, JSONL artefacts — is local-only.
- **`data/raw/documents/`** — the single document store, keyed by application: `data/raw/documents/<application_ref-with-slashes-preserved>/<sha256[:16]>.<ext>`, with a `_manifest.json` in each per-application directory. **Consolidated 2026-08-06** from the previous per-adapter layout (`data/raw/<source>/...`), which encoded *how* a document arrived into *where* it lives — the wrong axis. Acquisition route is a property of the fetch, not of the application: one application is legitimately served by several routes (an adapter, a hand download, a browser-obtained bundle from a portal that blocks automated clients), and the split scattered a single application's documents across folders. It also decayed — browser-obtained Wychavon documents were written under `raw/idox/` merely because that path helper was to hand, and Wychavon is not an Idox portal. How each document was obtained is now recorded per document in the manifest (`obtained`, `source_url`) and in the database. Migration: `scripts/migrate_single_store.py` (27,217 files moved and verified by re-hashing; every remaining file hashed against the corpus before the old trees were removed). Manifests regenerate from the database with `scripts/write_manifests.py`. **`data/raw/manual/`** is the inbox for hand-obtained bundles — a folder per application, ingested by `scripts/ingest_inbox.py`, which empties it, so anything sitting there means work outstanding. Content-addressed by SHA-256 so identical bytes share a hash but are still scoped per-application (the same design statement filed against two related applications lands in both directories). Local-first; lift to S3 / zenodo when corpus grows beyond local disk.
- **Path-layout quirk: prefix collisions when one application ref is a prefix of another** (e.g. `TowerHamlets/PA/15/00249` and `TowerHamlets/PA/15/00249/S` — the Section 73 variation). The slashes-preserved layout means the `/S` variant's directory naturally nests inside the parent's: the parent dir contains its own PDFs *and* a subdirectory containing the variation's PDFs. Both apps' `_manifest.json` files still distinguish their contents, and the apps are genuinely related (Section 73 = variation of the parent's conditions), so the nesting is editorially defensible. A future flat-path migration (`TowerHamlets/PA_15_00249/` etc.) would eliminate the quirk but would re-orphan every already-fetched directory, so deferred until the next clean-sheet rebuild.

---

## Politeness and rate limits

`PlanItClient` enforces:

- A configurable inter-request delay (default 2.5 s).
- Exponential backoff on 429 (60 s, 120 s, 240 s, 480 s — four retries).
- Identifying User-Agent with a contact email.

The same shape is expected for every adapter. PlanIt's rate limit appears to be a daily/hourly quota on top of per-second limits; the cache-based resume design ([dcp/repo.py:find_cached_response](dcp/repo.py)) means a partial sweep that hits the wall can be completed in a follow-up run without re-spending the budget.

---

## Cache-as-resumability

`source_snapshots` doubles as a request cache. When `cache_get` is supplied to `PlanItClient`, every request consults the cache first; cache hits short-circuit the HTTP layer entirely. `PageResponse.cached=True` flags hits so the orchestrator can skip re-recording the same snapshot.

This is the same mechanism that makes the audit trail durable, just queried in a different direction. Rerun semantics:

- **Same content, same URL** → cache hit, no API call.
- **Different content, same URL** (data updated since last fetch) → cache hit on the *previous* version is still served if `find_cached_response` is the lookup; a `--no-resume` invocation forces fresh fetches when staleness matters.

For full-refresh runs (e.g. before publishing aggregate claims), `dcp index --source planit --no-resume` re-fetches everything.

---

## Key design decisions, in one place

| Decision | Choice | Why |
|---|---|---|
| Database | Postgres 16 | Matches Luke's reference repos; JSONB for source-specific raw metadata. |
| ORM | None — raw `psycopg2` | Matches fuel-finder / meridian convention; queries short and obvious. |
| Triage LLM | v1: `granite4.1:30b` local (five-model eval, May 2026: 97% verdict accuracy at ~9s/app). dc_build: `claude-sonnet-5` against the enriched rubric (trial 2026-08-03: 47/50, 9/10 on invisibility cases). | Generations coexist per rubric; `FakeBackend` for CI. |
| Triage versioning | Per `(application_id, model, inserted_at)` | Re-running with a different model overlays a second opinion without touching the first. Resume is model-scoped. |
| Findings extraction | Three model families behind the verbatim-quote gate: GPT-5 (OpenAI Batch, primary for new content), Claude Sonnet, Qwen/MLX (second opinion only, per the label audit). v1's human-in-loop Read-tool rows remain in the store under their own model name. | The gate, not the model, is the hallucination protection; append-only rows make each family an overlay. |
| Multimodal pass | Originally planned via Claude vision; **probably won't do** | Phase 4 confirmed PDFs are overwhelmingly text-layered; vision can only see what's drawn and labelled, and concealed plant won't appear in drawings. Revisit per-app only. |
| Document corpus | Local filesystem first, S3 later | Mirrors fuel-finder's "local until it hurts" pattern. |
| Time scope | 2018+ for v1 | PlanIt has consistent coverage from 2018; sharp drop before. |
| Source order | PlanIt first | National, full-text searchable, single API. NSIP and per-council adapters added when journalism need warrants. |
| Schema mutability | Append-only / versioned where it matters; original values never overwritten | Reproducibility for journalism; defensibility back to source; re-analysis with refined prompts is cheap. |
| Resume mechanism | Cache via `source_snapshots`, not a separate cache table | One source of truth; same data serves both audit and resume. |
| Web framework | None. The reader (`scripts/export_reader.py`) is one self-contained HTML file — data, methodology and dictionary generated from the same queries; served from Cloud Run behind Guardian sign-in, no server-side logic of its own. | No build step, no runtime dependency beyond map tiles; a companion document is the first thing to go stale, so there are none. |
| Release packaging | Phased releases (2.x) regenerated by the runbook chain; artefacts carry their phase and land beside their predecessors on Drive; `release_diff.py` gates each against the last. v1's `dcp release` folders are HISTORY. | A citation of an earlier release keeps resolving; the diff is the check between a regression and a published one. |
| OCR for scanned-only pages | pypdfium2 + tesseract (default) / RapidOCR; generative VLMs excluded from the substrate role | The OCR text doubles as the verbatim-quote verification substrate. Non-generative engines fail noisily on illegible input; a VLM fails fluently, which would let invented quotes verify. Vision-capable models remain available as *readers* during extraction — never as the text of record. |
| Map coord backfill | `data/priors/inferred_coords.yaml` (typed alongside the raw record) | 11 of the top-61 worklist applications have no `location_x/y` in the raw PlanIt record because the address field carries no postcode. Inferred coordinates live in a small yaml priors file with per-entry provenance ("Nominatim forward-search returned …" or "sibling-ref backfill from …"); `dcp/map.py` falls back to it when source coords are null and flags inferred pins distinctly (`inferred_coords: true` in geojson + ⚑ badge in popups). Source coords stay null in `raw_metadata` — principle 3 (never mutate source) preserved. |
