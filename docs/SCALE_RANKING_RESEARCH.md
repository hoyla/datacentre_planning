# Ranking scale without a megawatt, and the sources not yet tried

Researched 2026-08-22, in answer to two questions from Luke: how do we
rank the projects we cannot rank — enough to choose the fifty worth
manual corroboration — and what routes to power use, on-site generation
and environmental impact have we not yet considered? Restructured the
same day at Luke's request into three worklists — his, the sessions',
and the joint one — with the survey material behind them as reference.

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
| No documents held | **127** | Metadata proxies, then targeted acquisition |
| Pre-planning, no application yet | **26** | Announcements, corporate and land records |

Two calibration points sharpen what "top fifty" means:

- **Ofgem's own count says the giants exist.** The July 2026 Curate
  consultation (already transcribed in `dcp/external_aggregates.py`)
  puts **206 data-centre projects at ≥100 MW** in the connection
  queue — 166 at 100–500 MW, 40 above 500. The corpus knows 34 sites
  at ≥100 MW. Some of the difference is queue-versus-planning
  population, some is speculative queue entries that will never file —
  but the gap is the triage problem in one number, and the NESO
  project-level request is the direct fix.
- **The claims layer already ranks sites planning cannot.** Six
  no-figure sites carry a strong external-claim match in the current
  reader — Kao Harlow, Eggborough, Drax and West Burton among them,
  all placed by NESO register claims on sites holding no or few
  documents. Three of those hold **zero documents**: the corpus
  already knows they are probably enormous, and holds nothing. That
  is the sharpest argument for targeted acquisition, and those names
  lead the joint list below.

The read-and-silent 151 are exhausted as a reading problem — their
silence is verified, so their instruments are external audiences and
value proxies. Acquisition is the *only* instrument for the
no-documents 127. The pre-planning 26 are invisible to both and need
the corporate and announcement records. Every proposal below serves
one of those three, and nothing here proposes a published number: the
aim is a defensible *worklist ordering*, the same status as
`worth_deep_read`, with the evidence for each site's position printed
beside it.

---

## 2. The work, divided

Three lists. Each entry names the reference section below (§4–§7)
where the caveats and verification status live — the lists say *what
and who*, the reference says *why and how carefully*.

### 2.1 Luke and the reporting team — letters, asks, and calls

The statutory requests cost an afternoon of drafting and ~28 days of
waiting each; the waiting is the whole cost, so they go first.
**Sent already** (confirmed 2026-08-22): NESO and Ofgem. One
precision worth checking on the NESO letter: Ofgem's consultation
names the **Information Request Notice returns** as its project-level
evidence base — if the letter did not name the IRN dataset
specifically, a one-paragraph follow-up that does is much harder to
deflect than "the demand queue".

