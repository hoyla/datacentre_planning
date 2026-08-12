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
from dcp import signal_families  # noqa: E402

MODEL_PATH = "mlx-community/Qwen3.6-35B-A3B-4bit"
MODEL_TAG = "mlx:Qwen3.6-35B-A3B-4bit"
ESCALATION_PATH = ROOT / "data" / "deepread_escalations.jsonl"
# Work finished while the database was unreachable, waiting to be
# written. The Studio reads; the database lives on the laptop, and the
# laptop is a laptop — it sleeps, it leaves the house, it changes
# network. Before this existed an outage cost the *inference*: four
# retries over three minutes, then the document was escalated and
# everything the model had produced for it was discarded. At ~9s a
# document that is the expensive half of the work thrown away for a
# reason that has nothing to do with the document.
SPOOL_PATH = ROOT / "data" / "deepread_spool.jsonl"
SPOOL_DONE_PATH = ROOT / "data" / "deepread_spool_drained.jsonl"

# How often to look for the database while offline. Long enough not to
# stall reading, short enough that a laptop reopened over lunch is
# noticed within a couple of documents.
PROBE_EVERY = 120.0

# v1.0 is what the current corpus was read under and must not change: it
# is half of the UNIQUE(document_id, model, prompt_version) resume
# contract, so editing it in place would orphan 18,000 completed reads and
# silently re-read them. v2.0 fixes the taxonomy fragmentation v1.0
# caused, and is opt-in via --prompt-version until a full re-run is
# actually wanted. See dcp/signal_families.py for why.
PROMPT_VERSION = "1.0"
DEFAULT_PROMPT_VERSION = "1.0"

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

# --- prompt v2.0 -----------------------------------------------------------
# Identical to v1.0 in what it extracts and in the verbatim-quote
# requirement. The single change is the taxonomy: v1.0 asked only for a
# free-form snake_case label and produced 54,044 of them, which made the
# findings unfilterable. v2.0 asks for a controlled `signal_family`
# alongside the free-text `signal_type`, so the index is usable without
# losing the specificity that made the free label worth having.
#
# The family list is rendered from dcp/signal_families.py rather than
# written out here, so the prompt cannot drift from the mapper.

PROMPT_V2 = """\
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
  "signal_family": the broad category, from the controlled list below
  "signal_type":   a short snake_case label of your own naming the
                   specific fact, as precisely as you like — this sits
                   beneath the family and is where detail belongs
  "value_text":    the fact in a few words
  "value_number" and "value_unit": if the fact is quantitative, else null
  "evidence_text": a VERBATIM quote from the document supporting it
  "evidence_page": the [PAGE n] number the quote appears on

%(families)s

Where a figure is a quantity, take care over WHOSE quantity it is. These
documents argue for approval by citing market forecasts, national policy
targets and other schemes. A capacity figure is only about this
development if the surrounding text says so; if it describes the market,
a policy ambition or a different site, extract it but name the
signal_type accordingly (for example market_demand_forecast rather than
it_load).

The evidence quote must appear in the document character-for-character —
it is checked automatically, and an invented quote is worse than no
finding. If the document contains nothing relevant, return an empty list.

Return strict JSON: {"findings": [...]}. No prose outside the JSON.

DOCUMENT:
"""


def prompt_for(version: str) -> str:
    if version == "1.0":
        return PROMPT
    if version == "2.0":
        from dcp import signal_families
        return PROMPT_V2 % {
            "families": signal_families.prompt_vocabulary_block()}
    raise SystemExit(f"unknown prompt version: {version}")

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


def mlx_generate(text: str, max_tokens: int,
                 prompt: str | None = None) -> tuple[str, float]:
    from mlx_lm import generate, load
    if "m" not in _MLX:
        _MLX["m"], _MLX["t"] = load(MODEL_PATH)
    model, tok = _MLX["m"], _MLX["t"]
    messages = [{"role": "user", "content": (prompt or PROMPT) + text}]
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
          -- Settled states only. `not_extracted` is deliberately absent:
          -- those documents re-enter the cohort once the text extractor
          -- has caught up, which is the whole point of distinguishing it
          -- from a document that genuinely holds no words.
          AND NOT EXISTS (SELECT 1 FROM deepread_log l
                          WHERE l.document_id = d.id
                            AND l.model = %s AND l.prompt_version = %s
                            AND l.read_state <> 'not_extracted')
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


