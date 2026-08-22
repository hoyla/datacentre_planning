"""Pull the Environment Agency register, then the permits it points at.

Two stages, deliberately separate. `--register` re-downloads the public
register snapshot — a daily file with no internal version, so its only
date is the date it was fetched, and replacing it changes which
candidates exist. `--documents` walks the candidates, finds each permit's
publication on gov.uk, downloads the PDFs and writes the text of every
page beside the manifest.

The PDFs land in data/raw/, which is gitignored and stays that way. What
gets committed is the manifest — each document's URL, sha256 and size —
and the extracted text, so a quote in a published story can be re-checked
from a fresh clone without re-fetching anything.

Finding the publication takes two routes because the register's own
`Document URL` column is incomplete: 35 of the 97 candidates carry one.
For the rest, gov.uk's search API answers to the bare permit number, and
recovers seven more — including Iron Mountain's Slough permit, and a
Redhill permit whose publication is titled "Digital Realty (UK) Limited"
and so identifies its operator for free.

Idempotent: a document whose sha256 already matches the manifest is not
re-downloaded, and the text is only re-extracted if the PDF changed.

Usage:
    scripts/fetch_ea_permits.py --register
    scripts/fetch_ea_permits.py --documents [--only virtus] [--limit 5]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dcp import ea_permits as ea
from dcp.extract import extract_pdf

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

CONTENT_API = "https://www.gov.uk/api/content"
SEARCH_API = "https://www.gov.uk/api/search.json"

# gov.uk is a public API with no published rate limit and a request here
# is cheap; a third of a second between them is courtesy, not throttling.
DELAY = 0.35


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return f.read()


def _json(url: str) -> dict | None:
    try:
        return json.loads(_get(url, timeout=30))
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError):
        return None


def fetch_register() -> int:
    """Re-download the register snapshot, byte for byte."""
    data = _get(ea.REGISTER_URL, timeout=120)
    if not data.startswith(b"PK\x03\x04"):
        print("The register download is not a zip — the endpoint has "
              "changed shape. Stopping rather than committing something "
              "unrecognised.", file=sys.stderr)
        return 1
    sha = hashlib.sha256(data).hexdigest()
    if ea.REGISTER_PATH.exists() and sha == ea.REGISTER_SHA256:
        print(f"Unchanged ({sha[:12]}…); nothing written.")
        return 0
    ea.REGISTER_PATH.write_bytes(data)
    print(f"Wrote {ea.REGISTER_PATH.name}, {len(data):,} bytes.\n"
          f"sha256: {sha}\n"
          f"Update ea_permits.AS_AT to {dt.date.today().isoformat()} and "
          f"REGISTER_SHA256 to the line above, then re-run --documents: "
          f"the candidate set may have moved.")
    return 0


def publication_paths(row: ea.RegisterRow) -> list[str]:
    """Every gov.uk path that might be this permit's publication, best first.

    The register's own link leads, since it is the Environment Agency's
    assertion about which publication belongs to which permit — but only
    when it points at a published page. One row in the current snapshot
    (Ark's UB3 4QQ permit) links to `/government/admin/publications/…`,
    an editing URL that serves nothing, so a link is not the same as a
    working link and both routes are tried in turn.

    Search accepts only a result whose title says the permit was issued
    and carries the permit number: an "application advertisement" is a
    different document with no schedule in it.
    """
    out = []
    if row.document_url:
        path = urllib.parse.urlparse(row.document_url).path
        if path.startswith("/government/publications/"):
            out.append(path)
    number = row.permission_number.rsplit("/", 1)[-1]
    d = _json(f"{SEARCH_API}?q={urllib.parse.quote(number)}&count=10")
    time.sleep(DELAY)
    for r in (d or {}).get("results", []):
        title = (r.get("title") or "").lower()
        link = r.get("link")
        if not link or link in out:
            continue
        if "permit issued" in title and number.lower() in title.replace("/", ""):
            out.append(link)
    return out


def attachments(path: str) -> tuple[str, list[dict]]:
    """(publication title, attachments) from gov.uk's content API.

    The API is used rather than the rendered page because it names each
    attachment and its content type, which HTML scraping would have to
    infer from a filename.
    """
    d = _json(f"{CONTENT_API}{path}")
    time.sleep(DELAY)
    if not d:
        return "", []
    out = []
    for a in (d.get("details") or {}).get("attachments", []):
        if (a.get("content_type") or "") != "application/pdf":
            continue
        out.append({
            "title": a.get("title") or "",
            "url": a.get("url") or "",
        })
    return d.get("title") or "", out


def kind_of(title: str) -> str:
    """Permit or decision document. Both are worth having — the permit
    carries Schedule 1, the decision document carries the Environment
    Agency's own account of what it permitted and why — but only the
    permit is the operative one, so the reader has to be able to tell."""
    t = title.lower()
    if "decision" in t:
        return "decision"
    if "permit" in t:
        return "permit"
    if "variation" in t:
        return "variation"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true",
                    help="Re-download the register snapshot.")
    ap.add_argument("--documents", action="store_true",
                    help="Resolve and download the candidates' permits.")
    ap.add_argument("--only", help="Substring filter on holder or operator.")
    ap.add_argument("--limit", type=int, help="Stop after N candidates.")
    args = ap.parse_args()

    if args.register:
        return fetch_register()
    if not args.documents:
        ap.error("pass --register or --documents")

    cands = ea.candidates()
    if args.only:
        q = args.only.lower()
        cands = [c for c in cands
                 if q in c.row.name.lower()
                 or q in (c.operator or "").lower()
                 or q in c.row.site_address.lower()]
    if args.limit:
        cands = cands[:args.limit]

    ea.PDF_DIR.mkdir(parents=True, exist_ok=True)
    ea.TEXT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = (json.loads(ea.MANIFEST_PATH.read_text())
                if ea.MANIFEST_PATH.exists() else {})

    resolved = downloaded = unchanged = 0
    for i, c in enumerate(cands, 1):
        row = c.row
        entry = manifest.get(row.slug) or {}
        prior_path = entry.get("publication_path")
        path, atts, title = None, [], ""
        for p_ in ([prior_path] if prior_path else publication_paths(row)):
            title, atts = attachments(p_)
            if atts:
                path = p_
                break
        if not path:
            print(f"[{i}/{len(cands)}] {row.permission_number} "
                  f"{row.name[:40]}: no publication found")
            manifest[row.slug] = {
                "permission_number": row.permission_number,
                "holder": row.name,
                "operator": c.operator,
                "kind": c.kind,
                "generators": list(c.generators),
                "site_address": row.site_address,
                "postcode": row.postcode,
                "local_authority": row.local_authority,
                "easting": row.easting, "northing": row.northing,
                "permission_date": (row.permission_date.isoformat()
                                    if row.permission_date else None),
                "activity": row.activity,
                "publication_path": None,
                "documents": [],
            }
            continue
        resolved += 1
        docs = []
        for a in atts:
            url = a["url"]
            stem = f"{row.slug}-{kind_of(a['title'] + ' ' + url)}"
            pdf = ea.PDF_DIR / f"{stem}.pdf"
            prior = next((d for d in entry.get("documents", [])
                          if d.get("url") == url), None)
            if pdf.exists() and prior and prior.get("sha256"):
                data = pdf.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                if sha == prior["sha256"]:
                    docs.append(prior)
                    unchanged += 1
                    continue
            try:
                data = _get(url, timeout=120)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                print(f"    ! {url}: {exc}")
                continue
            time.sleep(DELAY)
            pdf.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            pages = extract_pdf(pdf)
            for n, page in enumerate(pages, 1):
                (ea.TEXT_DIR / f"{stem}-p{n}.txt").write_text(page)
            docs.append({
                "title": a["title"], "url": url, "kind": kind_of(a["title"]),
                "stem": stem, "sha256": sha, "bytes": len(data),
                "pages": len(pages),
                "fetched": dt.date.today().isoformat(),
            })
            downloaded += 1
            print(f"[{i}/{len(cands)}] {row.permission_number} "
                  f"{a['title'][:46]}: {len(pages)}pp")
        manifest[row.slug] = {
            "permission_number": row.permission_number,
            "holder": row.name,
            "operator": c.operator,
            "kind": c.kind,
            "generators": list(c.generators),
            "site_address": row.site_address,
            "postcode": row.postcode,
            "local_authority": row.local_authority,
            "easting": row.easting, "northing": row.northing,
            "permission_date": (row.permission_date.isoformat()
                                if row.permission_date else None),
            "activity": row.activity,
            "publication_path": path,
            "publication_title": title,
            "documents": docs,
        }

    ea.MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with_docs = sum(1 for v in manifest.values() if v.get("documents"))
    print(f"\n{len(cands)} candidates, {resolved} with a publication, "
          f"{with_docs} with at least one document. "
          f"{downloaded} downloaded, {unchanged} already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
