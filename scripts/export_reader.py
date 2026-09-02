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
import math
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
from dcp import snapshot_drive as _snapshot_drive  # noqa: E402
from dcp import spans  # noqa: E402
from dcp import db  # noqa: E402
from dcp import deepread_select  # noqa: E402

from dcp.drive import FOLDER_URL as DRIVE_ROOT  # noqa: E402
from dcp.drive import WORKBOOK_SHEET_URL  # noqa: E402
from dcp.drive import SITES_URL  # noqa: E402
from dcp.drive import NOTEBOOK_URL  # noqa: E402
from dcp.drive import PINPOINT_URL  # noqa: E402
from dcp.drive import ADJACENT_POWER_URL  # noqa: E402

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
              -- The document join carries each statement's own citation
              -- (issue #146): the register URL here, the Drive copy
              -- resolved at render time, the page from the finding.
              SELECT s.site_key, f.signal_type, f.value_text, f.value_number,
                     f.value_unit, adj.verdict, f.signal_family, f.id,
                     f.document_id, f.evidence_page, d.url AS doc_url,
                     row_number() OVER (PARTITION BY s.site_key, f.signal_family
                       ORDER BY coalesce(adj.verdict = 'site_capacity', false) DESC,
                                length(coalesce(f.value_text,'')) DESC,
                                f.id) AS rf
              FROM findings f
              JOIN site_members m ON m.application_id=f.application_id AND m.retired_at IS NULL
              JOIN sites s ON s.id=m.site_id
              LEFT JOIN adj ON adj.finding_id = f.id
              LEFT JOIN documents d ON d.id = f.document_id
              WHERE s.retired_at IS NULL AND f.value_text IS NOT NULL
                AND f.signal_family <> 'unclassified')
            SELECT site_key, signal_type, value_text, value_number, value_unit,
                   verdict, signal_family, id, document_id, evidence_page,
                   doc_url FROM (
              -- Round-robin across families: the first of every family
              -- before the second of any. Each round leads with figures
              -- adjudicated as this site's, then the power families, then
              -- cooling, water and EIA, then the rest. Ranking by text
              -- length alone put a landscape paragraph labelled it_load at
              -- the top of a site's evidence, four times over.
              SELECT f.site_key, f.signal_type, f.value_text, f.value_number,
                     f.value_unit, f.verdict, f.signal_family, f.id,
                     f.document_id, f.evidence_page, f.doc_url,
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


# §5's "Adjudicated power figures": the figure, and everything a reporter
# needs to check it — the extractor's own words for the quantity, the
# quote, the page, the model that read it, the date the document was
# fetched. The site page has been showing the value and an application
# reference, which names where to look but not what was found there.
#
# One row per (site, quantity): the largest figure adjudicated as this
# site's own, which is the figure the sites table and the estimate both
# take. `DISTINCT ON` picks it, so the provenance cannot describe a
# different finding from the one the number came from.
SITE_FIGURE_SQL = """
            WITH latest AS (
              SELECT DISTINCT ON (finding_id) *
              FROM power_adjudication
              ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC,
                       id DESC)
            SELECT DISTINCT ON (s.site_key, pa.quantity_type)
                   s.site_key, pa.quantity_type, pa.value_mw, pa.model,
                   f.signal_type, f.evidence_text, f.evidence_page,
                   d.url, d.kind, d.fetched_at, a.application_ref, d.id
            FROM latest pa
            JOIN findings f ON f.id = pa.finding_id
            JOIN applications a ON a.id = pa.application_id
            LEFT JOIN documents d ON d.id = pa.document_id
            JOIN site_members m ON m.application_id = a.id AND m.retired_at IS NULL
            JOIN sites s ON s.id = m.site_id
            WHERE s.retired_at IS NULL AND pa.verdict = 'site_capacity'
              AND pa.value_mw IS NOT NULL
            ORDER BY s.site_key, pa.quantity_type, pa.value_mw DESC, pa.id DESC"""

# Editorial rule 4: "highlights never replace data, and a row excluded
# from a headline is shown with its reason". The panel above shows the
# figure that won; this shows every figure the adjudicator saw for the
# site, including the ones it ruled out, with the verdict and the
# reasoning that ruled them out. Without it the page asserts that its
# four numbers are the only four numbers in the documents, which for
# some sites is untrue by two orders of magnitude.
#
# Capped per site, because one site carries 3,151 of these. What was
# cut is stated on the page and the full set is in the site's findings
# CSV — a silent truncation would read as completeness.
SITE_ALL_FIGURES_SQL = """
            WITH latest AS (
              SELECT DISTINCT ON (finding_id) *
              FROM power_adjudication
              ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC,
                       id DESC),
            joined AS (
              SELECT s.site_key, pa.verdict, pa.quantity_type, pa.value_mw,
                     pa.value_original, pa.unit_original, pa.reasoning,
                     pa.model, f.signal_type, f.evidence_page, d.url, d.kind,
                     d.id AS document_id,
                     a.application_ref, pa.id
              FROM latest pa
              JOIN findings f ON f.id = pa.finding_id
              JOIN applications a ON a.id = pa.application_id
              LEFT JOIN documents d ON d.id = pa.document_id
              JOIN site_members m ON m.application_id = a.id
                   AND m.retired_at IS NULL
              JOIN sites s ON s.id = m.site_id
              WHERE s.retired_at IS NULL)
            SELECT * FROM (
              SELECT j.*, count(*) OVER (PARTITION BY site_key) AS cnt,
                     row_number() OVER (PARTITION BY site_key
                       ORDER BY (verdict = 'site_capacity') DESC,
                                value_mw DESC NULLS LAST, id) AS rn
              FROM joined j) t
            WHERE rn <= %s ORDER BY site_key, rn"""

ALL_FIGURES_CAP = 60

# The adjudicator's five answers, in the words the handoff's table uses,
# with the tone each carries. Green is the only one that feeds a number
# on this page; the rest are why a figure in the documents is not the
# site's.
VERDICT_LABEL = {
    "site_capacity": ("this site", "v-yes"),
    "market_context": ("excluded \u2014 market context", "v-out"),
    "comparator": ("excluded \u2014 another scheme", "v-out"),
    "policy_target": ("excluded \u2014 policy target", "v-out"),
    "unclear": ("not settled", "v-maybe"),
}


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
             "ups": "UPS", "hv": "HV", "lv": "LV", "mw": "MW", "uk": "UK",
             "it": "IT", "pv": "PV", "kw": "kW", "mwh": "MWh", "kwh": "kWh",
             "bess": "BESS", "co2": "CO\u2082", "hvac": "HVAC",
             "mva": "MVA", "kva": "kVA", "mwe": "MWe", "dno": "DNO"}


def humanise(token: str, *, sentence: bool = False) -> str:
    """A snake_case key as a label, with initialisms left as initialisms.

    `sentence` capitalises only the first word, for keys quoted inside a
    sentence: the extractor's `it_load_mw` is "IT load MW" where it is
    being quoted as its own words, not "It Load MW", which capitalises
    a pronoun that is not there and title-cases prose that is not a
    title.
    """
    words = (token or "").replace("_", " ").split()
    out = [_ACRONYMS.get(w.lower(), w if sentence else w.capitalize())
           for w in words]
    if sentence and out and out[0] not in _ACRONYMS.values():
        out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


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


def _polar(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    """A point on a circle, degrees clockwise from twelve o'clock."""
    rad = math.radians(deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _count_in_words(n: int, unit: str = "site") -> str:
    """"Twenty-two sites", for the Signals headline.

    The handoff asks the headline to state the count in words and the
    property — words because a numeral in a headline reads as a
    measurement of something, and this number is a count of rows a rule
    selected. Above 999 it stays a numeral: "one thousand and forty-one
    sites" is not a sentence anybody wants to read.

    `unit` is the noun the count is of, pluralised here. Pass "" where
    the caller supplies its own: a cohort headline may name schemes
    rather than sites, and that word belongs in the registry's sentence
    rather than in this function's assumption.
    """
    if n < 0 or n > 999:
        return f"{n:,}" + (f" {unit}s" if unit else "")
    if n < 20:
        word = _ONES[n]
    elif n < 100:
        word = _TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else "")
    else:
        rest = n % 100
        word = _ONES[n // 100] + " hundred" + (
            f" and {_count_in_words(rest, '')}" if rest else "")
    if not unit:
        return word.capitalize()
    return f"{word.capitalize()} {unit}" + ("" if n == 1 else "s")


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


def counted(v, empty: str = "") -> str:
    """Escape a ranked label, subduing its bracketed mention counts.

    `empty` is what to say when there is nothing — a dash meant four
    different silences here too, and these three fields are exactly
    where the difference matters: a site with no documents has not
    declined to name a cooling method.
    """
    if not v:
        return empty or NOT_STATED
    return _MENTION_COUNT_RE.sub(r'<span class="mcount">(\1)</span>', esc(v))


# Two or three words, in the muted style, for a table cell — the site
# pages can afford a phrase, a dense table cannot and scanning is what
# a table is for. "The register does not publish this", not a judgement
# about the scheme.
NOT_STATED = '<span class="q">not stated</span>'

# A description is different from a missing value: the record exists and
# carries no prose, which is a fact about the register's own entry.
NO_DESCRIPTION = '<span class="q">no description given</span>'

# There is no value because the field does not apply — a confidence tier
# for a figure that does not exist, a caveat on nothing. Distinct from
# "not stated", which says a source was silent about something real.
NOT_APPLICABLE = '<span class="q">not applicable</span>'

# `sites.classification` records which source produced the record, and
# the column held the vocabulary `dcp/sites.py` uses to build it —
# "both", "ours_only", "barbour_covered". A reporter asked what
# "Classification: both" meant, which is the fair question: it is our
# word for our own bookkeeping, printed at a reader without a key.
# The label is the answer to "where did this site record come from",
# because that is what the field has always held.
# How an application entered the dataset, in a few words. The stored
# values are the sweep's own vocabulary and several carry a parameter —
# `spatial:Ealing/250949FUL`, `operator:Savills`, `energy_national:PTNO-…`
# — so the prefix is translated and the parameter dropped: a table cell
# has room for the route, not the seed.
#
# A reporter asked of Barrow/B14/2018/0568, which shows no documents and
# no register link, why it was in the dataset at all. The answer was
# recorded — `dc_keyword` — and simply never rendered.
DISCOVERY_ROUTES = {
    "dc_keyword": "found by keyword sweep",
    "spatial": "found near a known site",
    "operator": "found by operator-name sweep",
    "nsip_energy": "from the NSIP energy layer",
    "nsip_register": "from the NSIP register",
    "energy_national": "found near an energy project",
    "parent_backfill": "parent of an application we held",
    "cohort": "added with a cohort",
    "barbour": "from Barbour's project record",
    # (label, citation URL) where the origin is someone's published
    # work: the phrase alone credits, the link cites, and this project
    # does not show one without the other.
    "foxglove_top10": ("from the Foxglove list",
                       "https://www.foxglove.org.uk/wp-content/uploads/2025/10/"
                       "2025_09_26-FINAL-Big-Tech-Data-Centres-Report-"
                       "Website-Version.pdf"),
    "s35_direction": "a Section 35 direction",
    "seed_accretion": "seeded by hand",
    "duplicate_of": "duplicate of another record",
    "exclude": "excluded by hand",
}


def discovery(value: str) -> str:
    """The routes that found an application, deduplicated, in order.

    Returns HTML (labels escaped here): a route sourced from someone's
    published work carries a link to it — "from the Foxglove list" was
    a credit with no way to reach the list (Luke, 2026-08-28).
    """
    seen, out = set(), []
    for part in (value or "").split(", "):
        route = DISCOVERY_ROUTES.get(part.split(":")[0].strip())
        if not route or route in seen:
            continue
        seen.add(route)
        if isinstance(route, tuple):
            label, url = route
            out.append(f'<a href="{esc(url)}" target="_blank" '
                       f'rel="noopener">{esc(label)}</a>')
        else:
            out.append(esc(route))
    return " &middot; ".join(out)


SITE_ORIGIN = {
    "both": ("The planning sweep and Barbour",
             "found independently in both, and merged"),
    "ours_only": ("The planning sweep",
                  "one or more applications we triaged as a datacentre; "
                  "Barbour has no project here"),
    "unlocatable": ("The planning sweep, without coordinates",
                    "triaged as a datacentre, but no application in it "
                    "carries a map position, so it cannot be clustered "
                    "by proximity or drawn on the map"),
    "barbour_only": ("Barbour only",
                     "a Barbour project with no planning application "
                     "matched to it — the application may exist and not "
                     "have been found"),
    "barbour_covered": ("Barbour, with applications alongside",
                        "a Barbour project whose nearby applications were "
                        "not themselves triaged as datacentres"),
}


def why_empty(held: int = 0, read: int = 0) -> str:
    """Why a field is empty, in the muted style, in two or three words.

    A dash means "unknown" in this reader, and it was being used for at
    least four different things: we hold documents and none says this;
    we hold nothing so cannot know; we hold documents nobody has read
    yet; and we looked and there is genuinely none. Only the last is a
    finding, and a reader could not tell which they were looking at.

    The wording is derived from the site's own coverage rather than
    chosen, because the alternative — writing "none found" everywhere —
    asserts a null result on sites where nothing was ever read. That is
    the same error as a negative result reported without checking the
    probe could see it.

    Deliberately not exhaustive: where the code cannot tell which
    negative applies, "not established" says nothing about why, which is
    honest. Precedent is the operator column, which has read
    "not established" since 2.4.
    """
    if not held:
        return '<span class="q">no documents held</span>'
    if not read:
        return '<span class="q">documents not yet read</span>'
    return '<span class="q">not in the documents</span>'


def doc_link(url, label: str, drive_url: str = "") -> str:
    """A document's title, linked to our copy, and to the register too.

    Two links, because they answer two different questions and neither
    substitutes for the other.

    **Our copy is the title link.** Every document behind a site in this
    dataset is on Drive — 52,908 of them — and that copy is the one that
    keeps working. A council can withdraw a document from its register,
    renumber it, move the portal, or put it behind a session, and all
    four have happened during this investigation. 512 documents carry a
    `file://` URL besides: 503 into a checkout that exists on no machine
    and 9 written by the manual-ingest path. Rendered as anchors those
    became 401 links in the published 2.8 reader that resolve to a
    stranger's filesystem — dead for every reader, and worse than dead
    because they look live.

    **The register is a second, quieter link.** A figure that goes into
    published reporting has to be attributable to the public source, not
    to a Drive folder the reader cannot open, so the citable URL has to
    stay visible. It is the fallback for the title as well, for the
    handful of documents held but not staged.

    Where neither exists the title is plain text; the document is still
    reachable through the site's Drive folder, which the panel links.
    """
    u = str(url or "")
    fetchable = u.startswith("http://") or u.startswith("https://")
    if drive_url:
        out = (f'<a href="{esc(drive_url)}" target="_blank" rel="noopener">'
               f'{esc(label)}</a>')
        if fetchable:
            out += (f'<span class="q"> · <a href="{esc(u)}" target="_blank" '
                    f'rel="noopener">register</a></span>')
        return out
    if fetchable:
        return (f'<a href="{esc(u)}" target="_blank" rel="noopener">'
                f'{esc(label)}</a>')
    return esc(label)


_SNAPSHOT_LEDGER: dict | None = None


def our_copy(c: dict) -> str:
    """`<a>our copy</a>` for a claim, or "" — the claims channel's
    half of `doc_link`.

    Same pair as a document's, led by the other one. A document's title
    links our Drive copy and the register comes second, because councils
    withdraw documents. A claim's published page stays the primary link,
    because it is the thing a published story cites; our copy is the
    labelled second, because a marketing page has no register behind it
    and can be rewritten without notice — which is exactly what CyrusOne
    LON1 did between two readings.

    Empty rather than a guess wherever resolution fails. Most claims
    here are not operator claims at all — a NESO row, a filing — and
    their locator names a row or a page rather than a snapshot, so they
    resolve to nothing by construction. `load_site_claims` calls that
    column `source_locator` and the operator tab's loaders call it
    `locator`; both are the same column.

    The separator is the caller's, because the three surfaces punctuate
    differently: a run-on provenance line, a ` · `-joined list, and a
    table cell.
    """
    # The ledger once, not once per claim: it is parsed YAML and this is
    # called several hundred times a build, which measured at two
    # seconds of a twenty-seven-second build for nothing.
    global _SNAPSHOT_LEDGER
    if _SNAPSHOT_LEDGER is None:
        _SNAPSHOT_LEDGER = _snapshot_drive.load_ledger()
    url = _snapshot_drive.copy_url(
        c.get("source_locator") or c.get("locator"),
        c.get("as_at"), c.get("quote") or "", ledger=_SNAPSHOT_LEDGER)
    if not url:
        return ""
    return (f'<a class="oursnap" href="{esc(url)}" target="_blank" '
            f'rel="noopener">our copy</a>')


def trim(text, n: int) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def app_anchor(key: str, ref: str) -> str:
    """A fragment id for one application's row on its site page.

    Slashes are legal in a fragment and the site permalinks already use
    them; whitespace is not, and a handful of references carry it.
    """
    return "app-" + re.sub(r"\s+", "_", f"{key}-{ref}")


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
  /* A middle step for the reading bar. --warn had been carrying
     everything from 1% to 93%, so a site 90% read looked like one 5%
     read (a reader, 2026-08-26). Amber sits between them and is dark
     enough to pass AA on white as text, which it also has to be: the
     same class colours the word beside the bar. */
  --mid:#8a5a00;
  /* The design brief's slate, for machine-generated content. It earns a
     colour of its own under the same rule as the rest: what a model
     wrote is a different KIND of thing from what a document says, and
     that difference is exactly what a reader has to keep hold of. */
  --machine:#3f5570;--machinebg:#eef1f6;--machineline:#d6dde8;
  --side-w:380px;--side-gap:48px}

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
.opdetail details>summary:before,.opsite details>summary:before{
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
/* The families are loaded by a <link> in the head, not by an @import
   here. An @import is only honoured as the first rule of a stylesheet
   and this one sat several hundred rules down, so every browser dropped
   it: nothing on this page has ever rendered in Source Serif, Source
   Sans or IBM Plex Mono — it has all been Georgia and the system sans,
   which is why the masthead measured to the handoff and did not look
   like it. */
/* Page #f6f6f6, paper #fff — the token table's two greys, used the way
   it uses them. Everything was white on white, so the filter bar, the
   table and the page behind them were one undifferentiated surface and
   the 4px card rules had nothing to sit on. */
body{margin:0;font:16px/1.62 "Source Sans 3",-apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,sans-serif;background:var(--page);color:var(--fg)}
#tbl-sites,#tbl-apps,#tbl-energy,.controls,.chips{background:var(--bg)}
/* The serif carries what a reader is looking FOR — a site's name and a
   figure — and nothing else. The handoff uses it the same way. */
.sitecell .sname,.mw .fig,h1,h2{font-family:"Source Serif 4",Georgia,
  "Times New Roman",serif}
a{color:var(--brand);text-decoration:none;transition:color .13s}
a:hover{color:#234b8a;text-decoration:underline}
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
/* Pages that are mostly tables with prose between them. The container
   goes to the page's own width so the tables can use it, and the prose
   is held to the ordinary reading measure inside it — a wide table and
   a 1620px-long sentence are not the same request (Luke, 2026-08-28).
   Everything is left-aligned rather than centred so the prose and the
   tables share a left edge and the eye has one line to return to. */
.wrap.tables{max-width:1620px;padding:24px 32px 10px;margin:0 auto}
/* Column widths on the Operators page, set because auto layout spends
   the page badly here: it gave "Terms the figures are published under"
   799px of 1536 to hold "Total Capacity", and squeezed the five
   audience columns to 80px each so every one of their headings wrapped
   over three lines. The rule Luke set (2026-08-28): a prose column may
   wrap, a narrow data column should not. So the data columns get a
   width and `nowrap`, and whatever is left goes to the prose. */
#tbl-ops th:nth-child(1),#tbl-ops td:nth-child(1){width:190px}
#tbl-ops th:nth-child(n+2):nth-child(-n+8),
#tbl-ops td:nth-child(n+2):nth-child(-n+8){width:96px;white-space:nowrap}
#tbl-ops th:nth-child(9),#tbl-ops td:nth-child(9){width:auto}

#tbl-green th:nth-child(1),#tbl-green td:nth-child(1){width:130px}
#tbl-green th:nth-child(2),#tbl-green td:nth-child(2){width:auto}
#tbl-green th:nth-child(3),#tbl-green td:nth-child(3){width:160px}
#tbl-green th:nth-child(4),#tbl-green td:nth-child(4){width:210px}
#tbl-green th:nth-child(5),#tbl-green td:nth-child(5){width:190px}
#tbl-green th:nth-child(6),#tbl-green td:nth-child(6){width:120px}
#tbl-green th:nth-child(7),#tbl-green td:nth-child(7){width:160px}
/* A site key and a figure are single tokens: breaking them mid-string
   makes them unreadable and unsearchable. The prose columns beside
   them wrap as normal. */
/* "12" and "figures" are one phrase, not a figure with a caption under
   it. `.q` is display:block everywhere, which is right beneath a value
   that needs explaining and wrong for a unit word: it put every count
   in this table on two lines and doubled the height of every row
   (Luke, 2026-08-28). The same applies to "no figure", which is the
   whole cell. */
#tbl-ops td .q{display:inline;margin-left:4px}
#tbl-green .fuelist .f{white-space:nowrap}
#tbl-green td:nth-child(6),#tbl-green td:nth-child(7){white-space:nowrap}
#tbl-green td:nth-child(6) .q,#tbl-green td:nth-child(7) .q{white-space:normal}
.wrap.tables > p,.wrap.tables > h3,.wrap.tables > .banner,
.wrap.tables > .lede{max-width:920px}
.lede{font-family:"Source Serif 4",Georgia,serif;font-size:20px;line-height:1.45;
  max-width:46em}
.parts{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));
  gap:18px;margin:20px 0}
.part{background:var(--bg);border:1px solid var(--line-lt);
  border-top:4px solid var(--brand);border-radius:0;padding:18px 20px 20px}
.part .kind{margin:0 0 6px;font-size:13px;font-weight:600;text-transform:uppercase;
  letter-spacing:.6px;color:var(--mut)}
