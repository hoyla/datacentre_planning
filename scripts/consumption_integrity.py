#!/usr/bin/env python3
"""What each site's power figure is worth, judged against its siblings.

Power consumption is the figure this investigation exists to establish,
and a single number in a column tells a reporter nothing about how much
weight it will bear. This puts every site's consumption figure beside the
other signals the same documents produced — the grid connection sought,
the standby generation installed, the floorspace — and says whether they
agree.

The point is not to pick a winner. It is to stop the dataset asserting
more than it knows: a 120 MW IT load corroborated by a 130 MW grid
connection is a different claim from a 120 MW IT load contradicted by a
30 MW connection, and a column showing "120" for both is misreporting one
of them.

Four statuses, from the site's own evidence only:

**corroborated** — a second independent signal agrees within tolerance.
  The grid connection covers the load, or generation is sized near it.

**uncorroborated** — one figure, nothing to check it against. Common and
  not a fault; it simply means the number rests on a single reading.

**contradicted** — two signals that cannot both be right. A grid
  connection materially below the consumption it must carry is the
  clearest case: you cannot draw 1,100 MW through a 30 MW connection.
  These are listed individually, because each is either an extraction
  error or a genuinely odd scheme, and only a person can say which.

**partial-generation** — generation far below consumption. Deliberately
  NOT called a contradiction, because it is usually true and it is
  interesting: a 120 MW hyperscale site with 2.9 MW of standby plant is
  telling you it has life-safety backup only and is wholly grid
  dependent. The v1 assumption that standby is sized to full load holds
  for enterprise halls and fails for hyperscale.

Tolerances are deliberately loose. Planning figures are rounded, phased
and inconsistent between documents by nature; this flags what cannot be
reconciled, not what merely differs.

Usage:
    scripts/consumption_integrity.py [--out FILE] [--min-mw 0]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

# A grid connection below this fraction of stated consumption cannot be
# reconciled — the site could not draw what it says it draws.
GRID_SHORTFALL = 0.8
# Generation within this band of consumption reads as "sized to carry the
# load", the classic full-redundancy pattern.
GEN_CORROBORATES = (0.8, 1.5)
# Below this, generation is life-safety only rather than load-carrying.
GEN_PARTIAL = 0.5

SQL = r"""
WITH cons AS (
  -- The single finding that supplies each site's headline consumption
  -- figure, with its own quote. Scope is a property of THAT finding:
  -- flagging a site because some other row said "per building" marked
  -- campuses whose headline was already the correct campus total.
  SELECT DISTINCT ON (s.site_key)
         s.site_key, pa.value_mw::float AS cons_mw, f.evidence_text
  FROM power_adjudication pa
  JOIN findings f ON f.id = pa.finding_id
  JOIN site_members m ON m.application_id = f.application_id
                     AND m.retired_at IS NULL
  JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
  WHERE pa.verdict = 'site_capacity'
    AND pa.quantity_type IN ('it_load','total_site')
  ORDER BY s.site_key, pa.value_mw DESC),
cap AS (
  SELECT s.site_key, s.display_name,
         max(pa.value_mw) FILTER (WHERE pa.quantity_type='it_load')::float     AS it_load,
         max(pa.value_mw) FILTER (WHERE pa.quantity_type='total_site')::float  AS total_site,
         max(pa.value_mw) FILTER (WHERE pa.quantity_type='grid_connection')::float AS grid,
         max(pa.value_mw) FILTER (WHERE pa.quantity_type='onsite_generation')::float AS gen,
         max(pa.value_mw) FILTER (WHERE pa.quantity_type='energy_storage')::float AS storage,
         max(pa.value_mw) FILTER (WHERE pa.quantity_type='thermal_input')::float AS thermal,
         count(*) FILTER (WHERE pa.quantity_type IN ('it_load','total_site')) AS n_cons
  FROM power_adjudication pa
  JOIN findings f ON f.id = pa.finding_id
  JOIN site_members m ON m.application_id = f.application_id
                     AND m.retired_at IS NULL
  JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
  WHERE pa.verdict = 'site_capacity' AND s.retired_at IS NULL
  GROUP BY 1,2)
