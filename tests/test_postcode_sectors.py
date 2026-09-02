"""Sector centroids from the ONSPD: the rules are facts about the directory.

No download: a handful of synthetic rows in the directory's own column
names exercise every rule — terminated postcodes excluded, the no-position
marker skipped, the sector split on the standard-spaced postcode, an
unweighted mean, and the count carried.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "derive_postcode_sectors", ROOT / "scripts" / "derive_postcode_sectors.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROWS = [
    # pcds, doterm, lat, long
    ("SL1 4BG", "", "51.5174", "-0.6179"),
    ("SL1 4BH", "", "51.5176", "-0.6181"),
    ("SL1 4BJ", "201803", "51.9000", "-0.9000"),      # terminated: excluded
    ("SL1 4QZ", "", "51.5223", "-0.6228"),
    ("GY1 1AA", "", "99.999999", "0.000000"),         # no position: skipped
    ("SG1 2FP", "", "51.8887", "-0.2047"),
    ("BADPOSTCODE", "", "51.0", "-1.0"),              # malformed: skipped
]


def _csv(rows=ROWS) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["pcd", "pcds", "doterm", "lat", "long"])
    for pcds, doterm, lat, lon in rows:
        w.writerow([pcds.replace(" ", ""), pcds, doterm, lat, lon])
    return buf.getvalue()


def test_sector_is_outward_plus_first_inward_character():
    m = _mod()
    assert m.sector_of("SL1 4BG") == "SL1 4"
    assert m.sector_of("EC1V 9BJ") == "EC1V 9"
    assert m.sector_of("sl1 4bg") == "SL1 4"
    assert m.sector_of("BADPOSTCODE") is None


def test_live_positioned_postcodes_average_and_the_rest_are_skipped(tmp_path):
    m = _mod()
    p = tmp_path / "onspd.csv"
    p.write_text(_csv())
    doc = m.derive(p, "May 2026", "https://example.test/onspd")
    s = doc["sectors"]
    assert set(s) == {"SL1 4", "SG1 2"}
    lat, lon, n = s["SL1 4"]
    assert n == 3                                   # BG, BH, QZ — not the terminated BJ
    assert abs(lat - (51.5174 + 51.5176 + 51.5223) / 3) < 1e-4
    assert abs(lon - (-0.6179 - 0.6181 - 0.6228) / 3) < 1e-4
    assert s["SG1 2"] == [51.8887, -0.2047, 1]
    c = doc["counts"]
    assert c["rows"] == 7 and c["terminated_skipped"] == 1
    assert c["unpositioned_or_malformed_skipped"] == 2 and c["sectors"] == 2


def test_the_file_names_its_edition_and_carries_the_attribution(tmp_path):
    m = _mod()
    p = tmp_path / "onspd.csv"
    p.write_text(_csv())
    doc = m.derive(p, "May 2026", "https://example.test/onspd")
    assert doc["edition"] == "May 2026" and "2026" in doc["attribution"]
    for holder in ("OS data", "Royal Mail", "Office for National Statistics", "Open Government Licence"):
        assert holder in doc["attribution"], holder
    assert doc["licence"].startswith("Open Government Licence")
    json.dumps(doc)   # serialisable as written


def test_a_zip_of_per_area_csvs_is_read_whole(tmp_path):
    import zipfile
    m = _mod()
    z = tmp_path / "ONSPD_TEST.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Data/multi_csv/ONSPD_TEST_UK_SL.csv", _csv(ROWS[:4]))
        zf.writestr("Data/multi_csv/ONSPD_TEST_UK_SG.csv", _csv(ROWS[5:6]))
        zf.writestr("User Guide/ONSPD User Guide.pdf", b"%PDF-1.4 not a csv")
    doc = m.derive(z, "May 2026", "https://example.test/onspd")
    assert set(doc["sectors"]) == {"SL1 4", "SG1 2"} and doc["counts"]["rows"] == 5
