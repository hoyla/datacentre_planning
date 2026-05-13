# NSIP register research — findings (2026-05-13)

Investigation of the Planning Inspectorate NSIP route as a Phase 1e source. The canonical PlanIt API doesn't cover NSIP-route applications, and we have at least one confirmed important case (Wapseys Wood — 300 MW DC approved as NSIP via Section 35 Direction March 2026) that we need to capture from this route.

---

## TL;DR

- **NSIP register publishes a CSV download endpoint** at https://national-infrastructure-consenting.planninginspectorate.gov.uk/api/applications-download — **verified 2026-05-13**: 213 KB, ~280 projects, no auth, text/csv content-type. This is the easiest scraping target we've found across any of our sources.
- **Section 35 Directions** are *not* indexed centrally; they're individual gov.uk publication pages under `https://www.gov.uk/government/publications/...-section-35-direction-...`. No RSS, no dedicated API. Discovery means search-based polling.
- **The DC-specific universe is currently tiny** — Section 35 directions for data centres only became possible after January 2026 regulations. Wapseys Wood is the first and so far only confirmed one. Volume will grow but slowly.
- **Pre-application limbo**: A Section 35 Direction (like Wapseys Wood) pre-dates the DCO application. The project won't appear in the NSIP register until the formal DCO is filed. End-to-end tracking needs to bridge the two phases.
- **Recommended adapter scope**: a daily ingest of the CSV download + per-project page fetch + a separate weekly poll of gov.uk for new Section 35 Directions. ~half a day of engineering.

---

## Source 1: NSIP register (primary)

**Canonical URL:** https://national-infrastructure-consenting.planninginspectorate.gov.uk/
**Replaces:** legacy `infrastructure.planninginspectorate.gov.uk` (still live but being phased out; primarily Wales projects).

### Access

| Aspect | Status |
|---|---|
| Bulk CSV download | **Available and verified.** GET `/api/applications-download` → text/csv, no auth, ~280 rows. |
| HTML register | Browsable at `/register-of-applications` |
| Per-project pages | `/projects/{PROJECT_ID}` (e.g. `EN010081`, `BC0410001`). React-rendered — likely needs Playwright for full content (documents page, examination timetable, etc.) |
| Filtered query API | Not documented / not visible |
| Anti-scraping | None detected. No CAPTCHA, no login, no obvious rate limit |

### CSV schema (verified from sample download)

Columns (header row, all quoted):

```
Project reference, Project name, Applicant name, Application type, Region,
Location, Grid reference - Easting, Grid reference - Northing, GPS co-ordinates,
Stage, Description, Anticipated submission period, Date of application,
Date application accepted, Date Examination started,
Examining Authority's anticipated close of examination, Date Examination closed,
Date of recommendation, Date of decision, Date withdrawn
```

Sample rows include:

- `BC0310001` — Trelavour Lithium Project (Cornish Lithium G5 Limited), Pre-application stage, August 2026 submission anticipated. Demonstrates that pre-application projects DO appear in the register with anticipated dates.
- `BC0410001` — East Midlands Gateway Phase 2 (Segro Properties Ltd), Examination stage, submitted October 2025. Demonstrates a project mid-examination with full dates populated.

The `Application type` column uses codes like `BC03 - An Industrial Process or Processes`, `BC04 - Storage or Distribution of Goods`. Data-centre-specific code may be a new addition post-2026 regulations — needs verification once any DC DCO is filed.

### Coverage scope

- Roughly 280 NSIP projects total since 2008.
- Currently zero confirmed DC projects in the register — Wapseys Wood is at pre-application stage, no DCO yet filed.
- The 2024 NPPF reforms (approved October 2025) made data centres eligible for NSIP; volume will grow.

### Document availability

Once a DCO is submitted, each project gets a documents page with the full bundle: DCO application form, Environmental Statement, examination library, examining authority's report, decision. Document URLs appear stable but JS-rendered — adapter needs to either parse the rendered DOM (Playwright) or find an underlying JSON API.

---

## Source 2: Section 35 Directions (gov.uk publications)

**No central index.** Each direction is a separate publication page at `https://www.gov.uk/government/publications/...-section-35-direction-planning-act-2008` with downloadable PDFs.

### Access

| Aspect | Status |
|---|---|
| Single index page | None |
| RSS feed | None for Section 35 Directions specifically |
| Gov.uk search API | https://www.gov.uk/api/search.json — exists, public, supports `q=` and `filter_format=publication` parameters. **Recommended discovery mechanism.** |
| PDF URLs | Stable `https://assets.publishing.service.gov.uk/media/{hash}/{filename}.pdf` |
| Anti-scraping | None |

### Known data-centre Section 35 Direction (May 2026)

**Wapseys Wood / SDC M40 Campus** is currently the only confirmed DC Section 35 Direction:

- **Publication page:** https://www.gov.uk/government/publications/data-centre-campus-wapseys-wood-buckinghamshire-section-35-direction-planning-act-2008
- **Direction PDF:** https://assets.publishing.service.gov.uk/media/69b7eb62b84f01b2be53a27e/Section_35_Direction_Wapseys_Wood.pdf (already cached in [data/seed_cases/wapseys_wood/](../seed_cases/wapseys_wood/))
- **Request Qualifying Statement:** https://assets.publishing.service.gov.uk/media/69b7ece3ba47c264e6c8cfba/Request_Document_-_SDC_M40_Campus_-_Section_35_Direction.pdf (54 pages, 6.99 MB — the substantive applicant case for national significance; not yet cached)
- **Applicant:** Slough Holdings UK Limited via Montagu Evans
- **Capacity:** 300 MW IT load (three 100 MW buildings)
- **Energy centre:** 270–350 MW generating capacity, gas-ready (pipeline up to ~900 MW)

