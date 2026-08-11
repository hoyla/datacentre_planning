# External data sources for data-centre capacity and generation

Assessment of third-party and statutory sources that could corroborate,
extend or challenge the capacity figures this project extracts from
planning documents.

Researched 2026-08-10. Every figure below was checked directly against the
source on that date rather than taken from secondary citation. Where a
check produced a null result, the null is recorded — an untested source
and a tested-and-empty source are not the same thing, and the distinction
is the whole point of this file.

Companion to [prior_art.md](../prior_art.md), which covers *published
reporting*. This file covers *data sources*.

---

## 1. The problem that makes all of these hard to compare

The House of Commons Library briefing
[CBP-10315](https://commonslibrary.parliament.uk/research-briefings/cbp-10315/)
(August 2025) states it plainly: **there is no formal definition of what a
data centre is.** There is likewise no agreed definition of what its "MW"
means.

Every source below therefore measures a different quantity, and none of
them labels which:

| Source | What its MW actually is |
|---|---|
| Planning applications (this project) | Total site electrical capacity as applied for |
| Data Center Map / Baxtel | Mixed — operator IT-load marketing **and** press-derived build-out, in the same field |
| NESO TEC register | Contracted transmission **export** capacity (generation only) |
| Capacity Market Register | De-rated dispatchable capacity, at portfolio level |
| CCA scheme | Metered annual **consumption** (TWh, not MW at all) |
| DC Byte | Probability-weighted pipeline |

**Design consequence.** No external MW should ever be merged into a single
capacity field. Capacity claims belong in an append-only structure — one
row per `(site, source, quantity_type, value, stage, as_at, source_url)` —
with no adjudication between them. The divergences are findings. They only
survive as findings if both numbers are kept.

---

## 2. Commercial directories

### Data Center Map (datacentermap.com)

Danish company (Data Center Map ApS), operating since 2007, behind Vercel
bot protection. Business model is a colocation lead-generation marketplace
with paid "premium member" listings; green map pins are paid, blue are
free.

Their [About our data](https://www.datacentermap.com/research/data/) page
is unusually candid and carries a country filter. UK-scoped:

| Data point | Global | UK |
|---|---|---|
| Total listings | 13,680 | **639** |
| — with Power in MW | 5,084 | **302** |
| — with coordinates | 12,774 | 625 |
| — with PUE | 964 | 91 |

The widely-quoted 5,084 figure is **global**, not UK. Their headline "568
UK facilities" also counts campus parent listings and their child
buildings separately — Humber Tech Park is four listings, Wycombe Air Park
is seven.

**Accuracy check against planning documents.** Tested against the three
best-documented UK sites, using the Foxglove/GAP figures transcribed in
[foxglove_top10.md](../data/prior_art_sources/foxglove_top10.md):

| Site | Planning document | DCM | Gap |
|---|---|---|---|
| Humber Tech Park (Greystoke) | 384 MW | 384 MW | exact |
| QTS Cambois, Blyth | 1,100 MW | 720 MW | −35% |
| VIRTUS Saunderton | 300 MW | 75 MW | −75% |

All three are labelled identically as "Fully Built-Out Power".

The mechanism is visible on the pages themselves. VIRTUS is a paying
member — spec sheet attached, security and amenities self-supplied — so
75 MW is the operator's marketing figure for saleable IT load. Greystoke
supplies DCM nothing: the Humber Tech page shows "No data supplied by
Greystoke" under POWER while displaying 128 MW under CAPACITY, and its
whitespace figure of 1,108,682.6 sq ft is an unrounded conversion of
exactly 103,000 m². That number was read off metric source material —
almost certainly the same planning documents this project ingests.

**So DCM's planned-site figures are not independent corroboration.** Using
them would be circular.

**Licensing.** Their [terms](https://www.datacentermap.com/legal/terms/)
clause 3 prohibits scraping *and* — in a separate sentence aimed squarely
at manual workarounds — states that "human access of the Site may not be
used to copy, download or in other ways retrieve data from the Site for
integration in to an external database." As a Danish company they also
benefit from EU sui generis database right independent of contract.

**But** their [research page](https://www.datacentermap.com/research/)
states: "We support staff Journalists with pro bono data exports upon
inquiry." Their "Referenced In" wall includes AP, Washington Post, BBC,
LA Times, Wired, Le Monde and the IEA. Asking is the route; a draft
request is held separately.

### Baxtel (baxtel.com)

~8,000+ sites globally. Materially more permissive terms: section 2.4
permits public site data to be "shared or referenced in artiles, research,
publications etc. so long as Baxtel is properly cited and backlinks, where
applicable." Scraping remains prohibited under section 3, and section 4.3
bars derivative works — the tension between 2.4 and 4.3 is worth a written
confirmation before relying on it.

Already the basis of published academic work: Maria Savona, Centre for
Inclusive Trade Policy, University of Sussex,
[Mapping the UK's data centres build-out](https://citp.ac.uk/publications/mapping-the-uks-data-centres-build-out-implications-for-digital-sovereignty)
(7 July 2026) — **348 live UK sites, 2.0 GW operational, 0.87 GW under
construction, 10.88 GW announced or permitted**, split 313 England / 14
Scotland / 12 Wales / 9 Northern Ireland, with 218 in London. A blog post
rather than peer-reviewed work, and the underlying dataset is not
published.

Set that 348 against DCM's 568 and the Commons Library's ~450. The spread
is the definition problem, not error.

### DC Byte

London-based; the source the trade press and consultancies cite for
pipeline. Their framing is the useful part — pipelines "measured by
delivery probability, not announced capacity," which is precisely the
discipline planning data lacks, since a permission is not a building.
Commercial, but publishes a free
[Global Data Centre Index](https://www.dcbyte.com/global-data-centre-index/).

### Not worth pursuing

Cloudscene, PeeringDB and datacenters.com are connectivity directories
with no capacity data. CBRE, JLL, Knight Frank, Savills and Cushman &
Wakefield publish free quarterly European reports with MW take-up —
citable, aggregate, London-skewed. Structure Research, Synergy,
datacenterHawk, Uptime and DCD Intelligence are all paid.

---

## 3. NESO: what exists and what does not

### There is no demand connections register

Checked directly against the NESO CKAN API
(`api.neso.energy/api/3/action/package_search`). The catalogue holds three
connection registers — **TEC**, **Embedded** (Scottish generation) and
**Interconnector**. All are generation-side. Every dataset matching
"demand" is a forecast or an aggregate.

**The widely-quoted figures are commentary, not data.** The 125 GW demand
queue (up from 41 GW in November 2024), the ~140 data centre projects
claiming Final Investment Decision, and the 99 GW of transmission-connected
demand through Gate 2 all appear in NESO's connections-reform documents
and legal summaries. None is a downloadable per-project register. The Gate 2
"EA Register" is a PDF limited to projects that consented to be named.

**Route to it:** NESO has been in public ownership since 2024 and is very
likely a public authority for Environmental Information Regulations
purposes; connection queue data is environmental information. Because NESO
has already published the aggregate and the FID count, a request for the
underlying project list is well-founded rather than speculative. EIR is a
broader and harder-to-refuse regime than FOIA.

### The TEC register does not find co-located generation

`transmission-entry-capacity-tec-register`, NESO Open Data Licence, CSV,
refreshed twice weekly. 2,212 rows as at 7 August 2026. Fields:
`Project Name`, `Customer Name`, `Connection Site`, `Stage`,
`MW Connected`, `Cumulative Total Capacity (MW)`, `MW Effective From`,
`Project Status`, `Agreement Type`, `Plant Type`, `Gate`.

**Zero data centres.** A keyword sweep for
`data cent|datacent|hyperscale|AI factory|tech park` plus the named
benchmark operators and sites returned nothing. The 106 rows carrying
`Demand` in `Plant Type` are the import leg of battery and solar hybrids,
not load customers.

**Tested for co-location detection against the nine anchors in
[data/colocated_energy_spike/](../data/colocated_energy_spike/) and it
fails.** Two reasons:

1. **No coordinates.** Location is given only as a `Connection Site`
   substation name, and a 400kV substation's catchment is regional. Every
   anchor matched something, and nearly all of it is noise: Blyth returns
   Berwick Bank offshore wind, Elsham returns the pre-existing Keadby CCGT
   complex, Hull returns Drax.
2. **Wrong weight class.** TEC entries run 400–4,000 MW. The spike's clean
   positive — the 21 MW gas-fired energy reserve facility at Yorkshire
   Energy Park, 14 reciprocating engines, consented six years before the
   data centre — is distribution-connected and could never appear.

**PlanIt spatial search remains the correct tool for co-location.** The
staged plan in the spike's `findings.md` stands.

**What TEC is honestly good for:** national context on the gas build-out.
139 gas rows totalling ~109 GW, including a distinctive cluster of
400–1,025 MW "Green Energy Centre" projects (Cilfynydd, Drakelow, East
Claydon, Buntington, Daines, Burwell) and `Eggborough CCGT - OCGT - BESS`
at 2,450 MW awaiting consents. Eggborough is also a named data centre
location; whether the two are related is **unverified** and worth checking.

---

## 4. The Capacity Market Register — the one that pays

`capacity-market-register`, NESO Open Data Licence, CSV. Components table
29,583 rows, CMU table 18,080 rows, as at 5 August 2026.

Structurally the best-matched source to this project: **99.5% of
components carry a postcode and 90.6% an OS grid reference**, so it joins
to sites on geography without fuzzy name matching.

**Data centres are invisible to any operator-name search.** The named
applicant is always an aggregator — E.ON, Enel X, Flexitricity, Bryt
Energy — never the site owner. A search of the CMU table for data centre
operators returns zero. The sector appears only in free text: regex over
`Description of CMU Components` and `Location and Post Code`.

That search returns **14 named data centre sites across 13 CMU IDs**:

| Site | Register description |
|---|---|
| 670 Ajax Avenue, Slough SL1 4BG | "Back up generator at a data centre"; later "DSR Component providing load turn down at a data centre" |
| Gyron Campus, Spring Way, Hemel Hempstead HP2 7SU | "Large data centre with back up generator on site" |
| 150 Maylands Avenue, Hemel Hempstead HP2 7DF | "Back up generator at a data centre" |
| Centro 3, Maxted Close, Hemel Hempstead HP2 7SU | "Back up generation at a data centre" |
| Citi Riverdale Data Centre, Lewisham SE13 7EY | "two Combined Chilling/Heating and Power plants (CCHP)… each with a connection capacity of 1.4MW, totalling 2.8MW" |
| Citibank Data Centre South, Molesworth Street | "Existing gas powerd CHP autogeneration unit" |
| Bootle Data Centre, Bridle Road L30 1PH | "two 1.4MW caterpillar generators" |
| Ark Data Centres, Cody Park, Farnborough GU14 0LH | 6 MW / 6.9 MWh battery |
| ATOS Andover Data Centre SP10 1DL | 2 MW / 2.3 MWh battery |
| Stellium Data Centres, Cobalt Park, NE28 9EJ | 2 MW / 2.3 MWh battery |

E.ON's DSR units carrying the Slough and Hemel components — DS1801 and
DS2101 at 30 MW connection capacity / 25.9 MW de-rated, plus DS1817,
DS2111, EHQ002 and EHQ003 — record `Capacity Agreement Awarded: Yes`.

**Why this matters editorially.** Kit described to the planning system as
emergency backup appears in a statutory register as a dispatchable
capacity resource under an awarded agreement. That is gotcha #5 in
prior_art.md, evidenced in a government dataset rather than inferred.

**Three caveats that stop this being a column.** Capacity sits at
CMU-portfolio level, not component level — these sites are *components of*
a 30 MW aggregated portfolio, and no per-site MW can be claimed. Delivery
years run 2018–2025, so much is historic. And all 14 are existing
colocation sites; **none of the hyperscale pipeline appears**, which is a
null worth stating in its own right.

Fourteen sites is a hand-checkable list for a reporter, not a pipeline
stage.

---

## 5. Planning cross-check of the Capacity Market sites

Read-only reconnaissance via PlanIt spatial search at 400 m around each
site's postcode. **Caveat: three of the five searches returned exactly 150
records, the page-size cap, so those results are truncated and the absence
of a record proves nothing.** Proximity also does not confirm that a
neighbouring consent belongs to the same operator — the address-level link
is unverified in every case below.

The searches did not pin a specific generator consent to a specific
Capacity Market component. They surfaced something more useful.

### Generator capacity accretes through small separate applications

At 672 Galvin Road, Slough — the same trading estate as the Ajax Avenue
Capacity Market entry — **P/00348/011** (16 January 2023, Conditions):

> "Installation of 4no. new generators into the existing external yard
> area to the north of the site cladded in louvre panels, and the
> installation of 2no. DAC units…"

The same site had earlier consents for 1.6 MWp of rooftop solar (2015) and
a lawful development certificate to convert a floor into a new data centre
(2022). At Hemel Hempstead, `4/02386/03/FUL` (2003) is simply
"Construction of single storey building to house generator."

**This is the Yorkshire Energy Park pattern at building scale.** Generator
capacity is not disclosed once in the main data centre permission; it
accumulates through minor, separately-referenced applications filed years
apart, each individually unremarkable, none of which mentions capacity in
MW. A sweep anchored on the main data centre consent will systematically
undercount installed generation — and the aggregate is only visible if
those follow-on applications are linked back to the site.

### Two naming-invisibility cases

Both would be missed by any search keyed on "data centre":

- `4/00976/12/MFA` (Dacorum, 2012): "Construction of one data centre unit
  **(class b8)**" — consented under the storage and distribution use class.
- `P/17941/000` and `P/17941/001` (Slough, 2019 and 2020, both withdrawn):
  "Change of use of the site for **fibre exchange (Sui Generis)**,
  installation of two generators…"

These belong with the existing invisibility-flag work from the `dc_build`
trial.

---

## 6. Other statutory sources

**Climate Change Agreement scheme.** Administered by techUK under DESNZ
policy, with the Environment Agency holding target-unit data. 170+ UK data
centre sites reporting **metered and audited** electricity consumption —
techUK's claim is that the UK "may be the only country where sector energy
consumption is measured using auditable data in this way." Aggregate is
published; site-level is an FoI target. This project already touches it
indirectly through the Digital Realty 408,041 tCO2e anchor in prior_art.

**Embedded Capacity Registers.** All six DNOs, monthly, on open-data
platforms. **Demand connections are excluded** except storage import, so
they are no use for data centre load. They do cover distribution-connected
generation ≥1 MW (Electricity North West goes to 50 kW).

**EU Energy Efficiency Directive 2023/1791** and Delegated Regulation
2024/1364. Every EU data centre with ≥500 kW installed IT power must
report annually to a European database: floor area, installed power,
energy consumption, capacity utilisation, waste heat, water. First reports
September 2024, annually each 15 May thereafter. **The UK has no
equivalent.** This is both a comparator jurisdiction where the numbers are
statutory filings rather than marketing claims, and a story in itself.

**Parliamentary briefings.** Commons Library
[CBP-10315](https://commonslibrary.parliament.uk/research-briefings/cbp-10315/)
(August 2025): ~450 large UK data centres, 2.5% of UK electricity,
3.3–6.3 GW by 2030, "almost 100 new data centres could be built in the
next 5 years." Also POSTnote
[PN-0762](https://post.parliament.uk/research-briefings/post-pn-0762/).

---

## 7. Recommendations

1. **Do not add any external MW as a site column.** Nothing surveyed here
   measures the same quantity as a planning application, and DCM's planned-
   site figures are derived from the same documents this project reads.
2. **Do not build TEC or the Capacity Market as pipeline stages.** TEC does
   not work for co-location; the Capacity Market yields 14 sites, which is
   an afternoon of reporter verification rather than an engineering task.
3. **The highest-value engineering remains the PlanIt co-location sweep**
   already scoped and costed in the May spike — extended, on the evidence
   in §5, to link follow-on generator applications back to their parent
   site.
4. **Two requests are worth more than any download:** an EIR request to
   NESO for the project-level demand connection queue, and an FoI to
   DESNZ/EA for site-level CCA consumption.
5. **Ask Data Center Map and Baxtel** rather than working around their
   terms. Both have journalist or research provisions.

---

## Verification notes

Everything above was checked on 2026-08-10 against live sources. The
reconnaissance scripts were run from a scratchpad and deliberately not
added to the repository; no project database or code was modified.

Unverified claims are flagged inline as such — specifically the
Eggborough gas/data-centre relationship, and every address-level link
between a Capacity Market entry and a neighbouring planning consent in §5.
Do not repeat either without checking.
