# PlanIt API exploration — findings (2026-05-12)

Hands-on exploration of `planit.org.uk`'s API before committing to adapter code, following the same "look at the data first" approach that worked for the seed cases.

Cached: [api_docs.html](api_docs.html), [areas.json](areas.json) (full UK area inventory, 485 records), [all_data_centre_records.json](all_data_centre_records.json) (full "data centre" sweep, 2,120 records).

---

## TL;DR

- **PlanIt holds 20.1M planning applications across 417 UK councils** with actual ingested data, spanning all UK regions including Scotland, Wales, Northern Ireland, Channel Islands, Isle of Man.
- The `"data centre"` keyword search returns **2,120 applications nationally**, distributed across **242 councils**. The union of all direct DC keywords (`data centre`, `data center`, `data hall`, `hyperscale`, `datacentre`, `colocation`, `data park`) totals 2,214 — i.e. `"data centre"` alone catches ~96% of the direct-language universe.
- Volume is **consistent from 2018 onwards** (150–280/year) and falls off sharply pre-2018 (≤75/year). That cleanly defines the "good data period" — start backfill at 2018, push earlier later if needed.
- The `/api/areas/` endpoint **doubles as the national portal inventory** Aisha asked for — per-council `gss_code`, `scraper_type`, `planning_url`, application count, date range. We get the inventory deliverable for free.
- **Rate limit is real** (429 after ~10–15 requests in quick succession). Treat as ≤1 req/2–3 s with 60 s backoff on 429.

---

## API shape (verified)

**Base:** `https://www.planit.org.uk/api/`
**Auth:** none required. Donation-supported.
**Format:** JSON (`/api/applics/json`, `/api/areas/json`).

### `/api/applics/{fmt}` — application search

Useful query parameters (verified):
| Param | Meaning |
|---|---|
| `search` | Text search across `description`, `application_type`, `development_type`, `id_type`, `status`, `decision`. Supports quoted phrases, `OR`, `NOT`. |
| `auth` | Filter by `area_name`. Must match exactly — see areas list. |
| `start_date` / `end_date` | Filter by application start date |
| `pg_sz` | Page size (default ~50; tested up to 200) |
| `page` | 1-indexed page number |
| `select` | Comma-separated whitelist of fields to return (reduces response size) |
| `sort` | Sort order. `-start_date` for newest first |
| `developer` | Text search across applicant/agent address & company |
| `krad`/`lat`/`lng`/`pcode` | Spatial circle search |
| `bbox` | Spatial rectangle search |
| `recent` / `changed` | Updates filter (days) |

Top-level response shape: `{from, to, total, records[], secs_taken}`.

### `/api/areas/{fmt}` — UK area inventory

Same paging/select pattern. Each record includes:
| Field | Use |
|---|---|
| `area_name` | The name used in `auth=` filter |
| `long_name` | E.g. `"Aberdeen City Council"` |
| `gss_code` | ONS GSS code — matches our `councils.gss_code` PK |
| `parent_name`, `in_region` | Geographic hierarchy |
| `scraper_type` | **Portal kind** (Idox / Atrium / Tascomi / Custom / etc.) |
| `planning_url` | The council's own planning portal URL |
| `total` | Total applications PlanIt has for this area |
| `min_date` / `max_date` | Date coverage |
| `borders` | Polygon (omit with `select=` — adds ~50 KB each) |

---

## Per-record field shape

Confirmed fields on a sample record:

```
address          Land At Former Power Station Site On Northern Side Of Cambois ...
altid            None
app_size         Medium                                                 # not capacity — appears to be application physical scale
app_state        Undecided                                              # status
app_type         Conditions                                             # Outline | Full | Conditions | RM | ...
area_id          48
area_name        Northumberland (County)
associated_id    24/04112/OUTES                                         # cross-link to parent application (gold for cross-reference)
consulted_date   2026-05-28
decided_date     None
description      Variation of Conditions 4 (Approved Plans), 17 (Access) ...
last_changed     2026-05-09T12:11:22.109217
last_different   2026-05-08T11:54:45.420822
last_scraped     2026-05-08T11:54:45.420822                             # when PlanIt last checked; NOT data freshness
link             https://www.planit.org.uk/planapplic/Northumberland/26/01617/VARYCO/
location         {'coordinates': [-1.533218, 55.150993], 'type': 'Point'}
location_x       -1.533218
location_y       55.150993
name             Northumberland/26/01617/VARYCO                         # globally unique key (council/ref)
other_fields     {agent_address, agent_company, applicant_name, ...}
postcode         None
reference        None
scraper_name     Northumberland
start_date       2026-05-07
uid              26/01617/VARYCO                                        # council's local ref
url              https://publicaccess.northumberland.gov.uk/...         # link to source council portal
```

