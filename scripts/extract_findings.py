"""Phase 4 — findings seed for the calibration round.

For the human-in-the-loop calibration (Claude Code Read tool + delta classifier),
findings are declared as structured Python rows keyed by application_ref.
The same loader inserts every app's findings; re-runs add a fresh round
under a new `inserted_at` per the schema's append-only contract.

This file grows as Luke and Claude work through the top-100 worklist.
Eventual production scale-up (Anthropic SDK + Sonnet 4.6, or whatever
shape) will write to `findings` under a different `model` string so the
two rounds coexist for audit.

Each entry: `doc_sha_prefix` is matched against
`documents.content_sha256 LIKE prefix%` for the application_ref to
resolve the document_id. `evidence_page` is the 1-based PDF physical
page number (so a reporter can Cmd-G in the file directly), NOT the
in-document page header which can drift.

Run: `.venv/bin/python -m scripts.extract_findings [app_ref ...]`
With no arguments, all apps are seeded; pass refs to scope a partial
re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402


# Provenance string for the LLM column. Reflects what actually happened
# during the calibration round: Opus 4.7 in Claude Code, reading PDFs
# via the Read tool. The eventual production sweep writes a different
# model name so the two rounds coexist.
MODEL = "claude-opus-4-7+read-tool"


FINDINGS_BY_APP: dict[str, list[dict[str, Any]]] = {

    # =====================================================================
    # Yorkshire Energy Park — gas reserve, the calibration headline app.
    # `EastRiding/16/02800/STPLF` — 21 MW gas-fired energy reserve, filed
    # six years before the EastRiding/22/00301/STREME DC at the same site.
    # =====================================================================
    "EastRiding/16/02800/STPLF": [
        # ----- Committee Report (scanned, no text layer — vision pass) -----
        {
            "doc_sha_prefix": "05abbe24",
            "signal_type": "applicant_name",
            "value_text": "AMP Energy Services Limited",
            "evidence_text": (
                "Application for Erection of a gas-fired energy reserve facility of up to 21MW "
                "capacity comprising of 14 gas reciprocating engine generators, 7 transformers "
                "and associated ancillary equipment and works ... by AMP Energy Services Limited"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "05abbe24",
            "signal_type": "fuel_supply",
            "value_text": "mains gas pipeline from National Transmission System; no on-site fuel storage",
            "evidence_text": (
                "Gas will be provided via a pipeline from the National Transmission System. "
                "There is no need to store fuel on site or fuel transfer around the site from "
                "fuel tanks to generators or delivery by road tanker."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "05abbe24",
            "signal_type": "grid_connection",
            "value_text": "11kV or 33kV cable export to substation",
            "evidence_text": (
                "Export from the site is through an 11kV or 33 KV cable to substation or "
                "alternative connection point."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "05abbe24",
            "signal_type": "grid_services_role",
            "value_text": "Short Term Operating Reserve (STOR) for National Grid",
            "evidence_text": (
                "This proposal, in conjunction with other Short Term Operating Reserves (STOR's), "
                "will ensure the National Grid has sufficient generation to meet demand by acting "
                "as an insurance against sudden losses in generation or unforeseen increases in demand."
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "05abbe24",
            "signal_type": "plant_configuration",
            "value_text": (
                "14 acoustically-contained engines paired into 7 step-up transformers, "
                "on concrete plinths within a 3m acoustic-fenced compound"
            ),
            "evidence_text": (
                "The proposed plant consists of 14 new gas reciprocating engines, each secured in "
                "an acoustic protected container, and 7 transformers. ... The containerised "
                "generators will be grouped in pairs, with each pair connected to a step up "
                "transformer. Each containerised engine and transformer will be sited on concrete "
                "plinth foundations. Two other buildings proposed on site are a gas kiosk and "
                "sub-station building."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "05abbe24",
            "signal_type": "decision_outcome",
            "value_text": "APPROVED (East Riding Planning Committee, 27 October 2016)",
            "evidence_text": "Recommendation: That the application be APPROVED as detailed in section 12 of this report.",
            "evidence_page": 2,
        },

        # ----- Updated Air Quality Report (bccbdf64) -----
        {
            "doc_sha_prefix": "bccbdf64",
            "signal_type": "engine_model",
            "value_text": "GE Jenbacher 420 GS gas engines",
            "evidence_text": (
                "The development comprises 14 of GE Jenbacher 420 GS gas engines, "
                "each rated at 1500 kW el with an exhaust flue/stack."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "bccbdf64",
            "signal_type": "engine_rated_kw",
            "value_number": 1500,
            "value_unit": "kW",
            "evidence_text": (
                "The development comprises 14 of GE Jenbacher 420 GS gas engines, "
                "each rated at 1500 kW el with an exhaust flue/stack."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "bccbdf64",
            "signal_type": "grid_services_role",
            "value_text": (
                "standby generator facility / Short Term Operating Reserve (STOR) "
                "backing intermittent renewables (wind) on the National Grid"
            ),
            "evidence_text": (
                "AMP Energy Services Limited is proposing to make an application for full "
                "planning permission to install a standby generator facility (also known as a "
                "short term operating reserve – STOR) on a site at Hedon, Hull. The purpose of "
                "the facility is to provide electricity for the National Grid at times of "
                "shortage from other energy sources, particularly renewable sources such as "
                "wind power."
            ),
            "evidence_page": 5,
        },

        # ----- Planning, Design & Access Statement (cdec105d) -----
        {
            "doc_sha_prefix": "cdec105d",
            "signal_type": "generator_count",
            "value_number": 14,
            "evidence_text": (
                "The application proposed the creation of a secure compound enclosed by "
                "acoustic fencing and containing 14 generators, office, storage and other "
                "ancillary buildings, together with associated access and works."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "cdec105d",
            "signal_type": "total_capacity_mw",
            "value_number": 21,
            "value_unit": "MW",
            "evidence_text": (
                "The application proposed the creation of a secure compound "
                "enclosed by acoustic fencing and containing 14 generators, "
                "office, storage and other ancillary buildings, together with "
                "associated access and works"
            ),
            "evidence_page": 5,
        },

        # ----- Application Form (a6c43d7b) -----
        {
            "doc_sha_prefix": "a6c43d7b",
            "signal_type": "facility_classification",
            "value_text": "standing reserve power plant",
            "evidence_text": (
                "Construction of a standing reserve power plant comprising 14 gas reciprocating "
                "engine generators and 7 transformers..."
            ),
            "evidence_page": 1,
        },
    ],

    # =====================================================================
    # Norwich Bioscience / John Innes Data Centre — reserved-matters
    # condition-discharge for a DC + CHP under parent outline 2012/1477.
    # `SouthNorfolkBroadland/2024/0841`. Editorial nuance: the CHP is
    # RELOCATED existing engines (not new kit) and the DC is a REPLACEMENT
    # building (not net-new at this site) — both absent from the description.
    # =====================================================================
    "SouthNorfolkBroadland/2024/0841": [
        # ----- Decision Notice (696fd100) -----
        {
            "doc_sha_prefix": "696fd100",
            "signal_type": "decision_outcome",
            "value_text": "APPROVED (South Norfolk Council, 10 October 2024)",
            "evidence_text": (
                "DECISION NOTICE ... Approval of the reserved matters following outline "
                "planning permission for development has been granted ... Date of Decision: "
                "10 October 2024"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "696fd100",
            "signal_type": "applicant_name",
            "value_text": "Mrs Sally Hines, The John Innes Centre, Norwich Research Park",
            "evidence_text": (
                "Applicant Mrs Sally Hines The John Innes Centre Norwich Research "
                "Park Norwich NR4 7UH"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "696fd100",
            "signal_type": "agent_name",
            "value_text": "Lanpro Services Limited (Mr Dean Starkey)",
            "evidence_text": (
                "Agent Mr Dean Starkey Lanpro Services Limited 98 Pottergate "
                "Norwich NR2 1EQ"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "696fd100",
            "signal_type": "facility_classification",
            "value_text": (
                "Reserved-matters condition-discharge under parent outline 2012/1477; "
                "discharges conditions 4, 5, 6, 7, 8, 10, 12, 20, 22, 23"
            ),
            "evidence_text": (
                "DISCHARGE OF CONDITIONS IMPOSED ON 2012/1477 "
                "Condition 4 : Surface water "
                "... Condition 5 : Foul water "
                "... Condition 6 : Contamination "
                "... Condition 8 : Monitoring "
                "... Condition 10 : External lighting"
            ),
            "evidence_page": 3,
        },

        # ----- Detailed Air Quality Assessment (192c94e5) — the editorial gold -----
        {
            "doc_sha_prefix": "192c94e5",
            "signal_type": "chp_engine_provenance",
            "value_text": "CHP comprising EXISTING ENGINES being relocated (not new kit)",
            "evidence_text": (
                "The proposal is for the construction of a Data Centre at the John Innes Centre "
                "on Norwich Business Park. The Data Centre will include Combined Heat and Power "
                "(CHP) comprising existing engines that are being relocated. Both the construction "
                "activity, and operation of the CHP plant, have the potential to emit pollutants "
                "to the air."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "192c94e5",
            "signal_type": "facility_classification",
            "value_text": "replacement (unstaffed) data centre building at John Innes Centre, Norwich Research Park",
            "evidence_text": (
                "The development will not generate any additional road traffic once operational "
                "because the building is a replacement building and will not be staffed."
            ),
            "evidence_page": 18,
        },
        {
            "doc_sha_prefix": "192c94e5",
            "signal_type": "chp_emission_load",
            "value_text": "relocated CHP units exceed the IAQM/EPUK 5 mg NOₓ/s assessment threshold",
            "evidence_text": (
                "The building will be served by relocated CHP units which will exceed the "
                "IAQM/EPUK threshold of 5mgNOx/s. Therefore, this is quantitatively assessed "
                "in this detailed air quality assessment."
            ),
            "evidence_page": 18,
        },
        {
            "doc_sha_prefix": "192c94e5",
            "signal_type": "standby_generator_regime",
            "value_text": "standby generators present; testing every 6 months for short periods only",
            "evidence_text": (
                "The development will include standby generators. These will only operate during "
                "power outages and for routine testing. Testing is only done every 6 months for "
                "short periods. Therefore, it is unlikely these standby generators will have a "
                "significant impact on local air quality as their use is likely to be very "
                "infrequent."
            ),
            "evidence_page": 18,
        },
        {
            "doc_sha_prefix": "192c94e5",
            "signal_type": "predicted_no2_impact",
            "value_text": (
                "predicted annual mean NO₂ change from CHP ≤ 5% of objective at all modelled "
                "receptors (max 1.8 µg/m³ increase); modelled NO₂ ≤ 24% of 40 µg/m³ AQAL"
            ),
            "evidence_text": (
                "The predicted annual mean NO2 concentration change due to emissions from the "
                "proposed CHP is no more than 5% of the relevant objective at all modelled "
                "receptors in each scenario. The modelled NO2 concentrations at each receptor is "
                "no greater than 24% of the Air Quality Annual Limit (AQAL) in any modelled "
                "scenario."
            ),
            "evidence_page": 20,
        },
    ],

    # =====================================================================
    # Poplar Business Park residential NMA — editorially a worklist
    # false-positive: triage caught the CHP / energy-centre keywords in
    # the description, but the deep-read shows the "energy centre" is a
    # building-services heating hub (~100 kWe CHP) for a Phase 1 housing
    # block, not on-site power generation for a data centre. Useful
    # demonstration that the pipeline can disambiguate keyword-matched
    # adjacents from substantive DC-relevant cases.
    # `TowerHamlets/PA/15/01527/S`.
    # =====================================================================
    # =====================================================================
    # Humber Tech Park (Elsham) — `NorthLincs/PA/2024/584`. Outline for a
    # 3-building hyperscale DC, 384 MW IT load total, 576 MW total site
    # load, 250 × 2.4 MW diesel generators (≈600 MW backup capacity).
    # Description names "emergency backup generators / fuel storage /
    # district heating centre" — hides the magnitudes. The Fuel Storage
    # Report explicitly frames the generators as "designed to act as the
    # primary supply" with the grid as "an economical alternative that
    # would normally be used" — backup-only in practice, primary-capable
    # in design. Document set is rich: AQA, dedicated Fuel Storage Report,
    # Sustainability & Renewable Energy Statement, Acoustics Assessment,
    # Planning Statement, all dated April-May 2024.
    # =====================================================================
    "NorthLincs/PA/2024/584": [
        # ----- Fuel Storage Report (Future-tech, 30/04/2024) -----
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "applicant_name",
            "value_text": "Humber Tech Park Ltd (c/o Anthony Crean KC, 75D Banbury Road, Oxford OX2 6PE)",
            "evidence_text": "Humber Tech Park Ltd Anthony Crean KC 75D Banbury Road Oxford OX2 6PE",
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "facility_classification",
            "value_text": (
                "hyperscale data-centre campus: 3 × 128 MW IT-load buildings "
                "(48 × 8 MW data halls), 576 MW total site load including "
                "mechanical/building services"
            ),
            "evidence_text": (
                "It is currently proposed that three data centre buildings will be "
                "constructed on the site and that each will have: Sixteen 8MW data "
                "halls each with an associated 4MW of mechanical and building "
                "services loads. Giving a total IT load per building of 128MW and "
                "supporting services load of 64MW. Each block of 12MW demand will "
                "be supported by various configurations of 2.4MW generators a "
                "total of 250 generators across the site. Thus, the overall site "
                "load for all three buildings is expected to be of the order of "
                "576 MW"
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "generator_count",
            "value_number": 250,
            "evidence_text": (
                "Each block of 12MW demand will be supported by various configurations "
                "of 2.4MW generators a total of 250 generators across the site."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "engine_rated_mw",
            "value_number": 2.4,
            "value_unit": "MW",
            "evidence_text": (
                "Each block of 12MW demand will be supported by various configurations "
                "of 2.4MW generators a total of 250 generators across the site."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "fuel_type",
            "value_text": "diesel (with on-site bulk storage)",
            "evidence_text": (
                "The purpose of this document is to provide an overview of the project "
                "scope and a basis of design for the proposed diesel generator fuel "
                "storage at the data centre development site in Humberside."
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "fuel_consumption_per_engine_lph",
            "value_number": 475,
            "value_unit": "L/hr",
            "evidence_text": (
                "At this stage generator fuel consumption will be calculated using "
                "475 litres per hour per engine at 80% load ... Fuel Consumption "
                "Rates Area No Engines at 80% load L/hr L/24hr Whole Site 250 "
                "118,750 2,850,000 ... Per Engine 1 475 11,400"
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "fuel_consumption_site_lph",
            "value_number": 118750,
            "value_unit": "L/hr",
            "evidence_text": (
                "Fuel Consumption Rates Area No Engines at 80% load L/hr L/24hr "
                "Whole Site 250 118,750 2,850,000"
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "fuel_storage_hours",
            "value_number": 24,
            "value_unit": "hours",
            "evidence_text": (
                "sufficient bulk fuel storage would be provided on-site for approximately "
                "24 Hours of continuous running of the generators. Each of these bulk "
                "fuel storage facilities would comprise two tanks ... The individual "
                "generator rooms are also currently being sized to accommodate a daily "
                "service tank sufficient to maintain each generator for up to 6 hours."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "generator_operation_role",
            "value_text": (
                "designed as primary-supply capable, operated as emergency backup "
                "(grid normal); routine testing only — generators expected to run only "
                "for testing or grid-failure scenarios"
            ),
            "evidence_text": (
                "this site will be designed with the generators to act as the primary "
                "supply but also with the incoming grid supply as an economical "
                "alternative that would normally be used. Accordingly, the generators "
                "are only expected to run for routine testing or in the unlikely event "
                "of failures with either the incoming electrical supply or site "
                "distribution."
            ),
            "evidence_page": 6,
        },

        # ----- Air Quality Assessment (10.05.2024) -----
        {
            "doc_sha_prefix": "819f38cf",
            "signal_type": "generator_count",
            "value_number": 250,
            "evidence_text": (
                "The development will consist of a data centre scheme distributed across "
                "three buildings and will include 250 emergency back-up generators."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "819f38cf",
            "signal_type": "engine_rated_kva",
            "value_number": 3000,
            "value_unit": "kVA",
            "evidence_text": (
                "A 250 no. 3,000 kVA diesel generators will operate to supply backup "
                "power to the site during power outage from the national grid."
            ),
            "evidence_page": 62,
        },
        {
            "doc_sha_prefix": "819f38cf",
            "signal_type": "standby_generator_regime",
            "value_text": (
                "each of the 250 generators tested separately for 30 minutes per month "
                "at full load"
            ),
            "evidence_text": (
                "To satisfy this requirement, each of the 250 generator plant will "
                "be tested separately ... The assumption within this assessment is "
                "that the generators will be tested separately, for 30 minutes per "
                "month, at full load"
            ),
            "evidence_page": 36,
        },

        # ----- Sustainability & Renewable Energy Statement (24.04.2024) -----
        {
            "doc_sha_prefix": "89571aef",
            "signal_type": "operational_power_demand_mw",
            "value_number": 38,
            "value_unit": "MW",
            "evidence_text": (
                "Maximum power demand ≈ 450 MW "
                "... Assumed operational diversity 50% of maximum "
                "... Operational power demand 38 MW "
                "... Data centre operation 8760 hours / year "
                "... Annual energy consumption 1,664,400,000 kWh"
            ),
            "evidence_page": 14,
        },
        {
            "doc_sha_prefix": "89571aef",
            "signal_type": "considered_renewable_option",
            "value_text": (
                "19 MW biomass-fuelled CCHP plant considered (would meet 10% reduction "
                "target but rejected as impractical — needs 680,000 m³ wood chip / year, "
                "equivalent to 136 articulated lorry deliveries per week)"
            ),
            "evidence_text": (
                "A 19MW biomass fuelled Combined Cooling Heat and Power (CCHP) plant "
                "could provide the targeted 10% reduction... In terms of fuel "
                "requirements a 19MW plant needs around 680,000m3 of wood chip per "
                "annum, which equates to 136 articulated lorry deliveries per week."
            ),
            "evidence_page": 16,
        },
        {
            "doc_sha_prefix": "89571aef",
            "signal_type": "considered_renewable_option",
            "value_text": (
                "100 kW medium-scale wind turbine considered (would offset only 83 "
                "tonnes CO2/year — negligible against 1.66 TWh annual energy demand)"
            ),
            "evidence_text": (
                "A medium scale wind turbine (with a 20m rotor diameter and rated "
                "power of ≈100kW) located on the site could produce around 195,000kWh "
                "per annum, which would it turn offset around 83 tonnes of CO2 per "
                "annum."
            ),
            "evidence_page": 16,
        },

        # ----- Planning Statement (01.05.2024) -----
        {
            "doc_sha_prefix": "d544e186",
            "signal_type": "total_it_load_mw",
            "value_number": 384,
            "value_unit": "MW",
            "evidence_text": (
                "The Data Centre would provide an IT Load (the key measure of data "
                "centre capacity) of up to 384MW. ... Up to three Data Centre buildings "
                "capable of 384MW of IT load with a total GEA of 309,000 sqm, including "
                "ancillary office space, with a maximum height of 13m (15m with the "
                "external gantry and flues)."
            ),
            "evidence_page": 8,
        },
    ],
    # =====================================================================
    # Elsham Tech Park — `NorthLincs/PA/2025/643`. The biggest DC
    # application in the worklist by IT load: ~1 GW. Includes BOTH a
    # continuous-operation natural-gas energy centre (20 engines, ~50 MW
    # CHP with heat recovery) AND 650 diesel back-up generators
    # (~1.6 GW). North Lincolnshire Council issued a Screening Opinion
    # on 2025-05-13 confirming NO EIA required — editorially worth
    # scrutinising. Developer: Greystoke Land. Description hides the
    # magnitudes.
    # =====================================================================
    "NorthLincs/PA/2025/643": [
        # ----- Planning Statement (Pegasus Group, 20.05.2025) -----
        {
            "doc_sha_prefix": "bccfdf28",
            "signal_type": "applicant_name",
            "value_text": "Elsham Tech Park Ltd (developer: Greystoke Land; agent: Pegasus Group)",
            "evidence_text": (
                "This Planning Statement has been prepared on behalf of Elsham Tech Park "
                "Ltd (the 'Applicant'). It relates to an Outline Planning Application that "
                "is submitted in connection with land adjacent to Elsham Wolds Industrial "
                "Estate, in North Lincolnshire (the 'Application Site')."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "bccfdf28",
            "signal_type": "total_it_load_mw",
            "value_number": 1000,
            "value_unit": "MW",
            "evidence_text": (
                "In summary, the application seeks outline planning permission for a "
                "large scale data centre campus and other associated works. It would "
                "provide a total IT Load (the key measure of data centre capacity) of "
                "approximately 1,000MW."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "bccfdf28",
            "signal_type": "eia_screening_outcome",
            "value_text": (
                "No EIA required — North Lincs Council Screening Opinion, 13 May 2025: "
                "'the proposal would be unlikely to have any significant environmental "
                "effects'"
            ),
            "evidence_text": (
                "The LPA issued a formal screening opinion on 13th May 2025. It "
                "confirmed that an EIA would not be required. It stated inter alia "
                "that:- 'North Lincolnshire Council advises that in light of the "
                "available information and having regard to the location and nature "
                "of the proposed development and the selection criteria for screening "
                "Schedule 2 development as set out in "
                "... Schedule 3 of the 2017 Regulations, the proposal would be "
                "unlikely to have any significant environmental effects "
                "... The proposed development although constituting Schedule 2 "
                "development category 10 is not considered to warrant an "
                "Environmental Impact Assessment"
            ),
            "evidence_page": 6,
        },

        # ----- Air Quality Assessment (Logika Group, 02.06.2025) -----
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "facility_classification",
            "value_text": (
                "1 GW data-centre campus with two combustion plant categories: a "
                "continuous-operation natural-gas energy centre AND back-up diesel "
                "generators (570+ emissions stacks total)"
            ),
            "evidence_text": (
                "The proposals are for an outline application involving the construction "
                "of a campus of data centres, distributed across a number of buildings, "
                "as well as an energy centre. The data centres will include back-up "
                "diesel generators (for emergency power provision), whilst the energy "
                "centre will include natural gas engines. The combination of generators "
                "and engines is referred throughout the report as 'energy plant'. ... "
                "The back-up generators will only be used in the event of loss of power "
                "to the site, as well as part of a regular testing regime, whilst the "
                "energy centre will operate continuously."
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "energy_centre_engine_count",
            "value_number": 20,
            "evidence_text": (
                "The proposed data centres will contain a maximum of 670 emissions "
                "points, comprising 20 stacks associated with the energy centre, and "
                "up to 650 stacks associated with the back-up diesel generators."
            ),
            "evidence_page": 68,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "energy_centre_engine_mw",
            "value_number": 2.499,
            "value_unit": "MW",
            "evidence_text": (
                "Table A4-2: Plant Specifications and Modelled Emissions and Release "
                "Conditions (per Unit) ... Energy Centre Back-up Generator "
                "Specified Net Fuel Input (kW) 5,678 6,644 ... Power Output (kW) "
                "2,499 2,480 ... Specified Exhaust Temperature (°C) 120 c 500 ... "
                "Specified NOx Emission Rate (mg/Nm3) d 50 e 168 e"
            ),
            "evidence_page": 69,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "grid_services_role",
            "value_text": (
                "energy-centre natural-gas engines operate continuously (modelled "
                "year-round) — primary on-site combustion generation, not backup; "
                "back-up diesel generators run only for testing or grid-failure"
            ),
            "evidence_text": (
                "the model has been run assuming continuous operation of the energy "
                "centre, whilst the outputs from the generators have been scaled "
                "based on their anticipated maximum an nual operation ( six hours "
                "per generator each year)"
            ),
            "evidence_page": 36,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "energy_centre_heat_recovery",
            "value_text": (
                "energy-centre plant installed with heat recovery technology "
                "(120°C exhaust temperature post-recovery, vs 500°C for the diesel "
                "back-up generators); likely supports the on-site horticultural "
                "glasshouse named in the application description"
            ),
            "evidence_text": (
                "Specified Exhaust Temperature (°C) 120 c 500 ... It is "
                "assumed that the energy centre plant will be installed with Heat "
                "Recovery technology"
            ),
            "evidence_page": 69,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "backup_generator_count",
            "value_number": 650,
            "evidence_text": (
                "up to 650 stacks associated with the back-up diesel generators, which "
                "will operate to supply backup power to the site during a power outage. "
                "The precise number of back-up generator stacks required to service the "
                "data centre buildings will be finalised as part of the detailed design "
                "specifications."
            ),
            "evidence_page": 68,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "engine_model",
            "value_text": "Kohler KD3100-E (16-cylinder, US EPA Tier 2 compliant)",
            "evidence_text": (
                "diesel generators will be Kohler KD Series KD3100-E sets, with "
                "outputs of 2,480 kWe / 3,100 kVA. In total, a maximum of 650 of "
                "these generators may be required to service the proposed "
                "development's backup power requirements"
            ),
            "evidence_page": 20,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "engine_rated_mw",
            "value_number": 2.48,
            "value_unit": "MW",
            "evidence_text": (
                "Energy Centre Back-up Generator Specified Net Fuel Input (kW) "
                "5,678 6,644 ... Power Output (kW) 2,499 2,480 ... Specified "
                "NOx Emission Rate (mg/Nm3) d 50 e 168 e ... Specified PM "
                "Emission Rate (mg/Nm3) d N/A 64.5"
            ),
            "evidence_page": 69,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "standby_generator_regime",
            "value_text": (
                "650 diesel generators, each modelled for max 6 hours / year of test "
                "operation; 10-minute cold-start window per test at unabated NOx "
                "(~2,000 mg/Nm³ — 12× the controlled emission rate) before SCR is "
                "effective"
            ),
            "evidence_text": (
                "the outputs from the generators have been scaled based on their "
                "anticipated maximum an nual operation ( six hours per generator "
                "each year). A cold start penalty (see Paragraph 4.15) has been "
                "applied to the emission concentrations from the back-up generators "
                "... It is assumed that the emission limit value will be met within "
                "10 minutes of a cold start-up ... assuming each back-up generator "
                "operates for 10 minutes at the unabated NOx emission concentration "
                "(i.e. the US EPA Tier 2 emission standard of 6,400 mg/kWh"
            ),
            "evidence_page": 69,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "predicted_no2_impact",
            "value_text": (
                "annual mean NO₂ at nearest receptors: baseline 24.1 µg/m³ → with "
                "development 25.0 µg/m³ (+2% of objective; Logika Group judgement: "
                "'negligible'); 1-hour maximum: 67.4 µg/m³ vs 200 µg/m³ objective"
            ),
            "evidence_text": (
                "Table 7-1: Predicted Annual Mean Nitrogen Dioxide (NO2) "
                "Concentrations in 2023 (µg/m3) ... Overall, the construction "
                "and operational air quality effects of Elsham Tech Park are "
                "judged to be not significant"
            ),
            "evidence_page": 36,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "operational_traffic",
            "value_text": (
                "1,278 vehicle trips daily, 70 HDV; ~50% westbound on M180 toward "
                "Scunthorpe, 21% southbound A18, 16% northbound A15 toward "
                "Barton-upon-Humber"
            ),
            "evidence_text": (
                "The proposed development is expected to generate a total of 1,278 "
                "vehicle trips daily, of which 70 will be HDVs."
            ),
            "evidence_page": 35,
        },
        {
            "doc_sha_prefix": "431ed476",
            "signal_type": "dispersion_modelling_basis",
            "value_text": (
                "ADMS-6 dispersion model; Humberside meteorological data 2019-2023; "
                "12 × 12 km Cartesian grid at 50 m resolution; building downwash "
                "modelled; receptor heights 18-27 m for back-up generator stacks "
                "(located on building roofs), 12 m for energy centre flues"
            ),
            "evidence_text": (
                "The impacts of emissions from the proposed energy plant have been "
                "predicted using the ADMS-6 dispersion model ... The energy centre "
                "flues have been modelled at a height of 12 m, whilst the back-up "
                "generator flues have been modelled 4 m above the building upon "
                "which it is located"
            ),
            "evidence_page": 68,
        },
    ],
    # =====================================================================
    # Project Union at Bulls Bridge (Ark Data Centres) — Hillingdon
    # `75111/APP/2020/1955`. The substantive parent outline that every
    # 2021-2025 Hillingdon worklist app (75111/APP/2021/* through /2025/*)
    # discharges conditions of. 22 standby reciprocating engines, energy
    # centre >50 MW thermal output (requires EA Part A1 environmental
    # permit). Within Hillingdon AQMA + 160m from Hayes North Hyde Road
    # AQFA. The planning portal description has the AQA's
    # "stand-by gas fired generation plant" mangled into
    # "stand-by generation plant and gas storage" — worth flagging.
    # =====================================================================
    "Hillingdon/75111/APP/2020/1955": [
        # ----- Air Quality Assessment (Phlorum Ltd, 15 June 2020) -----
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "applicant_name",
            "value_text": (
                "Ark Data Centres (ARK Estates 2 Ltd), 240 Blackfriars Road, London "
                "SE1 8NW — internal codename 'Project Union'"
            ),
            "evidence_text": (
                "Phlorum Ltd has been commissioned by Hurley Palmer Flatt on behalf "
                "of Ark Data Centres "
                "... for the proposed development of a data centre at Land at "
                "Bulls Bridge Industrial Estate, North Hyde Gardens, Hayes UB3 4QQ"
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "engineering_consultant",
            "value_text": (
                "Hurley Palmer Flatt (M&E lead); Phlorum Ltd (air quality assessment)"
            ),
            "evidence_text": (
                "Phlorum Ltd has been commissioned by Hurley Palmer Flatt on behalf of "
                "Ark Data Centres"
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "facility_classification",
            "value_text": (
                "new-build data centre with two MV Energy Centres including stand-by "
                "GAS FIRED generation plant + HV sub-station (the planning portal "
                "description has the 'gas fired' detail mangled into 'gas storage')"
            ),
            "evidence_text": (
                "Site clearance and preparation, including the demolition of remaining "
                "buildings, and the redevelopment of the site to provide: a new data "
                "centre, two MV Energy Centres (including stand-by gas fired generation "
                "plant), an HV Sub-Station, a visitor reception centre, plant"
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "generator_count",
            "value_number": 22,
            "evidence_text": (
                "In order to meet the electrical demand for the data centre in the "
                "event of a grid failure, proposals include 22 no. standby gas "
                "generators"
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "fuel_type",
            "value_text": (
                "natural gas (reciprocating gas engines, NOT diesel — though one "
                "Ealing-Council consultee response references '22 diesel generators', "
                "suggesting a fuel-type change during the application's evolution; AQA "
                "confirms gas-fired)"
            ),
            "evidence_text": (
                "reciprocating gas engine installations which are operational for fewer "
                "than 500 hours a year, like the proposed development, do not need to "
                "adhere to the ELVs. Regardless, the proposed standby generators are to "
                "incorporate selective catalytic reduction (SCR) technology and are "
                "understood to achieve a NOx emission rate below the ELV of 100mg.Nm-3."
            ),
            "evidence_page": 8,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "energy_centre_thermal_mw",
            "value_text": (
                "energy centre thermal output >50 MW — requires Environment Agency "
                "Part A1 Environmental Permit (separate application from planning)"
            ),
            "evidence_text": (
                "the proposed energy centre has a thermal output greater than 50MW "
                "it will require an Environmental Permit ... from the Environment "
                "Agency. A separate application is being made to the Environment "
                "Agency"
            ),
            "evidence_page": 8,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "standby_generator_regime",
            "value_text": (
                "monthly + bi-annual testing only; generator runtime <500 hrs/year "
                "(exempts from IED ELVs); modelled scenarios include 1 grid-failure/year "
                "at 100% load (= 20 generators operating)"
            ),
            "evidence_text": (
                "the principal emissions associated with the standby generators will be "
                "from monthly and bi-annual testing events. Nonetheless, a grid failure "
                "is not impossible and therefore this assessment considers a scenario in "
                "which one grid failure occurs each year."
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "68ab7417",
            "signal_type": "aqma_proximity",
            "value_text": (
                "site within Hillingdon AQMA (declared 2003 for annual-mean NO₂ "
                "exceedances); 160 m north of Hayes North Hyde Road AQFA (one of 12 "
                "GLA-designated Air Quality Focus Areas in Hillingdon for high NO₂ + "
                "human exposure)"
            ),
            "evidence_text": (
                "LBH has declared one Air Quality Management Area (AQMA) that "
                "covers the southern two thirds of the Borough. This AQMA was "
                "declared in 2003 "
                "... The proposed development is located within this AQMA "
                "... There are a number of AQFAs in the vicinity of the "
                "application site; including the Hayes North Hyde Road AQFA, "
                "which is found, at its closest, circa 160m to the south of the "
                "main site"
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "21f29d4a",  # OFFICERS REPORTS
            "signal_type": "consultee_concern",
            "value_text": (
                "London Borough of Ealing Regulatory Services flagged concerns about "
                "the standby generators (description in their comment as '22 diesel "
                "generators') — apparent fuel-type discrepancy with AQA's gas-engine "
                "description"
            ),
            "evidence_text": (
                "LONDON BOROUGH OF EALING FOLLOW-UP: We have had further comment from "
                "our Regulatory Services Team, who would wish to raise the following "
                "concern to the proposal. 'The following application has proposed to "
                "have standby 22 diesel generators...'"
            ),
            "evidence_page": 37,
        },
    ],
    # =====================================================================
    # Small Hillingdon DC — `49261/APP/2024/2904`. 1 MW IT load, single
    # back-up generator. The "small DC" worked example: confirms the
    # description-stated single generator scale rather than uncovering
    # hidden magnitudes.
    # =====================================================================
    "Hillingdon/49261/APP/2024/2904": [
        {
            "doc_sha_prefix": "b346a095",
            "signal_type": "total_it_load_mw",
            "value_number": 1,
            "value_unit": "MW",
            "evidence_text": (
                "the proposed Data Centre will have a negligible cooling water demand "
                "(< 150 m3 per annum) and lower operational power demand, with only one "
                "back-up generator (1.08MW) required for the proposed data centre "
                "building. ... The Proposed Development will contribute 1 MW of "
                "additional data centre capacity towards the unmet requirement in the "
                "Hayes availability zone."
            ),
            "evidence_page": 21,
        },
        {
            "doc_sha_prefix": "b346a095",
            "signal_type": "engine_rated_mw",
            "value_number": 1.08,
            "value_unit": "MW",
            "evidence_text": (
                "In the unlikely event of a loss of power supply, i.e. temporary grid "
                "blackout, the single emergency (back-up) generator (1.08 MW) will be "
                "utilised to maintain power supply."
            ),
            "evidence_page": 27,
        },
        {
            "doc_sha_prefix": "b346a095",
            "signal_type": "facility_classification",
            "value_text": (
                "small single-building data centre (Class B8) with a single emergency "
                "back-up generator; 1 MW utility-grid connection agreement pre-arranged "
                "with the utility provider; aimed at the 'Hayes availability zone' "
                "unmet capacity"
            ),
            "evidence_text": (
                "The accompanying Infrastructure and Utility Assessment confirms a "
                "connectivity agreement is in place between the Operator and the "
                "utility provider for a 1MW capacity connection to serve the Data "
                "Centre. ... The Proposed Development will contribute 1 MW of "
                "additional data centre capacity towards the unmet requirement in the "
                "Hayes availability zone."
            ),
            "evidence_page": 48,
        },
        {
            "doc_sha_prefix": "b346a095",
            "signal_type": "market_context",
            "value_text": (
                "London region data-centre capacity Q1 2024 = 993 MW peak IT load; "
                "+125 MW new supply expected through 2024"
            ),
            "evidence_text": (
                "As of Q1 2024, the London region had a data centre capacity (measured "
                "in terms of MW of peak IT load) of 993MW – with an anticipated 125 MW "
                "of new supply to be added throughout 2024."
            ),
            "evidence_page": 10,
        },
    ],
    # =====================================================================
    # Union Park expansion — `75111/APP/2022/1007`. Adds a third energy
    # centre to the 2020 outline (22 generators → 42 generators), modelled
    # at 1,176-1,386 generator-hours/year total. Ark operates 28 of the
    # 42 generators directly; remaining 14 are reserved for a future
    # hyperscale tenant.
    # =====================================================================
    "Hillingdon/75111/APP/2022/1007": [
        # ----- Damage Cost Addendum (Phlorum Ltd, 2022) -----
        {
            "doc_sha_prefix": "38da9dd1",  # damage-cost / dispersion addendum
            "signal_type": "facility_classification",
            "value_text": (
                "expansion of Ark Project Union — site now configured with THREE energy "
                "centres (vs two in the 2020 outline), 42 generators total, "
                "1,176-1,386 modelled generator-hours/year"
            ),
            "evidence_text": (
                "The above Damage Cost Calculation is based on the assumption "
                "that all 42 generators across the three proposed "
                "... (testing and maintenance) for 26 hours per year, with an "
                "additional two hours worth of grid failures. This equates to "
                "a total of 1,176 generator-hours annually"
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "b0a8d2c7",
            "signal_type": "generator_count",
            "value_number": 42,
            "evidence_text": (
                "For the purposes of this assessment, it was also assumed that the site "
                "loading for the grid failure would be 100% and all 42 generators "
                "would run concurrently."
            ),
            "evidence_page": 28,
        },
        {
            "doc_sha_prefix": "b0a8d2c7",
            "signal_type": "operator_tenant_split",
            "value_text": (
                "Ark operates 28 of 42 generators directly (its own three data halls); "
                "14 generators reserved for a future hyperscale tenant"
            ),
            "evidence_text": (
                "If a future (hyperscaler) tenant were to operate 14 generators, "
                "with Ark operating the other 28 "
                "... Table D.8: Proposed Generators Emission Rates (Ark "
                "operation of three data halls) Total emissions (kg) Ark "
                "Future (hyperscaler) tenant"
            ),
            "evidence_page": 53,
        },
        {
            "doc_sha_prefix": "b0a8d2c7",
            "signal_type": "predicted_no2_impact",
            "value_text": (
                "modelled normal year: 0.94 tonnes NOₓ and 0.02 tonnes PM₂.₅ across all "
                "42 generators; modelled testing scenario is 7.5× more conservative "
                "than realistic hyperscaler-tenant operating scenario"
            ),
            "evidence_text": (
                "The proposed development during a normal year of operation, with Ark "
                "operating all 42 generators would not generate more than 0.94 tonnes "
                "of NOX and 0.02 tonnes of PM2.5"
            ),
            "evidence_page": 89,
        },
        # ----- Supporting Information (site history) -----
        {
            "doc_sha_prefix": "498f0fc7",
            "signal_type": "site_history",
            "value_text": (
                "site historically hosted a 280 MW CEGB open-cycle gas-turbine power "
                "station (since demolished) — the proposed DC sits on a brownfield "
                "former-generation site"
            ),
            "evidence_text": (
                "A 280 MW open-cycle gas-turbine power station, the power station owned "
                "and operated by the CEGB occupied a large site on either side of "
                "Yeading Brook, to the south of the Paddington main line and north..."
            ),
            "evidence_page": 3,
        },
    ],
    # =====================================================================
    # West London Technology Park (Iver, Buckinghamshire) —
    # `Hillingdon/39707/APP/2022/3243`. Out-of-borough consultation
    # hosted on the Hillingdon Ocella portal. Greystoke Land's THIRD UK
    # DC site in this dataset (alongside Humber Tech Park and Elsham
    # Tech Park, both NorthLincs). Same Future-tech M&E consultant
    # signature across all three. 147 MW IT load, 171 diesel generators.
    # =====================================================================
    "Hillingdon/39707/APP/2022/3243": [
        {
            "doc_sha_prefix": "b44023c9",  # D&A Statement
            "signal_type": "applicant_name",
            "value_text": (
                "Greystoke Land Ltd (project: West London Technology Park; M&E consultant: "
                "Future-tech, per the doc reference '9526-FUT-...' pattern shared with "
                "Greystoke's Humber Tech Park and Elsham Tech Park applications)"
            ),
            "evidence_text": (
                "PROJECT DETAILS Client: Greystoke Land Ltd Site Address: West London "
                "Technology Park, land to the north of Palmers Moor Lane, Iver Area "
                "51.48ha Final Day Capacity 147MW 49526-FUT-ZZ-ZZ-PP-Z-0001"
            ),
            "evidence_page": 22,
        },
        {
            "doc_sha_prefix": "b44023c9",
            "signal_type": "total_it_load_mw",
            "value_number": 147,
            "value_unit": "MW",
            "evidence_text": (
                "Final Day Capacity 147MW ... Building 1 – 49MW Building 2 – 49MW "
                "Building 3 – 49MW"
            ),
            "evidence_page": 22,
        },
        {
            "doc_sha_prefix": "b44023c9",
            "signal_type": "facility_classification",
            "value_text": (
                "3-building DC park on 51.48 ha former landfill, 49 MW IT load per "
                "building (3 × 21 × 3.5 MW data halls), with on-site district heating "
                "network and 171 diesel back-up generators"
            ),
            "evidence_text": (
                "Building 1 – 49MW Building 2 – 49MW Building 3 – 49MW ... GENERAL "
                "ARRANGEMENT – INTERIOR GROUND FLOOR 7 MMRs Data Hall • Approx. 1100m2 "
                "• 3.5MW IT load ... GENERAL ARRANGEMENT – FIRST FLOOR ... Data Hall ... "
                "3.5MW IT load ... GENERAL ARRANGEMENT – SECOND FLOOR ... 3.5MW IT load"
            ),
            "evidence_page": 23,
        },
        # ----- Air Quality Report -----
        {
            "doc_sha_prefix": "529582c0",  # AQA  # placeholder, filled below
            "signal_type": "generator_count",
            "value_number": 171,
            "evidence_text": (
                "The development is proposed to be a data centre scheme distributed "
                "across three buildings, which will include 171 back-up diesel "
                "generators (for emergency power provision); with small amounts of "
                "traffic associated with the development."
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "529582c0",  # AQA
            "signal_type": "fuel_type",
            "value_text": "diesel back-up generators (with on-site fuel storage)",
            "evidence_text": (
                "The proposal involves the installation of 171 no. 2,000 kWe "
                "(2,500 kVa) back-up diesel generators; 57 for each data centre "
                "building"
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "b44023c9",  # Planning Statement (Project Details cover)
            "signal_type": "operator_pattern",
            "value_text": (
                "Greystoke Land's THIRD UK DC site (alongside Humber Tech Park at "
                "South Killingholme, NL/PA/2024/584; and Elsham Tech Park at Elsham "
                "Wolds, NL/PA/2025/643). All three use the same Future-tech M&E "
                "consultant (doc reference prefix '*-FUT-*') and follow the same "
                "doc-set template (AQA, Fuel Storage Report, Sustainability Statement). "
                "Combined indicative IT load across the three sites: ~1.5 GW."
            ),
            "evidence_text": (
                "Client: Greystoke Land Ltd ... 49526-FUT-ZZ-ZZ-PP-Z-0001"
            ),
            "evidence_page": 22,
        },
    ],
    # =====================================================================
    # Humber Tech Park EIA screening request — `NorthLincs/PA/SCR/2024/2`.
    # The screening predecessor to `NorthLincs/PA/2024/584` (Humber Tech
    # Park full application). 6 docs: the screening request itself + 4
    # statutory consultee responses (Environment Agency, National
    # Highways, NE Lindsey IDB, Archaeology) + 1 mystery 'x.pdf'.
    # =====================================================================
    "NorthLincs/PA/SCR/2024/2": [
        {
            "doc_sha_prefix": "5c85e874",
            "signal_type": "facility_classification",
            "value_text": (
                "EIA screening request for the Humber Tech Park full application "
                "(submitted later as NorthLincs/PA/2024/584) — 3 buildings, 384 MW IT "
                "load, 309,000 sqm GEA"
            ),
            "evidence_text": (
                "The Applicant proposes the submission of an outline planning "
                "application (with all matters reserved) which will comprise the "
                "following elements: Up to three Data Centre buildings capable of "
                "384MW of IT load with a total GEA of 309,000 sqm..."
            ),
            "evidence_page": 12,
        },
        {
            "doc_sha_prefix": "5c85e874",
            "signal_type": "nearby_development",
            "value_text": (
                "49.9 MW solar farm + BESS proposal 3.1 km south-east of the Humber "
                "Tech Park site (cumulative-impact context)"
            ),
            "evidence_text": (
                "It is approximately 3.1km south-east of the Site. Construction and "
                "operation of a solar farm (up to 49.9mw) and battery energy storage "
                "system (BESS) with associated works, equipment, infrastructure..."
            ),
            "evidence_page": 30,
        },
        {
            "doc_sha_prefix": "5b17c68e",
            "signal_type": "consultee_response_summary",
            "value_text": (
                "National Highways consultee response confirms the 384 MW × 3-building "
                "scope quoted in the screening note matches the full application"
            ),
            "evidence_text": (
                "Proposed development Within the EIA Screening note, the proposed "
                "development is stated to comprise: 'Up to three Data Centre "
                "buildings capable of 384MW of IT load with a total GEA of "
                "309,000 sqm...'"
            ),
            "evidence_page": 1,
        },
    ],
    # =====================================================================
    # Union Park district heating strategy discharge —
    # `Hillingdon/75111/APP/2025/2120`. Editorially substantive
    # condition-discharge: the energy centres are designed as continuous
    # low-grade heat sources but the district-heating connection is
    # currently unfeasible (no viable network nearby; leaflet drop to
    # neighbours yielded no interest).
    # =====================================================================
    "Hillingdon/75111/APP/2025/2120": [
        {
            "doc_sha_prefix": "0f39992c",
            "signal_type": "district_heating_outcome",
            "value_text": (
                "Condition 41 discharged: energy centres designed as continuous "
                "low-grade heat sources with provisions (valved tap-offs on cooling "
                "systems) for future DH connection, BUT implementation currently "
                "unfeasible — no viable DH network nearby + leaflet drop to "
                "neighbours yielded no significant interest in waste-heat export"
            ),
            "evidence_text": (
                "The report prepared by HDR concludes that, although a Waste Heat "
                "Recovery System could offer free cooling and contribute to long-term "
                "sustainability benefits, the absence of a viable District Heating "
                "Network within the vicinity of the development makes implementation "
                "currently unfeasible. Furthermore, a leaflet drop to owners and "
                "occupiers near Union Park regarding the potential to export waste "
                "heat from the data centre yielded no significant interest. ... There "
                "are provisions in the base building designs for the energy centres "
                "to be sources of continuous low-grade heat for connection into a "
                "future district heating system, should one be developed in the "
                "future. The provision consists of valved tap offs on appropriate "
                "sections of the energy centre cooling systems."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "0f39992c",
            "signal_type": "related_application",
            "value_text": (
                "future DH pipework would route via Ark's separate application "
                "`Hillingdon/75111/APP/2025/739` (red-line boundary covers the "
                "pipework — same developer)"
            ),
            "evidence_text": (
                "Whilst the district heating pipework is not shown to be within the "
                "red line boundary of permission ref. 75111/APP/2020/1955, it would "
                "be within the red line boundary of application ref. 75111/APP/2025/"
                "739, which is also owned by the same Developer. This means that the "
                "connection is feasible."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "0f39992c",
            "signal_type": "decision_outcome",
            "value_text": (
                "APPROVED (Condition 41 discharged) — but the requirement to comply "
                "with Condition 41 'remains in perpetuity'; the development must "
                "provide a single point of connection to a future DH network"
            ),
            "evidence_text": (
                "the application is recommended for approval. ... Whilst Condition 41 "
                "can be discharged, please be advised that the requirement to comply "
                "with Condition 41 remains in perpetuity. In effect, the development "
                "hereby approved shall provide a single point of connection to allow "
                "future connection to a district heating network."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "0f39992c",
            "signal_type": "engineering_consultant",
            "value_text": (
                "HDR (global engineering firm) prepared the Waste Heat Recovery / "
                "District Heat Network Connection Viability Study for the discharge"
            ),
            "evidence_text": (
                "HDR-0474-SWS-XX-REP-M-000001 Issue P02 Waste Heat Recovery and "
                "District Heat Network Connection Viability Study (Dated 3rd "
                "April 2025 HDR-0474-SWS-XX-REP-M-000001 Issue P03 Waste Heat "
                "Recovery and District Heat Network Connection Viability Study "
                "(Dated 15th October 2025)"
            ),
            "evidence_page": 2,
        },
    ],
    # =====================================================================
    # Basildon DC screening (Wickford) — `Basildon/23/01552/SCREEN`.
    # EIA Screening Opinion for a single-building greenfield DC in
    # Essex (modest scale by hyperscale standards). Decision: EIA not
    # required.
    # =====================================================================
    "Basildon/23/01552/SCREEN": [
        {
            "doc_sha_prefix": "ec526eb9",
            "signal_type": "facility_classification",
            "value_text": (
                "single-building DC of 18,330 sqm floorspace (12 m height) + 2,100 sqm "
                "energy centre + 7 m substation; 6.2 ha western parcel + 35 ha eastern "
                "parcel for open space / sports pitches; greenfield Green Belt site at "
                "Wickford"
            ),
            "evidence_text": (
                "The proposal comprises a data centre building of up to 18,330 sqm in "
                "floorspace and 12m (including roof plant) in height and an energy "
                "centre building of up to 2,100 sqm in floorspace and 12m in height. "
                "The proposed development also includes a 7m high substation, a 4m "
                "high security gatehouse, access road, car parking, cycle parking, "
                "service yard and loading facilities ... emergency back-up "
                "generators, fuel storage."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "ec526eb9",
            "signal_type": "eia_screening_outcome",
            "value_text": (
                "EIA NOT REQUIRED — Basildon Borough Council Screening Opinion; "
                "applicant filed request 13 December 2023"
            ),
            "evidence_text": (
                "The Local Planning Authority (LPA), Basildon Borough Council, has "
                "considered the proposals and its SCREENING OPINION is that: an EIA "
                "IS NOT REQUIRED. A request for a screening opinion was received by "
                "letter dated 13th December 2023."
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ec526eb9",
            "signal_type": "site_designation",
            "value_text": (
                "Green Belt site (Parcel 36 in Basildon Borough Green Belt Review "
                "2017); contributes to Green Belt purposes 1 (check sprawl of large "
                "built-up areas) and 3 (safeguarding countryside from encroachment); "
                "adjoins Grade II listed 'Fore Riders'; within 6km of 4 SSSIs "
                "(Norsey Woods, Hanningfield Reservoir, Langdon Hills, Wat Tyler "
                "Country Park)"
            ),
            "evidence_text": (
                "The site is within the Green Belt. ... The western parcel does, "
                "however, adjoin a Grade II listed building to the south-east, "
                "which is known as 'Fore Riders'. ... The site falls within "
                "Parcel 36 in the Basildon Borough Green Belt Review (2017) "
                "and partly contributes to Green Belt purposes 1"
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "ec526eb9",
            "signal_type": "related_application",
            "value_text": (
                "shares vehicular access with the consented Nevendon Road EV "
                "charging station (21/01515/FULL)"
            ),
            "evidence_text": (
                "Access to the site would be off Nevendon Road, sharing the access "
                "road to be created in association with the electric vehicle "
                "charging station (ref: 21/01515/FULL) which benefits from planning "
                "permission. An emergency access point would also be created on Old "
                "Nevendon Road, for use by the fire brigade and emergency vehicles "
                "only."
            ),
            "evidence_page": 2,
        },
    ],
    # =====================================================================
    # Yorkshire Energy Park — the DC. `EastRiding/22/00301/STREME`.
    # Reserved Matters Application #1 following outline permission
    # 17/01673/STOUTE. The marketed-green Tier 3 data centre at the
    # YEP, spatially neighbouring the 21 MW STPLF gas reserve we already
    # documented. Editorial crux: the Planning Statement markets the
    # whole park as Humber's "global transition to net zero" while
    # disclosing the Energy Centre is gas-fired CHP (with hydrogen
    # transition framed as future aspiration).
    # =====================================================================
    "EastRiding/22/00301/STREME": [
        # ----- Planning Statement (Avison Young, 8 March 2022) -----
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "applicant_name",
            "value_text": (
                "Hull Eco Park Ltd (HEPL) — agent: Avison Young (UK) Limited; "
                "Planning Statement authors: Kate Limbert, David Sweeting, "
                "Anne Burke-Hargreaves"
            ),
            "evidence_text": (
                "This Planning Statement has been prepared on behalf of Hull Eco Park "
                "Ltd (HEPL) to accompany a Reserved Matters Application (RMA) "
                "proposing an Energy Centre, Data Centre and associated "
                "infrastructure at land north west of Kingstown Hotel, Hull Road, "
                "Hedon ... For and on behalf of Avison Young (UK) Limited"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "facility_classification",
            "value_text": (
                "Yorkshire Energy Park Reserved Matters Application #1: Energy Centre "
                "+ Tier 3 Data Centre (region's first Tier 3, 24/7/365 operation) "
                "+ associated infrastructure. Marketed as Humber Freeport Zone's "
                "'next generation energy and technology business park' contributing "
                "to 'global transition to net zero'"
            ),
            "evidence_text": (
                "HEPL's vision for the Yorkshire Energy Park is to create a next "
                "generation energy and technology business park that will drive "
                "economic growth, support the local community and help position the "
                "Humber at the forefront of the global transition to net zero. "
                "Yorkshire Energy Park is a flagship development strategically "
                "located in the Humber Freeport Zone, at the heart of the UK's Energy "
                "Estuary. ... The Data Centre will be the region's first Tier 3 Data "
                "Centre and will house a data hall, office space and support space "
                "that will run 24 hours a day, 365 days a year."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "energy_centre_fuel",
            "value_text": (
                "GAS-FIRED Combined Heat and Power (CHP) plant — Energy Centre "
                "designed to supply 'low cost, resilient power to onsite occupiers' "
                "and scalable as demand grows. (Editorial: the energy-centre framing "
                "is primary-on-site combustion generation, NOT backup.)"
            ),
            "evidence_text": (
                "The Energy Centre will provide low cost, resilient power to onsite "
                "occupiers utilising a gas fired combined heat and power (CHP) plant "
                "that can be scaled up as the demand increases"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "hydrogen_aspirational",
            "value_text": (
                "Energy Centre fueled by NATURAL GAS at commissioning; hydrogen "
                "transition framed as future development goal, not initial design — "
                "the marketed-green claim depends on a yet-to-materialise "
                "fuel-switching technology"
            ),
            "evidence_text": (
                "Whilst initially the Energy Centre will utilise natural gas, the "
                "technology is being developed to easily enable a transition to "
                "hydrogen in the future as part of the Yorkshire Energy Park's "
                "journey to net zero carbon"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "renewable_component",
            "value_text": (
                "Energy Centre roof to include photovoltaic (solar) panels — token "
                "renewables alongside gas-fired CHP as primary generation"
            ),
            "evidence_text": (
                "The Energy Centre is being designed to include renewable technology "
                "such as photovoltaic (solar) panels"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "parent_permission",
            "value_text": (
                "Reserved Matters Application #1 following outline permission "
                "17/01673/STOUTE (approved by East Riding of Yorkshire Council on "
                "22 December 2020). First of a series of RMAs expected at the "
                "Yorkshire Energy Park"
            ),
            "evidence_text": (
                "This RMA is the first in a series of RMAs expected to be submitted "
                "at the Yorkshire Energy Park and follows approval on the 22 December "
                "2020 of Outline Planning Permission 17/01673/STOUTE (OPP)."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "spatial_link",
            "value_text": (
                "Site sits adjacent to the 21 MW gas-fired energy reserve facility "
                "at EastRiding/16/02800/STPLF (AMP Energy Services Ltd, approved "
                "2016 — different applicant but same site context). The pre-existing "
                "21 MW gas reserve + new gas-fired CHP energy centre + Tier 3 DC + "
                "marketed-green framing is the YEP editorial story."
            ),
            "evidence_text": (
                "land north west of Kingstown Hotel, Hull Road, Hedon (Proposed "
                "Development). ... at the heart of the UK's Energy Estuary."
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "9655e6e7",
            "signal_type": "job_creation_claim",
            "value_text": (
                "marketed at up to 4,480 jobs across construction + operational "
                "phases (full YEP scheme, not just RMA#1)"
            ),
            "evidence_text": (
                "Significant job creation – through both the construction and "
                "operational periods of the development – up to 4,480 jobs"
            ),
            "evidence_page": 3,
        },
    ],
    # =====================================================================
    # Birkhill / Coalburn DC + colocated solar + gas turbine —
    # `SouthLanarkshire/P/19/0896`. Rare Scottish entry with explicit
    # colocation of DC + 12 MW solar farm + 7.5 MW gas turbine + light
    # industrial — Planning Permission in Principle (Scottish PPP, the
    # outline equivalent). Site is the former M74 Central / Birkhill,
    # Coalburn at NS 838 364 (~33.3 ha).
    # =====================================================================
    "SouthLanarkshire/P/19/0896": [
        {
            "doc_sha_prefix": "146682ea",  # ground investigation report (historical)
            "signal_type": "site_context",
            "value_text": (
                "33.3 ha greenfield/quarry site at Birkhill, Coalburn (by Lesmahagow), "
                "South Lanarkshire — historical ground investigation by Johnson Poole "
                "& Bloomer for M74 Central Ltd dated July 2007 (re-used in the 2019 "
                "DC PPP submission); peat removal needed; no mining beneath site"
            ),
            "evidence_text": (
                "Johnson Poole & Bloomer Limited (JPB) were commissioned by Hodgins "
                "Smith Partnership on behalf of M74 Central Limited to carry out an "
                "initial Ground Investigation Report for the site at Birkhill, "
                "Coalburn by Lesmahagow. The site is centred on National Grid "
                "Reference NS 838 364 and occupies an area of approximately 33.3ha."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "df75c718",  # consultation response — Transport Scotland
            "signal_type": "facility_classification",
            "value_text": (
                "data centre + colocated 12 MW solar farm + 7.5 MW gas turbine + "
                "light industrial (Class 5) area — Scottish Planning Permission in "
                "Principle (the Scottish equivalent of outline permission). "
                "Application agent: Lodge Architects LLP (Glasgow)"
            ),
            "evidence_text": (
                "for planning permission in principle for erection of data "
                "centre (class 4 Business) and associated 12MW solar farm "
                "and 7.5MW gas turbine with light industrial class 5) area "
                "and associated infrastructure "
                "... Lodge Architects LLP, Crown House, 152 West Regent "
                "Street, Glasgow G2 2RQ"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "d4f864ee",  # Transport Scotland acknowledgement letter
            "signal_type": "consultee_response_summary",
            "value_text": (
                "Transport Scotland received the consultation 19 June 2019 — no "
                "objection flagged in the response (typical for non-trunk-road-adjacent "
                "applications)"
            ),
            "evidence_text": (
                "Transport Scotland Roads - Development Management TR /NPA /1A I "
                "acknowledge receipt of the planning application P/19/0896 for "
                "Planning Permission in Principle for erection of data centre "
                "(Class 4 Business) and associated..."
            ),
            "evidence_page": 1,
        },
    ],
    # =====================================================================
    # Bidder Street DC, Canning Town — `Newham/24/00088/FUL`. Former EMR
    # (scrap yard) site, Foster & Partners designed, 95,000 sqm total
    # floorspace across DC + plant + energy centre. 48 phased standby
    # diesel generators (12/year 2027-2030). 132kV/130MVA grid supply.
    # ~£11M s106 commitments incl. £2.67M carbon offset to render
    # 'zero carbon'. Recommended for approval at SDC 15 Oct 2024;
    # subject to Mayor of London Stage 2 referral.
    # =====================================================================
    "Newham/24/00088/FUL": [
        # ----- Committee Report (Newham SDC, 15 October 2024) -----
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "facility_classification",
            "value_text": (
                "DC building 72.3m AOD / ~59,923 sqm GEA + plant building 72.3m AOD "
                "/ ~30,302 sqm GEA + energy centre 32.4m AOD / ~4,789 sqm GEA = "
                "~95,000 sqm total floorspace on former EMR scrap yard, Bidder St, "
                "Canning Town"
            ),
            "evidence_text": (
                "Erection of a data centre (Use Class B8), comprising a Data Centre "
                "Building of approximately 72.3m AOD in height (approximately "
                "59,923sqm GEA including ancillary office space); a Plant Building "
                "of approximately 72.3m AOD in height (approximately 30,302sqm "
                "GEA), an Energy Centre of approximately 32.4m AOD in height "
                "(approximately 4,789sqm GEA), with associated works including "
                "landscaping, access, car and cycle parking, and servicing areas."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "architect",
            "value_text": (
                "Foster & Partners (Pritzker-prize-winning architect designing a "
                "data centre — design retention required by s106 + £100,000 "
                "Design Monitoring Fee)"
            ),
            "evidence_text": (
                "Architect/ Design Team retention (Foster & Partners) and Design "
                "Certifier provisions; Design Monitoring Fee of £100,000 (Indexed) "
                "for Architect/ Design Team changes."
            ),
            "evidence_page": 7,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "agent_name",
            "value_text": "RPS Consulting Services Limited (planning agent)",
            "evidence_text": "Agent: RPS Consulting Services Limited",
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "decision_outcome",
            "value_text": (
                "Recommended for APPROVAL at Newham Strategic Development "
                "Committee, 15 October 2024 — subject to Mayor of London (GLA) "
                "Stage 2 referral and s106 legal agreement; validation date "
                "2 January 2024"
            ),
            "evidence_text": (
                "LONDON BOROUGH OF NEWHAM STRATEGIC DEVELOPMENT COMMITTEE 15 "
                "October 2024 Application Number: 24/00088/FUL Validation "
                "Date: 2nd January 2024 Location: Land At Former EMR Site "
                "Bidder Street Canning Town London E16 4ST"
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "grid_connection",
            "value_text": (
                "132kV / 130 MVA power supply connection secured from UKPN in "
                "November 2020, with 'power on by December 2026' + additional "
                "grid network reinforcement works"
            ),
            "evidence_text": (
                "The applicant has further confirmed that they have secured a 132kV/"
                "130MVA power supply connection from the network operator UKPN in "
                "November 2020, for power on by December 2026, together with "
                "additional grid network reinforcement works"
            ),
            "evidence_page": 83,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "generator_count",
            "value_number": 48,
            "evidence_text": (
                "Operational emissions to air from testing and emergency use from "
                "the 48 standby generators were considered. ... Table 8.4 of the "
                "ES describes the stack characteristics for the 48 diesel "
                "generators proposed."
            ),
            "evidence_page": 91,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "fuel_type",
            "value_text": "diesel standby generators",
            "evidence_text": (
                "Table 8.4 of the ES describes the stack characteristics for the "
                "48 diesel generators proposed."
            ),
            "evidence_page": 91,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "standby_generator_regime",
            "value_text": (
                "phased deployment: 12 generators online 2027, 24 in 2028, 36 in "
                "2029, 48 from 2030 — Air Quality Neutral offsetting payment of "
                "£91,228 calculated against these excess emissions, with "
                "additional offsetting required from 2031 onwards"
            ),
            "evidence_text": (
                "Air quality offsetting payment of £91,228 based on excess "
                "emissions from 12 generators in 2027, 24 in 2028, 36 in 2029 and "
                "48 in 2030. Additional offsetting payments would be calculated "
                "in line with the guidance if the generators are kept from 2031."
            ),
            "evidence_page": 7,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "s106_carbon_offset",
            "value_text": (
                "Carbon Offset Contribution: £95/tonne CO₂ × 30 years = £2,670,452 "
                "(+RPI) — payment to make the development 'the equivalent of zero "
                "carbon'"
            ),
            "evidence_text": (
                "Carbon Offset Contribution payable at a rate of £95 per tonne "
                "over 30 years to make the development the equivalent of zero "
                "carbon (payable on implementation of the development). This "
                "equates to £2,670,452 +RPI"
            ),
            "evidence_page": 7,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "s106_other_contributions",
            "value_text": (
                "Newham Data Education Programme £4,080,000; Newham Digital "
                "Connectivity Strategy £1,625,000; Employment & Skills (35% "
                "construction + 50% end-user jobs to Newham residents) "
                "£1,224,081; TfL contributions £670,000; LBN Transport £1.2M+ "
                "incl. £1M towards Mayer Parry Bridge"
            ),
            "evidence_text": (
                "A financial contribution of £4,080,000 to the Council's Data "
                "Education Programme. ... A financial contribution of £1.625 "
                "million towards the delivery of Newham Digital Connectivity "
                "Strategy. ... Commitment to providing 35% construction jobs "
                "and 50% end user jobs to residents of the LBN through a "
                "financial contribution of £1,224,081."
            ),
            "evidence_page": 6,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "district_heating_readiness",
            "value_text": (
                "s106 requires space + plant readiness for future export of waste "
                "heat to a DHN; explicitly named neighbouring 'Crown Wharf' site "
                "as a potential recipient; no operator yet in place"
            ),
            "evidence_text": (
                "Delivery of space within the Site for the future installation "
                "of the necessary plant and equipment to facilitate the export "
                "of waste heat from the Data Centre offsite, including to the "
                "Crown Wharf site, if a DHN becomes available and where a DHN "
                "operator is in place to facilitate the delivery of waste heat "
                "from the Development"
            ),
            "evidence_page": 7,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "conditions_generator_specific",
            "value_text": (
                "Newham SDC imposed 6 separate generator conditions (cond. 34-39: "
                "type/performance, operating regime, emission monitoring, "
                "emission reduction, testing regime, specifications) — unusually "
                "granular regulatory attention to the back-up combustion plant"
            ),
            "evidence_text": (
                "34. Emergency Back Up Generators – type and performance "
                "35. Emergency Back Up Generators – Operating Regime "
                "36. Emergency Back Up Generators – Emission Monitoring "
                "37. Emergency Back Up Generators – Emission Reduction and Management "
                "38. Emergency Back Up Generators – Testing Regime "
                "39. Emergency Back Up Generators - Specifications"
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "b1becf37",
            "signal_type": "car_free_agreement",
            "value_text": (
                "'Car Free' s106 obligation — businesses/occupiers of the "
                "development precluded from issuing business parking permits in "
                "the Canning Town CPZ"
            ),
            "evidence_text": (
                "Enter in to a 'Car Free' agreement with Newham council which "
                "precludes businesses / occupiers of the development from being "
                "issued with business parking permits in the Canning Town CPZ "
                "pursuant to section 16 of the Greater London Council (General "
                "Powers) Act 1974"
            ),
            "evidence_page": 6,
        },
    ],
    # =====================================================================
    # Meld Energy Green Hydrogen Hub at Saltend Chemicals Park —
    # `EastRiding/24/00012/STOUT`. Same Humber corridor as YEP but
    # different developer (Meld Energy Ltd, agent Matz Ltd) and
    # different site (Reedmere site, south of Saltend Chemicals Park).
    # 100 MW green-hydrogen-by-electrolysis production hub, doubling
    # planned. Editorial significance: while the data-centre worklist
    # apps name hydrogen as an aspirational future fuel, this is
    # nearby actual hydrogen production capacity coming online — a
    # data point for whether the "hydrogen transition" pitches are
    # plausible at scale.
    # =====================================================================
    "EastRiding/24/00012/STOUT": [
        {
            "doc_sha_prefix": "86ffbbd2",  # Planning Statement (with header line)
            "signal_type": "applicant_name",
            "value_text": (
                "Meld Energy Ltd (MEL) — agent: Matz Ltd; Planning Statement dated "
                "November 2023"
            ),
            "evidence_text": (
                "Meld Energy Planning Statement Matz Ltd November 2023 "
                "... This Planning Statement has been prepared on behalf of "
                "Meld Energy Ltd (MEL) in support of an outline planning "
                "application submitted to East Riding of Yorkshire Council (LPA)"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "276930f8",
            "signal_type": "facility_classification",
            "value_text": (
                "100 MW Green Hydrogen production hub by electrolysis (renewable-"
                "powered), to supply existing Saltend Chemicals Park partners as "
                "renewable fuel/product; doubling capacity planned in the future"
            ),
            "evidence_text": (
                "The MEL Hydrogen hub will produce up to 100 MW of Green "
                "Hydrogen, which will be used by existing SCP partners as a "
                "renewable fuel or product"
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "449deddd",  # Drainage Impact Assessment (Matz Ltd, Nov 2023)
            "signal_type": "site_location",
            "value_text": (
                "Reedmere site, south side of Saltend Chemicals Park (SCP), "
                "Saltend Lane, Saltend, East Riding of Yorkshire HU12 8DS — "
                "same Humber estuary industrial corridor as the Yorkshire "
                "Energy Park (HU12 8DX) and AMP gas reserve"
            ),
            "evidence_text": (
                "The first MEL production hub is to be located on the South side of "
                "the Reedmere site and will produce up to 100MW of Green Hydrogen, "
                "which will be used by existing SCP partners."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "c19a9467",  # Air Quality Assessment (longer doc)
            "signal_type": "nearby_development",
            "value_text": (
                "neighbouring approved Nu-Energy Ltd 20 MW Waste-to-Energy "
                "Facility at the same Saltend cluster — air quality modelling "
                "covered both facilities"
            ),
            "evidence_text": (
                "Nu-Energy Ltd 20MW Waste to Energy Facility: A power "
                "generation facility on land and building Approved "
                "... The Air Quality Assessment modelled the predicted "
                "emissions levels at four receptors on the Humber Estuary"
            ),
            "evidence_page": 23,
        },
    ],
    # =====================================================================
    # CHEP UK pallet biomass kiln, Thurrock — `Thurrock/20/00569/FUL`.
    # Worklist false-positive: triage caught "biomass boiler" as Tier-1
    # signal, but the application is a heat-treatment kiln for shipping
    # pallets at CHEP UK's Hangmans Wood Industrial Park (CHEP is the
    # global pallet pooling operator). Not a DC. Editorially useful as a
    # null finding — distinguishes pallet manufacturing biomass from
    # DC-relevant on-site combustion.
    # =====================================================================
    "Thurrock/20/00569/FUL": [
        {
            "doc_sha_prefix": "87354ccf",
            "signal_type": "facility_classification",
            "value_text": (
                "pallet heat-treatment kiln + biomass boiler at CHEP UK Ltd, "
                "Stifford Rd, Aveley, South Ockendon RM15 4AA (global pallet "
                "pooling operator) — NOT a data centre; worklist false-"
                "positive caught by the 'biomass boiler' Tier-1 signal in the "
                "description"
            ),
            "evidence_text": (
                "Property name CHEP UK Ltd Address line 1 Stifford Rd Address "
                "line 2 Aveley ... Town/city South Ockendon Postcode RM15 4AA "
                "... Installation of a heat treatment kiln and biomass boiler"
            ),
            "evidence_page": 1,
        },
    ],
    # =====================================================================
    # Thurrock Lakeside DC — `Thurrock/25/00573/OUT`. Global
    # Infrastructure UK Ltd's hyperscale at the former Arena Essex
    # Raceway, adjacent to Lakeside Shopping Centre. 4 DC buildings
    # = 130,500 sqm GEA, 94 × 2.75 MW diesel back-up generators
    # (~258 MW backup capacity). Hybrid planning application (full +
    # outline).
    # =====================================================================
    "Thurrock/25/00573/OUT": [
        {
            "doc_sha_prefix": "6cd1f865",
            "signal_type": "applicant_name",
            "value_text": (
                "Global Infrastructure UK Ltd (likely a Global Infrastructure "
                "Partners-affiliated entity); agent Iceni Projects Ltd; ES Air "
                "Quality chapter by Environmental Resources Management (ERM)"
            ),
            "evidence_text": (
                "This chapter of the Environmental Statement (ES) has been "
                "prepared by Environmental Resources Management Ltd "
                "(hereafter referred to as 'ERM') "
                "... ERM on behalf of Global Infrastructure UK Ltd April 2025 "
                "Iceni Projects Ltd. Da Vinci House, 44 Saffron Hill, London, "
                "ECN1 8FH"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "6cd1f865",
            "signal_type": "facility_classification",
            "value_text": (
                "hyperscale data-centre campus on the former Arena Essex Raceway, "
                "adjacent to Lakeside Shopping Centre — up to 4 DC buildings, "
                "130,500 sqm GEA (excluding external plant) + 4,000 sqm office; "
                "M25 west, A13 south"
            ),
            "evidence_text": (
                "The Site is located at the former Arena Essex Raceway, Land "
                "to the north of Arterial Road West Thurrock, Essex RM19 1AE, "
                "within a predominantly mixed-use area that features "
                "industrial, residential, and commercial land uses"
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "6cd1f865",
            "signal_type": "generator_count",
            "value_number": 94,
            "evidence_text": (
                "94 diesel backup generators are proposed to be installed at the "
                "Site to provide emergency power in the event of a grid supply "
                "failure."
            ),
            "evidence_page": 13,
        },
        {
            "doc_sha_prefix": "6cd1f865",
            "signal_type": "engine_rated_mw",
            "value_number": 2.75,
            "value_unit": "MW",
            "evidence_text": (
                "Table 4.4 Modelled Emissions Parameters Engine Parameter a, b "
                "100% load 30% load c 10% load Engine Rating 2.75 MW Number of "
                "generators 94 Stack Orientation Vertical Stack Height above "
                "ground level (m) 26.0 Flue Diameter (m) 0.5"
            ),
            "evidence_page": 16,
        },
        {
            "doc_sha_prefix": "95485b37",  # applicant statement / corporate context doc
            "signal_type": "renewable_supply_commitment",
            "value_text": (
                "12-year 100 MW corporate Power Purchase Agreement with Scotland's "
                "Moray West offshore wind project (announced 2022) — actual "
                "contracted renewable supply, not just an aspirational hydrogen "
                "transition"
            ),
            "evidence_text": (
                "For example, in 2022 we announced a 12-year 100 MW corporate "
                "power purchase agreement to support Scotland's Moray West "
                "offshore wind development project."
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "6cd1f865",
            "signal_type": "eia_screening_outcome",
            "value_text": (
                "EIA Scoping Opinion issued by Thurrock Council 16 October 2024 — "
                "the application proceeded WITH an Environmental Statement (vs "
                "the no-EIA outcomes seen at Elsham Tech Park and Basildon "
                "Wickford)"
            ),
            "evidence_text": (
                "An Environmental Impact Assessment (EIA) scoping report was "
                "prepared and submitted to Thurrock Council in August 2024. An "
                "EIA Scoping Opinion was subsequently issued by Thurrock Council "
                "on 16th October 2024."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "6cd1f865",
            "signal_type": "standby_generator_regime",
            "value_text": (
                "94 generators tested monthly + bi-annually; groups of max 3 "
                "generators per test, 30 min each; modelled scenario assumes all "
                "94 operate at 100% over 24h for the worst-case grid-failure "
                "emergency"
            ),
            "evidence_text": (
                "Maintenance 1 Monthly, 11 times per year 30 minutes per "
                "generator group Groups of generators are tested (maximum three "
                "generators), one group after the other (maximum 8-10 generators "
                "tested per...) ... All 94 generators at the Site will operate "
                "in any one 24-hour period; and The generators operate on a "
                "maximum load of 100%."
            ),
            "evidence_page": 3,
        },
    ],
    # =====================================================================
    # Saltend hybrid gas + BESS facility — `EastRiding/17/03771/STPLF`.
    # Yet another Humber-estuary energy-cluster entry: 49 MW hybrid
    # natural-gas + battery-storage facility. Different to the
    # gas-only STPLF (16/02800) and the YEP DC+CHP (22/00301/STREME) —
    # this is the gas+BESS combination, which is the
    # frequency-response / grid-services pattern. Same Saltend
    # industrial cluster (HU12 8PP, near YEP's HU12 8DX).
    # =====================================================================
    "EastRiding/17/03771/STPLF": [
        {
            "doc_sha_prefix": "313ee329",  # Air Quality Assessment
            "signal_type": "facility_classification",
            "value_text": (
                "49 MW hybrid natural-gas + battery-energy-storage facility — "
                "11 GE Jenbacher 624 gas engines (4.5 MW each, 49 MW total "
                "electrical output) + 25 × 2 MW battery storage units; on "
                "Saltend Lane, Preston, East Riding (same industrial cluster "
                "as the YEP DC and Meld Energy hydrogen hub)"
            ),
            "evidence_text": (
                "AMP have developed draft proposals for a hybrid energy project "
                "combining natural gas generation and battery storage units. "
                "The proposed development will consist of 11 General Electric "
                "Jenbacher 624 natural gas engines (each engine has up to "
                "4.5MW electrical output, however, the installed engines will "
                "generate no more than 4 9MW electrical output in total) with "
                "a rated thermal input of 132MW and 25 x 2MW energy storage units"
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "313ee329",
            "signal_type": "total_capacity_mw",
            "value_number": 49,
            "value_unit": "MW",
            "evidence_text": (
                "the installed engines will generate no more than 4 9MW "
                "electrical output in total"
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "c17a3b2c",  # EA consultation technical note
            "signal_type": "site_cluster_pattern",
            "value_text": (
                "Humber Estuary / Saltend energy-infrastructure cluster: this "
                "49 MW gas+BESS hybrid joins (a) the 21 MW AMP gas reserve at "
                "STPLF 16/02800 (2016); (b) the YEP DC + gas CHP energy centre "
                "at 22/00301/STREME (2022); (c) Meld Energy's 100 MW green "
                "hydrogen hub at Reedmere/Saltend (24/00012/STOUT, 2024). "
                "All within ~2 km of each other on the same industrial estate."
            ),
            "evidence_text": (
                "Hybrid Natural Gas Production & Energy Storage Facility at "
                "Salt End, Hull - 17/03771/STPLF"
            ),
            "evidence_page": 1,
        },
    ],
    # =====================================================================
    # East Havering Data Centre Campus LDO scoping — `Havering/Z0001.24`.
    # Editorially MASSIVE and unusual: this is a Council-driven Local
    # Development Order (LDO) scoping exercise rather than a
    # developer-led application. Havering Council itself is promoting
    # the LDO designation via Ramboll UK as their consultant. Scope:
    # up to 400,000 sqm DC + 10 ha BESS + hydrogen fuel cells +
    # indoor horticulture (heat reuse) + district heating + 113 ha
    # min parkland — on Land North of Fen Lane, North Ockendon.
    # =====================================================================
    "Havering/Z0001.24": [
        {
            "doc_sha_prefix": "ae7267ef",  # LDO Scoping Opinion
            "signal_type": "facility_classification",
            "value_text": (
                "East Havering Data Centre Campus — Council-led Local Development "
                "Order (LDO) scoping exercise (NOT a typical developer-led "
                "application); Ramboll UK produced the scoping report on behalf "
                "of London Borough of Havering as Local Planning Authority"
            ),
            "evidence_text": (
                "This Scoping Opinion has been prepared on the basis of the "
                "information contained within the document titled 'East Havering "
                "Data Campus – EIA Scoping Opinion Request Report' dated February "
                "2024 (Project no. 1620016267) – 'the Scoping Report'. The "
                "document was produced by Ramboll UK on behalf of the London "
                "Borough of Havering as Local Planning Authority."
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "total_floorspace_sqm",
            "value_number": 400000,
            "value_unit": "sqm (max)",
            "evidence_text": (
                "New data centre campus (East Havering Data Centre Campus) of "
                "between 279,400sq.m and 400,000sq.m of floorspace plus up to "
                "10ha of battery storage."
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "facility_components",
            "value_text": (
                "data centre floorspace 250,000-340,000 sqm + indoor horticulture "
                "26,000-60,000 sqm + hydrogen fuel cell energy generation up to "
                "6,000 sqm + district heating energy centre 200-2,800 sqm + "
                "visitor centre 200-600 sqm + electrical substations 3,000-20,000 "
                "sqm + min 113 ha parkland/biodiversity habitat"
            ),
            "evidence_text": (
                "the campus will comprise between 250,000sq.m. and 340,000sq.m. "
                "of data centre floorspace and associated external plant and "
                "security, between 26,000sq.m and 60.000sq.m of indoor "
                "horticulture facilities, green energy initiative "
                "... a district heating energy centre (between 200sq.m and "
                "2,800sq.m)), a visitor centre (between 200sq.m and 600sq.m) "
                "and electrical substations and distribution infrastructure "
                "(between 3,000sq.m and 20,000sq.m), civil engineering "
                "... works, hard and soft landscaping, formation of "
                "associated parkland/enhanced biodiversity habitat (minimum "
                "113ha) at North Ockendon, Havering, Greater London"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "hydrogen_capacity_sqm",
            "value_number": 6000,
            "value_unit": "sqm (max hydrogen fuel cell area)",
            "evidence_text": (
                "green energy initiative (including up to 6,000sq.m of hydrogen"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "battery_storage_hectares",
            "value_number": 10,
            "value_unit": "hectares (max BESS area)",
            "evidence_text": (
                "between 279,400sq.m and 400,000sq.m of floorspace plus up to "
                "10ha of battery storage"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "planning_route",
            "value_text": (
                "Local Development Order (LDO) — a fast-tracked planning route "
                "designated by a local authority that pre-approves development "
                "for a specific area, bypassing the usual planning-application "
                "process. Havering Council promoting itself as the LDO sponsor "
                "is editorially noteworthy (Council-led DC promotion vs typical "
                "developer-led application)."
            ),
            "evidence_text": (
                "RE: SCOPING OPINION PURSUANT TO PART 7 REGULATION 32(6) OF THE "
                "TOWN AND COUNTRY PLANNING (ENVIRONMENTAL IMPACT ASSESSMENT) "
                "REGULATIONS 2017 (AS AMENDED) FOR DEVELOPMENT PROPOSED TO BE "
                "PERMITTED BY THE EAST HAVERING DATA CENTRE CAMPUS LOCAL "
                "DEVELOPMENT ORDER (LDO) ON LAND NORTH OF FEN LANE, NORTH "
                "OCKENDON, UPMINSTER"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "consultant",
            "value_text": (
                "Ramboll UK (Ben Seward) — based at 240 Blackfriars Road, "
                "London SE1 8NW, which is a multi-tenant coworking office "
                "building (no inferred relationship with other dataset apps "
                "that share the address)"
            ),
            "evidence_text": "Ben Seward Ramboll 240 Blackfriars Road London SE1 8NW",
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "ae7267ef",
            "signal_type": "aqma_proximity",
            "value_text": (
                "Havering has declared an AQMA for annual mean NO₂ exceedances "
                "and daily mean PM10 — the Council has agreed the AQ chapter "
                "scope and notably accepted that 'impacts from combustion based "
                "heating and hot water plant can be scoped out as this type of "
                "equipment is not proposed within the development'"
            ),
            "evidence_text": (
                "Havering has been declared an Air Quality Management Area "
                "(AQMA) for exceedances of the annual mean nitrogen dioxide "
                "objective and daily mean (PM10) National Air Quality Strategy "
                "Objective ... that impacts from combustion based heating and "
                "hot water plant can be scoped out as this type of equipment "
                "is not proposed within the development"
            ),
            "evidence_page": 5,
        },
    ],
    # =====================================================================
    # Longcross DC campus Phase 3 Reserved Matters —
    # `Runnymede/RU.21/0780`. The substantive parent of the 4 worklist
    # consultation copies (Windsor, SurreyHeath ×2, Runnymede-internal).
    # Granted by Runnymede BC on 4 November 2021. At Upper Longcross,
    # Chobham Lane (former DERA / Defence Evaluation and Research Agency
    # site, hence "Longcross North"). Same consultant signature as Ark
    # Project Union: Hurley Palmer Flatt (M&E energy statement) +
    # Phlorum (AQA) + Auricl (acoustic).
    # =====================================================================
    "Runnymede/RU.21/0780": [
        {
            "doc_sha_prefix": "42c86f80",  # Decision Notice
            "signal_type": "decision_outcome",
            "value_text": (
                "GRANT PERMISSION subject to conditions — Runnymede Borough "
                "Council, 4 November 2021; signed Ashley Smith (Corporate Head "
                "of Development Management & Building Control)"
            ),
            "evidence_text": (
                "Decision Notice: GRANT PERMISSION (subject to conditions) "
                "... Signed: Date of decision: Ashley Smith 04 November 2021 "
                "Ashley Smith Corporate Head of Development Management & "
                "Building Control"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "42c86f80",
            "signal_type": "agent_name",
            "value_text": "Savills (Cardiff office: 2 Kingsway, CF10 3FD)",
            "evidence_text": "Savills 2 Kingsway Cardiff CF10 3FD",
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "42c86f80",
            "signal_type": "facility_classification",
            "value_text": (
                "Phase 3 Reserved Matters DC campus on the former DERA "
                "(Defence Evaluation and Research Agency) site at Longcross "
                "North — components: data centre building(s) + cooling + "
                "office + roof-mounted PV cells; Energy Centre Building; "
                "Stand-By Generators and fuel storage; HV Sub-Station; "
                "visitor reception centre"
            ),
            "evidence_text": (
                "Phase 3 Reserved Matters application for the development of a "
                "data centre campus comprising: a) A building(s) for data "
                "storage and processing, associated cooling infrastructure, "
                "ancillary office and technical space and roof mounted PV "
                "cells; b) Energy Centre Building; c) Stand-By Generators and "
                "fuel storage; d) HV Sub-Station; e) visitor reception centre; "
                "... The application forms part of phase 3 of planning "
                "permission RU.13/0856 (as revised under RU.16/0584)"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "42c86f80",
            "signal_type": "consultant_signature",
            "value_text": (
                "Hurley Palmer Flatt (Energy Statement, Ref WED16285, Dec 2020 "
                "Issue 3) + Phlorum (Air Quality Assessment) + Auricl "
                "acoustic consulting (Plant Noise, 20 August 2021) — SAME "
                "consultant trio as Ark's Project Union at Bulls Bridge "
                "(Hillingdon/75111/APP/2020/1955). Editorially significant "
                "operator-network signature visible across multiple major "
                "UK hyperscale projects."
            ),
            "evidence_text": (
                "And the following supporting Documents: ... Plant Noise "
                "Assessment Report by Auricl acoustic consulting dated 20 "
                "August 2021 ... Energy Statement by Hurley Palmer Flatt "
                "Issue 3 Ref WED16285 Dec 2020 ... Air Quality Assessment by "
                "Phlorum ..."
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "42c86f80",
            "signal_type": "parent_permission",
            "value_text": (
                "RU.13/0856 (the hybrid permission for demolition + "
                "redevelopment of the Longcross North former DERA site), as "
                "revised under RU.16/0584 and RU.20/0729. This Phase 3 RMA "
                "is one phase of a larger mixed-use master plan."
            ),
            "evidence_text": (
                "The application forms part of phase 3 of planning permission "
                "RU.13/0856 (as revised under RU.16/0584) (Hybrid planning "
                "permission for the demolition of existing buildings and "
                "redevelopment of the Longcross North site)"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "42c86f80",
            "signal_type": "site_history",
            "value_text": (
                "former DERA (Defence Evaluation and Research Agency) site at "
                "Upper Longcross, Chobham Lane, Longcross KT16 0EE — military "
                "research base since demolished, being redeveloped under the "
                "Longcross North hybrid mixed-use master plan"
            ),
            "evidence_text": (
                "Upper Longcross, Chobham Lane, Longcross, KT16 0EE ... "
                "Hybrid planning permission for the demolition of existing "
                "buildings and redevelopment of the Longcross North site"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "42c86f80",
            "signal_type": "ev_charging_provision",
            "value_text": (
                "15 car parking spaces required to have fast-charge sockets "
                "(7 kW Mode 3 Type 2, 230V AC 32A single-phase dedicated "
                "supply) — condition 12"
            ),
            "evidence_text": (
                "Electric vehicle charging The development hereby approved "
                "shall not be occupied unless and until 15 of the proposed "
                "car parking spaces is provided with a fast charge socket "
                "(current minimum requirements - 7 kw Mode 3 with Type 2 "
                "connector - 230v AC 32 Amp single phase dedicated supply)"
            ),
            "evidence_page": 5,
        },
    ],
    # =====================================================================
    # TeleData expansion to Simon House, Manchester —
    # `Manchester/132638/FO/2022`. Small colocation operator
    # expanding into an adjacent vacant building (Simon House) next to
    # their existing Delta House site. Use Class change from E1 to
    # Sui Generis (DC + offices). Includes a FUEL CELL (Tier-1
    # signal) alongside conventional generator + transformer +
    # substation. Approved 25 April 2022.
    # =====================================================================
    "Manchester/132638/FO/2022": [
        {
            "doc_sha_prefix": "01c5b41b",
            "signal_type": "applicant_name",
            "value_text": (
                "TeleData (Mr Matt Edgley) — agent: Alpine Planning Ltd (Mr A Jelley, "
                "The Buttery, Tithe Farm, Holcot, NN6 9SH); case officer David Lawless "
                "at Manchester City Council"
            ),
            "evidence_text": (
                "Applicant: Mr Matt Edgley, Teledata Simon House, Brownley Road, "
                "Manchester, M22 5RA Agent (if any): Mr A Jelley, Alpine Planning "
                "Ltd, The Buttery, Tithe Farm, Holcot, NN6 9SH"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "01c5b41b",
            "signal_type": "facility_classification",
            "value_text": (
                "TeleData colocation campus expansion — Use Class E1 → Sui Generis "
                "(DC + offices); ground floor of Simon House becomes data centre, "
                "first floor remains offices. Adjacent to TeleData's existing Delta "
                "House operation (campus-style expansion). New kit: substation in "
                "GRP hut + electrical transformer + FUEL CELL + air condensing "
                "units (roof) + emergency generator."
            ),
            "evidence_text": (
                "The applicant is proposing to change the use of the property to a "
                "data centre and offices, in connection with their existing operation "
                "at Delta House – the ground floor would be converted into the data "
                "centre, while the first floor would remain in use as offices. ... "
                "the application is proposing to install the following at the rear "
                "and side of the site.: new substation within GRP hut, electrical "
                "transformer, fuel cell, air condensing units (roof top mounted) and "
                "emergency generator"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "01c5b41b",
            "signal_type": "decision_outcome",
            "value_text": "APPROVED — Manchester City Council Delegated Officer, 25 April 2022",
            "evidence_text": "Recommendation: Approve Date of recommendation: 25 April 2022",
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "01c5b41b",
            "signal_type": "local_objection",
            "value_text": (
                "1 letter of objection (1 letter of support) — neighbour cites "
                "TeleData as 'a constant nuisance neighbour since 2019' with noise "
                "from existing 48 air-conditioning units at Delta House, "
                "transformer noise requiring intervention by Environmental Health, "
                "and concern about cumulative impact of the Simon House expansion"
            ),
            "evidence_text": (
                "One letter of objection has been received... Teledata (based at "
                "Delta House) have been a constant nuisance neighbour since 2019. "
                "I have had to involved Environmental Health (Sue Jones) on "
                "numerous occasions about noise levels. ... I then had noise "
                "issues concerning the 48 air-conditioning units based at Delta "
                "House."
            ),
            "evidence_page": 3,
        },
    ],
    # =====================================================================
    # Milton Keynes Energy Network — `MiltonKeynes/PLN/2024/2768`. A
    # major heat-network-anchored scheme: an Energy Centre + a Data
    # Centre + a 13.7 km piped distribution network connecting to
    # multiple civic/institutional buildings as heat customers. Same
    # Ramboll UK consultant signature as East Havering LDO. EIA
    # screening request dated December 2024 — the only confirmed
    # real-deployment of the DC-anchored DHN model in our dataset.
    # =====================================================================
    "MiltonKeynes/PLN/2024/2768": [
        {
            "doc_sha_prefix": "4dc4412e",
            "signal_type": "applicant_name",
            "value_text": (
                "Milton Keynes Energy Limited — consultant: Ramboll UK Ltd "
                "(Alex Kerr / Michelle Wheeler, project no. 1620016640)"
            ),
            "evidence_text": (
                "On behalf of Milton Keynes Energy Limited ... This report has "
                "been produced by Ramboll UK Ltd ('Ramboll') on behalf of Milton "
                "Keynes Energy Limited (the 'Applicant'), pursuant to Regulation "
                "6(1) of The Town and Country Planning (Environmental Impact "
                "Assessment) Regulations 2017"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "4dc4412e",
            "signal_type": "facility_classification",
            "value_text": (
                "Energy Centre + Data Centre + 13.7 km piped distribution network "
                "('Milton Keynes Energy Network'). EC components: several thermal "
                "stores, evaporator platform, generator building, 11 kV "
                "substation, gas kiosk, two heat-exchange buildings, FIVE BOILER "
                "FLUES. DC components: generator building, 11 kV substation. "
                "Pipe network connects EC to: MK Civic Buildings, MK University "
                "Hospital, MK Open University Campus, Thames Valley Police, "
                "MK Library, Woughton Leisure Centre."
            ),
            "evidence_text": (
                "The proposed development would comprise: an energy centre ('EC') "
                "and associated structures (several thermal stores, an evaporator "
                "platform, a generator building, 11kV substation, a gas kiosk, "
                "two heat exchange buildings and five boiler flues); a data "
                "centre ('DC') and associated structures (a generator building "
                "and 11kV substation); and an associated piped distribution "
                "network, or pipe network ('PN'), which would cover a total "
                "distance of approximately 13.7 km. The PN would be installed "
                "across a single development phase, which would connect the EC "
                "with Milton Keynes City Centre's Civic Buildings, the Milton "
                "Keynes University Hospital ('MKUH') and the Milton Keynes Open "
                "University Campus ('MKOUC'), Thames Valley Police, the Milton "
                "Keynes Library and the Woughton Leisure Centre."
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "4dc4412e",
            "signal_type": "heat_network_anchors",
            "value_text": (
                "6 named civic / institutional heat customers connected via the "
                "13.7 km pipe network: MK Civic Buildings, MK University "
                "Hospital, MK Open University Campus, Thames Valley Police, MK "
                "Library, Woughton Leisure Centre. Only confirmed "
                "DC-heat-anchor DHN deployment in the worklist (Newham Bidder "
                "Street and Hillingdon Union Park have DH provisions but no "
                "operator / no real network)."
            ),
            "evidence_text": (
                "an associated piped distribution network, or pipe network "
                "('PN'), which would cover a total distance of approximately "
                "13.7 km. The PN would be installed across a single development "
                "phase, which would connect the EC with Milton Keynes City "
                "Centre's Civic Buildings, the Milton Keynes University "
                "Hospital ('MKUH') and the Milton Keynes Open University "
                "Campus ('MKOUC'), Thames Valley Police, the Milton Keynes "
                "Library and the Woughton Leisure Centre"
            ),
            "evidence_page": 4,
        },
        {
            "doc_sha_prefix": "4dc4412e",
            "signal_type": "consultant_signature",
            "value_text": (
                "Ramboll UK — same firm that produced the East Havering DC "
                "Campus LDO scoping report (Havering/Z0001.24). Ramboll appears "
                "to be specialising in council- / utility-led DC schemes where "
                "DC waste-heat reuse is the core editorial pitch (vs the "
                "developer-led hyperscale apps elsewhere in the worklist)."
            ),
            "evidence_text": (
                "This report has been produced by Ramboll UK Ltd ('Ramboll') on "
                "behalf of Milton Keynes Energy Limited"
            ),
            "evidence_page": 4,
        },
    ],
    # =====================================================================
    # Langley Business Centre Slough DC (Bucks consultation copy) —
    # `ChilternSouthBucks/PL/20/2041/ADJ`. The substantive app is
    # Slough/P/00437/093 (rank 80, on Agile portal we can't fetch).
    # Two consultation-response docs from the Bucks side ingested
    # manually. Both apps now tagged as duplicates.
    # =====================================================================
    "ChilternSouthBucks/PL/20/2041/ADJ": [
        {
            "doc_sha_prefix": "0f473a7f",
            "signal_type": "cross_borough_notice",
            "value_text": (
                "Slough Borough Council Reg-25-EIA cross-borough notice (29 June "
                "2020) to South Bucks District Council planning department, "
                "Capswood, Denham re Slough's P/00437/093 at Langley Business "
                "Centre. Case officer: Alistair De Joux. An Environmental "
                "Statement Addendum was issued under EIA Reg 25 (further "
                "information requested by the LPA)."
            ),
            "evidence_text": (
                "In accordance with The Town and Country Planning "
                "(Environmental Impact Assessment) Regulations 2017 (the EIA "
                "Regulations), I give notice that further information has been "
                "provided in accordance with EIA Regulation 25, in the form of "
                "an Addendum which now forms part of the Environmental "
                "Statement submitted in respect of the above planning application"
            ),
            "evidence_page": 2,
        },
        {
            "doc_sha_prefix": "0f473a7f",
            "signal_type": "facility_classification",
            "value_text": (
                "outline DC of up to 93,000 sqm gross at Langley Business Centre, "
                "Station Road, Slough SL3 8DS — plot (B) = DC + ancillary offices "
                "+ substation; plot (A) up to 9,650 sqm GEA = mixed-use (up to 60 "
                "dwellings + retail/A1-A5 + ENERGY CENTRE). Substantive permission "
                "sits at Slough/P/00437/093 (Agile portal, not yet adaptered)."
            ),
            "evidence_text": (
                "Outline planning permission with the details of access, "
                "appearance, landscaping, layout and scale reserved for later "
                "determination. Demolition and redevelopment to comprise on plot "
                "(B) a data centre of up to 93,000 sqm gross, including ancillary "
                "offices and sub station; and plot (A) up to 9,650 sqm GEA to "
                "comprise one or more land uses comprising: up to 60 dwellings "
                "(Use Class C3); additional development in Use Classes: A1, A2, "
                "A3 (retail), A4 (public house), A5 (take away) and an energy "
                "centre."
            ),
            "evidence_page": 1,
        },
    ],
    # =====================================================================
    # Southall Waste Depot BESS — `Hounslow/P/2017/4684`. Condition
    # discharge for a battery-storage + generator + PV scheme at a
    # waste depot. NOT a data centre. Worklist false-positive picked
    # up via "battery storage" Tier-4 signal + "generator" Tier-2 signal.
    # =====================================================================
    "Hounslow/P/2017/4684": [
        {
            "doc_sha_prefix": "dc737f39",
            "signal_type": "facility_classification",
            "value_text": (
                "battery-storage + generator + photovoltaic scheme at a Waste "
                "Depot on Southall Lane (NOT a data centre) — condition-discharge "
                "for boundary treatment + parking of the underlying permission "
                "01032/I/P4 (granted 6 Oct 2017). Includes a 50 sqm control / "
                "electric intake room, 72 sqm pump house, valve & quarantine "
                "areas, sprinkler tanks, and a 2,700 L bunded above-ground "
                "diesel tank. Worklist false-positive picked up by the "
                "'battery storage' + 'generator' signals."
            ),
            "evidence_text": (
                "Works to cover a battery storage facilities/generator "
                "(associated with approved photovoltaic panels). Erection of "
                "50m2 (GEA) control room and electric intake room. Erection "
                "of 72m2 (GEA) Pump House, 22m2 (GEA) Valve House & 115m2 "
                "(GEA) Quarantine Area"
            ),
            "evidence_page": 2,
        },
    ],
    # =====================================================================
    # Langley Business Centre DC (Slough primary) —
    # `Slough/P/00437/093`. The substantive 93,000 sqm / 130 MW DC
    # application that ChilternSouthBucks/PL/20/2041/ADJ +
    # ChilternSouthBucks/PL/20/0646/ADJ are consultation copies of.
    # Documents fetched from www.sbcplanning.co.uk (the older Slough
    # planning portal — the current Agile front-end at
    # planning.agileapplications.co.uk does not surface them).
    # =====================================================================
    "Slough/P/00437/093": [
        {
            "doc_sha_prefix": "2e23b813",  # Volume 3 technical appendices
            "signal_type": "applicant_name",
            "value_text": (
                "Zurich Assurance Ltd, c/o Threadneedle Portfolio Services Ltd "
                "— consultant: Ramboll (a fourth Ramboll-led council / utility "
                "scheme in our dataset, alongside East Havering LDO, Milton "
                "Keynes Energy Network, and Humber Tech Park via Future-tech "
                "for that one)"
            ),
            "evidence_text": (
                "Volume 3: Technical Appendices ... Zurich Assurance Ltd c/o "
                "Threadneedle Portfolio Services Ltd Langley Business Centre "
                "RAMBOLL"
            ),
            "evidence_page": 477,
        },
        {
            "doc_sha_prefix": "338c10bc",
            "signal_type": "total_it_load_mw",
            "value_number": 130,
            "value_unit": "MW",
            "evidence_text": (
                "Load calculations have been completed based on a ratio of 60% "
                "white space 40% plant and ancillary spaces and a value of 130MW "
                "was calculated as a maximum site load."
            ),
            "evidence_page": 9,
        },
        {
            "doc_sha_prefix": "8c22b42e",
            "signal_type": "facility_classification",
            "value_text": (
                "data-centre campus (Plot B, 93,000 sqm, 130 MW max site load) + "
                "mixed-use residential / commercial (Plot A, 9,650 sqm GEA, up "
                "to 60 dwellings + retail + energy centre). 5 MW per data hall "
                "configuration; 26 × 4 MW generator systems in N+1 (104 MW "
                "backup capacity)"
            ),
            "evidence_text": (
                "For the proposed development, we have a load of 100MW, therefore "
                "we need 25 x 4 MW (N) generators to meet the load and one more "
                "as a spare to allow for maintenance which provides 4% additional "
                "capacity. ... On this basis, the generators would be configured "
                "as 26 generator systems each system providing 104 megawatts (MW) "
                "in an N+1 configuration. ... an assumed electrical and cooling "
                "load of 5MW per data hall"
            ),
            "evidence_page": 13,
        },
        {
            "doc_sha_prefix": "8c22b42e",
            "signal_type": "generator_count",
            "value_number": 26,
            "evidence_text": (
                "the generators would be configured as 26 generator systems each "
                "system providing 104 megawatts (MW) in an N+1 configuration"
            ),
            "evidence_page": 13,
        },
        {
            "doc_sha_prefix": "8c22b42e",
            "signal_type": "engine_rated_mw",
            "value_number": 4,
            "value_unit": "MW",
            "evidence_text": (
                "we need 25 x 4 MW (N) generators to meet the load and one more "
                "as a spare to allow for maintenance"
            ),
            "evidence_page": 11,
        },
        {
            "doc_sha_prefix": "8c22b42e",
            "signal_type": "fuel_storage_litres",
            "value_number": 260000,
            "value_unit": "litres diesel (12 h runtime)",
            "evidence_text": (
                "Up to 260,000 litres of diesel fuel would be stored on site (to "
                "provide up to 12 hours of fuel)."
            ),
            "evidence_page": 13,
        },
        {
            "doc_sha_prefix": "338c10bc",
            "signal_type": "grid_connection",
            "value_text": (
                "DNO is SSE; initial payment received 2 October 2019 to reserve "
                "the required power supply (per Ramboll's Energy Statement). "
                "Substation size and supply voltage submitted as part of the "
                "DNO application."
            ),
            "evidence_text": (
                "The size of the substation and the supply voltage were also "
                "requested. 4.2 DNO – SSE Application & Payment Confirmation was "
                "received from SSE on 2/10/2019 of receipt of initial payment to "
                "reserve the required power supply"
            ),
            "evidence_page": 9,
        },
    ],
    # =====================================================================
    # Slough Manor Farm DC + BESS — `Slough/P/10076/013`. 50 MW DC +
    # 114 MW BESS + 47 diesel generators at Manor Farm / north of
    # Wraysbury Reservoir, Slough (near Heathrow). Docs from
    # sbcplanning.co.uk (older Slough planning portal, not Agile).
    # =====================================================================
    "Slough/P/10076/013": [
        {
            "doc_sha_prefix": "3fbab67b",
            "signal_type": "facility_classification",
            "value_text": (
                "50 MW data centre (41,061 sqm GIA) + 114 MW battery energy "
                "storage system + 47 diesel emergency generators + substation, "
                "on land at Manor Farm and north of Wraysbury Reservoir, "
                "Slough — Slough Availability Zone (UK DC market hub near "
                "Heathrow)"
            ),
            "evidence_text": (
                "The planning application comprises a 50MW Data Centre, Guard "
                "House, internal access routes and associated parking, a "
                "Substation and BESS. ... 41,061.49 sqm Gross Internal Area "
                "(GIA) 50MW Data Centre ... This is set out in further detail "
                "below, based on an approved 114mw battery storage scheme."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "3fbab67b",
            "signal_type": "total_it_load_mw",
            "value_number": 50,
            "value_unit": "MW",
            "evidence_text": "41,061.49 sqm Gross Internal Area (GIA) 50MW Data Centre",
            "evidence_page": 28,
        },
        {
            "doc_sha_prefix": "3fbab67b",
            "signal_type": "battery_storage_mw",
            "value_number": 114,
            "value_unit": "MW",
            "evidence_text": (
                "This is set out in further detail below, based on an approved "
                "114mw battery storage scheme. ... This is based on a 114MW "
                "Battery Storage site."
            ),
            "evidence_page": 45,
        },
        {
            "doc_sha_prefix": "7c2475be",
            "signal_type": "generator_count",
            "value_number": 47,
            "evidence_text": (
                "The proposed development will have 47 emergency diesel "
                "generators to power the data centre in the event of major "
                "grid failure."
            ),
            "evidence_page": 54,
        },
        {
            "doc_sha_prefix": "7c2475be",
            "signal_type": "fuel_type",
            "value_text": "diesel emergency generators (with associated fuel storage)",
            "evidence_text": (
                "The proposed development will have 47 emergency diesel "
                "generators to power the data centre in the event of major "
                "grid failure."
            ),
            "evidence_page": 54,
        },
        {
            "doc_sha_prefix": "e0d5621b",
            "signal_type": "market_context",
            "value_text": (
                "UK DC market has c. 2,190 MW of capacity (£7.5bn turnover); "
                "Slough's Availability Zone (AZ) has 379.23 MW of DC capacity "
                "— a major UK DC hub, primarily serving the West London cloud "
                "providers"
            ),
            "evidence_text": (
                "The UK Data Centre market has c. 2,190 Mega Watts (MW) of "
                "capacity (£7.5bn turnover "
                "... A significant proportion of demand is focused on the West "
                "London market, on the basis that this is within the "
                "availability zone of most of the major cloud providers"
            ),
            "evidence_page": 18,
        },
    ],
    # =====================================================================
    # Loughborough University energy + data centre —
    # `Charnwood/P/22/0023/2`. University-scale energy + data centre
    # building at the Whitworth Tower, Elvyn Way, Loughborough
    # University. Modest scale (university computing rather than
    # hyperscale colocation).
    # =====================================================================
    "Charnwood/P/22/0023/2": [
        {
            "doc_sha_prefix": "c1525f76",  # FULL-Grant-Conditionally decision
            "signal_type": "facility_classification",
            "value_text": (
                "university energy + data centre at Loughborough University "
                "(Whitworth Tower, Elvyn Way) — university computing scale, "
                "not hyperscale colocation"
            ),
            "evidence_text": (
                "Erection of energy and data centre with associated "
                "landscaping and ancillary works. Location: Whitworth Tower, "
                "Elvyn Way, Loughborough University, Loughborough, LE11 3UA"
            ),
            "evidence_page": 1,
        },
    ],
    # =====================================================================
    # WBE Margam biomass-anchored DC — `Neath/P2025/0187`. Editorially
    # distinctive: Western Bio-Energy (WBE)'s existing biomass plant at
    # Margam will supply a co-located 12 MW DC via PRIVATE WIRE — actual
    # operating renewable power supply rather than a PPA / aspirational
    # transition. 4th appearance of Future-tech as M&E consultant in the
    # dataset (alongside Humber Tech Park, Elsham Tech Park, West London
    # Tech Park).
    # =====================================================================
    "Neath/P2025/0187": [
        {
            "doc_sha_prefix": "8dcbaaad",  # Design and Access Statement (74p)
            "signal_type": "facility_classification",
            "value_text": (
                "12 MW data centre (2 × 3.75 MW data halls = 7.5 MW IT load, "
                "cloud-based model), Use Class B8, on Land at Tyn-y-Caeau, "
                "Margam, Port Talbot SA13 2NR. Power supplied via PRIVATE WIRE "
                "from the existing on-site Western Bio-Energy biomass plant; "
                "grid as back-up (up to 15.8 MW)."
            ),
            "evidence_text": (
                "The biomass boiler will provide up to 12 MW of power via a "
                "private wire to the data centre, with back-up from grid, "
                "which could provide up to 15.8 MW. Therefore WBE is seeking "
                "to maximise capacity of data centre (up to 12MW), subject to "
                "site constraints"
            ),
            "evidence_page": 24,
        },
        {
            "doc_sha_prefix": "8dcbaaad",
            "signal_type": "applicant_name",
            "value_text": (
                "Western Bio-Energy (WBE) — owner / operator of the existing "
                "biomass plant at Margam, expanding to colocate a DC behind "
                "the biomass plant's meter; M&E consultant: Future-tech "
                "(doc ref pattern '1044 - FUT - V1 - 00 - ...', matching the "
                "Future-tech signature on Greystoke Land's three sites at "
                "Humber / Elsham / West London)"
            ),
            "evidence_text": (
                "Therefore WBE is seeking to maximise capacity of data centre "
                "(up to 12MW), subject to site constraints"
            ),
            "evidence_page": 24,
        },
        {
            "doc_sha_prefix": "8dcbaaad",
            "signal_type": "total_it_load_mw",
            "value_number": 7.5,
            "value_unit": "MW (IT load, cloud-based model)",
            "evidence_text": (
                "Of 12MW (MVA), c.7.5 MW usable power/ IT load would be "
                "achieved, based on a cloud-based model, as opposed to an "
                "AI-based model"
            ),
            "evidence_page": 24,
        },
        {
            "doc_sha_prefix": "8dcbaaad",
            "signal_type": "renewable_supply_commitment",
            "value_text": (
                "PRIVATE WIRE connection to the existing on-site Western Wood "
                "Biomass Plant — actual operating renewable power, distinct "
                "from PPA arrangements (e.g. Thurrock Lakeside's Moray West "
                "wind PPA) or aspirational hydrogen transitions (e.g. Yorkshire "
                "Energy Park). Editorially the closest thing to a real "
                "renewable-anchored DC in the worklist."
            ),
            "evidence_text": (
                "The biomass boiler will provide up to 12 MW of power via a "
                "private wire to the data centre, with back-up from grid, "
                "which could provide up to 15.8 MW"
            ),
            "evidence_page": 24,
        },
    ],
    # =====================================================================
    # Broxbourne small DC change of use — `Broxbourne/07/24/0348/F`.
    # Single industrial-unit-scale DC conversion at Unit 3, Bingley
    # Road, Hoddesdon. Modest scale; site partially in Flood Zone 3.
    # =====================================================================
    "Broxbourne/07/24/0348/F": [
        {
            "doc_sha_prefix": "7bf1a533",
            "signal_type": "facility_classification",
            "value_text": (
                "small Sui Generis DC change-of-use in a single industrial "
                "unit (Unit 3 Bingley Road, Hoddesdon EN11 0BU — formerly "
                "Xylem Water Solutions warehouse, since redeveloped under "
                "parent 07/22/0479/F into 4 industrial sheds). Components: "
                "battery storage for solar PV + cooling + bunded fuel store "
                "+ generators + site transformer + HV switchgear. Wholly in "
                "Flood Zone 2, partially in Flood Zone 3. Agent: Carter "
                "Jonas; Case Officer: Louise Hart."
            ),
            "evidence_text": (
                "The application seeks planning permission for Change of use "
                "to allow a Sui Generis Data Centre (to include the "
                "development of battery storage for solar PV, cooling "
                "infrastructure, vented screening, bunded fuel store, "
                "generator, site transformer and high voltage switch gear) "
                "in addition to the permitted Class E (g) (iii), B2 and B8 "
                "uses. ... The site Falls wholly within Flood Zone 2 and "
                "partially within Flood Zone 3."
            ),
            "evidence_page": 2,
        },
    ],
    # =====================================================================
    # Widnes Waterfront mixed-use hybrid — `Warrington/2026/00295/HYB`.
    # 169,800 sqm cross-boundary scheme including a 75,320 sqm DC + BESS
    # as one of several uses. Site 5 within Warrington BC (WBC). Most
    # docs are environmental-search / desktop reports rather than DC
    # technical specs — substantive DC content modest in current bundle.
    # =====================================================================
    "Warrington/2026/00295/HYB": [
        {
            "doc_sha_prefix": "f55582d4",  # description-of-development doc
            "signal_type": "facility_classification",
            "value_text": (
                "75,320 sqm data centre (sui generis) as one use within a "
                "169,800 sqm cross-boundary hybrid scheme at Widnes Waterfront "
                "(Earle Road / Moss Bank Road, Widnes WA8 0GY) — also "
                "162,850 sqm B2/B8 industrial/warehousing, BESS, 28,610 sqm "
                "light industrial, retail, sport, creche. Hybrid full + "
                "outline application; the DC sits within the outline portion "
                "(all matters except Access reserved)."
            ),
            "evidence_text": (
                "Part B Outline planning permission with all matters reserved "
                "except for means of access for a phased development "
                "comprising up to 169,800 sqm of total floorspace across "
                "commercial / industrial / warehousing / waste management "
                "facilities providing up to 162,850 sqm of floorspace "
                "(including ancillary office accommodation) in Use Classes B2 "
                "and B8; up to 75,320 sqm of floorspace for data centre (sui "
                "generis); battery energy storage system"
            ),
            "evidence_page": 4,
        },
    ],

    # =====================================================================
    # Heyford Park mixed-use hybrid — `Cherwell/25/02190/HYBRID`.
    # 9,000-dwelling residential-led scheme at the former Heyford Park
    # USAF base; DC is one named use among many. Editorial weight on
    # the DC angle is modest (mostly residential).
    # =====================================================================
    "Cherwell/25/02190/HYBRID": [
        {
            "doc_sha_prefix": "7f2850a1",  # Application Form (redacted)
            "signal_type": "facility_classification",
            "value_text": (
                "9,000-dwelling residential-led hybrid scheme at Heyford "
                "Park, Camp Road, Upper Heyford (former US Air Force base). "
                "DC component is one named use among many — editorial "
                "weight is modest unless the DC element is substantially "
                "scaled (TBC once Planning Statement docs read)."
            ),
            "evidence_text": (
                "A hybrid planning application consisting of: demolition of "
                "buildings and structures as listed in Schedule 1. Up to "
                "9,000 new dwellings (Class C3) comprised of: Outline planning "
                "permission for up to 8,848 dwellings (Class C3)"
            ),
            "evidence_page": 4,
        },
    ],

    # =====================================================================
    # West Calder AI DC Campus — `WestLothian/0625/PAC/25`. 250 MW AI
    # data centre campus with BESS at the former Freeport Shopping
    # Village, West Calder. Editorially distinctive on three axes:
    # (1) explicit AI framing, (2) hyperscale 250 MW utility demand,
    # (3) BESS going through Scottish Government Section 36 consent
    # (separate from this Proposal-of-Application-Notice / PAC route).
    # =====================================================================
    "WestLothian/0625/PAC/25": [
        # Source doc is a handwritten Proposal of Application Notice form
        # (pypdf returns empty pages — see Read-tool vision verification in
        # 2026-05-16 session). Quotes below transcribe the handwritten
        # entries on the form, retaining the form-language capitalisation
        # and the applicant's misspelling of "separately".
        {
            "doc_sha_prefix": "54e72002",  # Proposal of Application Notice (handwritten form)
            "signal_type": "facility_classification",
            "value_text": (
                "250 MW AI Data Centre Campus + ancillary BESS at Land at "
                "Former Freeport Retail Village, Westwood, West Calder, "
                "EH55 8PN. Explicit AI framing (rare in the worklist — most "
                "DCs avoid naming the AI use case). 'Proposal of Application "
                "Notice' (PAC) is the Scottish pre-application notification "
                "stage. Applicant: Apatura DC Project 8 Ltd; agent: Tom Allan "
                "of PAA Consultants."
            ),
            "evidence_text": (
                "ERECTION OF AN AI DATA CENTRE CAMPUS WITH A 250MW DEMAND "
                "UTILITY CAPACITY WITH ANCILLARY BATTERY ENERGY STORAGE "
                "(TO BE CONSENTED SEPERATLY VIA SECTION 36 APPLICATION TO "
                "THE ECU), CAR PARKING, LANDSCAPING, ROADS, ACCESS AND "
                "ASSOCIATED WORKS. ... LAND AT FORMER FREEPORT RETAIL "
                "VILLAGE, WESTWOOD, WEST CALDER, EH55 8PN"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "54e72002",
            "signal_type": "total_it_load_mw",
            "value_number": 250,
            "value_unit": "MW (utility demand capacity)",
            "evidence_text": (
                "AI DATA CENTRE CAMPUS WITH A 250MW DEMAND UTILITY CAPACITY"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "54e72002",
            "signal_type": "planning_route",
            "value_text": (
                "Scottish dual-track: Proposal of Application Notice (PAC) "
                "for the DC building consent + separate Section 36 "
                "application to the Energy Consents Unit (ECU) for the BESS "
                "(S36 = Electricity Act 1989 consent for generation/storage "
                "above 50 MW in Scotland, equivalent to a Development "
                "Consent Order in England)"
            ),
            "evidence_text": (
                "ERECTION OF AN AI DATA CENTRE CAMPUS WITH A 250MW DEMAND "
                "UTILITY CAPACITY WITH ANCILLARY BATTERY ENERGY STORAGE "
                "(TO BE CONSENTED SEPERATLY VIA SECTION 36 APPLICATION TO "
                "THE ECU)"
            ),
            "evidence_page": 1,
        },
    ],

    "TowerHamlets/PA/15/01527/S": [
        # ----- Decision Notice (45512836) -----
        {
            "doc_sha_prefix": "45512836",
            "signal_type": "facility_classification",
            "value_text": (
                "residential development NMA at Poplar Business Park, E14 (Phase 1 housing); "
                "'energy centre' is the building-services heating hub, not on-site power "
                "generation for a data centre"
            ),
            "evidence_text": (
                "APPROVAL OF NON-MATERIAL AMENDMENTS TO A PLANNING PERMISSION "
                "... Location: Poplar Business Park, 10 Prestons Road, London, "
                "E14 9RL ... change all 2b/3p flats to 2b/4p flats (and "
                "associated minor internal layout changes) within Block A "
                "... relocate CHP plant from first floor A1 to external energy "
                "centre on the western boundary"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "45512836",
            "signal_type": "chp_rated_kwe",
            "value_number": 100,
            "value_unit": "kWe",
            "evidence_text": (
                "Heat generating plant installed in a single energy centre located within the "
                "Development and that upon completion of the scheme includes combined heat and "
                "power (CHP) generation (~100 kWe). The CHP system will be designed to allow "
                "future connection to a future district heating scheme."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "45512836",
            "signal_type": "chp_purpose",
            "value_text": (
                "residential heating: space heating + domestic hot water for the Phase 1 "
                "housing block (London Plan 2015 decentralised-energy compliance)"
            ),
            "evidence_text": (
                "a heat network supplying all spaces shall be installed and sized to the space "
                "heating and domestic hot water requirements of the Development ... Reason: To "
                "ensure a reduction of carbon dioxide emissions, through the cumulative steps "
                "of the Energy Hierarchy, in accordance with Policy 5.2 of the London Plan 2015 "
                "and delivery of a decentralised energy system"
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "45512836",
            "signal_type": "district_heating_readiness",
            "value_text": "CHP designed for future connection to external district heating scheme",
            "evidence_text": (
                "It shall be supplied with heat from either: An external district heating "
                "system or Heat generating plant installed in a single energy centre located "
                "within the Development and that upon completion of the scheme includes "
                "combined heat and power (CHP) generation (~100 kWe). The CHP system will be "
                "designed to allow future connection to a future district heating scheme."
            ),
            "evidence_page": 3,
        },
        {
            "doc_sha_prefix": "45512836",
            "signal_type": "decision_outcome",
            "value_text": "APPROVED — NMA approval (Tower Hamlets Council, 15 July 2016)",
            "evidence_text": (
                "S96a TOWN AND COUNTRY PLANNING ACT 1990 APPROVAL OF NON-MATERIAL AMENDMENTS "
                "TO A PLANNING PERMISSION ... 15/07/2016 ... The local planning authority "
                "hereby approves the non-material amendments referred to in the schedule above."
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "45512836",
            "signal_type": "agent_name",
            "value_text": "Barton Willmore Design (Mr James Carr)",
            "evidence_text": "Mr James Carr Barton Willmore Design 7 Soho Square London W1D 3QB",
            "evidence_page": 1,
        },
    ],
}


def resolve_app_and_docs(conn, application_ref: str) -> tuple[int, dict[str, int]]:
    """Look up the application id + a SHA-prefix → document_id map."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM applications WHERE application_ref = %s",
            (application_ref,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"Application not found: {application_ref}")
        application_id = row[0]
        cur.execute(
            "SELECT content_sha256, id FROM documents WHERE application_id = %s",
            (application_id,),
        )
        sha_to_doc: dict[str, int] = {sha: doc_id for sha, doc_id in cur.fetchall()}
    return application_id, sha_to_doc


