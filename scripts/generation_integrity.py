#!/usr/bin/env python3
"""What each site's on-site generation figure is worth, and what it burns.

On-site generation is the second figure this investigation turns on, and
for the original v1 question it was the first: do planning applications
disclose generating plant that contradicts an operator's public
renewable marketing? That question is only answerable if the record says
what the plant *is*, not merely how many megawatts it comes to.

It mostly does not. Of the generation verdicts in this corpus, three
quarters carry no fuel and no plant type at all — a number with no
noun. This report exists to make that visible rather than let a bare
megawatt figure imply more than it says.

Five checks, all from the site's own documents:

**fuel disclosure** — diesel, gas, HVO, CHP, solar, wind, EfW, or
nothing. A generation figure without a fuel is half a finding: it tells
a reporter the site has plant, not whether that plant contradicts
anything the operator says publicly.

**count against total** — where a quote gives both a unit count and a
unit rating ("32 x 2.5MW diesel generators"), the arithmetic is checked
against the recorded figure. Verified on this corpus: the extraction
multiplies correctly, so this is a regression test rather than a
discovery, and worth keeping for exactly that reason.

**prime versus standby** — a diesel set carries two nameplate ratings
that differ by 10-15%, and documents cite whichever suits. Where the
quote names one, it is recorded; where it does not, the figure carries
that ambiguity silently.

**generation against load** — generation far below consumption is not an
error, and it is not a diagnosis either. The example this paragraph used
to give — a 120 MW hyperscale site with 2.9 MW of standby plant, read as
life-safety backup on a grid-dependent site — was Amazon Didcot, and the
2.9 MW was one unit's specification where the same documents describe
"38 no. 2,640kW generator units per building" (HISTORY, 2026-08-10).
A low ratio says: open the passage and find out whether the figure is
one machine or the fleet. Generation far ABOVE consumption is worth a
look for the opposite reason: it may be an energy park that happens to
host a data centre rather than a data centre with generators.

**plant that is not generation** — batteries, UPS, thermal input and
storage keep arriving in this column. scripts/correct_adjudications.py
removes them; this reports anything that survives, because a silent zero
is how the last four families hid.

Usage:
    scripts/generation_integrity.py [--out FILE]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

FUELS = [
    ("diesel", re.compile(r"\bdiesel\b", re.I)),
    ("gas", re.compile(r"\bnatural gas\b|\bgas[- ]fired\b|\bgas engine|\bLPG\b", re.I)),
    ("HVO / biofuel", re.compile(r"\bHVO\b|biofuel|biodiesel|renewable diesel", re.I)),
    ("CHP / energy centre", re.compile(r"\bCHP\b|combined heat|energy centre", re.I)),
    ("solar", re.compile(r"\bsolar\b|photovolta|\bPV\b", re.I)),
    ("wind", re.compile(r"\bwind\b|turbine", re.I)),
    ("energy from waste", re.compile(r"\bEfW\b|incinerat|energy from waste|\bERF\b", re.I)),
]
# "32 x 2.5MW", "114 no. 2,000 kWe", "6 No. 5.8MW"
COUNT_RATE = re.compile(
    r"(\d{1,4})\s*(?:no\.?|nr|x|×)\s*[,\s]*([\d,]+(?:\.\d+)?)\s*(MW|kW|kWe|MWe)\b",
    re.I)
RATING_KIND = re.compile(r"\bprime\b|\bstandby rating\b|\bcontinuous\b|\bESP\b|\bPRP\b", re.I)
NOT_GENERATION = re.compile(r"\bbatter|\bBESS\b|energy storage|\bUPS\b|thermal input|heat input", re.I)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key, s.display_name, pa.value_mw::float,
                   pa.unit_original, f.signal_type, f.evidence_text,
                   a.application_ref, pa.model
            FROM power_adjudication pa
            JOIN findings f ON f.id = pa.finding_id
            JOIN applications a ON a.id = f.application_id
            JOIN site_members m ON m.application_id = f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
            WHERE pa.verdict = 'site_capacity'
              AND pa.quantity_type = 'onsite_generation'
            ORDER BY pa.value_mw DESC NULLS LAST""")
        rows = cur.fetchall()

        cur.execute("""
            SELECT s.site_key,
                   max(pa.value_mw) FILTER (WHERE pa.quantity_type
                       IN ('it_load','total_site'))::float AS cons,
                   max(pa.value_mw) FILTER (WHERE pa.quantity_type
                       = 'onsite_generation')::float AS gen
            FROM power_adjudication pa
            JOIN findings f ON f.id = pa.finding_id
            JOIN site_members m ON m.application_id = f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
            WHERE pa.verdict = 'site_capacity' GROUP BY 1""")
        ratios = {k: (c, g) for k, c, g in cur.fetchall()}

    sites: dict[str, dict] = {}
    arith_ok, arith_bad, no_fuel_rows = 0, [], 0
    survivors = []
    for (key, name, mw, unit, stype, quote, ref, model) in rows:
        q = " ".join((quote or "").split())
        site = sites.setdefault(key, {"name": name, "mw": None, "fuels": set(),
                                      "rated": False, "rows": 0})
        site["rows"] += 1
        if mw is not None and (site["mw"] is None or mw > site["mw"]):
            site["mw"] = mw
        found = [fname for fname, pat in FUELS if pat.search(q)]
        site["fuels"].update(found)
        if not found:
            no_fuel_rows += 1
        if RATING_KIND.search(q):
            site["rated"] = True
        if NOT_GENERATION.search(q):
            survivors.append((mw, key, name, q[:120]))
        m = COUNT_RATE.search(q)
        if m and mw is not None:
            n = int(m.group(1))
            rate = float(m.group(2).replace(",", ""))
            if m.group(3).lower().startswith("kw"):
                rate /= 1000.0
            implied = n * rate
            if implied > 0 and abs(implied - mw) / max(implied, mw) < 0.02:
                arith_ok += 1
            elif implied > 0 and abs(rate - mw) / max(rate, mw) < 0.02:
                arith_bad.append((mw, implied, n, key, name, q[:130]))

    stamp = dt.datetime.now(dt.timezone.utc)
    no_fuel_sites = [k for k, v in sites.items() if not v["fuels"]]
    out = [f"# On-site generation integrity — {stamp:%Y-%m-%d %H:%M} UTC", "",
           f"{len(rows)} generation verdicts across {len(sites)} sites.", "",
           "## Fuel disclosure", "",
           f"- verdicts naming no fuel or plant type: **{no_fuel_rows} of "
           f"{len(rows)}** ({100*no_fuel_rows/max(len(rows),1):.0f}%)",
           f"- sites where NO generation verdict names a fuel: "
           f"**{len(no_fuel_sites)} of {len(sites)}**", "",
           "A generation figure without a fuel says the site has plant, "
           "not whether that plant contradicts anything its operator "
           "says publicly — which was the question this investigation "
           "started from.", ""]

    counts: dict[str, int] = {}
    for v in sites.values():
        for f in v["fuels"]:
            counts[f] = counts.get(f, 0) + 1
    out += ["### Sites by disclosed fuel or plant type", "",
            "| fuel / plant | sites |", "|---|---|"]
    out += [f"| {f} | {n} |" for f, n in sorted(counts.items(), key=lambda x: -x[1])]
    out += [f"| **none disclosed** | **{len(no_fuel_sites)}** |", ""]

    out += ["## Count x rating arithmetic", "",
            f"- quotes giving both a unit count and a unit rating, where "
            f"the stored figure equals count x rating: **{arith_ok}**",
            f"- where the stored figure equals ONE UNIT rather than the "
            f"fleet: **{len(arith_bad)}**", ""]
    for mw, implied, n, key, name, q in arith_bad:
        out += [f"### {mw:,.1f} MW stored, {implied:,.1f} MW implied "
                f"({n} units) — {name or key}", f"- quote: \"{q}\"", ""]

    if survivors:
        out += ["## Non-generation plant still in this column", "",
                "scripts/correct_adjudications.py should have moved these; "
                "anything here means a rule needs widening.", ""]
        for mw, key, name, q in survivors:
            v = "—" if mw is None else f"{mw:,.1f} MW"
            out += [f"- {v} — {name or key}: \"{q}\""]
        out += [""]

    out += ["## Generation against load", ""]
    band: dict[str, list] = {}
    for key, (cons, gen) in ratios.items():
        if not (cons and gen):
            continue
        r = gen / cons
        # Descriptive, not diagnostic. These labels used to assert a
        # design intent — "sized to carry the load", "life-safety only" —
        # on the strength of a ratio, and named 0.8-1.5 the classic
        # full-redundancy pattern. Measured across the 47 sites
        # disclosing both figures (2026-08-11) that band holds 13 of
        # them; the median ratio is 0.75 and the modal case, 20 sites, is
        # below 0.5. The premise was inherited from v1 and the corpus
        # does not support it, so the bands now say what the numbers do
        # and leave why to a reader who can open the documents.
        b = ("generation above stated load" if r > 1.5
             else "generation comparable to stated load" if r >= 0.8
             else "generation between half and four-fifths of stated load"
             if r >= 0.5
             else "generation below half of stated load")
        band.setdefault(b, []).append((r, cons, gen, sites.get(key, {}).get("name", key),
                                       sorted(sites.get(key, {}).get("fuels", []))))
    for b in ("generation exceeds load (energy park?)", "sized to carry the load",
              "partial — load-carrying uncertain",
              "life-safety only; site is grid-dependent"):
        items = band.get(b, [])
        if not items:
            continue
        out += [f"### {b} ({len(items)})", ""]
        for r, cons, gen, nm, fuels in sorted(items, key=lambda x: -x[2]):
            out += [f"- **{gen:,.1f} MW** generation against {cons:,.1f} MW "
                    f"load ({r:.0%}) — {nm} — fuel: "
                    f"{', '.join(fuels) if fuels else '**not disclosed**'}"]
        out += [""]

    path = args.out or (ROOT / "data" / "reports" /
                        f"generation_integrity_{stamp:%Y-%m-%d_%H%M}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")

    print(f"{len(rows)} generation verdicts across {len(sites)} sites")
    print(f"  no fuel named: {no_fuel_rows} verdicts ({100*no_fuel_rows/max(len(rows),1):.0f}%), "
          f"{len(no_fuel_sites)} of {len(sites)} sites entirely")
    print(f"  count x rating: {arith_ok} correct, {len(arith_bad)} storing one unit")
    if survivors:
        print(f"  non-generation plant still present: {len(survivors)}")
    for f, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {f:22} {n} sites")
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
