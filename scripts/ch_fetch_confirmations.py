#!/usr/bin/env python3
"""Read the shareholders out of each company's latest confirmation statement.

The PSC register answers "who has significant control", and for 13 of the
companies in this sweep it answers "nobody" — an overseas limited
partnership is not a registrable relevant legal entity, so the chain
above it never reaches that register. The **confirmation statement**
answers a different and narrower question, "who holds the shares", and
it answers it for the same companies. UK Court Lane DC Ltd's PSC page
says no registrable person; its CS01 of 19 June 2026 says all seven
ordinary shares are held by UK COURT LANE DC HOLDINGS, LP.

And it is cheap, because of an accident of filing. Accounts are scanned
images with no text layer, which is why every figure in
`companies-house-claims.yaml` had to be transcribed by eye. Confirmation
statements are filed electronically and **do** carry a text layer, so
the shareholder block can be extracted rather than read — no OCR, no
risk of a silently misread digit, and the extracted text is checkable
against the PDF it came from.

The parser is deliberately shallow. It takes the "Full details of
Shareholders" section, splits it on the "Shareholding N:" headings, and
records the name and the shareholding line verbatim. Anything it cannot
parse is recorded as unparsed with its raw text rather than dropped: a
statement whose layout this does not fit is a fact about the filing, not
a company without shareholders.

Usage:
    scripts/ch_fetch_confirmations.py --filings data/raw/companies_house/filings_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from dcp import companies_house as ch

CS_DIR = ch.RAW_DIR / "cs"

# The shareholder block is a two-column table: a "Shareholding N:" /
# "Name:" label column on the left and the values on the right. Read
# WITHOUT `pdftotext -layout`, poppler emits every label first and every
# value afterwards, so the two columns arrive as two separate runs and
# pairing them means counting — which silently mis-pairs the moment one
# entry wraps onto an extra line. Sequence (Iver) UK Limited has ten
# shareholders and a naive read recovered two of them.
#
# `-layout` keeps the columns together, so a block can be parsed as a
# block. Every text extraction here uses it.
SECTION = re.compile(
    r"Full details of Shareholders(.*?)(?:\n\s*Confirmation Statement\s*\n|"
    r"End of Electronically filed document)", re.DOTALL)
BLOCK = re.compile(r"^\s*Shareholding\s+(\d+)\s*:", re.MULTILINE)
NAME = re.compile(r"^\s*Name:\s*(.+?)\s*$", re.MULTILINE)
LABEL = re.compile(r"^\s*[A-Z][A-Za-z ]{2,30}:")
FOOTER = re.compile(
    r"Electronically filed document for Company Number:.*", re.DOTALL)


def shareholders(text: str) -> list[dict]:
    """One entry per Shareholding block, holder and description verbatim.

    A block this cannot split is recorded with its raw lines under
    `unparsed` rather than dropped: a statement whose layout does not fit
    is a fact about the filing, not a company without shareholders.
    """
    m = SECTION.search(text)
    if not m:
        return []
    body = m.group(1)
    parts = BLOCK.split(body)[1:]            # [n, chunk, n, chunk, …]
    out = []
    for i in range(0, len(parts) - 1, 2):
        n, chunk = parts[i], FOOTER.sub("", parts[i + 1])
        name_m = NAME.search(chunk)
        holder = None
        if name_m:
            # A long holder name wraps onto continuation lines in the
            # value column, with no label of its own. Truncating at the
            # first line turns "THE INVESTMENT AND DEVELOPMENT OFFICE OF
            # THE GOVERNMENT OF RAS AL KHAIMAH" into "…OF THE", which
            # reads as a parse artefact and is in fact a sovereign
            # shareholder — so the continuation is followed.
            # `end()` sits at the end of the matched name, before its
            # newline, so the first element is the empty remainder of
            # that line and is dropped rather than read as a blank.
            tail = chunk[name_m.end():].splitlines()[1:]
            extra = []
            for ln in tail:
                if not ln.strip() or LABEL.match(ln) or not ln.startswith(" "):
                    break
                extra.append(ln.strip())
            holder = " ".join([name_m.group(1).strip(), *extra]).strip()
        # Everything above the Name: line is the shareholding description,
        # which carries the class of share, the count, and any transfer.
        head = chunk[:name_m.start()] if name_m else chunk
        desc = " ".join(head.split()) or None
        out.append({"shareholding": n, "holder": holder,
                    "description": desc,
                    "unparsed": None if (holder and desc)
                    else [ln.strip() for ln in chunk.splitlines() if ln.strip()]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filings", type=Path, required=True)
    ap.add_argument("--max-statements", type=int, default=8,
                    help="How far back through the confirmation-statement "
                         "history to look for one that names shareholders.")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    rows = json.loads(args.filings.read_text())
    client = ch.Client()
    out, no_cs, no_text = [], 0, 0
    for i, r in enumerate(rows, 1):
        number = r["company_number"]
        # The *latest* confirmation statement is usually the wrong one to
        # read. A "confirmation-statement-with-no-updates" filing says by
        # definition that nothing changed, and carries no shareholder
        # block at all — 48 of the 111 companies here filed one most
        # recently. Even a "with-updates" filing only carries the parts
        # that changed, so a company whose last update was to its share
        # capital has a statement of capital and no shareholders.
        #
        # So the whole confirmation-statement history is walked
        # newest-first, and the answer is the most recent filing that
        # actually names holders. A shareholder list stays true until it
        # is superseded, so an older statement is not a worse answer —
        # it is the current one, and its date says as of when.
        history = client.filing_history(number)
        cs_filings = [f for f in history
                      if (f.get("type") in ch.CONFIRMATION_TYPES
                          and ch.document_id_of(f))]
        cs_filings.sort(key=lambda f: f.get("date") or "", reverse=True)
        if not cs_filings:
            no_cs += 1
            out.append({"company_number": number,
                        "company_name": r.get("company_name"),
                        "confirmation_statement": None,
                        "statements_tried": 0,
                        "shareholders": [],
                        "note": "no confirmation statement filed"})
            continue

        holders, used, text = [], None, ""
        tried = 0
        for f in cs_filings[:args.max_statements]:
            tried += 1
            doc_id = ch.document_id_of(f)
            pdf = CS_DIR / f"{number}-{doc_id[:12]}.pdf"
            got = client.document(doc_id, pdf)
            text = ""
            if got:
                text = subprocess.run(["pdftotext", "-layout", str(got), "-"],
                                      capture_output=True, text=True).stdout
            holders = shareholders(text)
            if holders:
                used = f
                break
        if not text.strip():
            no_text += 1
        used = used or cs_filings[0]
        out.append({
            "company_number": number,
            "company_name": r.get("company_name"),
            "confirmation_statement": {
                "date": used.get("date"),
                "description": used.get("description"),
                "url": ch.filing_url(number, used)},
            "statements_filed": len(cs_filings),
            "statements_tried": tried,
            "has_text_layer": bool(text.strip()),
            "shareholders": holders,
        })
        if i % 20 == 0:
            print(f"  … {i}/{len(rows)}", flush=True)

    dest = args.out or (ch.RAW_DIR / f"shareholders_{client.as_at}.json")
    dest.write_text(json.dumps(out, indent=1))
    found = sum(1 for c in out if c["shareholders"])
    print(f"{len(out)} companies: {found} with a parsed shareholder list, "
          f"{no_cs} with no confirmation statement filed, {no_text} whose "
          f"document had no text layer.")
    print(f"{client.calls} API calls, {len(client.failures)} failures.")
    for path, err in client.failures[:20]:
        print(f"  FAILED {path}: {err}")
    print(f"Written to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