| # | To | Ask | Ref |
|---|---|---|---|
| 1 | Environment Agency | Three asks, one letter: the **specified-generator and MCP registration registers** (site, operator, capacity, fuel — the fleets below the permit sweep's 50 MWth floor); the **annual compliance returns** (run hours, fuel use) under the 42 permits already claimed; and the **UK ETS ultra-small-emitter list** for data-centre installations, with installed thermal capacity and monitored annual emissions (§6.2 — the USE carve-out is why these fleets are absent from every published ETS table, and the regulator holds the numbers anyway) | §6.2 |
| 2 | NRW / SEPA | Equivalents of the register asks for Wales and Scotland | §6.2 |
| 3 | Thames Water, then Affinity, Anglian, Severn Trent | The **"108 proposed hyper or large data centres"** list its WRMP24 documents describe, requested Ml/d per site, and screening outcomes. Water companies answer EIR (*Fish Legal*) | §6.3 |
| 4 | Each DNO (the licensed plc) | Accepted demand connections ≥10 MVA with technology type, **and the UKPN-equivalent demand-profile and large-demand datasets by name**, citing UKPN's publication as precedent | §6.1 |
| 5 | DESNZ / EA | CCA site-level metered consumption (ROADMAP, never sent) | §6.5 |
| 6 | DESNZ | Heat-network zoning model: identified data-centre heat sources and per-source estimates | §6.7 |
| 7 | DSIT | AI Growth Zone bid site lists and assessment criteria as applied (expect commercial redactions) | §6.4 |
| 8 | Named councils, top-ten sites only | Pre-application advice and correspondence, post-decision | §6.4 |

Non-statutory asks and calls, same week:

- **Data Center Map** journalist-export email (drafted already, per
  EXTERNAL_DATA_SOURCES §2).
- **Barbour refresh** through the data team, value fields explicitly
  in scope for the whole universe (§4.1).
- **The blind-spot operator letters need no new data**: VIRTUS
  (Stockley Park, 470 MWth, no site record within 2 km), the seven
  operators inside the Slough Trading Estate record, Ark re Meridian
  Park. The unmatched permits are not matching failures; they are
  addresses with named operators and a first question already written:
  what does this campus draw? (§5)
- **UKPN's gated datasets** sit behind Luke's portal login and are
  unpulled (ROADMAP): the Large Demand List refresh and "Data Centres
  by Local Authority". One logged-in session exports both.
- **Council bundle-request emails** for hard-portal sites the ranking
  elevates — a reporter's email asking the LPA for the document
  bundle costs less than an adapter, and the three zero-byte
  documents (ROADMAP) belong in the same letters.
- **Review the draft fifty** once 2.2 produces it. The ordering
  script prints its evidence per site precisely so this is an
  editorial read, not an act of faith.

### 2.2 Claude, in sessions against the live database — measurement, ranking, sweeps

Nothing here needs a letter answered; most of it needs the Postgres
that lives on Luke's machine, so these are session tasks there.

1. **Measure signal coverage across the unranked cohorts** — the
   query below, drafted 2026-08-22 against `migrations/` and the
   export query's CTEs but **not yet run**; expect small adjustments
   on first contact. It answers, in one table: how much of each
   cohort Barbour value, PlanIt size class and external claims can
   see. (The cohort split here approximates the reader's basis
   column — good enough for coverage, not for quoting.)

   ```sql
   WITH member AS (
     SELECT m.site_id, m.application_id
     FROM site_members m WHERE m.retired_at IS NULL),
   pw AS (   -- sites with any adjudicated site_capacity figure
     SELECT DISTINCT mb.site_id
     FROM power_adjudication p
     JOIN member mb ON mb.application_id = p.application_id
     WHERE p.verdict = 'site_capacity' AND p.value_mw IS NOT NULL),
   fs AS (   -- sites rankable from floorspace; bounds as dcp/site_scale.py
     SELECT site_id FROM (
       SELECT mb.site_id,
              percentile_cont(0.5) WITHIN GROUP (ORDER BY f.value_number) AS med
       FROM findings f JOIN member mb ON mb.application_id = f.application_id
       WHERE f.value_number BETWEEN 500 AND 400000
         AND lower(f.value_unit) IN ('sqm','m2','sq m','square metres',
                                     'square meters')
         AND f.signal_type = ANY(%(floorspace_signal_types)s)
       GROUP BY mb.site_id) x WHERE med >= 500),
   barb AS ( -- Barbour value per site (project-linked members)
     SELECT m.site_id, max(p.value_gbp) AS value_gbp
     FROM site_members m JOIN projects p ON p.id = m.project_id
     WHERE m.retired_at IS NULL GROUP BY m.site_id),
   size AS ( -- PlanIt's own size class, from raw_metadata
     SELECT mb.site_id,
            bool_or(a.raw_metadata->>'app_size' = 'Large') AS any_large
     FROM applications a JOIN member mb ON mb.application_id = a.id
     GROUP BY mb.site_id),
   claims AS (
     SELECT DISTINCT cm.site_id FROM capacity_claim_matches cm
     WHERE cm.retired_at IS NULL),
   docs AS (
     SELECT mb.site_id, count(d.id) AS n_docs
     FROM member mb
     LEFT JOIN documents d ON d.application_id = mb.application_id
     GROUP BY mb.site_id)
   SELECT CASE WHEN pw.site_id IS NOT NULL THEN 'has adjudicated figure'
               WHEN fs.site_id IS NOT NULL THEN 'floorspace only'
               WHEN coalesce(docs.n_docs, 0) = 0 THEN 'no documents'
               ELSE 'held, silent' END               AS cohort,
          count(*)                                   AS sites,
          count(barb.value_gbp)                      AS w_barbour_value,
          count(*) FILTER (WHERE size.any_large)     AS w_planit_large,
          count(claims.site_id)                      AS w_external_claim
   FROM sites s
   LEFT JOIN pw     ON pw.site_id = s.id
   LEFT JOIN fs     ON fs.site_id = s.id
   LEFT JOIN barb   ON barb.site_id = s.id
   LEFT JOIN size   ON size.site_id = s.id
   LEFT JOIN claims ON claims.site_id = s.id
   LEFT JOIN docs   ON docs.site_id = s.id
   WHERE s.retired_at IS NULL
   GROUP BY 1 ORDER BY 2 DESC;
   ```

   (`%(floorspace_signal_types)s` binds
   `dcp.site_scale.FLOORSPACE_SIGNAL_TYPES` — the predicate lives
   once, there. The 26 pre-planning sites separate on
   `s.classification`.)

2. **Build `scripts/rank_for_outreach.py`** — max-of-signals, one
   ordered worklist, every signal printed per site with its evidence.
   Import `site_scale.power_estimate` and `load_site_floorspace`
   rather than restating them; add Barbour value, `app_size`, the
   existing EIA flags, matched claims, permit MWth. No blended score,
   no artefact output — a script a reporter reads. **Note found while
   drafting this document:** the EIA presence flag proposed in §5.2
   *already exists* — `export_handover.py`'s `app_eia` CTE computes
   `eia_ref_hit` and `eia_doc_hit` per site and the workbook carries
   them. The ranking consumes it; nothing new is built.
3. **The fee and forms floorspace sweep** (§5.3–5.4) over cached
   text — deterministic, sized before it is attempted by counting how
   many "Application Form"/CIL documents have usable text.
4. **The zero-byte guard at fetch** plus the `find -size -1c` corpus
   sweep (ROADMAP's smallest item) — lands *before* the joint
   acquisition sprint so the new round cannot repeat the
   silent-empty failure.
5. **Desk checks still open** from this survey, each an hour of
   verification, none needing the database: the COMAH Schedule 1
   thresholds (§6.2); whether Germany's BAFA register is publicly
   queryable per site (§6.6); the trade-effluent register mechanics
   (§6.3); a first pull of the VOA bulk list filtered to SCat
   068/069 (§6.5); the DESNZ diesel conversion factor behind the
   USE-threshold arithmetic (§6.2). The UK ETS question itself was
   checked 2026-08-22 and is now written up in §6.2.
6. **Loaders for new claims sources** (LTDS first, §6.1) — only
   after the source clears the EXTERNAL_DATA_SOURCES bar, and each
   lands as claims with quantity types, never columns.
7. **A watcher for the EA's public consultations and gov.uk Section
   35 publications** (§6.2, and the NSIP research note) — pending DC
   generation permits carry full technical annexes months before the
   register hears of them.

### 2.3 Together — the human-at-keyboard captures

The acquisition tail needs a person and a browser; the sessions bring
the tooling and the bookkeeping. Ordered by expected yield:

1. **The named four first**: Kao Harlow (Project Nobel), Eggborough,
   Drax, West Burton — strong external claims, zero documents held.
   Whatever route their portals need, these justify it individually.
2. **The 31 browser-routed applications** (ROADMAP: 15 behind AWS
   WAF on the Coventry signature, 8 LPAssure serving
   `UnsupportedWebBrowser`, 8 Salesforce needing a harvested document
   listing) — roughly one working day with tooling that already
   works, taken in the ranking's order rather than portal order.
3. **The Northern Ireland adapter's one prerequisite** — a session
   with the network tab open on
   `planningregister.planningsystemni.gov.uk` to find the documents
   API the page calls; after that the adapter is routine and it is
   the whole of NI, not seven applications.
4. **Bespoke portals and the genuinely hard 13** (CAPTCHA, hard
   403s, Incapsula) — only where the ranking elevates the site, and
   the reporter's bundle-request email (2.1) is the first resort,
   not the last.
5. **Partition adjudication** — the sessions assemble the
   documentary evidence per campus (the permits are the sharpest,
   each naming a campus and a grid reference); Luke signs the
   boundary, as with the International Trading Estate split. The
   seven site-61 campuses are already named in
   `data/priors/site_partitions.yaml`. Gating, because a rank
   computed on an estate record ranks an estate — for the private
   worklist that still points at the right postcode, but nothing
   partition-suspect gets published.

---

## 3. Composing the fifty

The recipe the cohorts imply, once 2.2's ranking runs:

**Include on sight** — disclosed ≥100 MW (34 sites); strong external
claims (NESO ≥100 MW rows matched or matchable); EA permits
≥100 MWth, *including the unmatched ones*; NSIP / Section 35 / AI
Growth Zone schemes; the Foxglove/press anchors; the 26 pre-planning
schemes with any credible announced capacity (the Devon Data Campus
class).

**The blind-spot list is already written** — the unmatched permit
claims and the accounts-only campuses (§2.1, operator letters).

**Fill the remainder** from the script's ordering: Barbour value
rank, floorspace and fee-implied floorspace rank, then
`app_size`-Large no-document sites — which are also the acquisition
priority list; the two worklists are the same list read twice.

---

# Part II — the reference

What follows is the survey the lists point into: the caveats,
verification status and sources per item. Nothing below is loaded
until it clears the EXTERNAL_DATA_SOURCES bar.

## 4. Value figures — the direct answer to "is there a value?"

**Yes — and one of them is already in the database.**

### 4.1 Barbour ABI project value — held, exported, not yet used to rank

`projects.value_gbp` has been ingested since migration 005 and already
reaches the workbook as `barbour_value_gbp`
(`scripts/export_handover.py`). Estimating construction value is
Barbour's core business, and it is exactly the "value of the project"
figure the question asks for. What has never been done is to *use* it
— which is 2.2's first measurement.

Caveats that travel with it: Barbour's values are frequently their own
estimates derived from floorspace and building type, so for some rows
this is the floorspace proxy wearing a currency sign — an ordering
signal, not corroboration. One campus maps to several projects
(outline, fit-out, civils): rank on `max`, never `sum`, until a human
has looked. 253 projects cover well under half the universe, and the
export is from one moment — **a refreshed export is a licence
conversation, not an engineering task** (2.1). Credit required in
anything published. (Glenigan sells the same class of data if Barbour
cannot refresh; commercial, **[unverified]** terms.)

### 4.2 Ofgem's capex yardstick, inverted in the open

Ofgem assumes **£9.5m per MW** in the Curate consultation (its
Table 3 capex model — already quoted in EXTERNAL_DATA_SOURCES §3).
Dividing a credible project value by it gives an implied MW band.
This is a reporter's arithmetic to do in the open with the assumption
stated — the same posture as the MWth caveat — and it never enters
`value_mw`. For ranking, skip the conversion entirely and sort on the
value itself.

### 4.3 Companies House balance sheets — capex, not capacity

The 2026-08-20 survey established that accounts do not disclose
*capacity* (Ark excepted). They do disclose **money**: an SPV building
a campus capitalises it, so fixed assets / assets under construction
approximate cumulative capex, and year-on-year additions are build-out
pace. This is a different question from the one already tested, and it
is bulk-automatable: Companies House publishes **free daily and
monthly bulk files of iXBRL accounts**, with monthly archives back to
2008 (*checked 2026-08-22*:
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

### 4.4 Land as value: price paid and corporate ownership

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

### 4.5 Announced investment values

Government and operator announcements routinely state "£X bn
investment" where no planning document states a megawatt. The
`capacity_claims` vocabulary already has `announced_capacity`; an
`announced_value` quantity beside it would let the existing machinery
hold these — verbatim, dated, weakest-authority-labelled, matched by
hand like everything else. The operator-snapshots fetcher is the
infrastructure; gov.uk press releases are fetchable and stable.

## 5. Ranking signals already in the corpus

### 5.1 PlanIt's `app_size` — free, and covers the no-documents cohort

Ingested for every PlanIt application into `raw_metadata`
(`raw_metadata->>'app_size'`; `dcp/repo.py`). Coarse
(Small/Medium/Large), source-classified, but present **including for
the 127 sites with no documents** — which no document-derived signal
can say. A "Large" no-documents site outranks a "Small" one for
acquisition effort. Measure its agreement with the banded scale on
the 152 ranked sites before trusting it further.

### 5.2 An Environmental Statement is a scale claim in itself

EIA is triggered by thresholds, so the *presence* of an ES is a floor
on scale. **Already built**, found while restructuring this note:
`export_handover.py`'s `app_eia` CTE derives `eia_ref_hit` (EIA-shaped
application-reference suffixes) and `eia_doc_hit` (ES material among
held documents), and the workbook carries both. The ranking consumes
them; nothing new is built. The converse remains the editorial point
the project already knows from Elsham ("got a no-EIA Screening
Opinion"): a big site *without* an ES is a finding, not a gap.

### 5.3 Raising floorspace coverage from the forms

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
already uses **gross internal area, which sums storeys** — footprint
is the wrong quantity and mostly isn't what the signals carry. One
tightening is available: `FLOORSPACE_SIGNAL_TYPES` currently includes
`building_footprint`, which *is* the bungalow number. Worth either
excluding it or pairing it with a storey count where drawings state
one. The honest limit stands regardless: the corpus's own calibration
says ×2 spread either way, which is band-quality, not print-quality —
and band-quality is all a top-fifty needs.

### 5.4 The planning fee is a floorspace disclosure nobody reads

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
low-effort second floorspace channel that works on exactly the class
of application where prose says nothing.

### 5.5 Plant as scale, extended one step

Standby-generation capacity is already the cascade's fourth rung, and
the EA permits added MWth for 42 fleets. One further plant signal is
held but unbanded: **fuel storage volume**. Humber Tech's 2.85 million
litres of diesel (24-hour bulk) is a scale statement as loud as a
megawatt; storage litres over autonomy hours reproduces fleet
consumption. The findings store already extracts fuel volumes; banding
them into the ranking evidence costs a query.

### 5.6 The rank itself: a script, not a column

Assemble the above per site — adjudicated MW, claim MW, MWth,
floorspace, fee-implied floorspace, Barbour value, `app_size`, the
EIA flags, fuel volume — and emit an ordered worklist **printing every
signal it used per site**. Max-of-signals, not a blended score: a
blend manufactures a number nobody can defend, whereas "ranked here
because its permit says 470 MWth" is quotable. This lives in
`scripts/`, feeds reporter effort, and never reaches an artefact;
`DISCLOSED_BASES` and the reader's basis column are untouched.

## 6. Sources not yet tried, by the audience they serve

Extending the 2.2 release's organising idea: each row is somewhere a
data centre's size, draw or plant is stated to someone other than the
planning authority.

### 6.1 The electricity system, below NESO

- **DNO Long Term Development Statements.** Licence-mandated, public
  (registration at worst), and structured: SSEN publishes LTDS parts
  and tables on its open-data portal, SPEN and NGED publish behind
  free registration, UKPN exposes an
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
  appear as generation rows. A postcode/operator sweep of all six
  DNOs' ECRs is a cheap test of the co-location hypothesis from the
  grid side, complementing the PlanIt spatial sweep. Expected yield
  honest but narrow: only plant with an export connection appears;
  pure-island standby does not. **[Expected small positive;
  unverified.]**
- **The DNO EIR letters** (2.1) have a sharper ask than when ROADMAP
  first listed them: UKPN publishes a Large Demand List and
  half-hourly DC demand profiles — *request the equivalent from
  SSEN, SPEN, NGED, NPg and ENWL by name*, citing UKPN's precedent.
  A regulated peer refusing to publish what UKPN publishes is itself
  reportable.
- **Elexon settlement data** at grid-supply-point granularity can
  show a step change where one campus dominates a GSP.
  Research-grade, fiddly, and GSP-group aggregation defeats it in
  cities. **[Low priority; unverified.]**

### 6.2 The environmental regulators, beyond the 42 permits

- **The MCP and specified-generator registrations are the missing
  middle.** The permit sweep's floor is plant big enough for a
  bespoke permit; 55 candidates had no publication, "mostly MCP
  registrations". Any *new* combustion plant ≥1 MWth has needed a
  permit since December 2018 — most data-centre fleets are new — so
  the EA's registration records cover fleets the publication sweep
  cannot see. The EIR ask is in 2.1; probably the single largest
  uncovered on-site-generation source. **[Register contents
  unverified; the regime dates are in EXTERNAL_DATA_SOURCES §6
  already.]**
- **Permit compliance returns answer "does it actually run?".**
  Permits impose run-hour limits and annual reporting conditions; the
  returns operators file (run hours, fuel use) are environmental
  information held by the EA. An EIR for the annual returns under the
  42 permits already claimed would turn permitted capacity into
  *actual operation* — the exact gap prior_art gotcha 1 names.
  **[Reporting conditions per permit unverified; read the permits'
  reporting schedules first — they are already fetched.]**
- **UK ETS — checked 2026-08-22, and the invisibility is explained.**
  Data-centre standby fleets are in scope above 20 MWth aggregate
  rated thermal input, and the sector engages with the scheme as a
  sector — techUK has formally responded to UK ETS amendment
  proposals on the industry's behalf, and Amazon has a live EA
  application for an "Emergency Back-Up Generation Facility" at
  Thorney Lane, Iver, with a full BAT assessment on the EA's public
  consultation site (*checked 2026-08-22*:
  [gov.uk compliance guidance](https://www.gov.uk/government/publications/uk-emissions-trading-scheme-for-installations-how-to-comply/uk-emissions-trading-scheme-for-installations-how-to-comply),
  [RPS explainer](https://www.rpsgroup.com/insights/consulting-uki/data-centre-development-greenhouse-gas-permits-explained/),
  [techUK response](https://www.techuk.org/resource/techuk-responds-to-government-s-proposals-to-amend-the-uk-ets-on-behalf-of-the-data-centre-industry.html),
  [Thorney Lane BAT assessment](https://consult.environment-agency.gov.uk/psc/sl0-9ee-amazon-data-services-uk-limited/supporting_documents/application-bespoke-sp3224lp-app-bat-assessment-of-bat-final-2026-02-25-epr-mp3824mg-a001-020326pdf)).
  But an installation emitting under **2,500 tCO2e a year** can hold
  **ultra-small emitter status**: no permit, and absence from every
  published verified-emissions table — which is why no DC appears in
  them. The USE holder **must still monitor emissions under an
  approved plan** to prove it stays under the threshold
  ([gov.uk USE guidance](https://www.gov.uk/guidance/opt-out-of-the-uk-ets-if-your-installation-is-an-ultra-small-emitter),
  *checked 2026-08-22*), so the regulator holds the numbers — hence
  the third ask in the EA letter (2.1). Two levers fall out: 2,500
  tCO2e is roughly **900,000 litres of gas oil** (at ~2.7 kgCO2e per
  litre — **[pin the exact factor from the DESNZ GHG conversion
  tables before use]**), so USE status is itself a verifiable cap on
  actual running; and a site that *escalates out* of USE into the
  full scheme is a site whose generators genuinely ran. The EA
  consultation portal doubles as pipeline visibility: pending DC
  generation permits with technical annexes, months before the
  register hears of them (the watcher in 2.2).
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

### 6.3 Water companies — a sixth audience, and they answer EIR

Water and sewerage undertakers are **public authorities under the
EIR** (*Fish Legal*, CJEU C-279/12 and the Upper Tribunal's 2015
decision — settled law, cite-checked before sending). Three asks:

- **Thames Water has already counted the pipeline.** Its WRMP24
  documents state it has identified **"108 proposed hyper or large
  data centres"** in its area and applies a pass/fail screen to
  cooling-supply requests (*located via search 2026-08-22 in the
  WRMP24 document family on thameswater.co.uk — pin the exact
  document and page before quoting*). The EIR ask is in 2.1;
  Affinity, Anglian and Severn Trent will hold equivalents for the
  other clusters.
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

### 6.4 The planning system's other rooms

- **Appeals.** The reader's own "where I would look next" names this
  and nothing has been done. Appeal evidence is cross-examined and
  candid — `correct_adjudications.py` already quotes an appeal
  decision stating a 147 MW requirement the application never put
  that plainly. The Planning Inspectorate publishes appeals casework
  as open data on a five-year rolling window plus a searchable portal
  (*checked 2026-08-22*:
  [data.gov.uk dataset](https://www.data.gov.uk/dataset/a8ae664e-f73d-4e43-8d72-93b2199482d8/planning-inspectorate-planning-appeals-casework),
  [Appeals Casework Portal](https://acp.planninginspectorate.gov.uk/)).
  Sweep for the universe's refs; ingest decisions and inquiry
  documents for refused/called-in schemes.
- **Committee and cabinet papers are a second public record.**
  Officer reports, inward-investment papers, local-plan evidence and
  AI Growth Zone bids state megawatts and pounds that applications do
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
  pre-planning cohort. DSIT bid materials are FOI-able (2.1); several
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
  refusals weaken after determination. Site-targeted, top-ten-only
  (2.1).

### 6.5 The built estate, and whether consented sites are real

- **The VOA rating list ranks the estate that exists.** Bulk
  downloads of the 2023 and 2026 lists are public, purpose-built and
  non-purpose-built computer centres carry their own special category
  codes (**068/069**), and the valuation approach is documented in
  the VOA's own manual (*checked 2026-08-22*:
  [rating list downloads](https://voaratinglists.blob.core.windows.net/html/rlidata.htm),
  [Rating Manual s.281, computer centres](https://www.gov.uk/guidance/rating-manual-section-6-part-3-valuation-of-all-property-classes/section-281-computer-centres)).
  Three uses: rateable value as a scale rank for operating sites; the
  **appearance of a new hereditament as a build-out detector** —
  answering "a permission is not a building" from a statutory record
  rather than a commercial pipeline database; and the 2026
  revaluation deltas as a growth story. Caveats: RV is rental value,
  not power; a campus may be several hereditaments; addresses need
  the same match-by-adjudication treatment as everything else.
- **Satellite time series for the top fifty.** Sentinel-2 (free)
  shows whether a consented site is dirt, steel or roofed, quarter by
  quarter. Not a dataset to ingest — a per-site verification step for
  the fifty, and publishable imagery. The OSM priors already in
  `data/priors/osm` are the static complement.
- **Non-domestic EPCs** carry floor area per completed building in an
  open register; data-centre coverage doubtful (occupation-based
  exemptions). **[Unverified; expect thin.]**
- The **CCA site-level FoI** (2.1) remains the best route to audited
  consumption for the existing estate.

### 6.6 Comparator jurisdictions — what disclosure looks like

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
- **EU EED database** is already surveyed in EXTERNAL_DATA_SOURCES
  §6. The addition here: its published aggregates can benchmark the
  floor-area factor even if site-level rows stay confidential.
- **US SEC filings.** Digital Realty and Equinix file property
  schedules; historic 10-Ks listed per-site square footage and, in
  some years, megawatts, which would join the operator-claims store
  with an audited-adjacent pedigree. **[Current disclosure practice
  unverified.]**

### 6.7 Heat, as evidence of load

Heat network zoning turns waste heat into a *counted resource*:
DESNZ's National Zoning Model identifies heat-source opportunities,
the first zoning maps and the January 2026 government response are
published, and the Old Oak/Park Royal zone is explicitly built around
data-centre waste heat (*checked 2026-08-22*:
[government response, Jan 2026](https://assets.publishing.service.gov.uk/media/6970ad6dec1d126584b9ef20/heat-network-zoning-government-response-to-2023-consultation.pdf),
[OPDC announcement](https://www.london.gov.uk/who-we-are/city-halls-partners/old-oak-and-park-royal-development-corporation-opdc/opdc-media-centre/opdc-press-releases/opdc-pioneers-innovative-money-saving-technology-one-englands-first-heat-network-zones),
[techUK on the first zoning maps](https://www.techuk.org/resource/desnz-publishes-first-set-of-heat-network-zoning-maps-for-england.html)).
A recoverable-heat estimate for a named data centre is a load estimate
by another door. The EIR ask is in 2.1. **[Whether the model names
individual sites: unverified.]**

---

## 7. What this note deliberately does not propose

- **No external figure becomes a site column** — everything above
  lands in `capacity_claims` with its own quantity type, or in a
  private worklist ordering, or in a reporter's notebook.
  Recommendation 1 survived the strongest source yet found (the
  permits); nothing here is stronger.
- **No blended scale score in any artefact.** The ordering script
  prints its evidence; the moment a composite number looks quotable
  it has failed.
- **No scraping around DCM or Baxtel terms**; the journalist-export
  route stands.
- **Re-identification of anonymised rows** (UKPN, any LTDS anonymised
  table) stays a deliberate, method-labelled, per-row adjudication —
  the External aggregates sheet's rule extends to every source here.
- **Nothing is loaded until checked.** Every **[unverified]** above
  is a candidate for the EXTERNAL_DATA_SOURCES process — checked
  directly, dated, nulls recorded — not for a loader.
