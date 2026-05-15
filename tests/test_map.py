"""Light tests for the editorial map. The map is mostly an aggregator of
DB state + Folium rendering, but two pieces are easy to silently break:
the plant-source bucket classification (drives marker colours and the
editorial-nearest calculation) and the KML output (because we hand-roll
the XML and CDATA escaping)."""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

import pytest

from dcp import map as map_mod


# ---------------------------------------------------------------------------
# Bucket classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plant_source, expected_bucket", [
    ("gas", "fossil"),
    ("coal", "fossil"),
    ("oil", "fossil"),
    ("diesel", "fossil"),
    ("gas;oil", "fossil"),
    ("oil;gas", "fossil"),
    ("biomass", "biomass_waste"),
    ("biogas", "biomass_waste"),
    ("waste", "biomass_waste"),
    ("landfill_gas", "biomass_waste"),
    ("biomass;gas", "biomass_waste"),
    ("nuclear", "nuclear"),
    ("solar", "renewable"),
    ("wind", "renewable"),
    ("hydro", "renewable"),
    ("tidal", "renewable"),
    ("geothermal", "renewable"),
    ("battery", "storage"),
    ("", "other"),
    (None, "other"),
    ("WIND", "renewable"),    # case-insensitive
    ("GAS", "fossil"),
])
def test_bucket_classification(plant_source, expected_bucket):
    assert map_mod._bucket(plant_source) == expected_bucket


def test_editorial_buckets_match_expected_set():
    """Regression guard: removing fossil/biomass/nuclear from
    EDITORIAL_BUCKETS would silently broaden the 'nearest fossil-fuel plant'
    calculation to include renewables — which is the bug we just fixed."""
    assert map_mod.EDITORIAL_BUCKETS == {"fossil", "biomass_waste", "nuclear"}


# ---------------------------------------------------------------------------
# Nearest-plant computation
# ---------------------------------------------------------------------------


def _wp(application_ref, lat, lon, verdict="DC", foxglove=False):
    return map_mod.WorklistPoint(
        application_ref=application_ref, rank=1, lat=lat, lon=lon,
        verdict=verdict, worth_deep_read="yes", confidence="sure",
        tier1_hits=1, storage_hits=0, backup_hits=0,
        signals=["gas-fired"], why="x",
        description="Outline DC", address="x", council="x", foxglove=foxglove,
        portal_url="https://example.invalid/x",
        nearest_plant_km=None, nearest_plant_name=None, nearest_plant_bucket=None,
        nearest_editorial_km=None, nearest_editorial_name=None,
        nearest_editorial_bucket=None,
    )


def _plant(name, lat, lon, source):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"name": name, "plant_source": source,
                       "osm_type": "node", "osm_id": 1},
    }


def test_compute_nearest_distinguishes_any_vs_editorial():
    """A DC sitting nearer to a solar farm than to a gas plant should get
    `nearest_plant_*` = the solar farm and `nearest_editorial_*` = the gas
    plant. Conflating the two is the bug the popup labels were added to fix."""
    dc = _wp("X/1", lat=51.5074, lon=-0.1278)  # Central London
    plants = [
        _plant("Tiny Solar Array", 51.5074, -0.1280, "solar"),  # ~140m away
        _plant("Bunhill Gas Engine", 51.5260, -0.0900, "gas"),  # ~3.5km away
    ]
    map_mod._compute_nearest([dc], plants)
    assert dc.nearest_plant_name == "Tiny Solar Array"
    assert dc.nearest_plant_bucket == "renewable"
    assert dc.nearest_editorial_name == "Bunhill Gas Engine"
    assert dc.nearest_editorial_bucket == "fossil"
    # Editorial distance > any-plant distance, by construction
    assert dc.nearest_editorial_km > dc.nearest_plant_km


def test_compute_nearest_handles_no_editorial_plant():
    """If a DC's OSM neighbours are all renewable/storage, `nearest_editorial_*`
    must stay None rather than silently picking the closest renewable."""
    dc = _wp("X/1", lat=51.5074, lon=-0.1278)
    plants = [
        _plant("Solar Farm A", 51.5070, -0.1280, "solar"),
        _plant("Battery Site", 51.5090, -0.1290, "battery"),
    ]
    map_mod._compute_nearest([dc], plants)
    assert dc.nearest_plant_name == "Solar Farm A"
    assert dc.nearest_editorial_km is None
    assert dc.nearest_editorial_name is None


def test_compute_nearest_falls_back_to_operator_then_osm_id():
    """When a plant has no `name` tag, the popup label falls through to
    `operator`, then to a `OSM type/id` placeholder."""
    dc = _wp("X/1", lat=51.5, lon=-0.1)
    plant = _plant(name=None, lat=51.5, lon=-0.1, source="gas")
    plant["properties"]["name"] = None
    plant["properties"]["operator"] = "Acme Energy Ltd"
    map_mod._compute_nearest([dc], [plant])
    assert dc.nearest_editorial_name == "Acme Energy Ltd"

    # Now strip operator too
    plant["properties"]["operator"] = None
    dc2 = _wp("X/2", lat=51.5, lon=-0.1)
    map_mod._compute_nearest([dc2], [plant])
    assert dc2.nearest_editorial_name == "OSM node/1"


# ---------------------------------------------------------------------------
# KML output
# ---------------------------------------------------------------------------


def test_render_kml_produces_well_formed_xml(tmp_path):
    dc = _wp("Slough/T/137", lat=51.51, lon=-0.59, foxglove=False)
    dc.nearest_editorial_km = 0.24
    dc.nearest_editorial_name = "Slough Heat and Power"
    dc.nearest_editorial_bucket = "biomass_waste"
    out = tmp_path / "test.kml"
    map_mod.render_kml(points=[dc], out_path=out,
                       generated_at=dt.datetime(2026, 5, 15, 12, 0, 0))
    # Must parse as XML
    root = ET.fromstring(out.read_text())
    # KML root tag includes the namespace
    assert root.tag.endswith("kml")
    # Exactly one Placemark for our one point
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    placemarks = root.findall(".//kml:Placemark", ns)
    assert len(placemarks) == 1
    name_el = placemarks[0].find("kml:name", ns)
    assert name_el is not None
    assert "Slough/T/137" in name_el.text


def test_render_kml_escapes_xml_special_chars_in_ref(tmp_path):
    """An application_ref containing `&` or `<` must not break the XML
    output — `xml.sax.saxutils.escape` is what handles this."""
    dc = _wp("Council/A&B<C>/24/0001", lat=51.5, lon=-0.1)
    out = tmp_path / "test.kml"
    map_mod.render_kml(points=[dc], out_path=out,
                       generated_at=dt.datetime(2026, 5, 15))
    # If escaping is broken, ElementTree will refuse to parse.
    ET.fromstring(out.read_text())
