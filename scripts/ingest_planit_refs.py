#!/usr/bin/env python3
"""Ingest named application references from PlanIt, one `id_match` each.

The gap this fills. The national keyword sweep finds applications whose
*description* says data centre. A building consented as a B8 shell and
converted by a later variation never says it, and neither do its
condition discharges — so a scheme can be wholly absent while its
neighbour's paperwork names it in full. The Hemel Hempstead review
(2026-09-07) is the worked case: Amazon's Learning Lab application cited
the 3A Blossom Way permission chain by reference, and the corpus held
none of it.

Why by reference rather than by spatial sweep. A radius returns the
neighbourhood — 507 records within 450 m of one Hemel address — and
choosing from it is the judgement this project puts in a prior, not in a
filter. A reference list is the output of that judgement: someone read
the documents, wrote down what belongs, and this script fetches exactly
that. `discovered_via` records the label so the cohort stays visible
afterwards.

Two duties the caller owns, not this script:

  1. **Add the refs to their partition entry before the next
     materialise**, per site_partitions.yaml's own maintenance note. A
     new application with no family edge cannot spatially join a
     partition and will land in whichever unpartitioned site is in
     radius.
  2. Triage, materialise, fetch and read them — **in that order**. The
     fetch queue admits an application only once it is a live site
     member, and membership follows the triage verdict, so a fetch run
     before the sweep silently finds nothing to do.

Idempotent and resumable: each lookup is served from `source_snapshots`
when already captured, so a re-run after a 429 wall costs nothing for
the part already done. `name` is unique nationally in PlanIt, so a
council-prefixed id_match yields at most one record; anything ambiguous
is reported and skipped rather than guessed at.

Input file: one reference per line, `#` comments ignored, and a line of
the form `# label: <slug>` names the cohort; each application is tagged
`ref_ingest:<slug>` in `discovered_via`.

Usage:
    scripts/ingest_planit_refs.py --file refs.txt --dry-run
    scripts/ingest_planit_refs.py --file refs.txt --delay 12
    scripts/ingest_planit_refs.py --ref Dacorum/22/01067/ROC --label hemel-3a
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources.planit import (  # noqa: E402
    BASE, SOURCE_NAME, PlanItClient, RateLimited, _fetch_parent,
    _load_area_gss_map,
)

DEFAULT_LABEL = "ref_ingest"


def parse_ref_file(text: str) -> list[tuple[str, str]]:
    """-> [(ref, label)], in file order. `# label: <slug>` sets the label."""
    out: list[tuple[str, str]] = []
    label = DEFAULT_LABEL
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if body.lower().startswith("label:"):
                label = body.split(":", 1)[1].strip() or DEFAULT_LABEL
            continue
        out.append((line, label))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=None,
                    help="Reference list; one per line, '# label: <slug>' sets the tag.")
    ap.add_argument("--ref", action="append", default=[],
                    help="A single reference (repeatable).")
    ap.add_argument("--label", default=DEFAULT_LABEL,
                    help="discovered_via tag for --ref arguments.")
    ap.add_argument("--delay", type=float, default=12.0,
                    help="Inter-request delay. PlanIt is donation-supported "
                         "and 429s on a quota; 10s+ is the current spacing.")
    ap.add_argument("--max-retry-after", type=float, default=900.0,
                    help="Longest server-requested wait to sit through. "
                         "PlanIt's limit is a quota window, so waiting it "
                         "out is the polite move; the client gives up above "
                         "this and the run resumes from cache next time.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-fetch even where a snapshot exists.")
    args = ap.parse_args()

    targets: list[tuple[str, str]] = []
    if args.file:
        targets += parse_ref_file(args.file.read_text())
    targets += [(r, args.label) for r in args.ref]
    if not targets:
        raise SystemExit("nothing to do: pass --file or --ref")

    seen: set[str] = set()
    targets = [(r, lb) for r, lb in targets
               if not (r in seen or seen.add(r))]

    summary = {"considered": len(targets), "already_held": 0, "ingested": 0,
               "cached": 0, "not_found": 0, "ambiguous": 0}

    with db.connect() as conn:
        source_id = repo.ensure_source(
            conn, name=SOURCE_NAME, kind="aggregator", base_url=BASE)
        gss_map = _load_area_gss_map(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT application_ref FROM applications "
                        "WHERE source_id = %s", (source_id,))
            held = {r[0] for r in cur.fetchall()}

        cache_get = None
        if not args.no_resume:
            def cache_get(url: str) -> bytes | None:
                return repo.find_cached_response(conn, source_id=source_id, key=url)

        with PlanItClient(delay_seconds=args.delay, cache_get=cache_get,
                          max_retry_after=args.max_retry_after) as client:
            for ref, label in targets:
                if ref in held:
                    print(f"  held      {ref}")
                    summary["already_held"] += 1
                    continue
                try:
                    rec, page = _fetch_parent(client, ref)
                except RateLimited as exc:
                    print(f"\nPlanIt asked for {exc.retry_after:.0f}s — stopping. "
                          f"Re-run to resume; captured lookups are cached.",
                          file=sys.stderr)
                    break
                if page is not None and page.cached:
                    summary["cached"] += 1
                if rec is None:
                    kind = "ambiguous" if page is not None else "not_found"
                    print(f"  {kind:9s} {ref}")
                    summary[kind] += 1
                    continue
                print(f"  {'DRY ' if args.dry_run else ''}ingest {ref:26s} "
                      f"{rec.get('start_date')}  {(rec.get('address') or '')[:42]:42s} "
                      f"[{label}]")
                if args.dry_run:
                    continue
                if page is not None and not page.cached:
                    repo.record_snapshot(conn, source_id=source_id,
                                         key=page.url, raw_bytes=page.raw)
                repo.upsert_application(
                    conn, source_id=source_id, app=rec,
                    council_gss=gss_map.get(rec.get("area_name")),
                    discovered_via=[f"ref_ingest:{label}"],
                )
                summary["ingested"] += 1
                conn.commit()

        if not args.dry_run and summary["ingested"]:
            print(f"\ncouncil_gss backfill: {repo.backfill_council_gss(conn)}")
            conn.commit()

    print(f"\nSummary: {summary}")
    if not args.dry_run and summary["ingested"]:
        print("\nNext, and in this order — the fetch queue admits only\n"
              "live site members, so triage and materialise come first:\n"
              "  1. add every new ref to its entry in "
              "data/priors/site_partitions.yaml\n"
              "  2. scripts/catalogue_sweep.py   (dc_build triage)\n"
              "  3. scripts/materialise_sites.py --dry-run, then for real\n"
              "  4. scripts/fetch_outstanding.py --dry-run, then for real\n"
              "  5. scripts/deepread_escalate_openai.py --cohort first_read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
