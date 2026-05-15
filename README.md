# UK Data Centre Planning

Investigative-journalism tool. Builds a systematic national dataset of UK data-centre planning applications and surfaces signals about on-site power-generation infrastructure that may contradict public renewable / green marketing claims.

Collaboration with Aisha Down at the Guardian.

## Status

**Phase 1 — index complete, parent-backfill complete, Phase 2 triage in progress.** 1,832 UK data-centre applications ingested from 2007 onwards (parent-backfill adds the pre-2018 procedural ancestors), covering 401 councils with GSS code and portal-type metadata. `dcp triage` runs `granite4.1:30b` over the universe and writes versioned verdicts to `triage`. Deep-read stage not yet implemented. 71-test suite (unit + integration + triage) green.

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
- Ollama (local) for triage and structured extraction; default model `granite4.1:30b` chosen after a five-model comparison (IBM's JSON-tuning + 30b reasoning ≈ 97% verdict accuracy at ~9s/app). Pluggable `FakeBackend` keeps CI dependency-free.
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
for m in migrations/*.sql; do psql "$DATABASE_URL" -f "$m"; done

pytest                       # full suite (creates dcp_test DB, applies all migrations)
pytest -m "not integration"  # unit tests only, no Postgres required
```

## Pipeline

Three stages, each idempotent and resumable:

1. **Index** — paginate recent applications per source; upsert metadata into `applications`; preserve raw responses in `source_snapshots`. Reruns are no-ops by `(source, application_ref)` and content hash. Complementary `dcp backfill-parents` walks the `associated_id` chain to fetch parent permissions outside the keyword window.
2. **Triage** — `dcp triage` runs an Ollama model (default `granite4.1:30b`) over un-triaged applications, classifies against the DC + power-infrastructure rubric, and writes verdicts to `triage`. Versioned per `(application_id, model, inserted_at)`; resume is automatic and model-scoped, so re-running with a different model overlays a second opinion.
3. **Deep-read** — for triage matches (`verdict in ('DC', 'adjacent') AND worth_deep_read in ('yes', 'maybe')`), download document bundle, extract text (OCR fallback when no text layer), surface power-related signals into `findings`. Not yet implemented.

## Sources

Implemented:

1. **PlanIt API** (`planit.org.uk/api`) — national, full-text searchable, free. Primary keyword sweep + operator-name sweep + spatial colocated sweep + parent-backfill all run through this adapter.
2. **Planning Inspectorate NSIP register** — CSV download of all ~280 NSIP projects. One DC currently (Wapseys Wood, EN0110030); expected to grow.

Planned:

3. **Idox Public Access** generic adapter — long tail of council portals, needed for Phase 3 document fetch.
4. **Environment Agency public register** (industrial installations / combustion plant) — triangulation against permitted on-site capacity.

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

# 9. Reporter export — Aisha-facing markdown + xlsx
dcp export --top 50

# 10. Editorial map — interactive HTML + GeoJSON + KML
dcp map

# 11. (Optional) Phase 3 document fetch — Idox councils only at present
dcp fetch-docs --source idox --top 50
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
