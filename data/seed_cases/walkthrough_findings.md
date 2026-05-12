# Seed-case walkthrough — findings (2026-05-12)

Hands-on data exploration of Aisha's three exemplar applications before committing to scraper code. Goal: learn the document landscape, identify pipeline implications, surface real signals.

Source documents cached under `data/seed_cases/<case>/`.

---

## 1. Wapseys Wood (NSIP / Section 35 Direction)

**Source:** [Section 35 Direction PDF](https://assets.publishing.service.gov.uk/media/69b7eb62b84f01b2be53a27e/Section_35_Direction_Wapseys_Wood.pdf), 2 pages, ~260 KB.
**Cached at:** [section_35_direction.pdf](wapseys_wood/section_35_direction.pdf), text in `.txt`.

**Confirmed facts (from the direction itself):**
- **Applicant:** *Slough Holdings UK Limited* (acting via Montagu Evans). Note: "Slough" is the company name, not the site — site is in Buckinghamshire.
- **Request date:** 21 January 2026. **Direction signed:** 16 March 2026 by Lewis Thomas (Deputy Director — Planning Casework).
- **Capacity:** "up to c.300MW [IT load] across the three buildings (c.100MW per building)." Cooling: "air cooling is proposed."
- **The Energy Centre is named, distinctly:**
  > *"the Proposed Project is related to a proposed energy centre project for which development consent is required and would benefit from being considered as a single application."*

  Translation: the energy centre needs its **own** DCO — i.e. it's substantial enough to be a separate nationally significant infrastructure project. That's a strong inference for sizable on-site generation (CHP / gas turbine), not just diesel standby.

**What this document does not contain:** fuel type, energy-centre capacity, generator counts. Those would appear in the eventual DCO application (not yet filed at time of writing).

**Pipeline implications:**
- Section 35 Directions are an **early-stage signal source**: they pre-date the DCO application by months but already tell us a DC + energy-centre project is in the NSIP pipeline. Cheap to scrape (gov.uk asset CDN, no auth).
- We need two distinct NSIP-route adapters:
  1. Section 35 Directions: scan `assets.publishing.service.gov.uk/media/*` for DC-related PDFs (or follow gov.uk's planning casework index).
  2. Planning Inspectorate NSIP register: full DCO documents once filed.
- The applicant-name-doesn't-track-location pattern means we can't infer council from applicant. Need separate site-location extraction.

---

## 2. Yorkshire Energy Park / Data Centre (East Riding of Yorkshire — Idox variant)

**Source:** application detail page on `newplanningaccess.eastriding.gov.uk`, application reference `22/00301/STREME` (visible in document URLs), reserved-matters application to outline 17/01673/STOUTE (approved 22 Dec 2020).
**Cached at:** [yorkshire_data_park/](yorkshire_data_park/) — summary, full document index HTML, and the Energy Statement PDF.

**Confirmed facts:**
- **Applicant:** *Hull Eco Park Ltd (HEPL).*
- **Site:** Land NW of Kingstown Hotel, Hull Road, Hedon, East Riding of Yorkshire. The site is **literally called "Yorkshire Energy Park"** — the data centre is one zone of a wider energy park.
- **Capacity:** 240 racks initially (3–4 MW), expansion to 600 racks (~6 MW). Small by hyperscaler standards.
- **Status:** Approved.

**The smoking gun — Energy Statement (3 pages, by Vic Coupland Ltd):**
> *"The Data Centre operator have specifically selected the YEP site for their new data centre due to the resilient on-site **zero carbon** electrical and cooling energy generation planned for 2026, when the hydrogen source becomes available… The **Combined Heat and Power (CHP) turbines will initially be running off natural gas** until the planned hydrogen supply becomes available."*

Within the same document: marketed as "zero carbon," disclosed as natural-gas CHP, green claim conditional on a future hydrogen supply with no committed date. Textbook gap between marketing language and physical kit.

Plus: outline-permission **Condition 77** requires occupants to meet energy needs from on-site generation — i.e. the natural-gas CHP is the *primary* electricity source by planning condition, not a backup.

**Document landscape (174 documents on this one application):**
| Type | Count |
|---|---|
| Supporting Documents | 64 |
| Consultee Comment | 51 |
| Plans | 35 |
| Public Comment | 20 |
| Officer Report | 1 |
| eDecision | 1 |
| Press Advert | 1 |
| Application Form | 1 |

**Highest-yield methodological insight: consultee senders are themselves a signal.**

Before reading any letter, the consultee-list alone says "gas":
- 4 letters from **Northern Gas Networks** (gas distribution network operator).
- 1 letter from **National Grid Plant Protection** (transmission network operator).
- 1 public comment from **Equinor New Energy Limited** (Norwegian state oil and gas major).

Gas distribution operators don't consult on planning applications unless gas mains are involved. The presence and sender of consultee letters is a powerful low-cost classification feature **before any document is opened**.

**Pipeline implications:**
- The East Riding portal has the Idox URL signature (`applicationDetails.do?keyVal=…`) but lives under `/newplanningaccess/` instead of the canonical `/online-applications/`. **Adapter must detect by query-string shape, not path prefix.**
- "recaptcha-link" CSS class on document anchors did NOT actually gate access — links work with a polite `User-Agent` and no JS. So that class is decorative, not enforcement. (Worth verifying per-instance; this may differ by council.)
- The **document description column is the routing key** — "ENERGY STATEMENT", "ENERGY CENTRE - FLOOR PLANS", etc. all match cleanly on substring. We do NOT need to open every document; description-keyword routing on a per-doc basis is cheap and high-yield.
- The Energy Statement was 3 pages, native text layer, no OCR needed. This will not be representative — but where it exists, it's the highest-signal document on the application.
- **Consultee sender categorisation is a triage feature in itself.** Worth a schema addition: `documents.author` (extracted from the description column where present).

---

## 3. Loughton data centre (Epping Forest — Salesforce Experience Cloud)

**Source URL:** [public register entry](https://eppingforestdc.my.site.com/pr/s/planning-application/a0h8d000000NzLYAA0/epf116522). Application ref `epf116522`.
**Cached at:** [loughton/page.html](loughton/page.html) — but this is the JS boot loader only.

**Blocker hit:** the Epping Forest portal runs on **Salesforce Lightning Experience**. The page served by curl is 53 lines of HTML — a content-security-policy header, an Aura framework bootstrap, and almost no payload. All planning data and document lists are rendered client-side by JavaScript hitting Salesforce's internal Aura RPC endpoints.

We could not therefore independently confirm Aisha's findings on this case in this walkthrough — Aisha already inspected the application form (substation mention) and the Environment Agency consultee letter (18 backup generators) by hand.

**Pipeline implications:**
- **Salesforce Experience Cloud is a portal type we cannot scrape with simple HTTP.** Options:
  1. **Playwright / headless Chrome** — renders the SPA, scrapes the DOM. Slow, heavier infra, but reliable for any JS portal.
  2. **Reverse-engineer the Aura RPC** — Salesforce's Lightning framework uses an internal POST endpoint (`/aura?...`) for data. Possibly more efficient but fragile.
  3. **Check for an alternate route** — many councils run multiple portals; verify whether Epping Forest also publishes via Idox / a "legacy" public access for the same case. (Not investigated yet.)
- **Decision pending:** how many UK councils are on Salesforce? If just a handful, manual/headless-browser scraping is fine. If it's a growing pattern, we need a generic Salesforce adapter early.
- Aisha's hand-inspection findings (substation in form, 18 generators in EA letter) are the **key reference benchmark** — once we have any adapter working, our pipeline must reproduce them on this case.

---

## Cross-cutting learnings → schema and adapter design changes

### Confirm / amend in the migrations

- **Add `documents.author`** — for consultee letters and public comments, the sender's name is itself a signal. Currently we only have `kind`; the column "MR ALAN HEMINGWAY" or "NORTHERN GAS NETWORK" is what tells the story.
- **`documents.kind` taxonomy from real data:** {`application_form`, `officer_report`, `decision_notice`, `plans`, `supporting_documents`, `consultee_comment`, `public_comment`, `energy_statement`, `press_advert`}. The first eight match East Riding's column. Refine when we see more councils.
- **Application-level reference linkage** — Yorkshire DP has at least three reference numbers (17/01673/STOUTE outline, 22/01591/STVARE variation, 22/00301/STREME reserved matters). Need to handle "parent" and "related case" references. Possibly add `applications.related_refs JSONB`.

### Triage rubric — confirmed signal patterns

The walkthrough confirmed three Tier-1 signal patterns worth building into the triage prompt:

1. **"Energy centre" in description or document titles** — coded language for substantial on-site generation. Recurred in both Wapseys Wood and Yorkshire DP.
2. **CHP / Combined Heat and Power** — explicit primary generation; not backup. Yorkshire DP's Energy Statement names it directly.
3. **Consultee sender pattern** — Northern Gas Networks / Cadent / National Grid Gas as consultees correlates strongly with on-site gas.

And two patterns of "green claim with caveat":

4. **"Zero carbon … when [future condition]"** — Yorkshire DP defers zero-carbon to a future hydrogen supply with no committed date. Linguistic flag worth catching.
5. **"Energy costs equivalent to grid supply"** — Yorkshire DP frames the on-site CHP commercially. Signals primary generation rather than backup.

### Portal-type inventory (revised, real-world list)

| Portal kind | Example council | Scrape tech | URL signature |
|---|---|---|---|
| Idox Public Access (canonical) | many | curl/httpx | `/online-applications/applicationDetails.do?keyVal=…` |
| Idox-variant (custom path) | East Riding | curl/httpx (detect by query string) | `/newplanningaccess/applicationDetails.do?keyVal=…` |
| Salesforce Experience Cloud | Epping Forest | Playwright or Aura RPC | `*.my.site.com/pr/s/planning-application/<id>/<ref>` |
| NSIP Section 35 (gov.uk) | DESNZ (no LPA) | curl/httpx | `assets.publishing.service.gov.uk/media/*/Section_35_*.pdf` |
| NSIP DCO (Planning Inspectorate) | Planning Inspectorate | TBD | `national-infrastructure-consenting.planninginspectorate.gov.uk/…` |

Civica, Tascomi/Causeway, Ocella — not encountered in this walkthrough; deferred.

### Cost / volume reality check

- East Riding's one application: **174 documents**. We will not download all 174 for thousands of applications.
- **Description-keyword routing is essential.** On Yorkshire DP, ~23 of 174 docs matched any power-related keyword, of which only ~5 are truly high-priority (Energy Statement, energy-centre plans, gas-network consultee letters).
- For storage: if a typical matched DC application has ~100 docs and we keep 10–20 of them, average corpus per app ~ 50–100 MB. Across ~500 candidate UK applications: ~25–50 GB. Local first, S3 when convenient.

---

## Recommended pipeline-design changes (vs. earlier sketch)

1. **Per-document description-keyword routing** is more important than I had it. Move from "download every document for matched applications" to "download every document whose description matches the power-signal lexicon OR is of type Energy Statement / Officer Report / Application Form / EA Consultee Letter."
2. **Consultee sender is a first-class signal.** Add `documents.author` and a sender-name watchlist (Northern Gas Networks, Cadent, National Grid Gas, EA, lead local flood authority, etc.).
3. **Two-stage triage**: stage 1 from the application *description and consultee senders* alone (no document open required); stage 2 from the Energy Statement / Officer Report / Application Form text. Most matches will resolve at stage 1.
4. **NSIP Section 35 monitoring** is a separate, lightweight adapter — flag DC + "energy centre" mentions as soon as the direction is signed, months before the DCO appears.
5. **Salesforce adapter** is a known unknown — decide investment level once we have a count of UK councils on Salesforce.

---

## Open questions surfaced

- **How many UK councils run Salesforce Experience Cloud for planning?** Quick research, deferred.
- **The four parked Foxglove lookups** (DC01, International Trading Estate / GTR, G-Park Docklands, 103MW Court Lane) — still open.
- **Wapseys Wood DCO** — has the actual DCO application been filed yet, or only the Section 35 Direction? Worth a check on the Planning Inspectorate NSIP register.
