"""Canonical families over the free-form `findings.signal_type` labels.

The deep-read prompt asks the model for "a short snake_case label" per
finding. That was right for extraction — it lets the model name what it
actually found rather than forcing it into a box — but it means the
corpus carries **54,044 distinct labels across 346,653 findings**, 42,384
of them appearing once or twice. The same concept scatters:
`onsite_generation` / `on_site_generation` / `onsite_power_generation` /
`on_site_power_generation` are one signal under four names.

The findings themselves are sound — each carries a gate-verified verbatim
quote, a document and a page. What is missing is a usable index: a
reporter cannot ask "every site with on-site generation" of 54k labels.

This module supplies that index **without touching the original label**,
per the project's third principle (store the inferred value alongside,
never overwrite the raw record). `signal_type` remains exactly as the
model emitted it; `signal_family` is derived, recomputable, and carries
the rule that produced it so any grouping can be audited back.

Matching is deterministic and token-based rather than exact-string,
because the labels are compositional: `onsite_generation_fuel`,
`generator_testing_hours` and `backup_generators` all carry a token that
places them without needing to be enumerated. Rules are ordered — the
first family whose pattern matches wins — so more specific families are
declared before the general ones they would otherwise be swallowed by.

Anything unmatched lands in `unclassified` and is reported as such: an
honest count of what the taxonomy does not yet cover is worth more than a
tidy-looking mapping that quietly guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    """A canonical family and the pattern that recruits labels into it."""
    name: str
    pattern: str
    note: str = ""

    def compiled(self) -> re.Pattern:
        return re.compile(self.pattern, re.I)


# A snake_case token boundary, and the reason it cannot be `\b`.
#
# `\b` sits between a word character and a non-word character, and `_` is
# a word character. So `eia\b` matches a bare `eia` and `flood-eia`, and
# never matches `eia_status` — which is every label the token was written
# for. The family `eia_process` did not classify as `eia_process`; it
# came back `unclassified`. The same defect ran through `suds`, `chp`,
# `ups`, `dno`, `mva`, `bng`, `cemp`, `lpa`, `pue`, `sac`, `spa`, `scr`,
# `crac`, `crah`, `kv`, `hvo`, `gia`, `gea` and `mw`: 13,677 rows, 10.3%
# of everything `unclassified`, sat outside a family whose pattern was
# plainly written to hold them.
#
# The boundary the labels actually need is expressed over the characters
# a snake_case token is made of. `_`, `-`, a space and the end of the
# string all end a token; a letter or a digit does not. So `eia` matches
# in `eia_status`, `flood_eia` and a bare `eia`, and still does not match
# in `eias` — deleting the boundary rather than correcting it would be
# the more damaging fix.
#
# This corrects how a token is delimited. It does not change which
# tokens any family claims: that list is editorial (see the note below)
# and is not for this module to revise.
TOK_END = r"(?![a-z0-9])"
TOK_START = r"(?<![a-z0-9])"

# Ordered most-specific first. Each pattern is matched against the raw
# signal_type with word-ish boundaries handled inside the pattern, since
# labels are snake_case and tokens run together (`onsite`, `on_site`).
#
# EDITORIAL NOTE: this list is the answer to "how do the data and visuals
# teams want to slice the findings?", not a technical constant. It is
# expected to be revised with the reporting team; revising it and re-running
# the mapper is cheap and non-destructive.
FAMILIES: tuple[Family, ...] = (
    # --- parties, split by side (the adjacency question needs this) ---
    Family("party_applicant",
           r"applicant|developer|client|landowner|freeholder|operator_name|"
           r"end_user|occupier",
           "Applicant-side: who is promoting the scheme."),
    Family("party_adviser",
           r"consultant|agent|architect|engineer_practice|solicitor|"
           # `author` is delimited because otherwise it matches inside
           # "authority", and this family is declared before
           # party_authority — so party_authority's own explicit
           # `local_planning_authority`, `planning_authority` and
           # `local_authority` tokens could never be reached. A token
           # the vocabulary states but can never win is the tell. 11,706
           # findings were filed as advisers on 2026-08-26, among them
           # 2,980 `local_planning_authority`; the decision-maker was in
           # the same bucket as the consultants acting for the
           # applicant. 1,859 genuine author labels contain no
           # "authorit" and are unaffected.
           rf"planning_consult|adviser|advisor|author{TOK_END}|"
           rf"prepared_by|technical_author{TOK_END}",
           "Advisers acting for the applicant — the network question."),
    Family("party_authority",
           r"consultee|case_officer|local_planning_authority|"
           r"planning_authority|local_authority|council_officer|"
           rf"statutory_(consultee|body)|authority_name|lpa{TOK_END}|"
           r"environment_agency|natural_england|highways_england|"
           r"national_grid_(company|operator)",
           "Councils, statutory consultees and officers."),
    Family("party_other",
           r"part(y|ies)|contractor|stakeholder|third_party|"
           r"organisation|company_name|supplier",
           "Parties named without a stated side — needs attribution."),

    # --- the power story: most specific first ---
    Family("power_generation",
           rf"generat|generator|chp{TOK_END}|combined_heat|engine|turbine|"
           r"peaking|peaker|prime_power|standby_power|backup_power|"
           r"emergency_power|bess|battery_storage|energy_storage|"
           rf"fuel|diesel|gas_(supply|storage|main|connection)|hvo{TOK_END}|"
           rf"tank|resilience|ups{TOK_END}|uninterruptible|n\+1|redundan",
           "On-site generation, backup, fuel and storage plant. Fuel "
           "belongs here: it is the generation story, not a separate one."),
    Family("power_grid",
           rf"grid|substation|electrical_infrastructure|dno{TOK_END}|"
           r"connection_(agreement|capacity|offer)|point_of_connection|"
           rf"transformer|switchgear|hv_|kv{TOK_END}|mva{TOK_END}|private_wire|"
           r"electricity_(supply|infrastructure|network)|"
           r"power_infrastructure|power_(supply|connection|route)|"
           r"cable|pylon|overhead_line",
           "Grid connection, capacity and electrical infrastructure."),
    Family("power_demand",
           r"it_load|power_demand|load_capacity|energy_demand|"
           r"electricity_demand|mw_capacity|rack_(density|load)|"
           r"design_capacity|installed_capacity|power_capacity|"
           rf"energy_consumption|power_usage|pue{TOK_END}|megawatt|"
           rf"{TOK_START}mw{TOK_END}",
           "IT load, power demand and capacity figures."),
    Family("energy_efficiency_heat",
           r"heat_(network|recovery|reuse|export|pump)|district_heat|"
           r"waste_heat|energy_efficiency|renewable|solar|photovoltaic|"
           r"pv_|net_zero|carbon_(reduction|offset|neutral|footprint)|"
           r"energy_statement|sustainab|breeam|epc_|"
           r"greening_factor|green_roof",
           "Heat reuse, renewables, efficiency and sustainability ratings."),

    # --- water and cooling ---
    Family("cooling",
           rf"cooling|chiller|refrigerant|air_handling|crac{TOK_END}|"
           rf"crah{TOK_END}|"
           r"adiabatic|evaporative|free_cooling|heat_rejection",
           "Cooling systems and equipment."),
    Family("water",
           r"water|potable|abstraction|effluent|wastewater|foul_|"
           r"sewer|discharge_consent|dcww|thames_water",
           "Water supply, use, abstraction and disposal."),

    # --- environmental constraints ---
    Family("flood_drainage",
           rf"flood|drainage|suds{TOK_END}|surface_water|groundwater_level|"
           r"attenuation|watercourse|culvert|runoff|run_off|"
           r"climate_change_allowance|sequential_test",
           "Flood risk, drainage and surface water."),
    Family("designated_sites",
           rf"designat|sssi|sac{TOK_END}|spa{TOK_END}|ramsar|ancient_woodland|"
           r"conservation_area|listed_building|scheduled_monument|"
           r"green_belt|aonb|national_park|heritage|archaeolog",
           "Statutory designations and heritage constraints."),
    Family("ecology_biodiversity",
           rf"ecolog|biodiversity|bng{TOK_END}|habitat|species|newt|bat_|bird|"
           r"badger|invasive|tree_|arboricultur|hedgerow|landscap|"
           r"green_infrastructure",
           "Ecology, species, habitats and biodiversity net gain."),
    Family("air_quality_emissions",
           r"air_quality|emission|nox|no2|particulate|pm10|pm2|"
           rf"dispersion|stack_|abatement|scr{TOK_END}|selective_catalytic|"
           r"aqma|combustion_products",
           "Air quality, emissions and abatement."),
    Family("noise",
           r"noise|acoustic|decibel|db\(a\)|sound_|vibration",
           "Noise and acoustic assessment."),
    Family("land_quality",
           r"contamina|remediation|ground_(conditions|gas|investigation)|"
           r"geotechnical|geolog|hydrogeolog|aquifer|"
           r"source_protection|soil|made_ground|asbestos|landfill|"
           r"mining_legacy|pollution|spill",
           "Contamination, geology, hydrogeology and remediation."),
    Family("waste",
           r"waste|recycl|circular_economy|spoil|excavat",
           "Waste management and materials."),
    Family("transport_access",
           r"transport|traffic|highway|parking|access|vehicle|hgv|"
           r"trip_generation|travel_plan|cycle|pedestrian|ev_charging|"
           r"delivery|servicing|road_",
           "Transport, access, servicing and parking."),
    Family("socioeconomic",
           r"employment|staffing|jobs|economic|skills|training|"
           r"community|social_value|apprentice",
           "Employment, economic and community impact."),
    Family("permits_regulatory",
           r"permit|licence|license|regulat|compliance|"
           r"sensitive_receptor|statutory_requirement",
           "Environmental permits, licences and regulatory compliance."),
    Family("construction_operation",
           r"construction|phasing|programme|timeline|duration|"
           r"operational_hours|hours_of_(use|operation)|"
           rf"decommission|demolition|cemp{TOK_END}|security|fencing|lighting",
           "Construction phasing, operating hours, security and lighting."),

    # --- process and identity (lower priority: generic words) ---
    Family("eia_process",
           rf"eia{TOK_END}|environmental_impact|screening|scoping|"
           r"environmental_statement|significant_effect|cumulative",
           "EIA screening, scoping, significance and cumulative effects."),
    Family("development_scale",
           rf"floor_?(space|area)|gia{TOK_END}|gea{TOK_END}|height|storey|"
           rf"footprint|"
           r"site_area|hectare|development_(scale|size)|use_class|"
           r"massing|density|number_of_buildings|building_(area|scale|"
           r"dimension|size|footprint)|volume|capacity_sqm|sqm|square_",
           "Physical scale: area, height, floorspace, use class."),
    Family("application_admin",
           r"application_(reference|type|number|date|status)|"
           r"planning_(reference|application|history|condition|status|"
           r"policy|permission|obligation)|policy_reference|"
           r"document_(type|title|date|reference)|"
           r"supporting_document|decision|determination|committee|"
           r"validation_date|condition|s106|section_106|"
           r"obligation|appeal|reference_number|revision|"
           r"consultation_(period|response_date)",
           "Application references, documents, decisions, conditions, "
           "policy and planning history."),
    Family("site_identity",
           r"site_|project_|development_|proposal|proposed_|existing_|"
           r"facility_|building_|location|address|postcode|"
           # `ward\b` is the one token left with the broken boundary, on
           # purpose. Correcting it the way every other token above was
           # corrected recruits `upward_light_ratio`,
           # `seaward_boundary_distance`, `outward_hdv_peak` and `sward`
           # alongside `ward_name` and `ward_councillor` — measured
           # 2026-08-26 across the corpus, 41 rows of English words
           # ending in "ward" against 21 rows of electoral wards. It is
           # the only token where the correction recruits more labels it
           # was not written for than labels it was. Correcting it needs
           # a *leading* boundary as well, which would also stop it
           # matching today's `upward` and `forward`, and that is a
           # change of scope rather than of delimiting — an editorial
           # call, so it is left for a person.
           r"grid_reference|coordinates|ward\b|layout|scheme_",
           "What and where the site is, and how the scheme is described. "
           "Declared last among the descriptive families so more specific "
           "topics claim their labels first. Deliberately excludes bare "
           "`infrastructure`, `mitigation` and `feature`: those say nothing "
           "about subject (mitigation of *what*? infrastructure for *what*?) "
           "and filing them here would inflate coverage by guessing. They "
           "fall to `unclassified`, which is the honest answer."),
)

_COMPILED: tuple[tuple[str, re.Pattern], ...] = tuple(
    (f.name, f.compiled()) for f in FAMILIES)

UNCLASSIFIED = "unclassified"


def family_for(signal_type: str | None) -> str:
    """The canonical family for one raw label, or 'unclassified'.

    First match wins, so FAMILIES order encodes precedence: a label like
    `cooling_water_use` lands in `cooling` because cooling is declared
    before water — the cooling context is the more specific fact.
    """
    if not signal_type:
        return UNCLASSIFIED
    label = signal_type.strip().lower()
    for name, pattern in _COMPILED:
        if pattern.search(label):
            return name
    return UNCLASSIFIED


def family_names() -> list[str]:
    return [f.name for f in FAMILIES] + [UNCLASSIFIED]


# ---------------------------------------------------------------------------
# Prevention, as opposed to the cure above
# ---------------------------------------------------------------------------
#
# Everything above this line cleans up after the fact. It exists because
# prompt v1.0 asked the model for "a short snake_case label" and got
# 54,044 of them. Mapping them back into families recovers a usable index,
# but a re-run under the same prompt would produce a fresh 54,000, and the
# regexes above would then be chasing a new set of coinages.
#
# The fix is to constrain the vocabulary at the point of extraction while
# keeping what was genuinely valuable about the free-form label. The model
# naming precisely what it found — `generator_testing_hours` rather than a
# flat `power_generation` — carries real information that a fixed taxonomy
# would throw away. So a corrected prompt asks for BOTH: a `signal_family`
# drawn from this controlled list, and the model's own `signal_type` as a
# free-text refinement beneath it.
#
# On the API paths that field can be an enum in the structured-output
# schema, which makes an out-of-vocabulary family impossible rather than
# merely discouraged. The local model has no such enforcement, so its
# output is validated against this same list on the way in and anything
# unrecognised falls back to `family_for()` on the free-text label.
#
# These names are generated from FAMILIES rather than written out again,
# so the prompt's vocabulary and the mapper's vocabulary cannot drift
# apart — the failure mode that would otherwise reappear the first time
# someone adds a family to one and forgets the other.

PROMPT_FAMILY_ENUM: list[str] = [f.name for f in FAMILIES] + [UNCLASSIFIED]


def prompt_vocabulary_block() -> str:
    """The family list as prompt text, with the one-line note for each.

    Rendered from FAMILIES so it always matches what the mapper accepts.
    """
    lines = ["Choose signal_family from exactly this list:"]
    for f in FAMILIES:
        lines.append(f"  {f.name} — {f.note}")
    lines.append(f"  {UNCLASSIFIED} — none of the above fits; say so rather "
                 f"than forcing a match.")
    return "\n".join(lines)


def validate_family(value: str | None, fallback_label: str | None) -> str:
    """Coerce a model-supplied family into the controlled vocabulary.

    Used on paths where the schema cannot enforce the enum (the local
    model). An unrecognised value is not trusted and not discarded: the
    free-text label is mapped instead, which is the same route the v1.0
    corpus takes.
    """
    if value and value in PROMPT_FAMILY_ENUM:
        return value
    return family_for(fallback_label)
