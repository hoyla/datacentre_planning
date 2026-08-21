"""Create a new Google Sheet from a release workbook, and print its URL.

`sheet_sync.py` refreshes an existing Sheet in place, which is what keeps
hand formatting alive across regenerations — but it cannot add tabs, so a
release that introduces sheets (2.2 added four) needs a new Sheet rather
than a refresh. This makes one: the .xlsx is uploaded to the handover
folder with conversion, which produces a *native* Sheet — the kind with
an API behind it, as `dcp/drive.py` explains — carrying every tab.

The previous Sheet is deliberately left alone. A release lands beside its
predecessor so a citation of the older one keeps resolving; nothing here
renames, moves or bins anything.

Afterwards, put the new URL into `dcp/drive.py` as WORKBOOK_SHEET_URL so
the reader links to it and `sheet_sync.py` refreshes it from then on.
Formatting the new Sheet is a human job, once, and it then survives
every later sync.

Usage:
    scripts/create_workbook_sheet.py \
        --workbook data/exports/phase2.2_build/dc_handover_phase2.2.xlsx \
        --name DC_handover_v2_phase2.2
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from dcp.drive import FOLDER_ID

SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")


def _drive_service():
    """Reuse drive_sync's credentials rather than minting a second token —
    one consent, one token file, one thing to revoke."""
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get_service()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook", type=Path, required=True)
    ap.add_argument("--name", required=True,
                    help="Sheet title; name it for the release it holds.")
    ap.add_argument("--folder-id", default=FOLDER_ID,
                    help="Drive folder ID, never a name — a name lookup "
                         "silently created a duplicate archive once.")
    args = ap.parse_args()

    if not args.workbook.exists():
        sys.exit(f"no workbook at {args.workbook}")

    from googleapiclient.http import MediaFileUpload
    svc = _drive_service()
    media = MediaFileUpload(str(args.workbook), mimetype=XLSX_MIME,
                            resumable=True)
    created = svc.files().create(
        body={"name": args.name, "mimeType": SHEET_MIME,
              "parents": [args.folder_id]},
        media_body=media, fields="id,name,webViewLink").execute()

    print(f"created {created['name']}")
    print(f"  id:  {created['id']}")
    print(f"  url: {created['webViewLink']}")
    print("\nPut this in dcp/drive.py as WORKBOOK_SHEET_URL, then rebuild "
          "the reader so its links point at it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
