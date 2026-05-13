# Co-located energy applications — spatial spike findings (2026-05-12)

Test of the hypothesis: *a data-centre developer files the DC, but the gas/CHP/turbine that powers it is filed separately (different applicant, different planning reference) and would only surface through spatial proximity, not through a "data centre" keyword search.*

Spike scope: 10 anchor cases (9 Foxglove top-10 + Yorkshire Energy Park), spatial search at 1km radius via PlanIt's `lat`/`lng`/`krad` API, local filter for energy-generation keywords. Raw responses cached under `data/colocated_energy_spike/*.json` for reproducibility.

---

## TL;DR

**The hypothesis is real.** Yorkshire Energy Park is a clean positive: a separately-filed 21 MW gas-fired generation facility (14 gas-reciprocating-engine generators) sits at the same site as the eventual data centre application, filed six years earlier under a different planning reference, and would never have surfaced through any DC-keyword search.

But the signal-to-noise is low at 1km without filtering. Most matches across the ten cases are pre-existing substations, residential CHP for housing estates, or conditions on the DC application itself. The angle is **worth building** — but only with carefully designed filters and triage downstream.

| Anchor | Apps within 1km | Energy-keyword matches | Notable finding |
|---|---|---|---|
| Cambois (Blyth) | 177 | 49 | Site = former Blyth Power Station; many noise hits about that legacy plant, plus offshore wind farm consenting |
| Elsham Tech | 20 | 0 | Rural; sparse data |
| Humber Tech | 31 | 2 | Wind farm cable route + the DC's own EIA screening |
| Thurrock Google | 719 | 4 | Mostly EV-charging substations, one biomass kiln; not directly relevant |
| Saunderton | (skipped) | — | Wycombe legacy record has no location coordinates — retry needed with post-reorg ref |
| ITE Ealing | 2,546 | 130 | Dense urban (Southall); "energy centre" appears repeatedly in *residential* masterplans (Green Quarter), one CHP+gas-boilers condition near Heathrow |
| G-Park Docklands | 1,400 | 16 | Existing CHP arrangement nearby (PA/19/01070/NC references condition 23 on 2012 permission); the area is mixed-use, noisy |
| North Weald | 0 | 0 | **Fetch failure** — persistent 429s exhausted retries; not a real zero. Retry needed. |
| Court Lane Iver | 1,043 | 8 | **An adjacent DC application** (`Bucks/PL/25/4351/FA`) at Thorney Business Park — a *second* Iver-area data centre we didn't have in our DC universe via keyword (it does match "data centre" though, so likely is in the universe; worth confirming) |
| **Yorkshire Energy Park** | **185** | **39** | **The clean positive — see below** |

---

## The clean positive: Yorkshire Energy Park

Among the 39 energy-keyword matches within 1km of the Yorkshire Energy Park DC application (`EastRiding/22/00301/STREME`), one stands out:

> **`EastRiding/16/02800/STPLF`** (filed 2016-08-18): "Erection of a **gas-fired energy reserve facility of up to 21MW capacity comprising of 14 gas reciprocating engine generators, 7 transformers and associated ancil[lary equipment]**…"

Six years before the DC application was filed in 2022, a 21 MW gas-fired plant (14 gas-reciprocating-engine generators) was being permitted at what is now the Yorkshire Energy Park site. This is:

