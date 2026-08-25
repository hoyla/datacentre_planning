#!/usr/bin/env python3
"""Build the handover's front door, and the data behind it.

A handover is not one artefact, it is five — a workbook, a queryable
database, a Drive folder of source documents, a methodology note and this
reader — and a reporter handed five things with no map opens whichever
arrived last. So the landing view explains what the package contains and
when to reach for each part; the data sits behind it.

The reader and the workbook are two views of the same rows. The
difference is shape, not content: a spreadsheet is for filtering and
pivoting, this is for reading one site and following it outward — to its
applications, to their council registers, to the documents on Drive, to
the energy project next door.

Three rules drive the layout.

**A figure never appears without its qualification.** Every power number
carries its basis. A site whose documents have not been read is visually
distinct from one whose documents were read and disclosed nothing.

**Values from a partial reading are floors, not measurements.** The
largest capacity in the documents read so far is the largest we know of;
reading the rest can raise it and cannot lower it. A campus promoted as
1GW showing 500MW here is not a contradiction — it is the biggest figure
in the fraction of its documents that has been analysed. Those rows say
so, on the figure itself.

**Every claim is walkable.** Site → application → council register →
document on Drive. A number a reporter cannot trace is a number they
cannot publish.

Self-contained: no CDN, no network at runtime, opens from a file:// URL
or a shared drive.

    scripts/export_reader.py --out data/exports/phase1_build/reader.html
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import adjudication_gate  # noqa: E402
from dcp import release  # noqa: E402
from dcp import db  # noqa: E402
from dcp import deepread_select  # noqa: E402

from dcp.drive import FOLDER_URL as DRIVE_ROOT  # noqa: E402
from dcp.drive import WORKBOOK_SHEET_URL  # noqa: E402
from dcp.drive import SITES_URL  # noqa: E402
from dcp.drive import NOTEBOOK_URL  # noqa: E402
from dcp.drive import PINPOINT_URL  # noqa: E402

# Statuses meaning "we have not looked yet", as against "they disclosed
# nothing" — the distinction the page is built around.
NOT_YET_KNOWN = ("not_yet_analysed", "partially_analysed", "no_documents",
                 "pre_application")

# Findings shown per site before the list is summarised: enough to
# characterise the evidence, not so many that the page becomes the corpus.
# Raised from 14 for the site page (READER_REDESIGN_PLAN §7a), which
# groups them by family: fourteen spread over ten families showed one
# passage per family and nothing to group. The round-robin in
# FINDINGS_SQL means the extra rows are the second and third of each
# family, never the fifteenth of one; a site with fifteen families gets
# two of each and a third of the ten it has most of. Measured: 8.8 MB
# at 14, 10.2 MB at 30, 10.9 MB at 40.
FINDINGS_PER_SITE = 40

# Per-site, per-family counts of distinct passages, so the grouped list
# can say "3 of 41" rather than leave a reader guessing how much of the
# family they are seeing. Distinct passages, for the reason
# export_handover's app_findings gives: three readers of one sentence
# are corroboration, not three findings.
FAMILY_COUNTS_SQL = """
SELECT s.site_key, f.signal_family,
       count(DISTINCT (f.document_id, md5(f.evidence_text), f.evidence_page))
FROM findings f
JOIN site_members m ON m.application_id = f.application_id AND m.retired_at IS NULL
JOIN sites s ON s.id = m.site_id
WHERE s.retired_at IS NULL AND f.value_text IS NOT NULL
  AND f.signal_family IS NOT NULL AND f.signal_family <> 'unclassified'
GROUP BY s.site_key, f.signal_family
"""

# How many sites an organisation must be behind before it gets a chip.
# Two, so the strip is the organisations with more than one site in the
# dataset — which is what a filter on the strip is for. An organisation
# behind one site is still on that site's row, still searchable, and
# still filterable by clicking its badge; it simply does not need a
# permanent control of its own.
WHO_CHIP_FLOOR = 2

# Hoisted out of the builder so a test can run it twice against one
# database snapshot and compare. Every ordering in it is total —
# `f.id` in the window, `id DESC` in the CTE, `site_key, rn` on the
# outer select — because without those three the same database
# produced a different artefact on each build: 2,503 of 10,425 rows
# in a different position and 80 in a different *set*, across 69
# sites, measured 2026-08-22. Diffing a build against the last
# release is how regressions are caught here, so a build that is
# not a function of its inputs disables the check.
FINDINGS_SQL = """
            WITH adj AS (
              SELECT DISTINCT ON (finding_id) finding_id, verdict
              FROM power_adjudication
              ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC,
                       id DESC),
            ranked AS (
              -- Within each family, the figures the adjudication attributed
              -- to this site come first; then the fullest text; then id.
              SELECT s.site_key, f.signal_type, f.value_text, f.value_number,
                     f.value_unit, adj.verdict, f.signal_family, f.id,
                     row_number() OVER (PARTITION BY s.site_key, f.signal_family
                       ORDER BY coalesce(adj.verdict = 'site_capacity', false) DESC,
                                length(coalesce(f.value_text,'')) DESC,
                                f.id) AS rf
              FROM findings f
              JOIN site_members m ON m.application_id=f.application_id AND m.retired_at IS NULL
              JOIN sites s ON s.id=m.site_id
              LEFT JOIN adj ON adj.finding_id = f.id
              WHERE s.retired_at IS NULL AND f.value_text IS NOT NULL
                AND f.signal_family <> 'unclassified')
            SELECT site_key, signal_type, value_text, value_number, value_unit,
                   verdict, signal_family, id FROM (
              -- Round-robin across families: the first of every family
              -- before the second of any. Each round leads with figures
              -- adjudicated as this site's, then the power families, then
              -- cooling, water and EIA, then the rest. Ranking by text
              -- length alone put a landscape paragraph labelled it_load at
              -- the top of a site's evidence, four times over.
              SELECT f.site_key, f.signal_type, f.value_text, f.value_number,
                     f.value_unit, f.verdict, f.signal_family, f.id,
                     row_number() OVER (PARTITION BY f.site_key
                       ORDER BY f.rf,
                                coalesce(f.verdict = 'site_capacity', false) DESC,
                                CASE f.signal_family
                                  WHEN 'power_demand' THEN 1 WHEN 'power_generation' THEN 2
                                  WHEN 'power_grid' THEN 3 WHEN 'cooling' THEN 4
                                  WHEN 'water' THEN 5 WHEN 'eia_process' THEN 6
                                  ELSE 7 END,
                                f.signal_family, f.id) AS rn
              FROM ranked f) t
            WHERE rn <= %s
            ORDER BY site_key, rn"""


def _handover():
    spec = importlib.util.spec_from_file_location(
        "export_handover", Path(__file__).parent / "export_handover.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ONES = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety")


# Words this project spells in capitals. CSS `text-transform:capitalize`
# has no idea that EIA is an initialism and rendered the findings family
# `eia_process` as "Eia Process" (Luke, 2026-08-25). The list is short
# on purpose: only what actually appears in a family or a signal label.
_ACRONYMS = {"eia": "EIA", "pue": "PUE", "wue": "WUE", "chp": "CHP",
             "hgv": "HGV", "ev": "EV", "suds": "SuDS", "bng": "BNG",
             "sssi": "SSSI", "sac": "SAC", "spa": "SPA", "aonb": "AONB",
             "ups": "UPS", "hv": "HV", "lv": "LV", "mw": "MW", "uk": "UK"}


def humanise(token: str) -> str:
    """A snake_case key as a label, with initialisms left as initialisms."""
    words = (token or "").replace("_", " ").split()
    return " ".join(_ACRONYMS.get(w.lower(), w.capitalize()) for w in words)


def mw_text(v: float) -> str:
    """A megawatt figure as a reader should see it.

    Rounding to whole megawatts turned Plymouth's 0.2 MW standby set into
    "0 Standby generation capacity" — a figure that says the opposite of
    what the document says (Luke, 2026-08-25). Small figures are real
    here: a hospital's standby engine, a rooftop array, one generator's
    rating. Below 10 MW the figure keeps up to two decimals, trailing
    zeros trimmed so 3.00 does not appear where the documents say 3; at
    and above 10 the decimals are noise against the uncertainty in the
    number itself.
    """
    if v is None:
        return ""
    if abs(v) < 10:
        out = f"{v:.2f}"
    elif abs(v) < 1000:
        # One decimal survives here because it carries meaning: 49.9 MW
        # is the consenting threshold this corpus is full of, and a
        # reader shown "50" has been told the opposite of what the
        # application says. 218.4 is likewise a stated figure, not a
        # rounding of 218.
        out = f"{v:.1f}"
    else:
        return f"{v:,.0f}"
    return out.rstrip("0").rstrip(".")


def _count_in_words(n: int) -> str:
    """"Twenty-two sites", for the Signals headline.

    The handoff asks the headline to state the count in words and the
    property — words because a numeral in a headline reads as a
    measurement of something, and this number is a count of rows a rule
    selected. Above 999 it stays a numeral: "one thousand and forty-one
    sites" is not a sentence anybody wants to read.
    """
    if n < 0 or n > 999:
        return f"{n:,} sites"
    if n < 20:
        word = _ONES[n]
    elif n < 100:
        word = _TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else "")
    else:
        rest = n % 100
        word = _ONES[n // 100] + " hundred" + (
            f" and {_count_in_words(rest).removesuffix(' sites').removesuffix(' site')}"
            if rest else "")
    return f"{word.capitalize()} site" + ("" if n == 1 else "s")


def esc(v) -> str:
    """Escape a value for HTML.

    Never pass an HTML entity through this: `html.escape` turns `&mdash;`
    into `&amp;mdash;`, which renders as literal text. Use the real
    character (—); the page is UTF-8 and `html.escape` leaves non-ASCII
    alone.

    Unescaping first handles the other direction. A handful of source
    records reached us with the portal's own escaping still in them — one
    PINS project is literally named "… &amp; Power Station" — and escaping
    those a second time puts `&amp;amp;` on the page. Unescape-then-escape
    is idempotent for ordinary text and repairs the pre-escaped few. The
    stored value is untouched; this is a rendering decision, not a
    correction to the record.
    """
    return html.escape(html.unescape("" if v is None else str(v)))


# `Diesel (147 mentions), HVO (39)` — the brackets on a ranked label count
# passages in the documents, and the panel they sit on also carries counts
# of plant. site_profile names the unit on the first bracket; this greys
# every bracket on the line so the eye reads them as one kind of number
# before it reads any of them as a quantity of equipment.
_MENTION_COUNT_RE = re.compile(r"\((\d[\d,]*(?: [a-z]+)?)\)")


def counted(v) -> str:
    """Escape a ranked label, subduing its bracketed mention counts."""
    if not v:
        return "—"
    return _MENTION_COUNT_RE.sub(r'<span class="mcount">(\1)</span>', esc(v))


def trim(text, n: int) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


# Glyphs are written as characters, not CSS escapes. `content:"\25B8"`
# in a Python string is an octal escape first and a CSS one never: it
# reached the page as chr(0x15) + "B8", so the disclosure arrow read
# "B8Show the 45 planning applications". The same trap as HTML
# entities in esc() — write the character.
CSS = """
/* Colour means one thing here: the state of the evidence.
   READER_REDESIGN_PLAN §8b — "one neutral colour for cohort and
   organisation pills, colour reserved for verification state".
   So --brand is structure (masthead, headings, site names, links) and
   also the SETTLED state, --warn is attention (a floor, a provisional
   row, something withheld), --active is the reader's own filter, and
   everything categorical — cohorts, organisations — is neutral. The
   values are the Guardian's, which Luke asked for where they do not
   undermine that rule; what they are NOT used for is section identity,
   because red marking a section and red marking an unverified figure
   cannot both be read. */
:root{--bg:#fff;--fg:#121212;--body:#333;--mut:#6b6b6b;--line:#dcdcdc;
  --line-lt:#ececec;--page:#f6f6f6;--soft:#f6f6f6;
  --brand:#052962;--accent:#052962;--active:#ffe500;
  --warn:#c74600;--warnbg:#fdf0e6;--ok:#1d6b38;--okbg:#e9f3ec;
  /* The design brief's slate, for machine-generated content. It earns a
     colour of its own under the same rule as the rest: what a model
     wrote is a different KIND of thing from what a document says, and
     that difference is exactly what a reader has to keep hold of. */
  --machine:#3f5570;--machinebg:#eef1f6;--machineline:#d6dde8}

/* No dark scheme. Luke asked for the brief's white page, and the brief
   has none — but the reason to drop it rather than tune it is that
   colour here carries meaning: settled, attention, the reader's own
   filter, machine-written. A second palette is a second set of those
   four to keep true, and the one that was here had already drifted
   (brand went to a pale blue, which is the colour of nothing in
   particular). One palette, verified once. */
/* Disclosure triangles, the way meridian/report_render_html.py draws
   them: CSS borders on a zero-size box, not a glyph. Its comment has the
   reason — a glyph "renders sub-cap-height and looks like a stray dot",
   which is what Luke saw here, and a zero-size box means the triangle
   never grows the line it sits on. Slightly larger than Meridian's 5/8
   because this page's body is 16px against its 12px. currentColor, so
   each one takes the colour of the thing it opens. */
.tri:before,table.stats tr.op td:first-child:before,
details.reading summary h4:before,details.banner-d>summary:before,
.box.claims details>summary:before,details.apps-d>summary:before,
.opdetail details>summary:before,.opsite details>summary:before,
tr.site td:first-child:before{
  content:"";display:inline-block;width:0;height:0;margin-right:8px;
  border-top:6px solid transparent;border-bottom:6px solid transparent;
  border-left:9px solid currentColor;vertical-align:middle;position:relative;
  bottom:1px;transition:transform .12s}
details[open].reading summary h4:before,details.banner-d[open]>summary:before,
.box.claims details[open]>summary:before,details.apps-d[open]>summary:before,
.opdetail details[open]>summary:before,.opsite details[open]>summary:before,
tr.site.open td:first-child:before,
table.stats tr.op.open td:first-child:before{transform:rotate(90deg)}
*{box-sizing:border-box}
/* [hidden] is display:none only by UA default, and any rule setting
   display on the same element wins. That has now hidden nothing twice —
   the map's cohort key, which sat in the legend whether or not a cohort
   was marked, and the organisation filter bar, which announced a filter
   nobody had applied. Both were caught by a browser test rather than by
   reading. Stated once, at the top, for every [hidden] on the page. */
[hidden]{display:none !important}
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&family=IBM+Plex+Mono:wght@400;600&display=swap');
body{margin:0;font:16px/1.62 "Source Sans 3",-apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--fg)}
/* The serif carries what a reader is looking FOR — a site's name and a
   figure — and nothing else. The handoff uses it the same way. */
