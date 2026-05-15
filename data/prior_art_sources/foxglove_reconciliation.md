# Foxglove top-10 reconciliation against the ingested universe

Cross-check of the ten applications transcribed from [foxglove_top10.md](foxglove_top10.md) against the 1,549 applications ingested via the PlanIt adapter (2018-01-03 → 2026-05-07).

Reconciliation performed 2026-05-12, after the full v1 sweep. Query script is transient (not committed); the findings here are the durable artifact.

**Result: 8/10 confirmed, 1 probable, 1 unconfirmed.** The unconfirmed case is the implausibly-low-emissions outlier with the least identifying detail in the Foxglove report.

---

## Confirmed (8)

### #1 Cambois (QTS) — 1,100 MW

- **PlanIt records:**
  - `Northumberland/24/04112/OUTES` (2024-11-28, Outline, "erection of up to ten data centre buildings of Class B8 use")
  - `Northumberland/26/01617/VARYCO` (2026-05-07, Conditions variation referencing 24/04112/OUTES)
- **Address:** Land at Former Power Station Site, Cambois, Northumberland.
- **Cross-link:** This is the DeSmog Blyth case (580 diesel generators, 3.93 GWth nameplate). The 2026 variation surfaces first in the `-start_date` sort because it's the most recent activity on the application family.

### #2 Elsham Tech (Greystoke) — 1,000 MW

- **PlanIt records:**
  - `NorthLincs/PA/2025/643` (2025-05-27, "Outline planning permission for the construction of a data centre park, including ancillary offices, internal plant and cooling equipment, **emergency backup generators**")
  - `NorthLincs/PA/SCR/2025/5` (2025-04-10, EIA Screening Opinion)
- **Address:** Land adjacent to Elsham Wolds Industrial Estate, North Lincolnshire.
- **Foxglove status:** "Pending outline" — matches the 2025 outline filing date.
- **Lexicon note:** Description includes "emergency backup generators" verbatim — direct match for our triage signal lexicon.

### #3 Humber Tech (Greystoke) — 384 MW

- **PlanIt records:**
  - `NorthLincs/PA/2024/584` (2024-05-15, Outline, "data centre of up to 309,000m² (GEA) delivered across up to three buildings")
  - `NorthLincs/PA/SCR/2024/2` (2024-03-15, EIA screening)
- **Address:** Land south of the A160, South Killingholme — Humber estuary area, hence "Humber Tech".
- **Foxglove status:** "Approved" — would need to confirm the post-2024-05 approval decision separately.

### #5 Thurrock (Google) — 225 MW estimated

- **PlanIt records:**
  - `Thurrock/24/00927/SCO` (2024-08-28, EIA Scoping Opinion)
  - `Thurrock/25/00573/OUT` (2025-05-12, full hybrid application — "data centre campus comprising… up to four data centre buildings… up to 130,500 sqm GEA")