def _split_oversized(text: str, limit: int) -> list[str]:
    """One unit's text in pieces of at most `limit`, split on line breaks.

    Line boundaries because a spreadsheet row is the unit of meaning here,
    and a quote cut in half is a quote the verbatim gate will reject —
    which would turn an oversized document into a silently empty one
    rather than a read one. A single line longer than the limit is still
    passed through whole: truncating it would corrupt the evidence, and
    the model refusing one enormous row is a better failure than this
    function inventing a shorter one.
    """
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if buf and size + len(line) > limit:
            out.append("".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf:
        out.append("".join(buf))
    return out or [text]


def chunk_pages(pages: list[str], selected: list[int],
                max_chars: int) -> list[tuple[list[int], str]]:
    """Group selected pages into prompt-sized chunks of marked-up text.

    Page numbers in markers are 1-based physical PDF pages.

    A unit larger than `max_chars` is split across several chunks that
    keep its marker, so provenance still points at the sheet or page the
    text came from. This matters only since the format loaders landed: a
    PDF page is a few thousand characters and never tripped the limit,
    but one worksheet can be 1.3 million. The old guard could not help,
    because it only fired when a chunk was already non-empty — a single
    oversized block always went through whole, and the model answered
    with truncated JSON. That is the whole of the remaining parse-failure
    backlog: two spreadsheets, one of them a data-hall schedule reading
    "UP4 - 4.080MW DATAHALL DIRECT AIR SOLUTION @ 100% LOAD".
    """
    chunks: list[tuple[list[int], str]] = []
    nums: list[int] = []
    parts: list[str] = []
    size = 0
    for i in selected:
        marker = f"[PAGE {i + 1}]\n"
        body = f"{pages[i]}\n"
        # Room for the marker on every piece, and never a non-positive
        # budget however small max_chars is set.
        budget = max(1, max_chars - len(marker))
        pieces = ([body] if len(body) <= budget
                  else _split_oversized(body, budget))
        for piece in pieces:
            block = marker + piece
            if parts and size + len(block) > max_chars:
                chunks.append((nums, "".join(parts)))
                nums, parts, size = [], [], 0
            if (i + 1) not in nums:
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
                 failed: int = 0, elapsed: float | None = None,
                 model: str | None = None) -> None:
    """Record what became of one document, under `model` (default local).

    The batch readers pass their own tag. The upsert below is the only
    correct way to write this table — a second copy of it in another
    runner is how `not_extracted` came to outlive the extraction that
    fixed it — so callers reach for this rather than their own INSERT.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO deepread_log (document_id, application_id, model,
                prompt_version, tier, read_state, pages_total, pages_sent,
                findings_inserted, quotes_failed, elapsed_s)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            -- Upsert, because a document can legitimately be logged
            -- twice: `not_extracted` on a pass before the text existed,
            -- then read properly afterwards. DO NOTHING left the first
            -- verdict standing and the coverage figures wrong. A
            -- successful read is never overwritten by a later failure.
            ON CONFLICT (document_id, model, prompt_version) DO UPDATE SET
                read_state = EXCLUDED.read_state,
                tier = EXCLUDED.tier,
                pages_total = EXCLUDED.pages_total,
                pages_sent = EXCLUDED.pages_sent,
                findings_inserted = EXCLUDED.findings_inserted,
                quotes_failed = EXCLUDED.quotes_failed,
                elapsed_s = EXCLUDED.elapsed_s,
                completed_at = now()
            WHERE deepread_log.read_state <> 'read'""",
            (row["document_id"], row["application_id"], model or MODEL_TAG,
             PROMPT_VERSION, row["tier"], read_state, pages_total,
             pages_sent, inserted, failed, elapsed))
    # The one commit per document. Findings inserted by verify_and_insert
    # stay uncommitted until this row lands, so a death anywhere between
    # chunk and log rolls the whole document back and the next run
    # re-reads it cleanly instead of duplicating it.
    conn.commit()


