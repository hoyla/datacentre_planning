# Build plan: per-site consumption context from DESNZ local-authority data

Written 2026-08-12 for the next session to execute. Luke has approved
this shape ("lovely ideas… plan 1 now"). Everything needed is in the
repository — no re-fetching, no browser, no registration required.

## What is being built

One journalist-facing sentence per site, computed at export time:

> Large-user electricity consumption in this site's local authority rose
> 60% between 2019 and 2024, while nationally it fell 9% (DESNZ
> sub-national statistics; large users are half-hourly-metered
> non-domestic consumers, which includes data centres).

Surfaced in three places, all generated from one module:

1. **Reader site panel** — the sentence above, only where the site's
   local authority maps cleanly; omitted otherwise (no hedged filler).
2. **Workbook Sites sheet** — two columns: "LA large-user electricity
   2019→2024" (signed percent) and the national baseline beside it, plus
   Read me dictionary rows.
3. **External aggregates sheet + reader methodology** — DESNZ becomes a
   `Source` in `dcp/external_aggregates.py` with national aggregate rows
   (−9% national; Slough and Hillingdon as the two largest absolute
   risers nationally) — extending the module and sheet built 2026-08-12.

## Decisions already made — do not relitigate

- **Source**: `data/external_sources/desnz_la_nondom_halfhourly_2010-2024.csv`
  (committed; provenance, licence, sha256 of the source workbook and
  sanity anchors in `data/external_sources/README.md`).
- **Half-Hourly non-domestic only.** Data centres are HH-metered. The
  per-MSOA rows exclude HH entirely (verified: zero HH meters on every
  MSOA row), so LA level is the finest honest granularity. Do not build
  anything MSOA-level from this source.
- **Years**: headline is 2019→2024 change with the national change
  beside it; keep 2015 available for the longer arc. Series ends 2024 —
  say so where the number appears.
- **The figure describes the authority, not the site.** Wording must
  never imply it is the site's own consumption. It is context; the
  attribution is circumstantial and stays that way.
- **Caveats that travel with the number**: series ends 2024 (misses
  2025–26 energisations); DESNZ "Unallocated" bucket means LA figures
  are floors; an authority contains more than its data centres.
- Write "application"/"local authority" in full in journalist-facing
  text; never "app"/"LA" there.

## The one genuinely fiddly part: council → DESNZ local authority

Sites carry council prefixes from application refs (`councils` array in
both exporters) and Barbour rows carry an authority name. DESNZ names
are current local authorities (unitaries, districts, London boroughs;
Welsh dual names like "Newport / Casnewydd"; post-reorganisation names
like "Cumberland").

- Build a small mapping in a new `dcp/consumption_context.py`:
  normalised council name → DESNZ `local_authority` string. Start from
  the existing machinery — there is a `council_aliases` table and
  council-reorganisation handling (see `tests/test_council_reorg.py`);
  reuse before inventing.
- The mapping is an inference: store/emit it alongside, never overwrite
  source values (house principle 3).
- A site spanning several councils: use the site's council set; if the
  set maps to more than one authority, show the one containing the
  site's coordinates if that is already derivable, otherwise omit the
  sentence for that site and count it.
- **Assert coverage at export**: every site either maps or is counted
  as unmapped, and the export prints both numbers. No silent gaps.
- Expect awkward cases: City of London, county-council refs (minerals
  applications), Northern Ireland (DESNZ file is GB-only — NI sites are
  legitimately unmapped and must not error).

## Module shape

`dcp/consumption_context.py`:

- `load_series(path) -> dict[la_name, dict[year, kwh]]` — reads the CSV,
  no pandas needed.
- `national_change(series, y0=2019, y1=2024) -> float` — excludes
  "Unallocated"; must reproduce −9% (anchors in the README; make this a
  test).
- `authority_for(councils, barbour_authority) -> str | None` — the
  mapping above.
- `context_sentence(la, series) -> str | None` — the exact journalist
  wording, None when unmapped or the authority is missing years.
- Deterministic, no API calls; same inputs → same sentence.

Tests (`tests/test_consumption_context.py`): the national baseline
anchor; Slough +60% / Hillingdon +36% anchors; Welsh dual-name and
reorg mapping cases; NI returns None without error; a sentence
round-trips its own numbers.

## Order of work

1. Module + tests against the committed CSV (anchors in README).
2. Workbook columns + Read me rows (`scripts/export_handover.py` —
   collect in the Sites loop like `agg_figures` is collected).
3. Reader site panel sentence (`scripts/export_reader.py`) + a DESNZ
   paragraph in the methodology section beside the existing queue
   comparison; add DESNZ to `dcp/external_aggregates.py` SOURCES and
   AGGREGATES (national −9%, Slough, Hillingdon rows).
4. Regenerate `index.html` and a scratch workbook; **verify the built
   artefacts by opening them** (house rule — three of the 2.1 defects
   were invisible in diff review); check a mapped site (anything in
   Slough/Hillingdon), an unmapped NI site, and a multi-council site.
5. Update `docs/EXTERNAL_DATA_SOURCES.md`: a short section on the DESNZ
   LA series (what it can and cannot see, MSOA finding, link to the
   README) — the UKPN/CFI precedent from 2026-08-12 shows the format.
6. Fresh branch off main, PR. Do not touch the merged branches
   `external-aggregates` or `reader-pinpoint-link`.

## Context worth having (2026-08-12 session)

- PR #61 (external aggregates beside the data) and #60 (Pinpoint link)
  are merged. (Stale as of 2026-08-26: EdgeOne no longer deploys anything — its middleware redirects to Cloud Run, which is published by `cloudrun/deploy.sh`.)
- The reader's methodology now ends its adjudication section with the
  Ofgem queue comparison table — the DESNZ paragraph belongs right
  after it, same voice: what each side can see, nulls visible
  (Docklands −15%, Hertsmere flat, against Slough +60%).
- A separate session is fixing the workbook Provenance sheet's stale
  "Phase 1 of 3" labels; if it has landed, rebase over it — the new
  columns don't collide.
- Step 2 of the original idea (an LA-level choropleth map layer) is
  deliberately NOT in this plan; propose it separately once the
  sentence ships.
