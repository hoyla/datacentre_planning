#!/usr/bin/env python3
"""The machine reading of every site, via the OpenAI API, behind the gate.

READER_REDESIGN_PLAN §7b–d. dcp/machine_reading.py builds the input,
renders the prompt and gates the output; this is the route that sends
it, collects it and stores it.

Two ways to run it. `--sample` reads the twenty sites named in
SAMPLE_SITES synchronously and writes each reading to
data/machine_readings_sample/ as JSON and as markdown, for a person to
read before anything renders (§7d, the checkpoint); it stores them too,
because a stored reading is what the reader's panel is built from and
the review is best done in the reader. `--submit` puts every live site
with documents into an OpenAI batch, skipping any site whose input hash
already has a row, and `--collect` gates and stores what comes back.

What is stored: the reading as structured JSON, the model, the prompt
version, the hash of exactly what the model was shown, and how much
that was. A reading the gate refuses is stored with withheld_reason set
and is never rendered. Nothing is exported to the workbook or the
DuckDB (§3.2).

    scripts/machine_reading_openai.py --sample [--site KEY ...]
    scripts/machine_reading_openai.py --submit [--dry-run]
    scripts/machine_reading_openai.py --collect
    scripts/machine_reading_openai.py --report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from dcp import db, site_cohorts, site_profile
from dcp import machine_reading as mr

BATCH_DIR = ROOT / "data" / "machine_reading_batches"
SAMPLE_DIR = ROOT / "data" / "machine_readings_sample"
MAX_COMPLETION_TOKENS = 24_000

# The twenty (§7d), chosen to span the bases rather than the biggest
# schemes: the sites the review found wrong things on, a floorspace-only
# estimate, a pre-planning row with no documents, a Slough estate record,
# a site read in full and silent, a clustering artefact, a multi-campus
# site, a nationally significant project.
SAMPLE_SITES: tuple[tuple[str, str], ...] = (
    ("PTNO-12879308", "Watford Bypass — the per-unit generation case"),
    ("PTNO-12849818", "Elsham Wolds — gas engines, 650 diesels, 1 GW campus"),
    ("SITE-Medway/MC/21/0979", "Kingsnorth — export limit filed as a connection"),
    ("PTNO-12549436", "Amazon Didcot — the worst error in HISTORY; 259 tier-A documents"),
    ("PTNO-12785975", "Northumberland Energy Park — 1,100 MW total vs 99.9 MW grid"),
    ("PTNO-12880751", "Ocean Estates — two schemes clustered into one site"),
    ("PTNO-12778496", "Rover Way — 1,000 MW 'energy capacity' against 10 MW load"),
    ("PTNO-12513167", "JVC Business Park — 50 x 3.3 MWt read as 165 MW"),
    ("PTNO-12651066", "Graven Hill — rooftop PV as generation; 435 MW in the title"),
    ("PTNO-12610936", "West London Technology Park — 342 MW total, 140 MW grid"),
    ("PTNO-11891737", "Interxion — many applications, many audiences"),
    ("PTNO-12511337", "Union Park — the multi-campus site"),
    ("SITE-EN0110030", "A nationally significant project"),
    ("SITE-NorthAyrshire/26/00138/EIA", "Hunterston — per-unit headline, EIA"),
    ("PTNO-12628941", "Yorkshire Energy Park — 559 generation findings"),
    ("PTNO-12489447", "Langley Business Centre — 26 x 4 MW stated two ways"),
    ("SITE-Hillingdon/39707/APP/2022/3243", "Woodlands Park — 171 x 2 MWe"),
    ("PTNO-12842719", "Trident Way — 219 kW of solar"),
    ("PTNO-12256124", "Longcross — 28.8 MW generation, 3.75 MW load"),
    ("PTNO-11997865", "A small site read in full and silent"),
)


def _client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set (add it to .env)")
    return OpenAI()


def _context(conn):
    """The three corpus-wide inputs, loaded once."""
    return (site_profile.load_site_profiles(conn),
            site_profile.load_coverage_detail(conn),
            site_cohorts.compute_all(conn))


def _already(conn, site_key: str, model: str, input_hash: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("""SELECT 1 FROM site_machine_readings
                       WHERE site_key = %s AND model = %s
                         AND prompt_version = %s AND input_hash = %s
                         AND gate_version = %s""",
                    (site_key, model, mr.PROMPT_VERSION, input_hash,
                     mr.GATE_VERSION))
        return cur.fetchone() is not None


def _store(conn, inp: mr.SiteInput, model: str, reading: dict | None,
           verdict: mr.GateResult) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO site_machine_readings
                (site_key, model, prompt_version, input_hash, gate_version,
                 documents_read, pages_read, input_chars, reading,
                 withheld_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (site_key, model, prompt_version, input_hash, gate_version)
            DO NOTHING""",
            (inp.site_key, model, mr.PROMPT_VERSION, inp.input_hash,
             mr.GATE_VERSION, inp.documents_read, len(inp.pages),
             sum(len(p.text) for p in inp.pages),
             json.dumps(reading) if reading is not None else None,
             None if verdict.ok else verdict.reason))
    conn.commit()


