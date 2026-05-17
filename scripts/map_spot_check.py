"""Reverse-geocode the top-N ranked worklist pins via Nominatim and render
a markdown table for human map-vs-pin spot-check.

Two failure modes this catches:
  - The pin geocoded to a council office / civic centre instead of the
    actual application site (the "geocoded to council office" error).
  - The pin landed in a postcode centroid far from where the stated
    address narrative implies (visible as a mismatch between the
    application address and Nominatim's reverse name).

Nominatim usage policy is 1 req/second. We sleep 2 seconds between calls
to be polite, and identify ourselves via the User-Agent header.

Usage:
    scripts/map_spot_check.py                                        # top 50, today's geojson
    scripts/map_spot_check.py --top 100
    scripts/map_spot_check.py --geojson data/exports/worklist_points_2026-05-17.geojson
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import httpx


NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = (
    "datacentre_planning/0.1 (Luke Hoyland, journalism research; "
    "luke.hoyland@gmail.com)"
)


def reverse_geocode(lat: float, lon: float, *, client: httpx.Client) -> dict:
    r = client.get(
        NOMINATIM_URL,
        params={
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "zoom": 18,  # building / road-segment level
            "addressdetails": 1,
        },
        timeout=20.0,
    )
    r.raise_for_status()
    return r.json()


def _find_missing_pins(xlsx_path: Path, mapped_refs: set[str], n: int) -> list[tuple]:
    """Return worklist top-N rows whose application_ref isn't in the geojson,
    so the spot-check can call them out as "no pin on the map at all"
    rather than letting them silently fall off."""
    try:
        import openpyxl
    except ImportError:
        return []
    if not xlsx_path.exists():
        return []
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["Worklist"]
    rows = list(ws.values)
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}
    missing = []
    for r in rows[1 : n + 1]:
        ref = r[idx["Application ref"]]
        if ref not in mapped_refs:
            missing.append(
                (
                    r[idx["Rank"]],
                    ref,
                    r[idx["Council"]] or "",
                    r[idx["Address"]] or "",
                )
            )
    missing.sort()
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50)
    today = dt.date.today().isoformat()
    default_geojson = Path(f"data/exports/worklist_points_{today}.geojson")
    ap.add_argument("--geojson", type=Path, default=default_geojson)
    ap.add_argument(
        "--xlsx",
        type=Path,
        default=None,
        help=(
            "Worklist xlsx for the missing-pins cross-check. Defaults to "
            "the most recent data/exports/worklist_*.xlsx."
        ),
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=Path(f"data/exports/map_spotcheck_{today}.md"),
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Seconds between Nominatim requests (default 2, policy minimum 1).",
    )
    args = ap.parse_args()

    if not args.geojson.exists():
        print(f"geojson not found: {args.geojson}", file=sys.stderr)
        print("Run `dcp map` first to generate today's points file.", file=sys.stderr)
        return 2

    if args.xlsx is None:
        candidates = sorted(Path("data/exports").glob("worklist_*.xlsx"))
        args.xlsx = candidates[-1] if candidates else Path("data/exports/_missing.xlsx")

    with args.geojson.open() as f:
        gj = json.load(f)

    features = sorted(gj["features"], key=lambda f: f["properties"]["rank"])
    top = features[: args.top]

    print(
        f"Reverse-geocoding {len(top)} pins via Nominatim "
        f"(~{len(top) * args.sleep:.0f}s at {args.sleep}s/req)...",
        file=sys.stderr,
    )

    rows = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for i, feat in enumerate(top, 1):
            p = feat["properties"]
            lon, lat = feat["geometry"]["coordinates"]
            try:
                result = reverse_geocode(lat, lon, client=client)
                display = result.get("display_name", "")
                addr = result.get("address", {}) or {}
                # Compact reverse-geocode summary: most-specific feature + locality
                bits = []
                for key in ("building", "amenity", "office", "industrial",
                            "commercial", "house_number", "road", "neighbourhood",
                            "suburb", "village", "town", "city", "postcode"):
                    v = addr.get(key)
                    if v and v not in bits:
                        bits.append(v)
                    if len(bits) >= 4:
                        break
                summary = ", ".join(bits) if bits else display[:80]
            except Exception as e:
                summary = f"ERROR: {e}"
                display = ""

            rows.append({
                "rank": p["rank"],
                "ref": p["application_ref"],
                "council": p["council"],
                "address": p["address"],
                "lat": lat,
                "lon": lon,
                "nominatim": summary,
                "nominatim_full": display,
            })
            print(
                f"  {i:>3}/{len(top)}  rank {p['rank']:>3}  {p['application_ref']:<35}  "
                f"→ {summary[:60]}",
                file=sys.stderr,
            )
            time.sleep(args.sleep)

    # Cross-check against the worklist xlsx: which top-N ranks have no pin?
    mapped_refs = {feat["properties"]["application_ref"] for feat in gj["features"]}
    # Use a wider window (top + ~20%) so we catch missing pins from outside
    # the strict top-N that we'd otherwise miss when ranks have gaps.
    window = max(args.top + (args.top // 5), args.top + 10)
    missing = _find_missing_pins(args.xlsx, mapped_refs, n=window)

    # Render markdown
    out = []
    out.append(f"# Map pin spot-check — top {len(rows)} ranked")
    out.append("")
    out.append(
        f"Generated {dt.datetime.now().isoformat(timespec='seconds')} from "
        f"`{args.geojson.name}`. Reverse-geocoded via Nominatim "
        f"(`zoom=18`)."
    )
    out.append("")
    out.append(
        "Each row shows: rank · application ref · the council's own address "
        "string for the site · the lat/lon used to drop the map pin · what "
        "Nominatim says is there. The eyeball check is: does the Nominatim "
        "summary plausibly match the stated address? Classic failure modes:"
    )
    out.append("")
    out.append(
        "- **Council-office geocode** — Nominatim says \"Civic Centre\" / "
        "\"Council Offices\" / \"Town Hall\" / \"Municipal\" / the LPA name. "
        "The pin is on the council's HQ, not the actual site."
    )
    out.append(
        "- **Postcode-centroid drift** — Nominatim's locality (suburb / town) "
        "is a long way from the locality named in the address text."
    )
    out.append(
        "- **Wrong council area entirely** — Nominatim's town/city is in a "
        "different council from the LPA in the worklist row."
    )
    out.append("")
    out.append("Click through to the HTML map for any row that looks off.")
    out.append("")

    if missing:
        out.append(f"## Worklist ranks in the top {window} with no map pin at all")
        out.append("")
        out.append(
            "These applications are on the worklist but didn't geocode (no "
            "`location_x` / `location_y` from the source portal), so they "
            "don't appear on the HTML map at all. "
            f"{len(missing)} of the worklist's top {window} ranks fall in "
            "this bucket."
        )
        out.append("")
        out.append("| Rank | Ref | Council (LPA) | Address (worklist) |")
        out.append("|---:|---|---|---|")
        for rank, ref, council, addr in missing:
            addr_short = (addr or "").replace("|", "/")[:90]
            council_short = (council or "").replace("|", "/")
            out.append(f"| {rank} | `{ref}` | {council_short} | {addr_short} |")
        out.append("")

    out.append(f"## Top-{len(rows)} pin-vs-address table")
    out.append("")
    out.append("| Rank | Ref | Council (LPA) | Address (worklist) | Pin (lat, lon) | Nominatim says |")
    out.append("|---:|---|---|---|---|---|")
    for r in rows:
        addr_short = (r["address"] or "").replace("|", "/")[:90]
        nom_short = (r["nominatim"] or "").replace("|", "/")[:90]
        council_short = (r["council"] or "").replace("|", "/")
        out.append(
            f"| {r['rank']} | `{r['ref']}` | {council_short} | {addr_short} | "
            f"{r['lat']:.5f}, {r['lon']:.5f} | {nom_short} |"
        )
    out.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(out))
    print(f"\nWrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
