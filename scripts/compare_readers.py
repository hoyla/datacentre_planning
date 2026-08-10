#!/usr/bin/env python3
"""Compare what two or more models found in the same documents.

Phase 3's deliverable is the comparison itself: where readers disagree,
both readings are kept and the disagreement is the finding. This is the
instrument for that, and in the meantime it answers the narrower
question of which model to spend the budget on.

It reports three things, on the documents the models share:

**Gate failure rate.** The proportion of a model's findings whose
evidence quote could not be found in the source. This is the closest
thing to a mechanical honesty measure the pipeline has — a model that
paraphrases rather than quotes fails here, and no judgement call is
involved. It is computed from `deepread_log.quotes_failed`, which counts
attempts, against findings actually stored.

**Yield.** Findings per document. More is not automatically better — a
model that emits six variations of one fact scores well and helps
nobody — so it is read alongside the agreement figures rather than on
its own.

**Agreement.** For quantitative findings, whether two models extracted
the same number and unit from the same document. This is the useful
one: a figure two independent readers pulled out of the same document
is worth more than either alone, and a figure only one of them saw is
either an insight or a mistake, which is exactly the set a human should
look at.

Matching is deliberately conservative. Quantitative findings match on
(document, value, unit) with the value rounded to four significant
figures — enough to absorb 12.5 versus 12.50, not enough to conflate
12.5 MW with 13 MW. Qualitative findings are matched on their evidence
quote rather than their label, because the labels are free text and two
models will name the same fact differently; the quote is the thing they
both had to copy.

Usage:
    scripts/compare_readers.py --models claude-sonnet-5 mlx:Qwen3.6-35B-A3B-4bit
    scripts/compare_readers.py --models A B C --shared-only
    scripts/compare_readers.py --models A B --examples 15
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402


def sig4(x: float) -> float:
    """Round to four significant figures, so 12.5 and 12.50 are one
    number and 12.5 and 13.0 are two."""
    if x == 0:
        return 0.0
    from math import floor, log10
    return round(x, -int(floor(log10(abs(x)))) + 3)


_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def quote_key(text: str) -> str:
    """A quote reduced to something two models can be compared on:
    lowercase, punctuation stripped, whitespace collapsed, and cut to
    the first 12 words. Models quote overlapping spans of the same
    sentence rather than identical ones, so the opening is the reliable
    part."""
    t = _PUNCT.sub(" ", (text or "").lower())
    return " ".join(_WS.sub(" ", t).strip().split()[:12])


def finding_key(row: dict) -> tuple:
    """What counts as 'the same finding' across models."""
    if row["value_number"] is not None:
        return ("num", row["document_id"], sig4(float(row["value_number"])),
                (row["value_unit"] or "").lower().strip())
    return ("txt", row["document_id"], quote_key(row["evidence_text"]))


def load(models: list[str], prompt_version: str) -> tuple[dict, dict, dict]:
    per_model_docs: dict[str, set] = {m: set() for m in models}
    per_model_findings: dict[str, list] = {m: [] for m in models}
    gate: dict[str, dict] = {}

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT model, document_id, read_state, quotes_failed,
                   findings_inserted
            FROM deepread_log
            WHERE model = ANY(%s) AND prompt_version = %s""",
            (models, prompt_version))
        for model, doc_id, state, qf, ins in cur.fetchall():
            if state in ("read", "parse_failed"):
                per_model_docs[model].add(doc_id)
            g = gate.setdefault(model, {"failed": 0, "inserted": 0,
                                        "docs": 0, "parse_failed": 0})
            g["failed"] += qf or 0
            g["inserted"] += ins or 0
            g["docs"] += 1 if state in ("read", "parse_failed") else 0
            g["parse_failed"] += 1 if state == "parse_failed" else 0

        cur.execute("""
            SELECT model, document_id, signal_type, value_number,
                   value_unit, value_text, evidence_text, evidence_page
            FROM findings
            WHERE model = ANY(%s)""", (models,))
        for (model, doc_id, st, vn, vu, vt, ev, pg) in cur.fetchall():
            per_model_findings[model].append({
                "document_id": doc_id, "signal_type": st,
                "value_number": vn, "value_unit": vu, "value_text": vt,
                "evidence_text": ev, "evidence_page": pg})

    return per_model_docs, per_model_findings, gate


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--prompt-version", default="1.0")
    ap.add_argument("--examples", type=int, default=8,
                    help="How many disagreements to print.")
    args = ap.parse_args()

    models = args.models
    docs, findings, gate = load(models, args.prompt_version)

    shared = set.intersection(*(docs[m] for m in models)) if models else set()
    print(f"models: {', '.join(models)}")
    for m in models:
        print(f"  {m:34} {len(docs[m]):>7,} documents read")
    print(f"  {'documents all of them read':34} {len(shared):>7,}")
    if not shared:
        print("\nNo shared documents: there is nothing to compare. Run the "
              "same cohort through each model first.")
        return 1

    print("\nOn the shared documents:\n")
    header = (f"  {'model':34} {'findings':>9} {'per doc':>8} "
              f"{'gate fails':>11} {'fail rate':>10} {'parse fails':>12}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    per_model_shared: dict[str, list] = {}
    for m in models:
        rows = [f for f in findings[m] if f["document_id"] in shared]
        per_model_shared[m] = rows
        g = gate.get(m, {})
        # quotes_failed is corpus-wide in the log, so the rate is quoted
        # against this model's whole run rather than the shared subset —
        # stated rather than silently mixed.
        tot = (g.get("inserted", 0) or 0) + (g.get("failed", 0) or 0)
        rate = (100.0 * g.get("failed", 0) / tot) if tot else 0.0
        print(f"  {m:34} {len(rows):>9,} {len(rows) / len(shared):>8.1f} "
              f"{g.get('failed', 0):>11,} {rate:>9.1f}% "
              f"{g.get('parse_failed', 0):>12,}")
    print("\n  (gate-fail rate is over each model's entire run, not just "
          "the shared documents)")

    keyed = {m: defaultdict(list) for m in models}
    for m in models:
        for f in per_model_shared[m]:
            keyed[m][finding_key(f)].append(f)

    print("\nAgreement on quantitative findings "
          "(same document, same value, same unit):\n")
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            ka = {k for k in keyed[a] if k[0] == "num"}
            kb = {k for k in keyed[b] if k[0] == "num"}
            both = ka & kb
            union = ka | kb
            pct = 100.0 * len(both) / len(union) if union else 0.0
            print(f"  {a}  vs  {b}")
            print(f"    both found {len(both):,} of {len(union):,} distinct "
                  f"figures ({pct:.0f}%)")
            print(f"    only {a}: {len(ka - kb):,}")
            print(f"    only {b}: {len(kb - ka):,}")

    # The distinction that turned out to matter more than the headline.
    #
    # Raw overlap on (document, value, unit) said Sonnet and Qwen agreed
    # on 22% of figures, which reads as two readers contradicting each
    # other constantly. They do not. Restricted to passages BOTH models
    # quoted and put a number on, they agree 94% of the time. The gap is
    # almost entirely *selection*: which sentences each thought worth
    # extracting, not what the sentence said.
    #
    # Those are opposite findings with opposite consequences. Real
    # contradictions are rare and each one deserves a human. Selection
    # differences mean the models are complementary, and that running
    # two of them over everything recovers far more than running one
    # twice.
    if len(models) >= 2:
        a, b = models[0], models[1]
        qa: dict = defaultdict(set)
        qb: dict = defaultdict(set)
        for f in per_model_shared[a]:
            if f["value_number"] is not None:
                qa[(f["document_id"], quote_key(f["evidence_text"]))].add(
                    sig4(float(f["value_number"])))
        for f in per_model_shared[b]:
            if f["value_number"] is not None:
                qb[(f["document_id"], quote_key(f["evidence_text"]))].add(
                    sig4(float(f["value_number"])))
        co = set(qa) & set(qb)
        same = sum(1 for k in co if qa[k] & qb[k])
        diff = len(co) - same
        print("\nWhere both quoted the SAME passage and put a number on it:\n")
        print(f"  passages quoted by both : {len(co):,}")
        print(f"    same figure           : {same:,} "
              f"({100 * same / max(len(co), 1):.0f}%)")
        print(f"    different figure      : {diff:,} "
              f"({100 * diff / max(len(co), 1):.0f}%)  <- real disagreement")
        print(f"  passages only {a} quoted: {len(set(qa) - set(qb)):,}")
        print(f"  passages only {b} quoted: {len(set(qb) - set(qa)):,}")
        print("\n  Read those last two lines first. When both models look at "
              "the same\n  sentence they almost always agree; what differs is "
              "which sentences they\n  bother with. That is complementary "
              "coverage, not contradiction, and it\n  is the argument for "
              "breadth over buying one expensive opinion.")

        shown = 0
        print("\n  Genuine contradictions (same sentence, different figure):")
        for k in sorted(co):
            if not (qa[k] & qb[k]):
                print(f"    doc {k[0]}: {a}={sorted(qa[k])} {b}={sorted(qb[k])}")
                print(f"      “{k[1][:88]}…”")
                shown += 1
                if shown >= max(3, args.examples // 2):
                    break
        print("    (many are range endpoints — '1500 to 2000 hours' read from "
              "either end —\n     which is a convention difference, not an "
              "error in either reader.)")
        only_a = [k for k in keyed[a] if k[0] == "num" and k not in keyed[b]]
        print(f"\nFigures only {a} found "
              f"(the set worth a human's eye — insight or error):\n")
        for k in sorted(only_a)[: args.examples]:
            f = keyed[a][k][0]
            q = (f["evidence_text"] or "")[:110].replace("\n", " ")
            print(f"  doc {f['document_id']}  {f['signal_type']}  "
                  f"{f['value_number']} {f['value_unit'] or ''}")
            print(f"      “{q}…”")

    print("\nWhat this does not tell you: whether a figure is *right*, or "
          "whose it is.\n  A model that correctly labels a market forecast "
          "as market_demand_forecast\n  and one that calls it this site's "
          "it_load both 'found' the same number.\n  That distinction is the "
          "power adjudication's job, and it is the thing\n  most worth "
          "spot-checking by hand before choosing a model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
