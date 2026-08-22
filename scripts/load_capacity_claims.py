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
from dcp import ea_permits as ea


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and validate everything; write nothing.")
    ap.add_argument("--prune", action="store_true",
                    help="Delete stored claims a derived source no longer "
                         "produces (see below). Reported without this flag.")
    args = ap.parse_args()

    claims = cc.load_register_demand_claims()
    matches = cc.load_matches()
    ch_claims = cc.load_ch_claims()
    ch_matches = cc.load_ch_matches()
    op_claims = cc.load_operator_claims()
    op_matches = cc.load_operator_matches()
    ea_claims = ea.load_ea_claims()
    ea_matches = ea.load_ea_matches()
    problems = (cc.validate_matches(claims, matches)
                + cc.validate_ch(ch_claims, ch_matches)
                + cc.validate_operator(op_claims, op_matches)
                + ea.validate_ea(ea_claims, ea_matches))
    if problems:
        for p in problems:
            print(f"INVALID: {p}", file=sys.stderr)
        return 1
    total_mw = sum(c.value_mw for c in claims)
    print(f"{len(claims)} demand claims ({total_mw:,.0f} MW), "
          f"{len(matches)} matches, batch valid.")
    print(f"{len(ch_claims)} filed-accounts claims, {len(ch_matches)} matches, "
          f"every figure verified against the OCR of its cited page.")
    print(f"{len(op_claims)} operator-website claims, {len(op_matches)} "
          f"matches, every quote verified against its committed snapshot.")
    print(f"{len(ea_claims)} Environment Agency permit claims "
          f"({sum(c.value for c in ea_claims):,.0f} MWth), {len(ea_matches)} "
          f"matches, every figure verified against the committed text of "
          f"the page it cites.")
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

            # --- Sources whose claims are named rather than numbered -----
            # Filed accounts and operator websites share a shape: a
            # FiledClaim, and matches keyed by claim_name. One loop, so a
            # fix to the insert logic cannot reach one source and miss
            # the other.
            for filed, filed_matches in ((ch_claims, ch_matches),
                                         (op_claims, op_matches),
                                         (ea_claims, ea_matches)):
                ids: dict[str, int] = {}
                for fc in filed:
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
                        DO UPDATE SET attrs = EXCLUDED.attrs
                        RETURNING id, (xmax = 0) AS was_inserted
                        """,
                        (fc.source_key, fc.claim_name, fc.quantity_type,
                         fc.value, fc.unit, cc.mw_of(fc.value, fc.unit),
                         fc.stage, fc.as_at, fc.url, fc.locator,
                         json.dumps(fc.attrs)),
                    )
                    # The claim — source, name, quantity, value, unit,
                    # date, locator — is what the unique index protects
                    # and is never rewritten. `attrs` is the derived
                    # envelope around it, regenerated from the committed
                    # files on every run: the quote, the operator
                    # attribution, the document sha. Refreshing it is how
                    # an edit to a committed YAML reaches the store
                    # without a delete; leaving it stale would let the
                    # database and the file that produced it disagree,
                    # which is the failure this project can least afford.
                    # xmax = 0 distinguishes a real insert from an update.
                    cid, was_inserted = cur.fetchone()
                    ids[fc.claim_name] = cid
                    if was_inserted:
                        inserted_claims += 1

                for m in filed_matches:
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
                        (ids[m["claim_name"]], m["site_id"], m["method"],
                         m["confidence"], m["evidence"].strip(),
                         m["matched_by"]),
                    )
                    if cur.fetchone():
                        inserted_matches += 1
        conn.commit()

    # Orphans, for the one source whose claims are derived rather than
    # listed. The NESO, Companies House and operator claims are written
    # out by hand, so a claim disappearing from them is a deliberate
    # edit. The Environment Agency claims are computed from the
    # committed permit text, and a change to the reader — a better name
    # for an installation, a page number that moved — produces a claim
    # the loader inserts beside the old one rather than instead of it.
    # Reported always, deleted only on --prune, because a stored claim
    # vanishing from its own source is exactly the drift this project
    # needs to see rather than tidy away silently.
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, claim_name FROM capacity_claims "
                    "WHERE source_key = %s", (ea.SOURCE_KEY,))
        live = {c.claim_name for c in ea_claims}
        orphans = [(i, n) for i, n in cur.fetchall() if n not in live]
        if orphans:
            print(f"\n{len(orphans)} stored Environment Agency claims are no "
                  f"longer produced by the committed files:")
            for _i, n in sorted(orphans, key=lambda o: o[1]):
                print(f"  {n}")
            if args.prune:
                ids = [i for i, _n in orphans]
                cur.execute("DELETE FROM capacity_claim_matches "
                            "WHERE claim_id = ANY(%s)", (ids,))
                dropped_matches = cur.rowcount
                cur.execute("DELETE FROM capacity_claims WHERE id = ANY(%s)",
                            (ids,))
                conn.commit()
                print(f"Pruned {cur.rowcount} claims and {dropped_matches} "
                      f"matches.")
            else:
                print("Re-run with --prune to remove them.")

    n_claims = len(claims) + len(ch_claims) + len(op_claims) + len(ea_claims)
    n_matches = (len(matches) + len(ch_matches) + len(op_matches)
                 + len(ea_matches))
    print(f"OK. {inserted_claims} claims and {inserted_matches} matches "
          f"inserted ({n_claims - inserted_claims} claims, "
          f"{n_matches - inserted_matches} matches already present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
