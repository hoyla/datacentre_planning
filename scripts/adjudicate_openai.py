#!/usr/bin/env python3
"""Power adjudication over the long tail, via the OpenAI batch API.

The other two routes handle the ends of this problem. The Anthropic
batch adjudicator (scripts/adjudicate_power.py) did the original 3,974
and cannot run again — that budget is spent. Claude Code subagents
(scripts/adjudicate_subagent.py) take the *consequential* figures, those
on sites with no adjudicated capacity at all, where a verdict changes
what a site reports and model continuity with the original run is worth
paying subscription usage for.

This takes what is left: several thousand figures on sites that already
carry an adjudicated capacity. They refine rather than move a headline,
and at ~1,000 tokens each through a subagent the whole tail would cost
millions of tokens where a batch does it for a few dollars.

The rubric is not re-typed. PROMPT, SCHEMA, TO_MW and APPARENT are
imported from scripts/adjudicate_power.py, so all three routes ask the
identical question and a divergence between them is a fact about the
models rather than about three drifting copies of a prompt.

Verdicts are stored under model `openai:<model>:<effort>` at prompt
version `power-1.0`. That means the corpus carries adjudications from
more than one model — which is not a compromise but the project's
second-opinion philosophy applied to adjudication: where they overlap,
agreement corroborates and disagreement is a flag worth a human.

    scripts/adjudicate_openai.py --dry-run
    scripts/adjudicate_openai.py --submit [--reasoning-effort low]
    scripts/adjudicate_openai.py --collect
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "adjudicate_power", ROOT / "scripts" / "adjudicate_power.py")
_ap = importlib.util.module_from_spec(_spec)
sys.modules["adjudicate_power"] = _ap
_spec.loader.exec_module(_ap)

PROMPT, SCHEMA = _ap.PROMPT, _ap.SCHEMA
TO_MW, APPARENT = _ap.TO_MW, _ap.APPARENT
PROMPT_VERSION = "power-1.0"
BATCH_DIR = ROOT / "data" / "adjudication_batches_openai"
# 8000 starved gpt-5 at high reasoning: it spent 96%% of the budget
# thinking and 155 of 436 requests hit the ceiling with no answer
# written, losing a third of the batch. Reasoning tokens are output
# tokens, so the ceiling has to cover both.
MAX_COMPLETION_TOKENS = 16000
FIGURES_PER_REQUEST = 60


def model_tag(model: str, effort: str | None) -> str:
    return f"openai:{model}" + (f":{effort}" if effort else "")


def _client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set (add it to .env)")
    return OpenAI()


def load_tail(conn) -> list[dict]:
    """Unadjudicated candidate figures, minus anything any route has
    already ruled on at this prompt version.

    Deliberately not restricted to already-capped sites: if the subagent
    run is still in flight, whatever it has not yet stored simply falls
    to this route rather than being dropped. Duplication is prevented by
    the (finding_id, model, prompt_version) key, not by hoping the two
    cohorts do not overlap.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT f.application_id, a.application_ref,
                   coalesce(a.description, ''), f.id, f.document_id,
                   f.signal_type, f.value_number, f.value_unit,
                   coalesce(f.value_text, ''), coalesce(f.evidence_text, '')
            FROM findings f
            JOIN applications a ON a.id = f.application_id
            WHERE f.value_number IS NOT NULL
              AND lower(f.value_unit) = ANY(%s)
              AND NOT EXISTS (
                    SELECT 1 FROM power_adjudication p
                    WHERE p.finding_id = f.id
                      AND p.prompt_version = %s)
            ORDER BY f.application_id, f.value_number DESC""",
            (list(TO_MW) + list(APPARENT), PROMPT_VERSION))
        rows = cur.fetchall()

    apps: dict[int, dict] = {}
    for (app_id, ref, desc, fid, doc_id, stype, num, unit,
         vtext, quote) in rows:
        app = apps.setdefault(app_id, {"application_id": app_id, "ref": ref,
                                       "desc": desc[:400], "figures": []})
        app["figures"].append({
            "finding_id": fid, "document_id": doc_id, "signal_type": stype,
            "value_number": float(num), "value_unit": unit,
            "value_text": vtext, "evidence_text": quote})
    return list(apps.values())


def build_jsonl(apps: list[dict], model: str,
                effort: str | None) -> tuple[list[str], dict]:
    lines, meta = [], {}
    for app in apps:
        figs = app["figures"]
        for i in range(0, len(figs), FIGURES_PER_REQUEST):
            chunk = figs[i:i + FIGURES_PER_REQUEST]
            content = PROMPT % {"ref": app["ref"], "desc": app["desc"],
                                "figures": _ap.render_figures(chunk)}
            body = {"model": model,
                    "max_completion_tokens": MAX_COMPLETION_TOKENS,
                    "response_format": {"type": "json_schema",
                                        "json_schema": {
                                            "name": "power_adjudication",
                                            "strict": True,
                                            "schema": SCHEMA}},
                    "messages": [{"role": "user", "content": content}]}
            if effort:
                body["reasoning_effort"] = effort
            lines.append(json.dumps({
                "custom_id": f"{app['application_id']}-{i // FIGURES_PER_REQUEST}",
                "method": "POST", "url": "/v1/chat/completions",
                "body": body}, ensure_ascii=False))
        for f in figs:
            meta[str(f["finding_id"])] = {**f,
                                          "application_id": app["application_id"]}
    return lines, meta


def do_submit(model: str, effort: str | None, dry_run: bool,
              rate_in: float, rate_out: float) -> None:
    with db.connect() as conn:
        apps = load_tail(conn)
    lines, meta = build_jsonl(apps, model, effort)
    n_fig = sum(len(a["figures"]) for a in apps)
    in_tok = sum(len(l) for l in lines) / 4
    print(f"tail: {len(apps):,} applications, {n_fig:,} figures, "
          f"{len(lines):,} requests")
    print(f"  input ≈ {in_tok/1e6:.2f}M tokens; output ceiling "
          f"{len(lines)*MAX_COMPLETION_TOKENS/1e6:.1f}M")
    if rate_in or rate_out:
        lo = in_tok / 1e6 * rate_in
        hi = lo + len(lines) * MAX_COMPLETION_TOKENS / 1e6 * rate_out
        print(f"  ${lo:,.2f} input, up to ${hi:,.2f} worst case "
              f"(batch pricing halves both)")
    if dry_run or not lines:
        return

    client = _client()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    payload = ("\n".join(lines) + "\n").encode()
    f = client.files.create(file=("adjudicate_tail.jsonl", payload),
                            purpose="batch")
    batch = client.batches.create(input_file_id=f.id,
                                  endpoint="/v1/chat/completions",
                                  completion_window="24h")
    (BATCH_DIR / f"{batch.id}.json").write_text(json.dumps({
        "batch_id": batch.id, "model": model, "reasoning_effort": effort,
        "prompt_version": PROMPT_VERSION,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "figures": meta}))
    print(f"submitted {batch.id} ({batch.status})")


def do_collect() -> None:
    client = _client()
    for path in sorted(BATCH_DIR.glob("batch_*.json")):
        state = json.loads(path.read_text())
        if state.get("collected"):
            continue
        batch = client.batches.retrieve(state["batch_id"])
        if batch.status in ("failed", "cancelled"):
            print(f"{state['batch_id']}: {batch.status} — nothing to collect")
            continue
        if batch.status not in ("completed", "expired"):
            print(f"{state['batch_id']}: {batch.status} — not ready")
            continue

        tag = model_tag(state["model"], state.get("reasoning_effort"))
        meta = state["figures"]
        inserted = skipped = errored = 0
        raw = (client.files.content(batch.output_file_id).text
               if batch.output_file_id else "")
        # The error file, for the same reason the deep-read path reads
        # it: a request that failed at the API level appears only here,
        # and a figure with no verdict must stay unadjudicated rather
        # than silently vanish from the queue.
        if getattr(batch, "error_file_id", None):
            errored = len(client.files.content(
                batch.error_file_id).text.splitlines())

        with db.connect() as conn, conn.cursor() as cur:
            for line in raw.splitlines():
                r = json.loads(line)
                body = (r.get("response") or {}).get("body") or {}
                choice = (body.get("choices") or [{}])[0]
                if choice.get("finish_reason") not in ("stop", None):
                    continue
                content = (choice.get("message") or {}).get("content") or ""
                try:
                    adjs = json.loads(content).get("adjudications", [])
                except Exception:
                    continue
                for a in adjs:
                    m = meta.get(str(a.get("finding_id")))
                    if m is None:
                        skipped += 1
                        continue
                    unit = (m["value_unit"] or "").lower()
                    value_mw = unit_note = None
                    if a.get("verdict") == "site_capacity":
                        if unit in TO_MW:
                            value_mw = m["value_number"] * TO_MW[unit]
                        elif unit in APPARENT:
                            unit_note = ("apparent power (kVA/MVA); not "
                                         "converted to MW — power factor "
                                         "unknown")
                    cur.execute("""
                        INSERT INTO power_adjudication (application_id,
                            finding_id, document_id, verdict, quantity_type,
                            value_mw, value_original, unit_original,
                            unit_note, is_maximum, reasoning, model,
                            prompt_version)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (finding_id, model, prompt_version)
                        DO NOTHING""",
                        (m["application_id"], a["finding_id"],
                         m["document_id"], a.get("verdict"),
                         a.get("quantity_type"), value_mw,
                         m["value_number"], m["value_unit"], unit_note,
                         a.get("is_maximum"),
                         (a.get("reasoning") or "")[:600], tag,
                         PROMPT_VERSION))
                    inserted += cur.rowcount
            conn.commit()
        state["collected"] = True
        path.write_text(json.dumps(state))
        print(f"collected {state['batch_id']}: {inserted:,} adjudications"
              + (f", {skipped} unknown finding_ids" if skipped else "")
              + (f", {errored} API-level failures left unadjudicated"
                 if errored else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Estimate and stop without sending. Wins over "
                         "--submit when both are given.")
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--reasoning-effort", default="low",
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--rate-in", type=float, default=1.25)
    ap.add_argument("--rate-out", type=float, default=10.0)
    args = ap.parse_args()
    if args.collect:
        do_collect()
    elif args.submit or args.dry_run:
        # --dry-run wins over --submit: the safe reading of a
        # contradictory pair is the one that does not spend money.
        do_submit(args.model, args.reasoning_effort,
                  dry_run=args.dry_run or not args.submit,
                  rate_in=args.rate_in, rate_out=args.rate_out)
    else:
        ap.error("pass --dry-run, --submit or --collect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
