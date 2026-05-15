# Data licensing notice

The Apache License 2.0 (`LICENSE`) covers the code in this repository,
and the project-level copyright + attribution lives in `NOTICE`. The
data ingested or tracked under `data/` carries its *own* upstream
licensing, which the Apache `NOTICE` file alone doesn't capture — that's
what this document records.

## Data sources used in the pipeline

### PlanIt (planit.org.uk)

The PlanIt API aggregates UK local-authority planning data and is offered
free under a courteous-use convention. Records carry forward the
originating council's licensing (predominantly Open Government Licence
v3.0). The PlanIt project is donation-supported; please attribute
"Data sourced from planit.org.uk" in any downstream publication, and
respect their rate-limit posture (`dcp.sources.planit.PlanItClient`
already implements polite delays).

### Planning Inspectorate NSIP register

`national-infrastructure-consenting.planninginspectorate.gov.uk` —
machine-readable CSV. Licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
Attribution: "Contains public sector information licensed under the
Open Government Licence v3.0."

### Council planning portals (Idox `online-applications` / `newplanningaccess`,
Ocella, Salesforce, Arcus, etc.)

Documents fetched into `data/raw/` are individual application records
served by UK local-authority planning portals. The records themselves
are public planning information; the per-document copyright varies by
applicant and document type (planning forms are typically OGL or public;
third-party design statements and reports retain authors' copyright but
are made publicly available as part of the planning process).

This repository **does not redistribute** any of these documents — the
`data/raw/` directory is `.gitignore`d. Anyone wanting to reproduce the
corpus must fetch the documents themselves via `dcp fetch-docs` against
the relevant council portals.

### OpenStreetMap (`data/priors/osm/uk_power_plants.geojson`)

Power-station features extracted from OpenStreetMap via the Overpass API.
OSM data is licensed under the
[Open Data Commons Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/).

**Attribution required**: "© OpenStreetMap contributors" wherever the
power-station layer is shown (e.g. on the editorial map output).

Re-fetch (e.g. to refresh): `python scripts/fetch_osm_power_plants.py --force`.

### Foxglove (referenced, not redistributed)

[Foxglove](https://www.foxglove.org.uk/)'s 2025 "DC gap" report is
referenced verbatim in `data/prior_art_sources/foxglove_top10.md` for
the purpose of reconciling our keyword-sweep universe against their
top-10 cases. Foxglove retains copyright over their original report.
The PDF is not redistributed; readers wanting the source should request
or download from Foxglove directly.

### ONS / GSS codes

GSS codes used for `councils.gss_code` and `council_aliases` follow the
ONS Office for National Statistics convention (OGL v3.0).

---

## Data licensing on outputs

### Methodology trail (`data/seed_cases/`, `data/*_findings.md`, `data/triage_labelling/eval_*.md`, etc.)

The methodology documents — research findings, evaluation reports,
rubric — are released under the same Apache License 2.0 as the code.
Copyright Guardian News & Media Ltd. Attribution is appreciated if
re-used substantively in derivative research.

### Triage and finding outputs

Once the deep-read stage produces `findings` (Phase 4+), those rows will
carry the document references they were extracted from. Any external
publication that quotes a `findings` row should also cite the upstream
planning document by its application reference.

---

## In short

- **Code**: Apache License 2.0 (see `LICENSE` and `NOTICE`).
  Copyright 2026 Guardian News & Media Ltd.
- **Methodology docs**: Apache 2.0, with attribution appreciated.
- **OSM data**: ODbL — attribute "© OpenStreetMap contributors".
- **NSIP CSV**: OGL v3.0.
- **PlanIt data**: courtesy attribution to planit.org.uk.
- **Council planning documents**: not redistributed by this repo;
  per-document licensing applies if reproduced elsewhere.
