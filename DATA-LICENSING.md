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

### Barbour ABI (licensed, not redistributed)

The construction-intelligence workbook "Data Centres in planning and under
construction" (253 projects) was supplied to the Guardian by
[Barbour ABI](https://barbour-abi.com/) under a commercial licence
(clearance confirmed 2026-08-02). It is ingested into the `projects` table
(`dcp index --source barbour --file <xlsx>`), with the verbatim source rows
preserved in `raw_metadata`.

- **Attribution required**: credit **Barbour ABI** in any published output
  that draws on this data (project values, floor areas, build stages,
  client / architect / contractor identifications, or coverage claims
  derived from the cross-reference).
- **Not redistributed**: the workbook lives under `data/new_lists/`
  (gitignored) and the database rows are local-only. This repository does
  not republish the dataset; reproduction requires your own licensed copy.
- The role blocks carry named-individual contact details; they are held
  for reporting purposes under the Guardian editorial code and must not
  appear in published artefacts or tracked files.
- **Position reported 2026-09-02** (Luke, second-hand — "apparently";
  no written terms have changed in this file): Barbour are content with
  a citation in the reporting. So a public-facing output does not have
  to be Barbour-free to be publishable; it has to credit Barbour ABI.
  The two rules above stand as written until the licence text says
  otherwise: the workbook and its rows are not redistributed, and the
  role blocks never appear. The ROADMAP's public feed strips Barbour
  fields as a design choice for a reader-facing profile, not because
  this section requires it.

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

### Environment Agency public register (`data/external_sources/environment-agency-*`)

The Environment Agency's *Industrial installations* public register,
downloaded from
https://environment.data.gov.uk/public-register/downloads/industrial-installations
(a zip, despite the URL), together with the text of the environmental
permits it links to on gov.uk.

Licensed under the
[Environment Agency Conditional Licence](https://www.gov.uk/government/publications/environment-agency-conditional-licence/environment-agency-conditional-licence),
which permits copying, publishing, adapting and commercial re-use subject
to attribution and to the register's own re-use conditions
([data.gov.uk record](https://www.data.gov.uk/dataset/1b268e32-d399-4e1c-87a0-00a17a11fce6/compliance-ratings-waste-and-installations)).

- **Attribution required**, in the Environment Agency's own words:
  "Contains Environment Agency information © Environment Agency and/or
  database right". Carried in code as `dcp.ea_permits.ATTRIBUTION` so an
  artefact cannot render a permit figure without it.
- **Not redistributed**, on the same footing as the planning documents
  above. The permit PDFs and their extracted text live under
  `data/raw/ea_permits/`, which is gitignored: they are public documents
  at permanent gov.uk URLs, so this repository fetches them rather than
  republishing them. The licence would allow republishing; consistency
  with the rest of `data/raw/` is the reason not to.
- **The register snapshot is** committed, because it is a daily file with
  no version of its own and no archive behind it — yesterday's is simply
  gone. So is `environment-agency-permit-claims.yaml`, which holds each
  claim with the verbatim sentence it was read from, so a published
  figure stays checkable from a clone without the documents; and
  `environment-agency-permit-documents.json`, which pins every
  document's URL, sha256, byte count and page count for re-fetching.
- The licence explicitly grants no endorsement and no warranty: the
  Environment Agency is not liable for errors in the register, and does
  not endorse this use of it.

### ONS / GSS codes

GSS codes used for `councils.gss_code` and `council_aliases` follow the
ONS Office for National Statistics convention (OGL v3.0).

### postcodes.io (postcode centroids, used by hand from 2026-09-02)

[postcodes.io](https://postcodes.io) is a free, open-source postcode
lookup; its README says it serves the ONS Postcode Directory, Ordnance
Survey Open Names and the Scottish Postcode Directory. The service's
own code is MIT; the *data* it returns is those sources' data under
their licences — the ONS Postcode Directory is published under the
Open Government Licence v3.0 with an attribution statement its user
guide requires wherever the data is reproduced, naming Ordnance Survey
(Crown copyright and database right), Royal Mail (copyright and
database right) and the Office for National Statistics (Crown copyright
and database right), each with the year of the release used. Take the
exact wording and year from the ONSPD release on the ONS geoportal at
the time of publication.

Used so far only by hand: the postcode centroids that placed
ServerChoice's Stevenage address and the Slough Trading Estate
postcodes on 2026-09-02 (ROADMAP, Coverage gaps and the partition item)
came from its API. Any published output that carries a postcodes.io
centroid — the public feed's overlay on the ROADMAP is the intended one
— reproduces the attribution above and credits postcodes.io by name,
which is the courtesy its maintainers ask.

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
- **Barbour ABI**: commercial licence — credit "Barbour ABI" in published
  output; workbook and derived rows not redistributed.
- **Environment Agency permits**: Conditional Licence — attribute
  "Contains Environment Agency information © Environment Agency and/or
  database right"; register snapshot and derived claims committed,
  permit documents fetched rather than redistributed.
- **Council planning documents**: not redistributed by this repo;
  per-document licensing applies if reproduced elsewhere.
