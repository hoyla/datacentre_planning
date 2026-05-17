"""Aggregate corpus-level statistics for methodology notes / piece copy.

The brief here is *no editorial overlay*: every number that comes out of this
script has to be a direct aggregate of what's in the DB, not a judgement
about what the numbers mean. Anything that needs human classification
(fossil-only vs hybrid vs renewable, "exceeds emergency backup", etc.)
stays out — that's a separate pass, in the loop with a reporter.

Output is a markdown block, defensibly cite-able as "from `corpus_stats.py`
against the DB state of <date>". Drop into a methodology footnote or a
chart caption. A shorter form of the same numbers travels in the worklist
export header (see `dcp.export`); both rely on `dcp.corpus_stats` for the
underlying queries.

Usage:
    scripts/corpus_stats.py                      # print to stdout
    scripts/corpus_stats.py --output stats.md    # write to a file
    scripts/corpus_stats.py --model granite4.1:30b
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import corpus_stats, db  # noqa: E402


def _render_markdown(
    *,
    model: str,
    generated_at: dt.datetime,
    universe: dict,
    verdicts: dict,
    filters: dict,
    signals: dict,
    documents: dict,
    findings: dict,
) -> str:
    lines: list[str] = []
    lines.append(f"# Corpus statistics — generated {generated_at.date().isoformat()}")
    lines.append("")
    lines.append(
        f"Aggregated from the working DB. Triage model: `{model}`. "
        "All figures are direct aggregates — no editorial classification "
        "applied. See `data/triage_labelling/rubric.md` for the rubric "
        "underlying the verdict and signal columns."
    )
    lines.append("")

    # --- Universe ---
    lines.append("## Universe")
    lines.append("")
    date_span = ""
    if universe["date_min"] and universe["date_max"]:
        date_span = (
            f" (date received range: "
            f"{universe['date_min'].isoformat()} – {universe['date_max'].isoformat()})"
        )
    lines.append(f"- **Total applications ingested:** {universe['total']}{date_span}.")
    if universe["by_source"]:
        src_parts = ", ".join(f"{n} from `{s}`" for s, n in universe["by_source"])
        lines.append(f"- **By source:** {src_parts}.")
    if universe["discovery_tags"]:
        lines.append("- **Discovery-path tags** (an app can carry multiple — counts are per-tag, not per-app):")
        for tag, n in universe["discovery_tags"]:
            lines.append(f"  - `{tag}`: {n}")
    lines.append("")

    # --- Triage ---
    lines.append("## Triage verdicts")
    lines.append("")
    triaged = verdicts["triaged"]
    lines.append(
        f"- **Applications with a `{model}` verdict:** {triaged} "
        f"(of {universe['total']} in the universe)."
    )
    if triaged:
        for k, label in (
            ("dc", "data centre (`DC`)"),
            ("adjacent", "power-adjacent (`adjacent`)"),
            ("unrelated", "unrelated"),
            ("unknown", "unknown"),
        ):
            n = verdicts[k]
            pct = (n / triaged) * 100
            lines.append(f"  - {label}: **{n}** ({pct:.1f}%)")
    lines.append("")
    matched = verdicts["dc"] + verdicts["adjacent"]
    if matched:
        lines.append(
            f"- Of the {matched} `DC` + `adjacent` apps, the triage "
            "flagged `worth_deep_read` as:"
        )
        for k, label in (
            ("deep_read_yes", "yes"),
            ("deep_read_maybe", "maybe"),
            ("deep_read_no", "no"),
        ):
            n = verdicts[k]
            pct = (n / matched) * 100
            lines.append(f"  - {label}: **{n}** ({pct:.1f}%)")
    lines.append("")

    # --- Editorial filters ---
    lines.append("## Editorial filters")
    lines.append("")
    lines.append(
        "Applied after triage (and stored as tags alongside the verdict, "
        "never as overrides), to drop confirmed false-positives and "
        "consultation-stage duplicates from the worklist:"
    )
    lines.append(f"- **Excluded** (confirmed not-a-data-centre after deep-read): {filters['excluded']}.")
    if filters["exclude_reasons"]:
        for reason, n in filters["exclude_reasons"]:
            lines.append(f"  - `{reason}`: {n}")
    lines.append(
        f"- **Duplicates** (consultation-stage copies of a primary "
        f"application): {filters['duplicates']}."
    )
    lines.append("")

    # --- Worklist signals ---
    lines.append("## Worklist — power signals from descriptions")
    lines.append("")
    total = signals["total"]
    lines.append(
        f"- **Worklist size** (apps with `DC` / `adjacent` verdict, "
        f"`worth_deep_read in (yes, maybe)`, after editorial filtering): "
        f"**{total}**."
    )
    if total:
        lines.append(
            "- Classified by their triage `signals` array (mutually "
            "exclusive in this display order — see `dcp/worklist.py` "
            "for the rubric regexes):"
        )
        for k, label in (
            ("tier1_any", "primary on-site generation signal (Tier 1: gas turbine / CHP / energy centre / biomass / hydrogen / etc.)"),
            ("storage_only", "battery storage only (no Tier 1 generation signal)"),
            ("backup_only", "backup / standby generator signal only (no Tier 1, no storage)"),
            ("no_power_signal", "no extracted power signal — on the worklist via verdict + foxglove prior or adjacent context"),
        ):
            n = signals[k]
            pct = (n / total) * 100
            lines.append(f"  - {label}: **{n}** ({pct:.1f}%)")
        lines.append("")
        lines.append(
            "> ⚠️ These are signals extracted from the *application "
            "description text* by the Stage-1 triage, not from the "
            "submitted documents. They indicate where the editorial "
            "weight of the worklist sits at description-level; "
            "document-level disclosures land in the `findings` table "
            "(below), which is a much smaller and editorially-selected "
            "sample."
        )
    lines.append("")

    # --- Documents ---
    lines.append("## Document corpus (Phase 3)")
    lines.append("")
    lines.append(f"- **Documents fetched:** {documents['docs_total']}.")
    lines.append(
        f"- **Applications with at least one document on file:** "
        f"{documents['apps_with_docs']}."
    )
    lines.append("")

    # --- Findings ---
    lines.append("## Document-extracted findings (Phase 4)")
    lines.append("")
    lines.append(
        "Structured facts pulled from the documents themselves, each "
        "carrying its supporting quote, source filename, and page "
        "number. v1 covers a small editorially-selected sample, not "
        "the full worklist — see `ROADMAP.md` for scale-up plans."
    )
    lines.append("")
    lines.append(f"- **Findings recorded:** {findings['findings_total']}.")
    lines.append(
        f"- **Applications with findings:** {findings['apps_with_findings']}."
    )
    lines.append(
        f"- **Distinct documents touched:** {findings['documents_with_findings']}."
    )
    if findings["by_signal"]:
        lines.append("- **By signal type:**")
        for sig, n in findings["by_signal"]:
            lines.append(f"  - `{sig}`: {n}")
    lines.append("")
    lines.append(
        "> ⚠️ The findings sample is not statistically representative "
        "of the worklist. Apps were chosen for editorial salience "
        "(known hyperscalers, the Humber cluster, the Greystoke trio, "
        "etc.), so per-category proportions here are characteristic of "
        "*what was looked at*, not of the worklist universe."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model",
        default="granite4.1:30b",
        help="Triage model whose verdicts drive the verdict + worklist sections.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write to this path instead of stdout.",
    )
    args = ap.parse_args()

    generated_at = dt.datetime.now()
    with db.connect() as conn:
        stats = corpus_stats.collect(conn, model=args.model)

    md = _render_markdown(
        model=args.model,
        generated_at=generated_at,
        **stats,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
