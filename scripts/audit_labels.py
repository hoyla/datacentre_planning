#!/usr/bin/env python3
"""Does a finding's family match what the finding says? (§4.1e)

The extractor asked a model to name what it had found in its own words,
and 54,044 distinct labels came back; `signal_family` is the 25-value
canonical index over them. A row can be wrong at either step, and the
family alone does not show it — which is why Watford's evidence leads
with `it_load — Existing tree cover, the enclosed nature of the existing
views…`, landscape prose under a power family, promoted because it was
long.

READER_REDESIGN_PLAN §7a builds the site page's evidence list "excluding
rows the 2.3 label audit flags". This is that audit. It never writes to
`signal_type` or `signal_family`: the extractor's label is the record of
what the extractor said, and overwriting the thing under audit audits
nothing. Verdicts land in `finding_label_audit` beside it.

**Scope is the rows a reader sees**, not the corpus: the same query the
reader runs, 40 findings per site, 10,605 rows. Auditing a million rows
to change what is shown on ten thousand would be a month of tokens for
no change to any page.

    scripts/audit_labels.py --sample     # the sheet, blank
    scripts/audit_labels.py --run        # the model, same rows
    scripts/audit_labels.py --score      # the two, compared
    scripts/audit_labels.py --batch      # what a full run would send
    scripts/audit_labels.py --batch --submit

The sample is chosen, not random: every family that appears, plus the
class the review found by hand — a power family, no figure, and enough
prose to have been promoted by length.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from dcp import db, signal_families

_spec = importlib.util.spec_from_file_location(
    "adjudicate_power", ROOT / "scripts" / "adjudicate_power.py")
_ap = importlib.util.module_from_spec(_spec)
sys.modules["adjudicate_power"] = _ap
_spec.loader.exec_module(_ap)

PROMPT = _ap.LABEL_AUDIT_PROMPT
SCHEMA = _ap.LABEL_AUDIT_SCHEMA
PROMPT_VERSION = _ap.LABEL_AUDIT_PROMPT_VERSION

OUT_DIR = ROOT / "data" / "label_audit_sample"
SAMPLE_SIZE = 60
# Short rows and a short answer each: forty per request rather than the
# twenty a generation figure needs, because there is no passage to send.
FINDINGS_PER_REQUEST = 40
MAX_COMPLETION_TOKENS = 32000
VERDICTS = ("fits", "does_not_fit", "unclear")

# The reader's own selection, so the audit covers exactly the rows a
# reader can see. Read out of export_reader rather than copied, because
# two copies of this query would drift and the audit would then be of a
# set nobody looks at.
_READER = (ROOT / "scripts" / "export_reader.py").read_text(encoding="utf-8")
RENDERED_SQL = _READER.split('FINDINGS_SQL = """')[1].split('"""')[0]
FINDINGS_PER_SITE = 40


def load_rendered(conn) -> list[dict]:
    """Every finding the reader renders, with the family it is filed
    under and the id the audit is keyed on."""
    with conn.cursor() as cur:
        # The reader's own query, unmodified. It carries f.id through so
        # a verdict can be joined to a row; an earlier version of this
        # function rewrote the SQL with string replacement to add it,
        # which is a copy that drifts the moment the reader's ranking
        # changes.
        cur.execute(RENDERED_SQL, (FINDINGS_PER_SITE,))
        rows = cur.fetchall()
    return [{"site_key": r[0], "signal_type": r[1], "value_text": r[2],
             "value_number": r[3], "value_unit": r[4], "verdict": r[5],
             "signal_family": r[6], "finding_id": r[7]} for r in rows]


def choose_sample(rows: list[dict], size: int = SAMPLE_SIZE) -> list[dict]:
    """One row per family that appears, then the suspect class, then the
    longest remaining — deterministic, so the sheet is stable.

    The suspect class is the shape the review found by hand: a power
    family, no figure, and long enough prose to have been promoted by
    the length ranking. If the audit cannot catch those it is not worth
    running.
    """
    by_id = {r["finding_id"]: r for r in rows}
    chosen: dict[int, str] = {}
    for fam in sorted({r["signal_family"] for r in rows}):
        fam_rows = sorted((r for r in rows if r["signal_family"] == fam),
                          key=lambda r: (-len(r["value_text"] or ""),
                                         r["finding_id"]))
        if fam_rows:
            chosen.setdefault(fam_rows[0]["finding_id"], f"the {fam} family")
    suspect = sorted(
        (r for r in rows
         if r["signal_family"] in ("power_demand", "power_generation", "power_grid")
         and r["value_number"] is None and len(r["value_text"] or "") > 160),
        key=lambda r: (-len(r["value_text"] or ""), r["finding_id"]))
    for r in suspect:
        chosen.setdefault(r["finding_id"], "power family, no figure, long prose")
    for r in sorted(rows, key=lambda r: (-len(r["value_text"] or ""),
                                         r["finding_id"])):
        if len(chosen) >= size:
            break
        chosen.setdefault(r["finding_id"], "longest remaining")
    return [{**by_id[fid], "why_in_sample": why}
            for fid, why in list(chosen.items())[:size]]


SHEET_COLUMNS = ("row", "finding_id", "site_key", "family", "label",
                 "why_in_sample", "text", "verdict", "suggested_family",
                 "note")


def write_sheet(rows: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{PROMPT_VERSION}_sheet.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"row": i, "finding_id": r["finding_id"],
                        "site_key": r["site_key"],
                        "family": r["signal_family"], "label": r["signal_type"],
                        "why_in_sample": r["why_in_sample"],
                        "text": " ".join((r["value_text"] or "").split()),
                        "verdict": "", "suggested_family": "", "note": ""})
    return path


def _client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set (add it to .env)")
    return OpenAI()


def ask_chunk(client, chunk: list[dict], model: str,
              effort: str) -> tuple[dict[int, dict], list[dict]]:
    """One request, answered. Both routes go through here so the sample
    measures the request the batch sends."""
    content = PROMPT % {
        "vocabulary": signal_families.prompt_vocabulary_block(),
        "findings": _ap.render_label_findings(chunk)}
    resp = client.chat.completions.create(
        model=model, max_completion_tokens=MAX_COMPLETION_TOKENS,
        reasoning_effort=effort,
        response_format={"type": "json_schema", "json_schema": {
            "name": "label_audit", "strict": True, "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}])
    text = resp.choices[0].message.content or ""
    try:
        parsed = json.loads(text).get("labels", [])
    except json.JSONDecodeError:
        return {}, [{"reason": "response was not JSON "
                              f"(finish_reason={resp.choices[0].finish_reason})"}]
    texts = {r["finding_id"]: r["value_text"] or "" for r in chunk}
    got, failures = {}, []
    for a in parsed:
        fid = a.get("finding_id")
        if fid not in texts:
            failures.append({"finding_id": fid,
                             "reason": "answer names a finding that was "
                                       "not asked about"})
            continue
        a["span_verified"] = _ap.verify_span(a.get("evidence_span", ""),
                                             texts[fid])
        got[fid] = a
    # No silent gaps: a finding asked about and not answered is recorded
    # as a failure rather than left to be noticed by a later count.
    for fid in texts:
        if fid not in got:
            failures.append({"finding_id": fid,
                             "reason": "asked about and not answered"})
    return got, failures


def run_model(rows: list[dict], model: str, effort: str,
              workers: int = 6) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    client = _client()
    chunks = [rows[i:i + FINDINGS_PER_REQUEST]
              for i in range(0, len(rows), FINDINGS_PER_REQUEST)]
    answers: dict[str, dict] = {}
    failures: list[dict] = []

    def ask(chunk):
        got, bad = ask_chunk(client, chunk, model, effort)
        failures.extend(bad)
        for fid, a in got.items():
            answers[str(fid)] = a
        return f"  {len(got)} of {len(chunk)} answered"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(ask, c) for c in chunks]):
            print(fut.result(), flush=True)
    return {"prompt_version": PROMPT_VERSION, "model": model,
            "reasoning_effort": effort, "answers": answers,
            "failures": failures}


# ---------------------------------------------------------------------------
# Scoring, on the asymmetry this task has
# ---------------------------------------------------------------------------
# A `does_not_fit` verdict takes a real quote off a reader's page, and a
# `fits` or `unclear` leaves it where it is. So the counts that matter
# are the ones that ACT: a flag the person did not agree with is the
# expensive error, and a flag missed is the status quo.

def score(rows: list[dict], hand: dict[str, dict], run: dict) -> list[str]:
    answers = run.get("answers", {})
    out, checked = [], 0
    agreed = wrong_flag = missed_flag = other = unverified = 0
    lines: list[str] = []
    for i, r in enumerate(rows, 1):
        fid = str(r["finding_id"])
        h, m = hand.get(fid), answers.get(fid)
        if m and not m.get("span_verified"):
            unverified += 1
        if not h or not h.get("verdict"):
            continue
        checked += 1
        hv, mv = h["verdict"], (m or {}).get("verdict")
        if hv == mv:
            agreed += 1
            continue
        if mv == "does_not_fit":
            wrong_flag += 1
            what = "FLAGGED, and the person did not"
        elif hv == "does_not_fit":
            missed_flag += 1
            what = "left it, the person flagged it"
        else:
            other += 1
            what = f"{mv} vs {hv}"
        lines.append(f"  {i:>2}. finding {fid} [{r['signal_family']}]: {what}"
                     + (f"\n      model: {(m or {}).get('reasoning','')[:140]}"
                        if m else ""))
    out.append(f"{checked} of {len(rows)} rows hand-checked")
    if checked:
        out.append(f"  agreed                {agreed}/{checked} "
                   f"({agreed / checked:.0%})")
        out.append(f"  FLAGGED WRONGLY       {wrong_flag}  — the error that "
                   f"costs a reader a real quote")
        out.append(f"  flag missed           {missed_flag}  — the row stays "
                   f"where it is, as it does today")
        out.append(f"  other disagreement    {other}")
    out.append(f"  spans that did not verify: {unverified}")
    if lines:
        out.append("\nwhere they differ:")
        out.extend(lines)
    for f in run.get("failures", []):
        out.append(f"  request failure: {f}")
    return out


def read_hand_sheet(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    hand = {}
    for r in rows:
        fid = (r.get("finding_id") or "").strip()
        v = (r.get("verdict") or "").strip()
        if v and v not in VERDICTS:
            sys.exit(f"row {r.get('row')}: verdict {v!r} is not one of "
                     f"{', '.join(VERDICTS)}")
        if fid:
            hand[fid] = {"verdict": v,
                         "suggested_family": (r.get("suggested_family") or "").strip(),
                         "note": (r.get("note") or "").strip()}
    return hand


STORE_SQL = """
INSERT INTO finding_label_audit
    (finding_id, family_audited, verdict, suggested_family, evidence_span,
     span_verified, reasoning, model, prompt_version)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (finding_id, model, prompt_version) DO NOTHING