.part h3{margin:0 0 8px;font-family:"Source Serif 4",Georgia,serif;
  font-size:21px;font-weight:700;line-height:1.2}
.part .what{color:var(--body);font-size:14px;line-height:1.5;margin:0 0 10px}
.part .when{font-size:14px;line-height:1.5;color:var(--mut);margin:0}
.part .when b{color:var(--fg)}
.pill{display:inline-block;font-size:13px;padding:1px 8px;border-radius:9px;
  background:rgba(127,127,127,.15);color:var(--mut);margin-left:6px;vertical-align:1px}
/* The sidebar's width and the gap beside it, as tokens rather than as
   two numbers in two rules: the sections under the grid are held to the
   same measure as the column above them, and a change to one that did
   not reach the other would put prose at 1620px again. */
.startcol{max-width:calc(100% - var(--side-w) - var(--side-gap))}
@media (max-width:1100px){.startcol{max-width:none}}
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
h2.sec{font-size:23px;line-height:1.18;font-weight:700;margin:36px 0 10px}
h2.sec:first-child{margin-top:0}
.controls{display:flex;gap:14px;flex-wrap:wrap;padding:14px 20px;align-items:center;
  border-bottom:1px solid var(--line);position:sticky;top:var(--nav-h,41px);
  background:var(--bg);z-index:8}
input,select{font:inherit;font-size:15px;padding:9px 12px;border:1px solid #999;
  border-radius:4px;background:var(--bg);color:var(--fg)}
input[type=search]{width:300px;min-width:0}
select{width:auto}
.count{color:var(--mut);font-size:14px;margin-left:auto}
button.toggle{font:inherit;font-size:14px;padding:7px 14px;border:1px solid #999;
  border-radius:999px;background:var(--bg);color:var(--brand);cursor:pointer;
  transition:background .13s,border-color .13s,color .13s}
