"""OpenAI-backed deep-read batch pass — same pipeline, third model tag.

STATUS: UNEXERCISED. Written when an OpenAI credit balance looked like the
faster route to a deadline, but no API key ever materialised, so this has
never issued a live request. The cohort/chunking/gate logic is shared with
the Anthropic path and the JSONL shape follows OpenAI's documented batch
format, but treat every API interaction here as untested. Validate on the
54-document escalation cohort (which already holds Qwen and Sonnet reads,
making a three-way quality comparison exact) before any bulk use.

Exists because the organisation holds OpenAI API credits, and the pipeline
was deliberately built model-agnostic: the verbatim-quote gate (not the
model) is the hallucination protection, findings carry their model tag in
the append-only store, and the prompt/chunking/gate are imported from
scripts/deepread_run.py so no provider path can drift from another.

Flow mirrors scripts/deepread_escalate.py but speaks OpenAI's Batch API
(JSONL file upload -> batch -> poll -> download results file) and uses
their enforced-JSON structured outputs. Quality is validated before any
bulk spend: run --cohort escalation first — the 54 documents that already
carry both Qwen and Sonnet reads — and compare gate-failure rates.

Usage:
    scripts/deepread_escalate_openai.py --list-models
    scripts/deepread_escalate_openai.py --submit --cohort escalation --model <id>
    scripts/deepread_escalate_openai.py --submit --cohort remaining --model <id>
    scripts/deepread_escalate_openai.py --collect [--batch-id ...]
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

LOCAL_MODEL = _dr.MODEL_TAG
PROMPT_VERSION = _dr.PROMPT_VERSION
BATCH_DIR = ROOT / "data" / "deepread_batches_openai"

# OpenAI structured outputs require every property in `required` and
# additionalProperties: false — same shape we already use for Sonnet.
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "deepread_findings",
        "strict": True,
        "schema": _esc.FINDINGS_SCHEMA,
    },
}


def _client():
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("pip install openai   (not yet installed in this venv)")
    return OpenAI()  # reads OPENAI_API_KEY from the environment


def load_cohort(conn, which: str) -> list[dict]:
    """'escalation' = the dual-read validation set (docs with Qwen AND
    Sonnet reads); 'remaining' = everything not yet read by any model."""
    if which == "escalation":
        q = """
            SELECT DISTINCT d.id, a.id, a.application_ref, d.content_sha256,
                            d.kind, l.tier
            FROM deepread_log l
            JOIN documents d ON d.id = l.document_id
            JOIN applications a ON a.id = l.application_id
            WHERE l.model = 'claude-sonnet-5' AND l.prompt_version = %s
            ORDER BY a.application_ref, d.id"""
        params = [PROMPT_VERSION]
    else:
        q = """
            SELECT DISTINCT d.id, a.id, a.application_ref, d.content_sha256,
                            d.kind, NULL
            FROM sites s
            JOIN site_members sm ON sm.site_id = s.id
            JOIN applications a  ON a.id = sm.application_id
            JOIN documents d     ON d.application_id = a.id
            WHERE s.retired_at IS NULL
              AND d.content_sha256 IS NOT NULL AND d.bytes_path IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM deepread_log l
                              WHERE l.document_id = d.id
                                AND l.prompt_version = %s)
            ORDER BY a.application_ref, d.id"""
        params = [PROMPT_VERSION]
    with conn.cursor() as cur:
        cur.execute(q, params)
        rows = [{"document_id": r[0], "application_id": r[1],
                 "application_ref": r[2], "sha": r[3], "kind": r[4],
                 "tier": r[5]} for r in cur.fetchall()]
    if which != "escalation":
        plans = sel.plan_documents(rows)
        kept = []
        for row, plan in zip(rows, plans):
            if plan.tier == "skip" or plan.sampled_out:
                continue
            row["tier"] = plan.tier
            kept.append(row)
        rows = kept
    return rows


def build_jsonl(rows: list[dict], model: str,
                max_chars: int) -> tuple[list[str], dict]:
    lines, meta = [], {}
    for row in rows:
        cache = extract.cache_path_for("documents", row["application_ref"],
                                       row["sha"])
        if not cache.exists():
            continue
        try:
            pages = json.loads(cache.read_text()).get("pages") or []
        except Exception:
            continue
        if not any(p.strip() for p in pages):
            continue
        selected = sel.select_pages(pages, tier=row["tier"] or "B")
        chunks = _dr.chunk_pages(pages, selected, max_chars)
        meta[str(row["document_id"])] = {
            **{k: row[k] for k in ("document_id", "application_id",
                                   "application_ref", "sha", "kind", "tier")},
            "pages_total": len(pages),
            "pages_sent": [n for nums, _t in chunks for n in nums],
            "n_chunks": len(chunks),
        }
        for i, (_nums, text) in enumerate(chunks):
            lines.append(json.dumps({
                "custom_id": f"{row['document_id']}-{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "max_completion_tokens": 16000,
                    "response_format": RESPONSE_FORMAT,
                    "messages": [{"role": "user",
                                  "content": _dr.PROMPT + text}],
                },
            }, ensure_ascii=False))
    return lines, meta


def do_submit(cohort: str, model: str, max_chars: int, dry_run: bool) -> None:
    with db.connect() as conn:
        rows = load_cohort(conn, cohort)
    lines, meta = build_jsonl(rows, model, max_chars)
    size_mb = sum(len(l) for l in lines) / 1e6
    print(f"cohort '{cohort}': {len(meta)} documents, {len(lines)} requests, "
          f"{size_mb:.0f}MB of JSONL")
    if dry_run or not lines:
        return
    client = _client()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)

    # OpenAI batch input files cap at 200MB / 50k requests — slice as needed.
    slices, cur, cur_size = [], [], 0
    for line in lines:
        if cur and (cur_size + len(line) > 180e6 or len(cur) >= 45000):
            slices.append(cur)
            cur, cur_size = [], 0
        cur.append(line)
        cur_size += len(line)
    if cur:
        slices.append(cur)

    for n, slice_lines in enumerate(slices):
        payload = ("\n".join(slice_lines) + "\n").encode()
        f = client.files.create(file=(f"deepread_{cohort}_{n}.jsonl", payload),
                                purpose="batch")
        batch = client.batches.create(input_file_id=f.id,
                                      endpoint="/v1/chat/completions",
                                      completion_window="24h")
        state = {"batch_id": batch.id, "model": model,
                 "prompt_version": PROMPT_VERSION, "cohort": cohort,
                 "slice": n, "n_slices": len(slices),
                 "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "documents": meta}
        (BATCH_DIR / f"{batch.id}.json").write_text(json.dumps(state))
        print(f"submitted slice {n + 1}/{len(slices)}: {batch.id} "
              f"({batch.status})")
    print("collect with: scripts/deepread_escalate_openai.py --collect")


def do_collect(batch_id: str | None) -> None:
    client = _client()
    paths = ([BATCH_DIR / f"{batch_id}.json"] if batch_id
             else sorted(BATCH_DIR.glob("batch_*.json")))
    for path in paths:
        state = json.loads(path.read_text())
        if state.get("collected"):
            continue
        batch = client.batches.retrieve(state["batch_id"])
        if batch.status != "completed":
            print(f"{state['batch_id']}: {batch.status} — not ready")
            continue
        raw = client.files.content(batch.output_file_id).text
        by_doc: dict[str, list] = {}
        errored: dict[str, int] = {}
        for line in raw.splitlines():
            r = json.loads(line)
            doc_id, _c = r["custom_id"].rsplit("-", 1)
            body = (r.get("response") or {}).get("body") or {}
            choice = (body.get("choices") or [{}])[0]
            if r.get("error") or choice.get("finish_reason") not in (
                    "stop", None):
                errored[doc_id] = errored.get(doc_id, 0) + 1
                continue
            content = (choice.get("message") or {}).get("content") or ""
            try:
                findings = json.loads(content).get("findings", [])
            except Exception:
                errored[doc_id] = errored.get(doc_id, 0) + 1
                continue
            by_doc.setdefault(doc_id, []).extend(findings)

        model_tag = f"openai:{state['model']}"
        inserted = failed = docs = 0
        with db.connect() as conn:
            for doc_id, info in state["documents"].items():
                if doc_id not in by_doc and doc_id not in errored:
                    continue
                row = {k: info[k] for k in ("document_id", "application_id",
                                            "application_ref", "sha")}
                row["tier"] = info["tier"] or "B"
                cache = extract.cache_path_for("documents",
                                               info["application_ref"],
                                               info["sha"])
                pages = json.loads(cache.read_text()).get("pages") or []
                ins, fl = _insert(conn, row, by_doc.get(doc_id, []), pages,
                                  info["pages_sent"], model_tag)
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO deepread_log (document_id, application_id,
                            model, prompt_version, tier, read_state,
                            pages_total, pages_sent, findings_inserted,
                            quotes_failed)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (document_id, model, prompt_version)
                        DO NOTHING""",
                        (row["document_id"], row["application_id"], model_tag,
                         PROMPT_VERSION, row["tier"],
                         "parse_failed" if errored.get(doc_id) else "read",
                         info["pages_total"], info["pages_sent"], ins, fl))
                conn.commit()
                inserted += ins
                failed += fl
                docs += 1
        state["collected"] = True
        path.write_text(json.dumps(state))
        print(f"collected {state['batch_id']}: {docs} documents, "
              f"{inserted} findings inserted, {failed} failed the verbatim "
              f"gate" + (f", {len(errored)} docs with errored chunks"
                         if errored else ""))


