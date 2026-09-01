#!/usr/bin/env python3
"""Check a sample of the universe reached Drive — end to end, by file id.

The sync's own counters say what it believes it did. They are not
evidence. On 2026-08-09 they read perfectly while half a sample of ten
files had gone into a *second* archive at My Drive root, created because
a name lookup found nothing under the `drive.file` scope — the counters
cannot see a wrong parent, only a successful upload.

**The sample frame is the universe, not the ledger.** Until 2026-08-26
this drew its sample from `data/exports/.drive_sync_state.json`, which is
a record of what was uploaded from the staging tree — so its frame was
the tree, and a document that never reached the tree could not be
sampled. That is precisely the failure it was asked to catch: 3,679
documents held for 143 applications discovered on 2026-08-07 had no site
membership until 2026-08-25, so `build_drive_staging.py` never staged
them, the 2026-08-21 sync never saw them, and a ledger-framed check would
have passed on every sample it could ever have drawn. A check whose frame
is derived from the thing it is checking cannot find an omission.

So the frame is now `documents`: every document we hold whose application
belongs to a live site. For each one sampled the check follows the whole
chain —

    the database says we hold it
      → is it in the staging tree, at the path the builder would give it?
        → is it in the upload ledger?
          → does Drive have it, with those bytes, under the handover root?

— and any link that breaks is a failure, named as the link that broke.
The expected path is computed by `build_drive_staging.document_filenames`,
the same function the build uses, so the check cannot disagree with the
build about what a document is called.

The release artefacts are checked as before, from the ledger: they are
not documents and have no row to sample.

Read-only. It creates nothing and changes nothing.

    scripts/verify_drive_sample.py                 # 12 documents + the root artefacts
    scripts/verify_drive_sample.py --sample 40 --phase 2.7
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402
from dcp import release  # noqa: E402
from dcp.drive import FOLDER_ID, SYNC_LEDGER  # noqa: E402

STATE_PATH = SYNC_LEDGER
DEFAULT_STAGING = release.EXPORTS / "drive_staging"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parent_chain(svc, file_id: str, stop_at: str, limit: int = 8) -> list[str]:
    """Folder ids from this file upwards, nearest first, stopping at the root.

    The walk stops when it reaches `stop_at`, and treats a 404 above that
    as the end rather than an error: the grant is `drive.file`, so the
    tool can only see files it created, and the handover root's own
    parent was made by a human in a browser. That 404 is the scope
    working as intended — the same narrowness that makes a stray upload
    invisible to the sync, which is why this check exists at all.
    """
    chain, cur = [], file_id
    for _ in range(limit):
        try:
            meta = svc.files().get(fileId=cur, fields="parents").execute()
        except Exception:
            break
        parents = meta.get("parents") or []
        if not parents:
            break
        chain.append(parents[0])
        if parents[0] == stop_at:
            break
        cur = parents[0]
    return chain


# Every document we hold that the builder is supposed to stage: one whose
# application has a live site membership, or — since 2026-09-02 — one
# whose application is an adjacent-power scheme with no membership,
# staged under `adjacent_power/` beside `sites/`. The complement of this
# set is what `build_drive_staging.py` counts and refuses on; between
# them the two cover every document with bytes on disk. A frame that
# left the adjacent class out could never see one of its documents go
# missing, which is the reason this script samples the universe at all.
IN_UNIVERSE_SQL = """
    WITH latest AS (
      SELECT DISTINCT ON (application_id) application_id, verdict
        FROM triage ORDER BY application_id, inserted_at DESC)
    SELECT d.id
      FROM documents d
      JOIN site_members m ON m.application_id = d.application_id
                         AND m.retired_at IS NULL
      JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
     WHERE d.bytes_path IS NOT NULL
    UNION
    SELECT d.id
      FROM documents d
      JOIN latest l ON l.application_id = d.application_id
     WHERE d.bytes_path IS NOT NULL
       AND l.verdict = 'adjacent_power'
       AND NOT EXISTS (SELECT 1 FROM site_members m
                        WHERE m.application_id = d.application_id
                          AND m.retired_at IS NULL)
