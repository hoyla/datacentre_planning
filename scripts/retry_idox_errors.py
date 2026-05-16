"""Targeted retry pass for the Idox document-fetch adapter.

Builds a cohort from two distinct error sources and re-runs the existing
`fetch_documents_for_application` orchestrator against just those apps —
the cleanly-done worklist folders are left untouched (their manifests and
contents stay byte-for-byte as Aisha already received them).

Cohort:

  1. Apps whose per-app `_manifest.json` records `errors > 0` (transient
     per-doc download failures: 429-after-retries-exhausted, timeouts,
     intermittent 404s, peer disconnects).
  2. Apps that the original sweep classified as `SKIP[RuntimeError]` or
     `SKIP[no_documents_or_unparseable]` — the first is the whole-app
     equivalent of (1); the second is a mixed bag (some are genuinely
     withdrawn pages that pre-fix detection missed, some are real parse
     gaps worth re-checking now).

Not retried: `SKIP[withdrawn_from_view]` (genuinely gone) and
`SKIP[dns_failure]` (defunct portals). Their absence here is deliberate.

Outputs a `_retry_<date>.json` summary at the top of `data/raw/idox/`
listing the cohort, per-app before/after counts, and which directories
got new content — so Aisha can quickly see which folders to re-copy.

Usage:
    python scripts/retry_idox_errors.py                # default cohort
    python scripts/retry_idox_errors.py --sweep-output <path>   # override
    python scripts/retry_idox_errors.py --dry-run      # cohort only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox  # noqa: E402


RAW_IDOX_DIR = ROOT / "data" / "raw" / "idox"
DEFAULT_SWEEP_OUTPUT = Path(
    "/private/tmp/claude-1002768237/-Users-luke-hoyland-Code-Other-GitHub-datacentre-planning"
    "/94ac77e2-1630-4d17-a865-678f6a470460/tasks/bwwo8wap3.output"
)

RETRY_ERROR_CLASSES = {"RuntimeError", "no_documents_or_unparseable"}
# Deliberately excluded: withdrawn_from_view (genuine), dns_failure (defunct).


def _scan_errored_manifests() -> list[tuple[str, int, int]]:
    """List of (application_ref, prior_doc_count, prior_errors) for each
    `_manifest.json` whose `errors > 0`. Application_ref is reconstructed
    from the directory layout."""
    out: list[tuple[str, int, int]] = []
    for manifest_path in RAW_IDOX_DIR.rglob("_manifest.json"):
        data = json.loads(manifest_path.read_text())
        if data.get("errors", 0) > 0:
            out.append((
                data["application_ref"],
                len(data.get("documents", [])),
                data["errors"],
            ))
    return out


_SKIP_RE = re.compile(r"^\s+(\S+)\s+SKIP\[([^\]]+)\]\s*$")


def _scan_sweep_skips(sweep_output_path: Path) -> list[tuple[str, str]]:
    """Parse the previous sweep's stdout log for SKIP[<class>] lines.
    Returns (application_ref, error_class) for every skip whose class is in
    `RETRY_ERROR_CLASSES`."""
    if not sweep_output_path.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in sweep_output_path.read_text().splitlines():
        m = _SKIP_RE.match(line)
        if m is None:
            continue
        ref, cls = m.group(1), m.group(2)
        if cls in RETRY_ERROR_CLASSES:
            out.append((ref, cls))
    return out


def _app_lookup(conn, refs: list[str]) -> dict[str, tuple[int, str]]:
    """Map `application_ref -> (id, url)` for the cohort. Apps missing from
    the database — shouldn't happen — get dropped with a warning."""
    if not refs:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, application_ref, url FROM applications "
            "WHERE application_ref = ANY(%s)",
            (refs,),
        )
        return {ref: (id_, url) for id_, ref, url in cur.fetchall()}


def _count_docs_for_app(conn, application_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM documents WHERE application_id = %s",
            (application_id,),
        )
        return cur.fetchone()[0]


