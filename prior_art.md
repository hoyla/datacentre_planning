# Prior art — published research & reporting on UK data-centre power

A reference list of published work that touches on the same territory as this investigation. Two purposes:

1. **Avoid duplication.** Where prior work has established a finding, we should build on it, not re-do it.
2. **Sanity-check our numbers.** When our analysis produces an aggregate claim, we should be able to reconcile it with figures other reputable outlets have already published. Large unexplained divergences are a flag to investigate before publication.

Confidence notes are marked **[Confidence: High / Medium / Low]** based on whether the primary source was directly inspected or only reached via secondary citations.

Last updated: 2026-05-12.

---

## 1. Guardian — Google data centres, Essex (May 2026)

- **Authors:** Aisha Down & Priya Bharadia
- **Outlet:** The Guardian
- **Published:** ~9 May 2026
- **Subject:** Google / Greystoke Capital planning applications for Thurrock (52 ha) and North Weald data centres.
- **Primary URL:** https://www.theguardian.com/technology/2026/may/09/google-developers-significantly-misstate-carbon-emissions-of-proposed-uk-datacentres
- **[Confidence: Medium]** — story confirmed via multiple secondary outlets; original Guardian URL not directly verified in research pass.

**Methodology:** Reviewed planning documents. Examined developers' carbon-baseline methodology rather than auditing physical infrastructure. Key finding was a methodological sleight: developers compared one year of the proposed DC's emissions against the UK's *five-year* carbon budget, understating relative impact by a factor of five.

**Headline numbers:**
- North Weald's actual share of the 2033–37 UK carbon budget: **0.215%** (vs. reported 0.043%).
- Combined Thurrock + North Weald: **>1%** of the five-year UK carbon budget.
- Annual emissions for North Weald alone: **~570,000 tCO2** (per parallel reporting).

**What was NOT examined:** Specific generator counts, fuel-type breakdown, on-site backup capacity. Focus was emissions accounting, not physical kit.

**Formal objections filed:** Foxglove, Global Action Plan.

**Cross-reference value:** Anchors our own analysis in a concrete, recent UK case with reported figures. If our pipeline ingests these two applications, we should be able to reproduce the ~5× understatement finding from the same documents.

---

## 2. DeSmog — Blackstone / QTS Blyth (September 2025)

- **Title:** "Colossal Diesel Capacity of Trump-Donor's UK Data Centre"
- **Outlet:** DeSmog
- **Published:** 25 September 2025
- **URL:** https://www.desmog.com/2025/09/25/colossal-diesel-capacity-of-donald-trump-donor-blackstone-uk-data-centre-blyth/
- **[Confidence: High]**

**Methodology:** Obtained and analysed planning documents (including EIA technical appendices) submitted to Northumberland County Council. Cross-referenced generator specs with figures from Louis Goddard's Data Desk team. Planning ref: **24_04112_OUTES**.

**Headline numbers:**
- **580 diesel generators** on-site.
- Combined nameplate: **3.93 GWth** (gigawatt-thermal).
- ~**4% of UK electricity output** if run continuously at nameplate.
- **500** of the 580 designated "primary backup."
- On-site fuel storage: **48 hours**.
- Located 1.5 km from a GEOS Group oil terminal.

**Notable quote from the application itself:** the sustainability report acknowledged that "the increase in frequency of extreme weather events" will lead to "additional run hours based on emergency operation where the utility supplies to site fail" — softening the "backup only" framing.

**Cross-reference value:** A specific, document-backed UK precedent for vast on-site fossil-fuel capacity at a single DC. Our pipeline should produce the same generator count and capacity for this application; if not, our extraction logic is wrong.

**Methodological caveat to inherit:** DeSmog treated the planning application as truthful but noted the framing contradiction. They did not independently verify the 580 figure against operational reality.

---

## 3. DeSmog — Gas-powered AI data centres across Europe (April 2026)

- **Title:** "Inside the Plot to Cover Europe with Gas-Powered AI Data Centres"
- **Outlet:** DeSmog
- **Published:** 29 April 2026
- **URL:** https://www.desmog.com/2026/04/29/inside-the-plot-to-cover-europe-with-gas-powered-ai-data-centres/
- **[Confidence: High]**

