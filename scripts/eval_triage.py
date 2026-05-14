"""Run the Stage 1 triage prompt over Luke's labelled round-01 sample and report
agreement against the ground truth.

Designed to scale: writes JSONL incrementally as each result lands, so a crash or
ctrl-C doesn't lose completed work. `--resume <file>` appends to an existing
JSONL and skips applications already evaluated.

Outputs:
  - JSONL at data/triage_labelling/eval_<model>_<date>.jsonl
    (one row per application; written immediately after each LLM call)
  - Markdown report at data/triage_labelling/eval_<model>_<date>.md
    (regenerated at end of run from the JSONL)

Usage:
  scripts/eval_triage.py                       # fresh run, default model
  scripts/eval_triage.py --model qwen3.5:9b    # try a specific model
  scripts/eval_triage.py --resume data/triage_labelling/eval_qwen3.5:9b_2026-05-14_1530.jsonl
  scripts/eval_triage.py --limit 5             # smoke-test on first 5 apps
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import triage
from dcp.llm import OllamaBackend


def normalise_label(rec: dict) -> dict:
    """Clean up known quirks in Luke's round-01 labels."""
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


def serialize_row(label: dict, verdict, error: str | None, secs: float) -> dict:
    return {
        "num": label["num"],
        "ref": label["ref"],
        "title": label["title"],
        "ground_truth": {
            "verdict": label["verdict"],
            "worth_deep_read": label["worth_deep_read"],
            "signals": label["signals"],
            "why": label["why"],
            "confidence": label["confidence"],
        },
        "llm": ({
            "verdict": verdict.verdict,
            "worth_deep_read": verdict.worth_deep_read,
            "signals": verdict.signals,
            "why": verdict.why,
            "confidence": verdict.confidence,
        } if verdict else None),
        "error": error,
        "seconds": secs,
    }


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="data/triage_labelling/round_01_labels.json")
    ap.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "mistral"))
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap applications evaluated (after skipping resume rows).")
    ap.add_argument("--timeout", type=float, default=180.0,
                    help="Per-call Ollama timeout in seconds (default 180).")
    ap.add_argument("--resume", type=Path, default=None,
                    help="Existing JSONL to extend; refs already in it are skipped.")
    ap.add_argument("--output", type=Path, default=None,
                    help="Override output path prefix (without extension).")
    args = ap.parse_args()

    labels_path = ROOT / args.labels
    labels = [normalise_label(r) for r in json.loads(labels_path.read_text())]

    # Output filenames
    when = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    if args.output:
        prefix = args.output
    elif args.resume:
        # Resume: write into the same JSONL as before; report is regenerated from it.
        prefix = args.resume.with_suffix("")
    else:
        prefix = ROOT / f"data/triage_labelling/eval_{args.model.replace(':', '_')}_{when}"
    jsonl_path = prefix.with_suffix(".jsonl")
    md_path = prefix.with_suffix(".md")

    # Resume: load any prior rows, build skip set
    existing = load_jsonl(jsonl_path)
    done_refs = {row["ref"] for row in existing}
    if existing:
        print(f"Resume: {len(existing)} rows already in {jsonl_path.name}, skipping those refs")

    # Filter to remaining + apply limit
    remaining = [l for l in labels if l["ref"] not in done_refs]
    if args.limit is not None:
        remaining = remaining[:args.limit]

    backend = OllamaBackend(model=args.model, request_timeout=args.timeout)
    print(f"Triage: {len(remaining)} apps to evaluate against {args.model!r} "
          f"(per-call timeout {args.timeout:.0f}s, parse-retry on)")
    if not remaining:
        print("Nothing to do.")
        # Still regenerate the report from existing rows below
    else:
        print(f"Writing to {jsonl_path.name} (incremental).\n")

    # Run, appending each row as it lands
    started = time.time()
    with jsonl_path.open("a") as jf:
        for i, label in enumerate(remaining, 1):
            app = {
                "ref": label["ref"],
                "council": label["council"],
                "description": label["description"],
            }
            t0 = time.time()
            verdict = None
            err = None
            try:
                verdict = triage.triage_application(app, backend)
            except ValueError as e:
                # parse_response raised even after the in-module retry
                err = f"parse_error: {e}"
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            elapsed = time.time() - t0
            row = serialize_row(label, verdict, err, elapsed)
            jf.write(json.dumps(row) + "\n")
            jf.flush()
            v_str = verdict.verdict if verdict else "ERR"
            gt = label["verdict"] or "—"
            match = "✓" if (verdict and v_str == gt) else "✗"
            print(f"  #{label['num']:2d} {label['title'][:38]:38s}  "
                  f"gt={gt:10s} llm={v_str:10s} {match}  {elapsed:5.1f}s")

    total_secs = time.time() - started
    if remaining:
        print(f"\nThis run: {len(remaining)} apps in {total_secs:.0f}s "
              f"({total_secs/len(remaining):.1f}s avg)")

    # ---- Aggregate from full JSONL (existing + this run) ----
    all_rows = load_jsonl(jsonl_path)
    n_total = len(all_rows)
    n_errs = sum(1 for r in all_rows if r["error"])

    def matched_pairs():
        for r in all_rows:
            if not r["llm"] or not r["ground_truth"]["verdict"]:
                continue
            yield r

    pairs = list(matched_pairs())
    verdict_match = sum(
        1 for r in pairs if r["ground_truth"]["verdict"] == r["llm"]["verdict"]
    )
    deep_pairs = [r for r in pairs if r["ground_truth"]["worth_deep_read"]]
    deep_match = sum(
        1 for r in deep_pairs if r["ground_truth"]["worth_deep_read"] == r["llm"]["worth_deep_read"]
    )

    classes = ["DC", "adjacent", "unrelated", "unknown"]
    cm = {gt: {pred: 0 for pred in classes} for gt in classes}
    for r in pairs:
        gt_v = r["ground_truth"]["verdict"]
        llm_v = r["llm"]["verdict"]
        if gt_v in classes and llm_v in classes:
            cm[gt_v][llm_v] += 1

    sig_scores = []
    for r in pairs:
        gt_sigs = {
            s.strip().lower()
            for s in (r["ground_truth"]["signals"] or "").split(",")
            if s.strip() and s.strip().lower() != "foxglove"
        }
        llm_sigs = {s.strip().lower() for s in (r["llm"]["signals"] or []) if s.strip()}
        sig_scores.append(jaccard(gt_sigs, llm_sigs))
    avg_jaccard = sum(sig_scores) / len(sig_scores) if sig_scores else 0.0

    # ---- Markdown report ----
    out = []
    out.append(f"# Triage eval: {args.model}\n")
    out.append(f"Last updated {dt.datetime.now().isoformat(timespec='seconds')}. "
               f"JSONL: `{jsonl_path.name}` ({n_total} rows).\n")
    out.append("\n## Headline numbers\n")
    out.append(f"- **{n_total}** applications evaluated, {n_errs} errors")
    if pairs:
        out.append(f"- **Verdict accuracy: {verdict_match}/{len(pairs)} = {100*verdict_match/len(pairs):.0f}%**")
    if deep_pairs:
        out.append(f"- **Deep-read accuracy: {deep_match}/{len(deep_pairs)} = {100*deep_match/len(deep_pairs):.0f}%**")
    out.append(f"- **Signal Jaccard average: {avg_jaccard:.2f}**")
    # Per-stage timing
    times = [r["seconds"] for r in all_rows if r["seconds"]]
    if times:
        out.append(f"- Mean per-call latency: {sum(times)/len(times):.1f}s "
                   f"(min {min(times):.1f}s, max {max(times):.1f}s)")
    out.append("")

    out.append("\n## Verdict confusion (ground truth → LLM)\n")
    out.append("|  | " + " | ".join(f"→{c}" for c in classes) + " | total |")
    out.append("|---|" + "|".join("---" for _ in classes) + "|---|")
    for gt in classes:
        row_total = sum(cm[gt].values())
        cells = " | ".join(str(cm[gt][p]) for p in classes)
        out.append(f"| **{gt}** | {cells} | {row_total} |")

    # Errors
    err_rows = [r for r in all_rows if r["error"]]
    if err_rows:
        out.append("\n## Errors\n")
        for r in err_rows:
            out.append(f"\n### #{r['num']}. {r['title']}\n")
            out.append(f"- Ref: `{r['ref']}`")
            out.append(f"- Error: `{r['error']}`")
            out.append(f"- Seconds: {r['seconds']:.1f}")

    # Disagreements
    out.append("\n## Disagreements\n")
    disagreements = [
        r for r in pairs
        if r["ground_truth"]["verdict"] != r["llm"]["verdict"]
    ]
    if not disagreements:
        out.append("\n_(none on verdict)_\n")
    for r in disagreements:
        gt = r["ground_truth"]
        llm = r["llm"]
        out.append(f"\n### #{r['num']}. {r['title']}\n")
        out.append(f"- Ref: `{r['ref']}`")
        out.append(f"- GT verdict: **{gt['verdict']}** / LLM: **{llm['verdict']}**")
        out.append(f"- GT deep-read: {gt['worth_deep_read']} / LLM: {llm['worth_deep_read']}")
        out.append(f"- GT confidence: {gt['confidence']} / LLM: {llm['confidence']}")
        out.append(f"- GT why: {gt['why']}")
        out.append(f"- LLM why: {llm['why']}")
        out.append(f"- GT signals: `{gt['signals']}`")
        out.append(f"- LLM signals: `{', '.join(llm['signals']) if llm['signals'] else '(none)'}`")

    md_path.write_text("\n".join(out))
    print(f"\nReport: {md_path}")
    print(f"JSONL : {jsonl_path}")


if __name__ == "__main__":
    main()
