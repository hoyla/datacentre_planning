# External source snapshots

Raw or lightly-derived snapshots of external datasets, preserved because
they are either registration-gated or needed at export time. Never mutate
a snapshot; a re-fetch adds a new dated file beside the old one.

## desnz_la_nondom_halfhourly_2010-2024.csv

Local-authority-level **Half-Hourly** non-domestic electricity consumption
rows ("All MSOAs" rollups), extracted verbatim from DESNZ, *Lower and
Middle Super Output Areas electricity consumption*, file
`MSOA_non-domestic_elec_2010-2024.xlsx` (9.4 MB, not committed),
downloaded 2026-08-12 from:
https://assets.publishing.service.gov.uk/media/69427b3736f089d38be1f1ce/MSOA_non-domestic_elec_2010-2024.xlsx
sha256 of source workbook:
`28166187857b956c647c16ef72d5584c6ed3b6279aac489e7c512632ae937aca`

Half-Hourly (large-user) consumption is published **only** at local
authority level — every per-MSOA row in the source carries zero HH
meters, so data-centre-scale consumers are structurally invisible below
LA granularity (verified 2026-08-12). A national "Unallocated" bucket
(~2.9 TWh in 2024) means LA figures are floors. Licence: Open Government
Licence v3.

Sanity anchors for any re-ingest (kWh totals, HH only): national sum of
allocated LAs 2019 ≈ 134.2 TWh, 2024 ≈ 121.5 TWh (−9%); Slough 2019
1,084 GWh → 2024 1,734 GWh (+60%); Hillingdon 1,029 → 1,398 GWh (+36%).

## ukpn-large-demand-list.json

Full 496-row export of UK Power Networks' *Large Demand List*
(`ukpn-large-demand-list`), fetched 2026-08-12 through a registered
portal session — **anonymous access returns headers only**, so this
snapshot cannot be re-fetched without a UKPN Open Data Portal login.
Committed, not-yet-energised import projects ≥ 5,000 kVA across the
three UKPN licence areas. `demand_technology_type` has exactly two
values — "Large Demand" (252 rows, 7,250 MVA) and "Distributed Energy
Resource" (244 rows, 9,267 MVA) — data centres are NOT labelled.
Anonymised by the publisher; do not attempt to match rows to sites
except as a deliberate, method-labelled adjudication.
Licence: UK Power Networks open data terms (attribution required).

## neso-ea-register.xlsx

NESO's *Existing Agreements (EA) Register*, published alongside the Gate 2
connections-reform results, committed verbatim. Downloaded 2026-08-19
during the demand-sources research sweep and re-downloaded byte-identical
2026-08-20 from:
https://www.neso.energy/document/373996/download
sha256: `a96e29b4bf2d43c2d69a552ddecf7244e01a2ef045e93bbdfc2c318e60b0960c`

3,478 project rows (one sheet, header on spreadsheet row 5): Project Name,
Associated Installed Capacity (MW), Existing Connection Date, Existing
Connection Point, expressed-interest-in-Gate-1 flag, Technology Type. The
only public NESO artefact naming transmission **demand** customers with MW:
119 rows carry Technology Type "Transmission Connected Demand", 49,440 MW
in total, of which at least 20 are explicitly data-centre-named.

Caveats that must travel with any use: inclusion was **consent-based**
(the file's own banner: "PUBLIC - last updated 11/6/25 following developer
request to remove a project form the public EA list" — so absence proves
nothing, and the register can shrink); it records **pre-reform contracted
positions**, not Gate 2 outcomes; capacity is the contracted connection
ceiling, not IT load, built capacity or observed draw; the update date
"11/6/25" is read as 11 June 2025 (British format, consistent with the
Gate 2 timeline) but the format is not stated. No licence is stated on the
document; it is a published NESO document quoted with citation.

Sanity anchors for any re-parse: 3,478 data rows; 119 demand rows summing
49,440 MW; largest demand row "Walpole Flexible Generation" 2,550 MW;
"Iver 2 Ark Estates" 435 MW at "Uxbridge Moor (Iver B 132kV)".

Loaded into `capacity_claims` (migration 021) by
`scripts/load_capacity_claims.py`, which reads this file plus the
hand-adjudicated site matches in `neso-ea-register-matches.yaml`.

## ark-accounts-fy2025.pdf, kao-accounts-fy2025.pdf, companies_house_ocr/

Statutory accounts filed at Companies House, committed because they are
the evidence behind per-site and per-company power figures and because a
filed document is immutable once filed — unlike a portal dataset, this
snapshot can never diverge from its source.

| File | Company | Filing | Filed | sha256 |
|---|---|---|---|---|
| `ark-accounts-fy2025.pdf` | Ark Data Centres Limited (05656968) | Full accounts to 30 June 2025 | 2025-12-17 | `63caea3de3f43f4a18b86efa6f7146f2e1e8b7e96973311eb637dc186eaa1a50` |
| `kao-accounts-fy2025.pdf` | Kao Data Limited (11756346) | Full accounts to 31 March 2025 | 2025-12-18 | `275f71fd02d9f1aafa51a51e43a7242bd9118bd81ccfc4205e1325c2517a99b8` |

**Companies House scans what it publishes.** Neither PDF has a text
layer — every page is an image. Figures were therefore transcribed by eye
from pages rendered at 300 DPI, not lifted from OCR, because OCR misreads
a digit silently and a wrong digit in a capacity figure is the one error
this project cannot absorb. The OCR of each *cited* page is committed
under `companies_house_ocr/` so the transcription can be re-checked
offline, and `dcp.capacity_claims.verify_ch_quotes` asserts every
transcribed figure still appears in the digits of the page it cites —
a stand-in for the quote round-trip that text-layer sources get.

**Scope, established 2026-08-20.** Per-site megawatts are peculiar to
Ark. The latest full accounts for Kao Data, Yondr Group, Vantage UK,
Global Switch and CloudHQ UK were pulled and OCR'd, and **none states a
capacity figure of any kind**; Virtus filed new accounts on 19 and 20
August 2026 whose documents were not yet retrievable. Ark discloses
per-campus capacity because it is a UK-only company whose entire business
is four UK campuses. What *is* statutory is SECR energy reporting, and
that produces company totals only — which is why the consumption claims
carry `company_level` and are never matched to a site.

Figures, quotes, locators and hand-adjudicated site matches live in
`companies-house-claims.yaml` and load through
`scripts/load_capacity_claims.py`. Two of the six Ark capacity figures
match no site: Meridian Park (an operating Enfield data centre absent
from this corpus entirely) and the A9 building (no location stated).

## ukpn-dc-profiles-per-site.json

Per-site aggregate (96 rows) computed 2026-08-12 from UK Power Networks'
*Data Centre Demand Profiles* (`ukpn-data-centre-demand-profiles`,
~5.4M half-hourly rows, 2023-01-01 → 2026-05, refreshed monthly), via
the portal API `group_by` — same registration gate as above. Fields:
anonymised name, dc_type (78 Co-located / 18 Enterprise), voltage-level
initial (E/H/L), mean and max utilisation (share of the site's meter
capacity), half-hours observed. Key stats: median mean-utilisation 18.1%;
median 3.4-year peak 40.5%; 52 of 92 active sites never exceeded 50% of
meter capacity. Six sites show >100% utilisation (meter capacity changed
mid-period) — per-site values are indicative. Anonymised; never mapped
to sites.
