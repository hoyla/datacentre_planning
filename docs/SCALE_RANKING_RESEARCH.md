# Ranking scale without a megawatt, and the sources not yet tried

Researched 2026-08-22, in answer to two questions from Luke: how do we
rank the projects we cannot rank — enough to choose the fifty worth
manual corroboration — and what routes to power use, on-site generation
and environmental impact have we not yet considered?

Companion to [EXTERNAL_DATA_SOURCES.md](EXTERNAL_DATA_SOURCES.md), and
subordinate to it: that file's discipline is that a source is checked
directly before anything is built on it, and its recommendation 1 — no
external megawatt ever becomes a site column — is not relitigated here.
This note surveys **candidates**. Items are marked *checked 2026-08-22*
where the source was reached during this research, and **[unverified]**
where they rest on general knowledge or a search-result summary and must
be checked before anything is built or printed. Several entries record
an expected null; per the house rule, the null will be worth recording
when it is confirmed.

---

## 1. The problem, measured

The published reader (456 site rows, boundary 2026-08-22) splits the
universe cleanly:

| Cohort | Sites | What would rank them |
|---|---|---|
| A figure on some basis (IT load 89, total demand 3, grid connection 2, standby-implied 24, floorspace-estimated 43 — counted from the reader's basis column) | **152** | Ranked already; 34 sites ≥100 MW |
| Read and silent — documents held and analysed, no figure | **151** | External audiences and value proxies |
| No documents held | **127** | Metadata proxies, then acquisition |
| Pre-planning, no application yet | **26** | Announcements, corporate and land records |

Two calibration points sharpen what "top fifty" means:

- **Ofgem's own count says the giants exist.** The July 2026 Curate
  consultation (already transcribed in
  `dcp/external_aggregates.py`) puts **206 data-centre projects at
  ≥100 MW** in the connection queue — 166 at 100–500 MW, 40 above 500.
  The corpus knows 34 sites at ≥100 MW. Some of the difference is
  queue-versus-planning population (NESO's own CFI says most queue
  projects lack full permission), some is speculative queue entries that
  will never file — but the gap is the triage problem in one number,
  and the direct fix is the NESO IRN EIR already contemplated in
  ROADMAP, which would enumerate the ≥100 MW population project by
  project.
- **The claims layer already ranks sites planning cannot.** Six
  no-figure sites carry a strong external-claim match in the current
  reader — Kao Harlow, Eggborough, Drax and West Burton among them,
  all placed by NESO register claims on sites holding no or few
  documents. That mechanism works; most of this note is about feeding
  it.

The three unranked cohorts need different instruments, so the sections
below are organised by what each can see. Nothing here proposes a
published number: the aim is a defensible *worklist ordering*, the same
status as `worth_deep_read`, with the evidence for each site's position
printed beside it.

---

## 2. Value figures — the direct answer to "is there a value?"

**Yes — and one of them is already in the database.**

### 2.1 Barbour ABI project value — held, exported, not yet used to rank

`projects.value_gbp` has been ingested since migration 005 and already
reaches the workbook as `barbour_value_gbp`
(`scripts/export_handover.py`). Estimating construction value is
Barbour's core business, and it is exactly the "value of the project"
figure the question asks for. What has never been done is to *use* it:
measure coverage against the unranked cohorts and sort by it.

First action, zero acquisition cost — run against the live database:

```sql
SELECT ss.basis, count(*) AS sites,
       count(*) FILTER (WHERE b.v IS NOT NULL) AS with_value
FROM   site_scale_by_site ss                -- however the export derives basis
LEFT JOIN (SELECT pa.application_id, max(p.value_gbp) AS v
           FROM projects p JOIN project_applications pa ON pa.project_id = p.id
           GROUP BY pa.application_id) b USING (application_id)
GROUP  BY ss.basis;
```

(Shape, not copy-paste — the real join goes through `site_members` the
way `export_handover.py` line ~202 already does.)

Caveats that travel with it: Barbour's values are frequently their own
estimates derived from floorspace and building type, so for some rows
this is the floorspace proxy wearing a currency sign — an ordering
signal, not corroboration. One campus maps to several projects
(outline, fit-out, civils): rank on `max`, never `sum`, until a human
has looked. 253 projects cover well under half the universe, and the
export is from one moment — **a refreshed export is a licence
conversation, not an engineering task**, and worth asking the data team
for, this time with the value fields explicitly in scope for the whole
universe. Credit required in anything published. (Glenigan sells the
same class of data if Barbour cannot refresh; commercial,
**[unverified]** terms.)

### 2.2 Ofgem's capex yardstick, inverted in the open

Ofgem assumes **£9.5m per MW** in the Curate consultation (its Table 3
capex model — already quoted in EXTERNAL_DATA_SOURCES §3). Dividing a
credible project value by it gives an implied MW band. This is a
reporter's arithmetic to do in the open with the assumption stated —
the same posture as the MWth caveat — and it never enters `value_mw`.
For ranking, skip the conversion entirely and sort on the value itself.

### 2.3 Companies House balance sheets — capex, not capacity

The 2026-08-20 survey established that accounts do not disclose
*capacity* (Ark excepted). They do disclose **money**: an SPV building
a campus capitalises it, so fixed assets / assets under construction
approximate cumulative capex, and year-on-year additions are build-out
pace. This is a different question from the one already tested, and it
is bulk-automatable: Companies House publishes **free daily and monthly
bulk files of iXBRL accounts**, with monthly archives back to 2008
(*checked 2026-08-22*:
[Accounts Data Product](https://resources.companieshouse.gov.uk/infoAndGuide/faq/accountsDataProduct.shtml),
[historic monthly files](http://download.companieshouse.gov.uk/historicmonthlyaccountsdata.html)).
Parse `FixedAssets` / `AssetsUnderConstruction` tags for the applicant
SPVs the corpus already names.

Caveats: the bulk product carries electronically-filed accounts
(~97% iXBRL); the large image-scan filings this project has already
fought (Ark, Kao) are not in it, so coverage will be patchy exactly at
the top — but SPVs typically file small-company accounts
electronically, and a small-company filing still contains the balance
sheet. Group-level capitalisation can hide site splits; leasehold
structures (operator leases shell from propco) put the capex in a
different company — the VIRTUS propco/opco lesson applies verbatim.

### 2.4 Land as value: price paid and corporate ownership

HM Land Registry's **Price Paid** data and the **UK companies
(CCOD) / overseas companies (OCOD) ownership** datasets are free
(registration for CCOD/OCOD) **[unverified — terms and coverage not
checked this pass]**. Two uses: purchase price of an assembled site as
a crude value floor, and — more useful — sweeping ownership for
hyperscaler-affiliated SPVs to find **land banks before any
application exists**, which is the pre-planning cohort's problem.
DC01, the unidentified Foxglove case, is on ROADMAP as "most likely
falls out of an operator-name sweep"; title ownership is a second
route to the same answer.

### 2.5 Announced investment values

Government and operator announcements routinely state "£X bn
investment" where no planning document states a megawatt. The
`capacity_claims` vocabulary already has `announced_capacity`; an
`announced_value` quantity beside it would let the existing machinery
hold these — verbatim, dated, weakest-authority-labelled, matched by
hand like everything else. The operator-snapshots fetcher is the
infrastructure; gov.uk press releases are fetchable and stable.

---

## 3. Ranking signals already in the corpus

### 3.1 PlanIt's `app_size` — free, and covers the no-documents cohort

Already a column on `applications` (`dcp/repo.py`). Coarse
(Small/Medium/Large), source-classified, but present for every PlanIt
row **including the 127 sites with no documents** — which no
document-derived signal can say. A "Large" no-documents site outranks a
"Small" one for acquisition effort. Measure its agreement with the
banded scale on the 152 ranked sites before trusting it further.

### 3.2 An Environmental Statement is a scale claim in itself

EIA is triggered by thresholds, so the *presence* of an ES — multiple
volumes, technical appendices, a Non-Technical Summary — is a floor on
scale that costs nothing to read because it is derivable from document
titles already held (`classify_kind` territory, not model territory).
The converse is the story the project already knows from Elsham
("got a no-EIA Screening Opinion"): a big site *without* an ES is a
finding, not a gap. A `has_environmental_statement` flag per site,
derived from titles, would both rank and flag.

### 3.3 Raising floorspace coverage from the forms

Floorspace is known for ~168 sites, and drives the estimate for 43.
Two document families state it in fixed fields rather than prose, and
may have resisted the prose-shaped deep read:

- The **1APP application form** ("gross internal floorspace to be
  created") — held for most applications, frequently scanned;
- The **CIL Additional Information form**, which states GIA precisely
  where CIL applies.

A deterministic, form-targeted pass (regex over the cached text of
documents titled "Application Form" / "CIL") is the cheap experiment.
If the forms are image-scans, their `no_text`/OCR status is already
recorded, so the size of the recoverable population is measurable
before any work is done.

On Luke's "ten storeys versus a bungalow" objection: the estimator
already uses **gross internal area, which sums storeys** — footprint is
the wrong quantity and mostly isn't what the signals carry. One
tightening is available: `FLOORSPACE_SIGNAL_TYPES` currently includes
`building_footprint`, which *is* the bungalow number. Worth either
excluding it or pairing it with a storey count where drawings state
one. The honest limit stands regardless: the corpus's own calibration
says ×2 spread either way, which is band-quality, not print-quality —
and band-quality is all a top-fifty needs.

### 3.4 The planning fee is a floorspace disclosure nobody reads

Application fees in England are a piecewise-linear function of
floorspace with a cap, and the fee appears on the application form and
often in portal metadata — including for applications whose documents
we do not hold. Current schedule (*checked 2026-08-22*,
[Planning Portal fee schedule, 1 April 2026](https://ecab.planningportal.co.uk/uploads/english_application_fees.pdf)):
above 3,750 m², **£32,578 + £196 per 75 m², capped at £427,537**; the
December 2023 schedule it replaced ran £30,860 + £186 per 75 m² to a
£405,000 cap
([archived schedule](https://www.suffolk.gov.uk/asset-library/2023-fees-for-planning-applications-in-england.pdf)).
Inverting: **a capped fee implies roughly 155,000 m² of floorspace**,
which at the corpus's own 1.71 kW/m² is on the order of 260 MW —
arithmetic to state openly, never to store. Even far below the cap,
fee → floorspace band is deterministic. A regex for "fee" amounts over
form text, plus the fee field where a portal exposes one, is a
low-effort second floorspace channel that works on exactly the class of
application where prose says nothing.

### 3.5 Plant as scale, extended one step

Standby-generation capacity is already the cascade's fourth rung, and
the EA permits added MWth for 42 fleets. One further plant signal is
held but unbanded: **fuel storage volume**. Humber Tech's 2.85 million
litres of diesel (24-hour bulk) is a scale statement as loud as a
megawatt; storage litres over autonomy hours reproduces fleet
consumption. The findings store already extracts fuel volumes; banding
them into the ranking evidence costs a query.

### 3.6 The rank itself: a script, not a column

Assemble the above per site — adjudicated MW, claim MW, MWth,
floorspace, fee-implied floorspace, Barbour value, `app_size`, ES flag,
fuel volume — and emit an ordered worklist **printing every signal it
used per site**. Max-of-signals, not a blended score: a blend
manufactures a number nobody can defend, whereas "ranked here because
its permit says 470 MWth" is quotable. This lives in `scripts/`, feeds
reporter effort, and never reaches an artefact; `DISCLOSED_BASES` and
the reader's basis column are untouched.

---

## 4. Composing the fifty

The recipe the cohorts imply:

**Include on sight** — disclosed ≥100 MW (34 sites); strong external
claims (NESO ≥100 MW rows matched or matchable); EA permits ≥100 MWth,
**including the unmatched ones**; NSIP / Section 35 / AI Growth Zone
schemes; the Foxglove/press anchors; the 26 pre-planning schemes with
any credible announced capacity (the Devon Data Campus class).

**The blind-spot list is already written.** The unmatched permit claims
are operating campuses the planning corpus cannot see or cannot place:
VIRTUS Stockley Park at 470 MWth with *no site record within 2 km*;
nine permits and 1,430 MWth inside the single Slough Trading Estate
record; Ark Meridian Park present in audited accounts and absent from
the corpus. For an outreach exercise these are not matching failures,
they are the first letters to write — the operator exists, the campus
exists, and the question "what does it draw?" needs no planning record.

**Fill the remainder** from the script's ordering: Barbour value rank,
floorspace and fee-implied floorspace rank, then `app_size`-Large
no-document sites (which are also the acquisition priority list — the
two worklists are the same list read twice).

**One caution.** Site partitioning gates several of these: a rank
computed on a site record holding seven campuses ranks an estate, not a
project. The site-61 and Slough partitions ROADMAP already names are
upstream of any published use of the ordering — for a private worklist,
an estate-level rank still points reporters at the right postcode.

---

## 5. Sources not yet tried, by the audience they serve

Extending the 2.2 release's organising idea: each row is somewhere a
data centre's size, draw or plant is stated to someone other than the
planning authority. Verification status per item; nothing below is
loaded until it clears the EXTERNAL_DATA_SOURCES bar.

### 5.1 The electricity system, below NESO

- **DNO Long Term Development Statements.** Licence-mandated, public
  (registration at worst), and structured: SSEN publishes LTDS parts
  and tables on its open-data portal, SPEN and NGED publish behind free
  registration, UKPN exposes an
  [LTDS infrastructure-projects dataset](https://ukpowernetworks.opendatasoft.com/explore/dataset/ukpn-ltds-infrastructure-projects/)
  (*links checked 2026-08-22*; table-level content **[unverified]**).
  The LTDS "connection activity" tables carry accepted/committed
  connections per substation with MVA — sometimes anonymised,
  sometimes not. Candidate `capacity_claims` source with the same
  re-identification rules as the UKPN Large Demand List.
- **Embedded Capacity Registers, read for the other side.** Ruled out
  in EXTERNAL_DATA_SOURCES §6 for *demand*, correctly. But ECRs list
  distribution-connected **generation ≥1 MW with postcodes** — so a
  DC campus's gas engines, export-capable standby or co-located BESS
  appear as generation rows. A postcode/operator sweep of all six DNOs'
  ECRs is a cheap test of the co-location hypothesis from the grid
  side, complementing the PlanIt spatial sweep. Expected yield honest
  but narrow: only plant with an export connection appears; pure-island
  standby does not. **[Expected small positive; unverified.]**
- **The DNO EIR letters** ROADMAP lists as never sent now have a
  sharper ask: UKPN publishes a Large Demand List and half-hourly DC
  demand profiles — *request the equivalent from SSEN, SPEN, NGED, NPg
  and ENWL by name*, citing UKPN's precedent. A regulator-adjacent body
  refusing to publish what its peer publishes is itself reportable.
- **Elexon settlement data** at grid-supply-point granularity can show
  a step change where one campus dominates a GSP. Research-grade,
  fiddly, and GSP-group aggregation defeats it in cities.
  **[Low priority; unverified.]**

### 5.2 The environmental regulators, beyond the 42 permits

- **The MCP and specified-generator registrations are the missing
  middle.** The permit sweep's floor is plant big enough for a
  bespoke permit; 55 candidates had no publication, "mostly MCP
  registrations". Any *new* combustion plant ≥1 MWth has needed a
  permit since December 2018 — most data-centre fleets are new — so
  the EA's registration records cover fleets the publication sweep
  cannot see. **EIR to the Environment Agency for the specified
  generator and Medium Combustion Plant registers** (site, operator,
  capacity, fuel), with NRW and SEPA equivalents for Wales and
  Scotland. Probably the single largest uncovered on-site-generation
  source. **[Register contents unverified; the regime dates are in
  EXTERNAL_DATA_SOURCES §6 already.]**
- **Permit compliance returns answer "does it actually run?".**
  Permits impose run-hour limits and annual reporting conditions; the
  returns operators file (run hours, fuel use) are environmental
  information held by the EA. An EIR for the annual returns under the
  42 permits already claimed would turn permitted capacity into
  *actual operation* — the exact gap prior_art gotcha 1 names.
  **[Reporting conditions per permit unverified; read the permits'
  reporting schedules first — they are already fetched.]**
- **UK ETS.** Installations whose aggregate rated thermal input
  exceeds 20 MWth fall in scope, and the small-emitter opt-out
  requires *both* low emissions and <35 MWth — which a 925 MWth fleet
  fails. If DC standby fleets hold ETS permits, the registry's
  **verified annual emissions** are audited proof of how much diesel
  actually burned. Irish precedent suggests data centres do appear in
  ETS lists. **[Unverified whether UK DC fleets are in scope or
  exempted as emergency plant — settle this against the UK ETS
  installation list before anything else; a confirmed null is worth
  recording.]**
- **EA Pollution Inventory.** Part A installations report annual
  emissions above thresholds; standby fleets testing monthly may fall
  below reporting thresholds, in which case the null is the record.
  **[Unverified.]**
- **COMAH.** Gas oil's lower-tier threshold is 2,500 tonnes
  **[unverified — check COMAH 2015 Schedule 1 before use]**. Humber's
  2.85 million litres is ≈2,400 tonnes at 0.84–0.85 kg/l — *just*
  under. If that pattern repeats across sites, threshold-shaving on
  fuel storage is a story shaped exactly like the 49.9 MW connection
  applications; the HSE COMAH public register is the checkable side.

### 5.3 Water companies — a sixth audience, and they answer EIR

Water and sewerage undertakers are **public authorities under the
EIR** (*Fish Legal*, CJEU C-279/12 and the Upper Tribunal's 2015
decision — settled law, cite-checked before sending). Three asks:

- **Thames Water has already counted the pipeline.** Its WRMP24
  documents state it has identified **"108 proposed hyper or large
  data centres"** in its area and applies a pass/fail screen to
  cooling-supply requests (*located via search 2026-08-22 in the
  WRMP24 document family on thameswater.co.uk — pin the exact document
  and page before quoting*). EIR: the list, each site's requested
  supply in Ml/d, and the screening outcomes. Affinity, Anglian and
  Severn Trent will hold equivalents for the other clusters.
- **Trade effluent consents.** Cooling blowdown to sewer needs a
  consent stating volumes; sewerage undertakers keep a statutory
  public register of consents (Water Industry Act 1991 s.196
  **[section number unverified]**). Volumes here are operational, not
  planning-stage.
- **Abstraction licences.** No online public register; the EA's
  *Register of Licence Abstracts* spreadsheet and per-site EIR
  requests are the routes (*checked 2026-08-22*:
  [WhatDoTheyKnow response describing the register](https://www.whatdotheyknow.com/request/water_abstraction_licences_in_en),
  [abstraction datasets on data.gov.uk](https://www.data.gov.uk/dataset/7619198a-1bbf-4cbc-8014-f6a46edb230e/water-abstraction-data-sets)).
  Direct river/groundwater cooling is rarer in the UK than mains
  supply, so expect a thin yield — worth one pass for the estuary and
  power-station-site schemes.

### 5.4 The planning system's other rooms

- **Appeals.** The reader's own "where I would look next" names this
  and nothing has been done. Appeal evidence is cross-examined and
  candid — `correct_adjudications.py` already quotes an appeal
  decision stating a 147 MW requirement the application never put that
  plainly. The Planning Inspectorate publishes appeals casework as
  open data on a five-year rolling window plus a searchable portal
  (*checked 2026-08-22*:
  [data.gov.uk dataset](https://www.data.gov.uk/dataset/a8ae664e-f73d-4e43-8d72-93b2199482d8/planning-inspectorate-planning-appeals-casework),
  [Appeals Casework Portal](https://acp.planninginspectorate.gov.uk/)).
  Sweep for the universe's refs; ingest decisions and inquiry
  documents for refused/called-in schemes.
- **Committee and cabinet papers are a second public record.** Officer
  reports, inward-investment papers, local-plan evidence and AI
  Growth Zone bids state megawatts and pounds that applications do
  not, and they live on ModernGov/CMIS instances outside planning
  registers. A keyword sweep of council committee systems is a new
  corpus with the same shape as the planning one (title + PDF +
  date), and the recent FoI-based reporting on AI Growth Zones
  ("AI Growth Zones yet to accelerate planning activity",
  datacentrereview.com, August 2026 — **[title seen in search
  results; article not fetched, site blocked from this session]**)
  shows councils answer questions on exactly this.
- **AI Growth Zones as a scale signal.** Five zones announced to date
  (Culham; Blyth and Cobalt Park; Anglesey and Trawsfynydd; Bridgend;
  Lanarkshire), with a stated expectation that sites demonstrate
  **~500 MW capability** (*checked 2026-08-22*:
  [Computer Weekly overview](https://www.computerweekly.com/news/366628066/The-UK-governments-AI-Growth-Zones-strategy-Everything-you-need-to-know),
  [second-zone confirmation](https://www.computerweekly.com/news/366631325/Government-confirms-North-East-as-location-of-second-AI-Growth-Zone)).
  Zone membership is therefore a floor on ambition for the
  pre-planning cohort. DSIT bid materials are FOI-able; several
  councils published their own bids in cabinet papers. Greystoke's
  AIGZ marketing page is already in the operator snapshots — the
  programme's paper trail is the systematic version.
- **Scottish Section 36 and the Energy Consents Unit register.** The
  worklist's West Calder BESS is already S36-route; the ECU register
  names >50 MW generation schemes with capacity, and DC-adjacent gas
  or BESS consents in Scotland will appear there and not in PlanIt.
  **[Register mechanics unverified.]**
- **Pre-application records by EIR.** For named big sites
  post-decision, councils' pre-app advice and correspondence often
  contain the candid capacity discussion. Commercial-confidentiality
  refusals weaken after determination. Site-targeted, top-ten-only.

### 5.5 The built estate, and whether consented sites are real

- **The VOA rating list ranks the estate that exists.** Bulk downloads
  of the 2023 and 2026 lists are public, purpose-built and
  non-purpose-built computer centres carry their own special category
  codes (**068/069**), and the valuation approach is documented in the
  VOA's own manual (*checked 2026-08-22*:
  [rating list downloads](https://voaratinglists.blob.core.windows.net/html/rlidata.htm),
  [Rating Manual s.281, computer centres](https://www.gov.uk/guidance/rating-manual-section-6-part-3-valuation-of-all-property-classes/section-281-computer-centres)).
  Three uses: rateable value as a scale rank for operating sites; the
  **appearance of a new hereditament as a build-out detector** —
  answering "a permission is not a building" from a statutory record
  rather than a commercial pipeline database; and the 2026 revaluation
  deltas as a growth story. Caveats: RV is rental value, not power; a
  campus may be several hereditaments; addresses need the same
  match-by-adjudication treatment as everything else.
- **Satellite time series for the top fifty.** Sentinel-2 (free) shows
  whether a consented site is dirt, steel or roofed, quarter by
  quarter. Not a dataset to ingest — a per-site verification step for
  the fifty, and publishable imagery. The OSM priors already in
  `data/priors/osm` are the static complement.
- **Non-domestic EPCs** carry floor area per completed building in an
  open register; data-centre coverage doubtful (occupation-based
  exemptions). **[Unverified; expect thin.]**
- The **CCA site-level FoI** (ROADMAP, never sent) remains the best
  route to audited consumption for the existing estate.

### 5.6 Comparator jurisdictions — what disclosure looks like

- **Ireland.** The CSO publishes national **metered** data-centre
  electricity consumption, quarterly series to 2025: 7,663 GWh in
  2025, **23% of all metered consumption** (*checked 2026-08-22*:
  [CSO release, 7 July 2026](https://www.cso.ie/en/releasesandpublications/ep/p-dcmec/datacentresmeteredelectricityconsumption2025/keyfindings/)).
  The UK has no equivalent; DESNZ holds the meter classes that could
  produce one. That asymmetry is a story and a policy ask in one.
- **Germany.** The Energy Efficiency Act requires annual per-site
  reporting (consumption, PUE, heat reuse) to BAFA's data-centre
  register, feeding the EU database (*checked 2026-08-22*:
  [Mayer Brown summary](https://www.mayerbrown.com/en/insights/publications/2024/02/sustainable-data-centers-the-german-energy-efficiency-act-what-data-center-operators-need-to-consider-now-and-in-the-future);
  April 2026 draft amendment eases PUE targets,
  [Orrick note](https://www.orrick.com/en/Insights/2026/04/German-Energy-Efficiency-Act-Draft-Amendment-What-it-means-for-Companies-and-Data-Centres)).
  **[Whether the register is publicly queryable per site:
  unverified — check before citing it as a public register.]** If it
  is, operator-level kW/m² and PUE from German sites are transferable
  priors for the same operators' UK floorspace — a second calibration
  beside the corpus's own 1.71 kW/m².
- **EU EED database** is already surveyed in EXTERNAL_DATA_SOURCES §6.
  The addition here: its published aggregates can benchmark the
  floor-area factor even if site-level rows stay confidential.
- **US SEC filings.** Digital Realty and Equinix file property
  schedules; historic 10-Ks listed per-site square footage and, in
  some years, megawatts, which would join the operator-claims store
  with an audited-adjacent pedigree. **[Current disclosure practice
  unverified.]**

### 5.7 Heat, as evidence of load

Heat network zoning turns waste heat into a *counted resource*: DESNZ's
National Zoning Model identifies heat-source opportunities, the first
zoning maps and the January 2026 government response are published, and
the Old Oak/Park Royal zone is explicitly built around data-centre
waste heat (*checked 2026-08-22*:
[government response, Jan 2026](https://assets.publishing.service.gov.uk/media/6970ad6dec1d126584b9ef20/heat-network-zoning-government-response-to-2023-consultation.pdf),
[OPDC announcement](https://www.london.gov.uk/who-we-are/city-halls-partners/old-oak-and-park-royal-development-corporation-opdc/opdc-media-centre/opdc-press-releases/opdc-pioneers-innovative-money-saving-technology-one-englands-first-heat-network-zones),
[techUK on the first zoning maps](https://www.techuk.org/resource/desnz-publishes-first-set-of-heat-network-zoning-maps-for-england.html)).
A recoverable-heat estimate for a named data centre is a load estimate
by another door. **EIR to DESNZ for the zoning model's identified
data-centre heat sources and the per-source heat estimates.**
**[Whether the model names individual sites: unverified.]**

---

## 6. Requests worth sending — consolidated

Each runs ~28 statutory days; the cost of all of them is one afternoon
of drafting. The first three are already on ROADMAP as never-sent; the
rest are new from this survey. EIR framing throughout where the
information is environmental (connection data, emissions, water), for
the presumption of disclosure and because it disapplies the Utilities
Act s.105 bar.

| # | To | Ask |
|---|---|---|
| 1 | NESO | Project-level demand connection queue / IRN returns (ROADMAP; the direct fix for the 206-vs-34 gap) |
| 2 | DESNZ / EA | CCA site-level metered consumption (ROADMAP) |
| 3 | Each DNO (licensed plc) | Accepted demand connections ≥10 MVA with technology type; and the UKPN-equivalent demand-profile and large-demand datasets, citing UKPN's publication as precedent (ROADMAP, sharpened) |
| 4 | Environment Agency | Specified-generator and MCP registration registers: site, operator, capacity, fuel (§5.2) |
| 5 | Environment Agency | Annual compliance returns (run hours, fuel use) under the 42 permits already claimed (§5.2) |
| 6 | NRW / SEPA | Equivalents of 4 for Wales and Scotland |
| 7 | Thames Water (then Affinity, Anglian, Severn Trent) | The "108 proposed hyper or large data centres" list, requested Ml/d per site, screening outcomes (§5.3) |
| 8 | DESNZ | Heat-network zoning model: identified data-centre heat sources and per-source estimates (§5.7) |
| 9 | DSIT | AI Growth Zone bid site lists and assessment criteria as applied (§5.4; expect commercial redactions) |
| 10 | Named councils, top-ten sites only | Pre-application advice and correspondence, post-decision (§5.4) |

Plus two non-statutory asks already drafted or contemplated: the Data
Center Map pro-bono journalist export, and the Barbour refresh (§2.1).

---

## 7. What this note deliberately does not propose

- **No external figure becomes a site column** — everything above lands
  in `capacity_claims` with its own quantity type, or in a private
  worklist ordering, or in a reporter's notebook. Recommendation 1
  survived the strongest source yet found (the permits); nothing here
  is stronger.
- **No blended scale score in any artefact.** The ordering script
  prints its evidence; the moment a composite number looks quotable it
  has failed.
- **No scraping around DCM or Baxtel terms**; the journalist-export
  route stands.
- **Re-identification of anonymised rows** (UKPN, any LTDS anonymised
  table) stays a deliberate, method-labelled, per-row adjudication —
  the External aggregates sheet's rule extends to every source here.
- **Nothing is loaded until checked.** Every **[unverified]** above is
  a candidate for the EXTERNAL_DATA_SOURCES process — checked
  directly, dated, nulls recorded — not for a loader.
