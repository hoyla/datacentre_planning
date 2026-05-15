# Architecture

The shape of the system, the schema, the design principles, and where we expect to extend.

For *what's done and what's next*, see [ROADMAP.md](ROADMAP.md).
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
7. **Provenance is non-negotiable.** Every claim in `findings` carries a document reference, evidence text, page number, model name, and timestamp. Reporters can't use what we can't back to a quotable source. Aggregate outputs (markdown summaries, xlsx exports, any future web interface) must always link or cite back to the underlying `findings` / `documents` / `applications` rows, never present numbers without provenance.

---

## Three-stage pipeline

```
INDEX  →  TRIAGE  →  DEEP-READ
```

Each stage is idempotent and resumable. Each writes to a separate table family. They communicate only through Postgres, not in-memory state — so a stage can be re-run in isolation without re-doing earlier work.

### 1. Index

Per source, paginate the recent-applications feed (or equivalent), upsert structured metadata into `applications`, preserve the raw response in `source_snapshots`.

Implemented: PlanIt (`dcp/sources/planit.py`, including the parent-application backfill and operator/spatial sweeps), NSIP CSV (`dcp/sources/nsip.py`).
Pending: gov.uk-search-API Section 35 Directions half, MHCLG national service as a cross-validation source.

### 2. Triage

For each application without a recent triage verdict, ask an LLM (Ollama by default) to classify:

- Is this a data centre, adjacent, unrelated, or unknown?
- What's the rough capacity (MW) if mentioned?
- Are there power-related signals worth examining (substation, generator, fuel storage, "energy centre", etc.)?

Verdicts versioned per `(application_id, model, inserted_at)`; latest wins for "what do we currently think." Prior verdicts retained for prompt-revision comparison. The resume contract is per-model: `applications_pending_triage(conn, model=X)` excludes apps that already have a verdict from model X, so re-running with a new model overlays a second opinion without touching the first.

**Implemented** (`dcp triage`, prompt frozen 2026-05-14, model granite4.1:30b). Output fields: `verdict`, `worth_deep_read`, `signals[]`, `why`, `confidence`. The rubric lives in `data/triage_labelling/rubric.md` (tracked); the prompt is in [dcp/triage.py](dcp/triage.py). Captured lexicon includes: backup, generator, turbine, LPG, gas, failover, substation, fuel storage, emergency power, resilience, uptime, CHP, kVA, kW, MW, "energy centre" (Aisha-confirmed coded term — see `data/seed_cases/walkthrough_findings.md`).

### 3. Deep-read

