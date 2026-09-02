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
    ├── adjacent_power/               (power schemes beside sites, not in them)
    │   ├── _README.md
    │   └── <application_ref>/
    │       ├── _index.md            (documents, and the sites it stands beside)
    │       └── NNN - <derived name>.pdf
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

**The tree is rebuilt, not updated.** Everything under `sites/` is
written into a sibling `.building` directory and swapped in, so a folder
that has left the universe leaves the tree with it. It used to be purely
additive, which is how the Interxion folder came to hold 45 application
directories for a site with 16 (2026-08-25): after a re-partition the old
site folder kept the directories that had moved away, the same document
existed under two sites, and `drive_sync.py` could not recognise the move
because the old path was still there. The clean rebuild was folklore — a
step you had to know to take by hand — and is now what the script does.
The root is deliberately NOT swept: a released workbook or database from
an earlier phase is carried forward, because a citation of it has to keep
resolving. Additive at the root, exact under `sites/`.

**The script states its own shortfall and fails on it.** Two guards, both
of which would have fired on 2026-08-09 and 2026-08-21 and neither of
which existed then:

- *Before* building, it refuses when the site map is older than the
  universe it maps — a materialise that has not seen applications or
  Barbour projects discovered since. Membership is what decides whether a
  document is staged at all, so a stale map does not produce a slightly
  old tree, it produces a tree with holes in it that nothing downstream
  can see.
- *After* building, it counts the documents it did not stage, grouped by
  the application's latest triage verdict, and exits non-zero unless every
  one of them is triaged `not_dc`. `not_dc` is the only verdict that means
  "deliberately out of the handover"; anything else — including an
  application nobody has triaged yet — is material we hold and did not
  hand over.

That second guard is the one that matters, and it is stated as a count
rather than a boolean on purpose. On 2026-08-21 the sync was complete and
correct over the tree it was given (50,406 candidates, 0 failed, 0
skipped) and 3,679 documents held for 143 in-universe applications were
not in that tree, because those applications had been discovered on
2026-08-07 and had no site membership until the materialise of
2026-08-25. Nothing in the sync could see them: they were never in its
candidate set, so they could be neither `failed` nor `skipped`. A sync's
counters can only describe the tree it was handed. Only the builder knows
what the tree should have contained.

Usage:
    .venv/bin/python scripts/build_drive_staging.py [--out DIR] [--limit N]
    .venv/bin/python scripts/build_drive_staging.py --allow-stale-site-map
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

from dcp import adjacent_power as _adj  # noqa: E402
from dcp import db, extract, repo, signals  # noqa: E402
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


def app_dir_name(ref: str) -> str:
    """The application's directory name inside its site folder."""
    return clean(ref.replace("/", "_"), 60)


def document_filenames(ref: str, app_docs) -> list[tuple]:
    """Where each of an application's documents belongs in the tree.

    Returns `(sha, source path, path relative to the site folder, url,
    kind, source exists)` in the order the rows arrive, which is the
    order the numeric prefix counts in — so the caller must pass the
    documents exactly as the build query returns them (`fetched_at, id`).

    Extracted so there is one implementation of the derived name.
    `verify_drive_sample.py` computes the expected path from the same
    rows through this function; a second implementation would drift the
    moment the numbering changed, and the check would then disagree with
    the build while both looked right.

    A document whose bytes have gone from the canonical store still gets
    a name and still consumes its number — the prefix counts documents,
    not files present — and is reported rather than silently closing the
    gap in the sequence.
    """
    folder = app_dir_name(ref)
    used: set[str] = set()
    out: list[tuple] = []
    for i, (durl, kind, sha, bp, _ft) in enumerate(app_docs, 1):
        src = Path(bp)
        if not src.is_absolute():
            src = Path.cwd() / bp
        exists = src.exists()
        if not exists:
            out.append((sha, src, None, durl, kind, False))
            continue
        base = clean(kind or "document")
        fname = f"{i:03d} - {base}{src.suffix}"
        if fname.lower() in used:
            fname = f"{i:03d} - {base} [{sha[:8]}]{src.suffix}"
        used.add(fname.lower())
        out.append((sha, src, f"{folder}/{fname}", durl, kind, True))
    return out


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


# ---------------------------------------------------------------------------
# The clean rebuild
# ---------------------------------------------------------------------------

