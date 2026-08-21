"""Rebuild the Drive sync ledger from bulk listings, in minutes not hours.

`drive_sync.py` discovers the far side one file at a time: for each local
file it asks Drive "is there something of this name in this folder?".
That is the right shape for a sync — it has to hash and compare anyway —
but it means rebuilding a *lost* ledger costs one API round trip per
file. At 50,000 files and ~3/sec that is four hours of latency, at almost
no CPU and no bandwidth, purely to rediscover what Drive already knows.

Listing is far cheaper. Under the `drive.file` grant this tool can list
what it created, 1,000 items per request — so the whole tree comes back
in tens of calls rather than tens of thousands. This script does that and
writes the ledger the sync would eventually have written.

It never uploads, never creates and never trashes anything. The worst it
can do is produce a ledger that under-describes Drive, and the sync's own
per-file check corrects that on the next run.

Use it when `data/exports/` has been cleaned between releases, which
takes the ledger with it and leaves the reader and workbook claiming
every site is "not yet synced to Drive".

Usage:
    scripts/rebuild_drive_ledger.py --staging data/exports/drive_staging
    scripts/rebuild_drive_ledger.py --staging … --out /tmp/ledger.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

FOLDER_MIME = "application/vnd.google-apps.folder"
STATE_PATH = ROOT / "data" / "exports" / ".drive_sync_state.json"


def _service():
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get_service()


def _list_all(svc, q: str, fields: str) -> list[dict]:
    out, token = [], None
    while True:
        res = svc.files().list(
            q=q, fields=f"nextPageToken, files({fields})",
            pageSize=1000, pageToken=token).execute()
        out.extend(res.get("files", []))
        token = res.get("nextPageToken")
        print(f"    …{len(out):,}", end="\r", flush=True)
        if not token:
            break
    print(f"    {len(out):,} found      ")
    return out


def _key(local: Path) -> str:
    """The ledger key for a local file: its path as drive_sync saw it,
    which is relative to the repository root."""
    try:
        return str(local.resolve().relative_to(ROOT))
    except ValueError:
        return str(local)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", type=Path,
                    default=ROOT / "data" / "exports" / "drive_staging")
    ap.add_argument("--out", type=Path, default=STATE_PATH)
    ap.add_argument("--dest-id", default=None,
                    help="Drive folder ID the staging root maps to; "
                         "defaults to dcp.drive.FOLDER_ID.")
    args = ap.parse_args()

    if args.dest_id is None:
        from dcp.drive import FOLDER_ID
        args.dest_id = FOLDER_ID

    svc = _service()
    print("listing folders…")
    folders = _list_all(svc, f"mimeType='{FOLDER_MIME}' and trashed=false",
                        "id,name,parents")
    print("listing files…")
    files = _list_all(svc, f"mimeType!='{FOLDER_MIME}' and trashed=false",
                      "id,name,parents,md5Checksum")

    # Ledger shape, matching drive_sync.Syncer exactly:
    #   folders: "<parent id>/<name>" -> folder id
    #   files:   "<local path>"       -> {"md5", "id"}
    ledger_folders: dict[str, str] = {}
    by_parent_name: dict[tuple[str, str], dict] = {}
    for f in folders:
        for p in f.get("parents", []) or ["root"]:
            ledger_folders[f"{p}/{f['name']}"] = f["id"]
            by_parent_name[(p, f["name"])] = f
    for f in files:
        for p in f.get("parents", []) or ["root"]:
            by_parent_name[(p, f["name"])] = f

    # Walk the *local* tree and look each file up by (parent id, name).
    # Going local-first is what keeps this exact: Drive names are derived
    # from local ones, so reconstructing paths from Drive would have to
    # undo that derivation and guess. This direction never guesses — a
    # local file either has a counterpart at the expected place or it
    # does not, and "does not" simply leaves it for the sync to upload.
    ledger_files: dict[str, dict] = {}
    missing = 0
    dir_ids: dict[Path, str | None] = {args.staging: args.dest_id}

    def drive_id_for_dir(d: Path) -> str | None:
        if d in dir_ids:
            return dir_ids[d]
        parent_id = drive_id_for_dir(d.parent)
        fid = None
        if parent_id:
            hit = by_parent_name.get((parent_id, d.name))
            fid = hit["id"] if hit else None
        dir_ids[d] = fid
        return fid

    local_files = [p for p in args.staging.rglob("*") if p.is_file()]
    print(f"matching {len(local_files):,} local files…")
    for i, local in enumerate(local_files, 1):
        if i % 2000 == 0:
            print(f"    {i:,}/{len(local_files):,}", end="\r", flush=True)
        parent_id = drive_id_for_dir(local.parent)
        if not parent_id:
            missing += 1
            continue
        hit = by_parent_name.get((parent_id, local.name))
        if not hit:
            missing += 1
            continue
        # Prefer Drive's own md5 — it is what the sync compares against,
        # and taking it from the far side means this script never has to
        # read 131GB off disk to agree with it.
        md5 = hit.get("md5Checksum") or md5_of(local)
        # Key exactly as drive_sync does — `str(local)` for a path it was
        # handed relative to the working directory. An absolute key here
        # would produce a ledger that looks complete, shares not one entry
        # with the sync's, and silently re-does the whole tree.
        ledger_files[_key(local)] = {"md5": md5, "id": hit["id"]}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"folders": ledger_folders, "files": ledger_files}))
    print(f"\nwrote {args.out}")
    print(f"  {len(ledger_folders):,} folders, {len(ledger_files):,} files")
    print(f"  {missing:,} local files not found on Drive "
          f"(the sync will upload these)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
