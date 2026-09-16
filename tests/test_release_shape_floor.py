"""`release_diff.reader_shape` over the committed page, with floors.

The release discipline rests on diffing a build against the last
release, and that instrument is five regexes over 35 MB of HTML, each
with a recorded history of matching the wrong thing. Until 2026-09-16
none was asserted against a real page: the one end-to-end test fed
`<html></html>` to both sides, where every field is zero and every
comparison trivially equal, so a regex that silently stopped matching
would have reported "nothing fell" on a build that lost a section.
Floors, not exact counts: the corpus grows, and a count that falls
below these is a regex that broke or a page that lost something.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from statistics import median

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release_diff", ROOT / "scripts" / "release_diff.py")
rd = importlib.util.module_from_spec(_spec)
sys.modules["release_diff"] = rd
_spec.loader.exec_module(rd)

PAGE = ROOT / "index.html"


@pytest.fixture(scope="module")
def shape():
    assert PAGE.exists() and PAGE.stat().st_size > 1_000_000, (
        "index.html is the released page and is committed; a missing or "
        "tiny one is a broken checkout, not a reason to skip")
    return rd.reader_shape(PAGE)


def test_every_regex_found_something(shape):
    assert len(shape.tabs) >= 8, shape.tabs
    assert len(shape.views) >= 8, shape.views
    assert shape.sections >= 20, shape.sections
    assert shape.boxes >= 1_000, shape.boxes
    assert len(shape.controls) >= 10, shape.controls
    assert shape.dictionary_entries >= 40, shape.dictionary_entries
    assert len(shape.site_keys) >= 400, len(shape.site_keys)


def test_the_stamp_counts_are_the_page_counts(shape):
    """The masthead's numbers, read back against the rows they count.
    `release_diff` deliberately never judges the stamp (a corpus grows);
    this is the one place the two are held together."""
    stamp = dict(shape.stamp)
    assert stamp["sites"] == len(shape.site_keys)
    assert stamp["applications"] >= 1_000
    apps_rows = shape.rows_per_view["apps"]
    assert stamp["applications"] <= apps_rows <= stamp["applications"] + 5, (
        "the applications view's rows are the header plus one per application")


def test_every_site_panel_carries_links(shape):
    """The 2.8 regression was 401 dead links; a panel with none is a
    panel whose evidence went missing."""
    assert set(shape.links_per_site) == shape.site_keys
    assert min(shape.links_per_site.values()) >= 1
    assert median(shape.links_per_site.values()) >= 10