def _insert(conn, row, findings, pages, sent, model_tag) -> tuple[int, int]:
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
                _dr.escalate(reason="quote_failed_verification_openai",
                             application_ref=row["application_ref"],
                             sha=row["sha"], document_id=row["document_id"],
                             claimed_page=page, finding=f)
                continue
            num = f.get("value_number")
            num = num if isinstance(num, (int, float)) else None
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
                 str(f["signal_type"])[:80], f.get("value_text"), num,
                 f.get("value_unit"), quote, verified, model_tag,
                 PROMPT_VERSION))
            inserted += cur.rowcount
    conn.commit()
    return inserted, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--cohort", choices=["escalation", "remaining"],
                    default="escalation")
    ap.add_argument("--model", default=None)
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--max-chars", type=int, default=16000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.list_models:
        for m in sorted(_client().models.list(), key=lambda m: m.id):
            print(m.id)
        return
    if args.submit or args.dry_run:
        if args.submit and not args.model:
            ap.error("--submit requires --model (see --list-models)")
        do_submit(args.cohort, args.model or "<unset>", args.max_chars,
                  dry_run=not args.submit)
    elif args.collect:
        do_collect(args.batch_id)
    else:
        print("pass --list-models, --dry-run, --submit, or --collect")


if __name__ == "__main__":
    main()
