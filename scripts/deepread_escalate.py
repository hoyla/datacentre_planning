"""Sonnet escalation pass for deep-read failures, via the Batch API.

The local MLX deep-read (scripts/deepread_run.py) has two failure classes,
both visible in `deepread_log`: documents whose dense output overflowed the
token budget (`read_state = 'parse_failed'` — salvage recovers most but not
all), and documents whose extracted quotes failed the verbatim gate
(`quotes_failed > 0` — the model reciting boilerplate it knows rather than
text it saw). Both get a clean re-read here on claude-sonnet-5.

Design choices, and why:

- **Batch API** — half price, asynchronous, and nothing about an
  escalation queue needs latency. Results are collected in a second
  invocation, possibly hours later.
- **Structured outputs** — the batch requests carry a JSON schema the API
  enforces, so the parse-failure class cannot recur here by construction.
- **Same prompt, same page selection, same verbatim gate.** The Sonnet
  findings are only comparable to (and auditable against) the local run
  because every other variable is held fixed. Rows land under model
  'claude-sonnet-5' beside the 'mlx:…' rows — append-only, never replacing.

Usage:
    .venv/bin/python -u scripts/deepread_escalate.py --dry-run
    .venv/bin/python -u scripts/deepread_escalate.py --submit
    .venv/bin/python -u scripts/deepread_escalate.py --collect          # newest batch
    .venv/bin/python -u scripts/deepread_escalate.py --collect --batch-id msgbatch_...
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

# Import the local runner's prompt, chunking and verbatim gate so the two
# passes can never drift apart.
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("deepread_run", ROOT / "scripts" / "deepread_run.py")
_dr = _ilu.module_from_spec(_spec)
sys.modules["deepread_run"] = _dr
_spec.loader.exec_module(_dr)

MODEL = "claude-sonnet-5"
LOCAL_MODEL = _dr.MODEL_TAG
PROMPT_VERSION = _dr.PROMPT_VERSION
BATCH_DIR = ROOT / "data" / "deepread_batches"

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal_type": {"type": "string"},
                    "value_text": {"type": "string"},
                    "value_number": {"type": ["number", "null"]},
                    "value_unit": {"type": ["string", "null"]},
                    "evidence_text": {"type": "string"},
                    "evidence_page": {"type": "integer"},
                },
                "required": ["signal_type", "value_text", "value_number",
                             "value_unit", "evidence_text", "evidence_page"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def load_cohort_remaining(conn) -> list[dict]:
    """The bulk offload cohort: every readable document not yet read by ANY
    model under this prompt version. Local shards keep their own resume
    contract (keyed on the mlx model tag), so they will independently
    re-read these later — deliberate: dual reads are cross-model
    corroboration at zero marginal cost."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT d.id, a.id, a.application_ref, d.content_sha256,
                            d.kind
            FROM sites s
            JOIN site_members sm ON sm.site_id = s.id
            JOIN applications a  ON a.id = sm.application_id
            JOIN documents d     ON d.application_id = a.id
            WHERE s.retired_at IS NULL
              AND d.content_sha256 IS NOT NULL AND d.bytes_path IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM deepread_log l
                              WHERE l.document_id = d.id
                                AND l.prompt_version = %s)
            ORDER BY a.application_ref, d.id""", (PROMPT_VERSION,))
        rows = [{"document_id": r[0], "application_id": r[1],
                 "application_ref": r[2], "sha": r[3], "kind": r[4]}
                for r in cur.fetchall()]
    plans = sel.plan_documents(rows)
    kept = []
    for row, plan in zip(rows, plans):
        if plan.tier == "skip" or plan.sampled_out:
            continue
        row["tier"] = plan.tier
        kept.append(row)
    return kept


def load_cohort(conn) -> list[dict]:
    """Documents the local model struggled with, not yet re-read by Sonnet."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT d.id, a.id, a.application_ref, d.content_sha256,
                            d.kind, l.tier
            FROM deepread_log l
            JOIN documents d ON d.id = l.document_id
            JOIN applications a ON a.id = l.application_id
            WHERE l.model = %s AND l.prompt_version = %s
              AND (l.read_state = 'parse_failed' OR l.quotes_failed > 0)
              AND NOT EXISTS (SELECT 1 FROM deepread_log s
                              WHERE s.document_id = d.id
                                AND s.model = %s AND s.prompt_version = %s)
            ORDER BY a.application_ref, d.id""",
            (LOCAL_MODEL, PROMPT_VERSION, MODEL, PROMPT_VERSION))
        return [{"document_id": r[0], "application_id": r[1],
                 "application_ref": r[2], "sha": r[3], "kind": r[4],
                 "tier": r[5]} for r in cur.fetchall()]


def build_requests(rows: list[dict], max_chars: int) -> tuple[list[dict], dict]:
    """One batch request per chunk; custom_id = '<document_id>:<chunk_idx>'."""
    requests, meta = [], {}
    for row in rows:
        cache = extract.cache_path_for("documents", row["application_ref"],
                                       row["sha"])
        if not cache.exists():
            continue
        try:
            pages = json.loads(cache.read_text()).get("pages") or []
        except Exception:
            continue  # corrupt cache file — the local pass will flag it
        if not any(p.strip() for p in pages):
            continue
        selected = sel.select_pages(pages, tier=row["tier"])
        chunks = _dr.chunk_pages(pages, selected, max_chars)
        meta[str(row["document_id"])] = {
            **{k: row[k] for k in ("document_id", "application_id",
                                   "application_ref", "sha", "kind", "tier")},
            "pages_total": len(pages),
            "pages_sent": [n for nums, _t in chunks for n in nums],
            "n_chunks": len(chunks),
        }
        for i, (_nums, text) in enumerate(chunks):
            requests.append({
                "custom_id": f"{row['document_id']}-{i}",
                "params": {
                    "model": MODEL,
                    "max_tokens": 16000,
                    "output_config": {
                        "format": {"type": "json_schema",
                                   "schema": FINDINGS_SCHEMA},
                    },
                    "messages": [{"role": "user",
                                  "content": _dr.PROMPT + text}],
                },
            })
    return requests, meta


def do_submit(max_chars: int, dry_run: bool, cohort: str = "failures") -> None:
    with db.connect() as conn:
        rows = (load_cohort_remaining(conn) if cohort == "remaining"
                else load_cohort(conn))
    requests, meta = build_requests(rows, max_chars)
    n_docs = len(meta)
    approx_mtok = sum(len(r["params"]["messages"][0]["content"])
                      for r in requests) / 4 / 1e6
    print(f"cohort '{cohort}': {n_docs} documents, {len(requests)} chunks; "
          f"~{approx_mtok:.2f}M input tokens "
          f"(~${approx_mtok * (1.0 + 0.35 * 5):.0f} at Sonnet batch rates "
          f"incl. estimated output)")
    if dry_run or not requests:
        return

    import anthropic
    client = anthropic.Anthropic()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)

    # The Batch API caps a submission at 100k requests / 256MB. Slice by
    # size, keeping all of a document's chunks in one slice so collection
    # stays per-document.
    slices: list[tuple[list[dict], dict]] = []
    cur_reqs: list[dict] = []
    cur_meta: dict = {}
    cur_size = 0
    for doc_id, info in meta.items():
        doc_reqs = [r for r in requests
                    if r["custom_id"].rsplit("-", 1)[0] == doc_id]
        doc_size = sum(len(r["params"]["messages"][0]["content"])
                       for r in doc_reqs)
        if cur_reqs and (cur_size + doc_size > 180e6
                         or len(cur_reqs) + len(doc_reqs) > 45000):
            slices.append((cur_reqs, cur_meta))
            cur_reqs, cur_meta, cur_size = [], {}, 0
        cur_reqs.extend(doc_reqs)
        cur_meta[doc_id] = info
        cur_size += doc_size
    if cur_reqs:
        slices.append((cur_reqs, cur_meta))

    for n, (slice_reqs, slice_meta) in enumerate(slices):
        batch = client.messages.batches.create(requests=slice_reqs)
        state = {"batch_id": batch.id, "model": MODEL,
                 "prompt_version": PROMPT_VERSION, "cohort": cohort,
                 "slice": n, "n_slices": len(slices),
                 "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "documents": slice_meta}
        path = BATCH_DIR / f"{batch.id}.json"
        path.write_text(json.dumps(state, indent=1))
        print(f"submitted slice {n + 1}/{len(slices)}: {batch.id} "
              f"({batch.processing_status}, {len(slice_reqs)} requests)")
    print("collect with: scripts/deepread_escalate.py --collect-all")


def do_collect(batch_id: str | None) -> None:
    import anthropic
    client = anthropic.Anthropic()

    if batch_id is None:
        candidates = sorted(BATCH_DIR.glob("msgbatch_*.json"),
                            key=lambda p: p.stat().st_mtime)
        candidates = [p for p in candidates
                      if not json.loads(p.read_text()).get("collected")]
        if not candidates:
            print("no uncollected batches found")
            return
        batch_id = candidates[-1].stem
    state = json.loads((BATCH_DIR / f"{batch_id}.json").read_text())
    if state.get("collected"):
        print(f"{batch_id}: already collected")
        return

    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        c = batch.request_counts
        print(f"{batch_id}: {batch.processing_status} "
              f"(processing {c.processing}, succeeded {c.succeeded}, "
              f"errored {c.errored}) — try again later")
        return

    # Gather findings per document across its chunks.
    by_doc: dict[str, list] = {}
    errored: dict[str, int] = {}
    for result in client.messages.batches.results(batch_id):
        doc_id, _chunk = result.custom_id.rsplit("-", 1)
        if result.result.type != "succeeded":
            errored[doc_id] = errored.get(doc_id, 0) + 1
            continue
        msg = result.result.message
        if msg.stop_reason == "refusal":
            errored[doc_id] = errored.get(doc_id, 0) + 1
            continue
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            findings = json.loads(text).get("findings", [])
        except Exception:
            errored[doc_id] = errored.get(doc_id, 0) + 1
            continue
        by_doc.setdefault(doc_id, []).extend(findings)

    inserted_total = failed_total = docs_done = 0
    with db.connect() as conn:
        for doc_id, info in state["documents"].items():
            if doc_id not in by_doc and doc_id not in errored:
                continue  # nothing came back at all — leave for a resubmit
            row = {k: info[k] for k in ("document_id", "application_id",
                                        "application_ref", "sha", "tier")}
            cache = extract.cache_path_for("documents",
                                           info["application_ref"],
                                           info["sha"])
            pages = json.loads(cache.read_text()).get("pages") or []
            ins, fl = _insert_with_model(conn, row, by_doc.get(doc_id, []),
                                         pages, info["pages_sent"])
            state_name = ("parse_failed" if errored.get(doc_id)
                          else "read")
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deepread_log (document_id, application_id,
                        model, prompt_version, tier, read_state, pages_total,
                        pages_sent, findings_inserted, quotes_failed)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (document_id, model, prompt_version)
                    DO NOTHING""",
                    (row["document_id"], row["application_id"], MODEL,
                     PROMPT_VERSION, row["tier"], state_name,
                     info["pages_total"], info["pages_sent"], ins, fl))
            conn.commit()
            inserted_total += ins
            failed_total += fl
            docs_done += 1
    state["collected"] = True
    (BATCH_DIR / f"{batch_id}.json").write_text(json.dumps(state, indent=1))
    print(f"collected {batch_id}: {docs_done} documents, "
          f"{inserted_total} findings inserted, "
          f"{failed_total} failed the verbatim gate"
          + (f", {len(errored)} documents with errored/refused chunks"
             if errored else ""))


