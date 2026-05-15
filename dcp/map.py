"""Editorial map: worklist applications + UK power-station overlay.

Folium-based interactive HTML (Leaflet under the hood) for Aisha and the
data desk. Companion GeoJSON + KML exports for the graphics team / QGIS
users.

The map answers the editorial question Luke flagged: where do DC planning
applications sit unusually close to known fossil-fuel generation? The
Yorkshire Energy Park spike is the proof-of-concept — DC outline + 21 MW
gas-fired plant at the same site, filed years apart under different
references. Pre-computing distance-to-nearest-power-station puts that
signal one click away for every application on the worklist.

Outputs under `data/exports/`:
    worklist_map_<date>.html              — primary, self-contained
    worklist_points_<date>.geojson        — flat point layer for QGIS / kepler
    worklist_points_<date>.kml            — same data for Google Earth
    uk_power_plants_<date>.geojson        — copy of the OSM source layer

Inputs:
    `dcp.worklist.fetch` — the ranked worklist with full triage metadata
    `data/priors/osm/uk_power_plants.geojson` — OSM `power=plant` features,
        fetched once by `scripts/fetch_osm_power_plants.py`
"""

from __future__ import annotations

import datetime as dt
import json
import math
import xml.sax.saxutils
from dataclasses import dataclass
from pathlib import Path

from dcp import db, worklist


OSM_BUNDLED = Path("data/priors/osm/uk_power_plants.geojson")

# Plant-source buckets used for layer grouping and marker colouring. Order
# matters: the first matching bucket wins per feature. Buckets are journalism-
# editorially weighted — fossil first because that's the story.
PLANT_SOURCE_BUCKETS: list[tuple[str, set[str]]] = [
    ("fossil", {"gas", "coal", "oil", "diesel", "gas;oil", "oil;gas",
                "abandoned_mine_methane", "mine gas", "methane"}),
    ("biomass_waste", {"biomass", "biogas", "biofuel", "waste", "landfill_gas",
                       "wastewater", "sludge", "biomass;gas", "biomass;waste",
                       "waste;biomass", "biogas;biomass", "biogas;gas;sludge",
                       "waste_heat;gas"}),
    ("nuclear", {"nuclear"}),
    ("renewable", {"solar", "wind", "hydro", "tidal", "geothermal",
                   "wind;solar", "solar;steam", "geothermal;gas", "liquid_air",
                   "minewater"}),
    ("storage", {"battery"}),
]

PLANT_BUCKET_COLOR = {
    "fossil":        "#d62728",  # red
    "biomass_waste": "#ff7f0e",  # orange
    "nuclear":       "#9467bd",  # purple
    "renewable":     "#2ca02c",  # green
    "storage":       "#1f77b4",  # blue
    "other":         "#7f7f7f",  # grey
}

VERDICT_COLOR = {
    "DC":        "#d62728",  # red
    "adjacent":  "#ff7f0e",  # orange
    "unknown":   "#7f7f7f",  # grey
    "unrelated": "#bcbcbc",  # light grey (shouldn't appear in worklist)
}


def _bucket(plant_source: str | None) -> str:
    if not plant_source:
        return "other"
    src = plant_source.strip().lower()
    for bucket, members in PLANT_SOURCE_BUCKETS:
        if src in members:
            return bucket
    return "other"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Buckets that count as "editorially relevant" for the proximity question
# (i.e. fossil-fuel and adjacent combustion infrastructure). Renewables and
# battery storage are tracked for completeness but excluded from the
# editorial-nearest-plant calculation — a DC sitting next to a rooftop
# solar farm is not the buried-fossil-fuel story.
EDITORIAL_BUCKETS = {"fossil", "biomass_waste", "nuclear"}