# Suffixes of a published artefact. The root accumulates these on purpose
# and `drive_sync.py --prune` already declines to touch the tree root for
# the same reason: phase 1's workbook has to keep resolving after phase 2
# ships beside it. Everything else at the root is regenerated or dropped.
RELEASED_SUFFIXES = (".xlsx", ".duckdb")


def carry_forward_released(old_root: Path, new_root: Path,
                           staged: list[str]) -> list[str]:
    """Move an earlier release's artefacts into the tree being built.

    The rebuild is exact under `sites/` and additive at the root, and the
    difference is the whole point. A folder that has left the universe
    must leave the tree, or the same document sits under two sites and
    `drive_sync.py` reads a move as a second upload. A *published*
    workbook or database is the opposite case: it left the release folder
    when the next release was built, and dropping it from the tree would
    retract an artefact somebody may have cited.
    """
    if not old_root.is_dir():
        return []
    carried = []
    for f in sorted(old_root.iterdir()):
        if not f.is_file() or f.name in staged:
            continue
        if f.suffix.lower() not in RELEASED_SUFFIXES:
            continue
        if f.name.startswith("dc_build_handover_"):
            continue          # the superseded naming, dropped on sight
        link_or_copy(f, new_root / f.name)
        carried.append(f.name)
    return carried


def swap_in(built: Path, final: Path, keep_superseded: bool = False) -> None:
    """Put the freshly built tree where the live one was.

    Two renames rather than a copy: the tree is 137 GB of hard links into
    `data/raw`, so both trees can exist at once for nothing, and the
    window in which neither is at the final path is the time between two
    `rename(2)` calls. If the second one fails, the previous tree is at
    `<final>.superseded` and this says so rather than leaving a hole.
    """
    superseded = final.with_name(final.name + ".superseded")
    shutil.rmtree(superseded, ignore_errors=True)
    had_previous = final.exists()
    if had_previous:
        final.rename(superseded)
    try:
        built.rename(final)
    except OSError:
        if had_previous:
            superseded.rename(final)
        raise
    if not had_previous:
        return
    if keep_superseded:
        print(f"   previous tree kept at {superseded}")
    else:
        shutil.rmtree(superseded, ignore_errors=True)
        print(f"   rebuilt clean: the previous tree was replaced, not "
              f"updated, so anything that left a site left the tree")


# ---------------------------------------------------------------------------
# Guard 1 — is the site map older than the universe it maps?
# ---------------------------------------------------------------------------

# Membership is a property of applications and Barbour projects, not of
# documents: `site_members` joins a site to one of those two, and nothing
# else decides whether this script stages a document. So the corpus this
# map has to be newer than is the set of *nodes*, and the test is whether
# any node entered the universe after the last materialise.
#
# `documents.fetched_at` is deliberately NOT part of it, though it is the
# obvious candidate. A refetch pass rewrites `fetched_at` on documents
# whose applications were mapped weeks ago, so a guard reading it would
# fail on every refetch while nothing was wrong — and a guard that cries
# wolf is worse than no guard, which the runbook already says once about
# `release_diff.py`. The case it would appear to cover, a document held
# for an application with no membership, is exactly what guard 2 counts,
# and counts by name rather than by timestamp.
STALE_MAP_SQL = """
    SELECT (SELECT max(materialised_at) FROM sites)                  AS materialised,
           (SELECT count(*) FROM applications
             WHERE first_seen_at > (SELECT max(materialised_at) FROM sites)),
           (SELECT count(*) FROM projects
             WHERE first_seen_at > (SELECT max(materialised_at) FROM sites))
"""

STALE_MAP_EXAMPLES_SQL = """
    SELECT application_ref, first_seen_at FROM applications
     WHERE first_seen_at > (SELECT max(materialised_at) FROM sites)
     ORDER BY first_seen_at DESC LIMIT 10
"""


def site_map_staleness(cur) -> dict:
    """How far behind the universe the last materialise is."""
    cur.execute(STALE_MAP_SQL)
    materialised, n_apps, n_projects = cur.fetchone()
    cur.execute(STALE_MAP_EXAMPLES_SQL)
    return {"materialised_at": materialised,
            "applications": n_apps or 0,
            "projects": n_projects or 0,
            "examples": cur.fetchall()}