def _markdown(inp: mr.SiteInput, reading: dict, verdict: mr.GateResult,
              model: str) -> str:
    lines = [f"# {inp.name}", "",
             f"`{inp.site_key}` · {model} · {mr.PROMPT_VERSION} · {mr.GATE_VERSION} · "
             f"{inp.documents_read} documents, {len(inp.pages)} pages, "
             f"{sum(len(p.text) for p in inp.pages):,} characters read", ""]
    if not verdict.ok:
        lines += [f"**WITHHELD: {verdict.reason}**", ""]
    else:
        lines += [f"Gate: {verdict.figures_checked} figures and "
                  f"{verdict.quotes_checked} quotes verified across "
                  f"{verdict.paragraphs_passed} paragraphs"
                  + (f"; {verdict.paragraphs_withheld} paragraph"
                     f"{'s' if verdict.paragraphs_withheld != 1 else ''} withheld"
                     if verdict.paragraphs_withheld else "") + ".", ""]
    for sec, title in mr.SECTION_TITLES.items():
        lines += [f"## {title}", ""]
        for para in (reading.get("sections") or {}).get(sec) or []:
            lines += [para.get("text", ""), ""]
            for q in para.get("quotes") or []:
                where = (f"document {q.get('document_id')}"
                         + (f" p.{q['page']}" if q.get("page") else "")
                         if q.get("document_id") else
                         f"application {q.get('application_ref') or '?'}")
                lines += [f"> {' '.join((q.get('quote') or '').split())} — *{where}*", ""]
    return "\n".join(lines)


def read_one(client, inp: mr.SiteInput, model: str, effort: str) -> dict:
    resp = client.chat.completions.create(
        model=model, max_completion_tokens=MAX_COMPLETION_TOKENS,
        reasoning_effort=effort,
        response_format={"type": "json_schema", "json_schema": {
            "name": "site_reading", "strict": True, "schema": mr.SCHEMA}},
        messages=[{"role": "user", "content": mr.render_prompt(inp)}])
    text = resp.choices[0].message.content or ""
    return json.loads(text)


def _sample_one(client, conn, key, why, inp, model, effort) -> str:
    """Read one site, gate it, store it, write its files. Returns a line."""
    raw_path = SAMPLE_DIR / f"{key.replace('/', '_')}.raw.json"
    # The raw answer is written before the gate runs: a gate bug must
    # never cost a second call for the same reading.
    cached = json.loads(raw_path.read_text()) if raw_path.exists() else {}
    if (cached.get("input_hash") == inp.input_hash
            and cached.get("prompt_version") == mr.PROMPT_VERSION):
        reading = cached["reading"]
        how = "from disk"
    else:
        t0 = time.time()
        try:
            reading = read_one(client, inp, model, effort)
        except Exception as e:   # noqa: BLE001
            return f"{key}: request failed: {e}"
        # The previous prompt's answer is kept beside the new one: the
        # progression is evidence, and a re-gate of an old answer is
        # still possible from its own file.
        if cached and cached.get("prompt_version") != mr.PROMPT_VERSION:
            raw_path.with_name(raw_path.name.replace(
                ".raw.json", f".{cached.get('prompt_version', 'old')}.raw.json")
            ).write_text(json.dumps(cached))
        raw_path.write_text(json.dumps(
            {"input_hash": inp.input_hash, "model": model,
             "prompt_version": mr.PROMPT_VERSION, "reading": reading}))
        how = f"{time.time() - t0:.0f}s"
    verdict = mr.gate(reading, inp)
    _store(conn, inp, model, reading, verdict)
    slug = key.replace("/", "_")
    (SAMPLE_DIR / f"{slug}.json").write_text(json.dumps(
        {"site_key": key, "why": why, "model": model,
         "prompt_version": mr.PROMPT_VERSION, "input_hash": inp.input_hash,
         "gate": verdict.__dict__, "reading": reading}, indent=1))
    (SAMPLE_DIR / f"{slug}.md").write_text(_markdown(inp, reading, verdict, model))
    return (f"{key}: "
            f"{(f'OK ({verdict.paragraphs_withheld} paragraphs withheld)' if verdict.paragraphs_withheld else 'OK') if verdict.ok else 'WITHHELD — ' + verdict.reason} "
            f"({how}; {verdict.figures_checked} figures, "
            f"{verdict.quotes_checked} quotes)")


