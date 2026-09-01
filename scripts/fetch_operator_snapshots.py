"""Snapshot operator location pages: visible text plus any structured data.

Operators publish capacity on their own websites, and those pages change
without notice — a figure quoted in a published story has to be
recoverable a year later. Each page is reduced to the two things a claim
can be checked against (its visible text, and any JSON-LD or embedded
JSON carrying figures) and written to a dated snapshot under
data/external_sources/operator_snapshots/, with the fetch date and the
sha256 of the HTML that produced it.

Deliberately not a scraper of every page an operator has: the URL list is
curated, one page per named site, because the claims file is curated too
and an unreviewed page would produce an unreviewed claim.

Some pages render capacity only through JavaScript counters that read "0"
in the raw HTML (Ark's Webflow counters, Kao's Elementor blocks); their
real values sit in attributes, which is why those are captured too.

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
    "ntt": [
        ("ntt-london-1", "https://services.global.ntt/en-us/services/data-centers/emea/london-1-data-center"),
        ("ntt-hemel-3", "https://services.global.ntt/en-us/services/data-centers/emea/hemel-hempstead-3-data-center"),
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
    "ironmountain": [
        ("ironmountain-london-campus",
         "https://www.ironmountain.com/en-gb/data-centers/locations/emea/london"),
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


def snapshot(slug: str, url: str) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw_bytes = r.read()
    # The hash names what was hashed: the bytes the operator served, so
    # a re-fetch that returns a byte-identical document is visible as
    # such whichever kind it is.
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if is_pdf(raw_bytes):
        head = [f"# url: {url}",
                f"# fetched: {dt.datetime.now(dt.UTC).date().isoformat()}",
                f"# sha256(pdf): {digest}",
                "## STRUCTURED",
                "(none — PDF)",
                "## VISIBLE TEXT",
                pdf_text(raw_bytes)]
    else:
        raw = raw_bytes.decode("utf-8", errors="replace")
        head = [f"# url: {url}",
                f"# fetched: {dt.datetime.now(dt.UTC).date().isoformat()}",
                f"# sha256(html): {digest}",
                "## STRUCTURED",
                "\n\n".join(structured(raw)) or "(none)",
                "## VISIBLE TEXT",
                visible_text(raw)]
    dest = OUT / f"{slug}.txt"
    dest.write_text("\n\n".join(head))
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one operator key from PAGES")
    ap.add_argument("--slug", help="one page slug, to add or refresh a "
                                   "single snapshot without rewriting its "
                                   "neighbours' fetch dates")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    keys = [args.only] if args.only else list(PAGES)
    for k in keys:
        for slug, url in PAGES[k]:
            if args.slug and slug != args.slug:
                continue
            try:
                p = snapshot(slug, url)
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
