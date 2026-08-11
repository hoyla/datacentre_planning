"""OpenAI-backed deep-read batch pass — same pipeline, third model tag.

STATUS: exercised 2026-08-10. First live run was gpt-5 over the
60-document validation cohort: 692 findings, 0.9% verbatim-gate failure
(the best of the three readers), and 29% of requests answering nothing
at all — see MAX_COMPLETION_TOKENS and --reasoning-effort below, which
is the whole story of that run.

Three bugs were found by auditing it before it ever spent anything, and
they are worth knowing because each would have been expensive rather
than loud: the validation cohort selected all 18,044 documents Sonnet
had read rather than a sample; the bulk cohort excluded any document
any model had merely *logged*, dropping 5,694 readable ones whose only
row said `not_extracted`; and collect never opened the batch error
file, so an API-level failure produced no log row, stayed in the
cohort, and was resubmitted and recharged on every later run.

Exists because the organisation holds OpenAI API credits, and the pipeline
was deliberately built model-agnostic: the verbatim-quote gate (not the
model) is the hallucination protection, findings carry their model tag in
the append-only store, and the prompt/chunking/gate are imported from
scripts/deepread_run.py so no provider path can drift from another.

Flow mirrors scripts/deepread_escalate.py but speaks OpenAI's Batch API
(JSONL file upload -> batch -> poll -> download results file) and uses
their enforced-JSON structured outputs. Quality is validated before any
bulk spend, and that is enforced rather than advised: --cohort remaining
refuses to run until a validation batch for the same model tag has been
collected.

Usage:
    scripts/deepread_escalate_openai.py --preflight
    scripts/deepread_escalate_openai.py --list-models
    scripts/deepread_escalate_openai.py --dry-run --cohort remaining --model <id>
    scripts/deepread_escalate_openai.py --dry-run --cohort remaining --unread-only \
        --model <id>        # the coverage gap only; see --unread-only
    scripts/deepread_escalate_openai.py --submit --cohort validation --model <id> \
        [--reasoning-effort minimal] [--max-spend-usd N --rate-in N --rate-out N]
    scripts/deepread_escalate_openai.py --collect [--batch-id ...]
    scripts/compare_readers.py --models openai:<id> claude-sonnet-5 mlx:<id>
"""

from __future__ import annotations

import argparse
import json
import os
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
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set (add it to .env)")
    kwargs = {}
    # Only needed for a legacy key on an account that belongs to more
    # than one organisation: without it the request goes to the default
    # org, which may not be the one holding the credits. A project-scoped
    # key (sk-proj-…) already names both and ignores these.
    if os.environ.get("OPENAI_ORG_ID"):
        kwargs["organization"] = os.environ["OPENAI_ORG_ID"]
    if os.environ.get("OPENAI_PROJECT"):
        kwargs["project"] = os.environ["OPENAI_PROJECT"]
    return OpenAI(**kwargs)


def preflight() -> None:
    """Say which account is about to be charged, before anything is.

    There is more than one OpenAI account in play, and a key is opaque:
    nothing about `sk-…` says which organisation's credits it draws on.
    This makes the answer visible rather than assumed — the same reason
    the Drive folder is pinned by ID and the gate is probed from
    outside.
    """
    key = os.environ.get("OPENAI_API_KEY", "")
    kind = ("project-scoped" if key.startswith("sk-proj-")
            else "legacy/user" if key.startswith("sk-") else "unrecognised")
    print(f"key: …{key[-6:]}  ({kind}, {len(key)} chars)")
    for var in ("OPENAI_ORG_ID", "OPENAI_PROJECT"):
        if os.environ.get(var):
            print(f"{var}: {os.environ[var]}")

    client = _client()
    try:
        models = list(client.models.list())
    except Exception as exc:
        sys.exit(f"the key does not work: {type(exc).__name__}: "
                 f"{str(exc)[:300]}")
    print(f"authenticated: {len(models)} models visible")

    # The org/project the key resolves to, if the API will say. It
    # generally will not for a project-scoped key — no openai-organization
    # header comes back — so this reports the absence rather than
    # printing nothing, which would read as "checked, and fine".
    named = False
    try:
        raw = client.models.with_raw_response.list()
        for h in ("openai-organization", "openai-project"):
            if raw.headers.get(h):
                print(f"{h}: {raw.headers[h]}")
                named = True
    except Exception as exc:
        print(f"could not read response headers: {type(exc).__name__}")
    if not named:
        print("the API does not name the organisation or project for this "
              "key, so WHICH account this bills cannot be confirmed from "
              "here — check the dashboard, and confirm at the far side by "
              "watching the validation spend appear in the project you "
              "expect")

    interesting = [m.id for m in models
                   if any(t in m.id for t in ("gpt-5", "gpt-4.1", "o3", "o4"))]
    if interesting:
        print("candidate models: " + ", ".join(sorted(interesting)[:12]))