def _read_manifest_state(application_ref: str) -> tuple[int, int] | None:
    """Return `(docs, errors)` from the current manifest if present, else None."""
    manifest_path = RAW_IDOX_DIR / application_ref / idox.MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    data = json.loads(manifest_path.read_text())
    return len(data.get("documents", [])), data.get("errors", 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-output", type=Path, default=DEFAULT_SWEEP_OUTPUT,
                    help="Path to the original sweep's stdout log "
                         "(for SKIP-class detection).")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the cohort and exit; don't fetch anything.")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    # ---- Build cohort ---------------------------------------------------
    errored = _scan_errored_manifests()
    skipped = _scan_sweep_skips(args.sweep_output)

    print(f"Errored-manifest apps: {len(errored)}")
    print(f"SKIP-class apps in retry classes: {len(skipped)}")

    cohort_refs: list[str] = sorted({
        ref for ref, _docs, _errs in errored
    } | {ref for ref, _cls in skipped})
    print(f"Cohort total (unique): {len(cohort_refs)}")
    if args.dry_run:
        print()
        print("Cohort details (dry-run):")
        for ref, docs, errs in sorted(errored, key=lambda r: -r[2])[:20]:
            print(f"  {errs:3d} doc errors / {docs:3d} docs   {ref}")
        for ref, cls in skipped:
            print(f"  SKIP[{cls}]   {ref}")
        return 0

    # ---- Capture before-state per app -----------------------------------
    before_state: dict[str, dict] = {}
    with db.connect() as conn:
        app_ids = _app_lookup(conn, cohort_refs)
        for ref in cohort_refs:
            if ref not in app_ids:
                print(f"  warning: {ref} not in applications table; skipping")
                continue
            app_id, _ = app_ids[ref]
            db_docs = _count_docs_for_app(conn, app_id)
            manifest_state = _read_manifest_state(ref)
            before_state[ref] = {
                "application_id": app_id,
                "db_docs": db_docs,
                "manifest_docs": manifest_state[0] if manifest_state else None,
                "manifest_errors": manifest_state[1] if manifest_state else None,
                "had_manifest": manifest_state is not None,
            }

    # ---- Run retry ------------------------------------------------------
    started_at = dt.datetime.now(dt.timezone.utc)
    per_app_results: list[dict] = []

    source_id = None
    with db.connect() as conn:
        source_id = repo.ensure_source(
            conn, name=idox.SOURCE_NAME, kind="council",
            base_url="(per-council Idox host)",
        )
        with idox.IdoxClient(delay_seconds=args.delay) as client:
            for ref in cohort_refs:
                if ref not in app_ids:
                    continue
                app_id, url = app_ids[ref]
                print(f"  retrying {ref}  …")
                summary = idox.fetch_documents_for_application(
                    conn, client=client, application_id=app_id,
                    application_ref=ref,
                    application_url=url, source_id=source_id,
                    data_dir=args.data_dir,
                )
                new_state = _read_manifest_state(ref)
                db_docs_after = _count_docs_for_app(conn, app_id)
                per_app_results.append({
                    "application_ref": ref,
                    "before": before_state[ref],
                    "after": {
                        "db_docs": db_docs_after,
                        "manifest_docs": new_state[0] if new_state else None,
                        "manifest_errors": new_state[1] if new_state else None,
                        "had_manifest": new_state is not None,
                    },
                    "retry_summary": summary,
                    "files_added": db_docs_after - before_state[ref]["db_docs"],
                })

    finished_at = dt.datetime.now(dt.timezone.utc)

    # ---- Write retry manifest ------------------------------------------
    changed = [r for r in per_app_results if r["files_added"] > 0]
    still_failing = [
        r for r in per_app_results
        if r["after"].get("manifest_errors") and r["after"]["manifest_errors"] > 0
    ]
    newly_complete = [
        r for r in per_app_results
        if (r["before"].get("manifest_errors") or 0) > 0
        and (r["after"].get("manifest_errors") or 0) == 0
    ]

    out_path = RAW_IDOX_DIR / f"_retry_{started_at.date().isoformat()}.json"
    out_path.write_text(json.dumps({
        "generated_at_utc": started_at.isoformat(timespec="seconds"),
        "finished_at_utc": finished_at.isoformat(timespec="seconds"),
        "cohort_size": len(cohort_refs),
        "cohort_sources": {
            "errored_manifests": len(errored),
            "sweep_skip_runtime_or_unparseable": len(skipped),
        },
        "summary": {
            "apps_retried": len(per_app_results),
            "apps_with_new_files": len(changed),
            "total_new_files": sum(r["files_added"] for r in per_app_results),
            "newly_complete_apps": len(newly_complete),
            "still_failing_apps": len(still_failing),
        },
        "modified_folders": sorted(r["application_ref"] for r in changed),
        "still_failing_folders": sorted(r["application_ref"] for r in still_failing),
        "apps": per_app_results,
    }, ensure_ascii=False, indent=2) + "\n")

    print()
    print(f"Wrote retry manifest: {out_path}")
    print(f"  apps retried:        {len(per_app_results)}")
    print(f"  apps with new files: {len(changed)}")
    print(f"  total new files:     {sum(r['files_added'] for r in per_app_results)}")
    print(f"  newly complete:      {len(newly_complete)}")
    print(f"  still failing:       {len(still_failing)}")
    if changed:
        print()
        print("Modified folders (re-copy these for Aisha):")
        for r in sorted(changed, key=lambda x: -x["files_added"])[:10]:
            print(f"  +{r['files_added']:3d} files   {r['application_ref']}")
        if len(changed) > 10:
            print(f"  ... ({len(changed) - 10} more — see retry manifest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
