"""The production document deep-read: MLX Qwen3.6 over the site corpus.

Chosen by measurement (scripts/benchmark_deepread.py, 2026-08-07):
Qwen3.6-35B-A3B-4bit through MLX reads a document in ~9s where
granite4.1:30b takes ~58s — a 6.3× speedup that turns the corpus from
weeks into days — and on the substantive test documents it extracted the
same class of findings (applicant, grid connection, capacity) that the
v2 architecture needs. Thinking mode is disabled: a reasoning trace
would swamp both the JSON output and the throughput.

The pipeline per document:

1. Page-selected text from the corpus cache (dcp/deepread_select.py —
   tiers, drawings skipped, objection letters sampled, pages scored
   against the power/environmental lexicons).
2. Selected pages are sent in chunks, each page introduced by a
   `[PAGE n]` marker carrying its 1-based physical PDF page number, so
   findings come back with a page a reporter can Cmd-G to.
3. Every finding passes the verbatim-quote gate BEFORE it is stored:
   the evidence quote must appear (normalised for pypdf's whitespace
   habits, ellipsis-aware) on the page the model claimed, ±1 page, or
   anywhere in the sent text as a fallback that corrects the page
   number. Failures are never inserted — they go to the escalation
   queue for the Claude Code in-session pass.
4. Findings land in `findings` (append-only, model-tagged); every
   document attempt lands in `deepread_log`, including the ones
   deliberately not read, so coverage can be stated honestly.

Resume is a database query: documents already logged for this
(model, prompt_version) are skipped, so an interrupted run picks up
where it left off at no cost.

Usage:
    HF_HUB_OFFLINE=1 .venv/bin/python -u scripts/deepread_run.py --dry-run
    HF_HUB_OFFLINE=1 .venv/bin/python -u scripts/deepread_run.py
    HF_HUB_OFFLINE=1 .venv/bin/python -u scripts/deepread_run.py --tier A --limit 50
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, extract  # noqa: E402
from dcp import deepread_select as sel  # noqa: E402

MODEL_PATH = "mlx-community/Qwen3.6-35B-A3B-4bit"
MODEL_TAG = "mlx:Qwen3.6-35B-A3B-4bit"
PROMPT_VERSION = "1.0"
ESCALATION_PATH = ROOT / "data" / "deepread_escalations.jsonl"

PROMPT = """\
You are reading a UK planning document for an investigative journalism
project on data centres and their power and environmental impact.

Extract every factual claim relevant to any of: on-site power generation
(engines, turbines, CHP, generators, fuel), grid connection and capacity,
IT load or power demand in MW, water use including cooling, emissions and
air quality, designated sites and ecology, flood risk, EIA screening
outcomes, and the parties involved (applicant, agent, consultants).

The document text below is divided by [PAGE n] markers giving the
physical PDF page each passage comes from.

For each fact, return an object with:
  "signal_type": a short snake_case label
  "value_text":  the fact in a few words
  "value_number" and "value_unit": if the fact is quantitative, else null
  "evidence_text": a VERBATIM quote from the document supporting it
  "evidence_page": the [PAGE n] number the quote appears on

The evidence quote must appear in the document character-for-character —
it is checked automatically, and an invented quote is worse than no
finding. If the document contains nothing relevant, return an empty list.

Return strict JSON: {"findings": [...]}. No prose outside the JSON.

