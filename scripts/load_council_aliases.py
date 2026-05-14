"""Load the `council_aliases` table from a tracked YAML.

Operates on the production DB (`DATABASE_URL` from `.env`). Idempotent —
re-running on the same YAML upserts rather than duplicating.

Usage:
    scripts/load_council_aliases.py data/priors/council_aliases.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml_path", type=Path,
                    help="Aliases YAML (top-level `aliases: [{alias_name, gss_code, kind, notes}]`).")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.yaml_path.read_text())
    aliases = cfg.get("aliases", [])
    print(f"Loading {len(aliases)} aliases from {args.yaml_path.name}")

    with db.connect() as conn:
        with conn.cursor() as cur:
            for entry in aliases:
                cur.execute(
                    """
                    INSERT INTO council_aliases (alias_name, gss_code, kind, notes)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (alias_name) DO UPDATE SET
                        gss_code = EXCLUDED.gss_code,
                        kind = EXCLUDED.kind,
                        notes = EXCLUDED.notes
                    """,
                    (entry["alias_name"], entry["gss_code"], entry["kind"],
                     entry.get("notes")),
                )
        conn.commit()
    print(f"OK. {len(aliases)} aliases upserted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
