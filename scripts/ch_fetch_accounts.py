#!/usr/bin/env python3
"""Fetch filed accounts PDFs and render the pages a figure would be on.

Companies House scans what it publishes, so a filed PDF has no text
layer. Two artefacts come out of this script and they do different jobs:

  * **page images at 300 DPI**, which is what a figure is transcribed
    from — by eye, because OCR misreads a digit silently and a wrong
    digit in a capacity figure is the one error this project cannot
    absorb;
  * **OCR text of each page**, committed under
    `data/external_sources/companies_house_ocr/` for the pages a claim
    actually cites, so `dcp.capacity_claims.verify_ch_quotes` can assert
    offline that the transcribed digits are still on the page they cite.

Neither the PDF nor the images are committed unless the filing becomes a
source in `companies-house-claims.yaml`, in which case the PDF joins the
handful already there — a filed document is immutable once filed, so the
snapshot can never diverge from its source.

Usage:
    scripts/ch_fetch_accounts.py 14045228 16311501 …
    scripts/ch_fetch_accounts.py --from-filings data/raw/companies_house/filings_*.json \
        --accounts-types small full group
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from dcp import companies_house as ch

PDF_DIR = ch.RAW_DIR / "accounts"
PAGE_DIR = ch.RAW_DIR / "accounts_pages"


def render(pdf: Path, out_dir: Path, dpi: int = 300,
           first: int = 1, last: int | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / pdf.stem
    cmd = ["pdftoppm", "-r", str(dpi), "-png", "-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(pdf), str(stem)]
    subprocess.run(cmd, check=True, capture_output=True)
    return sorted(out_dir.glob(f"{pdf.stem}-*.png"))


def ocr(page_png: Path) -> str:
    r = subprocess.run(["tesseract", str(page_png), "stdout"],
                       capture_output=True, text=True)
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("numbers", nargs="*")
    ap.add_argument("--from-filings", type=Path)
    ap.add_argument("--accounts-types", nargs="*",
                    default=["small", "full", "group"],
                    help="Only fetch where the profile's accounts category "
                         "is one of these. A dormant or micro-entity filing "
                         "carries no investment-property note, so its "
                         "silence is structural and costs nothing to skip.")
    ap.add_argument("--render", action="store_true",
                    help="Also render pages to PNG at 300 DPI and OCR them.")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--max-pages", type=int, default=0)
    args = ap.parse_args()

    wanted: list[tuple[str, str, str]] = []   # number, name, document_id
    if args.from_filings:
        for c in json.loads(args.from_filings.read_text()):
            la = (c.get("accounts") or {}).get("last_accounts") or {}
            if la.get("type") not in args.accounts_types:
                continue
            latest = c.get("latest_accounts") or {}
            if not latest.get("document_id"):
                continue
            if args.numbers and c["company_number"] not in args.numbers:
                continue
            wanted.append((c["company_number"], c["company_name"],
                           latest["document_id"]))
    elif args.numbers:
        client0 = ch.Client()
        for n in args.numbers:
            hist = client0.filing_history(n)
            latest = ch.latest_accounts(hist)
            if not latest:
                print(f"{n}: no accounts filed")
                continue
            prof = client0.profile(n) or {}
            wanted.append((n, prof.get("company_name", ""),
                           ch.document_id_of(latest)))
    else:
        ap.error("give company numbers, or --from-filings")

    client = ch.Client()
    manifest = []
    for num, name, doc_id in wanted:
        dest = PDF_DIR / f"{num}.pdf"
        got = client.document(doc_id, dest)
        if not got:
            print(f"  FAILED {num} {name}: document {doc_id}")
            manifest.append({"company_number": num, "company_name": name,
                             "document_id": doc_id, "error": "fetch failed"})
            continue
        sha = hashlib.sha256(got.read_bytes()).hexdigest()
        entry = {"company_number": num, "company_name": name,
                 "document_id": doc_id, "path": str(got),
                 "bytes": got.stat().st_size, "sha256": sha}
        if args.render:
            pages = render(got, PAGE_DIR / num, dpi=args.dpi,
                           last=args.max_pages or None)
            entry["pages_rendered"] = len(pages)
            for p in pages:
                (p.with_suffix(".txt")).write_text(ocr(p))
        manifest.append(entry)
        print(f"  {num} {name[:44]:46} {entry['bytes']:>9,} bytes "
              f"{entry.get('pages_rendered', '')}")

    dest = ch.RAW_DIR / f"accounts_manifest_{client.as_at}.json"
    dest.write_text(json.dumps(manifest, indent=1))
    ok = sum(1 for m in manifest if "error" not in m)
    print(f"{ok}/{len(manifest)} documents fetched. "
          f"{len(client.failures)} failures. Manifest: {dest}")
    for path, err in client.failures[:20]:
        print(f"  FAILED {path}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
