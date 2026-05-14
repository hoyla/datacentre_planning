# UK Data Centre Planning

Investigative-journalism tool. Builds a systematic national dataset of UK data-centre planning applications and surfaces signals about on-site power-generation infrastructure that may contradict public renewable / green marketing claims.

Collaboration with Aisha Down at the Guardian.

## Status

**Phase 1 — index complete for PlanIt.** 1,549 UK data-centre applications ingested from 2018 onwards, covering 401 councils with GSS code and portal-type metadata. Triage and deep-read stages not yet implemented. Full 24-test suite (8 unit + 16 SQL integration) green.

See:
- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline philosophy, schema, design decisions.
- [ROADMAP.md](ROADMAP.md) — what's done, what's next, what's parked, open questions.
- [prior_art.md](prior_art.md) — published research and cross-reference benchmarks.
- `data/seed_cases/walkthrough_findings.md` — hands-on findings from Aisha's three exemplar applications.
- `data/planit_exploration/findings.md` — PlanIt API exploration writeup.
- `data/prior_art_sources/foxglove_top10.md` — Foxglove top-10 reconciliation target.

> **Note on `data/`**: most of `data/` is gitignored — research writeups, eval outputs, cached source-portal responses, labelling artefacts. These contain pre-publication editorial direction that we keep out of version control. **Tracked exceptions**: `data/operators.yaml` (operational config — operator/agent name list) and `data/triage_labelling/rubric.md` (the distilled triage methodology). The bullet-list above describes files you'll have locally if you've run the pipeline; if you've just cloned, they won't be present.

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

pytest                       # full suite (creates dcp_test DB, applies schema)
pytest -m "not integration"  # unit tests only, no Postgres required
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
