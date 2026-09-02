"""Issue #301: the map link's help tooltip opened off-screen and stayed open.

Source-level. The tooltip opens below its "?" and grows leftwards, and a
press anywhere else, or the pointer leaving it, drops the focus that
kept it open.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "scripts" / "export_reader.py").read_text()


def test_the_tooltip_opens_below_and_grows_leftwards():
    rule = re.search(r"\.tip \.tiptext\{([^}]*)\}", SRC).group(1)
    assert "position:absolute" in rule and "top:20px" in rule and "right:-8px" in rule
    assert "bottom:" not in rule and "left:" not in rule


def test_a_press_elsewhere_or_leaving_it_closes_a_focused_tooltip():
    assert "document.addEventListener('pointerdown'" in SRC
    assert "a.closest('.tip')" in SRC and "t.blur()" in SRC
    assert "addEventListener('mouseleave'" in SRC
    # hover, focus and focus-within still open it — keyboard and touch keep their route
    assert ".tip:hover .tiptext,.tip:focus .tiptext," in SRC
