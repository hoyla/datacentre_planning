"""Snapshot operator location pages: visible text plus any structured data.

Operators publish capacity on their own websites, and those pages change
without notice — a figure quoted in a published story has to be
recoverable a year later. Each page is reduced to the two things a claim
can be checked against (its visible text, and any JSON-LD or embedded
JSON carrying figures) and written under
data/external_sources/operator_snapshots/, with the fetch date and the
sha256 of the bytes that produced it.

**The store is append-only.** Until 2026-09-01 this wrote one file per
slug and overwrote it, while `capacity_claims` kept every reading of a
claim — so a superseded reading pointed at a file that no longer
contained its quote (CyrusOne LON1, 8.72 MW then 9 MW eight days later;
the 8.72 evidence survived only in git). Each fetch that changes
anything now writes `<slug>.<YYYY-MM-DD>.txt` beside its predecessors,
and an unchanged re-fetch writes nothing at all — the sha256 in the
newest held file is compared with the bytes just served, so re-running
the sweep is a byte-level no-op (principle 5) rather than 81 files with
a new date on them. `dcp.capacity_claims.snapshot_path` is the one
resolver every reader goes through; nothing else knows the naming.

Deliberately not a scraper of every page an operator has: the URL list is
curated, one page per named site, because the claims file is curated too
and an unreviewed page would produce an unreviewed claim.

Some pages render capacity only through JavaScript counters that read "0"
in the raw HTML (Ark's Webflow counters, Kao's Elementor blocks); their
real values sit in attributes, which is why those are captured too.

**A page a bot block will not serve is harvested in a browser.**
`--from-file` stores raw bytes captured elsewhere through exactly the
code a direct fetch uses, so the format cannot fork; `# obtained:`
records which route the file came by. Two rules travel with it. The
bytes must be what the server *sent* — never a browser's rendered text,
because content inside a collapsed `<details>` accordion is in the DOM
and not in `innerText`, and capturing that way produced a wrong
"published nowhere" finding about Iron Mountain on 2026-09-01. And the
URL comes from `PAGES` rather than the command line, so a snapshot
always names a page this project curated. Route and rules:
docs/PORTAL_NOTES.md.

**A PDF is a page here too.** Operators publish their per-facility
figures in spec sheets as often as in HTML, and until 2026-08-31 this
fetcher decoded every response as text and so could not hold one —
which left VIRTUS's Saunderton roster, the only self-auditing campus
arithmetic in the survey, uncitable. Responses are now sniffed for the
PDF magic bytes rather than trusted by URL suffix (the corpus's own
lesson: extensions lie), and their text is extracted with pypdf. The
extraction is deterministic and non-generative for the same reason the
OCR substrate is: this text is what the verbatim-quote gate checks a
claim against, so it must fail visibly rather than fluently.

Usage:
    scripts/fetch_operator_snapshots.py            # refresh all
    scripts/fetch_operator_snapshots.py --only ark
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dcp.capacity_claims import snapshot_path

OUT = ROOT / "data" / "external_sources" / "operator_snapshots"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# One entry per named site. Slug is the snapshot filename and the key the
# claims file refers to.
PAGES: dict[str, list[tuple[str, str]]] = {
    "ark": [
        ("ark-cody-park", "https://www.ark-d-c.com/locations/cody-park"),
        ("ark-spring-park", "https://www.ark-d-c.com/locations/spring-park"),
        ("ark-union-park", "https://www.ark-d-c.com/locations/union-park"),
        ("ark-longcross-park", "https://www.ark-d-c.com/locations/longcross-park"),
        ("ark-alliance-park", "https://www.ark-d-c.com/locations/alliance-park"),
        ("ark-meridian-park", "https://www.ark-d-c.com/locations/meridian-park"),
        ("ark-elstree", "https://www.ark-d-c.com/locations/elstree"),
    ],
    "greystoke": [
        ("greystoke-data-centres", "https://greystoke.co.uk/data-centres"),
        ("greystoke-home", "https://greystoke.co.uk/"),
        ("greystoke-ai-growth-zone", "https://greystoke.co.uk/ai-growth-zone"),
    ],
    "virtus": [
        ("virtus-saunderton", "https://virtusdatacentres.com/locations/uk/london/saunderton-campus"),
        # The campus page's own spec sheet, and the only place VIRTUS
        # publishes Saunderton's four facilities with a megawatt each.
        # Its path carries the publication date and a version marker,
        # which an HTML page does not give: .../2026/04/15/...-v2.pdf.
        ("virtus-saunderton-spec-sheet",
         "https://virtusdatacentres.com/media/attachments/2026/04/15/"
         "virtus_spec_sheet_saunderton-campus-v2.pdf"),
        ("virtus-slough-campus", "https://virtusdatacentres.com/locations/uk/london/slough-campus"),
        ("virtus-slough-london10", "https://virtusdatacentres.com/locations/uk/london/slough-london10"),
        ("virtus-stockley-park", "https://virtusdatacentres.com/locations/uk/london/stockley-park-campus"),
        ("virtus-hayes", "https://virtusdatacentres.com/locations/uk/london/hayes-campus"),
        ("virtus-enfield", "https://virtusdatacentres.com/locations/uk/london/enfield-campus"),
    ],
    "kao": [
        ("kao-harlow", "https://kaodata.com/locations/harlow/"),
        ("kao-slough", "https://kaodata.com/locations/slough/"),
        ("kao-northolt", "https://kaodata.com/locations/northolt/"),
        ("kao-manchester", "https://kaodata.com/locations/manchester/"),
    ],
    # The only operator publishing an IT figure and a grid figure for the
    # same site, which is the sole calibration anywhere in this survey for
    # how far the two diverge.
    "cyrusone": [
        ("cyrusone-lon1", "https://cyrusone.com/data-centers/emea/london-uk-lon1"),
        ("cyrusone-lon2", "https://cyrusone.com/data-centers/emea/london-uk-lon2"),
        ("cyrusone-lon3", "https://cyrusone.com/data-centers/emea/london-uk-lon3"),
        ("cyrusone-lon4", "https://cyrusone.com/data-centers/emea/london-uk-lon4"),
        ("cyrusone-lon5", "https://cyrusone.com/data-centers/emea/london-uk-lon5"),
        ("cyrusone-lon6", "https://cyrusone.com/data-centers/emea/london-uk-lon6"),
    ],
    "colt": [
        ("colt-london-4", "https://www.coltdatacentres.net/en-GB/our-locations/data-centre-locations-europe/london-4"),
        ("colt-london-6-7-8", "https://www.coltdatacentres.net/en-GB/our-locations/data-centre-locations-europe/london-6-7-8"),
    ],
    # NTT moved its pages between 2026-08-30 and 2026-09-02: the old
    # /services/data-centers/ paths answer 200 with a "New 404" body, and
    # the two snapshots taken that day hold exactly that (which is why no
    # NTT claim existed until 2026-09-02, and why `snapshot` now refuses
    # an error page). The London overview page carries the Gyron lineage
    # ("formerly operating as Gyron") and the roster of six.
    "ntt": [
        ("ntt-london", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/london-data-centers"),
        ("ntt-london-1", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/london-1-data-center"),
        ("ntt-hemel-2", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/hemel-hempstead-2-data-center"),
        ("ntt-hemel-3", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/hemel-hempstead-3-data-center"),
        ("ntt-hemel-4", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/hemel-hempstead-4-data-center"),
        ("ntt-slough-2", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/slough-2-data-center"),
        ("ntt-slough-3", "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/emea/slough-3-data-center"),
    ],
    "vantage": [
        ("vantage-cardiff", "https://vantage-dc.com/data-center-locations/emea/cardiff-united-kingdom/"),
        ("vantage-london-i", "https://vantage-dc.com/data-center-locations/emea/london-i-united-kingdom/"),
    ],
    "puredc": [
        ("puredc-brent-cross", "https://puredc.com/london-brent-cross"),
        ("puredc-park-royal", "https://puredc.com/our-london-park-royal-site"),
    ],
    # Three facilities on one campus, and the campus page adds them up:
    # 8.7 + 27 + 25 = 60.7 against a stated 61 MW. The rarest thing in
    # this survey — an operator whose total and breakdown check each
    # other (Luke, 2026-08-28).
    # Behind Vercel Attack Challenge Mode, so every direct fetch returns
    # 429 with `x-vercel-mitigated: challenge` — the whole host, its own
    # homepage included. Held via --from-file, per this module's
    # browser-harvest note. LON-2 has no page: it 404s, and the campus
    # FAQ plus a 2021 investor-relations announcement are the only
    # places its 27 MW is published.
    "ironmountain": [
        ("ironmountain-london-campus",
         "https://www.ironmountain.com/en-gb/data-centers/locations/emea/london"),
        ("ironmountain-lon1",
         "https://www.ironmountain.com/en-gb/data-centers/locations/emea/london/lon-1"),
        ("ironmountain-lon3",
         "https://www.ironmountain.com/en-gb/data-centers/locations/emea/london/lon-3"),
    ],
    "ada": [
        ("ada-docklands", "https://adainfrastructure.com/en-US/docklands"),
    ],
    # A developer's pre-application consultation site rather than an
    # operator's location page: the figures are proposals, and the
    # claims file labels them so.
    "apatura": [
        ("apatura-westerhill", "https://consult.apatura.energy/westerhill/the-project"),
    ],
    "globalswitch": [
        ("globalswitch-london", "https://www.globalswitch.com/data-centres/london/"),
    ],
    "stellium": [
        ("stellium-1", "https://stelliumdc.com/stellium-1/"),
    ],
    # The most complete small-operator disclosure found: a "Total IT
    # power" figure for every one of its fourteen sites, in the same
    # words each time.
    "pulsant": [
        ("pulsant-sc1", "https://www.pulsant.com/colocation/sc-1"),
        ("pulsant-sc2", "https://www.pulsant.com/colocation-medway-datacentre"),
        ("pulsant-sc3", "https://www.pulsant.com/colocation-newbridge-datacentre"),
        ("pulsant-nw1", "https://www.pulsant.com/colocation-manchester-datacentre"),
        ("pulsant-yh1", "https://www.pulsant.com/colocation-rotherham-datacentre"),
        ("pulsant-ne1", "https://www.pulsant.com/colocation-newcastle-central-datacentre"),
        ("pulsant-ne2", "https://www.pulsant.com/colocation-newcastle-ne2"),
        ("pulsant-wm1", "https://www.pulsant.com/colocation-birmingham-wm1"),
        ("pulsant-se1", "https://www.pulsant.com/colocation-milton-keynes-datacentre"),
        ("pulsant-se2", "https://www.pulsant.com/colocation-maidenhead-datacentre"),
        ("pulsant-se3", "https://www.pulsant.com/colocation-reading-south-datacentre"),
        ("pulsant-se4", "https://www.pulsant.com/colocation-reading-east-datacentre"),
        ("pulsant-se5", "https://www.pulsant.com/colocation-fareham-se5"),
        ("pulsant-ln1", "https://www.pulsant.com/colocation-south-london-datacentre"),
    ],
    # Bears on an existing tentative match: our Hoddesdon site currently
    # carries two 57 MW NESO rows, and nLighten's site in the same town is
    # an order of magnitude smaller.
    "nlighten": [
        ("nlighten-london", "https://nlighten.com/en/edge-location/london/"),
    ],
    # Capacity is present but never rendered: bare integers in
    # __NEXT_DATA__ under field_utility_power_capacity. The metro page
    # carries every UK value but strips the facility they belong to, so
    # each site is fetched individually — one page, one figure, no
    # inference. Note .co.uk 301s to .com; the canonical host is used
    # here so the snapshot's URL is the one that answers.
    "digitalrealty": [
        ("digitalrealty-london", "https://www.digitalrealty.co.uk/data-centers/emea/london"),
        ("digitalrealty-lgw14", "https://www.digitalrealty.com/data-centers/emea/london/lgw14"),
        ("digitalrealty-lgw15", "https://www.digitalrealty.com/data-centers/emea/london/lgw15"),
        ("digitalrealty-lgw16", "https://www.digitalrealty.com/data-centers/emea/london/lgw16"),
        ("digitalrealty-lhr13", "https://www.digitalrealty.com/data-centers/emea/london/lhr13"),
        ("digitalrealty-lhr17", "https://www.digitalrealty.com/data-centers/emea/london/lhr17"),
        ("digitalrealty-lhr18", "https://www.digitalrealty.com/data-centers/emea/london/lhr18"),
        ("digitalrealty-lhr19", "https://www.digitalrealty.com/data-centers/emea/london/lhr19"),
        ("digitalrealty-lhr20", "https://www.digitalrealty.com/data-centers/emea/london/lhr20"),
        ("digitalrealty-lhr26", "https://www.digitalrealty.com/data-centers/emea/london/lhr26"),
        ("digitalrealty-lhr27", "https://www.digitalrealty.com/data-centers/emea/london/lhr27"),
        ("digitalrealty-lon1", "https://www.digitalrealty.com/data-centers/emea/london/lon1"),
        ("digitalrealty-lon2", "https://www.digitalrealty.com/data-centers/emea/london/lon2"),
        ("digitalrealty-lon3", "https://www.digitalrealty.com/data-centers/emea/london/lon3"),
    ],
    # The public-consultation half of the pairs in
    # data/priors/operator_pages.yaml (issue #255). These are campaign
    # sites: they usually die when the process closes, and the audiences
    # finding asserts their *silence* on power — a negative result that
    # can only rest on a held snapshot showing the probe could have seen
    # the figure. First fetched 2026-08-30, the day of the review that
    # verified them.
    "consultation": [
        ("consult-elsham-tech-park", "https://www.elshamtechpark.com/"),
        ("consult-cato-auchtertool", "https://cato.ili-energy.com/"),
        ("consult-east-havering", "https://www.easthaveringdatacentrecampus.com/"),
        ("consult-apatura-ravenscraig", "https://consult.apatura.energy/ravenscraig/the-project"),
        ("consult-apatura-freeport", "https://consult.apatura.energy/freeport"),
        ("consult-west-london-tech-park", "https://www.westlondontechpark.com/"),
        ("consult-iver-heath-data-park", "https://iverheathdatapark.com/"),
        ("consult-abbots-langley", "https://www.abbotslangleydatacentre.co.uk/"),
        ("consult-humber-tech-park", "https://www.humbertechpark.com/"),
    ],
    # Corporate and scheme pages verified on the same review that were
    # not yet in this survey.
    "scheme": [
        ("questpark-home-of-production", "https://questpark.co.uk/"),
        ("digital-reef-projects", "https://www.digital-reef.io/digital-reef-projects"),
        ("qts-cambois", "https://q.com/data-centers/cambois/"),
    ],
    # The scheme's own architect stating 600MW for Cato (review sheet
    # T1-02) — neither operator nor consultation, held for the claims
    # channel.
    "architect": [
        ("graemenicholls-cato", "https://graemenicholls.com/cato-data-centre"),
    ],
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_pdf(raw: bytes) -> bool:
    """Sniffed, never taken from the URL — extensions lie, and a PDF
    served from a path ending .html would otherwise be stored as the
    replacement characters its bytes decode to."""
    return raw[:5] == b"%PDF-"


def pdf_text(raw: bytes) -> str:
    """Page-marked text of a PDF, deterministically.

    Marked by page because a spec sheet's figures sit on a particular
    page and a claim should be checkable against it, the same reason
    the document cache records physical pages.
    """
    import io

    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(raw))
    parts = []
    for n, page in enumerate(reader.pages, 1):
        parts.append(f"[PAGE {n}]\n{(page.extract_text() or '').strip()}")
    return "\n\n".join(parts)


def visible_text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t ]+", " ", html.unescape(t)).strip()


def structured(raw: str) -> list[str]:
    """JSON-LD blocks and counter attributes — where the real numbers hide
    on pages whose visible text says 0."""
    out = []
    for block in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', raw, re.DOTALL):
        try:
            out.append(json.dumps(json.loads(block), indent=1, sort_keys=True))
        except ValueError:
            out.append(block.strip())
    counters = re.findall(
        r'(?:fb-count-target|data-to-value|data-end)="([^"]+)"', raw)
    if counters:
        out.append("COUNTER TARGETS: " + ", ".join(counters))

    # Figures carried in embedded application state and never rendered.
    # Digital Realty ships a per-site field_utility_power_capacity to the
    # browser and displays none of it. Captured as bounded fragments
    # rather than whole payloads, which run to megabytes: the snapshot has
    # to stay small enough to read and to review in a diff.
    scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", raw, re.DOTALL))
    seen, frags = set(), []
    for m in re.finditer(
            r'"[a-z_]*(?:power|capacity)[a-z_]*"\s*:\s*(?:"[^"]{0,60}"|'
            r'\[[^\]]{0,200}\]|\d+)', scripts, re.IGNORECASE):
        s = _norm(m.group(0))
        if s not in seen:
            seen.add(s)
            frags.append(s)
    if frags:
        out.append("EMBEDDED FIGURES:\n" + "\n".join(frags[:60]))
    return out


# The header the skip decision reads. Both spellings exist since PR #310,
# when a PDF became a page like any other.
_DIGEST_RE = re.compile(r"^# sha256\((?:html|pdf)\): ([0-9a-f]{64})$")


def held_digest(path: Path | None) -> str | None:
    """The sha256 a held snapshot records, or None if it records none.

    None is never equal to a fresh digest, so an unreadable or
    header-less file makes the fetcher write rather than skip: an
    unrecognised file must not be mistaken for a match.
    """
    if path is None or not path.exists():
        return None
    # Ten lines, not six: the header has grown once already, and a
    # digest that scrolls out of the window would make every re-fetch
    # look changed — a silent failure of the no-op property rather than
    # a loud one.
    for line in path.read_text(encoding="utf-8").splitlines()[:10]:
        m = _DIGEST_RE.match(line)
        if m:
            return m.group(1)
    return None


def next_name(slug: str, day: str, out: Path) -> str:
    """The filename a change fetched on `day` should be written to.

    `_2` and not `-2` for a same-day second reading, because `_` sorts
    after `.` and `-` sorts before it: with a dash the day's second
    reading would sort ahead of its first and lexicographic order would
    stop being chronological, which is the property the resolver and a
    reporter reading `ls` both rely on.
    """
    name = f"{slug}.{day}.txt"
    n = 1
    while (out / name).exists():
        n += 1
        name = f"{slug}.{day}_{n}.txt"
    return name


def render(url: str, raw_bytes: bytes, day: str, obtained: str) -> str:
    """The snapshot file's text, from the bytes an operator served.

    Separated from the fetch so a page held by a browser harvest goes
    through exactly this code rather than a second implementation of
    the format. Whoever fetched it, the file is built the same way, and
    `# obtained:` records which route it came by — the same provenance
    the document store keeps per document, and the reason it is last in
    the header: everything that reads a fixed number of header lines
    reads them from the top.
    """
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if is_pdf(raw_bytes):
        head = [f"# url: {url}",
                f"# fetched: {day}",
                f"# sha256(pdf): {digest}",
                f"# obtained: {obtained}",
                "## STRUCTURED",
                "(none — PDF)",
                "## VISIBLE TEXT",
                pdf_text(raw_bytes)]
    else:
        raw = raw_bytes.decode("utf-8", errors="replace")
        head = [f"# url: {url}",
                f"# fetched: {day}",
                f"# sha256(html): {digest}",
                f"# obtained: {obtained}",
                "## STRUCTURED",
                "\n\n".join(structured(raw)) or "(none)",
                "## VISIBLE TEXT",
                visible_text(raw)]
    return "\n\n".join(head)


def store(slug: str, url: str, raw_bytes: bytes, out: Path,
          obtained: str) -> Path | None:
    """Write a new dated snapshot, or nothing if the bytes are unchanged.

    The store is append-only, so a sweep over unchanged pages must add
    nothing rather than restate 81 files under a new date.
    """
    # The hash names what was hashed: the bytes the operator served, so
    # a re-fetch that returns a byte-identical document is visible as
    # such whichever kind it is.
    if held_digest(snapshot_path(slug, out)) == hashlib.sha256(
            raw_bytes).hexdigest():
        return None
    # One reading of the clock, so the name and the header can never
    # disagree about which day this was fetched on.
    day = dt.datetime.now(dt.UTC).date().isoformat()
    dest = out / next_name(slug, day, out)
    dest.write_text(render(url, raw_bytes, day, obtained))
    return dest


class ErrorPage(Exception):
    """The server answered 200 with a page that says the page is gone."""


# What a "not found" page says about itself, in its title or its first
# words. Deliberately narrow: a data-centre page that happens to mention
# an error code deep in its body is not an error page, and a real one
# announces itself at the top.
_ERROR_PAGE = re.compile(
    r"\b(?:404|page not found|not found|no longer available)\b", re.I)


def looks_like_error_page(raw_bytes: bytes) -> bool:
    """A soft 404: HTTP 200 carrying a not-found page.

    `urlopen` raises on a real 404, so the only way an error page reaches
    the store is a server that answers 200 with one — which NTT's did on
    2026-08-30 for two pages, and the fetcher wrote both as snapshots
    ("New 404" is the whole visible text). A claim can never quote such
    a page, but an unreviewed one sits there as evidence that the
    operator publishes nothing, which is the wrong finding. So the title
    and the first words of the visible text are checked, and a match is
    refused rather than stored.
    """
    if is_pdf(raw_bytes):
        return False
    raw = raw_bytes.decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    if title and _ERROR_PAGE.search(html.unescape(title.group(1))):
        return True
    return bool(_ERROR_PAGE.search(visible_text(raw)[:80]))


def snapshot(slug: str, url: str, out: Path = OUT) -> Path | None:
    """Fetch the page and store it. None if nothing changed.

    Raises ErrorPage rather than storing a not-found page served as 200,
    so the sweep reports it as FAILED and the previous snapshot stands.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw_bytes = r.read()
    if looks_like_error_page(raw_bytes):
        raise ErrorPage(f"{url} answered 200 with a not-found page; "
                        f"not stored")
    return store(slug, url, raw_bytes, out, "direct")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one operator key from PAGES")
    ap.add_argument("--slug", help="one page slug, to add or refresh a "
                                   "single snapshot without touching its "
                                   "neighbours")
    ap.add_argument("--from-file", type=Path,
                    help="store a page harvested in a browser instead of "
                         "fetching it. Requires --slug; the URL comes from "
                         "PAGES, so the snapshot names the page this "
                         "project curated rather than whatever was typed. "
                         "Must be the RAW bytes the server sent — never a "
                         "browser's rendered text.")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if args.from_file:
        if not args.slug:
            ap.error("--from-file needs --slug, so the URL is the curated one")
        urls = {slug: url for pages in PAGES.values() for slug, url in pages}
        if args.slug not in urls:
            ap.error(f"{args.slug} is not a registered page; add it to PAGES "
                     f"first, so a snapshot always has a curated URL behind it")
        p = store(args.slug, urls[args.slug], args.from_file.read_bytes(),
                  OUT, "browser")
        if p is None:
            print(f"  {args.slug:<34} {'unchanged':>9}")
        else:
            print(f"  {p.name:<34} {p.stat().st_size/1000:>6.1f} kB  "
                  f"{urls[args.slug]}")
        return 0

    keys = [args.only] if args.only else list(PAGES)
    for k in keys:
        for slug, url in PAGES[k]:
            if args.slug and slug != args.slug:
                continue
            try:
                p = snapshot(slug, url)
                if p is None:
                    print(f"  {slug:<34} {'unchanged':>9}     {url}")
                else:
                    print(f"  {p.name:<34} {p.stat().st_size/1000:>6.1f} kB  {url}")
            # One unreachable operator must not abort the sweep — a
            # failed page leaves its previous snapshot in place, and the
            # quote check will keep passing against it until someone
            # refreshes it successfully.
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED {slug}: {type(e).__name__} {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
