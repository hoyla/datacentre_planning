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
