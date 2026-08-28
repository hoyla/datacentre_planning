"""Refuse to build an artefact from adjudications nobody has corrected.

Six families of quantity-type error live in the gap between "whose figure
is this" (which power adjudication asks) and "what kind of quantity is
this" (which nothing asked until 2026-08-10), and one figure sits here
that is not a family at all: a single sentence whose own document
contradicts it, guarded by value because no general rule survived
measurement. They are all correctable —
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
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[thermal_output_not_electrical]%'
     AND pa.quantity_type IN ('onsite_generation','it_load','total_site')
     AND f.evidence_text ~* 'thermal output|heat output'
     AND f.evidence_text ~* '[0-9][0-9.,]*\s*MWe'
     AND pa.value_mw > substring(f.evidence_text
                                 from '([0-9][0-9.,]*)\s*MWe')::numeric)
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[thermal_output_with_no_electrical_figure]%'
     AND pa.quantity_type IN ('onsite_generation','it_load','total_site')
     AND f.evidence_text ~* 'thermal output|heat output'
     AND f.evidence_text !~* '[0-9][0-9.,]*\s*(MWe|kWe)|electrical (output|power|capacity)|electricity generat')
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
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[voltage_not_capacity]%'
     AND pa.quantity_type IN ('grid_connection','total_site_power','it_load')
     AND pa.value_mw < 1
     AND f.evidence_text ~* '\y(11|33|66|132|275|400)\s*k[VW]\y'
     AND f.evidence_text ~* '\y(overhead|line|cable|circuit|feeder|network)\y')
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[equipment_label_not_connection]%'
     AND pa.quantity_type = 'grid_connection'
     AND f.evidence_text ~* 'floor plan|sections drawing|figure\s+[0-9]|substation\s+[0-9.]+\s*m²|legacy')
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[export_limit_not_connection]%'
     AND pa.quantity_type = 'grid_connection' AND pa.value_mw IS NOT NULL
     AND (f.evidence_text ~* ('\y(export|exporting|exported)\y[^.;]{0,80}\y'
            || replace(trim(trailing '.' from trim(trailing '0'
                 from pa.value_mw::text)), '.', '\.') || '\s*MWe?\y')
          OR f.evidence_text ~* ('\y'
            || replace(trim(trailing '.' from trim(trailing '0'
                 from pa.value_mw::text)), '.', '\.')
            || '\s*MWe?\y[^.;]{0,80}\y(export|exporting|exported)\y'))
     AND NOT f.evidence_text ~* ('\y'
            || replace(trim(trailing '.' from trim(trailing '0'
                 from pa.value_mw::text)), '.', '\.')
            || '\s*MWe?\y[^.;]{0,25}\yimport'))
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[export_limit_not_connection_chunkcut]%'
     AND pa.quantity_type = 'grid_connection' AND pa.value_mw = 49.9
     AND f.evidence_text ~* 'limited to\s+49,900\s+kW at unity p\.f\.')
 OR (coalesce(pa.unit_note,'') NOT LIKE '%[contradicted_by_own_document]%'
     AND pa.value_mw = 2240
     AND f.evidence_text ~* 'contribute.{0,12}2240\s*MW')
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


# The units scripts/adjudicate_power.py treats as power figures (its
# TO_MW and APPARENT tables). Copied here for the same reason the
# correction predicates are, and pinned in step by
# tests/test_adjudication_gate.py.
POWER_UNITS = [
    "mw", "megawatt", "megawatts", "mwe",
    "kw", "kilowatt", "kilowatts",
    "gw", "gigawatt", "gigawatts",
    "mva", "kva",
]

# The adjudication tail: power-unit findings no model has adjudicated.
#
# The number this must count is "no verdict from ANY model", and never
# "not yet done by the model whose resume query is to hand".
# adjudicate_power.load_candidates excludes only its own model+prompt —
# that is its resume contract — and read as a completeness measure it
# was misleading by fifty times (15,220 against a real 299, measured
# 2026-08-26; ROADMAP has the table). A gate that reported a
# five-figure backlog before every release would be ignored within two.
#
# Report-only, never a refusal: not every unadjudicated row is a site
# capacity waiting to be claimed — some are not-this-site by
# inspection, such as an operator describing its whole European fleet —
# so the honest assertion is the size, split by whether the row could
# move a headline (its site has no adjudicated capacity at all) or
# only refine one.
TAIL_SQL = r"""
WITH tail AS (
  SELECT f.id, f.application_id FROM findings f
  WHERE f.value_number IS NOT NULL
    AND lower(f.value_unit) = ANY(%s)
    AND NOT EXISTS (SELECT 1 FROM power_adjudication p
                    WHERE p.finding_id = f.id)),
site_of AS (
  SELECT m.application_id, m.site_id FROM site_members m
  JOIN sites s ON s.id = m.site_id
  WHERE m.retired_at IS NULL AND s.retired_at IS NULL),
sites_with_capacity AS (
  SELECT DISTINCT so.site_id
  FROM power_adjudication pa
  JOIN findings f ON f.id = pa.finding_id
  JOIN site_of so ON so.application_id = f.application_id
  WHERE pa.verdict = 'site_capacity')
SELECT count(DISTINCT t.id),
       count(DISTINCT t.id) FILTER (
         WHERE so.site_id IS NOT NULL
           AND so.site_id NOT IN (SELECT site_id FROM sites_with_capacity))
FROM tail t LEFT JOIN site_of so ON so.application_id = t.application_id
"""


def tail_counts(conn=None) -> tuple[int, int]:
    """(power-unit findings with no verdict from any model, the subset
    on live sites that carry no adjudicated capacity at all)."""
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(TAIL_SQL, (POWER_UNITS,))
            return cur.fetchone()
    with db.connect() as c, c.cursor() as cur:
        cur.execute(TAIL_SQL, (POWER_UNITS,))
        return cur.fetchone()


def report_tail(conn=None) -> tuple[int, int]:
    """Print the tail beside the corrections check, so no build can ship
    unadjudicated figures without having said so. 2.7 came within one
    runbook step of shipping 4,117 of them silently."""
    total, consequential = tail_counts(conn)
    if total:
        print(f"Adjudication tail: {total} power-unit findings have no "
              f"verdict from any model; {consequential} sit on sites with "
              f"no adjudicated capacity, where a verdict moves a headline. "
              f"scripts/adjudicate_power.py is the route. Building anyway "
              f"— the artefacts will not carry the missing figures.")
    else:
        print("Adjudication tail: empty — every power-unit finding has a "
              "verdict from at least one model.")
    return total, consequential


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
    report_tail(conn)