@dataclass
class WorklistPoint:
    application_ref: str
    rank: int
    lat: float
    lon: float
    verdict: str
    worth_deep_read: str
    confidence: str
    tier1_hits: int
    storage_hits: int
    backup_hits: int
    signals: list[str]
    why: str | None
    description: str | None
    address: str | None
    council: str | None
    foxglove: bool
    portal_url: str | None
    # Nearest of ANY OSM power plant (could be a rooftop solar array).
    nearest_plant_km: float | None
    nearest_plant_name: str | None
    nearest_plant_bucket: str | None
    # Nearest fossil/biomass/nuclear — the editorial question we actually care
    # about. Same `None` when no in-bucket plant exists in our OSM dataset
    # (shouldn't happen for UK, but kept defensive).
    nearest_editorial_km: float | None
    nearest_editorial_name: str | None
    nearest_editorial_bucket: str | None


def _row_to_point(row: dict, rank: int) -> WorklistPoint | None:
    meta = row.get("raw_metadata") or {}
    lon = meta.get("location_x")
    lat = meta.get("location_y")
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return WorklistPoint(
        application_ref=row["application_ref"],
        rank=rank,
        lat=lat_f,
        lon=lon_f,
        verdict=row["verdict"],
        worth_deep_read=row["worth_deep_read"],
        confidence=row["confidence"],
        tier1_hits=row["tier1_hits"],
        storage_hits=row["storage_hits"],
        backup_hits=row["backup_hits"],
        signals=row.get("signals") or [],
        why=row.get("why"),
        description=row.get("description"),
        address=row.get("address"),
        council=row.get("council_name"),
        foxglove=bool(row.get("foxglove")),
        portal_url=row.get("url"),
        nearest_plant_km=None,
        nearest_plant_name=None,
        nearest_plant_bucket=None,
        nearest_editorial_km=None,
        nearest_editorial_name=None,
        nearest_editorial_bucket=None,
    )


def _compute_nearest(points: list[WorklistPoint], plants: list[dict]) -> None:
    """Set nearest_plant_* + nearest_editorial_* on each WorklistPoint in-place.
    Two distinct "nearest" metrics:

    - `nearest_plant_*`     — closest of any OSM `power=plant` (might be a
                              rooftop solar array; useful as raw context).
    - `nearest_editorial_*` — closest of `fossil`/`biomass_waste`/`nuclear`
                              only (the buried-fossil-fuel story). The popup
                              foregrounds this one.

    O(|points| × |plants|) — fine for ~700 × ~4000 ≈ 3M haversine calls.
    """
    # Pre-stamp the bucket onto each plant once so we don't recompute per-point.
    plants_with_bucket = [
        (plant, _bucket(plant["properties"].get("plant_source")))
        for plant in plants
    ]
    for p in points:
        best_any_km: float | None = None
        best_any: dict | None = None
        best_edit_km: float | None = None
        best_edit: dict | None = None
        for plant, bucket in plants_with_bucket:
            coords = plant["geometry"]["coordinates"]
            d = _haversine_km(p.lat, p.lon, coords[1], coords[0])
            if best_any_km is None or d < best_any_km:
                best_any_km = d
                best_any = plant
            if bucket in EDITORIAL_BUCKETS and (best_edit_km is None or d < best_edit_km):
                best_edit_km = d
                best_edit = plant
        if best_any is not None:
            p.nearest_plant_km = round(best_any_km, 2)
            p.nearest_plant_name = _plant_label(best_any)
            p.nearest_plant_bucket = _bucket(best_any["properties"].get("plant_source"))
        if best_edit is not None:
            p.nearest_editorial_km = round(best_edit_km, 2)
            p.nearest_editorial_name = _plant_label(best_edit)
            p.nearest_editorial_bucket = _bucket(best_edit["properties"].get("plant_source"))


def _plant_label(plant: dict) -> str:
    p = plant["properties"]
    return (
        p.get("name")
        or p.get("operator")
        or f"OSM {p.get('osm_type')}/{p.get('osm_id')}"
    )


# ---------------------------------------------------------------------------
# Folium HTML output
# ---------------------------------------------------------------------------