button.toggle:hover{border-color:var(--brand)}
button.toggle[aria-pressed=true]{background:var(--brand);border-color:var(--brand);
  color:#fff;font-weight:600}
label.chk{font-size:14px;display:flex;align-items:center;gap:5px;cursor:pointer}
label.chk.off{opacity:.45;cursor:default}
/* The handoff's chips: 13px, 6px 13px, radius 999px, active in the
   brand fill and inactive white with a #c7c7c7 border. They were square
   and the active one was the Guardian yellow, on a rule I made up — that
   yellow "marks what the PERSON has done to the page". The handoff
   reserves yellow for the active tab underline and nothing else, and
   says what an active chip looks like, so there was no gap to fill.
   The strip sits under the filter bar rather than inside it, because it
   is a long line that wraps and the filter bar is sticky. */
.chips{display:flex;gap:7px;flex-wrap:wrap;align-items:baseline;
  padding:9px 22px;border-bottom:1px solid var(--line)}
.chiplabel{font-size:14px;font-weight:600;color:var(--mut);
  margin-right:3px}
.chips .help{font-size:13.5px;flex-basis:100%;margin:3px 0 0}
button.chip.clearchip{border-style:dashed}
button.chip{font:inherit;font-size:13px;padding:6px 13px;
  border:1px solid #c7c7c7;border-radius:999px;background:var(--bg);
  color:var(--brand);cursor:pointer;line-height:1.3;
  transition:background .13s,border-color .13s,color .13s}
button.chip:hover{border-color:var(--brand)}
/* The reader's own filter, in the Guardian's yellow: it marks what the
   PERSON has done to the page, which is a third thing from structure
   (brand) and from the state of a figure (warn). Black text on it
   because the yellow is bright enough to carry it and nothing else on
   the page is that colour. */
button.chip.on{background:var(--brand);border-color:var(--brand);color:#fff;
  font-weight:600}
button.chip.on .n{color:rgba(255,255,255,.65)}
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
/* Floated rather than flexed. Making .sitenav a flex container turned
   the back link into a flex item and Playwright could no longer click
   it — the element resolved and the click timed out, which is a real
   reader's problem as much as a test's. A float right-aligns the
   sequence on the same line without touching how the link lays out. */
.siteseq{float:right;margin-left:14px;white-space:nowrap}
.sitenav::after{content:"";display:block;clear:both}
.seqbtn{font:inherit;font-size:14px;color:var(--link);background:none;
  border:0;padding:2px 4px;cursor:pointer;border-radius:3px}
.seqbtn:hover:not(:disabled){background:var(--chip)}
.seqbtn:disabled{color:var(--mut);cursor:default}
#siteseqn{font-size:13px;color:var(--mut)}
#sitehost .grid{margin-top:0}
/* Signals cards. Square, ruled, no shadow; the count is the one large
   thing on the card because it is the one thing that was computed. */
/* §3 of the design handoff. One card per signal: 4px news red rule,
   the main column and a 300px column carrying the count and what
   cannot enter the cohort. Red belongs to signals here; caution is the
   orange elsewhere, and the two are different jobs. */
.signals{display:block;margin-top:14px}
.sigexplain{max-width:62em}
.card.sigcard{border-top-color:#c70000;display:grid;
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
.sigchecks{font-size:14px;line-height:1.5;color:var(--body)}
.sigwithheld{margin:0;font-size:15px;font-weight:600;color:var(--warn)}
.siglist{margin:6px 0 0;padding-left:18px;font-size:14px;columns:2;column-gap:24px}
.siglist li{break-inside:avoid;margin-bottom:3px}
@media (max-width:700px){.siglist{columns:1}}
/* The badge in the table cell is the same control in a smaller frame:
   it filters, so it looks pressable, but it must not out-shout the site
   name beside it. */
/* The same object as the chips above the table — same type, same
   metrics, same shape — because it is the same control. Only the colour
   differs, and only because a chip up there also shows whether it is the
   filter that is on (Luke, 2026-08-25). */
button.who{font:inherit;font-size:13px;padding:6px 13px;text-align:center;
  border:1px solid #c7c7c7;border-radius:999px;background:var(--bg);
  color:var(--brand);cursor:pointer;line-height:1.3;max-width:100%}
button.who:hover{border-color:var(--accent)}
span.who.multi{font-size:13px;font-weight:600;display:block}
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
#tbl-sites{min-width:1080px}
/* Counted from the left, so inserting a column shifts every rule after
   it — which is what happened when Who's behind it went in at 2 and
   Proposal inherited a 104px allowance meant for the MW figure. The
   heading each rule is for is named, so the next insertion is a
   re-reading rather than a guess. */
/* The handoff's signal-view proportions — site 2fr, signals 1.7fr, then
   two fixed columns — redistributed for the two columns Luke added on
   2026-08-24: participants of its own, and signals narrower and stacked
   to make room for it. */
#tbl-sites th:nth-child(1),#tbl-sites td:nth-child(1){width:100%;min-width:420px}
                                                                        /* Site */
/* min-width, not width. Column 1 takes width:100% so that it absorbs
   whatever the others leave — and under auto layout that made `width` on
   the rest a suggestion the browser ignored, squeezing every one of them
   to its minimum content and breaking the headings onto three lines. */
#tbl-sites th:nth-child(2),#tbl-sites td:nth-child(2){min-width:180px}   /* Who's behind it */
#tbl-sites th:nth-child(3),#tbl-sites td:nth-child(3){min-width:200px}   /* Signals */
#tbl-sites th:nth-child(4),#tbl-sites td:nth-child(4){min-width:172px}   /* Power on record */

/* The site cell answers "what is this" on its own: the name, then where
   it is and what it is called in this dataset, then what the applicant
   said they were building. It was three columns — name, councils, and a
   Proposal column of its own — which put the answer to one question in
   three places and made the table read as a spreadsheet rather than a
   list of sites (Luke, 2026-08-24, against the design proposal). */
.sitecell .sname{display:block;font-weight:700;font-size:18px;line-height:1.25;
  color:var(--accent)}
.sitecell .skey{display:block;color:var(--mut);font-size:13px;margin:2px 0 4px}
/* No measure on the proposal. It had one — 60ch, then 66ch — which held
   it to about half the width of a column that is now 759px, so the cell
   wrapped early into whitespace (Luke, 2026-08-25). The column is the
   measure. */
.sitecell .sprop{display:block;font-size:14px;line-height:1.4}
/* Signals stacked, not wrapped across the row: at one per line the eye
   reads a list, and the column stays narrow enough to leave the site
   cell its width (Luke, 2026-08-24). The tone is the handoff's, carried
   on the cohort in dcp/site_cohorts.py — red where a figure is absent or
   contradicted, amber where one exists but is incomplete. They were one
   neutral grey on a rule I wrote here, that colour on this page means
   the state of a figure; the handoff assigns these tones itself and a
   signal IS a statement about the state of a figure. */
/* Centred in the column, and centred inside the pill where the label
   wraps to two lines (Luke, 2026-08-25). Scoped to the table cell: on
   the site page the same pills sit in a flex row at the top of the
   header card, where an auto margin would push them apart instead of
   centring them. */
.sigcell{white-space:normal;text-align:center}
.sigcell .sigpill{margin-left:auto;margin-right:auto;text-align:center}
.sigpill{display:block;width:fit-content;max-width:100%;margin:0 0 5px;
  padding:6px 13px;border:1px solid;border-radius:999px;
  font-size:13px;line-height:1.3}
.sigpill.t-red{background:#fdecec;color:#a51818;border-color:#f3c9c9}
.sigpill.t-amber{background:#fdf0e6;color:#a13a00;border-color:#f2d6bd}
.sigpill.t-slate{background:#eef1f6;color:#3f5570;border-color:#d6dde8}
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
.rbar-fill.r-most{background:var(--mid)}
.rbar-fill.r-part{background:var(--warn)}
.rbar-fill.r-none{background:var(--line)}
.rstate.r-done{color:var(--ok)}
.rstate.r-most{color:var(--mid)}
.rstate.r-part{color:var(--warn)}
.rstate.r-none{color:var(--mut)}
.mw{font-variant-numeric:tabular-nums;line-height:1.15;white-space:nowrap}
.mw .fig{font-size:21px;line-height:1.15}
.mw .w-stated{font-weight:700}                       /* disclosed by the applicant */
.mw .w-implied{font-weight:500;color:var(--mut)}     /* a connection, or standby-implied */
.mw .w-modelled{font-weight:400;color:var(--mut)}    /* arithmetic on floorspace */
.mw .w-operator{font-weight:600;font-style:italic}   /* the operator's own campus figure */
.mw .w-none{font-weight:400;color:var(--mut)}
#tbl-sites th:nth-child(5),#tbl-sites td:nth-child(5){min-width:152px}
                                                        /* External power indicators */
/* Narrowed with the header two lines deep: "Reading, and its floor" no
   longer has to fit on one. */
#tbl-sites th:nth-child(6),#tbl-sites td:nth-child(6){min-width:158px}  /* Reading */
/* Narrowed to make room for the indicators column: of the "top level"
   cells this one has the most spare width, an address rarely needing
   its full former allowance. */
.tablenote{margin:14px 20px 0;font-size:13px;color:var(--mut);
  line-height:1.5;max-width:70em}
/* A date is one word or it is nothing: 2024-04-15 broken across two lines
   reads as two half-dates. The width comes out of Proposal, which is the
   one column here that can lose a few pixels without cost. */
#tbl-apps th:nth-child(4),#tbl-apps td:nth-child(4){white-space:nowrap;width:98px}
tr.detail td{min-width:0}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
/* The sites list is the handoff's signal view, which is a grid of rows
   rather than a spreadsheet: 16px 20px of padding, a 1px #dcdcdc rule
   between rows, and a 12px uppercase header sitting on a 1px #121212
   rule. It is still a <table> because sorting is this reader's and the
   handoff never asked for it to go. */
#tbl-sites td{padding:16px 20px;border-bottom:1px solid var(--line)}
/* The headings wrap. "External power indicators" has to say "external"
   — beside Power MW, "Power indicators" reads as indicators about that
   figure, which is exactly what they are not (Luke, 2026-08-25) — and
   that costs a second line. All-caps has no descenders to clear, so the
   leading closes to 1.15 and the row grows by about twelve pixels. */
#tbl-sites th{padding:11px 20px;font-size:12px;font-weight:700;
  text-transform:uppercase;letter-spacing:.6px;color:var(--mut);
  border-bottom:1px solid var(--fg);vertical-align:bottom;
  white-space:normal;line-height:1.15}
/* Sticky on the <thead>, not on each <th>. On a 910-row table the
   per-cell version silently stopped pinning — the headings scrolled away
   and ended up sitting below the first rows of data — while the same rule
   worked on a short table. Sticking the row group is reliable at any
   length. */
#tbl-sites thead,#tbl-apps thead,#tbl-energy thead{position:sticky;
  top:var(--th-top,82px);z-index:7}
th{background:var(--bg);cursor:pointer;white-space:nowrap;font-weight:600;
  border-bottom:2px solid var(--line);vertical-align:bottom}
/* U+00A0, not a space: the sites-table headings wrap (white-space:normal
   below), and a breaking space here put the glyph on a line of its own
   under "Who's behind it" and "External power indicators" (ROADMAP,
   2026-08-27). The heading's ?-link already abuts its last word, so the
   non-breaking space chains word, link and glyph into one unbreakable
   tail. */
th:after{content:"\\00a0↕";color:var(--mut);font-size:12px;opacity:.55}
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
/* A citation nests the register link inside itself, and both carry
   .q — so the block rule broke one citation across three lines and
   stranded the leading comma of ", p.1" at the start of one. A .q
   inside a .q is part of a line, not a line. */
.q .q{display:inline}
/* A statement's citation runs on from the statement (issue #146); .q
   would stack it in a block of its own. */
.cite{color:var(--mut);font-size:13px;font-weight:400}
.cite a{color:var(--mut)}
/* Status labels wrap. They are occasionally a full sentence — "No figure
   found so far — 56 of 69 documents analysed" — and holding those on one
   line gave the column more width than any other, on rows that are
   several lines deep anyway. */
/* The handoff's pill sets — background, text and border — used for the
   three strengths an external claim can have. Slate is the token table's
   "this is a note about method": a tentative match is a lead to resolve,
   not a measurement, so it must not wear the same colour as one that
   was checked. */
.tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:13px;
  white-space:normal;line-height:1.35;border:1px solid}
.tag.known{background:#e9f3ec;color:#1d6b38;border-color:#c7e0d0}
.tag.unknown{background:#fdf0e6;color:#a13a00;border-color:#f2d6bd}
.tag.tentative{background:#eef1f6;color:#3f5570;border-color:#d6dde8}
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
.card.sitehead{border-top-color:var(--brand);padding:22px 26px 24px;margin-bottom:0}
.sitepills{margin:0 0 10px;display:flex;gap:6px;flex-wrap:wrap}
/* No max-width. The handoff's 28em measured a name inside a column;
   this card is the full width of the page, and "SAUNDERTON DATA CENTRE
   - 4 VIRTUS DATA CENTRES" was wrapping across two lines in the middle
   of a line of empty space (Luke, 2026-08-25). */
.sitename{margin:0 0 6px;font-family:"Source Serif 4",Georgia,serif;
  font-size:32px;line-height:1.15;font-weight:700}
.siteident{margin:0 0 12px;font-size:15px;color:var(--mut)}
/* Issue #159: a row that is not a datacentre says so, quietly. The
   treatment is a badge and a slightly receded name, never a hidden or
   struck-through row — these sites are in the corpus on purpose, and
   the adjacency layer is how the energy story gets told. */
#tbl-sites tr.site:not([data-class="datacentre"]) .sname{color:var(--mut)}
/* The fuel list in the renewable-claims table. `.q` is display:block
   everywhere else, which is right for a caption under a figure and
   wrong inside a list: it broke each count onto its own line and left
   the separating comma stranding at the head of the next fuel
   ("Diesel / (6 sites) / , Gas"). One fuel per line, count inline,
   no separators to strand (Luke, 2026-08-28). */
.fuelist .f{display:block}
.fuelist .f .q{display:inline;margin-left:5px}
.classbadge{display:inline-block;margin-right:8px;padding:1px 7px;
 border:1px solid var(--line);border-radius:10px;font-size:11px;
 font-weight:600;color:var(--mut);white-space:nowrap;
 /* The badge leads the title, in both the row and the site heading.
    The heading is serif at a much larger size, so the chip states its
    own family, size and line-height rather than inheriting them and
    growing with whatever it sits in. */
 font-family:"Source Sans 3",-apple-system,BlinkMacSystemFont,
 "Segoe UI",Roboto,sans-serif;
 line-height:1.7;vertical-align:middle;letter-spacing:.01em}
/* §5's adjudicated power figures. The measurements are the handoff's:
   a 132px value column, the value in Source Serif at 23px, the quote in
   serif italic behind a 3px rule. A figure and its evidence read as one
   object here rather than as a number in one place and a citation in
   another. */
.figures .figrow{display:grid;grid-template-columns:132px minmax(0,1fr);
  gap:18px;align-items:baseline;border-top:1px solid var(--line);
  padding:13px 0 12px}
.figval{font-family:"Source Serif 4",Georgia,serif;font-size:23px;
  font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
.figval .figunit{font-size:15px;font-weight:600}
.figq{font-size:13px;color:var(--mut);margin-top:3px;line-height:1.35}
.figtold{margin:0;font-size:14px;line-height:1.45;color:var(--ink)}
.figmeta{margin:4px 0 0;font-size:14px;line-height:1.45}
.adjlist{margin:6px 0 0;padding-left:18px;font-size:14px;line-height:1.45}
.adjlist li{margin:0 0 9px}
/* The figure's citation is one line: the document title, then two
   sibling .q spans — doc_link's "· register" and the page/ref/model/
   fetched meta. Block .q broke it over three rows. The `.q .q` rule
   cannot reach these: their parent is .figmeta, not another .q — the
   same disease PR #240 cured for nested citations, in sibling form. */
.figmeta .q{display:inline}
.figquote{font-family:"Source Serif 4",Georgia,serif;font-style:italic;
  font-size:15px;color:var(--ink);border-left:3px solid var(--line);
  padding-left:12px;margin:7px 0 0;line-height:1.45}
.figgate{margin:5px 0 0;font-size:13px;color:var(--mut)}
.figabsent{margin:13px 0 0;font-size:14px;color:var(--mut);line-height:1.5;
  border-top:1px solid var(--line);padding-top:12px}
.figsum{margin-top:14px}
/* Editorial rule 4. The working under the four figures above: every
   figure the adjudicator saw, the ruled-out ones included, each with
   the verdict and the reason it was ruled out. */
.allfigs{margin-top:14px}
.allfigs>summary{display:inline-block;font-size:14px;font-weight:600;
  color:var(--brand);background:#fff;border:1px solid var(--brand);
  border-radius:999px;padding:8px 16px;cursor:pointer;list-style:none;
  transition:background .13s,color .13s}
.allfigs>summary:hover{background:var(--brand);color:#fff}
.allfigs>summary::-webkit-details-marker{display:none}
.allfigs .scroll{overflow-x:auto;margin-top:14px}
table.afig{width:100%;border-collapse:collapse;font-size:13px;min-width:900px}
table.afig th{padding:8px 10px;font-size:11px;text-transform:uppercase;
  letter-spacing:.5px;color:var(--mut);font-weight:700;
  border-bottom:1px solid var(--ink);white-space:nowrap}
table.afig td{padding:8px 10px;border-bottom:1px solid var(--line);
  vertical-align:top;line-height:1.4}
table.afig td.n{font-weight:600;white-space:nowrap;
  font-variant-numeric:tabular-nums}
table.afig td .q{display:block;margin-top:3px}
/* The handoff's four pill sets, used here for the adjudicator's answer.
   Green is the only verdict that feeds a number on the page. */
.adjpill{display:inline-block;font-size:11.5px;font-weight:600;
  border-radius:999px;padding:1px 8px;white-space:nowrap;border:1px solid}
.adjpill.v-yes{background:#e9f3ec;color:#1d6b38;border-color:#c7e0d0}
.adjpill.v-out{background:#eef1f6;color:#3f5570;border-color:#d6dde8}
.adjpill.v-maybe{background:#fdf0e6;color:#a13a00;border-color:#f2d6bd}
.sitestate{margin:0 0 12px;display:flex;align-items:center;gap:14px;
  flex-wrap:wrap;font-size:14px;color:var(--mut)}
.sitestate .rbar{margin:0;flex:0 0 150px}
.statebit{display:inline-flex;align-items:center;gap:8px}
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
/* The applications table is wider than the page allows; it scrolls
   inside its band rather than spilling over the layout (issue #156). */
details.apps-d .appscroll{overflow-x:auto;min-width:0}
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
/* One quantity, one site, several figures: one row per figure, with the
   site, quantity and ratio spanning them. Widths on <col> rather than
   nth-child, because rowspan means the second row of a group starts at
   the figure and every positional selector would land a column out. */
/* Site names here run to 600px set on one line and the provenance to
   340px; a 23/auto split gave the provenance 686px of which half was
   empty and wrapped the site name to four lines, which then set the
   height of every row in its group. */
#tbl-lfl .c-site{width:38%}
#tbl-lfl .c-qty{width:14%}
#tbl-lfl .c-val{width:88px}
#tbl-lfl .c-aud{width:150px}
#tbl-lfl .c-ratio{width:74px}
#tbl-lfl td.src{color:var(--mut);font-size:13px;line-height:1.35}
/* The rule-off belongs at the end of a group, not between the figures
   inside one. */
#tbl-lfl tr.fig>td{border-bottom:0}
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
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));
  gap:20px 28px;margin:12px 0 6px;align-items:start}
/* A chart whose labels are names rather than bands needs the whole
   row: at half width the site names set at ~7px and the longest
   overran the viewBox (Luke, 2026-08-28). Full width also shortens
   the explainer beneath it, which buys the bars vertical room. */
.charts .chart-wide{grid-column:1/-1}
figure.chart{margin:0}
figure.chart figcaption{font-size:14px;font-weight:650;margin-bottom:6px}
figure.chart svg{width:100%;height:auto}
figure.chart rect{fill:var(--accent);opacity:.78}
figure.chart rect:hover{opacity:1}
figure.chart rect.hl{opacity:.42}
figure.chart .ax{stroke:var(--line)}
figure.chart .xl,figure.chart .yl{fill:var(--mut);font-size:12px}
/* A stack of three parts, and the pies, in one palette: brand for what an
   applicant stated, slate for what this project worked out, and the
   external tiers in the same green/amber/slate the row pills use, so a
   colour means the same thing in a chart as it does in the table. */
figure.chart rect.s-stated,figure.chart .s-stated{fill:var(--brand)}
figure.chart rect.s-est,figure.chart .s-est{fill:var(--machine)}
/* The two document-based-but-not-disclosed bases (issue #151): the
   provenance pie separates them from a stated load, in the same
   muted register the Power MW column gives their figures. */
figure.chart .s-grid{fill:#5b7d9c}
figure.chart .s-standby{fill:#9c8a5b}
/* A first-party campus figure: its own colour, because it is neither
   what an applicant stated to the authority nor this project's
   arithmetic, and the chart about provenance must not imply it is. */
figure.chart .s-operator{fill:#7a5b9c}
figure.chart .s-none{fill:#dcdcdc}
figure.chart .s-strong{fill:#1d6b38}
figure.chart .s-prob{fill:#c74600}
figure.chart .s-tent{fill:var(--machine)}
figure.chart path,figure.chart circle{opacity:.85}
figure.chart path:hover,figure.chart circle:hover{opacity:1}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;margin:0 0 8px;
  font-size:13px;color:var(--body);line-height:1.4}
.legend .key{display:flex;align-items:baseline;gap:6px}
.legend i{display:inline-block;width:10px;height:10px;flex:0 0 10px;
  position:relative;top:1px}
.legend .s-stated{background:var(--brand)}
.legend .s-est,.legend .s-tent{background:var(--machine)}
.legend .s-grid{background:#5b7d9c}
.legend .s-standby{background:#9c8a5b}
.legend .s-operator{background:#7a5b9c}
.legend .s-none{background:#dcdcdc}
.legend .s-strong{background:#1d6b38}
.legend .s-prob{background:#c74600}
.legend .q{display:inline;color:var(--mut)}
figure.pie .piebody{display:flex;gap:18px;align-items:center;flex-wrap:wrap}
figure.pie svg{width:140px;flex:0 0 140px}
figure.pie .legend{flex-direction:column;gap:5px;margin:0;min-width:180px}
a.dlink{margin-left:5px;font-weight:400;color:var(--mut);text-decoration:none;
  font-size:13px;border:1px solid var(--line);border-radius:50%;padding:0 4px}
a.dlink:hover{color:var(--accent);border-color:var(--accent);text-decoration:none}
/* Start here, from §2 of the design brief rather than from my own head:
   content and a 380px sidebar, 48px apart; cards are white with a 4px
   top rule in the colour of what they are about — brand for structure,
   caution orange for the pitfalls, ink for the package. */
.startgrid{display:grid;grid-template-columns:minmax(0,1fr) var(--side-w);
  gap:var(--side-gap);
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
.card .banner-d{margin:14px 0 0;font-size:13.5px;line-height:1.5}
.card .banner-d>summary{font-size:14px}
.card .banner-d .m{margin-top:9px}
/* §6's link, on a line of its own: it was the tail of the "Reach for it
   when" sentence, which buried the one thing on the card that goes
   somewhere (Luke, 2026-08-25). */
.part .golink{margin:10px 0 0;font-size:15px;font-weight:600}
/* A breakdown, not five more totals. The label is indented behind a rule
   that runs down the group, so the sum and its parts are distinguishable
   without reading the numbers. */
tr.breakdown>th{padding-left:26px;font-weight:400;position:relative}
tr.breakdown>th:before{content:"";position:absolute;left:12px;top:0;bottom:0;
  border-left:2px solid var(--line)}
tr.breakdown>td{color:var(--mut)}
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
/* Wider than it was, because the filter bar lives here on this tab and
   a cohort chip is a sentence. Still a quarter of a 1500px window, so
   the map keeps a portrait viewport — which is the shape of the UK, and
   the reason the controls are down the side at all. */
#mapside{flex:0 0 322px;overflow-y:auto;padding:14px 16px;display:flex;
  flex-direction:column;gap:13px;border-right:1px solid var(--line)}
/* The same bar, stood on its end. Not a second set of controls with the
   same names — the element itself is moved here by show(), so the state
   cannot fork. Everything that sat in a row sits in a column, and the
   two rules that made a horizontal bar work (the sticky offset and the
   count pushed right by an auto margin) are undone. */
/* display:contents above the table, so the bar is a wrapper for moving
   the controls about and not a box they live inside. `.controls` is
   position:sticky, and a sticky element sticks within its PARENT's box —
   so once the bar became that parent the filter bar scrolled away at
   177px and left the table's header row pinned on its own with a gap
   above it (Luke, 2026-08-25). Down the side of the map it is a real
   box again, because there it is the thing being laid out. */
#filterbar{display:contents}
#filterbar.down-the-side{display:block;position:static;margin:0 -16px;
  border-bottom:1px solid var(--line)}
#filterbar.down-the-side .controls{position:static;flex-direction:column;
  align-items:stretch;gap:9px;padding:0 16px 12px}
#filterbar.down-the-side .controls input[type=search],
#filterbar.down-the-side .controls select{width:100%;min-width:0}
#filterbar.down-the-side .count{margin-left:0;order:-1;font-weight:600;
  color:var(--fg)}
#filterbar.down-the-side .chips{flex-direction:column;align-items:stretch;
  gap:6px;padding:12px 16px}
#filterbar.down-the-side .chips .chip{width:100%;text-align:center}
#filterbar.down-the-side .chips .help{flex-basis:auto;font-size:12.5px;
  margin-top:6px}
#filterbar.down-the-side .chk{font-size:13.5px}
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
#mapzoom button{width:31px;height:31px;font-size:21px;border:1px solid #999;
  background:var(--bg);color:var(--fg);cursor:pointer;border-radius:4px}
#mapinfo{position:absolute;top:12px;left:12px;width:300px;background:var(--bg);
  border:1px solid #999;border-radius:0;padding:11px 13px;font-size:14.5px;z-index:6}
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
  background:var(--bg);border:1px solid #999;border-radius:0;padding:8px 10px;
  font-size:13.5px;line-height:1.45;color:var(--fg);
  z-index:8;text-align:left;cursor:auto}
/* focus-within as well as focus: a tap on a touch device, where there
   is no hover at all, lands focus on the span or on something inside
   it depending on the engine. */
.tip:hover .tiptext,.tip:focus .tiptext,
.tip:focus-within .tiptext{display:block}
/* The map is showing a subset someone chose on another tab. Said out
   loud, with the way out attached, because a map silently showing 190 of
   429 sites is indistinguishable from a map that is simply wrong. */
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
  // What is on the map against what the filter left, and how many of
  // that the map cannot show. A map quietly holding fewer sites than the
  // table is indistinguishable from a map that is simply wrong.
  const wantS = VISIBLE_SITES ? VISIBLE_SITES.size
                              : MAPPTS.filter(p=>p.k==='s').length;
  const gotS = MAPPTS.filter(p=>p.k==='s'&&p.vis).length;
  const gotE = MAPPTS.filter(p=>p.k==='e'&&p.vis).length;
  const missing = wantS - gotS;
  const bits=[];
  if(document.getElementById('ms').checked){
    bits.push(gotS.toLocaleString()+' of '+wantS.toLocaleString()+' site'
              +(wantS===1?'':'s')+' on the map');
    if(missing>0) bits.push(missing.toLocaleString()+' with no recorded location');
  }
  if(gotE) bits.push(gotE.toLocaleString()+' energy project'+(gotE===1?'':'s'));
  document.getElementById('mapcount').textContent =
    bits.join(' \u00b7 ') || 'Nothing to show';
}
/* Which sites the filter bar leaves, decided once in apply(). A site is
   on the map because it is in the table, never because the map tested
   it again: the two used to hold the same rules twice and could report
   different totals for one filter. */
let VISIBLE_SITES=null;
function mapFilter(){
  const s=(document.getElementById('q').value||'').toLowerCase().trim();
  const showE=document.getElementById('me').checked;
  const showS=document.getElementById('ms').checked;
  for(const p of MAPPTS){
    let ok = p.k==='e' ? showE : showS;
    // An energy project is not a site: no filter in the bar describes
    // one, so the layer switch and the search are all that reach it.
    if(ok && p.k==='e' && s) ok = p.h.includes(s);
    if(ok && p.k==='s' && VISIBLE_SITES) ok = VISIBLE_SITES.has(p.id);
    p.vis=ok;
  }
  /* §8c: the chips colour the markers, and the chip row above is the
     only place a cohort is chosen — the map used to carry a select of
     its own that a handover wrote into. */
  map.cohort = cohort || '';
  const key=document.getElementById('mapcohortkey');
  key.hidden = !map.cohort;
  if(map.cohort){
    const c=document.querySelector('#cohortchips .chip[data-cohort="'+map.cohort+'"]');
    document.getElementById('mapcohortname').textContent =
      c ? c.textContent.replace(/\\s*\\([^)]*\\)\\s*$/,'').trim() : map.cohort;
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
  MAPPTS.forEach(p=>{p.sel=false;});
  const want=[];
  if(siteKey||energyRef){
    // Jumping to one site clears the filters, or the site would be
    // filtered out of the very view that was opened to show it.
    document.getElementById('me').checked=true;
    document.getElementById('ms').checked=true;
    setWho(''); setCohort('');
    document.getElementById('q').value='';
    document.getElementById('f').value='all';
    document.getElementById('o').value='';
    apply();
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
  ['me','ms'].forEach(id=>document.getElementById(id).addEventListener('change',mapFilter));
  document.getElementById('mzin').addEventListener('click',()=>zoomAround(map.z+1));
  document.getElementById('mzout').addEventListener('click',()=>zoomAround(map.z-1));
  // The view, not the filters: those are the bar above, shared with the
  // table, and a button down here that silently cleared them would be a
  // second place the two views can come apart.
  document.getElementById('mreset').addEventListener('click',()=>{
    map.fitted=false; map.userMoved=false;  // refit to the current window
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
  // Nothing to hand over: the map is already showing the filter, because
  // apply() told it. This frames the view around what is on it.
  show('map', true);
  const plotted=MAPPTS.filter(p=>p.k==='s'&&p.vis);
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

function goApp(id){
  // The Proposal box links to the application row its clause was lifted
  // from. That row sits inside a closed <details>, so the bare anchor
  // would scroll to nothing: open every enclosing disclosure first.
  const el=document.getElementById(id);
  if(!el) return true;   // fall back to the plain anchor jump
  for(let d=el.closest('details'); d; d=d.parentElement&&d.parentElement.closest('details')) d.open=true;
  el.scrollIntoView({block:'center'});
  return false;
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
  history.pushState(null,'','#site-'+encodeURIComponent(key));
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
  // The pinned strip is `.controls`, not the whole bar: the chips scroll
  // away under it and the table's header row pins directly beneath it.
  // Measuring the bar put the header 104px lower than the thing it is
  // supposed to sit against. Nothing to offset when the bar is standing
  // down the side of the map.
  const fb=document.getElementById('filterbar');
  const on=fb && !fb.hidden && !fb.classList.contains('down-the-side');
  const bar=on ? fb.querySelector('.controls') : null;
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
  // The filter bar belongs to the two views it filters, and is the same
  // bar in both — so a reader who filters the table and switches to the
  // map finds the controls where they left them, still set.
  //
  // On the map it runs down the side rather than across the top: the UK
  // is tall and narrow, so a portrait viewport fits it and a landscape
  // one wastes the width on sea (Luke, 2026-08-25). The element MOVES —
  // it is re-parented, not duplicated — so there is still one set of
  // controls, one set of ids and one state, whichever shape it is in.
  const fb=document.getElementById('filterbar');
  fb.hidden = !(v==='sites' || v==='map');
  const side=document.getElementById('mapside');
  if(v==='map'){
    if(fb.parentElement!==side) side.insertBefore(fb, side.firstChild);
    fb.classList.add('down-the-side');
    // Nothing to offer a reader already looking at it; the sidebar's
    // "Fit the map to these sites" frames the set from here.
    document.getElementById('seemap').hidden = true;
    document.querySelector('.controls .tip').hidden = true;
  }else{
    const home=document.getElementById('filterbar-home');
    if(fb.parentElement!==home.parentElement) home.after(fb);
    fb.classList.remove('down-the-side');
    document.getElementById('seemap').hidden = false;
    document.querySelector('.controls .tip').hidden = false;
  }
  window.scrollTo(0,0);
  sticky();
  // The map sizes itself from its container, which has no dimensions
  // while the tab is hidden — so it has to draw once it is on screen.
  if(v==='map' && typeof drawMap==='function' && map.el) soon(drawMap);
  // The tab lives in the URL so a refresh returns to where you were, the
  // back button steps between tabs, and a dictionary entry can be linked.
  if(!quiet && location.hash !== '#'+v) history.pushState(null,'','#'+v);
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
// pushState does not fire hashchange, so back and forward over the
// entries it writes arrive here instead.
addEventListener('popstate', ()=>{fromHash(); paintWhoBar();});
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
// The sites either side of this one, in the table as it is filtered
// and sorted right now. Nothing has to be remembered to do this: the
// filter hides rows with display:none rather than removing them, so the
// DOM still holds the reader's set in their order, and openSite already
// takes a row. This is the same reason Back returns to the right place.
function visibleSiteRows(){
  return Array.prototype.filter.call(
    document.querySelectorAll('tr.site'),
    r => r.style.display !== 'none');
}
function siteStep(delta){
  if(!openTr) return false;
  const rows=visibleSiteRows(), i=rows.indexOf(openTr);
  const next=rows[i+delta];
  if(next) openSite(next);
  return false;
}
// Where the reader is in their own set, and whether there is anywhere
// left to go. Called on open, because the set can only change while the
// table is on screen.
function paintSiteSeq(){
  const rows=visibleSiteRows(), i=rows.indexOf(openTr);
  const prev=document.getElementById('siteprev');
  const next=document.getElementById('sitenext');
  const num=document.getElementById('siteseqn');
  if(!prev||!next||!num) return;
  const known = i >= 0 && rows.length > 1;
  prev.disabled = !known || i === 0;
  next.disabled = !known || i === rows.length - 1;
  // A position is only meaningful inside a set the reader chose. One
  // site on its own is not a sequence, and saying "1 of 1" invites the
  // question of what the other one is.
  num.textContent = known ? (i + 1) + ' of ' + rows.length : '';
  document.querySelector('.siteseq').hidden = !known;
}
function openSite(tr){
  if(openKey) closeSite(false);
  const key=tr.dataset.key;
  const cell=tr.nextElementSibling.firstElementChild;
  const host=document.getElementById('sitehost');
  while(cell.firstChild) host.appendChild(cell.firstChild);
  openKey=key; openTr=tr; openCell=cell;
  tr.classList.add('open');
  show('site', true);
  siteHash(key);
  paintSiteSeq();
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
      o=document.getElementById('o'),n=document.getElementById('n'),
      sc=document.getElementById('sc');
function apply(){
  const s=q.value.toLowerCase().trim(), mode=f.value, org=o.value,
        kind=sc.value; let shown=0;
  // Rows that pass everything EXCEPT the cohort chip. The chips count
  // against this, so the number beside each one is what that chip would
  // leave from where the reader is standing — which is what the help
  // text under them has always claimed (Luke, 2026-08-25). Counting
  // against the whole corpus made the claim false the moment any other
  // filter was on.
  const base=[], visible=new Set();
  for(const r of rows){
    let ok=(!s||r.dataset.hay.includes(s));
    if(ok&&who)              ok=r.dataset.who.split('|').includes(who);
    if(ok&&mode==='known')   ok=r.dataset.known==='1';
    if(ok&&mode==='unknown') ok=r.dataset.known!=='1';
    if(ok&&mode==='energy')  ok=r.dataset.near!=='';
    if(ok&&mode==='power')   ok=r.dataset.mw!=='';
    if(ok&&mode==='prov')    ok=r.dataset.prov==='1';
    if(ok&&org)              ok=r.dataset.origin.indexOf(org)>=0;
    // Issue #159. The class filter selects; it never ejects. With no
    // kind chosen every row is present, adjacency and suspects
    // included, which is the corpus as collected.
    if(ok&&kind)             ok=r.dataset.class===kind;
    if(ok) base.push(r);
    if(ok&&cohort)           ok=('|'+r.dataset.cohorts+'|').indexOf('|'+cohort+'|')>=0;
    r.style.display=ok?'':'none';
    r.nextElementSibling.style.display=ok?'':'none';
    if(ok){shown++; visible.add(r.dataset.key);}
  }
  // The handoff's count-string honesty rule: a filtered count is never
  // shown against the total, because "31 of 456" reads as a claim about
  // the release rather than about the chip that is on.
  const inCohort = cohort
    ? rows.filter(r=>('|'+r.dataset.cohorts+'|').indexOf('|'+cohort+'|')>=0).length
    : rows.length;
  n.textContent = cohort
    ? shown.toLocaleString()+' of '+inCohort.toLocaleString()+' sites in this cohort'
    : shown.toLocaleString()+' of '+rows.length.toLocaleString()+' sites';
  paintChipCounts(base);
  // Nothing to project is not a map worth opening. And the label says
  // "all" only when it means it (Luke, 2026-08-25): the link opens what
  // is on screen, so while anything is filtered it is not all of them.
  const seemap=document.getElementById('seemap');
  seemap.disabled = shown===0;
  seemap.textContent = (shown===rows.length) ? 'See all on map' : 'See on map';
  // The map is the same set, drawn differently. It is told here rather
  // than deciding for itself, so the two views cannot disagree about
  // what is filtered.
  VISIBLE_SITES = visible;
  if(typeof mapFilter==='function' && map.el) mapFilter();
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
// The number beside each chip, recomputed against the rows that pass
// every other control. A chip that would leave nothing is disabled
// rather than left clickable: an empty table is a worse answer than a
// chip that says it has none here.
function paintChipCounts(base){
  document.querySelectorAll('#cohortchips .chip[data-cohort]').forEach(c=>{
    const k=c.dataset.cohort, span=c.querySelector('.n');
    if(!k||!span||c.dataset.withheld) return;
    const live=base.filter(r=>
      ('|'+r.dataset.cohorts+'|').indexOf('|'+k+'|')>=0).length;
    span.textContent='('+live.toLocaleString()+')';
    c.disabled = live===0 && cohort!==k;
  });
  document.getElementById('clearcohort').hidden = !cohort;
}
function paintChips(){
  document.querySelectorAll('#whochips .chip').forEach(c=>{
    const on = (c.dataset.who||'')===who;
    c.classList.toggle('on', on); c.setAttribute('aria-pressed', on);});
  document.querySelectorAll('button.who').forEach(b=>
    b.classList.toggle('on', b.dataset.who===who));
  document.querySelectorAll('#cohortchips .chip').forEach(c=>{
    const k=c.dataset.cohort;
    const on = k!==undefined && k!=='' && k===cohort;
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

[q,f,o,sc].forEach(el=>el.addEventListener('input',apply));
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
function goView(v,id){
  show(v, true);
  history.pushState(null,'','#'+id);
  const el=document.getElementById(id);
  if(el){el.scrollIntoView({block:'center'}); el.classList.add('flash');
         setTimeout(()=>el.classList.remove('flash'), 1600);}
}
function goDict(id){
  show('dict', true);
  // pushState, not replaceState: a jump from a column heading to its
  // definition is somewhere the reader went, and Back was leaving the
  // reader altogether because nothing here ever wrote a history entry
  // (Luke, 2026-08-25).
  history.pushState(null,'','#'+id);
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
    # And never a named fallback either: with no release folder to
    # derive from, both are required and the script says so, rather
    # than stamping "phase 1" and writing beside a two-year-old build.
    _rel = release.latest_release_dir()
    ap.add_argument("--out", type=Path,
                    default=(_rel / "reader.html") if _rel else None,
                    help="where to write the reader; defaults to the newest "
                         "release folder, and is required when there is none")
    ap.add_argument("--phase", default=None,
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
    args.phase = release.current_phase(args.phase, _rel)
    if args.out is None:
        ap.error(f"no release folder under {release.EXPORTS} to write "
                 f"into; pass --out")

    hv = _handover()
    from dcp import capacity_claims as ccl
    from dcp import consumption_context as cc
    from dcp import entities
    from dcp import external_aggregates as extagg
    from dcp import machine_reading as mreading
    from dcp import operator_disclosure as odis
    from dcp import organisations
    from dcp import site_cohorts
    from dcp import site_class as sclass
    from dcp import origin as origin_mod
    from dcp import proposal as prop
    from dcp import signals as sig
    from dcp import site_profile, site_scale as scale

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(hv.SITE_SQL); site_rows = cur.fetchall()
        # Curated display names (issue #169): where an alias exists it
        # becomes the working name everywhere downstream — the table,
        # the map, the search haystack, the nearest-site labels — and
        # the derived default survives in `derived_names` so the site's
        # own page can still show what the record is built from. An
        # alias naming a dead key fails the build here, before anything
        # renders under the misleading derived name again.
        from dcp import site_aliases as _sal
        _aliases = _sal.load_aliases()
        derived_names = {r[0]: r[2] for r in site_rows if r[0] in _aliases}
        site_rows = [(r[0], r[1], _aliases.get(r[0], r[2]), *r[3:])
                     for r in site_rows]
        cur.execute(hv.APP_SQL); app_rows = cur.fetchall()
        cur.execute(hv.BARBOUR_ONLY_SQL); barbour_rows = cur.fetchall()
        # A pre-planning row is a row a reporter reads, so it can carry
        # an alias like any other — three do, added the day the Segro
        # rows were looked at. Its key is not in `sites` (there is no
        # site record yet), so liveness is checked against the rendered
        # universe rather than the table: pseudo keys included, and the
        # check therefore has to wait until they are known.
        _preplanning_keys = {f"PTNO-{r[0]}" for r in barbour_rows}
        _sal.require_live(_aliases,
                          {r[0] for r in site_rows} | _preplanning_keys)
        # The operator's own pages for a site (issue #255), labelled by
        # the audience they address — corporate pages state the power
        # figure almost without fail, consultation pages almost never
        # do, so the kind travels with the link. Same liveness contract
        # as the aliases, for the same reason.
        from dcp import operator_pages as _opp
        _operator_pages = _opp.load_pages()
        _opp.require_live(_operator_pages,
                          {r[0] for r in site_rows} | _preplanning_keys)
        # The facility rosters (issue #247). Nothing renders from them
        # yet; the build validates their liveness anyway, because a
        # roster keyed to a dead site is curation silently lost — the
        # same contract as the aliases and the operator pages.
        from dcp import site_facilities as _sfac
        _facilities = _sfac.load_facilities()
        _sfac.require_live(_facilities,
                           {r[0] for r in site_rows} | _preplanning_keys)
        # And every held copy a roster cites must actually be held: a
        # roster naming a snapshot nobody has is a provenance claim with
        # nothing behind it.
        _sfac.require_held_snapshots(_facilities)
        # The campus-scope adjudications (issue #250). Only the reviewed
        # entries carrying a `power_cell` change a number, and each is a
        # decision that an operator's campus figure ranks a site above
        # the planning figure describing one of its facilities. Same
        # liveness contract; the claim check runs once the claims are
        # loaded, below.
        from dcp import campus_scope as _csc
        _scopes = _csc.load_scopes()
        _csc.require_live(_scopes,
                          {r[0] for r in site_rows} | _preplanning_keys)
        displacements = _csc.load_displacements()

        def _shown(key, name):
            """A site's name as it should read.

            `prop.title_case` exists to tame a derived name a register
            or Barbour shouts in capitals. A curated alias is not that:
            a person wrote it, initialisms and all, and title_case only
            rewrites tokens that arrive entirely in capitals — which is
            exactly what an initialism is. It rendered "SDC" as "Sdc"
            and "(ILI" as "(ili", the second because `capitalize`
            lowercases everything after a first character that cannot
            itself be uppercased (Luke, 2026-08-30). The alias was
            already exact in every link on the page, so one site was
            being named two ways in one document.
            """
            shown = name or key
            return shown if key in _aliases else prop.title_case(shown)
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

        # §5's figures, with the provenance the handoff asks for.
        cur.execute(SITE_FIGURE_SQL)
        fig_prov = {}
        for (k, qt, v, model, as_written, quote_text, page, url, kind,
             fetched, ref, doc_id) in cur.fetchall():
            fig_prov[(k, qt)] = {
                "mw": float(v), "model": model, "as_written": as_written,
                "quote": quote_text or "", "page": page, "url": url or "",
                "title": mreading.document_title(url, kind) if url else "",
                "fetched": fetched, "ref": ref, "document_id": doc_id}

        # Editorial rule 4's table.
        cur.execute(SITE_ALL_FIGURES_SQL, (ALL_FIGURES_CAP,))
        all_figs, all_figs_total = defaultdict(list), {}
        for (k, verdict, qt, v, v_orig, u_orig, reasoning, model, as_written,
             page, url, kind, doc_id, ref, _id, cnt, _rn) in cur.fetchall():
            all_figs_total[k] = cnt
            all_figs[k].append({
                "verdict": verdict, "quantity": qt, "mw": v,
                "value": v_orig, "unit": u_orig, "reason": reasoning or "",
                "model": model, "as_written": as_written, "page": page,
                "url": url or "", "document_id": doc_id,
                "title": mreading.document_title(url, kind) if url else "",
                "ref": ref})

        # External capacity claims: grid-register figures attached to
        # sites by hand-adjudicated inference (dcp/capacity_claims). They
        # render in their own box, never into the site's power estimate —
        # a contracted ceiling is not the quantity a planning application
        # states, and the divergence between the two is the finding.
        claims_by_site = ccl.load_site_claims(cur)
        n_claims_total = len(ccl.load_claim_rows(cur))
        # A displacement pins the claim's value, so a republished figure
        # stops the build rather than silently re-ranking a site: the
        # adjudication was made about the figure it names. Not an as_at
        # pin — five committed operator claims carry no as_at at all,
        # Vantage Cardiff's among them (measured 2026-09-01).
        _csc.require_claims_unmoved(displacements, claims_by_site)

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
                       coalesce(suggested_family, ''), coalesce(evidence_span, '')
                FROM finding_label_audit
                ORDER BY finding_id, inserted_at DESC, id DESC""")
            label_verdicts = {fid: (v, fam, span)
                              for fid, v, fam, span in cur.fetchall()
                              if v in ("does_not_fit", "not_a_finding")}
        # `not_a_finding` is the one verdict that takes a row off this
        # list rather than moving it, because there is nowhere to move it
        # to: the row is the extractor's own reasoning caught in a quote,
        # an empty form field, a job description. Nothing is deleted —
        # the finding is still in the database, the findings CSV and the
        # workbook, and the count of what was withheld is printed at the
        # end of the build. What changes is that a reporter reading a
        # site's evidence is not handed text that states nothing.
        # A verdict acts only if its citation still stands. The stored
        # `span_verified` is what the gate said when the row was written,
        # and the gate has changed since — it could not see a citation
        # written with an ellipsis, which is what all four unverified
        # flags turned out to be. So the check is made here, against the
        # finding's own text, by the same function that guarded storage.
        # A flag that cannot show its words in the text does not move a
        # reader's quote; it is counted instead.
        n_demoted = n_not_findings = n_unsupported = 0
        for (k, st, vt, vn, vu, verdict, fam, fid,
             doc_id, page, doc_url) in _raw_findings:
            filed_as = ""
            moved = label_verdicts.get(fid)
            if moved and not spans.verify_span(moved[2], vt or ""):
                n_unsupported += 1
                moved = None
            if moved and moved[0] == "not_a_finding":
                n_not_findings += 1
                continue
            if moved and moved[1] and moved[1] != fam:
                filed_as, fam = fam, moved[1]
                n_demoted += 1
            findings[k].append((st, vt, vn, vu, verdict, fam, filed_as,
                                doc_id, page, doc_url))
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
        # A quote copied from the structured facts cites its application
        # and no document, because the prompt asks for exactly that. The
        # figure it was copied from is a finding and carries the document
        # it was read from, so the link is recoverable without guessing;
        # ambiguous text is dropped inside `figure_sources`.
        fig_sources = mreading.figure_sources(conn)
        cited_docs.update(mreading.cited_documents_by_id(
            conn, {d for m in fig_sources.values() for d, _ in m.values()}))
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
        # Built here rather than beside the other Drive maps below,
        # which read the sync ledger alone: this one reads
        # `document_drive_files` and so needs the connection, which is
        # closed by then.
        drive_docs = hv._drive_document_map(conn)
        # A cited document with no recorded Drive id falls back to the
        # register, which is a link that can rot. That is a acceptable
        # outcome and a silent one, so it is counted out loud: the usual
        # cause is a sync that ran without `record_drive_ids.py` after
        # it, and the number says how much of the corpus is affected.
        with conn.cursor() as _dcur:
            _dcur.execute("""
                SELECT count(DISTINCT d.id)
                FROM documents d
                JOIN findings f ON f.document_id = d.id
                JOIN site_members m ON m.application_id = f.application_id
                     AND m.retired_at IS NULL
                JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
                WHERE NOT EXISTS (SELECT 1 FROM document_drive_files x
                                  WHERE x.document_id = d.id)""")
            n_no_drive = _dcur.fetchone()[0]
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
    # What kind of site each row is (issue #159). A class is a filter and
    # a row treatment, never an ejection: the adjacency layer and the
    # disguise-suspect class are the investigation's own design, and a
    # reader that hid them would hide the reason they were collected.
    with db.connect() as _cconn:
        site_classes = sclass.compute_all(_cconn)
    # The control's numbers must be the table's, not the corpus's: the
    # reader renders 25 pre-planning rows the database has no site for,
    # and they are 'no planning record' too. A control saying 19 that
    # produces 44 rows is the count-honesty rule broken in the one place
    # a reporter would check it.
    rendered_classes: dict[str, int] = defaultdict(int)
    cohorts_of_site: dict[str, list[str]] = defaultdict(list)
    cohort_title: dict[str, str] = {}
    cohort_tone: dict[str, str] = {}
    for _c in cohorts:
        cohort_title[_c.cohort.key] = _c.cohort.title
        cohort_tone[_c.cohort.key] = _c.cohort.tone
        for _m in _c.result.members:
            cohorts_of_site[_m.site_key].append(_c.cohort.key)

    apps_by_site = defaultdict(list)
    for r in app_rows:
        apps_by_site[r[0]].append(r)

    # Why an application with no documents has none. The acquisition
    # machinery records a verdict for every attempt — a blocked portal
    # and a council that publishes nothing look identical in a count of
    # zero and mean opposite things — and until now the record stayed in
    # the database while the reader showed a bare 0 (issue: the Hackney
    # register that dropped its own history read the same as a council
    # that never published). Keyed by reference; the latest outcome per
    # application, only for applications holding nothing.
    with db.connect() as _conn, _conn.cursor() as _cur:
        _cur.execute("""
            WITH latest AS (
              SELECT DISTINCT ON (application_id) application_id, outcome,
                     coalesce(detail, '') AS detail
              FROM acquisition_outcome
              ORDER BY application_id, checked_at DESC)
            SELECT a.application_ref, t.outcome, t.detail
            FROM latest t JOIN applications a ON a.id = t.application_id
            WHERE NOT EXISTS (SELECT 1 FROM documents d
                              WHERE d.application_id = a.id)""")
        empty_reasons = {ref: (outcome, detail)
                         for ref, outcome, detail in _cur.fetchall()}
        # Adjacent power (issue #252): substations, energy centres and
        # standby fleets consented in their own right relate to a site,
        # they do not belong to one, and since the clusterer stopped
        # admitting the verdict they are not members anywhere. The
        # relationship table carries the evidence; documentary rows
        # (discovery, cohort) render as entries, proximity rows only as
        # a count — one kilometre is the clustering radius, not a supply
        # relationship, and 71 distance-only rows rendered as peers of
        # 39 documentary ones would read as endorsement by volume
        # (Luke's call, 2026-08-30).
        _cur.execute("""
            SELECT s.site_key, sap.basis, sap.distance_m, sap.evidence,
                   a.application_ref, left(coalesce(a.description,''), 240),
                   a.url
            FROM site_adjacent_power sap
            JOIN sites s ON s.id = sap.site_id AND s.retired_at IS NULL
            JOIN applications a ON a.id = sap.application_id
            WHERE sap.retired_at IS NULL
            ORDER BY s.site_key, (sap.basis = 'proximity'),
                     sap.basis, sap.distance_m NULLS LAST""")
        adjacent_by_site: dict[str, dict] = {}
        for _sk, _basis, _dist, _evid, _ref, _desc, _aurl in _cur.fetchall():
            _e = adjacent_by_site.setdefault(_sk, {"doc": [], "prox": 0})
            if _basis == "proximity":
                _e["prox"] += 1
            else:
                _e["doc"].append((_basis, _dist, _evid, _ref, _desc, _aurl))
    _OUTCOME_PHRASE = {
        "none_published": "the register lists no documents",
        "error": "the last retrieval attempt failed and will be retried",
        "no_adapter": "this portal cannot be read automatically yet",
    }

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
    # One row per site: the figure, whether anybody stated it, and the
    # strongest external claim matched to the site. Three charts read it
    # and none of them recomputes the ladder, so they cannot disagree
    # with each other or with the table.
    capacity_shape: list[dict] = []
    power_basis_counts: dict[str, int] = {}
    map_points: list[dict] = []
    drive = hv._drive_folder_map()
    drive_apps = hv._drive_application_map()
    drive_csv = hv._drive_findings_map()
    drive_adj = hv._drive_adjacent_map()
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
        f"<tr class='breakdown'><th scope='row'>{esc(lbl)}</th>"
        f"<td class='n'>{by_outcome[k]:,}</td>"
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

    def _cite(q, site_key=None):
        """Where a quote is from: the document, linked to the register's
        copy, with its page; or the application whose adjudicated figure
        it is.

        A quote the model cited to an application alone is resolved back
        to the document of the adjudicated figure it was copied from,
        where exactly one figure on this site carries that text. The
        model's own citation is untouched in the stored reading; this is
        a lookup at render, not a rewrite of the record.
        """
        doc_id = q.get("document_id")
        if not doc_id and site_key:
            hit = fig_sources.get(site_key, {}).get(
                " ".join((q.get("quote") or "").split()))
            if hit:
                doc_id, q = hit[0], {**q, "page": hit[1]}
        if doc_id:
            d = cited_docs.get(int(doc_id))
            page = f', p.{q["page"]}' if q.get("page") else ""
            if d:
                return (f'{doc_link(d["url"], d["title"], drive_docs.get(int(doc_id), ""))}'
                        f'{page} · {esc(d["application_ref"])}')
            return f'document {doc_id}{page}'
        return f'application {esc(q.get("application_ref") or "")}, adjudicated figure'

    def reading_panel(key, docs_held=0):
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
            # A site with documents and no reading says why, instead of
            # silently lacking a panel its neighbours have (issue #145).
            # The reason is mechanical, not editorial \u2014 readings are
            # generated in batches from each site's own documents and
            # the batches have covered only some sites so far \u2014 and the
            # wording must not overpromise a schedule: at this build 19
            # of 524 sites carry one. Sites with no documents get no
            # note; their page already says no documents are held, and
            # there is nothing for a reading to read.
            if docs_held:
                return ('<div class="box reading withheld"><h4>A machine\u2019s '
                        'reading of this site\u2019s documents</h4>'
                        '<p class="help">None yet \u2014 not a judgement about '
                        'this site. Readings are generated in batches from '
                        'each site\u2019s own documents, and the batches run so '
                        'far have covered only some sites; this one has not '
                        'been read yet. Where a reading exists it renders '
                        'only if every figure in it carries a quote that '
                        'verified against the documents.</p></div>')
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
                    f'<span class="q">{_cite(q, key)}</span></li>'
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
        # The panel says where each name came from; this column has no
        # room and no category distinction, so the source is stripped
        # here. Leaving it on also broke the de-duplication below, which
        # compares an applicant against an end user by string.
        def _bare(v: str) -> str:
            return re.sub(r"\s*\((?:Barbour|documents)\)\s*$", "",
                          (v or "").strip())

        primary = _bare(prof.get("operator_primary"))
        end_user = _bare(prof.get("end_user"))
        applicant = _bare(prof.get("applicant_of_record"))
        # Where the applicant came from decides how to read it. Barbour
        # states a list of organisations; the documents state one party
        # and then its contact details — "Slough Holdings UK Limited,
        # 103 Mount Street, London, W1K 2TJ" — so only the first field
        # of a document-sourced applicant is a name, and splitting the
        # rest out would put a postcode on the row as an operator.
        from_documents = (prof.get("applicant_of_record") or "").strip(
            ).endswith("(documents)")
        applicant_first = applicant.split(",")[0].strip()
        # The column said "not established" whenever Barbour named no
        # operator — on 158 live sites whose own page named an applicant
        # of record read from the documents. The page knew more than the
        # column that indexes it, which is the Segro fault in reverse
        # (Luke, 2026-08-27). An applicant is a weaker claim than an
        # operator, so it is used only when nothing stronger exists and
        # the tooltip names its source.
        badge = group or primary or applicant_first
        if not badge:
            return {"filter_key": "", "sort": "zzz",
                    "cell": '<span class="q">not established</span>'}
        if group:
            source = "a confirmed alias group"
        elif primary:
            source = "Barbour's end user" if end_user else "Barbour's client"
        else:
            source = ("the site's documents" if from_documents
                      else "Barbour's client")
        # Every operator Barbour states for the site, so that a chip for
        # any of them finds the site. A site record that covers an estate
        # holds several — the Slough Trading Estate record carries
        # Equinix, VIRTUS, Zenium and Iron Mountain — and a row that wore
        # one of those names, and answered only that one chip, would be
        # the site-fragmentation hazard HISTORY records, as a badge.
        # One organisation, once. These were compared by string, so the
        # same company under two spellings — or under one spelling and
        # again as the badge — printed twice: "Frimley Health NHS… and
        # Frimley Health NHS…". The panel can afford to show a name in
        # two roles because it labels the roles; this column names no
        # category, so a repeat is only noise. Luke, 2026-08-26.
        # The key a badge filters on is the alias GROUP where one is
        # confirmed, and the raw name otherwise. Luke, 2026-08-25: "no
        # one will want to filter to different names of the same group —
        # they want to see the group." Clicking Vantage Data Centres
        # Limited therefore finds VDC LHR11 Limited's rows too, which
        # is the whole point of confirming a group.
        def _fkey(name: str) -> str:
            g = organisations.group_for(name, alias_index)
            return entities.canonical_key(g.group if g else name)

        # ...and every comparison below uses that same key, because a
        # confirmed group IS the organisation. Comparing raw names let a
        # group's own member stand beside it as a second party —
        # "Google and Global Infrastructure…", where Global
        # Infrastructure UK Limited is the Alphabet subsidiary the badge
        # already names. Six groups showed it (Luke, 2026-08-27): Google,
        # Vantage, Colt, Microsoft, Amazon. The 2026-08-26 fix above made
        # "one organisation, once" true of two spellings of one name;
        # this makes it true of a group and its member.
        operators, _seen = [badge], {_fkey(badge)}
        # Barbour's end user is a list, and so is a Barbour applicant; a
        # document-sourced applicant is one name followed by an address.
        shared = end_user or (applicant_first if from_documents else applicant)
        for n in shared.split(","):
            n = n.strip()
            k = _fkey(n)
            if n and k not in _seen:
                _seen.add(k)
                operators.append(n)
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
        _applicant_first = applicant.split(",")[0].strip()
        # `_seen` already holds the badge's group key and every operator
        # kept, so one test covers what two raw-name tests used to.
        if _applicant_first and _fkey(_applicant_first) not in _seen:
            via_bits.append(f"via {trim(_applicant_first, 34)}")
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
        _rung_claim, _rung_displaces = ccl.rung_inputs(
            key, claims_by_site.get(key, []), displacements)
        est = scale.power_estimate(it_load_mw=it, total_site_mw=tot, grid_mw=grid,
                                   generation_mw=gen,
                                   floorspace_sqm=site_floorspace.get(key),
                                   has_documents=bool(docs),
                                   prose_held=p_held, prose_read=p_read,
                                   operator_claim=_rung_claim,
                                   operator_displaces=_rung_displaces)
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
        _tiers = [c["confidence"] for c in claims_by_site.get(key, [])]
        capacity_shape.append({
            "mw": est.value_mw,
            "stated": bool(est.value_mw) and est.basis in scale.DISCLOSED_BASES,
            # Three provenances, not two. An operator's campus figure is
            # neither "from the site's documents" nor this project's
            # arithmetic on a floor area, and filing it under either
            # would be false on the chart whose whole subject is where a
            # figure comes from — the #151 failure in a third costume.
            "prov": ("operator" if est.basis == scale.OPERATOR_BASIS else
                     "stated" if est.basis in scale.DISCLOSED_BASES else
                     "estimated"),
            "claim": ("strong" if "strong" in _tiers else
                      "probable" if "probable" in _tiers else
                      "tentative" if "tentative" in _tiers else "")})
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
                    + (f' · <a href="{esc(drive[hv._folder_key(key)])}" target="_blank" '
                       f'rel="noopener">Drive</a>'
                       if held and hv._folder_key(key) in drive else '')
                    + (f' · <a href="{esc(_reg)}" target="_blank" rel="noopener">'
                       f'Register</a>' if _reg else '')
                    + '</span>')})
        maplink = (f'<a href="#map" onclick="showMap(\'{esc(key)}\');return false"'
                   f' title="Show this site on the map">map</a>') if lat and lon else ""
        gmaps = (f'<a href="https://www.google.com/maps/search/?api=1&query={lat},{lon}"'
                 f' target="_blank" rel="noopener">Google Maps</a>') if lat and lon else ""
        full_desc = max((a[16] or "" for a in apps), key=len, default="") or (btitle or "")
        summary, descriptive, src_i = prop.summarise(
            [a[16] for a in apps] or [btitle])
        summary = prop.tidy(summary)
        # Issue #256: the Proposal box names its source. The summary is
        # verbatim from exactly one application, so the phrase links to
        # that application's row, carries its reference and received
        # date, and the text under "published as" is that application's
        # own description — not the longest on record, which the box
        # used to show even when the clause came from a different one.
        if apps and src_i is not None:
            _sa = apps[src_i]
            prop_source = (
                f'Lifted verbatim from <a href="#{esc(app_anchor(key, _sa[1]))}"'
                f' onclick="return goApp(\'{esc(app_anchor(key, _sa[1]))}\')">'
                f'an application below</a> ({esc(_sa[1])}, received '
                + (esc(str(_sa[5])) if _sa[5] else NOT_STATED)
                + '), which the council published as:')
            box_desc = _sa[16] or ""
        elif apps:
            prop_source = ('Lifted verbatim from an application below, '
                           'which the council published as:')
            box_desc = full_desc
        else:
            # No applications at all: the summary came from the Barbour
            # title, and "an application below" would point at a table
            # that says there are none. Same phrasing as the
            # pre-planning page.
            prop_source = 'Barbour ABI records it as:'
            box_desc = full_desc
        near = nearest(lat, lon)
        org = origins.get(key, [])
        env = sorted({s for a in apps for s in sig.environmental_signals(a[16] or "")})

        approws = []
        for a in sorted(apps, key=lambda x: str(x[5] or ""), reverse=True):
            portal = (f'<a href="{esc(a[12])}" target="_blank" rel="noopener">register</a>'
                      if a[12] and not str(a[12]).startswith("file://")
                      else '<span class="q">no register link</span>')
            durl = hv._drive_application_url(drive_apps, key, a[1])
            docs_cell = (f'<a href="{esc(durl)}" target="_blank" rel="noopener">'
                         f'{a[13] or 0}</a>' if durl else str(a[13] or 0))
            approws.append(
                f"<tr id=\"{esc(app_anchor(key, a[1]))}\">"
                f"<td><strong>{esc(a[1])}</strong></td><td>{esc(a[3])}</td>"
                # Four different silences. The register not publishing a
                # status or a date is not the same as us not having
                # triaged the application, and "not triaged" is a fact
                # about this project rather than about the council.
                f"<td>{esc(a[4]) or NOT_STATED}</td>"
                f"<td>{esc(str(a[5] or '')) or NOT_STATED}</td>"
                f"<td>{esc(str(a[6] or '')) or NOT_STATED}</td>"
                f"<td>{esc(a[7]) or '<span class=\"q\">not triaged</span>'}</td>"
                f"<td>{docs_cell}</td><td>{portal}</td></tr>"
                f"<tr><td colspan='8' class='help' style='padding-bottom:9px'>"
                f"{esc(trim(a[16], 320))}"
                # A zero with its reason beside it. A blocked portal and
                # a council that publishes nothing produce the same 0,
                # and the recorded acquisition verdict is what tells
                # them apart — e.g. Hackney's new register dropped its
                # own history, which a reporter should read as a
                # public-access failure, not a quiet application.
                + (lambda _r: (
                    f"<br><span class='q'>No documents held — "
                    f"{esc(trim(_r[1], 300)) if _r[1] else esc(_OUTCOME_PHRASE.get(_r[0], _r[0]))}"
                    f"</span>") if _r else "")(
                        empty_reasons.get(a[1])
                        if not (a[13] or 0) else None)
                + "</td></tr>")
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
        for (st, vt, vn, vu, verdict, fam, filed_as,
             f_doc, f_page, f_url) in findings.get(key, []):
            grouped.setdefault(fam or "other", []).append(
                (st, vt, vn, vu, verdict, filed_as, f_doc, f_page, f_url))
        fl = []
        n_shown = 0
        for fam, rows_ in grouped.items():
            items = []
            for st, vt, vn, vu, verdict, filed_as, f_doc, f_page, f_url in rows_:
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
                # Each statement cites its document (issue #146): the
                # Drive copy as the working link, the register beside it,
                # the page where the finding recorded one — the same
                # two-link rule as doc_link, built flat here because .q
                # is display:block and a citation must sit on the
                # statement's own line, not stack under it.
                cite = ""
                if f_doc or f_url:
                    _drive = drive_docs.get(int(f_doc), "") if f_doc else ""
                    _u = str(f_url or "")
                    _reg = _u if _u.startswith(("http://", "https://")) else ""
                    parts = []
                    if _drive:
                        parts.append(f'<a href="{esc(_drive)}" target="_blank" '
                                     f'rel="noopener">document</a>')
                        if _reg:
                            parts.append(f'<a href="{esc(_reg)}" target="_blank" '
                                         f'rel="noopener">register</a>')
                    elif _reg:
                        parts.append(f'<a href="{esc(_reg)}" target="_blank" '
                                     f'rel="noopener">document</a>')
                    if parts:
                        pg = f", p. {f_page}" if f_page else ""
                        cite = (" <span class='cite'>· "
                                + " · ".join(parts) + pg + "</span>")
                items.append(f"<li><span class='st'>{esc(st)}</span>{num}{tag}{moved} — "
                             f"{esc(trim(vt,190))}{cite}</li>")
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
                csv_url = drive_csv.get(hv._folder_key(key), "")
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

        # §5's caveat banner: one sentence in bold saying what state
        # this site is in, then what follows from it. The handoff names
        # five states and the build carried two, so a fully-read site
        # with no capacity in it looked identical to one nobody had got
        # to yet.
        def _banner(head, rest):
            return f'<div class="banner" style="margin-top:0"><b>{head}</b> {rest}</div>'

        # The signals this site matches, as pills on its own page — the
        # same neutral pill the table row uses, because a cohort is a
        # category and colour on this page means the state of a figure.
        sig_pills = "".join(
            f'<span class="sigpill t-{cohort_tone.get(_k, "slate")}">'
            f'{esc(cohort_title.get(_k, _k))}</span>'
            for _k in cohorts_of_site.get(key, ()))
        if sig_pills:
            sig_pills = f'<p class="sitepills">{sig_pills}</p>'

        # One banner, stating the plain fact about this site: either its
        # documents are unread, or it has none and here is why.
        # Every site gets a Drive folder, including those with nothing in
        # them but a site report — so the label has to say which it is,
        # or "Source documents" sends a reporter to an empty folder.
        _durl = drive.get(hv._folder_key(key))
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
        # A site page no longer sits under the table's header row, so
        # the two facts that row carried have to be on the page itself
        # (Luke, 2026-08-25): how much of the site has been read, and
        # what the reading leaves its capacity figure meaning. The bar
        # is the table's, so the two views say the same thing the same
        # way; the right column's coverage panel carries the detail.
        # Three steps, not two. A bar that is red at 90% and green at
        # 95% tells a reader those are opposite states; they are the
        # same state a few documents apart. Asked for by a reader on
        # 2026-08-26: red under 75%, amber to 95%, green above.
        # Measured against the documents that CAN be read, not every
        # document held. A site with four documents, one of them a
        # drawing, is as read as it will ever be, and showing that as
        # 75% in red told a reporter it was barely looked at (a reader,
        # 2026-08-26). `prose_held` is tiers A and B — drawings and the
        # deliberately-sampled repetitive classes are excluded, because
        # neither is a backlog. 93 sites that read as red are in fact
        # complete on everything readable.
        #
        # Still unfixed, and visible here: a corrupt or zero-byte
        # document counts in prose_held and can never be read, so its
        # site cannot reach green. That wants the held-but-unreadable
        # state the ROADMAP describes, and is not this change.
        _pct = (p_read / p_held) if p_held else 0
        _done = bool(p_held) and _pct >= 0.95
        _rstate = ("r-done" if _done else
                   "r-most" if _pct >= 0.75 else
                   "r-part" if p_read else "r-none")
        # The word still says what the READING means for the figures,
        # which does not change at 75%: a floor is a floor whether one
        # document is unread or four hundred. Only the colour grades.
        _rword = ("Complete" if _done else
                  "Figures are floors" if p_read else "Nothing published")
        _unread_able = _cd.get("prose_unreadable", 0)
        _skipped = held - p_held - _unread_able
        _bartitle = (f"{p_read} of {p_held} readable documents read"
                     + (f"; {_skipped} of the {held} held are drawings or "
                        f"sampled by design" if _skipped else "")
                     # Never silently dropped from the denominator: a
                     # document we hold and cannot read is a fact about
                     # the source, and a reporter may want to chase it.
                     + (f"; {_unread_able} yielded no readable text and "
                        f"cannot be analysed" if _unread_able else ""))
        state_html = (
            f'<span class="rbar" title="{esc(_bartitle)}">'
            f'<span class="rbar-fill {_rstate}" '
            f'style="width:{(100 * p_read / p_held) if p_held else 0:.0f}%"></span></span>'
            f'<span class="statebit">{p_read:,} of {p_held:,} readable '
            f'documents read '
            f'<span class="rstate {_rstate}">{_rword}</span></span>'
            # On the page, not only in the bar's tooltip (Luke,
            # 2026-08-26): a document we hold and cannot read is a fact
            # about the source that a reporter may want to chase, and
            # taking it out of the denominator without saying so would
            # be the kind of quiet subtraction this reader refuses
            # everywhere else. The table row has no room; this page has.
            + (f'<span class="statebit"><span class="q">'
               f'{_unread_able:,} more held, and unreadable</span></span>'
               if _unread_able else '')
            + (f'<span class="statebit"><span class="q">'
               f'{_skipped:,} drawings or sampled by design</span></span>'
               if _skipped else '')
            + f'<span class="statebit"><span class="tag '
              f'{"known" if known else "unknown"}">{esc(cap_label)}</span></span>')

        # §5's links row, built where the Drive URL is known. No council
        # register link: this reader holds register URLs per application,
        # not per site, and the applications table below carries every
        # one of them — a single "register" link would have to pick one
        # and would be wrong on any site that spans councils.
        _csv = drive_csv.get(hv._folder_key(key), "")
        _bits = []
        if _durl and held:
            _bits.append(f'<a href="{esc(_durl)}" target="_blank" rel="noopener">'
                         f'{held:,} documents on Drive</a>')
        if _csv:
            _bits.append(f'<a href="{esc(_csv)}" target="_blank" rel="noopener">'
                         f'Findings CSV'
                         + (f' ({findings_n:,})' if findings_n else '') + '</a>')
        for _pg in _operator_pages.get(key, ()):
            _bits.append(f'<a href="{esc(_pg["url"])}" target="_blank" '
                         f'rel="noopener">{esc(_opp.link_text(_pg))}</a>')
        # Our map, not Google's: the internal map is the one showing
        # proximity to energy projects (issue #144), and Google Maps
        # already sits beside the coordinates in Site details.
        if lat is not None and lon is not None:
            _bits.append(f'<a href="#map" onclick="showMap(\'{esc(key)}\');'
                         f'return false">Show on the map</a>')
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

        # Two register rows for one site that do not agree. Only counted
        # where they measure the same quantity: a grid connection and a
        # metered consumption differing is not a disagreement.
        _by_q = defaultdict(set)
        for _c in site_claims:
            if _c.get("value_mw") is not None:
                _by_q[_c["quantity_type"]].add(round(float(_c["value_mw"]), 1))
        _claim_conflict = any(len(v) > 1 for v in _by_q.values())

        # The state is `cap_key`, not a threshold reinvented here:
        # site_profile.capacity_status already decides what a site's
        # emptiness or figure means, and a banner reaching its own
        # verdict could contradict the status tag two lines above it.
        # The handoff names five states and the build carried two, so a
        # fully-read site with no capacity in it looked identical to one
        # nobody had got to yet.
        # p_held/p_read, not held/read: cap_key is computed from the
        # prose pool, and a drawing with no extractable text cannot
        # state a capacity. The word "readable" carries the denominator
        # so this and the coverage bar are not two versions of one
        # number.
        site_banner = ""
        if cap_key in ("pre_application", "no_documents"):
            lbl, why = site_profile.no_documents_reason(
                ["pre_application"] if not (n_apps or 0)
                else site_outcomes.get(key, ()))
            site_banner = _banner(esc(lbl) + ".", esc(why))
        elif cap_key == "inferred_floor_area":
            # The weakest class in the release, and the one most likely
            # to be quoted as though it were disclosed.
            site_banner = _banner(
                "The figure for this site is not stated anywhere.",
                "It is inferred from floorspace using the density "
                "assumption set out in the methodology, and it is the "
                "weakest class of figure in this release: usable as a "
                "sense of scale, never as a quoted number.")
        elif cap_key == "read_none_disclosed":
            # A finished check, not a missing value. Without this the
            # page reads as a gap in the project rather than a silence
            # in the record.
            site_banner = _banner(
                f"All {p_held:,} readable document"
                f"{'' if p_held == 1 else 's'} for this site "
                f"{'has' if p_held == 1 else 'have'} been analysed and "
                f"none states a capacity.",
                "This is recorded as a finished check, not as a missing "
                "value: the absence is the record\u2019s, not this "
                "project\u2019s.")
        elif cap_key == "not_yet_analysed":
            site_banner = _banner(
                f"None of this site\u2019s {p_held:,} readable document"
                f"{'' if p_held == 1 else 's'} has been analysed yet.",
                "Nothing below is a statement about what they contain.")
        elif is_prov or cap_key == "partially_analysed":
            site_banner = _banner(
                "Reading is incomplete.",
                esc(site_profile.provisional_statement(p_held, p_read)))
        elif _claim_conflict:
            site_banner = _banner(
                "Register rows that plausibly describe this site disagree "
                "with each other.",
                "A tentative match is not evidence; both are shown so "
                "that a reporter can resolve the disagreement rather "
                "than inherit it.")

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
                # And which realm the figure describes, where the source
                # itself says: a facility inside a campus total is not a
                # second opinion on that campus, and must never be added
                # to it.
                if c.get("component_of"):
                    _qty += (" <span class='help'>· one facility within "
                             f"{esc(c['component_of'])}</span>")
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
                          if c["source_locator"] else "")
                       + (f" · {_ourcopy}" if (_ourcopy := our_copy(c)) else ""))
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


        # §5's "Adjudicated power figures", in the form the handoff
        # specifies: the value in serif at 23px, the quantity under it,
        # who it was told to and the words it was published in, then the
        # document, the page, the model and the fetch date, then the
        # quote itself.
        #
        # Provenance is attached only where it describes the number
        # beside it. The generation figure is the power adjudication
        # filtered again by generation-2.5 — which rules some of those
        # rows out as storage or as not generation at all — so its
        # maximum can be lower than the power adjudication's, and
        # pinning the larger row's quote to the smaller number would
        # source a figure to a document that does not state it.
        _fig_order = [("it_load", it), ("total_site", tot),
                      ("grid_connection", grid), ("onsite_generation", gen)]
        _fig_rows, _absent = [], []
        for _qt, _val in _fig_order:
            _label = ccl.QUANTITY_LABELS.get(_qt, _qt.replace("_", " "))
            if not _val:
                _absent.append(_label)
                continue
            pv = fig_prov.get((key, _qt))
            if pv and abs(pv["mw"] - float(_val)) > 0.001:
                pv = None
            _doc = (doc_link(pv["url"], pv["title"],
                             drive_docs.get(pv.get("document_id") or -1, ""))
                    if pv and pv["title"] else "")
            _meta = []
            if pv:
                if pv["page"]:
                    _meta.append(f'page&nbsp;{pv["page"]}')
                _meta.append(f'{esc(pv["ref"])}')
                if pv["model"]:
                    _meta.append(f'read by {esc(pv["model"])}')
                if pv["fetched"]:
                    _meta.append(f'fetched {pv["fetched"]:%-d %b %Y}')
            else:
                _src = power_src.get((key, _qt))
                if _src:
                    _meta.append(f'adjudicated in {esc(_src)}')
            _quote = ""
            if pv and pv["quote"]:
                _quote = (f'<p class="figquote">\u201c'
                          f'{esc(trim(" ".join(pv["quote"].split()), 460))}'
                          f'\u201d</p>'
                          f'<p class="figgate">Quote verified verbatim against '
                          f'the document text before storage \u00b7 '
                          f'<a href="#methodology">how the gate works</a></p>')
            _told = ('Told to <b>the planning authority</b>'
                     + (f' \u00b7 published as \u201c'
                        f'{esc(humanise(pv["as_written"], sentence=True))}\u201d' if pv else ''))
            _fig_rows.append(
                f'<div class="figrow"><div><div class="figval">{mw_text(_val)}'
                f'<span class="figunit"> MW</span></div>'
                f'<div class="figq">{esc(_label)}</div></div><div>'
                f'<p class="figtold">{_told}</p>'
                + (f'<p class="figmeta">{_doc}'
                   + (f' <span class="q">\u00b7 ' + " \u00b7 ".join(_meta)
                      + '</span>' if _meta else '') + '</p>'
                   if (_doc or _meta) else '')
                + _quote + '</div></div>')

        # Editorial rule 4: every figure the adjudicator saw for this
        # site, the ruled-out ones included, each with the verdict and
        # the reason. Collapsed, because it is the working underneath a
        # number rather than the number.
        _af = all_figs.get(key) or []
        allfigs_html = ""
        if _af:
            _total = all_figs_total.get(key, len(_af))
            _kept = sum(1 for r in _af if r["verdict"] == "site_capacity")
            _rows = "".join(
                # The figure as its source printed it: a 3,900 kVA
                # switchboard is not "0 MW", and kVA is not megawatts at
                # all. The normalised value appears beside it only where
                # the adjudicator produced one and the units differ.
                '<tr><td class="n">'
                + (f'{r["value"]:,g}' if r["value"] is not None
                   else (f'{r["mw"]:g}' if r["mw"] is not None else "\u2014"))
                + '</td><td class="q">'
                + esc(r["unit"] or ("MW" if r["mw"] is not None else ""))
                + (f'<span class="q">= {r["mw"]:g} MW</span>'
                   if r["mw"] is not None and r["unit"] not in (None, "MW")
                   else "") + '</td>'
                + f'<td>{esc(humanise(r["as_written"] or "", sentence=True))}</td>'
                + '<td>' + doc_link(r["url"], r["title"] or r["ref"],
                                     drive_docs.get(r.get("document_id") or -1, "")) + '</td>'
                + '<td class="q">' + (f'page {r["page"]}' if r["page"] else "—")
                + f' \u00b7 {esc(r["ref"])}</td>'
                + f'<td class="q">{esc(r["model"] or "")}</td>'
                + '<td><span class="adjpill {1}">{0}</span>'.format(
                    esc(VERDICT_LABEL.get(r["verdict"], (r["verdict"], "v-maybe"))[0]),
                    VERDICT_LABEL.get(r["verdict"], (r["verdict"], "v-maybe"))[1])
                + (f'<span class="q">{esc(trim(r["reason"], 260))}</span>'
                   if r["reason"] else "") + '</td></tr>'
                for r in _af)
            _cut = ("" if _total <= len(_af) else
                    f' The {_total - len(_af):,} not shown are the lowest-valued '
                    f'of the {_total:,}; the full set is in this site\u2019s '
                    f'findings CSV.')
            allfigs_html = (
                f'<details class="allfigs"><summary>Show every figure found in '
                f'this site\u2019s documents, including the '
                f'{_total - _kept:,} excluded from the figures above'
                f'</summary>'
                f'<div class="scroll"><table class="afig"><thead><tr>'
                f'<th>Value</th><th>Unit</th><th>Quantity as written</th>'
                f'<th>Document</th><th>Locator</th><th>Read by</th>'
                f'<th>Adjudication</th></tr></thead><tbody>{_rows}</tbody>'
                f'</table></div>'
                f'<p class="help">{len(_af):,} of {_total:,} adjudicated '
                f'figures.{_cut} Rows marked excluded are kept, not deleted: '
                f'a maximum taken over this table will be wrong, which is why '
                f'the reason travels with the row.'
                + (f' Full set in <a href="{esc(_csv)}" target="_blank" '
                   f'rel="noopener">this site\u2019s findings CSV</a>'
                   if _csv else '')
                + ' and the <a href="#package">DuckDB file</a>.</p></details>')

        figures_html = (
            '<div class="box figures"><h4>Adjudicated power figures</h4>'
            '<p class="help">The figures adjudicated as describing <em>this '
            'site</em>. Different quantities are not contradictions; the '
            'comparison that matters is one quantity told twice. Every row '
            'below is also a row in the findings CSV.</p>'
            + ("".join(_fig_rows) if _fig_rows else
               '<p class="help">No figure in this site\u2019s documents was '
               'adjudicated as its capacity.</p>')
            + (f'<p class="figabsent">Not stated in any document read: '
               f'{esc(", ".join(_absent))}.</p>' if _absent else '')
            + f'<dl class="kv figsum"><dt>Best available</dt><dd>'
            + (f'<b>{mw_text(est.value_mw)} MW</b>' if est.value_mw
               else '<span class="q">no figure</span>')
            + ('<span class="prov"> ' + esc(site_profile.PROVISIONAL_MARK)
               + '</span>' if is_prov and est.value_mw else '')
            + f'</dd><dt>Basis</dt><dd>{esc(est.basis)}</dd>'
            + f'<dt>Confidence</dt><dd>{esc(est.confidence) or NOT_APPLICABLE}</dd>'
            + f'<dt>Caveat</dt><dd>{esc(est.caveat) or NOT_APPLICABLE}</dd>'
            + mixed_note
            + '</dl>'
            + allfigs_html
            + f'<p class="help provenance">{esc(ccl.DECLARED_POWER_NOTE)}</p>'
            + '</div>')

        who = who_cell(prof)
        reading_html = reading_panel(key, held)
        _adj = adjacent_by_site.get(key)
        adjacent_html = ""
        if _adj:
            _items = "".join(
                f'<li><b>{esc(_ref)}</b>'
                + (f' · <a href="{esc(_aurl)}" target="_blank" '
                   f'rel="noopener">register</a>'
                   if _aurl and str(_aurl).startswith("http") else '')
                + (f' · <a href="{esc(drive_adj[hv.clean_ref(_ref)])}" '
                   f'target="_blank" rel="noopener">our copy</a>'
                   if hv.clean_ref(_ref) in drive_adj else '')
                + (f' · {_dist / 1000:.2f} km' if _dist is not None else '')
                + f'<br>{esc(trim(_desc, 180))}'
                + f'<br><span class="help">{esc(_evid)}</span></li>'
                for _basis, _dist, _evid, _ref, _desc, _aurl in _adj["doc"])
            _prox = _adj["prox"]
            _prox_note = (
                f'<p class="help">{_prox} further power application'
                f'{"" if _prox == 1 else "s"} lie'
                f'{"s" if _prox == 1 else ""} within 1 km of this site. '
                f'Distance alone is a candidate, not a supply '
                f'relationship, so they are counted rather than '
                f'listed.</p>' if _prox else '')
            adjacent_html = (
                '<div class="box adjacent"><h4>Adjacent power</h4>'
                '<p class="help">Power infrastructure consented in its '
                'own right — a substation, an energy centre, a standby '
                'fleet — stands beside this site rather than belonging '
                'to it: its capacity could serve many purposes and is '
                'not this site’s demand. Each entry records how '
                'the connection is known. Their documents are held on '
                f'Drive under <a href="{ADJACENT_POWER_URL}" '
                'target="_blank" rel="noopener">adjacent_power</a>, '
                'beside the site folders; an entry links its own folder '
                'once that folder has been synced.</p>'
                + (f'<ul class="adjlist">{_items}</ul>' if _items else '')
                + _prox_note + '</div>')
        hay = " ".join(str(x or "").lower() for x in
                       (name, derived_names.get(key), key, addr,
                        ", ".join(councils or []), full_desc,
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
        # four weights and one glyph: a disclosed figure is stated in
        # full, a connection or standby-implied figure is lighter, a
        # floorspace estimate carries "≈" because it is arithmetic on an
        # area rather than anything anyone published, and an operator's
        # own campus figure is italic — published, but to customers
        # rather than to the planning authority.
        # Keyed on the basis first, because the rung is Medium and a
        # Medium grid connection is not the same kind of figure: one is
        # a first-party statement, the other headroom we read off an
        # application. Confidence carries the rest, as it always did.
        _wclass = ("w-operator" if est.basis == scale.OPERATOR_BASIS else
                   {"High": "w-stated", "Medium": "w-implied",
                    "Low": "w-implied", "Indicative": "w-modelled"}.get(
                        est.confidence or "", "w-implied"))
        _mark = "≈" if est.confidence == "Indicative" else ""
        mw_cell = ((f"<span class='fig {_wclass}'>{_mark}{mw}</span>"
                    f"<span class='q'>{esc(est.basis)}"
                    + (" <span class='prov'>· may rise</span>" if is_prov and mw else "")
                    + "</span>") if mw
                   else f"<span class='q'>{esc(est.basis)}</span>")

        # A confidence tier and a count, never a megawatt figure: the main
        # row is scanned and sorted, and a number here beside Declared
        # power would read as directly comparable to it. It is not — a
        # register claim can be a different quantity type from the site's
        # own figure, and "tentative" exists precisely to say a match is
        # a lead rather than an attribution. Collapsing several of those
        # into one "highest" number would launder that distinction away.
        _tier_rank = {"strong": 3, "probable": 2, "tentative": 1}
        if site_claims:
            # A campus total and the facility figures inside it are one
            # source itemised, not several sources agreeing, so the
            # components do not swell the count on a row someone scans
            # and sorts — the same reason this cell shows a tier and
            # never a megawatt. They are named in the tooltip and shown
            # in full in the panel below. Where a site holds components
            # whose parent is matched elsewhere (VIRTUS's Slough rows,
            # whose campus claim covers a wider scope than this site),
            # the components are all there is and they are counted.
            _counted = [c for c in site_claims
                        if not c.get("component_of")] or site_claims
            best = max(_counted, key=lambda c: _tier_rank[c["confidence"]])
            _n = len(_counted)
            ind_label = best["confidence"] + (f" ×{_n}" if _n > 1 else "")
            ind_title = "; ".join(
                f"{c['claim_name']} ({c['confidence']}"
                + (", part of " + c["component_of"] if c.get("component_of")
                   else "") + ")"
                for c in site_claims)
            ind_class = {"strong": "known", "probable": "unknown",
                         "tentative": "tentative"}[best["confidence"]]
            ind_cell = (f'<span class="tag {ind_class}" title="{esc(ind_title)}">'
                       f'{esc(ind_label)}</span>')
            ind_sort = _tier_rank[best["confidence"]] * 100 + _n
        else:
            # No external claim is MATCHED to this site — which is not
            # the same as no external source naming it. `load_site_claims`
            # returns only live matches, and claims go unmatched because a
            # site record covers a whole estate as often as because no
            # register mentions the scheme. Saying "none in external
            # sources" would assert a search nobody ran.
            ind_cell = '<span class="q">no external match</span>'
            ind_sort = 0

        rendered_classes[site_classes[key].key] += 1
        body.append(f"""<tr class="site" data-key="{esc(key)}" data-hay="{esc(hay)}"
 data-known="{1 if known else 0}"
 data-near="{esc(near[0]['name'] if near else '')}" data-mw="{est.value_mw or ''}"
 data-prov="{1 if is_prov else 0}" data-origin="{esc('|'.join(org))}"
 data-who="{esc(who['filter_key'])}" data-cohorts="{esc('|'.join(cohorts_of_site.get(key, ())))}"
 data-class="{esc(site_classes[key].key)}">
<td class="sitecell" data-v="{esc(_shown(key, name))}"><span class="sname">{
 '' if site_classes[key].is_datacentre else
 f'<span class="classbadge" title="{esc(site_classes[key].display_description)}">'
 f'{esc(site_classes[key].label)}</span>'}{esc(trim(_shown(key, name), 84))}</span>
 <span class="skey">{esc(' · '.join([x for x in [key, trim(addr, 74), ', '.join(councils or [])] if x]))}</span>
 <span class="sprop">{esc(trim(summary, 230)) or NO_DESCRIPTION}{
 '' if descriptive else ' — the register holds no description of the development itself, only procedural applications'}</span></td>
<td data-v="{esc(who['sort'])}">{who['cell']}</td>
<td class="sigcell" data-v="{len(cohorts_of_site.get(key, ()))}">{
 ''.join(f'<span class="sigpill t-{cohort_tone.get(_k, "slate")}">'
         f'{esc(cohort_title.get(_k, _k))}</span>'
         for _k in cohorts_of_site.get(key, ())) or '<span class="q">no cohorts</span>'}</td>
<td class="mw" data-v="{est.value_mw or ''}">{mw_cell}</td>
<td data-v="{ind_sort}">{ind_cell}</td>
<td data-v="{p_read}"><span class="rbar" title="{esc(_bartitle)}"><span
 class="rbar-fill {_rstate}"
 style="width:{(100 * p_read / p_held) if p_held else 0:.0f}%"></span></span>{p_read:,}/{p_held:,}<span
 class="q">readable documents read</span><span class="q rstate {_rstate}">{_rword}</span></td>
</tr>
<tr class="detail"><td colspan="6">
 <!-- §5 of the design handoff. The header card carries the name and the
      identifiers, which the page used to scrape out of the row with
      `tr.querySelector('td strong')` — and after the table's site cell
      became a multi-row cell there was no <strong> to find, so every
      site page was titled with its key. Built here, from the values
      themselves, it cannot drift from the row again. -->
 <div class="card sitehead">
  {sig_pills}
  <h2 class="sitename">{
   '' if site_classes[key].is_datacentre else
   f'<span class="classbadge" title="{esc(site_classes[key].display_description)}">'
   f'{esc(site_classes[key].label)}</span>'}{esc(_shown(key, name))}</h2>
  <!-- "Record built from" is said, not implied: the bare origin phrase
       ("The planning sweep and Barbour") read as an unlabelled mystery
       in the subheading, while the Site details box below labels the
       same value (issue #153). Lower-cased to sit inside the sentence
       the label starts. -->
  <p class="siteident">{esc(", ".join(councils or []))}{" · " if addr else ""}{esc(addr)}
   · <code>{esc(key)}</code> · Record built from {esc(SITE_ORIGIN.get(cls, (cls, ""))[0][:1].lower() + SITE_ORIGIN.get(cls, (cls, ""))[0][1:])}</p>
  <p class="sitestate">{state_html}</p>
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
    <p><strong>{esc(summary) or NO_DESCRIPTION}</strong></p>
    <p class="help">{prop_source}</p><p>{esc(trim(box_desc, 640)) or NO_DESCRIPTION}</p></div>
{figures_html}
  {claims_html}
  <div class="box"><h4>Key findings from the planning applications</h4>
   {findings_html}</div>
 </div>
 <div class="col-computed">
  {reading_html}
  {adjacent_html}
  <div class="box identity"><h4>Site details</h4>
    <div class="fields">
     <div class="stack">
      <div><span class="lbl">Site key</span><span class="val">{esc(key)}</span></div>
      <div><span class="lbl">Record built from</span><span class="val">{
        esc(SITE_ORIGIN.get(cls, (cls, ""))[0])}
       <span class="help">{esc(SITE_ORIGIN.get(cls, ("", ""))[1])}</span></span></div>
      <!-- Issue #159. The class is stated with the applications that
           produced it, so it reads as a derivation a reporter can
           check rather than a label the site has been given. -->
      <div><span class="lbl">Kind of site</span><span class="val">{
        esc(site_classes[key].label)}
       <span class="help">{esc(site_classes[key].display_description)}{
        " " + esc(site_classes[key].provenance)
        if site_classes[key].provenance else ""}</span></span></div>
      {f'''<div><span class="lbl">Derived name</span><span class="val">{esc(derived_names[key])}
       <span class="help">the record&#x27;s own generated name; the display name is a
       curated alias (data/priors/site_aliases.yaml, with its source)</span></span></div>'''
       if key in derived_names else ''}
     </div>
     <!-- The coordinates themselves link to our map, not just the word
          "map" beside them: users clicked the Google Maps link and
          missed ours, which is the one showing proximity to energy
          projects (issue #144). -->
     <div><span class="lbl">Coordinates</span><span class="val">
      {f'<a href="#map" onclick="showMap(\'{esc(key)}\');return false" '
       f'title="Show this site on the map">{lat:.5f}, {lon:.5f}</a>'
       if lat and lon else '—'}
      {maplink}{' · ' + gmaps if gmaps else ''}
      <span class="help">{esc(csrc or 'source unknown')}</span></span></div>
     <div><span class="lbl">How we found it</span><span class="val">
      {esc(', '.join(org)) or NOT_STATED}
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
     <dt>End user</dt><dd>{esc(prof.get('end_user')) or why_empty(held, read)}
      {f'<span class="help">group: {esc(prof["operator_group"])}</span>'
        if prof.get('operator_group') else ''}</dd>
     <dt>Applicant of record</dt><dd>{esc(prof.get('applicant_of_record')) or why_empty(held, read)}</dd>
     <dt>Advisers</dt><dd>{esc(prof.get('advisers')) or why_empty(held, read)}</dd>
     <dt>Also named in the documents</dt><dd>{counted(prof.get('named_in_documents'), why_empty(held, read))}</dd>
     <dt>Planning authority</dt><dd>{esc(prof.get('authority'))
        or '<span class="q">not recorded</span>'}</dd>
     <dt>Barbour project</dt><dd>{esc(btitle)
        or '<span class="q">no Barbour match</span>'}
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
      (esc(prof.get('generator_count')) + ' units') if prof.get('generator_count')
      else why_empty(held, read)}</dd>
    <dt>Generation type</dt><dd>{counted(prof.get('generator_fuel'), why_empty(held, read))}</dd>
    <dt>Cooling method</dt><dd>{counted(prof.get('cooling_method'), why_empty(held, read))}</dd>
    <dt>Water evidence</dt><dd>{esc(prof.get('water_evidence')) or why_empty(held, read)}</dd>
    <dt>EIA status</dt><dd>{esc(prof.get('eia_status_label')) or why_empty(held, read)}</dd>
    <dt>Environmental subjects</dt><dd>{esc(', '.join(env)) or why_empty(held, read)}</dd>
    <dt>Finding subjects</dt><dd>{esc(', '.join((families or [])[:6])) or why_empty(held, read)}</dd>
   </dl>
   <p class="help">{esc(prof.get('generator_caveat') or '')}</p>
   <p class="help">{esc(prof.get('cooling_caveat') or '')}</p></div>
  {ctx_html}
 </div>
</div>
<!-- Below BOTH columns, not the last item of the left one (issue
     #156). The applications table is wider than a column and used to
     overflow the left column to full width — which read as designed
     until a site with a short left column put the right column's boxes
     level with it, and the spill collided with them. A full-width band
     after the grid is the layout the overflow was accidentally
     imitating, and the scroll wrapper keeps the wide table inside it. -->
{f'''<details class="apps-d"><summary>Show the {len(apps)} planning application{'' if len(apps) == 1 else 's'} for this site</summary><div class="appscroll">{apps_html}</div></details>''' if apps else apps_html}
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
        # Same contract as a live site: the alias displays, the derived
        # title stays visible on the row's own page.
        derived_title = title
        title = _aliases.get(key, title)
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
        # A pre-planning row is a Barbour record with no application, so
        # it goes through the same rule rather than being told what it
        # is: several of these titles name a data centre outright, and
        # hardcoding the class badged "Virtus Data Centres - London 3
        # Data Centre" as having no planning record AND not being a
        # datacentre.
        _pcls = sclass.classify(key, (), (key,), ((key, title or ""),))
        rendered_classes[_pcls.key] += 1
        body.append(f"""<tr class="site" data-key="{esc(key)}" data-hay="{esc(hay)}"
 data-known="0"
 data-near="{esc(near[0]['name'] if near else '')}" data-mw="" data-prov="0"
 data-origin="Barbour ABI" data-who="{esc(who['filter_key'])}" data-cohorts=""
 data-class="{esc(_pcls.key)}">
<td class="sitecell" data-v="{esc(_shown(key, title))}"><span class="sname">{
 '' if _pcls.is_datacentre else
 f'<span class="classbadge" title="{esc(_pcls.display_description)}">{esc(_pcls.label)}</span>'}{esc(trim(_shown(key, title), 84))}</span>
 <span class="skey">{esc(' · '.join([x for x in [key, trim(address or '', 74), authority or ''] if x]))}</span>
 <span class="sprop">{esc(trim(summary, 230)) or NO_DESCRIPTION}</span></td>
<td data-v="{esc(who['sort'])}">{who['cell']}</td>
<td class="sigcell" data-v="0"><span class="q">no signals</span></td>
<td class="mw" data-v=""><span class="q">no application yet</span></td>
<td data-v="0"><span class="q">no documents</span></td>
<td data-v="-1"><span class="q rstate r-none">Nothing published</span></td>
</tr>
<tr class="detail"><td colspan="6">
 <div class="card sitehead">
  <h2 class="sitename">{
   '' if _pcls.is_datacentre else
   f'<span class="classbadge" title="{esc(_pcls.display_description)}">'
   f'{esc(_pcls.label)}</span>'}{esc(_shown(key, title))}</h2>
  <p class="siteident">{esc(authority or '')}{" · " if address else ""}{esc(address)}
   · <code>{esc(key)}</code> · Barbour ABI project, no application yet</p>{
   f'<p class="siteident">Barbour ABI titles this project '
   f'&#8220;{esc(derived_title)}&#8221;; the name above is a reporter&#8217;s.</p>'
   if derived_title != title else ''}
  <p class="sitelinks">{''.join(
    f'''<span><a href="{esc(_pg["url"])}" target="_blank" rel="noopener">{esc(_opp.link_text(_pg))}</a></span>'''
    for _pg in _operator_pages.get(key, ()))}{f'''<span><a href="#map" onclick="showMap('{esc(key)}');return false">Show on the map</a></span>'''
   if plat is not None and plon is not None else ''}<span><a href="#site-{esc(key)}">Link to this site</a></span></p>
 </div>
 <div class="banner" style="margin-top:0"><b>No application submitted yet.</b>
  {esc(site_profile.NO_DOCUMENT_REASONS['pre_application'])}</div>
 <div class="sitebody">
  <div class="col-record">
   <div class="box proposal"><h4>Proposal</h4>
    <p><strong>{esc(summary) or NO_DESCRIPTION}</strong></p>
    <p class="help">Barbour ABI records it as:</p><p>{esc(description) or NO_DESCRIPTION}</p></div>
  <div class="box"><h4>Scheme</h4>
   <dl class="kv">
    <dt>Planning authority</dt><dd>{esc(authority) or NOT_STATED}</dd>
    <dt>Contract value</dt><dd>{f'£{pvalue:,.0f}' if pvalue else '—'}</dd>
    <dt>Floor area</dt><dd>{f'{pfloor:,.0f} m²' if pfloor else '—'}</dd>
    <dt>Site area</dt><dd>{f'{psite:,.2f} ha' if psite else '—'}</dd>
    <dt>Plan date</dt><dd>{esc(str(pplan or '')) or NOT_STATED}</dd>
    <dt>Decision date</dt><dd>{esc(str(pdecision or '')) or NOT_STATED}</dd>
   </dl>
   <p class="help provenance">Barbour ABI data is licensed and must be credited
    in published output.</p></div>
  <!-- The row's "Who's behind it" column is computed for these rows from
       Barbour's role blocks (bprof, above), but the panel used to show
       none of it: the table asserted "Segro" on three Ipswich Road /
       Buckingham Avenue / Ajax Avenue rows and the page a reader clicked
       through to never mentioned Segro (Luke, 2026-08-27). A column the
       page cannot substantiate is the one thing provenance forbids, so
       the same fields the column reads are stated here. -->
  <div class="box parties"><h4>Who is behind it</h4>
   <dl class="kv">
    <dt>End user</dt><dd>{esc(bprof.get('end_user')) or NOT_STATED}
     {f'<span class="help">group: {esc(bprof["operator_group"])}</span>'
       if bprof.get('operator_group') else ''}</dd>
    <dt>Applicant of record</dt><dd>{esc(bprof.get('applicant_of_record')) or NOT_STATED}</dd>
    <dt>Advisers</dt><dd>{esc(bprof.get('advisers')) or NOT_STATED}</dd>
    <dt>Planning authority</dt><dd>{esc(bprof.get('authority')) or NOT_STATED}</dd>
   </dl>
   <p class="help">Every name here is Barbour ABI's own role block for this
    project, and nothing else: with no application there are no documents to
    read, so there is no second source to agree or disagree with it.</p></div>
  </div>
  <div class="col-computed">
   <div class="box identity"><h4>Site details</h4>
    <div class="fields">
     <div class="stack">
      <div><span class="lbl">Barbour reference</span><span class="val">{esc(pref)}</span></div>
      <div><span class="lbl">Stage</span><span class="val">{esc(pstage) or NOT_STATED}</span></div>
     </div>
     <div><span class="lbl">Development type</span><span class="val">{esc(dev_type) or NOT_STATED}</span></div>
     <div><span class="lbl">Coordinates</span><span class="val">
      {f'<a href="#map" onclick="showMap(\'{esc(key)}\');return false" '
       f'title="Show this site on the map">{plat:.5f}, {plon:.5f}</a>'
       if plat and plon else '—'} {maplink}</span></div>
     <div><span class="lbl">Environmental subjects</span>
      <span class="val">{esc(', '.join(env)) or NOT_STATED}</span></div>
     <div><span class="lbl">Nearest energy project</span>
      <span class="val">{near_html}</span></div>
    </div></div>
   {ctx_html}
  </div>
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
            count_html = ('<p class="sigwithheld">Not computed for this '
                          'release.</p>'
                          f'<p class="sigfloor">{esc(r.withheld)}</p>')
            actions = ""
        else:
            count_html = (f'<div class="signum">{n:,}</div>'
                          f'<div class="sigunit">site{"" if n == 1 else "s"}, '
                          f'when this page was built</div>')
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
        # The design handoff's §3 card: family label, verification pill,
        # a headline stating the count in words and the property, the
        # rule itself in a monospace block, what it does not tell you,
        # the actions row, and a right-hand column carrying the count
        # and what cannot enter the cohort.
        n_members = len(c.result.members)
        # A withheld cohort has no count, and "no sites match this" is
        # the one thing it must not say: the rule was not run, which is a
        # different claim from a result of zero. Its headline is the
        # property alone.
        _words = _count_in_words(n_members, "")
        headline = (esc(c.cohort.title) if r.withheld else
                    esc(c.cohort.headline.format(
                        n=_words[:1].upper() + _words[1:])))
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
   <h3 class="sigheadline">{headline}</h3>
   <p class="sigprose">{esc(c.cohort.definition)}</p>
   <div class="sigquery">{esc(c.cohort.rule)}</div>
   <p class="siglimits"><b>What it does not tell you.</b> {esc(c.cohort.limits)}</p>
   {checks_html}
   {actions}
  </div>
  <div class="sigside">
   {count_html}
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
         f'{esc(c.cohort.title)} <span class="n">({len(c.result.members)})</span></button>')
        if not c.result.withheld else
        (f'<button type="button" class="chip" disabled '
         f'title="{esc(c.result.withheld)}" data-withheld="1">'
         f'{esc(c.cohort.title)} <span class="n">(withheld)</span></button>')
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
            f"<span class='q'>{esc(r[0])}</span>"
            # Why this application is in the dataset. A reporter asked
            # of Barrow/B14/2018/0568, which has no documents and no
            # register link, why it was there at all -- and the answer
            # was recorded and simply not shown: our keyword sweep found
            # it, and its description names a data centre in terms.
            f"<span class='q'>{discovery(r[17])}</span></td>"
            f"<td>{esc(r[3])}</td><td>{esc(r[4]) or NOT_STATED}</td>"
            f"<td data-v='{esc(str(r[5] or ''))}'>{esc(str(r[5] or '')) or NOT_STATED}</td>"
            f"<td>{esc(r[7]) or '<span class=\"q\">not triaged</span>'}</td>"
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
            f"<td class='mw'>{esc(p['cap']) or NOT_STATED}</td><td>{esc(p['type'])}</td>"
            f"<td>{esc(p['stage'] or p['status']) or NOT_STATED}</td><td>{esc(p['applicant'])}</td>"
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

    def stacked_bars(items, title, note, series, unit=""):
        """Bars split into named parts, bottom part first.

        `items` is [(label, {series_key: count})]; `series` is
        [(key, human label, css class)] in stacking order. The parts are
        distinguished by fill and named in a legend, because a stack read
        by colour alone is unreadable to anyone who cannot separate the
        two — and these two parts are not interchangeable: one is what an
        applicant stated, the other is arithmetic on a floor area.
        """
        if not items:
            return ""
        w, h, pad, gap = 520, 168, 26, 3
        top = max(sum(v.values()) for _, v in items) or 1
        bw = (w - pad) / len(items)
        rects, labels = [], []
        for i, (lab, parts) in enumerate(items):
            x, y = pad + i * bw, h - 20
            for key, human, cls in series:
                v = parts.get(key, 0)
                if not v:
                    continue
                bh = (h - 34) * v / top
                y -= bh
                rects.append(
                    f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" '
                    f'width="{bw - gap:.1f}" height="{bh:.1f}">'
                    f'<title>{esc(lab)}: {v:,} {esc(human)}</title></rect>')
            if len(items) <= 9 or i % 2 == 0 or i == len(items) - 1:
                labels.append(f'<text class="xl" x="{x + (bw - gap) / 2:.1f}" '
                              f'y="{h - 7}" text-anchor="middle">{esc(lab)}</text>')
        legend = "".join(
            f'<span class="key"><i class="{cls}"></i>{esc(human)} '
            f'<b>{sum(v.get(key, 0) for _, v in items):,}</b></span>'
            for key, human, cls in series)
        return (f'<figure class="chart"><figcaption>{esc(title)}</figcaption>'
                f'<p class="legend">{legend}</p>'
                f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
                f'<text class="yl" x="0" y="12">{top:,}</text>'
                f'<line class="ax" x1="{pad}" y1="{h - 20}" x2="{w}" y2="{h - 20}"/>'
                + "".join(rects) + "".join(labels)
                + f'</svg><p class="help">{esc(note)}</p></figure>')

    def pie(slices, title, note):
        """Proportions, with every slice named and counted in the legend.

        A pie is only honest where the parts are one whole and the whole
        is stated, so the total goes in the middle and each slice carries
        its own count — nobody has to estimate an angle.
        """
        slices = [(lab, v, cls) for lab, v, cls in slices if v]
        total = sum(v for _, v, _ in slices)
        if not total:
            return ""
        r, cx, cy = 62, 70, 74
        arcs, a0 = [], -90.0
        for lab, v, cls in slices:
            a1 = a0 + 360.0 * v / total
            if len(slices) == 1:
                arcs.append(f'<circle class="{cls}" cx="{cx}" cy="{cy}" r="{r}">'
                            f'<title>{esc(lab)}: {v:,}</title></circle>')
                break
            x0, y0 = _polar(cx, cy, r, a0)
            x1, y1 = _polar(cx, cy, r, a1)
            big = 1 if a1 - a0 > 180 else 0
            arcs.append(
                f'<path class="{cls}" d="M{cx} {cy} L{x0:.2f} {y0:.2f} '
                f'A{r} {r} 0 {big} 1 {x1:.2f} {y1:.2f} Z">'
                f'<title>{esc(lab)}: {v:,} of {total:,}</title></path>')
            a0 = a1
        legend = "".join(
            f'<span class="key"><i class="{cls}"></i>{esc(lab)} '
            f'<b>{v:,}</b> <span class="q">{100 * v / total:.0f}%</span></span>'
            for lab, v, cls in slices)
        return (f'<figure class="chart pie"><figcaption>{esc(title)}</figcaption>'
                f'<div class="piebody">'
                f'<svg viewBox="0 0 140 148" role="img" aria-label="{esc(title)}">'
                + "".join(arcs) +
                f'</svg><p class="legend">{legend}</p></div>'
                f'<p class="help">{esc(note)}</p></figure>')

    def hbars(items, title, note, unit=""):
        """Horizontal bars for few items with real names.

        `items` is [(label, value, hover)] largest-first; the vertical
        helper's x-axis labels cannot hold a project name, and rotating
        them was rejected the last time it came up. Values render at
        the bar end so the chart reads without the axis."""
        if not items:
            return ""
        # Full-width canvas. The label gutter is measured from the
        # longest label rather than guessed — a fixed 190px clipped
        # "HASPIELAW 200MW BATTERY STORAG" against the viewBox edge,
        # and SVG has no overflow to save it. ~6.6px per character at
        # this size, floored so short-label charts keep their bars long.
        w, rh, pad_r = 1080, 30, 74
        pad_l = max(200, int(max(len(l) for l, _, _ in items) * 6.6) + 14)
        h = len(items) * rh + 10
        top = max(v for _, v, _ in items) or 1
        rows = []
        for i, (lab, v, hover) in enumerate(items):
            bw = (w - pad_l - pad_r) * v / top
            y = 4 + i * rh
            rows.append(
                f'<text class="xl" x="{pad_l - 8}" y="{y + rh - 10}" '
                f'text-anchor="end">{esc(lab)}</text>'
                f'<rect x="{pad_l}" y="{y}" width="{bw:.1f}" height="{rh - 8}">'
                f'<title>{esc(hover)}: £{v:,.0f}{esc(unit)}</title></rect>'
                f'<text class="xl" x="{pad_l + bw + 6:.1f}" y="{y + rh - 10}">'
                f'&pound;{v:,.0f}{esc(unit)}</text>')
        return (f'<figure class="chart chart-wide">'
                f'<figcaption>{esc(title)}</figcaption>'
                f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
                + "".join(rows)
                + f'</svg><p class="help">{esc(note)}</p></figure>')

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
    # The same bands, but the estimated figures are no longer missing
    # from the picture — they are stacked on top of the stated ones and
    # named, so the shape of the corpus is visible without the weakest
    # class of figure being mistaken for a disclosure (Luke, 2026-08-25).
    band_split = {b[0]: {"stated": 0, "operator": 0, "estimated": 0}
                  for b in BANDS}
    for row in capacity_shape:
        v = row["mw"]
        if not v:
            continue
        for lab, lo, hi in BANDS:
            if lo <= v < hi:
                band_split[lab][row["prov"]] += 1
                break
    _n_stated = sum(b["stated"] for b in band_split.values())
    _n_oper = sum(b["operator"] for b in band_split.values())
    _n_est = sum(b["estimated"] for b in band_split.values())
    chart_bands = stacked_bars(
        [(b[0], band_split[b[0]]) for b in BANDS],
        "Sites by capacity (MW)",
        f"Sites whose documents are unread, or which disclose nothing and cannot be "
        f"estimated, are absent — not zero. “From the site's documents” covers a "
        f"stated load, a grid connection or standby plant sized to the load — the pie "
        f"beside this separates those. An estimate is this project's arithmetic on "
        f"a floor area, never a figure anybody published, and it is the weakest class in "
        f"the release: usable as a sense of scale, never as a quoted number. A third "
        f"part names the {_n_oper} sites ranked on a figure their operator publishes "
        f"about its own campus, which is neither of those things — a first-party "
        f"statement to customers rather than to the planning authority. Partly-read "
        f"sites can move up a band as reading continues.",
        [("stated", "From the site's documents", "s-stated"),
         ("operator", "Operator-stated campus figure", "s-operator"),
         ("estimated", "Estimated from floorspace", "s-est")])

    # The same population as the bands, split by provenance instead of
    # scale. Grid connection and standby capacity render in the Power MW
    # column in the estimated style, so hiding them inside “stated” here
    # both overstated disclosure and contradicted the column (issue
    # #151, Luke's call on 2026-08-27: refine the pie, leave the stack
    # two-way).
    _n_it = power_basis_counts.get("Disclosed IT load", 0)
    _n_tot = power_basis_counts.get("Disclosed total site demand", 0)
    _n_grid = power_basis_counts.get("Grid connection capacity", 0)
    _n_standby = power_basis_counts.get("Standby generation capacity", 0)
    _n_operator_basis = power_basis_counts.get(scale.OPERATOR_BASIS, 0)
    chart_basis = pie(
        [("Stated as the site's own load", _n_it + _n_tot, "s-stated"),
         ("Grid connection capacity", _n_grid, "s-grid"),
         ("Standby generation capacity", _n_standby, "s-standby"),
         ("Operator-stated campus figure", _n_operator_basis, "s-operator"),
         ("Estimated from floorspace", _n_est, "s-est")],
        "Where a site's own figure comes from",
        f"The {_n_stated + _n_oper + _n_est} sites carrying any capacity figure — the "
        f"same sites the chart above bands by size, split here by what each figure "
        f"rests on. A stated load is the applicant's own number; a grid connection is "
        f"headroom rather than consumption; standby capacity is inferred from plant "
        f"sized to carry the load; an operator-stated campus figure is published by "
        f"the operator about its own facilities and is not in the planning record at "
        f"all; a floorspace estimate is this project's arithmetic. The other "
        f"{n_sites - _n_stated - _n_oper - _n_est} sites carry none — their documents "
        f"are unread, or disclose nothing and give no floor area to work from.")

    # And of the sites whose applications say nothing, how many are
    # described by something outside the planning system.
    _silent = [r for r in capacity_shape if not r["stated"]]
    _by_tier = {t: sum(1 for r in _silent if r["claim"] == t)
                for t in ("strong", "probable", "tentative")}
    _silent_est = sum(1 for r in _silent if r["mw"])
    # ---- The Barbour hyperscalers, by value (issue #177) -------------
    # Luke: the chart works if we clearly state what we display. What we
    # display: projects where Barbour records a value AND the promoter's
    # own title claims 100 MW or more. Both numbers are the promoter's
    # world — the title MW is the figure the dictionary already warns is
    # never copied into the Power MW column, and the value is Barbour's
    # project estimate. A floor, not a census: most valued projects
    # state no MW at all, and the note prints the split.
    _hyp_mw_re = re.compile(r"(\d+(?:\.\d+)?)\s*MW", re.I)
    with db.connect() as _bconn, _bconn.cursor() as _bcur:
        _bcur.execute("SELECT title, value_gbp FROM projects "
                      "WHERE value_gbp IS NOT NULL")
        _valued = _bcur.fetchall()
    _hyp = []
    for _t, _v in _valued:
        _ms = [float(m) for m in _hyp_mw_re.findall(_t or "")]
        if _ms and max(_ms) >= 100:
            _hyp.append((_t, float(_v), max(_ms)))
    _hyp.sort(key=lambda r: -r[1])

    def _hyp_label(title):
        # The place name, not the whole promoter title: everything
        # before the first " - ", in Barbour's own casing — .title()
        # was tried and mangled the codes ("Sdc M40", "200Mw"), and
        # this project does not rewrite source names anyway. The full
        # title is the hover.
        head = re.split(r"\s+-\s+", title or "")[0].strip()
        return re.sub(r"\s+", " ", head)[:44]

    chart_barbour = hbars(
        [(_hyp_label(t), v / 1e6, f"{mw:,.0f} MW — {t}") for t, v, mw in _hyp],
        "The Barbour hyperscalers, by project value",
        f"Barbour ABI project estimates (licensed, credited): the "
        f"{len(_hyp)} projects of the {len(_valued)} carrying a value whose "
        f"own title also claims 100 MW or more. Both figures are the "
        f"promoter's — the MW is the title's claim, never copied into the "
        f"power columns, and the value is Barbour's estimate of the "
        f"project, not a disclosed cost. A floor, not a census: the other "
        f"{len(_valued) - len(_hyp)} valued projects state no MW in their "
        f"title, which does not make them small.",
        unit="m")

    chart_elsewhere = pie(
        [("Nothing from outside either",
          sum(1 for r in _silent if not r["claim"]), "s-none"),
         ("Strong external match", _by_tier["strong"], "s-strong"),
         ("Probable external match", _by_tier["probable"], "s-prob"),
         ("Tentative external match", _by_tier["tentative"], "s-tent")],
        "Sites whose applications state no capacity",
        f"{len(_silent)} sites, of which {_silent_est} carry a floorspace estimate "
        f"from this project even though the application itself states nothing. An "
        f"external match is a grid-register row, a filed account or an operator's own "
        f"page that this project judged to describe the site — a different quantity, "
        f"from a different authority, and not the figure the applicant gave the "
        f"council. A tentative match is a lead to resolve, not evidence. Every match, "
        f"with its reasoning, is on the site's own page.")

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

    # ---- The scale panel (issue #166) --------------------------------
    # Replaces "The rest of the package" block: scale at a glance, every
    # figure computed here and never typed, every row linked to the
    # definition or comparison that produces it. The framing that
    # settled this panel: computed and citable beats vivid and wrong —
    # no invented equivalences, and the one comparator is Ofgem's own
    # published figure. Row indices follow the site_rows unpack above.
    # float() throughout: these columns arrive as Decimal, and
    # Decimal / 1e9 is a TypeError rather than a number.
    _sp_grid = [float(r[14]) for r in site_rows if r[14]]
    _sp_gen = [float(r[15]) for r in site_rows if r[15]]
    _sp_bval = [float(r[25]) for r in site_rows if r[25]]
    _sp_gc, _sp_diesel, _sp_gas = [], 0, 0
    for r in site_rows:
        _prof = profiles.get(r[0], {})
        if _prof.get("generator_count"):
            _sp_gc.append(_prof["generator_count"])
        _fuels = _prof.get("generator_fuels") or ()
        _sp_diesel += "Diesel" in _fuels
        _sp_gas += "Gas" in _fuels

    def _sp_pow(mw: float) -> str:
        return (f"{mw/1000:,.1f} GW" if mw >= 1000 else f"{mw:,.0f} MW")

    def _sp_link(view, anchor_id, label):
        return (f'<a href="#{anchor_id}" onclick="goView(\'{view}\','
                f'\'{anchor_id}\');return false">{label}</a>')

    _q_link = _sp_link("method", "meth-queue",
                       "the banded comparison with Ofgem&rsquo;s queue")
    scale_panel = f"""
  <div class="card card-ink">
   <h2 class="sideh">The scale of what the documents disclose</h2>
   <p class="cnote">Sums over the minority of sites whose documents state a figure.
    Every number below is computed from the corpus when this page is built, is a floor
    from an incomplete read, and is a measure of what is disclosed — not of what exists.</p>
   <div class="crow"><span>Disclosed capacity</span><b>{_sp_pow(sum(site_mw_values))}</b></div>
   <p class="cnote">Summed over the {len(site_mw_values)} sites stating one, of {n_sites}.
    Ofgem&rsquo;s Curate consultation (para 2.8) puts &asymp;{extagg.OFGEM_QUEUE_TOTALS[1]/1000:,.0f}&nbsp;GW
    of data-centre demand in the GB connection queue across &asymp;{extagg.OFGEM_QUEUE_TOTALS[0]}
    projects &mdash; {_q_link}.</p>
   <div class="crow"><span>Contracted grid connections</span><b>{_sp_pow(sum(_sp_grid))}</b></div>
   <p class="cnote">Summed over {len(_sp_grid)} sites with an adjudicated connection figure.
    A connection is an offer to draw, not consumption &mdash;
    {_sp_link("dict", dict_ids[("Sites", "IT load / Total site / Grid connection / On-site generation MW")], "what each power column means")}.</p>
   <div class="crow"><span>On-site generation disclosed</span><b>{_sp_pow(sum(_sp_gen))}</b></div>
   <p class="cnote">Summed over {len(_sp_gen)} sites disclosing a generation figure &mdash;
    {_sp_link("dict", dict_ids[("Sites", "On-site generation figure basis")], "what counts as one")}.</p>
   <div class="crow"><span>Standby generators</span><b>at least {sum(_sp_gc):,}</b></div>
   <p class="cnote">Summed over the {len(_sp_gc)} sites whose documents state a count
    ({_sp_diesel} sites name diesel, {_sp_gas} gas). Floors: the highest count in any one
    document per site, phases never added &mdash;
    {_sp_link("dict", dict_ids[("Sites", "Standby generators (count)")], "how these are counted")}.</p>
   <div class="crow"><span>Barbour ABI project value</span><b>&pound;{sum(_sp_bval)/1e9:,.1f}bn</b></div>
   <p class="cnote">Summed over the {len(_sp_bval)} sites whose Barbour ABI record prices the
    project (licensed data, credited) &mdash;
    {_sp_link("dict", dict_ids[("Sites", "Barbour columns")], "what the Barbour columns are")}.</p>
  </div>"""
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
        op_rows = odis.load_rows(_cur, drive_docs)
        op_divs = odis.load_divergences(_cur, drive_docs)
    # The renewable claim beside the combustion the sites disclose
    # (Luke, 2026-08-28). Built from a curated claims file, never
    # inferred from a keyword: the direction of a mention decides its
    # meaning, and Apatura's diesel passages argue for eliminating
    # diesel. dcp/green_claims.py carries the reasoning.
    from dcp import green_claims as _gc
    with db.connect() as _gconn:
        _green_rows = _gc.build_rows(_gconn, profiles)
    _AUD = [(k, lbl) for k, lbl, _ in odis.AUDIENCES]

    def _aud_cell(row, key):
        got = row.by_audience.get(key) or []
        if not got:
            return '<td class="none"><span class="q">no figure</span></td>'
        return (f'<td class="yes">{len(got)}'
                f'<span class="q">figure{"" if len(got) == 1 else "s"}</span></td>')

    def _site_a(key, name, n=52):
        """A site name that opens the site.

        href *and* onclick: the href is what a right-click copies and
        what still works if scripting is off, the onclick does the work
        without a round trip through hashchange — which would not fire
        at all if the reader is already on that site's hash.

        `n=None` sets the name in full. Truncation earns its place in a
        narrow column and nowhere else: in a column with room to spare
        it only makes two long, similar site names look identical
        (Luke, 2026-08-28).
        """
        def _lab(t):
            return esc(t if n is None else trim(t, n))
        if not key:
            return _lab(name or "—")
        return (f'<a href="#site-{quote(key, safe="")}" '
                f'onclick="return goSite(\'{esc(key)}\')">'
                f'{_lab(name or key)}</a>')

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
            # Only the external claims: a planning row's own copy is the
            # document link above, already resolved by Drive file id.
            if _copy := our_copy(c):
                bits.append(_copy)
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

    def _lfl_group(d, q):
        """One table row per figure, the site and ratio spanning them.

        The figure and its provenance used to share a cell, as a stack
        of divs — a column by eye only. Nothing held "340 MW" level with
        the NESO row it came from once a provenance line wrapped, and
        the audience, which is the whole point of this comparison, was
        buried mid-sentence. Real cells make that alignment the table's
        job rather than the reader's (Luke, 2026-08-28).

        The site, quantity and ratio are one value per group, so they
        use rowspan rather than repeating: a ratio printed against each
        of the figures it was computed from would read as a property of
        the figure.
        """
        vals = q["values"]
        span = f' rowspan="{len(vals)}"' if len(vals) > 1 else ""
        qty = ccl.QUANTITY_LABELS.get(q["quantity_type"], q["quantity_type"])
        out = []
        for i, c in enumerate(vals):
            # Hairlines inside a group would make the group boundary
            # indistinguishable from the rows within it; the rowspan
            # cells only rule off at the end, so the figure cells match.
            row = "" if i == len(vals) - 1 else ' class="fig"'
            head = (f'<td{span}>{_site_a(d.get("site_key"), d["site"], None)}</td>'
                    f'<td{span}>{esc(qty)}</td>') if i == 0 else ""
            tail = (f'<td class="n"{span}>{q["ratio"]:.2f}&times;</td>'
                    if i == 0 else "")
            out.append(
                f'<tr{row}>{head}'
                f'<td class="n">{float(c["value"]):,.4g} MW</td>'
                f'<td>{esc(dict(_AUD).get(c["audience"], c["audience"]))}</td>'
                f'<td class="src">{_op_source(c)}</td>'
                f'{tail}</tr>')
        return "".join(out)

    _lfl_rows = "".join(_lfl_group(d, q) for d, q in _lfl)
    _lfl_table = (
        '<table class="stats" id="tbl-lfl">'
        '<colgroup><col class="c-site"><col class="c-qty"><col class="c-val">'
        '<col class="c-aud"><col class="c-src"><col class="c-ratio"></colgroup>'
        '<thead><tr><th scope="col">Site</th><th scope="col">Quantity</th>'
        '<th scope="col">Figure</th><th scope="col">Audience</th>'
        '<th scope="col">Where it was published</th>'
        '<th scope="col">Ratio</th></tr></thead>'
        f'<tbody>{_lfl_rows}</tbody></table>'
    ) if _lfl_rows else '<p class="help">None currently.</p>'

    # One row per claim. Every cell either carries evidence or says why
    # it does not — a blank here would read as "no generators".
    def _unknown_use(r):
        """Never a dash. A dash in this column would be read as "none",
        and we do not know that: no fuel disclosed in the documents we
        hold is a statement about our reading, not about the site
        (Luke, 2026-08-28 — the same rule as the two "none" strings the
        generation column distinguishes).
        """
        if not r.sites:
            return ('<span class="q">not established: no site of this '
                    'operator is in the corpus</span>')
        return ('<span class="q">not established: no generation described '
                'in the documents held</span>')

    def _green_row(r):
        fuels = (('<span class="fuelist">' + "".join(
                     f'<span class="f">{esc(lbl)}'
                     f'<span class="q">({n} site{"" if n == 1 else "s"})</span></span>'
                     for lbl, n in r.fuels) + '</span>')
                 if r.fuels else
                 f'<span class="q">{esc(r.generation_use)}</span>')
        units = (f"at least {r.generator_floor}"
                 if r.generator_floor else '<span class="q">no count disclosed</span>')
        permit = (f"{r.permit_mwth:,.1f} MWth<span class=\"q\">{r.permit_count} permit"
                  f"{'' if r.permit_count == 1 else 's'}, {r.permit_engines} engines</span>"
                  if r.has_permit else
                  '<span class="q">no permit found; may be under the 50 MWth '
                  'threshold at which one is required</span>')
        # The quote links to the page it was taken from, so the claim
        # can be checked at source rather than taken on trust.
        quoted = esc(r.claim.quote)
        if r.claim.source_url:
            quoted = (f'<a href="{esc(r.claim.source_url)}" rel="nofollow noopener" '
                      f'target="_blank">{quoted}</a>')
        # And our copy of the page it was taken from. A green claim
        # carries no `as_at` — it asserts the page as it reads now — so
        # it takes the newest-first arm, and its own quote still decides
        # which file the link may point at.
        _green_copy = our_copy({"locator": r.claim.snapshot,
                                "quote": r.claim.quote})
        # Every site the row is built from, reachable. Site KEYS rather
        # than names (Luke, 2026-08-28): names mix curated aliases in
        # sentence case with raw Barbour titles in capitals, which reads
        # as disorder in a narrow column, and the key is what a reporter
        # carries between the reader, the workbook and the DuckDB.
        # Truncated because an S35 stub's key runs to eighty characters
        # and would set the width of the whole table; the full key and
        # the site's name are on hover.
        def _keylink(k):
            short = k if len(k) <= 24 else k[:23] + "\u2026"
            nm = site_names.get(k) or ""
            tip = esc(k + (" \u2014 " + nm if nm else ""))
            return (f'<a href="#site-{quote(k, safe="")}" '
                    f'onclick="return goSite(&#39;{esc(k)}&#39;)" '
                    f'title="{tip}"><code>{esc(short)}</code></a>')

        if r.sites:
            sitecell = ('<span class="fuelist">' + "".join(
                f'<span class="f">{_keylink(k)}</span>' for k in r.sites)
                + '</span>')
        else:
            sitecell = '<span class="q">none in this corpus</span>'
        return (f'<tr><td>{esc(r.claim.operator)}</td>'
                f'<td><q>{quoted}</q>'
                # One muted line under the quote, not two: `.q` is a
                # block, so a separate span would put a bare "·" at the
                # start of a line of its own.
                f'<span class="q">{esc(r.claim.gloss)}'
                + (f' · {_green_copy}' if _green_copy else "")
                + '</span></td>'
                f'<td>{sitecell}</td>'
                f'<td>{fuels}</td>'
                f'<td>{esc(r.generation_use) if r.fuels else _unknown_use(r)}</td>'
                f'<td data-num="1">{units}</td>'
                f'<td data-num="1">{permit}</td></tr>')

    _green_body = "".join(_green_row(r) for r in _green_rows)

    operators_html = f"""
 <p class="lede">A datacentre's size is stated to at least five different audiences: the
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
 {_lfl_table}
 <p class="help">A ratio of 1.00× is corroboration, not coincidence: two audiences given
 the same number by the same developer, arrived at independently by this project.</p>

 <h3>Renewable-power claims, beside the generation the documents describe</h3>
 <p>Six operators in this corpus publish a claim about renewable power. Their sites'
  own planning documents describe on-site combustion. Both are shown here, in the
  operator's own words, because the wording is the finding: <em>procurement</em> is a
  statement about what is bought, <em>powered</em> about how a building runs, and a
  <em>goal</em> is neither. Each quote links to the page it was taken from, and each
  site key opens that site; hover a key for its name.</p>
 <div class="banner"><b>What this table is not.</b> It is not a list of operators caught
  out. &ldquo;100% renewable&rdquo; conventionally describes procured grid electricity, so
  an unqualified claim is not false because a site also holds standby plant &mdash; the
  question is what the claim leaves out. Two operators here, Ark and Kao Data, name their
  standby fuel beside the claim.</div>
 <table class="stats" id="tbl-green"><thead><tr>
  <th scope="col">Operator</th><th scope="col">What it claims, in its own words</th>
  <th scope="col">Its sites in this corpus</th>
  <th scope="col">On-site generation its documents describe</th>
  <th scope="col">Use</th><th scope="col">Units disclosed</th>
  <th scope="col">Permitted standby</th></tr></thead>
  <tbody>{_green_body}</tbody></table>
 <p class="help"><b>Generators existing is not generators running.</b> {esc(_gc.REGULATORY_CAVEAT)}</p>
 <p class="help"><b>A missing permit is not a clean site.</b> {esc(_gc.PERMIT_THRESHOLD_CAVEAT)}</p>
 <p class="help"><b>Counts are floors.</b> {esc(_gc.COUNT_CAVEAT)}</p>

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
   datacentre language in the application description.</li>
  <li><b>Operator watch-list</b> — searches for named developers, operators and advisers.</li>
  <li><b>Spatial sweeps</b> around known sites, which catch the substations, grid connections
   and enabling works that never mention a datacentre.</li>
  <li><b>Family links</b> — the parents and children of applications already held.</li>
  <li><b>Barbour ABI</b> project intelligence, reconciled against the planning universe in
   both directions.</li>
  <li><b>Foxglove and Global Action Plan's</b>
   <a href="https://www.foxglove.org.uk/wp-content/uploads/2025/10/2025_09_26-FINAL-Big-Tech-Data-Centres-Report-Website-Version.pdf"
   target="_blank" rel="noopener">September 2025 report</a> on large data centres in the
   English planning system, which seeded ten application families here and served as an
   independent check on this project&rsquo;s coverage — every site on their list is in this
   dataset, identified down to its planning references.</li>
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

 <h2 class="sec" id="meth-queue">What the regulator can see that these documents cannot</h2>
 <p class="m">On 29 July 2026 Ofgem published its
 <a href="{esc(_ofgem_src.url)}" target="_blank" rel="noopener">Curate consultation</a> on
 demand connections reform. Its paragraph 2.8 states that approximately 73&nbsp;GW of the GB
 demand connection queue is datacentres — around 315 projects holding contracted connection
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
 least 9&nbsp;GW of queue projects reclassified themselves from battery to datacentre
 between May 2024 and August 2025 (paragraph 2.10), so any register that classifies projects
 by declared technology undercounts datacentres — the planning-side counterpart is the
 naming-invisibility cases this corpus tracks. And NESO's voluntary
 <a href="{esc(_cfi_src.url)}" target="_blank" rel="noopener">call for input</a> on the
 demand queue found only 32% of datacentre projects had secured an off-taker, and 71 of 148
 reported financial commitment with FID evidence — NESO's own caveat: developer intent, not
 confirmed deliverability. These aggregates are deliberately not joined to the sites here:
 the sources measure different quantities, and the anonymised ones cannot be matched to a
 site without guessing. The full set, with verbatim quotes, locators and access dates, is on
 the workbook's External aggregates sheet.</p>
 <p class="m">Consumption is the measurement the queue cannot make. DESNZ's
 <a href="{esc(_desnz_src.url)}" target="_blank" rel="noopener">sub-national electricity
 statistics</a> record what large users actually drew: Half-Hourly-metered non-domestic
 consumption — the meter class datacentres belong to — published at local-authority level
 only, because below that level the source carries no half-hourly meters at all. Between
 2019 and 2024 that consumption fell {abs(_d_nat)}% nationally, while rising
 {_d_slough}% in Slough and {_d_hillingdon}% in Hillingdon — the two largest absolute rises
 of any GB local authority. The nulls are as visible as the rises: Tower Hamlets, holding
 the Docklands cluster, fell {abs(_d_towerhamlets)}%, and Hertsmere, with datacentre sites
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
 <p class="m"><b>The silences are significant.</b> An unusual
 property of this dataset is that it can show what applications <em>do not</em> say. Two examples are
 already visible: sites whose documents were read in full and state no capacity figure at
 all, and the majority of on-site generation figures that name no fuel and
 no plant type. For an investigation that began by asking whether operators disclose
 generation contradicting their public renewable positioning, "most of them do not say what
 it burns" is a finding about disclosure itself, and it is measurable here rather than
 anecdotal.</p>
 <p class="m"><b>Figures that stop just under 50 MW.</b> Above 50 MW a generating station
 in England needs consent from the Secretary of State rather than the local council, and
 855 findings across 51 sites state a bound just under it — "generation totalling less
 than 50 MW", "capped at 50 MW", "49.9". That is a behaviour, not noise: a ceiling stated
 that precisely is a routing decision about which consent regime applies. A ceiling is
 also not a load — the like-for-like comparisons here exclude these figures for that
 reason — so where one appears, the question is what the site actually intends to
 install, and that answer is usually elsewhere in its documents.</p>
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
 <p class="m"><b>Energy parks with a datacentre attached.</b> Several records pair a data
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
  <li><b>An external megawatt and a planning megawatt rarely measure the same thing.</b> A
   company's accounts, a market report and a planning statement can each state a capacity
   for one scheme and all be right: one site's environmental statement gives 103.32 MW of
   IT load and 139.5 MW of total load in a single table, beside a 140 MW reserved grid
   connection. A gap between two sources is only a finding after establishing that they
   measure the same quantity — here that took one table and dissolved what looked like a
   36 MW discrepancy.</li>
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
   distinction an ownership story turns on. Since these notes were first written the route
   has been tested and it pays twice over: a single-asset SPV's audited accounts state what
   its property valuation assumes — for one scheme here, "successful delivery of a
   103.3 MW hyperscale data centre", a capacity an external valuer priced and an auditor
   signed — and the charges register records who lends against the scheme, which the PSC
   register is structurally unable to show. The External claims panel on a site's page
   carries what has been loaded so far.</li>
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


    about_numbers = f"""<details class="banner banner-d"><summary>About these numbers</summary>
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
 <p class="m"><b>Read twice: under way, not complete.</b> Every document here has been read
 once. A second reading, by a different model against the same pages, is what would turn
 "no capacity disclosed" from an absence of evidence into evidence of absence. That pass
 has started and its findings feed this release where it has reached, but it is not
 complete and the corpus-wide comparison — where two readings disagree, the disagreement
 is the finding — has not been produced. Where this release says a site discloses
 nothing, that remains the weaker claim.</p></div></details>"""

    out = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>UK datacentre plans v2, phase {args.phase} release</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- The gate is there to stop the link being passed around, so the page
     should not turn up in a search either. -->
<meta name="robots" content="noindex, nofollow, noarchive">
<!-- The handoff's three families, requested the way its own prototype
     does. Source Serif is asked for at 400 and in italic as well as at
     600/700, because verbatim quotes are set in serif italic and a
     synthesised oblique of a bold weight is not that. `display=swap` so
     a slow font never blanks the page, and the fallbacks in every stack
     are real faces rather than `serif`/`sans-serif`. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&display=swap">
<style>{CSS}</style></head><body>
<header class="masthead"><div class="mhead">
 <h1>UK datacentre plans</h1>
 <!-- Sites and applications only: the document and verified-findings
      counts live in the coverage panel, where they sit beside what they
      mean (issue #147). -->
 <div class="sub">v2, phase {args.phase} · {n_sites} sites ·
 {len(app_rows):,} applications ·
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

<!-- One filter bar, above both the table and the map. Not two bars kept
     in step: the map used to carry its own search box, its own 100 MW
     toggle and its own cohort select, and a handover copied the Sites
     tab's state into them — which is a synchronisation, and every one of
     those has drifted at least once. The map now shows the set the table
     shows because it is told by the same code, from the same controls
     (Luke, 2026-08-25). -->
<span id="filterbar-home" hidden></span>
<div id="filterbar" hidden>
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
 <select id="sc">
  <option value="">Any kind of site</option>
  {''.join(f'<option value="{esc(k)}">{esc(sclass.CLASS_FILTER_LABELS[k])}'
           f' ({rendered_classes[k]:,})</option>'
           for k in sclass.CLASS_ORDER if rendered_classes[k])}
 </select>
 <select id="o"><option value="">Any origin</option>
  {''.join(f'<option value="{esc(o)}">{esc(o)}</option>' for o in origin_opts)}</select>
 <span class="count" id="n"></span>
 <button type="button" id="seemap" class="linkish">See all on map</button><!--
 label set by apply(): "all" only while nothing is filtered --><span
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
 <!-- No "All N sites" chip. Luke, 2026-08-25: once the counts answer to
      the filters above, it says what the count string on the right
      already says, and it said it wrongly whenever a filter was on. The
      clearing job it also did belongs to a Clear that appears only when
      there is something to clear — the pattern the organisation bar
      above already uses. Clicking the active chip clears it too, and
      always did. -->
 <button type="button" class="chip clearchip" id="clearcohort" hidden
  onclick="setCohort('')">Clear</button>
 {cohort_chips}
 <span class="help">Each chip is a named rule over the adjudicated figures, with its
  definition and limits on the <a href="#signals" onclick="show('signals');return false">Signals</a>
  tab. The count is the number of sites the chip would leave <em>from what is on
  screen now</em>, so it falls as the filters above narrow the set; the cohort's
  own size is the one on the Signals tab. The table and the map show the same
  filtered set — these controls belong to both.</span>
</div>
</div>

<section id="view-start" class="view on"><div class="wrap wide">
 <p class="lede">Every planning application we can find for a UK datacentre or its
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
  <h2 class="cardh">Two ways in</h2>
  <div class="twoways">
   <div class="way way-signals">
    <div class="waylab">Signals</div>
    <p>Named queries over the adjudicated findings — cohorts of sites that share a
     measurable property. Each one shows its own definition and the script that produces
     it. No model chooses what appears, and no cohort is a conclusion.</p>
    <!-- secondary like its neighbour: the filled style read as "the
         default way in" and kept steering frequent users to Signals,
         when the meat of the reader is the Sites table (issue #148). -->
    <button type="button" class="cta secondary" onclick="show('signals')">Open the signal list</button>
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




 <!-- In the reading column, not below the grid. With the pitfalls card
      moved to the foot of the page the left column held one card against
      a 900px sidebar, which left 600px of nothing between them and the
      section underneath. The charts fill the column they belong to. -->
 <h2 class="sec">The shape of it</h2>
 <p class="help">The first chart counts applications and does not depend on the reading;
 it moves only as the tail of applications is retrieved. The three capacity charts do depend
 on it, and every figure in them is a floor — further reading can raise a site's capacity,
 and can move a site into a chart it is not in yet, but cannot do the reverse.</p>
 <div class="charts">{chart_years}{chart_bands}{chart_basis}{chart_elsewhere}{chart_barbour}</div>
 </div>

 <aside class="startside">
  <div class="card card-brand">
   <h2 class="sideh">Coverage, stated as a boundary</h2>
   <!-- The scope row. It was a strip of five stat tiles above the fold,
        four of whose numbers this card or the masthead already carried
        (Luke, 2026-08-25: "almost redundant"). What only the tiles had
        was the size of the corpus itself, so that is what moved. -->
   <div class="crow"><span>Sites</span><b>{n_sites}</b></div>
   <p class="cnote">Assembled from {n_apps_total:,} planning applications and
    {len(nsip)} national energy projects, each reachable from its own tab.</p>
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
   {about_numbers}
  </div>
{scale_panel}
 </aside>
 </div>

 <h2 class="sec" id="package">What the package contains</h2>
 <div class="parts">
  <div class="part"><p class="kind">this web portal</p>
   <h3><a href="#sites" onclick="show('sites');return false">Sites</a>,
    <a href="#apps" onclick="show('apps');return false">Applications</a>,
    <a href="#energy" onclick="show('energy');return false">Energy projects</a>,
    <a href="#map" onclick="show('map');return false">Map</a></h3>
   <p class="what">Each site expands to its full proposal text, power breakdown, generation
    and cooling evidence, who is behind it, its planning applications with links to the
    council's own register, and what the documents were found to say.</p>
   <p class="when"><b>Reach for it when</b> you want to read a site and follow it outward.</p></div>
  <div class="part"><p class="kind">this web portal</p>
   <h3><a href="#notes" onclick="show('notes');return false">Assistant's
    notes</a></h3>
   <p class="what">A record of what this data looks like from the inside, written by the AI
    assistant that built the pipeline: which silences look significant, where
    the figures can mislead, what to check before publishing, and where to look next.
    <b>Nothing in it is a finding</b> — every claim points at a site, a column or a document
    you can open, and anything that cannot be traced that way is an opinion to discard.</p>
   <p class="when"><b>Reach for it when</b> you want the failure modes before the numbers —
    or a shortlist of what to pull on first.</p></div>
  <div class="part"><p class="kind">this web portal</p>
   <h3><a href="#method" onclick="show('method');return false">Methodology</a>
    · <a href="#dict" onclick="show('dict');return false">Data dictionary</a></h3>
   <p class="what">How sites were identified, how documents were retrieved and read, how
    power figures were adjudicated — and what every column in the workbook means.</p>
   <p class="when"><b>Reach for it when</b> an editor or a subject asks how a number was
    arrived at. The <b>?</b> beside any column heading jumps straight to its definition.</p></div>
  <div class="part"><p class="kind">spreadsheet</p>
   <h3>Workbook</h3>
   <p class="what">The same rows with all {len(hv.SITE_HEADERS)} columns, filterable and
    pivotable, with a provenance sheet — and the sheets behind the Operators view:
    every capacity claim, what each operator tells which audience, and the figures
    for sites told more than one thing.</p>
   <p class="when"><b>Reach for it when</b> you want to slice the data yourself.
    </p>
   <p class="golink"><a href="{WORKBOOK_SHEET_URL}" target="_blank"
    rel="noopener">Open the spreadsheet</a> <span class="help">· or the .xlsx
    <a href="{DRIVE_ROOT}" target="_blank" rel="noopener">on Drive</a></span></p></div>
  <div class="part"><p class="kind">Drive</p>
   <h3>Source documents</h3>
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
    </p>
   <p class="golink"><a href="{SITES_URL}" target="_blank" rel="noopener">Open the site
    folders</a></p></div>
  <div class="part"><p class="kind">Gemini Notebook</p>
   <h3>Interrogate planning summaries on Notebook</h3>
   <p class="what">The report and full findings table of every site this reader classes
    as a datacentre — {rendered_classes[sclass.DATACENTRE]:,} of the
    {sum(rendered_classes.values()):,} rows in its sites list — one document per site,
    loaded into a notebook you can question in plain language — "which sites mention gas
    turbines?", "who is the agent on the Slough applications?". It answers from these
    documents and cites the site it drew each answer from. What it holds is <b>this
    project's summaries</b> of the corpus, not the council documents themselves. The
    other classes — disguise suspects, procedural-only and adjacent-power sites, and
    schemes with no planning record — are in the site folders on Drive and in Pinpoint,
    not here: a question about one of them gets nothing back from the notebook, which
    is not the same as there being nothing.</p>
   <p class="when"><b>Reach for it when</b> the question spans sites and you would otherwise
    be opening folders one at a time. Check anything you intend to publish against the site
    row or the document itself — the notebook is a way in, not a source.
    </p>
   <p class="golink"><a href="{NOTEBOOK_URL}" target="_blank" rel="noopener">Open the notebook</a></p></div>
  <div class="part"><p class="kind">Pinpoint</p>
   <h3>Interrogate all planning documents on Pinpoint</h3>
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
    </p>
   <p class="golink"><a href="{PINPOINT_URL}" target="_blank" rel="noopener">Open the
    collection</a></p></div>
  <div class="part"><p class="kind">Giant</p>
   <h3>Search the documents on Giant</h3>
   <p class="what">The same document set as the Pinpoint collection above — the planning
    applications, the findings — in the Guardian&#x27;s secure document platform,
    ingested as <code>uk-datacentres</code>.</p>
   <p class="when"><b>Reach for it when</b> you want pure text search across the set
    with results that show the context and take you directly to the matching
    passage.</p>
   <p class="golink"><a
    href="https://giant.pfi.gutools.co.uk/search?filters.ingestion[]=uk-datacentres"
    target="_blank" rel="noopener">Search the collection</a></p></div>
  <div class="part"><p class="kind">DuckDB</p>
   <h3>Query database</h3>
   <p class="what">Every site, application, document and finding in one file
    (<code>dc_phase{args.phase}.duckdb</code>, ~106 MB). Opens in DuckDB CLI, Python, R or
    the DuckDB web shell.</p>
   <p class="when"><b>Reach for it when</b> the question is not in a column.
    </p>
   <p class="golink"><a href="{DRIVE_ROOT}" target="_blank" rel="noopener">Open it on Drive</a></p></div>
 </div>

 <div class="startcol">
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
      <td class="help">Broken down beneath it — most of it is finished work,
       not a gap.</td></tr>
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
 that were retrieved, reviewed and judged not to be datacentres. They stay in the corpus —
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
 <!-- Luke, 2026-08-25: both blocks are cautionary, so they read as one
      warning rather than two, at the end where a reader has seen what
      the numbers are before being told how they mislead. -->
 {_pitfalls_from_notes(assistant_notes_html)}
 </div>
</div></section>

<section id="view-signals" class="view"><div class="wrap wide">{signals_html}</div></section>

<section id="view-site" class="view">
<div class="sitepage">
 <p class="sitenav"><a href="#sites" onclick="return backToSites()">← Back to the sites
  table</a> <span class="help">Filters, chips and sort are as you left them.</span>
  <span class="siteseq"><button type="button" id="siteprev" class="seqbtn"
   onclick="return siteStep(-1)" title="Previous site in the filtered table">←
   Previous</button><span id="siteseqn" class="help"></span><button type="button"
   id="sitenext" class="seqbtn" onclick="return siteStep(1)"
   title="Next site in the filtered table">Next →</button></span></p>
 <div id="sitehost"></div>
</div>
</section>

<section id="view-sites" class="view">
<table id="tbl-sites"><thead><tr>
 <th>{dl("Sites","Site name","Site")}</th>
 <th>{dl("Sites","End user (Barbour); Applicant of record (Barbour); "
          "Advisers (Barbour)","Who's behind it")}</th>
 <th data-num="1">{dl("Signals","Cohort","Signals it matches")}</th>
 <th data-num="1">{dl("Sites","Power MW (best available)","Power MW")}</th>
 <th data-num="1">{dl("Sites","External power indicators",
                       "External power indicators")}</th>
 <th data-num="1">{dl("Sites","Documents held / Documents analysed",
                      "Reading, and its floor")}</th>
</tr></thead><tbody>{''.join(body)}</tbody></table>
<!-- The handoff's footnote, kept although the view it distinguished is
     gone: with one table it is no longer "neither view drops a row" but
     the load-bearing half — that nothing is filtered out for being
     empty — is still what a reader needs told. -->
<p class="tablenote">No row is dropped for being empty. A site with no figure
 appears with the reason it has none, and a site whose documents have not been
 read appears as unread rather than as zero. Capacity status and coordinates are
 on each site's own page.</p>
</section>

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
 nearest datacentre site first. Metadata only — no project documents fetched.</span></div>
<table id="tbl-energy"><thead><tr><th>Project</th>
 <th>{dl("Energy projects","All columns","Stated capacity")}</th><th>Type</th>
 <th>Stage</th><th>Applicant</th><th>Region</th><th data-num="1">Nearest site</th>
 <th>Source</th><th>Description</th></tr></thead>
<tbody>{''.join(h for _, h in energyrows)}</tbody></table></section>

<section id="view-map" class="view">
<div id="mapwrap">
 <aside id="mapside">
  <!-- Layers, not filters. Energy projects are not in the sites table
       and no filter above applies to them, so which layers are drawn is
       the one question this map answers on its own. -->
  <div class="mgroup">
   <label class="chk"><input type="checkbox" id="ms" checked> Data-centre sites</label>
   <label class="chk"><input type="checkbox" id="me" checked> Energy projects</label>
  </div>
  <button type="button" id="mreset" class="toggle">Fit the map to these sites</button>
  <p class="count" id="mapcount"></p>
  <div id="mapkey">
   <div><span class="pin s"></span> datacentre site</div>
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
  <div id="mapinfo" class="mapoverlay" hidden></div>
  <div id="mapzoom" class="mapoverlay"><button id="mzin" title="Zoom in">+</button>
   <button id="mzout" title="Zoom out">−</button></div>
 </div>
</div>
</section>

<section id="view-operators" class="view"><div class="wrap tables">{operators_html}</div></section>

<section id="view-method" class="view"><div class="wrap">{methodology_html}</div></section>

<section id="view-notes" class="view"><div class="wrap">{assistant_notes_html}</div></section>

<section id="view-dict" class="view"><div class="wrap">
 <p class="lede">What every column contains and how it was derived. The same definitions
 appear on the workbook's Read me sheet, so a column cannot mean one thing there and
 another here.</p>
 {''.join(dict_html)}
</div></section>

<footer>This
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
    if n_demoted or n_not_findings:
        print(f"  Label audit: {n_demoted:,} rendered findings moved to the "
              f"family the audit says fits, each marked with where it was "
              f"filed; {n_not_findings:,} withheld as not findings at all "
              f"(still in the database, the CSVs and the workbook); "
              f"{n_unsupported:,} verdicts ignored because their citation "
              f"is not in the finding's text")
    else:
        print("  Label audit: no verdicts stored, so nothing moved")
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
    print(f"  Our copy on Drive: {len(drive_docs):,} documents have a "
          f"recorded Drive file id" +
          (f"; {n_no_drive:,} cited documents have none and fall back to "
           f"the register — run scripts/record_drive_ids.py"
           if n_no_drive else ", covering every cited document"))
    if claims_rows_rendered != _claims_live:
        _missing = sorted(set(claims_by_site) -
                          {r[0] for r in site_rows})
        print(f"  Capacity claims: NOT RENDERED — matched sites absent "
              f"from the site rows: {_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
