# External data sources for data-centre capacity and generation

Assessment of third-party and statutory sources that could corroborate,
extend or challenge the capacity figures this project extracts from
planning documents.

Researched 2026-08-10. Every figure below was checked directly against the
source on that date rather than taken from secondary citation. Where a
check produced a null result, the null is recorded — an untested source
and a tested-and-empty source are not the same thing, and the distinction
is the whole point of this file.

**Sections carry their own dates, because sources were added later than
the survey.** A heading reading *in use since ⟨date⟩* means the source
reaches the artefacts: the Environment Agency permits (§6), DESNZ
sub-national consumption (§6), Companies House (§6), NESO's Existing
Agreements register (§3) and operators' own websites (§7). Anything
without that marker was surveyed and not adopted, and the reason is
stated where it sits. Four of those five were live before this file
said so; §3's register, Companies House's status and the whole of §7
were brought current on 2026-08-31.

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

*Built 2026-08-20* as `capacity_claims` plus `capacity_claim_matches`
(migration 021): claims verbatim from the source, site attachment as a
separate hand-adjudicated inference with written evidence, retirable but
never deleted. First source loaded: NESO's Existing Agreements Register
(`data/external_sources/neso-ea-register.xlsx` and its matches file, via
`scripts/load_capacity_claims.py`) — the register surfaced by the
2026-08-19/20 demand-sources research sweep as the only public NESO
artefact naming transmission demand customers with MW.

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

