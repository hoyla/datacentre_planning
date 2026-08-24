"""Adjudicate which power figures actually describe each development.

The deep-read captured every power fact in every document. That was the
right instruction — but it means the corpus cannot answer the question the
reporting team most wants ("how big is this site?"), because planning
statements quote the market far more often than they quote themselves.
Measured on the Sonnet pass: of the twenty-two largest MW/GW findings in
the corpus, *all twenty-two* are market forecasts, policy targets or grid
statistics. Ranking sites by their largest figure would be nonsense.

This pass reads no documents. It takes the findings already extracted and
gate-verified, groups them by application, and asks a much narrower
question per application: of these candidate figures, which describe THIS
development, and which quantity does each measure? Reusing paid-for
extractions makes it a fraction of the bulk pass's cost, and every answer
still points back at a verbatim quote that survived the gate.

Four quantities are kept apart deliberately. IT load, grid connection
capacity, on-site generation and cooling capacity routinely differ by
more than a factor of two for the same site — a 100MW campus may hold
120MW of standby diesel behind a 150MW grid offer. Collapsing them into
"the site's MW" would replace one error with another.

Exclusions are recorded with a reason rather than dropped, so "why doesn't
this site show the 30GW figure in its documents?" resolves to a row.

Usage:
    scripts/adjudicate_power.py --measure    # token count + cost, spends nothing
    scripts/adjudicate_power.py --submit
    scripts/adjudicate_power.py --collect
    scripts/adjudicate_power.py --report     # per-site power profile
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

MODEL = "claude-sonnet-5"
# power-1.0 is what the corpus was adjudicated under and must not change:
# it is half of the (finding_id, model, prompt_version) key, so editing it
# in place would leave two different prompts sharing one version and make
# the audit trail a lie.
#
# power-1.1 adds the quantity-kind rules below — the six families that
# reached readers on 2026-08-10 — so that errors are not created and then
# corrected by scripts/correct_adjudications.py, but mostly not created.
#
# It is NOT the default, because selecting it re-adjudicates the entire
# corpus: no figure carries a 1.1 verdict, so every one re-enters the
# cohort. That is roughly $20-40 of batch and a deliberate decision, not
# a side effect of an import. It is also UNVALIDATED: the 229-figure
# ground-truth set in the scratchpad is the way to check it improves the
# specific cases before spending that.
PROMPT_VERSION = "power-1.0"
PROMPT_VERSION_LATEST = "power-1.1"
STATE_PATH = ROOT / "data" / "power_adjudication_batch.json"

# Units that carry a real-power meaning we can normalise to MW. MVA and
# kVA are apparent power — related to MW only through a power factor we
# do not know — so they are recorded but never silently converted.
TO_MW = {
    "mw": 1.0, "megawatt": 1.0, "megawatts": 1.0, "mwe": 1.0,
    "kw": 0.001, "kilowatt": 0.001, "kilowatts": 0.001,
    "gw": 1000.0, "gigawatt": 1000.0, "gigawatts": 1000.0,
}
APPARENT = {"mva", "kva"}

PROMPT = """\
You are auditing extracted figures from UK planning documents for an
investigative journalism project on data centres.

Below are power-related figures extracted from the documents of ONE
planning application, each with the verbatim quote it came from.

Your task: decide which figures describe **the power capacity of the
development that this application is for**, and which do not.

This matters because planning statements argue for approval by citing
market demand, national policy and grid statistics. Those figures are
about the industry, not about this building. A figure is only
`site_capacity` if the quote shows it describes THIS development's own
plant, load, or connection.

For each figure, return:
  "finding_id":  the id given
  "verdict":     one of
                 "site_capacity"  - describes this development
                 "market_context" - market/sector demand or supply
                 "policy_target"  - national/regional policy ambition
                 "comparator"     - a different named site or scheme
                 "unclear"        - cannot tell from the quote alone
  "quantity_type": only when site_capacity, else null. One of:
                 "it_load"           - IT/rack load the facility draws
                 "grid_connection"   - contracted or sought grid capacity
                 "onsite_generation" - standby/backup/CHP/renewable plant
                 "cooling"           - cooling system capacity
                 "total_site"        - total site demand where the quote
                                       explicitly says total, not IT-only
                 "other"
  "is_maximum":  true if the quote presents it as an ultimate or consented
                 ceiling rather than one phase; false otherwise; null when
                 not site_capacity
  "reasoning":   one short sentence citing what in the quote decided it

Be strict. If the quote does not make clear that the figure belongs to
this development, use "unclear" rather than guessing. Under-claiming is
recoverable; a wrong site capacity in a published chart is not.

BEFORE deciding whose figure it is, decide whether it is a power
capacity at all. These were all mis-filed as site capacity in an earlier
run of this task, and each put a wrong number in front of a reader:

