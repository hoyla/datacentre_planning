#!/usr/bin/env python3
"""Triage the large site-capacity figures, because those are the ones read.

A reporter opening this dataset goes to the biggest numbers first. A
decimal error, a unit confusion or a misread quantity anywhere in that
set discredits the rest of it, so the largest figures deserve more than
the same automated confidence as the smallest.

This does not decide anything. It sorts every site_capacity verdict at
or above a threshold into "no reason to doubt" and "look at this", and
prints the second group with its quotes. The categories come from errors
already found in this corpus rather than from imagination:

**energy, not power** — an ARK document gives a data centre load as
"251,859,057.50 kW which equates to 94,197.29 kWh/m2". The unit says
power; the cross-reference says energy. Migration 015 demoted three of
these. Any quote carrying kWh/MWh/GWh or "per annum" beside a power
figure is suspect.

**thermal, not electrical** — "a Thermal Input of around 1.2GW" is fuel
energy entering a plant, typically two to three times the electrical
capacity leaving it. Recording it as the site's power capacity
overstates the site.

**storage, not generation** — a 1,000 MW battery energy storage system
is rated for how fast it can discharge, not for what the site draws or
generates. It belongs in the record, but not as the development's
capacity.

**apparent, not real** — MVA and kVA are apparent power; converting them
to MW needs a power factor nobody has published. The adjudicator already
records these without converting, and this flags any that slipped
through with a value_mw.

**implausible** — no announced data centre campus anywhere approaches
3 GW. Above that, something is wrong by construction.

**suspiciously round multiples** — a figure exactly 10x or 1000x another
figure on the same site is the signature of a decimal or unit slip.

Usage:
    scripts/review_large_capacities.py [--min-mw 100] [--out FILE]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

ENERGY = re.compile(r"kwh|mwh|gwh|per annum|annually|per year|kwh/m", re.I)
THERMAL = re.compile(r"thermal|heat input|calorific|fuel input", re.I)
STORAGE = re.compile(r"battery|bess|energy storage|storage system", re.I)
IMPLAUSIBLE_MW = 3000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--min-mw", type=float, default=100.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key, s.display_name, pa.id, pa.value_mw,
                   pa.value_original, pa.unit_original, pa.quantity_type,
                   pa.model, f.signal_type,
                   regexp_replace(f.evidence_text, E'\\\\s+', ' ', 'g'),
                   a.application_ref
            FROM power_adjudication pa
            JOIN findings f ON f.id = pa.finding_id
            JOIN applications a ON a.id = f.application_id
            JOIN site_members m ON m.application_id = f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
            WHERE pa.verdict = 'site_capacity' AND pa.value_mw >= %s
            ORDER BY pa.value_mw DESC""", (args.min_mw,))
        rows = cur.fetchall()

    by_site: dict[str, list] = defaultdict(list)
    for r in rows:
        by_site[r[0]].append(r)

    flagged, clean = [], []
    for (key, name, aid, mw, orig, unit, qt, model, stype, quote,
         ref) in rows:
        reasons = []
        text = f"{quote} {stype}"
        if mw >= IMPLAUSIBLE_MW:
            reasons.append("implausible (>3 GW)")
        if ENERGY.search(text):
            reasons.append("energy units in quote/label — may not be power")
        if THERMAL.search(text):
            reasons.append("thermal input, not electrical capacity")
        if STORAGE.search(text) and qt != "onsite_generation":
            reasons.append("storage rating")
        elif STORAGE.search(text):
            reasons.append("storage rating recorded as generation")
        if (unit or "").lower() in ("mva", "kva"):
            reasons.append("apparent power converted to MW")
        # a figure that is exactly 10x/100x/1000x another on the same
        # site is what a decimal slip looks like
        others = {round(o[3], 6) for o in by_site[key] if o[2] != aid}
        for factor in (10, 100, 1000):
            if any(abs(mw - o * factor) < 0.01 or abs(mw * factor - o) < 0.01
                   for o in others):
                reasons.append(f"exactly {factor}x another figure on this "
                               f"site — possible decimal slip")
                break
        (flagged if reasons else clean).append(
            (mw, key, name, ref, qt, unit, orig, model, stype, quote, reasons))

    stamp = dt.datetime.now(dt.timezone.utc)
    out = [f"# Large site-capacity review (>= {args.min_mw:g} MW) — "
           f"{stamp:%Y-%m-%d %H:%M} UTC", "",
           f"{len(rows)} verdicts at or above {args.min_mw:g} MW across "
           f"{len(by_site)} sites.",
           f"**{len(flagged)} flagged for human reading; {len(clean)} with "
           f"no automated reason to doubt.**", "",
           "Flagged does not mean wrong. It means a category of error "
           "already found in this corpus applies, and a person should "
           "decide.", ""]

    out.append("## Flagged")
    out.append("")
    for (mw, key, name, ref, qt, unit, orig, model, stype, quote,
         reasons) in flagged:
        out += [f"### {mw:,.0f} MW — {name or key}",
                f"- site `{key}` · application `{ref}`",
                f"- recorded as **{qt or '—'}** from {orig:g} {unit} "
                f"(signal `{stype}`, adjudicated by `{model}`)",
                "- flags: " + "; ".join(reasons),
                f"- quote: \"{quote[:400]}\"", ""]

    out += ["## Not flagged", "",
            "| MW | site | type | quote |", "|---|---|---|---|"]
    for (mw, key, name, ref, qt, unit, orig, model, stype, quote,
         _r) in clean:
        q = quote[:110].replace("|", "\\|")
        out.append(f"| {mw:,.0f} | {(name or key)[:38]} | {qt or '—'} "
                   f"| {q} |")

    path = args.out or (ROOT / "data" / "reports" /
                        f"large_capacity_review_{stamp:%Y-%m-%d_%H%M}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")

    print(f"{len(rows)} verdicts >= {args.min_mw:g} MW across "
          f"{len(by_site)} sites")
    print(f"  flagged for reading: {len(flagged)}")
    print(f"  no automated doubt : {len(clean)}")
    counts: dict[str, int] = defaultdict(int)
    for f in flagged:
        for r in f[-1]:
            counts[r.split(" —")[0].split(" (")[0]] += 1
    for reason, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {n:>4}  {reason}")
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
