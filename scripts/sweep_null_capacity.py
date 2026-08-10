#!/usr/bin/env python3
"""Re-verify the null-capacity claim, reproducibly this time.

The claim — some number of consented or pending data-centre sites
disclose no power capacity figure anywhere in their planning documents —
is one of the dataset's flagship findings, precisely because a corpus
built to principle 1 can produce a null result and mean it.

The first version of that claim (71 sites, 2026-08-07) cannot be relied
on, for two reasons this script exists to fix. It was measured before
the extractor could read Word, Outlook or spreadsheet documents, so its
"read in full" cohort could contain documents nobody could read; and
the regex sweep that confirmed it was never committed, so nobody could
re-run it. This is the committed, re-runnable form. Its number is
whatever it prints on the day it runs, against the coverage it states.

What it does:

1. Builds the cohort honestly: live sites holding at least one document,
   with NO adjudicated site-capacity figure (power_adjudication verdict
   'site_capacity' on any member application's findings), split by
   reading coverage — fully read, partly read, unread. Only the fully
   read cohort can support the claim; the others are reported as what
   they are.
2. Sweeps every cached page of the fully read cohort's documents for
   power-unit patterns (MW, MVA, GW, kVA, kW, spelled-out variants).
   `kWh` self-excludes on the word boundary: energy is not power.
3. Classifies each hit from its surrounding text. EV chargers, kW/m²
   intensity targets, building services and rooftop PV are benign —
   power figures that are not the data centre's capacity. Standby
   generation, grid connections and anything unclassified are NOT
   dismissed: they are printed with their quotes for human eyes,
   because a sweep that auto-waves-away the interesting residue would
   be the "nobody looked" bug wearing a lab coat.
4. Cross-checks the findings table for capacity-unit findings on cohort
   sites that have not yet been adjudicated — if any exist, the run is
   provisional and says so loudly: the claim cannot be made while
   candidate figures await adjudication.

Output: a dated markdown report under data/reports/ plus a stdout
summary. Read-only against the database and caches; safe to run at any
time; authoritative only when it says it is.

Usage:
    scripts/sweep_null_capacity.py [--limit N] [--site KEY]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db, extract  # noqa: E402

POWER = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:MW|MVA|MWe|GW|kVA|kW|megawatts?|kilowatts?)\b",
    re.IGNORECASE)

# Context classes, checked in order against ±90 characters around a hit.
# The first two groups are benign — real power figures that are not the
# site's capacity. The rest are flagged for human reading.
BENIGN = [
    ("ev_charging", re.compile(r"charg(er|ing|e point)|electric vehicle|\bEV\b", re.I)),
    ("intensity_target", re.compile(r"/\s*m2|/\s*m²|per square|kwh/m", re.I)),
    ("building_services", re.compile(r"heat pump|boiler|ashp|hvac|air condition|lift\b|lighting", re.I)),
    ("onsite_renewables", re.compile(r"\bpv\b|solar|photovolta|kwp", re.I)),
]
FLAGGED = [
    ("standby_generation", re.compile(r"generat|genset|standby|back[- ]?up|diesel", re.I)),
    ("grid_connection", re.compile(r"grid|substation|connection|supply capacity|import", re.I)),
]


def classify(context: str) -> tuple[str, bool]:
    for name, pat in BENIGN:
        if pat.search(context):
            return name, False
    for name, pat in FLAGGED:
        if pat.search(context):
            return name, True
    return "unclassified", True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0,
                    help="Sweep only the first N fully-read sites (smoke test).")
    ap.add_argument("--site", default=None, help="Sweep one site key.")
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        # Sites, coverage, and adjudicated-capacity status in one pass.
        cur.execute("""
            WITH members AS (
              SELECT s.site_key, s.display_name, a.id AS application_id,
                     a.application_ref
              FROM sites s
              JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
              JOIN applications a ON a.id = m.application_id
              WHERE s.retired_at IS NULL),
            docs AS (
              SELECT mb.site_key, d.id AS document_id, mb.application_ref,
                     d.content_sha256
              FROM members mb
              JOIN documents d ON d.application_id = mb.application_id
              WHERE d.bytes_path IS NOT NULL),
            read AS (
              SELECT DISTINCT document_id FROM deepread_log
              WHERE read_state = 'read'),
            cap AS (
              SELECT DISTINCT mb.site_key
              FROM members mb
              JOIN findings f ON f.application_id = mb.application_id
              JOIN power_adjudication pa ON pa.finding_id = f.id
              WHERE pa.verdict = 'site_capacity')
            SELECT d.site_key, min(m.display_name),
                   count(*) AS held,
                   count(*) FILTER (WHERE r.document_id IS NOT NULL) AS read,
                   bool_or(d.site_key IN (SELECT site_key FROM cap)) AS has_cap
            FROM docs d
            JOIN members m ON m.site_key = d.site_key
            LEFT JOIN read r ON r.document_id = d.document_id
            GROUP BY d.site_key""")
        sites = cur.fetchall()

        cur.execute("""
            SELECT s.site_key, a.application_ref, d.content_sha256
            FROM sites s
            JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
            JOIN applications a ON a.id = m.application_id
            JOIN documents d ON d.application_id = a.id
            WHERE s.retired_at IS NULL AND d.bytes_path IS NOT NULL""")
        docs_by_site: dict[str, list] = defaultdict(list)
        for key, ref, sha in cur.fetchall():
            docs_by_site[key].append((ref, sha))

        # Candidate figures still awaiting adjudication, per site — the
        # blocker that makes a run provisional.
        cur.execute("""
            SELECT s.site_key, count(*)
            FROM sites s
            JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
            JOIN findings f ON f.application_id = m.application_id
            WHERE s.retired_at IS NULL
              AND lower(coalesce(f.value_unit,'')) IN
                  ('mw','mva','gw','kva','kw')
              AND NOT EXISTS (SELECT 1 FROM power_adjudication pa
                              WHERE pa.finding_id = f.id)
            GROUP BY 1""")
        unadjudicated = dict(cur.fetchall())

    no_cap = [(k, n, h, r) for k, n, h, r, has in sites if not has]
    fully = [(k, n, h) for k, n, h, r in no_cap if r >= h]
    partly = [(k, n, h, r) for k, n, h, r in no_cap if 0 < r < h]
    unread = [(k, n, h) for k, n, h, r in no_cap if r == 0]

    if args.site:
        fully = [t for t in fully if t[0] == args.site] or \
                [(args.site, "(forced)", 0)]
    if args.limit:
        fully = fully[: args.limit]

    stamp = dt.datetime.now(dt.timezone.utc)
    lines = [f"# Null-capacity sweep — {stamp:%Y-%m-%d %H:%M} UTC", ""]
    pending = sum(unadjudicated.get(k, 0) for k, _, _ in fully)
    provisional = pending > 0
    if provisional:
        lines += [f"**PROVISIONAL: {pending:,} capacity-unit findings on "
                  f"the fully-read cohort await adjudication.** Until they "
                  f"are adjudicated, a site below may hold a disclosed "
                  f"figure this sweep cannot see as one. Run "
                  f"scripts/adjudicate_power.py and re-run.", ""]

    clean, benign_only, flagged_sites, unsweepable = [], [], [], []
    for key, name, held in fully:
        hits, swept, missing = [], 0, 0
        for ref, sha in docs_by_site.get(key, []):
            cache = extract.cache_path_for("documents", ref, sha)
            # A missing or unreadable cache is counted, never skipped
            # silently: a site whose text is absent from disk must come
            # out as "could not be swept", not as "clean". Zero matches
            # against zero text is the nobody-looked bug, and this
            # script exists because that bug reached a published claim.
            if not cache.exists():
                missing += 1
                continue
            try:
                pages = json.loads(cache.read_text()).get("pages") or []
            except Exception:
                missing += 1
                continue
            swept += 1
            for pno, text in enumerate(pages, 1):
                for m in POWER.finditer(text or ""):
                    ctx = text[max(0, m.start() - 90): m.end() + 90]
                    cls, flag = classify(ctx)
                    hits.append((flag, cls, ref, pno, m.group(0),
                                 " ".join(ctx.split())))
        flagged = [h for h in hits if h[0]]
        if missing:
            unsweepable.append((key, name, held, swept, missing))
        elif not hits:
            clean.append((key, name, held))
        elif not flagged:
            benign_only.append((key, name, held, len(hits)))
        else:
            flagged_sites.append((key, name, held, hits, flagged))

    n_claim = len(clean) + len(benign_only)
    lines += [
        "## Summary", "",
        f"- Sites with documents and **no adjudicated capacity**: "
        f"{len(no_cap)}",
        f"  - fully read (the only cohort that can support the claim): "
        f"{len(fully)}",
        f"  - partly read (floors, not findings): {len(partly)}",
        f"  - entirely unread: {len(unread)}",
        "",
        f"**Of the fully read: {n_claim} sites genuinely state no "
        f"capacity figure** — {len(clean)} with zero power-unit text "
        f"anywhere, {len(benign_only)} whose only power-unit text is "
        f"benign (EV charging, kW/m² targets, building services, rooftop "
        f"PV). {len(flagged_sites)} sites carry flagged matches that "
        f"need human eyes before they count either way.", ""]
    if unsweepable:
        lines += [f"**{len(unsweepable)} sites could not be fully swept** "
                  f"(text caches missing or unreadable) and are excluded "
                  f"from every count above — absence of text is not "
                  f"absence of a figure:", ""]
        lines += [f"- {k} — {n} ({sw} of {h} documents sweepable)"
                  for k, n, h, sw, _m in unsweepable]
        lines += [""]
    if provisional:
        lines += ["**This run is provisional** (see above); do not quote "
                  "its numbers.", ""]

    if flagged_sites:
        lines += ["## Flagged — read these before the claim is made", ""]
        for key, name, held, hits, flagged in flagged_sites:
            lines += [f"### {key} — {name}",
                      f"{held} documents; {len(flagged)} flagged of "
                      f"{len(hits)} total matches", ""]
            for _f, cls, ref, pno, matched, ctx in flagged[:8]:
                lines += [f"- **[{cls}]** {ref} p.{pno} — `{matched}`",
                          f"  > …{ctx[:240]}…", ""]
            if len(flagged) > 8:
                lines += [f"- …and {len(flagged) - 8} more", ""]

    lines += ["## Clean sites (zero power-unit text)", ""]
    lines += [f"- {k} — {n} ({h} documents)" for k, n, h in clean]
    lines += ["", "## Benign-only sites", ""]
    lines += [f"- {k} — {n} ({h} documents; {c} benign matches)"
              for k, n, h, c in benign_only]

    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"null_capacity_sweep_{stamp:%Y-%m-%d_%H%M}.md"
    out.write_text("\n".join(lines) + "\n")

    print(f"fully-read no-capacity sites: {len(fully)} | clean: {len(clean)} "
          f"| benign-only: {len(benign_only)} | flagged: {len(flagged_sites)} "
          f"| unsweepable: {len(unsweepable)}")
    print(f"partly read: {len(partly)} | unread: {len(unread)}")
    if provisional:
        print(f"PROVISIONAL — {pending:,} candidate figures await "
              f"adjudication; do not quote this run.")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
