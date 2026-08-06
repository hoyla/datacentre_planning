"""Re-point application URLs whose portal host has migrated.

Councils replace their Public Access installs and leave the old host
serving an HTTP-200 notice page ("Public Access has a new URL"), which
a fetcher cannot distinguish from content. Where the successor host is
verified to preserve the Idox keyVal (probe one application first), a
host rewrite recovers the whole council.

Principle 3: the original URL is preserved in
``raw_metadata.previous_urls`` (append-only list) before ``url`` is
updated — the record of where we *used* to look is part of the audit
trail.

Verified mappings (2026-08-06): the Buckinghamshire family — the
pre-unitary Chiltern/South Bucks and Aylesbury Vale hosts both moved to
the unified Buckinghamshire Public Access, keyVal preserved (probed
ChilternSouthBucks/PL/20/0152/ADJ: documents parse on the new host).

Usage:
    .venv/bin/python scripts/remap_migrated_portals.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402

# old host -> verified successor host
HOST_MAP = {
    "pa-csb.buckinghamshire.gov.uk": "publicaccess.buckinghamshire.gov.uk",
    "publicaccess.aylesburyvaledc.gov.uk": "publicaccess.buckinghamshire.gov.uk",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        total = 0
        for old_host, new_host in HOST_MAP.items():
            cur.execute(
                "SELECT id, application_ref, url, raw_metadata FROM applications "
                "WHERE url LIKE %s", (f"%//{old_host}/%",))
            rows = cur.fetchall()
            print(f"{old_host} -> {new_host}: {len(rows)} applications")
            for app_id, ref, url, meta in rows:
                new_url = url.replace(f"//{old_host}/", f"//{new_host}/")
                if args.dry_run:
                    print(f"  {ref}: {new_url}")
                    continue
                meta = meta or {}
                prev = meta.get("previous_urls") or []
                prev.append(url)
                meta["previous_urls"] = prev
                cur.execute(
                    "UPDATE applications SET url=%s, raw_metadata=%s WHERE id=%s",
                    (new_url, json.dumps(meta), app_id))
                total += 1
        if not args.dry_run:
            conn.commit()
            print(f"Updated {total} application URLs (old URLs preserved "
                  f"in raw_metadata.previous_urls)")


if __name__ == "__main__":
    main()
