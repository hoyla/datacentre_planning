"""The design handoff's numbers, asserted against a rendered page.

`docs/DESIGN_CONFORMANCE.md` used to be a table saying which parts of
`design_handoff_datacentre_reader/README.md` the build honoured. It was
wrong three times in a fortnight — it said Signals was unbuilt when most
of it was built, said IBM Plex Mono was not loaded when it was named in
the stylesheet, and never noticed that no webfont had loaded at all. A
document that asserts conformance cannot detect the day conformance
stops.

So the handoff's specified values live here instead, checked against a
real build in a real browser. The failures this replaces were all of one
kind — **a rule that was written correctly and then stopped applying**:

- an `@import` several hundred rules down a stylesheet, which is only
  honoured as the first rule, so no page has ever used Source Serif;
- `.card` setting `border-top` as a shorthand below an earlier
  `.sigcard { border-top-color }`, so the signal cards drew grey;
- two different pills both called `.vpill`, so the later block won for
  both and the verification pill shrank to 11.5px;
- a dead `.sigfam` from a superseded card re-declaring the family label
  grey thirty lines under the rule that made it red.

None of those are visible by reading the CSS near where the rule is
written, and none changes any count, so `release_diff` sees nothing.
They are only visible in `getComputedStyle`.

What is asserted is the handoff's own text: colours, sizes, weights,
spacing and shape from its "Design tokens" section and the per-screen
specifications. Where a decision has overridden it, the assertion states
the override and cites who made it, so a future reader can tell a
deliberate departure from a regression.

Needs the live database (to build) and Playwright's Chromium; skips
cleanly without either.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api",
                                 reason="playwright not installed")

ROOT = Path(__file__).resolve().parent.parent
HANDOFF = ROOT / "design_handoff_datacentre_reader" / "README.md"

# The token table, verbatim.
BRAND = "rgb(5, 41, 98)"
YELLOW = "rgb(255, 229, 0)"
NEWS_RED = "rgb(199, 0, 0)"
ORANGE = "rgb(199, 70, 0)"
SLATE = "rgb(63, 85, 112)"
INK = "rgb(18, 18, 18)"
BODY = "rgb(51, 51, 51)"
SECONDARY = "rgb(107, 107, 107)"
RULE = "rgb(220, 220, 220)"
LIGHT_RULE = "rgb(236, 236, 236)"
PAGE = "rgb(246, 246, 246)"
PAPER = "rgb(255, 255, 255)"
STAMP_BLUE = "rgb(168, 186, 214)"

SERIF = "Source Serif 4"
SANS = "Source Sans 3"
MONO = "IBM Plex Mono"


@pytest.fixture(scope="module")
def page(built_reader):
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as e:
            pytest.skip(f"Chromium not available: {str(e).splitlines()[0]}")
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        pg.goto(built_reader)
        pg.wait_for_selector("#tbl-sites tr.site", state="attached")
        yield pg
        browser.close()


def css_of(page, selector: str, *props: str) -> dict:
    """Computed style of the first match, or skip if the page has none.

    Some panels only exist where the corpus has the data — a site with no
    adjudicated figure has no figure row — so a missing element is a
    reason to skip that assertion, never to fail it. A missing element
    that should always exist is asserted separately.
    """
    got = page.evaluate(
        """([sel, props]) => {
             const e = document.querySelector(sel);
             if (!e) return null;
             const g = getComputedStyle(e);
             return Object.fromEntries(props.map(p => [p, g[p]]));
           }""", [selector, list(props)])
    if got is None:
        pytest.skip(f"no {selector} in this build")
    return got


def open_a_site_with(page, marker: str) -> bool:
    """Open the first site whose panel contains `marker`.

    Searching by name picked whichever site matched the string, and that
    site might have no adjudicated figure — so the two tests needing one
    skipped on every run, and a test that always skips is not a test.
    The panels sit inside the table until a row is opened, so the right
    site can be found before opening anything.
    """
    key = page.evaluate(
        """(marker) => {
             for (const d of document.querySelectorAll('#tbl-sites tr.detail'))
               if (d.querySelector(marker))
                 return d.previousElementSibling.dataset.key;
             return null;
           }""", marker)
    if not key:
        return False
    page.evaluate("(k) => location.hash = '#site-' + k", key)
    page.wait_for_selector(f"#sitehost {marker}", state="attached")
    return True


def family_of(page, selector: str) -> str:
    """The first family in the stack, unquoted."""
    stack = css_of(page, selector, "fontFamily")["fontFamily"]
    return stack.split(",")[0].strip().strip('"\'')


# ---------------------------------------------------------------------------
# The type actually arrives
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_the_font_stylesheet_is_a_link_in_the_head(page):
    """An @import is honoured only as a stylesheet's first rule.

    The reader carried one several hundred rules down, so every browser
    dropped it and the whole page rendered in Georgia and the system
    sans while every measurement still matched the handoff. Structural,
    so this holds with no network.
    """
    state = page.evaluate("""() => {
        const links = [...document.querySelectorAll('link[rel=stylesheet]')];
        const fonts = links.filter(l => /fonts\\.googleapis\\.com/.test(l.href));
        const inline = [...document.querySelectorAll('style')]
            .map(s => s.textContent).join('\\n');
        return {inHead: fonts.filter(l => !!l.closest('head')).length,
                total: fonts.length,
                atImports: (inline.match(/^\\s*@import/gm) || []).length};}""")
    assert state["total"] >= 1, "no font stylesheet is requested at all"
    assert state["inHead"] == state["total"], "a font <link> outside <head>"
    assert state["atImports"] == 0, (
        "an @import in an inline stylesheet: it will be dropped unless it "
        "is the first rule, and it never is")


@pytest.mark.integration
def test_the_three_families_load_and_are_used(page):
    """Skipped offline; the structural test above still holds there."""
    page.wait_for_timeout(1500)
    loaded = page.evaluate(
        "() => [...new Set([...document.fonts].map(f => f.family))]")
    if not loaded:
        pytest.skip("no webfont loaded — offline, or Google Fonts unreachable")
    for family in (SERIF, SANS, MONO):
        assert family in loaded, f"{family} did not load: {loaded}"
    # And that the page asks for them where the handoff says it should:
    # headlines and figures in the serif, UI in the sans, keys in mono.
    assert family_of(page, "h1") == SERIF
    assert family_of(page, "body") == SANS
    assert family_of(page, ".sitecell .sname") == SERIF
    assert family_of(page, ".mw .fig") == SERIF


# ---------------------------------------------------------------------------
# §1 Header
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_masthead_matches_section_one(page):
    head = css_of(page, ".masthead", "backgroundColor", "paddingLeft",
                  "paddingRight")
    assert head["backgroundColor"] == BRAND
    assert head["paddingLeft"] == head["paddingRight"] == "32px"

    inner = css_of(page, ".masthead .mhead", "maxWidth")
    assert inner["maxWidth"] == "1620px"

    title = css_of(page, "h1", "fontSize", "fontWeight", "lineHeight", "color")
    assert title["fontSize"] == "28px"
    assert title["fontWeight"] == "700"
    assert title["lineHeight"] == "30.8px", "28px at 1.1"
    assert title["color"] == PAPER

    stamp = css_of(page, ".masthead .sub", "fontSize", "color")
    assert stamp["fontSize"] == "14px"
    assert stamp["color"] == STAMP_BLUE


@pytest.mark.integration
def test_tabs_match_section_one(page):
    got = page.evaluate("""() => {
        const g = e => getComputedStyle(e);
        const bs = [...document.querySelectorAll('nav.top button')];
        const on = bs.find(b => b.getAttribute('aria-selected') === 'true');
        const off = bs.find(b => b.getAttribute('aria-selected') !== 'true');
        const count = off.querySelector('span');
        return {n: bs.length,
                size: g(off).fontSize, weight: g(off).fontWeight,
                padding: g(off).padding, offOpacity: g(off).opacity,
                offBorder: g(off).borderBottomColor,
                onBorder: g(on).borderBottomWidth + ' ' + g(on).borderBottomColor,
                onOpacity: g(on).opacity,
                countOpacity: count ? g(count).opacity : null};}""")
    assert got["n"] >= 9, f"only {got['n']} tabs"
    assert got["size"] == "15px"
    assert got["weight"] == "600"
    assert got["padding"] == "9px 12px 11px"
    assert got["offOpacity"] == "0.75"
    assert got["offBorder"] == "rgba(0, 0, 0, 0)", "inactive underline must be clear"
    assert got["onBorder"] == f"4px {YELLOW}"
    assert got["onOpacity"] == "1"
    assert got["countOpacity"] == "0.6"


# ---------------------------------------------------------------------------
# §3 Signals
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_signal_card_matches_section_three(page):
    page.click("#tab-signals")
    card = css_of(page, ".sigcard", "borderTopWidth", "borderTopColor",
                  "gridTemplateColumns", "backgroundColor")
    assert card["borderTopWidth"] == "4px"
    assert card["borderTopColor"] == NEWS_RED, (
        "the signal card's rule is news red; a shorthand on .card lower "
        "in the sheet has taken this once already")
    assert card["backgroundColor"] == PAPER
    assert card["gridTemplateColumns"].endswith("300px"), card["gridTemplateColumns"]

    fam = css_of(page, ".sigfam", "color", "fontSize", "fontWeight",
                 "textTransform", "letterSpacing")
    assert fam["color"] == NEWS_RED
    assert (fam["fontSize"], fam["fontWeight"]) == ("13px", "700")
    assert fam["textTransform"] == "uppercase"
    assert fam["letterSpacing"] == "0.6px"

    pill = css_of(page, ".sigcard .vpill", "fontSize")
    assert pill["fontSize"] == "13px", (
        "the verification pill is 13px; it shared a class name with the "
        "all-figures adjudication pill once and took its 11.5px")

    head = css_of(page, ".sigheadline", "fontSize", "lineHeight", "fontWeight")
    assert head["fontSize"] == "25px"
    assert head["fontWeight"] == "700"
    assert family_of(page, ".sigheadline") in (SERIF, "Georgia")

    query = css_of(page, ".sigquery", "fontSize", "backgroundColor",
                   "borderLeftWidth", "borderLeftColor", "whiteSpace")
    assert query["fontSize"] == "13px"
    assert query["backgroundColor"] == "rgb(242, 244, 247)"
    assert query["borderLeftWidth"] == "3px"
    assert query["borderLeftColor"] == STAMP_BLUE
    assert query["whiteSpace"] == "pre-wrap"

    num = css_of(page, ".signum", "fontSize")
    assert num["fontSize"] == "42px"
    side = css_of(page, ".sigside", "borderLeftWidth", "borderLeftColor",
                  "paddingLeft")
    assert (side["borderLeftWidth"], side["borderLeftColor"]) == ("1px", RULE)
    assert side["paddingLeft"] == "22px"


@pytest.mark.integration
def test_a_withheld_cohort_states_the_refusal_and_no_count(page):
    """Editorial, not cosmetic: not-computed is not a measurement of zero.

    The card built the reason into a variable it never rendered, so the
    one cohort deliberately not computed showed "0 sites".
    """
    page.click("#tab-signals")
    got = page.evaluate("""() => [...document.querySelectorAll('.sigcard')]
        .filter(c => c.querySelector('.sigwithheld'))
        .map(c => ({head: c.querySelector('.sigheadline').innerText,
                    side: c.querySelector('.sigside').innerText}))""")
    if not got:
        pytest.skip("no cohort is withheld in this build")
    for card in got:
        assert "0" not in card["side"].split("\n")[0], (
            "a withheld cohort must not print a count")
        assert not re.match(r"^(No|Zero|None)\b", card["head"]), card["head"]
        assert len(card["side"]) > 40, "the refusal must carry its reason"


# ---------------------------------------------------------------------------
# §4 Sites
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_filter_bar_and_chips_match_section_four(page):
    page.click("#tab-sites")
    bar = css_of(page, ".controls", "padding", "borderBottomWidth",
                 "borderBottomColor", "backgroundColor")
    assert bar["padding"] == "14px 20px"
    assert (bar["borderBottomWidth"], bar["borderBottomColor"]) == ("1px", RULE)
    assert bar["backgroundColor"] == PAPER

    search = css_of(page, "#q", "fontSize", "padding", "borderTopColor",
                    "borderRadius", "width")
    assert search["fontSize"] == "15px"
    assert search["padding"] == "9px 12px"
    assert search["borderTopColor"] == "rgb(153, 153, 153)"
    assert search["borderRadius"] == "4px"
    # 230, not the handoff's 300 — the departure DESIGN_CONFORMANCE records
    # under "Shorter menu options": with the postcode box in the bar the
    # row needed 1,563 px at 300 and wrapped on a 1,440 px laptop.
    assert search["width"] == "230px"

    off = css_of(page, "#cohortchips .chip[data-cohort]", "backgroundColor",
                 "color", "borderTopColor", "fontSize", "padding",
                 "borderRadius")
    assert off["backgroundColor"] == PAPER
    assert off["color"] == BRAND
    assert off["borderTopColor"] == "rgb(199, 199, 199)"
    assert (off["fontSize"], off["padding"]) == ("13px", "6px 13px")
    assert off["borderRadius"] == "999px"

    # No chip is active until one is clicked, so the brand fill has to be
    # provoked rather than found — and then waited for. The handoff asks
    # for a 120-150ms colour transition, so a computed style read the
    # instant after the click is a colour part-way between the two.
    page.click("#cohortchips .chip[data-cohort]:not([disabled])")
    page.wait_for_timeout(250)
    on = css_of(page, "#cohortchips .chip.on", "backgroundColor", "color")
    assert on["backgroundColor"] == BRAND
    assert on["color"] == PAPER
    # Luke, 2026-08-25: the handoff's first chip, "All 456 sites", is gone
    # — once the counts answer to the filters above them it duplicated the
    # count string and was wrong whenever a filter was on. Clearing is a
    # Clear that appears only when there is something to clear.
    assert not page.locator(
        "#cohortchips .chip[data-cohort]").filter(has_text=re.compile(
            r"^All [\d,]+ sites$")).count()
    assert page.is_visible("#clearcohort")
    page.click("#clearcohort")
    assert page.is_hidden("#clearcohort")


@pytest.mark.integration
def test_the_chip_counts_answer_to_the_filters_above_them(page):
    """Luke, 2026-08-25. The help text under the chips has always said the
    count is what the chip leaves; counting against the whole corpus made
    that false the moment any other filter was on. A chip that would
    leave nothing is disabled rather than left to empty the table.
    """
    page.click("#tab-sites")
    page.evaluate("() => { setWho(''); setCohort(''); }")
    page.select_option("#f", "all")
    wide = page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll(
             '#cohortchips .chip[data-cohort]:not([data-withheld])')]
             .map(c => [c.dataset.cohort, c.querySelector('.n').textContent]))""")
    page.select_option("#f", "unknown")
    page.wait_for_timeout(150)
    narrow = page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll(
             '#cohortchips .chip[data-cohort]:not([data-withheld])')]
             .map(c => [c.dataset.cohort,
                        [c.querySelector('.n').textContent, c.disabled]]))""")
    page.select_option("#f", "all")
    assert wide and set(wide) == set(narrow)
    moved = [k for k in wide if narrow[k][0] != wide[k]]
    assert moved, f"no chip count moved when a filter was applied: {wide}"
    for k, (count, off) in narrow.items():
        n_live = int(count.strip("()").replace(",", ""))
        assert off == (n_live == 0), f"{k}: count {n_live}, disabled {off}"


@pytest.mark.integration
def test_sites_table_matches_section_four(page):
    page.click("#tab-sites")
    th = css_of(page, "#tbl-sites thead th", "fontSize", "fontWeight",
                "textTransform", "letterSpacing", "borderBottomColor",
                "borderBottomWidth", "color")
    assert (th["fontSize"], th["fontWeight"]) == ("12px", "700")
    assert th["textTransform"] == "uppercase"
    assert th["letterSpacing"] == "0.6px"
    assert (th["borderBottomWidth"], th["borderBottomColor"]) == ("1px", INK)
    assert th["color"] == SECONDARY

    td = css_of(page, "#tbl-sites tr.site td", "padding", "borderBottomColor",
                "verticalAlign")
    assert td["padding"] == "16px 20px"
    assert td["borderBottomColor"] == RULE
    assert td["verticalAlign"] == "top"

    name = css_of(page, ".sitecell .sname", "fontSize", "fontWeight", "color")
    assert (name["fontSize"], name["fontWeight"]) == ("18px", "700")
    assert name["color"] == BRAND
    assert css_of(page, ".sitecell .skey", "fontSize", "color") == {
        "fontSize": "13px", "color": SECONDARY}

    mw = css_of(page, ".mw .fig", "fontSize")
    assert mw["fontSize"] == "21px"

    bar = css_of(page, ".rbar", "height", "backgroundColor")
    assert bar["height"] == "6px"
    assert bar["backgroundColor"] == RULE


@pytest.mark.integration
def test_the_signal_pills_carry_the_handoff_tones(page):
    """Red, amber or slate — the tone is the cohort's, not the page's.

    They were one neutral grey for a while, on a rule invented here; the
    handoff assigns a tone to every signal and `dcp/site_cohorts.py` now
    carries it.
    """
    page.click("#tab-sites")
    tones = page.evaluate("""() => [...document.querySelectorAll('.sigcell .sigpill')]
        .map(p => getComputedStyle(p).backgroundColor)
        .filter((v, i, a) => a.indexOf(v) === i)""")
    allowed = {"rgb(253, 236, 236)", "rgb(253, 240, 230)", "rgb(238, 241, 246)"}
    assert tones, "no signal pill rendered in the table"
    assert set(tones) <= allowed, f"off-palette signal pill: {tones}"


@pytest.mark.integration
def test_a_row_chip_is_the_same_object_as_a_filter_chip(page):
    """Luke, 2026-08-25: same font, same size, same shape; colour only
    differs, because a chip above the table also shows what is on."""
    page.click("#tab-sites")
    chip = css_of(page, "#cohortchips .chip", "fontSize", "padding",
                  "borderRadius")
    for row_chip in (".sigcell .sigpill", "button.who"):
        got = css_of(page, row_chip, "fontSize", "padding", "borderRadius")
        assert got == chip, f"{row_chip} is not the chip above the table: {got}"


# ---------------------------------------------------------------------------
# §5 Site page
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_site_page_matches_section_five(page):
    page.click("#tab-sites")
    page.click("#tbl-sites tr.site")
    head = css_of(page, "#sitehost .sitehead", "borderTopWidth",
                  "borderTopColor", "padding")
    assert head["borderTopWidth"] == "4px"
    assert head["borderTopColor"] == BRAND
    assert head["padding"] == "22px 26px 24px"
    assert css_of(page, "#sitehost .sitename", "fontSize")["fontSize"] == "32px"
    assert css_of(page, "#sitehost .sitebody",
                  "gridTemplateColumns")["gridTemplateColumns"].count("px") >= 2

    banner = page.evaluate("""() => {const b=document.querySelector('#sitehost .banner');
        if(!b) return null; const g=getComputedStyle(b);
        return {bg:g.backgroundColor, w:g.borderLeftWidth, c:g.borderLeftColor};}""")
    if banner:
        assert banner["bg"] == "rgb(253, 246, 227)", "the caveat banner is #fdf6e3"
        assert banner["w"] == "4px"
        assert banner["c"] == ORANGE
    page.click("#view-site .sitenav a")


@pytest.mark.integration
def test_an_adjudicated_figure_carries_its_quote(page):
    """§5, and editorial rule 2: every number walks back to a document."""
    page.click("#tab-sites")
    if not open_a_site_with(page, ".figrow"):
        pytest.skip("no site in this build has an adjudicated figure")
    row = page.evaluate("""() => {
        const f = document.querySelector('#sitehost .figrow');
        const g = e => e ? getComputedStyle(e) : null;
        const q = f.querySelector('.figquote');
        return {grid: g(f).gridTemplateColumns,
                value: g(f.querySelector('.figval')).fontSize,
                told: !!f.querySelector('.figtold'),
                quote: q ? {style: g(q).fontStyle, size: g(q).fontSize,
                            rule: g(q).borderLeftWidth} : null};}""")
    page.click("#view-site .sitenav a")
    assert row["grid"].startswith("132px"), row["grid"]
    assert row["value"] == "23px"
    assert row["told"], "a figure must say who it was told to"
    if row["quote"]:
        assert row["quote"]["style"] == "italic"
        assert row["quote"]["size"] == "15px"
        assert row["quote"]["rule"] == "3px"


@pytest.mark.integration
def test_every_figure_found_is_reachable(page):
    """Editorial rule 4: highlights never replace data, and an excluded
    row is shown with its reason rather than deleted."""
    page.click("#tab-sites")
    if not open_a_site_with(page, ".allfigs"):
        pytest.skip("no site in this build has an all-figures table")
    got = page.evaluate("""() => {
        const d = document.querySelector('#sitehost .allfigs');
        d.open = true;
        const heads = [...d.querySelectorAll('th')].map(h => h.innerText.trim());
        return {heads, rows: d.querySelectorAll('tbody tr').length,
                verdicts: [...d.querySelectorAll('.adjpill')].length,
                note: d.querySelector('.help').innerText};}""")
    page.click("#view-site .sitenav a")
    assert [h.lower() for h in got["heads"]] == [
        "value", "unit", "quantity as written", "document",
        "locator", "read by", "adjudication"], got["heads"]
    assert got["rows"] >= 1 and got["verdicts"] == got["rows"], (
        "every row carries the adjudicator's verdict")
    assert "kept, not deleted" in got["note"]


# ---------------------------------------------------------------------------
# §6 The package
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_package_cards_match_section_six(page):
    page.click("#tab-start")
    grid = css_of(page, ".parts", "gap", "gridTemplateColumns")
    assert grid["gap"] == "18px"
    assert len(grid["gridTemplateColumns"].split()) >= 2, "auto-fill, not one column"

    card = css_of(page, ".part", "backgroundColor", "borderTopWidth",
                  "borderTopColor", "borderRadius", "padding")
    assert card["backgroundColor"] == PAPER
    assert (card["borderTopWidth"], card["borderTopColor"]) == ("4px", BRAND)
    assert card["borderRadius"] == "0px"
    assert card["padding"] == "18px 20px 20px"

    kind = css_of(page, ".part .kind", "fontSize", "fontWeight",
                  "textTransform", "color")
    assert (kind["fontSize"], kind["fontWeight"]) == ("13px", "600")
    assert kind["textTransform"] == "uppercase"
    assert kind["color"] == SECONDARY
    assert css_of(page, ".part h3", "fontSize")["fontSize"] == "21px"

    missing = page.evaluate(
        "() => [...document.querySelectorAll('.part')]"
        ".filter(p => !p.querySelector('.kind')).length")
    assert missing == 0, f"{missing} package cards have no kind label"


# ---------------------------------------------------------------------------
# Tokens that apply everywhere
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_no_shadows_anywhere(page):
    """Tokens: "square cards … no shadows anywhere".

    Inset shadows are excluded: they draw the open row's left edge, which
    is a border the table cannot otherwise paint. A zero-blur ring is a
    second border on a circle over map tiles, not elevation.
    """
    offenders = page.evaluate("""() => {
        const css = [...document.querySelectorAll('style')]
            .map(s => s.textContent).join('\\n');
        return (css.match(/box-shadow:[^;}]+/g) || [])
            .map(d => d.trim())
            .filter(d => !/inset/.test(d))
            .filter(d => !/^box-shadow:\\s*0\\s*0\\s*0\\s*1px/.test(d))
            .filter(d => !/none/.test(d));}""")
    assert offenders == [], f"drop shadows remain: {offenders}"


@pytest.mark.integration
def test_the_page_is_the_grey_and_the_panels_are_the_paper(page):
    assert css_of(page, "body", "backgroundColor")["backgroundColor"] == PAGE
    assert css_of(page, "#tbl-sites", "backgroundColor")["backgroundColor"] == PAPER
    assert css_of(page, ".card", "backgroundColor")["backgroundColor"] == PAPER


@pytest.mark.integration
def test_links_darken_on_hover_over_a_short_transition(page):
    """Interactions: hover darkens to #234b8a; transitions 120–150ms,
    colour and border only — no scale, no bounce."""
    got = css_of(page, ".tablenote", "color")  # any element, to force a query
    assert got  # keeps the fixture honest if the selector ever disappears
    rules = page.evaluate("""() => {
        const css = [...document.querySelectorAll('style')]
            .map(s => s.textContent).join('\\n');
        const hover = /a:hover\\s*\\{([^}]*)\\}/.exec(css);
        const durations = (css.match(/transition:[^;}]+/g) || [])
            .map(d => d.match(/([\\d.]+)s/g) || []).flat()
            .map(v => Math.round(parseFloat(v) * 1000));
        const transforms = (css.match(/transition:[^;}]*transform[^;}]*/g) || [])
            .filter(d => !/\\.tri|triangle|rotate/.test(d));
        return {hover: hover ? hover[1] : "", durations, transforms};}""")
    assert "#234b8a" in rules["hover"], rules["hover"]
    slow = [d for d in rules["durations"] if d > 400]
    assert not slow, f"transitions longer than the handoff's range: {slow}ms"


@pytest.mark.integration
def test_the_pill_sets_are_the_four_in_the_token_table(page):
    """Green / red / amber / slate, each a background, a text colour and
    a border. A tentative external claim is slate, because a lead to
    resolve must not wear the colour of a check that was made.
    """
    page.click("#tab-sites")
    sets = page.evaluate("""() => {
        const out = {};
        for (const cls of ['known', 'unknown', 'tentative']) {
            const e = document.querySelector('.tag.' + cls);
            if (!e) continue;
            const g = getComputedStyle(e);
            out[cls] = [g.backgroundColor, g.color, g.borderTopColor,
                        g.borderRadius];
        }
        return out;}""")
    expected = {
        "known": ["rgb(233, 243, 236)", "rgb(29, 107, 56)",
                  "rgb(199, 224, 208)", "999px"],
        "unknown": ["rgb(253, 240, 230)", "rgb(161, 58, 0)",
                    "rgb(242, 214, 189)", "999px"],
        "tentative": ["rgb(238, 241, 246)", SLATE,
                      "rgb(214, 221, 232)", "999px"],
    }
    assert sets, "no status pill rendered"
    for cls, values in sets.items():
        assert values == expected[cls], f".tag.{cls} is {values}"


@pytest.mark.integration
def test_the_handoff_is_still_in_the_repo():
    """These numbers are transcribed from it; if it goes, so does the
    only record of where they came from."""
    assert HANDOFF.exists(), f"{HANDOFF} is missing"
    text = HANDOFF.read_text()
    for token in ("#052962", "#ffe500", "#c70000", "#c74600", "#3f5570",
                  "No shadows anywhere"):
        assert token in text, f"{token} is no longer in the handoff"
