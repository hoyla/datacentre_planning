"""Refuse to build an artefact from adjudications nobody has corrected.

Six families of quantity-type error live in the gap between "whose figure
is this" (which power adjudication asks) and "what kind of quantity is
this" (which nothing asked until 2026-08-10). They are all correctable —
scripts/correct_adjudications.py does it idempotently — and correcting
them is a step someone has to remember.

This is the mechanism that replaces the remembering. Every export calls
`require_corrected()` before it writes anything, and if uncorrected
adjudications exist the build stops with the command that fixes it. The
same shape as .githooks/pre-push and the self-checks in migrations 017
and 018, both of which caught real mistakes today that review did not.

Why a gate rather than just running the correction automatically: the
corrections demote figures and change what sites report. A build should
not silently alter the dataset it is publishing. It should stop and say
so, and let a person run the correction and look at what moved.
"""

from __future__ import annotations

import sys

from dcp import db

# One row per rule in scripts/correct_adjudications.py. Kept as SQL here
# rather than imported from the script because this module must be
# importable by every export without pulling in argparse machinery — and
# because a gate that shares its predicate with the thing it guards can
# fail in the same direction. tests/test_adjudication_gate.py asserts the
# two stay in step.
UNCORRECTED_SQL = r"""
SELECT count(*) FROM power_adjudication pa
JOIN findings f ON f.id = pa.finding_id
WHERE pa.verdict = 'site_capacity'
  AND (
    (coalesce(pa.unit_note,'') NOT LIKE '%[energy_not_power]%'
     AND pa.value_mw > 3000)
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[storage_not_generation]%'
     AND pa.quantity_type IN ('onsite_generation','grid_connection')
     AND f.evidence_text ~* '\ybatter|\ybess\y|energy storage|\yups\y|uninterruptible'
     AND f.evidence_text !~* 'transformer|substation containing')
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[thermal_not_electrical]%'
     AND pa.quantity_type IN ('onsite_generation','it_load','total_site')
     AND (f.evidence_text ~* 'thermal input|heat input|calorific|fuel input'
          OR f.signal_type ~* 'thermal_input|heat_input'))
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[headerless_table_row]%'
     AND length(f.evidence_text) > 0
     AND (length(regexp_replace(f.evidence_text,'[^0-9]','','g'))::float
          / length(regexp_replace(btrim(f.evidence_text),'\s+',' ','g'))) > 0.30
     AND (SELECT count(*) FROM unnest(regexp_split_to_array(
            lower(f.evidence_text),'[^a-z]+')) AS w WHERE length(w) >= 3) < 8
     AND f.evidence_text !~* '\d[\d,.]*\s*(mw|kw|gw|mva|kva|mwe)\y')
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[temporary_supply]%'
     AND pa.quantity_type = 'grid_connection'
     AND f.evidence_text ~* '\ytemporar')
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[equipment_label_not_connection]%'
     AND pa.quantity_type = 'grid_connection'
     AND f.evidence_text ~* 'floor plan|sections drawing|figure\s+[0-9]|substation\s+[0-9.]+\s*m²|legacy')
  )
"""

MESSAGE = """\
Refusing to build: {n} adjudications have not been through the
quantity-type corrections.

Power adjudication decides whose figure something is. It does not decide
what KIND of quantity it is, and six families of error live there — a
battery counted as generation, thermal input counted as electrical
output, a headerless table row counted as a capacity, a temporary
construction supply counted as a grid connection. Every one of them put
a wrong number in front of a reader on 2026-08-10, including a 251,859
MW site and an Amazon campus described as grid-dependent when its
documents describe 100 MW of standby plant.

Run:

    scripts/correct_adjudications.py --dry-run   # see what would change
    scripts/correct_adjudications.py             # apply it

then look at what moved before rebuilding:

    scripts/consumption_integrity.py
    scripts/generation_integrity.py

This build is not blocked because the corrections are hard. It is blocked
because they are easy to forget, and forgetting is silent.
"""


def uncorrected_count(conn=None) -> int:
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(UNCORRECTED_SQL)
            return cur.fetchone()[0]
    with db.connect() as c, c.cursor() as cur:
        cur.execute(UNCORRECTED_SQL)
        return cur.fetchone()[0]


def require_corrected(conn=None, *, allow_override: bool = True) -> None:
    """Stop the build if uncorrected adjudications exist.

    `--i-know-the-adjudications-are-uncorrected` exists for the one
    legitimate case: rebuilding deliberately mid-investigation to look at
    something. It is deliberately long to type.
    """
    if allow_override and "--i-know-the-adjudications-are-uncorrected" in sys.argv:
        print("WARNING: building over uncorrected adjudications, by request.")
        return
    n = uncorrected_count(conn)
    if n:
        sys.exit(MESSAGE.format(n=n))
