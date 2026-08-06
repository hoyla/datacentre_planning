"""Assemble the Drive-shaped handover tree from the canonical store.

Produces `data/exports/drive_staging/` — the exact structure agreed for
the Guardian data/visuals-team handover (ROADMAP, "Handover design") —
so the eventual upload is a single `rclone sync` once credentials exist.
Everything here is derived; the canonical store and database remain the
source of truth, and the tree is rebuilt rather than edited.

    drive_staging/
    ├── README.md                    (what this is, how to read it)
    ├── data_dictionary.md
    ├── methodology.md
    ├── dc_build_handover_<date>.xlsx
    └── sites/
        └── <site_key> — <site name>/
            ├── _site_report.md      (per-site summary: applications,
            │                         parties, signals, Barbour fields)
            └── <application_ref>/
                ├── _index.md        (document list with source URLs)
                └── NNN - <derived name>.pdf

Two deliberate choices:

- **Hard links, not copies.** The corpus is ~70GB; the staging tree
  shares inodes with the canonical store, so it costs directory entries,
  not disk. (Copy fallback if linking fails.)
- **Human-readable derived filenames.** The canonical store is
  content-hash named (right for provenance, useless in a Drive UI).
  Derived names come from the council's own document description, with a
  stable numeric prefix for ordering and a hash suffix on collisions.
  The mapping is recorded in each folder's `_index.md`.

Usage:
    .venv/bin/python scripts/build_drive_staging.py [--out DIR] [--limit N]
"""

from __future__ import annotations

import argparse
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

from dcp import db, signals  # noqa: E402

BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def clean(name: str, maxlen: int = 80) -> str:
    out = BAD.sub(" ", name or "").strip(" .")
    out = re.sub(r"\s+", " ", out)
    return out[:maxlen].strip(" .") or "document"


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

    n_docs = n_apps = 0
    for key in site_keys:
        name, cls, lat, lng = site_meta[key]
        folder = sites_dir / f"{clean(key, 40)} — {clean(name or 'unnamed', 60)}"
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

            if not app_docs:
                continue
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
                shown_url = durl if not durl.startswith("file://") else "obtained by hand"
                index.append(f"| {fname} | {kind or '—'} | {shown_url} |")
            (app_folder / "_index.md").write_text("\n".join(index) + "\n")

        folder.mkdir(parents=True, exist_ok=True)
        (folder / "_site_report.md").write_text("\n".join(report) + "\n")

    # Root artefacts.
    out.mkdir(parents=True, exist_ok=True)
    for doc in ("docs/data_dictionary.md", "docs/methodology.md"):
        p = Path(doc)
        if p.exists():
            shutil.copyfile(p, out / p.name)
    workbooks = sorted(Path("data/exports").glob("dc_build_handover_*.xlsx"))
    if workbooks:
        shutil.copyfile(workbooks[-1], out / workbooks[-1].name)
    (out / "README.md").write_text(f"""# UK data-centre planning dataset — source documents

Generated {generated} from the datacentre_planning pipeline. This tree is
**derived**: it is rebuilt from the canonical store, so do not edit files
here — annotations belong in the shared workbook's annotation tab.

- `dc_build_handover_*.xlsx` — the dataset interface (sites + applications).
- `data_dictionary.md` / `methodology.md` — what every field means, how the
  dataset was built, and what has been measured about its accuracy.
- `sites/` — one folder per site: a `_site_report.md` summary, then one
  folder per planning application holding its documents. Each application
  folder's `_index.md` maps the readable filenames to source URLs.

Documents marked "obtained by hand" were downloaded manually from portals
that block automated clients; their citable source is the application's
portal page. Consultation responses are reproduced as councils published
them and contain objectors' names and addresses. Barbour ABI project data
is licensed for this use; attribution is required in published output.
""")
    print(f"staged {len(site_keys)} sites, {n_apps} applications, "
          f"{n_docs} documents -> {out}")


if __name__ == "__main__":
    main()