SELECT cap.site_key, cap.display_name, cap.it_load, cap.total_site,
       cap.grid, cap.gen, cap.storage, cap.thermal, cap.n_cons,
       units.n_units, units.unit_quote, councils.n_councils,
       coalesce(fleet.understated, false) AS gen_understated,
       coalesce(
         cons.evidence_text ~* '(each|per) (building|hall|data hall|unit|block|phase)'
         AND NOT cons.evidence_text ~* 'across the (campus|site|development)|in total|overall|total (it load|load|capacity)|combined',
         false) AS partial_scope
FROM cap
LEFT JOIN cons ON cons.site_key = cap.site_key
-- How many buildings the documents say there are. A per-building figure
-- is only a floor until this is known; with it, the site's implied total
-- is arithmetic the reader can check rather than a number we invented.
LEFT JOIN LATERAL (
  SELECT CASE lower((regexp_match(f.evidence_text,
           '\y(two|three|four|five|six|[0-9]+)\s+(?:no\.?\s+)?(?:data centre |dc )?buildings\y', 'i'))[1])
           WHEN 'two' THEN 2 WHEN 'three' THEN 3 WHEN 'four' THEN 4
           WHEN 'five' THEN 5 WHEN 'six' THEN 6
           ELSE nullif(regexp_replace((regexp_match(f.evidence_text,
                '\y([0-9]+)\s+(?:no\.?\s+)?(?:data centre |dc )?buildings\y','i'))[1],
                '[^0-9]','','g'),'')::int END AS n_units,
         left(regexp_replace(f.evidence_text, E'\\s+',' ','g'), 150) AS unit_quote
  FROM findings f
  JOIN site_members m2 ON m2.application_id = f.application_id AND m2.retired_at IS NULL
  JOIN sites s2 ON s2.id = m2.site_id AND s2.site_key = cap.site_key
  WHERE f.evidence_text ~* '\y(two|three|four|five|six|[0-9]+)\s+(no\.?\s+)?(data centre |dc )?buildings\y'
  LIMIT 1) units ON true
-- Signals drawn from applications in different planning authorities are
-- a clustering question before they are a data question: the 1km rule
-- can merge two schemes that merely stand near each other.
-- Does any quote on this site describe a FLEET whose per-unit rating is
-- what got recorded? "38 no. 2,640kW generator units" beside a stored
-- 2.9 MW means the column holds one machine, not the site's plant.
LEFT JOIN LATERAL (
  SELECT bool_or(f3.evidence_text ~* '[0-9]{1,4}\s*(no\.?|nr|x|×)\s*[,\s]*[0-9,]+(\.[0-9]+)?\s*(MW|kW|kWe|MWe)\y')
         AS understated
  FROM power_adjudication pa3
  JOIN findings f3 ON f3.id = pa3.finding_id
  JOIN site_members m4 ON m4.application_id = f3.application_id AND m4.retired_at IS NULL
  JOIN sites s4 ON s4.id = m4.site_id AND s4.site_key = cap.site_key
  WHERE pa3.verdict='site_capacity' AND pa3.quantity_type='onsite_generation') fleet ON true
LEFT JOIN LATERAL (
  SELECT count(DISTINCT split_part(a2.application_ref, '/', 1)) AS n_councils
  FROM site_members m3
  JOIN applications a2 ON a2.id = m3.application_id
  JOIN sites s3 ON s3.id = m3.site_id AND s3.site_key = cap.site_key
  WHERE m3.retired_at IS NULL) councils ON true
WHERE cap.it_load IS NOT NULL OR cap.total_site IS NOT NULL
   OR cap.grid IS NOT NULL OR cap.gen IS NOT NULL
