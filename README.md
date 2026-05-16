# UK Data Centre Planning

Investigative-journalism tool. Builds a systematic national dataset of UK data-centre planning applications and surfaces signals about on-site power-generation infrastructure that may contradict public renewable / green marketing claims.

Collaboration with Aisha Down at the Guardian.

## Status

**Phases 1, 2, 3 (top-100), 4 (v1), and 6 (v2 reporter export with editorial cohorts) all green.** 1,832 UK data-centre applications ingested 2007–2026, classified by `granite4.1:30b` Stage-1 triage (683 DC · 136 adjacent · 965 unrelated · 48 unknown). Top-100 worklist document fetch ~99% complete across Idox, Ocella, and a manual-ingest path for one-off portals. Phase 4 v1 deep-read landed with `dcp/extract.py` (pypdf cache + regex pre-pass) + `dcp/findings.py` (delta classifier, NEW DISCLOSURE / REFINEMENT / CONFIRMATION) feeding the editorial export; ~35 apps now carry document-extracted findings via human-in-loop Claude-Code Read-tool extraction. Reporter export restructured around editorial cohorts (highlights at top → themed cohorts with cross-references → long-tail rank-ordered → filtered-from-worklist), mirrored in the xlsx with a separate Filtered sheet.

See:
- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline philosophy, schema, design decisions.
- [ROADMAP.md](ROADMAP.md) — what's done, what's next, what's parked, open questions.
- [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md) — flip-day mechanics (repo is currently private; methodology trail already tracked).
- [prior_art.md](prior_art.md) — published research and cross-reference benchmarks.
- [LICENSE](LICENSE) / [NOTICE](NOTICE) / [DATA-LICENSING.md](DATA-LICENSING.md) — Apache 2.0 (code, © 2026 Guardian News & Media Ltd.); per-source upstream data licensing.
- `data/seed_cases/walkthrough_findings.md` — hands-on findings from Aisha's three exemplar applications.
- `data/planit_exploration/findings.md` — PlanIt API exploration writeup.
- `data/prior_art_sources/foxglove_top10.md` — Foxglove top-10 reconciliation target.

> **Note on `data/`**: the methodology trail (research writeups, eval reports, the rubric) is tracked. Point-in-time outputs (document corpus under `data/raw/`, hand-off exports under `data/exports/`, raw JSONL eval outputs, the round-01 labelled sample) stay gitignored — see [POST_PUBLICATION_CHECKLIST.md](POST_PUBLICATION_CHECKLIST.md) for the per-file rationale. The bullet-list above describes the tracked subset; you'll see them in a fresh clone.

## Stack

