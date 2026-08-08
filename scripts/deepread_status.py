"""Deep-read coverage at a glance: who has read what, and what overlaps.

Answers the three questions that come up repeatedly while the corpus is
being read by more than one model:

  - How much of the corpus does each model cover?
  - How fast is the local pass moving right now?
  - How many documents have been read TWICE, independently? That is the
    adjudication cohort — the set where the two reads can be compared and
    disagreements surfaced — and it is the number that matters most once
    the API pass is complete and the local pass has become corroboration
    rather than a race.

Deliberately a script in the repo rather than a scratch file: an earlier
version lived in /private/tmp and was lost to a reboot mid-run, taking the
monitor with it.

Usage:
    .venv/bin/python scripts/deepread_status.py
    .venv/bin/python scripts/deepread_status.py --window 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402

LOCAL = "mlx:Qwen3.6-35B-A3B-4bit"
API = "claude-sonnet-5"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=30,
                    help="Minutes over which to measure the local rate.")
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM deepread_log
            WHERE model = %s AND completed_at > now() - make_interval(mins => %s)
              AND read_state IN ('read','parse_failed')""",
            (LOCAL, args.window))
        recent = cur.fetchone()[0]

        cur.execute("""SELECT model, count(DISTINCT document_id), sum(findings_inserted)
                       FROM deepread_log GROUP BY model""")
        by_model = {m: (docs, findings or 0) for m, docs, findings in cur.fetchall()}

        cur.execute("""
            SELECT count(*) FROM (
              SELECT document_id FROM deepread_log WHERE model = %s
              INTERSECT
              SELECT document_id FROM deepread_log WHERE model = %s) x""",
            (API, LOCAL))
        dual = cur.fetchone()[0]

    api_docs, api_f = by_model.get(API, (0, 0))
    loc_docs, loc_f = by_model.get(LOCAL, (0, 0))
    rate = recent * (60 / args.window)
    print(f"Sonnet: {api_docs:,} docs read ({api_f:,} findings) — complete. "
          f"Qwen corroboration: {loc_docs:,} docs ({loc_f:,} findings), "
          f"{rate:.0f}/h. Dual-read (adjudication cohort): {dual:,} docs.")


if __name__ == "__main__":
    main()