def _popup_html(p: WorklistPoint) -> str:
    """Compact HTML card for the marker popup. Folium will inject this as
    `iframe`-rendered content — keep the markup self-contained and simple."""
    sig_text = ", ".join(p.signals) if p.signals else "<em>(none)</em>"
    descr = (p.description or "").strip()
    descr_short = (descr[:300] + "…") if len(descr) > 300 else descr
    fx_badge = " <strong style='color:#9467bd'>★ Foxglove top-10</strong>" if p.foxglove else ""
    nearest_any = "—"
    if p.nearest_plant_name is not None:
        nearest_any = (
            f"{p.nearest_plant_name} "
            f"<small>({p.nearest_plant_bucket}, {p.nearest_plant_km:.1f} km)</small>"
        )
    nearest_edit = "—"
    if p.nearest_editorial_name is not None:
        nearest_edit = (
            f"<b style='color:#c0392b'>{p.nearest_editorial_name}</b> "
            f"<small>({p.nearest_editorial_bucket}, {p.nearest_editorial_km:.1f} km)</small>"
        )
    portal_link = (
        f"<a href='{p.portal_url}' target='_blank'>Source portal ↗</a>"
        if p.portal_url else ""
    )
    return f"""
    <div style='font-family:system-ui,sans-serif;font-size:12px;width:340px'>
      <div style='font-weight:bold;font-size:13px'>#{p.rank} {p.application_ref}{fx_badge}</div>
      <div style='color:#555;margin-bottom:4px'>{p.council or '—'} · {p.address or ''}</div>
      <table style='border-collapse:collapse;width:100%'>
        <tr><td><b>Verdict</b></td><td>{p.verdict} · deep-read {p.worth_deep_read} · conf {p.confidence}</td></tr>
        <tr><td><b>Tier-1 / Stor / Bkp</b></td><td>{p.tier1_hits} / {p.storage_hits} / {p.backup_hits}</td></tr>
        <tr><td><b>Signals</b></td><td>{sig_text}</td></tr>
        <tr><td><b>Nearest fossil/bio/nuclear</b></td><td>{nearest_edit}</td></tr>
        <tr><td><b>Nearest plant (any)</b></td><td>{nearest_any}</td></tr>
      </table>
      <div style='margin-top:4px;color:#333'>{descr_short}</div>
      <div style='margin-top:4px'>{portal_link}</div>
    </div>
    """


def _plant_popup_html(plant: dict) -> str:
    props = plant["properties"]
    name = props.get("name") or "(unnamed)"
    source = props.get("plant_source") or "?"
    output = props.get("plant_output_electricity") or "?"
    method = props.get("plant_method") or "?"
    operator = props.get("operator") or "?"
    return f"""
    <div style='font-family:system-ui,sans-serif;font-size:12px;width:260px'>
      <div style='font-weight:bold'>{name}</div>
      <table style='border-collapse:collapse;width:100%'>
        <tr><td><b>Operator</b></td><td>{operator}</td></tr>
        <tr><td><b>Source</b></td><td>{source}</td></tr>
        <tr><td><b>Method</b></td><td>{method}</td></tr>
        <tr><td><b>Capacity</b></td><td>{output}</td></tr>
      </table>
      <div style='color:#888;font-size:11px;margin-top:2px'>OSM {props.get('osm_type')}/{props.get('osm_id')}</div>
    </div>
    """


