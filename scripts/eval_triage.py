"""Run the Stage 1 triage prompt over Luke's labelled round-01 sample and
report agreement against the ground truth.

Outputs:
  - markdown report at data/triage_labelling/eval_<model>_<date>.md
  - per-case verdicts JSON at data/triage_labelling/eval_<model>_<date>.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import triage
from dcp.llm import OllamaBackend


def normalise_label(rec: dict) -> dict:
    """Clean up known quirks in Luke's round-01 labels.

    - "DC, adjacent" → "DC" (the primary classification)
    - "unknwon" → "unknown" (typo)
    - "____" (placeholder) → None (#8 was left unfilled)
    """
    out = dict(rec)
    v = out.get("verdict")
    if v == "DC, adjacent":
        out["verdict"] = "DC"
    elif v == "unknwon":
        out["verdict"] = "unknown"
    elif v == "____":
        out["verdict"] = None
    dr = out.get("worth_deep_read")
    if dr == "____":
        out["worth_deep_read"] = None
    return out


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="data/triage_labelling/round_01_labels.json")
    ap.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "mistral"))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    labels_path = ROOT / args.labels
    labels = [normalise_label(r) for r in json.loads(labels_path.read_text())]
    if args.limit is not None:
        labels = labels[:args.limit]

    backend = OllamaBackend(model=args.model)
    print(f"Running triage over {len(labels)} applications using model={args.model!r}")

    rows = []
    started = time.time()
    for i, label in enumerate(labels, 1):
        app = {
            "ref": label["ref"],
            "council": label["council"],
            "description": label["description"],
        }
        t0 = time.time()
        try:
            verdict = triage.triage_application(app, backend)
            err = None
        except Exception as e:
            verdict = None
            err = str(e)
        elapsed = time.time() - t0
        rows.append({"label": label, "verdict": verdict, "error": err, "secs": elapsed})
        v = verdict.verdict if verdict else "ERR"
        gt = label["verdict"] or "—"
        match = "✓" if (verdict and v == gt) else "✗"
        print(f"  #{label['num']:2d} {label['title'][:40]:40s}  gt={gt:10s} llm={v:10s} {match}  {elapsed:.1f}s")

    total_secs = time.time() - started
    print(f"\nTotal: {total_secs:.0f}s ({total_secs/len(labels):.1f}s avg)")

    # ---- Aggregate stats ----
    n_total = len(rows)
    n_errs = sum(1 for r in rows if r["error"])

    pairs = [(r["label"], r["verdict"]) for r in rows if r["verdict"] and r["label"]["verdict"]]
    verdict_match = sum(1 for l, v in pairs if l["verdict"] == v.verdict)
    deep_read_pairs = [(l, v) for l, v in pairs if l["worth_deep_read"]]
    deep_read_match = sum(1 for l, v in deep_read_pairs if l["worth_deep_read"] == v.worth_deep_read)

    classes = ["DC", "adjacent", "unrelated", "unknown"]
    cm = {gt: {pred: 0 for pred in classes} for gt in classes}
    for l, v in pairs:
        if l["verdict"] in classes and v.verdict in classes:
            cm[l["verdict"]][v.verdict] += 1

    sig_scores = []
    for l, v in pairs:
        gt_sigs = {s.strip().lower() for s in (l["signals"] or "").split(",") if s.strip() and s.strip().lower() != "foxglove"}
        llm_sigs = {s.strip().lower() for s in v.signals if s.strip()}
        sig_scores.append(jaccard(gt_sigs, llm_sigs))
    avg_jaccard = sum(sig_scores) / len(sig_scores) if sig_scores else 0.0

    # ---- Markdown report ----
    when = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    report_path = ROOT / f"data/triage_labelling/eval_{args.model}_{when}.md"
    json_path = ROOT / f"data/triage_labelling/eval_{args.model}_{when}.json"

    out = []
    out.append(f"# Triage eval: {args.model}\n")
    out.append(f"Run at {dt.datetime.now().isoformat(timespec='seconds')}, total {total_secs:.0f}s ({total_secs/n_total:.1f}s avg).\n")
    out.append("\n## Headline numbers\n")
    out.append(f"- **{n_total}** applications evaluated, {n_errs} errors")
    if pairs:
        out.append(f"- **Verdict accuracy: {verdict_match}/{len(pairs)} = {100*verdict_match/len(pairs):.0f}%**")
    if deep_read_pairs:
        out.append(f"- **Deep-read accuracy: {deep_read_match}/{len(deep_read_pairs)} = {100*deep_read_match/len(deep_read_pairs):.0f}%**")
    out.append(f"- **Signal Jaccard average: {avg_jaccard:.2f}**")
    out.append("")

    out.append("\n## Verdict confusion (ground truth → LLM)\n")
    out.append("|  | " + " | ".join(f"→{c}" for c in classes) + " | total |")
    out.append("|---|" + "|".join("---" for _ in classes) + "|---|")
    for gt in classes:
        row_total = sum(cm[gt].values())
        cells = " | ".join(str(cm[gt][p]) for p in classes)
        out.append(f"| **{gt}** | {cells} | {row_total} |")

    out.append("\n## Disagreements\n")
    for r in rows:
        l = r["label"]
        v = r["verdict"]
        if r["error"]:
            out.append(f"\n### #{l['num']}. {l['title']} — ERROR\n")
            out.append(f"```\n{r['error']}\n```")
            continue
        if not v:
            continue
        gt_v = l["verdict"]
        if gt_v and gt_v != v.verdict:
            out.append(f"\n### #{l['num']}. {l['title']}\n")
            out.append(f"- Ref: `{l['ref']}`")
            out.append(f"- GT verdict: **{gt_v}** / LLM: **{v.verdict}**")
            out.append(f"- GT deep-read: {l['worth_deep_read']} / LLM: {v.worth_deep_read}")
            out.append(f"- GT confidence: {l['confidence']} / LLM: {v.confidence}")
            out.append(f"- GT why: {l['why']}")
            out.append(f"- LLM why: {v.why}")
            out.append(f"- GT signals: `{l['signals']}`")
            out.append(f"- LLM signals: `{', '.join(v.signals)}`")
            out.append(f"- Description: {l['description'][:300]}{'…' if len(l['description'])>300 else ''}")

    report_path.write_text("\n".join(out))
    print(f"\nReport: {report_path}")

    json_path.write_text(json.dumps([
        {
            "num": r["label"]["num"],
            "ref": r["label"]["ref"],
            "ground_truth": {
                "verdict": r["label"]["verdict"],
                "worth_deep_read": r["label"]["worth_deep_read"],
                "signals": r["label"]["signals"],
                "why": r["label"]["why"],
                "confidence": r["label"]["confidence"],
            },
            "llm": ({
                "verdict": r["verdict"].verdict,
                "worth_deep_read": r["verdict"].worth_deep_read,
                "signals": r["verdict"].signals,
                "why": r["verdict"].why,
                "confidence": r["verdict"].confidence,
            } if r["verdict"] else None),
            "error": r["error"],
            "seconds": r["secs"],
        }
        for r in rows
    ], indent=2))
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
