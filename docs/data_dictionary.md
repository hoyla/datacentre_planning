# Data dictionary — UK data-centre planning dataset (v2)

*Generated artefacts described here: the handover workbook
(`dc_build_handover_<date>.xlsx`), the site reports, and the queryable
database export. Field definitions are stable; row counts are snapshots
(as of 2026-08-05: 391 sites, 1,894 applications ingested of which 705
carry a data-centre verdict, 11,518 source documents, 186 verified
findings). Regeneration is one command per artefact; nothing is
hand-maintained.*

## Units of the dataset

**Site** — the unit the investigation reasons about: a cluster of
planning applications and/or Barbour ABI construction projects joined by
explicit record links, family references between applications, or
spatial proximity (≤ 1 km, campus scale). Sites carry stable public keys:

- `PTNO-<n>` — anchored on a Barbour ABI project (its Ptno).
- `SITE-<application ref>` — no Barbour anchor; keyed by the
  alphabetically first application in the cluster.

A site key, once issued, always refers to the same site. Re-clustering
updates membership; sites that stop emerging are marked retired, never
deleted or reused.

**Application** — one planning application as published by its local
planning authority, keyed `Council/reference`. Applications belong to
sites; several applications (outline, reserved matters, conditions,
variations) typically realise one site.

**Document** — one file fetched from a planning portal (or ingested
manually), content-hashed, with its source URL recorded. Manifest files
in each application's folder map hashed filenames to document type,
date, and source URL.

**Finding** — one extracted fact (e.g. "14 gas reciprocating engine
generators", "21 MW") with its verbatim supporting quote, source
document, page, extraction model, and timestamp. Quotes are machine-
verified against the source text before entering the dataset.

## Sites tab

| Column | Definition | Source |
|---|---|---|
| Site key | Stable identity (see above) | derived |
| Classification | `both` = in our planning universe and Barbour's; `ours_only` = planning applications only; `barbour_covered` = Barbour project whose linked applications carry non-data-centre verdicts; `barbour_only` = Barbour project we hold no applications for; `unlocatable` = data-centre-verdict applications with no usable coordinates | derived |
| Site name | Barbour project title where anchored, else lead application address/description | Barbour / application |
| Latitude, Longitude | Site coordinates | see Coordinate source |
| Coordinate source | `barbour` (project record), `application` (portal/PlanIt record), `inferred_prior` (our manually-verified inference) | — |
| Councils | Local planning authorities of member applications | applications |
| Applications / Application refs | Member applications of the site | derived (membership method recorded per member) |
| Verdict mix (v1 triage) | Latest triage verdicts across member applications. **Interim**: the v1 four-class rubric (`DC` / `adjacent` / `unrelated` / `unknown`); replaced by the eight-class dc_build taxonomy when the catalogue sweep runs | model (see methodology) |
| Documents held | Count of fetched documents across member applications | corpus |
| Verified findings | Count of quote-verified extracted facts | extraction (v1 deep-read; v2 pending) |
| Max disclosed MW | Largest megawatt figure among verified findings | extraction, quote-gated |
| EIA indicators (heuristic) | `ref pattern` = application reference carries an EIA-shaped suffix (FULEA, OUTES, EIASR, SCR, SCO, SCREEN); `ES documents` = held documents include Environmental Statement material. A **floor, not an estimate**: reference conventions vary by council and document coverage is still growing. Authoritative EIA status (including screening outcomes — "EIA not required" decisions) comes from deep-read | heuristic |
| Barbour Ptno / title / stage / value £ / floor area / site area / plan & decision dates | Barbour ABI project record fields, reproduced as licensed. Contact and role fields are deliberately not exported | Barbour ABI (credit required in published output) |

## Applications tab

| Column | Definition | Source |
|---|---|---|
| Site key | Owning site | derived |
| Joined site via | How the application joined its site: `project_link` (explicit Barbour↔application match), `family` (referenced by another application's related-case field), `spatial` (≤ 1 km), `singleton` | derived |
| Council / Status / Dates | As published by the authority. **Statuses are refresh-pending**: at least one decided application still shows a stale status pending the refresh pass | portal / PlanIt |
| Verdict (latest) + confidence + model + reasoning + signals | The most recent model classification, with the model's stated confidence (`sure` / `probable` / `guessing`), its one-sentence reasoning, and power-related terms found in the description. All verdict history is retained in the database | model |
| Portal URL | The application on the council's portal | authority |
| Documents held / Verified findings | As for sites | corpus / extraction |
| Address / Description | As published | authority |

## Confidence and honesty conventions

- Model verdicts carry the model's own confidence and are **versioned,
  never overwritten** — the database retains every prior verdict.
- Extracted quantitative facts appear only with a verbatim quote that
  has passed automated verification against the source document.
- Fields that cannot be supported by the visible text are recorded as
  `unknown` rather than guessed; where ground-truth labelling found the
  truth invisible from the description, that is flagged
  (`invisible_from_description`) rather than silently absorbed.
- Heuristic columns are labelled as such in the header.

## What the documents contain

Planning bundles include consultation responses reproduced as councils
published them; these carry objectors' names and addresses. Barbour ABI
records are licensed for this use with attribution; their named-contact
fields exist in the database but are excluded from all exports.
