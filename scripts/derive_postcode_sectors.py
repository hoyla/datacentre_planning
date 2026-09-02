#!/usr/bin/env python3
"""Derive postcode-sector centroids from the ONS Postcode Directory.

The reader's "near a postcode" control (ROADMAP, Smaller things; decided
2026-09-02) works at sector precision — "SL1 4", about a kilometre —
because a lookup for "plans near you" needs to centre a map and list
sites within ten kilometres, not find a house (Luke: "we don't need
house addresses"). Roughly eleven thousand sectors are a few hundred
kilobytes in the page; 1.8 million unit postcodes would be tens of
megabytes, and the reader is 33 MB already.

Input: the ONSPD's multi-CSV zip or a single CSV of it, downloaded from
the Open Geography portal (OGL v3.0) into data/raw/onspd/, which is
gitignored like the rest of data/raw/. Only the derived file is
committed, and it names the edition it came from.

Rules, each a fact about the directory:
- `doterm` non-empty means the postcode is terminated; only live
  postcodes contribute, so a sector's centroid is where its current
  postcodes are.
- `lat` 99.999999 / `long` 0.000000 is the directory's "no position"
  marker (Channel Islands, Isle of Man, some special postcodes); those
  rows are skipped, and the sector is omitted if nothing else remains.
- The sector is the outward code plus the first character of the inward
  code: "SL1 4BG" -> "SL1 4". `pcds` is the standard-spaced form, so the
  split is on its single space.
- The centroid is the unweighted mean of the live postcodes' positions.
  A postcode's own position in the directory is the centroid of its
  delivery points, so this is a mean of centroids, and the row carries
  the count so a reader can see how much stands behind it.

Output: data/external_sources/postcode_sectors.json —
  {"edition": "May 2026", "source": ..., "attribution": ..., "derived":
   "YYYY-MM-DD", "sectors": {"SL1 4": [lat, lon, n], ...}}

Usage:
    scripts/derive_postcode_sectors.py --input data/raw/onspd/ONSPD_MAY_2026_UK.zip --edition "May 2026"
    scripts/derive_postcode_sectors.py --input data/raw/onspd/onspd.csv --edition "May 2026"
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "external_sources" / "postcode_sectors.json"

NO_POSITION_LAT = 99.999999
# The ONSPD's stated attribution, reproduced wherever its data is
# (DATA-LICENSING, postcodes.io section). The year is the edition's.
ATTRIBUTION = ("Contains OS data © Crown copyright and database right {year}; "
               "Contains Royal Mail data © Royal Mail copyright and database "
               "right {year}; Source: Office for National Statistics licensed "
               "under the Open Government Licence v.3.0")


def sector_of(pcds: str) -> str | None:
    """'SL1 4BG' -> 'SL1 4'. None for a malformed postcode."""
    parts = pcds.strip().split()
    if len(parts) != 2 or not parts[1]:
        return None
    return f"{parts[0].upper()} {parts[1][0].upper()}"


def accumulate(rows, acc: dict[str, list]) -> tuple[int, int, int]:
    """Fold ONSPD rows into acc[sector] = [sum_lat, sum_lon, n].

    Returns (rows_seen, terminated_skipped, unpositioned_skipped)."""
    seen = term = unpos = 0
    for r in rows:
        seen += 1
        if (r.get("doterm") or "").strip():
            term += 1
            continue
        try:
            lat, lon = float(r["lat"]), float(r["long"])
        except (KeyError, ValueError):
            unpos += 1
            continue
        if lat >= NO_POSITION_LAT - 1e-6:
            unpos += 1
            continue
        sec = sector_of(r.get("pcds") or r.get("pcd") or "")
        if sec is None:
            unpos += 1
            continue
        a = acc[sec]
        a[0] += lat
        a[1] += lon
        a[2] += 1
    return seen, term, unpos


def _csv_streams(path: Path):
    """Yield (name, text-file) for each CSV in a zip, or the file itself."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist()
                     if n.lower().endswith(".csv") and "/data/" in n.lower().replace("\\", "/")
                     or (n.lower().endswith(".csv") and n.lower().startswith("data/"))]
            if not names:      # a zip holding one big CSV, or a flat layout
                names = [n for n in z.namelist() if n.lower().endswith(".csv")
                         and "user guide" not in n.lower() and "documents" not in n.lower()]
            for n in sorted(names):
                with z.open(n) as fh:
                    yield n, io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
    else:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            yield path.name, fh


def derive(path: Path, edition: str, source_url: str) -> dict:
    acc: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0])
    seen = term = unpos = 0
    for name, fh in _csv_streams(path):
        reader = csv.DictReader(fh)
        # Column names in the ONSPD are lower case (pcds, doterm, lat, long)
        # in every edition since 2011; a header in another case is
        # normalised rather than refused.
        reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
        s, t, u = accumulate(reader, acc)
        seen += s; term += t; unpos += u
        print(f"  {name}: {s:,} rows", file=sys.stderr)
    year = edition.split()[-1]
    sectors = {k: [round(v[0] / v[2], 5), round(v[1] / v[2], 5), v[2]]
               for k, v in sorted(acc.items()) if v[2] > 0}
    return {
        "edition": edition,
        "source": source_url,
        "licence": "Open Government Licence v3.0",
        "attribution": ATTRIBUTION.format(year=year),
        "derived": dt.date.today().isoformat(),
        "rule": ("unweighted mean of the positions of live (doterm empty) "
                 "postcodes per sector (outward code + first inward "
                 "character); rows without a position skipped"),
        "counts": {"rows": seen, "terminated_skipped": term,
                   "unpositioned_or_malformed_skipped": unpos,
                   "sectors": len(sectors)},
        "sectors": sectors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True,
                    help="the ONSPD zip or a CSV extracted from it")
    ap.add_argument("--edition", required=True, help='e.g. "May 2026"')
    ap.add_argument("--source-url", default="https://geoportal.statistics.gov.uk/")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    if not args.input.is_file():
        ap.error(f"{args.input} is not a file")
    doc = derive(args.input, args.edition, args.source_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n")
    c = doc["counts"]
    print(f"{c['rows']:,} rows -> {c['sectors']:,} sectors "
          f"({c['terminated_skipped']:,} terminated and "
          f"{c['unpositioned_or_malformed_skipped']:,} unpositioned skipped); "
          f"wrote {args.out} ({args.out.stat().st_size/1e3:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
