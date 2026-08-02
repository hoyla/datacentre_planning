"""Post-mortem for Barbour ABI projects whose planning_ref didn't match our universe.

For every `projects` row with a planning_ref but no project_applications link,
look the bare ref up on PlanIt (`id_match`, cached via source_snapshots like
every other PlanIt pass) and classify why our original sweep missed it:

- procurement_notice   — ref is a "FIND A TENDER" id, not a planning ref
- pre_2018             — in PlanIt, but starts before our 2018+ sweep window
- no_dc_keywords       — in PlanIt, in-window, but the description doesn't
                         contain any DC-sweep keyword (the description-search
                         couldn't have found it)
- post_sweep           — in PlanIt with keywords, but only started after our
                          2026-05 sweep
- sweep_escape         — in PlanIt, in-window, has keywords: a genuine escape
                         worth understanding individually
- ref_collision        — PlanIt has record(s) for the bare ref, but in a
                         different council than Barbour's authority (bare
                         refs are not nationally unique) — treat as not
                         found for this authority
- not_in_planit        — no PlanIt record for the bare ref (portal-only
                         council, Crown dependency, or ref-format drift)
- pending              — not looked up yet (run aborted by rate limiting;
                         re-run to continue from cache)

Writes a markdown report and prints a summary. Idempotent: PlanIt responses
are served from source_snapshots on re-run.

Usage:
    .venv/bin/python scripts/barbour_gap_postmortem.py [--out PATH] [--delay 2.5]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources.planit import PlanItClient  # noqa: E402

SWEEP_WINDOW_START = date(2018, 1, 1)
SWEEP_DATE = date(2026, 5, 14)  # the original v1 keyword sweep
DC_KEYWORDS_PLAIN = (
    "data centre", "data center", "data hall", "hyperscale",
    "datacentre", "colocation", "data park",
)


def _has_dc_keyword(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in DC_KEYWORDS_PLAIN)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


_AUTHORITY_NOISE = (
    "london borough of", "royal borough of", "borough", "city", "county",
    "district", "metropolitan", "council", "the", "of",
)


def _norm_authority(s: str) -> str:
    """'Newport City Council (Phone: ...)' → 'newport';
    'London Borough of Tower Hamlets' → 'towerhamlets'."""
    s = re.sub(r"\(.*", "", s).lower()
    for w in _AUTHORITY_NOISE:
        s = re.sub(rf"\b{w}\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


# PlanIt area names that abbreviate the council's own name non-prefixically.
_AREA_ALIASES = {"bucks": "buckinghamshire", "herts": "hertfordshire",
                 "notts": "nottinghamshire", "wilts": "wiltshire"}


def _authority_matches(barbour_authority: str | None, planit_area: str | None) -> bool:
    """Does PlanIt's council match Barbour's authority string? Equality after
    normalisation (with known abbreviations expanded), or a one-sided prefix
    for names of 5+ chars ('Hart' vs 'Hartlepool' must NOT match — 4 chars).
    No authority on the Barbour side → accept (nothing to check)."""
    if not barbour_authority or not planit_area:
        return True
    a = _norm_authority(barbour_authority)
    b = _norm_authority(planit_area)
    a = _AREA_ALIASES.get(a, a)
    b = _AREA_ALIASES.get(b, b)
    if not a or not b:
        return True
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 5 and longer.startswith(shorter)


def classify(records: list[dict], *, authority: str | None) -> tuple[str, dict | None]:
    """Classify a PlanIt id_match result set for one bare ref. Bare refs are
    not nationally unique, so records from a different council than Barbour's
    authority are collisions, not matches."""
    if not records:
        return "not_in_planit", None
    in_authority = [r for r in records
                    if _authority_matches(authority, r.get("area_name"))]
    if not in_authority:
        return "ref_collision", records[0]
    # Prefer the record that looks most substantive: keyword hit first, then
    # most recent start_date. (A ref can still match >1 record in-council,
    # e.g. altid drift across a conditions family.)
    records = sorted(
        in_authority,
        key=lambda r: (_has_dc_keyword(r.get("description")),
                       r.get("start_date") or ""),
        reverse=True,
    )
    rec = records[0]
    start = _parse_date(rec.get("start_date"))
    if start and start < SWEEP_WINDOW_START:
        return "pre_2018", rec
    if not _has_dc_keyword(rec.get("description")):
        return "no_dc_keywords", rec
    if start and start > SWEEP_DATE:
        return "post_sweep", rec
    return "sweep_escape", rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path("data/new_lists/barbour_gap_postmortem.md"))
    ap.add_argument("--delay", type=float, default=2.5)
    args = ap.parse_args()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.external_ref, p.planning_ref, p.title,
                       p.stage_summary, p.authority_name, p.planning_link
                FROM projects p
                WHERE p.planning_ref IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM project_applications pa
                                  WHERE pa.project_id = p.id)
                ORDER BY p.stage_summary, p.external_ref
                """
            )
            cols = [d[0] for d in cur.description]
            targets = [dict(zip(cols, row)) for row in cur.fetchall()]

        planit_source_id = repo.ensure_source(
            conn, name="planit", kind="aggregator",
            base_url="https://www.planit.org.uk/api",
        )

        def cache_get(url: str) -> bytes | None:
            return repo.find_cached_response(
                conn, source_id=planit_source_id, key=url)

        results: list[tuple[dict, str, dict | None]] = []
        rate_limited = False
        with PlanItClient(delay_seconds=args.delay, cache_get=cache_get) as client:
            for i, t in enumerate(targets, 1):
                ref = t["planning_ref"]
                if ref.upper().startswith("FIND A TENDER"):
                    results.append((t, "procurement_notice", None))
                    print(f"[{i:2d}/{len(targets)}] {ref[:30]:30} procurement_notice")
                    continue
                if rate_limited:
                    results.append((t, "pending", None))
                    continue
                records: list[dict] = []
                try:
                    for page in client.iter_applications(
                        search=None, id_match=ref, pg_sz=20,
                    ):
                        if not page.cached:
                            repo.record_snapshot(
                                conn, source_id=planit_source_id,
                                key=page.url, raw_bytes=page.raw,
                            )
                            conn.commit()
                        records.extend(page.data.get("records", []))
                except RuntimeError as e:
                    # Persistent 429s — PlanIt's quota is exhausted for now.
                    # Finish gracefully with what we have; completed lookups
                    # are cached, so a later re-run resumes for free.
                    print(f"[{i:2d}/{len(targets)}] {ref[:30]:30} RATE-LIMITED — "
                          f"remaining refs marked pending ({e})")
                    rate_limited = True
                    results.append((t, "pending", None))
                    continue
                verdict, rec = classify(records, authority=t["authority_name"])
                results.append((t, verdict, rec))
                name = (rec or {}).get("name", "")
                print(f"[{i:2d}/{len(targets)}] {ref[:30]:30} {verdict:18} {name[:40]}")

        # ------------------------------------------------------------------
        # Report
        # ------------------------------------------------------------------
        by_verdict: dict[str, list] = {}
        for t, verdict, rec in results:
            by_verdict.setdefault(verdict, []).append((t, rec))

        lines = [
            "# Barbour ABI gap post-mortem",
            "",
            "Generated by `scripts/barbour_gap_postmortem.py` against PlanIt "
            "(`id_match` lookups, cached in `source_snapshots`).",
            "",
            f"{len(targets)} Barbour projects carry a planning reference that "
            f"didn't match any application in our universe. Why:",
            "",
            "| Classification | Count | Meaning |",
            "|---|---|---|",
        ]
        meanings = {
            "procurement_notice": "Not a planning reference (Find a Tender id)",
            "pre_2018": "In PlanIt, but predates our 2018+ sweep window",
            "no_dc_keywords": "In PlanIt, in-window, but description has no DC keyword — the description sweep couldn't see it",
            "post_sweep": "In PlanIt with DC keywords, but post-dates the 2026-05 sweep",
            "sweep_escape": "In PlanIt, in-window, with keywords — genuine escape, examine individually",
            "ref_collision": "PlanIt's hits for this bare ref are in a different council than Barbour's authority — not found for this authority",
            "not_in_planit": "No PlanIt record for the bare ref (portal-only, Crown dependency, or ref drift)",
            "pending": "Not looked up yet — run aborted by PlanIt rate limiting; re-run to resume from cache",
        }
        order = ["sweep_escape", "post_sweep", "no_dc_keywords", "pre_2018",
                 "ref_collision", "not_in_planit", "procurement_notice", "pending"]
        for v in order:
            if v in by_verdict:
                lines.append(f"| {v} | {len(by_verdict[v])} | {meanings[v]} |")
        lines.append("")

        for v in order:
            if v not in by_verdict:
                continue
            lines.append(f"## {v} ({len(by_verdict[v])})")
            lines.append("")
            for t, rec in by_verdict[v]:
                lines.append(
                    f"- **{t['planning_ref']}** — {t['title'] or '(untitled)'} "
                    f"(Barbour {t['external_ref']}, {t['stage_summary']}, "
                    f"authority: {t['authority_name'] or 'n/a'})"
                )
                if rec:
                    lines.append(
                        f"  - PlanIt: `{rec.get('name')}` start={rec.get('start_date')} "
                        f"state={rec.get('app_state')}"
                    )
                    desc = (rec.get("description") or "").strip().replace("\n", " ")
                    if desc:
                        lines.append(f"  - description: {desc[:300]}")
            lines.append("")

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines))
        print(f"\nReport: {args.out}")
        counts = {v: len(items) for v, items in sorted(by_verdict.items())}
        print(f"Summary: {counts}")


if __name__ == "__main__":
    main()
