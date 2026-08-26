#!/usr/bin/env python3
"""Name the scheme SPVs the corpus already holds, and resolve them at
Companies House.

The candidates come from three places, all of which are already in the
database or committed to the repository:

  * Barbour's **client-of-record** and end-user slots (`CyName_Client`,
    `CyName_4..13` with their `Role_*`), which is where a scheme's own
    vehicle is named — `UK Court Lane DC Limited`, `VDC LHR11 Limited`;
  * **findings** in the `party_applicant` and `party_other` families,
    which is where a document names the applicant — `Manor Farm Propco
    Limited`, `Latos Data Centre Ltd`, `Apatura DC Project 11 Ltd`;
  * `data/priors/organisation_aliases.yaml`, which is where a person has
    already recorded what a name turned out to be.

Two filters narrow the field, and both are deliberately shallow: this
script produces *candidates*, and which candidate is the company is a
person's adjudication that lands in the aliases file.

  1. The string has to look like a UK company (a legal suffix), and not
     look like an adviser writing on someone's behalf.
  2. A scheme SPV exists for one scheme, so a name appearing across many
     sites is an operator or a consultancy rather than a vehicle. The
     site count travels with every candidate rather than being used to
     drop anything silently.

What it writes is a working file for review, not a source of truth:
`data/raw/companies_house/spv_candidates.json`, one entry per candidate
name with the Companies House search results beside it. Nothing is
asserted; a match is chosen by a person and written into
`companies-house-spvs.yaml` with its evidence.

Usage:
    scripts/ch_resolve_spvs.py [--limit N] [--no-search]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from dcp import companies_house as ch
from dcp import db

OUT = ch.RAW_DIR / "spv_candidates.json"
ALIASES = ROOT / "data" / "priors" / "organisation_aliases.yaml"

SUFFIX = re.compile(
    r"\b(limited|ltd\.?|llp|l\.l\.p\.?|plc|p\.l\.c\.?|sarl|s\.a\.r\.l\.?|llc)\s*$",
    re.IGNORECASE)

# Prefixes that mean the string is a sentence about a party rather than a
# party. "Applicant is X Ltd" is the same company as "X Ltd" and the
# finding text keeps both; the sentence forms are stripped, not dropped,
# so the mention count stays with the company.
LEAD = re.compile(
    r"^(the\s+)?(joint\s+)?(applicant|applicants|appellant|appellants|client|"
    r"clients|agent|developer|owner|applicant/client|applicant/developer|"
    r"applicant entity|applicant entities|applicant parties|applicant/project|"
    r"applicant consortium|application submitted|document|report|"
    r"environmental statement|prepared|submitted|consultant)"
    r"[^:]{0,40}?(\bis\b|\bare\b|\bnamed\b|:|\bfor\b|\bby\b|\bon behalf of\b)\s+",
    re.IGNORECASE)

# Names that are the professional record, not the scheme's vehicle.
ADVISER = re.compile(
    r"\b(arup|aecom|wsp|ramboll|stantec|turley|barton willmore|lichfields|"
    r"avison young|gerald eve|jll|cbre|knight frank|colliers|cushman|"
    r"mott macdonald|arcadis|buro happold|curtins|waterman|rps group|slr "
    r"consulting|temple group|erm\b|atkins|hydrock|tetra tech|sweco|jacobs|"
    r"deloitte|savills|montagu evans|pegasus group|quod\b|dp9|iceni|"
    r"carter jonas|marrons|bidwells|strutt|firstplan|boyer|rapleys|"
    r"i2 analytical|eurofins|socotec|delta-simons|pinnacle consulting|"
    r"nicholas webb|ove arup|wyg |concept engineering|architects?)\b", re.IGNORECASE)


def _clean(name: str) -> str:
    s = " ".join(str(name).split())
    prev = None
    while prev != s:
        prev = s
        s = LEAD.sub("", s).strip(" .,:;-")
    return s


def barbour_candidates(cur) -> dict[str, dict]:
    """Owner-role names from Barbour's project party blocks."""
    owner_roles = {"Client", "End user", "Associated developer",
                   "Equity Partner/Finance", "Delivery Partner"}
    slots = [str(i) for i in range(4, 14)] + ["Client", "Architect", "Contractor"]

    cur.execute("SELECT id, title, external_ref, address, postcode, raw_metadata "
                "FROM projects")
    projects = cur.fetchall()
    cur.execute("""
        SELECT pa.project_id, a.id FROM project_applications pa
        JOIN applications a ON a.id = pa.application_id
    """)
    proj_apps = collections.defaultdict(list)
    for pid, aid in cur.fetchall():
        proj_apps[pid].append(aid)
    cur.execute("""
        SELECT sm.application_id, s.id, s.display_name FROM site_members sm
        JOIN sites s ON s.id = sm.site_id WHERE s.retired_at IS NULL
    """)
    app_site = collections.defaultdict(list)
    for aid, sid, sname in cur.fetchall():
        app_site[aid].append((sid, sname))

    out: dict[str, dict] = {}
    for pid, title, ref, addr, pcode, rm in projects:
        sites = {}
        for aid in proj_apps.get(pid, []):
            for sid, sname in app_site.get(aid, []):
                sites[sid] = sname
        for slot in slots:
            role, name = rm.get(f"Role_{slot}"), rm.get(f"CyName_{slot}")
            if not role or not name or role not in owner_roles:
                continue
            name = _clean(name)
            if not SUFFIX.search(name) or ADVISER.search(name):
                continue
            e = out.setdefault(name.lower(), {
                "name": name, "sources": [], "sites": {}, "mentions": 0})
            e["sources"].append({
                "source": "barbour", "role": role, "project_ref": ref,
                "project_title": title, "address": addr, "postcode": pcode,
                "company_address": " ".join(
                    str(rm.get(f"CyAddr{n}_{slot}") or "") for n in (1, 2, 3, 4)
                ).strip(),
                "company_postcode": rm.get(f"CyPcode_{slot}"),
            })
            e["sites"].update(sites)
            e["mentions"] += 1
    return out


