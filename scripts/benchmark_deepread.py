"""Compare local deep-read backends on real documents, one at a time.

The deep-read is the expensive phase: ~27,000 documents, so throughput
decides whether it takes two nights or two weeks. This benchmark runs the
same documents through each candidate **sequentially** — 48GB of RAM
cannot hold a 23GB and a 17GB model at once — and reports tokens/second,
wall-clock per document, and what each actually extracted.

Candidates:

- `granite` — granite4.1:30b via Ollama, the model the v2 architecture was
  chosen on (39/50 enriched on the adjudicated triage set).
- `mlx` — an MLX build served through Apple's Metal stack, which on Apple
  Silicon is typically substantially faster than Ollama's llama.cpp
  backend. Qwen3.6-35B-A3B is a mixture-of-experts with ~3B active
  parameters, so it should behave like a small model at inference time
  while retaining large-model quality.

Quality is not scored automatically — the outputs are printed for
adjudication, because "did it find the generator count and quote it
verbatim" is a judgement call, and the verbatim-quote gate is what
protects the corpus either way.

Usage:
    .venv/bin/python -u scripts/benchmark_deepread.py --docs 3
    .venv/bin/python -u scripts/benchmark_deepread.py --docs 3 --only mlx
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, extract  # noqa: E402

MLX_MODEL = "mlx-community/Qwen3.6-35B-A3B-4bit"
OLLAMA_MODEL = "granite4.1:30b"

PROMPT = """\
You are reading a UK planning document for an investigative journalism
project on data centres and their power and environmental impact.

Extract every factual claim relevant to any of: on-site power generation
(engines, turbines, CHP, generators, fuel), grid connection and capacity,
IT load or power demand in MW, water use including cooling, emissions and
air quality, designated sites and ecology, flood risk, EIA screening
outcomes, and the parties involved (applicant, agent, consultants).

For each, return an object with:
  "signal_type": a short snake_case label
  "value_text":  the fact in a few words
  "value_number" and "value_unit": if the fact is quantitative, else null
  "evidence_text": a VERBATIM quote from the document supporting it

The evidence quote must appear in the document character-for-character —
it is checked automatically, and an invented quote is worse than no
finding. If the document contains nothing relevant, return an empty list.

Return strict JSON: {"findings": [...]}. No prose outside the JSON.

DOCUMENT:
"""


def pick_documents(n: int) -> list[tuple[str, str, Path]]:
    """A few documents likely to be substantive: prefer planning statements
    and energy/environmental reports on data-centre applications."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT a.application_ref, d.content_sha256, d.bytes_path, d.kind
            FROM documents d
            JOIN applications a ON a.id = d.application_id
            WHERE d.bytes_path IS NOT NULL
              AND (d.kind ILIKE '%%energy%%' OR d.kind ILIKE '%%planning statement%%'
                   OR d.kind ILIKE '%%environmental%%')
            ORDER BY random() LIMIT %s""", (n,))
        return [(r[0], r[1], Path(r[2])) for r in cur.fetchall()]


def document_text(ref: str, sha: str, path: Path, max_chars: int) -> str:
    doc = extract.extract_document(source="documents", application_ref=ref,
                                   sha=sha, bytes_path=path, ocr=True)
    text = "\n".join(doc.pages if isinstance(doc.pages, list) else [])
    return text[:max_chars]


def run_ollama(text: str, timeout: float) -> tuple[str, float, dict]:
    import httpx
    t0 = time.time()
    r = httpx.post("http://localhost:11434/api/generate",
                   json={"model": OLLAMA_MODEL, "prompt": PROMPT + text,
                         "stream": False, "format": "json"},
                   timeout=timeout)
    elapsed = time.time() - t0
    data = r.json()
    stats = {"eval_count": data.get("eval_count"),
             "prompt_eval_count": data.get("prompt_eval_count")}
    return data.get("response", ""), elapsed, stats


_MLX_CACHE: dict = {}


def run_mlx(text: str, max_tokens: int) -> tuple[str, float, dict]:
    from mlx_lm import generate, load
    if "m" not in _MLX_CACHE:
        _MLX_CACHE["m"], _MLX_CACHE["t"] = load(MLX_MODEL)
    model, tok = _MLX_CACHE["m"], _MLX_CACHE["t"]
    messages = [{"role": "user", "content": PROMPT + text}]
    # Qwen3.6 is a thinking model by default; a reasoning trace would swamp
    # the JSON output and the throughput numbers alike.
    prompt = tok.apply_chat_template(messages, add_generation_prompt=True,
                                     enable_thinking=False)
    t0 = time.time()
    out = generate(model, tok, prompt=prompt, max_tokens=max_tokens, verbose=False)
    elapsed = time.time() - t0
    approx_tokens = len(out) / 4
    return out, elapsed, {"eval_count": int(approx_tokens)}


def summarise(label: str, raw: str, elapsed: float, stats: dict, text_len: int) -> None:
    tok = stats.get("eval_count") or 0
    tps = tok / elapsed if elapsed and tok else 0
    findings = []
    try:
        start = raw.find("{")
        findings = json.loads(raw[start:]).get("findings", [])
    except Exception:
        pass
    print(f"  {label:8} {elapsed:6.1f}s  ~{tps:5.1f} tok/s  "
          f"{len(findings):2d} findings  (input {text_len} chars)")
    for f in findings[:4]:
        ev = (f.get("evidence_text") or "")[:60]
        print(f"       - {str(f.get('signal_type'))[:26]:26} "
              f"{str(f.get('value_text'))[:30]:30} “{ev}…”")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=3)
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--only", choices=["granite", "mlx"])
    args = ap.parse_args()

    docs = pick_documents(args.docs)
    print(f"{len(docs)} documents sampled\n")
    texts = []
    for ref, sha, path in docs:
        try:
            texts.append((ref, document_text(ref, sha, path, args.max_chars)))
        except Exception as exc:
            print(f"  skip {ref}: {exc}")

    # Sequential by design: one model resident at a time.
    for backend in (["granite", "mlx"] if not args.only else [args.only]):
        print(f"\n=== {backend} " + "=" * 40)
        totals = []
        for ref, text in texts:
            print(f"  {ref}")
            try:
                if backend == "granite":
                    raw, el, st = run_ollama(text, args.timeout)
                else:
                    raw, el, st = run_mlx(text, args.max_tokens)
                summarise(backend, raw, el, st, len(text))
                totals.append(el)
            except Exception as exc:
                print(f"    FAILED: {type(exc).__name__}: {str(exc)[:120]}")
        if totals:
            print(f"  mean {sum(totals)/len(totals):.1f}s/document — "
                  f"27,000 documents ≈ {sum(totals)/len(totals)*27000/3600:.0f} hours")
        if backend == "granite":
            import subprocess
            subprocess.run(["ollama", "stop", OLLAMA_MODEL], capture_output=True)
            print("  (unloaded granite from memory)")


if __name__ == "__main__":
    main()