def _no_nul(v):
    """Postgres text cannot hold NUL (0x00) and raises on it. One arrived
    in a gpt-5 finding after 460,000 findings without one -- the model can
    emit what the source never contained -- so every string is stripped at
    the database boundary rather than trusting any reader not to."""
    return v.replace("\x00", "") if isinstance(v, str) else v

def verify_findings(row: dict, findings: list[dict],
                    pages: list[str], sent: list[int]) -> tuple[list[tuple], int]:
    """The verbatim gate, with no database attached. Returns (rows, failed).

    Split from the insert so that a document read while the database
    is unreachable is still *verified* — against its own page text,
    which is local — and the admissible rows can wait in the spool
    instead of the reading being thrown away.

    The gate stays here rather than moving to drain time on purpose:
    it is what decides whether a finding may be stored at all, and
    deferring it would mean parking unverified model output in a file
    that a later run inserts on trust.
    """
    values: list[tuple] = []
    failed = 0
    sent_set = set(sent)
    if True:
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
            # Under v2.0 the model names the family directly; the local
            # path has no schema enforcement, so an out-of-vocabulary
            # answer is mapped from the label instead of being trusted.
            label = str(f["signal_type"])[:80]
            supplied = f.get("signal_family")
            if supplied:
                family = signal_families.validate_family(supplied, label)
                source = ("model" if family == supplied
                          else "derived_fallback")
            else:
                family = signal_families.family_for(label)
                source = "derived"
            # ON CONFLICT against the content key (migration 012): a
            # document processed twice — a killed run, a parse_failed
            # retry — re-derives the same findings, and re-deriving must
            # not re-insert. 20,377 duplicate rows existed before the
            # index did. rowcount keeps the inserted count honest when
            # the guard absorbs one.
            values.append((
                row["application_id"], row["document_id"],
                _no_nul(label), family, source,
                _no_nul(f.get("value_text")), num,
                _no_nul(f.get("value_unit")), _no_nul(quote),
                verified_page, MODEL_TAG, PROMPT_VERSION))
    return values, failed


def insert_verified(conn, values: list[tuple]) -> int:
    """Write gated findings. Returns how many were new.

    Deliberately no commit: findings become visible only alongside the
    `deepread_log` row that records they were read, in the one commit
    `log_document` makes. Committing per chunk was how 20,377 duplicates
    happened — chunks landed, the process died before the log row, and
    the cohort query re-offered the document.
    """
    inserted = 0
    with conn.cursor() as cur:
        for v in values:
            cur.execute("""
                INSERT INTO findings (application_id, document_id,
                    signal_type, signal_family, family_source, value_text,
                    value_number, value_unit, evidence_text, evidence_page,
                    model, prompt_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (application_id, document_id, model,
                    prompt_version, signal_type, md5(value_text),
                    value_number, value_unit, md5(evidence_text),
                    evidence_page)
                DO NOTHING""", v)
            inserted += cur.rowcount
    return inserted


# The columns `findings_content_key` compares, as offsets into the value
# tuples `verify_findings` builds. `signal_family` and `family_source`
# are deliberately absent: they are derived, and the index does not
# distinguish rows differing only there.
CONTENT_KEY = (0, 1, 10, 11, 2, 5, 6, 7, 8, 9)


