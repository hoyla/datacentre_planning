#!/usr/bin/env python3
"""Check a sample of synced files at the far side, by file id.

The sync's own counters say what it believes it did. They are not
evidence. On 2026-08-09 they read perfectly while half a sample of ten
files had gone into a *second* archive at My Drive root, created because
a name lookup found nothing under the `drive.file` scope — the counters
cannot see a wrong parent, only a successful upload.

So this asks Drive, per file id from the upload ledger: what is your
name, who is your parent, how big are you, and what is your md5. Then it
compares each against the local file the ledger says it came from, and
walks the parent chain to confirm it ends at the handover root rather
than somewhere else that looks the same.

Read-only. It creates nothing and changes nothing.

    scripts/verify_drive_sample.py                 # 12 random + the root artefacts
    scripts/verify_drive_sample.py --sample 40
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp.drive import FOLDER_ID  # noqa: E402

STATE_PATH = Path("data/exports/.drive_sync_state.json")


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--seed", type=int, default=None,
                    help="fix the sample for a repeatable check")
    ap.add_argument("--phase", default=None,
                    help="which release is being verified, e.g. 2.1. Older "
                         "releases' artefacts are then reported but do not "
                         "fail the check.")
    args = ap.parse_args()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    ds = importlib.util.module_from_spec(spec)
    sys.modules["drive_sync"] = ds
    spec.loader.exec_module(ds)
    svc = ds.get_service()

    ledger = json.loads(STATE_PATH.read_text())["files"]

    # The release artefacts always, then a random sample of the rest.
    # Checking only random files would pass while the one thing everybody
    # opens sat in the wrong folder.
    always = [k for k in ledger
              if Path(k).parent.name == "drive_staging"
              and Path(k).suffix.lower() in (".xlsx", ".duckdb", ".html")]
    rest = [k for k in ledger if k not in always]
    if args.seed is not None:
        random.seed(args.seed)
    picked = always + random.sample(rest, min(args.sample, len(rest)))

    print(f"handover root: {FOLDER_ID}")
    print(f"checking {len(picked)} files by id "
          f"({len(always)} release artefacts + {len(picked) - len(always)} sampled)\n")

    bad = legacy = 0
    for key in picked:
        entry = ledger[key]
        local = Path(key)
        try:
            meta = svc.files().get(
                fileId=entry["id"],
                fields="name, size, md5Checksum, trashed, parents").execute()
        except Exception as exc:
            print(f"  MISSING  {local.name}: {str(exc)[:90]}")
            bad += 1
            continue

        problems = []
        if meta.get("trashed"):
            problems.append("in the bin")
        if local.exists():
            if meta.get("md5Checksum") and meta["md5Checksum"] != md5_of(local):
                problems.append("md5 differs from local")
            if meta.get("size") and int(meta["size"]) != local.stat().st_size:
                problems.append(f"size {meta['size']} vs local "
                                f"{local.stat().st_size}")
        else:
            problems.append("no local file to compare")

        chain = parent_chain(svc, entry["id"], FOLDER_ID)
        if FOLDER_ID not in chain:
            problems.append(f"parent chain does not reach the handover root "
                            f"({' -> '.join(chain[:3]) or 'none'})")

        # A previous release's artefact is not this release's problem.
        # Phase 1's workbook and database have sat outside the handover
        # root since before this check existed, and phase 2's joined
        # them; that is worth reporting and is not a reason to hold a
        # release that put its own files in the right place.
        current = args.phase is None or f"phase{args.phase}" in local.name \
            or local.name == "reader.html"
        mark = ("FAIL" if problems and current
                else "note" if problems else "ok  ")
        if problems and current:
            bad += 1
        else:
            legacy += bool(problems)
        depth = len(chain)
        print(f"  {mark} {meta.get('name', '?')[:58]:60} depth {depth}"
              + ("  " + "; ".join(problems) if problems else ""))

    print()
    if legacy:
        print(f"{legacy} older artefact(s) flagged — pre-existing, not from "
              f"this run; see the note in the runbook about the phase 1 and "
              f"phase 2 files sitting outside the handover root")
    if bad:
        print(f"{bad} of {len(picked)} failed for THIS release — "
              f"do not announce it")
        return 1
    print(f"this release verified: right bytes, right folder, not binned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
