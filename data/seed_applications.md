# Seed applications — exemplar cases for pipeline validation

Hand-curated examples flagged by Aisha (Guardian) in her 2026-05-12 email to Luke. Each one demonstrates a specific pattern our pipeline must be able to surface. If our scraper + triage + extraction can't reproduce the power-related findings noted below from these exact applications, our coverage is incomplete.

Complementary to:
- [foxglove_top10.md](prior_art_sources/foxglove_top10.md) — Foxglove's surveyed top-10 ≥100 MW England applications.
- [/prior_art.md](../prior_art.md) — published research and reporting.

---

## 1. Loughton data centre — Epping Forest District Council

- **Portal URL:** https://eppingforestdc.my.site.com/pr/s/planning-application/a0h8d000000NzLYAA0/epf116522
- **Application ref:** `epf116522` (inferred from URL slug — verify)
- **Council:** Epping Forest District Council (Essex)
- **Portal kind:** **Salesforce Experience Cloud** (`*.my.site.com`) — a portal type *not* in our previous list (Idox / Civica / Tascomi / Ocella / bespoke). Worth a generic adapter once we know how widely Salesforce is used in UK planning.

**What Aisha found:**
- The **planning application form** mentions only a *"substation"* on premises — no further detail given.
- The **Environment Agency consultee letter** (attached to the application by EA) refers to **18 backup generators**.

**What this teaches us:**
- **Companion data is essential.** The headline planning document understates the physical kit; the detail lives in consultee responses. Our document-fetch pipeline must collect *every* document on the application's record, including consultee letters from EA, the lead local flood authority, etc.
- "Substation on premises" is a quiet signal — easy to miss without targeted triage prompts.

---

## 2. Wapseys Wood — DESNZ Section 35 Direction (NSIP route)

- **Source URL:** https://assets.publishing.service.gov.uk/media/69b7eb62b84f01b2be53a27e/Section_35_Direction_Wapseys_Wood.pdf
- **Application route:** Direct to Planning Inspectorate / DESNZ via Section 35 Direction, NSIP regime. Bypasses the local council planning portal entirely.
- **Council:** Buckinghamshire (notional — the application doesn't sit on their portal).
- **Capacity:** 300 MW (per DeSmog April 2026).

**What Aisha found:**
- The Section 35 Direction document refers to an *"energy centre project"* adjacent to the data centre, with no further explanation of what fuel powers it.
- DeSmog reporting characterises this as a **gas-powered** data centre.

**What this teaches us:**
- **"Energy centre" is a coded term** — it sounds neutral but, in DC planning context, can mean a behind-the-meter gas turbine / CHP plant. Add to our triage vocabulary.
- **The NSIP / Section 35 route is a separate pipeline** from council portals. Our adapter list needs:
  - The NSIP register on the Planning Inspectorate site.
  - The DESNZ-published Section 35 Directions on `assets.publishing.service.gov.uk`.
- Identifying *which* DCs took the NSIP route is itself a story — Wapseys Wood is described in published reporting as the Labour government's first NSIP DC approval (March 2026).

---

## 3. Yorkshire Data Park — East Riding of Yorkshire Council

- **Portal URL:** https://newplanningaccess.eastriding.gov.uk/newplanningaccess/applicationDetails.do?keyVal=R6FGK7BJJ4200&activeTab=summary
- **Application keyVal:** `R6FGK7BJJ4200`
- **Council:** East Riding of Yorkshire
- **Portal kind:** Idox-style URL pattern (`/applicationDetails.do?keyVal=…`) but served under `/newplanningaccess/` rather than the canonical `/online-applications/`. Generic Idox adapter must tolerate path-prefix variants.

**What Aisha found:**
- The application refers to an **"energy centre"** — same coded language as Wapseys Wood.
- Believed gas-powered (Aisha's working assumption; to be verified from the documents).

**What this teaches us:**
- The "energy centre" pattern recurs across unrelated applications — looks like industry standard language for on-site primary generation infrastructure.
- Idox URL patterns vary more than the canonical `/online-applications/` path suggests. Adapter design should detect the Idox query-string shape (`applicationDetails.do?keyVal=…`) rather than rely on a fixed path prefix.

---

## What these three together imply for the pipeline

1. **Companion-data fetching is mandatory, not optional.** The Loughton case proves the headline document undersells. Pipeline schema (already in place: `documents.kind`) supports per-document typing — extraction must tag consultee letters separately and treat them as first-class evidence.
2. **"Energy centre" goes into the triage and extraction vocab** alongside the existing lexicon (backup, generator, turbine, LPG, gas, failover, substation, fuel storage, CHP, kVA, kW, MW).
3. **The portal-type inventory needs to grow** beyond the four I previously listed. Confirmed in the wild so far: Idox (canonical), Idox (variant path `/newplanningaccess/`), Salesforce (`*.my.site.com`), plus the NSIP / DESNZ route. Each is a distinct adapter.
4. **A national portal inventory is a deliverable in its own right.** Build the registry of `(council, admin_unit, portal_kind, base_url)` as an early artifact — useful for spotting omissions in our own coverage and reusable for future investigations.
