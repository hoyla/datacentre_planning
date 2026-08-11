#!/usr/bin/env python3
"""Power adjudication via Claude Code subagents, for the figures that matter.

The batch adjudicator (scripts/adjudicate_power.py) speaks to the
Anthropic API, whose budget is spent. This is the same rubric and the
same prompt, run instead through Claude Code subagents — the same model,
reached by a different route, and tagged as such: verdicts land under
`claude-sonnet-5+subagent`, exactly as v1's extraction was tagged
`claude-opus-4-7+read-tool`. How a judgement was made is part of its
provenance.

Scope is deliberate. A validation probe over 229 already-adjudicated
figures put subagent-vs-API agreement at 94% on the full five-way
verdict and 95% on the only distinction a published chart cares about —
is this the site's own capacity or not. But it costs ~862 tokens per
figure, so the whole 6,297-figure backlog would be ~5.4M tokens, where
an OpenAI batch does the same work for a few dollars.

So this handles the **consequential** set: figures on sites that carry no
adjudicated capacity at all, where a verdict can move a site's headline
number rather than refine it. The long tail goes through the cheaper
route. Model continuity is bought where it changes what gets published.

The probe also found the one bias worth correcting: the subagent is
markedly less willing than the API to answer "unclear", and promoted
component-level equipment ratings (a cooling unit's datasheet figure, a
transformer's plate rating) to site capacity. The prompt below says so
explicitly, because a general instruction to "be strict" did not
prevent it.

    scripts/adjudicate_subagent.py --prepare --shards 6   # write shard files
    #   … launch one subagent per shard with PROMPT_FOR_WORKER …
    scripts/adjudicate_subagent.py --ingest               # read + store
    scripts/adjudicate_subagent.py --report               # what changed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

MODEL = "claude-sonnet-5+subagent"
PROMPT_VERSION = "power-1.0"          # identical rubric to the API run
SHARD_DIR = ROOT / "data" / "adjudication_shards"

TO_MW = {"mw": 1.0, "megawatt": 1.0, "megawatts": 1.0, "mwe": 1.0,
         "kw": 0.001, "kilowatt": 0.001, "kilowatts": 0.001,
         "gw": 1000.0, "gigawatt": 1000.0, "gigawatts": 1000.0}
APPARENT = {"mva", "kva"}

# Appended to the shared rubric for workers. Everything here answers a
# specific, measured failure from the probe rather than a general worry.
EXTRA_GUIDANCE = """
Two clarifications, from measured errors in an earlier run of this task:

1. **Equipment ratings are not site capacity.** A cooling unit's
   datasheet figure, a named transformer's plate rating, a manufacturer's
   product-range specification — these describe a component or a product,
   not the development's capacity. Verdict "unclear" unless the quote
   ties the figure to the development's own total load, connection or
   installed plant. An earlier run promoted several of these and each
   would have inflated a published capacity figure.

2. **"unclear" is the correct answer more often than feels comfortable.**
   The instruction to be strict is not rhetorical: a figure whose quote
   does not itself establish that it belongs to this development is
   "unclear", even when context makes it plausible. Under-claiming is
   recoverable by a later pass; a wrong site capacity in a published
   chart is not.