def _no_nul(v):
    """Postgres text cannot hold NUL (0x00) and raises on it. One arrived
    in a gpt-5 finding after 460,000 findings without one -- the model can
    emit what the source never contained -- so every string is stripped at
    the database boundary rather than trusting any reader not to."""
    return v.replace("\x00", "") if isinstance(v, str) else v

def _insert_with_model(conn, row: dict, findings: list[dict],
                       pages: list[str], sent: list[int]) -> tuple[int, int]:
    """verify_and_insert, but stamping the Sonnet model tag."""
    inserted = failed = 0
    with conn.cursor() as cur:
        for f in findings:
            quote = (f.get("evidence_text") or "").strip()
            if not quote or not f.get("signal_type"):
                continue
            page = _dr.coerce_page(f.get("evidence_page"))
            verified_page = None
            candidates = ([page, page - 1, page + 1]
                          if page and 1 <= page <= len(pages) else [])
            for p in candidates + [p for p in sent if p not in candidates]:
                if 1 <= p <= len(pages) and _dr.quote_on_page(quote, pages[p - 1]):
                    verified_page = p
                    break
            if verified_page is None:
                failed += 1
                _dr.escalate(reason="quote_failed_verification_sonnet",
                             application_ref=row["application_ref"],
                             sha=row["sha"], document_id=row["document_id"],
                             claimed_page=page, finding=f)
                continue
            num = f.get("value_number")
            num = num if isinstance(num, (int, float)) else None
            # Conflict-guarded against the content key (migration 012), so
            # re-collecting a batch cannot re-insert what a previous
            # collection already stored. rowcount keeps the count honest.
            cur.execute("""
                INSERT INTO findings (application_id, document_id,
                    signal_type, value_text, value_number, value_unit,
                    evidence_text, evidence_page, model, prompt_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (application_id, document_id, model,
                    prompt_version, signal_type, md5(value_text),
                    value_number, value_unit, md5(evidence_text),
                    evidence_page)
                DO NOTHING""",
                (row["application_id"], row["document_id"],
                 _no_nul(str(f["signal_type"])[:80]),
                 _no_nul(f.get("value_text")), num,
                 _no_nul(f.get("value_unit")), _no_nul(quote),
                 verified_page, MODEL, PROMPT_VERSION))
            inserted += cur.rowcount
    conn.commit()
    return inserted, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--collect-all", action="store_true",
                    help="Collect every uncollected batch that has ended.")
    ap.add_argument("--cohort", choices=["failures", "remaining"],
                    default="failures",
                    help="'failures' re-reads local-model failures; "
                         "'remaining' offloads every unread document.")
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--max-chars", type=int, default=16000)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report cohort size and cost estimate only.")
    args = ap.parse_args()
    if args.dry_run or args.submit:
        do_submit(args.max_chars, dry_run=not args.submit, cohort=args.cohort)
    elif args.collect_all:
        for path in sorted(BATCH_DIR.glob("msgbatch_*.json")):
            if not json.loads(path.read_text()).get("collected"):
                do_collect(path.stem)
    elif args.collect:
        do_collect(args.batch_id)
    else:
        print("pass --dry-run, --submit, --collect, or --collect-all")


if __name__ == "__main__":
    main()