ORDER BY coalesce(cap.it_load, cap.total_site, cap.grid, cap.gen) DESC NULLS LAST
"""


def classify(cons, grid, gen, partial_scope=False, n_units=None,
             unit_quote=None, n_councils=1, gen_understated=False,
             it=None, tot=None):
    """(status, note) for one site's consumption figure."""
    if cons is None:
        return ("no-consumption-figure",
                "No consumption figure; other power signals only.")
    # IT load is a component of total site demand -- total is IT plus
    # cooling and overhead -- so an IT load above a site's own stated
    # total is impossible, not merely surprising. West London reached
    # 2,240 MW against its own stated 342 MW maximum, from a quote OCR
    # had eaten ("thi propo al would contribute of 2240MW"), which the
    # verbatim gate passed because it matches the damaged source exactly.
    if it is not None and tot is not None and it > tot * 1.05:
        return ("impossible-components",
                f"IT load {it:,.1f} MW exceeds this site's own stated "
                f"total demand of {tot:,.1f} MW. Total includes IT load "
                f"plus cooling and overhead, so one of the two figures is "
                f"wrong -- check both quotes before using either. A "
                f"garbled OCR quote is the usual cause.")
    # Scope outranks corroboration. A figure the documents describe as
    # per-building or per-phase is not this site's consumption, and
    # saying it is understates the site — which for this investigation
    # is as much a misreport as overstating it. Northumberland reads
    # "each building will provide approximately 72MW" beside a
    # whole-scheme figure of 1,100MW; a reader given 72 has been told
    # something false about a very large site.
    if partial_scope and n_units and n_units > 1:
        # The corpus holds both halves: a per-unit figure and a count of
        # units. Multiplying them is arithmetic the reader can check
        # against two quotes, so the implied total is stated — as an
        # implication, never as a disclosed figure.
        return ("scope-resolved",
                f"Documents give {cons:,.1f} MW per building and state "
                f"{n_units} buildings, implying about "
                f"{cons * n_units:,.0f} MW for the site. The {cons:,.1f} MW "
                f"in the capacity column is per building, not the site. "
                f"Building count from: \"{(unit_quote or '')[:110]}\"")
    if partial_scope:
        return ("scope-uncertain",
                f"The quote behind this {cons:,.1f} MW figure describes a "
                f"building, hall or phase rather than the whole site. The "
                f"site total may be a multiple of it, and this dataset "
                f"does not reliably know how many units are proposed. "
                f"Treat as a floor for the site, not its capacity.")
    checks, notes = [], []
    if grid is not None:
        if grid < cons * GRID_SHORTFALL and (n_councils or 1) > 1:
            return ("possible-clustering-artefact",
                    f"Grid connection {grid:,.1f} MW is below the "
                    f"{cons:,.1f} MW consumption — but this site's "
                    f"applications span {n_councils} planning authorities, "
                    f"so the two figures may describe different schemes "
                    f"merged by the 1km proximity rule. A site-definition "
                    f"question before a data one.")
        if grid < cons * GRID_SHORTFALL:
            return ("contradicted",
                    f"Grid connection {grid:,.1f} MW is below the "
                    f"{cons:,.1f} MW this site says it will draw — the two "
                    f"cannot both be right.")
        checks.append("grid")
        notes.append(f"grid connection {grid:,.1f} MW covers it")
    if gen is not None and cons > 0:
        ratio = gen / cons
        if GEN_CORROBORATES[0] <= ratio <= GEN_CORROBORATES[1]:
            checks.append("generation")
            notes.append(f"standby generation {gen:,.1f} MW is sized to "
                         f"carry the load ({ratio:.0%})")
        elif ratio < GEN_PARTIAL:
            # Only if the generation figure is the site's fleet and not
            # one machine's spec sheet. Amazon Didcot recorded 2.9 MW
            # from "Mechanical Generator - 2,873 kW" while the same
            # documents say "38 no. 2,640kW generator units per
            # building" — about 100 MW. Called grid-dependent on the
            # smaller number, the dataset told a reporter the opposite
            # of what the application says.
            if gen_understated:
                notes.append(f"recorded generation {gen:,.1f} MW appears "
                             f"to be a single unit: the documents describe "
                             f"a fleet, so the site's real standby capacity "
                             f"is higher and its grid-dependence cannot be "
                             f"judged from this figure")
                return ("generation-understated", "; ".join(notes))
            notes.append(f"standby generation {gen:,.1f} MW is only "
                         f"{ratio:.0%} of load — life-safety backup, not "
                         f"load-carrying; the site is grid-dependent")
            if not checks:
                return ("partial-generation", "; ".join(notes))
        else:
            notes.append(f"standby generation {gen:,.1f} MW exceeds load "
                         f"({ratio:.0%})")
    if checks:
        return ("corroborated", "; ".join(notes))
    return ("uncorroborated",
            "Single reading; no second signal in this site's documents to "
            "check it against." + (" " + "; ".join(notes) if notes else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--min-mw", type=float, default=0.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(SQL)
        rows = cur.fetchall()

    buckets: dict[str, list] = {}
    for (key, name, it, tot, grid, gen, storage, thermal, n_cons,
         n_units, unit_quote, n_councils, gen_understated,
         partial_scope) in rows:
        # The larger of the two, not it_load-by-preference. A campus
        # stating 72 MW per building and 1,100 MW overall has both, and
        # preferring the IT-load column reported the smaller as the
        # site's consumption.
        cons = max([v for v in (it, tot) if v is not None], default=None)
        if cons is not None and cons < args.min_mw:
            continue
        status, note = classify(cons, grid, gen, partial_scope,
                                n_units, unit_quote, n_councils,
                                gen_understated, it, tot)
        buckets.setdefault(status, []).append(
            (key, name, cons, it, tot, grid, gen, storage, thermal,
             n_cons, note))

    stamp = dt.datetime.now(dt.timezone.utc)
    order = ["impossible-components", "contradicted", "generation-understated",
             "possible-clustering-artefact",
             "scope-resolved", "scope-uncertain", "partial-generation",
             "corroborated", "uncorroborated", "no-consumption-figure"]
    total = sum(len(v) for v in buckets.values())
    out = [f"# Consumption integrity — {stamp:%Y-%m-%d %H:%M} UTC", "",
           f"{total} sites carry at least one adjudicated power figure.", ""]
    out += [f"- **{s}**: {len(buckets.get(s, []))}" for s in order
            if buckets.get(s)]
    out += ["",
            "Corroboration is judged only from the site's own documents. "
            "A figure being uncorroborated is not a doubt about it — most "
            "applications state their load once — but it is the difference "
            "between one reading and two that agree, and a reporter "
            "quoting the number deserves to know which they have.", ""]

    for status in order:
        items = buckets.get(status, [])
        if not items:
            continue
        out += [f"## {status} ({len(items)})", ""]
        for (key, name, cons, it, tot, grid, gen, storage, thermal,
             n_cons, note) in items:
            head = f"{cons:,.1f} MW" if cons is not None else "no figure"
            out += [f"### {head} — {name or key}", f"- site `{key}`"]
            bits = []
            if it is not None: bits.append(f"IT load {it:,.1f}")
            if tot is not None: bits.append(f"total site {tot:,.1f}")
            if grid is not None: bits.append(f"grid {grid:,.1f}")
            if gen is not None: bits.append(f"generation {gen:,.1f}")
            if storage is not None: bits.append(f"storage {storage:,.1f}")
            if thermal is not None: bits.append(f"thermal {thermal:,.1f}")
            out += [f"- signals (MW): {' · '.join(bits)}",
                    f"- {note}", ""]

    path = args.out or (ROOT / "data" / "reports" /
                        f"consumption_integrity_{stamp:%Y-%m-%d_%H%M}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")

    print(f"{total} sites with an adjudicated power figure")
    for s in order:
        if buckets.get(s):
            print(f"  {s:22} {len(buckets[s]):>4}")
    print(f"report: {path}")
    if buckets.get("contradicted"):
        print("\ncontradictions — each is an extraction error or an odd "
              "scheme, and only a person can say which:")
        for (key, name, cons, *_rest, note) in buckets["contradicted"]:
            print(f"  {cons:>9,.1f} MW  {(name or key)[:44]}")
            print(f"             {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
