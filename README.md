# UK Data Centre Planning

Investigative-journalism tool. Builds a systematic national dataset of UK data-centre planning applications and surfaces signals about on-site power-generation infrastructure that may contradict public renewable / green marketing claims.

Collaboration with Aisha Down at the Guardian.

## Status

**Phase 0 — scaffolding.** No scraping yet. Pipeline is plumbing only.

See:
- [prior_art.md](prior_art.md) — published research and reporting; cross-reference benchmarks our own analysis should reconcile against.
- [data/prior_art_sources/foxglove_top10.md](data/prior_art_sources/foxglove_top10.md) — Foxglove/Global Action Plan's ten ≥100 MW England applications, transcribed from their Sep 2025 report. Our pipeline's first known-good universe.

## Stack

- Python 3.12, raw `psycopg2` (no ORM).
- Postgres for state; append-only `source_snapshots` audit table preserves every fetch.
- Ollama (local) for triage and structured extraction; pluggable `FakeBackend` keeps CI dependency-free.
- Claude vision via personal Anthropic API for site-plan / blueprint multimodality (Phase 4 only).
- S3 for document corpus (introduced when local `data/` becomes inconvenient).
- CLI-driven (`scrape.py` or `dcp …`). FastAPI portal only if reporters need it.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env

docker compose up -d postgres
psql "$DATABASE_URL" -f migrations/001_initial.sql

pytest
```

## Pipeline

Three stages, each idempotent and resumable:

1. **Index** — paginate recent applications per source; upsert metadata into `applications`; preserve raw responses in `source_snapshots`. Reruns are no-ops by `(source, application_ref)` and content hash.
2. **Triage** — Ollama classifies each new application against the DC + power-infrastructure rubric. Versioned per `(application_id, inserted_at)`.
3. **Deep-read** — for triage matches, download document bundle, extract text (OCR fallback when no text layer), surface power-related signals into `findings`.

## Sources (planned, by priority)

1. **PlanIt API** (`planit.org.uk/api`) — national, full-text searchable, free.
2. **Planning Inspectorate NSIP register** — large opt-in cases (≥50 MW, e.g. Wapseys Wood).
3. **Idox Public Access** generic adapter — long tail of council portals.
4. **Environment Agency public register** (industrial installations / combustion plant) — triangulation against permitted on-site capacity.

## Methodology principle

Ingest broadly; analyse second. We don't decide the story before we see the data; we need to be able to find null findings as well as dramatic ones. The Foxglove top-10 is our first reconciliation target — if our pipeline doesn't reproduce their list with matching MW figures, our coverage is broken.
