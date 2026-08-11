"""Assemble the Drive-shaped handover tree from the canonical store.

Produces `data/exports/drive_staging/` — the exact structure agreed for
the Guardian data/visuals-team handover (ROADMAP, "Handover design") —
so the eventual upload is a single `rclone sync` once credentials exist.
Everything here is derived; the canonical store and database remain the
source of truth, and the tree is rebuilt rather than edited.

    drive_staging/
    ├── dc_handover_phase<N>.xlsx     (each release's, side by side)
    ├── dc_phase<N>.duckdb
    ├── reader.html                   (always the current release)
    └── sites/
        └── <site_key> — <site name>/
            ├── _site_report — <site_key> — <site name>.md
            │                        (per-site summary: applications,
            │                         parties, signals, Barbour fields)
            ├── _findings — <site_key> — <site name>.csv
            └── <application_ref>/
                ├── _index.md        (document list with source URLs)
                └── NNN - <derived name>.pdf

Three deliberate choices:

- **Hard links, not copies.** The corpus is ~70GB; the staging tree
  shares inodes with the canonical store, so it costs directory entries,
  not disk. (Copy fallback if linking fails.)
- **Human-readable derived filenames.** The canonical store is
  content-hash named (right for provenance, useless in a Drive UI).
  Derived names come from the council's own document description, with a
  stable numeric prefix for ordering and a hash suffix on collisions.
  The mapping is recorded in each folder's `_index.md`.
- **The per-site report and findings carry the site in their own
  filenames**, not just in the folder above them. Anything that flattens
  the tree — a NotebookLM collection, a Pinpoint upload, a folder of
  downloads — otherwise presents 429 files called `_site_report.md` and
  429 called `_findings.csv`, and the reader has no way to tell which
  site is which. The site key is in there as well as the name because
  display names are not unique: four sites are called "Reading Quarry
  Berrys Lane Burghfield", and the name alone would collide.

Renaming these files leaves their old names behind on Drive, because
`drive_sync.py` uploads by path and never deletes. Run that sync with
`--prune` after any rename here, or the collection gains a stale twin of
every file it already had.

Usage:
    .venv/bin/python scripts/build_drive_staging.py [--out DIR] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, extract, signals  # noqa: E402
from dcp import release as release_mod  # noqa: E402

BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def clean(name: str, maxlen: int = 80) -> str:
    out = BAD.sub(" ", name or "").strip(" .")
    out = re.sub(r"\s+", " ", out)
    return out[:maxlen].strip(" .") or "document"


def site_stem(key: str, name: str | None) -> str:
    """The one place a site's `key — name` label is composed.

    Used for the site's folder and for the two files inside it that name
    the site in their own filename. One function so the folder and the
    files can never disagree about the truncation.
    """
    return f"{clean(key, 40)} — {clean(name or 'unnamed', 60)}"


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path("data/exports/drive_staging"))
    # Bump this with the phase. It is the current release, not phase 1's:
    # the artefacts are named for the phase that produced them, so that a
    # citation of the phase 1 workbook keeps resolving after phase 2
    # ships beside it rather than on top of it.
    ap.add_argument("--release-dir", dest="release_dir", type=Path,
                    default=None,
                    help="folder whose workbook, database and reader go to the "
                         "Drive root; the release is the source of truth for "
                         "which generated artefacts belong together. Defaults "
                         "to the most recently written data/exports/*_build.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only the first N sites (for a dry look).")
    args = ap.parse_args()

    out = args.out
    sites_dir = out / "sites"
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            WITH latest AS (
              SELECT DISTINCT ON (application_id) application_id, verdict, confidence
              FROM triage ORDER BY application_id, inserted_at DESC)
            SELECT s.site_key, s.display_name, s.classification,
                   s.latitude, s.longitude,
                   a.id, a.application_ref, a.url, a.status,
                   a.date_received, a.date_decided, a.description,
                   coalesce(l.verdict, '?'), l.confidence,
                   a.raw_metadata->'agile_parties',
                   a.raw_metadata->'portal_status_observed'
            FROM sites s
            JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
            JOIN applications a ON a.id = m.application_id
            LEFT JOIN latest l ON l.application_id = a.id
            WHERE s.retired_at IS NULL
            ORDER BY s.site_key, a.application_ref""")
        rows = cur.fetchall()

        cur.execute("""SELECT application_id, url, kind, content_sha256,
                              bytes_path, fetched_at
                       FROM documents WHERE bytes_path IS NOT NULL
                       ORDER BY fetched_at, id""")
        docs_by_app: dict[int, list] = defaultdict(list)
        for app_id, url, kind, sha, bp, ft in cur.fetchall():
            docs_by_app[app_id].append((url, kind, sha, bp, ft))

        # Every verified finding, keyed by application and document hash so
        # each site's CSV can point at the exact file sitting beside it in
        # the same folder. The reader used to send people to the workbook
        # for these; the workbook never held them.
        # The adjudication columns are the point of the LEFT JOIN. Without
        # them the CSV shows every power figure as an equal finding --
        # including the ones adjudication identified as somebody else's:
        # a 30 GW national storage target and a 22,700 MW market forecast
        # both appear in these documents, and both would read as site
        # capacity to anyone opening the file. That is the exact
        # misreading the adjudication layer exists to prevent, and a CSV
        # built from `findings` alone walks straight past it.
        #
        # DISTINCT ON keeps one adjudication per finding, preferring a
        # decided verdict over 'unclear' and the most recent within that,
        # so a figure adjudicated by two models does not duplicate the row.
        cur.execute("""
            WITH adj AS (
              SELECT DISTINCT ON (finding_id)
                     finding_id, verdict, quantity_type, value_mw, unit_note
              FROM power_adjudication
              ORDER BY finding_id,
                       (verdict = 'unclear'),        -- decided verdicts first
                       inserted_at DESC)
            SELECT f.application_id, d.content_sha256,
                   coalesce(f.signal_family,''), f.signal_type,
                   f.value_text, f.value_number, f.value_unit,
                   f.evidence_text, f.evidence_page, f.model,
                   adj.verdict, adj.quantity_type, adj.value_mw, adj.unit_note,
                   d.pagination
            FROM findings f
            LEFT JOIN documents d ON d.id = f.document_id
            LEFT JOIN adj ON adj.finding_id = f.id
            ORDER BY f.application_id, d.content_sha256,
                     f.evidence_page NULLS LAST, f.id""")
        findings_by_app: dict[int, list] = defaultdict(list)
        for row in cur.fetchall():
            findings_by_app[row[0]].append(row[1:])

        cur.execute("""SELECT m.site_id, s.site_key, p.title, p.value_gbp,
                              p.floor_area, p.stage_summary
                       FROM site_members m
                       JOIN sites s ON s.id = m.site_id
                       JOIN projects p ON p.id = m.project_id
                       WHERE m.retired_at IS NULL""")
        barbour_by_key: dict[str, list] = defaultdict(list)
        for _sid, key, title, val, floor, stage in cur.fetchall():
            barbour_by_key[key].append((title, val, floor, stage))

    by_site: dict[str, list] = defaultdict(list)
    site_meta: dict[str, tuple] = {}
    for r in rows:
        by_site[r[0]].append(r)
        site_meta[r[0]] = (r[1], r[2], r[3], r[4])

    # Sites with no member applications — chiefly `barbour_only`: a project
    # Barbour records that we hold no planning application for. Their
    # absence is itself data (either the application is filed under a
    # reference we have not matched, or the scheme has not reached planning),
    # so they get a folder saying so rather than silently vanishing from
    # the handover.
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key, s.display_name, s.classification,
                   s.latitude, s.longitude
            FROM sites s
            WHERE s.retired_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM site_members m
                WHERE m.site_id = s.id AND m.retired_at IS NULL
                  AND m.application_id IS NOT NULL)
            ORDER BY s.site_key""")
        for key, name, cls, lat, lng in cur.fetchall():
            by_site.setdefault(key, [])
            site_meta[key] = (name, cls, lat, lng)

    site_keys = sorted(by_site)
    if args.limit:
        site_keys = site_keys[: args.limit]

    n_docs = n_apps = n_findings_csv = 0
    for key in site_keys:
        name, cls, lat, lng = site_meta[key]
        stem = site_stem(key, name)
        folder = sites_dir / stem
        findings_name = f"_findings — {stem}.csv"
        report_name = f"_site_report — {stem}.md"
        # (application_ref, doc file-or-absence, page, family, type, value,
        #  number, unit, quote, model) rows accumulated across this site's
        # applications, written as the findings CSV beside the site report.
        site_csv_rows: list[tuple] = []
        report = [f"# {name or key}", "",
                  f"**Site key:** `{key}`  ",
                  f"**Classification:** {cls}  ",
                  f"**Coordinates:** {lat}, {lng}" if lat else "**Coordinates:** not yet geocoded",
                  ""]
        if barbour_by_key.get(key):
            report.append("## Barbour ABI project record(s)")
            report.append("")
            for title, val, floor, stage in barbour_by_key[key]:
                bits = [f"**{title}**"]
                if val: bits.append(f"value £{val:,.0f}")
                if floor: bits.append(f"floor area {floor}")
                if stage: bits.append(stage)
                report.append("- " + " — ".join(bits))
            report.append("")
        report += ["## Planning applications", ""]
        if not by_site[key]:
            report += [
                "**No planning applications identified for this site.**", "",
                "This site comes from the Barbour ABI construction record "
                "above; no planning application in our universe has been "
                "matched to it. That can mean the application is filed under "
                "a reference we have not yet linked, that it sits on a portal "
                "we cannot reach, or that the scheme has not reached the "
                "planning stage. The absence is recorded rather than hidden: "
                "it is a lead, not a gap in the record.", "",
            ]

        for r in by_site[key]:
            (_, _, _, _, _, app_id, ref, url, status, received, decided,
             desc, verdict, conf, parties, observed) = r
            n_apps += 1
            app_docs = docs_by_app.get(app_id, [])
            report.append(f"### {ref}")
            report.append("")
            if desc:
                report.append(f"> {desc.strip()[:600]}")
                report.append("")
            report.append(f"- **Verdict (v1 triage):** {verdict}"
                          + (f" ({conf})" if conf else ""))
            report.append(f"- **Status:** {status or 'unknown'}"
                          f"  |  received {received or '—'}"
                          f"  |  decided {decided or '—'}")
            if parties:
                pretty = ", ".join(f"{k}: {v}" for k, v in parties.items())
                report.append(f"- **Parties (portal record):** {pretty}")
            if observed and isinstance(observed, dict):
                appl = observed.get("applicant"); agent = observed.get("agent")
                if appl or agent:
                    report.append(f"- **Parties (observed on portal):** "
                                  f"applicant {appl or '—'}; agent {agent or '—'}")
            env = signals.flatten(signals.environmental_signals(desc))
            if env:
                report.append(f"- **Environmental subjects (description):** "
                              + "; ".join(env))
            report.append(f"- **Portal page:** {url or '—'}")
            report.append(f"- **Documents held:** {len(app_docs)}"
                          + (f" — see `{clean(ref.replace('/', '_'), 60)}/`"
                             if app_docs else ""))
            report.append("")

            sha_to_fname: dict[str, str] = {}
            if app_docs:
                app_folder = folder / clean(ref.replace("/", "_"), 60)
                index = [f"# Documents — {ref}", "",
                         f"Source: {url or 'obtained by hand'}", "",
                         "| file | document | source |", "|---|---|---|"]
                used: set[str] = set()
                for i, (durl, kind, sha, bp, _ft) in enumerate(app_docs, 1):
                    src = Path(bp)
                    if not src.is_absolute():
                        src = Path.cwd() / bp
                    if not src.exists():
                        continue
                    base = clean(kind or "document")
                    fname = f"{i:03d} - {base}{src.suffix}"
                    if fname.lower() in used:
                        fname = f"{i:03d} - {base} [{sha[:8]}]{src.suffix}"
                    used.add(fname.lower())
                    link_or_copy(src, app_folder / fname)
                    n_docs += 1
                    # The CSV references documents by these exact names, so
                    # the mapping is captured here, in the loop that assigns
                    # them — a second script recomputing the numbering would
                    # drift the moment this one changed.
                    sha_to_fname[sha] = f"{clean(ref.replace('/', '_'), 60)}/{fname}"
                    shown_url = durl if not durl.startswith("file://") else "obtained by hand"
                    index.append(f"| {fname} | {kind or '—'} | {shown_url} |")
                (app_folder / "_index.md").write_text("\n".join(index) + "\n")

            for (sha, family, stype, vtext, vnum, vunit, quote, page,
                 model, verdict, qty, mw, unit_note,
                 pagination) in findings_by_app.get(
                     app_id, ()):
                doc_file = sha_to_fname.get(sha) if sha else None
                # Spelled out rather than passed through as a code, because
                # this file is read by people and opened in Excel. A blank
                # means the finding is not a power figure and was never put
                # to adjudication -- which is different from being judged
                # and set aside, and the two must not look alike.
                whose = {
                    "site_capacity":  "this development",
                    "market_context": "NOT this site — market or sector context",
                    "policy_target":  "NOT this site — policy target",
                    "comparator":     "NOT this site — a different named scheme",
                    "unclear":        "could not be attributed from the quote",
                }.get(verdict, "" if verdict is None else verdict)
                site_csv_rows.append((
                    ref,
                    doc_file or "(document not in this folder)",
                    extract.cite_page(page, pagination),
                    family, stype, vtext,
                    vnum if vnum is not None else "",
                    vunit or "", quote, model,
                    whose,
                    qty or "",
                    f"{mw:g}" if mw is not None else "",
                    unit_note or ""))

        folder.mkdir(parents=True, exist_ok=True)
        if site_csv_rows:
            # utf-8-sig: the BOM is what makes Excel open a UTF-8 CSV
            # correctly on double-click, and Sheets ignores it.
            with (folder / findings_name).open("w", newline="",
                                               encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["application", "document file",
                            "where in the document", "signal family",
                            "signal type", "value", "number", "unit",
                            "verbatim quote", "extracted by",
                            "whose figure is this?", "quantity type",
                            "adjudicated MW", "quantity note"])
                w.writerows(site_csv_rows)
            n_findings_csv += len(site_csv_rows)
            report.append(f"## Findings")
            report.append("")
            report.append(
                f"`{findings_name}` in this folder holds all "
                f"{len(site_csv_rows):,} verified findings extracted from "
                f"this site's documents — each row names the document file "
                f"it came from (in the application folders here), where in "
                f"that document it appears, the verbatim quote, and the "
                f"model that read it. Only a PDF has pages, so a Word "
                f"file cites a section and a workbook a sheet. Every "
                f"quote was checked against the source text before it was "
                f"stored.")
            report.append("")
            report.append(
                "**Read the 'whose figure is this?' column before quoting any "
                "megawatt number.** Planning documents argue for approval by "
                "citing the market, so a figure appearing in this site's "
                "documents is often about something else entirely — a "
                "national policy target, a competitor's scheme, a sector "
                "forecast. Each power figure has been adjudicated for whose "
                "it is, and only those marked *this development* describe "
                "the site. A blank means the finding is not a power figure "
                "and was never put to adjudication, which is different from "
                "having been judged and set aside.")
            report.append("")
        (folder / report_name).write_text("\n".join(report) + "\n")
        # The previous build wrote these two under bare names. They are
        # hard links into nothing and cheap to drop, but leaving them
        # would ship both spellings of the same file in the same folder.
        for superseded in ("_findings.csv", "_site_report.md"):
            (folder / superseded).unlink(missing_ok=True)

    # Root artefacts. Three things and no more: the documents, the
    # workbook, and the database. The explanatory material — README,
    # methodology, data dictionary — used to ship here as markdown beside
    # them, which meant three files nobody opens from a Drive listing and
    # a fourth copy of every definition to keep in step. It now lives in
    # the reader, generated from the same queries as the data, so it
    # cannot drift out of date the way a companion document does.
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("README.md", "data_dictionary.md", "methodology.md"):
        (out / stale).unlink(missing_ok=True)
    # The release folder is the source of these, not data/exports at large:
    # globbing the exports directory picked up every workbook and database
    # ever generated, so the Drive root offered a reader three dated
    # spreadsheets and no way to tell which one the reader.html agreed with.
    for old_artefact in out.glob("dc_build_handover_*.xlsx"):
        old_artefact.unlink()
    release = Path(args.release_dir) if args.release_dir else (
        release_mod.latest_release_dir(Path("data/exports/phase1_build")))
    if not args.release_dir:
        print(f"   release folder: {release} (newest; --release-dir overrides)")
    staged_root = []
    if release.is_dir():
        for f in sorted(release.iterdir()):
            if f.suffix.lower() in (".xlsx", ".duckdb", ".html"):
                # Drop the old entry first. `link_or_copy` skips a
                # destination that already exists, which is right for the
                # 46,000 content-hashed documents and wrong here: a
                # regenerated artefact keeps its name. The workbook and
                # reader survived only because their writers truncate the
                # existing inode, so the hard link saw the new bytes —
                # DuckDB replaces the file instead, and staging quietly
                # kept pointing at a database eight hours out of date.
                (out / f.name).unlink(missing_ok=True)
                link_or_copy(f, out / f.name)
                staged_root.append(f.name)
    else:
        workbooks = sorted(Path("data/exports").glob("dc_build_handover_*.xlsx"))
        if workbooks:
            shutil.copyfile(workbooks[-1], out / workbooks[-1].name)
            staged_root.append(workbooks[-1].name)
    print("   root artefacts: " + (", ".join(staged_root) or "none"))
    print(f"staged {len(site_keys)} sites, {n_apps} applications, "
          f"{n_docs} documents, {n_findings_csv:,} findings rows in "
          f"per-site CSVs -> {out}")


if __name__ == "__main__":
    main()