Schema mapping into our `applications` table:
- `applications.application_ref` ← `uid`
- `applications.source_id` → PlanIt source row
- `applications.council_gss` ← look up from `area_name` via areas inventory
- `applications.url` ← `url` (council portal) — preferred over PlanIt's `link`
- `applications.title` / `description` ← `description`
- `applications.address` ← `address`
- `applications.postcode` ← `postcode`
- `applications.date_received` ← `start_date`
- `applications.date_decided` ← `decided_date`
- `applications.status` ← `app_state`
- `applications.raw_metadata` ← `app_type`, `app_size`, `associated_id`, `other_fields`, `last_changed`, etc.

`name` (council/ref composite) is a natural unique key for PlanIt-as-source.

---

## Keyword universe expansion

Hit totals for each direct DC keyword (single-keyword queries):

| Search term | Hits | Notes |
|---|---|---|
| `"data centre"` | **2,120** | Primary net |
| `"data center"` | 4 | US spelling; rare in UK |
| `"data hall"` | 72 | Sub-component term |
| `hyperscale` | 7 | Rare in description |
| `datacentre` | 46 | One-word variant |
| `colocation` | 12 | Industry term |
| `"data park"` | 1 | Rare |
| **Direct union** | **2,214** | All direct-keyword OR (+94 vs. `"data centre"` alone) |
| `"energy centre"` | 9,061 | **Too noisy** — community CHP, biomass, etc. Needs heavy triage downstream. |

**Decision:** v1 PlanIt sweep uses the direct union (~2,214 records). `"energy centre"` becomes a separate slower sweep with mandatory triage filtering, since the false-positive rate would otherwise dominate.

---

## Year distribution (from the 2,120 `"data centre"` hits)

```
  2026:   92  (YTD May)
  2025:  279  ←
  2024:  169
  2023:  161
  2022:  165
  2021:  155
  2020:  185
  2019:  152
  2018:  148
  ───── good-data inflection ─────
  2017:   39
  2016:   34
  2015:   51
  2014:   38
  2013:   68
  2012:   75
  ...
```

Consistent 150–280/year from 2018 onwards; sharp drop to ≤75/year before. Two plausible explanations both worth flagging:

1. PlanIt's scraping coverage genuinely thinner pre-2018 (more councils onboarded over time).
2. Real-world DC application volume was lower pre-2018 (pre-AI boom).

Either way, **2018+ is the defensible "good data period"** for v1. ~1,300 applications in scope, comfortably below the API's 5,000 result cap.

---

## Council & portal-type distribution

**2,120 DC applications span 242 distinct councils.**

**Top 20 councils** (heavy bias toward London / Thames Valley):
```
  307  Hillingdon
  162  Central Bedfordshire
   90  Tower Hamlets
   79  Old Oak Park Royal
   75  Ealing
   51  Brent
   48  Windsor
   48  Hart
   45  Slough
   38  Vale of White Horse
   37  Runnymede
   35  Newport          ← Wales
   35  Chiltern South Bucks  (legacy name, see below)
   30  Hounslow
   24  Leeds
   22  Glasgow          ← Scotland
   21  North Lanarkshire ← Scotland
   21  Broxbourne
   19  Wiltshire
   17  Rushmoor
```

**By portal type (across the DC universe):**
| Portal type | DC apps | Comment |
|---|---|---|
| Idox | 989 (47%) | Dominant. Single adapter unlocks half the universe. |
| Ocella | 325 (15%) | Hillingdon, Central Beds — punches above its weight |
| Custom | 224 (10%) | One adapter per |
| Agile | 142 (7%) | |
| Atrium | 87 | Wycombe (legacy), Tower Hamlets |
| Arcus | 64 | **Epping Forest is here** — see Salesforce note below |
| None / unknown | 61 | Includes Buckinghamshire's legacy district refs |
| PlanningExplorer | 56 | Civica-family |
| EnterpriseStore | 56 | |
| Tascomi | 49 | |
| NIPortal | 15 | Northern Ireland |
| Other | <15 each | Long tail |

---

## Foxglove top-10 council coverage

All Foxglove top-10 councils are in PlanIt's inventory with healthy totals:

| Foxglove case | PlanIt area | Portal | Total apps | Date range |
|---|---|---|---|---|
| Cambois (QTS) | Northumberland (County) | Idox | 104,972 | 2000–2026 |
| Elsham Tech, Humber Tech (Greystoke) | North Lincs | Custom | 13,798 | 2015–2026 |
| Thurrock (Google) | Thurrock | Idox | 32,523 | 2002–2026 |
| Virtus Saunderton | Buckinghamshire (composite) | Idox Idox | 8,086 | 2002–2026 |
| North Weald (Google) | Epping Forest | **Arcus** | 70,453 | 1999–2026 |
| G-Park Docklands | Newham | Idox | 60,247 | 1999–2026 |
| 103MW Court Lane | Portsmouth | Idox | 31,386 | 2002–2026 |

