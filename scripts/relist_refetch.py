#!/usr/bin/env python3
"""Refetch the documents the re-list audit found absent from the corpus.

`scripts/relist_audit.py` measured what the registers offered against what
we hold and wrote one row per absent document to
`data/reports/relist_refetch_list.csv`. This is the pass that goes and
gets them. It downloads nothing itself: it hands each application back to
the adapter that fetched it originally, so manifests, content-hash dedup,
snapshots and provenance behave exactly as they do on a first fetch, and
a document that has since been withdrawn is simply not offered again.

Re-walking the whole application rather than the CSV's individual URLs is
deliberate. The audit's listing is a snapshot from May; the register has
moved on. The adapters re-list live, skip every document already held by
URL, and download the rest — which picks up documents added since the
audit as well as the ones it named, and never re-downloads bytes we have.

**Priority is the point.** The absent documents are not equally valuable:
175 are filed `Report/ Statement`, the class where power disclosures
live, and 707 are drawings. So the work is cut into tranches and each is
a separate run, worked to completion before the next starts:

    reports    applications with an absent report or statement
    priority   Northumberland Energy Park, and the Telehouse application
    rest       everything else except the Glasgow university masterplan
    glasgow    the Gilmorehill campus masterplan — 491 drawings for a
               university estate, the largest single block in the list
               and the least likely to matter to the investigation

Etiquette is per host, not global: applications are sharded by portal
hostname and one worker takes each shard strictly serially, so a host
never sees more than one request at a time and never faster than
`--delay` (default 10s). A host that refuses three applications in a row
has the rest of its shard recorded as retryable errors and dropped for
this run. Coventry is skipped by name — it is AWS WAF-protected and
deliberately not scraped.

Resumable. Each application that finishes cleanly is written to
`data/raw/_relist_refetch_state.json` as it completes; relaunching the
same command skips straight past them. An application that ended with
errors stays eligible, and re-walking it is cheap.

    scripts/relist_refetch.py --tranche reports --dry-run
    scripts/relist_refetch.py --tranche reports
    scripts/relist_refetch.py --tranche priority
    scripts/relist_refetch.py --tranche rest
    scripts/relist_refetch.py --tranche glasgow
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import datetime as dt
import importlib.util
import json
import logging
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.acquisition_outcome import classify_outcome  # noqa: E402
from dcp.sources import agile, aifusion, arcus, idox, ocella, salesforce_pr  # noqa: E402

log = logging.getLogger("relist_refetch")

REFETCH_CSV = Path("data/reports/relist_refetch_list.csv")
STATE_PATH = Path("data/raw/_relist_refetch_state.json")

# Deliberately not scraped: AWS WAF-protected, and the project's standing
# decision is to leave it alone rather than probe it.
BLOCKED_HOSTS = ("planningportal.coventry.gov.uk", "coventry.gov.uk")

GLASGOW_SITE = "PTNO-12104907"          # Gilmorehill campus masterplan
NEP_SITE = "PTNO-12785975"              # Northumberland Energy Park
TELEHOUSE_REF = "TowerHamlets/PA/18/03088/A1"

# The class that carries power disclosures. The audit's own kind label is
# `Report/ Statement` (175 documents across 6 applications); the wider
# match also takes `Report`, `Officer Report`, `Environmental Statement`,
# `Transport Statement` and the rest, which is 291 documents across 30
# applications. The wider one is the tranche: a planning statement is a
# planning statement whichever kind string the portal filed it under.
def _is_report(kind: str | None) -> bool:
    k = (kind or "").lower()
    return "report" in k or "statement" in k


HANDLED = ("idox", "ocella", "agile", "arcus", "aifusion", "salesforce_pr",
           "newport_docstore")


def _newport_module():
    path = Path(__file__).resolve().parent / "fetch_newport_docstore.py"
    spec = importlib.util.spec_from_file_location("newport_docstore", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------
# The work list
# --------------------------------------------------------------------

class Target:
    __slots__ = ("ref", "url", "adapter", "site_key", "site_name",
                 "absent", "reports", "app_id", "host")

    def __init__(self, row: dict):
        self.ref = row["application_ref"]
        self.url = row["application_url"]
        self.adapter = row["adapter"]
        self.site_key = row["site_key"]
        self.site_name = row["site_name"]
        self.absent = 0
        self.reports = 0
        self.app_id: int | None = None
        self.host = (urlparse(self.url).hostname or "").lower()


def load_targets(csv_path: Path) -> dict[str, Target]:
    """One Target per application, carrying how many documents the audit
    found absent for it and how many of those are reports."""
    targets: dict[str, Target] = {}
    with csv_path.open() as fh:
        for row in csv.DictReader(fh):
            t = targets.get(row["application_ref"])
            if t is None:
                t = targets[row["application_ref"]] = Target(row)
            t.absent += 1
            if _is_report(row["kind"]):
                t.reports += 1
    return targets


def tranche_of(t: Target) -> str:
    if t.site_key == GLASGOW_SITE:
        return "glasgow"
    if t.reports:
        return "reports"
    if t.site_key == NEP_SITE or t.ref == TELEHOUSE_REF:
        return "priority"
    return "rest"


# --------------------------------------------------------------------
# State
# --------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"completed": {}, "started_at": dt.datetime.now().isoformat()}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(STATE_PATH)


def record(conn, app_id: int, outcome: str, adapter: str,
           detail: str | None = None, found: int = 0) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO acquisition_outcome
                       (application_id, outcome, adapter, detail, documents_found)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (app_id, outcome, adapter, detail, found))
    conn.commit()


# --------------------------------------------------------------------
# One host's shard
# --------------------------------------------------------------------

def _run_shard(host: str, targets: list[Target], *, args, state: dict,
               lock: threading.Lock, totals: dict, results: list) -> None:
    """Fetch one portal host's applications, serially, with this worker's
    own clients and database connection."""
    clients: dict[str, object] = {}

    def client_for(fam: str):
        if fam not in clients:
            if fam == "ocella":
                clients[fam] = ocella.OcellaClient(
                    delay_seconds=args.delay, backoff_seconds=args.backoff,
                    max_retries=args.max_retries)
            elif fam == "agile":
                clients[fam] = agile.AgileClient(
                    delay_seconds=args.delay, max_retries=args.max_retries)
            elif fam == "arcus":
                clients[fam] = arcus.ArcusClient(
                    delay_seconds=args.delay, max_retries=args.max_retries)
            else:
                # idox, aifusion and salesforce_pr all speak through the
                # Idox client.
                clients[fam] = idox.IdoxClient(
                    delay_seconds=args.delay, backoff_seconds=args.backoff,
                    max_retries=args.max_retries)
        return clients[fam]

    listings = salesforce_pr.load_listings() if any(
        t.adapter == "salesforce_pr" for t in targets) else {}
    strikes = 0
    try:
        with db.connect() as conn:
            src = {}
            for t in targets:
                if t.adapter not in src:
                    name = {"salesforce_pr": "salesforce",
                            "newport_docstore": "idox"}.get(t.adapter, t.adapter)
                    src[t.adapter] = repo.ensure_source(
                        conn, name=name, kind="council",
                        base_url=f"(per-council {name} host)")
            conn.commit()

            for t in targets:
                if strikes >= args.host_strikes:
                    with lock:
                        totals["host_dropped"] += 1
                        results.append({"ref": t.ref, "host": host,
                                        "outcome": "skipped_host_refusing",
                                        "absent": t.absent})
                    record(conn, t.app_id, "error", t.adapter,
                           f"skipped: {host} refused {args.host_strikes} "
                           f"applications in a row this run")
                    continue
                if shutil.disk_usage(args.data_dir).free / 1e9 < args.min_free_gb:
                    log.error("%s: stopping, below the disk floor", host)
                    break

                t0 = time.time()
                kw = dict(conn=conn, application_id=t.app_id,
                          application_ref=t.ref, application_url=t.url,
                          source_id=src[t.adapter], data_dir=args.data_dir)
                # The per-application ceiling fetch_outstanding.py has,
                # by a different mechanism: its SIGALRM only works in
                # the main thread and this loop is a worker. A timer
                # closes this shard's clients instead, which makes a
                # stalled read — the twenty-minute open-idle-connection
                # signature of 2026-08-26 — raise into the except arm
                # below, where the application is recorded `error` and
                # so stays retryable. The cleared dict means the next
                # application builds fresh clients.
                timed_out = threading.Event()

                def _cut_off():
                    timed_out.set()
                    for c in list(clients.values()):
                        with contextlib.suppress(Exception):
                            c.close()
                    clients.clear()

                watchdog = threading.Timer(args.app_timeout, _cut_off)
                watchdog.daemon = True
                watchdog.start()
                try:
                    if t.adapter == "idox":
                        s = idox.fetch_documents_for_application(
                            client=client_for("idox"), **kw)
                    elif t.adapter == "ocella":
                        s = ocella.fetch_documents_for_application(
                            client=client_for("ocella"), **kw)
                    elif t.adapter == "agile":
                        s = agile.fetch_documents_for_application(
                            client=client_for("agile"), **kw)
                    elif t.adapter == "arcus":
                        s = arcus.fetch_documents_for_application(
                            client=client_for("arcus"), **kw)
                    elif t.adapter == "aifusion":
                        s = aifusion.fetch_documents_for_application(
                            client=client_for("aifusion"), **kw)
                    elif t.adapter == "salesforce_pr":
                        s = salesforce_pr.fetch_documents_for_application(
                            client=client_for("idox"), listings=listings, **kw)
                    elif t.adapter == "newport_docstore":
                        # Newport's URL is Idox-shaped and its documents
                        # are not on the documents tab; its fetcher takes
                        # the reference and finds them in the docstore.
                        newport = _newport_module()
                        s = newport.fetch_one(conn, client_for("idox"),
                                              ref=t.ref)
                    else:
                        s = {"error_class": "no_adapter", "links_found": 0,
                             "downloaded": 0, "skipped_existing": 0,
                             "errors": 0}
                except Exception as exc:
                    detail = (f"timeout: exceeded {args.app_timeout}s "
                              f"wall-clock; recorded retryable"
                              if timed_out.is_set() else str(exc)[:180])
                    record(conn, t.app_id, "error", t.adapter, detail)
                    with lock:
                        totals["timeout" if timed_out.is_set()
                               else "error"] += 1
                        results.append({"ref": t.ref, "host": host,
                                        "outcome": ("timeout"
                                                    if timed_out.is_set()
                                                    else "exception"),
                                        "detail": detail,
                                        "absent": t.absent})
                    log.error("%-40s %s %s", t.ref,
                              "TIMEOUT" if timed_out.is_set() else "EXCEPTION",
                              detail[:90])
                    strikes += 1
                    continue
                finally:
                    watchdog.cancel()

                got = s.get("downloaded", 0)
                errs = s.get("errors", 0)
                zero = s.get("zero_byte", 0)
                listed = s.get("links_found") or 0
                held = got + (s.get("skipped_existing") or 0)
                strikes = strikes + 1 if (errs and not got) else 0

                # `none_published` is a SETTLED verdict, and the rule for
                # awarding one lives in dcp/acquisition_outcome.py — not
                # here. This file used to carry its own copy, and the copy
                # had already drifted: it also accepted
                # `no_documents_in_store`, which is the Newport docstore's
                # own empty answer, on the one host where an unparseable
                # page used to return an empty list. That is the same
                # mistake in an eighth costume, on the exact site that
                # produced all 17 wrongly-settled applications found on
                # 2026-08-26 — Uskmouth Power Station, 350 documents
                # offered and none held. One rule, one place.
                outcome, detail = classify_outcome(s)
                record(conn, t.app_id, outcome, t.adapter, detail, got)

                with lock:
                    totals[outcome] = totals.get(outcome, 0) + 1
                    totals["documents"] += got
                    totals["doc_errors"] += errs
                    totals["zero_byte"] += zero
                    results.append({
                        "ref": t.ref, "host": host, "adapter": t.adapter,
                        "site_key": t.site_key, "outcome": outcome,
                        "absent_at_audit": t.absent, "listed": listed,
                        "downloaded": got, "held": held, "errors": errs,
                        "zero_byte": zero, "error_class": s.get("error_class"),
                        "seconds": round(time.time() - t0, 1)})
                    # Only a clean finish is remembered. Anything with
                    # errors stays eligible for the next relaunch.
                    if errs == 0 and outcome in ("fetched", "none_published"):
                        state["completed"][t.ref] = {
                            "downloaded": got, "at": dt.datetime.now().isoformat()}
                        _save_state(state)
                    log.info("%-42s %-14s listed=%-4d new=%-4d err=%-3d "
                             "(%.0fs) | run total %d docs",
                             t.ref[:42], outcome, listed, got, errs,
                             time.time() - t0, totals["documents"])
    finally:
        for c in clients.values():
            try:
                c.close()
            except Exception:
                pass


# --------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tranche", default="reports",
                   choices=["reports", "priority", "rest", "glasgow", "all"])
    p.add_argument("--csv", type=Path, default=REFETCH_CSV)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=10.0,
                   help="minimum seconds between requests to one host")
    p.add_argument("--backoff", type=float, default=30.0)
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--host-strikes", type=int, default=3)
    p.add_argument("--app-timeout", type=int, default=900,
                   help="wall-clock ceiling per application, seconds — "
                        "the same 900 fetch_outstanding.py uses; a "
                        "timed-out application is recorded as a "
                        "retryable error, never settled")
    p.add_argument("--min-free-gb", type=float, default=15.0)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    targets = load_targets(args.csv)
    state = _load_state()
    done = set(state.get("completed", {}))

    chosen, skipped = [], collections.Counter()
    for t in targets.values():
        tr = tranche_of(t)
        if args.tranche != "all" and tr != args.tranche:
            continue
        if t.ref in done:
            skipped["already_complete"] += 1
            continue
        if any(b in t.host for b in BLOCKED_HOSTS):
            skipped["coventry_waf_skipped_by_policy"] += 1
            continue
        if t.adapter not in HANDLED:
            skipped[f"no_adapter:{t.adapter}"] += 1
            continue
        chosen.append(t)

    # Resolve application ids. A ref in the CSV that no longer resolves is
    # a real finding, not something to paper over.
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT application_ref, id FROM applications "
                    "WHERE application_ref = ANY(%s)",
                    ([t.ref for t in chosen],))
        ids = dict(cur.fetchall())
    unresolved = [t.ref for t in chosen if t.ref not in ids]
    for ref in unresolved:
        skipped["ref_not_in_applications"] += 1
    chosen = [t for t in chosen if t.ref in ids]
    for t in chosen:
        t.app_id = ids[t.ref]

    # Biggest shortfall first within each host, so an interrupted run has
    # taken the applications that matter most.
    chosen.sort(key=lambda t: (-t.reports, -t.absent, t.ref))
    if args.limit:
        chosen = chosen[:args.limit]

    per_host: dict[str, list[Target]] = collections.defaultdict(list)
    for t in chosen:
        per_host[t.host].append(t)

    log.info("tranche %s: %d applications, %d absent documents, "
             "%d reports/statements, across %d hosts",
             args.tranche, len(chosen), sum(t.absent for t in chosen),
             sum(t.reports for t in chosen), len(per_host))
    for k, v in sorted(skipped.items()):
        log.info("   skipped %-38s %d", k, v)
    if unresolved:
        log.warning("   unresolved refs: %s", ", ".join(unresolved[:10]))
    for h, ts in sorted(per_host.items(), key=lambda kv: -sum(
            t.absent for t in kv[1]))[:12]:
        log.info("   %-46s %3d apps  %4d absent", h, len(ts),
                 sum(t.absent for t in ts))
    if args.dry_run:
        return 0

    totals = {"fetched": 0, "partial": 0, "none_published": 0, "error": 0,
              "timeout": 0, "host_dropped": 0, "documents": 0,
              "doc_errors": 0, "zero_byte": 0}
    results: list[dict] = []
    lock = threading.Lock()
    started = time.monotonic()
    shards = sorted(per_host.items(), key=lambda kv: -len(kv[1]))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_run_shard, host, ts, args=args, state=state,
                               lock=lock, totals=totals, results=results)
                   for host, ts in shards]
        for f in futures:
            f.result()

    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    manifest = Path("data/raw") / f"_relist_refetch_{args.tranche}_{stamp}.json"
    manifest.write_text(json.dumps(
        {"tranche": args.tranche, "totals": totals,
         "skipped": dict(skipped), "unresolved_refs": unresolved,
         "minutes": round((time.monotonic() - started) / 60, 1),
         "results": results}, ensure_ascii=False, indent=2) + "\n")
    log.info("done in %.0fm: %d documents downloaded "
             "(%d fetched, %d partial, %d hold nothing, %d errors, "
             "%d dropped for a refusing host); %d per-document failures "
             "of which %d zero-byte",
             (time.monotonic() - started) / 60, totals["documents"],
             totals["fetched"], totals["partial"], totals["none_published"],
             totals["error"], totals["host_dropped"], totals["doc_errors"],
             totals["zero_byte"])
    log.info("manifest: %s", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