**Methodology:** Interview-led — Datacloud Energy Europe 2026 conference attendance + interviews with gas-turbine manufacturers (MWM/Caterpillar Europe, Langley Holdings) and operators. Cross-referenced with planning and regulatory filings.

**Key UK-relevant claims:**
- **300 MW gas-powered DC at Wapseys Wood, Buckinghamshire** approved by UK Labour government (March 2026) as "nationally significant infrastructure."
- Industry plans **≥23 GW of gas-turbine electricity** combined across Europe and US (Meta, Google, Microsoft, OpenAI, Nvidia, xAI).
- MWM "confident" in numerous European projects up to **100 MW each**.
- UK turbine maker Langley Holdings flagged slower UK rollout than US due to public opposition.

**Cross-reference value:** Establishes that **on-site primary gas generation** (not just diesel backup) is now a real and rapidly-growing UK pattern. Wapseys Wood is a concrete case to ingest. Also confirms the "NSIP escape hatch" route worth watching in our pipeline.

---

## 4. Carbon Brief — UK DC emissions reanalysis (March 2026)

- **Title:** "Analysis: CO2 from UK data centres could be 'hundreds of times' higher than thought"
- **Outlet:** Carbon Brief
- **Published:** 23 March 2026
- **URL:** https://www.carbonbrief.org/analysis-co2-from-uk-data-centres-could-be-hundreds-of-times-higher-than-thought/
- **Related:** https://www.carbonbrief.org/ai-five-charts-that-put-data-centre-energy-use-and-emissions-into-context/
- **[Confidence: High]**

**Methodology:** Sensitivity analysis, not survey. Took DSIT's 2035 capacity baseline (11.2 GW AI) and re-ran the emissions calculation under varying assumptions:
- **90% load factor** (industry standard).
- **0.4 MtCO2 per TWh** from gas power (IEA-derived).
- **Variable fossil-fuel share**: 5%, 25%, 50%+.

