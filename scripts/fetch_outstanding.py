#!/usr/bin/env python3
"""Fetch the applications we have not yet dealt with.

"Applications with no documents" was never one thing. Some we have never
gone after; others were fetched and the register genuinely holds nothing.
The second group is completed work — a fact about what the applicant
published, not a gap in our collection — and keeping it in the queue
makes the outstanding number look permanently worse than it is.

So this works from `acquisition_outcome` rather than from the absence of
documents: an application is outstanding only if we have never reached a
verdict on it, or the verdict was a transient error. Anything recorded
`none_published`, `portal_blocked` or `login_required` stays out of the
queue until someone deliberately re-checks it.

Every attempt writes its own outcome row, so the queue shrinks as work is
done and `application_acquisition.last_checked_at` stays truthful for
planning revisits — an application whose register held nothing in March
may hold an Environmental Statement by August.

Dispatches to whichever adapter suits the portal. Portals we cannot read
are recorded `no_adapter` rather than retried.

    scripts/fetch_outstanding.py --dry-run
    scripts/fetch_outstanding.py
    scripts/fetch_outstanding.py --recheck none_published   # deliberate revisit
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import logging
import shutil
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.acquisition_outcome import SETTLED, classify_outcome, record  # noqa: E402
from dcp.sources import (agile, arcus, idox, ni_planning, ocella,  # noqa: E402
                         salesforce_pr)

log = logging.getLogger("fetch_outstanding")

# Verdicts that mean the work is finished — imported rather than restated,
# so what settles an application and what awards a settled verdict cannot
# drift apart. `--recheck` names one explicitly when a revisit is intended.

OUTSTANDING_SQL = """
SELECT a.id, a.application_ref, a.url
FROM applications a
JOIN site_members m ON m.application_id = a.id AND m.retired_at IS NULL
LEFT JOIN LATERAL (
    SELECT outcome FROM acquisition_outcome ao
    -- Insertion order, not checked_at, matching application_acquisition.
    -- A backdated correction must not be overruled by the wrong row it
    -- was written to correct.
    WHERE ao.application_id = a.id ORDER BY ao.id DESC LIMIT 1) o ON true
WHERE a.url IS NOT NULL
  AND (NOT EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id)
       OR o.outcome = 'partial')
  AND (o.outcome IS NULL OR o.outcome IN ('error', 'partial')
       OR o.outcome = ANY(%s))