.sitecell .sname,.mw .fig,h1,h2{font-family:"Source Serif 4",Georgia,
  "Times New Roman",serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
/* The masthead, from the design proposal: one full-bleed band carrying
   the title, the release stamp and the tabs, where there were three
   stacked strips in two colours. It is about a third of the height and
   says more — the stamp gains the findings count — and it puts the
   product's name and what the reader is looking at in one glance.
   The tab row stays sticky; the title scrolls away with the page. */
header.masthead{background:var(--brand);color:#fff;padding:14px 32px 0}
header.masthead .mhead{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
  max-width:1620px;margin:0 auto}
header.masthead h1{margin:0;font-size:28px;line-height:1.1;font-weight:700;
  font-family:"Source Serif 4",Georgia,serif;color:#fff}
header.masthead .sub{color:#a8bad6;font-size:14px;line-height:1.4}
nav.top{display:flex;gap:2px;padding:0 32px;background:var(--brand);
  position:sticky;top:0;z-index:9;overflow-x:auto;max-width:none}
nav.top .navinner{display:flex;gap:2px;max-width:1620px;margin:0 auto;width:100%}
nav.top button{font:inherit;font-size:15px;font-weight:600;padding:9px 12px 11px;
  border:0;background:none;color:#fff;cursor:pointer;opacity:.75;
  border-bottom:4px solid transparent;white-space:nowrap}
nav.top button:hover{opacity:1}
nav.top button[aria-selected=true]{opacity:1;border-bottom-color:var(--active)}
/* The count belongs to the tab, so it is the same word at a lower
   volume rather than a badge of its own. */
nav.top button .pill{background:none;color:inherit;opacity:.6;padding:0 0 0 5px;
  border-radius:0;font-size:inherit}
.view{display:none}.view.on{display:block}
/* 920px is a measure for prose, and the methodology, dictionary and
   notes tabs keep it. Start here and Signals are layouts, not prose:
   the brief gives them 32px page padding and a content column beside a
   380px sidebar, and inside 920px that column came out 492px — near
   enough the same width as the sidebar, which is what Luke saw. The
   masthead's 1620px is the page's width; these use it. */
.wrap{max-width:920px;padding:24px 22px 10px}
.wrap.wide{max-width:1620px;padding:24px 32px 10px;margin:0 auto}
.lede{font-family:"Source Serif 4",Georgia,serif;font-size:20px;line-height:1.45;
  max-width:46em}
.parts{display:grid;gap:11px;margin:20px 0}
.part{border:1px solid var(--line);border-radius:7px;padding:13px 15px;background:var(--soft)}
.part h3{margin:0 0 3px;font-size:16.5px}
.part .what{color:var(--mut);font-size:14.5px;margin:0 0 6px}
.part .when{font-size:14px;margin:0}
.pill{display:inline-block;font-size:13px;padding:1px 8px;border-radius:9px;
  background:rgba(127,127,127,.15);color:var(--mut);margin-left:6px;vertical-align:1px}
.stat{display:flex;gap:24px;flex-wrap:wrap;margin:16px 0 4px;padding:13px 15px;
  border:1px solid var(--line);border-radius:7px}
/* Selectors reach the children of any tile, not just the div ones. The
   three clickable tiles are buttons, so a `.stat div span` rule skipped
   them entirely: they inherited the button's 14px and lost the block
   display, rendering as a tiny run-together "455sites" beside the
   full-size figures. */
.stat span{display:block;font-size:21px;font-weight:650;font-variant-numeric:tabular-nums}
.stat small{display:block;color:var(--mut);font-size:13.5px}
.banner{margin:16px 0;padding:12px 14px;border-left:3px solid var(--warn);
  background:var(--warnbg);color:var(--warn);border-radius:0 5px 5px 0;font-size:14.5px}
/* The coverage caveats only need reading once, but the panel sat between the
   stat tiles and the charts on every visit — so it folds shut by default. */
details.banner-d>summary{cursor:pointer;font-weight:650;list-style:none;
  display:inline-block;padding:0}
details.banner-d>summary::-webkit-details-marker{display:none}
details.banner-d>summary:hover{text-decoration:underline}
details.banner-d>div{margin-top:9px}
h2.sec{font-size:15px;margin:24px 0 8px}
.controls{display:flex;gap:9px;flex-wrap:wrap;padding:11px 22px;align-items:center;
  border-bottom:1px solid var(--line);position:sticky;top:var(--nav-h,41px);
  background:var(--bg);z-index:8}
input,select{font:inherit;padding:6px 9px;border:1px solid var(--line);border-radius:5px;
  background:var(--bg);color:var(--fg)}
input[type=search]{min-width:250px}
.count{color:var(--mut);font-size:14px;margin-left:auto}
button.toggle{font:inherit;font-size:14.5px;padding:6px 12px;border:1px solid var(--line);
  border-radius:5px;background:var(--bg);color:var(--fg);cursor:pointer}
button.toggle:hover{border-color:var(--accent)}
button.toggle[aria-pressed=true]{background:var(--accent);border-color:var(--accent);
  color:#fff;font-weight:600}
label.chk{font-size:14px;display:flex;align-items:center;gap:5px;cursor:pointer}
label.chk.off{opacity:.45;cursor:default}
/* The organisation chips. Square rather than the prototype's pills, and
   one neutral colour rather than a palette: colour on this page means
   verification state (.tag.known, .tag.unknown), and a coloured pill for
   an organisation would read as a judgement about it. The strip sits
   under the filter bar rather than inside it, because it is a long line
   that wraps and the filter bar is sticky. */
.chips{display:flex;gap:7px;flex-wrap:wrap;align-items:baseline;
  padding:9px 22px;border-bottom:1px solid var(--line)}
.chiplabel{font-size:14px;font-weight:600;color:var(--mut);
  margin-right:3px}
.chips .help{font-size:13.5px;flex-basis:100%;margin:3px 0 0}
button.chip{font:inherit;font-size:14px;padding:4px 10px;
  border:1px solid var(--line);border-radius:3px;background:var(--bg);
  color:var(--fg);cursor:pointer;line-height:1.3}
button.chip:hover{border-color:var(--accent)}
/* The reader's own filter, in the Guardian's yellow: it marks what the
   PERSON has done to the page, which is a third thing from structure
   (brand) and from the state of a figure (warn). Black text on it
   because the yellow is bright enough to carry it and nothing else on
   the page is that colour. */
button.chip.on{background:var(--active);border-color:var(--active);color:#121212;
  font-weight:600}
button.chip .n{color:var(--mut);font-size:13px;margin-left:3px}
button.chip:disabled{opacity:.5;cursor:not-allowed;border-style:dashed}
/* The machine reading: a collapsed box, one neutral rule, no colour —
   colour on this page means verification state and this is not one.
   The summary carries the whole label so that what it is is read
   before what it says. */
details.reading{border:1px solid var(--line);border-radius:3px;padding:10px 13px;
  margin:14px 0 4px}
details.reading summary{cursor:pointer;list-style:none}
details.reading summary::-webkit-details-marker{display:none}
details.reading summary h4{display:inline;margin:0 8px 0 0;font-size:13px;
  text-transform:uppercase;letter-spacing:.5px;color:var(--mut)}
details.reading summary .help{display:inline}
.rbody{margin-top:10px;max-width:880px}
.rbody h5{margin:12px 0 4px;font-size:13.5px;text-transform:uppercase;
  letter-spacing:.5px;color:var(--mut)}
.rbody p{margin:0 0 4px;font-size:15px;line-height:1.5}
ul.rq{margin:0 0 10px;padding-left:18px;font-size:13.5px;color:var(--mut)}
ul.rq li{margin-bottom:2px}
.box.reading{border-top-color:var(--machineline);background:var(--machinebg);
  padding-left:14px;padding-right:14px}
.box.reading h4{color:var(--machine)}
.box.reading .rbody{color:var(--body)}
.box.reading.withheld{margin:14px 0 4px;border-radius:0}
.rwithheld{font-style:italic;color:var(--warn)}
/* The site page. Full width like the table it came from, since the
   panel's four-column grid was laid out for that width. */
.sitepage{padding:14px 22px 30px}
.sitenav{margin:0 0 10px;font-size:14.5px}
.sitepage h2{margin:4px 0 2px;font-size:22px;line-height:1.2}
.sitewhere{margin:0 0 14px;color:var(--mut);font-size:14.5px}
#sitehost .grid{margin-top:0}
/* Signals cards. Square, ruled, no shadow; the count is the one large
   thing on the card because it is the one thing that was computed. */
/* §3 of the design handoff. One card per signal: 4px news red rule,
   the main column and a 300px column carrying the count and what
   cannot enter the cohort. Red belongs to signals here; caution is the
   orange elsewhere, and the two are different jobs. */
.signals{display:block;margin-top:14px}
.sigexplain{max-width:62em}
.sigcard{border-top-color:#c70000;display:grid;
  grid-template-columns:minmax(0,1fr) 300px;gap:36px;margin-bottom:16px}
@media (max-width:900px){.sigcard{grid-template-columns:1fr;gap:20px}}
.sigtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.sigfam{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  color:#c70000}
.sigrule{font-size:13px;color:var(--mut)}
/* Verification, as a pill: green where a person has checked a
   membership, amber where the rule alone selected it. */
.vpill{font-size:13px;padding:2px 10px;border-radius:999px;border:1px solid}
.vpill-hand{background:#e9f3ec;color:#1d6b38;border-color:#c7e0d0}
.vpill-machine{background:#fdf0e6;color:#a13a00;border-color:#f2d6bd}
.sigheadline{margin:0 0 10px;font-size:25px;line-height:1.18;font-weight:700;
  font-family:"Source Serif 4",Georgia,serif;max-width:30em}
.sigprose{margin:0 0 12px;font-size:15px;line-height:1.5;color:var(--body)}
/* The rule itself, not a description of it. */
.sigquery{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:13px;line-height:1.55;color:#22303f;background:#f2f4f7;
  border-left:3px solid #a8bad6;padding:10px 12px;white-space:pre-wrap;margin:0 0 12px}
.siglimits{margin:0 0 12px;font-size:14px;line-height:1.5}
.sigside{border-left:1px solid var(--line);padding-left:22px}
@media (max-width:900px){.sigside{border-left:0;border-top:1px solid var(--line);
  padding-left:0;padding-top:14px}}
.signum{font-family:"Source Serif 4",Georgia,serif;font-size:42px;line-height:1.05;
  font-weight:700}
.sigunit{font-size:13px;color:var(--mut);margin-bottom:10px}
.sigfloor{margin:0 0 8px;padding-top:10px;border-top:1px solid var(--line-lt);
  font-size:13px;line-height:1.5;color:var(--mut)}
.sigsrc{font-size:13px;color:var(--mut);background:#f2f2f2;padding:1px 5px}
.sigactions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0 0}
.box.signal{border-radius:3px;padding:14px 16px}
.box.signal h3{margin:4px 0 8px;font-size:21px}
.sighead{display:flex;justify-content:space-between;align-items:baseline}
.sigfam{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  color:var(--mut)}
.sigcount{font-size:30px;font-weight:700;line-height:1.1;margin:2px 0 8px}
.sigcount.withheld{font-size:21px;color:var(--mut)}
.sigchecks{font-size:14px}
.sigdef dt{color:var(--mut)}
.sigdef code{font-size:13.5px;white-space:normal}
.sigactions{font-size:14.5px;margin:8px 0 4px}
.siglist{margin:6px 0 0;padding-left:18px;font-size:14px;columns:2;column-gap:24px}
.siglist li{break-inside:avoid;margin-bottom:3px}
@media (max-width:700px){.siglist{columns:1}}
button.chip.on .n{color:#121212;opacity:.7}
/* The badge in the table cell is the same control in a smaller frame:
   it filters, so it looks pressable, but it must not out-shout the site
   name beside it. */
button.who{font:inherit;font-size:14px;padding:2px 7px;text-align:left;
  border:1px solid var(--line);border-radius:3px;background:var(--bg);
  color:var(--fg);cursor:pointer;line-height:1.3;max-width:100%}
button.who:hover{border-color:var(--accent)}
span.who.multi{font-size:14px;font-weight:600;display:block}
button.who.on{background:var(--fg);border-color:var(--fg);color:var(--bg)}
/* No overflow wrapper around these tables, deliberately. An ancestor with
   overflow-x:auto becomes the containing scroll box for position:sticky,
   so the column headers anchored to it scrolled off the top of the page
   with the table instead of pinning under the filter bar. The page itself
   stays the scroll container; a narrow window scrolls sideways. */
/* border-collapse:separate, not collapse. WebKit ignores position:sticky
   on a <th> inside a collapsed-border table — the header simply scrolls
   away — and that is what put the column headings below the first row of
   data. Only bottom borders are drawn on cells, so separate borders look
   identical here. */
table{border-collapse:separate;border-spacing:0;width:100%;min-width:1390px;
  font-size:14.5px}
/* Counted from the left, so inserting a column shifts every rule after
   it — which is what happened when Who's behind it went in at 2 and
   Proposal inherited a 104px allowance meant for the MW figure. The
   heading each rule is for is named, so the next insertion is a
   re-reading rather than a guess. */
#tbl-sites th:nth-child(1),#tbl-sites td:nth-child(1){min-width:330px}   /* Site */
#tbl-sites th:nth-child(2),#tbl-sites td:nth-child(2){width:168px}       /* Who's behind it */
#tbl-sites th:nth-child(3),#tbl-sites td:nth-child(3){width:210px}       /* Signals */
#tbl-sites th:nth-child(4),#tbl-sites td:nth-child(4){width:132px}       /* Power on record */

/* The site cell answers "what is this" on its own: the name, then where
   it is and what it is called in this dataset, then what the applicant
   said they were building. It was three columns — name, councils, and a
   Proposal column of its own — which put the answer to one question in
   three places and made the table read as a spreadsheet rather than a
   list of sites (Luke, 2026-08-24, against the design proposal). */
.sitecell .sname{display:block;font-weight:700;font-size:18px;line-height:1.25;
  color:var(--accent)}
.sitecell .skey{display:block;color:var(--mut);font-size:13px;margin:2px 0 4px}
.sitecell .sprop{display:block;font-size:14.5px;line-height:1.4;max-width:60ch}
/* Signals stacked, not wrapped across the row: at one per line the eye
   reads a list, and the column stays narrow enough to leave the site
   cell its width. One neutral fill — colour on this page means the state
   of a figure, not the identity of a cohort. */
.sigcell{white-space:normal}
.sigpill{display:block;width:fit-content;max-width:100%;margin:0 0 4px;
  padding:2px 9px;border:1px solid var(--line);border-radius:999px;
  background:var(--soft);color:var(--fg);font-size:13px;line-height:1.35}
/* The figure carries the weight; what kind of figure it is sits under it
   in the muted line the rest of the page uses for evidence-about-evidence. */
/* The reading bar, from the handoff's fourth column — and the one place
   its colour spec and §8b's rule agree, because how much of a site has
   been read IS the state of its evidence rather than a category. Blue
   where the reading is done, the warning colour where a figure can only
   be a floor, grey where nothing was published to read. The words are
   there too: a bar alone says "some" to a person who cannot see the
   difference between the two fills. */
.rbar{display:block;height:6px;background:var(--line);margin:0 0 5px;
  border-radius:0;overflow:hidden;max-width:150px}
.rbar-fill{display:block;height:100%}
.rbar-fill.r-done{background:var(--ok)}
.rbar-fill.r-part{background:var(--warn)}
.rbar-fill.r-none{background:var(--line)}
.rstate.r-done{color:var(--ok)}
.rstate.r-part{color:var(--warn)}
.rstate.r-none{color:var(--mut)}
.mw{font-variant-numeric:tabular-nums;line-height:1.15;white-space:nowrap}
.mw .fig{font-size:21px;line-height:1.15}
.mw .w-stated{font-weight:700}                       /* disclosed by the applicant */
.mw .w-implied{font-weight:500;color:var(--mut)}     /* a connection, or standby-implied */
.mw .w-modelled{font-weight:400;color:var(--mut)}    /* arithmetic on floorspace */
.mw .w-none{font-weight:400;color:var(--mut)}
#tbl-sites th:nth-child(5),#tbl-sites td:nth-child(5){width:108px}       /* Power indicators */
#tbl-sites th:nth-child(6),#tbl-sites td:nth-child(6){width:150px}       /* Status */
/* Narrowed to make room for the indicators column: of the "top level"
   cells this one has the most spare width, an address rarely needing
   its full former allowance. */
#tbl-sites th:nth-child(7),#tbl-sites td:nth-child(7){min-width:190px}   /* Location */
#tbl-sites th:nth-child(8),#tbl-sites td:nth-child(8){width:112px}       /* Read */
/* A date is one word or it is nothing: 2024-04-15 broken across two lines
   reads as two half-dates. The width comes out of Proposal, which is the
   one column here that can lose a few pixels without cost. */
#tbl-apps th:nth-child(4),#tbl-apps td:nth-child(4){white-space:nowrap;width:98px}
tr.detail td{min-width:0}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
/* Sticky on the <thead>, not on each <th>. On a 910-row table the
   per-cell version silently stopped pinning — the headings scrolled away
   and ended up sitting below the first rows of data — while the same rule
   worked on a short table. Sticking the row group is reliable at any
   length. */
#tbl-sites thead,#tbl-apps thead,#tbl-energy thead{position:sticky;
  top:var(--th-top,82px);z-index:7}
th{background:var(--bg);cursor:pointer;white-space:nowrap;font-weight:600;
  border-bottom:2px solid var(--line);vertical-align:bottom}
th:after{content:" ↕";color:var(--mut);font-size:12px;opacity:.55}
tr.site{cursor:pointer}
tr.site:hover{background:rgba(127,127,127,.06)}
/* An open row and its panel share a background and a left edge, so it is
   obvious which row the panel below belongs to. */
tr.site.open>td{background:var(--soft);box-shadow:inset 0 1px 0 var(--accent)}
tr.site.open>td:first-child{box-shadow:inset 3px 1px 0 -1px var(--accent),
  inset 0 1px 0 var(--accent)}
tr.detail.on>td{box-shadow:inset 3px 0 0 -1px var(--accent)}
tr.detail{display:none;background:var(--soft)}
tr.detail.on{display:table-row}
tr.detail td{padding:14px 18px 18px 30px}
/* The qualifier under a figure wraps; only the figure itself must not.
   Inheriting nowrap from .mw made "Disclosed total site demand · may
   rise" set the width of the whole column. */
.mw .q{white-space:normal}
.prov{color:var(--warn);font-weight:400}
.q{display:block;color:var(--mut);font-size:13px;font-weight:400;line-height:1.35}
/* Status labels wrap. They are occasionally a full sentence — "No figure
   found so far — 56 of 69 documents analysed" — and holding those on one
   line gave the column more width than any other, on rows that are
   several lines deep anyway. */
.tag{display:inline-block;padding:2px 7px;border-radius:9px;font-size:13px;
  white-space:normal;line-height:1.35}
.tag.known{background:var(--okbg);color:var(--ok)}
.tag.unknown{background:var(--warnbg);color:var(--warn)}
/* The panel is a four-column grid, split by what the boxes are about
   rather than by their size. Column 1 describes the record — what is
   proposed, and the identifiers and provenance of the row itself.
   Columns 2 to 4 carry the three subject boxes on one row, with the
   consumption context as a shallow band beneath them.

   The identity fields were a full-width band across the top until this
   layout, which cost columns 2 to 4 exactly its height in whitespace
   while the first column ran long — the same imbalance as before it,
   reversed. Stacking the two record boxes in one column puts the tall
   subject boxes and the tall proposal side by side instead. */
/* §5 of the handoff: the body is two columns, 1.55fr and 1fr.
   The four-column grid of seven equal cards was the jigsaw Luke
   objected to; one column was my over-correction, and he said so —
   "the 'jigsaw' comment wasn't an appeal to go to one column; it was an
   appeal to use the proposed new design". Left: what the documents say
   about this site. Right: what was computed from them, and the
   coverage that qualifies it. */
.sitebody{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);
  gap:22px;align-items:start}
@media (max-width:1100px){.sitebody{grid-template-columns:1fr}}
.sitebody .col-record,.sitebody .col-computed{display:flex;flex-direction:column;
  gap:0;min-width:0}
/* §5's header card, and the identifiers under the name. */
.sitehead{border-top-color:var(--brand);padding:22px 26px 24px;margin-bottom:0}
.sitepills{margin:0 0 10px;display:flex;gap:6px;flex-wrap:wrap}
.sitename{margin:0 0 6px;font-family:"Source Serif 4",Georgia,serif;
  font-size:32px;line-height:1.15;font-weight:700;max-width:28em}
.siteident{margin:0 0 12px;font-size:15px;color:var(--mut)}
.sitelinks{margin:0;display:flex;gap:24px;flex-wrap:wrap;font-size:14px}
/* The caveat banner the handoff puts directly beneath the header, in
   its own colours: this is the sentence that stops a floor being read
   as a total. */
.sitehead + .banner{background:#fdf6e3;border:0;border-left:4px solid var(--warn);
  color:#3d2b00;padding:14px 18px;font-size:15px;line-height:1.55;
  border-radius:0;margin:0 0 18px}
.grid{display:flex;flex-direction:column;gap:0;align-items:stretch}
.box{border:0;border-top:4px solid var(--line);border-radius:0;
  padding:18px 0 10px;min-width:0}
.box > p,.box > .help,.box > dl{max-width:74ch}
/* A flex column rather than two grid rows: grid rows are shared across
   the whole panel, so an identity box placed in row 2 hangs below the
   tallest subject box in row 1 — a void under the proposal exactly as
   tall as whichever box happens to be longest. */
.col-record{display:contents}
/* One sentence and its caveats: a wide, short band under the subject
   boxes. Left in the grid's auto-flow it landed in the first column,
   stranding the documents section below an empty row. */
.box.ctx{}
/* box.claims takes no explicit placement — it sits in row 1 between
   Declared power and Generation, an ordinary third box. It used to
   claim the full width like .ctx, but a full-width item mid-sequence
   breaks CSS Grid's auto-placement for everything after it: needing
   three contiguous free tracks in row 1, and finding only two (Declared
   power already holds the first), the browser drops the whole item to
   row 2 — and then auto-places every later box from that cursor
   position, pushing Generation into a track meant for something else
   and leaving row 1 half-empty. A full-width item is safe only at the
   end of the sequence, which is where .ctx has always lived. */
/* Where the panel's numbers come from, set apart from the caveats that
   follow each figure: it qualifies the whole box, not one row. */
.help.provenance{border-left:2px solid var(--line);padding-left:9px;
  margin-bottom:9px}
.box.claims .claim{margin-bottom:10px}
.box.claims details>summary{cursor:pointer;font-size:13.5px;color:var(--accent);
  list-style:none}
.box.claims details>summary::-webkit-details-marker{display:none}
.box.claims details>p{margin-top:6px}
@media (max-width:1100px){
  .grid{grid-template-columns:1fr 1fr}
  /* Three boxes wide enough to want the full width again: dissolving the
     wrapper returns them to the panel grid as direct items. */
  .col-record{display:contents}
  .box.proposal{grid-column:1 / -1;grid-row:auto}
  .box.identity{grid-column:1 / -1;grid-row:auto}
  .box.parties{grid-column:1 / -1;grid-row:auto}
  .box.ctx{grid-column:1 / -1}
}
@media (max-width:700px){
  .grid{grid-template-columns:1fr}
  .box.proposal,.box.identity{grid-column:1}
}
/* One field per row: the identity box now sits in the narrow first
   column, where four abreast would break every value onto its own
   wrapped lines. It widens to two only where the box itself goes full
   width, at the breakpoints below. Site key and classification stay
   paired in a stack, which is what keeps them sharing one cell there
   rather than each taking a whole one. */
.fields{display:grid;grid-template-columns:1fr;gap:9px 18px}
.fields .stack{display:flex;flex-direction:column;gap:9px}
.fields .wide{grid-column:1 / -1}
@media (max-width:1100px){.fields{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.fields{grid-template-columns:1fr}}
.fields .lbl{display:block;color:var(--mut);font-size:13px;margin-bottom:1px}
.fields .val{display:block;font-size:14px;line-height:1.45}
.box h4{margin:0 0 7px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut)}
.box p{margin:0 0 8px}
.kv{display:grid;grid-template-columns:148px 1fr;gap:2px 12px;font-size:14px;margin:0}
.kv dt{color:var(--mut)}.kv dd{margin:0}
.fams{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:6px 22px}
.fam{border-top:1px solid var(--line);padding:6px 0 4px;min-width:0}
.famhead{font-size:13.5px;margin-bottom:3px}
/* No text-transform: the label is capitalised where it is built,
   because CSS cannot tell EIA from Eia. */
.famname{font-weight:600}
details.famrest summary{font-size:13.5px;color:var(--mut);cursor:pointer;margin:2px 0 0 16px}
ul.find{margin:0;padding-left:16px;font-size:14px}
ul.find li{margin-bottom:3px}
ul.find .st{color:var(--mut)}
table.apps{font-size:14px;margin-top:4px}
table.apps th{position:static;font-size:13px;text-transform:uppercase;letter-spacing:.4px;
  color:var(--mut);cursor:default;z-index:auto}
table.apps th:after{content:""}
table.apps td{padding:5px 9px 5px 0}
h4.sub-head{margin:18px 0 4px;font-size:13px;text-transform:uppercase;
  letter-spacing:.5px;color:var(--mut)}
details.apps-d{margin-top:16px;border-top:1px solid var(--line);padding-top:10px}
details.apps-d>summary{cursor:pointer;font-size:14px;color:var(--accent);
  list-style:none;display:inline-block;padding:3px 0}
details.apps-d>summary::-webkit-details-marker{display:none}
details.apps-d>summary:hover{text-decoration:underline}
.stat button{font:inherit;border:0;background:none;color:inherit;cursor:pointer;
  padding:0;text-align:left;border-radius:5px}
.stat button span{color:var(--accent)}
.stat button:hover span,.stat button:focus-visible span{text-decoration:underline}
.stat button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
table.stats{width:100%;margin:6px 0 18px;font-size:14.5px;min-width:0;
  border-collapse:separate;border-spacing:0}
table.stats th[scope=row]{position:static;font-weight:500;white-space:normal;
  border-bottom:1px solid var(--line);z-index:auto;cursor:default}
table.stats th:after{content:""}
table.stats th[scope=col]{position:static;cursor:default;white-space:normal;
  border-bottom:2px solid var(--line);z-index:auto}
/* The queue comparison is five narrow columns; at full page width the
   numbers drift a screen away from the band labels and the headers
   stack. Capped, with roomier numeric columns than the 74px default. */
table.stats.queue{max-width:620px}
table.stats.queue td.n{width:105px}
table.stats.queue th[scope=col]{vertical-align:bottom}
table.stats tr.lead th[scope=row]{font-weight:650}
/* Told / not told. The dash has to read as "nothing published here",
   not as a missing value we failed to collect, so it is muted rather
   than absent and the filled cell says how many figures. */
table.stats td.yes{color:var(--ok);font-weight:600}
table.stats td.yes .q{color:var(--mut);font-weight:400;margin-left:4px}
table.stats td.none{color:var(--mut)}
table.stats td.n{font-variant-numeric:tabular-nums;text-align:right;width:74px;
  white-space:nowrap}
table.stats td.help{width:52%}
/* Operator rows expand, the same one-at-a-time gesture as the Sites
   table. Every number in that table is an aggregate — six sites, eleven
   figures — and an aggregate a reader cannot open is an assertion.
   The panel underneath is where the sites are named and every figure
   carries the document it was published in. */
table.stats tr.op{cursor:pointer}
table.stats tr.op:hover>td{background:rgba(127,127,127,.06)}
table.stats tr.op.open>td{background:var(--soft);
  box-shadow:inset 0 1px 0 var(--accent)}
.opdetail h5{margin:14px 0 6px;font-size:13px;font-weight:650;
  text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}
.opdetail h5:first-child{margin-top:0}
.opdetail .claim{margin:0 0 9px}
.opdetail .claim p{margin:0 0 2px}
.opdetail .sitelist{margin:0}
.opdetail details>summary,.opsite details>summary{cursor:pointer;
  font-size:13.5px;color:var(--accent);list-style:none}
.opdetail details>summary::-webkit-details-marker,
.opsite details>summary::-webkit-details-marker{display:none}
.opsite{margin-bottom:12px}
.opsite .claim{margin:0 0 9px}
.opsite .claim p{margin:0 0 2px}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px;
  margin:12px 0 6px}
figure.chart{margin:0}
figure.chart figcaption{font-size:14px;font-weight:650;margin-bottom:6px}
figure.chart svg{width:100%;height:auto}
figure.chart rect{fill:var(--accent);opacity:.78}
figure.chart rect:hover{opacity:1}
figure.chart rect.hl{opacity:.42}
figure.chart .ax{stroke:var(--line)}
figure.chart .xl,figure.chart .yl{fill:var(--mut);font-size:12px}
a.dlink{margin-left:5px;font-weight:400;color:var(--mut);text-decoration:none;
  font-size:13px;border:1px solid var(--line);border-radius:50%;padding:0 4px}
a.dlink:hover{color:var(--accent);border-color:var(--accent);text-decoration:none}
/* Start here, from §2 of the design brief rather than from my own head:
   content and a 380px sidebar, 48px apart; cards are white with a 4px
   top rule in the colour of what they are about — brand for structure,
   caution orange for the pitfalls, ink for the package. */
.startgrid{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:48px;
  align-items:start;margin-top:20px}
@media (max-width:1100px){.startgrid{grid-template-columns:1fr;gap:28px}}
.card{background:var(--bg);border:1px solid var(--line-lt);border-top:4px solid var(--line);
  padding:20px 24px 22px;margin:0 0 16px}
.card-brand{border-top-color:var(--brand)}
.card-warn{border-top-color:var(--warn)}
.card-ink{border-top-color:#333}
.cardh{margin:0 0 12px;font-size:23px;line-height:1.18;font-weight:700;
  font-family:"Source Serif 4",Georgia,serif}
.cardintro{margin:0 0 14px;font-size:15px;line-height:1.5;color:var(--body)}
.twoways{display:grid;grid-template-columns:1fr 1fr;gap:28px}
@media (max-width:760px){.twoways{grid-template-columns:1fr;gap:22px}}
/* The rule and the label share a colour, and the colour says which of
   the two things this is: news red for signals, brand for the data. */
.twoways .way{border-left:3px solid var(--line);padding-left:16px}
.twoways .way-signals{border-left-color:#c70000}
.twoways .way-data{border-left-color:var(--brand)}
.waylab{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;
  margin-bottom:7px}
.way-signals .waylab{color:#c70000}
.way-data .waylab{color:var(--brand)}
.twoways .way p{margin:0 0 14px;font-size:15px;line-height:1.5;color:var(--body)}
/* Five pitfalls, hairline between each, lead in 600 above its body. */
.pit{border-top:1px solid var(--line);padding:12px 0 2px}
.pit:first-of-type{border-top:0;padding-top:0}
.pith{font-size:15px;font-weight:600;margin-bottom:3px}
.pit p{margin:0 0 10px;font-size:15px;line-height:1.5;color:var(--body)}
/* The sidebar states a boundary: a number, and what it excludes. */
.sideh{margin:0 0 12px;font-size:13px;font-weight:700;text-transform:uppercase;
  letter-spacing:.6px;color:var(--brand)}
.card-ink .sideh{color:#333}
.crow{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
  font-size:14px;padding-top:12px;border-top:1px solid var(--line-lt)}
.crow:first-of-type{border-top:0;padding-top:0}
.crow b{font-weight:600}
.cnote{margin:2px 0 12px;font-size:13px;line-height:1.45;color:var(--mut)}
.cta{font:inherit;font-size:15px;font-weight:600;padding:9px 18px;border-radius:999px;
  border:1px solid var(--brand);background:var(--brand);color:#fff;cursor:pointer}
.cta.secondary{background:var(--bg);color:var(--brand)}
.cta:hover{text-decoration:underline}
.entry{padding:9px 0;border-bottom:1px solid var(--line);scroll-margin-top:70px}
.entry h3{margin:0 0 3px;font-size:15px}
.entry p{margin:0;color:var(--mut);font-size:14.5px}
.entry.flash{background:var(--warnbg);border-radius:5px;padding-left:9px;padding-right:9px}
.wrap h3.m{font-size:16.5px;margin:20px 0 4px}
.wrap p.m{margin:0 0 9px}
.wrap ul.m{margin:0 0 9px;padding-left:19px}
.wrap ul.m li{margin-bottom:4px}
/* Controls beside the map, not above and below it. A laptop viewport is
   landscape and Britain is not, so stacking a filter bar on top and a key
   underneath left a short, wide strip of map with the key pushed off the
   bottom of the screen. In a side column the map keeps the full height
   and comes out closer to square, and the key is always visible.
   The height is set so the page exactly fills the viewport and does not
   scroll — --map-top is measured, because the masthead above it is not a
   fixed height. */
#mapwrap{display:flex;height:calc(100vh - var(--map-top,150px));min-height:440px;
  border-top:1px solid var(--line)}
#mapside{flex:0 0 250px;overflow-y:auto;padding:14px 16px;display:flex;
  flex-direction:column;gap:13px;border-right:1px solid var(--line)}
#mapside input[type=search]{min-width:0;width:100%}
#mapside .mgroup{display:flex;flex-direction:column;gap:7px}
#mapside .count{margin:0;font-size:14px}
#mapside .help{margin:0}
#mapside .attrib{margin-top:auto;padding-top:10px;border-top:1px solid var(--line)}
@media (max-width:760px){
  #mapwrap{flex-direction:column;height:auto}
  #mapside{flex:none;border-right:0;border-bottom:1px solid var(--line)}
  #mapview{height:70vh}
}
#mapview{position:relative;overflow:hidden;flex:1;height:100%;min-width:0;
  background:var(--soft);cursor:grab;touch-action:none}
#mapview:active{cursor:grabbing}
#maptiles,#mappins{position:absolute;inset:0}
#mappins{pointer-events:none}
img.tl{position:absolute;width:256px;height:256px;user-select:none;-webkit-user-drag:none}
/* The tile inversion went with the dark scheme: OpenStreetMap's own
   tiles are a light map, and inverting them was only ever to stop a
   white rectangle glaring out of a dark page. */
.pin{position:absolute;width:11px;height:11px;margin:-6px 0 0 -6px;border-radius:50%;
  border:1.5px solid #fff;padding:0;cursor:pointer;pointer-events:auto;
  box-shadow:0 0 0 1px rgba(0,0,0,.35)}
.pin.s{background:var(--warn)}
.pin.e{background:var(--brand)}
/* §8c: the chips colour the map. Not a hue per cohort — §8b keeps
   colour for the state of a figure, and a dozen cohort colours would
   spend it on categories — but the reader's own selection, in the same
   yellow their chips use, with everything outside it stepped back so
   the shape of the cohort is what the eye finds. */
.pin.inco{background:var(--active);border-color:#121212;
  box-shadow:0 0 0 1px rgba(0,0,0,.5)}
.pin.outco{opacity:.28}
.pin.sel{width:19px;height:19px;margin:-10px 0 0 -10px;border-width:3px;z-index:5}
#mapzoom{position:absolute;top:12px;right:12px;display:flex;flex-direction:column;gap:3px}
#mapzoom button{width:31px;height:31px;font-size:21px;border:1px solid var(--line);
  background:var(--bg);color:var(--fg);cursor:pointer;border-radius:5px}
#mapinfo{position:absolute;top:12px;left:12px;width:300px;background:var(--bg);
  border:1px solid var(--line);border-radius:7px;padding:11px 13px;font-size:14.5px;
  box-shadow:0 2px 14px rgba(0,0,0,.16);z-index:6}
#mapinfo .cardx{position:absolute;top:4px;right:6px;border:0;background:none;
  color:var(--mut);font-size:21px;line-height:1;cursor:pointer;padding:2px 4px}
#mapinfo .cardx:hover{color:var(--fg)}
#mapinfo .cardlinks{display:block;margin-top:7px;padding-top:7px;
  border-top:1px solid var(--line);font-size:14px}
#mapkey{font-size:13.5px;color:var(--mut);display:flex;flex-direction:column;gap:5px}
/* Explicit inline-block: on the map a .pin is a <button>, which is
   inline-block already, but in the key it is a <span> — inline, so width
   and height were ignored and the swatch collapsed to a sliver. */
#mapkey div{display:flex;align-items:center;gap:7px}
#mapkey .pin{position:static;pointer-events:none;display:inline-block;
  flex:0 0 11px;width:11px;height:11px;margin:0}
footer{padding:20px 22px 34px;color:var(--mut);font-size:13.5px;border-top:1px solid var(--line)}
.help{font-size:13px;color:var(--mut)}
/* A button that reads as a link: it navigates rather than submits, but it
   is a button because it acts on the page's current state rather than
   going to an address. */
.linkish{border:0;background:none;padding:0;font:inherit;color:var(--lnk,#0b57d0);
  cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.linkish:disabled{color:var(--mut);cursor:default;text-decoration:none}
.tip{display:inline-flex;align-items:center;justify-content:center;width:15px;
  height:15px;margin-left:5px;border-radius:50%;border:1px solid var(--line);
  color:var(--mut);font-size:10.5px;cursor:help;position:relative;vertical-align:1px}
.tip .tiptext{display:none;position:absolute;bottom:20px;left:-8px;width:290px;
  background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px 10px;
  font-size:13.5px;line-height:1.45;color:var(--fg);box-shadow:0 2px 14px rgba(0,0,0,.16);
  z-index:8;text-align:left;cursor:auto}
/* focus-within as well as focus: a tap on a touch device, where there
   is no hover at all, lands focus on the span or on something inside
   it depending on the engine. */
.tip:hover .tiptext,.tip:focus .tiptext,
.tip:focus-within .tiptext{display:block}
/* The map is showing a subset someone chose on another tab. Said out
   loud, with the way out attached, because a map silently showing 190 of
   429 sites is indistinguishable from a map that is simply wrong. */
#mapsubset{position:absolute;top:10px;left:10px;right:58px;z-index:7;
  display:flex;gap:8px;align-items:baseline;padding:7px 10px;border:1px solid var(--line);
  border-radius:6px;background:var(--bg);font-size:13.5px;
  box-shadow:0 2px 10px rgba(0,0,0,.12)}
#mapsubset[hidden]{display:none}
/* Bracketed mention counts. Subdued because they qualify the label they
   follow rather than stating a quantity of anything on the site — the
   same grey as .help and the field keys, which is already the page's
   sign for "this is about the evidence, not the development". */
.mcount{color:var(--mut)}
"""

MAP_JS = """
/* A slippy map in about a hundred lines, rather than a mapping library.
   Two reasons. The page has to stay one file that opens from a Drive
   folder, so a CDN script tag is out; and vendoring a minified library
   into a journalism deliverable means shipping code nobody here has read.
   Tiles come from OpenStreetMap when there is a connection and simply do
   not paint when there isn't — the markers, filters and search keep
   working either way, which is the part that matters offline. */
/* Run now, and once more on the next turn of the loop. Layout that
   depends on an element becoming visible needs to happen after the
   display change, and requestAnimationFrame is the usual way to wait —
   but it never fires in some embedded viewers, which left the map
   centred on the whole country when a link asked for two specific
   points. Both calls are pure re-renders, so doing it twice is free. */
function soon(fn){ try{ fn(); }catch(e){} setTimeout(fn, 0); }
const TS=256, MINZ=5, MAXZ=17;
const map={z:6, cx:-2.4, cy:54.2, el:null, tiles:null, pins:null, drag:null,
           fitted:false, fitSize:null, userMoved:false, subset:null};
function proj(lat,lon,z){
  const n=Math.pow(2,z), la=lat*Math.PI/180;
  return [(lon+180)/360*n*TS,
          (1-Math.log(Math.tan(la)+1/Math.cos(la))/Math.PI)/2*n*TS];
}
function unproj(px,py,z){
  const n=Math.pow(2,z);
  const lon=px/(n*TS)*360-180;
  const k=Math.PI-2*Math.PI*py/(n*TS);
  return [180/Math.PI*Math.atan(0.5*(Math.exp(k)-Math.exp(-k))), lon];
}
/* Zoom about a point, keeping whatever is under the cursor where it is.
   Zooming about the viewport centre — which is what changing map.z alone
   does — means the thing you are trying to look at slides away from you
   at every step, and you chase it with the drag handle. */
function zoomAround(nz, clientX, clientY){
  nz = Math.max(MINZ, Math.min(MAXZ, nz));
  if(nz === map.z) return;
  map.userMoved = true;
  hideCard();
  const r = map.el.getBoundingClientRect();
  const w = map.el.clientWidth, h = map.el.clientHeight;
  const px = (clientX === undefined) ? w / 2 : clientX - r.left;
  const py = (clientY === undefined) ? h / 2 : clientY - r.top;
  const [cx, cy] = proj(map.cy, map.cx, map.z);
  const ox = cx - w / 2, oy = cy - h / 2;
  const f = Math.pow(2, nz - map.z);
  const nox = (ox + px) * f - px, noy = (oy + py) * f - py;
  const [la, lo] = unproj(nox + w / 2, noy + h / 2, nz);
  map.z = nz; map.cy = la; map.cx = lo;
  drawMap();
}

function drawMap(){
  /* First real draw fits the data to whatever space the window actually
     gives us, rather than opening at a hardcoded zoom 6 that crops the
     country on a laptop and wastes half a widescreen. It happens here,
     not in initMap, because the tab is hidden at startup and a hidden
     element has no width to fit to. */
  /* Refit while the opening view is still untouched. The first draw can
     happen before the side column has settled and given the map its full
     height, so the fit lands against a shorter box and the map opens
     further out than it should. Once the reader has panned or zoomed,
     their view is theirs and is never overridden. */
  const size = map.el.clientWidth + 'x' + map.el.clientHeight;
  if(map.el.clientWidth > 0 && !map.userMoved
     && (!map.fitted || (map.fitSize && map.fitSize !== size))){
    map.fitted = true;
    const vis = MAPPTS.filter(p => p.vis);
    if(vis.length){ fitTo(vis); return; }
  }
  const w=map.el.clientWidth, h=map.el.clientHeight;
  const [cx,cy]=proj(map.cy,map.cx,map.z);
  const ox=cx-w/2, oy=cy-h/2, n=Math.pow(2,map.z);
  let html='';
  for(let tx=Math.floor(ox/TS); tx<=Math.floor((ox+w)/TS); tx++){
    for(let ty=Math.floor(oy/TS); ty<=Math.floor((oy+h)/TS); ty++){
      if(ty<0||ty>=n) continue;
      const wx=((tx%n)+n)%n;
      html+='<img class="tl" alt="" loading="lazy" src="https://tile.openstreetmap.org/'
        +map.z+'/'+wx+'/'+ty+'.png" style="left:'+(tx*TS-ox)+'px;top:'+(ty*TS-oy)+'px">';
    }
  }
  map.tiles.innerHTML=html;
  let pins='', shown=0;
  for(const p of MAPPTS){
    if(!p.vis) continue;
    const [x,y]=proj(p.lat,p.lon,map.z);
    const dx=x-ox, dy=y-oy;
    if(dx<-40||dy<-40||dx>w+40||dy>h+40) { shown++; continue; }
    shown++;
    pins+='<button class="pin '+p.k+(p.sel?' sel':'')
      +(map.cohort ? (p.c&&p.c.includes(map.cohort) ? ' inco' : ' outco') : '')
      +'" style="left:'+dx+'px;top:'+dy
      +'px" data-i="'+p.i+'" title="'+p.t+'"></button>';
  }
  map.pins.innerHTML=pins;
  document.getElementById('mapcount').textContent =
    shown+' of '+MAPPTS.length+' locations';
}
/* A set of site keys projected from the Sites tab, or null for "no
   subset". mapFilter INTERSECTS with it rather than replacing it, so the
   map's own controls keep working inside the projection instead of
   silently discarding it the moment one is touched. */
function clearSubset(){
  map.subset=null;
  map.cohort='';
  document.getElementById('mcohort').value='';
  document.getElementById('mapcohortkey').hidden=true;
  document.getElementById('mapsubset').hidden=true;
  mapFilter();
}
/* The map's search box searches exactly what the Sites tab's box
   searches, by reading the row's own haystack out of the table instead
   of keeping a second, thinner copy in MAPPTS. Two reasons: a term that
   matched an applicant or a proposal on the Sites tab used to find
   nothing on the map, and — since seeAllOnMap now mirrors the term
   across — a narrower haystack here would quietly drop sites the
   projection contains and make the overlay's count wrong.
   Built on first use: this script is defined before the table is
   parsed. */
let SITEHAY=null;
function siteHay(id){
  if(SITEHAY===null){
    SITEHAY=new Map();
    for(const r of document.querySelectorAll('#tbl-sites tr.site'))
      SITEHAY.set(r.dataset.key, r.dataset.hay);
  }
  const h=SITEHAY.get(id);
  return h===undefined ? null : h;
}
function mapFilter(){
  const s=(document.getElementById('mq').value||'').toLowerCase().trim();
  const showE=document.getElementById('me').checked;
  const showS=document.getElementById('ms').checked;
  const big=document.getElementById('mbig').getAttribute('aria-pressed')==='true';
  for(const p of MAPPTS){
    let ok = p.k==='e' ? showE : showS;
    if(ok&&map.subset&&p.k==='s') ok = map.subset.has(p.id);
    if(ok&&s) ok=(p.k==='s' ? (siteHay(p.id) || p.h) : p.h).includes(s);
    if(ok&&big&&p.k!=='e'){
      ok = p.mw===null ? !document.getElementById('munk').checked : p.mw>=100;
    }
    p.vis=ok;
  }
  drawMap();
}
function fitTo(pts){
  if(!pts.length) return;
  if(pts.length===1){ map.cy=pts[0].lat; map.cx=pts[0].lon; map.z=12; return drawMap(); }
  const la=pts.map(p=>p.lat), lo=pts.map(p=>p.lon);
  map.cy=(Math.min(...la)+Math.max(...la))/2;
  map.cx=(Math.min(...lo)+Math.max(...lo))/2;
  const w=map.el.clientWidth||800, h=map.el.clientHeight||600;
  // 0.88, not 0.7. Jersey and Shetland stretch the bounding box well
  // beyond where the sites actually are, so a generous margin on top of
  // that opened the map on most of western Europe.
  for(let z=MAXZ; z>=MINZ; z--){
    const a=proj(Math.min(...la),Math.min(...lo),z), b=proj(Math.max(...la),Math.max(...lo),z);
    if(Math.abs(b[0]-a[0])<w*0.88 && Math.abs(b[1]-a[1])<h*0.88){ map.z=z; break; }
  }
  map.fitSize = w + 'x' + h;
  drawMap();
}
function showMap(siteKey, energyRef){
  show('map', true);
  // Jumping to one site leaves any projection behind, or the site would
  // be filtered out of the very view that was opened to show it.
  map.subset=null;
  document.getElementById('mapsubset').hidden=true;
  MAPPTS.forEach(p=>{p.sel=false;});
  const want=[];
  if(siteKey||energyRef){
    document.getElementById('me').checked=true;
    document.getElementById('ms').checked=true;
    document.getElementById('mq').value='';
    document.getElementById('mbig').setAttribute('aria-pressed','false');
    document.getElementById('munk').checked=false;
    document.getElementById('munk').disabled=true;
    document.getElementById('munklab').classList.add('off');
    mapFilter();
    for(const p of MAPPTS){
      if((siteKey&&p.k==='s'&&p.id===siteKey)||(energyRef&&p.k==='e'&&p.id===energyRef)){
        p.sel=true; want.push(p);
      }
    }
  }
  soon(()=>{ if(want.length){ map.userMoved=true; fitTo(want); } else drawMap(); });
}
/* Put the card beside the marker, clamped inside the map. It used to be
   pinned to the bottom-left of the map container — and the map is taller
   than the fold, so on a click near the top the card opened below the
   visible area and looked as though nothing had happened. */
function showCard(p, pin){
  const box = document.getElementById('mapinfo');
  box.innerHTML = '<button class="cardx" aria-label="Close">\u00d7</button>' + p.pop;
  box.hidden = false;
  const view = map.el.getBoundingClientRect();
  const at = pin.getBoundingClientRect();
  const bw = box.offsetWidth, bh = box.offsetHeight;
  const x = at.left - view.left + at.width + 12;
  const y = at.top - view.top - bh / 2 + at.height / 2;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  // Flip to the other side of the marker rather than sitting on top of it.
  box.style.left = (x + bw > view.width - 8
                    ? clamp(at.left - view.left - bw - 12, 8, view.width - bw - 8)
                    : clamp(x, 8, view.width - bw - 8)) + 'px';
  box.style.top = clamp(y, 8, Math.max(8, view.height - bh - 8)) + 'px';
  box.querySelector('.cardx').addEventListener('click', () => { box.hidden = true; });
}

function hideCard(){ const b=document.getElementById('mapinfo'); if(b) b.hidden=true; }

function initMap(){
  map.el=document.getElementById('mapview');
  map.tiles=document.getElementById('maptiles');
  map.pins=document.getElementById('mappins');
  map.el.addEventListener('pointerdown',e=>{
    /* The card is a child of the map, so a press on one of its links
       arrives here too. Starting a drag then hid the card on the first
       pointermove — a pixel of movement, which every real mouse
       produces — so the anchor was gone before the mouseup that would
       have followed it, and both internal and external links silently
       did nothing. Capturing the pointer to the map compounds it.
       closest(), not classList: a press can land on a pin's child or on
       the card's own <a>, and classList only sees the element itself. */
    if(e.target.closest('.pin, .mapoverlay')) return;
    map.drag={x:e.clientX,y:e.clientY}; map.el.setPointerCapture(e.pointerId);
  });
  map.el.addEventListener('pointermove',e=>{
    if(!map.drag) return;
    const [cx,cy]=proj(map.cy,map.cx,map.z);
    const [la,lo]=unproj(cx-(e.clientX-map.drag.x), cy-(e.clientY-map.drag.y), map.z);
    map.cy=la; map.cx=lo; map.drag={x:e.clientX,y:e.clientY};
    map.userMoved=true; hideCard(); drawMap();
  });
  addEventListener('pointerup',()=>{map.drag=null;});
  /* A wheel event is not a zoom level. A trackpad emits a stream of them
     for one gesture, so stepping a level per event flew through five
     levels before the fingers had stopped moving. Accumulate instead, and
     step only when enough has built up — pinch (ctrlKey) counts for more
     per unit than a scroll, because the gesture is shorter. */
  let wheelAcc = 0, wheelAt = 0;
  map.el.addEventListener('wheel',e=>{
    e.preventDefault();
    const t = e.timeStamp || 0;
    if(t - wheelAt > 400) wheelAcc = 0;      // a new gesture starts clean
    wheelAt = t;
    wheelAcc += -e.deltaY * (e.ctrlKey ? 0.02 : 0.006);
    while(wheelAcc >= 1){ zoomAround(map.z + 1, e.clientX, e.clientY); wheelAcc -= 1; }
    while(wheelAcc <= -1){ zoomAround(map.z - 1, e.clientX, e.clientY); wheelAcc += 1; }
  },{passive:false});
  // Double-click zooms in where you clicked; with alt or shift, out.
  map.el.addEventListener('dblclick',e=>{
    if(e.target.closest('.pin, .mapoverlay')) return;
    e.preventDefault();
    zoomAround(map.z + ((e.altKey || e.shiftKey) ? -1 : 1), e.clientX, e.clientY);
  });
  map.pins.addEventListener('click',e=>{
    const b=e.target.closest('.pin'); if(!b) return;
    showCard(MAPPTS[+b.dataset.i], b);
  });
  // Double-clicking a marker goes in on it rather than opening its card.
  map.pins.addEventListener('dblclick',e=>{
    const b=e.target.closest('.pin'); if(!b) return;
    e.preventDefault(); e.stopPropagation();
    const p=MAPPTS[+b.dataset.i];
    map.cy=p.lat; map.cx=p.lon; map.z=Math.min(MAXZ, Math.max(map.z+2, 14));
    drawMap();
  });
  ['mq'].forEach(id=>document.getElementById(id).addEventListener('input',mapFilter));
  ['me','ms'].forEach(id=>document.getElementById(id).addEventListener('change',mapFilter));
  document.getElementById('mbig').addEventListener('click',function(){
    const on=this.getAttribute('aria-pressed')!=='true';
    this.setAttribute('aria-pressed', on);
    const unk=document.getElementById('munk');
    unk.disabled=!on;
    document.getElementById('munklab').classList.toggle('off', !on);
    mapFilter();
  });
  document.getElementById('munk').addEventListener('change', mapFilter);
  document.getElementById('mapsubsetclear').addEventListener('click', clearSubset);
  document.getElementById('mcohort').addEventListener('change', e=>{
    map.cohort = e.target.value || '';
    const k=document.getElementById('mapcohortkey');
    k.hidden = !map.cohort;
    if(map.cohort){
      document.getElementById('mapcohortname').textContent =
        e.target.options[e.target.selectedIndex].text;
    }
    drawMap();
  });
  document.getElementById('mzin').addEventListener('click',()=>zoomAround(map.z+1));
  document.getElementById('mzout').addEventListener('click',()=>zoomAround(map.z-1));
  document.getElementById('mreset').addEventListener('click',()=>{
    map.fitted=false; map.userMoved=false;  // refit to the current window
    document.getElementById('mq').value='';
    document.getElementById('mbig').setAttribute('aria-pressed','false');
    const unk=document.getElementById('munk');
    unk.checked=false; unk.disabled=true;
    document.getElementById('munklab').classList.add('off');
    document.getElementById('me').checked=true; document.getElementById('ms').checked=true;
    MAPPTS.forEach(p=>p.sel=false); mapFilter();});
  addEventListener('resize',()=>{ if(document.getElementById('view-map').classList.contains('on')) drawMap(); });
  mapFilter();
}

/* Open one site's row on the Sites tab, expanded, with filters cleared so
   the row cannot be hidden by a filter the reader left set on another tab. */
/* Show exactly the sites the Sites tab is currently displaying.
   Reads the table rather than re-deriving the filter, so it cannot drift
   from what the reporter is actually looking at: whatever apply() left
   visible is what goes on the map, including any future filter nobody
   has thought of yet. */
function seeAllOnMap(){
  const keys=[];
  for(const r of document.querySelectorAll('#tbl-sites tr.site')){
    if(r.style.display!=='none') keys.push(r.dataset.key);
  }
  const want=new Set(keys);
  const plotted=MAPPTS.filter(p=>p.k==='s'&&want.has(p.id));
  show('map', true);
  map.subset=want;
  document.getElementById('me').checked=false;
  document.getElementById('ms').checked=true;
  // The two power controls and the search term are mirrored from the
  // Sites tab rather than reset. They were reset, so that a control
  // left over from an earlier visit could not filter the projection a
  // second time and make the count lie — but that left the sidebar
  // reporting "100 MW or greater: off" while the reader was looking at
  // exactly the >=100 MW set, which is the same lie told the other way
  // round. Copying is safe where clearing was: both tabs test the same
  // figure with the same rule (est.value_mw, blank meaning undisclosed)
  // and, since siteHay() below, search the same string — so re-applying
  // any of them to a subset they already produced changes nothing.
  const _big=document.getElementById('big').getAttribute('aria-pressed')==='true';
  document.getElementById('mbig').setAttribute('aria-pressed', _big);
  document.getElementById('munk').checked=
    _big && document.getElementById('unk').checked;
  document.getElementById('munk').disabled=!_big;
  document.getElementById('munklab').classList.toggle('off', !_big);
  document.getElementById('mq').value=document.getElementById('q').value;
  MAPPTS.forEach(p=>{p.sel=false;});
  plotted.forEach(p=>{p.sel=true;});
  /* §8c: the chips colour the markers. The map takes the cohort from
     the Sites tab rather than keeping its own, so the two views cannot
     disagree about which cohort is on. */
  const sel=document.getElementById('mcohort');
  sel.value = cohort || '';
  sel.dispatchEvent(new Event('change'));
  mapFilter();
  const missing = keys.length - plotted.length;
  document.getElementById('mapsubsettext').textContent =
    plotted.length.toLocaleString()+' of '+keys.length.toLocaleString()
    +' filtered site'+(keys.length===1?'':'s')+' shown'
    + (missing ? ' — '+missing.toLocaleString()+' ha'+(missing===1?'s':'ve')
                 +' no recorded location' : '');
  document.getElementById('mapsubset').hidden=false;
  soon(()=>{ if(plotted.length){ map.userMoved=true; fitTo(plotted); } else drawMap(); });
}

/* How much chrome is pinned above the scrolling content. Three layers
   stack: the tab bar at top:0, the filter bar beneath it, and the
   table's own sticky header row. scrollIntoView({block:'start'}) knows
   about none of them, so a row scrolled to "the top" lands underneath
   all three — which put a site's name off screen and left the reporter
   looking at expanded detail with no way to tell whose it was.
   Measured from the live elements rather than assumed: the filter bar
   wraps to two lines at some widths, and the whole point is that this
   is the height nobody can predict. */
function stickyOffset(){
  const h = el => (el && el.offsetParent !== null)
                  ? el.getBoundingClientRect().height : 0;
  return h(document.querySelector('nav.top'))
       + h(document.querySelector('.view.on .controls'))
       + h(document.querySelector('.view.on table thead'));
}
// Scroll, then check where the row actually landed and correct.
//
// One shot is enough when a row is opened by clicking, because the page
// is already laid out. It is not enough for a shared link opened cold:
// clearing the filters puts hundreds of rows back into the table and
// expands a panel, and a position computed before that reflow lands
// over a thousand pixels out — far enough that the site is off screen
// and the page looks blank. Measuring the result is the only way to be
// sure, since there is no single event that means "layout is done".
// Browsers restore the previous scroll position on a reload or a
// back-navigation, and they do it *after* load handlers run — so it
// silently overrode the jump to a linked site, landing the reader
// thousands of pixels past it with the row off screen. The tell was the
// same wrong offset recurring exactly across separate reloads. This
// page decides where it starts.
if('scrollRestoration' in history) history.scrollRestoration='manual';

function scrollRowToTop(r, tries){
  const y = Math.max(0, window.scrollY
    + r.getBoundingClientRect().top - stickyOffset() - 8);
  window.scrollTo({top: y});
  const n = tries || 0;
  // Keep correcting until the row actually sits where it should. This
  // page is eight megabytes and a cold, uncached load reflows for a
  // while after the load event, so a short burst of retries lands
  // confidently in the wrong place — the row ends up a thousand pixels
  // above the viewport and the reader sees an unrelated part of the
  // table. Nothing announces "layout is finished", so measure instead.
  //
  // setTimeout rather than requestAnimationFrame: rAF is throttled or
  // suspended in a background tab, which is exactly where a shared link
  // gets opened — middle-clicked now, read later.
  if(n < 25) setTimeout(() => {
    // If the page has moved for any reason other than us, the reader is
    // scrolling and this must stop fighting them.
    if(Math.abs(window.scrollY - y) > 2) return;
    if(Math.abs(r.getBoundingClientRect().top - stickyOffset() - 8) > 4)
      scrollRowToTop(r, n + 1);
  }, 120);
}

function goSite(key){
  // A link to one site opens that site's page. The table's filters are
  // left exactly as they were: the page shows regardless of what the
  // table is filtered to, and back returns the reader to the state they
  // left — which is the point of having a page rather than a row.
  const r=document.querySelector('tr.site[data-key="'+CSS.escape(key)+'"]');
  if(r){
    openSite(r);
  } else {
    // A link to a site this release does not contain — an older key, or
    // a site retired by a re-materialisation. Say so rather than
    // silently landing the reader on an unfiltered table.
    show('sites', true);
    const n=document.getElementById('n');
    if(n) n.textContent='That site is not in this release';
  }
  return false;
}
// A site's own address. Keys carry slashes — SITE-Aberdeen/180242/DPP —
// so they are encoded going in and decoded coming out; fromHash already
// decodes. replaceState rather than push, to match how the tabs behave:
// the back button steps between views, not between rows.
function siteHash(key){
  history.replaceState(null,'','#site-'+encodeURIComponent(key));
}
function copySiteLink(key, el){
  const url=location.href.split('#')[0]+'#site-'+encodeURIComponent(key);
  // Put it in the address bar first, so the fallback below is always
  // true: whatever the clipboard does, the link is somewhere the reader
  // can get at it.
  siteHash(key);
  let settled=false;
  const say=(msg)=>{ if(settled) return; settled=true;
                     const was=el.textContent; el.textContent=msg;
                     setTimeout(()=>{el.textContent=was;}, 2200); };
  // The clipboard API needs a secure context *and* a focused document,
  // and when the document is not focused the promise can simply never
  // settle rather than rejecting — leaving a reader who clicked with no
  // feedback at all. Hence the timer: the message is guaranteed even if
  // the promise is not.
  setTimeout(()=>say('Copy it from the address bar'), 700);
  if(navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(url).then(
      ()=>say('Link copied'), ()=>say('Copy it from the address bar'));
  } else {
    const t=document.createElement('textarea');
    t.value=url; t.style.position='fixed'; t.style.opacity='0';
    document.body.appendChild(t); t.select();
    try{ say(document.execCommand('copy') ? 'Link copied'
                                          : 'Copy it from the address bar'); }
    catch(e){ say('Copy it from the address bar'); }
    document.body.removeChild(t);
  }
  return false;
}
"""

JS = """
function sticky(){
  const nav=document.querySelector('nav.top');
  const navH=nav?nav.getBoundingClientRect().height:41;
  const bar=document.querySelector('.view.on .controls');
  const barH=bar?bar.getBoundingClientRect().height:0;
  const r=document.documentElement.style;
  r.setProperty('--nav-h', navH+'px');
  r.setProperty('--th-top', (navH+barH)+'px');
  const wrap=document.getElementById('mapwrap');
  if(wrap && wrap.offsetParent){
    r.setProperty('--map-top',
      (wrap.getBoundingClientRect().top + window.scrollY) + 'px');
  }
}
addEventListener('resize', sticky);
// Read from the DOM, never hand-listed. Two hardcoded arrays of view
// names — one here and one for the hash router — is one list too many:
// the Operators tab shipped in 2.2 missing from both, so selecting it
// switched every view off and none on, and the page went blank. A tab
// that exists in the markup is a tab, and that is the only definition.
const VIEWS=[...document.querySelectorAll('section.view')]
  .map(s=>s.id.replace(/^view-/,''));
function show(v, quiet){
  // Any tab away from an open site returns its panel to the table, so
  // the next open starts from a row that still has one.
  if(v!=='site' && openKey) closeSite(false);
  for(const k of VIEWS){
    const el=document.getElementById('view-'+k), tb=document.getElementById('tab-'+k);
    if(el) el.classList.toggle('on', k===v);
    // The site page has no tab of its own: it is a place inside Sites,
    // and the Sites tab stays lit while a reader is on it.
    if(tb) tb.setAttribute('aria-selected', k===v || (v==='site' && k==='sites'));
  }
  window.scrollTo(0,0);
  sticky();
  // The map sizes itself from its container, which has no dimensions
  // while the tab is hidden — so it has to draw once it is on screen.
  if(v==='map' && typeof drawMap==='function' && map.el) soon(drawMap);
  // The tab lives in the URL so a refresh returns to where you were, the
  // back button steps between tabs, and a dictionary entry can be linked.
  if(!quiet) history.replaceState(null,'','#'+v);
}
// Same source as show(): a view is linkable because it exists, not
// because someone remembered to add it here.
const TABS=VIEWS;
function fromHash(){
  const h=decodeURIComponent(location.hash.replace(/^#/,''));
  if(h.startsWith('dict-')){
    show('dict', true);
    const el=document.getElementById(h);
    if(el) soon(()=>el.scrollIntoView({block:'center'}));
  } else if(h.startsWith('site-')){
    // A link straight to one open site. goSite clears the filters
    // first, because a shared link has to work for someone whose
    // filters are not the sender's — and the default filter hides
    // sites under 100 MW.
    goSite(h.slice(5));
  } else if(h.startsWith('who:')||h.startsWith('cohort:')){
    // A filtered table, sent as a link. The tab comes first so the
    // rows exist to be filtered.
    show('sites', true);
    who=''; cohort='';
    for(const part of h.split(';')){
      if(part.startsWith('who:')) who=part.slice(4);
      else if(part.startsWith('cohort:')) cohort=part.slice(7);
    }
    paintChips(); apply(); sticky(); filterHash();
  } else if(TABS.includes(h)){
    show(h, true);
  }
}
addEventListener('hashchange', ()=>{fromHash(); paintWhoBar();});
// One row open at a time, so that the address bar always names exactly
// what is on screen and a copied URL means what the sender saw. Rows
// used to expand independently; Luke traded that for an unambiguous
// link, on the grounds that shareable links are the better way to hold
// several sites at once — one per tab, each with its own address.
/* The site page. The panel's markup lives once, in the <tr class="detail">
   after each row — that is what keeps an 8 MB page from being a 16 MB
   one, and it is what scripts/release_diff.py counts links in. Opening a
   site MOVES that panel into the page's host element and hands it back
   on the way out, so the page and the row can never show two versions
   of one site. One site at a time, by construction. */
let openKey=null, openTr=null, openCell=null;
function openSite(tr){
  if(openKey) closeSite(false);
  const key=tr.dataset.key;
  const cell=tr.nextElementSibling.firstElementChild;
  const host=document.getElementById('sitehost');
  while(cell.firstChild) host.appendChild(cell.firstChild);
  openKey=key; openTr=tr; openCell=cell;
  tr.classList.add('open');
  const name=tr.querySelector('td strong'), where=tr.querySelector('td .q');
  document.getElementById('sitetitle').textContent=name?name.textContent:key;
  document.getElementById('sitewhere').textContent=where?where.textContent:'';
  document.getElementById('sitekey').textContent=key;
  show('site', true);
  siteHash(key);
  window.scrollTo(0,0);
}
function closeSite(navigate){
  if(!openKey) return;
  const host=document.getElementById('sitehost');
  while(host.firstChild) openCell.appendChild(host.firstChild);
  const tr=openTr;
  tr.classList.remove('open');
  openKey=null; openTr=null; openCell=null;
  if(navigate!==false){
    // Back to the table as the reader left it — filters, chips, sort —
    // with the row they came from at the top. filterHash() restores the
    // address bar to the filter state, or #sites.
    show('sites', true);
    filterHash();
    soon(()=>scrollRowToTop(tr));
  }
}
function backToSites(){ closeSite(true); return false; }
document.querySelectorAll('tr.site').forEach(tr=>tr.addEventListener('click',e=>{
  if(e.target.closest('a, button'))return;
  openSite(tr);
}));
/* Operator rows, same gesture. No hash for these: an operator is not a
   shareable object in this release, and a second hash prefix would
   compete with the #site- links the panel is full of. */
document.querySelectorAll('tr.op').forEach(tr=>tr.addEventListener('click',e=>{
  if(e.target.closest('a'))return;
  const was=tr.classList.contains('open');
  document.querySelectorAll('tr.op.open').forEach(o=>{
    o.classList.remove('open'); o.nextElementSibling.classList.remove('on');});
  if(!was){tr.classList.add('open'); tr.nextElementSibling.classList.add('on');}
}));
const rows=[...document.querySelectorAll('tr.site')];
const q=document.getElementById('q'),f=document.getElementById('f'),
      o=document.getElementById('o'),n=document.getElementById('n');
function apply(){
  const s=q.value.toLowerCase().trim(), mode=f.value, org=o.value; let shown=0;
  for(const r of rows){
    let ok=(!s||r.dataset.hay.includes(s));
    if(ok&&who)              ok=r.dataset.who.split('|').includes(who);
    if(ok&&cohort)           ok=('|'+r.dataset.cohorts+'|').indexOf('|'+cohort+'|')>=0;
    if(ok&&mode==='known')   ok=r.dataset.known==='1';
    if(ok&&mode==='unknown') ok=r.dataset.known!=='1';
    if(ok&&mode==='energy')  ok=r.dataset.near!=='';
    if(ok&&mode==='power')   ok=r.dataset.mw!=='';
    if(ok&&mode==='prov')    ok=r.dataset.prov==='1';
    if(ok&&org)              ok=r.dataset.origin.indexOf(org)>=0;
    // Default is to remove only what is *known* to be small. A site with
    // no disclosed figure has not been shown to be under 100 MW, and
    // dropping it silently would turn an unread document into a fact.
    if(ok&&big.getAttribute('aria-pressed')==='true'){
      const v=r.dataset.mw;
      ok = v==='' ? !unk.checked : parseFloat(v)>=100;
    }
    r.style.display=ok?'':'none';
    r.nextElementSibling.style.display=ok?'':'none';
    if(ok)shown++;
  }
  n.textContent=shown+' of '+rows.length+' sites';
  // Nothing to project is not a map worth opening.
  document.getElementById('seemap').disabled = shown===0;
}
// Who's behind it. One organisation at a time — the chips answer "show
// me this operator's sites", and a multi-select would answer a question
// nobody asked while making the URL ambiguous. The state is in the hash
// so a filtered table is a link somebody can send.
let who='', cohort='';
// The two chip groups compose (an operator's sites that are also silent
// on capacity) and the hash carries both, so the URL always says what
// the table shows: #who:virtus;cohort:read_in_full_silent.
function filterHash(){
  const parts=[];
  if(who) parts.push('who:'+encodeURIComponent(who));
  if(cohort) parts.push('cohort:'+encodeURIComponent(cohort));
  history.replaceState(null,'', parts.length ? '#'+parts.join(';') : '#sites');
}
function paintChips(){
  document.querySelectorAll('#whochips .chip').forEach(c=>{
    const on = (c.dataset.who||'')===who;
    c.classList.toggle('on', on); c.setAttribute('aria-pressed', on);});
  document.querySelectorAll('button.who').forEach(b=>
    b.classList.toggle('on', b.dataset.who===who));
  document.querySelectorAll('#cohortchips .chip').forEach(c=>{
    const on = (c.dataset.cohort||'')===cohort;
    c.classList.toggle('on', on); c.setAttribute('aria-pressed', on);});
}
function setWho(k){
  who = (who===k) ? '' : k;
  paintWhoBar(); paintChips(); apply(); sticky(); filterHash();
  return false;
}
/* The active organisation filter, said out loud. A badge click is
   invisible once the rows move, and a reader who cannot see what is
   filtering the table reads a subset as the whole. */
function paintWhoBar(){
  const bar=document.getElementById('whobar');
  if(!bar) return;
  bar.hidden = !who;
  if(who){
    const b=document.querySelector('tr.site[data-who~="'+who+'"] .who')
         || document.querySelector('[data-whoname="'+who+'"]');
    document.getElementById('whonow').textContent =
      (b ? b.getAttribute('data-whoname') || b.textContent.trim() : who);
  }
}
function setCohort(k){
  cohort = (cohort===k) ? '' : k;
  paintChips(); apply(); sticky(); filterHash();
  return false;
}
// A Signals card's "open in table": the cohort on, nothing else.
function openCohort(k){
  show('sites', true);
  who=''; cohort=k;
  paintChips(); apply(); sticky(); filterHash();
  window.scrollTo(0,0);
  return false;
}
const big=document.getElementById('big'), unk=document.getElementById('unk'),
      unklab=document.getElementById('unklab');
big.addEventListener('click',()=>{
  const on=big.getAttribute('aria-pressed')!=='true';
  big.setAttribute('aria-pressed', on);
  unklab.classList.toggle('off', !on);
  unk.disabled=!on;
  apply(); sticky();
});
unk.addEventListener('change',apply);
unk.disabled=true; unklab.classList.add('off');
[q,f,o].forEach(el=>el.addEventListener('input',apply));
document.getElementById('seemap').addEventListener('click', seeAllOnMap);
function wire(sel){
  document.querySelectorAll(sel+' > thead th').forEach((th,i)=>th.addEventListener('click',()=>{
    const tb=th.closest('table').tBodies[0];
    const num=th.dataset.num==='1', dir=th.dataset.dir==='asc'?-1:1;
    th.dataset.dir=dir===1?'asc':'desc';
    const pairs=[]; let cur=null;
    [...tb.rows].forEach(r=>{
      if(r.classList.contains('detail')&&cur){pairs[pairs.length-1][1]=r;}
      else {pairs.push([r,null]); cur=r;}
    });
    pairs.sort((a,b)=>{
      const x=a[0].cells[i]?.dataset.v??a[0].cells[i]?.innerText??'',
            y=b[0].cells[i]?.dataset.v??b[0].cells[i]?.innerText??'';
      return num?((parseFloat(x)||-1)-(parseFloat(y)||-1))*dir
                :String(x).localeCompare(String(y))*dir;
    }).forEach(([r,d])=>{tb.appendChild(r); if(d)tb.appendChild(d);});
  }));
}
wire('#tbl-sites'); wire('#tbl-apps'); wire('#tbl-energy');
apply(); sticky(); fromHash(); paintWhoBar(); addEventListener('load', ()=>{sticky(); fromHash();});

// A column heading explains itself: jump to its dictionary entry.
function goDict(id){
  show('dict', true);
  history.replaceState(null,'','#'+id);
  const el=document.getElementById(id);
  if(el){el.scrollIntoView({block:'center'}); el.classList.add('flash');
         setTimeout(()=>el.classList.remove('flash'), 1600);}
}
"""


def main() -> int:
    # Nothing is written from adjudications nobody has
    # corrected. See dcp/adjudication_gate.py.
    adjudication_gate.require_corrected()
    ap = argparse.ArgumentParser(description=__doc__)
    # Derived from the newest release folder, never named. Run bare
    # during the 2.1 regeneration these defaulted to phase1_build and
    # "1", so the front page would have been stamped "phase 1 release"
    # and written into a folder two releases old. See dcp/release.py.
    _rel = release.latest_release_dir()
    ap.add_argument("--out", type=Path,
                    default=(_rel / "reader.html") if _rel
                            else Path("data/exports/phase1_build/reader.html"))
    ap.add_argument("--phase", default=release.phase_of(_rel) or "1",
                    help="stamps the title, the header and the database "
                         "filename; defaults to the newest release folder's "
                         "phase, so starting a NEW phase means passing it")
    ap.add_argument("--publish", type=Path, default=None,
                    help="also write here — index.html at the repository root, "
                         "which is what the EdgeOne deployment serves")
    # §7d: the readings are rendered only once a person has read the
    # twenty-site sample. A release that has to go out before that
    # checkpoint builds without them rather than waiting or shipping
    # unreviewed ones; nothing else on the page changes.
    ap.add_argument("--no-readings", action="store_true",
                    help="build without the machine readings, for a release "
                         "made before the sample has been reviewed")
    args = ap.parse_args()

    hv = _handover()
    from dcp import capacity_claims as ccl
    from dcp import consumption_context as cc
    from dcp import entities
    from dcp import external_aggregates as extagg
    from dcp import machine_reading as mreading
    from dcp import operator_disclosure as odis
    from dcp import organisations
    from dcp import site_cohorts
    from dcp import origin as origin_mod
    from dcp import proposal as prop
    from dcp import signals as sig
    from dcp import site_profile, site_scale as scale

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(hv.SITE_SQL); site_rows = cur.fetchall()
        cur.execute(hv.APP_SQL); app_rows = cur.fetchall()
        cur.execute(hv.BARBOUR_ONLY_SQL); barbour_rows = cur.fetchall()
        cur.execute(hv.NSIP_SQL); nsip_rows = cur.fetchall()
        # Coverage, counted over the applications that belong to a live
        # site — the ones this page shows. The wider corpus also holds
        # documents for applications that were reviewed and not clustered
        # into a data-centre site; those are reported separately rather
        # than folded into a headline that implies they are in scope.
        cur.execute("""
          WITH member AS (
            SELECT DISTINCT a.id FROM applications a
            JOIN site_members m ON m.application_id=a.id AND m.retired_at IS NULL
            JOIN sites s ON s.id=m.site_id AND s.retired_at IS NULL),
          docs AS (SELECT application_id, count(*) n FROM documents GROUP BY 1),
          rd AS (SELECT d.application_id, count(DISTINCT dl.document_id) n
                 FROM deepread_log dl JOIN documents d ON d.id=dl.document_id
                 WHERE dl.read_state='read' GROUP BY 1),
          outc AS (SELECT DISTINCT ON (application_id) application_id, outcome
                   FROM acquisition_outcome ORDER BY application_id, id DESC)
          SELECT coalesce(d.n,0), coalesce(r.n,0), o.outcome, m.id
          FROM member m
          LEFT JOIN docs d ON d.application_id=m.id
          LEFT JOIN rd r ON r.application_id=m.id
          LEFT JOIN outc o ON o.application_id=m.id""")
        cover_rows = cur.fetchall()
        cover = [(a, b, c) for a, b, c, _ in cover_rows]
        # The same applications counted over prose alone. The analysis
        # table below says how many applications are fully read, and an
        # application is not "partially analysed" because a location plan
        # in it was skipped by design — that reading of it made 78% of
        # the corpus look outstanding when 1% of the prose was.
        cur.execute("""
          SELECT d.id, d.application_id,
                 EXISTS (SELECT 1 FROM deepread_log dl
                         WHERE dl.document_id=d.id AND dl.read_state='read'),
                 EXISTS (SELECT 1 FROM deepread_log dl
                         WHERE dl.document_id=d.id AND dl.read_state='no_text')
          FROM documents d
          WHERE EXISTS (SELECT 1 FROM site_members m
                        JOIN sites s ON s.id=m.site_id AND s.retired_at IS NULL
                        WHERE m.application_id=d.application_id
                          AND m.retired_at IS NULL)""")
        # Prose is tiers A and B, exactly as site_profile.load_coverage_detail
        # defines it — the repetitive tier is a category of its own and is
        # reported as one, never folded into either side. This loop counts
        # the same thing that function does, at application granularity
        # rather than site, because the two are shown on the same page and
        # a reader comparing them is entitled to find them consistent.
        # An earlier version of this counted every non-drawing document as
        # prose awaiting analysis, which over-stated the per-application
        # backlog by the whole of tier C.
        plan_by_id = deepread_select.universe_plan(conn)
        _prose: dict[int, list[int]] = {}
        n_no_text = 0
        for doc_id, app_id, was_read, no_text in cur.fetchall():
            plan = plan_by_id.get(doc_id)
            if plan is None or plan.tier in ("skip", "C"):
                continue
            if no_text and not was_read:
                # Held, classified as prose, and containing no words:
                # photographs of site notices, plans filed as JPEGs. Both
                # tesseract and Apple Vision read them as blank, so no
                # further pass will move them. Counting them as awaiting
                # analysis would leave a residue that never clears and
                # imply a backlog that does not exist; they are named
                # instead, which is what the corpus can honestly say.
                n_no_text += 1
                continue
            e = _prose.setdefault(app_id, [0, 0])
            e[0] += 1
            e[1] += bool(was_read)
        cover_prose = [tuple(_prose.get(app_id, (0, 0))) for *_, app_id in cover_rows]
        cur.execute("""SELECT count(*) FROM documents d WHERE NOT EXISTS (
                         SELECT 1 FROM site_members m JOIN sites s ON s.id=m.site_id
                         WHERE m.application_id=d.application_id
                           AND m.retired_at IS NULL AND s.retired_at IS NULL)""")
        n_outside = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM documents"); n_docs_all = cur.fetchone()[0]
        cur.execute("""SELECT count(DISTINCT document_id) FROM deepread_log
                       WHERE read_state='read'"""); n_read = cur.fetchone()[0]
        cur.execute("""SELECT s.site_key, array_agg(DISTINCT t)
                       FROM sites s
                       JOIN site_members m ON m.site_id=s.id AND m.retired_at IS NULL
                       JOIN applications a ON a.id=m.application_id
                       CROSS JOIN LATERAL unnest(coalesce(a.discovered_via,'{}')) t
                       WHERE s.retired_at IS NULL GROUP BY s.site_key""")
        origins = {k: origin_mod.routes_for(t) for k, t in cur.fetchall()}
        # Why a site holds nothing. Read from the recorded outcome of each
        # retrieval attempt rather than inferred from the absence itself,
        # so "checked, publishes nothing" stays distinguishable from
        # "never tried".
        cur.execute("""
            SELECT s.site_key, array_agg(DISTINCT coalesce(o.outcome,'untried'))
            FROM sites s
            JOIN site_members m ON m.site_id=s.id AND m.retired_at IS NULL
            JOIN applications a ON a.id=m.application_id
            LEFT JOIN LATERAL (
              SELECT outcome FROM acquisition_outcome ao
              WHERE ao.application_id=a.id ORDER BY ao.id DESC LIMIT 1) o ON true
            WHERE s.retired_at IS NULL
            GROUP BY s.site_key""")
        site_outcomes = dict(cur.fetchall())
        # Which application each headline quantity came from. A site can
        # span several buildings across several councils, and the site
        # row takes the largest of each quantity independently — so its
        # IT load and its total site demand may describe different
        # buildings, and occasionally the total reads lower than the IT
        # load. Both figures are right; naming their source dissolves the
        # apparent contradiction and makes each one checkable.
        cur.execute("""
            SELECT site_key, quantity_type, application_ref FROM (
              SELECT s.site_key, pa.quantity_type, a.application_ref,
                     row_number() OVER (PARTITION BY s.site_key, pa.quantity_type
                                        ORDER BY pa.value_mw DESC,
                                                 pa.id DESC) AS rn
              FROM power_adjudication pa
              JOIN applications a ON a.id = pa.application_id
              JOIN site_members m ON m.application_id = a.id AND m.retired_at IS NULL
              JOIN sites s ON s.id = m.site_id
              WHERE s.retired_at IS NULL AND pa.verdict = 'site_capacity'
                AND pa.value_mw IS NOT NULL) t
            WHERE rn = 1""")
        power_src = {(k, q): r for k, q, r in cur.fetchall()}

        # External capacity claims: grid-register figures attached to
        # sites by hand-adjudicated inference (dcp/capacity_claims). They
        # render in their own box, never into the site's power estimate —
        # a contracted ceiling is not the quantity a planning application
        # states, and the divergence between the two is the finding.
        claims_by_site = ccl.load_site_claims(cur)
        n_claims_total = len(ccl.load_claim_rows(cur))

        # A figure adjudicated as somebody else's must not appear in this
        # list looking like the site's own. Ten of them did: the panel
        # ranks power findings to the top, and "22,700 MW" is a Savills
        # market forecast sitting in a Chiltern application. They are kept
        # rather than hidden -- a reader seeing what the documents contain
        # is the point -- but each is labelled with whose it is.
        cur.execute(FINDINGS_SQL, (FINDINGS_PER_SITE,))
        findings = defaultdict(list)
        _raw_findings = cur.fetchall()

        # The label audit (§4.1e): where it says a row's family does not
        # fit its text, the row is DEMOTED to the family it belongs
        # under, not dropped. Luke, 2026-08-24: the quote is real and
        # verified — only the filing is wrong — so removing it costs a
        # reporter a true quote, while moving it stops the false
        # impression and keeps the evidence. The row says where it was
        # filed, because a silent move is a second unrecorded judgement.
        #
        # Guarded on the table existing: a build against a database
        # without migration 025 shows exactly what it showed before.
        label_verdicts: dict[int, tuple[str, str]] = {}
        cur.execute("SELECT to_regclass('public.finding_label_audit')")
        if cur.fetchone()[0]:
            cur.execute("""
                SELECT DISTINCT ON (finding_id) finding_id, verdict,
                       coalesce(suggested_family, '')
                FROM finding_label_audit
                ORDER BY finding_id, inserted_at DESC, id DESC""")
            label_verdicts = {fid: (v, fam) for fid, v, fam in cur.fetchall()
                              if v == "does_not_fit"}
        n_demoted = 0
        for k, st, vt, vn, vu, verdict, fam, fid in _raw_findings:
            filed_as = ""
            moved = label_verdicts.get(fid)
            if moved and moved[1] and moved[1] != fam:
                filed_as, fam = fam, moved[1]
                n_demoted += 1
            findings[k].append((st, vt, vn, vu, verdict, fam, filed_as))
        cur.execute(FAMILY_COUNTS_SQL)
        family_counts: dict[str, dict[str, int]] = defaultdict(dict)
        for k, fam, n in cur.fetchall():
            family_counts[k][fam] = int(n)

    # Confirmed alias members only, so a proposal in the priors file
    # changes nothing that a reader sees until a person has confirmed it.
    alias_index = organisations.alias_index(organisations.load_groups())
    with db.connect() as conn:
        profiles = site_profile.load_site_profiles(conn)
        coverage = site_profile.load_coverage(conn)
        # The cohorts, computed here and nowhere else on this page: the
        # Signals cards, the chips and each row's memberships all read
        # this one list, so a count on a card is the number of rows the
        # chip leaves.
        cohorts = site_cohorts.compute_all(conn)
        # The machine readings (§7b–e): the latest per site that passed
        # the gate, and the reason for any site whose latest was refused.
        # Rendered collapsed on the site page, labelled as what they are;
        # never exported.
        readings, readings_withheld = mreading.load_latest(conn)
        if args.no_readings:
            readings, readings_withheld = {}, {}
        cited_docs = mreading.cited_documents(conn, readings)
        # `held`/`read` are every document; `prose_*` are the ones the
        # deep-read is for. The caveats run off prose, the counts shown
        # to a reporter run off both, and they are different numbers on
        # purpose — see site_profile.load_coverage_detail.
        cov_detail = site_profile.load_coverage_detail(conn)
        # The same loader the workbook uses. Passing None here was the
        # reason 43 sites read "no capacity disclosed" in this view and
        # carried a floor-area estimate in the workbook — one dataset
        # answering "how big is this?" two ways.
        site_floorspace = scale.load_site_floorspace(conn)
        # The stamp's findings count, counted the way a site panel counts
        # it: distinct passages rather than rows, because several models
        # reading one sentence is corroboration, not volume.
        with conn.cursor() as _cur:
            # Scoped to live sites, like every other number in the stamp:
            # the corpus also holds findings for applications that were
            # reviewed and not clustered into a data-centre site, and a
            # stamp that counted those beside "456 sites · 1,709
            # applications" would be describing a different thing in the
            # same breath. 1,009,220 against 1,002,774 today.
            _cur.execute("""
                SELECT count(DISTINCT (f.document_id, md5(f.evidence_text),
                                       f.evidence_page))
                FROM findings f
                JOIN site_members m ON m.application_id = f.application_id
                     AND m.retired_at IS NULL
                JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL""")
            n_findings_total = _cur.fetchone()[0]
    site_names = {r[0]: r[2] for r in site_rows}
    cohorts_of_site: dict[str, list[str]] = defaultdict(list)
    cohort_title: dict[str, str] = {}
    for _c in cohorts:
        cohort_title[_c.cohort.key] = _c.cohort.title
        for _m in _c.result.members:
            cohorts_of_site[_m.site_key].append(_c.cohort.key)

    apps_by_site = defaultdict(list)
    for r in app_rows:
        apps_by_site[r[0]].append(r)

    nsip = [{"ref": r[0], "status": r[1], "lat": r[2], "lon": r[3],
             "name": r[4] or r[0], "applicant": r[5] or "", "type": r[6] or "",
             "region": r[7] or "", "stage": r[8] or "",
             "cap": "; ".join(r[9] or []), "desc": r[10] or "", "url": r[13]}
            for r in nsip_rows if r[2] is not None and r[3] is not None]

    def nearest(lat, lon):
        if lat is None or lon is None or not nsip:
            return None
        best = min(nsip, key=lambda p: hv._haversine_km(lat, lon, p["lat"], p["lon"]))
        return best, round(hv._haversine_km(lat, lon, best["lat"], best["lon"]), 1)

    site_mw_values: list[float] = []
    power_basis_counts: dict[str, int] = {}
    map_points: list[dict] = []
    drive = hv._drive_folder_map()
    drive_apps = hv._drive_application_map()
    drive_csv = hv._drive_findings_map()
    n_apps_total = len(cover)
    n_docs = sum(c[0] for c in cover)
    # For the coverage sidebar (§2): how the applications divide on
    # whether a register published anything, which is the boundary the
    # card exists to state.
    n_apps_with_docs = sum(1 for c in cover if c[0])
    n_apps_no_docs = n_apps_total - n_apps_with_docs
    # 'none_published' is the outcome vocabulary's own word for
    # "checked, and the council has published nothing" — completed work
    # rather than a gap, which is exactly the distinction this row of
    # the sidebar exists to draw. I guessed 'empty' first and the card
    # said nought had been checked.
    n_apps_checked_empty = sum(1 for c in cover
                               if not c[0] and (c[2] or "") == "none_published")
    n_read = sum(c[1] for c in cover)
    pct = 100 * n_read // n_docs if n_docs else 0
    # The same corpus, split by what the methodology does with it. The
    # undivided ratio is honest and unusable as a headline: it says 78%
    # because it counts 5,751 drawings the deep-read skips by design and
    # the objection letters it samples on purpose. A reporter reads 78%
    # as "a fifth of the evidence is unexamined", when the prose that can
    # carry a disclosure is 99% read.
    n_prose      = sum(c["prose_held"] for c in cov_detail.values())
    n_prose_read = sum(c["prose_read"] for c in cov_detail.values())
    pct_prose = 100 * n_prose_read // n_prose if n_prose else 0
    n_graphical  = sum(c["graphical"] for c in cov_detail.values())
    n_sampled    = sum(c["sampled_held"] for c in cov_detail.values())
    n_sampled_rd = sum(c["sampled_read"] for c in cov_detail.values())

    def _pc(x, of=None):
        of = n_apps_total if of is None else of
        return f"{100 * x / of:.1f}%" if of else "—"

    have = [c for c in cover if c[0]]
    none_held = [c for c in cover if not c[0]]
    by_outcome = defaultdict(int)
    for c in none_held:
        by_outcome[c[2] or "untried"] += 1
    # Deliberately phrased as work states, not as absence. An application
    # whose register genuinely publishes nothing is finished work, and
    # counting it as a gap makes the dataset look permanently incomplete.
    OUTCOMES = [
        ("none_published", "Register publishes no documents",
         "Checked; the council has published nothing. Completed work, not a gap."),
        ("no_adapter", "Portal not yet readable",
         "The council runs portal software this pipeline cannot yet read."),
        ("untried", "Not yet attempted",
         "Queued for the next acquisition pass."),
        ("error", "Retrieval failed, will retry",
         "A transient failure; these are retried, not settled."),
        ("portal_blocked", "Portal blocks automated access",
         "Retrieved by hand where the site warrants it."),
        ("login_required", "Documents behind a login",
         "Not retrievable without an account."),
    ]
    have_prose = [c for c in cover_prose if c[0]]
    full_read = sum(1 for c in have_prose if c[1] >= c[0])
    part_read = sum(1 for c in have_prose if 0 < c[1] < c[0])
    un_read = sum(1 for c in have_prose if c[1] == 0)

    app_stats_rows = "".join(
        f"<tr><th scope='row'>{esc(lbl)}</th><td class='n'>{by_outcome[k]:,}</td>"
        f"<td class='n'>{_pc(by_outcome[k])}</td><td class='help'>{esc(note)}</td></tr>"
        for k, lbl, note in OUTCOMES if by_outcome[k])
    body = []

    # DESNZ consumption context, loaded once so every panel compares
    # against the same national change; coverage counted and printed so
    # unmapped sites are a number, never a silent gap.
    # A machine's reading of a site's documents, rendered collapsed and
    # labelled as what it is. Only where a reading exists and passed the
    # gate; a withheld reading is a one-line reason and nothing else,
    # since the refusal is itself a fact about the site's documents.
    # The label states; it does not instruct.
    n_readings_rendered = n_readings_withheld = n_paragraphs_withheld = 0

    def _cite(q):
        """Where a quote is from: the document, linked to the register's
        copy, with its page; or the application whose adjudicated figure
        it is."""
        doc_id = q.get("document_id")
        if doc_id:
            d = cited_docs.get(int(doc_id))
            page = f', p.{q["page"]}' if q.get("page") else ""
            if d and d["url"]:
                return (f'<a href="{esc(d["url"])}" target="_blank" rel="noopener">'
                        f'{esc(d["title"])}</a>{page} · {esc(d["application_ref"])}')
            if d:
                return f'{esc(d["title"])}{page} · {esc(d["application_ref"])}'
            return f'document {doc_id}{page}'
        return f'application {esc(q.get("application_ref") or "")}, adjudicated figure'

    def reading_panel(key):
        nonlocal n_readings_rendered, n_readings_withheld, n_paragraphs_withheld
        r = readings.get(key)
        if not r:
            why = readings_withheld.get(key)
            if why:
                n_readings_withheld += 1
                return (f'<div class="box reading withheld"><h4>A machine\u2019s reading of '
                        f'this site\u2019s documents</h4><p class="help">Withheld: '
                        f'{esc(why)}. A reading is shown only where every figure in it '
                        f'carries a quote that verified against the documents.</p></div>')
            return ""
        n_readings_rendered += 1
        sections = (r["reading"] or {}).get("sections") or {}
        # Counted before the summary is written, because an omission a
        # reader cannot see is one they will assume did not happen: the
        # withheld line sits inside a panel that opens closed, so a
        # reader who never expands it learns nothing at all.
        held = sum(1 for paras in sections.values()
                   for para in (paras or []) if para.get("withheld"))
        body = []
        for sec, title in mreading.SECTION_TITLES.items():
            paras = sections.get(sec) or []
            if not paras:
                continue
            body.append(f"<h5>{esc(title)}</h5>")
            for para in paras:
                # gate-2.0: a paragraph the gate refused is a one-line
                # reason where it would have stood — the model's words
                # do not render, and the refusal is not hidden either.
                if para.get("withheld"):
                    n_paragraphs_withheld += 1
                    # The reason as a reader may have it: the failure and
                    # the document, never the model's unverified words.
                    # The full reason is in the stored row and in the
                    # sample markdown a person checks (mreading.public_reason).
                    body.append(f'<p class="help rwithheld">One paragraph withheld: '
                                f'{esc(mreading.public_reason(para["withheld"]))}.</p>')
                    continue
                quotes = "".join(
                    f'<li>\u201c{esc(" ".join((q.get("quote") or "").split()))}\u201d '
                    f'<span class="q">{_cite(q)}</span></li>'
                    for q in (para.get("quotes") or []))
                body.append(f'<p>{esc(para.get("text", ""))}</p>'
                            + (f'<ul class="rq">{quotes}</ul>' if quotes else ""))
        when = r["inserted_at"].strftime("%-d %B %Y") if r.get("inserted_at") else ""
        return (f'<details class="box reading"><summary><h4>A machine\u2019s reading of '
                f'this site\u2019s documents</h4><span class="help">Generated by '
                f'{esc(r["model"])} on {esc(when)} from {r["documents_read"]} documents '
                f'({r["pages_read"]} pages); prompt {esc(r["prompt_version"])}. '
                f'Not a finding. Every rendered figure carries a verbatim quote that was '
                f'verified against the documents before it was stored.'
                + ((f' {held} paragraphs are withheld, each with its reason '
                    f'where it would have stood.' if held != 1 else
                    ' One paragraph is withheld, with its reason where it '
                    'would have stood.') if held else '')
                + f'</span></summary>'
                f'<div class="rbody">{"".join(body)}</div></details>')

    # The who's-behind-it cell, and the key it filters on.
    #
    # What the badge shows is the most-stated thing known about the site,
    # in that order: the group a person has confirmed, else the end user
    # Barbour records, else Barbour's client. A name the documents merely
    # use often never reaches this column — that was the first version's
    # error, and it put Savills on seventeen rows. Where a site's badge
    # and its applicant of record are different organisations, both are
    # shown, because "Amazon, via Colliers International" is the fact and
    # either half alone is misleading.
    who_counts: dict[str, int] = defaultdict(int)

    def who_cell(prof):
        group = (prof.get("operator_group") or "").strip()
        primary = (prof.get("operator_primary") or "").strip()
        end_user = (prof.get("end_user") or "").strip()
        applicant = (prof.get("applicant_of_record") or "").strip()
        badge = group or primary
        if not badge:
            return {"filter_key": "", "sort": "zzz",
                    "cell": '<span class="q">not established</span>'}
        source = ("a confirmed alias group" if group else
                  "Barbour's end user" if end_user else
                  "Barbour's client")
        # Every operator Barbour states for the site, so that a chip for
        # any of them finds the site. A site record that covers an estate
        # holds several — the Slough Trading Estate record carries
        # Equinix, VIRTUS, Zenium and Iron Mountain — and a row that wore
        # one of those names, and answered only that one chip, would be
        # the site-fragmentation hazard HISTORY records, as a badge.
        operators = [n.strip() for n in (end_user or applicant).split(",") if n.strip()]
        if badge not in operators:
            operators.insert(0, badge)
        # The key a badge filters on is the alias GROUP where one is
        # confirmed, and the raw name otherwise. Luke, 2026-08-25: "no
        # one will want to filter to different names of the same group —
        # they want to see the group." Clicking Vantage Data Centres
        # Limited therefore finds VDC LHR11 Limited's rows too, which
        # is the whole point of confirming a group.
        def _fkey(name: str) -> str:
            g = organisations.group_for(name, alias_index)
            return entities.canonical_key(g.group if g else name)

        keys = [_fkey(n) for n in operators]
        for n in operators:
            who_counts[n] += 1
        others = len(operators) - 1
        if others >= 2:
            # An estate record: say so and name them all. No single
            # button, because no single organisation is behind it.
            names = ", ".join(operators)
            return {
                "filter_key": "|".join(keys), "sort": badge,
                # Each operator's own key, so the bar can name whichever
                # one a reader arrived by.
                "cell": (f'<span class="who multi" data-whoname="{esc(names)}" '
                         f'title="{esc(names)} — from {source}. '
                         f'This site record covers several operators’ premises; '
                         f'each one’s chip finds it.">{len(operators)} operators</span>'
                         f'<span class="q">{esc(trim(names, 60))}</span>')}
        via_bits = []
        if applicant and applicant != badge and not end_user.startswith(applicant):
            via_bits.append(f"via {trim(applicant, 34)}")
        if others:
            via_bits.append(f"and {trim(operators[1], 24)}")
        via = (f'<span class="q">{esc(" · ".join(via_bits))}</span>'
               if via_bits else "")
        return {
            "filter_key": "|".join(keys), "sort": badge,
            "cell": (f'<button type="button" class="who" data-who="{esc(keys[0])}" '
                     f'data-whoname="{esc(badge)}" '
                     f'title="{esc(badge)} — from {source}. '
                     f'Click to show only this organisation’s sites." '
                     f'onclick="event.stopPropagation();'
                     f'setWho(this.dataset.who)">{esc(trim(badge, 30))}</button>'
                     + via)}

    desnz = cc.load_series()
    ctx_mapped = ctx_unmapped = 0
    ctx_unrecognised: set[str] = set()
    claims_sites_rendered = claims_rows_rendered = 0
    for r in site_rows:
        (key, cls, name, lat, lon, csrc, councils, n_apps, refs, verdicts,
         docs, findings_n, it, tot, grid, gen, ncap, nexc, families,
         eref, edoc, manual, ptno, btitle, bstage, bvalue, bfloor,
         bsite, bplan, bdec, bauthority) = r
        prof = profiles.get(key, {})
        held, read = coverage.get(key, (docs or 0, 0))
        _cd = cov_detail.get(key, {})
        p_held = _cd.get("prose_held", held)
        p_read = _cd.get("prose_read", read)
        apps = apps_by_site.get(key, [])
        est = scale.power_estimate(it_load_mw=it, total_site_mw=tot, grid_mw=grid,
                                   generation_mw=gen,
                                   floorspace_sqm=site_floorspace.get(key),
                                   has_documents=bool(docs),
                                   prose_held=p_held, prose_read=p_read)
        cap_key, cap_label = site_profile.capacity_status(
            pre_application=(n_apps or 0) == 0, docs_held=p_held, docs_read=p_read,
            power_value_mw=est.value_mw, power_basis=est.basis)
        known = cap_key not in NOT_YET_KNOWN
        is_prov, prov_note = site_profile.provisional(p_held, p_read)
        if est.value_mw:
            # Only figures somebody stated. A floor-area estimate is
            # displayed on the row, where its basis sits beside it, but
            # it is kept out of the counts compared against Ofgem's
            # connection queue — the workbook draws the same line, and
            # the reason is in scale.DISCLOSED_BASES.
            if est.basis in scale.DISCLOSED_BASES:
                site_mw_values.append(est.value_mw)
            power_basis_counts[est.basis] = \
                power_basis_counts.get(est.basis, 0) + 1
        addr = max((a[15] or "" for a in apps), key=len, default="") or \
            ", ".join(councils or [])
        _reg = next((a[12] for a in sorted(
            apps, key=lambda x: str(x[5] or ""), reverse=True)
            if a[12] and not str(a[12]).startswith("file://")), "")
        if lat is not None and lon is not None:
            map_points.append({
                "k": "s", "id": key, "lat": lat, "lon": lon,
                # §8c: the map answers the active cohort chip.
                "c": list(cohorts_of_site.get(key, ())),
                "mw": est.value_mw, "t": (name or key)[:80],
                "h": " ".join(x.lower() for x in
                              (name or key, ", ".join(councils or []), addr) if x),
                "pop": (
                    f'<b>{esc(name or key)}</b><br><span class="help">'
                    f'{esc(", ".join(councils or []))}</span><br>'
                    + (f'<b>{mw_text(est.value_mw)} MW</b> '
                       f'<span class="help">{esc(est.basis)}</span><br>'
                       if est.value_mw else
                       f'<span class="help">{esc(est.basis)}</span><br>')
                    + (f'<span class="help">{held:,} documents, {p_read:,} of '
                       f'{p_held:,} prose analysed</span><br>' if held else
                       '<span class="help">no documents held</span><br>')
                    # A pin is a starting point, so the card carries the
                    # three places worth going next: the full row, the
                    # documents themselves, and the council's own register.
                    + '<span class="cardlinks">'
                    + f'<a href="#sites" onclick="return goSite(\'{esc(key)}\')">'
                      f'Open this site</a>'
                    + (f' · <a href="{esc(drive[hv._norm_key(key)])}" target="_blank" '
                       f'rel="noopener">Drive</a>'
                       if held and hv._norm_key(key) in drive else '')
                    + (f' · <a href="{esc(_reg)}" target="_blank" rel="noopener">'
                       f'Register</a>' if _reg else '')
                    + '</span>')})
        maplink = (f'<a href="#map" onclick="showMap(\'{esc(key)}\');return false"'
                   f' title="Show this site on the map">map</a>') if lat and lon else ""
        gmaps = (f'<a href="https://www.google.com/maps/search/?api=1&query={lat},{lon}"'
                 f' target="_blank" rel="noopener">Google Maps</a>') if lat and lon else ""
        full_desc = max((a[16] or "" for a in apps), key=len, default="") or (btitle or "")
        summary, descriptive = prop.summarise([a[16] for a in apps] or [btitle])
        summary = prop.tidy(summary)
        near = nearest(lat, lon)
        org = origins.get(key, [])
        env = sorted({s for a in apps for s in sig.environmental_signals(a[16] or "")})

        approws = []
        for a in sorted(apps, key=lambda x: str(x[5] or ""), reverse=True):
            portal = (f'<a href="{esc(a[12])}" target="_blank" rel="noopener">register</a>'
                      if a[12] and not str(a[12]).startswith("file://") else "—")
            durl = hv._drive_application_url(drive_apps, key, a[1])
            docs_cell = (f'<a href="{esc(durl)}" target="_blank" rel="noopener">'
                         f'{a[13] or 0}</a>' if durl else str(a[13] or 0))
            approws.append(
                f"<tr><td><strong>{esc(a[1])}</strong></td><td>{esc(a[3])}</td>"
                f"<td>{esc(a[4] or '—')}</td><td>{esc(str(a[5] or '—'))}</td>"
                f"<td>{esc(str(a[6] or '—'))}</td><td>{esc(a[7] or '—')}</td>"
                f"<td>{docs_cell}</td><td>{portal}</td></tr>"
                f"<tr><td colspan='8' class='help' style='padding-bottom:9px'>"
                f"{esc(trim(a[16], 320))}</td></tr>")
        apps_html = ("<table class='apps'><thead><tr><th>Reference</th><th>Council</th>"
                     "<th>Status</th><th>Received</th><th>Decided</th><th>Verdict</th>"
                     "<th>Documents</th><th>Source</th></tr></thead><tbody>"
                     + "".join(approws) + "</tbody></table>") if approws else \
            ("<p class='help'>No planning applications — known only from Barbour project "
             "intelligence, at pre-planning stage.</p>")

        # Grouped by family, families in the order the round-robin led
        # with them (adjudicated figures, then the power families, then
        # cooling, water, EIA, then the rest), rows within a family in
        # the order they were ranked. The first two of each family are
        # open; the rest of what was fetched sits behind "show all", and
        # the count says how many the family holds in total so that "3
        # of 41" is on the page rather than implied.
        #
        # The label audit READER_REDESIGN_PLAN §4.1e describes — a batch
        # flagging rows whose family does not match their text — does not
        # exist yet, so nothing is excluded on that ground; the family a
        # row sits under is the extractor's label, as ever.
        grouped: dict[str, list] = {}
        for st, vt, vn, vu, verdict, fam, filed_as in findings.get(key, []):
            grouped.setdefault(fam or "other", []).append(
                (st, vt, vn, vu, verdict, filed_as))
        fl = []
        n_shown = 0
        for fam, rows_ in grouped.items():
            items = []
            for st, vt, vn, vu, verdict, filed_as in rows_:
                num = f" <strong>{vn:g} {esc(vu or '')}</strong>" if vn is not None else ""
                # Adjudicated as describing something other than this site.
                not_ours = {
                    "market_context": "market or sector context, not this site",
                    "policy_target":  "a policy target, not this site",
                    "comparator":     "a different named scheme, not this site",
                }.get(verdict)
                tag = (f" <span class='q' style='color:#b3261e'>[{esc(not_ours)}]</span>"
                       if not_ours else "")
                # A moved row says where it was moved from. The
                # extractor's label is still on the row; what changed is
                # only which heading a reader finds it under.
                moved = (f" <span class='q'>[filed as {esc(filed_as)}]</span>"
                         if filed_as else "")
                items.append(f"<li><span class='st'>{esc(st)}</span>{num}{tag}{moved} — "
                             f"{esc(trim(vt,190))}</li>")
            n_shown += len(items)
            total = family_counts.get(key, {}).get(fam, len(items))
            head = (f"<span class='famname'>{esc(humanise(fam))}</span> "
                    f"<span class='q'>{len(items)} of {total:,} shown</span>"
                    if total > len(items) else
                    f"<span class='famname'>{esc(humanise(fam))}</span> "
                    f"<span class='q'>{total:,}</span>")
            first, rest = items[:2], items[2:]
            fl.append(
                f"<div class='fam'><div class='famhead'>{head}</div>"
                f"<ul class='find'>{''.join(first)}</ul>"
                + (f"<details class='famrest'><summary>Show {len(rest)} more</summary>"
                   f"<ul class='find'>{''.join(rest)}</ul></details>" if rest else "")
                + "</div>")
        if fl:
            findings_html = "<div class='fams'>" + "".join(fl) + "</div>"
            if findings_n and findings_n > n_shown:
                # Not the workbook: it holds per-site counts and the
                # adjudicated figures, and a reporter sent there for the
                # findings themselves found nothing. The full set lives in
                # each site's Drive folder (the findings CSV, beside the
                # documents the rows cite) and in the DuckDB findings table.
                # Named by role rather than by filename: the CSV carries the
                # site's own name now, so there is no one string to quote.
                csv_url = drive_csv.get(hv._norm_key(key), "")
                where = (f"<a href='{esc(csv_url)}' target='_blank' rel='noopener'>"
                         f"this site's findings CSV</a>" if csv_url else
                         "the findings CSV in this site's Drive folder")
                findings_html += (f"<p class='help'>Showing {n_shown} of {findings_n:,} "
                                  f"verified findings; the full set is in {where}, "
                                  f"and in the DuckDB file.</p>")
        elif held and read >= held:
            # Read in full and still nothing: a null result, not a gap.
            # The earlier wording said "not analysed" whenever the list was
            # empty, which contradicted the power caveat on the same panel.
            findings_html = ("<p class='help'>This site's documents were read in full "
                             "and produced no findings in the categories extracted. "
                             "That is a result, not a gap: the documents are held and "
                             "were analysed.</p>")
        elif held and read:
            findings_html = (f"<p class='help'>Nothing found yet in the {read:,} of "
                             f"{held:,} documents analysed so far.</p>")
        elif held:
            findings_html = ("<p class='help'>No findings yet — none of this site's "
                             "documents have been analysed.</p>")
        else:
            findings_html = "<p class='help'>No documents held.</p>"

        # The signals this site matches, as pills on its own page — the
        # same neutral pill the table row uses, because a cohort is a
        # category and colour on this page means the state of a figure.
        sig_pills = "".join(
            f'<span class="sigpill">{esc(cohort_title.get(_k, _k))}</span>'
            for _k in cohorts_of_site.get(key, ()))
        if sig_pills:
            sig_pills = f'<p class="sitepills">{sig_pills}</p>'

        # One banner, stating the plain fact about this site: either its
        # documents are unread, or it has none and here is why.
        site_banner = ""
        if not held:
            lbl, why = site_profile.no_documents_reason(
                ["pre_application"] if not (n_apps or 0)
                else site_outcomes.get(key, ()))
            site_banner = ('<div class="banner" style="margin-top:0"><b>'
                           + esc(lbl) + '.</b> ' + esc(why) + '</div>')
        elif is_prov:
            site_banner = ('<div class="banner" style="margin-top:0"><b>'
                           'Reading is incomplete.</b> '
                           + esc(site_profile.provisional_statement(p_held, p_read))
                           + '</div>')

        # Every site gets a Drive folder, including those with nothing in
        # them but a site report — so the label has to say which it is,
        # or "Source documents" sends a reporter to an empty folder.
        _durl = drive.get(hv._norm_key(key))
        if not _durl:
            drive_html = "<span class='help'>not yet synced to Drive</span>"
        elif held:
            drive_html = (f'<a href="{_durl}" target="_blank" rel="noopener">'
                          f'Open Drive folder</a> <span class="help">'
                          f'{held:,} document{"" if held == 1 else "s"}</span>')
        else:
            drive_html = (f'<a href="{_durl}" target="_blank" rel="noopener">'
                          f'Site folder</a> <span class="help">summary only — no '
                          f'documents held</span>')
        # §5's links row, built where the Drive URL is known. No council
        # register link: this reader holds register URLs per application,
        # not per site, and the applications table below carries every
        # one of them — a single "register" link would have to pick one
        # and would be wrong on any site that spans councils.
        _csv = drive_csv.get(hv._norm_key(key), "")
        _bits = []
        if _durl and held:
            _bits.append(f'<a href="{esc(_durl)}" target="_blank" rel="noopener">'
                         f'{held:,} documents on Drive</a>')
        if _csv:
            _bits.append(f'<a href="{esc(_csv)}" target="_blank" rel="noopener">'
                         f'Findings CSV'
                         + (f' ({findings_n:,})' if findings_n else '') + '</a>')
        _bits.append(f'<a href="#site-{esc(key)}">Link to this site</a>')
        site_links = "".join(f'<span>{b}</span>' for b in _bits)

        near_html = (f'{esc(near[0]["name"])} — {near[1]} km'
                     + (f', {esc(near[0]["cap"])}' if near[0]["cap"] else "")
                     + f' <a href="{esc(near[0]["url"])}" target="_blank" '
                       f'rel="noopener">PINS</a>') if near else "—"

        # DESNZ consumption context: the sentence appears only where the
        # site's local authority maps cleanly — no hedged filler on the
        # sites that span authorities or sit outside Great Britain — and
        # the caveats travel with it, naming the inferred authority so
        # the mapping is visible beside its product.
        ctx_la = cc.authority_for(councils, bauthority)
        ctx_sentence = cc.context_sentence(ctx_la, desnz) if ctx_la else None
        if ctx_sentence:
            ctx_mapped += 1
            ctx_html = (
                '<div class="box ctx"><h4>Local authority context</h4>'
                f'<p>{esc(ctx_sentence)}</p>'
                f'<p class="help">{esc(cc.context_note(ctx_la))}</p></div>')
        else:
            ctx_unmapped += 1
            ctx_html = ""
        ctx_unrecognised.update(cc.unrecognised(councils))

        # Grid-register claims: rendered beside the planning-derived
        # power, never into it. Tentative matches say what they are, and
        # the adjudication evidence travels with every row — the match is
        # our inference, so the reasoning has to be one click away.
        site_claims = claims_by_site.get(key, [])
        if site_claims:
            claims_sites_rendered += 1
            claims_rows_rendered += len(site_claims)
            _claim_rows = []
            for c in site_claims:
                qty = ccl.QUANTITY_LABELS.get(c["quantity_type"],
                                              c["quantity_type"])
                try:
                    _cd = dt.date.fromisoformat(c["connection_date"] or "")
                    conn_date = f"{_cd.day} {_cd:%B %Y}"
                except ValueError:
                    conn_date = c["connection_date"]
                # The figure as its source printed it — 800 kW stays 800 kW
                # and an MWh consumption total never acquires a megawatt
                # sign — with the normalised MW only where it differs.
                _orig = (f"{float(c['value_original']):,.10g} "
                         f"{c['unit_original']}")
                _mw = c["value_mw"]
                if _mw is not None and c["unit_original"] != "MW":
                    _orig += f" <span class='help'>({float(_mw):,.4g} MW)</span>"
                # An operator's own word for the quantity is evidence, so
                # it is shown instead of ours where one exists.
                _qty = c["operator_term"] or qty
                _entry = {"neso_ea_register": "register entry",
                          "ea_permit": "permitted at"}.get(
                              c["source_key"], "for")
                head = (f"<p><strong>{_orig}</strong> "
                        f"{esc(_qty)} — {_entry} "
                        f"“{esc(c['claim_name'])}”"
                        + (f", {esc(c['connection_point'])}"
                           if c["connection_point"] else "")
                        + (f", connection date {esc(conn_date)}"
                           if conn_date else "")
                        + (f" <span class='help'>({esc(c['stage'])})</span>"
                           if c["stage"] else "")
                        + ".</p>")
                conf = (f"{c['confidence']} match"
                        + (f" — {ccl.TENTATIVE_NOTE}"
                           if c["confidence"] == "tentative" else "")
                        + f" · {esc(c['method']).replace('_', ' ')}")
                # Only the operator-website source is titled by the
                # operator; every other source carries an operator name
                # too — a permit holder, a filing company — and titling
                # those by it would caption an Environment Agency permit
                # as the operator's own marketing.
                src_title = (c["operator"] + " (own website)"
                             if c["source_key"] == "operator_website"
                             and c["operator"] else
                             ccl.SOURCE_TITLES.get(c["source_key"],
                                                   c["source_key"]))
                _as_at = c["as_at"]
                src = (f'<a href="{esc(c["source_url"])}" target="_blank" '
                       f'rel="noopener">{esc(src_title)}</a>'
                       + (f", as at {_as_at.day} {_as_at:%B %Y}"
                          if _as_at else "")
                       + (f", {esc(c['source_locator'])}"
                          if c["source_locator"] else ""))
                _claim_rows.append(
                    f'<div class="claim">{head}'
                    f'<p class="help">{conf} · {src}</p>'
                    f'<details><summary>How this was matched</summary>'
                    f'<p class="help">{esc(c["evidence"])}</p></details>'
                    f'</div>')
            # Only the caveats for quantities this site actually has:
            # a generic wall of them would be skipped, and the one that
            # matters would go with it.
            _seen_q, _caveats = set(), []
            for c in site_claims:
                q = c["quantity_type"]
                if q in _seen_q:
                    continue
                _seen_q.add(q)
                if q in ccl.QUANTITY_CAVEATS:
                    _caveats.append(
                        f'<p class="help"><b>'
                        f'{esc(ccl.QUANTITY_LABELS.get(q, q).capitalize())}:'
                        f'</b> {esc(ccl.QUANTITY_CAVEATS[q])}</p>')
            claims_html = (
                '<div class="box claims"><h4>Other power indicators</h4>'
                f'<p class="help provenance">{esc(ccl.INDICATORS_NOTE)}</p>'
                + "".join(_claim_rows) + "".join(_caveats) + '</div>')
        else:
            claims_html = ""

        def _q(v, qt, _k=key):
            if not v:
                return "—"
            src = power_src.get((_k, qt))
            return (f"{v:g} MW" + (f' <span class="help">{esc(src)}</span>'
                                   if src else ""))

        # Only worth saying where the two actually disagree.
        mixed_note = ""
        if it and tot and tot < it and (power_src.get((key, "it_load"))
                                        != power_src.get((key, "total_site"))):
            mixed_note = ('<dt>Note</dt><dd class="help">These two figures come from '
                          'different applications at this site, so they describe '
                          'different buildings rather than contradicting each other.</dd>')

        who = who_cell(prof)
        reading_html = reading_panel(key)
        hay = " ".join(str(x or "").lower() for x in
                       (name, key, addr, ", ".join(councils or []), full_desc,
                        prof.get("operator_group"), prof.get("end_user"),
                        prof.get("applicant_of_record"), prof.get("advisers"),
                        prof.get("named_in_documents"),
                        prof.get("cooling_method"), btitle,
                        near[0]["name"] if near else "", " ".join(refs or []),
                        " ".join(c["claim_name"] for c in site_claims)))
        mw = mw_text(est.value_mw)
        # Luke, 2026-08-20 and again on 2026-08-24: the basis has to be
        # legible ON the figure, and "I'd do it with weight and a mark
        # rather than colour alone (colour vanishes the moment someone
        # sorts)". So the ladder in site_scale.power_estimate reads as
        # three weights and one glyph: a disclosed figure is stated in
        # full, a connection or standby-implied figure is lighter, and a
        # floorspace estimate carries "≈" because it is arithmetic on an
        # area rather than anything anyone published.
        _wclass = {"High": "w-stated", "Medium": "w-implied",
                   "Low": "w-implied", "Indicative": "w-modelled"}.get(
                       est.confidence or "", "w-implied")
        _mark = "≈" if est.confidence == "Indicative" else ""
        mw_cell = ((f"<span class='fig {_wclass}'>{_mark}{mw}</span>"
                    f"<span class='q'>{esc(est.basis)}"
                    + (" <span class='prov'>· may rise</span>" if is_prov and mw else "")
                    + "</span>") if mw
                   else f"<span class='fig w-none'>—</span>"
                        f"<span class='q'>{esc(est.basis)}</span>")

        # A confidence tier and a count, never a megawatt figure: the main
        # row is scanned and sorted, and a number here beside Declared
        # power would read as directly comparable to it. It is not — a
        # register claim can be a different quantity type from the site's
        # own figure, and "tentative" exists precisely to say a match is
        # a lead rather than an attribution. Collapsing several of those
        # into one "highest" number would launder that distinction away.
        _tier_rank = {"strong": 3, "probable": 2, "tentative": 1}
        if site_claims:
            best = max(site_claims, key=lambda c: _tier_rank[c["confidence"]])
            _n = len(site_claims)
            ind_label = best["confidence"] + (f" ×{_n}" if _n > 1 else "")
            ind_title = "; ".join(f"{c['claim_name']} ({c['confidence']})"
                                  for c in site_claims)
            ind_class = "known" if best["confidence"] == "strong" else "unknown"
            ind_cell = (f'<span class="tag {ind_class}" title="{esc(ind_title)}">'
                       f'{esc(ind_label)}</span>')
            ind_sort = _tier_rank[best["confidence"]] * 100 + _n
        else:
            ind_cell = "—"
            ind_sort = 0

        body.append(f"""<tr class="site" data-key="{esc(key)}" data-hay="{esc(hay)}"
 data-known="{1 if known else 0}"
 data-near="{esc(near[0]['name'] if near else '')}" data-mw="{est.value_mw or ''}"
 data-prov="{1 if is_prov else 0}" data-origin="{esc('|'.join(org))}"
 data-who="{esc(who['filter_key'])}" data-cohorts="{esc('|'.join(cohorts_of_site.get(key, ())))}">
<td class="sitecell" data-v="{esc(name or key)}"><span class="sname">{esc(trim(name or key, 58))}</span>
 <span class="skey">{esc(' · '.join([x for x in [', '.join(councils or []), key] if x]))}</span>
 <span class="sprop">{esc(trim(summary, 118)) or '—'}{
 '' if descriptive else ' — the register holds no description of the development itself, only procedural applications'}</span></td>
<td data-v="{esc(who['sort'])}">{who['cell']}</td>
<td class="sigcell" data-v="{len(cohorts_of_site.get(key, ()))}">{
 ''.join(f'<span class="sigpill">{esc(cohort_title.get(_k, _k))}</span>'
         for _k in cohorts_of_site.get(key, ())) or '<span class="q">—</span>'}</td>
<td class="mw" data-v="{est.value_mw or ''}">{mw_cell}</td>
<td data-v="{ind_sort}">{ind_cell}</td>
<td data-v="{esc(cap_label)}"><span class="tag {'known' if known else 'unknown'}">{esc(cap_label)}</span></td>
<td data-v="{esc(addr)}">{esc(trim(addr, 105)) or '—'} {maplink}</td>
<td data-v="{read}"><span class="rbar" title="{read} of {held} documents read"><span
 class="rbar-fill {'r-done' if held and read >= held * 0.94 else ('r-part' if read else 'r-none')}"
 style="width:{(100 * read / held) if held else 0:.0f}%"></span></span>{read:,}/{held:,}<span class="q">documents read{
 f' · <a href="{esc(_durl)}" target="_blank" rel="noopener" '
 f'onclick="event.stopPropagation()">Drive</a>' if _durl and held else ''
}</span><span class="q rstate {'r-done' if held and read >= held * 0.94 else ('r-part' if read else 'r-none')}">{
 'Complete' if held and read >= held * 0.94 else ('Figures are floors' if read else 'Nothing published')
}</span></td>
</tr>
<tr class="detail"><td colspan="8">
 <!-- §5 of the design handoff. The header card carries the name and the
      identifiers, which the page used to scrape out of the row with
      `tr.querySelector('td strong')` — and after the table's site cell
      became a multi-row cell there was no <strong> to find, so every
      site page was titled with its key. Built here, from the values
      themselves, it cannot drift from the row again. -->
 <div class="card sitehead">
  {sig_pills}
  <h2 class="sitename">{esc(name or key)}</h2>
  <p class="siteident">{esc(", ".join(councils or []))}{" · " if addr else ""}{esc(trim(addr, 90))}
   · <code>{esc(key)}</code> · {esc(cls)}</p>
  <p class="sitelinks">{site_links}</p>
 </div>
 {site_banner}
 <div class="sitebody">
 <!-- §5's two columns. Left is the record — what this site's own
      documents say, in the order a reporter reads it. Right is what
      was computed from them and the coverage that qualifies it. The
      handoff's left column 1 (a signed reporter's note) and right
      column 1 (a template digest) were rejected in the plan's §2; the
      machine reading stands where the digest would have. -->
 <div class="col-record">
  <div class="box proposal"><h4>Proposal</h4>
    <p><strong>{esc(summary) or '—'}</strong></p>
    <p class="help">Lifted verbatim from an application below, which the council published
     as:</p><p>{esc(trim(full_desc, 640)) or '—'}</p></div>
<div class="box"><h4>Declared power</h4>
   <dl class="kv">
    <dt>Best available</dt><dd>{('<strong>'+mw+' MW</strong>') if mw else '—'}
     {'<span class="prov"> ' + esc(site_profile.PROVISIONAL_MARK) + '</span>' if is_prov and mw else ''}</dd>
    <dt>Basis</dt><dd>{esc(est.basis)}</dd>
    <dt>Confidence</dt><dd>{esc(est.confidence or '—')}</dd>
    <dt>Caveat</dt><dd>{esc(est.caveat or '—')}</dd>
    <dt>IT load</dt><dd>{_q(it, 'it_load')}</dd>
    <dt>Total site</dt><dd>{_q(tot, 'total_site')}</dd>
    <dt>Grid connection</dt><dd>{_q(grid, 'grid_connection')}</dd>
    <dt>On-site generation</dt><dd>{_q(gen, 'onsite_generation')}{
      f' <span class="help">{esc(prof.get("gen_figure_note"))}</span>'
      if prof.get("gen_figure_note") else ''}</dd>
    {mixed_note}
    <dt>Excluded figures</dt><dd>{nexc or 0}
     <span class="help">market context, not this site</span></dd>
   </dl>
   <p class="help provenance">{esc(ccl.DECLARED_POWER_NOTE)}</p></div>
  {claims_html}
  <div class="box"><h4>What the documents say</h4>
   {findings_html}</div>
  {f'''<details class="apps-d"><summary>Show the {len(apps)} planning application{'' if len(apps)==1 else 's'} for this site</summary>{apps_html}</details>''' if apps else apps_html}
 </div>
 <div class="col-computed">
  {reading_html}
  <div class="box identity"><h4>Site details</h4>
    <div class="fields">
     <div class="stack">
      <div><span class="lbl">Site key</span><span class="val">{esc(key)}</span></div>
      <div><span class="lbl">Classification</span><span class="val">{esc(cls)}</span></div>
     </div>
     <div><span class="lbl">Coordinates</span><span class="val">
      {f'{lat:.5f}, {lon:.5f}' if lat and lon else '—'}
      {maplink}{' · ' + gmaps if gmaps else ''}
      <span class="help">{esc(csrc or 'source unknown')}</span></span></div>
     <div><span class="lbl">How we found it</span><span class="val">
      {esc(', '.join(org)) or '—'}
      {f'<span class="help">{esc(origin_mod.explain(org))}</span>' if len(org) < 3 else
       '<span class="help">Several independent routes reached this site, which is a '
       'stronger signal than any one of them.</span>'}</span></div>
     <div><span class="lbl">{'Source documents' if held else 'Drive'}</span>
      <span class="val">{drive_html}</span></div>
     <div><span class="lbl">Share</span><span class="val">
      <a href="#site-{esc(quote(key, safe=''))}" data-key="{esc(key)}"
         onclick="event.stopPropagation();
         return copySiteLink(this.dataset.key, this)">Copy link to this site</a>
      <span class="help">Opens straight to this site's page, whatever
       the table is filtered to.</span></span></div>
    </div></div>
  <div class="box parties"><h4>Who is behind it</h4>
    <dl class="kv">
     <dt>End user</dt><dd>{esc(prof.get('end_user') or '—')}
      {f'<span class="help">group: {esc(prof["operator_group"])}</span>'
        if prof.get('operator_group') else ''}</dd>
     <dt>Applicant of record</dt><dd>{esc(prof.get('applicant_of_record') or '—')}</dd>
     <dt>Advisers</dt><dd>{esc(prof.get('advisers') or '—')}</dd>
     <dt>Also named in the documents</dt><dd>{counted(prof.get('named_in_documents'))}</dd>
     <dt>Planning authority</dt><dd>{esc(prof.get('authority') or '—')}</dd>
     <dt>Barbour project</dt><dd>{esc(btitle or '—')}
      {f'<span class="help">{esc(bstage or "")}</span>' if bstage else ''}</dd>
     <dt>Nearest energy project</dt><dd>{near_html}</dd>
    </dl>
    <p class="help">{esc(prof.get('parties_source') or site_profile.PARTIES_ABSENT)}.
     End user, applicant and advisers are as Barbour ABI's project record states them.
     The last line is different: those organisations are named in the site's own
     documents, and the number is how often — the firm that wrote the planning statement
     is named more often than the developer, and a utilities section names whoever has
     ducts in the road.</p></div>
   <div class="box"><h4>Generation, cooling and water</h4>
   <dl class="kv">
    <dt>Standby generators</dt><dd>{
      (esc(prof.get('generator_count')) + ' units') if prof.get('generator_count') else '—'}</dd>
    <dt>Generation type</dt><dd>{counted(prof.get('generator_fuel'))}</dd>
    <dt>Cooling method</dt><dd>{counted(prof.get('cooling_method'))}</dd>
    <dt>Water evidence</dt><dd>{esc(prof.get('water_evidence') or '—')}</dd>
    <dt>EIA status</dt><dd>{esc(prof.get('eia_status_label') or '—')}</dd>
    <dt>Environmental subjects</dt><dd>{esc(', '.join(env)) or '—'}</dd>
    <dt>Finding subjects</dt><dd>{esc(', '.join((families or [])[:6])) or '—'}</dd>
   </dl>
   <p class="help">{esc(prof.get('generator_caveat') or '')}</p>
   <p class="help">{esc(prof.get('cooling_caveat') or '')}</p></div>
  {ctx_html}
 </div>
</div>
</td></tr>""")

    # Barbour-recorded projects with no planning application yet. They are
    # the pipeline ahead of the planning system, so leaving them out would
    # make the dataset look like a record of what has already been applied
    # for. Almost everything about them is honestly blank; the row says why
    # rather than implying the site is small or quiet.
    existing = {r[0].upper() for r in site_rows}
    n_barbour = 0
    for (pref, title, pstage, dev_type, authority, address, description,
         plat, plon, pvalue, pfloor, psite, pplan, pdecision,
         praw) in barbour_rows:
        key = f"PTNO-{pref}"
        if key.upper() in existing:
            continue
        n_barbour += 1
        _, cap_label = site_profile.capacity_status(
            pre_application=True, docs_held=0, docs_read=0,
            power_value_mw=None, power_basis="")
        near = nearest(plat, plon)
        maplink = (f'<a href="#map" onclick="showMap(\'{esc(key)}\');return false"'
                   f' title="Show this site on the map">map</a>') if plat and plon else ""
        env = sorted(sig.environmental_signals(description or "").keys())
        summary = prop.tidy(prop.summarise([description, title])[0])
        # A pre-planning row has no documents, so Barbour's role blocks
        # are the whole of what is known about who is behind it — which
        # makes this the one place the column is the row's main content.
        bprof = site_profile.site_parties(
            site_profile.barbour_parties(praw or {}, str(pref or "")),
            (), [site_profile._AUTHORITY_PHONE_RE.sub("", authority or "")],
            alias_index)
        who = who_cell(bprof)
        if plat is not None and plon is not None:
            map_points.append({
                "k": "s", "id": key, "lat": plat, "lon": plon, "mw": None,
                "c": [],
                "t": (title or key)[:80],
                "h": " ".join(x.lower() for x in
                              (title or key, authority or "", address or "") if x),
                "pop": (f'<b>{esc(title or key)}</b><br><span class="help">'
                        f'{esc(authority or "")}</span><br>'
                        f'<span class="help">No application submitted yet — '
                        f'Barbour ABI project intelligence</span><br>'
                        f'<a href="#sites" onclick="return goSite(\'{esc(key)}\')">'
                        f'Open this site</a>')})
        hay = " ".join(str(x or "").lower() for x in
                       (title, key, address, authority, description, dev_type,
                        bprof["end_user"], bprof["applicant_of_record"],
                        bprof["advisers"]))
        near_html = (f'{esc(near[0]["name"])} — {near[1]} km'
                     f' <a href="{esc(near[0]["url"])}" target="_blank" '
                     f'rel="noopener">PINS</a>') if near else "—"
        ctx_la = cc.authority_for((), authority)
        ctx_sentence = cc.context_sentence(ctx_la, desnz) if ctx_la else None
        if ctx_sentence:
            ctx_mapped += 1
            ctx_html = (
                '<div class="box ctx"><h4>Local authority context</h4>'
                f'<p>{esc(ctx_sentence)}</p>'
                f'<p class="help">{esc(cc.context_note(ctx_la))}</p></div>')
        else:
            ctx_unmapped += 1
            ctx_html = ""
        body.append(f"""<tr class="site" data-key="{esc(key)}" data-hay="{esc(hay)}"
 data-known="0"
 data-near="{esc(near[0]['name'] if near else '')}" data-mw="" data-prov="0"
 data-origin="Barbour ABI" data-who="{esc(who['filter_key'])}" data-cohorts="">
<td class="sitecell" data-v="{esc(title or key)}"><span class="sname">{esc(trim(title or key, 58))}</span>
 <span class="skey">{esc(' · '.join([x for x in [authority or '', key] if x]))}</span>
 <span class="sprop">{esc(trim(summary, 118)) or '—'}</span></td>
<td data-v="{esc(who['sort'])}">{who['cell']}</td>
<td class="sigcell" data-v="0"><span class="q">—</span></td>
<td class="mw" data-v="">—<span class="q">no application yet</span></td>
<td data-v="0">—</td>
<td data-v="{esc(cap_label)}"><span class="tag unknown">{esc(cap_label)}</span></td>
<td data-v="{esc(address or '')}">{esc(trim(address, 105)) or '—'} {maplink}</td>
<td data-v="-1">—<span class="q">nothing published</span></td>
</tr>
<tr class="detail"><td colspan="8">
 <div class="banner" style="margin-top:0"><b>No application submitted yet.</b>
  {esc(site_profile.NO_DOCUMENT_REASONS['pre_application'])}</div>
 <div class="grid">
  <div class="col-record">
   <div class="box proposal"><h4>Proposal</h4>
    <p><strong>{esc(summary) or '—'}</strong></p>
    <p class="help">Barbour ABI records it as:</p><p>{esc(description) or '—'}</p></div>

   <div class="box identity"><h4>Site details</h4>
    <div class="fields">
     <div class="stack">
      <div><span class="lbl">Barbour reference</span><span class="val">{esc(pref)}</span></div>
      <div><span class="lbl">Stage</span><span class="val">{esc(pstage or '—')}</span></div>
     </div>
     <div><span class="lbl">Development type</span><span class="val">{esc(dev_type or '—')}</span></div>
     <div><span class="lbl">Coordinates</span><span class="val">
      {f'{plat:.5f}, {plon:.5f}' if plat and plon else '—'} {maplink}</span></div>
     <div><span class="lbl">Environmental subjects</span>
      <span class="val">{esc(', '.join(env)) or '—'}</span></div>
    </div></div>
  </div>

  <div class="box"><h4>Scheme</h4>
   <dl class="kv">
    <dt>Planning authority</dt><dd>{esc(authority or '—')}</dd>
    <dt>Contract value</dt><dd>{f'£{pvalue:,.0f}' if pvalue else '—'}</dd>
    <dt>Floor area</dt><dd>{f'{pfloor:,.0f} m²' if pfloor else '—'}</dd>
    <dt>Site area</dt><dd>{f'{psite:,.2f} ha' if psite else '—'}</dd>
   </dl></div>
  <div class="box"><h4>Dates</h4>
   <dl class="kv">
    <dt>Plan date</dt><dd>{esc(str(pplan or '—'))}</dd>
    <dt>Decision date</dt><dd>{esc(str(pdecision or '—'))}</dd>
   </dl></div>
  <div class="box"><h4>Nearby</h4>
   <dl class="kv"><dt>Nearest energy project</dt><dd>{near_html}</dd></dl>
   <p class="help">Barbour ABI data is licensed and must be credited in published output.</p>
  </div>
  {ctx_html}
 </div></td></tr>""")

    n_sites = len(site_rows) + n_barbour
    # The chips, from the counts the rows themselves produced — a group
    # that is on the strip is a group that is on a row, and the number
    # beside it is the number of rows a click will leave. Ranked by
    # sites, then by name so two builds of one database agree.
    # The Signals tab: one card per registry entry, registry order, no
    # ranking of sites anywhere. Every number on a card is the length
    # of a list that was computed on this build; the definition, rule
    # and limits are the registry's own text, and the same text goes to
    # the workbook's Read me sheet from the same source.
    def _signal_card(c):
        r = c.result
        key = c.cohort.key
        n = len(r.members)
        if r.withheld:
            count_html = ('<div class="sigcount withheld">Withheld</div>'
                          f'<p class="help">{esc(r.withheld)}</p>')
            actions = ""
        else:
            count_html = (f'<div class="sigcount">{n:,}<span class="q"> site'
                          f'{"" if n == 1 else "s"}</span></div>')
            site_list = "".join(
                f'<li><a href="#site-{esc(quote(m.site_key, safe=""))}" '
                f'onclick="return goSite(this.dataset.key)" '
                f'data-key="{esc(m.site_key)}">'
                f'{esc(site_names.get(m.site_key) or m.site_key)}</a>'
                f'<span class="q"> {esc("; ".join(f"{a} {b}" for a, b in m.evidence.items() if b not in (None, "")))}</span></li>'
                for m in r.members)
            csv_lines = ["site_key,site_name," + ",".join(
                sorted({a for m in r.members for a in m.evidence}))]
            cols = sorted({a for m in r.members for a in m.evidence})
            for m in r.members:
                csv_lines.append(",".join(
                    '"' + str(v).replace('"', '""') + '"' for v in
                    [m.site_key, site_names.get(m.site_key) or m.site_key]
                    + [m.evidence.get(a, "") for a in cols]))
            csv_data = quote("\n".join(csv_lines), safe="")
            # The handoff's actions row: a primary pill that opens the
            # cohort in the table, then the script that produces it and
            # the cohort as CSV — the two things a reader needs to check
            # the count without taking the page's word for it.
            # A cohort the rule selected nothing for has nothing to open
            # and nothing to export. It still renders — an empty cohort
            # is a result, and hiding it would make the registry look
            # like whatever happened to match today.
            actions = "" if not n else (
                f'<p class="sigactions">'
                f'<button type="button" class="cta" data-k="{esc(key)}" '
                f'onclick="return openCohort(this.dataset.k)">'
                f'Open these {n:,} sites in the table</button> '
                f'<code class="sigsrc">{esc(c.cohort.compute.__module__.replace(".", "/"))}'
                f'.py · {esc(c.cohort.compute.__qualname__)}</code> '
                f'<a href="data:text/csv;charset=utf-8,{csv_data}" '
                f'download="{esc(key)}.csv">Cohort as CSV</a> · '
                f'<a href="#cohort:{esc(key)}">Link to this filter</a></p>'
                f'<details><summary>The {n:,} site{"" if n == 1 else "s"}</summary>'
                f'<ul class="siglist">{site_list}</ul></details>')
        checks_html = ""
        if c.checks:
            bits = []
            if c.confirmed:
                bits.append(f"{c.confirmed} hand-checked and holding")
            if c.disputed:
                bits.append(f"{len(c.disputed)} hand-checked and rejected: "
                            + ", ".join(esc(site_names.get(k.site_key) or k.site_key)
                                        + f" ({esc(k.note.strip())})" for k in c.disputed))
            if c.outside:
                bits.append(f"{len(c.outside)} checked on sites the rule does not select: "
                            + ", ".join(esc(site_names.get(k.site_key) or k.site_key)
                                        for k in c.outside))
            checks_html = '<p class="sigchecks">' + "; ".join(bits) + ".</p>"
        notes_html = "".join(f'<p class="help">{esc(x)}</p>' for x in r.notes)
        # The design handoff's §3 card: family label, verification pill,
        # a headline stating the count in words and the property, the
        # rule itself in a monospace block, what it does not tell you,
        # the actions row, and a right-hand column carrying the count
        # and what cannot enter the cohort.
        n_members = len(c.result.members)
        pill = ('<span class="vpill vpill-hand">Hand-checked</span>'
                if c.confirmed else
                '<span class="vpill vpill-machine">Computed, not hand-checked</span>')
        # "who cannot enter this cohort, and which way further reading
        # moves it" — from the rule's own notes where it has them. Where
        # it has none, nothing is written: a floor statement invented for
        # the shape of the card would be the one thing on this screen no
        # query produced.
        floor = "".join(f'<p class="sigfloor">{esc(x)}</p>' for x in r.notes)
        return f"""
 <div class="card sigcard" id="signal-{esc(key)}">
  <div class="sigmain">
   <div class="sigtop"><span class="sigfam">{esc(humanise(c.cohort.family))}</span>{pill}
    <span class="sigrule">rule {esc(c.cohort.rule_version)}</span></div>
   <h3 class="sigheadline">{esc(_count_in_words(n_members))} {esc(c.cohort.title.lower())}</h3>
   <p class="sigprose">{esc(c.cohort.definition)}</p>
   <div class="sigquery">{esc(c.cohort.rule)}</div>
   <p class="siglimits"><b>What it does not tell you.</b> {esc(c.cohort.limits)}</p>
   {checks_html}{notes_html}
   {actions}
  </div>
  <div class="sigside">
   <div class="signum">{n_members:,}</div>
   <div class="sigunit">sites{"" if c.result.withheld else ", when this page was built"}</div>
   {floor}
  </div>
 </div>"""

    n_signals = sum(1 for c in cohorts if not c.result.withheld)
    signals_html = f"""
 <div class="card card-ink sigexplain">
  <h2 class="cardh">What these are, and who wrote them</h2>
  <p>Each signal is a deterministic query over the adjudicated findings, defined in
  <code>dcp/site_cohorts.py</code> and re-run when this page is generated. The wording is
  a fixed template with the count substituted in; the order is the registry's, and nothing
  on this page ranks one site above another — the lists are in site-key order.
  <b>No language model selected, ranked or described anything on this screen</b>, and no
  cohort asserts a cause. A signal says only: these sites share this property, measured
  this way.</p>
  <p>A hand-check is a person's verdict on one membership, recorded beside the rule in
  <code>data/priors/cohort_checks.yaml</code>; the rule does not read it. Where a check
  rejects a site the rule selected, or accepts one it did not, both are printed. A cohort
  marked <em>withheld</em> was not computed in this release, for the reason given. The
  same cohorts, with the same rule versions, are the <code>Cohorts</code> sheet of the
  workbook and the <code>cohorts</code> table of the database.</p>
 </div>
 <div class="signals">{"".join(_signal_card(c) for c in cohorts)}</div>
"""

    cohort_chips = "".join(
        (f'<button type="button" class="chip" data-cohort="{esc(c.cohort.key)}" '
         f'onclick="setCohort(this.dataset.cohort)" aria-pressed="false" '
         f'title="{esc(c.cohort.definition)}">'
         f'{esc(c.cohort.title)} <span class="n">{len(c.result.members)}</span></button>')
        if not c.result.withheld else
        (f'<button type="button" class="chip" disabled '
         f'title="{esc(c.result.withheld)}">{esc(c.cohort.title)} '
         f'<span class="n">withheld</span></button>')
        for c in cohorts)
    n_who_named = sum(who_counts.values())
    who_chips = "".join(
        f'<button type="button" class="chip" '
        f'data-who="{esc(entities.canonical_key(nm))}" '
        f'onclick="setWho(this.dataset.who)" aria-pressed="false">'
        f'{esc(trim(nm, 26))} <span class="n">{c}</span></button>'
        for nm, c in sorted(who_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if c >= WHO_CHIP_FLOOR)
    # Sites in the table that can never be a pin. Derived from the points
    # actually built rather than counted separately, so the tooltip cannot
    # disagree with the map it is explaining.
    n_mappable = sum(1 for m in map_points if m["k"] == "s")
    n_no_coords = n_sites - n_mappable

    approws_all = []
    for r in sorted(app_rows, key=lambda x: (x[3] or "", x[1] or "")):
        portal = (f'<a href="{esc(r[12])}" target="_blank" rel="noopener">register</a>'
                  if r[12] and not str(r[12]).startswith("file://") else "—")
        durl = hv._drive_application_url(drive_apps, r[0], r[1])
        docs_cell = (f'<a href="{esc(durl)}" target="_blank" rel="noopener">{r[13] or 0}</a>'
                     if durl else str(r[13] or 0))
        hay = " ".join(str(x or "").lower() for x in (r[1], r[3], r[7], r[15], r[16]))
        approws_all.append(
            f'<tr data-hay="{esc(hay)}">'
            f"<td data-v='{esc(r[1])}'><strong>{esc(r[1])}</strong>"
            f"<span class='q'>{esc(r[0])}</span></td>"
            f"<td>{esc(r[3])}</td><td>{esc(r[4] or '—')}</td>"
            f"<td data-v='{esc(str(r[5] or ''))}'>{esc(str(r[5] or '—'))}</td>"
            f"<td>{esc(r[7] or '—')}</td>"
            f"<td data-num='1' data-v='{r[13] or 0}'>{docs_cell}</td>"
            f"<td>{r[14] or 0}</td><td>{portal}</td>"
            f"<td>{esc(trim(r[16], 150))}</td></tr>")

    # Carry the site key alongside the name: the Energy rows link to the
    # site's own row and to the pair of them on the map, and both need the
    # key rather than the display name.
    site_coords = [(x[3], x[4], x[2] or x[0], x[0]) for x in site_rows
                   if x[3] is not None and x[4] is not None]
    energyrows = []
    for p in nsip:
        d, sname, skey = min(((hv._haversine_km(p["lat"], p["lon"], la, lo), nm, k)
                              for la, lo, nm, k in site_coords),
                             default=(None, "", ""))
        hay = " ".join(str(x).lower() for x in
                       (p["name"], p["applicant"], p["region"], p["desc"][:200]))
        energyrows.append((d if d is not None else 1e9,
            f'<tr data-hay="{esc(hay)}">'
            f"<td><strong>{esc(p['name'])}</strong><span class='q'>{esc(p['ref'])}</span></td>"
            f"<td class='mw'>{esc(p['cap']) or '—'}</td><td>{esc(p['type'])}</td>"
            f"<td>{esc(p['stage'] or p['status'] or '—')}</td><td>{esc(p['applicant'])}</td>"
            f"<td>{esc(p['region'])}</td>"
            f"<td data-v='{d if d is not None else ''}'>"
            + (f"<a href='#sites' onclick=\"return goSite('{esc(skey)}')\">"
               f"{esc(trim(sname, 42))}</a>"
               f"<span class='q'><a href='#map' onclick=\"showMap('{esc(skey)}',"
               f"'{esc(p['ref'])}');return false\" title='Show both on the map'>"
               f"{d:.1f} km</a></span>" if d is not None else "—")
            + "</td>"
            f"<td><a href=\"{esc(p['url'])}\" target=\"_blank\" rel=\"noopener\">PINS</a></td>"
            f"<td>{esc(trim(p['desc'], 150))}</td></tr>"))
    energyrows.sort(key=lambda t: t[0])

    # ---- Charts ---------------------------------------------------------
    # Inline SVG, no library: the page has to open from a Drive folder on a
    # train. Both charts are drawn from fields that do not depend on the
    # deep read, so neither moves as analysis continues — the caveat that
    # matters here is acquisition, not reading.
    def bars(items, title, note, unit="", highlight=None):
        if not items:
            return ""
        w, h, pad, gap = 520, 168, 26, 3
        top = max(v for _, v in items) or 1
        bw = (w - pad) / len(items)
        rects, labels = [], []
        for i, (lab, v) in enumerate(items):
            bh = (h - 34) * v / top
            x, y = pad + i * bw, h - 20 - bh
            cls = "hl" if highlight and highlight(lab) else ""
            rects.append(
                f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{bw - gap:.1f}" '
                f'height="{bh:.1f}"><title>{esc(lab)}: {v:,}{esc(unit)}</title></rect>')
            if len(items) <= 9 or i % 2 == 0 or i == len(items) - 1:
                labels.append(f'<text class="xl" x="{x + (bw - gap) / 2:.1f}" y="{h - 7}" '
                              f'text-anchor="middle">{esc(lab)}</text>')
        return (f'<figure class="chart"><figcaption>{esc(title)}</figcaption>'
                f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
                f'<text class="yl" x="0" y="12">{top:,}</text>'
                f'<line class="ax" x1="{pad}" y1="{h - 20}" x2="{w}" y2="{h - 20}"/>'
                + "".join(rects) + "".join(labels)
                + f'</svg><p class="help">{esc(note)}</p></figure>')

    years = defaultdict(int)
    for r in app_rows:
        if r[5]:
            years[r[5].year] += 1
    yr_items = [(str(y), years[y]) for y in sorted(years) if y >= 2015]
    this_year = max(years) if years else None
    chart_years = bars(
        yr_items, "Applications received, by year",
        f"Council registers are indexed densely from 2018, so earlier years are "
        f"undercounted rather than quiet. {this_year} is a part year.",
        unit=" applications",
        highlight=lambda l: l == str(this_year))

    BANDS = [("under 10", 0, 10), ("10–24", 10, 25), ("25–49", 25, 50),
             ("50–99", 50, 100), ("100–199", 100, 200), ("200+", 200, 1e9)]
    band_counts = {b[0]: 0 for b in BANDS}
    for v in site_mw_values:
        for lab, lo, hi in BANDS:
            if lo <= v < hi:
                band_counts[lab] += 1
                break
    chart_bands = bars(
        [(b[0], band_counts[b[0]]) for b in BANDS],
        "Sites by disclosed capacity (MW)",
        f"Only the {len(site_mw_values)} sites that disclose a figure appear. Sites whose "
        f"documents are unread, or which disclose nothing, are absent — not zero. Partly-read "
        f"sites can move up a band as reading continues.",
        unit=" sites")

    # ---- Data dictionary ---------------------------------------------
    # One definition, used by both artefacts. The workbook's dictionary
    # sheet and this page render the same DICTIONARY list, so a column
    # cannot mean one thing in the spreadsheet and another here.
    def _slug(sheet, col):
        keep = "".join(ch.lower() if ch.isalnum() else "-" for ch in f"{sheet}-{col}")
        return "dict-" + re.sub(r"-+", "-", keep).strip("-")

    dict_ids = {(sh, c): _slug(sh, c) for sh, c, _ in hv.DICTIONARY}
    dict_html, current = [], None
    for sheet, col, desc in hv.DICTIONARY:
        if sheet != current:
            current = sheet
            dict_html.append(f'<h2 class="sec" id="dict-{esc(sheet.lower().replace(" ","-"))}">'
                             f'{esc(sheet)}</h2>')
        dict_html.append(
            f'<div class="entry" id="{dict_ids[(sheet, col)]}">'
            f'<h3>{esc(col)}</h3><p>{esc(desc)}</p></div>')

    def dl(sheet, col, label):
        """A column heading that links to its own definition."""
        i = dict_ids.get((sheet, col))
        return (f'{esc(label)}<a class="dlink" title="What does this column mean?" '
                f'onclick="event.stopPropagation();goDict(\'{i}\');return false" '
                f'href="#{i}">?</a>' if i else esc(label))

    for pr in nsip:
        map_points.append({
            "k": "e", "id": pr["ref"], "lat": pr["lat"], "lon": pr["lon"], "c": [],
            "mw": None, "t": pr["name"][:80],
            "h": " ".join(x.lower() for x in
                          (pr["name"], pr["applicant"], pr["region"], pr["ref"]) if x),
            "pop": (f'<b>{esc(pr["name"])}</b><br><span class="help">'
                    f'{esc(pr["ref"])} · {esc(pr["region"])}</span><br>'
                    + (f'<b>{esc(pr["cap"])}</b><br>' if pr["cap"] else "")
                    + f'<a href="{esc(pr["url"])}" target="_blank" rel="noopener">'
                      f'Planning Inspectorate page</a>')})
    for i, mp in enumerate(map_points):
        mp["i"] = i
        mp["vis"] = True
        mp["sel"] = False
    map_payload = json.dumps(map_points, separators=(",", ":"))
    # §8c. The map marks a cohort rather than filtering to one: the point
    # is to see where its sites sit among the rest, which a subset
    # cannot show. Registry order, like the chips.
    cohort_options = "".join(
        ['<option value="">— none —</option>']
        + [f'<option value="{esc(c.cohort.key)}">{esc(c.cohort.title)}</option>'
           for c in cohorts if not c.result.withheld])

    origin_opts = sorted({o for v in origins.values() for o in v})
    n_prov = sum(1 for r in site_rows
                 if site_profile.provisional(
                     cov_detail.get(r[0], {}).get("prose_held", 0),
                     cov_detail.get(r[0], {}).get("prose_read", 0))[0])

    # ---- Methodology ------------------------------------------------------
    # Written here rather than shipped as a markdown file beside the data:
    # a companion document is the first thing to go stale, and every count
    # in this one is injected from the same query that built the page.

    # The regulator's queue beside this release's disclosures. External
    # figures come from dcp/external_aggregates (entered once, with their
    # locators); this release's column is the same per-site figures the
    # page displays, banded the way Ofgem bands its Table 1. The two are
    # deliberately never joined at site level — the premise is recorded in
    # that module and in docs/EXTERNAL_DATA_SOURCES.md.
    queue_rows_html = "".join(
        f"<tr><th scope='row'>{esc(label)}</th><td class='n'>{n_proj:,}</td>"
        f"<td class='n'>{mw:,}</td><td class='n'>{esc(pct)}</td>"
        f"<td class='n'>{ours:,}</td></tr>"
        for (label, _lo, _hi, n_proj, mw, pct), (_l, ours) in zip(
            extagg.OFGEM_QUEUE_BANDS, extagg.band_counts(site_mw_values)))
    queue_rows_html += (
        f"<tr class='lead'><th scope='row'>All bands</th>"
        f"<td class='n'>{extagg.OFGEM_QUEUE_TOTALS[0]:,}</td>"
        f"<td class='n'>{extagg.OFGEM_QUEUE_TOTALS[1]:,}</td>"
        f"<td class='n'>100%</td>"
        f"<td class='n'>{len(site_mw_values):,}</td></tr>")
    _ofgem_src = extagg.SOURCES["ofgem_curate"]
    _cfi_src = extagg.SOURCES["neso_cfi"]
    # The DESNZ paragraph's figures are computed from the committed
    # extract at generation time, like every number on this page — the
    # verbatim anchors live in dcp/external_aggregates and the extract's
    # README, and the tests hold the two together.
    _desnz_src = extagg.SOURCES["desnz_lahh"]
    _d_nat = round(cc.national_change(desnz))
    _d_slough = round(cc.change_pct(desnz["Slough"]))
    _d_hillingdon = round(cc.change_pct(desnz["Hillingdon"]))
    _d_towerhamlets = round(cc.change_pct(desnz["Tower Hamlets"]))
    _d_hertsmere = round(cc.change_pct(desnz["Hertsmere"]))

    # ---- Operators: the same companies, told to five audiences ----------
    with db.cursor(dict_rows=False) as _cur:
        op_rows = odis.load_rows(_cur)
        op_divs = odis.load_divergences(_cur)
    _AUD = [(k, lbl) for k, lbl, _ in odis.AUDIENCES]

    def _aud_cell(row, key):
        got = row.by_audience.get(key) or []
        if not got:
            return '<td class="none">—</td>'
        return (f'<td class="yes">{len(got)}'
                f'<span class="q">figure{"" if len(got) == 1 else "s"}</span></td>')

    def _site_a(key, name, n=52):
        """A site name that opens the site.

        href *and* onclick: the href is what a right-click copies and
        what still works if scripting is off, the onclick does the work
        without a round trip through hashchange — which would not fire
        at all if the reader is already on that site's hash.
        """
        if not key:
            return esc(trim(name or "—", n))
        return (f'<a href="#site-{quote(key, safe="")}" '
                f'onclick="return goSite(\'{esc(key)}\')">'
                f'{esc(trim(name or key, n))}</a>')

    def _op_source(c):
        """Where one figure came from: the link, and where to look in it.

        Nothing on this page is allowed to be an assertion, so every
        figure carries this line. A planning figure cites the
        application and, where the adjudication recorded one, the
        document it was read out of; an external claim cites the source
        it was published in and the confidence of the match that put it
        against this site.
        """
        bits = []
        if c["source_key"] == "planning_documents":
            app, ref = c.get("application_url"), esc(c["claim_name"])
            bits.append(f'<a href="{esc(app)}" target="_blank" rel="noopener">'
                        f'{ref}</a>' if app else ref)
            doc = c.get("source_url")
            if doc and doc != app:
                bits.append(f'<a href="{esc(doc)}" target="_blank" '
                            f'rel="noopener">the document</a>')
        else:
            title = ccl.SOURCE_TITLES.get(c["source_key"], c["source_key"])
            url = c.get("source_url")
            bits.append(f'<a href="{esc(url)}" target="_blank" rel="noopener">'
                        f'{esc(title)}</a>' if url else esc(title))
        if c.get("locator"):
            bits.append(esc(c["locator"]))
        _as = c.get("as_at")
        if _as:
            bits.append(f"as at {_as.day} {_as:%B %Y}")
        if c.get("confidence"):
            bits.append(
                f'{esc(c["confidence"])} match'
                + (f' ({esc(c["method"]).replace("_", " ")})'
                   if c.get("method") else ""))
        return " · ".join(bits)

    def _op_figure(c, with_site=True):
        """One figure, its source, and what the source actually says."""
        qual = []
        if c.get("term"):
            # "Published as", not "the operator calls this". Most of
            # these are the operator's own printed phrase, but Digital
            # Realty's eleven are the JSON key the figure is carried
            # under in the page's data — published, and recorded as
            # printed, but not a phrase anybody wrote to be read.
            qual.append(f'published as “{esc(c["term"])}”')
        if c.get("stage"):
            qual.append(esc(c["stage"]))
        ev = ""
        if c.get("quote"):
            ev += ('<details><summary>What the source says</summary>'
                   f'<p class="help">{esc(trim(c["quote"], 700))}</p>'
                   '</details>')
        if c.get("evidence"):
            ev += ('<details><summary>How this was matched to the site'
                   '</summary>'
                   f'<p class="help">{esc(c["evidence"])}</p></details>')
        return (
            '<div class="claim"><p>'
            f'<strong>{float(c["value"]):,.10g} {esc(c["unit"])}</strong> '
            f'{esc(ccl.QUANTITY_LABELS.get(c["quantity_type"], c["quantity_type"]))}'
            + (f' — {_site_a(c.get("site_key"), c.get("site_name"))}'
               if with_site and c.get("site_key") else "")
            + (f' <span class="q">{esc(c["claim_name"])}</span>'
               if c.get("claim_name")
               and c["source_key"] != "planning_documents" else "")
            + '</p>'
            + f'<p class="help">{" · ".join(qual + [_op_source(c)])}</p>'
            + ev + '</div>')

    def _op_detail(r):
        """Everything the row above it counts, itemised and linked."""
        parts = []
        if r.site_names:
            parts.append(
                f'<h5>The {len(r.site_names)} site'
                f'{"" if len(r.site_names) == 1 else "s"} these figures '
                f'attach to</h5><p class="sitelist">'
                + " · ".join(_site_a(k, n, 60) for k, n in r.site_names)
                + '</p>')
        else:
            parts.append(
                '<h5>Sites</h5><p class="help">None of this operator\'s '
                'published figures has been matched to a site in this '
                'dataset, so the row above counts no sites. The figures '
                'themselves are below, with their sources.</p>')
        for key, label in _AUD:
            got = r.by_audience.get(key) or []
            if not got:
                continue
            parts.append(
                f'<h5>{esc(label)} — {len(got)} figure'
                f'{"" if len(got) == 1 else "s"}</h5>'
                + "".join(_op_figure(c) for c in got))
        return f'<div class="opdetail">{"".join(parts)}</div>'

    _op_body = "".join(
        f'<tr class="op"><td><strong>{esc(r.operator)}</strong></td>'
        f'<td class="n">{r.audiences}</td>'
        f'<td class="n">{len(r.sites) or "—"}</td>'
        + "".join(_aud_cell(r, k) for k, _ in _AUD)
        + f'<td class="help">{esc("; ".join(sorted(t for t in r.terms if t)) or "—")}</td>'
          f'</tr><tr class="detail"><td colspan="7">{_op_detail(r)}</td></tr>'
        for r in op_rows)

    # Same quantity, two audiences: the only comparison where a gap is
    # unambiguously a gap rather than two different measurements.
    _lfl = [(d, q) for d in op_divs for q in d.get("like_for_like", [])]
    _lfl.sort(key=lambda x: -x[1]["ratio"])

    def _lfl_values(values):
        return "".join(
            f'<div>{float(c["value"]):,.4g} MW '
            f'<span class="q">'
            f'{esc(dict(_AUD).get(c["audience"], c["audience"]))} — '
            f'{_op_source(c)}</span></div>'
            for c in values)

    _lfl_rows = "".join(
        f'<tr><td>{_site_a(d.get("site_key"), d["site"], 46)}</td>'
        f'<td>{esc(ccl.QUANTITY_LABELS.get(q["quantity_type"], q["quantity_type"]))}</td>'
        f'<td>{_lfl_values(q["values"])}</td>'
        f'<td class="n">{q["ratio"]:.2f}&times;</td></tr>'
        for d, q in _lfl)

    operators_html = f"""
 <p class="lede">A data centre's size is stated to at least five different audiences: the
 planning authority, the grid operator, the auditors, its customers and the environmental
 regulator. This page puts those figures beside each other, one row per operator. The
 regulator's column is the odd one out — it is the thermal rating of the standby generator
 fleet, in MWth, so it sizes what the site is built to survive rather than what it draws.</p>
 <div class="banner"><b>Read this as a description, not a scoreboard.</b>
  {esc(odis.FAIRNESS_NOTE)}</div>
 <h3>What each operator publishes, and to whom</h3>
 <p class="help">Every count in this table opens. Click a row for the sites it covers and
 for each figure behind it — the value, what the operator called it, the document or page
 it was published in, and how it was matched to a site.</p>
 <table class="stats" id="tbl-ops"><thead><tr><th scope="col">Operator</th>
  <th scope="col">Audiences</th><th scope="col">Sites here</th>
  {"".join(f'<th scope="col">{esc(lbl)}</th>' for _, lbl in _AUD)}
  <th scope="col">Terms the figures are published under</th></tr></thead>
  <tbody>{_op_body}</tbody></table>
 <p class="help">{esc(odis.METHOD_NOTE)}</p>

 <h3>The same quantity, told to two audiences</h3>
 <p>Most of the differences between these figures are not disagreements: IT load is
 supposed to be smaller than total site power, and a contracted grid connection is a
 different thing again. The comparison below is the narrow one where a gap really is a
 gap — one quantity, one site, more than one audience.</p>
 {f'<table class="stats"><thead><tr><th scope="col">Site</th><th scope="col">Quantity</th><th scope="col">Figures on record, and where each was published</th><th scope="col">Ratio</th></tr></thead><tbody>{_lfl_rows}</tbody></table>' if _lfl_rows else '<p class="help">None currently.</p>'}
 <p class="help">A ratio of 1.00× is corroboration, not coincidence: two audiences given
 the same number by the same developer, arrived at independently by this project.</p>

 <h3>Every site whose figures reached more than one audience</h3>
 <p class="help">{len(op_divs)} sites. Figures are shown in the unit each source printed,
 grouped by who was told. Site names open the site; each figure carries the source it was
 published in and, where the source is a document, what it says.</p>
 {"".join(
   f'<div class="box opsite"><h4>{_site_a(d.get("site_key"), d["site"], 70)}</h4>'
   + "".join(_op_figure(c, with_site=False) for c in d["claims"])
   + '</div>'
   for d in op_divs)}
"""

    methodology_html = f"""
 <p class="lede">How this dataset was built, what has been measured about its accuracy, and
 where its edges are. Every figure below is generated with the page, so it describes this
 release rather than an earlier one.</p>

 <h2 class="sec">How sites were found</h2>
 <p class="m">The search is deliberately wider than any story. A corpus assembled to prove a
 point cannot produce a null finding, so applications were ingested on a broad definition and
 the editorial judgement applied afterwards, to structured facts.</p>
 <ul class="m">
  <li><b>Keyword search</b> across council planning registers via the PlanIt index —
   data-centre language in the application description.</li>
  <li><b>Operator watch-list</b> — searches for named developers, operators and advisers.</li>
  <li><b>Spatial sweeps</b> around known sites, which catch the substations, grid connections
   and enabling works that never mention a data centre.</li>
  <li><b>Family links</b> — the parents and children of applications already held.</li>
  <li><b>Barbour ABI</b> project intelligence, reconciled against the planning universe in
   both directions.</li>
  <li><b>The Planning Inspectorate's</b> national infrastructure register, for the energy
   layer.</li>
 </ul>
 <p class="m">Applications cluster into sites by explicit record links, family references and
 spatial proximity. Dense urban clusters merge conservatively, so the site count is a lower
 bound: two adjacent halls of one campus may appear as two sites, never one site split in
 error. Every site's row names the routes that reached it — several independent routes to the
 same site is a stronger signal than one.</p>
 <p class="m">The result: <b>{n_sites} sites</b> and <b>{n_apps_total:,} applications</b>,
 of which {len(nsip)} nationally significant energy projects sit in a separate layer.</p>

 <h2 class="sec">How documents were retrieved</h2>
 <p class="m">Council registers run on perhaps a dozen different software platforms, each
 with its own quirks. Documents are fetched by per-platform adapters with an identifying
 User-Agent, multi-second delays, backoff on rate-limiting, and no circumvention of access
 controls. Every fetch is snapshotted; every document is content-hashed against its source
 URL, so re-runs cost nothing and nothing is stored twice.</p>
 <p class="m">Where a portal blocks automated clients outright, documents were retrieved by
 hand and are labelled as such — their citable source is the application's own register
 page. Where a council publishes nothing, that is recorded as a finished check rather than
 left looking like a gap: of the {len(none_held):,} applications holding no documents,
 {by_outcome.get('none_published', 0)} have been checked and the register genuinely
 publishes nothing.</p>
 <p class="m"><b>{n_docs:,} documents</b> are held across {len(have):,} applications. The
 outstanding tail is enumerated on the front page, never silent.</p>

 <h2 class="sec">How documents were read</h2>
 <p class="m">Facts are extracted from documents by a language model in two stages —
 structured extraction first, comparison against consenting and marketing claims second — so
 the hypothesis is never baked into the extraction. <b>Every extracted fact carries a
 verbatim quote, checked mechanically against the source text before it enters the store</b>,
 with OCR fallback for scanned documents. Quotes that fail that check are rejected rather
 than corrected.</p>
 <p class="m">{n_prose_read:,} of {n_prose:,} prose documents ({pct_prose}%) have been
 analysed. The remaining {n_graphical:,} drawings and {n_sampled - n_sampled_rd:,} unsampled
 objection letters are excluded by the selection rules above, not outstanding: counted in,
 the ratio reads {n_read:,} of {n_docs:,} ({pct}%). A second model is re-reading a subset
 independently; where the two disagree, both readings are kept and the disagreement is the
 finding.</p>

 <h2 class="sec">How power figures were adjudicated</h2>
 <p class="m">This is the part most likely to be quoted, and the part where a naive approach
 fails hardest. Planning statements argue for approval by citing the market: national demand
 forecasts, competitors' schemes, policy targets. Taking the largest megawatt figure in a
 site's documents therefore produces nonsense — under that rule one Slough application
 reported 30&nbsp;GW, which was a national storage target, and a Chiltern one 22,700&nbsp;MW,
 which was a Savills market forecast.</p>
 <p class="m">Every capacity figure is instead adjudicated for <em>whose</em> it is, and only
 those the documents attribute to the development itself are admitted. Of the twenty-two
 largest figures in the corpus, all twenty-two describe something other than the site they
 appear in.</p>
 <p class="m">Admitted figures are kept apart by quantity — IT load, total site demand, grid
 connection and standby generation are different numbers for the same site, and a single
 "site MW" column would silently mix them. Each site's headline figure carries its basis,
 its confidence and its caveat. Where a site spans several buildings, the figures may come
 from different applications; the panel names the application behind each one.</p>
 <p class="m"><b>Asking whose figure it is turned out not to be enough.</b> A second question
 had to be added — <em>what kind of quantity is this?</em> — after six families of error were
 found sitting in the gap between the two. Every stage had been faithful: the extractor
 quoted its document exactly, the adjudicator answered the question it was asked. Nobody
 asked whether a figure denominated in kW was a power figure at all.</p>
 <ul class="m">
  <li><b>Energy is not power.</b> One application gives a load as "251,859,057.50&nbsp;kW
   which equates to 94,197.29&nbsp;kWh/m²" — the unit says power, the cross-reference says
   energy. Divided by the hours in a year it is about 28.7&nbsp;MW. Untreated it entered the
   table as 251,859&nbsp;MW, four times the United Kingdom's generating capacity. Figures
   above 3&nbsp;GW are now rejected outright: no announced campus anywhere approaches it.</li>
  <li><b>Storage is not generation.</b> A 1,000&nbsp;MW battery states how fast it can
   discharge, and a UPS rating is a battery too. Both are recorded under
   <code>energy_storage</code> and excluded from the generation column.</li>
  <li><b>Thermal input is not electrical output.</b> "A Thermal Input of around 1.2&nbsp;GW"
   is fuel entering a plant, typically two to three times the electricity leaving it. Kept as
   <code>thermal_input</code>; one site's headline halved to a defensible figure once
   separated.</li>
  <li><b>A number in a table is not a capacity.</b> 116 figures rested on a quote carrying no
   unit at all — one read "80% - 480W" and became 480&nbsp;MW; another was a table of pounds
   sterling that became a 384&nbsp;MW IT load.</li>
  <li><b>A substation on a drawing is not a grid connection.</b> Four sites appeared to draw
   more than their connection could carry; the "connections" were a battery compound, a
   drawing schedule complete with the substation's floor area, an earlier scheme's plant, and
   a temporary construction supply.</li>
  <li><b>One machine is not the fleet.</b> A site recorded 2.9&nbsp;MW of standby generation
   from a single unit's specification while its documents described "38 no. 2,640&nbsp;kW
   generator units per building" — about 100&nbsp;MW. Sites where this pattern is detected
   are flagged rather than multiplied, because "26 no. 28000&nbsp;kW generators" is genuinely
   ambiguous about whether the rating is per unit or the total.</li>
  <li><b>Not every power figure in a generation column is generation.</b> Every one of the
   1,667 adjudicated on-site generation figures was read again against the passage around its
   quote and asked what it is a figure of. Seventeen sites' largest — 1,696&nbsp;MW between
   them — turned out to be something else: a battery's rating filed as "energy capacity", a
   screening threshold for "a collective combustion installation of more than 300&nbsp;MW of
   <em>heat</em> output", a thermal output stated beside the electrical one, a generator
   manufacturer's datasheet. Those figures are kept off the generation line and counted in
   its place, with the reason, so a number that disappears can still be found. Where the
   passage does not settle whether a figure describes one machine, a stated group or the
   whole site, the panel says that rather than choosing.</li>
 </ul>
 <p class="m">Nothing was deleted in correcting these. The findings, their quotes and their
 original values are untouched; what was withdrawn is only the claim that a number is a
 site's power capacity. Two apparent contradictions were left standing deliberately, because
 the documents really do assert them: one site states 218&nbsp;MW of demand against a
 connection "designed to support a power transfer capacity of 120&nbsp;MW", and another
 reserved 57&nbsp;MW "anticipated to serve the needs of building 1" for a 155&nbsp;MW
 scheme.</p>

 <h2 class="sec">What the regulator can see that these documents cannot</h2>
 <p class="m">On 29 July 2026 Ofgem published its
 <a href="{esc(_ofgem_src.url)}" target="_blank" rel="noopener">Curate consultation</a> on
 demand connections reform. Its paragraph 2.8 states that approximately 73&nbsp;GW of the GB
 demand connection queue is data centres — around 315 projects holding contracted connection
 offers of 1&nbsp;MW to 1,500&nbsp;MW — against a 2025/26 peak GB electricity demand of
 45&nbsp;GW. The project-level data behind those aggregates, NESO's mandatory Information
 Request Notice of March 2026, is not published. What can be compared is the shape of the
 two universes:</p>
 <table class="stats queue"><thead><tr><th scope="col">MW band</th>
  <th scope="col">Queue: projects</th><th scope="col">Queue: MW</th>
  <th scope="col">Queue: share</th>
  <th scope="col">Sites here: disclosed or plant-derived</th></tr></thead>
  <tbody>{queue_rows_html}</tbody></table>
 <p class="m">The queue columns are Ofgem's Table 1 — contracted connection capacity, which
 is headroom rather than consumption. This release's column counts sites whose documents
 yield a disclosed IT load, total site demand, grid connection or standby generation figure,
 banded the same way. The floor-area estimates this release shows on 43 site rows are left
 out of it: they are this project's own arithmetic, and they do not belong in a count set
 against a register of figures developers contracted for. The two universes overlap but neither contains the other: the queue
 includes projects that have never filed a planning application — Ofgem's consultation
 argues much of it never will — and this release includes the built estate back to 2015.
 The comparison shows what each side can see, not a shortfall to be subtracted. The
 asymmetry at the top end is the finding: the larger the project, the more likely its power
 figure exists only in the connection queue.</p>
 <p class="m">Two more of the consultation's findings bear directly on this dataset. At
 least 9&nbsp;GW of queue projects reclassified themselves from battery to data centre
 between May 2024 and August 2025 (paragraph 2.10), so any register that classifies projects
 by declared technology undercounts data centres — the planning-side counterpart is the
 naming-invisibility cases this corpus tracks. And NESO's voluntary
 <a href="{esc(_cfi_src.url)}" target="_blank" rel="noopener">call for input</a> on the
 demand queue found only 32% of data centre projects had secured an off-taker, and 71 of 148
 reported financial commitment with FID evidence — NESO's own caveat: developer intent, not
 confirmed deliverability. These aggregates are deliberately not joined to the sites here:
 the sources measure different quantities, and the anonymised ones cannot be matched to a
 site without guessing. The full set, with verbatim quotes, locators and access dates, is on
 the workbook's External aggregates sheet.</p>
 <p class="m">Consumption is the measurement the queue cannot make. DESNZ's
 <a href="{esc(_desnz_src.url)}" target="_blank" rel="noopener">sub-national electricity
 statistics</a> record what large users actually drew: Half-Hourly-metered non-domestic
 consumption — the meter class data centres belong to — published at local-authority level
 only, because below that level the source carries no half-hourly meters at all. Between
 2019 and 2024 that consumption fell {abs(_d_nat)}% nationally, while rising
 {_d_slough}% in Slough and {_d_hillingdon}% in Hillingdon — the two largest absolute rises
 of any GB local authority. The nulls are as visible as the rises: Tower Hamlets, holding
 the Docklands cluster, fell {abs(_d_towerhamlets)}%, and Hertsmere, with data-centre sites
 of its own in this dataset, fell {abs(_d_hertsmere)}%. Each site panel carries its own
 authority's change beside the national one where the authority maps cleanly
 ({ctx_mapped} of {n_sites} sites; the remainder span more than one authority, sit outside
 Great Britain, or record no authority at all). The figure describes the authority, never
 the site: an authority's total covers all its large users, the series ends in 2024 — so
 sites energised since are not in it — and authority figures are floors, because DESNZ
 could not place a national remainder of roughly 2.9&nbsp;TWh in any authority.</p>

 <h2 class="sec">Known limits of this release</h2>
 <ul class="m">
  <li><b>Reading is incomplete on some sites.</b> {n_prov} of {n_sites} sites have prose
   documents still outstanding, and their findings-derived values are floors that can
   rise.</li>
  <li><b>Acquisition has a tail.</b> {len(none_held) - by_outcome.get('none_published', 0):,}
   applications are still to be retrieved or are on portals not yet readable.</li>
  <li><b>Council statuses are point-of-ingest</b> and a refresh pass is pending.</li>
  <li><b>Water is reported as cooling method, not volume</b> — see the front page.</li>
  <li><b>Some truths are invisible in application metadata.</b> A ground-truth exercise found
   10 cases in 50 that could not be resolved without reading the documents; only deep-read
   settles those.</li>
 </ul>

 <h2 class="sec">Provenance</h2>
 <p class="m">Aggregate → site → application → document → quote. Every number in this
 package walks back to a source document, its portal URL, its fetch timestamp and the model
 that read it. Where a link in that chain is inferred — a fuzzy name match, a spatial
 cluster, a model verdict — the inference is stored beside the original record with its
 method named. Original records are never overwritten, and re-runs add rows rather than
 replacing them.</p>

 <h2 class="sec">Conditions of use</h2>
 <p class="m">Barbour ABI project data is licensed for this use and <b>requires attribution
 in published output</b>. Consultation responses are reproduced as councils published them
 and contain objectors' names and addresses; personal contact details are excluded
 throughout. Documents marked as obtained by hand should be cited to the application's
 register page, not to this archive.</p>
"""

    # Working notes from the AI assistant that built the pipeline. Kept
    # deliberately separate from the data pages and labelled as what it
    # is: nothing here is a finding, and every factual claim points at a
    # site, a column or a document the reader can open. The value is in
    # the failure modes — a reporter who knows how this data can mislead
    # is better armed than one handed a clean-looking number.
    # §8a wants the pitfalls on the Start page "verbatim" from the notes.
    # Lifted from the rendered notes rather than written twice: a
    # restatement is a second copy that drifts, and this list is the
    # project's own account of how it got numbers wrong.
    def _pitfalls_from_notes(html: str, limit: int = 5) -> str:
        """The brief's second card, built from the notes rather than
        written twice: 4px caution rule, five items, each separated by a
        hairline with its lead in 600 and its body under it."""
        import re as _re
        m = _re.search(r'<h2 class="sec">Where this data can mislead.*?</h2>'
                       r'\s*<p class="m">(.*?)</p>\s*<ul class="m">(.*?)</ul>',
                       html, _re.S)
        if not m:
            return ""
        intro, items_html = m.group(1), m.group(2)
        out = []
        for li in _re.findall(r"<li>(.*?)</li>", items_html, _re.S)[:limit]:
            lead = _re.match(r"\s*<b>(.*?)</b>(.*)", li, _re.S)
            if lead:
                out.append(f'<div class="pit"><div class="pith">{lead.group(1)}</div>'
                           f'<p>{lead.group(2).strip()}</p></div>')
            else:
                out.append(f'<div class="pit"><p>{li.strip()}</p></div>')
        return (f'<div class="card card-warn">'
                f'<h2 class="cardh">Where this data can mislead</h2>'
                f'<p class="cardintro">{intro}</p>{"".join(out)}'
                f'<p class="help">Verbatim from the assistant\u2019s notes, which carry '
                f'the rest of them. <button type="button" class="linkish" '
                f'onclick="show(\'notes\')">Read the notes</button></p></div>')

    assistant_notes_html = f"""
 <p class="lede">Working notes from the AI assistant that built this pipeline. <b>This is not
 editorial content and nothing here is a finding.</b> It is a record of what the data looks
 like from the inside: what seems worth pulling on, where it can mislead, what should be
 checked before anything is published, and where to look next. Every claim below can be
 traced to a site, a column or a document in this release — if something here cannot be
 verified that way, treat it as an opinion and discard it.</p>

 <h2 class="sec">What looks worth pulling on</h2>
 <p class="m"><b>The silences are the strongest material.</b> This dataset's most unusual
 property is that it can show what applications <em>do not</em> say. Two examples are
 already visible: sites whose documents were read in full and state no capacity figure at
 all, and — more striking — the majority of on-site generation figures that name no fuel and
 no plant type. For an investigation that began by asking whether operators disclose
 generation contradicting their public renewable positioning, "most of them do not say what
 it burns" is a finding about disclosure itself, and it is measurable here rather than
 anecdotal.</p>
 <p class="m"><b>The gap between demand and grid connection.</b> A handful of sites state
 they will draw materially more than the connection their own documents describe. Those are
 not errors — they have been checked by hand — and they raise a question the planning file
 cannot answer: where does the rest come from, and when. Two such sites are flagged in this
 release.</p>
 <p class="m"><b>Generation far below stated load — read the passage before reading the
 ratio.</b> Where the on-site generation figure is a small fraction of the stated load, the
 obvious reading is life-safety standby on a grid-dependent site. On this corpus that
 reading is usually wrong: the generation figure is often one machine's rating standing in
 for a fleet (Watford Bypass: 3.2 MW beside "112 No. standby generators"; Amazon Didcot once
 recorded 2.9 MW from one unit's specification where the same documents describe about
 100 MW), or rooftop solar counted as generation. The site panel now says which it is,
 and names any fleet the documents disclose by count and rating — without multiplying.
 Across the 47 sites stating both figures the ratio's median is 0.75 and the modal case is
 below half, so no band of it diagnoses the engineering; it says where to look.</p>
 <p class="m"><b>Energy parks with a data centre attached.</b> Several records pair a data
 centre with generation or storage far larger than the computing load — the scheme's centre
 of gravity is arguably the power project, not the building. Worth deciding, per site, which
 story is being told.</p>

 <h2 class="sec">Where this data can mislead — pitfalls found the hard way</h2>
 <p class="m">Each of these produced a wrong number during construction and was corrected.
 They are listed because the same traps apply to anyone doing their own analysis over the
 workbook or the database.</p>
 <ul class="m">
  <li><b>The largest number in a document is almost never the site's.</b> Planning statements
   argue by citing the market. Of the twenty-two largest megawatt figures in this corpus, all
   twenty-two describe something else — a national target, a competitor, a forecast. Any
   analysis that takes a maximum will be wrong.</li>
  <li><b>Not everything measured in megawatts is power.</b> Annual energy, thermal input,
   battery discharge ratings and UPS capacity all appear in MW or kW and mean different
   things. They are separated here; they will not be in a raw extract.</li>
  <li><b>A figure may be per building, per hall or per phase.</b> Multiplying is sometimes
   right and sometimes double-counting, and the documents are often ambiguous about which.
   Where this release detects the pattern it flags rather than multiplies.</li>
  <li><b>Table rows lie.</b> A number lifted from a table without its column headers can be
   anything — pounds, square metres, a row index. Where a quote carries no unit, the figure
   is not treated as a capacity.</li>
  <li><b>A regex sweep over this corpus produces mostly false positives.</b> Searching for
   "MW" finds manhole annotations, EV charger ratings and postcodes (TW6 2GW). Findings here
   went through an adjudication step for that reason.</li>
  <li><b>Some evidence quotes are OCR garbage.</b> Every quote was machine-verified to appear
   in its source document, which guarantees fidelity, not legibility — a scanned page can
   yield a verbatim-true but unreadable quote. Check the source document before quoting
   anything that reads oddly.</li>
 </ul>

 <h2 class="sec">What deserves a human before publication</h2>
 <ul class="m">
  <li><b>Any figure you intend to print.</b> Open the site panel, read the quote, then open
   the source document. The chain is built for exactly this and takes a minute.</li>
  <li><b>Sites flagged as partly read.</b> Their values are floors and can only rise. A site
   promoted publicly as 1&nbsp;GW may show less here purely because the document saying so
   has not been analysed.</li>
  <li><b>Sites whose applications span more than one council.</b> Clustering is by proximity,
   so two schemes standing near each other can be merged into one record. Where this release
   detects it, the site is flagged rather than silently reconciled.</li>
  <li><b>Generation figures without a fuel.</b> The absence is real and reportable, but
   before writing that a specific operator has undisclosed diesel, read that site's
   documents directly.</li>
  <li><b>Anything adjudicated by a single model.</b> Where two readers agree, a figure is
   corroborated; where only one read it, it rests on one judgement.</li>
 </ul>

 <h2 class="sec">Where I would look next</h2>
 <p class="m">These are suggestions for reporting, not work this pipeline has done. Each
 would independently test what the planning documents claim.</p>
 <ul class="m">
  <li><b>Grid connection registers.</b> Distribution network operators publish embedded
   capacity registers, and the electricity system operator publishes the transmission
   connections queue. These record what a site has actually applied for and been offered —
   independent of what an applicant tells a council. For the sites here that disclose no
   capacity, or whose stated demand exceeds their connection, that is the natural check.</li>
  <li><b>Companies House.</b> Applicants are frequently special-purpose vehicles. Officers,
   persons of significant control and registered addresses are the route from an SPV to the
   operator behind it. This dataset deliberately does not fuzzy-match company names, because
   near-identical names are often genuinely different companies — which is exactly the
   distinction an ownership story turns on.</li>
  <li><b>Planning appeals.</b> Refused applications generate appeal evidence that is
   cross-examined and often far more candid than the original submission. Nothing from the
   appeals system is in this release.</li>
  <li><b>Environmental permits.</b> Combustion plant above certain thresholds needs a permit
   naming fuel, capacity and running hours — a direct cross-check on the generation figures
   here, and on the sites that name no fuel at all.</li>
  <li><b>Ask the operators.</b> The clearest questions this data raises are simple ones: what
   will the site draw at full build, what fuel does the standby plant burn, how many hours a
   year is it expected to run, and where is the connection coming from.</li>
 </ul>

 <h2 class="sec">What I would not claim from this data</h2>
 <ul class="m">
  <li><b>That the dataset is complete.</b> A tail of applications is still being retrieved,
   and coverage of Northern Ireland is minimal.</li>
  <li><b>That a site with no capacity figure is small.</b> It may simply not have said.</li>
  <li><b>That totals across sites are meaningful without care.</b> Sites state different
   quantities — IT load, total demand, grid connection — and summing them mixes categories.</li>
  <li><b>That absence of a fuel type means absence of fossil generation.</b> It means the
   documents in hand do not say.</li>
 </ul>
"""


    out = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>UK datacentre plans v2, phase {args.phase} release</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- The gate is there to stop the link being passed around, so the page
     should not turn up in a search either. -->
<meta name="robots" content="noindex, nofollow, noarchive">
<style>{CSS}</style></head><body>
<header class="masthead"><div class="mhead">
 <h1>UK datacentre plans</h1>
 <div class="sub">v2, phase {args.phase} · {n_sites} sites ·
 {len(app_rows):,} applications · {n_docs:,} documents ·
 {n_findings_total:,} verified findings ·
 generated {dt.datetime.now(dt.timezone.utc):%-d %b %Y %H:%M} UTC ·
 pipeline {esc(hv._git_commit())}</div></div></header>
<nav class="top"><div class="navinner">
 <button id="tab-start" aria-selected="true" onclick="show('start')">Start here</button>
 <button id="tab-signals" aria-selected="false" onclick="show('signals')">Signals<span class="pill">{n_signals}</span></button>
 <button id="tab-sites" aria-selected="false" onclick="show('sites')">Sites<span class="pill">{n_sites}</span></button>
 <button id="tab-apps" aria-selected="false" onclick="show('apps')">Applications<span class="pill">{len(app_rows):,}</span></button>
 <button id="tab-energy" aria-selected="false" onclick="show('energy')">Energy projects<span class="pill">{len(nsip)}</span></button>
 <button id="tab-map" aria-selected="false" onclick="show('map')">Map</button>
 <button id="tab-operators" aria-selected="false" onclick="show('operators')">Operators<span class="pill">{len(op_rows)}</span></button>
 <button id="tab-method" aria-selected="false" onclick="show('method')">Methodology</button>
 <button id="tab-dict" aria-selected="false" onclick="show('dict')">Data dictionary</button>
 <button id="tab-notes" aria-selected="false" onclick="show('notes')">Assistant's notes</button>
</div></nav>

<section id="view-start" class="view on"><div class="wrap wide">
 <p class="lede">Every planning application we can find for a UK data centre or its
 supporting power infrastructure, the documents councils published with them, and what those
 documents say. Assembled from council planning registers, the Planning Inspectorate's
 national infrastructure register, and Barbour ABI project intelligence.</p>

 <div class="startgrid">
 <div class="startmain">

 <!-- §2 of the design brief, as written: white card, 4px brand top rule,
      two equal columns each with a 3px left rule and an uppercase label
      in the rule's colour. The red is the brief's news red and belongs
      to signals; caution is the orange below. They were never competing
      for the same job — collapsing them was my error, not the brief's. -->
 <div class="card card-brand">
  <h2 class="cardh">Two ways in, and they are not the same thing</h2>
  <div class="twoways">
   <div class="way way-signals">
    <div class="waylab">Signals</div>
    <p>Named queries over the adjudicated findings — cohorts of sites that share a
     measurable property. Each one shows its own definition and the script that produces
     it. No model chooses what appears, and no cohort is a conclusion.</p>
    <button type="button" class="cta" onclick="show('signals')">Open the signal list</button>
   </div>
   <div class="way way-data">
    <div class="waylab">The data</div>
    <p>The full tables, unchanged: every site, application, energy project and operator,
     with every column, every caveat and every figure traceable to a document, a page and
     the model that read it.</p>
    <button type="button" class="cta secondary" onclick="show('sites')">Open the sites table</button>
   </div>
  </div>
 </div>

 <div class="stat">
  <button onclick="show('sites')"><span>{n_sites}</span><small>sites</small></button>
  <button onclick="show('apps')"><span>{n_apps_total:,}</span><small>applications</small></button>
  <button onclick="show('energy')"><span>{len(nsip)}</span><small>energy projects</small></button>
  <div><span>{n_docs:,}</span><small>documents held</small></div>
  <div><span>{n_prose_read:,}</span><small>prose analysed ({pct_prose}%)</small></div>
 </div>

 <details class="banner banner-d"><summary>About these numbers</summary>
 <div><b>Nearly all of the readable material has been read.</b>
 {n_prose_read:,} of {n_prose:,} prose documents ({pct_prose}%) have been analysed — the
 planning and energy statements, officer reports, consultee responses and screening
 opinions, which is where disclosures live. Two classes are excluded on purpose and are not
 a gap: {n_graphical:,} drawings, elevations and location plans carry no extractable prose,
 and {n_sampled_rd:,} of {n_sampled:,} near-identical objection letters were sampled rather
 than read exhaustively, because their value is aggregate sentiment rather than unique fact.
 Counting all three together gives {n_read:,} of {n_docs:,} ({pct}%), which understates the
 reading rather than describing it.<br><br>
 <b>{n_prov} of {n_sites} sites still have prose outstanding.</b> On those rows every
 findings-derived value — capacity, generator counts, cooling method, the names involved —
 is a <em>floor</em>: the largest or fullest we have seen so far. Further reading can raise
 these figures and cannot lower them, so a campus promoted as 1GW may show a smaller number
 here simply because the document stating the larger figure has not been analysed yet. Those
 rows are marked <em>(prior to complete deep read)</em> and can be isolated with the Sites
 filter. A small tail of applications is also still being retrieved. Both are completed in
 the next release.
 <p class="m"><b>Read twice: not yet done.</b> Every document here has been read once. A
 second reading, by a different model against the same pages, is what would turn "no
 capacity disclosed" from an absence of evidence into evidence of absence — and it has not
 been carried out. Where this release says a site discloses nothing, it means nothing was
 found on one pass, which is the weaker claim.</p></div></details>

 {_pitfalls_from_notes(assistant_notes_html)}
 </div>

 <aside class="startside">
  <div class="card card-brand">
   <h2 class="sideh">Coverage, stated as a boundary</h2>
   <div class="crow"><span>Documents held</span><b>{n_docs:,}</b></div>
   <p class="cnote">Across {n_apps_with_docs:,} of {n_apps_total:,} applications. Of the
    {n_apps_no_docs:,} holding none, {n_apps_checked_empty:,} have been checked and the
    register genuinely publishes nothing.</p>
   <div class="crow"><span>Prose analysed</span><b>{n_prose_read:,} ({pct_prose}%)</b></div>
   <p class="cnote">The remainder is in the deep-read queue or awaiting OCR. Every figure
    in this release is a floor.</p>
   <div class="crow"><span>Sites disclosing a capacity</span><b>{len(site_mw_values)} of {n_sites}</b></div>
   <p class="cnote">The other {n_sites - len(site_mw_values)} split into sites read in full
    that state nothing, sites partly read, and sites with no documents. Never combined into
    one number.</p>
   <div class="crow"><span>Verified findings</span><b>{n_findings_total:,}</b></div>
   <p class="cnote">Each checked verbatim against its source text before storage. Quotes
    that failed the check were rejected, not corrected.</p>
   <div class="crow"><span>Read twice</span><b>Not yet done</b></div>
   <p class="cnote">Reading the corpus a second time, so a silence can be evidence of
    absence rather than an absence of evidence. Not carried out for this release.</p>
  </div>
  <div class="card card-ink">
   <h2 class="sideh">The rest of the package</h2>
   <p class="cnote">This reader is one artefact in the release, not the whole of it.</p>
   <button type="button" class="cta secondary"
    onclick="document.getElementById('package').scrollIntoView()">Workbook, database,
    Drive, Pinpoint, notebook</button>
  </div>
 </aside>
 </div>

 <h2 class="sec">The shape of it</h2>
 <p class="help">Both charts read the dataset as it stands today. Neither depends on the
 deep read, so neither changes as the remaining documents are analysed — but both will move
 as the tail of applications is retrieved.</p>
 <div class="charts">{chart_years}{chart_bands}</div>

 <h2 class="sec" id="package">What the package contains</h2>
 <div class="parts">
  <div class="part"><h3><a href="#sites" onclick="show('sites');return false">Sites</a>,
    <a href="#apps" onclick="show('apps');return false">Applications</a>,
    <a href="#energy" onclick="show('energy');return false">Energy projects</a>,
    <a href="#map" onclick="show('map');return false">Map</a><span class="pill">this web
    portal</span></h3>
   <p class="what">Each site expands to its full proposal text, power breakdown, generation
    and cooling evidence, who is behind it, its planning applications with links to the
    council's own register, and what the documents were found to say.</p>
   <p class="when"><b>Reach for it when</b> you want to read a site and follow it outward.</p></div>
  <div class="part"><h3><a href="#notes" onclick="show('notes');return false">Assistant's
    notes</a><span class="pill">this web portal</span></h3>
   <p class="what">A record of what this data looks like from the inside, written by the AI
    assistant that built the pipeline: which silences look like the strongest material, where
    the figures can mislead, what to check before publishing, and where to look next.
    <b>Nothing in it is a finding</b> — every claim points at a site, a column or a document
    you can open, and anything that cannot be traced that way is an opinion to discard.</p>
   <p class="when"><b>Reach for it when</b> you want the failure modes before the numbers —
    or a shortlist of what to pull on first.</p></div>
  <div class="part"><h3><a href="#method" onclick="show('method');return false">Methodology</a>
    · <a href="#dict" onclick="show('dict');return false">Data dictionary</a><span
    class="pill">this web portal</span></h3>
   <p class="what">How sites were identified, how documents were retrieved and read, how
    power figures were adjudicated — and what every column in the workbook means.</p>
   <p class="when"><b>Reach for it when</b> an editor or a subject asks how a number was
    arrived at. The <b>?</b> beside any column heading jumps straight to its definition.</p></div>
  <div class="part"><h3>Workbook<span class="pill">spreadsheet</span></h3>
   <p class="what">The same rows with all {len(hv.SITE_HEADERS)} columns, filterable and
    pivotable, with a provenance sheet — and the sheets behind the Operators view:
    every capacity claim, what each operator tells which audience, and the figures
    for sites told more than one thing.</p>
   <p class="when"><b>Reach for it when</b> you want to slice the data yourself.
    &nbsp;<a href="{WORKBOOK_SHEET_URL}" target="_blank" rel="noopener">Open the
    spreadsheet</a> <span class="help">· or the .xlsx
    <a href="{DRIVE_ROOT}" target="_blank" rel="noopener">on Drive</a></span></p></div>
  <div class="part"><h3>Source documents<span class="pill">Drive</span></h3>
   <p class="what">The council documents themselves, filed by site and by application. Every
    Drive link in these tables lands in the right folder. Each site's folder also carries a
    <b>site report</b> (the applications, parties and Barbour record, in prose) and a
    <b>findings CSV</b> — every verified finding for that site, one row each, naming the
    document file beside it, where in that document it appears, the verbatim quote and
    the model that read it. Only a PDF has pages, so a Word file cites a section and a
    workbook a sheet — the column says which, because it is what you follow to check
    a quote.
    Both are named after the site, so they stay identifiable outside their folders.</p>
   <p class="when"><b>Reach for it when</b> you need the original to quote or verify — or
    everything extracted from one site in a single file.
    &nbsp;<a href="{SITES_URL}" target="_blank" rel="noopener">Open the site
    folders</a></p></div>
  <div class="part"><h3>Interrogate planning summaries on Notebook<span class="pill">Gemini
    Notebook</span></h3>
   <p class="what">Every site's report and its full findings table, one document per site,
    loaded into a notebook you can question in plain language — "which sites mention gas
    turbines?", "who is the agent on the Slough applications?". It answers from these
    documents and cites the site it drew each answer from. What it holds is <b>this
    project's summaries</b> of the corpus, not the council documents themselves.</p>
   <p class="when"><b>Reach for it when</b> the question spans sites and you would otherwise
    be opening folders one at a time. Check anything you intend to publish against the site
    row or the document itself — the notebook is a way in, not a source.
    &nbsp;<a href="{NOTEBOOK_URL}" target="_blank" rel="noopener">Open the notebook</a></p></div>
  <div class="part"><h3>Interrogate all planning documents on Pinpoint<span
    class="pill">Pinpoint</span></h3>
   <p class="what">The council documents themselves — every planning application document
    holding prose — as one full-text searchable collection. Where the notebook above holds
    this project's summaries, this holds the source material, so a phrase that no one
    thought to extract is still findable. Drawings and exact duplicates are excluded:
    a drawing carries no text to search, and the same document is routinely filed against
    several applications for one site. Pinpoint has no folders, so each filename carries its
    site and application in front of it.</p>
   <p class="when"><b>Reach for it when</b> you want to search wording across the whole
    corpus rather than read a site — a phrase, a company name, a consultant. It is a search
    index, not the archive of record: the PDFs are recompressed to fit Pinpoint's quota, so
    quote from the Drive original when the passage spans a table or a multi-column page.
    &nbsp;<a href="{PINPOINT_URL}" target="_blank" rel="noopener">Open the
    collection</a></p></div>
  <div class="part"><h3>Query database<span class="pill">DuckDB</span></h3>
   <p class="what">Every site, application, document and finding in one file
    (<code>dc_phase{args.phase}.duckdb</code>, ~106 MB). Opens in DuckDB CLI, Python, R or
    the DuckDB web shell.</p>
   <p class="when"><b>Reach for it when</b> the question is not in a column.
    &nbsp;<a href="{DRIVE_ROOT}" target="_blank" rel="noopener">Open it on Drive</a></p></div>
 </div>

 <h2 class="sec">Where the applications stand</h2>
 <table class="stats"><tbody>
  <tr><th scope="row">Applications in the dataset</th><td class="n">{n_apps_total:,}</td>
      <td class="n">100%</td><td class="help">Every application attached to a site here.</td></tr>
  <tr class="lead"><th scope="row">With documents retrieved</th><td class="n">{len(have):,}</td>
      <td class="n">{_pc(len(have))}</td>
      <td class="help">Applications, not documents — {n_docs:,} documents were retrieved
       across these {len(have):,}.</td></tr>
  <tr class="lead"><th scope="row">No documents held</th><td class="n">{len(none_held):,}</td>
      <td class="n">{_pc(len(none_held))}</td>
      <td class="help">Broken down below — most of it is finished work, not a gap.</td></tr>
  {app_stats_rows}
 </tbody></table>

 <h4 class="sub-head">Analysis, across the {len(have_prose):,} applications holding prose
 documents</h4>
 <p class="help">Counted over prose only. Drawings are excluded because the deep read skips
 them by design, so an application is not half-read on account of a location plan.
 The repetitive classes — objections, neighbour comments, petitions and correspondence —
 are counted separately above and read at one in five by policy, not left outstanding.
 A further {n_no_text:,} documents are held and contain no words at all — photographs of
 site notices, plans filed as images — read as blank by two independent text recognisers.
 They are named rather than counted as unanalysed: an unreadable document is a different
 thing from an unread one, and only one of the two can be fixed by reading.</p>
 <table class="stats"><tbody>
  <tr><th scope="row">Every prose document analysed</th><td class="n">{full_read:,}</td>
      <td class="n">{_pc(full_read, len(have_prose))}</td>
      <td class="help">Findings for these are complete as far as the documents go.</td></tr>
  <tr><th scope="row">Partially analysed</th><td class="n">{part_read:,}</td>
      <td class="n">{_pc(part_read, len(have_prose))}</td>
      <td class="help">Values are floors: further reading can raise them.</td></tr>
  <tr><th scope="row">Not yet analysed</th><td class="n">{un_read:,}</td>
      <td class="n">{_pc(un_read, len(have_prose))}</td>
      <td class="help">Documents are held and readable; nothing has been extracted yet.</td></tr>
 </tbody></table>
 <p class="help">A further {n_outside:,} documents sit outside these figures, on applications
 that were retrieved, reviewed and judged not to be data centres. They stay in the corpus —
 counter-evidence is part of the record — but they are not part of this dataset's
 {n_docs:,}.</p>

 <h2 class="sec">Three things to know before quoting anything</h2>
 <p><b>Power figures are adjudicated, not maxima.</b> Planning statements quote the market
 constantly. Of the twenty-two largest megawatt figures in this corpus, all twenty-two
 describe something other than the site they appear in. Only figures the documents attribute
 to the development itself are used, and each carries its basis and confidence.</p>
 <p><b>Figures from partly-read sites are floors.</b> See the note above: they can rise.</p>
 <p><b>Water is reported as cooling method, not volume.</b> The water findings are dominated
 by drainage and flood engineering every development produces; only 93 sites disclose
 anything about consumption. A volume would imply a precision the applications do not
 contain — and that silence is itself worth reporting.</p>
</div></section>

<section id="view-signals" class="view"><div class="wrap wide">{signals_html}</div></section>

<section id="view-site" class="view">
<div class="sitepage">
 <p class="sitenav"><a href="#sites" onclick="return backToSites()">← Back to the sites
  table</a> <span class="help">Filters, chips and sort are as you left them.</span></p>
 <h2 id="sitetitle"></h2>
 <p class="sitewhere"><span id="sitewhere"></span> <span class="q" id="sitekey"></span></p>
 <div id="sitehost"></div>
</div>
</section>

<section id="view-sites" class="view">
<div class="controls">
 <input type="search" id="q" placeholder="Search site, council, address, applicant, proposal…">
 <select id="f">
  <option value="all">All sites</option>
  <option value="power">Only sites with a power figure</option>
  <option value="known">Only fully-read sites</option>
  <option value="unknown">Only where reading or acquisition is incomplete</option>
  <option value="prov">Only sites whose figures may rise</option>
  <option value="energy">Only sites near a national energy project</option>
 </select>
 <select id="o"><option value="">Any origin</option>
  {''.join(f'<option value="{esc(o)}">{esc(o)}</option>' for o in origin_opts)}</select>
 <button type="button" id="big" class="toggle" aria-pressed="false">100 MW or greater</button>
 <label class="chk" id="unklab"><input type="checkbox" id="unk"> Exclude unknown MW
  consumption</label>
 <span class="count" id="n"></span>
 <button type="button" id="seemap" class="linkish">See all on map</button><span
  class="tip" tabindex="0" role="note" aria-label="Why the map may show fewer sites
 than the table">?<span class="tiptext">The map can only show sites with a recorded
 location. {n_no_coords} of {n_sites} sites have none — usually because the council
 published no grid reference and the address could not be resolved — so they stay in the
 table but never appear as a pin. The link says how many of the sites you have filtered
 to can be shown, and how many cannot.</span></span>
</div>
<!-- No chip per organisation. Luke, 2026-08-25: "I don't really think we
     need a button at the top of the page for each participant" — a badge
     in the row is where a reader meets the name, and clicking it there
     is the filter. 164 names would otherwise be 164 buttons above a
     table nobody has looked at yet. What a chip row did carry, and a
     badge cannot, is the fact that a filter is ON and how to leave: that
     is this bar, which appears only when one is. -->
<div class="chips" id="whobar" hidden role="status">
 <span class="chiplabel">Who's behind it</span>
 <span id="whonow"></span>
 <button type="button" class="chip" onclick="setWho('')">Clear</button>
 <span class="help">{n_who_named} of {n_sites} sites name an end user or a client;
  the rest say so. Clicking a name in the table filters the table and the map together.</span>
</div>
<div class="chips" id="cohortchips" role="group" aria-label="Filter by what the documents say">
 <span class="chiplabel">What the documents say</span>
 <button type="button" class="chip on" data-cohort="" onclick="setCohort('')"
  aria-pressed="true">Any</button>
 {cohort_chips}
 <span class="help">Each chip is a named rule over the adjudicated figures, with its
  definition and limits on the <a href="#signals" onclick="show('signals');return false">Signals</a>
  tab. The count is the number of rows the chip leaves.</span>
</div>
<table id="tbl-sites"><thead><tr>
 <th>{dl("Sites","Site name","Site")}</th>
 <th>{dl("Sites","End user (Barbour); Applicant of record (Barbour); "
          "Advisers (Barbour)","Who's behind it")}</th>
 <th data-num="1">{dl("Signals","Cohort","Signals it matches")}</th>
 <th data-num="1">{dl("Sites","Power MW (best available)","Power MW")}</th>
 <th data-num="1">{dl("Sites","External power indicators","Power indicators")}</th>
 <th>{dl("Sites","Capacity status","Status")}</th>
 <th>{dl("Sites","Latitude / Longitude / Coordinate source","Location")}</th>
 <th data-num="1">{dl("Sites","Documents held / Documents analysed","Read")}</th>
</tr></thead><tbody>{''.join(body)}</tbody></table></section>

<section id="view-apps" class="view">
<div class="controls"><span class="count">{len(app_rows):,} applications. The document count
 links to that application's folder on Drive; Source opens the council's own register.</span></div>
<table id="tbl-apps"><thead><tr><th>Reference</th><th>Council</th><th>Status</th>
 <th>Received</th><th>{dl("Applications","Verdict (latest) / confidence / model / reasoning","Verdict")}</th>
 <th data-num="1">{dl("Applications","Drive folder","Documents")}</th>
 <th data-num="1">{dl("Sites","Verified findings","Findings")}</th>
 <th>{dl("Applications","Portal URL","Source")}</th><th>Proposal</th></tr></thead>
<tbody>{''.join(approws_all)}</tbody></table></section>

<section id="view-energy" class="view">
<div class="controls"><span class="count">{len(nsip)} nationally significant energy projects,
 nearest data-centre site first. Metadata only — no project documents fetched.</span></div>
<table id="tbl-energy"><thead><tr><th>Project</th>
 <th>{dl("Energy projects","All columns","Stated capacity")}</th><th>Type</th>
 <th>Stage</th><th>Applicant</th><th>Region</th><th data-num="1">Nearest site</th>
 <th>Source</th><th>Description</th></tr></thead>
<tbody>{''.join(h for _, h in energyrows)}</tbody></table></section>

<section id="view-map" class="view">
<div id="mapwrap">
 <aside id="mapside">
  <input type="search" id="mq" placeholder="Search site, council, applicant…">
  <div class="mgroup">
   <label class="chk"><input type="checkbox" id="ms" checked> Data-centre sites</label>
   <label class="chk"><input type="checkbox" id="me" checked> Energy projects</label>
  </div>
  <div class="mgroup">
   <label class="chk" for="mcohort">Mark the sites in a signal</label>
   <select id="mcohort">{cohort_options}</select>
  </div>
  <div class="mgroup">
   <button type="button" id="mbig" class="toggle" aria-pressed="false">100 MW or greater</button>
   <label class="chk off" id="munklab"><input type="checkbox" id="munk" disabled>
    Exclude unknown MW consumption</label>
  </div>
  <button type="button" id="mreset" class="toggle">Reset view and filters</button>
  <p class="count" id="mapcount"></p>
  <div id="mapkey">
   <div><span class="pin s"></span> data-centre site</div>
   <div><span class="pin e"></span> energy project</div>
   <div id="mapcohortkey" hidden><span class="pin s inco"></span>
    in <span id="mapcohortname"></span></div>
  </div>
  <p class="help">Click a marker for its details. Double-click the map to zoom in
   where you click.</p>
  <p class="help attrib">Tiles © <a href="https://www.openstreetmap.org/copyright"
   target="_blank" rel="noopener">OpenStreetMap</a> contributors. Sites without
   coordinates are absent.</p>
 </aside>
 <div id="mapview">
  <div id="maptiles"></div><div id="mappins"></div>
  <div id="mapsubset" class="mapoverlay" hidden><span id="mapsubsettext"></span><button
   type="button" id="mapsubsetclear" class="linkish">Clear this selection</button></div>
  <div id="mapinfo" class="mapoverlay" hidden></div>
  <div id="mapzoom" class="mapoverlay"><button id="mzin" title="Zoom in">+</button>
   <button id="mzout" title="Zoom out">−</button></div>
 </div>
</div>
</section>

<section id="view-operators" class="view"><div class="wrap">{operators_html}</div></section>

<section id="view-method" class="view"><div class="wrap">{methodology_html}</div></section>

<section id="view-notes" class="view"><div class="wrap">{assistant_notes_html}</div></section>

<section id="view-dict" class="view"><div class="wrap">
 <p class="lede">What every column contains and how it was derived. The same definitions
 appear on the workbook's Read me sheet, so a column cannot mean one thing there and
 another here.</p>
 {''.join(dict_html)}
</div></section>

<footer><b>Please do not forward this link or the password.</b> This
 supports unpublished reporting. Barbour ABI data is licensed and requires credit in published output. Personal
 contact details are excluded throughout. Distances are straight-line, to the nearest site we
 hold coordinates for. A blank stated capacity on an energy project means its PINS page states
 none.</footer>
<script>const MAPPTS={map_payload};</script>
<script>{MAP_JS}{JS}initMap();</script></body></html>"""

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")
    # The published page is the same artefact, not a variant of it: the
    # methodology and dictionary are generated here, so a hand-copied
    # docs/index.html is a second version of them waiting to disagree.
    if args.publish:
        args.publish.parent.mkdir(parents=True, exist_ok=True)
        args.publish.write_text(out, encoding="utf-8")
        print(f"  also wrote {args.publish} (EdgeOne deployment root)")
    # No silent gaps: every site panel either carries the consumption
    # context or is counted here, and unknown council prefixes are named.
    assert ctx_mapped + ctx_unmapped == n_sites, \
        (ctx_mapped, ctx_unmapped, n_sites)
    print(f"wrote {args.out} ({len(out)/1024/1024:.1f} MB) — {n_sites} sites, "
          f"{len(app_rows)} applications, {len(nsip)} energy projects, "
          f"{n_prov} sites marked provisional")
    print(f"  Consumption context: {ctx_mapped} site panels carry the DESNZ "
          f"sentence, {ctx_unmapped} do not (several authorities, Northern "
          f"Ireland, development corporations, or no authority recorded)")
    if ctx_unrecognised:
        print(f"  Consumption context: UNRECOGNISED council prefixes — add "
              f"to dcp/consumption_context.py: {sorted(ctx_unrecognised)}")
    # No silent gaps: every live claim match either rendered on a panel
    # or is named here. A shortfall means a matched site fell out of the
    # site rows — retired, or filtered upstream — and its claim would
    # otherwise vanish without a trace.
    _claims_live = sum(len(v) for v in claims_by_site.values())
    print(f"  Label audit: {n_demoted:,} rendered findings moved to the family "
          f"the audit says fits, each marked with where it was filed"
          if n_demoted else
          "  Label audit: no verdicts stored, so nothing moved")
    if args.no_readings:
        print("  Machine readings: none built — --no-readings was passed, so "
              "no site page carries one and no reading is counted below")
    else:
        print(f"  Machine readings: {n_readings_rendered} rendered "
              f"({n_paragraphs_withheld} paragraphs withheld within them), "
              f"{n_readings_withheld} withheld with a reason, "
              f"{n_sites - n_readings_rendered - n_readings_withheld} sites with none")
    print(f"  Capacity claims: {n_claims_total} claims held, {_claims_live} "
          f"matched to sites, rendered on {claims_sites_rendered} site "
          f"panels ({claims_rows_rendered} claim rows)")
    if claims_rows_rendered != _claims_live:
        _missing = sorted(set(claims_by_site) -
                          {r[0] for r in site_rows})
        print(f"  Capacity claims: NOT RENDERED — matched sites absent "
              f"from the site rows: {_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
