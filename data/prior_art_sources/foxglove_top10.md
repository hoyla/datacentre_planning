# Foxglove / Global Action Plan — Top 10 surveyed applications

Transcribed verbatim from the September 2025 report "Big Tech Data Centres: a threat to UK decarbonisation", page 5.

**Source PDF:** `foxglove_gap_report.pdf` (in this directory) / [Global Action Plan original](https://www.globalactionplan.org.uk/files/big_tech_data_centres_2025_09_26.pdf)
**Extracted:** 2026-05-12 via pdftotext.

## Selection criteria (verbatim, p.4–5)

- **Geography:** England only — "we were only able to look at England in detail."
- **Size threshold:** ≥100 MW operational capacity. "'Large scale' for the purposes of this report is defined as 100MW or above."
- **Required disclosure:** Both (a) a stated MW figure AND (b) a developer estimate of carbon emissions from operational-phase electricity use. Sites missing either were excluded.
- **Inclusions despite implausibility:** Implausibly low developer figures were retained "to highlight the lack of clarity or consistency in how the emissions resulting from planned data centres are being assessed."
- **Scope statement:** "Foxglove was able to identify twice as many data centres in the planning system which appeared to be 100MW or above, but we did not include these here as we were not able to find carbon emissions estimates for their operational phase from their developers."

So the **universe of ≥100 MW England DC applications known to Foxglove as of Sep 2025 is approximately 20** — half disclosed enough to be listed, half didn't.

## The list (verbatim figures from the report)

| # | Site name | Developer | App. year | Capacity (MW) | Status (as of Sep 2025) | Developer emissions estimate (tCO2e/yr) | Council *(my inference, verify)* |
|---|---|---|---|---|---|---|---|
| 1 | **Cambois (QTS)** | QTS / Blackstone | 2024 | 1,100 | Outline approved 03.2025 | 184,160 | Northumberland *(ref: 24_04112_OUTES — confirmed via DeSmog)* |
| 2 | **Elsham Tech (Greystoke)** | Greystoke | 2025 | 1,000 | Pending outline | 857,254 | North Lincolnshire *(verify)* |
| 3 | **Humber Tech (Greystoke)** | Greystoke | 2024 | 384 | Approved | 387,805 | North Lincolnshire *(verify; ref likely PA/2025/643)* |
| 4 | **DC01** | *(not named in report)* | 2024 | 320 | Outline approved 02.2025 | **6,056** *(flagged inconsistent — see below)* | TBC |
| 5 | **Thurrock (Google)** | Google / Greystoke Capital | 2025 | 225 *(estimated)* | Pending | 568,657 | Thurrock |
| 6 | **Virtus Saunderton** | Virtus | 2022 | 300 | Under construction | 101,660 | Buckinghamshire *(Wycombe area; verify)* |
| 7 | **International Trading Estate (GTR)** | GTR | 2025 | 256 | Permission pending | 219,031 | TBC |
| 8 | **G-Park Docklands (GLP)** | GLP | 2025 (RM) | 210 | Under construction | **1,148** *(flagged inconsistent)* | London Borough — likely Newham *(verify)* |
| 9 | **North Weald (Google)** | Google / Greystoke Capital | 2025 | 164 | Under consultation | 419,427 | Epping Forest *(verify)* |
| 10 | **103MW Court Lane** | *(not named in report)* | 2022 | 103 | Approved | **340** *(flagged inconsistent)* | Portsmouth *(Court Lane Cosham; verify)* |
| | **Total** | | | **4,137 MW** | | **2,745,538** | |

## Key observations from the report itself

- **Two orders of magnitude inconsistency:** "DC01 appears to estimate annual carbon emissions of 6,056 tonnes for a 320 MW facility; whereas Google estimates carbon emissions of 568,657 tonnes — nearly 100 times higher — for its Thurrock site, which we would estimate to be of a smaller scale."
- **Sense-check anchor (existing facility):** A Digital Realty UK data centre (name not disclosed) reported **408,041 tCO2e in 2021** under the Climate Change Agreements scheme. The new generation is expected to be significantly larger, yet several developer figures in the table are an order of magnitude *below* this — implying widespread underestimation.
- **Headline benchmark:** Combined developer-stated emissions of 2,745,538 tCO2e/yr ≈ the entire 2025 carbon saving from UK switch to electric cars (CCC: 2.9 Mt).

## Cross-references to other prior art

- **Cambois (QTS) #1** is the **Blyth site DeSmog covered** in September 2025 (planning ref `24_04112_OUTES`, Northumberland CC). DeSmog reported **580 diesel generators / 3.93 GWth nameplate** from the same application. Foxglove records the developer's own emissions estimate at 184,160 tCO2e/yr — which is **lower than the Digital Realty 2021 anchor** despite vastly larger capacity. This is a clear case where the developer's figure looks implausibly low against their own disclosed kit.
- **Thurrock #5 + North Weald #9** are the **Aisha Down & Priya Bharadia Guardian story** (May 2026). Developer-stated combined: 988,084 tCO2e/yr. The Guardian's analysis used the carbon-budget-comparison angle on top of these figures.
- **G-Park Docklands #8** (1,148 tCO2e/yr for 210 MW) and **103MW Court Lane #10** (340 tCO2e/yr for 103 MW) are the most extreme outliers — implying near-zero operational emissions. Worth treating as top candidates for "developer figure implausibly low" findings in our own pipeline.

## What's known to be missing from this list (for our scope)

1. **Scotland, Wales, Northern Ireland** — explicitly excluded by Foxglove.
2. **Sub-100 MW applications** — excluded by size threshold.
3. **≥100 MW applications without disclosed emissions** — Foxglove says roughly another **10 sites** in this category exist. Identifying these is a tractable next research task and immediately differentiates our work.
4. **On-site backup / standby generation capacity** — Foxglove's emissions figures are from grid-electricity demand only. They do not list generator counts or fuel types per site. The Blyth/Cambois 580-diesel finding from DeSmog is *not* reflected in Foxglove's emissions figure. This is the gap our pipeline is built to close.

## Immediate use as a benchmark

When our pipeline first ingests, these are the ten applications it **must** find. If our universe doesn't contain all ten with matching capacity figures, our scraping logic is incomplete. The councils to seed are at minimum:

- Northumberland
- North Lincolnshire (2 applications)
- Thurrock
- Buckinghamshire (Wycombe area)
- Epping Forest (Essex)
- + 4 to identify (DC01, International Trading Estate / GTR, G-Park Docklands, 103MW Court Lane)

Identifying the four with unknown councils is itself a useful early-stage scoping task.

## Open lookups (parked)

Council and planning reference still to confirm for four of the ten:

- **DC01** (2024, 320 MW, 6,056 tCO2e) — developer name not in report; one of the implausibly-low outliers.
- **International Trading Estate (GTR)** (2025, 256 MW, 219,031 tCO2e).
- **G-Park Docklands (GLP)** (2025 RM, 210 MW, 1,148 tCO2e) — implausibly-low outlier.
- **103MW Court Lane** (2022, 103 MW, 340 tCO2e) — implausibly-low outlier; likely Portsmouth (Cosham).

Three of the four are the implausibly-low-emissions outliers, which makes finding them a priority for the eventual "developer figure looks systematically understated" finding. **Parked** — return to before Phase 1 scraping.
