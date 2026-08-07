"""Claude-Code-in-session escalation: export chunks, read them here, merge back.

STATUS: UNEXERCISED, and built on a misread. It was written to route the
602 credit-exhaustion chunks to in-session reading; those are
infrastructure failures and belong back on the API, which is what
deepread_escalate_retry.py now does. Kept because the shape it
establishes — export a work manifest, have subagents read and extract,
merge results back through the same verbatim gate under a distinct model
tag — is what the genuine adjudication pass needs, and rebuilding it
would be wasted effort. Nothing here has run against the database.

This restores the original v1 architecture decision (2026-08-03): the local
model does the bulk read, and genuinely awkward cases — here, chunks whose
API attempt actually returned a failure — are read by Claude Code directly,
subscription-covered rather than metered against API credits. Re-submitting
a failed request to the same paid API is both wasteful and beside the
point when a human-grade reader is sitting right here.

Two phases, split because the read itself is done by a subagent (a Task/
Agent call), not by this script:

  --prepare   Splits the just-collected batch results into (a) documents
              with zero failures — banked immediately via do_collect's
              logic, no cost or delay — and (b) documents with at least
              one failed chunk. For (b), writes each failed chunk's exact
              prompt text (reconstructed deterministically — same chunking,
              same prompt) to a scratch file, and saves that document's
              already-succeeded chunk findings alongside, so the eventual
              merge combines both sources into one finding set per
              document. Prints a worklist an Agent can be pointed at.

  --merge     After the agent(s) have written their findings JSON per the
              manifest, this reads them back, merges with the saved
              already-succeeded findings, runs the same verbatim gate, and
              performs exactly one findings+deepread_log insert per
              document — under model tag 'claude-sonnet-5+claude-code' so
              provenance honestly records how the read was done.

Usage:
    scripts/deepread_agent_escalate.py --prepare
    # ... agents read the manifest's chunk files, write result JSON ...
    scripts/deepread_agent_escalate.py --merge
"""

from __future__ import annotations

import argparse
import json
import sys
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

MODEL_TAG = "claude-sonnet-5+claude-code"
PROMPT_VERSION = _dr.PROMPT_VERSION
BATCH_DIR = _esc.BATCH_DIR
SCRATCH = ROOT / "data" / "deepread_agent_escalate"


def _batch_results(client, batch_id: str):
    """(doc_id -> [(chunk_idx, ok, findings_or_None)], ...) for one batch."""
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


def do_prepare() -> None:
    import anthropic
    client = anthropic.Anthropic()

    states = [json.loads(p.read_text()) for p in BATCH_DIR.glob("msgbatch_*.json")
              if not json.loads(p.read_text()).get("collected")]
    if not states:
        print("no uncollected batches — nothing to prepare")
        return

    SCRATCH.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    banked_docs = failing_docs = banked_findings = 0

    with db.connect() as conn:
        for state in states:
            per_doc = _batch_results(client, state["batch_id"])
            for doc_id, info in state["documents"].items():
                chunks = per_doc.get(doc_id, [])
                has_failure = any(not ok for _i, ok, _f in chunks)
                cache = extract.cache_path_for("documents",
                                               info["application_ref"],
                                               info["sha"])
                try:
                    pages = json.loads(cache.read_text()).get("pages") or []
                except Exception:
                    pages = []

                if not has_failure:
                    # Fully succeeded: bank it now under the normal Sonnet
                    # tag, exactly as a clean API collection would.
                    row = {k: info[k] for k in
                           ("document_id", "application_id",
                            "application_ref", "sha", "tier")}
                    findings = [f for _i, _ok, fs in chunks for f in (fs or [])]
                    ins, fl = _esc._insert_with_model(conn, row, findings,
                                                      pages, info["pages_sent"])
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
                             _esc.MODEL, PROMPT_VERSION, row["tier"],
                             info["pages_total"], info["pages_sent"], ins, fl))
                    conn.commit()
                    banked_docs += 1
                    banked_findings += ins
                    continue

                # Partial or total failure: save what succeeded, export
                # what failed for an agent to read directly.
                failing_docs += 1
                succeeded_findings = [f for _i, ok, fs in chunks if ok
                                      for f in (fs or [])]
                failed_chunk_idxs = [i for i, ok, _f in chunks if not ok]

                selected = sel.select_pages(pages, tier=info["tier"] or "B")
                text_chunks = _dr.chunk_pages(pages, selected, 16000)

                chunk_files = []
                for idx in failed_chunk_idxs:
                    if idx >= len(text_chunks):
                        continue  # shouldn't happen; guards a re-chunk drift
                    nums, text = text_chunks[idx]
                    fname = f"{doc_id}-{idx}.txt"
                    (SCRATCH / fname).write_text(_dr.PROMPT + text)
                    chunk_files.append({"file": fname, "chunk_idx": idx,
                                        "pages": nums})

                manifest[doc_id] = {
                    **{k: info[k] for k in
                       ("document_id", "application_id", "application_ref",
                        "sha", "kind", "tier", "pages_total", "pages_sent")},
                    "succeeded_findings": succeeded_findings,
                    "failed_chunks": chunk_files,
                }

    (SCRATCH / "manifest.json").write_text(json.dumps(manifest, indent=1))
    n_chunks = sum(len(v["failed_chunks"]) for v in manifest.values())
    print(f"banked {banked_docs} fully-succeeded documents "
          f"({banked_findings} findings) — no cost, no delay")
    print(f"{failing_docs} documents need {n_chunks} chunks read directly — "
          f"manifest and prompt files at {SCRATCH}")
    print(f"Each chunk file at {SCRATCH}/<doc_id>-<idx>.txt already contains "
          f"the exact prompt sent to the API (find/extract/quote "
          f"instructions + document text). An agent should read each file, "
          f"produce {{\"findings\": [...]}} per the prompt's own schema, "
          f"and write it to {SCRATCH}/results/<doc_id>-<idx>.json")
    (SCRATCH / "results").mkdir(exist_ok=True)


