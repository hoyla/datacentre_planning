"""The dc_build catalogue sweep: classify the whole universe under v2.1.

Walks every application without a dc_build verdict for the chosen model
and appends one classification per application. Resume is automatic and
rubric-aware, so v1 verdicts neither satisfy nor block this sweep, and a
kill loses at most the in-flight call.

Cost control: `--pilot N` runs N applications, reports measured cost per
application and the projected total, and stops. Run the pilot first —
the projection is the number to check a budget against.

Usage:
    .venv/bin/python -u scripts/catalogue_sweep.py --pilot 40
    .venv/bin/python -u scripts/catalogue_sweep.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, triage  # noqa: E402

# claude-sonnet-5 list prices, USD per million tokens.
PRICE_IN, PRICE_OUT = 3.00, 15.00


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--pilot", type=int, default=None,
                    help="Run this many applications, report projected cost, stop.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-enrich", action="store_true")
    args = ap.parse_args()

    # Two different numbers, and conflating them overstates the bill.
    # `universe` is every application; `pending` is the subset with no
    # dc_build verdict, which is all the resume-aware sweep will touch.
    # The pilot previously projected against the universe and quoted
    # $29 for what was in fact $12 of work.
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM applications")
        universe = cur.fetchone()[0]
        cur.execute("""
            SELECT count(*) FROM applications a
            WHERE NOT EXISTS (
              SELECT 1 FROM triage t
              WHERE t.application_id = a.id
                AND t.raw_response->>'rubric' = 'dc_build')
              AND NOT (a.discovered_via @> ARRAY['nsip_energy'])""")
        pending_total = cur.fetchone()[0]
    print(f"universe: {universe} applications; "
          f"{pending_total} pending a dc_build verdict")

    started = time.time()
    counter = {"n": 0}

    def progress(p):
        counter["n"] += 1
        if counter["n"] % 25 == 0 or p.get("error"):
            done, tot = p["scanned"], p["pending"]
            rate = (time.time() - started) / max(counter["n"], 1)
            eta = (tot - done) * rate / 60
            print(f"  {done}/{tot}  {p['ref']:36} {str(p['verdict']):18} "
                  f"({p['elapsed']:.1f}s)  eta {eta:.0f}m"
                  + (f"  ERROR {p['error']}" if p.get("error") else ""))

    summary = triage.run_triage(
        model=args.model, rubric="dc_build", enrich=not args.no_enrich,
        limit=args.pilot or args.limit, progress=progress)

    elapsed = time.time() - started
    print(f"\n{summary}")
    print(f"elapsed: {elapsed/60:.1f} min for {summary['scanned']} applications")

    if args.pilot and summary["scanned"]:
        # Measure real token usage from the rows just written.
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT avg(in_chars), avg(out_chars) FROM (
                    SELECT length(raw_response->>'rendered_input') AS in_chars,
                           length(raw_response->>'text') AS out_chars
                    FROM triage
                    WHERE raw_response->>'rubric' = 'dc_build'
                    ORDER BY inserted_at DESC LIMIT %s) recent""",
                (summary["scanned"],))
            in_chars, out_chars = cur.fetchone()
        # ~4 characters per token, plus the system prompt on every call.
        sys_tokens = len(triage.DC_BUILD_SYSTEM_PROMPT) / 4
        in_tok = (float(in_chars or 0) / 4) + sys_tokens
        out_tok = float(out_chars or 0) / 4
        per_app = (in_tok * PRICE_IN + out_tok * PRICE_OUT) / 1_000_000
        # Against pending, not universe: the pilot's own scanned rows are
        # already recorded, so they are not remaining work.
        remaining = max(pending_total - summary["scanned"], 0)
        print(f"\nmeasured: ~{in_tok:.0f} input + ~{out_tok:.0f} output tokens/application")
        print(f"cost/application: ${per_app:.4f}")
        print(f"projected for remaining {remaining} pending: "
              f"${per_app * remaining:.2f}")
        print(f"(a full re-sweep of all {universe} would be "
              f"${per_app * universe:.2f})")
        print(f"projected wall-clock: {(elapsed/summary['scanned'])*remaining/60:.0f} min")


if __name__ == "__main__":
    main()