def render_html(
    *,
    points: list[WorklistPoint],
    plants: list[dict],
    out_path: Path,
    generated_at: dt.datetime,
) -> None:
    import folium
    from folium.plugins import MarkerCluster

    # UK-centred map; zoom roughly Britain + nearby continent
    fmap = folium.Map(location=[54.0, -2.5], zoom_start=6, tiles="OpenStreetMap",
                      control_scale=True)

    # Worklist layer groups (one per verdict so each can be toggled).
    by_verdict: dict[str, folium.FeatureGroup] = {}
    for verdict in ("DC", "adjacent", "unknown"):
        grp = folium.FeatureGroup(name=f"Worklist · {verdict}", show=True)
        grp.add_to(fmap)
        by_verdict[verdict] = grp
    foxglove_grp = folium.FeatureGroup(name="Worklist · Foxglove top-10", show=True)
    foxglove_grp.add_to(fmap)

    for p in points:
        colour = VERDICT_COLOR.get(p.verdict, "#000000")
        # Marker size scales with tier-1 hits so the strong-signal cases pop.
        radius = 5 + min(p.tier1_hits, 3) * 3
        marker = folium.CircleMarker(
            location=[p.lat, p.lon],
            radius=radius,
            color=colour,
            weight=1,
            fill=True,
            fill_color=colour,
            fill_opacity=0.7 if not p.foxglove else 0.9,
            tooltip=f"#{p.rank} {p.application_ref} · {p.verdict}",
            popup=folium.Popup(_popup_html(p), max_width=380),
        )
        # Foxglove cases get a layer of their own AND stay in their verdict layer
        if p.foxglove:
            marker.add_to(foxglove_grp)
        marker.add_to(by_verdict.get(p.verdict, by_verdict["unknown"]))

    # Power-plant layer groups, one per editorial bucket.
    plant_groups: dict[str, folium.FeatureGroup] = {
        b: folium.FeatureGroup(
            name=f"Power plants · {b}",
            # Default: fossil + biomass on; renewables/storage/other off (reduce clutter)
            show=(b in {"fossil", "biomass_waste", "nuclear"}),
        ) for b in ["fossil", "biomass_waste", "nuclear", "renewable", "storage", "other"]
    }
    for grp in plant_groups.values():
        grp.add_to(fmap)
    for plant in plants:
        coords = plant["geometry"]["coordinates"]
        bucket = _bucket(plant["properties"].get("plant_source"))
        folium.CircleMarker(
            location=[coords[1], coords[0]],
            radius=4,
            color=PLANT_BUCKET_COLOR[bucket],
            weight=1,
            fill=True,
            fill_color=PLANT_BUCKET_COLOR[bucket],
            fill_opacity=0.6,
            tooltip=(plant["properties"].get("name") or "")
                    + f" ({plant['properties'].get('plant_source') or '?'})",
            popup=folium.Popup(_plant_popup_html(plant), max_width=300),
        ).add_to(plant_groups[bucket])

    folium.LayerControl(collapsed=False).add_to(fmap)

    legend_html = f"""
    <div style='position:fixed;bottom:30px;left:10px;z-index:9999;
                background:white;padding:8px 12px;border:1px solid #ccc;
                font-family:system-ui,sans-serif;font-size:12px;
                box-shadow:0 1px 4px rgba(0,0,0,0.2)'>
      <div style='font-weight:bold;margin-bottom:4px'>UK DC planning worklist</div>
      <div>{len(points)} app points · {len(plants)} OSM power plants</div>
      <div style='margin-top:6px'>
        <span style='color:{VERDICT_COLOR["DC"]}'>●</span> DC ·
        <span style='color:{VERDICT_COLOR["adjacent"]}'>●</span> adjacent ·
        <span style='color:{VERDICT_COLOR["unknown"]}'>●</span> unknown
      </div>
      <div>
        <span style='color:{PLANT_BUCKET_COLOR["fossil"]}'>●</span> fossil ·
        <span style='color:{PLANT_BUCKET_COLOR["biomass_waste"]}'>●</span> biomass/waste ·
        <span style='color:{PLANT_BUCKET_COLOR["nuclear"]}'>●</span> nuclear ·
        <span style='color:{PLANT_BUCKET_COLOR["renewable"]}'>●</span> renewable ·
        <span style='color:{PLANT_BUCKET_COLOR["storage"]}'>●</span> storage
      </div>
      <div style='color:#666;margin-top:4px;font-size:11px'>
        Marker size = Tier-1 signal count. Generated {generated_at.isoformat(timespec="minutes")}.
      </div>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))
    fmap.save(str(out_path))


# ---------------------------------------------------------------------------
# GeoJSON output
# ---------------------------------------------------------------------------


def render_geojson(*, points: list[WorklistPoint], out_path: Path) -> None:
    """Worklist points as a flat GeoJSON FeatureCollection. Properties match
    the xlsx columns so the same filtering logic works in QGIS / kepler.gl."""
    features = []
    for p in points:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
            "properties": {
                "rank": p.rank,
                "application_ref": p.application_ref,
                "verdict": p.verdict,
                "worth_deep_read": p.worth_deep_read,
                "confidence": p.confidence,
                "tier1_hits": p.tier1_hits,
                "storage_hits": p.storage_hits,
                "backup_hits": p.backup_hits,
                "signals": p.signals,
                "why": p.why,
                "council": p.council,
                "address": p.address,
                "foxglove_top10": p.foxglove,
                "portal_url": p.portal_url,
                "nearest_plant_km": p.nearest_plant_km,
                "nearest_plant_name": p.nearest_plant_name,
                "nearest_plant_bucket": p.nearest_plant_bucket,
                "nearest_editorial_km": p.nearest_editorial_km,
                "nearest_editorial_name": p.nearest_editorial_name,
                "nearest_editorial_bucket": p.nearest_editorial_bucket,
            },
        })
    out_path.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False, indent=2,
    ))


# ---------------------------------------------------------------------------
# KML output
# ---------------------------------------------------------------------------


def render_kml(*, points: list[WorklistPoint], out_path: Path,
               generated_at: dt.datetime) -> None:
    """Worklist points as a KML 2.2 document. Aimed at the Guardian graphics
    team (Google Earth users). One Folder per verdict so they can toggle the
    DC / adjacent / unknown groups independently."""
    esc = xml.sax.saxutils.escape

    def _placemark(p: WorklistPoint) -> str:
        desc_lines = [
            f"<b>Verdict:</b> {p.verdict} (deep-read {p.worth_deep_read}, confidence {p.confidence})",
            f"<b>Tier-1 / Storage / Backup:</b> {p.tier1_hits} / {p.storage_hits} / {p.backup_hits}",
            f"<b>Signals:</b> {', '.join(p.signals) if p.signals else '(none)'}",
            f"<b>Council:</b> {p.council or '—'}",
            f"<b>Address:</b> {p.address or ''}",
        ]
        if p.nearest_editorial_name is not None:
            desc_lines.append(
                f"<b>Nearest fossil/bio/nuclear:</b> {p.nearest_editorial_name} "
                f"({p.nearest_editorial_bucket}, {p.nearest_editorial_km} km)"
            )
        if p.nearest_plant_name is not None:
            desc_lines.append(
                f"<b>Nearest plant (any):</b> {p.nearest_plant_name} "
                f"({p.nearest_plant_bucket}, {p.nearest_plant_km} km)"
            )
        if p.description:
            descr = p.description.strip()
            desc_lines.append("")
            desc_lines.append(descr)
        if p.portal_url:
            desc_lines.append("")
            desc_lines.append(f'<a href="{p.portal_url}">Source portal</a>')
        # KML uses CDATA for HTML descriptions
        body = "<br/>".join(desc_lines)
        fx = " ★ Foxglove" if p.foxglove else ""
        style_id = f"verdict-{p.verdict}-fx{int(p.foxglove)}"
        return (
            f"  <Placemark>\n"
            f"    <name>#{p.rank} {esc(p.application_ref)}{fx}</name>\n"
            f"    <styleUrl>#{style_id}</styleUrl>\n"
            f"    <description><![CDATA[{body}]]></description>\n"
            f"    <Point><coordinates>{p.lon},{p.lat},0</coordinates></Point>\n"
            f"  </Placemark>"
        )

    def _style(style_id: str, colour_hex: str, scale: float = 1.0) -> str:
        # KML colour is aabbggrr — alpha + reversed RGB
        r, g, b = colour_hex[1:3], colour_hex[3:5], colour_hex[5:7]
        kml_color = f"ff{b}{g}{r}".lower()
        return (
            f"<Style id='{style_id}'>\n"
            f"  <IconStyle>\n"
            f"    <color>{kml_color}</color>\n"
            f"    <scale>{scale}</scale>\n"
            f"    <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>\n"
            f"  </IconStyle>\n"
            f"</Style>"
        )

    styles = []
    for verdict, colour in VERDICT_COLOR.items():
        styles.append(_style(f"verdict-{verdict}-fx0", colour, 0.9))
        styles.append(_style(f"verdict-{verdict}-fx1", colour, 1.3))

    folders: dict[str, list[str]] = {"DC": [], "adjacent": [], "unknown": []}
    foxglove_folder: list[str] = []
    for p in points:
        pm = _placemark(p)
        folders.setdefault(p.verdict, []).append(pm)
        if p.foxglove:
            foxglove_folder.append(pm)

    folder_chunks = []
    for verdict in ("DC", "adjacent", "unknown"):
        if folders.get(verdict):
            inner = "\n".join(folders[verdict])
            folder_chunks.append(
                f"<Folder><name>Worklist · {verdict}</name>\n{inner}\n</Folder>"
            )
    if foxglove_folder:
        inner = "\n".join(foxglove_folder)
        folder_chunks.append(
            f"<Folder><name>Worklist · Foxglove top-10</name>\n{inner}\n</Folder>"
        )

    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        '<Document>\n'
        f'  <name>UK DC planning worklist — {generated_at.date().isoformat()}</name>\n'
        f'  <description>Generated {esc(generated_at.isoformat(timespec="seconds"))}. '
        f'{len(points)} worklist application points.</description>\n'
        + "\n".join(styles) + "\n"
        + "\n".join(folder_chunks) + "\n"
        '</Document>\n</kml>\n'
    )
    out_path.write_text(kml)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def build_map(
    *,
    model: str = "granite4.1:30b",
    output_dir: Path = Path("data/exports"),
    osm_path: Path | None = None,
    generated_at: dt.datetime | None = None,
) -> dict[str, Path | int]:
    """Generate the HTML map + GeoJSON + KML companion files. Returns paths
    + counts so the CLI can print a status block."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or dt.datetime.now()
    today = generated_at.date().isoformat()
    out_html = output_dir / f"worklist_map_{today}.html"
    out_geojson = output_dir / f"worklist_points_{today}.geojson"
    out_kml = output_dir / f"worklist_points_{today}.kml"
    out_plants = output_dir / f"uk_power_plants_{today}.geojson"

    osm_src = osm_path or OSM_BUNDLED
    if not osm_src.exists():
        raise FileNotFoundError(
            f"OSM power-plants source not found at {osm_src}. "
            f"Run scripts/fetch_osm_power_plants.py first."
        )
    plants = json.loads(osm_src.read_text())["features"]

    with db.connect() as conn:
        data = worklist.fetch(conn, model=model)
    points: list[WorklistPoint] = []
    for rank, row in enumerate(data.rows, 1):
        wp = _row_to_point(row, rank)
        if wp is not None:
            points.append(wp)

    _compute_nearest(points, plants)

    render_html(points=points, plants=plants, out_path=out_html,
                generated_at=generated_at)
    render_geojson(points=points, out_path=out_geojson)
    render_kml(points=points, out_path=out_kml, generated_at=generated_at)
    out_plants.write_text(osm_src.read_text())

    return {
        "html": out_html,
        "geojson": out_geojson,
        "kml": out_kml,
        "power_plants_geojson": out_plants,
        "points_mapped": len(points),
        "points_dropped_no_coords": len(data.rows) - len(points),
        "plants": len(plants),
    }