"""


def do_batch(rows: list[dict], model: str, effort: str, workers: int,
             submit: bool) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT finding_id FROM finding_label_audit "
                    "WHERE model=%s AND prompt_version=%s",
                    (model, PROMPT_VERSION))
        done = {r[0] for r in cur.fetchall()}
    todo = [r for r in rows if r["finding_id"] not in done]
    chunks = [todo[i:i + FINDINGS_PER_REQUEST]
              for i in range(0, len(todo), FINDINGS_PER_REQUEST)]
    print(f"{len(rows):,} rendered findings, {len(done):,} already audited "
          f"under {model}/{PROMPT_VERSION}; {len(todo):,} to ask across "
          f"{len(chunks)} requests")
    if not submit:
        print("(measurement only — nothing sent, nothing stored; "
              "re-run with --submit)")
        return

    client = _client()
    stored = flagged = 0

    def run(chunk):
        nonlocal stored, flagged
        got, failures = ask_chunk(client, chunk, model, effort)
        by_id = {r["finding_id"]: r for r in chunk}
        written = 0
        with db.connect() as c2, c2.cursor() as cur:
            for fid, a in got.items():
                cur.execute(STORE_SQL, (
                    fid, by_id[fid]["signal_family"], a.get("verdict"),
                    a.get("suggested_family"),
                    (a.get("evidence_span") or "")[:2000],
                    bool(a.get("span_verified")),
                    (a.get("reasoning") or "")[:600], model, PROMPT_VERSION))
                written += cur.rowcount
            c2.commit()
        stored += written
        flagged += sum(1 for a in got.values()
                       if a.get("verdict") == "does_not_fit")
        return (f"  {written} stored of {len(got)} answered"
                + (f", {len(failures)} failures" if failures else ""))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(run, c) for c in chunks]):
            print(fut.result(), flush=True)
    print(f"stored {stored:,} verdicts; {flagged:,} rows flagged as filed "
          f"under a family that does not fit")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--hand", type=Path)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reasoning-effort", default="medium",
                    choices=["minimal", "low", "medium", "high"])
    args = ap.parse_args()
    if not (args.sample or args.run or args.score or args.batch):
        ap.error("pass --sample, --run, --score or --batch")

    with db.connect() as conn:
        rendered = load_rendered(conn)
    print(f"{len(rendered):,} findings are rendered across "
          f"{len({r['site_key'] for r in rendered}):,} sites")
    sample = choose_sample(rendered)
    run_path = args.out_dir / f"{PROMPT_VERSION}_model.json"

    if args.sample:
        print(f"wrote {write_sheet(sample, args.out_dir)} ({len(sample)} rows)")
    if args.run:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        run = run_model(sample, args.model, args.reasoning_effort, args.workers)
        run_path.write_text(json.dumps(run, indent=1), encoding="utf-8")
        n_flag = sum(1 for a in run["answers"].values()
                     if a["verdict"] == "does_not_fit")
        print(f"wrote {run_path}: {len(run['answers'])} answers, "
              f"{n_flag} flagged, {len(run['failures'])} failures")
    if args.score:
        hand_path = args.hand or (args.out_dir / f"{PROMPT_VERSION}_hand.csv")
        if not hand_path.exists():
            sys.exit(f"no filled sheet at {hand_path}")
        if not run_path.exists():
            sys.exit(f"no model answers at {run_path} — run --run first")
        print("\n".join(score(sample, read_hand_sheet(hand_path),
                              json.loads(run_path.read_text()))))
    if args.batch:
        do_batch(rendered, args.model, args.reasoning_effort, args.workers,
                 submit=args.submit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
