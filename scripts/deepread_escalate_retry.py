"""Retry the 602 chunks that failed at the API layer (credit exhaustion),
and bank everything else immediately.

Two outcomes from the bulk offload's three batches:
  - ~17,510 documents where every chunk succeeded — banked now, no reason
    to wait.
  - ~480 documents with at least one chunk that returned an actual error
    (credit balance too low, one transient key-validation glitch) — held
    back rather than logged incomplete, because `deepread_log` has a
    UNIQUE(document_id, model, prompt_version) constraint: log it now with
    partial findings and a later top-up can never add the rest under the
    same tag. Instead: retry exactly the failed chunks (not whole
    documents — the succeeded chunks already paid for stand), then do
    exactly one findings+log insert per document once both sources exist.

This is purely a Sonnet-via-API retry, same MODEL tag as the original —
the failure was infrastructure (an exhausted credit balance), not a model
struggling, so there's no reason to record it as anything but a normal
Sonnet read that happened to arrive in two API calls.

Usage:
    scripts/deepread_escalate_retry.py --prepare   # bank complete docs, submit retry
    scripts/deepread_escalate_retry.py --collect   # merge once the retry batch ends
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, extract  # noqa: E402
from dcp import deepread_select as sel  # noqa: E402

import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("deepread_run", ROOT / "scripts" / "deepread_run.py")
_dr = _ilu.module_from_spec(_spec)
sys.modules["deepread_run"] = _dr
_spec.loader.exec_module(_dr)

_espec = _ilu.spec_from_file_location("deepread_escalate",
                                      ROOT / "scripts" / "deepread_escalate.py")
_esc = _ilu.module_from_spec(_espec)
sys.modules["deepread_escalate"] = _esc
_espec.loader.exec_module(_esc)

MODEL = _esc.MODEL
PROMPT_VERSION = _esc.PROMPT_VERSION
BATCH_DIR = _esc.BATCH_DIR
STATE_PATH = ROOT / "data" / "deepread_retry_state.json"


def do_prepare() -> None:
    import anthropic
    client = anthropic.Anthropic()

    orig_paths = [p for p in BATCH_DIR.glob("msgbatch_*.json")
                  if json.loads(p.read_text()).get("cohort") == "remaining"
                  and not json.loads(p.read_text()).get("collected")]
    if not orig_paths:
        print("no uncollected 'remaining'-cohort batches — nothing to prepare")
        return

    deferred: dict[str, dict] = {}
    retry_requests: list[dict] = []
    banked_docs = banked_findings = 0

    with db.connect() as conn:
        for path in orig_paths:
            state = json.loads(path.read_text())
            per_doc = _batch_results(client, state["batch_id"])
            for doc_id, info in state["documents"].items():
                chunks = per_doc.get(doc_id, [])
                failed_idxs = [i for i, ok, _f in chunks if not ok]
                succeeded_findings = [f for _i, ok, fs in chunks if ok
                                      for f in (fs or [])]
                if not failed_idxs:
                    row = {k: info[k] for k in
                           ("document_id", "application_id",
                            "application_ref", "sha", "tier")}
                    cache = extract.cache_path_for("documents",
                                                   info["application_ref"],
                                                   info["sha"])
                    try:
                        pages = json.loads(cache.read_text()).get("pages") or []
                    except Exception:
                        pages = []
                    ins, fl = _esc._insert_with_model(conn, row,
                                                      succeeded_findings, pages,
                                                      info["pages_sent"])
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO deepread_log (document_id,
                                application_id, model, prompt_version, tier,
                                read_state, pages_total, pages_sent,
                                findings_inserted, quotes_failed)
                            VALUES (%s,%s,%s,%s,%s,'read',%s,%s,%s,%s)
                            ON CONFLICT (document_id, model, prompt_version)
                            DO NOTHING""",
                            (row["document_id"], row["application_id"],
                             MODEL, PROMPT_VERSION, row["tier"],
                             info["pages_total"], info["pages_sent"],
                             ins, fl))
                    conn.commit()
                    banked_docs += 1
                    banked_findings += ins
                    continue

                # Deferred: rebuild the exact failed chunk(s) deterministically.
                cache = extract.cache_path_for("documents",
                                               info["application_ref"],
                                               info["sha"])
                pages = json.loads(cache.read_text()).get("pages") or []
                selected = sel.select_pages(pages, tier=info["tier"] or "B")
                text_chunks = _dr.chunk_pages(pages, selected, 16000)
                for idx in failed_idxs:
                    if idx >= len(text_chunks):
                        continue
                    _nums, text = text_chunks[idx]
                    retry_requests.append({
                        "custom_id": f"{doc_id}-{idx}",
                        "params": {
                            "model": MODEL, "max_tokens": 16000,
                            "output_config": {"format": {
                                "type": "json_schema",
                                "schema": _esc.FINDINGS_SCHEMA}},
                            "messages": [{"role": "user",
                                          "content": _dr.PROMPT + text}],
                        },
                    })
                deferred[doc_id] = {
                    **{k: info[k] for k in
                       ("document_id", "application_id", "application_ref",
                        "sha", "tier", "pages_total", "pages_sent")},
                    "succeeded_findings": succeeded_findings,
                }
            path.write_text(json.dumps({**state, "collected": True}))

    print(f"banked {banked_docs} fully-succeeded documents "
          f"({banked_findings} findings)")
    print(f"{len(deferred)} documents deferred, {len(retry_requests)} "
          f"chunks to retry")
    if not retry_requests:
        return

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=retry_requests)
    STATE_PATH.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "deferred": deferred,
    }, indent=1))
    print(f"submitted retry batch {batch.id} ({batch.processing_status}, "
          f"{len(retry_requests)} requests)")
    print("collect with: scripts/deepread_escalate_retry.py --collect")


