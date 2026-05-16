"""Aggregate corpus-level statistics for methodology notes / piece copy.

The brief here is *no editorial overlay*: every number that comes out of this
script has to be a direct aggregate of what's in the DB, not a judgement
about what the numbers mean. Anything that needs human classification
(fossil-only vs hybrid vs renewable, "exceeds emergency backup", etc.)
stays out — that's a separate pass, in the loop with a reporter.

Output is a markdown block, defensibly cite-able as "from `corpus_stats.py`
against the DB state of <date>". Drop into a methodology footnote or a
chart caption.

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

from dcp import db, worklist  # noqa: E402


def _scalar(cur, sql: str, params: dict | tuple | None = None) -> int:
    cur.execute(sql, params or {})
    row = cur.fetchone()
    return row[0] if row else 0


def _universe(conn) -> dict:
    with conn.cursor() as cur:
        total = _scalar(cur, "SELECT count(*) FROM applications")
        date_min, date_max = None, None
        cur.execute(
            "SELECT min(date_received), max(date_received) FROM applications "
            "WHERE date_received IS NOT NULL"
        )
        row = cur.fetchone()
        if row:
            date_min, date_max = row
        cur.execute(
            "SELECT s.name, count(*) FROM applications a "
            "JOIN sources s ON s.id = a.source_id GROUP BY s.name ORDER BY count(*) DESC"
        )
        by_source = list(cur.fetchall())
        # Discovery-path counts. An app can carry multiple tags, so the
        # sum is greater than the universe size — counts are per-tag, not
        # per-app. The "primary" discovery is the DC-keyword sweep; others
        # are augmenting passes.
        cur.execute(
            """
            SELECT tag, count(*) AS n FROM (
                SELECT unnest(discovered_via) AS tag FROM applications
            ) t
            GROUP BY tag
            HAVING count(*) >= 5
            ORDER BY n DESC
            """
        )
        discovery_tags = list(cur.fetchall())
    return {
        "total": total,
        "date_min": date_min,
        "date_max": date_max,
        "by_source": by_source,
        "discovery_tags": discovery_tags,
    }


def _verdicts(conn, *, model: str) -> dict:
    sql = """
    WITH latest_triage AS (
      SELECT DISTINCT ON (application_id) *
      FROM triage WHERE model = %(model)s
      ORDER BY application_id, inserted_at DESC
    )
    SELECT
      count(*) AS triaged,
      count(*) FILTER (WHERE t.verdict = 'DC') AS dc,
      count(*) FILTER (WHERE t.verdict = 'adjacent') AS adjacent,
      count(*) FILTER (WHERE t.verdict = 'unrelated') AS unrelated,
      count(*) FILTER (WHERE t.verdict = 'unknown') AS unknown,
      count(*) FILTER (
        WHERE t.verdict IN ('DC','adjacent') AND t.worth_deep_read = 'yes'
      ) AS deep_read_yes,
      count(*) FILTER (
        WHERE t.verdict IN ('DC','adjacent') AND t.worth_deep_read = 'maybe'
      ) AS deep_read_maybe,
      count(*) FILTER (
        WHERE t.verdict IN ('DC','adjacent') AND t.worth_deep_read = 'no'
      ) AS deep_read_no
    FROM applications a JOIN latest_triage t ON t.application_id = a.id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"model": model})
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))


def _editorial_filters(conn) -> dict:
    """Counts for the `exclude:*` and `duplicate_of:*` tags applied in
    `data/priors/cohorts.yaml` and `data/priors/duplicates.yaml`. These
    sit alongside the verdict — never replace it — so the audit trail
    survives."""
    with conn.cursor() as cur:
        excluded = _scalar(
            cur,
            "SELECT count(*) FROM applications "
            "WHERE EXISTS (SELECT 1 FROM unnest(discovered_via) AS tag WHERE tag LIKE 'exclude:%%')",
        )
        duplicates = _scalar(
            cur,
            "SELECT count(*) FROM applications "
            "WHERE EXISTS (SELECT 1 FROM unnest(discovered_via) AS tag WHERE tag LIKE 'duplicate_of:%%')",
        )
        cur.execute(
            """
            SELECT split_part(tag, ':', 1) || ':' || split_part(tag, ':', 2) AS reason,
                   count(*) AS n
            FROM (SELECT unnest(discovered_via) AS tag FROM applications) t
            WHERE tag LIKE 'exclude:%%'
            GROUP BY reason ORDER BY n DESC
            """
        )
        exclude_reasons = list(cur.fetchall())
    return {
        "excluded": excluded,
        "duplicates": duplicates,
        "exclude_reasons": exclude_reasons,
    }