MAX_COMPLETION_TOKENS = 8000

# Where the measured cost per request is recorded after a validation
# batch is collected, so the bulk estimate stops being arithmetic on a
# ceiling and becomes arithmetic on observation. This is the whole
# argument for validating first, made concrete.
USAGE_PATH = ROOT / "data" / "openai_measured_usage.json"


# A dry run over the bulk cohort reads one cache file per document. At
# 26,000 documents that is fifteen minutes to answer "roughly how big is
# this", so above this many, sample and scale.
SAMPLE_THRESHOLD = 300


def _measured_usage(model: str) -> dict | None:
    """Observed tokens per request for this model, or None if it has
    never run. Written by --collect."""
    if not USAGE_PATH.exists():
        return None
    try:
        store = json.loads(USAGE_PATH.read_text())
    except Exception:
        return None
    u = store.get(model)
    if not u or not u.get("requests"):
        return None
    return {"requests": u["requests"],
            "in_per_request": u["in"] / u["requests"],
            "out_per_request": u["out"] / u["requests"]}


def _require_validation(model: str) -> None:
    """Refuse a bulk run until a validation batch has been collected for
    this model.

    Quality is unknown until something has been compared against the two
    models that already read these documents. An unvalidated bulk run
    spends the whole budget to discover what sixty documents would have
    told us for the price of a coffee — and the escalate script's own
    header has said so since it was written, without anything enforcing
    it.
    """
    collected = []
    for p in BATCH_DIR.glob("batch_*.json"):
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        if (s.get("cohort") == "validation" and s.get("collected")
                and s.get("model") == model):
            collected.append(p.name)
    if not collected:
        sys.exit(
            f"refusing a bulk run: no collected validation batch for "
            f"{model!r}.\n\n"
            f"  scripts/deepread_escalate_openai.py --submit "
            f"--cohort validation --model {model}\n"
            f"  scripts/deepread_escalate_openai.py --collect\n\n"
            "The validation cohort is 60 documents that Qwen and Sonnet "
            "have both already read, so the comparison is exact and costs "
            "a rounding error. Bulk spend before that is buying an "
            "unknown.")
    print(f"  validation batch found ({collected[0]}) — bulk run allowed")


def model_tag_for(model: str, reasoning_effort: str | None = None) -> str:
    """The model name findings and log rows are stamped with. Namespaced
    so an OpenAI read can never be confused with the Qwen or Sonnet read
    of the same document — the findings unique index includes it.

    Reasoning effort is part of the tag because it changes the reading,
    not just the bill. The first gpt-5 run spent 94% of its output
    budget on reasoning tokens and hit the ceiling on 29% of requests,
    returning nothing for them; a run at a lower effort is a different
    reader and has to be comparable against the first rather than
    silently mixed into it.
    """
    return f"openai:{model}" + (f":{reasoning_effort}" if reasoning_effort
                                else "")