**But the aggregates are published, and by Ofgem rather than NESO.** The
primary source is Ofgem,
[*Consultation Curate – Demand Connections Reform*](https://www.ofgem.gov.uk/sites/default/files/2026-07/Proposed-data-centre-connection-reforms-curate-consultation-document.pdf),
published 29 July 2026, response deadline 16 September 2026. Verbatim,
paragraph 2.7:

> "Between November 2024 and June 2025 total contracted offers in the
> demand queue rose sharply from 41 GW (17 GW transmission, 24 GW
> distribution) to 125 GW (97 GW transmission, 29 GW distribution) in
> June 2025."

And paragraph 2.8:

> "approximately 73 GW of the total demand queue are data centres,
> comprising around 315 data centre projects with total contracted
> capacity ranging from 1 MW to 1,500 MW."

Table 1 of the consultation gives the size distribution:

| Size | MW band | Projects | Total (MW) | % of DC queue |
|---|---|---|---|---|
| Small | 0–10 | 11 | 76 | 0.1% |
| Medium | 10–50 | 47 | 1,370 | 1.9% |
| Large | 50–100 | 51 | 3,492 | 4.8% |
| Extra-large | 100–500 | 166 | 36,632 | 50.2% |
| Hyper | 500+ | 40 | 31,408 | 43.0% |

Ofgem sets that against "peak GB electricity demand in 2025/26" of 45 GW,
and puts implied total capex at £693 billion — around 23% of UK GDP in
2025 — at an assumed £9.5m per MW.

**Handle the 45 GW comparator carefully.** Ofgem's footnote 10 sources it
to NESO Triad Data 2025/26. The primary document is
[*Triads 2025/26*](https://www.neso.energy/document/379521/download)
(NESO, 26 March 2026), which gives the three Triads as **45,004 MW on
5 January 2026**, 41,227 MW on 3 February 2026 and 40,976 MW on
20 November 2025. NESO defines a Triad as one of "the three half-hour
settlement periods of highest **net system demand on the GB electricity
transmission system** between November and February (inclusive) each year,
separated by at least ten clear days."

Net system demand is what the transmission system sees, and is net of
embedded distribution-connected generation. It is therefore **not** total
GB consumption at peak, and the underlying figure is higher. Ofgem is
comparing it against 73 GW of contracted *connection capacity* — a
contractual ceiling, of which a substantial share is distribution-connected
and would be netted off transmission demand entirely. Two different
quantities, exactly as in §1. Attribute the comparison to Ofgem; do not
assert "GB peak demand is 45 GW" in our own voice.

Note also that Ofgem's executive summary says "peak demand in Great Britain
in **2025** was 45 GW" while paragraph 2.8 says 2025/26. The peak fell on
5 January 2026, so the executive summary phrasing is wrong.

**Paragraph 2.10 is the most reportable line in the document:**

> "between May 2024 and August 2025 at least 9 GW of data centres in the
> transmission queue had modified their connection request from a
> 'battery' technology to data centre."

Ofgem adds that stakeholders point to "a financial incentive structure
that make battery, and other technologies, increasingly likely to modify
their current connection to become data centres at the next application
window." Any dataset that classifies projects by declared technology —
including the connection registers themselves — therefore undercounts
data centres, with a named mechanism for how.

**Verified against the primary document, 2026-08-12.** NESO's *Demand
Call for Input – High Level Summary* (March 2026) is published — it is
the download on NESO's
[Demand IRN page](https://www.neso.energy/industry-information/connections/demand-information-request-notice-irn)
([document 378226](https://www.neso.energy/document/378226/download), 8
pages). An earlier draft of this section flagged the figures secondary
commentary attributed to it ("~140 data centres, ~50 GW, 71 at FID") as
unverified. Read directly, the document gives:

- Data centre demand in CFI responses: **50,802 MW across 152 project
  phases** (a project may have several phases; 243 responses in total,
  229 linkable to NESO's connection records, and around 16 GW not
  linkable to a transmission zone).
- Financial commitment with FID evidence, data centres only: **71
  projects (21,598 MW) yes; 77 projects (29,590 MW) no.**
- The same question across all demand technologies: 94 projects
  (27,726 MW) yes; 149 projects (64,274 MW) no.
- Off-takers, verbatim: "Only 32% of data centre projects have secured
  off-takers, while 68% have not yet secured one, often pending a firm
  connection date."
- Planning permission, the caption of a chart whose axes resist exact
  transcription from the PDF: "Most projects have not yet secured full
  or outline planning permission, although a notable proportion have
  applications underway or approved" — the regulator's own evidence that
  the queue and the planning system see substantially different
  populations.

So the commentary was close on count and total and wrong in its framing:
71 at FID is 71 *of 148 data centre respondents to that question*, and
21.6 GW of the 51.2 GW answering. NESO's caveat travels with all of it:
"These CFI insights should be considered indicative only. They represent
developer intent, not confirmed deliverability."

These figures, with locators and access dates, are transcribed once in
`dcp/external_aggregates.py`, which generates both the workbook's
External aggregates sheet and the reader's methodology comparison.
Correct them there, never in the artefacts.

**Route to the project-level data.** Ofgem paragraphs 2.3–2.4 name its own
evidence base, which tells us precisely what NESO holds:

- NESO's **voluntary Call for Input** on the demand queue, issued November
  2025; summary published by NESO March 2026.
- **Project-level data from NESO's mandatory Information Request Notice
  (IRN) to demand projects in the transmission queue, issued 13 March
  2026.**
- Project-level data collected by DNOs from a voluntary call on their
  demand queues, March 2026, aggregated by NESO.

The IRN is the target. It is mandatory, project-level, dated, and a
regulator has publicly confirmed both that NESO holds it and that it has
been analysed — Ofgem's Table 3 is headed "NESO information request notice
estimated capex of data centres by size."

NESO has been a public authority under **both** FOIA 2000 and the EIR 2004
since it launched in 2024, with an Information Rights team, a stated
20-working-day deadline and a published response log. Requests go to
`boxinformationrights@nationalenergyso.com`. EIR is the right frame:
connection data is environmental information under regulation 2(1), and
regulation 12(2) imposes an express presumption in favour of disclosure.

### The Existing Agreements register — in use since 2026-08-20

**The exception to the heading above, and it needs stating plainly**: no
project-level *demand queue* is published, but NESO does publish one
artefact that names transmission demand customers with megawatts, and it
has been a live source in this project since 2026-08-20. Read the two
subsections together — "there is no demand connections register" is true
of the CKAN connection registers and false as a statement about NESO
overall.

`data/external_sources/neso-ea-register.xlsx`, as-at 11 June 2025 per the
file's own banner, loaded by `scripts/load_capacity_claims.py` and parsed
by `dcp/capacity_claims.py`. Header row 5. **119 rows carry
`Transmission Connected Demand`** in the technology column — which the
file spells two ways, so the comparison is case-insensitive — totalling
49,440 MW.

**Quantity type: contracted transmission connection capacity.** A ceiling
someone once agreed with NESO. Not IT load, not built capacity, not
observed draw, and any consumer that renders a claim renders its
`quantity_type` beside it.

**Matching is hand adjudication, not a join.** Every attachment of a row
to a site lives in `neso-ea-register-matches.yaml` with written evidence,
a `method`, a `confidence` from `strong | probable | tentative` (enforced
by migration 021) and a `matched_by` stamp. **18 rows are matched**
(13 on 2026-08-20, five more on 2026-08-31 when the triage's outcomes
were written). The file's `considered:` section is as important as its
`matches:` — it records rows examined and *not* matched with the reason,
because a tested-and-empty result is not an untested one. A row with no
match is a normal, permanent state rather than a backlog item.

**The unmatched cohort was triaged on 2026-08-31, and every row now
carries an outcome** — `docs/NESO_UNMATCHED_TRIAGE.md` for the
row-by-row working, the matches file for the standing adjudications.
The headline for anyone tempted to treat the residue as a work queue:
**61 of the 106 were not data-centre schemes at all**, the register
listing transmission demand customers of every kind — hydrogen
electrolysis, rail traction supply, carbon capture, steel and battery
storage.

### What IS published — 2026-08-12 sweep of the open-data portals

No project-level demand register exists anywhere, but the distribution
side publishes more than the transmission side, and one operator far more
than the rest:

- **UK Power Networks, [Large Demand List](https://ukpowernetworks.opendatasoft.com/explore/dataset/ukpn-large-demand-list/)**
  (`ukpn-large-demand-list`): 496 live, committed, not-yet-energised
  import projects of 5,000 kVA and above across the three UKPN licence
  areas (London, South East, East). Anonymised, but each row carries
  licence area, grid supply point, demand technology type, required
  import capacity (kVA) and application date. The record count and schema
  are public; **row access needs free portal registration** — the
  anonymous CSV export returns headers only.
- **UK Power Networks, [Data Centre Demand Profiles](https://ukpowernetworks.opendatasoft.com/explore/assets/ukpn-data-centre-demand-profiles/)**
  (`ukpn-data-centre-demand-profiles`): half-hourly observed load of
  identified (anonymised) data centres from 1 January 2023, expressed as
  a proportion of each site's meter capacity, by voltage level and data
  centre type. ~5.4M rows at access, refreshed monthly. The only
  published measurement of what data centres actually *draw* as against
  what they secured — the quantity every grid-connection caveat in the
  reader hedges about. Same registration gate. (An earlier
  `ukpn-data-centre-utilisation` dataset is archived in its favour.)
- **NGED's [Connection Queue](https://connecteddata.nationalgrid.co.uk/dataset/connection-queue)**
  publishes per-GSP CSVs with named sites and a `Site Import Capacity
  (MW)` column — but the sampled file (Coventry GSP) contains only
  generation rows (Solar, BESS) with zero import. It is the Gate 2
  generation queue wearing a schema that could carry demand. One GSP of
  ~40 checked; a sweep is cheap if certainty is ever needed.
- **SPEN, Northern Powergrid and ENWL** portals: no demand-queue
  equivalent found in a quick catalogue probe (not exhaustive). The
  ENA-aggregated distribution queue data Ofgem cites in paragraph 2.4 is
  not published as a dataset anywhere found.

A caution that belongs with the UKPN pair: a grid supply point plus a
capacity plus an application date will sometimes identify a project
uniquely. Any such match is a deliberate re-identification exercise
producing an adjudicated, method-labelled inference stored beside the
record — never a join. The workbook's External aggregates sheet states
the same rule in its own header.

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
139 gas rows totalling ~109 GW, and `Eggborough CCGT - OCGT - BESS` at
2,450 MW awaiting consents. Eggborough is also a named data centre
location; whether the two are related is **unverified** and worth checking.

> **Correction, 2026-08-31.** This paragraph previously placed "a
> distinctive cluster of 400–1,025 MW 'Green Energy Centre' projects
> (Cilfynydd, Drakelow, East Claydon, Buntington, Daines, Burwell)"
> *inside* the gas rows. **None of those is gas.** Re-queried against the
> live register: 52 GEC rows across 42 distinct schemes, and the plant
> type on every one of them is some combination of `Demand`, `Energy
> Storage System`, `PV Array (Photo Voltaic/solar)` and `Wind Onshore`.
> Zero carry any gas term. Of 102 rows whose plant type names a gas
> technology, exactly one has a green-energy name — "Didcot High Impact
> Green Energy Hub (HIGEH) 1", a CCGT with storage, solar and wind at
> 1,000 MW — and it is a *Hub*, not one of these Centres.
>
> The error was quoted onward before it was checked (into ROADMAP and
> `docs/NESO_UNMATCHED_TRIAGE.md`, both corrected in the same change),
> which is the cost of a characterisation stated without the field it
> rests on. Where a claim rests on a coded field, name the field.

### The "Green Energy Centre" portfolios — 2026-08-31

Worth its own note because the schemes recur across both NESO artefacts
and hold no planning presence here at all.

**In the TEC register:** 52 rows, 42 distinct schemes, 57–2,050 MW
cumulative. **30 of the 52 carry `Demand` in `Plant Type`** — NESO's own
classification records a demand component alongside the storage and
solar. Two SPV naming families: twenty customers of the form
"⟨substation⟩ NG Limited" (Drakelow NG, Willington NG, Cilfynydd NG …)
and twelve schemes suffixed "(Ethos Green)".

**In the Existing Agreements register:** nineteen of the same schemes
appear as `Transmission Connected Demand`, 8,660 MW between them —
Buntington 850, Hockliffe 850, Navenby 580, East Claydon 500, Hawthorn
Pit 500, Overton 500, Feckenham 500, and so on down to Botley and
Bramford 2 at 200 each.

**Almost every scheme is named after the substation it connects at**
(Navenby GEC at Navenby, Drakelow at Drakelow, Pelham at Pelham), which
is what grid-capacity acquisition looks like before a site is named.
**None of the nineteen has a planning application anywhere in this
corpus** — checked against site display names, member application and
project text, and the curated aliases.

**Why it matters, stated carefully.** Ethos Green Energy publicly
describes its Green Energy Centres as integrated hubs of renewable
generation, long-duration storage *and colocated data centres*, and has
announced a joint development agreement with Frontier Power for up to
5 GW of colocated data-centre capacity. So the `Demand` leg *may* be a
data centre. **The register does not say so**, and the null hypothesis
above — that a `Demand` plant type is the import leg of a storage-and-
solar hybrid — is untested against these schemes and fits the plant-type
coding equally well. What can be said without inference: 8,660 MW of
transmission-connected demand sits behind a name that a search for "data
centre" does not return, and the planning system, as this corpus has
collected it, holds nothing about any of it.

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

### Environment Agency public register — in use since 2026-08-22

The second statutory source to reach the artefacts, and the first that
carries capacity. It works for a reason none of the commercial
directories can copy: a data centre's diesel standby fleet is sized to
peak load plus redundancy, a fleet that size needs an environmental
permit, and the permit is a public document that states the fleet's
rating when the planning application states nothing at all.

The register itself is at
https://environment.data.gov.uk/public-register/downloads/industrial-installations
and is **a zip, not the bare CSV the URL implies**. 5,198 rows; no
capacity column anywhere in it. What it carries is a permit number, a
holder, an address, a grid reference and — for two thirds of the rows
that matter — a link to the permit on gov.uk. So the register is an
index and the permit is the source, which is the opposite way round from
every other dataset in this document.

**Measured yield, 2026-08-21/22.** 97 candidate rows (a curated operator
vocabulary or "data centre" in the holder or address, *and* an activity
type authorising combustion plant). 42 have a permit publication and all
42 yield a readable total thermal input: 7,439 MWth, 31 of them
corroborated by the document's own per-engine breakdown. Eight are
matched to sites by hand. The largest single permit is Amazon's Didcot
North campus: 129 generators, 925 MWth.

**Why it does not breach recommendation 1 below.** It is not an external
MW becoming a site column. Thermal input is its own quantity in the
claims vocabulary and `value_mw` is null on every one of these rows,
because MWth does not convert to MW. Nor is there a constant to convert
it with: the one permit in the set stating both quantities is Telehouse
Docklands, "The rated generation capacity of the SBGs ranges from 1.6
megawatt electrical (MWe) to 2.4 MWe (average thermal input of 5.1
MWth)", which puts thermal input at roughly two to three times the
electrical rating. That spread is a reporter's to apply in the open, and
to state.

**Limits that travel with it.** Existing plant of 1–5 MWth needs no
permit until 1 January 2029, so an absent permit proves nothing.
Emergency-only backup is outside specified-generator permitting unless
the plant provides balancing services or Capacity Market/DSR — which is
the same exclusion that made the Capacity Market register a dead end in
§4, and explains why. Wales is NRW's register and Scotland SEPA's.

**A caution about the fleet, from the permits rather than from
engineering folklore.** A standby fleet is not a measure of load, and
five of the 42 say so themselves: Ark Spring Park's redundancy is
"N+1", "one generator more than would be required to provide the total
power for the site in event of external power failure", and Amazon Hayes
states that "only 12 of the 14 generators would need to operate to carry
the sites electrical load". Where a permit states its redundancy the
reading captures it; the other 37 say nothing about it, and nothing
should be assumed for them.

Licence: Environment Agency Conditional Licence — redistribution
permitted with attribution. The register snapshot is committed because it
is a daily file with no archive behind it; the permit documents are
fetched rather than republished, like everything else under
`data/raw/`.

### DESNZ sub-national electricity consumption — in use since 2026-08-12

The one statutory source surveyed here that made it into the artefacts,
and it carries consumption, not capacity — so it does not touch
recommendation 1 below. DESNZ's
[sub-national electricity statistics](https://assets.publishing.service.gov.uk/media/69427b3736f089d38be1f1ce/MSOA_non-domestic_elec_2010-2024.xlsx)
publish annual **metered** consumption by local authority and meter
type, Open Government Licence v3. The Half-Hourly non-domestic rows are
the meter class data centres belong to.

**What it can see.** Real metered draw, 2010–2024, for every GB local
authority. Between 2019 and 2024 large-user consumption fell 9%
nationally while rising 60% in Slough and 36% in Hillingdon — the two
largest absolute rises of any authority (+650 GWh and +369 GWh; third
place is less than half of second). The nulls are equally visible:
Tower Hamlets, holding the Docklands cluster, fell 15%, and Hertsmere —
with data-centre sites in this dataset — fell 4%.

**What it cannot see.** Anything below local-authority level: the
Half-Hourly class is published only as an "All MSOAs" rollup, and every
per-MSOA row in the source carries **zero** Half-Hourly meters (verified
2026-08-12), so data-centre-scale consumers are structurally invisible
below authority granularity — nothing MSOA-level should ever be built
from this source. The series ends in 2024, so 2025–26 energisations are
not in it. Authority figures are floors: a national "Unallocated" bucket
(~2.9 TWh in 2024) could not be placed anywhere. Northern Ireland is
absent. And an authority's total covers all its large users, so the
figure is context for a site, never attribution to it.

**Where it lives.** The Half-Hourly extract is committed at
`data/external_sources/` with the source workbook's sha256 and the
sanity anchors any re-ingest must reproduce (see its README — the
workbook itself is 9.4 MB and not committed).
`dcp/consumption_context.py` computes the per-site sentence and the
council → authority mapping (an inference, emitted beside the source
values); the workbook's Sites sheet, the reader's site panels and the
External aggregates tables all draw from it, and both exporters print
mapped/unmapped coverage at generation.

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

### Companies House — in use since 2026-08-20, and mostly a null

**The heading used to read "tested 2026-08-20, and mostly a null", which
outlived the testing.** The null below still stands and is the important
part; what changed is that the minority which *does* disclose turned out
to be worth harvesting. The channel is live — **22 claims, 10 of them
matched to sites** — carried in
`data/external_sources/companies-house-claims.yaml` with the filing, the
page locator and a verbatim quote, and every transcribed figure checked
against the OCR of the page it cites before it lands
(`verify_ch_quotes`). Ownership and the scheme SPVs are separate work in
`companies-house-ownership.yaml` and `companies-house-spvs.yaml`; the
single-asset SPV is the reason the null is not the whole story, since a
company whose only asset is one scheme states that scheme's capacity by
construction rather than by choice.

Statutory accounts were surveyed after the August research sweep flagged
them as a possible per-site capacity source. **The generalisation does not
hold.** The latest full accounts of Kao Data, Yondr Group, Vantage UK,
Global Switch and CloudHQ UK contain no capacity figure of any kind;
Virtus filed on 19–20 August 2026 and its documents were not yet
retrievable. Per-campus megawatts appear in **Ark Data Centres Limited**
alone, because Ark is a UK-only company whose whole business is four UK
campuses — the disclosure is a narrative choice in the business review,
not a statutory requirement.

What *is* statutory is SECR energy reporting, and it yields **company
totals, never a site split**. Ark: 280,597 MWh total and 203,608 MWh IT
for calendar 2024. Kao: 121,962.26 MWh for the year to 31 March 2025
(self-verifying — divided by the stated revenue it reproduces the printed
energy intensity of 0.001911 exactly), alongside a PUE of 1.52 and WUE of
0.18, with consumption stated to be metered site by site via MPAN meters
and simply not published at that granularity.

**The number worth reporting comes from putting the two together.**
203,608 MWh of IT load over 2024's 8,784 hours averages 23.2 MW against
108.42 MW of built capacity across the same four sites — **about 21%**.
Total draw including cooling averages 29.5%; implied PUE 1.38. UK Power
Networks' half-hourly metering of around 100 real data centres gives a
median mean-utilisation of **18.1%**. An audited set of company accounts
and a network operator's meters, entirely independent of each other, land
in the same band — which is the empirical answer to treating contracted
or built capacity as demand.

**Corrected again, 2026-08-24: the SPVs are where the capacity is.**
Every company in the survey above is an operator, or an operator's
property company. Neither is where a single scheme lives. **UK Court
Lane DC Ltd** (14045228) holds one asset — a freehold at Court Lane
Industrial Estate, Iver — and its FRS 102 accounts to 30 April 2026
state, in the critical judgements note, that the £205,000,000 valuation
assumes "successful delivery of a 103.3 MW hyperscale data centre".

That is a different KIND of disclosure from Ark's. Ark's per-campus
megawatts are a narrative choice in a business review, which is why they
generalise to nobody. A single-asset SPV's investment property IS the
scheme, so the assumptions the valuation rests on are a disclosure
requirement — the capacity is in the accounts by construction. And the
figure is motivated to be accurate in a way marketing is not: it is what
an external valuer priced and an auditor signed.

It also appears to disagree with the commercial record. Barbour titles
this project "COURT LANE - 140MW DATA CENTRE"; the audited accounts
assume 103.3 MW.

**Resolved, 2026-08-26: it is not a disagreement, and the planning
documents settle it.** The corpus holds this scheme as site 81, and its
own environmental statement states three different figures on three
pages of the same application, ChilternSouthBucks/PL/22/4145/OA:

| Figure | Where | Quantity |
|---|---|---|
| **Total IT Load – 103.32 MW** | p10 | what the servers draw |
| **Total Data Centre Load – 139.5 MW** | p10, same table | IT plus cooling and losses |
| "The proposed development has a **140MW grid connection reserved**" | p27, and p48 of the 2024 application, four occurrences | what the network agreed to supply |

The accounts' 103.3 MW is the **IT load**, rounded from the planning
record's own 103.32. Barbour's 140 is the total data centre load
rounded up, and the grid connection is 140 because the connection was
sized for the total load. The three numbers are consistent, and the
apparent 26% "discrepancy" was an artefact of comparing an IT figure
with a whole-site figure.

Which is the more useful finding, because it says what the SPV figure
*is*: a company's audited valuation assumption can be matched to a
specific quantity in its own planning submission, and doing that
identifies which quantity it is. The general rule stands and gets
sharper — **never compare an external megawatt to a planning megawatt
without establishing that they measure the same thing**; here that took
one join and overturned the headline.

A second scheme at the same location is separately described in the 2024
application as taking "approximately 160MW", so the site record carries
two proposals, not one.

Two further things the same filing carries, both invisible to the
planning record. The auditors flag **a material uncertainty over going
concern**: the funding plan "is dependent on a new investor commitment
which had not been concluded", against £125.6m of net current
liabilities and £33m of deferred consideration due December 2026. And
the ownership is disclosed as far as an LP and no further — "UK Court
Lane DC Holding LP is the immediate parent … UK Court Lane DC Ltd does
not have an ultimate controlling party" — which is why its PSC register
reads "no registrable person". A US LP parent is not a registrable
relevant legal entity, so the chain above it is never recorded. Expect
that pattern on any US-parented scheme; the charges register and the
related-party notes (here, an "NFO Holdings, LLC" facility refinanced in
May 2026) carry more than the PSC page does.

Not every scheme is held this way, and an SPV that has not yet filed
accounts discloses nothing. But where the structure exists, this is the
only source found in this entire survey that states a per-scheme
capacity as a matter of course.

**Swept, 2026-08-26 — and "as a matter of course" is too strong.** The
class was enumerated: 111 companies named in Barbour's owner-role slots,
in `party_applicant` and `party_other` findings, and in
`data/priors/organisation_aliases.yaml` were resolved at Companies House
(`scripts/ch_resolve_spvs.py`), their profiles, filing histories,
charges, PSC registers and officers pulled
(`scripts/ch_pull_filings.py`), and the latest accounts of all 52 that
had filed accounts of a category which *could* carry an
investment-property note were downloaded, rendered and OCR'd page by
page. Every page of all 52 was searched for "MW", "MWh", "MVA" and
"megawatt".

**Ten of the 52 mention megawatts at all.** Four state something the
claims store did not already hold, and they are now in it. The other
six repeat figures already held, or state an emissions intensity.

The decisive negative is **Segro Pure Premier Park Data Centre Limited**
(16311501). It is the same shape as Court Lane — one scheme, one
investment property, an independent external valuation by CBRE, an
IFRS 13 fair-value note — and across 25 pages it states **no capacity
figure of any kind**. Its note says the valuation "incorporates a number
of assumptions including market yields, development assumptions and
comparable market transactions" and does not say what the development
assumptions are. So the disclosure requirement is that assumptions
exist and are material; naming a megawatt figure among them remains the
directors' choice. A single-asset SPV's accounts are where a per-scheme
capacity **can** appear, not where one always does.

**Vantage UK does state a capacity figure, correcting §6's opening.**
Vantage Data Centers UK Limited (06132144) was listed above among the
five operators disclosing none. Its accounts to 31 December 2025, filed
7 August 2026, carry a SECR table with "Total IT load (MW) 41.19"
(2024: 35.28) alongside 505,866,500 kWh of UK energy consumption. It is
a company total, not a site split, and what it measures is not stated —
505,866,500 kWh over the year averages about 57.7 MW of total draw,
which against 41.19 MW of IT implies a PUE of 1.40 and is consistent
with an average IT draw rather than an installed rating. It is loaded as
`company_level`, in the company's own words.

**The one new per-campus figure came from a subsidiary, not a group.**
Ark Data Centres Limited's group accounts name Union Park only in a
forward-looking sentence with no number. **Ark Estates 2 Limited**
(12113969), which holds it, states in its own strategic report that the
site "had 24 MW (2024: 12 MW) of built capacity as of 30 June 2025. In
addition, 48 MW of further capacity is under construction, with a
further 24 MW to be built subject to planning permission." That last
clause is a company telling its auditors how much of its pipeline
depends on a consent it does not have. Reading the estate companies as
well as the group is what found it.

**HFD DataVita Limited** (SC467509) states that its site's designation
as Scotland's first AI Growth Zone "will enable up to 500 MW of AI ready
data centre capacity", and that a committed £112m first phase "will
fully enable 16 MW of AI grade capacity at DataVita's existing Tier III
data centre", with CoreWeave Inc. named as partner. The 16 MW is loaded;
the 500 MW is a zone-level ceiling covering land beyond any application
this corpus holds, and is recorded under `noted:` rather than loaded,
because every quantity type in the store would misdescribe it.

**Nineteen of the 111 have filed no accounts at all** — including
Elsham Tech Park Limited, which holds a 1 GW campus, and Slough Holdings
UK Limited, which holds a 300 MW one. That is a measured null with a
date attached, not a gap in the sweep.

**Ownership is where the class pays.** Details in
`data/external_sources/companies-house-ownership.yaml`; the short
version is that the PSC register alone would have been misleading. It
reads "no registrable person" for 13 of the 111. Probing the charges
endpoint for every company rather than trusting the profile's
`has_charges` flag found charges on **49**, where the flag claimed
five — and the charges are what carry the chain. STX-A10 Limited
(Waltham Cross) discloses no PSC and no parent; its two charges were to
Global Infrastructure UK Limited, whose PSC is **Alphabet, Inc.** The
Register of Overseas Entities turns out to be a *better* ownership
source than the domestic one: it files no accounts, but it compels a
named beneficial owner, so eleven Jersey Vantage vehicles all name
DigitalBridge Group, Inc., and Manor Farm Propco Limited — the 147 MW
Slough scheme — names Tritax Big Box REIT plc.

**And the confirmation statement is the cheapest thing in this survey.**
It answers a narrower question than the PSC register — who holds the
shares, not who has significant control — and it answers it for
companies where the PSC register is silent. It is also, uniquely among
the Companies House documents read for this project, **filed
electronically with a text layer**, so shareholders are extracted rather
than transcribed: no OCR, no risk of a silently misread character. 57 of
the 111 yielded a list, 178 shareholdings in all; the 21 that yielded
nothing are all overseas entities or LLPs, neither of which files a
CS01.

Two traps, both of which cost real names before they were fixed. The
most recent statement is usually the wrong one — a
"confirmation-statement-with-no-updates" carries no shareholder block by
definition, and 48 of the 111 filed one most recently — so the history
has to be walked back to the last filing that names holders. And the
block is a two-column table that `pdftotext` scrambles without
`-layout`: reading it naively recovered two of Sequence (Iver) UK
Limited's ten shareholders, and truncated one name to "THE INVESTMENT
AND DEVELOPMENT OFFICE OF THE", which in full is "…OF THE GOVERNMENT OF
RAS AL KHAIMAH" — a UAE sovereign investment office holding shares in
Pure Data Centres Group, SEGRO's joint-venture partner at Premier Park,
and invisible on that company's PSC page.

Some of what it named. UK Court Lane DC Ltd's seven ordinary shares are
held by **UK Court Lane DC Holdings, LP**, the immediate parent its PSC
page cannot record. Bucks DC Limited is held by **SOF-12 Bucks DC UK
Holdco Limited** — Starwood Opportunity Fund XII, one vintage later than
the SOF-11 vehicle holding Greenwich, so two London schemes sit in
different funds of the same manager. "IRE EVAF II The Fort Propco
Limited" turns out to stand for **Invesco** Real Estate European
Value-Add Fund II, which the confirmation statement spells out and the
PSC register does not. Sequence (Iver) UK Limited, whose PSC page names
nobody, has eleven shareholdings across two classes led by a Luxembourg
SCSp. And Google's Global Infrastructure UK Limited is held by **Raiden
Unlimited Company** — an unlimited company, a form exempt from filing
accounts, sitting between the UK land vehicle and Alphabet.

Acquisition notes: the API needs a key (`CH_API_KEY`), and the document
endpoint 302s to S3, which rejects a request still carrying the
Authorization header — follow the redirect unauthenticated. The S3 URL
it hands back is signed and expires in 60 seconds, so fetch it
immediately rather than passing it around. Everything
Companies House publishes is scanned, so figures are transcribed from
rendered pages by eye and re-checked against committed OCR of the cited
page; see `data/external_sources/README.md`.

---

## 7. Operators' own websites — in use since 2026-08-30

Absent from this file until 2026-08-31, which was an omission rather than
a judgement: by claim count it is the **second-largest channel** in the
store, and the only one where the party making the claim is the party
that owns the asset.

**What it is.** 80 claims from operators' own pages, held in
`data/external_sources/operator-claims.yaml` with
`dcp/operator_pages.py` and the site→page prior
`data/priors/operator_pages.yaml` — 39 page entries across 31 sites,
since a site can hold both a corporate and a consultation page, and the
loader keys by site. 43 claims are matched to sites.

*Why the file and the table give different counts, and why the table is
right:* the file holds 80 claims and the store holds 81
`operator_website` rows. **This is the append-only design working, not a
drift.** The file states the current reading of each claim; the table
keeps every reading ever taken. Exactly one claim has been read twice —
`CyrusOne LON1 (Slough)`, at 8.72 MW on 2026-08-20 and 9 MW on
2026-08-28 — and both rows stand, with their own quotes and snapshots.

That single pair is the best argument in this file for the snapshot
discipline, and the claim's own note says why: *"The figure changed under
us, and the snapshot guard is how we know … an operator replacing a
precise published figure with a round one is a fact about the
disclosure, and 8.72 is what anyone citing this site before 2026-08-28
would have quoted."* Eight days apart, no announcement on the page,
floor area unchanged at 4,309 sq. m. The grid-supply claim from the same
page did not move.

So when counting, **fold to the latest reading per claim** — do not treat
the extra row as an orphan and do not count the raw table as a claim
total.
Every claim is quote-verified against a **same-day snapshot** in
`data/external_sources/operator_snapshots/`, because a marketing page has
no register behind it: nothing preserves what a redesigned site used to
say, so a claim without a snapshot taken at claim time is unciteable
later.

**Where it sits in the authority order — the weakest, and labelled so.**
Marketing material, not an audited or regulatory disclosure. It renders
with the operator's own name attached rather than a generic source label,
because *who is saying it* is the entire point of the weakest-authority
source.

**Typed standing, not equal standing** (decided with Luke, 2026-08-30).
This is a deliberate, scoped revision of the 2026-08-20 ruling that no
external megawatt reaches a scannable row. **First-party operator
statements about the operator's own facilities** may become a labelled
rung on the declared-power ladder and may be admissible to
`at_least_100mw` with the basis named — because operator pages are
campus-level, facility-named and single-basis, which is the comparability
the planning corpus lacks. **Third-party aggregates stay tier-and-count**
(§2 above, and `dcp/external_aggregates.py`). The ruling was about
comparability, and a labelled rung is how the ladder already handles
incomparability. Conditions travelling with it: the snapshot discipline
above, and that the planning-disclosure finding survives elevation — "no
document ever stated this campus's load on a common basis" stays
reportable.

**Two findings the channel produced that the others could not.**

*The denominator, sourced.* A campus roster on an operator's own page
gives a sourced count of facilities, so "three of five facilities
disclose" has a citable five. VIRTUS's Saunderton datasheet also
self-audits: 9.5 + 22.5 + 16 + 30 against a stated "Campus Total of
78 MW", exact — the benchmark for when a sum can ever be trusted, and
snapshotted and loaded as four matched claims on 2026-09-01. Its
Slough campus states 145.5 MW against 132.2 summed from its own seven
rows, which is a discrepancy worth putting to the operator.

*The audiences finding.* Pages carry a `kind` — `corporate` or
`consultation`, the tell for the latter being a stated consultation
period — because they say different things to different readers. Five of
the first five sites holding both kinds stated megawatts on the corporate
page and nothing on the consultation page (East Havering 600, West London
Tech Park 90, Iver Heath 90, Abbots Langley 96, Humber 384). Apatura is
the counter-example: its consultation pages state capacity and are also
its only scheme presence. The working hypothesis is that silence appears
where a developer runs *two* pages and can segment audiences — one page,
one story; two pages, two stories. Because "the consultation site doesn't
say" is a negative result, each silent page needs its own snapshot, and
consultation-window dates let the silence be timed against what the
application had already told the council.

**Limits.** Coverage is whatever the operator chose to publish, so
absence proves nothing about a site. Figures are undated unless the page
dates them. A page can restate a campus total that overlaps another
claim, so these must never be summed across pages — the Saunderton
facility rows are held as components of the campus total beside it, and
adding the five together would double the campus. The fetcher took HTML
only until 2026-09-01; it now sniffs and extracts PDFs, which is what
made VIRTUS's Saunderton spec sheet — and with it the survey's only
self-auditing campus arithmetic — citable at all.

---

## 8. Recommendations

1. **Do not add any external MW as a site column.** Nothing surveyed here
   measures the same quantity as a planning application, and DCM's planned-
   site figures are derived from the same documents this project reads.
   *Still holds.* The Environment Agency permits added in §6 are the
   test of it: they are the strongest external figures found anywhere in
   this survey, they are statutory, and they still went in as claims
   beside the planning data with their own quantity type rather than
   into a column.
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
Eggborough gas/data-centre relationship and every address-level link
between a Capacity Market entry and a neighbouring planning consent in
§5. Do not repeat either without checking. (The 140/71 Final Investment
Decision figures previously flagged here were resolved against the
primary NESO document on 2026-08-12; §3 carries the verified figures.)

**Correction, 2026-08-10.** An earlier draft of this file attributed the
41 GW → 125 GW demand queue growth to "NESO's connections-reform documents
and legal summaries", and stated that a NESO data request "found around
140 data centre projects claiming to have reached Final Investment
Decision". Both came from search-result summaries rather than primary
documents. The queue figure is Ofgem's, published 29 July 2026 and quoted
verbatim above; the 140-at-FID figure could not be traced to any primary
source and was flagged as unverified. The law-firm briefing originally
credited with the figures contains neither of them.

**Resolution, 2026-08-12.** The document behind the FID figures — NESO's
*Demand Call for Input – High Level Summary* — was located on NESO's IRN
page, downloaded and read. §3 now quotes it directly, and the same-day
sweep of the network operators' open-data portals above records what is
and is not published. The transcribed figures live in
`dcp/external_aggregates.py` and flow from there into the workbook and
the reader.