- **Energy is not power.** "251,859,057.50 kW which equates to
  94,197.29 kWh/m2" is a year's consumption, not a capacity; converted
  it implied a site four times the national grid. A figure whose
  magnitude is absurd for a building — anything above about 3,000 MW —
  is wrong whatever unit it carries. Verdict "unclear".
- **Storage is not generation, and not demand.** A battery or UPS rating
  says how fast it can discharge. Use quantity_type "other" and say so
  in the reasoning; never "onsite_generation".
- **Thermal input is not electrical output.** "a Thermal Input of around
  1.2GW" is fuel entering a plant, typically two to three times the
  electricity leaving it. Verdict "unclear" unless the quote gives an
  electrical figure.
- **A number in a table is not a capacity.** If the quote carries no
  unit at all — "80%% - 480W", "Data Centre 150 210 1,839,600", a row of
  pounds sterling — nothing establishes it is megawatts. Verdict
  "unclear".
- **A substation on a drawing is not a grid connection.** "- 6MW
  Substation 25.4m²" is an equipment schedule; "TEMPORARY 1MW
  SUBSTATION" is a construction supply. A grid connection is capacity
  sought, reserved, contracted or offered.
- **A single unit is not the fleet.** "38 no. 2,640kW generator units"
  is about 100 MW of plant, not 2.6 MW. Where a quote gives both a count
  and a per-unit rating, the figure for this development is the product.
  Where it gives only one machine's spec, say so in the reasoning.

Return strict JSON: {"adjudications": [...]}. No prose outside the JSON.

APPLICATION: %(ref)s
DESCRIPTION: %(desc)s

