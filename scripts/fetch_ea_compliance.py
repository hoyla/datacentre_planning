"""Pull the Environment Agency's Compliance Assessment Reports.

A permit records what an operator may run. A CAR records what an
Environment Agency officer found — and, where the assessment is a data
review rather than a site visit, what the operator's own **annual
return** said. That return is the document this project has asked for
under the EIR, and the reviewing officer quotes its figures.

So this is the only published source in the corpus that reports what
standby plant actually did. Everything else — the permit's 500-hour
cap, the MWth on the schedule, the generator counts in planning
documents — describes capacity or permission.

The Agency began publishing CARs for Installations on 18 August 2025, so
the coverage is recent and partial: this harvest is a sweep of every
permit this project already tracks, and the ones with no compliance
documents are recorded as such rather than skipped, because "no report
published" is a finding about the register and not a gap in the run.

Same contract as scripts/fetch_ea_permits.py. PDFs land in data/raw/,
which is gitignored; what is committed is the manifest — each report's
URL, sha256, byte count and page count — and the extracted text, so a
quote in a published story can be re-checked from a fresh clone.
Idempotent: a report whose sha256 already matches is not re-downloaded,
and its text is only re-extracted if the bytes changed.

Usage:
    scripts/fetch_ea_compliance.py                  # every permit
    scripts/fetch_ea_compliance.py --only virtus
    scripts/fetch_ea_compliance.py --limit 5
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dcp import ea_permits as ea
from dcp.extract import extract_pdf

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# The public register publishes no rate limit and these are small
# requests; a third of a second between them is courtesy.
DELAY = 0.35


def _get(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return f.read()


def list_documents(stem: str) -> list[dict] | None:
    """The compliance documents published for one permit.

    `[]` means the endpoint answered and this permit has none published;
    `None` means the request failed and we do not know. Those are
    different facts and the caller must not record the second as the
    first — a timeout is not evidence of a clean site.

    A 404 belongs in the first group, not the second. The register
    answers an unknown permit with 404 and the body "File path not
    exist", which is it telling us there are no compliance documents
    for this permit — 47 of the 97 permits here are in that position.
    Treating it as an error would have made the commonest real finding
    in this sweep indistinguishable from a network failure.
    """
    url = ea.COMPLIANCE_LIST_URL.format(stem=stem)
    try:
        raw = _get(url, timeout=45)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        return None
    except (urllib.error.URLError, TimeoutError):
        return None
    time.sleep(DELAY)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # The register serves an HTML 404 page for an unknown permit
        # rather than a JSON error, so unparseable means "not found".
        return []
    return data if isinstance(data, list) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Substring filter on holder or operator.")
    ap.add_argument("--limit", type=int, help="Stop after N permits.")
    args = ap.parse_args()

    cands = ea.candidates()
    if args.only:
        q = args.only.lower()
        cands = [c for c in cands
                 if q in c.row.name.lower()
                 or q in (c.operator or "").lower()
                 or q in c.row.site_address.lower()]
    if args.limit:
        cands = cands[:args.limit]

    ea.COMPLIANCE_PDF_DIR.mkdir(parents=True, exist_ok=True)
    ea.COMPLIANCE_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = ea.load_compliance_manifest()

    with_docs = downloaded = unchanged = failed = 0
    for i, c in enumerate(cands, 1):
        row = c.row
        stem = row.permission_number.rsplit("/", 1)[-1].upper()
        listed = list_documents(stem)
        if listed is None:
            failed += 1
            print(f"[{i}/{len(cands)}] {row.permission_number}: "
                  f"listing failed — left as it was, not recorded as empty")
            continue

        docs = []
        prior = {d.get("url"): d
                 for d in (manifest.get(row.slug) or {}).get("documents", [])}
        for d in listed:
            name = d.get("document") or ""
            link = d.get("link") or ""
            if not name or not link:
                continue
            url = ea.COMPLIANCE_BASE_URL + link
            meta = ea.parse_compliance_name(name)
            doc_stem = f"{row.slug}-car-{meta['report_id'] or name}"
            pdf = ea.COMPLIANCE_PDF_DIR / f"{doc_stem}.pdf"
            was = prior.get(url)
            if pdf.exists() and was and was.get("sha256"):
                if hashlib.sha256(pdf.read_bytes()).hexdigest() == was["sha256"]:
                    # Keep what cost a download — sha, bytes, pages, the
                    # date we fetched it — and re-derive what is only a
                    # parse of the filename. Reusing the whole prior
                    # entry meant a correction to ASSESSMENT_TYPES could
                    # never reach an already-downloaded report: the 16
                    # reports first labelled "unrecognised code PR"
                    # would have kept that label through every re-run.
                    docs.append({**was,
                                 "assessment_type": meta["type"],
                                 "assessment": meta["type_label"],
                                 "report_id": meta["report_id"],
                                 "issued": meta["issued"]})
                    unchanged += 1
                    continue
            try:
                data = _get(url)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                print(f"    ! {url}: {exc}")
                failed += 1
                continue
            time.sleep(DELAY)
            pdf.write_bytes(data)
            pages = extract_pdf(pdf)
            for n, page in enumerate(pages, 1):
                (ea.COMPLIANCE_TEXT_DIR / f"{doc_stem}-p{n}.txt").write_text(page)
            docs.append({
                "document": name, "url": url, "stem": doc_stem,
                "assessment_type": meta["type"],
                "assessment": meta["type_label"],
                "report_id": meta["report_id"],
                "issued": meta["issued"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data), "pages": len(pages),
                "fetched": dt.date.today().isoformat(),
            })
            downloaded += 1
            print(f"[{i}/{len(cands)}] {row.permission_number} "
                  f"{meta['type_label']} {meta['issued']}: {len(pages)}pp")

        if docs:
            with_docs += 1
        manifest[row.slug] = {
            "permission_number": row.permission_number,
            "holder": row.name,
            "operator": c.operator,
            "site_address": row.site_address,
            "postcode": row.postcode,
            # Checked, and none published — as against a permit this
            # sweep never reached, which is simply absent from the file.
            "checked": dt.date.today().isoformat(),
            "documents": sorted(docs, key=lambda d: (d.get("issued") or "",
                                                     d.get("report_id") or "")),
        }

    ea.COMPLIANCE_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    total = sum(len(v.get("documents") or []) for v in manifest.values())
    print(f"\n{len(cands)} permits checked, {with_docs} with at least one "
          f"report; {total} reports in the manifest. "
          f"{downloaded} downloaded, {unchanged} already current"
          + (f", {failed} failed" if failed else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