- **Address:** Arena Essex and Fishing Lake, Arterial Road, Purfleet-on-thames, Essex.
- **Cross-link:** This is the Aisha Down / Priya Bharadia Guardian story (May 2026, with North Weald — see #9). The May 2025 hybrid filing is the substantive application; the 2024 SCO is its pre-app.

### #6 Virtus Saunderton — 300 MW

- **PlanIt records (full application family):**
  - Original outline: `Wycombe/08/05740/FULEA` (likely pre-ingestion window, not in DB)
  - Variation: `Wycombe/22/06872/VCDN` (2022-07-08, "Erection of 4 no. Data centre buildings")
  - Reserved-matters and condition discharges through 2024–2025
  - Latest: `Bucks/PL/25/6761/VRC` (2025-12-23, latest variation, post-unitary-reorg)
- **Address:** Former Molins Site, Haw Lane, Saunderton, Buckinghamshire.
- **Council-reorg note:** Pre-2020 records under the legacy `Wycombe` district name; post-2020 under `Buckinghamshire` unitary. Both surface in our universe; explicit GSS linkage pending the council-reorg work item in [ROADMAP.md](../../ROADMAP.md).

### #7 International Trading Estate (GTR) — 256 MW

- **PlanIt records:**
  - Parent permission: `Ealing/250949FUL` (2025-03-07, "Construction of four data centre units within three buildings of approximately 67.9m AOD… approximately 158,702sqm GEA, Use Class B8")
  - Multiple condition discharges (`Ealing/2607**CND`) reference permission "ref: 250949FUL dated 19/12/2025" — so the outline was **permitted on 19 Dec 2025**.
- **Address:** International Trading Estate, Trident Way, Southall, UB2 5LF.
- **Foxglove status:** "Permission pending" (Sep 2025 report) — now permitted (per condition-discharge references).

### #9 North Weald (Google) — 164 MW

- **PlanIt records:**
  - `EppingForest/EPF/1449/24` (2024-07-15, EIA Scoping Report)
  - `EppingForest/EPF/0849/25` (2025-04-16, "Outline planning application… to deliver a data centre campus, with up to 2 no. data centre buildings… up to 77,148m² GEA… **emergency back-up generators, energy storage (fuel tanks and/or battery storage)**")
- **Address:** Land West of Merlin Way, North Weald Airfield, North Weald Bassett, CM16 6AA.
- **Important distinction:** This is **separate from the Loughton DC** (`EppingForest/EPF/1165/22`, Alandale Scaffolding, Langston Road, Loughton) — both are in Epping Forest but they're different sites, different applications, and (relevant for the Foxglove vs Aisha cross-reference) different stories. Loughton is Aisha's seed case; North Weald is Foxglove #9 and the second site in Aisha & Priya's Guardian May 2026 piece.
- **Lexicon note:** Description includes "emergency back-up generators, energy storage (fuel tanks and/or battery storage)" — explicit power-infrastructure disclosure in the application itself, which is unusual.

### #10 103MW Court Lane — 103 MW

- **PlanIt records:**
  - Outline: `ChilternSouthBucks/PL/22/4145/OA` (2022-11-30, "Outline planning application… for the demolition of the Court Lane Industrial Estate and the redevelopment of the site to comprise a data centre… up to 65,000sqm (GEA) (excluding generator yard)")
  - Reserved matters: `Bucks/PL/26/02874/DE` (2026-04-07)
- **Address:** Court Lane Industrial Estate, Court Lane, Iver, Buckinghamshire.
- **Foxglove status:** "Approved" (2022).
- **Cross-link:** This is the same project some prior research calls "**West London Tech Park (Iver)**" by Greystoke. Foxglove records the developer-stated emissions at just **340 tCO2e/yr for 103 MW** — orders of magnitude below comparable applications (the Digital Realty UK existing-facility anchor is 408,041 tCO2e). One of the three Foxglove "implausibly low" outliers; a high-priority deep-read target.
- **Disambiguation note:** Court Lane Iver is **a different application from Virtus Saunderton (#6)** despite both being in Buckinghamshire / former district councils. Both have ChilternSouthBucks variants in our universe.

---

## Probable (1)

### #8 G-Park Docklands (GLP) — 210 MW

- **Best PlanIt match:**
  - `TowerHamlets/PA/22/01140/A1` (2022-07-22, "demolition of existing Travelodge Hotel… erection of a data centre (Use Class B8)… 33,870 sqm GIA")
  - `TowerHamlets/PA/18/03088/A1` (2018-11-30, original outline)
- **Address:** London Docklands Travelodge Hotel, Coriander Avenue, London, E14 2AA.
- **Confidence:** Medium. "Docklands" in the address matches Foxglove's "Docklands" label; Tower Hamlets is the right council for that area. But the Travelodge-to-DC conversion is small-scale (33,870 sqm GIA) and the developer isn't named in our records — we can't directly verify "GLP" (Global Logistic Properties) as the applicant without consulting `other_fields`/applicant data.
- **Alternative considered and rejected:** `Wiltshire/PL/2024/05527` ("Spring Park data centre campus, Neston, SN13") — superficially matches "park" + DC but it's neither in Docklands nor under GLP branding. Spring Park is the campus name, in rural Wiltshire.
- **Recommended verification:** Inspect the `other_fields` JSON on PA/22/01140 for applicant/agent details to confirm GLP. Defer to the operator-name sweep (Phase 1b).

---

## Unconfirmed (1)

### #4 DC01 — 320 MW

- **No direct match found.** "DC01" is a generic / internal project code; the Foxglove report doesn't name a council, developer, or address for this entry, just the size (320 MW), application year (2024), status (outline approved 02.2025) and emissions (6,056 tCO2e — implausibly low).
- **Searches attempted (all returned nothing):**
  - Literal "DC01" in description or application_ref.
  - "320 MW" in description.
  - Outline applications filed 2024 → approved early 2025 in candidate council clusters.
- **Candidate clusters worth examining manually:**
  - Iver Heath / Dromenagh Farm — `ChilternSouthBucks/PL/22/3403/FA` (2022-10-20, hyperscale DC redevelopment at Shannon Group Headquarters) plus variations like `Bucks/PL/25/6737/VRC` (2025-12-23). Different timing than Foxglove implies but the only "hyperscale" outline approved in that window in Bucks.
  - Other 2024-filed outline approvals not yet inspected.
- **Recommended next step:** Manual review of Foxglove's source for this entry (if traceable), or request from Foxglove directly. Failing that, defer to the operator-name sweep — the developer-name field on the original application should disambiguate. **Three of Foxglove's implausibly-low-emissions outliers** (DC01 6,056 tCO2e for 320 MW, G-Park Docklands 1,148 tCO2e for 210 MW, 103MW Court Lane 340 tCO2e for 103 MW) are exactly the cases where developer figures look most suspicious; resolving DC01's identity is a high-value piece of journalism follow-up in its own right.

---

## Implications for the project

1. **Coverage validation passed.** The PlanIt sweep captures every Foxglove ≥100 MW case that's discoverable by description (8/10 directly; 1 of remainder is identifiable by address; 1 is genuinely under-identified at source).
2. **The operator-name sweep (Phase 1b) is the clear next-coverage win.** Three of the named projects (Elsham Tech / Humber Tech / Virtus / Greystoke + GLP) would have been findable more cleanly by developer name than by description keyword. Worth running before triage, since it expands the candidate universe.
3. **Council-reorg handling matters more than I initially assumed.** Saunderton (#6) and Court Lane (#10) both have application chains crossing the 2020 Bucks reorganisation. Pre-2020 `Wycombe` / `ChilternSouthBucks` records and post-2020 `Buckinghamshire` records need to be linked for these to be navigable as single application families.
4. **`associated_id` is doing real work.** Multiple Foxglove cases (#1 Cambois, #6 Saunderton, #10 Court Lane) have a parent outline with subsequent conditions-variation and reserved-matters applications. PlanIt's `associated_id` field reliably points back to the parent. Worth promoting to a typed `applications.parent_ref` column rather than living in `raw_metadata`.
5. **The May 2026 Guardian story sites are both in scope.** Aisha & Priya covered both Thurrock (#5) and North Weald (#9). Our universe contains both application families. Reproducing their numbers from the source documents is a defensible-by-construction outcome of the deep-read stage.
6. **Three implausibly-low-emissions outliers** (#4 DC01, #8 G-Park Docklands, #10 Court Lane) are immediately high-priority deep-read targets. They're where the journalism gap between the developer's planning-form figure and the physical kit is likely widest.

For the project roadmap implications, see [ROADMAP.md](../../ROADMAP.md).