FIGURES:
%(figures)s
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "adjudications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "integer"},
                    "verdict": {"type": "string", "enum": [
                        "site_capacity", "market_context", "policy_target",
                        "comparator", "unclear"]},
                    # A nullable enum must be expressed as anyOf: pairing
                    # "type": ["string","null"] with an enum containing
                    # null is rejected by the schema validator.
                    "quantity_type": {"anyOf": [
                        {"type": "string", "enum": [
                            "it_load", "grid_connection", "onsite_generation",
                            "cooling", "total_site", "other"]},
                        {"type": "null"}]},
                    "is_maximum": {"type": ["boolean", "null"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["finding_id", "verdict", "quantity_type",
                             "is_maximum", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["adjudications"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# The generation questions (READER_REDESIGN_PLAN §4.1e)
# ---------------------------------------------------------------------------
#
# power-1.0 asked whose figure it is and which quantity it measures. It
# never asked the two questions that decide what an on-site generation
# figure MEANS, and both of them reached readers wrong.
#
# **One machine or the fleet.** A generation figure in these documents is
# one of three things: the rating of a single engine, the combined rating
# of a stated number of engines, or the site's total generating capacity.
# The reader's rollup takes the largest adjudicated figure, so where the
# largest is one machine's rating the panel said "On-site generation
# 3.2 MW" two lines above "112 units". dcp.site_profile.generation_figure
# now labels that case from the passages themselves, and does it well
# enough to ship — six per-unit sites out of 72 — but it is a reading of
# vocabulary and arithmetic, and it can only see what one quote says.
#
# **What kind of plant.** Standby generators run on grid failure and for
# testing; prime movers run to supply the site's load; rooftop PV is
# generation the site cannot dispatch; a battery is not generation at
# all. Elsham Wolds' 50 MW is twenty gas engines that "operate
# continuously to provide electricity" — and the same passage discloses
# "up to 650 no. 2,480 kW back-up diesel generators", which is a
# different kind of plant entirely. Without this distinction any cohort
# built on generation compares a gas power station with a diesel that
# runs twelve hours a year, and the "standby below 10% of stated load"
# cohort the design handoff proposed did exactly that.
#
# Asked here, in the file all three adjudication routes import, under
# their own prompt version — never a second copy of the prompt, and never
# an edit to power-1.0, which is half of the key its 3,974 verdicts are
# stored under.
#
# Nothing is multiplied. The model reports the count and the rating the
# quote states; whether a fleet total belongs in a headline is a
# question for the rollup and for a human, not for the adjudicator.
# The prompt's history, each version kept in data/generation_sample/ as
# evidence. 1.0 answered about the passage rather than the figure on the
# row; 1.1 over-corrected into reading "50 x 3.3 MWt" as 165 MW of
# generation; 1.2 asked the questions in order — is this electricity,
# then whose; 1.3 renamed a value Luke had read as an operator's estate.
#
# 2.0 changes the INPUT, after Luke hand-checked the 1.2 sample and
# scored the model 13/40 on figure basis: "I'm required to judge based
# on the quote alone, but most of those quotes don't provide any context
# — a number sitting below 'site total' and a number below 'plant C
# total' mean different things. So for the most part my answers were,
# correctly, 'unclear'." The model had said site_total or per_unit on
# nearly every one of those; a careful reader could not, and the
# adjudicator must not. So each figure now arrives with the passage
# around it on its page — the paragraph before and after the quote —
# and the person checking the sheet sees the same passage. And the
# vocabulary that misled is renamed: "per_unit" read as a building
# ("at Unit 1"), "fleet_total" read as the whole site's fleet when it
# meant a stated group of engines.
# 2.1: a basis value for what most renewable and energy-centre figures
# are — the rated total of ONE named installation, which the passage does
# not say is the whole site's generation. 2.0 had only "group of
# machines" or "site", and put Graven Hill's rooftop PV into the first
# and Trident Way's solar into the second; Luke's note on the latter was
# "this is the total for renewable sources but that doesn't mean there
# aren't others". Also: smaller requests, because Elsham's fifty-eight
# figures with their passages overran the output budget and the answer
# came back cut off, twice.
#
# 2.2: the two rules Luke's hand-check of the 2.1 sample asked for
# (82% on figure basis, 75% on plant type, and the residue was one
# pattern in two halves). The model drew conclusions from text that is
# not prose — a plant schedule's row of column headings, a generator
# manufacturer's datasheet, the annotations on a general-arrangement
# drawing — where Luke wrote "it's not safe to draw conclusions from
# this raw text, which makes little sense without formatting". And it
# named a duty the passage never stated, reading "prime" from the words
# "energy centre" and "incinerator", and "standby" from a diesel tank
# and from a datasheet's "maximum stand-by power at rated RPM", which
# is a rating class of the product and not this development's duty.
# So: a figure whose support is a fragment is "unclear" unless the
# fragment states the figure itself ("11 x 3.9MW generators" does); and
# plant type comes from duty words attached to the machines this figure
# counts, not from what kind of installation they sit in.
# 2.3: scored 2.2 at 36/40 on figure basis (90%) and 32/40 on plant
# type (80%), and the plant residue was two patterns. A figure that is
# not itself an electrical output — Reading Quarry's 28 MW of heat,
# Elsham's 5,678 kW energy input — had its plant read from the kind of
# installation behind it, where Luke wrote "it's likely that the output
# will be used continuously ... but this isn't made explicit in the
# passage so it should not be trusted". And a figure covering machines
# of two duties at once — Didcot's "30 running, 4 standby" — came back
# "unclear" where the sheet says "mixed", which is the value that
# exists for exactly that case.
# 2.4: two corrections to 2.3, which scored 35/40 basis and 36/40
# plant. The mixed rule's carve-out said the standby-headed group "has
# one duty and the passage contradicts itself about it: that is
# unclear", and the model read the first half and answered
# standby_combustion — the instruction now ends with the answer. And
# the two rules needed an order: a fragment stops at "unclear", but
# prose does not, and "the 50MW of energy produced by the Incinerator"
# is an energy figure the electricity test already settles.
# 2.5: 2.4 fixed KAO and lost Didcot. The carve-out was written to be
# emphatic — "not mixed, and not standby_combustion" — and the model
# applied it to any group with a split inside it, including "IT — 34
# Generators (30 running, 4 standby)", which is the case "mixed" exists
# for. The tell that separates them is the WORD: KAO's passage says
# "standby" twice, as the fleet's duty and again as the spare machines
# within it, and cannot mean both; Didcot's says "running" and
# "standby", which are two duties and no contradiction at all.
GENERATION_PROMPT_VERSION = "generation-2.5"

GENERATION_PROMPT = """\
You are auditing extracted figures from UK planning documents for an
investigative journalism project on data centres.

Every figure below has already been adjudicated as describing THIS
development's own on-site electricity generation. That question is
settled; do not revisit it.

Each figure comes with the QUOTE it was extracted from and the PASSAGE
around that quote on the same page of the same document — the text
before and after, as the page has it. Read the passage. A heading above
a table, the sentence before a number, the unit on a column: that is
where a figure's meaning is, and the quote alone rarely carries it.

Answer two questions about each figure. **Where the passage does not
settle a question, the answer is "unclear".** A person who hand-checked
an earlier version of this task answered "unclear" on most rows given
the quote alone, and was right to; the model that answered "site total"
from the words "Total Installed Capacity" beside a number was not. Do
not infer what a figure is from its size, from the site's name, or from
what data centres usually install.

**You are describing the FIGURE on the row, not the passage.** One
passage often states several figures, and they are not the same kind of
thing. Given "emergency generator sets (currently estimated as 150 x
2MW units)": asked about the figure 300 MW, the answer is
"stated_group_total"; asked about 2 MW, it is "per_generator".

**Ask "is this electricity?" first.** A thermal or fuel input, an annual
energy total, or a battery's discharge rating is "not_generation"
whatever else the passage says about counts and units. "MWt", "thermal
output", "thermal input" and "energy input" are heat; "MWe",
"electrical output" and a bare "MW" beside a generator are electricity.

**Then arithmetic settles it before vocabulary does.** Where the passage
states a count and a per-generator rating whose product is the figure
on the row — within rounding — the figure is "stated_group_total",
however the sentence phrases it.

**A figure whose passage never says what it is a figure of is
"unclear".** Many pages are not prose: a plant schedule's column
headings, a generator manufacturer's datasheet, the annotations on a
drawing, the fields of an application form. Such a fragment settles a
figure only where its OWN labels name what the figure is a figure of —
"11 x 3.9MW generators" gives a count beside a rating; a form's "Solar
energy … Total Installed Capacity (Megawatts) 0.21" names the
installation and gives its total. Where the labels do not, the answer
to BOTH questions is "unclear", however suggestive they are: "GEN
1500kW" on a drawing carrying several differently rated generators,
"Total: 46.9 MW" at the foot of a schedule whose columns mix input
rating, output power and thermal input, "Gross Engine Power Standby kW
(hp) 136.9" in a datasheet of a product, "Energy capacity: 1000
Megawatts" in a form against "battery storage". A passage that is
prose says what it means in a sentence; a passage that is not must be
read for what its labels state and never for what they suggest.

**That rule stops at fragments, and prose goes on to the next test.**
Where the support is a fragment whose labels do not name the figure,
"unclear" is the answer and the reasoning ends. Where it is prose, ask
"is this electricity?" as above and answer accordingly: a sentence that
names the plant and what it produces — "the 50MW of energy produced by
the Incinerator", "generating a thermal output of 28MW" — settles
question 1 as "not_generation", because the sentence never calls the
figure an electrical output. "Unclear" is for a passage that does not
say, not for a sentence that says something other than electricity.

**The figures listed below are all from one application, and you may
read them together.** Where one row's passage settles another row's
figure, say so in the reasoning. The evidence_span must still come from
the passage of the row it belongs to.

**1. What is this figure a figure of?**

  "per_generator"       the rating of ONE generating machine — an
                        engine, a turbine, a generator set. Signalled by
                        "each", "per generator", "no. 2,480 kW
                        generators", or a count stated beside this
                        rating. NOT "per unit" where unit means a
                        building ("at Unit 1", "Units 2-8").
  "stated_group_total"  the combined rating of a STATED number of
                        machines — "20 no. 2,499 kW natural gas engines
                        with a combined capacity of just under 50 MW" is
                        the group total when the figure is the 50 MW.
                        The group may or may not be all the generation
                        on the site; that is not this question.
  "installation_total"  the rated total of ONE named installation or
                        kind of plant, with no count of machines stated
                        and no statement that it is the whole site's
                        generation: "219kW of Photo-Voltaic (PV)
                        panels", "an energy centre with the capacity to
                        generate 49.9 MW", "Total Installed Capacity
                        (Megawatts) 0.21" under a heading for solar.
                        A solar array does not preclude a diesel fleet.
  "site_total"          the total generating capacity of the whole
                        development, all plant — only where the passage
                        says so: "total site capacity", "total on-site
                        generation", "the capacity to generate 49.9 MW
                        on-site". A total for one building, one phase or
                        one kind of plant is not the site's.
  "not_generation"      not an electrical generating capacity at all: a
                        thermal or fuel input, an annual energy figure in
                        kWh or MWh, a battery or UPS rating, a
                        consumption or demand figure.
  "unclear"             the passage does not settle it.

**2. What kind of plant is it?**

  "standby_combustion"  engines or turbines that run on grid failure and
                        for testing — "back-up", "standby", "emergency",
                        "resilience", "life safety".
  "prime_combustion"    combustion plant intended to supply the site's
                        normal load or export: CHP, an energy centre,
                        gas engines that "operate continuously", a gas
                        turbine, energy-from-waste.
  "renewable"           solar PV, wind, hydro, ground/air source heat.
  "storage"             battery, UPS, flywheel. Storage is not
                        generation; it stores what something else made.
  "mixed"               this one figure covers more than one of the
                        above and the passage does not separate them.
  "unclear"             the passage does not say.

**Plant type is about the machines THIS figure counts, and only where
the passage says what they do.** Duty is stated in words — "standby",
"back-up", "emergency", "operate continuously", "supply the site",
"export to the grid". Where the passage names more than one kind of
plant and does not attach its duty words to the machines this figure
counts — twenty gas engines and 650 back-up diesels in one paragraph,
an incinerator and a rooftop array in another — the answer is
"unclear", even where one reading is the likelier. Do not read duty
from the fuel or its tank, from a rating class in a manufacturer's
datasheet ("maximum stand-by power at rated RPM" describes the
product, not this development's duty), or from what kind of
installation the machines sit in. Where the passage's own duty words
disagree — "standby generators", of which "nine serve the load and two
are standby" — that is "unclear" too.

**Where question 1 is "not_generation", plant type is "unclear" unless
the passage says in duty words what the machines do.** A thermal
output, an energy or fuel input, an annual total: the machines behind
such a figure have a kind, but the figure is not their electrical
rating and the passage rarely stops to say how they run. "will provide
standby power ... in the case of an emergency power outage" states the
duty and settles it; "the electrical output from the ERC will be used
to supply the proposed data centre" says where the electricity goes,
which is not the same statement, and the answer stays "unclear".

**A figure covering machines of two duties at once is "mixed".** Where
the passage states that the machines this figure counts include both
machines that run and machines held in reserve — "IT — 34 Generators
(30 running, 4 standby)" — the one figure covers more than one duty,
and "mixed" is the value for that. Two different duty words are two duties; the
SAME word twice is a contradiction. "IT — 34 Generators (30 running, 4
standby)" names running machines and reserve machines, and the figure
covering both is "mixed". "11 standby generator sets", of which "nine
serve the load and two are standby", uses "standby" once for the
fleet and again for the spares inside it, so the passage cannot be
read either way: that one is "unclear".

Also return, when and only when the passage states them:
  "unit_count"      how many machines the passage names (an integer).
                    "up to 650" is 650.
  "unit_rating_mw"  the rating of one machine, in MW, converting from kW
                    where the passage is in kW.
  Never multiply them, and never compute one from the other. If the
  passage gives one and not the other, return null for the other.

And for every figure:
  "evidence_span"   the shortest VERBATIM run of characters from the
                    PASSAGE that decides question 1 and question 2 —
                    copied exactly, not paraphrased, not re-punctuated.
                    A span that does not appear in the passage character
                    for character is treated as a failure and the answer
                    is not stored.
  "reasoning"       one short sentence naming what in the passage
                    decided it — or, for "unclear", what is missing.

Return strict JSON: {"generation": [...]}. No prose outside the JSON.

APPLICATION: %(ref)s
DESCRIPTION: %(desc)s

FIGURES:
%(figures)s
"""

GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "generation": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "integer"},
                    "figure_basis": {"type": "string", "enum": [
                        "per_generator", "stated_group_total",
                        "installation_total", "site_total",
                        "not_generation", "unclear"]},
                    "plant_type": {"type": "string", "enum": [
                        "standby_combustion", "prime_combustion",
                        "renewable", "storage", "mixed", "unclear"]},
                    "unit_count": {"type": ["integer", "null"]},
                    "unit_rating_mw": {"type": ["number", "null"]},
                    "evidence_span": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["finding_id", "figure_basis", "plant_type",
                             "unit_count", "unit_rating_mw", "evidence_span",
                             "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["generation"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# The label audit (§4.1e): does a finding's family match what it says?
# ---------------------------------------------------------------------------
#
# Here rather than in its own file because of the standing rule in §3:
# any new adjudication question extends the one prompt file every route
# imports, under its own version, never a second copy.
#
# The question is narrow on purpose. It is NOT "what is this finding
# about" — re-extracting 10,605 rows would invite a second opinion on
# work that is already stored with its quote. It is "does the family
# this row is filed under fit its text", which has a defensible default:
# leave it alone.
#
# Which is the whole shape of the loss here. A flag REMOVES a row from
# the evidence a reader sees under a family. A row wrongly flagged costs
# a reporter a real quote they would have read; a row wrongly left costs
# them a moment working out why landscape prose is filed under IT load.
# The first is worse, so `unclear` is a first-class answer and the
# prompt says to reach for it (Luke, 2026-08-24: better unclear than
# wrong).
LABEL_AUDIT_PROMPT_VERSION = "label-1.0"

LABEL_AUDIT_PROMPT = """\
You are auditing how extracted findings from UK planning documents have
been filed, for an investigative journalism project on data centres.

Each finding below was extracted by another model, which named what it
had found in its own words (the LABEL) and quoted the text it found it
in (the TEXT). Those free-text labels were then mapped into a fixed set
of families, and the FAMILY on each row is the result.

Your question is only this: **does the family fit the text?**

You are not asked what the finding is about, and you are not asked
whether the label is the best one. A row is filed correctly if a
reporter looking under that family would expect to find this text
there.

%(vocabulary)s

Answer for each finding:

  "verdict"
    "fits"          the text belongs under this family.
    "does_not_fit"  the text plainly belongs under a different family —
                    it is about another subject entirely, not merely a
                    less good match. Name that family.
    "unclear"       the text does not settle it: it is too short, too
                    generic, spans several subjects, or is a fragment
                    that could sit under more than one family.

**Reach for "unclear" rather than "does_not_fit" whenever you hesitate.**
A "does_not_fit" verdict removes this text from what a reporter reads
under that family, and a quote wrongly removed is worse than a quote
filed under an imperfect heading. A text that mentions several subjects
FITS the family of any of them.

  "suggested_family"  only for "does_not_fit": the family it belongs
                      under, from the list above. Null otherwise.
  "evidence_span"     the shortest VERBATIM run of characters from the
                      finding's own TEXT that decides it — copied
                      exactly. A span that does not appear in the text
                      character for character is treated as a failure.
  "reasoning"         one short sentence naming what in the text decided
                      it.

Return strict JSON: {"labels": [...]}. No prose outside the JSON.

FINDINGS:
%(findings)s
"""

LABEL_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "integer"},
                    "verdict": {"type": "string",
                                "enum": ["fits", "does_not_fit", "unclear"]},
                    "suggested_family": {"type": ["string", "null"]},
                    "evidence_span": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["finding_id", "verdict", "suggested_family",
                             "evidence_span", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def render_label_findings(rows: list[dict]) -> str:
    """The findings block of LABEL_AUDIT_PROMPT: the family on trial, the
    extractor's own label, and the text it is filed against."""
    out = []
    for r in rows:
        text = " ".join((r["value_text"] or "").split())
        out.append(f'- finding_id {r["finding_id"]}\n'
                   f'  family: {r["signal_family"]}\n'
                   f'  label: {r["signal_type"]}\n'
                   f'  text: "{text}"')
    return "\n".join(out)


# The universe of the generation questions: every finding some route has
# adjudicated as this development's own on-site generation. DISTINCT ON
# picks one verdict per finding the way the reader's rollup does, so the
# batch asks about exactly the rows a reader can see.
GENERATION_CANDIDATES_SQL = """
WITH adj AS (
  SELECT DISTINCT ON (finding_id) finding_id, verdict, quantity_type,
         value_mw, application_id
  FROM power_adjudication
  ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC, id DESC)
SELECT s.site_key, s.display_name, adj.application_id, a.application_ref,
       coalesce(a.description, ''), adj.finding_id, f.document_id,
       f.signal_type, adj.value_mw, f.value_number, f.value_unit,
       coalesce(f.value_text, ''), coalesce(f.evidence_text, ''),
       f.evidence_page, d.content_sha256
FROM adj
JOIN findings f ON f.id = adj.finding_id
JOIN applications a ON a.id = adj.application_id
LEFT JOIN documents d ON d.id = f.document_id
JOIN site_members sm ON sm.application_id = adj.application_id
     AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id
WHERE s.retired_at IS NULL
  AND adj.verdict = 'site_capacity'
  AND adj.quantity_type = 'onsite_generation'
  AND adj.value_mw IS NOT NULL AND adj.value_mw > 0
ORDER BY s.site_key, adj.value_mw DESC, adj.finding_id
"""


# How much of the page to show around a quote. A paragraph either side:
# enough for a table's heading and a sentence's subject, not so much
# that a page of forty figures is sent forty times.
PASSAGE_BEFORE = 700
PASSAGE_AFTER = 500


def passage_for(quote: str, page_text: str,
                before: int = PASSAGE_BEFORE, after: int = PASSAGE_AFTER) -> str:
    """The quote with the page around it, or the quote alone when the
    quote cannot be found on the page (an OCR difference, a page that
    was never cached). Whitespace normalised, nothing else."""
    page = " ".join((page_text or "").split())
    q = " ".join((quote or "").split())
    if not page or not q:
        return q
    i = page.lower().find(q.lower())
    if i < 0:
        # Try the first half of the quote: extraction sometimes trims
        # the end of a sentence differently from the page.
        head = q[: max(30, len(q) // 2)]
        i = page.lower().find(head.lower())
        if i < 0:
            return q
    start, end = max(0, i - before), min(len(page), i + len(q) + after)
    out = page[start:end]
    if start > 0:
        out = "…" + out
    if end < len(page):
        out = out + "…"
    return out


def render_generation_figures(figures: list[dict]) -> str:
    """The figures block of GENERATION_PROMPT: each figure, its quote,
    and the passage around the quote on its page.

    `figures` carry `passage` where the route could find the page; the
    quote alone otherwise, and the block says which. A span the model
    must copy verbatim cannot be asked for from text it was not shown,
    so the whole passage goes in untruncated.
    """
    out = []
    for f in figures:
        quote = " ".join((f["evidence_text"] or "").split())
        passage = f.get("passage") or quote
        out.append(
            f'- finding_id {f["finding_id"]}: {float(f["value_mw"]):g} MW '
            f'(as extracted: {f["value_number"]:g} {f["value_unit"]}; '
            f'label: {f["signal_type"]})\n'
            f'  quote: "{quote}"\n'
            + (f'  passage: "{passage}"' if passage != quote else
               '  passage: (the page could not be read; the quote is all there is)'))
    return "\n".join(out)


def verify_span(span: str, quote: str) -> bool:
    """Is `span` a verbatim run of `quote`, ignoring how it was wrapped?

    The findings gate's rule, applied to a classification rather than a
    figure: whitespace differs between a PDF's line breaks and a model's
    copy of them, so it is normalised on both sides; nothing else is.
    An empty span verifies against nothing.
    """
    if not span or not span.strip():
        return False
    return " ".join(span.split()) in " ".join((quote or "").split())



def load_candidates(conn) -> dict[int, dict]:
    """Power-ish findings grouped by application, excluding any already
    adjudicated under this model+prompt_version."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT f.application_id, a.application_ref,
                   coalesce(a.description, ''), f.id, f.document_id,
                   f.signal_type, f.value_number, f.value_unit,
                   f.value_text, f.evidence_text
            FROM findings f
            JOIN applications a ON a.id = f.application_id
            WHERE f.value_number IS NOT NULL
              AND lower(f.value_unit) = ANY(%s)
              AND NOT EXISTS (
                    SELECT 1 FROM power_adjudication p
                    WHERE p.finding_id = f.id AND p.model = %s
                      AND p.prompt_version = %s)
            ORDER BY f.application_id, f.value_number DESC""",
            (list(TO_MW) + list(APPARENT), MODEL, PROMPT_VERSION))
        rows = cur.fetchall()

    apps: dict[int, dict] = {}
    for (app_id, ref, desc, fid, doc_id, stype, num, unit,
         vtext, evidence) in rows:
        app = apps.setdefault(app_id, {"application_id": app_id, "ref": ref,
                                       "desc": desc[:400], "figures": []})
        app["figures"].append({
            "finding_id": fid, "document_id": doc_id, "signal_type": stype,
            "value_number": float(num), "value_unit": unit,
            "value_text": vtext, "evidence_text": evidence,
        })
    return apps


def render_figures(figures: list[dict]) -> str:
    out = []
    for f in figures:
        quote = (f["evidence_text"] or "").replace("\n", " ")[:300]
        out.append(
            f'- finding_id {f["finding_id"]}: {f["value_number"]:g} '
            f'{f["value_unit"]} (label: {f["signal_type"]}; '
            f'value: {(f["value_text"] or "")[:80]})\n'
            f'  quote: "{quote}"')
    return "\n".join(out)


def build_requests(apps: dict[int, dict]) -> list[dict]:
    reqs = []
    for app_id, app in apps.items():
        # Cap per request: a handful of applications carry hundreds of
        # figures; split them so no single prompt gets unwieldy.
        figs = app["figures"]
        for i in range(0, len(figs), 60):
            chunk = figs[i:i + 60]
            content = PROMPT % {"ref": app["ref"], "desc": app["desc"],
                                "figures": render_figures(chunk)}
            reqs.append({
                "custom_id": f"{app_id}-{i // 60}",
                "params": {
                    "model": MODEL, "max_tokens": 8000,
                    "output_config": {"format": {"type": "json_schema",
                                                 "schema": SCHEMA}},
                    "messages": [{"role": "user", "content": content}],
                },
            })
    return reqs


def do_measure(submit: bool = False) -> None:
    with db.connect() as conn:
        apps = load_candidates(conn)
    reqs = build_requests(apps)
    n_figs = sum(len(a["figures"]) for a in apps.values())
    print(f"{len(apps)} applications, {n_figs} candidate figures, "
          f"{len(reqs)} requests")
    if not reqs:
        return

    # Measure real tokens rather than guessing from characters — the
    # bulk pass taught that lesson at a cost of $150.
    import anthropic
    client = anthropic.Anthropic()
    sample = reqs[:min(25, len(reqs))]
    counted = 0
    for r in sample:
        counted += client.messages.count_tokens(
            model=MODEL, messages=r["params"]["messages"]).input_tokens
    mean_in = counted / len(sample)
    total_in = mean_in * len(reqs)
    # Output is one small object per figure; measured shape ~60 tokens each.
    total_out = n_figs * 60
    cost = total_in / 1e6 * 1.0 + total_out / 1e6 * 5.0
    print(f"measured mean input: {mean_in:,.0f} tokens/request "
          f"(sampled {len(sample)})")
    print(f"projected: {total_in/1e6:.2f}M input + ~{total_out/1e6:.2f}M "
          f"output -> ${cost:,.2f} at Sonnet batch rates")
    if not submit:
        print("\n(measurement only — nothing spent; re-run with --submit)")
        return

    batch = client.messages.batches.create(requests=reqs)
    STATE_PATH.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "applications": {str(k): {"application_id": v["application_id"],
                                  "figures": v["figures"]}
                         for k, v in apps.items()},
    }, indent=1))
    print(f"submitted {batch.id} ({batch.processing_status})")


def do_collect() -> None:
    if not STATE_PATH.exists():
        print("no batch state — run --submit first")
        return
    state = json.loads(STATE_PATH.read_text())
    if state.get("collected"):
        print("already collected")
        return

    import anthropic
    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        c = batch.request_counts
        print(f"{state['batch_id']}: {batch.processing_status} "
              f"(succ {c.succeeded}, err {c.errored}, proc {c.processing})")
        return

    # finding_id -> its original metadata, for units and provenance.
    by_finding: dict[int, dict] = {}
    for app in state["applications"].values():
        for f in app["figures"]:
            by_finding[f["finding_id"]] = f

    inserted = skipped = 0
    with db.connect() as conn, conn.cursor() as cur:
        for result in client.messages.batches.results(state["batch_id"]):
            if result.result.type != "succeeded":
                continue
            msg = result.result.message
            if msg.stop_reason == "refusal":
                continue
            text = next((b.text for b in msg.content if b.type == "text"), "")
            try:
                adjs = json.loads(text).get("adjudications", [])
            except Exception:
                continue
            app_id = int(result.custom_id.rsplit("-", 1)[0])
            for a in adjs:
                fid = a.get("finding_id")
                meta = by_finding.get(fid)
                if meta is None:
                    skipped += 1
                    continue
                unit = (meta["value_unit"] or "").lower()
                value_mw = unit_note = None
                if a.get("verdict") == "site_capacity":
                    if unit in TO_MW:
                        value_mw = meta["value_number"] * TO_MW[unit]
                    elif unit in APPARENT:
                        unit_note = ("apparent power (kVA/MVA); not "
                                     "converted to MW — power factor unknown")
                cur.execute("""
                    INSERT INTO power_adjudication (application_id,
                        finding_id, document_id, verdict, quantity_type,
                        value_mw, value_original, unit_original, unit_note,
                        is_maximum, reasoning, model, prompt_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (finding_id, model, prompt_version)
                    DO NOTHING""",
                    (app_id, fid, meta["document_id"], a.get("verdict"),
                     a.get("quantity_type"), value_mw, meta["value_number"],
                     meta["value_unit"], unit_note, a.get("is_maximum"),
                     (a.get("reasoning") or "")[:600], MODEL,
                     PROMPT_VERSION))
                inserted += 1
        conn.commit()
    state["collected"] = True
    STATE_PATH.write_text(json.dumps(state, indent=1))
    print(f"inserted {inserted} adjudications"
          + (f" ({skipped} referenced unknown finding_ids)" if skipped else ""))


def do_report() -> None:
    """Per-site power profile, highest IT load first."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key, s.display_name, p.quantity_type,
                   max(p.value_mw) AS mw, count(*) AS n
            FROM power_adjudication p
            JOIN site_members sm ON sm.application_id = p.application_id
            JOIN sites s ON s.id = sm.site_id
            WHERE p.verdict = 'site_capacity' AND p.value_mw IS NOT NULL
              AND s.retired_at IS NULL
            GROUP BY s.site_key, s.display_name, p.quantity_type
            ORDER BY s.site_key, p.quantity_type""")
        rows = cur.fetchall()
    sites: dict[str, dict] = {}
    for site_key, name, qty, mw, n in rows:
        s = sites.setdefault(site_key, {"name": name})
        s[qty] = float(mw)
    order = sorted(sites.items(),
                   key=lambda kv: -(kv[1].get("it_load")
                                    or kv[1].get("total_site")
                                    or kv[1].get("grid_connection") or 0))
    print(f"{'site':38} {'IT load':>9} {'grid':>9} {'gen':>9}")
    for key, s in order[:40]:
        print(f"{(s['name'] or key)[:38]:38} "
              f"{s.get('it_load', float('nan')):9.1f} "
              f"{s.get('grid_connection', float('nan')):9.1f} "
              f"{s.get('onsite_generation', float('nan')):9.1f}")
    print(f"\n{len(sites)} sites with at least one adjudicated capacity")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.measure or args.submit:
        do_measure(submit=args.submit)
    elif args.collect:
        do_collect()
    elif args.report:
        do_report()
    else:
        print("pass --measure, --submit, --collect or --report")


if __name__ == "__main__":
    main()