- **Filed under a different planning reference** (`16/02800/STPLF` vs the DC's `22/00301/STREME`)
- **Filed years earlier** — outside the time window of any current-DC-development sweep
- **Never mentions "data centre"** in its description — wouldn't appear in any keyword sweep
- **Found only via spatial proximity** to the DC's location

And critically: this is exactly the "energy reserve facility" / "gas reciprocating engine" pattern that, in the DC context, looks like **primary on-site generation marketed as backup**. The Energy Statement Aisha-and-Luke found in the seed walkthrough explicitly says "CHP turbines will initially be running off natural gas" — and now we have the formal planning consent for the underlying gas generation plant. Different document family, different applicant, same site, six years apart.

This is the kind of finding the broader investigation needs structurally, not as anecdote — and it would never have surfaced through a DC-application search alone.

Also worth noting from the same 1km radius:
- `EastRiding/15/03220/STPLF` (2015): "Installation of **bio-fuelled power generation plant** including sub-station"
- `EastRiding/16/03571/STVAR` (2016): variation of conditions including a "bio-fuel" condition
- A long chain of conditions discharges suggesting the energy-generation infrastructure was an ongoing piece of work for years before the DC application was ever filed.

So there's potentially a *temporal* angle too: separately-filed energy generation may *predate* the DC by years — the DC then gets placed at an existing energy-generation site, but the carbon footprint conversation happens around the DC's planning record where the on-site gas isn't mentioned because someone else permitted it years earlier.

---

## What the noise looks like

Most energy-keyword matches in the dense urban cases (Ealing, Tower Hamlets) are:

1. **Substations** — every London borough has thousands. The keyword filter is too inclusive here.
2. **Residential CHP / "energy centre"** — masterplans for housing estates (e.g. Ealing's "Green Quarter") include community energy centres. Not what we're hunting; needs to be filtered out.
3. **Conditions discharges** on the DC application itself — these show up because they're at the same coordinates. Filter by application_ref against the anchor.
4. **Pre-existing power infrastructure** — e.g. Cambois's matches are mostly about the historic Blyth Power Station, decommissioning, ash mounds.

The Yorkshire Energy Park case stood out because the description is specific and unambiguous ("gas-fired energy reserve facility of up to 21MW capacity comprising of 14 gas reciprocating engine generators"). That's the shape of the high-value match.

---

## Recommended filters before this becomes a real sweep

Don't ingest all spatial matches blindly. Apply structural filters at fetch time or in triage:

1. **Exclude pure-substation matches** unless capacity or "gas" / "CHP" / "generation" also appears.
2. **Require a generation-capacity signal**: numeric MW mention, "engines", "turbines", "CHP", "power generation plant", "energy reserve", "gas-fired", "biomass-fired", "fuel cell", "hydrogen", or "BESS" / "battery energy storage" (the last for grid-balancing rather than primary, but still worth flagging).
3. **Exclude residential masterplan "energy centres"** — they're community CHPs serving housing, not industrial. Heuristic: `description` mentions `residential` or `dwelling` or `housing` or `flats` or `homes`.
4. **Exclude conditions discharges on the anchor itself** — filter by `application_ref != anchor.application_ref` and by `associated_id != anchor.application_ref`.
5. **Capture applicant / agent names** from `other_fields` — same agent on both the DC and the adjacent energy plant is itself a flag.
6. **Don't require time-window overlap**: as Yorkshire Energy Park shows, the energy plant can predate the DC by years.

Even with these filters, manual / LLM triage will still be required at the per-match level. Treat this sweep as a candidate-generation step, not a finding-generation step.

---

## Cost of doing this at scale

For the full 1,549-DC universe at 1km radius:
- ~1,549 spatial searches
- At 3 s polite delay + ~10 s per location (1-3 pages), avg = ~12 s
- Plus 429 backoffs — these are inevitable in dense urban areas where ~2,500 apps fit in 1km
- Realistic total: 6–10 hours of polite wall-clock time, but only minutes of actual API budget
- Cache-as-resume means a 429 wall doesn't lose the work already done

This is the same magnitude as the original PlanIt sweep, ingested once and re-used. Output: a new table `colocated_applications(anchor_application_id, candidate_application_id, distance_m, keyword_hits, …)` — additive to the current schema.

---

## Open follow-ups

- **Retry the two failed cases**: Saunderton (find a coordinate from the post-reorg Bucks ref or a related application) and North Weald (the 0-result was a 429 fetch failure, not a real zero — re-run after rate-limit cools).
- **Wapseys Wood would be the ultimate test** — but it's NSIP-route, not in PlanIt, so we'd need to find the energy-centre application directly via Planning Inspectorate or DESNZ. The Section 35 Direction explicitly says the energy centre needs its own DCO, so it should be findable as a separate filing.
- **Applicant-name cross-reference** as a primary signal: the Foxglove top-10 includes Greystoke (twice), Google, Blackstone/QTS, Virtus, GTR, GLP. A separate sweep for *energy-generation applications by these developers' SPVs or named energy entities* might be a higher-yield alternative to spatial search. Worth a follow-on spike before committing to a full spatial sweep.

---

## Recommendation

**Build this, but in stages.** First, a tighter Phase 1c sweep with the filters above applied at fetch time. Then a Phase 1d operator-name sweep that hunts for energy-side filings by known DC operators' affiliated entities (this would have caught the Yorkshire Energy Park `16/02800/STPLF` filing if Hull Eco Park Ltd's earlier identity were known).

The Yorkshire Energy Park finding alone — a 21 MW gas-fired generation plant filed six years before the DC, at the same site, never mentioning data centres — is the proof that this is a structural pattern worth chasing rather than an incidental curiosity. The journalism payoff if even 20–30% of the DC universe shows this pattern is significant: it reframes the "DC carbon footprint" conversation from one of marketing claims vs. backup-generator disclosure to one of corporate-structure obscurement.