**Cambois/Blyth confirmed:** the very first record returned by our `"data centre"` sort was a 2026 conditions-variation referencing parent `24/04112/OUTES` — the exact Blyth application DeSmog covered. Validated.

**Epping Forest (Loughton) revelation:** PlanIt scrapes Epping Forest via the **Arcus** scraper. The Salesforce frontend at `eppingforestdc.my.site.com` that we hit during the seed walkthrough is presumably a newer public-facing skin atop the same underlying case-management system. **We may not need a Salesforce adapter at all** — Loughton's `epf116522` should be findable via PlanIt search.

**Caveat — council reorganisations:** "Wycombe" and "Chiltern South Bucks" appear in `areas.json` with `total=0` because they were merged into the new unitary "Buckinghamshire" in 2020. Pre-2020 applications still live under the legacy area names; post-2020 under the unitary. Adapter must handle both, and pre/post-reorg applications won't share a council key. Same pattern likely applies to other recent unitary mergers (e.g. North Yorkshire, Somerset, Cumbria).

---

## Rate limit behaviour

Hit `429 Too Many Requests` after ~10–15 requests in <30 seconds. Backed off 30–60 s, then resumed cleanly. Conservative policy for our scraper:

- Default delay: **2–3 seconds between requests.**
- On 429: sleep 60 s, retry once. Exponential backoff if it recurs.
- `pg_sz=100–200` is comfortable; the 5,000 results / 1,000 KB caps don't bite at these sizes.
- Total estimated time to ingest the entire 2018+ universe (~1,300 records, ~13 pages at pg_sz=100): well under 5 minutes at the polite rate.

We can comfortably do incremental nightly re-runs in a few minutes; full backfill in tens of minutes. No need to optimise.

---

## Adapter design implications

What this walk-through changes from the earlier sketch:

1. **`/api/areas/` is part of the adapter, not separate work.** The first run of the PlanIt adapter should populate our `councils` table from `areas.json`. We get `gss_code`, portal type, council URL, and historical totals in one go. The "national portal inventory" deliverable Aisha asked for then exists as a side effect.

2. **`name` (council/ref composite) is the natural dedup key** for PlanIt as a source. Maps to our `applications.application_ref` with PlanIt's source_id.

3. **`associated_id` is gold for cross-application linkage.** The Blyth case alone shows variations, discharges, and parent OUTES applications all share an `associated_id`. Schema-wise we already have `applications.raw_metadata JSONB` to carry this; we may want a dedicated `applications.parent_ref` for explicit linking.

4. **Council-reorganisation handling.** Pre-2020 Wycombe/Chiltern/etc. records can't share a `council_gss` with their post-2020 unitary successor. Either we record the legacy GSS or accept the gap. Worth a small note in the schema.

5. **Salesforce adapter is probably unnecessary at this stage.** Epping Forest is in PlanIt via Arcus. Verify by finding `epf116522` once rate limit clears.

6. **The `/api/applics/json?developer=...` search is a hidden lever** for finding applications by operator name (Google, Greystoke, Blackstone, etc.) without needing description matches. Useful for the Phase 2 sweep that catches applications filed under neutral language.

7. **Rate limit is the only friction.** No auth, no CAPTCHAs, no obfuscation. Idiomatic Python `httpx` with polite delays is the whole adapter.

---

## Recommended v1 PlanIt adapter scope

1. **Populate `councils`** from `/api/areas/?select=area_name,long_name,gss_code,parent_name,in_region,scraper_type,planning_url,total,min_date,max_date`. ~485 rows.
2. **Sweep applications** with the direct-DC keyword union, paged with `pg_sz=100` and 2 s delay, `start_date>=2018-01-01`, sorted by `-start_date`. Upserts on `(source_id, name)`.
3. **Raw response capture:** each page's JSON body lands in `source_snapshots` with the request URL as `key` and content hash for dedup. Reruns are no-ops on unchanged pages.
4. **Output state:** `applications` table populated with ~1,300 rows. `triage` and `findings` remain empty until later phases.

That's the whole adapter for v1. Estimated build time: a couple of hours.

---

## Open items the walk-through left

- **Verify Loughton `epf116522` is findable via PlanIt** once rate limit clears. If yes, kills the Salesforce-adapter assumption. If no, we still need a different approach for that council.
- **The four parked Foxglove lookups** (DC01, International Trading Estate / GTR, G-Park Docklands, 103MW Court Lane) — should now be straightforward via PlanIt's developer-name search or description matches. Worth a small follow-on pass.
- **PlanIt's `total` on areas hits 20,086,348** — sanity-check against published UK planning volumes. Sounds high but UK runs ~500k–1M planning applications a year, so 20M over ~25 years is plausible.
- **`other_fields`** structure varies between records — should be normalised when we ingest (extract applicant_name, agent_company, etc. into dedicated `applications` columns).