"""

# The sampled documents, plus every sibling in the same application:
# the staged filename carries a numeric prefix counted over the
# application's whole document list, so a document's expected path cannot
# be derived without its siblings.
DETAIL_SQL = """
    WITH picked AS (
      SELECT DISTINCT d.application_id
        FROM documents d WHERE d.id = ANY(%s))
    SELECT a.id, a.application_ref, s.site_key, s.display_name,
           d.id, d.url, d.kind, d.content_sha256, d.bytes_path, d.fetched_at
      FROM picked p
      JOIN applications a ON a.id = p.application_id
      JOIN documents d ON d.application_id = a.id AND d.bytes_path IS NOT NULL
      LEFT JOIN site_members m ON m.application_id = a.id AND m.retired_at IS NULL
      LEFT JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
     ORDER BY a.id, d.fetched_at, d.id
"""
# The LEFT JOINs are what let an adjacent-power application through with
# no site: its expected path is under `adjacent_power/` rather than a
# site folder, and `expected_paths` branches on the absent site key.


def sample_universe(cur, n: int,
                    rng: random.Random) -> tuple[list[int], int]:
    cur.execute(IN_UNIVERSE_SQL)
    ids = [r[0] for r in cur.fetchall()]
    return sorted(rng.sample(ids, min(n, len(ids)))), len(ids)


def expected_paths(cur, doc_ids: list[int], staging: Path,
                   bds) -> list[dict]:
    """Where each sampled document should be sitting, per the builder."""
    cur.execute(DETAIL_SQL, (doc_ids,))
    by_app: dict[int, list] = defaultdict(list)
    meta: dict[int, tuple] = {}
    for (app_id, ref, site_key, site_name, doc_id, url, kind, sha, bp,
         ft) in cur.fetchall():
        meta[app_id] = (ref, site_key, site_name)
        by_app[app_id].append((doc_id, (url, kind, sha, bp, ft)))

    wanted = set(doc_ids)
    out = []
    for app_id, rows in by_app.items():
        ref, site_key, site_name = meta[app_id]
        stem = bds.site_stem(site_key, site_name)
        named = bds.document_filenames(ref, [r[1] for r in rows])
        for (doc_id, row), (sha, src, relpath, _url, kind, exists) in zip(
                rows, named):
            if doc_id not in wanted:
                continue
            if not relpath:
                path = None
            elif site_key:
                path = staging / "sites" / stem / relpath
            else:
                path = staging / bds.ADJACENT_DIR / relpath
            out.append({
                "doc_id": doc_id, "ref": ref, "site_key": site_key,
                "sha": sha, "kind": kind, "source": src, "exists": exists,
                "path": path,
            })
    return out


def ledger_key(path: Path) -> str:
    """The key the sync wrote for a staged path.

    `drive_sync.py` keys its ledger on the path it was handed, which the
    runbook passes repository-relative (`data/exports/drive_staging/…`).
    Since R7 the staging default here is absolute, and on 2026-09-01 an
    exact-string lookup then reported every sampled document as "NOT IN
    THE UPLOAD LEDGER" while the recorder, matching on the path's tail,
    found 55,944 of them — the verifier failing in a way that read as
    the tree failing. Absolute paths under the repository resolve to the
    relative key; anything else is looked up as given.
    """
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return str(path)


def check_document(item: dict, ledger: dict, svc) -> list[str]:
    """Every link in the chain from `documents` row to bytes on Drive."""
    if not item["exists"]:
        return [f"canonical store has no bytes at {item['source']}"]
    local = item["path"]
    if not local.exists():
        return ["NOT IN THE STAGING TREE — the builder did not put it at "
                f"{local}"]
    entry = ledger.get(ledger_key(local)) or ledger.get(str(local))
    if entry is None:
        return ["NOT IN THE UPLOAD LEDGER — it is in the tree and no sync "
                "has ever sent it"]
    problems = []
    try:
        meta = svc.files().get(
            fileId=entry["id"],
            fields="name, size, md5Checksum, trashed, parents").execute()
    except Exception as exc:
        return [f"MISSING ON DRIVE: {str(exc)[:90]}"]
    if meta.get("trashed"):
        problems.append("in the bin")
    if meta.get("md5Checksum") and meta["md5Checksum"] != md5_of(local):
        problems.append("md5 differs from local")
    if meta.get("size") and int(meta["size"]) != local.stat().st_size:
        problems.append(f"size {meta['size']} vs local {local.stat().st_size}")
    chain = parent_chain(svc, entry["id"], FOLDER_ID)
    if FOLDER_ID not in chain:
        problems.append(f"parent chain does not reach the handover root "
                        f"({' -> '.join(chain[:3]) or 'none'})")
    return problems


def check_artefacts(ledger: dict, svc, phase: str | None) -> tuple[int, int]:
    """The release artefacts at the tree root, from the ledger.

    They are the one thing here with no row in `documents` to sample, and
    the one thing everybody opens.
    """
    keys = [k for k in ledger
            if Path(k).parent.name == "drive_staging"
            and Path(k).suffix.lower() in (".xlsx", ".duckdb", ".html")]
    bad = legacy = 0
    for key in sorted(keys):
        local = Path(key)
        entry = ledger[key]
        problems = []
        try:
            meta = svc.files().get(
                fileId=entry["id"],
                fields="name, size, md5Checksum, trashed, parents").execute()
        except Exception as exc:
            meta = {}
            problems.append(f"MISSING: {str(exc)[:80]}")
        if meta.get("trashed"):
            problems.append("in the bin")
        if local.exists() and meta:
            if meta.get("md5Checksum") and meta["md5Checksum"] != md5_of(local):
                problems.append("md5 differs from local")
            if meta.get("size") and int(meta["size"]) != local.stat().st_size:
                problems.append(f"size {meta['size']} vs local "
                                f"{local.stat().st_size}")
        elif not local.exists():
            problems.append("no local file to compare")
        if meta:
            chain = parent_chain(svc, entry["id"], FOLDER_ID)
            if FOLDER_ID not in chain:
                problems.append("parent chain does not reach the handover root")
        # A previous release's artefact is not this release's problem.
        # Phase 1's workbook and database have sat outside the handover
        # root since before this check existed, and phase 2's joined
        # them; that is worth reporting and is not a reason to hold a
        # release that put its own files in the right place.
        current = phase is None or f"phase{phase}" in local.name \
            or local.name == "reader.html"
        mark = ("FAIL" if problems and current
                else "note" if problems else "ok  ")
        if problems and current:
            bad += 1
        else:
            legacy += bool(problems)
        print(f"  {mark} {local.name[:58]:60}"
              + ("  " + "; ".join(problems) if problems else ""))
    return bad, legacy


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--seed", type=int, default=None,
                    help="fix the sample for a repeatable check")
    ap.add_argument("--staging", type=Path, default=DEFAULT_STAGING,
                    help="the staging tree the ledger was built from")
    ap.add_argument("--phase", default=None,
                    help="which release is being verified, e.g. 2.7. Older "
                         "releases' artefacts are then reported but do not "
                         "fail the check.")
    args = ap.parse_args()

    ds = _load_script("drive_sync")
    bds = _load_script("build_drive_staging")
    svc = ds.get_service()

    ledger = json.loads(STATE_PATH.read_text())["files"]
    rng = random.Random(args.seed)

    with db.connect() as conn, conn.cursor() as cur:
        doc_ids, universe = sample_universe(cur, args.sample, rng)
        items = expected_paths(cur, doc_ids, args.staging, bds)

    print(f"handover root: {FOLDER_ID}")
    print(f"frame: {universe:,} documents held for applications with a live "
          f"site — the universe, not the ledger")
    print(f"checking {len(items)} sampled documents plus the release "
          f"artefacts\n")

    bad = 0
    for item in sorted(items, key=lambda i: (i["ref"], i["doc_id"])):
        problems = check_document(item, ledger, svc)
        shown = item["path"].name if item["path"] else f"document {item['doc_id']}"
        print(f"  {'FAIL' if problems else 'ok  '} {item['ref'][:28]:30} "
              f"{shown[:44]:46}"
              + ("  " + "; ".join(problems) if problems else ""))
        bad += bool(problems)

    print()
    art_bad, legacy = check_artefacts(ledger, svc, args.phase)
    print()
    if legacy:
        print(f"{legacy} older artefact(s) flagged — pre-existing, not from "
              f"this run; see the note in the runbook about the phase 1 and "
              f"phase 2 files sitting outside the handover root")
    if bad or art_bad:
        print(f"{bad} of {len(items)} sampled documents and {art_bad} release "
              f"artefact(s) failed for THIS release — do not announce it")
        return 1
    print(f"this release verified: {len(items)} documents drawn from the "
          f"universe are in the tree, in the ledger, and on Drive with the "
          f"right bytes under the right parent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
