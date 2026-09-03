"""Build the reader, load it in a browser, click what a reporter clicks.

Every regression that reached a shipped reader was invisible to the
suite and obvious within seconds of opening the page: card links that
did nothing (the map's drag handler ate the click), a chip that took its
own flex column and squashed the map, an energy checkbox that went dead
inside a projection, a sidebar that described a different map from the
one on screen. Four hundred tests passed throughout, because nothing
drove the artefact. ROADMAP asked for a build-and-drive test; this is
it.

It takes the session-wide reader build (conftest's `built_reader`),
opens it headless in Chromium through Playwright, and asserts the
behaviours, not the pixels:

- every tab button shows its view and hides the others;
- a site row opens, its panel shows, and the address bar names it;
- every filter control changes the count, the count matches the rows
  actually visible, and "See on map" reports the same set;
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
import pathlib
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def reader_url(built_reader) -> str:
    """The session-wide build in conftest, so this suite and the
    design-conformance suite do not build the reader twice."""
    return built_reader


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


def _reset(page) -> None:
    """Every control off. The page is module-scoped, so a filter one test
    leaves on is a filter the next one inherits — which used to be
    harmless and is not now that a cohort chip can empty the table."""
    page.click("#tab-sites")
    page.evaluate("() => { setWho(''); setCohort(''); }")
    page.fill("#q", "")
    page.select_option("#f", "all")
    page.select_option("#o", "")


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
def test_a_site_row_opens_its_page_and_back_returns_the_table(page):
    """READER_REDESIGN_PLAN §7a: a row opens a page, not an expansion.

    The panel's markup is moved from the row into the page and handed
    back on the way out, so after a round trip the table must hold
    exactly what it held before — counted by links, the same instrument
    release_diff uses.
    """
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    row = page.locator("#tbl-sites tr.site").first
    key = row.get_attribute("data-key")
    detail = page.locator(f"#tbl-sites tr.site[data-key='{key}'] + tr.detail")
    links_before = detail.locator("a[href]").count()
    assert links_before >= 2, "the panel is where the evidence chain starts"

    row.click()
    assert _views_on(page) == ["site"]
    assert page.evaluate("() => decodeURIComponent(location.hash)") == f"#site-{key}"
    assert page.locator("#sitehost .sitename").inner_text().strip()
    assert page.locator("#view-site h2#sitetitle").count() == 0, (
        "the name belongs to the header card, not to a page-level "
        "heading scraped out of the row")
    assert page.locator("#sitehost a[href]").count() == links_before
    assert detail.locator("a[href]").count() == 0, "the panel must move, not copy"
    # The Sites tab stays lit: the page is a place inside Sites.
    assert page.get_attribute("#tab-sites", "aria-selected") == "true"

    page.click("#view-site .sitenav a")
    assert _views_on(page) == ["sites"]
    assert detail.locator("a[href]").count() == links_before
    assert page.locator("#sitehost *").count() == 0
    assert "open" not in (row.get_attribute("class") or "")


@pytest.mark.integration
def test_back_from_a_site_keeps_the_filters(page):
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "power")
    shown, _ = _count_text(page)
    row = page.locator("#tbl-sites tr.site:visible").first
    row.click()
    assert _views_on(page) == ["site"]
    page.click("#view-site .sitenav a")
    assert page.input_value("#f") == "power"
    assert _count_text(page)[0] == shown
    page.select_option("#f", "all")


@pytest.mark.integration
def test_filters_change_the_count_and_the_count_is_true(page):
    _reset(page)
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

    # 100 MW is a cohort chip, not a toggle in the bar (Luke,
    # 2026-08-25). A site with no figure is not a member, and the cohort
    # says on the Signals tab that this is not a claim it is smaller.
    big = page.locator("#cohortchips .chip[data-cohort=at_least_100mw]")
    big.click()
    shown_big, in_cohort = _count_text(page)
    assert 0 < shown_big < total
    assert shown_big == in_cohort == _visible_site_rows(page)
    page.click("#clearcohort")
    assert _count_text(page)[0] == total


@pytest.mark.integration
def test_the_organisation_filter_states_itself_and_can_be_left(page):
    """The who's-behind-it filter (READER_REDESIGN_PLAN §5e, amended by
    Luke 2026-08-25: the badge in the row is the control, and there is no
    button per organisation above the table).

    Four things at once, because they are one behaviour: the badge
    filters, the count it leaves is the number of rows a reader can see,
    the URL says which filter is on — a filtered table has to be
    sendable — and the page SAYS it is filtered, because a reader who
    cannot see what is filtering a table reads a subset as the whole.
    """
    page.click("#tab-sites")
    page.fill("#q", "")
    page.select_option("#f", "all")
    _, total = _count_text(page)
    assert not page.locator("#whobar").is_visible(), \
        "the filter bar shows with no filter on"

    badge = page.locator("#tbl-sites tr.site button.who").first
    key = badge.get_attribute("data-who")
    name = badge.get_attribute("data-whoname")
    assert key and name
    badge.click()
    shown, total_now = _count_text(page)
    assert total_now == total
    assert 0 < shown < total, "the badge filtered nothing"
    assert shown == _visible_site_rows(page), "the count lies"
    assert page.evaluate("() => decodeURIComponent(location.hash)") == "#who:" + key

    bar = page.locator("#whobar")
    assert bar.is_visible(), "the table is filtered and does not say so"
    assert name[:18] in bar.inner_text(), \
        f"the bar does not name what it filtered to: {bar.inner_text()!r}"

    # Every row left is that organisation's — alone, or as one of the
    # operators an estate record holds.
    assert page.evaluate(
        "k => [...document.querySelectorAll('#tbl-sites tr.site')]"
        "  .filter(r => r.style.display !== 'none')"
        "  .every(r => r.dataset.who.split('|').includes(k))", key)

    page.locator("#whobar .chip").click()          # Clear
    assert _count_text(page)[0] == total
    assert not bar.is_visible()


@pytest.mark.integration
def test_a_badge_in_the_table_filters_to_its_organisation(page):
    """The badge is the control, and it lives on the row."""
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
    page.locator("#whobar .chip").click()


@pytest.mark.integration
def test_signals_cards_count_what_their_chips_leave(page):
    """READER_REDESIGN_PLAN §6c: a card's count is the chip's row count.

    The prototype's counts were typed in and wrong. Here the number on
    every computed card is read off the page, the matching chip is
    clicked, and the table must show exactly that many rows.
    """
    page.click("#tab-signals")
    assert _views_on(page) == ["signals"]
    cards = page.locator(".sigcard")
    assert cards.count() >= 3
    # The count moved into the card's right-hand column with the design
    # handoff's §3 layout; a withheld cohort has no .signum at all.
    counts = page.evaluate(
        "() => [...document.querySelectorAll('.sigcard')].map(b => ({"
        "  key: b.id.replace(/^signal-/, ''),"
        "  n: (b.querySelector('.signum')||{}).textContent||null}))")
    # A cohort the rule selected nothing for has no chip to click: its
    # card states the zero, which is a result, and offers nothing to
    # open. Those are checked by the assertion below rather than here.
    computed = [(c["key"], int(c["n"].split()[0].replace(",", "")))
                for c in counts if c["n"]
                and int(c["n"].split()[0].replace(",", "")) > 0]
    empty = [c["key"] for c in counts if c["n"]
             and int(c["n"].split()[0].replace(",", "")) == 0]
    for key in empty:
        card = page.locator(f"#signal-{key}")
        assert card.locator(".signum").inner_text().strip() == "0"
        assert card.locator(".cta").count() == 0, \
            f"{key} selected no sites and still offers to open them"
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
def test_an_organisation_and_a_signal_compose_and_both_sit_in_the_url(page):
    """A badge filter and a cohort chip are different questions and both
    apply. The badge is the row's; the chip is the table's."""
    _reset(page)
    # The chip counts answer to the filters above them now, so most
    # organisations' sites match no cohort at all and every chip is
    # disabled. Find one that does compose rather than taking the first
    # badge on the page and skipping when it does not.
    whos = page.locator("#tbl-sites tr.site button.who")
    coh = page.locator("#cohortchips .chip[data-cohort]:not([disabled])")
    for i in range(min(whos.count(), 40)):
        page.evaluate("() => setWho('')")
        whos.nth(i).click()
        if coh.count():
            break
    else:
        pytest.skip("no organisation in this build composes with a cohort")
    coh.first.click()
    h = page.evaluate("() => decodeURIComponent(location.hash)")
    assert h.startswith("#who:") and ";cohort:" in h
    shown, _ = _count_text(page)
    assert shown == _visible_site_rows(page)
    # The URL round-trips: reload on it and the same filter is on.
    page.goto(page.url)
    page.wait_for_function("() => document.querySelectorAll('tr.site').length > 0")
    assert page.evaluate("() => decodeURIComponent(location.hash)") == h
    assert _count_text(page)[0] == shown
    page.locator("#whobar .chip").click()
    page.click("#clearcohort")


@pytest.mark.integration
def test_a_machine_reading_is_collapsed_labelled_and_quoted(page):
    """READER_REDESIGN_PLAN §7e. Where a reading exists it renders
    closed, says what it is before what it says, and every quote names
    where it is from. Skips when no site carries one yet."""
    n = page.locator("details.reading").count()
    if n == 0:
        pytest.skip("no machine reading in this build")
    key = page.evaluate(
        "() => document.querySelector('details.reading').closest('tr.detail')"
        "  .previousElementSibling.dataset.key")
    page.evaluate(f"() => {{ location.hash = '#site-{key}'; }}")
    page.wait_for_function(
        "() => document.querySelector('#view-site').classList.contains('on')")
    d = page.locator("#sitehost details.reading").first
    assert d.count() == 1
    assert not d.evaluate("el => el.open"), "a reading must render collapsed"
    label = d.locator("summary").inner_text()
    assert "machine" in label.lower() and "Not a finding" in label
    d.locator("summary").click()
    assert d.evaluate("el => el.open")
    assert d.locator(".rbody p").count() >= 1


@pytest.mark.integration
def test_a_withheld_paragraph_is_declared_before_it_is_found(page):
    """A panel opens closed, so a withheld paragraph sitting inside it is
    invisible to a reader who never expands — and an omission a reader
    cannot see is one they will assume did not happen. Every panel
    holding one says so in its summary, and the count matches what is
    inside (Luke, 2026-08-24)."""
    panels = page.locator("details.reading")
    if panels.count() == 0:
        pytest.skip("no machine reading in this build")
    checked = 0
    for i in range(panels.count()):
        d = panels.nth(i)
        held = d.locator("p.rwithheld").count()
        summary = d.locator("summary").inner_text()
        if held:
            checked += 1
            assert "withheld" in summary, \
                "a panel holding a withheld paragraph does not say so"
            assert str(held) in summary or (held == 1 and "One" in summary), \
                f"summary does not name the count ({held}): {summary[-120:]}"
        else:
            assert "withheld" not in summary
    if not checked:
        pytest.skip("no withheld paragraph in this build")
    # Every quote names its source, and cited documents link out.
    # Asserted per item rather than by counting `.q` elements: a cited
    # document now carries two, the page-and-reference span and the
    # register link beside the link to our own copy, so one-span-per-item
    # stopped being the same claim as every-item-has-a-span.
    assert d.locator("ul.rq li:has(.q)").count() == d.locator("ul.rq li").count()
    # Cleanup, and guarded because this test never opens the site page
    # itself — it reads panels wherever they sit. The site view is open
    # only because the test above navigated there, so an unguarded click
    # waits the full 30 seconds for a view that was never on whenever
    # that test is deselected, skipped, or reordered.
    if page.locator("#view-site").is_visible():
        page.click("#view-site .sitenav a")


@pytest.mark.integration
def test_the_map_shows_the_set_the_table_shows(page):
    """One filter bar, two views (Luke, 2026-08-25).

    The map used to be handed a copy of the table's result and to keep
    its own search box, 100 MW toggle and cohort select alongside it, so
    the two could report different totals for one filter. It reads the
    same decision now, and its count has to reconcile with the table's.
    """
    _reset(page)
    page.select_option("#f", "power")
    shown, _ = _count_text(page)
    page.click("#seemap")
    assert _views_on(page) == ["map"]
    text = page.locator("#mapcount").inner_text()
    m = re.match(r"([\d,]+) of ([\d,]+) sites? on the map", text)
    assert m, text
    plotted, filtered = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    assert filtered == shown, "the map describes a different set from the table"
    assert plotted <= filtered
    if plotted < filtered:
        assert "no recorded location" in text

    # And filtering from the map moves both: the bar is the same bar.
    assert page.is_visible("#filterbar")
    page.select_option("#f", "all")
    after = page.locator("#mapcount").inner_text()
    assert after != text, "changing a filter on the map changed nothing"
    page.click("#tab-sites")
    assert _count_text(page)[0] == int(
        re.match(r"([\d,]+) of ([\d,]+) sites?", after).group(2).replace(",", ""))


@pytest.mark.integration
def test_deep_links_land(page):
    key = page.locator("#tbl-sites tr.site").nth(3).get_attribute("data-key")
    # Set a filter first: a shared link must open the site for someone
    # whose filters are not the sender's.
    page.click("#tab-sites")
    page.select_option("#f", "power")
    page.evaluate(f"() => {{ location.hash = '#site-{key}'; }}")
    page.wait_for_function(
        "() => document.querySelector('#view-site').classList.contains('on')")
    assert _views_on(page) == ["site"]
    assert page.locator("#sitehost a[href]").count() >= 2
    # The page shows whatever the table is filtered to; the filter is
    # the reader's and is not touched by a link.
    assert page.input_value("#f") == "power"
    page.click("#view-site .sitenav a")
    page.select_option("#f", "all")

    entry = page.evaluate("() => document.querySelector('#view-dict .entry')?.id")
    assert entry, "dictionary has no entries"
    page.evaluate(f"() => {{ location.hash = '#{entry}'; }}")
    page.wait_for_function("() => document.querySelector('#view-dict').classList.contains('on')")
    assert _views_on(page) == ["dict"]
    page.click("#tab-sites")


@pytest.mark.integration
def test_a_cohort_chip_colours_the_map(page):
    """§8c: "chips colour the map's markers by the active cohort". Not a
    hue per cohort — §8b keeps colour for the state of a figure — but
    the reader's own selection in the same yellow the chips use, with
    everything outside it stepped back. The map takes the cohort from
    the Sites tab, so the two views cannot disagree about which is on.
    """
    _reset(page)
    page.click("#tab-map")
    # The chip itself, in the bar the map shares with the table. The map
    # used to carry a select of its own that a handover wrote into.
    chip = page.locator(
        "#cohortchips .chip[data-cohort]:not([disabled])").first
    if not chip.count():
        pytest.skip("no cohort has members in this build")
    chip.click()
    page.wait_for_timeout(250)
    inside = page.locator("#mappins .pin.inco").count()
    outside = page.locator("#mappins .pin.outco").count()
    assert inside > 0, "no marker is marked as in the active cohort"
    assert outside > 0, "every marker is in the cohort — the chip did nothing"
    key = page.locator("#mapcohortkey")
    assert key.is_visible(), "the key does not say what the colour means"
    name = page.locator("#mapcohortname").inner_text().strip()
    assert name and "(" not in name, f"the key names the chip, not its count: {name!r}"
    # Clearing puts the map back.
    page.click("#clearcohort")
    page.wait_for_timeout(250)
    assert page.locator("#mappins .pin.inco").count() == 0
    assert not key.is_visible()
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
    assert _views_on(page) == ["site"], "the card's link did not leave the map"


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


@pytest.mark.integration
def test_next_and_previous_walk_the_filtered_set(page):
    """A reporter's own set, stepped through without going back.

    Asked for by a reader on 2026-08-26, and cheap for a reason worth
    recording: the filter hides rows with `display:none` rather than
    removing them, so the DOM already holds the reader's set in their
    chosen order. Nothing has to be remembered between the table and the
    site page — which is the same reason Back returns to the right place.

    The failure this guards against is the sequence quietly walking the
    WHOLE table while the reader believes they are inside their filter.
    """
    page.click("#tab-sites")
    page.fill("#q", "data centre")
    page.wait_for_timeout(250)

    rows = page.locator("tr.site:visible")
    n = rows.count()
    assert n > 2, f"filter left {n} rows; this test needs a few to step through"

    first_key = rows.nth(0).get_attribute("data-key")
    second_key = rows.nth(1).get_attribute("data-key")
    rows.nth(0).click()
    page.wait_for_selector("#view-site", state="visible")

    seq = page.locator("#siteseqn")
    assert seq.inner_text().strip() == f"1 of {n}", (
        f"position reads {seq.inner_text()!r}, so the sequence is not the "
        f"filtered set of {n}")
    assert page.locator("#siteprev").is_disabled(), \
        "there is nothing before the first site, so Previous must be dead"

    page.click("#sitenext")
    page.wait_for_timeout(200)
    assert page.locator("#view-site").is_visible()
    assert seq.inner_text().strip() == f"2 of {n}"
    # The site it moved to is the table's own next row, not the corpus's.
    assert page.evaluate("openKey") == second_key

    page.click("#siteprev")
    page.wait_for_timeout(200)
    assert page.evaluate("openKey") == first_key
    assert page.locator("#siteprev").is_disabled()


@pytest.mark.integration
def test_no_link_in_the_built_page_points_at_a_filesystem(built_reader):
    """The check that was missing when 401 dead links shipped in 2.8.

    Every other assertion here drives behaviour through a browser; this
    one reads the bytes, because the failure was not behavioural. The
    anchors worked perfectly — they resolved to a path on the machine
    that built the page, and to nothing at all anywhere else, and no
    test looked at where a link went.

    Held as a property of the artefact rather than of `doc_link`, which
    is asserted separately: the unit test cannot see a call site that
    forgot to use it.
    """
    import urllib.parse
    html = pathlib.Path(urllib.parse.urlparse(built_reader).path).read_text()
    bad = re.findall(r'href=["\']([^"\']*file://[^"\']*)["\']', html)
    assert not bad, (
        f"{len(bad)} links resolve on nobody's machine, e.g. {bad[:3]} — "
        f"a document we hold should link to our copy on Drive")

    # And the positive half: the documents we hold are actually offered.
    ours = html.count("drive.google.com/file/d/")
    assert ours > 1000, (
        f"only {ours} document links point at our Drive copies; the "
        f"corpus holds 52,908 documents and the reader cites thousands, "
        f"so this looks like the map failed to build rather than a page "
        f"that genuinely cites nothing")


@pytest.mark.integration
def test_every_our_copy_link_names_a_snapshot_this_repository_holds(built_reader):
    """The same check as the one above, for the claims channel.

    A claim's "our copy" link is resolved from the claim's own quote
    against the append-only snapshot store, then from the file's
    recorded Drive id. Both halves can fail silently: a resolution that
    picked the wrong file would render a link that works and shows
    evidence for a different figure, and a file with no ledger entry
    would render nothing at all. So this reads the built bytes and
    asserts the property — every rendered our-copy href names a file id
    in the committed ledger — rather than trusting the helper, which
    cannot see a call site that resolved by hand.
    """
    import urllib.parse

    from dcp import snapshot_drive as sd
    html = pathlib.Path(urllib.parse.urlparse(built_reader).path).read_text()
    hrefs = re.findall(r'<a class="oursnap" href="([^"]+)"', html)
    ids = {m["file_id"] for m in sd.load_ledger().values()}
    stray = sorted({h for h in hrefs
                    if not re.fullmatch(
                        r"https://drive\.google\.com/file/d/([^/]+)/view", h)
                    or re.fullmatch(
                        r"https://drive\.google\.com/file/d/([^/]+)/view",
                        h).group(1) not in ids})
    assert not stray, (
        f"{len(stray)} our-copy links do not name a snapshot in "
        f"data/external_sources/operator_snapshots_drive.yaml, e.g. "
        f"{stray[:3]} — a claim must link its own evidence or nothing")

    # And the positive half, so a build that resolved nothing at all
    # cannot pass by rendering no links — the check above is vacuous on
    # an empty set.
    #
    # **Only against a reader this code built.** CI drives the committed
    # `index.html`, which is a *released* artefact: it predates this
    # feature and correctly carries no our-copy links, so a count
    # asserted there measures the age of the release rather than the
    # behaviour of the code, and fails every PR until the next build is
    # published. That is how this test failed on its first CI run.
    # The released page still gets the stray check above, which is the
    # half that must never fail on bytes about to be served.
    #
    # What covers the gap in CI: `test_snapshot_drive.py` asserts every
    # committed claim resolves to a ledgered file, and that the three
    # reader surfaces call the helper — neither needs a build.
    if os.environ.get("READER_HTML"):
        pytest.skip("READER_HTML names a reader built earlier; a link "
                    "count belongs to a build made from this code")
    assert len(hrefs) > 50, (
        f"only {len(hrefs)} claims offer our copy of the page they were "
        f"read from; the store holds 84 snapshots behind 81 operator "
        f"claims and six green claims, so this looks like resolution "
        f"failed rather than a corpus that genuinely cites nothing")


def test_every_operator_rung_cell_is_labelled_in_the_built_page(built_reader):
    """A first-party campus figure must never render as a planning one.

    The rung puts a number a marketing page published into the column a
    reporter sorts, so the label is not styling — decision 2 of
    docs/PLAN_OPERATOR_RUNG.md is conditional on a reader being able to
    see what the figure is and what the planning record says instead.
    This reads the built bytes rather than trusting the mapping, which
    cannot see a call site that classed a cell by hand.

    Both halves, as `test_every_our_copy_link...` does above: no
    `w-operator` cell may carry any other basis label, and the two
    adjudicated displacements must actually be there — checked only
    against a reader this code built, because the committed
    `index.html` is a released artefact predating the feature and a
    count asserted there measures the age of the release.
    """
    import urllib.parse

    from dcp import campus_scope, site_scale

    html = pathlib.Path(urllib.parse.urlparse(built_reader).path).read_text()
    cells = re.findall(
        r"<span class='fig (w-[a-z]+)'>[^<]*</span><span class='q'>([^<]*)",
        html)
    mislabelled = sorted({(w, q) for w, q in cells
                          if (w == "w-operator")
                          != (q == site_scale.OPERATOR_BASIS)})
    assert not mislabelled, (
        f"the operator weight class and its basis label disagree on "
        f"{len(mislabelled)} cells, e.g. {mislabelled[:3]} — a first-party "
        f"figure styled as a planning disclosure, or the reverse")

    if os.environ.get("READER_HTML"):
        pytest.skip("READER_HTML names a reader built earlier; the "
                    "displacements belong to a build made from this code")
    n = sum(1 for w, _q in cells if w == "w-operator")
    assert n >= len(campus_scope.load_displacements()), (
        f"only {n} operator-rung cells rendered, against "
        f"{len(campus_scope.load_displacements())} adjudicated "
        f"displacements alone — a build that ranked none of them would "
        f"pass the check above vacuously")


def test_near_a_postcode_filters_orders_and_states_what_it_cannot_place(page):
    """The control decided on 2026-09-02 at sector precision: SL1 4BG is
    the Slough Trading Estate, so a small radius keeps the estate's sites
    and drops the rest, the survivors come nearest first, the hash carries
    it, and clearing it puts everything back."""
    _reset(page)
    # CI drives the committed index.html, a released page. Until the
    # release that carries the control it has no #near, and a test that
    # waits for one measures the age of the release, not the code — how
    # this test failed on its first CI run. Feature-detected rather than
    # keyed to READER_HTML, so a scratch build of this code is still driven.
    if page.locator("#near").count() == 0:
        pytest.skip("this page predates the postcode control (built before 2026-09-02)")
    page.fill("#near", "")
    before, total = _count_text(page)
    page.fill("#near", "SL1 4BG")
    page.select_option("#nearkm", "5")
    page.wait_for_timeout(200)
    shown, _ = _count_text(page)
    assert 0 < shown < before, (shown, before)
    text = page.locator("#n").inner_text()
    assert "cannot be placed" in text
    assert "near:SL1%204BG" in page.url or "near:SL1 4BG" in page.url
    assert "km:5" in page.url
    kms = page.evaluate(
        "() => [...document.querySelectorAll('#tbl-sites tr.site')]"
        ".filter(r => r.style.display !== 'none')"
        ".map(r => [parseFloat(r.dataset.km), r.querySelector('.skey .dist').hidden])")
    assert kms and all(k <= 5 for k, _ in kms), kms[:5]
    assert kms == sorted(kms), "survivors are not nearest first"
    assert not any(hidden for _, hidden in kms), "a survivor's distance is not shown"
    # an outward code alone resolves to the mean of its sectors
    page.fill("#near", "SL1")
    page.wait_for_timeout(200)
    shown_out, _ = _count_text(page)
    assert shown_out > 0
    # a typed sector is the sector (Luke, 2026-09-03: it read as district SL14)
    page.fill("#near", "SL1 4")
    page.wait_for_timeout(200)
    assert "no such postcode sector" not in page.locator("#n").inner_text()
    assert _count_text(page)[0] == shown
    # on the map, the postcode frames the view: the radius, not the country
    page.click("#tab-map")
    page.wait_for_timeout(300)
    assert page.evaluate("() => map.z") >= 10, "the map stayed at the country's zoom"
    page.fill("#near", "")
    page.wait_for_timeout(300)
    assert page.evaluate("() => map.z") <= 7, "clearing the postcode did not frame the plotted set"
    page.fill("#near", "SL1 4BG")
    page.wait_for_timeout(300)
    assert page.evaluate("() => map.z") >= 10, "a postcode typed on the map did not frame it"
    page.click("#tab-sites")
    page.wait_for_timeout(200)
    # nonsense says so rather than showing nothing silently
    page.fill("#near", "ZZ99 9ZZ")
    page.wait_for_timeout(200)
    assert "no such postcode sector" in page.locator("#n").inner_text()
    page.fill("#near", "")
    page.wait_for_timeout(200)
    after, _ = _count_text(page)
    assert after == before
    assert "near:" not in page.url
    first = page.evaluate("() => document.querySelector('#tbl-sites tr.site').dataset.key")
    original = page.evaluate("() => rows[0].dataset.key")
    assert first == original, "rows were not put back in their own order"