def stale_map_lines(state: dict) -> tuple[list[str], bool]:
    """The always-printed block, and whether it is a refusal.

    Pure, so the rule can be tested without a database.
    """
    when = state["materialised_at"]
    stamp = when.isoformat(timespec="seconds") if when else "never"
    n_apps, n_proj = state["applications"], state["projects"]
    lines = [f"   site map: materialised {stamp}; "
             f"{n_apps} application(s) and {n_proj} Barbour project(s) "
             f"have entered the universe since"]
    if when is None:
        lines.append("   REFUSING: nothing has ever been materialised, so no "
                     "application has a site and the tree would be empty. "
                     "Run scripts/materialise_sites.py.")
        return lines, True
    if not (n_apps or n_proj):
        return lines, False
    for ref, seen in state["examples"]:
        lines.append(f"       {ref}  first seen {seen.isoformat(timespec='seconds')}")
    if n_apps > len(state["examples"]):
        lines.append(f"       ... and {n_apps - len(state['examples'])} more")
    lines.append(
        "   REFUSING: the site map is older than the universe it maps. An "
        "application with no site membership has no folder to be staged "
        "into, so its documents would be left out of the tree and out of "
        "the sync's candidate set — invisible to both its skipped and its "
        "failed counters. Run scripts/materialise_sites.py, then this. "
        "Pass --allow-stale-site-map only with a reason you can state.")
    return lines, True


# ---------------------------------------------------------------------------
# Guard 2 — what did the tree not contain, and was that on purpose?
# ---------------------------------------------------------------------------

# `not_dc` is the one verdict that means a document is out of the handover
# by decision. Every other value — and the absence of a verdict most of
# all — means we hold material the reader was not given and nobody chose
# that.
TOLERATED_VERDICT = "not_dc"
UNTRIAGED = "(not triaged)"

# `adjacent_power` is the other verdict with somewhere of its own to go —
# staged, not excused. Since issue #252 (2026-08-30) the clusterer
# refuses that class membership: a substation, an energy centre or a
# battery consented in its own right stands beside a site rather than
# belonging to it, and its capacity must never read as the site's own
# demand. So its documents cannot sit under a site folder — but they are
# held, in-universe, and cited (four of them by a machine reading at
# 2.11), and the first staging build after the veto found 744 of them
# with nowhere to go. They are filed under `adjacent_power/` beside
# `sites/` (Luke, 2026-09-02: "next to, rather than inside, sites"),
# and the shortfall below counts them as staged only once this build has
# actually written them.
ADJACENT_VERDICT = "adjacent_power"
ADJACENT_DIR = "adjacent_power"

# WHICH applications belong here is decided once, in
# `dcp.adjacent_power.staged_applications`, and read by this script, by
# `record_drive_ids.py` and by `verify_drive_sample.py`. Each used to
# carry its own copy of the rule, and on 2026-09-02 the copies agreed
# with each other and disagreed with the materialise about what "a
# member" meant — four applications' documents with no Drive home
# (#349). The shared rule also brings in a scheme's own paperwork: a
# discharge or amendment whose parent is an adjacent-power application
# is triaged `not_dc` (it is not a data centre and its text ties it only
# to its parent), so by verdict it fell to the shortfall's "excluded by
# decision" while its parent had a folder. Union Park's four discharges,
# 44 documents, until this landed.
ADJACENT_APPS_SQL = """
    SELECT a.id, a.application_ref, a.url, a.status,
           a.date_received, a.date_decided, a.description
      FROM applications a
     WHERE a.id = ANY(%s)
     ORDER BY a.application_ref
"""

# Which sites each adjacent scheme stands beside, and how that is known
# — the relationship table #252 built in place of membership.
RELATED_SQL = """
    SELECT ap.application_id, s.site_key, s.display_name,
           ap.basis, ap.distance_m
      FROM site_adjacent_power ap
      JOIN sites s ON s.id = ap.site_id AND s.retired_at IS NULL
     WHERE ap.retired_at IS NULL
     ORDER BY ap.application_id, ap.basis, s.site_key
"""

ADJACENT_README = """# Adjacent power

Power infrastructure consented in its own right — a substation, an
energy centre, a standby fleet, a battery — that stands beside a data
centre site rather than belonging to it.

Since 30 August 2026 these applications are not members of any site:
a substation's capacity could serve many purposes and must never read
as a site's own demand. Each site's page in the reader lists the
schemes beside it in its "Adjacent power" box, with how the connection
is known. Their documents are held exactly as a site's are and are
filed here, one folder per application, beside `sites/` rather than
inside any site's folder. Each folder's `_index.md` names the sites the
scheme stands beside and why.
"""