def _batch_results(client, batch_id: str):
    per_doc: dict[str, list[tuple[int, bool, list | None]]] = {}
    for result in client.messages.batches.results(batch_id):
        doc_id, chunk_s = result.custom_id.rsplit("-", 1)
        chunk_idx = int(chunk_s)
        ok, findings = False, None
        if result.result.type == "succeeded":
            msg = result.result.message
            if msg.stop_reason != "refusal":
                text = next((b.text for b in msg.content
                            if b.type == "text"), "")
                try:
                    findings = json.loads(text).get("findings", [])
                    ok = True
                except Exception:
                    pass
        per_doc.setdefault(doc_id, []).append((chunk_idx, ok, findings))
    return per_doc


def do_collect() -> None:
    if not STATE_PATH.exists():
        print("no retry state — run --prepare first")
        return
    state = json.loads(STATE_PATH.read_text())
    if state.get("collected"):
        print("already collected")
        return

    import anthropic
    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        c = batch.request_counts
        print(f"{state['batch_id']}: {batch.processing_status} "
              f"(succeeded {c.succeeded}, errored {c.errored}, "
              f"processing {c.processing}) — try again later")
        return

    per_doc = _batch_results(client, state["batch_id"])
    inserted_total = failed_total = docs_done = still_failing = 0
    with db.connect() as conn:
        for doc_id, info in state["deferred"].items():
            retry_chunks = per_doc.get(doc_id, [])
            still_bad = [i for i, ok, _f in retry_chunks if not ok]
            findings = list(info["succeeded_findings"])
            findings.extend(f for _i, ok, fs in retry_chunks if ok
                            for f in (fs or []))

            cache = extract.cache_path_for("documents", info["application_ref"],
                                           info["sha"])
            pages = json.loads(cache.read_text()).get("pages") or []
            row = {k: info[k] for k in ("document_id", "application_id",
                                        "application_ref", "sha", "tier")}
            ins, fl = _esc._insert_with_model(conn, row, findings, pages,
                                              info["pages_sent"])
            read_state = "parse_failed" if still_bad else "read"
            if still_bad:
                still_failing += 1
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deepread_log (document_id, application_id,
                        model, prompt_version, tier, read_state,
                        pages_total, pages_sent, findings_inserted,
                        quotes_failed)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (document_id, model, prompt_version)
                    DO NOTHING""",
                    (row["document_id"], row["application_id"], MODEL,
                     PROMPT_VERSION, row["tier"], read_state,
                     info["pages_total"], info["pages_sent"], ins, fl))
            conn.commit()
            inserted_total += ins
            failed_total += fl
            docs_done += 1

    state["collected"] = True
    STATE_PATH.write_text(json.dumps(state, indent=1))
    print(f"merged {docs_done} documents: {inserted_total} findings "
          f"inserted, {failed_total} failed the verbatim gate"
          + (f", {still_failing} still had a bad chunk after retry"
             if still_failing else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--collect", action="store_true")
    args = ap.parse_args()
    if args.prepare:
        do_prepare()
    elif args.collect:
        do_collect()
    else:
        print("pass --prepare or --collect")


if __name__ == "__main__":
    main()
