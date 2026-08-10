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

    # The org/project the key actually resolves to, straight from the
    # response headers rather than from what anyone believes.
    try:
        raw = client.models.with_raw_response.list()
        for h in ("openai-organization", "openai-project"):
            if raw.headers.get(h):
                print(f"{h}: {raw.headers[h]}")
    except Exception:
        pass

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


def model_tag_for(model: str) -> str:
    """The model name findings and log rows are stamped with. Namespaced
    so an OpenAI read can never be confused with the Qwen or Sonnet read
    of the same document — the findings unique index includes it."""
    return f"openai:{model}"


def load_cohort(conn, which: str, sample: int = 0,
                model_tag: str | None = None) -> list[dict]:
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
    if which == "validation":
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
                                AND l.read_state <> 'not_extracted')
            ORDER BY a.application_ref, d.id"""
        if not model_tag:
            raise ValueError("the 'remaining' cohort must be scoped to a "
                             "model tag, or it cannot tell what this model "
                             "has already read")
        params = [PROMPT_VERSION, model_tag]
    with conn.cursor() as cur:
        cur.execute(q, params)
        rows = [{"document_id": r[0], "application_id": r[1],
                 "application_ref": r[2], "sha": r[3], "kind": r[4],
                 "tier": r[5]} for r in cur.fetchall()]
    if which == "validation":
        # Already-read documents carry a tier from the run that read
        # them; page selection follows it, so the comparison is
        # like-for-like against what the other two models saw.
        return rows[:sample] if sample else rows

    plans = sel.plan_documents(rows)
    kept = []
    for row, plan in zip(rows, plans):
        if plan.tier == "skip" or plan.sampled_out:
            continue
        row["tier"] = plan.tier
        kept.append(row)
    return kept


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
              rate_out: float = 0.0, max_spend: float = 0.0) -> None:
    tag = model_tag_for(model)

    # The validation interlock runs FIRST, before a single cache file is
    # opened. It used to sit after the JSONL build, which meant refusing
    # a 26,000-document bulk run took ten minutes of reading documents
    # it was about to decline to submit. A refusal should be instant, or
    # people learn to skip the step that produces it.
    if cohort == "remaining" and not dry_run:
        _require_validation(model)

    with db.connect() as conn:
        rows = load_cohort(conn, cohort, sample=sample, model_tag=tag)

    # A dry run over the whole corpus does not need to build the whole
    # corpus: read a sample and scale. Exact for anything small, and for
    # the bulk cohort the answer is a size decision, not an invoice.
    scale_factor = 1.0
    if dry_run and len(rows) > SAMPLE_THRESHOLD:
        scale_factor = len(rows) / SAMPLE_THRESHOLD
        print(f"cohort '{cohort}': {len(rows):,} documents — estimating from "
              f"a {SAMPLE_THRESHOLD}-document sample")
        rows = rows[:SAMPLE_THRESHOLD]

    lines, meta = build_jsonl(rows, model, max_chars)
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
    # If a validation batch has been collected for this model, cost the
    # run on what a request actually consumed. Otherwise all that can
    # honestly be quoted is the ceiling, which is why the first run is a
    # validation run.
    measured = _measured_usage(model)
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

        model_tag = model_tag_for(state["model"])
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
            prev = store.get(state["model"], {"requests": 0, "in": 0, "out": 0})
            store[state["model"]] = {
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
    ap.add_argument("--cohort", choices=["validation", "remaining"],
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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.preflight:
        preflight()
        return
    if args.list_models:
        for m in sorted(_client().models.list(), key=lambda m: m.id):
            print(m.id)
        return
    if args.submit or args.dry_run:
        if args.submit and not args.model:
            ap.error("--submit requires --model (see --list-models)")
        do_submit(args.cohort, args.model or "<unset>", args.max_chars,
                  dry_run=not args.submit, sample=args.sample,
                  rate_in=args.rate_in, rate_out=args.rate_out,
                  max_spend=args.max_spend_usd)
    elif args.collect:
        do_collect(args.batch_id)
    else:
        print("pass --list-models, --dry-run, --submit, or --collect")


if __name__ == "__main__":
    main()