**Headline numbers:**
- DSIT official estimate: **0.142 MtCO2** for 11.2 GW capacity (assumes near-total grid decarbonisation).
- Carbon Brief at 5% gas: **~2 MtCO2** (≈10× DSIT).
- Carbon Brief at higher gas reliance: **30+ MtCO2** (Denmark's annual emissions).
- At 20 GW capacity with heavy gas use: **~70 MtCO2** (~500× DSIT; Sweden's annual emissions).

**Cross-reference value:** Provides the **emissions-per-TWh-of-gas conversion factor** (0.4 MtCO2/TWh) we should reuse for consistency. Our aggregate generator-capacity findings can be plugged into this model to produce comparable emissions estimates.

**Methodological caveat:** Carbon Brief did not interrogate planning applications directly — they reverse-engineered what grid decarbonisation rate would have to be true for DSIT to be right (>98% clean by 2035; implausible). Our work feeds into theirs: actual fossil-fuel capacity counts let their model use evidence rather than scenarios.

---

## 5. Foxglove & Global Action Plan — Big Tech Data Centres report (September 2025)

- **Title:** "Big Tech Data Centres: A Threat to UK Decarbonisation"
- **Published:** 26 September 2025
- **URL (Global Action Plan):** https://www.globalactionplan.org.uk/files/big_tech_data_centres_2025_09_26.pdf
- **URL (Foxglove):** https://www.foxglove.org.uk/wp-content/uploads/2025/10/2025_09_26-FINAL-Big-Tech-Data-Centres-Report-Website-Version.pdf
- **Press release:** https://www.globalactionplan.org.uk/insights/publications/new-reportbig-tech-data-centresa-threat-to-uk-decarbonisation
- **[Confidence: High]**

**Methodology (verbatim from p.4–5 of the report):** **England only**. Threshold ≥100 MW. Included only applications where the developer disclosed **both** a MW figure **and** an operational-phase carbon emissions estimate. Implausibly low figures were retained "to highlight the lack of clarity or consistency." Foxglove notes they identified roughly **twice as many** ≥100 MW England applications but excluded ~10 of them for missing emissions figures.

**Headline numbers (verified from PDF, transcribed in [foxglove_top10.md](data/prior_art_sources/foxglove_top10.md)):**
- **Ten ≥100 MW England applications** with both power and emissions disclosed: combined **4,137 MW** and **2,745,538 tCO2e/yr** developer-stated emissions.
- That total ≈ the entire 2025 UK carbon saving from the EV switch (CCC: 2.9 Mt).
- ~**20 ≥100 MW England applications** known to Foxglove in total — half disclosed enough to be listed.
- **BBC reported** ~100 DCs in planning/construction across the UK; Foxglove believe the real number is "significantly higher."
- **Two-orders-of-magnitude inconsistency** between developer figures for similar-sized facilities. DC01 (320 MW): 6,056 tCO2e/yr. Thurrock/Google (225 MW): 568,657 tCO2e/yr. The discrepancy implies systematic underreporting somewhere.
- **Existing-DC sense-check anchor:** Digital Realty UK reported 408,041 tCO2e in 2021 under CCA scheme — several listed figures are below this despite vastly larger capacity.

**Top-10 list (see [foxglove_top10.md](data/prior_art_sources/foxglove_top10.md) for full table):** Cambois (QTS) [= DeSmog's Blyth], Elsham Tech (Greystoke), Humber Tech (Greystoke), DC01, Thurrock (Google), Virtus Saunderton, International Trading Estate (GTR), G-Park Docklands (GLP), North Weald (Google), 103MW Court Lane.

**Cross-reference value:** This is the **closest prior work to what we're building**. Two specific anchor links to other prior art:
- **Cambois (QTS)** = the Blyth DeSmog case. DeSmog says 580 diesel generators / 3.93 GWth; Foxglove records developer-stated emissions of just 184,160 tCO2e/yr — a direct opportunity to demonstrate the planning-figure-versus-physical-kit gap.
- **Thurrock + North Weald** = the Guardian (Down/Bharadia) case. Combined developer estimate: 988,084 tCO2e/yr.

When our pipeline first ingests, it must produce these ten applications with matching MW figures — otherwise our coverage is broken.

**Methodological gap we can close:** Their brief excluded sub-100 MW sites, devolved-nations sites, and ≥100 MW sites without disclosed emissions (~10 known to exist). Our brief — ingest all DC applications, all sizes, all nations — closes all three.

---

## 6. Opportunity Green — Parliamentary Environmental Audit Committee submission (October 2025)

- **Submitted:** 30 October 2025
- **URL:** https://committees.parliament.uk/writtenevidence/151599/html/
- **[Confidence: Medium]** — submission inspected via committee site, not by full reading.

**Key claims relevant to our work:**
- Grid connection backlog is driving operators toward gas grid connections and on-site generators.
- Quoted developer statement: *"Data centres can't connect to the electricity network today… So they come to the gas network… and saying they'll build a small gas power station to power locally their data centre."*
- "100% renewable" claims by operators often rely on accounting offsets divorced from physical on-site emissions.
- 78% of UK consumers polled (Beyond Fossil Fuels, October 2025) believe new DCs should only be built with renewables commitments.

**Cross-reference value:** Provides the causal mechanism — *grid scarcity drives on-site gas* — that frames our findings as systemic rather than incidental.

---

## 7. National Grid ESO — Data Centre Impact Study (November 2025)

- **Source:** NESO / DSO
- **URL:** https://dso.nationalgrid.co.uk/downloads/15083/data-centre-impact-study2.pdf
- **[Confidence: Low]** — PDF not directly read in research pass; cited from secondary references.

**Headline figure (from earlier NESO statements):** UK DCs could account for up to **9% of UK electricity demand by 2025**.

**Cross-reference value:** A baseline for total DC electricity demand to scale our generator findings against. Worth reading in full early in the project.

---

## 8. IEA — Energy and AI (2025–2026)

- **URLs:** https://www.iea.org/reports/energy-and-ai/ ; https://www.iea.org/reports/energy-and-ai/energy-supply-for-ai
- **[Confidence: Medium]**

**Global benchmarks (UK breakdowns not separately published):**
- Global DC electricity: **460 TWh (2024) → >1,000 TWh (2030)** projected.
- Current renewables share: ~**27%**; coal ~30%; gas ~26%.
- Fossil fuels expected to meet **>40%** of *additional* DC demand to 2030.
- **70% surge in gas-turbine orders in 2025** globally.
- US: >40% of DC power from gas; China: ~70% from coal.

**Cross-reference value:** Global context for whether the UK picture we find is in line with, ahead of, or behind international trends.

---

## Cross-reference benchmarks (numbers we should be able to corroborate)

When our pipeline produces aggregate claims, these are the existing reference points to reconcile against:

| Metric | Published value | Source |
|---|---|---|
| Blackstone Blyth generator count | 580 (3.93 GWth) | DeSmog Sep 2025 |
| Google Essex (Thurrock + North Weald) carbon share of 2033–37 UK budget | >1% | Guardian May 2026 |
| Google North Weald annual emissions | ~570,000 tCO2 | Guardian May 2026 |
| Top 10 England DCs ≥100 MW combined emissions (developer-stated) | 2,745,538 tCO2e/yr (4,137 MW combined) | Foxglove/GAP Sep 2025, p.5 |
| DCs in planning/construction (BBC figure, all sizes) | ~100 | BBC Aug 2025 (cited Foxglove p.7) |
| ≥100 MW England DC applications known to Foxglove | ~20 (10 with disclosed emissions, ~10 without) | Foxglove/GAP Sep 2025, p.7 |
| Existing UK DC reference emissions (Digital Realty, 2021) | 408,041 tCO2e | CCA scheme via Foxglove p.7 |
| Wapseys Wood gas-powered DC | 300 MW | DeSmog Apr 2026 |
| DSIT official 2035 DC emissions estimate | 0.142 MtCO2 | DSIT (via Carbon Brief) |
| Carbon Brief alternative 2035 estimate (5% gas) | ~2 MtCO2 | Carbon Brief Mar 2026 |
| Emissions conversion factor (gas) | 0.4 MtCO2 / TWh | IEA via Carbon Brief |
| UK DC share of electricity by 2025 | up to ~9% | NESO Nov 2025 |

---

## Methodological gotchas to inherit

1. **Nameplate ≠ utilisation.** "3.93 GW" is peak thermal capacity. Actual run hours depend on grid reliability and extreme-weather frequency. Planning documents rarely specify load factor.
2. **Primary vs. total backup.** Blyth distinguishes "primary backup" (500 units) from total (580). Always state whether a count is all generators or only the primary subset.
3. **Accounting offsets ≠ physical emissions.** "100% renewable" via PPAs is grid-accounting, not on-site. Cross-reference against actual grid carbon intensity, not the claim.
4. **Planning ≠ operational.** Designs change; not all permitted kit ends up installed. Where possible, triangulate against the Environmental Permits Register and FoI'd operational data.
5. **"Emergency use" framing.** Documents soften capacity by labelling it emergency-only. Cross-check against the same documents' climate-resilience language for contradiction.

---

## Open investigative angles (what's still unaddressed)

Things prior work has *not* established, where our systematic data could differentiate:

1. **National count of on-site diesel/gas generators across all UK DC applications.** Foxglove/GAP capped at ≥100 MW with disclosed emissions; smaller and undisclosed sites are unmeasured.
2. **% of DCs marketed as "green" that include non-renewable backup.** Not systematically published anywhere.
3. **Buried-language signal patterns.** Aisha's "electrical substation on premises" example: a national audit of oblique disclosures has not been done.
4. **NSIP escape-hatch volume.** How many DCs are taking the Wapseys Wood route to bypass local planning scrutiny?
5. **Planning vs. environmental-permit reconciliation.** Where do the two registers diverge? Operators who omit generators from planning but appear in environmental permits are a story.
6. **Methodology audit at scale.** The Guardian's 5× understatement finding — is it isolated to Greystoke / Google, or is the same accounting trick widespread?
