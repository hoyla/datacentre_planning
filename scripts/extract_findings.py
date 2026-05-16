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
from typing import Any

from dcp import db, repo


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
                "The application proposed the creation of a secure compound enclosed by "
                "acoustic fencing and containing 14 generators, office, storage and other "
                "ancillary buildings ... up to 21MW capacity."
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
                "Applicant: Mrs Sally Hines, The John Innes Centre, Norwich Research Park, "
                "Norwich, NR4 7UH"
            ),
            "evidence_page": 1,
        },
        {
            "doc_sha_prefix": "696fd100",
            "signal_type": "agent_name",
            "value_text": "Lanpro Services Limited (Mr Dean Starkey)",
            "evidence_text": (
                "Agent: Mr Dean Starkey, Lanpro Services Limited, 98 Pottergate, Norwich, NR2 1EQ"
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
                "DISCHARGE OF CONDITIONS IMPOSED ON 2012/1477 ... Condition 4: Surface water; "
                "Condition 5: Foul water; Condition 6: Contamination; Condition 7: Verification; "
                "Condition 8: Monitoring; Condition 10: External lighting; Condition 12: Fire "
                "hydrants; Condition 20: Archaeology; Condition 22: Surfacing of footway/cycleway; "
                "Condition 23: Roads, footways and cycleways"
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
            "evidence_text": "Humber Tech Park Ltd, Anthony Crean KC, 75D Banbury Road, Oxford OX2 6PE",
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
                "constructed on the site and that each will have: Sixteen 8MW data halls "
                "each with an associated 4MW of mechanical and building services loads. "
                "Giving a total IT load per building of 128MW and supporting services "
                "load of 64MW. ... Thus, the overall site load for all three buildings is "
                "expected to be of the order of 576 MW."
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
                "At this stage generator fuel consumption will be calculated using 475 "
                "litres per hour per engine at 80% load... Fuel Consumption Rates: "
                "Whole Site 250 engines = 118,750 L/hr = 2,850,000 L/24hr; Per Engine "
                "1 = 475 L/hr = 11,400 L/24hr."
            ),
            "evidence_page": 5,
        },
        {
            "doc_sha_prefix": "94ebbfb4",
            "signal_type": "fuel_consumption_site_lph",
            "value_number": 118750,
            "value_unit": "L/hr",
            "evidence_text": (
                "Whole Site, 250 No Engines at 80% load: 118,750 L/hr ≈ 2,850,000 L/24hr "
                "with all generators running."
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
                "To satisfy this requirement, each of the 250 generator plant will be "
                "tested separately. The assumption within this assessment is that the "
                "generators will be tested separately, for 30 minutes per month, at "
                "full load."
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
                "Maximum power demand ≈ 450 MW. Assumed operational diversity 50% of "
                "maximum. Operational power demand 38 MW. Data centre operation 8760 "
                "hours / year. Annual energy consumption 1,664,400,000 kWh."
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
                "Location: Poplar Business Park, 10 Prestons Road, London, E14 9RL. "
                "APPROVAL OF NON-MATERIAL AMENDMENTS TO A PLANNING PERMISSION ... change all "
                "2b/3p flats to 2b/4p flats (and associated minor internal layout changes) "
                "within Block A ... relocate CHP plant from first floor A1 to external energy "
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
            "evidence_text": "Mr James Carr, Barton Willmore Design, 7 Soho Square, London W1D 3QB",
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


def main() -> None:
    targets = sys.argv[1:] or list(FINDINGS_BY_APP.keys())
    with db.connect() as conn:
        for app_ref in targets:
            findings = FINDINGS_BY_APP.get(app_ref)
            if findings is None:
                print(f"  SKIP {app_ref}: no findings defined")
                continue
            n = seed_app(conn, app_ref, findings)
            print(f"  Inserted {n:3d} findings for {app_ref}")
    print(f"Round model: {MODEL}")


if __name__ == "__main__":
    main()