def dedupe_verified(values: list[tuple]) -> list[tuple]:
    """Drop the rows `findings_content_key` would collapse anyway.

    A long document routinely produces the same finding from the same
    quote more than once — chunk overlap, and repeated boilerplate in a
    document whose parse went wrong. Postgres absorbs that silently, so
    online it never mattered.

    Offline it did. The spool wrote every row and reported how many it
    wrote, while an online read reports what Postgres inserted, so one
    column of one log meant two different things: on 2026-08-12 two
    spooled documents claimed 230 and 142 findings where 73 and 32
    landed. Deduping here rather than printing a second number also
    means the spool holds exactly what the drain will insert.

    It is an estimate of one thing only — rows already in `findings` from
    an earlier partial write would still be absorbed by the index — so
    the drain's own total stays the authority.
    """
    seen: set[tuple] = set()
    out: list[tuple] = []
    for v in values:
        key = tuple(v[i] for i in CONTENT_KEY)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def spool(row: dict, *, values: list[tuple], read_state: str,
          pages_total: int | None, pages_sent: list[int] | None,
          failed: int = 0, elapsed: float | None = None) -> None:
    """Park a finished document until the database can take it.

    Append-only, one JSON object per document, flushed immediately: the
    spool exists precisely for the case where things are going wrong, so
    it must survive the process dying moments later.

    What is stored is the *verified* rows, not the model's raw output —
    the gate has already run against the local page text. Replaying this
    is therefore an insert, never a re-judgement.
    """
    SPOOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "document_id": row["document_id"],
        "application_id": row["application_id"],
        "application_ref": row["application_ref"],
        "sha": row["sha"],
        "tier": row["tier"],
        "read_state": read_state,
        "pages_total": pages_total,
        "pages_sent": pages_sent,
        "failed": failed,
        "elapsed": elapsed,
        "values": [list(v) for v in values],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with SPOOL_PATH.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


def drain_spool(conn) -> tuple[int, int]:
    """Write everything the spool is holding. Returns (documents, findings).

    Ordinary inserts through the ordinary path, so the content-key guard
    and the `deepread_log` upsert apply exactly as they would have at
    read time — replaying a document already written is a no-op rather
    than a duplicate.

    Drained records move to a companion file rather than being deleted:
    the same append-only reflex as everywhere else, and it leaves
    evidence of what an outage actually cost.
    """
    if not SPOOL_PATH.exists():
        return 0, 0
    records = []
    for line in SPOOL_PATH.read_text().splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn final line costs one document
    if not records:
        return 0, 0
    docs = findings = 0
    for rec in records:
        row = {k: rec[k] for k in ("document_id", "application_id",
                                   "application_ref", "sha", "tier")}
        values = [tuple(v) for v in rec["values"]]
        inserted = insert_verified(conn, values) if values else 0
        log_document(conn, row, read_state=rec["read_state"],
                     pages_total=rec["pages_total"],
                     pages_sent=rec["pages_sent"],
                     inserted=inserted, failed=rec["failed"],
                     elapsed=rec["elapsed"])
        docs += 1
        findings += inserted
    with SPOOL_DONE_PATH.open("a") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    SPOOL_PATH.unlink()
    return docs, findings


def commit_or_spool(conn, row: dict, *, values: list[tuple], read_state: str,
                    pages_total: int | None, pages_sent: list[int] | None,
                    failed: int = 0, elapsed: float | None = None) -> int:
    """Write the document, or park it if there is nowhere to write to.

    `conn` is None when the run is in offline mode. The reading has
    already happened either way — this is only about where the result
    goes, which is the whole point: an unreachable database should cost
    a write, not an inference.
    """
    if conn is None:
        keep = dedupe_verified(values)
        spool(row, values=keep, read_state=read_state,
              pages_total=pages_total, pages_sent=pages_sent,
              failed=failed, elapsed=elapsed)
        return len(keep)
    inserted = insert_verified(conn, values) if values else 0
    log_document(conn, row, read_state=read_state, pages_total=pages_total,
                 pages_sent=pages_sent, inserted=inserted, failed=failed,
                 elapsed=elapsed)
    return inserted


def settle_spool() -> None:
    """Try to land whatever the spool is holding, or say what is held.

    Reached on every exit — a finished cohort, a requested stop, a
    Ctrl-C. Work sitting in the spool is read, verified and invisible, so
    no exit path gets to be silent about it. The Ctrl-C path used to
    `return` past this, which meant the one exit most likely to happen
    during an outage was the one that said nothing.
    """
    if not SPOOL_PATH.exists():
        return
    import psycopg2
    try:
        with db.connect() as conn:
            docs, found = drain_spool(conn)
        print(f"drained {docs} spooled documents, {found} findings")
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        held = sum(1 for _ in SPOOL_PATH.open())
        print(f"WARNING: database still unreachable — {held} documents "
              f"remain in {SPOOL_PATH}. They are read and verified; "
              f"re-run when it is back and they will be written first.")