def finding_candidates(cur) -> dict[str, dict]:
    """Applicant/other party names from deep-read findings."""
    cur.execute("""
        SELECT f.value_text, s.id, s.display_name, count(*)
        FROM findings f
        JOIN applications a ON a.id = f.application_id
        LEFT JOIN site_members sm ON sm.application_id = a.id
        LEFT JOIN sites s ON s.id = sm.site_id AND s.retired_at IS NULL
        WHERE f.signal_family IN ('party_applicant', 'party_other')
          AND f.value_text IS NOT NULL
        GROUP BY 1, 2, 3
    """)
    out: dict[str, dict] = {}
    for text, sid, sname, n in cur.fetchall():
        name = _clean(text)
        if not (6 < len(name) <= 90) or not SUFFIX.search(name):
            continue
        if ADVISER.search(name):
            continue
        e = out.setdefault(name.lower(), {
            "name": name, "sources": [], "sites": {}, "mentions": 0})
        e["mentions"] += n
        if sid:
            e["sites"][sid] = sname
        if not e["sources"]:
            e["sources"].append({"source": "findings"})
    return out


def alias_candidates() -> dict[str, dict]:
    doc = yaml.safe_load(ALIASES.read_text()) or {}
    out: dict[str, dict] = {}
    for g in doc.get("groups", []):
        for m in g.get("members", []):
            name = _clean(m["name"])
            out.setdefault(name.lower(), {
                "name": name, "sources": [], "sites": {}, "mentions": 0,
            })["sources"].append({
                "source": "organisation_aliases",
                "group": g.get("group"), "relation": m.get("relation"),
                "status": m.get("status"),
                "company_number": m.get("company_number"),
                "register": m.get("register", "companies_house"),
            })
    return out


def merge(*maps: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in maps:
        for k, v in m.items():
            e = out.setdefault(k, {"name": v["name"], "sources": [],
                                   "sites": {}, "mentions": 0})
            e["sources"] += v["sources"]
            e["sites"].update(v["sites"])
            e["mentions"] += v["mentions"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="Search only the N most-mentioned candidates.")
    ap.add_argument("--no-search", action="store_true",
                    help="Build the candidate list; do not call the API.")
    ap.add_argument("--names-file", type=Path,
                    help="Restrict the search to the names in this file, "
                         "one per line — the reviewed shortlist.")
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        cands = merge(barbour_candidates(cur), finding_candidates(cur),
                      alias_candidates())
    print(f"{len(cands)} company-shaped party names in the corpus.")

    wanted = list(cands.values())
    if args.names_file:
        keep = {_clean(ln).lower() for ln in
                args.names_file.read_text().splitlines() if ln.strip()}
        wanted = [c for c in wanted if c["name"].lower() in keep]
        missing = keep - {c["name"].lower() for c in wanted}
        for m in sorted(missing):
            # A shortlisted name the corpus does not carry verbatim is
            # still searched: it may be a variant a person recognised.
            wanted.append({"name": m, "sources": [{"source": "shortlist"}],
                           "sites": {}, "mentions": 0})
    wanted.sort(key=lambda c: -c["mentions"])
    if args.limit:
        wanted = wanted[:args.limit]

    if args.no_search:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(wanted, indent=1, default=str))
        print(f"{len(wanted)} candidates written to {OUT} (no search).")
        return 0

    client = ch.Client()
    for i, c in enumerate(wanted, 1):
        hits = client.search_companies(c["name"], n=6)
        c["ch_search"] = [{
            "company_number": h.get("company_number"),
            "title": h.get("title"),
            "status": h.get("company_status"),
            "type": h.get("company_type"),
            "created": h.get("date_of_creation"),
            "address": h.get("address_snippet"),
        } for h in hits]
        if i % 25 == 0:
            print(f"  … {i}/{len(wanted)} searched", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(wanted, indent=1, default=str))
    exact = sum(1 for c in wanted if c.get("ch_search") and
                c["ch_search"][0]["title"].lower().replace(".", "")
                .replace("limited", "ltd").strip()
                == c["name"].lower().replace(".", "")
                .replace("limited", "ltd").strip())
    print(f"{len(wanted)} candidates searched, {exact} with an exact "
          f"top-hit name match. {client.calls} API calls, "
          f"{client.cache_hits} from cache, {len(client.failures)} failures.")
    for path, err in client.failures[:20]:
        print(f"  FAILED {path}: {err}")
    print(f"Written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
