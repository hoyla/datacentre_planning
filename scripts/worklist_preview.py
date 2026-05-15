"""Render the top-N triage-ranked worklist as a markdown card stack, one
section per application, suitable for skimming in an IDE.

Lighter-weight than the formal `dcp export` (which produces both Markdown
and an Aisha-facing xlsx); this preview is intended for quick local scans
while iterating on the rubric or post-triage refinements. Output lives
under `data/worklist/` (gitignored — editorial only).

Ranking and lineage logic live in `dcp.worklist`; this script is just the
CLI shell.

Usage:
    scripts/worklist_preview.py                # top 50, default model
    scripts/worklist_preview.py --top 100
    scripts/worklist_preview.py --model granite4.1:30b --top 50
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, worklist  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50, help="How many ranked entries to include.")
    ap.add_argument("--model", default="granite4.1:30b", help="Triage model to draw from.")
    ap.add_argument("--output", type=Path, default=None,
                    help="Override output path. Default: data/worklist/top<N>_<YYYY-MM-DD>.md")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    out_path = args.output or (ROOT / f"data/worklist/top{args.top}_{today}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with db.connect() as conn:
        data = worklist.fetch(conn, model=args.model, limit=args.top)

    summary = data.summary
    header = [
        f"# Triage worklist — top {len(data.rows)} ranked",
        "",
        f"Generated {dt.datetime.now().isoformat(timespec='seconds')} from model `{args.model}`.",
        "",
        "## Universe summary",
        "",
        f"- **{summary['total']}** applications triaged total",
        f"- DC: {summary['dc']} · adjacent: {summary['adjacent']} · "
        f"unrelated: {summary['unrelated']} · unknown: {summary['unknown']}",
        f"- **Worklist (DC/adjacent ∩ deep-read yes/maybe, or Foxglove-tagged): {summary['worklist']}**",
        "",
        "## Ranking",
        "",
        "Aligned with `data/triage_labelling/rubric.md` tiers. Primary on-site generation "
        "signals (rubric Tier 1) weighted 3×; storage signals (rubric Tier 4) weighted 1×; "
        "backup/standby (rubric Tier 2) shown for context but used only as a secondary "
        "tie-break — every DC has backup, so it's a deep-read trigger, not a finding. "
        "Confidence and recency tie-break.",
        "",
        "Cards below are ordered head-of-list first. Click the source-portal link "
        "for the full document bundle.",
        "",
        "---",
        "",
    ]
    body = []
    for i, row in enumerate(data.rows, 1):
        body.append(worklist.render_card(i, row, data.anchors))
        body.append("---")
        body.append("")
    out_path.write_text("\n".join(header + body))
    print(f"Wrote {out_path}")
    if data.rows:
        top = data.rows[0]
        print(f"Top entry: #1 `{top['application_ref']}` "
              f"(t1={top['tier1_hits']}, storage={top['storage_hits']})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
