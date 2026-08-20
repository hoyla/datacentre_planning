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
}


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
    return out


def snapshot(slug: str, url: str) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", errors="replace")
    body = "\n\n".join([
        f"# url: {url}",
        f"# fetched: {dt.datetime.now(dt.UTC).date().isoformat()}",
        f"# sha256(html): {hashlib.sha256(raw.encode()).hexdigest()}",
        "## STRUCTURED",
        "\n\n".join(structured(raw)) or "(none)",
        "## VISIBLE TEXT",
        visible_text(raw),
    ])
    dest = OUT / f"{slug}.txt"
    dest.write_text(body)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one operator key from PAGES")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    keys = [args.only] if args.only else list(PAGES)
    for k in keys:
        for slug, url in PAGES[k]:
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
