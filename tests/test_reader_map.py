"""The map's own event handling, which has no other test and is easy to
break invisibly.

The reader ships a hand-rolled slippy map rather than a mapping library,
so its pointer handling is ours to get right. The card that opens when a
pin is clicked is a CHILD of the map element, which means every press on
it also arrives at the map's drag handler. That handler treated it as
the start of a drag: the first pointermove — a pixel, which every real
mouse produces — called hideCard(), so the anchor was gone before the
mouseup that would have followed it. Both the internal "Open this site"
link and the external Drive and register links silently did nothing, in
a released build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path("scripts/export_reader.py").read_text()

# Handlers on the map container that begin a gesture. A press inside the
# card must not start any of them.
GESTURE_HANDLERS = ("pointerdown", "dblclick")


def _handler_body(event: str) -> str:
    """The body of `map.el.addEventListener('<event>', e => { ... })`."""
    start = SRC.index(f"map.el.addEventListener('{event}'")
    return SRC[start:start + 700]


@pytest.mark.parametrize("event", GESTURE_HANDLERS)
def test_a_press_on_an_overlay_starts_no_map_gesture(event):
    body = _handler_body(event)
    assert ".mapoverlay" in body, (
        f"the map's {event} handler does not exempt overlays, so pressing "
        f"a control in one starts a map gesture and the control never fires")


def test_every_overlay_carries_the_class_the_guard_looks_for():
    """The guard is one class, not a list of ids, so that adding an
    overlay cannot silently reintroduce the bug — but only if the new
    overlay is labelled. These are the elements sitting inside the map."""
    inner = SRC[SRC.index('<div id="mapview">'):]
    inner = inner[:inner.index("</div>\n</div>")]
    for el in ("mapinfo", "mapzoom"):
        block = inner[inner.index(f'id="{el}"'):][:120]
        assert "mapoverlay" in block, f"#{el} is inside the map but not a .mapoverlay"


@pytest.mark.parametrize("event", GESTURE_HANDLERS)
def test_the_guard_matches_children_not_just_the_element(event):
    """`classList.contains` only sees the element pressed.

    A press lands on the card's <a>, or on a pin's inner text — not on
    the card or the pin itself — so the guard has to walk up.
    """
    body = _handler_body(event)
    assert "closest(" in body, f"{event} guard does not use closest()"
    assert "classList.contains('pin')" not in body, (
        f"{event} still guards with classList.contains, which misses a "
        f"press on a child element")


def test_the_card_is_still_inside_the_map():
    """If it ever moves out, these guards become dead weight rather than
    load-bearing, and the reason for them stops being obvious."""
    assert re.search(r'<div id="mapview">.*?<div id="mapinfo"',
                     SRC, re.S), (
        "mapinfo is no longer nested inside mapview — re-check whether "
        "the gesture guards are still needed")


def test_the_card_carries_the_links_this_protects():
    """The bug was invisible partly because nothing asserted the card has
    links at all."""
    assert 'class="cardlinks"' in SRC
    assert "goSite(" in SRC          # internal: open the site row
    assert 'rel="noopener"' in SRC   # external: Drive and the register


def test_dragging_the_map_still_hides_the_card():
    """The fix must not turn into 'never hide the card' — a card left
    floating over a map the user has panned is pointing at nothing."""
    body = _handler_body("pointerdown")
    move = SRC[SRC.index("map.el.addEventListener('pointermove'"):][:600]
    assert "hideCard()" in move
    assert "map.drag" in body