def _signals_in_worklist(conn, *, model: str) -> dict:
    """For apps in the editorial worklist (verdict in DC/adjacent +
    worth_deep_read yes/maybe, after exclude/duplicate filtering), classify
    by which rubric tiers their triage `signals` array hit.

    Uses the same regexes as `dcp.worklist` for tier 1 (primary on-site
    generation), tier 4 (storage), and tier 2 (backup) — see
    `data/triage_labelling/rubric.md` for the definitions.

    The classification is mutually exclusive in display order: tier1 wins
    over storage, storage wins over backup-only. An app with no matching
    signal lands in `none`. The intent is to give a sense of where the
    worklist's editorial weight sits *before* any document-level
    extraction — these are signals from the application description, not
    from the documents themselves.
    """
    sql = """
    WITH latest_triage AS (
      SELECT DISTINCT ON (application_id) *
      FROM triage WHERE model = %(model)s
      ORDER BY application_id, inserted_at DESC
    ),
    worklist AS (
      SELECT a.id, t.signals
      FROM applications a JOIN latest_triage t ON t.application_id = a.id
      WHERE
        (
          (t.verdict IN ('DC','adjacent') AND t.worth_deep_read IN ('yes','maybe'))
          OR 'foxglove_top10' = ANY(a.discovered_via)
        )
        AND NOT EXISTS (
          SELECT 1 FROM unnest(a.discovered_via) AS tag
          WHERE tag LIKE 'exclude:%%' OR tag LIKE 'duplicate_of:%%'
        )
    ),
    hits AS (
      SELECT
        id,
        (SELECT count(*) FROM unnest(signals) s WHERE lower(s) ~ %(tier1)s)   AS tier1,
        (SELECT count(*) FROM unnest(signals) s WHERE lower(s) ~ %(storage)s) AS storage,
        (SELECT count(*) FROM unnest(signals) s WHERE lower(s) ~ %(backup)s)  AS backup
      FROM worklist
    )
    SELECT
      count(*) AS total,
      count(*) FILTER (WHERE tier1 > 0) AS tier1_any,
      count(*) FILTER (WHERE tier1 = 0 AND storage > 0) AS storage_only,
      count(*) FILTER (WHERE tier1 = 0 AND storage = 0 AND backup > 0) AS backup_only,
      count(*) FILTER (WHERE tier1 = 0 AND storage = 0 AND backup = 0) AS no_power_signal
    FROM hits
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "model": model,
                "tier1": worklist.TIER1_REGEX,
                "storage": worklist.TIER_STORAGE_REGEX,
                "backup": worklist.TIER_BACKUP_REGEX,
            },
        )
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))


def _documents(conn) -> dict:
    with conn.cursor() as cur:
        docs_total = _scalar(cur, "SELECT count(*) FROM documents")
        apps_with_docs = _scalar(
            cur,
            "SELECT count(DISTINCT application_id) FROM documents",
        )
    return {"docs_total": docs_total, "apps_with_docs": apps_with_docs}


def _findings(conn) -> dict:
    """Phase-4 findings aggregates. Categories (NEW DISCLOSURE /
    REFINEMENT / CONFIRMATION) are derived at render time in
    `dcp.findings.classify` against each app's description + triage
    signals, not stored on the row — so the counts here are by raw
    `signal_type`. The render-time categorisation runs in
    `dcp.findings.fetch_for_applications`; for an editorial-facing
    breakdown of NEW vs REFINEMENT see the export's per-app blocks.
    """
    with conn.cursor() as cur:
        total = _scalar(cur, "SELECT count(*) FROM findings")
        apps = _scalar(cur, "SELECT count(DISTINCT application_id) FROM findings")
        docs = _scalar(
            cur,
            "SELECT count(DISTINCT document_id) FROM findings WHERE document_id IS NOT NULL",
        )
        cur.execute(
            "SELECT signal_type, count(*) AS n FROM findings "
            "GROUP BY signal_type ORDER BY n DESC"
        )
        by_signal = list(cur.fetchall())
    return {
        "findings_total": total,
        "apps_with_findings": apps,
        "documents_with_findings": docs,
        "by_signal": by_signal,
    }


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
        universe = _universe(conn)
        verdicts = _verdicts(conn, model=args.model)
        filters = _editorial_filters(conn)
        signals = _signals_in_worklist(conn, model=args.model)
        documents = _documents(conn)
        findings = _findings(conn)

    md = _render_markdown(
        model=args.model,
        generated_at=generated_at,
        universe=universe,
        verdicts=verdicts,
        filters=filters,
        signals=signals,
        documents=documents,
        findings=findings,
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