def stage_adjacent_power(out: Path, apps, docs_by_app,
                         related, why=None) -> tuple[set[str], int]:
    """Stage every application that belongs under `adjacent_power/`.

    `apps` are `ADJACENT_APPS_SQL` rows for the ids
    `dcp.adjacent_power.staged_applications` returned, `docs_by_app` the
    same document rows the site loop uses (so `document_filenames`
    numbers them identically, and `record_drive_ids.py` and
    `verify_drive_sample.py` derive the same names), `related` the
    `RELATED_SQL` rows keyed by application id, and `why` that
    function's dict — a scheme's own paperwork names its parent in its
    index and lists the sites the parent stands beside, since the
    relationship table has rows for the parent and none for a discharge
    of its conditions. Returns the references staged and the document
    count; an application with nothing held is skipped and not counted
    as staged, so the shortfall guard still sees it.
    """
    why = why or {}
    root = out / ADJACENT_DIR
    staged: set[str] = set()
    n_docs = 0
    for app_id, ref, url, status, received, decided, desc in apps:
        app_docs = docs_by_app.get(app_id, [])
        if not app_docs:
            continue
        folder = root / app_dir_name(ref)
        folder.mkdir(parents=True, exist_ok=True)
        index = [f"# Documents — {ref}", "",
                 f"Source: {url or 'obtained by hand'}", ""]
        if desc:
            index += [f"> {desc.strip()[:600]}", ""]
        info = why.get(app_id) or {}
        parent_ref = info.get("parent_ref")
        if parent_ref:
            index += [f"- **Status:** {status or 'unknown'}"
                      f"  |  received {received or '—'}"
                      f"  |  decided {decided or '—'}",
                      f"- **Paperwork of an adjacent-power scheme, not a "
                      f"site member:** a discharge, amendment or variation "
                      f"of `{parent_ref}` (folder `{app_dir_name(parent_ref)}` "
                      f"beside this one). Triage calls it `not_dc` because "
                      f"it is not a data centre and its text ties it only "
                      f"to that parent; it is filed here so the scheme's "
                      f"paperwork stays with the scheme.", ""]
            rel = related.get(info.get("parent_id"), [])
        else:
            index += [f"- **Status:** {status or 'unknown'}"
                      f"  |  received {received or '—'}"
                      f"  |  decided {decided or '—'}",
                      "- **Adjacent power, not a site member:** this scheme's "
                      "capacity is not any site's demand; see the reader's "
                      "'Adjacent power' box on the sites below.", ""]
            rel = related.get(app_id, [])
        if rel:
            index.append("Stands beside:")
            for key, name, basis, dist in rel:
                index.append(f"- {name or key} (`{key}`) — {basis}"
                             + (f", {dist:,.0f} m" if dist else ""))
            index.append("")
        index += ["| file | document | source |", "|---|---|---|"]
        for sha, src, relpath, durl, kind, exists in document_filenames(
                ref, app_docs):
            if not exists:
                continue
            fname = relpath.split("/", 1)[1]
            link_or_copy(src, folder / fname)
            n_docs += 1
            shown = durl if not durl.startswith("file://") else "obtained by hand"
            index.append(f"| {fname} | {kind or '—'} | {shown} |")
        (folder / "_index.md").write_text("\n".join(index) + "\n")
        staged.add(ref)
    if staged:
        (root / "_README.md").write_text(ADJACENT_README)
    return staged, n_docs

UNSTAGED_SQL = f"""
    WITH latest AS (
      SELECT DISTINCT ON (application_id) application_id, verdict
        FROM triage ORDER BY application_id, inserted_at DESC)
    SELECT coalesce(l.verdict, '{UNTRIAGED}') AS verdict,
           a.application_ref,
           count(d.id) AS n_docs
      FROM documents d
      JOIN applications a ON a.id = d.application_id
      LEFT JOIN latest l ON l.application_id = a.id
     WHERE d.bytes_path IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM site_members m
                        WHERE m.application_id = a.id
                          AND m.retired_at IS NULL)
     GROUP BY 1, 2
     ORDER BY 1, 3 DESC, 2
"""