def load_cohort(conn, which: str, sample: int = 0,
                model_tag: str | None = None,
                tiers: tuple[str, ...] = (),
                limit: int = 0,
                unread_only: bool = False) -> list[dict]:
    """'validation' = a small sample of documents already read by BOTH
    other models, for a three-way comparison; 'remaining' = documents
    this model has not read.

    The validation query used to select every document Sonnet had ever
    read — 18,044 of them — while its docstring called it a 54-document
    validation set. Running it "to check quality before bulk spend"
    would have *been* the bulk spend, on documents already read twice.
    It is now what it claims: dual-read documents, sampled.

    The sample is deliberately a spread of ordinary documents rather
    than the escalation cases. Escalations are the hard tail; they
    measure gate-failure rates, not whether the model finds what is
    plainly there in a normal supporting statement, which is the
    question a bulk run turns on.
    """
    if which == "power":
        # A validation cohort weighted to the documents the investigation
        # actually turns on.
        #
        # The plain `validation` sample is drawn across all dual-read
        # documents, which are overwhelmingly application forms and
        # decision notices: of its 60 documents only 4 carry a capacity
        # figure at all. That measures a reader on ordinary prose and
        # then asks it to be trusted with supporting statements, which
        # is the wrong test for a data-centre power investigation.
        #
        # This selects dual-read documents where some model already
        # found a figure in MW, kW, kVA or MVA -- 333 of them, mostly
        # Additional Information, objections and supporting statements.
        # Whether a cheaper configuration still finds those figures is
        # the question worth spending a validation batch on.
        q = """
            SELECT d.id, a.id, a.application_ref, d.content_sha256,
                   d.kind, max(l.tier)
            FROM deepread_log l
            JOIN documents d ON d.id = l.document_id
            JOIN applications a ON a.id = d.application_id
            WHERE l.prompt_version = %s
              AND EXISTS (SELECT 1 FROM findings f
                          WHERE f.document_id = d.id
                            AND lower(coalesce(f.value_unit,'')) IN
                                ('mw','kw','kva','mva'))
            GROUP BY d.id, a.id, a.application_ref, d.content_sha256, d.kind
            HAVING count(*) FILTER (WHERE l.model = 'claude-sonnet-5'
                                      AND l.read_state = 'read') > 0
               AND count(*) FILTER (WHERE l.model LIKE 'mlx%%'
                                      AND l.read_state = 'read') > 0
            ORDER BY md5(d.id::text)"""
        params = [PROMPT_VERSION]
    elif which == "validation":
        q = """
            SELECT d.id, a.id, a.application_ref, d.content_sha256,
                   d.kind, max(l.tier)
            FROM deepread_log l
            JOIN documents d ON d.id = l.document_id
            JOIN applications a ON a.id = d.application_id
            WHERE l.prompt_version = %s
            GROUP BY d.id, a.id, a.application_ref, d.content_sha256, d.kind
            HAVING count(*) FILTER (WHERE l.model = 'claude-sonnet-5'
                                      AND l.read_state = 'read') > 0
               AND count(*) FILTER (WHERE l.model LIKE 'mlx%%'
                                      AND l.read_state = 'read') > 0
            -- Deterministic pseudo-random order: same sample every run,
            -- so a re-validation compares like with like, and no ORDER
            -- BY random() surprises anyone with a different bill.
            ORDER BY md5(d.id::text)"""
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
              -- Scoped to THIS model, and to states that mean the
              -- document was actually processed. The unscoped version
              -- excluded anything any model had logged at all, which
              -- silently dropped 5,694 readable documents whose only
              -- log row said `not_extracted` — the very backlog the
              -- format loaders and migrations 011/013 exist to rescue.
              AND NOT EXISTS (SELECT 1 FROM deepread_log l
                              WHERE l.document_id = d.id
                                AND l.prompt_version = %s
                                AND l.model = %s
                                AND l.read_state <> 'not_extracted')"""
        if not model_tag:
            raise ValueError("the 'remaining' cohort must be scoped to a "
                             "model tag, or it cannot tell what this model "
                             "has already read")
        params = [PROMPT_VERSION, model_tag]
        if unread_only:
            # Close the coverage gap rather than corroborate: keep only
            # documents NO model has read. Without this the cohort is
            # everything *this* model has not read, which on a corpus two
            # other readers have already been over is mostly second
            # opinions — worth having, and a different release.
            #
            # Deliberately NOT scoped to prompt_version, unlike the clause
            # above. This one has to mean what the reader's coverage
            # figure means, and export_reader.py counts a document read if
            # any deepread_log row says 'read', whatever prompt read it. A
            # cohort that disagreed with the front page about which
            # documents are unread would close a gap the page still
            # reported, or bill for documents it already counted.
            q += """
              AND NOT EXISTS (SELECT 1 FROM deepread_log l2
                              WHERE l2.document_id = d.id
                                AND l2.read_state = 'read')"""
        q += """
            ORDER BY a.application_ref, d.id"""
    with conn.cursor() as cur:
        cur.execute(q, params)
        rows = [{"document_id": r[0], "application_id": r[1],
                 "application_ref": r[2], "sha": r[3], "kind": r[4],
                 "tier": r[5]} for r in cur.fetchall()]
    if which in ("validation", "power"):
        # Already-read documents carry a tier from the run that read
        # them; page selection follows it, so the comparison is
        # like-for-like against what the other two models saw.
        return rows[:sample] if sample else rows

    # Planned over the whole universe, not over these rows. Sampling is
    # "every Nth tier-C document within its application", so planning a
    # filtered set samples a different fifth — a cohort scoped to one
    # model's backlog would pull in repetitive documents the global
    # policy had set aside, and the reader would still call them unread.
    # See sel.universe_plan.
    plan_by_id = sel.universe_plan(conn)
    kept = []
    for row in rows:
        plan = plan_by_id.get(row["document_id"])
        if plan is None or not plan.will_read:
            continue
        if tiers and plan.tier not in tiers:
            continue
        row["tier"] = plan.tier
        kept.append(row)
    # Take the cohort in slices when the whole thing is more money than
    # anyone wants to commit on an estimate. The order is deterministic
    # (application_ref, document id), and a collected slice leaves log
    # rows that exclude it from the next call -- so running --limit N
    # repeatedly walks the cohort without overlap and without needing to
    # remember where it got to.
    return kept[:limit] if limit else kept


def do_record_no_text(model: str, reasoning_effort: str | None = None) -> int:
    """Give the unreadable documents a verdict instead of a silence.

    231 documents sit in the cohort holding a cache with no words in it:
    photographs of site notices, plans filed as JPEGs, a 4.7MB Exif photo
    filed as Supporting Information. Both tesseract and Apple Vision read
    them as blank (measured 2026-08-11, 0 of 10 on a like-for-like
    sample), so no OCR pass is going to change the answer.

    Left alone they are indistinguishable from a backlog — held,
    classified as prose, never read, for ever. `no_text` is the verdict
    the schema already has for exactly this, and deepread_run has written
    it for years down the non-batch path. This writes it down the batch
    path too.

    Deliberately its own action rather than a side effect of --submit or
    --dry-run: it writes, and a dry run that quietly wrote rows would be
    a worse trap than the one it fixes. Idempotent — the upsert never
    overwrites a successful read, so a document that later becomes
    readable and is read keeps the read.
    """
    tag = model_tag_for(model, reasoning_effort)
    written = kept = 0
    with db.connect() as conn:
        rows = load_cohort(conn, "remaining", model_tag=tag, unread_only=True)
        for row in rows:
            cache = extract.cache_path_for("documents", row["application_ref"],
                                           row["sha"])
            if not cache.exists():
                continue
            try:
                pages = json.loads(cache.read_text()).get("pages") or []
            except Exception:
                continue
            if any(p.strip() for p in pages):
                kept += 1
                continue
            _dr.log_document(conn, row, read_state="no_text",
                             pages_total=len(pages), pages_sent=None,
                             model=tag)
            written += 1
    print(f"{written:,} documents recorded as no_text under {tag}; "
          f"{kept:,} of the cohort have text and were left alone")
    return written


def build_jsonl(rows: list[dict], model: str, max_chars: int,
                reasoning_effort: str | None = None,
                dropped: dict[str, int] | None = None
                ) -> tuple[list[str], dict]:
    """Requests for a cohort, plus a tally of what never became one.

    `dropped` counts documents the cohort selected and this could not
    build, by reason. It used to `continue` past all three cases in
    silence, which is how a 245-document cohort produced a 3-document
    batch and said nothing: 231 of them held a cache whose every page
    was blank. The count and the cohort then disagree about coverage,
    and only the smaller number is visible — an absence recorded as
    nothing at all, which is the failure mode this project is most
    careful about everywhere else.
    """
    lines, meta = [], {}
    drop = dropped if dropped is not None else {}
    for row in rows:
        cache = extract.cache_path_for("documents", row["application_ref"],
                                       row["sha"])
        if not cache.exists():
            drop["cache missing"] = drop.get("cache missing", 0) + 1
            continue
        try:
            pages = json.loads(cache.read_text()).get("pages") or []
        except Exception:
            drop["cache unreadable"] = drop.get("cache unreadable", 0) + 1
            continue
        if not any(p.strip() for p in pages):
            # Extraction ran and produced no words. Overwhelmingly
            # single-page graphical documents whose kind did not name
            # them as drawings; some are scans OCR read as blank.
            drop["no extractable text"] = drop.get("no extractable text", 0) + 1
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
            body = {"model": model}
            if reasoning_effort:
                # This is copying, not deliberating: the model has to
                # find facts already written on the page and quote them
                # character for character. Left at its default, gpt-5
                # burned 4,965 reasoning tokens per request to do that
                # and ran out of budget before answering 29% of the
                # time.
                body["reasoning_effort"] = reasoning_effort
            lines.append(json.dumps({
                "custom_id": f"{row['document_id']}-{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    **body,
                    # 16,000 was a ceiling nobody costed. A findings
                    # payload for one chunk is hundreds of tokens, not
                    # thousands, and the ceiling is what a worst-case
                    # estimate is built from — so an unnecessarily high
                    # one makes every spend guard useless. There is no
                    # retry in a batch, so it keeps real headroom.
                    "max_completion_tokens": MAX_COMPLETION_TOKENS,
                    "response_format": RESPONSE_FORMAT,
                    "messages": [{"role": "user",
                                  "content": _dr.PROMPT + text}],
                },
            }, ensure_ascii=False))
    return lines, meta


def do_submit(cohort: str, model: str, max_chars: int, dry_run: bool,
              sample: int = 0, rate_in: float = 0.0,
              rate_out: float = 0.0, max_spend: float = 0.0,
              reasoning_effort: str | None = None,
              tiers: tuple[str, ...] = (), limit: int = 0,
              unread_only: bool = False) -> None:
    tag = model_tag_for(model, reasoning_effort)

    # The validation interlock runs FIRST, before a single cache file is
    # opened. It used to sit after the JSONL build, which meant refusing
    # a 26,000-document bulk run took ten minutes of reading documents
    # it was about to decline to submit. A refusal should be instant, or
    # people learn to skip the step that produces it.
    if cohort == "remaining" and not dry_run:
        _require_validation(model)

    with db.connect() as conn:
        rows = load_cohort(conn, cohort, sample=sample, model_tag=tag,
                           tiers=tiers, limit=limit, unread_only=unread_only)

    # A dry run over the whole corpus does not need to build the whole
    # corpus: read a sample and scale. Exact for anything small, and for
    # the bulk cohort the answer is a size decision, not an invoice.
    # A named slice is a slice someone is about to pay for, so it is
    # costed exactly -- building every request rather than extrapolating
    # from 300 of them. Sampling is for answering "how big is the whole
    # thing", not "what will this cost me".
    scale_factor = 1.0
    if dry_run and not limit and len(rows) > SAMPLE_THRESHOLD:
        scale_factor = len(rows) / SAMPLE_THRESHOLD
        print(f"cohort '{cohort}': {len(rows):,} documents — estimating from "
              f"a {SAMPLE_THRESHOLD}-document sample, spread across the "
              f"cohort")
        # Every k-th document, not the first 300. The cohort is ordered by
        # application reference, so the first 300 are one alphabetical
        # corner of the country -- and they turned out to hold shorter
        # documents than average, which made a half-of-tier-A estimate
        # come in 40% under the exact figure. A spread sample crosses
        # every council in the cohort.
        step = max(1, len(rows) // SAMPLE_THRESHOLD)
        rows = rows[::step][:SAMPLE_THRESHOLD]

    dropped: dict[str, int] = {}
    lines, meta = build_jsonl(rows, model, max_chars,
                              reasoning_effort=reasoning_effort,
                              dropped=dropped)
    size_mb = sum(len(l) for l in lines) / 1e6 * scale_factor

    # A spend estimate before the spend. ~4 characters per token is the
    # usual English rule of thumb and is close enough to size a decision;
    # output is bounded by max_completion_tokens but typically lands far
    # below it, so the ceiling is quoted rather than a guess.
    in_chars = sum(len(l) for l in lines) * scale_factor
    in_tok = in_chars / 4
    out_ceiling = len(lines) * scale_factor * MAX_COMPLETION_TOKENS
    n_docs = int(len(meta) * scale_factor)
    n_reqs = int(len(lines) * scale_factor)
    approx = "≈" if scale_factor > 1 else ""
    print(f"cohort '{cohort}': {approx}{n_docs:,} documents, "
          f"{approx}{n_reqs:,} requests, {approx}{size_mb:.0f}MB of JSONL")
    if dropped:
        # Said out loud, because the difference between the cohort and
        # the batch is a coverage claim. These documents are selected,
        # unread, and will stay unread -- which is worth knowing, and is
        # not the same as their not existing.
        total = sum(dropped.values())
        detail = ", ".join(f"{v:,} {k}" for k, v in
                           sorted(dropped.items(), key=lambda kv: -kv[1]))
        print(f"  {total:,} of {len(rows):,} selected documents cannot be "
              f"built into a request: {detail}")
    # If a validation batch has been collected for this model, cost the
    # run on what a request actually consumed. Otherwise all that can
    # honestly be quoted is the ceiling, which is why the first run is a
    # validation run.
    measured = _measured_usage(tag)
    out_expected = None
    if measured:
        out_expected = n_reqs * measured["out_per_request"]
        print(f"  input ≈ {in_tok / 1e6:.1f}M tokens; expected output "
              f"≈ {out_expected / 1e6:.1f}M tokens, measured at "
              f"{measured['out_per_request']:.0f} tokens/request over "
              f"{measured['requests']:,} real requests "
              f"(ceiling {out_ceiling / 1e6:.0f}M)")
    else:
        print(f"  input ≈ {in_tok / 1e6:.1f}M tokens; output ceiling "
              f"{out_ceiling / 1e6:.1f}M tokens — no measured usage for "
              f"{model!r} yet, so only the ceiling can be quoted. Run the "
              f"validation cohort and this becomes a real number.")

    if rate_in or rate_out:
        cost_in = in_tok / 1e6 * rate_in
        ceil_cost = cost_in + out_ceiling / 1e6 * rate_out
        if out_expected is not None:
            exp = cost_in + out_expected / 1e6 * rate_out
            print(f"  at the rates given: ${exp:,.2f} expected, "
                  f"${ceil_cost:,.2f} worst case")
        else:
            print(f"  at the rates given: ${cost_in:,.2f} input alone, "
                  f"${ceil_cost:,.2f} worst case")
        print("  (batch pricing is normally half these list rates)")
    else:
        print("  pass --rate-in / --rate-out (dollars per 1M tokens) for a "
              "cost estimate")
    if dry_run or not lines:
        return

    # ---- spend guards -------------------------------------------------
    # Three of them, because the failure being guarded against is not
    # malice but a wrong flag at the end of a long day: a cohort that
    # looked small, a model that costs ten times another, a resubmission
    # of work already paid for.

    # 1. The validation interlock already ran, at the top, before any
    #    work. (Guard one of three; see _require_validation.)

    # 2. A hard ceiling on the estimate. Deliberately compares against
    #    the OUTPUT CEILING, not the likely spend: the guard should trip
    #    on the worst case, because that is the one nobody predicted.
    if max_spend:
        if not (rate_in or rate_out):
            sys.exit("--max-spend-usd needs --rate-in/--rate-out to mean "
                     "anything. Give the model's list rates.")
        # Checked against the *expected* figure once there is a measured
        # one, because a guard that only ever sees an 800M-token ceiling
        # refuses everything, and a guard that always refuses is a guard
        # people learn to override without reading.
        basis = ("expected" if out_expected is not None else "worst case")
        amount = (in_tok / 1e6 * rate_in
                  + (out_expected if out_expected is not None
                     else out_ceiling) / 1e6 * rate_out)
        if amount > max_spend:
            sys.exit(f"refusing to submit: {basis} ${amount:,.2f} exceeds "
                     f"--max-spend-usd ${max_spend:,.2f}.\n"
                     f"Raise the ceiling deliberately, or shrink the cohort.")
        print(f"  {basis} ${amount:,.2f} is within the ${max_spend:,.2f} "
              f"ceiling")

    # 3. The last line of defence is not in this script. A project
    #    budget limit in the OpenAI dashboard is the only stop that
    #    survives a bug in the code above.
    print("  (a project budget limit in the OpenAI dashboard is the only "
          "guard that survives a bug in this script — set one)")

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
                 "reasoning_effort": reasoning_effort,
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
        if batch.status in ("failed", "cancelled"):
            print(f"{state['batch_id']}: {batch.status} — nothing to collect. "
                  f"{getattr(batch, 'errors', None) or ''}")
            continue
        if batch.status not in ("completed", "expired"):
            print(f"{state['batch_id']}: {batch.status} — not ready")
            continue
        if batch.status == "expired":
            # An expired batch still returns whatever completed inside the
            # window. Collecting it is right; pretending it was whole is
            # not, and the documents it never reached must stay in the
            # cohort rather than be logged as read.
            print(f"{state['batch_id']}: EXPIRED — collecting partial results")

        by_doc: dict[str, list] = {}
        errored: dict[str, int] = {}
        usage = {"requests": 0, "in": 0, "out": 0}
        raw = (client.files.content(batch.output_file_id).text
               if batch.output_file_id else "")

        # The error file, which the first version never opened. A request
        # that fails at the API level appears here and NOT in the output
        # file, so ignoring it meant those documents got no log row, sat
        # in the cohort, and were resubmitted — and re-charged — on every
        # subsequent run, with nothing anywhere recording that they had
        # been tried. Silent partial success, the paid edition.
        n_err_file = 0
        if getattr(batch, "error_file_id", None):
            for line in client.files.content(batch.error_file_id).text.splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                cid = r.get("custom_id") or ""
                if "-" not in cid:
                    continue
                doc_id, _c = cid.rsplit("-", 1)
                errored[doc_id] = errored.get(doc_id, 0) + 1
                n_err_file += 1
            if n_err_file:
                print(f"  {n_err_file} requests failed at the API level "
                      f"(from the batch error file)")
        for line in raw.splitlines():
            r = json.loads(line)
            doc_id, _c = r["custom_id"].rsplit("-", 1)
            body = (r.get("response") or {}).get("body") or {}
            u = body.get("usage") or {}
            if u:
                usage["requests"] += 1
                usage["in"] += u.get("prompt_tokens", 0)
                usage["out"] += u.get("completion_tokens", 0)
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

        model_tag = model_tag_for(state["model"],
                                  state.get("reasoning_effort"))
        inserted = failed = docs = 0
        with db.connect() as conn:
            for doc_id, info in state["documents"].items():
                # A document nothing came back for — neither findings nor
                # an error — was never processed. It gets no log row, so
                # it stays in the cohort and is tried again. Logging it
                # as read would be the whole project's cardinal sin with
                # an invoice attached.
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
        state["usage"] = usage
        path.write_text(json.dumps(state))

        # Record what a request actually cost in tokens, keyed by model,
        # so the next estimate is measured rather than assumed.
        if usage["requests"]:
            store = {}
            if USAGE_PATH.exists():
                try:
                    store = json.loads(USAGE_PATH.read_text())
                except Exception:
                    store = {}
            prev = store.get(model_tag, {"requests": 0, "in": 0, "out": 0})
            store[model_tag] = {
                "requests": prev["requests"] + usage["requests"],
                "in": prev["in"] + usage["in"],
                "out": prev["out"] + usage["out"],
            }
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            USAGE_PATH.write_text(json.dumps(store, indent=1))
            print(f"  measured: {usage['in'] / usage['requests']:.0f} input "
                  f"and {usage['out'] / usage['requests']:.0f} output tokens "
                  f"per request — recorded for costing the bulk run")
        print(f"collected {state['batch_id']}: {docs} documents, "
              f"{inserted} findings inserted, {failed} failed the verbatim "
              f"gate" + (f", {len(errored)} docs with errored chunks"
                         if errored else ""))


def _no_nul(v):
    """Postgres text cannot hold NUL (0x00) and raises on it. One arrived
    in a gpt-5 finding after 460,000 findings without one -- the model can
    emit what the source never contained -- so every string is stripped at
    the database boundary rather than trusting any reader not to."""
    return v.replace("\x00", "") if isinstance(v, str) else v

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
                 _no_nul(str(f["signal_type"])[:80]),
                 _no_nul(f.get("value_text")), num,
                 _no_nul(f.get("value_unit")), _no_nul(quote), verified,
                 model_tag, PROMPT_VERSION))
            inserted += cur.rowcount
    conn.commit()
    return inserted, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--cohort", choices=["validation", "power", "remaining"],
                    default="validation",
                    help="'validation' samples documents already read by "
                         "both other models, for a three-way comparison; "
                         "'remaining' is everything this model has not read.")
    ap.add_argument("--sample", type=int, default=60,
                    help="Validation cohort size (default 60). Ignored for "
                         "--cohort remaining.")
    ap.add_argument("--model", default=None)
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--max-chars", type=int, default=16000)
    ap.add_argument("--rate-in", type=float, default=0.0,
                    metavar="USD", help="Dollars per 1M input tokens, for "
                                        "the estimate.")
    ap.add_argument("--rate-out", type=float, default=0.0,
                    metavar="USD", help="Dollars per 1M output tokens.")
    ap.add_argument("--max-spend-usd", type=float, default=0.0, metavar="USD",
                    help="Refuse to submit if the worst-case estimate "
                         "exceeds this. Needs --rate-in/--rate-out.")
    ap.add_argument("--preflight", action="store_true",
                    help="Show which account, org and project the key "
                         "resolves to, and which models it can see. "
                         "Spends nothing.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Submit only the first N documents of the "
                         "'remaining' cohort. Deterministic order, and a "
                         "collected slice is excluded from the next call, "
                         "so repeated --limit runs walk the cohort without "
                         "overlap. Use it to check an estimate against an "
                         "actual before committing the rest.")
    ap.add_argument("--tier", nargs="+", default=None,
                    choices=["A", "B", "C"], metavar="TIER",
                    help="Restrict the 'remaining' cohort to these tiers. "
                         "Tier A is supporting statements and consultee "
                         "responses -- 22%% of the corpus and where the "
                         "disclosures are -- so spending a better (dearer) "
                         "configuration on A while B and C get a cheap one "
                         "buys accuracy exactly where findings come from.")
    ap.add_argument("--reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"],
                    help="Reasoning models bill reasoning as output and "
                         "spend it from max_completion_tokens. Extraction "
                         "does not need deliberation; gpt-5 at its default "
                         "spent 94%% of its budget thinking and answered "
                         "nothing on 29%% of requests. Becomes part of the "
                         "model tag.")
    ap.add_argument("--record-no-text", action="store_true",
                    help="Write a no_text verdict for cohort documents whose "
                         "cache holds no words, so they stop reading as an "
                         "unanalysed backlog. Writes; idempotent.")
    ap.add_argument("--unread-only", action="store_true",
                    help="Restrict the 'remaining' cohort to documents no "
                         "model has read, closing the coverage gap rather "
                         "than adding a second opinion. Matches the "
                         "reader's own definition of unread.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.preflight:
        preflight()
        return
    if args.list_models:
        for m in sorted(_client().models.list(), key=lambda m: m.id):
            print(m.id)
        return
    if args.record_no_text:
        # Explicit, because the row names the run that met the document.
        # A verdict filed under 'openai:<unset>' would be a permanent
        # record of nobody in particular having found nothing.
        if not args.model:
            ap.error("--record-no-text requires --model: the verdict is "
                     "logged under the tag of the run whose cohort "
                     "selected the document")
        do_record_no_text(args.model, args.reasoning_effort)
        return
    if args.submit or args.dry_run:
        if args.submit and not args.model:
            ap.error("--submit requires --model (see --list-models)")
        do_submit(args.cohort, args.model or "<unset>", args.max_chars,
                  dry_run=not args.submit, sample=args.sample,
                  rate_in=args.rate_in, rate_out=args.rate_out,
                  max_spend=args.max_spend_usd,
                  reasoning_effort=args.reasoning_effort,
                  tiers=tuple(args.tier or ()), limit=args.limit,
                  unread_only=args.unread_only)
    elif args.collect:
        do_collect(args.batch_id)
    else:
        print("pass --list-models, --dry-run, --submit, or --collect")


if __name__ == "__main__":
    main()