def do_sample(model: str, effort: str, only: list[str] | None,
              workers: int = 6) -> None:
    """The twenty, read concurrently: one site at this text budget takes
    the model a quarter of an hour, and twenty in a row is an afternoon
    a person would otherwise spend waiting to read them.

    Each worker builds its own site's input and drops it when done. The
    first version built all twenty up front and held them — and a
    site's input carries every cached page of every document it holds,
    for the gate, which for Interxion is 2,340 documents; the process
    was killed before the first reading came back.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    client = _client()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        profiles, coverage, cohorts = _context(conn)
    targets = [(k, why) for k, why in SAMPLE_SITES if not only or k in only]

    # One connection per worker: psycopg2 connections are not shared
    # across threads, and each store is its own short transaction.
    def run(item):
        key, why = item
        with db.connect() as c2:
            inp = mr.load_site_input(c2, key, profile=profiles.get(key, {}),
                                     coverage=coverage.get(key, {}),
                                     cohorts=cohorts)
            chars = sum(len(p.text) for p in inp.pages)
            head = (f"{key}: {why}\n   {inp.documents_read} of "
                    f"{inp.documents_considered} documents, {len(inp.pages)} "
                    f"pages, {chars:,} chars")
            if _already(c2, key, model, inp.input_hash):
                return head + "\n   already read under this input; skipped"
            return head + "\n   " + _sample_one(client, c2, key, why, inp,
                                                  model, effort)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(run, it) for it in targets]):
            print(fut.result(), flush=True)


def do_submit(model: str, effort: str, dry_run: bool) -> None:
    with db.connect() as conn:
        profiles, coverage, cohorts = _context(conn)
        with conn.cursor() as cur:
            cur.execute("""SELECT DISTINCT s.site_key FROM sites s
                           JOIN site_members sm ON sm.site_id = s.id AND sm.retired_at IS NULL
                           JOIN documents d ON d.application_id = sm.application_id
                           WHERE s.retired_at IS NULL AND d.bytes_path IS NOT NULL
                           ORDER BY s.site_key""")
            keys = [r[0] for r in cur.fetchall()]
        lines, meta, skipped, chars = [], {}, 0, 0
        for key in keys:
            inp = mr.load_site_input(conn, key, profile=profiles.get(key, {}),
                                     coverage=coverage.get(key, {}),
                                     cohorts=cohorts)
            if _already(conn, key, model, inp.input_hash):
                skipped += 1
                continue
            body = {"model": model, "max_completion_tokens": MAX_COMPLETION_TOKENS,
                    "reasoning_effort": effort,
                    "response_format": {"type": "json_schema", "json_schema": {
                        "name": "site_reading", "strict": True, "schema": mr.SCHEMA}},
                    "messages": [{"role": "user", "content": mr.render_prompt(inp)}]}
            lines.append(json.dumps({"custom_id": key, "method": "POST",
                                     "url": "/v1/chat/completions", "body": body},
                                    ensure_ascii=False))
            meta[key] = {"input_hash": inp.input_hash,
                         "documents_read": inp.documents_read,
                         "pages_read": len(inp.pages),
                         "input_chars": sum(len(p.text) for p in inp.pages)}
            chars += meta[key]["input_chars"]
    print(f"{len(lines)} sites to read, {skipped} already read under their "
          f"current input; ≈{chars / 4 / 1e6:.1f}M input tokens")
    if dry_run or not lines:
        return
    client = _client()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    payload = ("\n".join(lines) + "\n").encode()
    f = client.files.create(file=("machine_reading.jsonl", payload), purpose="batch")
    batch = client.batches.create(input_file_id=f.id, endpoint="/v1/chat/completions",
                                  completion_window="24h")
    (BATCH_DIR / f"{batch.id}.json").write_text(json.dumps({
        "batch_id": batch.id, "model": model, "reasoning_effort": effort,
        "prompt_version": mr.PROMPT_VERSION,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "sites": meta}))
    print(f"submitted {batch.id} ({batch.status})")


def do_collect() -> None:
    client = _client()
    for path in sorted(BATCH_DIR.glob("batch_*.json")):
        state = json.loads(path.read_text())
        if state.get("collected"):
            continue
        batch = client.batches.retrieve(state["batch_id"])
        if batch.status not in ("completed", "expired"):
            print(f"{state['batch_id']}: {batch.status} — not ready")
            continue
        raw = client.files.content(batch.output_file_id).text if batch.output_file_id else ""
        model = state["model"]
        stored = withheld = failed = 0
        with db.connect() as conn:
            profiles, coverage, cohorts = _context(conn)
            for line in raw.splitlines():
                r = json.loads(line)
                key = r.get("custom_id")
                body = (r.get("response") or {}).get("body") or {}
                choice = (body.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content") or ""
                try:
                    reading = json.loads(content)
                except Exception:
                    failed += 1
                    continue
                # The input is rebuilt rather than trusted from the state
                # file, and its hash compared: a reading of an input that
                # has since changed is a reading of something that no
                # longer exists, and is stored withheld saying so.
                inp = mr.load_site_input(conn, key, profile=profiles.get(key, {}),
                                         coverage=coverage.get(key, {}),
                                         cohorts=cohorts)
                expected = state["sites"].get(key, {}).get("input_hash")
                if inp.input_hash != expected:
                    verdict = mr.GateResult(False, "the site's inputs changed "
                                                   "between submission and collection")
                else:
                    verdict = mr.gate(reading, inp)
                _store(conn, inp, model, reading, verdict)
                stored += verdict.ok
                withheld += not verdict.ok
        state["collected"] = True
        path.write_text(json.dumps(state))
        print(f"collected {state['batch_id']}: {stored} readings stored, "
              f"{withheld} withheld, {failed} unparseable")


def do_regate() -> None:
    """Re-judge every cached answer under the current gate, storing a
    new row per site under this gate version. No model call."""
    with db.connect() as conn:
        profiles, coverage, cohorts = _context(conn)
        for raw_path in sorted(SAMPLE_DIR.glob("*.raw.json")):
            raw = json.loads(raw_path.read_text())
            key = raw_path.name[:-len(".raw.json")]
            key = next((k for k, _ in SAMPLE_SITES if k.replace("/", "_") == key), key)
            inp = mr.load_site_input(conn, key, profile=profiles.get(key, {}),
                                     coverage=coverage.get(key, {}),
                                     cohorts=cohorts)
            if inp.input_hash != raw.get("input_hash"):
                print(f"{key}: input changed since the answer on disk; skipped")
                continue
            if raw.get("prompt_version", mr.PROMPT_VERSION) != mr.PROMPT_VERSION:
                print(f"{key}: answer on disk is {raw['prompt_version']}; skipped")
                continue
            if _already(conn, key, raw["model"], inp.input_hash):
                print(f"{key}: already gated under {mr.GATE_VERSION}")
                continue
            verdict = mr.gate(raw["reading"], inp)
            _store(conn, inp, raw["model"], raw["reading"], verdict)
            slug = key.replace("/", "_")
            (SAMPLE_DIR / f"{slug}.md").write_text(
                _markdown(inp, raw["reading"], verdict, raw["model"]))
            print(f"{key}: {'OK' if verdict.ok else 'WITHHELD — ' + verdict.reason}")


def do_report() -> None:
    with db.connect() as conn:
        latest, withheld = mr.load_latest(conn)
    print(f"{len(latest)} sites with a reading that passed the gate; "
          f"{len(withheld)} whose latest reading was withheld")
    for key, why in sorted(withheld.items()):
        print(f"  withheld {key}: {why}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--site", action="append", help="restrict --sample to these keys")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--regate", action="store_true",
                    help="re-judge the cached sample answers under the current gate")
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--reasoning-effort", default="medium",
                    choices=["minimal", "low", "medium", "high"])
    args = ap.parse_args()
    if args.sample:
        do_sample(args.model, args.reasoning_effort, args.site)
    elif args.submit or args.dry_run:
        do_submit(args.model, args.reasoning_effort, dry_run=not args.submit)
    elif args.collect:
        do_collect()
    elif args.regate:
        do_regate()
    elif args.report:
        do_report()
    else:
        ap.error("pass --sample, --submit, --collect or --report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