A figure that IS this development's own declared installed capacity —
for example an application form stating this scheme's solar or heat-pump
capacity — is site_capacity, with the appropriate quantity_type.
"""


def load_consequential(conn, include_refinements: bool = False) -> list[dict]:
    """Candidate figures on sites holding no adjudicated capacity.

    These are the ones where a verdict can change what a site reports,
    rather than add another figure beneath an existing one.

    `include_refinements` drops that restriction and takes every
    unadjudicated figure. The restriction exists because of volume, not
    principle: at ~862 tokens a figure the 6,297-figure backlog was 5.4M
    tokens, where an OpenAI batch did the same work for a few dollars. A
    small tail does not raise that question — 77 figures is ~66k tokens —
    and running them here keeps them on the same model as the primary
    adjudication instead of splitting one week's verdicts across two
    adjudicators for no reason but queue latency. Opt-in, so the default
    discipline stands.
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH capped AS (
              SELECT DISTINCT m.site_id
              FROM power_adjudication pa
              JOIN findings f ON f.id = pa.finding_id
              JOIN site_members m ON m.application_id = f.application_id
                                 AND m.retired_at IS NULL
              WHERE pa.verdict = 'site_capacity')
            SELECT DISTINCT f.application_id, a.application_ref,
                   coalesce(a.description, ''), f.id, f.document_id,
                   f.signal_type, f.value_number, f.value_unit,
                   coalesce(f.value_text, ''), coalesce(f.evidence_text, '')
            FROM findings f
            JOIN applications a ON a.id = f.application_id
            JOIN site_members m ON m.application_id = f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
            WHERE f.value_number IS NOT NULL
              AND lower(f.value_unit) = ANY(%s)
              AND (%s OR m.site_id NOT IN (SELECT site_id FROM capped))
              AND NOT EXISTS (
                    SELECT 1 FROM power_adjudication p
                    WHERE p.finding_id = f.id
                      AND p.prompt_version = %s)
            ORDER BY f.application_id, f.value_number DESC""",
            (list(TO_MW) + list(APPARENT), include_refinements,
             PROMPT_VERSION))
        rows = cur.fetchall()

    apps: dict[int, dict] = {}
    for (app_id, ref, desc, fid, doc_id, stype, num, unit,
         vtext, quote) in rows:
        app = apps.setdefault(app_id, {"application_id": app_id, "ref": ref,
                                       "desc": desc[:400], "figures": []})
        app["figures"].append({
            "finding_id": fid, "document_id": doc_id, "signal_type": stype,
            "value_number": float(num), "value_unit": unit,
            "value_text": vtext[:80], "evidence_text": quote[:300]})
    return list(apps.values())


def prepare(shards: int, include_refinements: bool = False) -> None:
    with db.connect() as conn:
        apps = load_consequential(conn, include_refinements)
    n_fig = sum(len(a["figures"]) for a in apps)
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    for p in SHARD_DIR.glob("shard_*.json"):
        p.unlink()
    # Whole applications per shard: the rubric asks "is this figure THIS
    # development's", which needs the application's other figures beside
    # it. Splitting an application across workers would remove exactly
    # the context the judgement is made from.
    buckets: list[list] = [[] for _ in range(shards)]
    for i, app in enumerate(sorted(apps, key=lambda a: -len(a["figures"]))):
        buckets[i % shards].append(app)          # round-robin by size
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        (SHARD_DIR / f"shard_{i}.json").write_text(json.dumps(bucket, indent=1))
    print(f"{len(apps)} applications, {n_fig} figures -> "
          f"{sum(1 for b in buckets if b)} shards in {SHARD_DIR}")
    for i, bucket in enumerate(buckets):
        if bucket:
            print(f"  shard_{i}.json: {len(bucket)} applications, "
                  f"{sum(len(a['figures']) for a in bucket)} figures")


def ingest() -> None:
    meta: dict[int, dict] = {}
    for p in sorted(SHARD_DIR.glob("shard_*.json")):
        for app in json.loads(p.read_text()):
            for f in app["figures"]:
                meta[f["finding_id"]] = {**f, "application_id":
                                         app["application_id"]}

    verdicts: dict[str, dict] = {}
    for p in sorted(SHARD_DIR.glob("verdicts_*.json")):
        try:
            verdicts.update(json.loads(p.read_text()))
        except Exception as exc:
            print(f"  could not read {p.name}: {exc}")

    inserted = skipped = 0
    with db.connect() as conn, conn.cursor() as cur:
        for fid_s, a in verdicts.items():
            fid = int(fid_s)
            m = meta.get(fid)
            if m is None:
                skipped += 1
                continue
            unit = (m["value_unit"] or "").lower()
            value_mw = unit_note = None
            if a.get("verdict") == "site_capacity":
                if unit in TO_MW:
                    value_mw = m["value_number"] * TO_MW[unit]
                elif unit in APPARENT:
                    unit_note = ("apparent power (kVA/MVA); not converted "
                                 "to MW — power factor unknown")
            cur.execute("""
                INSERT INTO power_adjudication (application_id, finding_id,
                    document_id, verdict, quantity_type, value_mw,
                    value_original, unit_original, unit_note, is_maximum,
                    reasoning, model, prompt_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (finding_id, model, prompt_version)
                DO NOTHING""",
                (m["application_id"], fid, m["document_id"],
                 a.get("verdict"), a.get("quantity_type"), value_mw,
                 m["value_number"], m["value_unit"], unit_note,
                 a.get("is_maximum"), (a.get("reasoning") or "")[:600],
                 MODEL, PROMPT_VERSION))
            inserted += cur.rowcount
        conn.commit()
    print(f"inserted {inserted} adjudications"
          + (f" ({skipped} unknown finding_ids)" if skipped else ""))


def report() -> None:
    """What the run actually changed, and what a human should look at."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT verdict, count(*) FROM power_adjudication
                       WHERE model=%s GROUP BY 1 ORDER BY 2 DESC""", (MODEL,))
        print("verdicts stored by this route:")
        for v, n in cur.fetchall():
            print(f"  {v:16} {n:>6,}")
        cur.execute("""SELECT count(DISTINCT s.site_key)
            FROM power_adjudication pa
            JOIN findings f ON f.id=pa.finding_id
            JOIN site_members m ON m.application_id=f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id=m.site_id AND s.retired_at IS NULL
            WHERE pa.model=%s AND pa.verdict='site_capacity'""", (MODEL,))
        print(f"\nsites gaining a capacity figure: {cur.fetchone()[0]}")
        # Every promotion to site_capacity, for the hand check the probe
        # showed is warranted.
        cur.execute("""SELECT s.site_key, pa.value_mw, pa.unit_original,
                              pa.quantity_type, left(pa.reasoning, 90)
            FROM power_adjudication pa
            JOIN findings f ON f.id=pa.finding_id
            JOIN site_members m ON m.application_id=f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id=m.site_id AND s.retired_at IS NULL
            WHERE pa.model=%s AND pa.verdict='site_capacity'
            ORDER BY pa.value_mw DESC NULLS LAST LIMIT 25""", (MODEL,))
        print("\nlargest new site_capacity verdicts — CHECK THESE BY HAND:")
        for key, mw, unit, qt, why in cur.fetchall():
            shown = f"{mw:g} MW" if mw is not None else f"(as {unit})"
            print(f"  {shown:>12}  {qt or '—':18} {key[:40]}")
            print(f"                {why}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--shards", type=int, default=6)
    ap.add_argument("--include-refinements", action="store_true",
                    help="Also take figures on sites that already hold "
                         "an adjudicated capacity. For a small tail only "
                         "— see load_consequential.")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.prepare:
        prepare(args.shards, args.include_refinements)
    elif args.ingest:
        ingest()
    elif args.report:
        report()
    else:
        ap.error("pass --prepare, --ingest or --report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