def seed_app(conn, application_ref: str, findings: list[dict[str, Any]]) -> int:
    application_id, sha_to_doc = resolve_app_and_docs(conn, application_ref)
    inserted = 0
    for entry in findings:
        prefix = entry["doc_sha_prefix"]
        doc_id = next(
            (did for sha, did in sha_to_doc.items() if sha.startswith(prefix)), None,
        )
        if doc_id is None:
            raise RuntimeError(
                f"No document with SHA prefix {prefix} for {application_ref}",
            )
        repo.record_finding(
            conn,
            application_id=application_id,
            document_id=doc_id,
            signal_type=entry["signal_type"],
            model=MODEL,
            value_text=entry.get("value_text"),
            value_number=entry.get("value_number"),
            value_unit=entry.get("value_unit"),
            evidence_text=entry.get("evidence_text"),
            evidence_page=entry.get("evidence_page"),
        )
        inserted += 1
    return inserted


def reset_app(conn, application_ref: str) -> int:
    """Delete every finding row for this app + model, so the next seed
    pass starts from a clean slate.

    The schema is append-only by default; we lift that for this calibration
    round specifically because the seed script IS the source of truth (and
    is tracked in git, so the audit trail lives there). A correction that
    just appends a new row would still leave the wrong-doc / wrong-page row
    visible via the (app, doc, signal, model) dedup tuple. Cleanest fix:
    drop the round for the model + re-insert.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM findings "
            "WHERE model = %s "
            "AND application_id = (SELECT id FROM applications WHERE application_ref = %s)",
            (MODEL, application_ref),
        )
        return cur.rowcount


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--reset", action="store_true",
        help="Delete existing findings for the target apps + this model before inserting. "
             "Use after editing the seed dict to correct a transcription error.",
    )
    ap.add_argument("app_refs", nargs="*", help="App refs to (re-)seed. Default: all.")
    args = ap.parse_args()

    targets = args.app_refs or list(FINDINGS_BY_APP.keys())
    with db.connect() as conn:
        for app_ref in targets:
            findings = FINDINGS_BY_APP.get(app_ref)
            if findings is None:
                print(f"  SKIP {app_ref}: no findings defined")
                continue
            if args.reset:
                deleted = reset_app(conn, app_ref)
                if deleted:
                    print(f"  Cleared {deleted:3d} prior findings for {app_ref}")
            n = seed_app(conn, app_ref, findings)
            print(f"  Inserted {n:3d} findings for {app_ref}")
    print(f"Round model: {MODEL}")


if __name__ == "__main__":
    main()