For triage matches, fetch the full document bundle from the source portal (or aggregator's links), dedupe by content hash, extract text (OCR fallback when no text layer), surface power-related signals into `findings`.

Two-stage extraction per the seed walkthrough:
- **Stage 1** (cheap): from description + consultee senders alone, before opening any document. Northern Gas Networks as a consultee → high gas-infrastructure prior.
- **Stage 2** (per-document): structured fact extraction with evidence-text capture. Generator counts, fuel type, rated capacity, on-site CHP mentions, fuel-storage hours.

Optional multimodal pass: Claude vision on site plans and elevations for the matched subset, identifying fuel tanks and generator enclosures.

**Document-fetch implemented** for canonical Idox portals (`dcp fetch-docs --source idox`); see `dcp/sources/idox.py`. Per-application `_manifest.json` is the hand-over signal. SSL chain reconstruction via the `truststore` package (OS native trust store + AIA chasing) unblocks councils whose servers send incomplete certificate chains. **Structured extraction (Stage 2) and the multimodal pass are not yet implemented.**

---

## Schema

Current schema in [migrations/001_initial.sql](migrations/001_initial.sql) plus subsequent migrations: [002_discovery_tracking.sql](migrations/002_discovery_tracking.sql) (the `discovered_via` array and the `colocated_candidates` table) and [003_triage_columns.sql](migrations/003_triage_columns.sql) (Stage-1 rubric refresh — added `worth_deep_read`, `signals[]`, `why`; converted `confidence` from REAL to TEXT to match the categorical rubric). Tables and their relationships:

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
findings         │ append-only, versioned per inserted_at
findings_visual  │ (planned — multimodal extraction)
```

Key invariants:

- `source_snapshots(source_id, key, content_sha256)` — same content fetched again = no-op insert. Different content (e.g. updated page) creates a new row.
- `applications(source_id, application_ref)` UNIQUE. ON CONFLICT updates description / dates / status / url / raw_metadata, refreshes `last_seen_at`, preserves `first_seen_at` and existing non-null `council_gss` (COALESCE).
- `documents(application_id, content_sha256)` UNIQUE — same document fetched twice doesn't duplicate.
- `triage`, `findings` are versioned, never updated. Latest by `inserted_at` is current; historical rows kept for prompt-revision comparison.

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
- **`data/raw/`** — downloaded document bundles from Phase 3 (`dcp fetch-docs`). Layout: `data/raw/<source>/<application_ref-with-slashes-preserved>/<sha256[:16]>.<ext>`, with a `_manifest.json` in each per-application directory once its fetch loop completes. Content-addressed by SHA-256 so identical bytes share a hash but are still scoped per-application (the same design statement filed against two related applications lands in both directories). Local-first; lift to S3 / zenodo when corpus grows beyond local disk.
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
| Triage LLM | Ollama (local), `granite4.1:30b` | Five-model eval (May 2026): granite4.1:30b 97% verdict accuracy at ~9s/app. IBM's JSON-tuning + 30b reasoning beat bigger non-granite models on calibration. `FakeBackend` for CI. |
| Triage versioning | Per `(application_id, model, inserted_at)` | Re-running with a different model overlays a second opinion without touching the first. Resume is model-scoped. |
| Multimodal pass | Claude vision via personal Anthropic API | Ollama vision too weak for site plans. Volume on matched subset is small. |
| Document corpus | Local filesystem first, S3 later | Mirrors fuel-finder's "local until it hurts" pattern. |
| Time scope | 2018+ for v1 | PlanIt has consistent coverage from 2018; sharp drop before. |
| Source order | PlanIt first | National, full-text searchable, single API. NSIP and per-council adapters added when journalism need warrants. |
| Schema mutability | Append-only / versioned where it matters; original values never overwritten | Reproducibility for journalism; defensibility back to source; re-analysis with refined prompts is cheap. |
| Resume mechanism | Cache via `source_snapshots`, not a separate cache table | One source of truth; same data serves both audit and resume. |
| Web framework (when needed) | FastAPI with auto-generated Redoc + OpenAPI | Matches Luke's fuel-finder convention; APIs should be documented by default. |

---

## What's not in the architecture yet

- **Council-reorganisation handling** for pre-2020 records under legacy district names (Wycombe → Buckinghamshire, Chiltern South Bucks → Buckinghamshire, etc.). Currently surfaces as NULL `council_gss` with the legacy `area_name` preserved in `raw_metadata`. Per principle 3, the legacy name stays untouched; any canonicalisation goes in a new column or join table, not over the original.
- **Document-fetch adapters per portal type.** Idox (canonical and `/newplanningaccess/` variant), Salesforce (verified unnecessary for now; Loughton accessible via PlanIt's Arcus scraper), NSIP, etc.
- **Findings export / reporter-facing output.** Markdown summary + xlsx for hand-off (meridian pattern). Phase 6+.
- **Web interface (when needed).** If/when a reporter-facing browse UI is needed, **FastAPI** is the chosen framework — matches Luke's fuel-finder convention. Any HTTP API exposed by it should be documented via **Redoc with OpenAPI** (FastAPI generates both `/docs` Swagger and `/redoc` ReDoc views automatically; keep the operation `summary`, `description`, and Pydantic-model field docstrings populated). This isn't urgent — the CLI-driven export is enough until a journalist needs to click around — but the decision is locked when the time comes.
- **CI**. Tests are local-only; no GitHub Actions yet. Worth setting up when team scales beyond Luke + Aisha.
