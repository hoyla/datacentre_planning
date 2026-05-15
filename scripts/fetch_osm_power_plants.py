"""One-time fetch of UK power-station features from OpenStreetMap via the
Overpass API. Stored at `data/priors/osm/uk_power_plants.geojson` (tracked,
since OSM data is freely redistributable under ODbL — and reproducibility
matters for a journalism project).

The result feeds the editorial map (`dcp map`) so Aisha can spot DC
applications sited close to known power stations — the Yorkshire Energy Park
pattern in reusable form.

Re-run only when you want to refresh — OSM data updates daily, but power
stations don't move; monthly or even quarterly is plenty. Use --force to
overwrite an existing file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT = ROOT / "data" / "priors" / "osm" / "uk_power_plants.geojson"

# UK-ish bounding box (Shetlands to Channel Islands, west of Ireland to east coast).
# Slightly over-wide rather than risk clipping coastal stations.
UK_BBOX = (49.5, -8.5, 61.0, 2.0)  # south, west, north, east

# `out center` returns a single (lat, lon) for each feature regardless of
# whether it's a node, way (closed polygon), or relation (multi-polygon).
OVERPASS_QUERY = """
[out:json][timeout:120];
(
  node["power"="plant"]({s},{w},{n},{e});
  way["power"="plant"]({s},{w},{n},{e});
  relation["power"="plant"]({s},{w},{n},{e});
);
out center tags;
""".strip()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "datacentre_planning research (luke.hoyland@gmail.com)"


def fetch(verbose: bool = True) -> dict:
    s, w, n, e = UK_BBOX
    query = OVERPASS_QUERY.format(s=s, w=w, n=n, e=e)
    if verbose:
        print(f"POSTing Overpass query for power=plant in UK bbox ({s},{w},{n},{e})…")
    r = httpx.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=180.0,
    )
    r.raise_for_status()
    return r.json()


def to_geojson(overpass: dict) -> dict:
    """Convert Overpass JSON to a flat GeoJSON FeatureCollection. Each feature
    is a Point at the OSM element's centroid (`center` from Overpass), with
    the OSM tags carried verbatim as properties so the map renderer can pick
    out `name`, `plant:source`, `plant:output:electricity`, `operator`."""
    features: list[dict] = []
    for el in overpass.get("elements", []):
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags") or {}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "osm_type": el.get("type"),
                "osm_id": el.get("id"),
                "name": tags.get("name"),
                "operator": tags.get("operator"),
                "plant_source": tags.get("plant:source"),
                "plant_output_electricity": tags.get("plant:output:electricity"),
                "plant_method": tags.get("plant:method"),
                "start_date": tags.get("start_date"),
                "end_date": tags.get("end_date"),
                "tags": tags,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--force", action="store_true",
                    help="Overwrite the existing file if present.")
    args = ap.parse_args()

    if args.output.exists() and not args.force:
        print(f"{args.output} exists; pass --force to refresh.")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    overpass = fetch()
    gj = to_geojson(overpass)
    args.output.write_text(json.dumps(gj, ensure_ascii=False, indent=2))
    print(f"Wrote {len(gj['features'])} features to {args.output}")
    # Quick distribution by plant_source so we can sanity-check coverage
    counts: dict[str, int] = {}
    for f in gj["features"]:
        src = f["properties"]["plant_source"] or "(unknown)"
        counts[src] = counts.get(src, 0) + 1
    print("By plant_source:")
    for src, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
