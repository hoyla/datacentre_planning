"""The "near a postcode" control, as the export writes it (ROADMAP, 2026-09-02).

Source-level: a control in the shared bar, sector centroids embedded, the
rows carrying their coordinate, the hash carrying the state, the count
line naming what cannot be placed, and the directory's attribution where
a centroid renders. The behaviour is driven in test_reader_smoke.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "scripts" / "export_reader.py").read_text()


def test_the_control_sits_in_the_shared_bar_beside_the_search_box():
    bar = SRC[SRC.index('<div id="filterbar" hidden>'):SRC.index('<span class="count" id="n">')]
    assert 'id="q"' in bar and 'id="near"' in bar and 'id="nearkm"' in bar
    assert bar.index('id="q"') < bar.index('id="near"') < bar.index('id="nearkm"')
    assert 'value="10" selected' in bar
    # bound like every other control, and it writes the hash
    assert "document.getElementById('near'),document.getElementById('nearkm')]" in SRC


def test_sectors_are_embedded_from_the_committed_directory_file_and_credited():
    assert 'postcode_sectors.json' in SRC and "const SECTORS={sectors_payload}" in SRC
    doc = json.loads((ROOT / "data" / "external_sources" / "postcode_sectors.json").read_text())
    assert doc["edition"] and "Office for National Statistics" in doc["attribution"]
    assert "{esc(onspd_attribution)}" in SRC and SRC.count("{esc(onspd_edition)}") >= 2
    assert "ONS Postcode Directory" in SRC


def test_rows_carry_their_coordinate_and_a_distance_slot():
    assert SRC.count('data-lat="{lat if lat else \'\'}" data-lon="{lon if lon else \'\'}"') == 1
    assert SRC.count('data-lat="{plat if plat else \'\'}" data-lon="{plon if plon else \'\'}"') == 1
    assert SRC.count('<span class="skey"><span class="dist" hidden></span>') == 2


def test_resolution_is_sector_then_outward_and_distance_is_haversine():
    assert "function sectorKey(" in SRC and "function resolveNear(" in SRC
    assert "function kmBetween(" in SRC and "Math.asin(Math.sqrt(h))" in SRC
    assert "if(SECTORS[k]) return" in SRC and "s.startsWith(k+' ')" in SRC


def test_the_state_travels_in_the_hash_and_the_count_names_the_unplaced():
    assert "parts.push('near:'" in SRC and "parts.push('km:'" in SRC
    assert "h.startsWith('near:')" in SRC and "part.startsWith('km:')" in SRC
    assert "' cannot be placed'" in SRC and "' · no such postcode sector'" in SRC
    assert "document.getElementById('near').value='';" in SRC     # a jump to one site clears it


def test_the_map_frames_the_radius_and_the_rows_reorder_by_distance():
    assert "const d=NEAR.km/111" in SRC and "fitTo([{lat:NEAR.lat-d" in SRC
    assert "function orderRows(byKm)" in SRC and "orderRows(true)" in SRC and "orderRows(false)" in SRC


def _js_parser() -> str:
    """The parser as the page ships it, sectorKey through resolveNear."""
    start = SRC.index("function sectorKey(")
    end = SRC.index("function kmBetween(")
    return SRC[start:end]


def test_the_parser_reads_a_typed_sector_and_a_postcode_still_being_typed(tmp_path):
    """Luke, 2026-09-03: "SL1 4" found nothing — the first parser read it as
    a district SL14. The space a person types is the parse; a lone trailing
    letter is a postcode mid-keystroke, not nonsense; and an unspaced
    "SL14" falls back to sector 4 of SL1 when no district SL14 exists."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node is not installed; the parser is exercised in test_reader_smoke")
    sectors = {"SL1 4": [51.52, -0.61], "SL1 3": [51.51, -0.60], "SW1A 1": [51.50, -0.14]}
    cases = ["SL1 4BG", "sl1 4bg", "SL14BG", "SL1 4", "SL1  4", "SL1 4B", "SL14", "SL1",
             "SW1A 1AA", "SW1A", "ZZ99 9ZZ", "SL", "", "SL1-4BG"]
    script = (f"const SECTORS={json.dumps(sectors)};\n{_js_parser()}\n"
              f"const out={{}};for(const c of {json.dumps(cases)})"
              "{const r=resolveNear(c);out[c]=[sectorKey(c), r&&r.label, r&&+r.lat.toFixed(3)];}"
              "process.stdout.write(JSON.stringify(out));")
    js = tmp_path / "parser.js"
    js.write_text(script)
    got = json.loads(subprocess.run([node, str(js)], check=True, capture_output=True, text=True).stdout)
    mean_lat = round((51.52 + 51.51) / 2, 3)
    assert got["SL1 4BG"] == ["SL1 4", "SL1 4", 51.52]
    assert got["sl1 4bg"] == ["SL1 4", "SL1 4", 51.52]
    assert got["SL14BG"] == ["SL1 4", "SL1 4", 51.52]
    assert got["SL1 4"] == ["SL1 4", "SL1 4", 51.52], "a typed sector is the sector"
    assert got["SL1  4"] == ["SL1 4", "SL1 4", 51.52]
    assert got["SL1 4B"] == ["SL1 4", "SL1 4", 51.52], "one trailing letter is mid-typing"
    assert got["SL14"] == ["SL14", "SL1 4", 51.52], "no district SL14, so sector 4 of SL1"
    assert got["SL1"] == ["SL1", "SL1", mean_lat], "an outward code is the mean of its sectors"
    assert got["SW1A 1AA"] == ["SW1A 1", "SW1A 1", 51.5]
    assert got["SW1A"] == ["SW1A", "SW1A", 51.5]
    assert got["ZZ99 9ZZ"] == ["ZZ99 9", None, None]
    assert got["SL"] == [None, None, None]
    assert got[""] == [None, None, None]
    assert got["SL1-4BG"] == ["SL1 4", "SL1 4", 51.52]


def test_a_postcode_frames_the_map_when_the_map_is_the_view_on_screen():
    """The survivors were a dot among 197 energy rings at the country's
    zoom, so a postcode typed on the map looked as if it found nothing."""
    assert "function frameForNear(" in SRC and "function frameNear(" in SRC
    apply_body = SRC[SRC.index("function apply(){"):SRC.index("function filterHash(")]
    assert "frameForNear()" in apply_body, "apply() does not frame the map for a postcode"
    show_body = SRC[SRC.index("function show(v, quiet){"):SRC.index("const TABS=VIEWS;")]
    assert "frameForNear()" in show_body, "arriving on the map with a postcode set does not frame it"
    assert "nearFramed=nearState()" in SRC, "See on map does not record what it framed"
