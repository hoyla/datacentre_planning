"""What the permits say, and which sites they might belong to.

Two jobs, both for a human to read rather than for a pipeline to consume.
`--readings` prints every permit that was fetched, what was read out of
it, and whether the per-engine ratings corroborate the stated total —
including the permits that yielded nothing, because a source's silences
matter as much as its figures. `--candidates` adds, for each claim, the
sites near it: by shared postcode first, then by distance from the
permit's own grid reference.

Nothing here writes a match. The output is the working paper for the
adjudication that goes, by hand and with written evidence, into
data/external_sources/ea-permit-matches.yaml. Proximity is a candidate
generator and never an identity: one site record can hold several
campuses, and reading district proximity as identity is exactly what
produced the Union Park match that had to be retired.

Usage:
    scripts/read_ea_permits.py --readings
    scripts/read_ea_permits.py --candidates [--km 3] [--only virtus]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from dcp import db
from dcp import ea_permits as ea


def readings() -> int:
    if not ea.have_permit_text():
        print(f"No permit text under {ea.TEXT_DIR}. The documents are not "
              f"committed; fetch them first:\n"
              f"    scripts/fetch_ea_permits.py --documents\n"
              f"The claims themselves are in "
              f"{ea.CLAIMS_PATH.relative_to(ea.ROOT)} and need no fetch.",
              file=sys.stderr)
        return 1
    manifest = ea.load_manifest()
    with_doc = [(s, e) for s, e in sorted(manifest.items())
                if any(d.get("kind") == "permit" for d in e["documents"])]
    read = 0
    print(f"{len(manifest)} candidates, {len(with_doc)} with a permit "
          f"document.\n")
    for slug, entry in with_doc:
        doc = next(d for d in entry["documents"] if d["kind"] == "permit")
        r = ea.read_permit_text(ea.permit_pages(doc["stem"]), slug,
                                entry["permission_number"])
        head = (f"{entry['permission_number']}  {entry['holder'][:44]}  "
                f"{entry['postcode']}")
        if r.total_mwth is None:
            print(f"--  {head}\n    nothing readable in {doc['pages']} pages")
            continue
        read += 1
        print(f"{r.total_mwth:>9.4g} MWth  {head}")
        print(f"    {ea._site_name(entry)}")
        print(f"    generators {r.generator_count}, "
              f"engines {r.engines or '—'}"
              + (f", redundancy {r.redundancy}" if r.redundancy else ""))
        print(f"    {r.corroboration}")
        print(f"    page {r.total_page}: “{(r.total_quote or '')[:150]}”")
        print()
    print(f"{read} of {len(with_doc)} permits state a readable total.")
    return 0


def write_claims() -> int:
    """Regenerate the committed claims file from the local permit text.

    The one step that needs the fetched documents. Everything downstream
    — the loader, the artefacts, the tests — reads the file this writes,
    so a clone with no documents is still a working checkout.
    """
    if not ea.have_permit_text():
        print(f"No permit text under {ea.TEXT_DIR}. Fetch the documents "
              f"first:\n    scripts/fetch_ea_permits.py --documents",
              file=sys.stderr)
        return 1
    claims = ea.build_ea_claims()
    problems = ea.verify_ea_quotes(claims)
    if problems:
        for p in problems:
            print(f"INVALID: {p}", file=sys.stderr)
        return 1
    before = len(ea.load_ea_claims()) if ea.CLAIMS_PATH.exists() else 0
    ea.write_claims_file(claims)
    print(f"Wrote {ea.CLAIMS_PATH.name}: {len(claims)} claims, "
          f"{sum(c.value for c in claims):,.1f} MWth "
          f"(was {before}). Every quote verified against the page it "
          f"cites.")
    return 0


def candidates(km: float, only: str | None) -> int:
    claims = ea.load_ea_claims()
    if only:
        q = only.lower()
        claims = [c for c in claims
                  if q in c.claim_name.lower() or q in c.company_name.lower()]
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.id, s.site_key, s.display_name, s.latitude, s.longitude,
                   array_remove(array_agg(DISTINCT a.postcode), NULL),
                   count(DISTINCT a.id)
            FROM sites s
            JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
            JOIN applications a ON a.id = m.application_id
            WHERE s.retired_at IS NULL
            GROUP BY 1, 2, 3, 4, 5""")
        sites = cur.fetchall()

    print(f"{len(claims)} claims against {len(sites)} live sites. "
          f"Postcode matches first, then anything within {km} km.\n")
    for c in claims:
        pc = (c.attrs.get("postcode") or "").upper().replace(" ", "")
        east, north = c.attrs.get("easting"), c.attrs.get("northing")
        lat = lon = None
        if east and north:
            lat, lon = ea.osgb_to_wgs84(east, north)
        rows = []
        for sid, key, name, slat, slon, pcs, n_apps in sites:
            exact = pc and any(
                (p or "").upper().replace(" ", "") == pc for p in pcs)
            d = (ea.km_between(lat, lon, float(slat), float(slon))
                 if lat is not None and slat is not None else None)
            if exact or (d is not None and d <= km):
                rows.append((0 if exact else 1, d if d is not None else 999,
                             sid, key, name, n_apps, exact))
        print(f"{c.value:>9.4g} MWth  {c.claim_name}")
        print(f"           {c.company_name} · {c.attrs['postcode']} · "
              f"{c.attrs['local_authority']}")
        if not rows:
            print("           no site within range — the corpus may not "
                  "hold this site at all")
        for _, d, sid, key, name, n_apps, exact in sorted(rows)[:6]:
            tag = "postcode" if exact else f"{d:.2f} km"
            print(f"           site {sid:>4} [{tag:>9}] {name[:60]} "
                  f"({n_apps} applications, {key})")
        print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", action="store_true")
    ap.add_argument("--candidates", action="store_true")
    ap.add_argument("--write-claims", action="store_true",
                    help="Re-derive the claims from the local permit text "
                         "and write data/external_sources/"
                         "ea-permit-claims.yaml.")
    ap.add_argument("--km", type=float, default=2.0)
    ap.add_argument("--only")
    args = ap.parse_args()
    if args.write_claims:
        return write_claims()
    if args.readings:
        return readings()
    if args.candidates:
        return candidates(args.km, args.only)
    ap.error("pass --readings, --candidates or --write-claims")


if __name__ == "__main__":
    sys.exit(main())