def unstaged_documents(cur, staged_adjacent=frozenset()) -> list[tuple[str, str, int]]:
    """`(verdict, application_ref, document count)` for everything left out.

    A document is staged if its application has a live `site_members`
    row — the join at the top of this script — or, since 2026-09-02,
    if it is an adjacent-power application this build wrote under
    `adjacent_power/`. So this is the complement of the tree, computed
    from the universe rather than from the tree, which is the only way
    to see a document that never reached it. `staged_adjacent` is the
    set of references `stage_adjacent_power` actually wrote: an
    adjacent-power application it did not write stays in the shortfall
    and fails the build, because the class has a home now and an
    absence from it is not on purpose.
    """
    cur.execute(UNSTAGED_SQL)
    # Anything this build wrote under adjacent_power/ is staged, whatever
    # its verdict: a scheme's own discharges are `not_dc` and were being
    # reported as "held but not staged" while sitting in the tree.
    return [(v, ref, n) for v, ref, n in cur.fetchall()
            if ref not in staged_adjacent]


def shortfall_lines(rows: list[tuple[str, str, int]],
                    show: int = 12) -> tuple[list[str], bool]:
    """The always-printed shortfall block, and whether it is a failure.

    Pure, so the rule can be exercised without a database.
    """
    if not rows:
        return ["   shortfall: none — every document held is in this tree"], False
    by_verdict: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for verdict, ref, n in rows:
        by_verdict[verdict].append((ref, n))
    lines = ["   documents held but not staged, by latest triage verdict:"]
    for verdict in sorted(by_verdict, key=lambda v: (v == TOLERATED_VERDICT, v)):
        apps = by_verdict[verdict]
        ndocs = sum(n for _, n in apps)
        mark = "ok " if verdict == TOLERATED_VERDICT else "!! "
        lines.append(f"     {mark}{verdict:16} {ndocs:>7,} documents "
                     f"across {len(apps):>4} application(s)")
    held = [(v, r, n) for v, r, n in rows if v != TOLERATED_VERDICT]
    if not held:
        return lines, False
    ndocs = sum(n for _, _, n in held)
    apps = {r for _, r, _ in held}
    lines.append("")
    lines.append(f"   {ndocs:,} documents held for {len(apps):,} in-universe "
                 f"application{'' if len(apps) == 1 else 's'} "
                 f"are not in this tree")
    for verdict, ref, n in sorted(held, key=lambda r: (-r[2], r[1]))[:show]:
        lines.append(f"       {ref:44} {n:>6,} documents   [{verdict}]")
    if len(held) > show:
        lines.append(f"       ... and {len(held) - show} more application(s)")
    lines.append(
        "   A sync cannot see these. They were never in its candidate set, "
        "so they are neither its skipped nor its failed. Give each one a "
        "site (scripts/materialise_sites.py) or a triage verdict that says "
        "it is out of scope, and rebuild.")
    return lines, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=release_mod.EXPORTS / "drive_staging")
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
                    help="Only the first N sites (for a dry look). Writes to "
                         "a `.partial` sibling and never swaps: a subset of "
                         "the tree must not replace the tree.")
    ap.add_argument("--allow-stale-site-map", action="store_true",
                    help="Build even though applications or projects have "
                         "entered the universe since the last materialise. "
                         "The tree will be missing their documents.")
    ap.add_argument("--keep-superseded", action="store_true",
                    help="Leave the replaced tree at `<out>.superseded` "
                         "instead of removing it after the swap.")
    args = ap.parse_args()

    final = args.out
    # Build beside the live tree and swap, rather than writing into it.
    # See the module docstring: the additive build left application
    # directories behind after a re-partition, and a move drive_sync.py
    # cannot see is a document that exists twice on Drive.
    if args.limit:
        out = final.with_name(final.name + ".partial")
    else:
        out = final.with_name(final.name + ".building")
    sites_dir = out / "sites"
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    # Before anything is written: is the map we are about to stage from
    # older than the universe it maps? A stale map does not make an
    # out-of-date tree, it makes a tree with holes nothing downstream can
    # see, because a document with no site has no folder to be missing
    # from.
    with db.connect() as conn, conn.cursor() as cur:
        state = site_map_staleness(cur)
    lines, refuse = stale_map_lines(state)
    print("\n".join(lines))
    if refuse:
        if not args.allow_stale_site_map:
            raise SystemExit(1)
        print("   --allow-stale-site-map: building anyway")

    shutil.rmtree(out, ignore_errors=True)   # a previous run that died

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
                app_folder = folder / app_dir_name(ref)
                index = [f"# Documents — {ref}", "",
                         f"Source: {url or 'obtained by hand'}", "",
                         "| file | document | source |", "|---|---|---|"]
                # The CSV and `_index.md` reference documents by these exact
                # names, and so does verify_drive_sample.py. All three read
                # them off `document_filenames`, which is the only place the
                # numbering is decided.
                for sha, src, relpath, durl, kind, exists in document_filenames(
                        ref, app_docs):
                    if not exists:
                        continue
                    fname = relpath.split("/", 1)[1]
                    link_or_copy(src, app_folder / fname)
                    n_docs += 1
                    sha_to_fname[sha] = relpath
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

    # The adjacent-power schemes, beside the sites rather than inside
    # them. Skipped under --limit, which builds a subset of sites for a
    # look and must not be mistaken for the tree.
    staged_adjacent: set[str] = set()
    n_adj_docs = 0
    if not args.limit:
        with db.connect() as conn, conn.cursor() as cur:
            adjacent_why = _adj.staged_applications(cur)
            cur.execute(ADJACENT_APPS_SQL, (list(adjacent_why),))
            adjacent_apps = cur.fetchall()
            cur.execute(RELATED_SQL)
            related: dict[int, list] = defaultdict(list)
            for app_id, key, name, basis, dist in cur.fetchall():
                related[app_id].append((key, name, basis, dist))
        staged_adjacent, n_adj_docs = stage_adjacent_power(
            out, adjacent_apps, docs_by_app, related, why=adjacent_why)

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
    # Derived or explicit, never a named fallback, and never the
    # exports directory at large: `current_release_dir` refuses when
    # there is no release folder, which replaces both the `phase1_build`
    # default and the glob that used to stand in for a missing folder —
    # the three-dated-spreadsheets confusion the comment above records.
    release = release_mod.current_release_dir(
        Path(args.release_dir) if args.release_dir else None)
    if not args.release_dir:
        print(f"   release folder: {release} (newest; --release-dir overrides)")
    staged_root = []
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
    carried = carry_forward_released(final, out, staged_root)
    print("   root artefacts: " + (", ".join(staged_root) or "none")
          + (f"  (carried forward: {', '.join(carried)})" if carried else ""))

    if args.limit:
        print(f"--limit {args.limit}: left at {out}, NOT swapped in — a "
              f"subset of the tree must not replace the tree")
    else:
        swap_in(out, final, keep_superseded=args.keep_superseded)
    print(f"staged {len(site_keys)} sites, {n_apps} applications, "
          f"{n_docs} documents, {n_findings_csv:,} findings rows in "
          f"per-site CSVs -> {final if not args.limit else out}")
    print(f"   adjacent power: {len(staged_adjacent)} applications, "
          f"{n_adj_docs} documents under {ADJACENT_DIR}/, beside sites/")

    # A zero-byte document is a failed fetch stored before the guard
    # existed (HISTORY, 2.8): three are known, none can be re-fetched,
    # and nothing downstream tells "held and empty" from "held and
    # silent". The tree is hard links into the store, so sweeping it is
    # sweeping the store — and this runs every release, so a fourth would
    # announce itself here rather than in somebody's export.
    tree = final if not args.limit else out
    empties = repo.zero_byte_files(tree)
    print(f"   zero-byte documents in the tree: {len(empties)}"
          + (" — held but empty, unreadable by construction:"
             if empties else ""))
    for path in empties[:10]:
        print(f"     {path.relative_to(tree)}")
    if len(empties) > 10:
        print(f"     … and {len(empties) - 10:,} more")

    # What is NOT in the tree, said out loud, every run. The 2026-08-21
    # sync reported 50,406 candidates, 0 failed and 0 skipped over a tree
    # that was missing 3,679 documents; nothing in the sync could have
    # said so, because a document with no site membership never became a
    # candidate. Only the builder knows the difference between the tree
    # and the universe.
    with db.connect() as conn, conn.cursor() as cur:
        rows = unstaged_documents(cur, staged_adjacent)
    lines, failed = shortfall_lines(rows)
    print("\n".join(lines))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