- Python 3.12, raw `psycopg2` (no ORM).
- Postgres for state; append-only `source_snapshots` audit table preserves every fetch.
- Ollama (local) for Stage-1 triage; default model `granite4.1:30b` chosen after a five-model comparison (IBM's JSON-tuning + 30b reasoning ≈ 97% verdict accuracy at ~9s/app). Pluggable `FakeBackend` keeps CI dependency-free.
- Claude Code Read-tool (human-in-loop, model name `claude-opus-4-7+read-tool`) for Stage-2 findings extraction. Text-extraction step is decoupled (cached page-JSON), so a future batch SDK pass slots in as a new model name.
- Document corpus on local filesystem; S3 lift deferred until corpus growth warrants.
- CLI-driven (`dcp …` entrypoint). No web portal planned — the dataset is a snapshot re-rendered on demand into markdown + xlsx + KML + interactive map, not a live application. A static-site build is the likely shape if browsing ever becomes a requirement.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env

docker compose up -d postgres
for m in migrations/*.sql; do psql "$DATABASE_URL" -f "$m"; done

pytest                       # full suite (creates dcp_test DB, applies all migrations)
pytest -m "not integration"  # unit tests only, no Postgres required
```

## Pipeline

Three stages, each idempotent and resumable:

1. **Index** — paginate recent applications per source; upsert metadata into `applications`; preserve raw responses in `source_snapshots`. Reruns are no-ops by `(source, application_ref)` and content hash. Complementary `dcp backfill-parents` walks the `associated_id` chain to fetch parent permissions outside the keyword window.
2. **Triage** — `dcp triage` runs an Ollama model (default `granite4.1:30b`) over un-triaged applications, classifies against the DC + power-infrastructure rubric, and writes verdicts to `triage`. Versioned per `(application_id, model, inserted_at)`; resume is automatic and model-scoped, so re-running with a different model overlays a second opinion.
3. **Deep-read** — for triage matches (`verdict in ('DC', 'adjacent') AND worth_deep_read in ('yes', 'maybe')`), `dcp fetch-docs --source {idox,ocella}` downloads the document bundle (or `scripts/ingest_manual_docs.py` ingests journalist-supplied files for portals without an adapter). `dcp/extract.py` caches per-page text + runs the regex pre-pass for MW / generator-count / fuel-storage patterns. `dcp/findings.py` records `(application_id, document_id, signal_type, model, evidence_text, evidence_page)` rows and classifies each as NEW DISCLOSURE / REFINEMENT / CONFIRMATION against the triage signals. v1 covers ~35 apps via human-in-loop Read-tool extraction; the export consumes the findings via the same `dcp export` command (no sidecar files).

## Sources

Implemented — application metadata (Phase 1):

1. **PlanIt API** (`planit.org.uk/api`) — national, full-text searchable, free. Primary keyword sweep + operator-name sweep + spatial colocated sweep + parent-backfill all run through this adapter.
2. **Planning Inspectorate NSIP register** — CSV download of all ~280 NSIP projects. One DC currently (Wapseys Wood, EN0110030); expected to grow.

Implemented — document fetch (Phase 3):

3. **Idox Public Access** (`dcp fetch-docs --source idox`) — canonical and `/newplanningaccess/` variants; SSL chain reconstruction via `truststore`.
4. **Ocella** (`dcp fetch-docs --source ocella`) — POST to `showDocuments?reference=<ref>&module=pl`, anchor parse. Covers Hillingdon, NorthLincs, Slough Langley, several Welsh portals.
5. **Manual** (`scripts/ingest_manual_docs.py`) — journalist drops files into `data/raw/fully_manual/<ref>/`, the script hashes + hard-links them into the canonical layout and records them without overwriting any adapter-recorded URL.

Planned:

6. **Environment Agency public register** (industrial installations / combustion plant) — triangulation against permitted on-site capacity.

## Reproducing the dataset

After [Setup](#setup), the canonical sequence to rebuild the universe from
scratch (~6–10 h of polite wall-clock against PlanIt + Ollama):

```bash
# 1. Primary national sweep (PlanIt DC keyword union)
dcp index --source planit

# 2. NSIP register (large opt-in cases)
dcp index --source nsip

# 3. Operator-name sweep (catches operator-coded applications)
dcp operators --source planit

# 4. Spatial colocated sweep (DC anchors → 1 km neighbours)
dcp colocated fetch --source planit
dcp colocated process

# 5. Parent-application backfill (walks PlanIt's associated_id chain to
#    recover pre-2018 substantive permissions referenced from procedurals)
dcp backfill-parents --source planit

# 6. Council aliases (fix the legacy district names → current unitary GSS)
python scripts/load_council_aliases.py data/priors/council_aliases.yaml
python scripts/backfill_council_gss.py

# 7. Operator priors (Foxglove top-10 safety-net tags)
python scripts/tag_priors.py data/priors/foxglove_top10.yaml

# 8. Stage 1 triage (granite4.1:30b over the universe — ~5 h wall-clock)
dcp triage --model granite4.1:30b

# 9. Editorial-structure tags (cohorts, exclusions, duplicates)
python scripts/tag_cohorts.py     # reads data/priors/cohorts.yaml
python scripts/tag_duplicates.py  # reads data/priors/duplicates.yaml

# 10. Reporter export — markdown + xlsx, structured around editorial cohorts
dcp export --top 50

# 11. Editorial map — interactive HTML + GeoJSON + KML
dcp map

# 12. Phase 3 document fetch — Idox + Ocella portals
dcp fetch-docs --source idox  --top 100
dcp fetch-docs --source ocella --top 100

# 13. (Optional) Manual ingest for portals without an adapter
#     drop files under data/raw/fully_manual/<application_ref>/ first
python scripts/ingest_manual_docs.py

# 14. Phase 4 findings extraction (currently human-in-loop via Read tool)
python scripts/extract_findings.py
```

Each stage is idempotent: re-running picks up where it left off
(`source_snapshots` is also the resume cache; triage uses model-scoped
`NOT EXISTS` filtering on prior verdicts). Stages 1–7 are independent of
the LLM and run in well under an hour combined; stage 8 dominates the
wall-clock.

The OSM power-stations layer used by `dcp map` ships in the repo
(`data/priors/osm/uk_power_plants.geojson`, ODbL-licensed). Refresh it
with `python scripts/fetch_osm_power_plants.py --force` if you want a
newer snapshot.

For a partial reproduction (e.g. to validate methodology against a
single council), substitute `--limit N` on `dcp index`, `dcp triage`,
and `dcp fetch-docs` to scope each stage.

## Methodology principle

Ingest broadly; analyse second. We don't decide the story before we see the data; we need to be able to find null findings as well as dramatic ones. The Foxglove top-10 is our first reconciliation target — if our pipeline doesn't reproduce their list with matching MW figures, our coverage is broken.