# Set by SIGTERM, read at each document boundary. A flag rather than an
# exception because the point of TERM is to stop *without* throwing away
# a document mid-inference: on a large Environmental Statement that is up
# to an hour and a half of Studio time, and the runbook has promised this
# behaviour since before anything implemented it.
_STOP = {"requested": False}


def request_stop(signum, frame) -> None:
    """Ask for a stop at the next document boundary.

    Python runs a signal handler at the next bytecode boundary in the
    main thread, and MLX generation is a long call into C, so this
    acknowledgement appears when the current *chunk* finishes rather than
    instantly. That is a delay of seconds to a couple of minutes, not a
    failure to stop. `kill -9` is the immediate option and costs the
    document in flight.
    """
    if _STOP["requested"]:
        return
    _STOP["requested"] = True
    print("\nstop requested — finishing the current document first "
          "(kill -9 to stop now, at the cost of re-reading it)", flush=True)


def install_stop_handler() -> None:
    """Make SIGTERM a graceful stop, and make SIGINT arrive at all.

    Without the first, TERM took Python's default disposition and killed
    the process where it stood. Nothing was corrupted — findings stay
    uncommitted until the `deepread_log` row lands, so the transaction
    rolled back and resume re-read the document cleanly — but the runbook
    said TERM 'lets the current document finish and its row commit', and
    it did not. Documents up to 86 minutes long were being thrown away by
    the documented way of stopping.

    The second is subtler. A shell sets SIGINT to SIG_IGN for a command
    it starts in the background, and Python honours an inherited SIG_IGN
    rather than installing its own handler — so the reader, which is
    always started as `nohup … &` over ssh, ignored SIGINT completely and
    `except KeyboardInterrupt` could never run. Measured, after a `kill
    -INT` was delivered to a live run and the run read on to completion.
    Restoring the default handler gives three honest levels of stopping:
    TERM finishes the document, INT abandons it, -9 takes the process.
    """
    import signal
    signal.signal(signal.SIGTERM, request_stop)
    if signal.getsignal(signal.SIGINT) == signal.SIG_IGN:
        signal.signal(signal.SIGINT, signal.default_int_handler)


class Sink:
    """Where a finished document goes, and the only thing that connects.

    It holds no connection between documents and opens one only at commit
    time — *after* the read. That ordering is the whole point. The
    connection used to be opened first and held across the read, so an
    outage beginning mid-document surfaced at commit, and the retry
    re-read the document from scratch: two outages on 2026-08-12 spent
    696s and 576s of Studio time re-reading documents whose inference was
    finished and whose findings were already through the verbatim gate.

    So the retry ladder here retries the *write*. PR #50 made an outage
    cost a write rather than an inference for every document read while
    already offline; this extends that to the one document that discovers
    the outage, which was the only one still paying twice.
    """

    def __init__(self) -> None:
        self.offline = False
        self._probe_at = 0.0

    def _going_offline(self) -> None:
        self.offline = True
        self._probe_at = time.time() + PROBE_EVERY

    def _probe(self) -> None:
        """While offline, look for the database and drain if it is back.

        Bounded by PROBE_EVERY: retrying on every document would spend
        the connect timeout per document discovering the same outage.
        """
        import psycopg2
        if not self.offline or time.time() < self._probe_at:
            return
        try:
            with db.connect() as probe:
                docs, found = drain_spool(probe)
            self.offline = False
            print(f"  database back — drained {docs} documents, "
                  f"{found} findings from the spool")
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            self._probe_at = time.time() + PROBE_EVERY

    def commit(self, row: dict, *, values: list[tuple], read_state: str,
               pages_total: int | None, pages_sent: list[int] | None,
               failed: int = 0, elapsed: float | None = None) -> int:
        """Store one finished document. Returns findings stored.

        Two short retries ride out a blip; past that the run goes offline
        and the result is spooled. A connection per document is
        deliberate — over a multi-day run a single held connection is the
        thing most likely to die, and a broken one would turn every
        subsequent document into a spurious failure.
        """
        import psycopg2
        self._probe()
        if not self.offline:
            for attempt in range(3):
                try:
                    with db.connect() as conn:
                        return commit_or_spool(
                            conn, row, values=values, read_state=read_state,
                            pages_total=pages_total, pages_sent=pages_sent,
                            failed=failed, elapsed=elapsed)
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    if attempt == 2:
                        self._going_offline()
                        print("  database unreachable — going offline; "
                              "reading continues and results are spooled")
                        break
                    wait = 15 * (attempt + 1)
                    print(f"  database unreachable — retrying the write "
                          f"for {row['application_ref']} in {wait}s")
                    time.sleep(wait)
        return commit_or_spool(
            None, row, values=values, read_state=read_state,
            pages_total=pages_total, pages_sent=pages_sent,
            failed=failed, elapsed=elapsed)


