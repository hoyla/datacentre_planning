#!/usr/bin/env python3
"""Reinstate findings the quote gate wrongly rejected.

A finding is stored only if its evidence quote appears in the document's
cached page text. That gate is the hallucination protection and it is
right to be strict — but until 2026-08-31 it compared against text pypdf
had broken mid-word ("d ata centres", "940 µ g/m 3"), so a model that
copied the passage correctly failed it. The finding was then counted as a
failed gate, which reads as the model behaving badly rather than as
evidence discarded.

Nothing was lost. `data/deepread_escalations.jsonl` keeps every rejected
finding beside its document, its claimed page and the reader that
produced it. This replays them against the fixed gate and inserts the
ones that now pass. **No model is called and nothing is re-read**; the
whole job is local.

Provenance, per ROADMAP ("The re-gate's provenance question answers
itself from deepread_log"):

  * `model` and `prompt_version` are the ORIGINAL read's, recovered by
    joining the escalation's document_id to `deepread_log` on the reader
    its reason names. That model, under that prompt, produced the
    finding; the gate wrongly refused it. Both columns sit in the
    content key, so the true pair is also what keeps a recovered row
    deduplicable against a genuine re-read.
  * `gate_version` (migration 033) records the gate that admitted it,
    which is what makes the cohort countable and retirable without
    falsifying the model.

Usage:
    scripts/regate_escalations.py                 # dry run: report only
    scripts/regate_escalations.py --sample 20     # dry run + show rows
    scripts/regate_escalations.py --write         # insert
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))
from psycopg2.extras import RealDictCursor  # noqa: E402

from dcp import db, signal_families  # noqa: E402

ESCALATIONS = ROOT / "data" / "deepread_escalations.jsonl"

# The gate, loaded the way every reader loads it, so this cannot drift
# from what the runners apply.
_spec = importlib.util.spec_from_file_location(
    "verify_findings", ROOT / "scripts" / "verify_findings.py")
VF = importlib.util.module_from_spec(_spec)
sys.modules["verify_findings"] = VF
_spec.loader.exec_module(VF)

from dcp.machine_reading import GATE_VERSION  # noqa: E402

# The escalation reason names the reader; `deepread_log.model` names it
# more precisely. Match on the family and disambiguate on time.
READER_FAMILY = {
    "quote_failed_verification": "mlx",
    "quote_failed_verification_openai": "openai",
    "quote_failed_verification_sonnet": "claude-sonnet-5",
    "quote_failed_verification_agent": "claude-code",
}


def _page_of(claimed) -> int | None:
    """`claimed_page` is usually an int and sometimes '[PAGE 4]'."""
    if claimed in (None, ""):
        return None
    m = re.search(r"\d+", str(claimed))
    return int(m.group()) if m else None


def load_escalations() -> list[dict]:
    out = []
    for line in ESCALATIONS.open():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if str(row.get("reason", "")) not in READER_FAMILY:
            continue
        f = row.get("finding") or {}
        if not (f.get("evidence_text") or "").strip() or not f.get("signal_type"):
            continue
        out.append(row)
    return out


def resolve_reads(conn, rows: list[dict]) -> dict[int, list[dict]]:
    """document_id -> its deepread_log rows (model, prompt_version, when)."""
    ids = sorted({r["document_id"] for r in rows if r.get("document_id")})
    log: dict[int, list[dict]] = collections.defaultdict(list)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for i in range(0, len(ids), 5000):
            cur.execute(
                """SELECT document_id, application_id, model, prompt_version,
                          completed_at
                   FROM deepread_log WHERE document_id = ANY(%s)""",
                (ids[i:i + 5000],))
            for r in cur.fetchall():
                log[r["document_id"]].append(dict(r))
    return log


def pick_read(cands: list[dict], family: str, ts: str | None) -> dict | None:
    """The read that produced this finding.

    Family narrows it; where a family has more than one model tag
    (`openai:gpt-5:minimal` against `:low`) the nearest completed_at to
    the escalation's own timestamp decides. Returns None when nothing
    matches — those are dropped rather than guessed at.
    """
    same = [c for c in cands if family in (c["model"] or "")]
    if not same:
        return None
    if len(same) == 1 or not ts:
        return same[0]
    try:
        from datetime import datetime
        want = datetime.fromisoformat(ts)
    except Exception:
        return same[0]
    dated = [c for c in same if c.get("completed_at")]
    if not dated:
        return same[0]
    return min(dated, key=lambda c: abs(
        (c["completed_at"].replace(tzinfo=None) - want).total_seconds()))


def cached_pages(conn, doc_ids: list[int]) -> dict[int, list[str]]:
    paths: dict[int, str] = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for i in range(0, len(doc_ids), 5000):
            cur.execute("SELECT id, bytes_path FROM documents WHERE id = ANY(%s)",
                        (doc_ids[i:i + 5000],))
            for r in cur.fetchall():
                paths[r["id"]] = r["bytes_path"]
    out: dict[int, list[str]] = {}
    for did, bp in paths.items():
        try:
            cp = VF._cache_path_for_bytes(bp)
        except Exception:
            continue
        if not cp.exists():
            continue
        try:
            out[did] = json.loads(cp.read_text()).get("pages") or []
        except Exception:
            continue
    return out


def passes(pages: list[str], quote: str, page: int | None,
           sent: list[int] | None) -> int | None:
    """The page the quote verifies on, or None.

    The same candidate order the runners use: the claimed page, its
    neighbours, then any other page that was sent to the model. A quote
    is never searched in a page the model was not shown.
    """
    frags = [VF._normalise(f) for f in VF._quote_fragments(quote)]
    if not frags:
        return None
    cands: list[int] = []
    if page and 1 <= page <= len(pages):
        cands = [page, page - 1, page + 1]
    for p in cands + [p for p in (sent or []) if p not in cands]:
        if 1 <= p <= len(pages) and VF.fragments_present(
                VF._normalise(pages[p - 1] or ""), frags):
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true",
                    help="insert. Without it nothing is written.")
    ap.add_argument("--sample", type=int, default=0,
                    help="print N recovered rows before the summary")
    args = ap.parse_args()

    rows = load_escalations()
    print(f"quote-failure escalations with a usable finding: {len(rows):,}")

    with db.connect() as conn:
        log = resolve_reads(conn, rows)
        pages_by_doc = cached_pages(
            conn, sorted({r["document_id"] for r in rows if r.get("document_id")}))
        print(f"documents with cached page text: {len(pages_by_doc):,}")

        recovered: list[tuple] = []
        why = collections.Counter()
        by_gate_model = collections.Counter()
        shown = 0

        for r in rows:
            did = r.get("document_id")
            f = r["finding"]
            pages = pages_by_doc.get(did)
            if pages is None:
                why["no cached page text"] += 1
                continue
            read = pick_read(log.get(did, []), READER_FAMILY[r["reason"]],
                             r.get("ts"))
            if read is None:
                why["no deepread_log row for this reader — dropped"] += 1
                continue
            quote = f["evidence_text"].strip()
            page = passes(pages, quote, _page_of(r.get("claimed_page")),
                          r.get("pages_sent"))
            if page is None:
                why["still absent — the gate was right"] += 1
                continue

            label = str(f["signal_type"])[:80]
            family = signal_families.family_for(label)
            num = f.get("value_number")
            num = num if isinstance(num, (int, float)) else None
            recovered.append((
                read["application_id"], did, label, family, "derived",
                f.get("value_text"), num, f.get("value_unit"), quote, page,
                read["model"], read["prompt_version"], GATE_VERSION))
            by_gate_model[read["model"]] += 1
            if shown < args.sample:
                shown += 1
                print(f"\n  [{shown}] {read['model']} / {read['prompt_version']}"
                      f" -> doc {did} p{page}  {label}")
                print(f"      {quote[:160]!r}")

        print(f"\nrecovered: {len(recovered):,}")
        for k, v in why.most_common():
            print(f"  not recovered — {k}: {v:,}")
        print("\nby the model that originally read the document:")
        for m, n in by_gate_model.most_common():
            print(f"  {n:>7,}  {m}")
        print(f"\nall would be stored with gate_version = {GATE_VERSION!r}")

        if not args.write:
            print("\nDRY RUN — nothing written. Pass --write to insert.")
            return 0

        inserted = 0
        with conn.cursor() as cur:
            for v in recovered:
                cur.execute("""
                    INSERT INTO findings (application_id, document_id,
                        signal_type, signal_family, family_source, value_text,
                        value_number, value_unit, evidence_text, evidence_page,
                        model, prompt_version, gate_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (application_id, document_id, model,
                        prompt_version, signal_type, md5(value_text),
                        value_number, value_unit, md5(evidence_text),
                        evidence_page)
                    DO NOTHING""", v)
                inserted += cur.rowcount
        conn.commit()
        print(f"\ninserted {inserted:,} "
              f"({len(recovered) - inserted:,} already present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