DOCUMENT:
"""

# ---------------------------------------------------------------------------
# Quote verification — same normalisation as scripts/verify_findings.py,
# imported so the pre-insert gate and the pre-publication audit can never
# drift apart.
# ---------------------------------------------------------------------------


def _load_verify():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "verify_findings", ROOT / "scripts" / "verify_findings.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_findings"] = mod  # dataclasses looks itself up here
    spec.loader.exec_module(mod)
    return mod


_VF = _load_verify()


def quote_on_page(quote: str, page_text: str) -> bool:
    frags = [_VF._normalise(f) for f in _VF._quote_fragments(quote)]
    return bool(frags) and _VF._all_fragments_in_order(
        _VF._normalise(page_text), frags)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

_MLX: dict = {}


def mlx_generate(text: str, max_tokens: int) -> tuple[str, float]:
    from mlx_lm import generate, load
    if "m" not in _MLX:
        _MLX["m"], _MLX["t"] = load(MODEL_PATH)
    model, tok = _MLX["m"], _MLX["t"]
    messages = [{"role": "user", "content": PROMPT + text}]
    # Qwen3.6 is a thinking model by default; disable it or the trace
    # swamps the JSON and the throughput alike.
    prompt = tok.apply_chat_template(messages, add_generation_prompt=True,
                                     enable_thinking=False)
    t0 = time.time()
    out = generate(model, tok, prompt=prompt, max_tokens=max_tokens,
                   verbose=False)
    return out, time.time() - t0


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_findings(raw: str) -> list[dict] | None:
    """Findings list from model output, or None when unparseable.

    Tolerates a markdown fence and trailing text; an output truncated
    mid-string is unparseable by design — the caller retries with a
    larger token budget rather than accepting half a quote.
    """
    cleaned = _FENCE_RE.sub("", raw.strip())
    start = cleaned.find("{")
    astart = cleaned.find("[")
    # A bare JSON array is a legitimate shape too: `[]` is the model's
    # honest "no findings" on pages of pure tabular data, and `[{...}]`
    # is the findings list without its wrapper object.
    if astart >= 0 and (start < 0 or astart < start):
        try:
            arr, _end = json.JSONDecoder().raw_decode(cleaned[astart:])
            return arr if isinstance(arr, list) else None
        except json.JSONDecodeError:
            return None
    if start < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError:
        return None
    f = obj.get("findings")
    return f if isinstance(f, list) else None


def salvage_findings(raw: str) -> list[dict]:
    """Complete findings objects from a truncated output.

    Dense documents (application forms above all) can overflow even the
    doubled token budget; the whole-array parse then fails and every
    finding in the chunk was lost. Each *complete* object in the array is
    still individually well-formed, and every one must still pass the
    verbatim gate — so recovering them loses nothing but the truncated
    tail, and the document keeps its parse_failed flag for the re-read
    queue either way.
    """
    cleaned = _FENCE_RE.sub("", raw.strip())
    dec = json.JSONDecoder()
    out: list[dict] = []
    i = cleaned.find("[")
    if i < 0:
        return out
    i += 1
    while True:
        j = cleaned.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(cleaned[j:])
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            out.append(obj)
        i = j + end
    return out


_PAGE_NUM_RE = re.compile(r"(\d+)")


def coerce_page(value) -> int | None:
    """The prompt asks for an integer but the model sometimes echoes the
    marker ("[PAGE 7]") or a numeric string. Take the number either way —
    the verbatim gate still checks the quote is actually on that page."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = _PAGE_NUM_RE.search(value)
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Corpus plan
# ---------------------------------------------------------------------------


def load_cohort(conn, *, tier: str | None, ref: str | None,
                site: str | None, shard: tuple[int, int] | None = None) -> list[dict]:
    """Documents of applications on live sites, minus those already read
    under this (model, prompt_version)."""
    q = """
        SELECT DISTINCT d.id, a.id, a.application_ref, d.content_sha256,
                        d.kind
        FROM sites s
        JOIN site_members sm ON sm.site_id = s.id
        JOIN applications a  ON a.id = sm.application_id
        JOIN documents d     ON d.application_id = a.id
        WHERE s.retired_at IS NULL
          AND d.content_sha256 IS NOT NULL
          AND d.bytes_path IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM deepread_log l
                          WHERE l.document_id = d.id
                            AND l.model = %s AND l.prompt_version = %s)
    """
    params: list = [MODEL_TAG, PROMPT_VERSION]
    if ref:
        q += " AND a.application_ref = %s"
        params.append(ref)
    if site:
        q += " AND s.site_key = %s"
        params.append(site)
    if shard:
        # Two-device orchestration without coordination: shard k of n
        # takes documents with id % n = k. Disjoint by construction, so
        # runners on separate machines sharing one database can never
        # collide on a document.
        q += " AND d.id %% %s = %s"
        params.extend([shard[1], shard[0]])
    q += " ORDER BY a.application_ref, d.id"
    with conn.cursor() as cur:
        cur.execute(q, params)
        rows = [{"document_id": r[0], "application_id": r[1],
                 "application_ref": r[2], "sha": r[3], "kind": r[4]}
                for r in cur.fetchall()]
    plans = sel.plan_documents(rows)
    for row, plan in zip(rows, plans):
        row["tier"], row["reason"], row["sampled_out"] = \
            plan.tier, plan.reason, plan.sampled_out
    if tier:
        rows = [r for r in rows if r["tier"] == tier]
    return rows


