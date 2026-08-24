#!/usr/bin/env python3
"""Apply the quantity-type corrections to every adjudication, always.

Power adjudication asks one question — is this figure about this
development — and answers it well. It never asks what KIND of quantity
the figure is, and four families of error live in that gap. Each was
found by hand on 2026-08-10 and fixed by a migration; each migration is
a one-off with a hardcoded guard, which makes it a record of what
happened rather than a defence against it happening again.

This is the defence. It is idempotent, it is safe to run repeatedly, and
it must run after every adjudication pass, because every pass reproduces
the same errors: the prompt has not changed, and the corpus is full of
the same material. The tail batch submitted on 2026-08-10 carried 337
battery figures, 153 thermal-input figures, 52 energy-shaped figures and
44 temporary supplies into an adjudicator with no vocabulary for any of
them.

The four families, in the order they were found:

**energy is not power** (migration 015). An ARK document gives a load as
"251,859,057.50 kW which equates to 94,197.29 kWh/m2" — the unit says
power, the cross-reference says energy. Converted, it implied a site
four times the size of the national grid.

**storage and heat are not generation** (016). A 1,000 MW battery is a
discharge rating; 1.2 GW of "Thermal Input" is fuel entering a plant,
not electricity leaving it. Both were filed under on-site generation,
which is the second most important figure in the project.

**a table row is not a capacity** (017). "80% - 480W" became 480 MW; a
table of pounds sterling became a 384 MW IT load. A quote with no unit
in it cannot establish that its number is megawatts.

**a substation on a drawing is not a grid connection** (018).
"- 6MW Substation       25.4m²" is a drawing schedule complete with the
substation's floor area; "TEMPORARY 1MW SUBSTATION" is a construction
supply.

Nothing here deletes. Verdicts are demoted to `unclear` or moved to an
honest quantity type; findings, quotes and original values are
untouched. What goes is only the claim that a number is this site's
power capacity.

    scripts/correct_adjudications.py --dry-run
    scripts/correct_adjudications.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

# Note \y, not \b: in PostgreSQL regular expressions \b is a backspace
# and \y is the word boundary. Written with \b these predicates match
# nothing at all, which on 2026-08-10 demoted 261 rows instead of 116 and
# needed a restore from backup. Note also \s+ rather than a literal
# space: text lifted from PDFs reads "Substation       25.4m²".
RULES = [
    # (name, set-clause, extra predicate, human note)
    ("energy_not_power",
     "verdict='unclear', quantity_type=NULL, value_mw=NULL, is_maximum=NULL",
     # Magnitude, not vocabulary. Two drafts of this rule tried to spot
     # the energy/power confusion in the text and both produced only
     # false positives: "energy centre capacity 47MW" is power, and so
     # are "168 MW IT * 1.3 = 218.4 MW or 1,910 GWh" and "4000 GWh/year
     # = 456 MW continuous load", where the document supplies both
     # quantities deliberately. What actually distinguished the one real
     # case was that 251,859,057 kW is four times the national grid.
     # No announced data centre campus anywhere approaches 3 GW, so that
     # is the test — a figure this large is wrong whatever its words say.
     r"""pa.value_mw > 3000""",
     "figure is annual energy, not power"),

    ("storage_not_generation",
     "quantity_type='energy_storage'",
     # Evidence, not signal type — two transformer rows ("a Substation
     # containing two 78.5 MVA") reached this rule through their label
     # alone. A transformer is not storage.
     r"""pa.quantity_type IN ('onsite_generation','grid_connection')
         AND f.evidence_text ~* '\ybatter|\ybess\y|energy storage|\yups\y|uninterruptible'
         AND f.evidence_text !~* 'transformer|substation containing'""",
     "storage or UPS discharge rating, not generation"),

    ("thermal_not_electrical",
     "quantity_type='thermal_input'",
     r"""pa.quantity_type IN ('onsite_generation','it_load','total_site')
         AND (f.evidence_text ~* 'thermal input|heat input|calorific|fuel input'
              OR f.signal_type ~* 'thermal_input|heat_input')""",
     "thermal or fuel input, not electrical capacity"),

    ("thermal_output_not_electrical",
     "quantity_type='thermal_input'",
     # A CHP or generator fleet has two outputs and the documents name
     # both: "a thermal output of over 800mw and nearly 300MWe". Storing
     # the larger one as generation put 800 MW of on-site generation on a
     # 256 MW site — the electrical truth is 300.
     #
     # The sibling rule above matches 'thermal input', which is fuel
     # going in, and cannot see this: thermal OUTPUT is heat coming out,
     # and it is equally not electricity. Matching the words alone would
     # be wrong — 68 rows say 'thermal output' and most are the correctly
     # stored electrical figure from a sentence that mentions both. What
     # identifies a mis-stored one is arithmetic, not vocabulary: the
     # quote gives an explicit MWe figure and we stored something larger,
     # so what we stored is the thermal number. Measured 2026-08-11: 2
     # rows, both genuine, no false positives.
     r"""pa.quantity_type IN ('onsite_generation','it_load','total_site')
         AND f.evidence_text ~* 'thermal output|heat output'
         AND f.evidence_text ~* '[0-9][0-9.,]*\s*MWe'
         AND pa.value_mw > substring(f.evidence_text
                                     from '([0-9][0-9.,]*)\s*MWe')::numeric""",
     "thermal output; the same sentence gives the electrical figure in MWe"),

    # The premise, because a rule is a claim about the world: **a figure
    # the document itself calls a thermal or heat output is not this
    # site's electrical generation, and where the quote never names an
    # electrical quantity there is nothing to weigh it against.**
    #
    # Agreed with Luke 2026-08-24, after §4.1e read all 1,667 generation
    # figures against their passages.
    #
    # The sibling rule above cannot see these: it needs an MWe figure in
    # the same quote to weigh against, which is what makes it safe on the
    # 68 rows that say "thermal output" while correctly storing the
    # electrical number. This rule takes the complement — a thermal or
    # heat output with NO electrical quantity anywhere in the quote — and
    # is safe for the opposite reason: there is no electrical figure in
    # the sentence because the sentence is not about electricity.
    #
    # North Hyde Gardens holds both kinds and is the reason the guard is
    # written this way. One quote there is an EIA screening threshold —
    # "a collective combustion installation of more than 300mw of heat
    # output" — and moves. Another says "100 generators across the site
    # giving a thermal output of over 800mw and nearly 300MWe", where the
    # stored 300 is the electrical figure and must stay. A rule matching
    # "thermal output" alone would have taken the site's real generation
    # figure with the threshold.
    #
    # Measured before filing, 2026-08-24: 25 rows, hand-read, no false
    # positives. They are EIA screening thresholds ("a collective
    # combustion installation of more than 300mw of heat output"), a
    # consenting threshold ("the proposed energy centre has a thermal
    # output greater than 50MW"), an incinerator's heat beside an
    # electrical figure that lives in a different quote, and a CHP unit's
    # 308 kW of heat.
    ("thermal_output_with_no_electrical_figure",
     "quantity_type='thermal_input'",
     r"""pa.quantity_type IN ('onsite_generation','it_load','total_site')
         AND f.evidence_text ~* 'thermal output|heat output'
         AND f.evidence_text !~* '[0-9][0-9.,]*\s*(MWe|kWe)|electrical (output|power|capacity)|electricity generat'""",
     "thermal or heat output; the quote names no electrical quantity"),

    ("headerless_table_row",
     "verdict='unclear', quantity_type=NULL, value_mw=NULL, is_maximum=NULL",
     r"""length(f.evidence_text) > 0
         AND (length(regexp_replace(f.evidence_text,'[^0-9]','','g'))::float
              / length(regexp_replace(btrim(f.evidence_text),'\s+',' ','g'))) > 0.30
         AND (SELECT count(*) FROM unnest(regexp_split_to_array(
                lower(f.evidence_text),'[^a-z]+')) AS w WHERE length(w) >= 3) < 8
         AND f.evidence_text !~* '\d[\d,.]*\s*(mw|kw|gw|mva|kva|mwe)\y'""",
     "table row with no headers and no unit"),

    ("temporary_supply",
     "verdict='unclear', quantity_type=NULL, value_mw=NULL, is_maximum=NULL",
     r"""pa.quantity_type='grid_connection' AND f.evidence_text ~* '\ytemporar'""",
     "temporary construction supply, not the completed connection"),

    ("equipment_label_not_connection",
     "verdict='unclear', quantity_type=NULL, value_mw=NULL, is_maximum=NULL",
     r"""pa.quantity_type='grid_connection'
         AND f.evidence_text ~* 'floor plan|sections drawing|figure\s+[0-9]|substation\s+[0-9.]+\s*m²|legacy'""",
     "equipment label or another scheme's plant, not this connection"),

    # The premise, because a rule is a claim about the world: **a figure
    # is not this development's capacity when the same document states
    # the development's capacity as something else, three times, in the
    # decision-maker's own conclusions.**
    #
    # Unlike every rule above this one, this is an instance and not a
    # family, and it is pinned to one value in one sentence deliberately.
    # The general form was written and measured first: demote a
    # site_capacity figure whose document also holds a site_capacity
    # figure five times smaller, where the quote talks of need, demand or
    # a forecast. It matched 64 rows and was wrong on about 62 of them —
    # "Maximum power demand ≈ 450 MW", "210MW IT capacity", "The peak
    # demand is estimated to be 106 MW" are all real capacities, and
    # "an IT capacity of around 72 MW towards demand in the SAZ" is a
    # real capacity described in exactly the rejected phrasing. Need and
    # demand are the ordinary vocabulary of a capacity statement. The
    # general rule is not available; this specific figure still has to go.
    #
    # PL/21/4429/OA, appeal decision, paragraph 32: "the urgent need for
    # data centres up until 2027 (this proposal would contribute of
    # 2240MW towards this need)". The sentence is broken — "contribute
    # of" — and the same document says at paragraph 59 "The total power
    # requirement of the appeal proposal is anticipated to be 147MW",
    # at 37 "The 147MW, which the appeal proposal will deliver", and at
    # 59 again "would deliver around 147MW towards the anticipated
    # demand of 1730MW in the SAZ". The nearest real 2,2xx figure in the
    # document is the appellant's London forecast of 2,248MW-3,082MW at
    # paragraph 21. So 2240 belongs to the need side of that sentence.
    #
    # Demoted to `unclear` rather than moved to `market_context`: what
    # the document rules out is that this is the proposal's capacity, not
    # what the number actually counts. The adjudicator reached `unclear`
    # on one of its three passes over this same sentence unaided.
    ("contradicted_by_own_document",
     "verdict='unclear', quantity_type=NULL, value_mw=NULL, is_maximum=NULL",
     r"""pa.value_mw = 2240
         AND f.evidence_text ~* 'contribute.{0,12}2240\s*MW'""",
     "the same document states this proposal as 147MW; 2240MW is the "
     "need it contributes towards, not the contribution"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = 0
    with db.connect() as conn, conn.cursor() as cur:
        for name, set_clause, pred, note in RULES:
            # Only rows still asserting a capacity, and only those this
            # rule has not already corrected — that is what makes
            # re-running a no-op rather than a second helping of notes.
            where = f"""pa.verdict='site_capacity'
                        AND coalesce(pa.unit_note,'') NOT LIKE '%%[{name}]%%'
                        AND ({pred})"""
            cur.execute(f"""SELECT count(*) FROM power_adjudication pa
                            JOIN findings f ON f.id=pa.finding_id
                            WHERE {where}""")
            n = cur.fetchone()[0]
            total += n
            print(f"  {name:32} {n:>5} {'would be' if args.dry_run else ''} "
                  f"corrected  ({note})")
            if n and not args.dry_run:
                # The note is a bound parameter, not interpolated. One of
                # these reads "another scheme's plant", and an apostrophe
                # inside a single-quoted SQL literal ends the string. It
                # went unnoticed because the rule matched zero rows on the
                # first run and the UPDATE is skipped when the count is
                # zero -- so the bug waited for the first batch that
                # actually triggered it.
                cur.execute(f"""
                    UPDATE power_adjudication pa
                       SET {set_clause},
                           unit_note = coalesce(pa.unit_note || ' ', '')
                                       || %s
                      FROM findings f
                     WHERE f.id = pa.finding_id AND {where}""",
                    (f"[{name}] {note}",))
        if not args.dry_run:
            conn.commit()

    print(f"\n{total} adjudications {'would be' if args.dry_run else ''} "
          f"corrected")
    if not args.dry_run and total:
        print("re-run to confirm it is now a no-op")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
