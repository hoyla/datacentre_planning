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
                DO NOTHING""",
                (row["application_id"], row["document_id"],
                 _no_nul(label), family, source,
                 _no_nul(f.get("value_text")), num,
                 _no_nul(f.get("value_unit")), _no_nul(quote),
                 verified_page, MODEL_TAG, PROMPT_VERSION))
            inserted += cur.rowcount
    # No commit here, deliberately: findings only become visible together
    # with the deepread_log row that records they were read, in the one
    # commit log_document makes. Committing per chunk was how 20,377
    # duplicates happened — chunks landed, the process died before the
    # log row, and the cohort query re-offered the document.
    return inserted, failed


def process_document(conn, row: dict, *, max_chars: int,
                     max_tokens: int, prompt: str | None = None) -> str:
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
        # `not_extracted`, not `no_text`. The two are opposite facts and
        # were recorded identically: one says the document contains no
        # words, the other that nobody has looked. 4,836 documents were
        # skipped under the second while reading as the first, and the
        # cohort query never revisited them — a text-layered 86-page
        # supporting statement counted as analysed-and-empty.
        log_document(conn, row, read_state="not_extracted",
                     pages_total=None, pages_sent=None)
        return "not extracted yet"
    payload = json.loads(cache.read_text())
    if payload.get("engine") in extract.STALE_ENGINES:
        # The same fact in a third costume: a cache written by an extractor
        # that had no loader for this format. Empty because nobody could
        # read it, not because it holds no words.
        log_document(conn, row, read_state="not_extracted",
                     pages_total=None, pages_sent=None)
        return "no loader for this format"
    pages = payload.get("pages") or []
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
                                                  max_tokens=args.max_tokens,
                                                  prompt=active_prompt)
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
