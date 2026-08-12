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
FINDINGS_PER_SITE = 14


def _handover():
    spec = importlib.util.spec_from_file_location(
        "export_handover", Path(__file__).parent / "export_handover.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
:root{--bg:#fff;--fg:#16171b;--mut:#63666e;--line:#e4e5e9;--soft:#f7f8fa;
  --accent:#0b5fff;--warn:#8a5a00;--warnbg:#fff8e6;--ok:#0a6b3d;--okbg:#edfaf3}
@media (prefers-color-scheme:dark){:root{--bg:#131419;--fg:#e9eaee;--mut:#989aa4;
  --line:#282a33;--soft:#1a1c22;--accent:#7ea6ff;--warn:#ffcf70;--warnbg:#2a2410;
  --ok:#7fe0ac;--okbg:#102319}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--fg)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{padding:16px 22px 12px}
h1{margin:0 0 3px;font-size:19px}
.sub{color:var(--mut);font-size:12.5px}
nav.top{display:flex;gap:2px;padding:0 22px;border-bottom:1px solid var(--line);
  background:var(--bg);position:sticky;top:0;z-index:9;overflow-x:auto}
nav.top button{font:inherit;font-size:13.5px;padding:10px 15px;border:0;background:none;
  color:var(--mut);cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
nav.top button[aria-selected=true]{color:var(--fg);border-bottom-color:var(--accent);font-weight:600}
.view{display:none}.view.on{display:block}
.wrap{max-width:920px;padding:24px 22px 10px}
.lede{font-size:15.5px;line-height:1.62}
.parts{display:grid;gap:11px;margin:20px 0}
.part{border:1px solid var(--line);border-radius:7px;padding:13px 15px;background:var(--soft)}
.part h3{margin:0 0 3px;font-size:14.5px}
.part .what{color:var(--mut);font-size:13px;margin:0 0 6px}
.part .when{font-size:12.5px;margin:0}
.pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:9px;
  background:rgba(127,127,127,.15);color:var(--mut);margin-left:6px;vertical-align:1px}
.stat{display:flex;gap:24px;flex-wrap:wrap;margin:16px 0 4px;padding:13px 15px;
  border:1px solid var(--line);border-radius:7px}
/* Selectors reach the children of any tile, not just the div ones. The
   three clickable tiles are buttons, so a `.stat div span` rule skipped
   them entirely: they inherited the button's 14px and lost the block
   display, rendering as a tiny run-together "455sites" beside the
   full-size figures. */
.stat span{display:block;font-size:21px;font-weight:650;font-variant-numeric:tabular-nums}
.stat small{display:block;color:var(--mut);font-size:12px}
.banner{margin:16px 0;padding:12px 14px;border-left:3px solid var(--warn);
  background:var(--warnbg);color:var(--warn);border-radius:0 5px 5px 0;font-size:13px}
h2.sec{font-size:15px;margin:24px 0 8px}
.controls{display:flex;gap:9px;flex-wrap:wrap;padding:11px 22px;align-items:center;
  border-bottom:1px solid var(--line);position:sticky;top:var(--nav-h,41px);
  background:var(--bg);z-index:8}
input,select{font:inherit;padding:6px 9px;border:1px solid var(--line);border-radius:5px;
  background:var(--bg);color:var(--fg)}
input[type=search]{min-width:250px}
.count{color:var(--mut);font-size:12.5px;margin-left:auto}
button.toggle{font:inherit;font-size:13px;padding:6px 12px;border:1px solid var(--line);
  border-radius:5px;background:var(--bg);color:var(--fg);cursor:pointer}
button.toggle:hover{border-color:var(--accent)}
button.toggle[aria-pressed=true]{background:var(--accent);border-color:var(--accent);
  color:#fff;font-weight:600}
label.chk{font-size:12.5px;display:flex;align-items:center;gap:5px;cursor:pointer}
label.chk.off{opacity:.45;cursor:default}
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
table{border-collapse:separate;border-spacing:0;width:100%;min-width:1180px;
  font-size:13px}
#tbl-sites th:nth-child(1),#tbl-sites td:nth-child(1){min-width:210px}
#tbl-sites th:nth-child(2),#tbl-sites td:nth-child(2){min-width:260px}
#tbl-sites th:nth-child(3),#tbl-sites td:nth-child(3){width:104px}
#tbl-sites th:nth-child(4),#tbl-sites td:nth-child(4){width:150px}
#tbl-sites th:nth-child(5),#tbl-sites td:nth-child(5){min-width:250px}
#tbl-sites th:nth-child(6),#tbl-sites td:nth-child(6){width:112px}
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
th:after{content:" ↕";color:var(--mut);font-size:10px;opacity:.55}
tr.site{cursor:pointer}
tr.site:hover{background:rgba(127,127,127,.06)}
/* An open row and its panel share a background and a left edge, so it is
   obvious which row the panel below belongs to. */
tr.site.open>td{background:var(--soft);box-shadow:inset 0 1px 0 var(--accent)}
tr.site.open>td:first-child{box-shadow:inset 3px 1px 0 -1px var(--accent),
  inset 0 1px 0 var(--accent)}
tr.detail.on>td{box-shadow:inset 3px 0 0 -1px var(--accent)}
tr.site td:first-child:before{content:"▸";color:var(--mut);margin-right:7px;
  display:inline-block;transition:transform .12s}
tr.site.open td:first-child:before{transform:rotate(90deg)}
tr.detail{display:none;background:var(--soft)}
tr.detail.on{display:table-row}
tr.detail td{padding:14px 18px 18px 30px}
.mw{font-variant-numeric:tabular-nums;font-weight:650;white-space:nowrap}
/* The qualifier under a figure wraps; only the figure itself must not.
   Inheriting nowrap from .mw made "Disclosed total site demand · may
   rise" set the width of the whole column. */
.mw .q{white-space:normal}
.prov{color:var(--warn);font-weight:400}
.q{display:block;color:var(--mut);font-size:11.5px;font-weight:400;line-height:1.35}
/* Status labels wrap. They are occasionally a full sentence — "No figure
   found so far — 56 of 69 documents analysed" — and holding those on one
   line gave the column more width than any other, on rows that are
   several lines deep anyway. */
.tag{display:inline-block;padding:2px 7px;border-radius:9px;font-size:11px;
  white-space:normal;line-height:1.35}
.tag.known{background:var(--okbg);color:var(--ok)}
.tag.unknown{background:var(--warnbg);color:var(--warn)}
/* The panel is a four-column grid: the proposal down the left across two
   rows, the identity fields as one wide block above, and the three
   subject boxes beneath it. Before this everything lived in the first
   column and three columns of whitespace sat beside it. */
.grid{display:grid;grid-template-columns:minmax(250px,1.15fr) repeat(3,1fr);
  gap:12px;align-items:start}
.box{border:1px solid var(--line);border-radius:8px;padding:11px 13px;min-width:0}
.box.proposal{grid-column:1;grid-row:1 / span 2}
.box.identity{grid-column:2 / -1;grid-row:1}
@media (max-width:1100px){
  .grid{grid-template-columns:1fr 1fr}
  .box.proposal{grid-column:1 / -1;grid-row:auto}
  .box.identity{grid-column:1 / -1;grid-row:auto}
}
@media (max-width:700px){
  .grid{grid-template-columns:1fr}
  .box.proposal,.box.identity{grid-column:1}
}
/* Four columns on one row. Site key and classification are always a few
   characters, so they share a column stacked rather than each taking a
   whole one — which is what pushed the source documents onto a second
   row of their own. */
.fields{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px 18px}
.fields .stack{display:flex;flex-direction:column;gap:9px}
.fields .wide{grid-column:1 / -1}
@media (max-width:1100px){.fields{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.fields{grid-template-columns:1fr}}
.fields .lbl{display:block;color:var(--mut);font-size:11.5px;margin-bottom:1px}
.fields .val{display:block;font-size:12.5px;line-height:1.45}
.box h4{margin:0 0 7px;font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut)}
.box p{margin:0 0 8px}
.kv{display:grid;grid-template-columns:148px 1fr;gap:2px 12px;font-size:12.5px;margin:0}
.kv dt{color:var(--mut)}.kv dd{margin:0}
ul.find{margin:0;padding-left:16px;font-size:12.5px}
ul.find li{margin-bottom:3px}
ul.find .st{color:var(--mut)}
table.apps{font-size:12.5px;margin-top:4px}
table.apps th{position:static;font-size:11px;text-transform:uppercase;letter-spacing:.4px;
  color:var(--mut);cursor:default;z-index:auto}
table.apps th:after{content:""}
table.apps td{padding:5px 9px 5px 0}
h4.sub-head{margin:18px 0 4px;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.5px;color:var(--mut)}
details.apps-d{margin-top:16px;border-top:1px solid var(--line);padding-top:10px}
details.apps-d>summary{cursor:pointer;font-size:12.5px;color:var(--accent);
  list-style:none;display:inline-block;padding:3px 0}
details.apps-d>summary::-webkit-details-marker{display:none}
details.apps-d>summary:before{content:"▸ ";display:inline-block;
  transition:transform .12s;width:12px}
details.apps-d[open]>summary:before{transform:rotate(90deg)}
details.apps-d>summary:hover{text-decoration:underline}
.stat button{font:inherit;border:0;background:none;color:inherit;cursor:pointer;
  padding:0;text-align:left;border-radius:5px}
.stat button span{color:var(--accent)}
.stat button:hover span,.stat button:focus-visible span{text-decoration:underline}
.stat button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
table.stats{width:100%;margin:6px 0 18px;font-size:13px;min-width:0;
  border-collapse:separate;border-spacing:0}
table.stats th[scope=row]{position:static;font-weight:500;white-space:normal;
  border-bottom:1px solid var(--line);z-index:auto;cursor:default}
table.stats th:after{content:""}
table.stats tr.lead th[scope=row]{font-weight:650}
table.stats td.n{font-variant-numeric:tabular-nums;text-align:right;width:74px;
  white-space:nowrap}
table.stats td.help{width:52%}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px;
  margin:12px 0 6px}
figure.chart{margin:0}
figure.chart figcaption{font-size:12.5px;font-weight:650;margin-bottom:6px}
figure.chart svg{width:100%;height:auto}
figure.chart rect{fill:var(--accent);opacity:.78}
figure.chart rect:hover{opacity:1}
figure.chart rect.hl{opacity:.42}
figure.chart .ax{stroke:var(--line)}
figure.chart .xl,figure.chart .yl{fill:var(--mut);font-size:9.5px}
a.dlink{margin-left:5px;font-weight:400;color:var(--mut);text-decoration:none;
  font-size:11px;border:1px solid var(--line);border-radius:50%;padding:0 4px}
a.dlink:hover{color:var(--accent);border-color:var(--accent);text-decoration:none}
.entry{padding:9px 0;border-bottom:1px solid var(--line);scroll-margin-top:70px}
.entry h3{margin:0 0 3px;font-size:13.5px}
.entry p{margin:0;color:var(--mut);font-size:13px}
.entry.flash{background:var(--warnbg);border-radius:5px;padding-left:9px;padding-right:9px}
.wrap h3.m{font-size:14.5px;margin:20px 0 4px}
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
#mapside .count{margin:0;font-size:12.5px}
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
@media (prefers-color-scheme:dark){img.tl{filter:invert(1) hue-rotate(180deg) brightness(.86)}}
.pin{position:absolute;width:11px;height:11px;margin:-6px 0 0 -6px;border-radius:50%;
  border:1.5px solid #fff;padding:0;cursor:pointer;pointer-events:auto;
  box-shadow:0 0 0 1px rgba(0,0,0,.35)}
.pin.s{background:#d1341f}
.pin.e{background:#0b5fff}
.pin.sel{width:19px;height:19px;margin:-10px 0 0 -10px;border-width:3px;z-index:5}
#mapzoom{position:absolute;top:12px;right:12px;display:flex;flex-direction:column;gap:3px}
#mapzoom button{width:31px;height:31px;font-size:17px;border:1px solid var(--line);
  background:var(--bg);color:var(--fg);cursor:pointer;border-radius:5px}
#mapinfo{position:absolute;top:12px;left:12px;width:300px;background:var(--bg);
  border:1px solid var(--line);border-radius:7px;padding:11px 13px;font-size:13px;
  box-shadow:0 2px 14px rgba(0,0,0,.16);z-index:6}
#mapinfo .cardx{position:absolute;top:4px;right:6px;border:0;background:none;
  color:var(--mut);font-size:17px;line-height:1;cursor:pointer;padding:2px 4px}
#mapinfo .cardx:hover{color:var(--fg)}
#mapinfo .cardlinks{display:block;margin-top:7px;padding-top:7px;
  border-top:1px solid var(--line);font-size:12.5px}
#mapkey{font-size:12px;color:var(--mut);display:flex;flex-direction:column;gap:5px}
/* Explicit inline-block: on the map a .pin is a <button>, which is
   inline-block already, but in the key it is a <span> — inline, so width
   and height were ignored and the swatch collapsed to a sliver. */
#mapkey div{display:flex;align-items:center;gap:7px}
#mapkey .pin{position:static;pointer-events:none;display:inline-block;
  flex:0 0 11px;width:11px;height:11px;margin:0}
footer{padding:20px 22px 34px;color:var(--mut);font-size:12px;border-top:1px solid var(--line)}
.help{font-size:11.5px;color:var(--mut)}
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
  font-size:12px;line-height:1.45;color:var(--fg);box-shadow:0 2px 14px rgba(0,0,0,.16);
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
  border-radius:6px;background:var(--bg);font-size:12px;
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
    pins+='<button class="pin '+p.k+(p.sel?' sel':'')+'" style="left:'+dx+'px;top:'+dy
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
  document.getElementById('mapsubset').hidden=true;
  mapFilter();
}
function mapFilter(){
  const s=(document.getElementById('mq').value||'').toLowerCase().trim();
  const showE=document.getElementById('me').checked;
  const showS=document.getElementById('ms').checked;
  const big=document.getElementById('mbig').getAttribute('aria-pressed')==='true';
  for(const p of MAPPTS){
    let ok = p.k==='e' ? showE : showS;
    if(ok&&map.subset&&p.k==='s') ok = map.subset.has(p.id);
    if(ok&&s) ok=p.h.includes(s);
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
  // The map's own controls start from neutral, or a leftover 100 MW
  // toggle would filter the projection again and the count would lie.
  document.getElementById('me').checked=false;
  document.getElementById('ms').checked=true;
  document.getElementById('mq').value='';
  document.getElementById('mbig').setAttribute('aria-pressed','false');
  document.getElementById('munk').checked=false;
  document.getElementById('munk').disabled=true;
  document.getElementById('munklab').classList.add('off');
  MAPPTS.forEach(p=>{p.sel=false;});
  plotted.forEach(p=>{p.sel=true;});
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
function scrollRowToTop(r){
  const y = window.scrollY + r.getBoundingClientRect().top - stickyOffset() - 8;
  window.scrollTo({top: Math.max(0, y)});
}

function goSite(key){
  show('sites', true);
  document.getElementById('q').value='';
  document.getElementById('f').value='all';
  document.getElementById('o').value='';
  document.getElementById('big').setAttribute('aria-pressed','false');
  document.getElementById('unk').checked=false;
  document.getElementById('unk').disabled=true;
  document.getElementById('unklab').classList.add('off');
  apply();
  const r=document.querySelector('tr.site[data-key="'+CSS.escape(key)+'"]');
  if(r){
    if(!r.classList.contains('open')){
      r.classList.add('open'); r.nextElementSibling.classList.add('on');
    }
    soon(()=>scrollRowToTop(r));
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
function show(v, quiet){
  for(const k of ['start','sites','apps','energy','map','method','dict','notes']){
    const el=document.getElementById('view-'+k), tb=document.getElementById('tab-'+k);
    if(el) el.classList.toggle('on', k===v);
    if(tb) tb.setAttribute('aria-selected', k===v);
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
const TABS=['start','sites','apps','energy','map','method','dict'];
function fromHash(){
  const h=decodeURIComponent(location.hash.replace(/^#/,''));
  if(h.startsWith('dict-')){
    show('dict', true);
    const el=document.getElementById(h);
    if(el) soon(()=>el.scrollIntoView({block:'center'}));
  } else if(TABS.includes(h)){
    show(h, true);
  }
}
addEventListener('hashchange', fromHash);
document.querySelectorAll('tr.site').forEach(tr=>tr.addEventListener('click',e=>{
  if(e.target.closest('a'))return;
  tr.classList.toggle('open'); tr.nextElementSibling.classList.toggle('on');
}));
const rows=[...document.querySelectorAll('tr.site')];
const q=document.getElementById('q'),f=document.getElementById('f'),
      o=document.getElementById('o'),n=document.getElementById('n');
function apply(){
  const s=q.value.toLowerCase().trim(), mode=f.value, org=o.value; let shown=0;
  for(const r of rows){
    let ok=(!s||r.dataset.hay.includes(s));
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
apply(); sticky(); fromHash(); addEventListener('load', ()=>{sticky(); fromHash();});

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
    args = ap.parse_args()

    hv = _handover()
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
                                        ORDER BY pa.value_mw DESC) AS rn
              FROM power_adjudication pa
              JOIN applications a ON a.id = pa.application_id
              JOIN site_members m ON m.application_id = a.id AND m.retired_at IS NULL
              JOIN sites s ON s.id = m.site_id
              WHERE s.retired_at IS NULL AND pa.verdict = 'site_capacity'
                AND pa.value_mw IS NOT NULL) t
            WHERE rn = 1""")
        power_src = {(k, q): r for k, q, r in cur.fetchall()}

        # A figure adjudicated as somebody else's must not appear in this
        # list looking like the site's own. Ten of them did: the panel
        # ranks power findings to the top, and "22,700 MW" is a Savills
        # market forecast sitting in a Chiltern application. They are kept
        # rather than hidden -- a reader seeing what the documents contain
        # is the point -- but each is labelled with whose it is.
        cur.execute("""
            WITH adj AS (
              SELECT DISTINCT ON (finding_id) finding_id, verdict
              FROM power_adjudication
              ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC)
            SELECT site_key, signal_type, value_text, value_number, value_unit,
                   verdict FROM (
              SELECT s.site_key, f.signal_type, f.value_text, f.value_number,
                     f.value_unit, adj.verdict,
                     row_number() OVER (PARTITION BY s.site_key
                       ORDER BY (f.signal_family IN ('power_demand','power_generation',
                                 'power_grid','cooling','water','eia_process')) DESC,
                                length(coalesce(f.value_text,'')) DESC) AS rn
              FROM findings f
              JOIN site_members m ON m.application_id=f.application_id AND m.retired_at IS NULL
              JOIN sites s ON s.id=m.site_id
              LEFT JOIN adj ON adj.finding_id = f.id
              WHERE s.retired_at IS NULL AND f.value_text IS NOT NULL
                AND f.signal_family <> 'unclassified') t
            WHERE rn <= %s""", (FINDINGS_PER_SITE,))
        findings = defaultdict(list)
        for k, st, vt, vn, vu, verdict in cur.fetchall():
            findings[k].append((st, vt, vn, vu, verdict))

    with db.connect() as conn:
        profiles = site_profile.load_site_profiles(conn)
        coverage = site_profile.load_coverage(conn)
        # `held`/`read` are every document; `prose_*` are the ones the
        # deep-read is for. The caveats run off prose, the counts shown
        # to a reporter run off both, and they are different numbers on
        # purpose — see site_profile.load_coverage_detail.
        cov_detail = site_profile.load_coverage_detail(conn)

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
    map_points: list[dict] = []
    drive = hv._drive_folder_map()
    drive_apps = hv._drive_application_map()
    drive_csv = hv._drive_findings_map()
    n_apps_total = len(cover)
    n_docs = sum(c[0] for c in cover)
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

    for r in site_rows:
        (key, cls, name, lat, lon, csrc, councils, n_apps, refs, verdicts,
         docs, findings_n, it, tot, grid, gen, ncap, nexc, families,
         eref, edoc, manual, ptno, btitle, bstage, bvalue, bfloor,
         bsite, bplan, bdec) = r
        prof = profiles.get(key, {})
        held, read = coverage.get(key, (docs or 0, 0))
        _cd = cov_detail.get(key, {})
        p_held = _cd.get("prose_held", held)
        p_read = _cd.get("prose_read", read)
        apps = apps_by_site.get(key, [])
        est = scale.power_estimate(it_load_mw=it, total_site_mw=tot, grid_mw=grid,
                                   generation_mw=gen, floorspace_sqm=None,
                                   has_documents=bool(docs),
                                   prose_held=p_held, prose_read=p_read)
        cap_key, cap_label = site_profile.capacity_status(
            pre_application=(n_apps or 0) == 0, docs_held=p_held, docs_read=p_read,
            power_value_mw=est.value_mw, power_basis=est.basis)
        known = cap_key not in NOT_YET_KNOWN
        is_prov, prov_note = site_profile.provisional(p_held, p_read)
        if est.value_mw:
            site_mw_values.append(est.value_mw)
        addr = max((a[15] or "" for a in apps), key=len, default="") or \
            ", ".join(councils or [])
        _reg = next((a[12] for a in sorted(
            apps, key=lambda x: str(x[5] or ""), reverse=True)
            if a[12] and not str(a[12]).startswith("file://")), "")
        if lat is not None and lon is not None:
            map_points.append({
                "k": "s", "id": key, "lat": lat, "lon": lon,
                "mw": est.value_mw, "t": (name or key)[:80],
                "h": " ".join(x.lower() for x in
                              (name or key, ", ".join(councils or []), addr) if x),
                "pop": (
                    f'<b>{esc(name or key)}</b><br><span class="help">'
                    f'{esc(", ".join(councils or []))}</span><br>'
                    + (f'<b>{est.value_mw:,.0f} MW</b> '
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

        fl = []
        for st, vt, vn, vu, verdict in findings.get(key, []):
            num = f" <strong>{vn:g} {esc(vu or '')}</strong>" if vn is not None else ""
            # Adjudicated as describing something other than this site.
            not_ours = {
                "market_context": "market or sector context, not this site",
                "policy_target":  "a policy target, not this site",
                "comparator":     "a different named scheme, not this site",
            }.get(verdict)
            tag = (f" <span class='q' style='color:#b3261e'>[{esc(not_ours)}]</span>"
                   if not_ours else "")
            fl.append(f"<li><span class='st'>{esc(st)}</span>{num}{tag} — "
                      f"{esc(trim(vt,190))}</li>")
        if fl:
            findings_html = "<ul class='find'>" + "".join(fl) + "</ul>"
            if findings_n and findings_n > len(fl):
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
                findings_html += (f"<p class='help'>Showing {len(fl)} of {findings_n:,} "
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
        near_html = (f'{esc(near[0]["name"])} — {near[1]} km'
                     + (f', {esc(near[0]["cap"])}' if near[0]["cap"] else "")
                     + f' <a href="{esc(near[0]["url"])}" target="_blank" '
                       f'rel="noopener">PINS</a>') if near else "—"

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

        hay = " ".join(str(x or "").lower() for x in
                       (name, key, addr, ", ".join(councils or []), full_desc,
                        prof.get("applicants"), prof.get("advisers"),
                        prof.get("cooling_method"), btitle,
                        near[0]["name"] if near else "", " ".join(refs or [])))
        mw = "" if est.value_mw is None else f"{est.value_mw:,.0f}"
        mw_cell = (f"{mw}<span class='q'>{esc(est.basis)}"
                   + (" <span class='prov'>· may rise</span>" if is_prov and mw else "")
                   + "</span>") if mw else f"—<span class='q'>{esc(est.basis)}</span>"

        body.append(f"""<tr class="site" data-key="{esc(key)}" data-hay="{esc(hay)}"
 data-known="{1 if known else 0}"
 data-near="{esc(near[0]['name'] if near else '')}" data-mw="{est.value_mw or ''}"
 data-prov="{1 if is_prov else 0}" data-origin="{esc('|'.join(org))}">
<td data-v="{esc(name or key)}"><strong>{esc(trim(name or key, 58))}</strong>
 <span class="q">{esc(', '.join(councils or []))}</span></td>
<td data-v="{esc(trim(summary,80))}">{esc(trim(summary, 118)) or '—'}
 {'' if descriptive else '<span class="q">the register holds no description of the development itself, only procedural applications</span>'}</td>
<td class="mw" data-v="{est.value_mw or ''}">{mw_cell}</td>
<td data-v="{esc(cap_label)}"><span class="tag {'known' if known else 'unknown'}">{esc(cap_label)}</span></td>
<td data-v="{esc(addr)}">{esc(trim(addr, 105)) or '—'} {maplink}</td>
<td data-v="{read}">{read}/{held}<span class="q">documents read{
 f' · <a href="{esc(_durl)}" target="_blank" rel="noopener" '
 f'onclick="event.stopPropagation()">Drive</a>' if _durl and held else ''
}</span></td>
</tr>
<tr class="detail"><td colspan="6">
 {site_banner}
 <div class="grid">
  <div class="box proposal"><h4>Proposal</h4>
   <p><strong>{esc(summary) or '—'}</strong></p>
   <p class="help">Lifted verbatim from an application below, which the council published
    as:</p><p>{esc(trim(full_desc, 640)) or '—'}</p></div>

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
   </div></div>

  <div class="box"><h4>Power</h4>
   <dl class="kv">
    <dt>Best available</dt><dd>{('<strong>'+mw+' MW</strong>') if mw else '—'}
     {'<span class="prov"> ' + esc(site_profile.PROVISIONAL_MARK) + '</span>' if is_prov and mw else ''}</dd>
    <dt>Basis</dt><dd>{esc(est.basis)}</dd>
    <dt>Confidence</dt><dd>{esc(est.confidence or '—')}</dd>
    <dt>Caveat</dt><dd>{esc(est.caveat or '—')}</dd>
    <dt>IT load</dt><dd>{_q(it, 'it_load')}</dd>
    <dt>Total site</dt><dd>{_q(tot, 'total_site')}</dd>
    <dt>Grid connection</dt><dd>{_q(grid, 'grid_connection')}</dd>
    <dt>On-site generation</dt><dd>{_q(gen, 'onsite_generation')}</dd>
    {mixed_note}
    <dt>Excluded figures</dt><dd>{nexc or 0}
     <span class="help">market context, not this site</span></dd>
   </dl></div>

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

  <div class="box"><h4>Who is behind it</h4>
   <dl class="kv">
    <dt>Applicant / operator</dt><dd>{counted(prof.get('applicants'))}</dd>
    <dt>Advisers</dt><dd>{counted(prof.get('advisers'))}</dd>
    <dt>Planning authority</dt><dd>{counted(prof.get('authorities'))}</dd>
    <dt>Barbour project</dt><dd>{esc(btitle or '—')}
     {f'<span class="help">{esc(bstage or "")}</span>' if bstage else ''}</dd>
    <dt>Nearest energy project</dt><dd>{near_html}</dd>
   </dl>
   <p class="help">Names are counted: the organisation named forty times is the developer,
    the one named twice is usually a consultee's consultant.</p></div>
 </div>

 <h4 class="sub-head">What the documents say</h4>
 {findings_html}
 {f'''<details class="apps-d"><summary>Show the {len(apps)} planning application{'' if len(apps)==1 else 's'} for this site</summary>{apps_html}</details>''' if apps else apps_html}
</td></tr>""")

    # Barbour-recorded projects with no planning application yet. They are
    # the pipeline ahead of the planning system, so leaving them out would
    # make the dataset look like a record of what has already been applied
    # for. Almost everything about them is honestly blank; the row says why
    # rather than implying the site is small or quiet.
    existing = {r[0].upper() for r in site_rows}
    n_barbour = 0
    for (pref, title, pstage, dev_type, authority, address, description,
         plat, plon, pvalue, pfloor, psite, pplan, pdecision) in barbour_rows:
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
        if plat is not None and plon is not None:
            map_points.append({
                "k": "s", "id": key, "lat": plat, "lon": plon, "mw": None,
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
                       (title, key, address, authority, description, dev_type))
        near_html = (f'{esc(near[0]["name"])} — {near[1]} km'
                     f' <a href="{esc(near[0]["url"])}" target="_blank" '
                     f'rel="noopener">PINS</a>') if near else "—"
        body.append(f"""<tr class="site" data-key="{esc(key)}" data-hay="{esc(hay)}"
 data-known="0"
 data-near="{esc(near[0]['name'] if near else '')}" data-mw="" data-prov="0"
 data-origin="Barbour ABI">
<td data-v="{esc(title or key)}"><strong>{esc(trim(title or key, 58))}</strong>
 <span class="q">{esc(authority or '')}</span></td>
<td data-v="{esc(trim(summary,80))}">{esc(trim(summary, 118)) or '—'}</td>
<td class="mw" data-v="">—<span class="q">no application yet</span></td>
<td data-v="{esc(cap_label)}"><span class="tag unknown">{esc(cap_label)}</span></td>
<td data-v="{esc(address or '')}">{esc(trim(address, 105)) or '—'} {maplink}</td>
<td data-v="-1">—<span class="q">nothing published</span></td>
</tr>
<tr class="detail"><td colspan="6">
 <div class="banner" style="margin-top:0"><b>No application submitted yet.</b>
  {esc(site_profile.NO_DOCUMENT_REASONS['pre_application'])}</div>
 <div class="grid">
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
 </div></td></tr>""")

    n_sites = len(site_rows) + n_barbour
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
            "k": "e", "id": pr["ref"], "lat": pr["lat"], "lon": pr["lon"],
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

    origin_opts = sorted({o for v in origins.values() for o in v})
    n_prov = sum(1 for r in site_rows
                 if site_profile.provisional(
                     cov_detail.get(r[0], {}).get("prose_held", 0),
                     cov_detail.get(r[0], {}).get("prose_read", 0))[0])

    # ---- Methodology ------------------------------------------------------
    # Written here rather than shipped as a markdown file beside the data:
    # a companion document is the first thing to go stale, and every count
    # in this one is injected from the same query that built the page.
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
 </ul>
 <p class="m">Nothing was deleted in correcting these. The findings, their quotes and their
 original values are untouched; what was withdrawn is only the claim that a number is a
 site's power capacity. Two apparent contradictions were left standing deliberately, because
 the documents really do assert them: one site states 218&nbsp;MW of demand against a
 connection "designed to support a power transfer capacity of 120&nbsp;MW", and another
 reserved 57&nbsp;MW "anticipated to serve the needs of building 1" for a 155&nbsp;MW
 scheme.</p>

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
 <p class="m"><b>Sites that are grid-dependent by design.</b> Where standby generation is a
 small fraction of stated load, the plant is life-safety only and the site relies wholly on
 the grid. That is an operational fact with public-interest consequences, and it can be read
 straight off the capacity components in the site panel.</p>
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
<header><h1>UK datacentre plans v2, phase {args.phase} release</h1>
 <div class="sub">{n_sites} sites · {n_docs:,} documents ·
 generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC ·
 pipeline {esc(hv._git_commit())}</div></header>
<nav class="top">
 <button id="tab-start" aria-selected="true" onclick="show('start')">Start here</button>
 <button id="tab-sites" aria-selected="false" onclick="show('sites')">Sites<span class="pill">{n_sites}</span></button>
 <button id="tab-apps" aria-selected="false" onclick="show('apps')">Applications<span class="pill">{len(app_rows):,}</span></button>
 <button id="tab-energy" aria-selected="false" onclick="show('energy')">Energy projects<span class="pill">{len(nsip)}</span></button>
 <button id="tab-map" aria-selected="false" onclick="show('map')">Map</button>
 <button id="tab-method" aria-selected="false" onclick="show('method')">Methodology</button>
 <button id="tab-dict" aria-selected="false" onclick="show('dict')">Data dictionary</button>
 <button id="tab-notes" aria-selected="false" onclick="show('notes')">Assistant's notes</button>
</nav>

<section id="view-start" class="view on"><div class="wrap">
 <p class="lede">Every planning application we can find for a UK data centre or its
 supporting power infrastructure, the documents councils published with them, and what those
 documents say. Assembled from council planning registers, the Planning Inspectorate's
 national infrastructure register, and Barbour ABI project intelligence.</p>

 <div class="stat">
  <button onclick="show('sites')"><span>{n_sites}</span><small>sites</small></button>
  <button onclick="show('apps')"><span>{n_apps_total:,}</span><small>applications</small></button>
  <button onclick="show('energy')"><span>{len(nsip)}</span><small>energy projects</small></button>
  <div><span>{n_docs:,}</span><small>documents held</small></div>
  <div><span>{n_prose_read:,}</span><small>prose analysed ({pct_prose}%)</small></div>
 </div>

 <div class="banner"><b>Nearly all of the readable material has been read.</b>
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
 the next release.</div>

 <h2 class="sec">The shape of it</h2>
 <p class="help">Both charts read the dataset as it stands today. Neither depends on the
 deep read, so neither changes as the remaining documents are analysed — but both will move
 as the tail of applications is retrieved.</p>
 <div class="charts">{chart_years}{chart_bands}</div>

 <h2 class="sec">What the package contains</h2>
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
    pivotable, with a provenance sheet.</p>
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
<table id="tbl-sites"><thead><tr>
 <th>{dl("Sites","Site name","Site")}</th>
 <th>{dl("Sites","Proposal","Proposal")}</th>
 <th data-num="1">{dl("Sites","Power MW (best available)","Power MW")}</th>
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
   <button type="button" id="mbig" class="toggle" aria-pressed="false">100 MW or greater</button>
   <label class="chk off" id="munklab"><input type="checkbox" id="munk" disabled>
    Exclude unknown MW consumption</label>
  </div>
  <button type="button" id="mreset" class="toggle">Reset view and filters</button>
  <p class="count" id="mapcount"></p>
  <div id="mapkey">
   <div><span class="pin s"></span> data-centre site</div>
   <div><span class="pin e"></span> energy project</div>
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
    print(f"wrote {args.out} ({len(out)/1024/1024:.1f} MB) — {n_sites} sites, "
          f"{len(app_rows)} applications, {len(nsip)} energy projects, "
          f"{n_prov} sites marked provisional")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