def process_document(sink: Sink, row: dict, *, max_chars: int,
                     max_tokens: int, prompt: str | None = None) -> str:
    """Run one document end to end; returns a short status string.

    Reads first, then hands the result to `sink`, which is what opens
    a connection. Nothing here knows or cares whether the database is
    reachable."""
    if row["tier"] == "skip":
        sink.commit(row, values=[], read_state="skipped_graphical",
                        pages_total=None, pages_sent=None)
        return "skip (graphical)"
    if row["sampled_out"]:
        sink.commit(row, values=[], read_state="sampled_out",
                        pages_total=None, pages_sent=None)
        return "sampled out"

    cache = extract.cache_path_for("documents", row["application_ref"],
                                   row["sha"])
    if not cache.exists():
        # `not_extracted`, not `no_text`. The two are opposite facts and
        # were recorded identically: one says the document contains no
        # words, the other that nobody has looked. 4,836 documents were
        # skipped under the second while reading as the first, and the
        # cohort query never revisited them — a text-layered 86-page
        # supporting statement counted as analysed-and-empty.
        sink.commit(row, values=[], read_state="not_extracted",
                        pages_total=None, pages_sent=None)
        return "not extracted yet"
    payload = json.loads(cache.read_text())
    if payload.get("engine") in extract.STALE_ENGINES:
        # The same fact in a third costume: a cache written by an extractor
        # that had no loader for this format. Empty because nobody could
        # read it, not because it holds no words.
        sink.commit(row, values=[], read_state="not_extracted",
                        pages_total=None, pages_sent=None)
        return "no loader for this format"
    pages = payload.get("pages") or []
    if not any(p.strip() for p in pages):
        sink.commit(row, values=[], read_state="no_text",
                        pages_total=len(pages), pages_sent=None)
        return "empty text layer"

    selected = sel.select_pages(pages, tier=row["tier"])
    if sel.selection_is_large(pages, selected):
        # Announced, not trimmed. Nothing is dropped — this exists so a
        # genuinely expensive document is visible before it starts to
        # look like a hung process.
        escalate(reason="large_document",
                 application_ref=row["application_ref"], sha=row["sha"],
                 document_id=row["document_id"], pages_total=len(pages),
                 pages_selected=len(selected),
                 chars_selected=sum(len(pages[i]) for i in selected))
    chunks = chunk_pages(pages, selected, max_chars)
    sent = [n for nums, _t in chunks for n in nums]

    t0 = time.time()
    verified: list[tuple] = []
    inserted = failed = 0
    parse_failed = False
    for ci, (nums, text) in enumerate(chunks, 1):
        # Per chunk, not per document. A 172-chunk workbook used to print
        # nothing for half an hour and was killed twice as a hang; the
        # database was fine and the model was working the whole time.
        # Anything that takes minutes must say so while it is happening.
        if len(chunks) > 8:
            print(f"      chunk {ci}/{len(chunks)} "
                  f"({row['sha'][:8]}, {time.time() - t0:.0f}s elapsed)",
                  flush=True)
        raw, _el = mlx_generate(text, max_tokens, prompt)
        findings = parse_findings(raw)
        if findings is None:
            # Most likely truncation — one retry with double the budget.
            raw, _el = mlx_generate(text, max_tokens * 2, prompt)
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
        vals, fl = verify_findings(row, findings, pages, nums)
        verified.extend(vals)
        failed += fl
    elapsed = time.time() - t0

    inserted = sink.commit(
        row, values=verified,
        # Deliberately still "read". Capping is page selection, not a
        # different outcome, and `pages_sent` beside `pages_total`
        # already records exactly what was and was not looked at — the
        # same way ordinary page filtering is recorded. Inventing a state
        # here would change what `read_state = 'read'` counts in
        # site_profile.load_coverage_detail and move published coverage
        # figures as a side effect of a performance fix.
        read_state="parse_failed" if parse_failed else "read",
        pages_total=len(pages), pages_sent=sent,
        failed=failed, elapsed=elapsed)
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
    ap.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION,
                    choices=["1.0", "2.0"],
                    help="1.0 is what the existing corpus was read under. "
                         "2.0 adds the controlled signal_family vocabulary "
                         "that stops taxonomy fragmentation, and starts a "
                         "SEPARATE read of the whole corpus — it shares no "
                         "resume state with 1.0.")
    args = ap.parse_args()

    global PROMPT_VERSION
    PROMPT_VERSION = args.prompt_version
    active_prompt = prompt_for(PROMPT_VERSION)
    if PROMPT_VERSION != DEFAULT_PROMPT_VERSION:
        # Changing version re-reads everything, because the resume
        # contract is keyed on it. That is correct for a deliberate
        # re-run and expensive as an accident, so make it loud.
        print(f"*** prompt v{PROMPT_VERSION} selected: this is a full "
              f"re-read, not a resume of the v{DEFAULT_PROMPT_VERSION} "
              f"corpus ***")

    shard = None
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        if not 0 <= k < n:
            ap.error("--shard K/N requires 0 <= K < N")
        shard = (k, n)

    with db.connect() as conn:
        # Before the cohort query, not after: resume works by asking the
        # database which documents are already logged, and anything
        # sitting in the spool is read but unlogged. Draining second
        # would hand back a cohort containing documents we have already
        # read, and they would be read again.
        if SPOOL_PATH.exists():
            docs, found = drain_spool(conn)
            print(f"drained {docs} spooled documents from a previous run "
                  f"({found} findings) before selecting the cohort")
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

    # One sink for the run: it owns the offline state and is the only
    # thing that opens a connection, at commit time rather than before
    # the read. The loop below therefore has no database in it at all.
    sink = Sink()
    install_stop_handler()
    t0 = time.time()
    done = 0
    interrupted = False
    for i, row in enumerate(rows, 1):
        try:
            status = process_document(sink, row, max_chars=args.max_chars,
                                      max_tokens=args.max_tokens,
                                      prompt=active_prompt)
            if sink.offline:
                status += " [spooled]"
            done = i
        except KeyboardInterrupt:
            # `break`, not `return`. Returning here skipped the spool
            # settle below, so interrupting an offline run left hundreds
            # of read-and-verified documents on disk with nothing said
            # about them — the one moment the warning matters most.
            print("\ninterrupted — the current document will be re-read "
                  "on resume")
            interrupted = True
            break
        except Exception as exc:
            status = f"ERROR {type(exc).__name__}: {str(exc)[:100]}"
            escalate(reason="exception",
                     application_ref=row["application_ref"],
                     sha=row["sha"], document_id=row["document_id"],
                     error=status)
        # The sha matters: one application here has two documents both
        # called SUPPORTING INFORMATION, and with only ref and kind
        # printed they are the same line. An hour went into diagnosing a
        # "regression" that was simply the other document.
        print(f"  [{i}/{len(rows)}] {row['application_ref']} "
              f"{row['sha'][:8]} {(row['kind'] or '')[:40]:40} {status}")
        if i % 25 == 0:
            rate = i / ((time.time() - t0) / 3600)
            print(f"  --- {rate:.0f} docs/hour; "
                  f"~{(len(rows) - i) / max(rate, 1):.1f}h remaining ---")
        if _STOP["requested"]:
            print("  stopping at a document boundary as asked — nothing "
                  "in flight, nothing to re-read")
            break
    settle_spool()
    print(f"\n{'stopped' if _STOP['requested'] or interrupted else 'done'}: "
          f"{done} of {len(rows)} documents in "
          f"{(time.time() - t0) / 3600:.1f}h")


if __name__ == "__main__":
    main()
