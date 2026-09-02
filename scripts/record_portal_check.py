#!/usr/bin/env python3
"""Record a portal check made by hand, as an acquisition outcome.

The adapters record what they conclude in `acquisition_outcome`, and
"checked and empty" stays distinct from "never tried" only because a row
says which. A person who opens the register and finds no documents has
made the same check with better eyes, and until 2026-09-02 that check
had nowhere to go except a SQL statement typed into a session (the four
`browser_probe` rows of August were written that way). This script is
that statement, with the provenance the row needs: who checked, when,
what they saw, and — when the page was printed to PDF — where the
capture is filed.

The capture is evidence of absence, so it is deliberately NOT ingested
as a document: an application that lists no documents must not come to
hold one. It goes beside the other hand-obtained bundles under
`data/raw/manual_bundles/<ref with : for />/`, gitignored like the rest
of `data/raw/`, and the outcome's detail names the path.

Append-only: a new row each time, never an update. The fold — latest
row per application — is `dcp.acquisition_outcome`'s and the exporters'.

Usage:
    .venv/bin/python scripts/record_portal_check.py \\
        --application-ref Midlothian/07/00051/FUL \\
        --outcome none_published \\
        --detail "Idox page lists no documents (Luke, by hand)" \\
        [--capture "data/raw/manual/.../page.pdf"] [--checked-by luke] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402
from dcp.acquisition_outcome import SETTLED  # noqa: E402

# What a person can conclude from a portal page. `error` is for a
# register that would not answer at all; the settled four are the
# verdicts that take an application off the queue, and each needs the
# detail to say what was seen.
HAND_OUTCOMES = tuple(SETTLED) + ("error",)
# The adapter name the August rows used for a browser check by hand;
# kept so the fold and the exporters see one route, not two.
ADAPTER = "browser_probe"
BUNDLES = Path("data/raw/manual_bundles")


def capture_destination(application_ref: str, capture: Path,
                        bundles: Path = BUNDLES) -> Path:
    """Where a page capture is filed: the bundle folder for its
    application (macOS-style `:` for `/`), under its own filename."""
    return bundles / application_ref.replace("/", ":") / capture.name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--application-ref", required=True)
    ap.add_argument("--outcome", required=True, choices=HAND_OUTCOMES)
    ap.add_argument("--detail", required=True,
                    help="what was seen, in words — this is the evidence")
    ap.add_argument("--capture", type=Path,
                    help="a PDF or image of the page as seen; moved beside "
                         "the other hand-obtained bundles and named in detail")
    ap.add_argument("--checked-by", default="hand")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.capture and not args.capture.is_file():
        ap.error(f"--capture {args.capture} is not a file")
    dest = capture_destination(args.application_ref, args.capture) if args.capture else None
    detail = (f"{args.detail.strip()} — checked by {args.checked_by} on "
              f"{dt.date.today().isoformat()}")
    if dest:
        detail += f"; page capture at {dest}"

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, url FROM applications WHERE application_ref = %s",
                    (args.application_ref,))
        row = cur.fetchone()
        if row is None:
            print(f"no application with reference {args.application_ref!r}",
                  file=sys.stderr)
            return 2
        app_id, url = row
        print(f"{args.application_ref} ({url})\n  -> {args.outcome}: {detail}")
        if args.dry_run:
            print("  dry run — nothing recorded, nothing moved")
            return 0
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(args.capture), str(dest))
            print(f"  capture filed at {dest}")
        cur.execute("""INSERT INTO acquisition_outcome
                         (application_id, outcome, adapter, detail,
                          documents_found, checked_at)
                       VALUES (%s, %s, %s, %s, 0, now()) RETURNING id""",
                    (app_id, args.outcome, ADAPTER, detail))
        print(f"  recorded acquisition_outcome row {cur.fetchone()[0]}")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
