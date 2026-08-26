#!/usr/bin/env python3
"""Pull the filing record for a list of resolved companies.

Five things per company, and the ownership four are first-class outputs
rather than a by-product of the capacity hunt:

  * **profile** — status, type, accounts category and next-due dates. The
    accounts category is what says whether a capacity assumption could
    exist at all: a dormant or micro-entity filing carries no
    investment-property note, so its silence is measured, not missing.
  * **filing history** — every accounts filing (so a figure can be dated
    to a year rather than to "the latest"), the confirmation statements
    and the charge filings.
  * **charges** — who lent and over what. On a single-asset SPV the
    lender is routinely the only party named above it anywhere public.
  * **PSC register, both halves** — the people, *and* the statements. An
    overseas LP is not a registrable relevant legal entity, so a
    US-parented scheme's page reads "no registrable person": a
    disclosure with a meaning, not an empty register.
  * **officers** — the directors, and the corporate-director service
    addresses that frequently give the group away.

Everything is snapshotted raw under `data/raw/companies_house/<date>/`
by `dcp.companies_house.Client` before it is summarised, so a re-run is
a no-op on unchanged content and a changed register leaves the earlier
state intact beside the new one.

Output: `data/raw/companies_house/filings_<date>.json`, one object per
company. Nothing is written to the database and nothing is asserted
about a site — that adjudication happens in the committed YAML.

Usage:
    scripts/ch_pull_filings.py --numbers-file NUMBERS.txt
    scripts/ch_pull_filings.py 14045228 OE003126 …
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from dcp import companies_house as ch


def pull(client: ch.Client, number: str, name_hint: str = "") -> dict:
    prof = client.profile(number)
    if prof is None:
        return {"company_number": number, "name_hint": name_hint,
                "error": "profile not found"}

    history = client.filing_history(number)
    # The charges register is asked for every company, not only those
    # whose profile carries has_charges. The flag is a derived summary
    # and gating the request on it means "no charges" is inherited rather
    # than measured — the endpoint answering 404 is the observation, and
    # it costs one call.
    charges = client.charges(number)
    psc = client.psc(number)
    officers = client.officers(number)

    accts = ch.accounts_history(history)
    latest = ch.latest_accounts(history)
    cs = ch.latest_confirmation(history)

    return {
        "company_number": number,
        "name_hint": name_hint,
        "company_name": prof.get("company_name"),
        "status": prof.get("company_status"),
        "type": prof.get("type"),
        "incorporated": prof.get("date_of_creation"),
        "registered_office": prof.get("registered_office_address"),
        "foreign_company_details": prof.get("foreign_company_details"),
        "sic_codes": prof.get("sic_codes"),
        "accounts": prof.get("accounts"),
        "has_charges": prof.get("has_charges"),
        "has_insolvency_history": prof.get("has_insolvency_history"),
        # A company that has filed no accounts discloses nothing. That is
        # a measured null with a date attached — the first accounts are
        # due on a stated day — not a gap in this sweep.
        "has_filed_accounts": ch.has_filed_accounts(prof),
        "accounts_filings": [{
            "made_up_to": a.get("action_date"),
            "filed": a.get("date"),
            "description": a.get("description"),
            "type": a.get("type"),
            "document_id": ch.document_id_of(a),
            "url": ch.filing_url(number, a),
            "pages": a.get("pages"),
        } for a in accts],
        "latest_accounts": ({
            "made_up_to": latest.get("action_date"),
            "filed": latest.get("date"),
            "description": latest.get("description"),
            "document_id": ch.document_id_of(latest),
            "url": ch.filing_url(number, latest),
        } if latest else None),
        "latest_confirmation_statement": ({
            "date": cs.get("date"),
            "description": cs.get("description"),
            "document_id": ch.document_id_of(cs),
            "url": ch.filing_url(number, cs),
        } if cs else None),
        "charges": ch.summarise_charges(charges),
        "psc": ch.summarise_psc(psc),
        "officers": [{
            "name": o.get("name"),
            "role": o.get("officer_role"),
            "appointed_on": o.get("appointed_on"),
            "resigned_on": o.get("resigned_on"),
            "nationality": o.get("nationality"),
            "country_of_residence": o.get("country_of_residence"),
            "identification": o.get("identification"),
            "address": o.get("address"),
        } for o in officers],
        "filing_history_count": len(history),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("numbers", nargs="*")
    ap.add_argument("--numbers-file", type=Path,
                    help="One company number per line; anything after a "
                         "space or a hash is a comment (the name).")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    wanted: list[tuple[str, str]] = [(n, "") for n in args.numbers]
    if args.numbers_file:
        for line in args.numbers_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            num, _, rest = line.partition(" ")
            wanted.append((num.strip(), rest.strip()))
    if not wanted:
        ap.error("give company numbers, or --numbers-file")

    client = ch.Client()
    out = []
    for i, (num, hint) in enumerate(wanted, 1):
        out.append(pull(client, num, hint))
        if i % 10 == 0:
            print(f"  … {i}/{len(wanted)}", flush=True)

    dest = args.out or (ch.RAW_DIR / f"filings_{client.as_at}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, default=str))

    filed = sum(1 for c in out if c.get("has_filed_accounts"))
    charged = sum(1 for c in out if c.get("charges"))
    nopsc = sum(1 for c in out
                if (c.get("psc") or {}).get("reads_as_no_registrable_person"))
    print(f"{len(out)} companies. {filed} have filed accounts, "
          f"{charged} carry charges, {nopsc} read as no registrable person.")
    print(f"{client.calls} API calls, {client.cache_hits} from cache, "
          f"{len(client.failures)} failures.")
    for path, err in client.failures[:20]:
        print(f"  FAILED {path}: {err}")
    print(f"Written to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