The Request Qualifying Statement is significant: it's the substantive 54-page document arguing for national significance, including the energy-centre details. Worth fetching and caching.

### Other Section 35 Directions for context (non-DC)

- Net Zero Teesside (2020)
- Eurolink Interconnector (2022)
- East Midlands Gateway Phase 2 (2024)
- Dozen+ others for energy, water, rail

Most pre-date the 2026 DC eligibility — so they're not relevant for our investigation but confirm the publication pattern.

### Legal context

Infrastructure Planning (Business or Commercial Projects) (Amendment) Regulations 2026, in force 8 January 2026 — formally enables DCs to be prescribed for Section 35 direction requests.

---

## Recommended adapter design

A small **two-source NSIP adapter** as Phase 1e. Both sources are low-friction (no CAPTCHAs, no auth, polite scraping welcomed), so engineering effort is modest.

### Adapter 1: NSIP register CSV ingest

```
GET https://national-infrastructure-consenting.planninginspectorate.gov.uk/api/applications-download
→ parse CSV
→ for each row: upsert into applications with discovered_via=['nsip_register']
  Map columns: project_ref → application_ref; date_of_application → date_received;
  description, location, grid-ref → fields; GPS coords → location_x/y; stage → status.
→ source: a new sources row, e.g. 'nsip', kind='nsip'
→ record full CSV body in source_snapshots once per fetch
```

For DC-relevance filtering at ingest: scan `Project name` + `Description` for the same DC keyword union we use on PlanIt. Filter at insert; only DC-relevant rows land in applications.

Volume: ~280 projects total; expected DC subset = small single digits initially, growing.

### Adapter 2: Section 35 Directions watcher

```
Weekly poll of gov.uk search API:
  GET https://www.gov.uk/api/search.json?q=%22Section+35+Direction%22&filter_format=publication&order=-public_timestamp
→ parse JSON; for each result published since last_seen_at:
  - check publication page for "data centre" / "DC" mentions
  - if relevant: cache the publication page + linked PDFs
  - upsert a stub application record with discovered_via=['s35_direction']
  - flag for triage — pre-DCO so we lack a project_ref; bridge to NSIP register
    later when the DCO is filed
```

The bridge problem: a Section 35 Direction precedes the DCO application by months. The project gets an NSIP project_ref only when the DCO is formally filed. Reconciliation needs a composite key — likely `(applicant_name, location, capacity_mw_estimate)` — to link the Section 35 Direction record to its later NSIP register entry.

### Schema fit

Both sources land in the existing `applications` table with no schema change. They use `discovered_via=['nsip_register']` or `['s35_direction']` so triage / queries can distinguish from the PlanIt universe. Same source_snapshots cache + idempotent upsert semantics apply.

---

## Open questions

1. **Will DC projects appear in the CSV with a recognisable application type code?** The 2026 regulations may have introduced a new BC code (e.g. BC10 — Data Centres). Wapseys Wood will tell us when it files its DCO. Until then, scan Project name / Description for DC keywords.
2. **National Policy Statement for data centres** — expected to set NSIP eligibility thresholds (likely ~50 MW). Not yet published as of May 2026. Once published, defines our scope.
3. **Project IDs through reorganisation** — does an NSIP project that was previously listed on the legacy `infrastructure.planninginspectorate.gov.uk` get a new ID in the new portal, or is the ID stable across the migration?
4. **Gov.uk search API rate limits** — undocumented. Worth a small test before relying on it.

---

## Risks

- **Tiny current universe** means low immediate return on engineering investment. Counter: any NSIP-scale DC finding is high-value journalism (these are 200+ MW projects).
- **Pre-application invisibility** — a Section 35 Direction is the *only* signal we get until the DCO is filed months later. The watcher adapter is necessary precisely because waiting for the NSIP register entry means missing the early-stage story.
- **Document scraping for examination libraries** could become non-trivial as DCO applications accumulate hundreds of supporting documents (the East Riding Yorkshire Energy Park case had 174 documents at council level; an NSIP DCO will likely have more).

---

## Recommendation

Build Adapter 1 (CSV ingest) **now** — it's ~2 hours of work and gives us the foundation. Build Adapter 2 (Section 35 watcher) when there's a *second* DC Section 35 Direction to test against, or sooner if Aisha wants real-time alerting on new ones.

Wapseys Wood remains a manual-only case for now; cache its existing documents into our DB (the Section 35 Direction is already in [data/seed_cases/wapseys_wood/](../seed_cases/wapseys_wood/); we'd add the Request Qualifying Statement next).

---

## References

- [National Infrastructure Consenting Portal](https://national-infrastructure-consenting.planninginspectorate.gov.uk/)
- [NSIP CSV download endpoint](https://national-infrastructure-consenting.planninginspectorate.gov.uk/api/applications-download)
- [Planning Inspectorate blog on the portal migration (Oct 2023)](https://planninginspectorate.blog.gov.uk/2023/10/10/a-new-home-for-national-infrastructure-planning/)
- [Wapseys Wood Section 35 Direction publication page](https://www.gov.uk/government/publications/data-centre-campus-wapseys-wood-buckinghamshire-section-35-direction-planning-act-2008)
- [Infrastructure Planning Regulations 2026 (data centres into NSIP)](https://www.legislation.gov.uk/ukdsi/2025/9780348275438)
- [Gov.uk Search API](https://www.gov.uk/api/search.json) (undocumented but public)