GROUP BY a.id, a.application_ref, a.url
ORDER BY a.application_ref
"""


def _campaign():
    spec = importlib.util.spec_from_file_location(
        "dc_campaign", Path(__file__).parent / "fetch_dc_campaign.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ApplicationTimeout(BaseException):
    """A single application exceeded its wall-clock budget.

    **BaseException, not Exception, and that is the whole point.** The
    adapters catch `Exception` per document so that one bad link does
    not cost the rest of a bundle — `idox.fetch_documents_for_application`
    ends its download loop with a bare `except Exception as exc: failure
    = exc; break`. A timeout raised as an ordinary Exception therefore
    landed in that handler, was filed as one document's failure, and the
    loop moved to the next link. SIGALRM fires once, so the ceiling was
    then gone for good and the application ran unbounded.

    Measured on 2026-08-27: `Southwark/18/AP/1604` ran for **216
    minutes** against a 900-second deadline, and the sweep's rate fell
    from 321 documents an hour to under 50 while it did. Deriving from
    BaseException puts the timeout beside KeyboardInterrupt and
    SystemExit, where a per-item `except Exception` cannot reach it.
    """


@contextlib.contextmanager
def deadline(seconds: int):
    """Abandon an application that will not finish.

    httpx's `timeout=` is per socket operation, not per request, so a
    server that dribbles a byte every minute never trips it. One
    Hillingdon application held the sweep for thirteen minutes on a
    connection that was open, idle and going nowhere — with no output,
    because progress is logged per application rather than per document.

    SIGALRM gives the loop a real ceiling. The raised error is caught by
    the same handler as any other failure, so the application is recorded
    `error` and retried on a later pass rather than being settled.
    """
    def fire(_signum, _frame):
        raise ApplicationTimeout(f"exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, fire)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=4.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--recheck", action="append", default=[],
                   choices=list(SETTLED),
                   help="also revisit applications already settled this way")
    p.add_argument("--min-free-gb", type=float, default=15.0)
    # The adapters' default ladder (4 tries, 60s doubling) is right for a
    # single application and wrong for a sweep: a host that is simply down
    # costs 15 minutes before we move on. Errors are recorded, not settled,
    # so a later pass retries them — better to give up quickly and revisit.
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--backoff", type=float, default=15.0)
    # Generous enough for a genuinely large document set at the request
    # spacing, short enough that one wedged connection cannot own the run.
    p.add_argument("--app-timeout", type=int, default=900,
                   help="wall-clock ceiling per application, in seconds")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    camp = _campaign()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(OUTSTANDING_SQL, (args.recheck,))
        rows = cur.fetchall()

    listings = salesforce_pr.load_listings()
    plan: dict[str, list] = {}
    for app_id, ref, url in rows:
        fam = camp.portal_family(url)
        if fam == "salesforce" and ref not in listings:
            fam = "salesforce_needs_listing"
        plan.setdefault(fam, []).append((app_id, ref, url))

    handled = ("idox", "ocella", "agile", "arcus", "salesforce",
               "ni_planning")
    log.info("outstanding: %d applications across %d portal families",
             len(rows), len(plan))
    for fam in sorted(plan, key=lambda f: -len(plan[f])):
        mark = "will fetch" if fam in handled else "no adapter"
        log.info("   %-26s %4d   %s", fam, len(plan[fam]), mark)
    if args.dry_run:
        return 0

    # One client PER HOST, not per family. The adapters answer a 429 by
    # permanently widening that client's spacing, and their contract is
    # explicit that clients are one per host so the adaptation stays
    # per-council. Sharing a client across a family breaks that: one
    # hostile council (Bassetlaw escalated 4s -> 45s) ends up throttling
    # every other council in the same sweep.
    from urllib.parse import urlparse
    rt = dict(max_retries=args.max_retries)
    def make(fam):
        if fam == "idox":
            return idox.IdoxClient(delay_seconds=args.delay,
                                   backoff_seconds=args.backoff, **rt)
        if fam == "ocella":
            return ocella.OcellaClient(delay_seconds=args.delay,
                                       backoff_seconds=args.backoff, **rt)
        if fam == "agile":
            return agile.AgileClient(delay_seconds=args.delay, **rt)
        if fam == "ni_planning":
            # A plain polite HTTP client; the adapter supplies the
            # tenant header itself, per request.
            return idox.IdoxClient(delay_seconds=args.delay,
                                   backoff_seconds=args.backoff, **rt)
        return arcus.ArcusClient(delay_seconds=args.delay, **rt)
    clients: dict[tuple, object] = {}
    def client_for(fam, url):
        key = (fam, (urlparse(url).hostname or "").lower())
        if key not in clients:
            clients[key] = make(fam)
        return clients[key]
    mods = {"idox": idox, "ocella": ocella, "agile": agile,
            "arcus": arcus, "salesforce": salesforce_pr,
            "ni_planning": ni_planning}
    totals = {"fetched": 0, "partial": 0, "none_published": 0, "error": 0,
              "no_adapter": 0, "documents": 0}
    started = time.monotonic()
    try:
        with db.connect() as conn:
            src = {f: repo.ensure_source(conn, name=f, kind="council",
                                         base_url=f"(per-council {f} host)")
                   for f in handled}
            conn.commit()
            # Portals we cannot read are recorded once, so they leave the
            # queue and stop being recounted as outstanding work.
            for fam, items in plan.items():
                if fam in handled:
                    continue
                for app_id, ref, _ in items:
                    record(conn, app_id, "no_adapter", fam,
                           "no adapter for this portal type")
                    totals["no_adapter"] += 1
                log.info("recorded %d %s applications as no_adapter",
                         len(items), fam)

            # Round-robin across hosts rather than marching alphabetically.
            # One hostile council otherwise blocks the whole sweep: Bassetlaw
            # 429s every document and the adapter widens its spacing to 45s,
            # so a run ordered by reference spends hours on 'B' before
            # reaching anyone else. Interleaving means its slowness costs
            # only its own applications.
            from collections import defaultdict, deque
            from urllib.parse import urlparse
            per_host = defaultdict(deque)
            for f in handled:
                for t in plan.get(f, []):
                    per_host[(urlparse(t[2]).hostname or "").lower()].append((f, *t))
            todo, queues = [], list(per_host.values())
            while queues:
                for q in list(queues):
                    if q: todo.append(q.popleft())
                    if not q: queues.remove(q)
            if args.limit:
                todo = todo[:args.limit]
            # A host that keeps refusing is not worth grinding through: after
            # this many consecutive failures its remaining applications are
            # recorded as errors (retryable) and skipped for this run.
            HOST_STRIKES = 3
            strikes = defaultdict(int)
            for i, (fam, app_id, ref, url) in enumerate(todo, 1):
                host = (urlparse(url).hostname or "").lower()
                if strikes[host] >= HOST_STRIKES:
                    record(conn, app_id, "error", fam,
                           f"skipped: {host} refused {HOST_STRIKES} times this run")
                    totals["error"] += 1
                    continue
                if shutil.disk_usage(args.data_dir).free / 1e9 < args.min_free_gb:
                    log.error("stopping at %d/%d: below the disk floor", i, len(todo))
                    break
                kw = dict(conn=conn, application_id=app_id, application_ref=ref,
                          application_url=url, source_id=src[fam],
                          data_dir=args.data_dir)
                if fam == "salesforce":
                    kw["client"] = client_for("idox", url); kw["listings"] = listings
                else:
                    kw["client"] = client_for(fam, url)
                try:
                    with deadline(args.app_timeout):
                        s = mods[fam].fetch_documents_for_application(**kw)
                # ApplicationTimeout is a BaseException so the adapters
                # cannot swallow it, which means this handler has to name
                # it: `except Exception` alone would let the ceiling
                # abort the whole sweep instead of one application.
                except (ApplicationTimeout, Exception) as exc:
                    record(conn, app_id, "error", fam, str(exc)[:180])
                    totals["error"] += 1
                    log.error("[%d/%d] %-28s %s: %s", i, len(todo), ref, fam,
                              str(exc)[:70])
                    continue
                got = s.get("downloaded", 0)
                if s.get("errors") and not got:
                    strikes[host] += 1
                else:
                    strikes[host] = 0
                # An application is only finished when everything the
                # register listed actually arrived. Recording a short
                # fetch as done is the same silent failure as recording a
                # blocked page as "no documents": the queue empties, the
                # site looks covered, and a third of its evidence is
                # missing with nothing saying so. Halton rate-limiting
                # mid-application is exactly how this happens.
                listed = s.get("links_found") or 0
                held = got + (s.get("skipped_existing") or 0)
                outcome, detail = classify_outcome(s)
                record(conn, app_id, outcome, fam, detail, got)
                totals[outcome] = totals.get(outcome, 0) + 1
                if outcome in ("fetched", "partial"):
                    totals["documents"] += got
                if outcome == "partial":
                    log.warning("[%d/%d] %-28s PARTIAL %d of %d listed",
                                i, len(todo), ref, held, listed)
                log.info("[%d/%d] %-28s %-10s found=%d new=%d | docs %d in %.0fm",
                         i, len(todo), ref, fam, s.get("links_found", 0), got,
                         totals["documents"], (time.monotonic() - started) / 60)
    finally:
        for c in clients.values():
            try: c.close()
            except Exception: pass

    log.info("done: %(fetched)d fetched (%(documents)d documents), "
             "%(partial)d partial and still queued, "
             "%(none_published)d hold nothing, %(error)d errors, "
             "%(no_adapter)d recorded as unreadable", totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
