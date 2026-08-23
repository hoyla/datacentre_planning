"""Build the reader, load it in a browser, click what a reporter clicks.

Every regression that reached a shipped reader was invisible to the
suite and obvious within seconds of opening the page: card links that
did nothing (the map's drag handler ate the click), a chip that took its
own flex column and squashed the map, an energy checkbox that went dead
inside a projection, a sidebar that described a different map from the
one on screen. Four hundred tests passed throughout, because nothing
drove the artefact. ROADMAP asked for a build-and-drive test; this is
it.

It builds the reader from the live database into a temporary file (nine
seconds), opens it headless in Chromium through Playwright, and asserts
the behaviours, not the pixels:

- every tab button shows its view and hides the others;
- a site row opens, its panel shows, and the address bar names it;
- every filter control changes the count, the count matches the rows
  actually visible, and "See all on map" reports the same set;
- deep links land — a `#site-` link opens that site with the filters
  cleared, a `#dict-` link opens the dictionary;
- a map card's link navigates (the 2.1 regression);
- the operators table expands;
- nothing throws. Console *errors* about map tiles are tolerated,
  because tiles are the one runtime dependency and the test may run
  offline; an uncaught exception is not.

Needs the live database (to build) and Playwright's Chromium
(`playwright install chromium`); skips cleanly without either. Marked
integration for the same reason the determinism test is: a small
fixture would not exercise the real markup.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "scripts" / "export_reader.py"

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


def _build(out: Path) -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    proc = subprocess.run(
        [sys.executable, str(EXPORT), "--out", str(out), "--phase", "test"],
        cwd=ROOT, capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0:
        combined = proc.stdout + proc.stderr
        tail = combined.strip().splitlines()[-8:]
        if "uncorrected" in combined:
            pytest.skip("adjudication gate refused the build: " + " / ".join(tail))
        if "could not connect" in combined or "OperationalError" in combined:
            pytest.skip("live database unreachable: " + " / ".join(tail))
        pytest.fail("build failed:\n" + "\n".join(tail))


@pytest.fixture(scope="module")
def reader_url(tmp_path_factory) -> str:
    out = tmp_path_factory.mktemp("reader") / "reader.html"
    _build(out)
    return out.as_uri()


@pytest.fixture(scope="module")
def page(reader_url):
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as e:
            pytest.skip(f"Chromium not available to Playwright: {str(e).splitlines()[0]}")
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        pg.errors = []      # uncaught exceptions
        pg.console_errors = []
        pg.on("pageerror", lambda exc: pg.errors.append(str(exc)))
        pg.on("console", lambda msg: pg.console_errors.append(msg.text)
              if msg.type == "error" else None)
        pg.goto(reader_url)
        # The page opens on Start, so the rows exist but are not visible.
        pg.wait_for_selector("#tbl-sites tr.site", state="attached")
        yield pg
        browser.close()


# --- helpers ------------------------------------------------------------

def _visible_site_rows(page) -> int:
    return page.evaluate(
        "() => [...document.querySelectorAll('#tbl-sites tr.site')]"
        ".filter(r => r.style.display !== 'none').length")


def _count_text(page) -> tuple[int, int]:
    m = re.match(r"([\d,]+) of ([\d,]+) sites", page.locator("#n").inner_text())
    assert m, "count string missing or reshaped"
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def _views_on(page) -> list[str]:
    return page.evaluate(
        "() => [...document.querySelectorAll('section.view.on')].map(s => s.id.slice(5))")


# --- the behaviours -------------------------------------------------------

@pytest.mark.integration
def test_every_tab_shows_exactly_its_view(page):
    tabs = page.evaluate(
        "() => [...document.querySelectorAll('nav.top button[id^=tab-]')].map(b => b.id.slice(4))")
    assert len(tabs) >= 9, tabs
    for tab in tabs:
        page.click(f"#tab-{tab}")
        assert _views_on(page) == [tab], f"after clicking {tab}: {_views_on(page)}"
        assert page.locator(f"#view-{tab}").is_visible()
    page.click("#tab-sites")


@pytest.mark.integration
def test_a_site_row_opens_and_the_address_bar_names_it(page):
    page.click("#tab-sites")
    row = page.locator("#tbl-sites tr.site").first
    key = row.get_attribute("data-key")
    row.click()
    assert "open" in row.get_attribute("class")
    detail = page.locator(f"#tbl-sites tr.site[data-key='{key}'] + tr.detail")
    assert detail.is_visible()
    assert page.evaluate("() => decodeURIComponent(location.hash)") == f"#site-{key}"
    # The panel is where the evidence chain starts; it must carry links.
    assert detail.locator("a[href]").count() >= 2
    row.click()
    assert "open" not in row.get_attribute("class")


@pytest.mark.integration
def test_filters_change_the_count_and_the_count_is_true(page):
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    shown, total = _count_text(page)
    assert shown == total == _visible_site_rows(page)

    seen = {total}
    for value in page.evaluate(
            "() => [...document.querySelectorAll('#f option')].map(o => o.value)"):
        page.select_option("#f", value)
        shown, total_now = _count_text(page)
        assert total_now == total
        assert shown == _visible_site_rows(page), f"filter {value}: count lies"
        seen.add(shown)
    assert len(seen) > 1, "no filter changed the count"
    page.select_option("#f", "all")

    page.fill("#q", "virtus")
    shown, _ = _count_text(page)
    assert 0 < shown < total
    assert shown == _visible_site_rows(page)
    page.fill("#q", "")

    page.click("#big")
    shown_big, _ = _count_text(page)
    assert shown_big < total
    assert not page.is_disabled("#unk"), "exclude-unknown must enable with the 100 MW toggle"
    page.check("#unk")
    shown_known_big, _ = _count_text(page)
    assert shown_known_big < shown_big
    page.uncheck("#unk")
    page.click("#big")
    assert _count_text(page)[0] == total


@pytest.mark.integration
def test_an_organisation_chip_filters_and_is_a_link(page):
    """The who's-behind-it chips (READER_REDESIGN_PLAN §5e).

    Three things at once, because they are one behaviour: the chip
    filters the table, the count it leaves is the number of rows a
    reader can see, and the URL says which chip is on — a filtered table
    has to be sendable.
    """
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    _, total = _count_text(page)

    chip = page.locator("#whochips .chip").nth(1)   # 0 is "Any"
    key = chip.get_attribute("data-who")
    assert key, "a chip with no organisation behind it"
    chip.click()
    shown, total_now = _count_text(page)
    assert total_now == total
    assert 0 < shown < total, "the chip filtered nothing"
    assert shown == _visible_site_rows(page), "the chip's count lies"
    assert page.evaluate("() => decodeURIComponent(location.hash)") == "#who:" + key
    assert chip.get_attribute("aria-pressed") == "true"

    # Every row left is that organisation's.
    assert page.evaluate(
        "k => [...document.querySelectorAll('#tbl-sites tr.site')]"
        "  .filter(r => r.style.display !== 'none')"
        "  .every(r => r.dataset.who === k)", key)

    # Clicking it again is the way back, and so is Any.
    chip.click()
    assert _count_text(page)[0] == total
    chip.click()
    page.locator("#whochips .chip").first.click()
    assert _count_text(page)[0] == total


@pytest.mark.integration
def test_a_badge_in_the_table_filters_to_its_organisation(page):
    """The badge is the same control as the chip, on the row itself."""
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    _, total = _count_text(page)
    badge = page.locator("#tbl-sites tr.site button.who").first
    key = badge.get_attribute("data-who")
    badge.click()
    shown, _ = _count_text(page)
    assert 0 < shown <= total
    assert shown == _visible_site_rows(page)
    assert page.evaluate("() => decodeURIComponent(location.hash)") == "#who:" + key
    # Clicking a badge must not open the row underneath it.
    assert page.locator("#tbl-sites tr.site.open").count() == 0
    page.locator("#whochips .chip").first.click()


@pytest.mark.integration
def test_signals_cards_count_what_their_chips_leave(page):
    """READER_REDESIGN_PLAN §6c: a card's count is the chip's row count.

    The prototype's counts were typed in and wrong. Here the number on
    every computed card is read off the page, the matching chip is
    clicked, and the table must show exactly that many rows.
    """
    page.click("#tab-signals")
    assert _views_on(page) == ["signals"]
    cards = page.locator(".box.signal")
    assert cards.count() >= 3
    counts = page.evaluate(
        "() => [...document.querySelectorAll('.box.signal')].map(b => ({"
        "  key: b.id.replace(/^signal-/, ''),"
        "  n: (b.querySelector('.sigcount:not(.withheld)')||{}).textContent||null}))")
    computed = [(c["key"], int(c["n"].split()[0].replace(",", "")))
                for c in counts if c["n"]]
    assert computed, "no computed cohort on the page"
    withheld = [c["key"] for c in counts if not c["n"]]
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    for key, n in computed:
        chip = page.locator(f'#cohortchips .chip[data-cohort="{key}"]')
        chip.click()
        shown, _ = _count_text(page)
        assert shown == n == _visible_site_rows(page), f"{key}: card says {n}, table shows {shown}"
        assert page.evaluate("() => decodeURIComponent(location.hash)") == f"#cohort:{key}"
        chip.click()
    for key in withheld:
        assert page.locator(f'#cohortchips .chip[disabled]').count() >= 1
        assert page.locator(f'#cohortchips .chip[data-cohort="{key}"]').count() == 0


@pytest.mark.integration
def test_the_two_chip_groups_compose_and_both_sit_in_the_url(page):
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    who = page.locator("#whochips .chip").nth(1)
    coh = page.locator("#cohortchips .chip:not([disabled])").nth(1)
    who.click(); coh.click()
    h = page.evaluate("() => decodeURIComponent(location.hash)")
    assert h.startswith("#who:") and ";cohort:" in h
    shown, _ = _count_text(page)
    assert shown == _visible_site_rows(page)
    # The URL round-trips: reload on it and the same filter is on.
    page.goto(page.url)
    page.wait_for_function("() => document.querySelectorAll('tr.site').length > 0")
    assert page.evaluate("() => decodeURIComponent(location.hash)") == h
    assert _count_text(page)[0] == shown
    page.locator("#whochips .chip").first.click()
    page.locator("#cohortchips .chip").first.click()


@pytest.mark.integration
def test_see_all_on_map_describes_the_same_set(page):
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "power")
    shown, _ = _count_text(page)
    page.click("#seemap")
    assert _views_on(page) == ["map"]
    text = page.locator("#mapsubsettext").inner_text()
    m = re.match(r"([\d,]+) of ([\d,]+) filtered sites? shown", text)
    assert m, text
    plotted, filtered = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    assert filtered == shown, "the map's sidebar describes a different set from the table"
    assert plotted <= filtered
    if plotted < filtered:
        assert "no recorded location" in text
    page.click("#tab-sites")
    page.select_option("#f", "all")


@pytest.mark.integration
def test_deep_links_land(page):
    key = page.locator("#tbl-sites tr.site").nth(3).get_attribute("data-key")
    # Set a filter first: a shared link must open the site for someone
    # whose filters are not the sender's.
    page.click("#tab-sites")
    page.select_option("#f", "power")
    page.evaluate(f"() => {{ location.hash = '#site-{key}'; }}")
    page.wait_for_function(
        f"() => document.querySelector(\"#tbl-sites tr.site[data-key='{key}']\")"
        ".classList.contains('open')")
    assert _views_on(page) == ["sites"]
    assert page.input_value("#f") == "all", "a shared link must clear the filters"

    entry = page.evaluate("() => document.querySelector('#view-dict .entry')?.id")
    assert entry, "dictionary has no entries"
    page.evaluate(f"() => {{ location.hash = '#{entry}'; }}")
    page.wait_for_function("() => document.querySelector('#view-dict').classList.contains('on')")
    assert _views_on(page) == ["dict"]
    page.click("#tab-sites")


@pytest.mark.integration
def test_a_map_card_link_survives_a_real_mouse(page):
    """The 2.1 regression, re-enacted.

    The card is a child of the map, so pressing one of its links reached
    the map's drag handler, and the first pixel of pointer movement —
    which every real mouse produces between press and release — hid the
    card before the mouseup that would have completed the click. A
    Playwright `click()` moves the pointer *before* pressing and would
    pass against that bug, so this presses, moves one pixel, releases.
    """
    page.click("#tab-map")
    page.wait_for_selector("button.pin.s", state="attached")
    # Pins overlap at the fitted zoom, so a pointer click on "the first
    # pin" can be refused as obstructed by another. Which pin opens the
    # card is immaterial here; dispatching the click is not.
    page.locator("button.pin.s").first.dispatch_event("click")
    card = page.locator("#mapinfo")
    assert card.is_visible(), "clicking a pin did not open its card"
    # "Open this site" is href="#sites" with an onclick that calls goSite.
    link = card.locator("a[onclick*='goSite']").first
    assert link.count() == 1, "the card carries no 'Open this site' link"
    box = link.bounding_box()
    assert box, "card link has no box"
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 1, y + 1)
    page.mouse.up()
    page.wait_for_function("() => location.hash.startsWith('#site-')", timeout=5000)
    assert _views_on(page) == ["sites"], "the card's link did not leave the map"


@pytest.mark.integration
def test_an_operator_row_expands(page):
    page.click("#tab-operators")
    row = page.locator("tr.op").first
    if row.count() == 0:
        pytest.skip("no operator rows")
    row.click()
    assert "open" in row.get_attribute("class")
    assert page.locator("tr.op.open + tr.detail").is_visible()
    page.click("#tab-sites")


@pytest.mark.integration
def test_nothing_threw(page):
    assert page.errors == [], page.errors
    tiles = [e for e in page.console_errors
             if "tile" in e.lower() or "net::" in e or "Failed to load resource" in e]
    real = [e for e in page.console_errors if e not in tiles]
    assert real == [], real
