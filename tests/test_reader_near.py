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
