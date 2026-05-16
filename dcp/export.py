"""Reporter export — produces the Aisha-facing hand-off pair:

  - `worklist_<date>.md`   — top-N narrative markdown, one card per application
  - `worklist_<date>.xlsx` — all worklist entries as a flat sortable / filterable
                             table, suitable for Excel review

Lives under `data/exports/` (gitignored). Re-runnable whenever the universe
or triage changes; downstream consumers see the latest verdict per app via
the shared `dcp.worklist.fetch` query (DISTINCT ON inserted_at).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from dcp import db, findings as findings_mod, worklist


METHODOLOGY_NOTE = """\
### Methodology in one paragraph

We index UK planning applications from PlanIt (national aggregator, all
councils 2018+) plus the Planning Inspectorate NSIP register, complemented
by a parent-application backfill that walks PlanIt's `associated_id` chain
to recover pre-2018 substantive permissions referenced from procedural
follow-ons. A spatial sweep within 1 km of each DC anchor pulls in
neighbouring applications regardless of description language. A `granite4.1:30b`
LLM (Ollama, local) classifies each application against the rubric in
`data/triage_labelling/rubric.md` — verdict (DC / adjacent / unrelated /
unknown), deep-read recommendation, signals, and confidence. This worklist
filters to `verdict ∈ {{DC, adjacent}} AND deep-read ∈ {{yes, maybe}}`, plus a
safety-net tag for the Foxglove top-10 (which captures procedural follow-ons
the LLM correctly classifies as unrelated but where the family lineage is
still editorially important). Ranking weights primary on-site generation
signals (rubric Tier 1) at 3× and storage signals (rubric Tier 4) at 1×;
backup is a deep-read trigger, not a finding, so it serves only as a
tie-break. Council names follow the current unitary; legacy district names
are preserved in raw metadata. The xlsx companion has every worklist
entry; the markdown carries the top {md_top} curated, head-of-list first.
"""


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def render_markdown(
    *,
    data: worklist.WorklistData,
    top: int,
    model: str,
    generated_at: dt.datetime,
) -> str:
    s = data.summary
    rows_for_md = data.rows[:top]
    when = generated_at.isoformat(timespec="seconds")

    out: list[str] = []
    out.append(f"# Data-centre planning worklist — {generated_at.date().isoformat()}")
    out.append("")
    out.append(
        f"Investigation: systematic UK DC planning dataset, surfacing on-site "
        f"power-generation signals.  "
        f"Generated {when} from triage model `{model}`."
    )
    out.append("")
    out.append("## At a glance")
    out.append("")
    out.append(f"- **Universe:** {s['total']} applications triaged.")
    out.append(
        f"- **Verdict mix:** DC {s['dc']} · adjacent {s['adjacent']} · "
        f"unrelated {s['unrelated']} · unknown {s['unknown']}."
    )
    out.append(
        f"- **Worklist size:** {s['worklist']} applications "
        f"(DC/adjacent ∩ deep-read yes/maybe, or Foxglove-tagged)."
    )
    out.append(f"- **This document:** top {len(rows_for_md)} ranked entries, head-of-list first.")
    out.append(f"- **Companion xlsx:** all {s['worklist']} worklist entries, flat table for filtering.")
    out.append("")
    out.append(METHODOLOGY_NOTE.format(md_top=len(rows_for_md)))
    out.append("")
    out.append("### How to read each card")
    out.append("")
    out.append(
        "Each card shows the LLM's verdict and confidence, the rubric-tiered signal "
        "counts, the council and address, the signals extracted from the description, "
        "a one-line model reasoning, the full description verbatim (so you can "
        "sanity-check the LLM), a `Why this is on the worklist` explanation of how "
        "the application entered our universe, and a link to the source-portal "
        "record. Substantive deep-read claims should be drillable back to those "
        "documents."
    )
    out.append("")
    out.append("---")
    out.append("")
    for i, row in enumerate(rows_for_md, 1):
        out.append(worklist.render_card(i, row, data.anchors))
        out.append("---")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# XLSX export
# ---------------------------------------------------------------------------


def write_xlsx(
    *,
    path: Path,
    data: worklist.WorklistData,
    model: str,
    generated_at: dt.datetime,
) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Worklist"

    headers = [
        "Rank",
        "Application ref",
        "Verdict",
        "Deep read recommended",
        "Confidence",
        "Tier-1 hits",
        "Storage hits",
        "Backup hits",
        "Foxglove top-10",
        "Council",
        "Address",
        "Date received",
        "App type",
        "Signals",
        "LLM reasoning",
        "Discovered via (raw)",
        "Discovered via (humanised)",
        "Source portal URL",
        "Description",
        # Phase-4 columns (NULL/blank for apps without findings yet).
        "Findings — new disclosures",
        "Findings — refinements",
        "Findings — disclosed MW",
        "Findings — headline",
    ]
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")
        cell.alignment = Alignment(vertical="center", wrap_text=False)

    for rank, row in enumerate(data.rows, 1):
        descr = row.get("description") or ""
        signals = ", ".join(row.get("signals") or [])
        via_raw = ", ".join(row.get("discovered_via") or [])
        via_human = "\n".join(
            f"• {line}" for line in worklist.expand_lineage(
                row.get("discovered_via"), data.anchors,
            )
        )
        date_received = row.get("date_received")
        date_str = date_received.isoformat() if date_received else ""
        council = (
            row.get("council_name")
            or (row.get("raw_metadata") or {}).get("area_name")
            or ""
        )
        app_type = (row.get("raw_metadata") or {}).get("app_type") or ""
        # Phase-4 columns: populated only when the app has findings rows.
        row_findings = row.get("findings") or []
        f_counts = findings_mod.category_counts(row_findings)
        new_count = f_counts.get(findings_mod.CATEGORY_NEW) or None
        ref_count = f_counts.get(findings_mod.CATEGORY_REFINEMENT) or None
        disclosed_mw = findings_mod.disclosed_mw_total(row_findings)
        headline = findings_mod.headline_disclosure(row_findings) or None
        ws.append([
            rank,
            row["application_ref"],
            row["verdict"],
            row["worth_deep_read"],
            row["confidence"],
            row["tier1_hits"],
            row["storage_hits"],
            row["backup_hits"],
            "yes" if row.get("foxglove") else "",
            council,
            row.get("address") or "",
            date_str,
            app_type,
            signals,
            row.get("why") or "",
            via_raw,
            via_human,
            row.get("url") or "",
            descr,
            new_count,
            ref_count,
            disclosed_mw,
            headline,
        ])

    # Column widths — calibrated for the dominant content per column.
    widths = {
        "A": 6,  "B": 36, "C": 10, "D": 9,  "E": 10,
        "F": 8,  "G": 8,  "H": 9,  "I": 9,  "J": 28,
        "K": 50, "L": 13, "M": 14, "N": 50, "O": 60,
        "P": 40, "Q": 60, "R": 50, "S": 80,
        # Phase-4 findings columns.
        "T": 11, "U": 11, "V": 12, "W": 80,
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # Wrap text on the long columns so the row stays usable when sorted.
    wrap_cols = {"N", "O", "P", "Q", "S", "W"}
    last_row = len(data.rows) + 1
    for col in wrap_cols:
        for r in range(2, last_row + 1):
            ws[f"{col}{r}"].alignment = Alignment(vertical="top", wrap_text=True)
    # Top-align everything for sortable readability
    for r in range(2, last_row + 1):
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=c)
            if cell.alignment.wrap_text is None:
                cell.alignment = Alignment(vertical="top")

    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"

    # Methodology / summary on a second sheet
    meta = wb.create_sheet("Methodology")
    meta_rows = [
        ("Generated at", generated_at.isoformat(timespec="seconds")),
        ("Triage model", model),
        ("Total triaged", data.summary["total"]),
        ("DC", data.summary["dc"]),
        ("Adjacent", data.summary["adjacent"]),
        ("Unrelated", data.summary["unrelated"]),
        ("Unknown", data.summary["unknown"]),
        ("Worklist size", data.summary["worklist"]),
        ("", ""),
        ("Methodology", METHODOLOGY_NOTE.format(md_top="(see markdown)").strip()),
    ]
    for r, (k, v) in enumerate(meta_rows, 1):
        meta.cell(row=r, column=1, value=k).font = Font(bold=True)
        meta.cell(row=r, column=2, value=v).alignment = Alignment(
            vertical="top", wrap_text=True,
        )
    meta.column_dimensions["A"].width = 22
    meta.column_dimensions["B"].width = 110

    wb.save(path)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def export_worklist(
    *,
    model: str = "granite4.1:30b",
    output_dir: Path,
    md_top: int = 50,
    generated_at: dt.datetime | None = None,
) -> dict[str, Path]:
    """Generate the markdown + xlsx pair for the current worklist.

    Markdown carries the top `md_top` cards for narrative reading; the xlsx
    has every worklist entry, ranked, with both the raw and humanised
    `discovered_via` lineage columns so Aisha can filter however she likes.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or dt.datetime.now()
    today = generated_at.date().isoformat()
    md_path = output_dir / f"worklist_{today}.md"
    xlsx_path = output_dir / f"worklist_{today}.xlsx"

    with db.connect() as conn:
        data = worklist.fetch(conn, model=model)  # no limit — full worklist

    md_path.write_text(render_markdown(
        data=data, top=md_top, model=model, generated_at=generated_at,
    ))
    write_xlsx(path=xlsx_path, data=data, model=model, generated_at=generated_at)
    return {"markdown": md_path, "xlsx": xlsx_path}