def do_merge() -> None:
    manifest_path = SCRATCH / "manifest.json"
    if not manifest_path.exists():
        print("no manifest — run --prepare first")
        return
    manifest = json.loads(manifest_path.read_text())
    results_dir = SCRATCH / "results"

    inserted_total = failed_total = docs_done = docs_incomplete = 0
    with db.connect() as conn:
        for doc_id, info in manifest.items():
            findings = list(info["succeeded_findings"])
            missing = []
            for c in info["failed_chunks"]:
                rpath = results_dir / f"{doc_id}-{c['chunk_idx']}.json"
                if not rpath.exists():
                    missing.append(c["chunk_idx"])
                    continue
                try:
                    findings.extend(json.loads(rpath.read_text())
                                    .get("findings", []))
                except Exception:
                    missing.append(c["chunk_idx"])
            if missing:
                docs_incomplete += 1
                continue  # wait for the remaining chunk(s)

            cache = extract.cache_path_for("documents", info["application_ref"],
                                           info["sha"])
            pages = json.loads(cache.read_text()).get("pages") or []
            row = {k: info[k] for k in ("document_id", "application_id",
                                        "application_ref", "sha", "tier")}
            ins, fl = _insert_agent(conn, row, findings, pages,
                                    info["pages_sent"])
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deepread_log (document_id, application_id,
                        model, prompt_version, tier, read_state, pages_total,
                        pages_sent, findings_inserted, quotes_failed)
                    VALUES (%s,%s,%s,%s,%s,'read',%s,%s,%s,%s)
                    ON CONFLICT (document_id, model, prompt_version)
                    DO NOTHING""",
                    (row["document_id"], row["application_id"], MODEL_TAG,
                     PROMPT_VERSION, row["tier"], info["pages_total"],
                     info["pages_sent"], ins, fl))
            conn.commit()
            inserted_total += ins
            failed_total += fl
            docs_done += 1

    print(f"merged {docs_done} documents: {inserted_total} findings inserted, "
          f"{failed_total} failed the verbatim gate")
    if docs_incomplete:
        print(f"{docs_incomplete} documents still waiting on agent output — "
              f"re-run --merge once they're written")


def _insert_agent(conn, row, findings, pages, sent) -> tuple[int, int]:
    inserted = failed = 0
    with conn.cursor() as cur:
        for f in findings:
            quote = (f.get("evidence_text") or "").strip()
            if not quote or not f.get("signal_type"):
                continue
            page = _dr.coerce_page(f.get("evidence_page"))
            verified = None
            cands = ([page, page - 1, page + 1]
                     if page and 1 <= page <= len(pages) else [])
            for p in cands + [p for p in sent if p not in cands]:
                if 1 <= p <= len(pages) and _dr.quote_on_page(quote, pages[p - 1]):
                    verified = p
                    break
            if verified is None:
                failed += 1
                _dr.escalate(reason="quote_failed_verification_agent",
                             application_ref=row["application_ref"],
                             sha=row["sha"], document_id=row["document_id"],
                             claimed_page=page, finding=f)
                continue
            num = f.get("value_number")
            num = num if isinstance(num, (int, float)) else None
            cur.execute("""
                INSERT INTO findings (application_id, document_id,
                    signal_type, value_text, value_number, value_unit,
                    evidence_text, evidence_page, model)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (row["application_id"], row["document_id"],
                 str(f["signal_type"])[:80], f.get("value_text"), num,
                 f.get("value_unit"), quote, verified, MODEL_TAG))
            inserted += 1
    conn.commit()
    return inserted, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    if args.prepare:
        do_prepare()
    elif args.merge:
        do_merge()
    else:
        print("pass --prepare or --merge")


if __name__ == "__main__":
    main()