def chunk_pages(pages: list[str], selected: list[int],
                max_chars: int) -> list[tuple[list[int], str]]:
    """Group selected pages into prompt-sized chunks of marked-up text.
    Page numbers in markers are 1-based physical PDF pages."""
    chunks: list[tuple[list[int], str]] = []
    nums: list[int] = []
    parts: list[str] = []
    size = 0
    for i in selected:
        block = f"[PAGE {i + 1}]\n{pages[i]}\n"
        if parts and size + len(block) > max_chars:
            chunks.append((nums, "".join(parts)))
            nums, parts, size = [], [], 0
        nums.append(i + 1)
        parts.append(block)
        size += len(block)
    if parts:
        chunks.append((nums, "".join(parts)))
    return chunks


# ---------------------------------------------------------------------------
# Per-document processing
# ---------------------------------------------------------------------------


def escalate(**payload) -> None:
    ESCALATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with ESCALATION_PATH.open("a") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def log_document(conn, row: dict, *, read_state: str, pages_total: int | None,
                 pages_sent: list[int] | None, inserted: int = 0,
                 failed: int = 0, elapsed: float | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO deepread_log (document_id, application_id, model,
                prompt_version, tier, read_state, pages_total, pages_sent,
                findings_inserted, quotes_failed, elapsed_s)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (document_id, model, prompt_version) DO NOTHING""",
            (row["document_id"], row["application_id"], MODEL_TAG,
             PROMPT_VERSION, row["tier"], read_state, pages_total,
             pages_sent, inserted, failed, elapsed))
    conn.commit()


def verify_and_insert(conn, row: dict, findings: list[dict],
                      pages: list[str], sent: list[int]) -> tuple[int, int]:
    """The verbatim gate, then storage. Returns (inserted, failed)."""
    inserted = failed = 0
    sent_set = set(sent)
    with conn.cursor() as cur:
        for f in findings:
            quote = (f.get("evidence_text") or "").strip()
            if not quote or not f.get("signal_type"):
                continue
            page = coerce_page(f.get("evidence_page"))
            verified_page = None
            candidates = []
            if page and 1 <= page <= len(pages):
                candidates = [page, page - 1, page + 1]
            for p in candidates + [p for p in sent if p not in candidates]:
                if 1 <= p <= len(pages) and quote_on_page(quote, pages[p - 1]):
                    verified_page = p
                    break
            if verified_page is None:
                failed += 1
                escalate(reason="quote_failed_verification",
                         application_ref=row["application_ref"],
                         sha=row["sha"], document_id=row["document_id"],
                         claimed_page=page, pages_sent=sorted(sent_set),
                         finding=f)
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
                 f.get("value_unit"), quote, verified_page, MODEL_TAG))
            inserted += 1
    conn.commit()
    return inserted, failed


def process_document(conn, row: dict, *, max_chars: int,
                     max_tokens: int) -> str:
    """Run one document end to end; returns a short status string."""
    if row["tier"] == "skip":
        log_document(conn, row, read_state="skipped_graphical",
                     pages_total=None, pages_sent=None)
        return "skip (graphical)"
    if row["sampled_out"]:
        log_document(conn, row, read_state="sampled_out",
                     pages_total=None, pages_sent=None)
        return "sampled out"

    cache = extract.cache_path_for("documents", row["application_ref"],
                                   row["sha"])
    if not cache.exists():
        log_document(conn, row, read_state="no_text",
                     pages_total=None, pages_sent=None)
        return "no cached text"
    pages = json.loads(cache.read_text()).get("pages") or []
    if not any(p.strip() for p in pages):
        log_document(conn, row, read_state="no_text",
                     pages_total=len(pages), pages_sent=None)
        return "empty text layer"

    selected = sel.select_pages(pages, tier=row["tier"])
    chunks = chunk_pages(pages, selected, max_chars)
    sent = [n for nums, _t in chunks for n in nums]

    t0 = time.time()
    inserted = failed = 0
    parse_failed = False
    for nums, text in chunks:
        raw, _el = mlx_generate(text, max_tokens)
        findings = parse_findings(raw)
        if findings is None:
            # Most likely truncation — one retry with double the budget.
            raw, _el = mlx_generate(text, max_tokens * 2)
            findings = parse_findings(raw)
        if findings is None:
            # Still truncated: salvage the complete objects, keep the
            # parse_failed flag so the chunk stays in the re-read queue.
            parse_failed = True
            findings = salvage_findings(raw)
            escalate(reason="parse_failed",
                     application_ref=row["application_ref"], sha=row["sha"],
                     document_id=row["document_id"], pages_sent=nums,
                     salvaged=len(findings), raw_tail=raw[-400:])
            if not findings:
                continue
        ins, fl = verify_and_insert(conn, row, findings, pages, nums)
        inserted += ins
        failed += fl
    elapsed = time.time() - t0

    log_document(conn, row,
                 read_state="parse_failed" if parse_failed else "read",
                 pages_total=len(pages), pages_sent=sent,
                 inserted=inserted, failed=failed, elapsed=elapsed)
    return (f"{inserted} findings"
            + (f", {failed} failed gate" if failed else "")
            + (", PARSE FAIL" if parse_failed else "")
            + f"  [{len(sent)}/{len(pages)} pages, {elapsed:.0f}s]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tier", choices=["A", "B", "C"], default=None)
    ap.add_argument("--ref", default=None, help="Single application_ref")
    ap.add_argument("--site", default=None, help="Single site_key")
    ap.add_argument("--max-chars", type=int, default=16000,
                    help="Chunk budget in characters of marked-up text.")
    # A cap, not a target: sparse documents stop early regardless, so a
    # generous budget costs nothing there and spares dense documents the
    # doubled-retry regeneration that was eating half an hour on the worst.
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report the plan without loading the model.")
    ap.add_argument("--shard", default=None, metavar="K/N",
                    help="Process only documents with id %% N == K "
                         "(e.g. 0/2 and 1/2 on two machines sharing "
                         "the database).")
    args = ap.parse_args()

    shard = None
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        if not 0 <= k < n:
            ap.error("--shard K/N requires 0 <= K < N")
        shard = (k, n)

    with db.connect() as conn:
        rows = load_cohort(conn, tier=args.tier, ref=args.ref, site=args.site,
                           shard=shard)
        # Tier A first: statements and consultee responses carry the
        # disclosures, so early hours produce editorial value even if the
        # run is interrupted.
        order = {"A": 0, "B": 1, "C": 2, "skip": 3}
        rows.sort(key=lambda r: (order.get(r["tier"], 9),
                                 r["application_ref"]))
        if args.limit:
            rows = rows[: args.limit]

        by_tier: dict[str, int] = {}
        for r in rows:
            key = ("sampled_out" if r["sampled_out"] else r["tier"])
            by_tier[key] = by_tier.get(key, 0) + 1
        print(f"deep-read cohort: {len(rows)} documents pending "
              f"({', '.join(f'{k}:{v}' for k, v in sorted(by_tier.items()))}) "
              f"— model {MODEL_TAG}, prompt v{PROMPT_VERSION}")
        if args.dry_run or not rows:
            return

    t0 = time.time()
    for i, row in enumerate(rows, 1):
        try:
            # A connection per document: over a multi-day run a single
            # held connection is the thing most likely to die, and a
            # broken one would turn every subsequent document into a
            # spurious failure. A brief retry ladder rides out transient
            # outages (the laptop hosting the database napping, a wifi
            # blip) at the cost of pausing, not skipping.
            import psycopg2
            for attempt in range(4):
                try:
                    with db.connect() as doc_conn:
                        status = process_document(doc_conn, row,
                                                  max_chars=args.max_chars,
                                                  max_tokens=args.max_tokens)
                    break
                except (psycopg2.OperationalError,
                        psycopg2.InterfaceError):
                    if attempt == 3:
                        raise
                    wait = 30 * (attempt + 1)
                    print(f"  database unreachable — retrying {row['application_ref']} "
                          f"in {wait}s (attempt {attempt + 2}/4)")
                    time.sleep(wait)
        except KeyboardInterrupt:
            print("\ninterrupted — resume with the same command")
            return
        except Exception as exc:
            status = f"ERROR {type(exc).__name__}: {str(exc)[:100]}"
            escalate(reason="exception",
                     application_ref=row["application_ref"],
                     sha=row["sha"], document_id=row["document_id"],
                     error=status)
        print(f"  [{i}/{len(rows)}] {row['application_ref']} "
              f"{(row['kind'] or '')[:40]:40} {status}")
        if i % 25 == 0:
            rate = i / ((time.time() - t0) / 3600)
            print(f"  --- {rate:.0f} docs/hour; "
                  f"~{(len(rows) - i) / max(rate, 1):.1f}h remaining ---")
    print(f"\ndone: {len(rows)} documents in "
          f"{(time.time() - t0) / 3600:.1f}h")


if __name__ == "__main__":
    main()
