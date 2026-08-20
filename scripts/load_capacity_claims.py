"""Load the NESO EA Register demand claims and their hand-adjudicated matches.

Operates on the production DB (`DATABASE_URL` from `.env`). Idempotent by
constraint: re-running on the same snapshot and matches file inserts
nothing (capacity_claims_content_key, capacity_claim_matches_content_key).
The matches batch is validated in full before anything is written, so a
bad file fails whole rather than half-loading.

Usage:
    scripts/load_capacity_claims.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import capacity_claims as cc
from dcp import db


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and validate everything; write nothing.")
    args = ap.parse_args()

    claims = cc.load_register_demand_claims()
    matches = cc.load_matches()
    ch_claims = cc.load_ch_claims()
    ch_matches = cc.load_ch_matches()
    problems = (cc.validate_matches(claims, matches)
                + cc.validate_ch(ch_claims, ch_matches))
    if problems:
        for p in problems:
            print(f"INVALID: {p}", file=sys.stderr)
        return 1
    total_mw = sum(c.value_mw for c in claims)
    print(f"{len(claims)} demand claims ({total_mw:,.0f} MW), "
          f"{len(matches)} matches, batch valid.")
    print(f"{len(ch_claims)} filed-accounts claims, {len(ch_matches)} matches, "
          f"every figure verified against the OCR of its cited page.")
    if args.dry_run:
        return 0

    inserted_claims = inserted_matches = 0
    with db.connect() as conn:
        with conn.cursor() as cur:
            claim_ids: dict[int, int] = {}
            for c in claims:
                attrs = {
                    "connection_point": c.connection_point,
                    "existing_connection_date":
                        c.existing_connection_date.isoformat()
                        if c.existing_connection_date else None,
                    "gate1_interest": c.gate1_interest,
                    "technology_type": c.technology_verbatim,
                }
                cur.execute(
                    """
                    INSERT INTO capacity_claims
                        (source_key, claim_name, quantity_type,
                         value_original, unit_original, value_mw, stage,
                         as_at, source_url, source_locator, attrs)
                    VALUES (%s, %s, 'grid_connection', %s, 'MW', %s,
                            'existing agreement (pre-Gate 2)', %s, %s, %s, %s)
                    ON CONFLICT (source_key, claim_name, quantity_type,
                                 value_original, unit_original, as_at,
                                 source_locator)
                    DO NOTHING
                    RETURNING id
                    """,
                    (cc.SOURCE_KEY, c.claim_name, c.value_mw, c.value_mw,
                     cc.AS_AT, cc.SOURCE_URL, c.source_locator,
                     json.dumps(attrs)),
                )
                row = cur.fetchone()
                if row:
                    claim_ids[c.excel_row] = row[0]
                    inserted_claims += 1
                else:
                    cur.execute(
                        """
                        SELECT id FROM capacity_claims
                        WHERE source_key = %s AND source_locator = %s
                        """,
                        (cc.SOURCE_KEY, c.source_locator))
                    claim_ids[c.excel_row] = cur.fetchone()[0]

            for m in matches:
                cur.execute(
                    """
                    INSERT INTO capacity_claim_matches
                        (claim_id, site_id, method, confidence, evidence,
                         matched_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (claim_id, site_id, method, md5(evidence))
                    DO NOTHING
                    RETURNING id
                    """,
                    (claim_ids[m.excel_row], m.site_id, m.method,
                     m.confidence, m.evidence, m.matched_by),
                )
                if cur.fetchone():
                    inserted_matches += 1

            # --- Companies House filed accounts --------------------------
            ch_ids: dict[str, int] = {}
            for fc in ch_claims:
                cur.execute(
                    """
                    INSERT INTO capacity_claims
                        (source_key, claim_name, quantity_type,
                         value_original, unit_original, value_mw, stage,
                         as_at, source_url, source_locator, attrs)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key, claim_name, quantity_type,
                                 value_original, unit_original, as_at,
                                 source_locator)
                    DO NOTHING
                    RETURNING id
                    """,
                    (fc.source_key, fc.claim_name, fc.quantity_type, fc.value,
                     fc.unit, cc.mw_of(fc.value, fc.unit), fc.stage, fc.as_at,
                     fc.url, fc.locator, json.dumps(fc.attrs)),
                )
                row = cur.fetchone()
                if row:
                    ch_ids[fc.claim_name] = row[0]
                    inserted_claims += 1
                else:
                    cur.execute(
                        """
                        SELECT id FROM capacity_claims
                        WHERE source_key = %s AND claim_name = %s
                          AND source_locator = %s
                        """,
                        (fc.source_key, fc.claim_name, fc.locator))
                    ch_ids[fc.claim_name] = cur.fetchone()[0]

            for m in ch_matches:
                cur.execute(
                    """
                    INSERT INTO capacity_claim_matches
                        (claim_id, site_id, method, confidence, evidence,
                         matched_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (claim_id, site_id, method, md5(evidence))
                    DO NOTHING
                    RETURNING id
                    """,
                    (ch_ids[m["claim_name"]], m["site_id"], m["method"],
                     m["confidence"], m["evidence"].strip(), m["matched_by"]),
                )
                if cur.fetchone():
                    inserted_matches += 1
        conn.commit()

    n_claims = len(claims) + len(ch_claims)
    n_matches = len(matches) + len(ch_matches)
    print(f"OK. {inserted_claims} claims and {inserted_matches} matches "
          f"inserted ({n_claims - inserted_claims} claims, "
          f"{n_matches - inserted_matches} matches already present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
