#!/usr/bin/env python3
"""Put the operator snapshots on Drive, and record where each one landed.

WP-B of docs/HANDOVER_SNAPSHOT_CHAIN.md. The claims channel's evidence
is a committed snapshot of an operator's page; every other evidence
class in this handover means Drive when it says "our copy", and this
makes the snapshots mean the same thing.

**It could not run before the store was append-only.** A store that
overwrote in place would have put an "our copy" link on a file the
claim beside it no longer matched — the wrong-document failure
`document_drive_files` exists to prevent, one layer up. Dated files
never change after upload, so this sync is pure addition: no rename to
chase, no prune to get wrong, and re-running it uploads nothing.

## Folder creation is a separate, asked-for act

The grant is `drive.file`, so this tool can only see what it created —
which is exactly how a name lookup once failed to find the operator's
handover folder and silently built a second copy of the whole archive
at My Drive root. So there is no name resolution here at all:

- `--create-folder` creates the snapshots folder under the handover
  root, reads the created id back with `files.get` to prove it exists
  where it was asked for, prints it, and stops. Paste it into
  `dcp/drive.SNAPSHOTS_FOLDER_ID`.
- Every other run addresses that constant, and `files.get`s it first.
  A 404 stops the run. It never falls back to creating one.

## The ledger is the committed YAML

`data/external_sources/operator_snapshots_drive.yaml`, keyed on the
snapshot filename. It is the record, not a cache derived from one:
`drive_sync.py`'s own state file is gitignored and belongs to the
document tree, and a second source of truth for the same fact is how
two trees came to hold 429 site folders each.

Every id is verified before it is written. Drive computes md5 server
side, so after upload the file is read back and its md5 and parent
checked against what was sent; an id that fails either is reported and
not recorded, because a link resolving to the wrong evidence is worse
than no link.

Usage:
    scripts/sync_snapshots_drive.py --create-folder   # once, then paste the id
    scripts/sync_snapshots_drive.py --dry-run
    scripts/sync_snapshots_drive.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dcp import drive, snapshot_drive
from dcp.capacity_claims import OPERATOR_SNAPSHOT_DIR

FOLDER_NAME = "operator_snapshots"


def _drive_sync():
    """The client machinery, reused; the ledger, deliberately not."""
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def create_folder(svc, retry) -> str:
    """Create the snapshots folder and prove it landed where asked."""
    fid = retry(lambda: svc.files().create(
        body={"name": FOLDER_NAME,
              "mimeType": "application/vnd.google-apps.folder",
              "parents": [drive.FOLDER_ID]},
        fields="id").execute())["id"]
    # Read it back rather than trusting the create. Under `drive.file` a
    # folder this tool cannot see is a folder it will happily duplicate,
    # so the id is only usable once something has confirmed it resolves
    # and sits under the handover root.
    meta = retry(lambda: svc.files().get(
        fileId=fid, fields="id, name, parents, trashed").execute())
    if meta.get("trashed") or drive.FOLDER_ID not in (meta.get("parents") or []):
        raise SystemExit(
            f"created folder {fid} does not read back under the handover "
            f"root {drive.FOLDER_ID}: {meta}")
    return fid


def require_folder(svc, retry, folder_id: str) -> None:
    """Stop on a folder id that no longer resolves. Never create one."""
    try:
        meta = retry(lambda: svc.files().get(
            fileId=folder_id, fields="id, name, parents, trashed").execute())
    except Exception as exc:
        raise SystemExit(
            f"dcp.drive.SNAPSHOTS_FOLDER_ID {folder_id} does not resolve: "
            f"{str(exc)[:160]}\nThis does NOT fall back to creating a folder — "
            f"that is how a second copy of the archive came to exist. Fix the "
            f"constant, or restore the folder from the Drive bin.") from exc
    if meta.get("trashed"):
        raise SystemExit(f"snapshots folder {folder_id} is in the Drive bin")


def upload_one(svc, retry, path: Path, folder_id: str, local_md5: str) -> dict:
    """Upload one snapshot and return a verified ledger entry.

    Raises if the copy Drive holds does not match the bytes sent, or
    landed anywhere but the snapshots folder.
    """
    from googleapiclient.http import MediaFileUpload

    fid = retry(lambda: svc.files().create(
        body={"name": path.name, "parents": [folder_id]},
        media_body=MediaFileUpload(str(path), mimetype="text/plain"),
        fields="id").execute())["id"]
    meta = retry(lambda: svc.files().get(
        fileId=fid, fields="id, md5Checksum, parents, trashed").execute())
    if meta.get("md5Checksum") != local_md5:
        raise ValueError(
            f"{path.name}: Drive holds md5 {meta.get('md5Checksum')} for "
            f"{fid} but the local file is {local_md5}")
    if folder_id not in (meta.get("parents") or []):
        raise ValueError(
            f"{path.name}: {fid} is not in the snapshots folder "
            f"(parents {meta.get('parents')})")
    return {"file_id": fid, "md5": local_md5,
            "uploaded": dt.datetime.now(dt.UTC).date().isoformat()}


def write_ledger(folder_id: str, entries: dict[str, dict],
                 path: Path = snapshot_drive.LEDGER_PATH) -> None:
    """Rewrite the ledger, in filename order so its diff is readable."""
    lines = [
        "# Where each operator snapshot's copy lives on Drive.",
        "#",
        "# Written by scripts/sync_snapshots_drive.py, read by",
        "# dcp/snapshot_drive.py. Keyed on the snapshot's own filename,",
        "# because the store is append-only and a claim is evidenced by the",
        "# reading it was taken from rather than by the newest one.",
        "#",
        "# Every id here was read back from Drive after upload and its md5",
        "# checked against the local bytes. Do not hand-edit: an id that",
        "# resolves to the wrong file is a working link under a citation",
        "# naming different evidence, which is the failure this file and",
        "# document_drive_files both exist to make impossible.",
        "#",
        "# Entries are never removed. A dated snapshot does not change, so",
        "# its copy stays valid for as long as anything cites it.",
        f"folder_id: {folder_id}",
        "files:",
    ]
    for name in sorted(entries):
        e = entries[name]
        lines.append(f"  {name}:")
        lines.append(f"    file_id: {e['file_id']}")
        lines.append(f"    md5: {e['md5']}")
        lines.append(f"    uploaded: {e['uploaded']}")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--create-folder", action="store_true",
                    help="create the snapshots folder under the handover "
                         "root, print its id, and stop")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be uploaded, send nothing")
    args = ap.parse_args()

    ds = _drive_sync()
    ledger = snapshot_drive.load_ledger()
    pending = snapshot_drive.unsynced(OPERATOR_SNAPSHOT_DIR, ledger)

    print(f"snapshots held        : "
          f"{len(list(OPERATOR_SNAPSHOT_DIR.glob('*.txt'))):,}")
    print(f"  already on Drive    : {len(ledger):,}")
    print(f"  to upload           : {len(pending):,}")

    if args.dry_run and not args.create_folder:
        for p in pending[:10]:
            print(f"    + {p.name}")
        if len(pending) > 10:
            print(f"    ... and {len(pending) - 10} more")
        print("\ndry run — nothing uploaded")
        return 0

    svc = ds.get_service(ds.get_credentials())
    # Sync is constructed for its retry policy alone — the network-outage
    # schedule that took an overnight run from fatal to resumable. Its
    # own ledger is read at construction and never written here.
    retry = ds.Sync(svc)._retry

    if args.create_folder:
        fid = create_folder(svc, retry)
        print(f"\ncreated {FOLDER_NAME} under the handover root")
        print(f"  folder id : {fid}")
        print(f"  url       : https://drive.google.com/drive/folders/{fid}")
        print("\nPaste that into dcp/drive.SNAPSHOTS_FOLDER_ID, then re-run "
              "without --create-folder.")
        return 0

    folder_id = drive.SNAPSHOTS_FOLDER_ID
    if not folder_id:
        raise SystemExit(
            "dcp.drive.SNAPSHOTS_FOLDER_ID is empty — run this with "
            "--create-folder once and paste the id it prints. Nothing is "
            "resolved by name here, deliberately.")
    require_folder(svc, retry, folder_id)

    if not pending:
        print("\nnothing to do — every held snapshot has a Drive id")
        return 0

    recorded, failed = dict(ledger), []
    for p in pending:
        try:
            recorded[p.name] = upload_one(svc, retry, p, folder_id,
                                          ds.md5_of(p))
            print(f"  uploaded {p.name}  -> {recorded[p.name]['file_id']}")
        except Exception as exc:  # noqa: BLE001
            failed.append((p.name, str(exc)[:160]))
            print(f"  FAILED {p.name}: {str(exc)[:160]}", file=sys.stderr)

    write_ledger(folder_id, recorded)
    print(f"\nrecorded {len(recorded) - len(ledger):,} new Drive file ids "
          f"in {snapshot_drive.LEDGER_PATH.name}")
    if failed:
        print(f"{len(failed)} failed and were NOT recorded", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
