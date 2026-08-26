#!/usr/bin/env python3
"""Re-list the corpus and measure what each fetch missed.

ROADMAP phase 2, "Re-list the corpus to find historical partial
fetches": a short fetch used to be recorded as complete, and the
manifests cannot show it because they record what was stored, not what
was offered. Per-site document counts are on every reader site page, so
this runs before anyone quotes one.

**Measurement only.** Nothing here downloads a document. Each pass
obtains a listing, compares it to the `documents` rows, and appends a row
to `document_listing_audit` (migration 026). The output is a prioritised
refetch list for a human to act on.

Three passes, cheapest first:

    scripts/relist_audit.py --pass snapshot   # free: listings we already hold
    scripts/relist_audit.py --pass harvest    # free: browser-harvested listings
    scripts/relist_audit.py --pass live       # re-lists; touches council portals

`--pass live` is resumable: an application already audited from a live
listing is skipped unless `--recheck` is given, so an interrupted sweep
continues where it stopped. It is also budgeted — `--limit`,
`--time-budget` — because 1,694 applications at a polite spacing is
several hours, and stopping early costs nothing but progress.

Politeness is the adapters' own: one client per host, adaptive spacing
that widens permanently on a 429, and a strike count that abandons a host
rather than grinding at it. `--delay` defaults to 10s, wider than the
document campaign's 4s, because this sweep has no deadline. Hosts known
to refuse automated access (Coventry's AWS WAF) are skipped by name and
the skip is recorded — an unmeasured application must not read as a
measured zero.

    scripts/relist_audit.py --report          # what the audit found so far

`--population` chooses what is being asked. The default, `holding`,
audits applications that hold documents: a shortfall there is a fetch
that stopped short. `none-published` audits applications settled as
registers that publish nothing — they hold no documents, so the default
population's join to `documents` cannot see them, and until this flag
existed the audit was structurally incapable of noticing that one of
them had a register full of documents. A shortfall there is not a short
fetch but a verdict that was never earned.

    scripts/relist_audit.py --population none-published --pass snapshot
    scripts/relist_audit.py --population none-published --pass live
    scripts/relist_audit.py --population none-published --report

The two populations are reported separately and their totals must not be
added together; they are answers to different questions.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, relist_audit, repo  # noqa: E402
from dcp.sources import agile, arcus, idox, ocella, salesforce_pr  # noqa: E402

log = logging.getLogger("relist_audit")

# Applications that hold at least one document — the population the
# roadmap names. An application holding none is already the queue that
# `fetch_outstanding.py` works from; this is about the ones we believe
# are done.
POPULATION_SQL = """
SELECT a.id, a.application_ref, a.url, count(d.id) AS held,
       EXISTS (SELECT 1 FROM site_members m
               WHERE m.application_id = a.id AND m.retired_at IS NULL)
           AS in_universe
FROM applications a
JOIN documents d ON d.application_id = a.id
WHERE a.url IS NOT NULL
GROUP BY a.id, a.application_ref, a.url
ORDER BY a.application_ref
"""

# Applications settled `none_published` — recorded as registers that
# publish nothing, and therefore out of the outstanding queue for good.
#
# They hold no documents, which is precisely why the population above
# cannot see them: it joins `documents`, so the audit that exists to
# catch a fetch which stopped short has been structurally blind to the
# fetches that stopped at zero. `dcp.acquisition_outcome` now refuses to
# award the verdict on a run that failed or retrieved nothing, but the
# rows written before it existed were awarded by a mapping that read only
# `error_class` and never the per-document error count beside it. A
# register that listed five documents and failed on all five could be
# recorded as a register that holds none.
#
# Auditing them asks the one question that settles it: does the register
# offer documents? An offer against a settled `none_published` is the
# defect realised. Measurement only — no verdict here is rewritten.
SETTLED_EMPTY_SQL = """
SELECT a.id, a.application_ref, a.url,
       (SELECT count(*) FROM documents d WHERE d.application_id = a.id) AS held,
       EXISTS (SELECT 1 FROM site_members m
               WHERE m.application_id = a.id AND m.retired_at IS NULL)
           AS in_universe
FROM applications a
-- Insertion order, not checked_at — the ordering fetch_outstanding.py
-- and document_listing_audit_current both use, so "settled" means the
-- same thing in all three places.
JOIN LATERAL (
    SELECT outcome FROM acquisition_outcome ao
    WHERE ao.application_id = a.id ORDER BY ao.id DESC LIMIT 1) o ON true
WHERE a.url IS NOT NULL AND o.outcome = 'none_published'
ORDER BY a.application_ref
"""

POPULATIONS = {"holding": POPULATION_SQL, "none-published": SETTLED_EMPTY_SQL}

POPULATION_LABEL = {
    "holding": "applications holding documents",
    "none-published": "applications settled `none_published`",
}


def _campaign():
    """`portal_family` from the campaign runner, for labelling the
    portals this module has no listing path for. Imported the way
    fetch_outstanding.py does it — the campaign is a script, not a
    package module."""
    spec = importlib.util.spec_from_file_location(
        "dc_campaign", Path(__file__).parent / "fetch_dc_campaign.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _population(conn, *, universe_only: bool,
                which: str = "holding") -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(POPULATIONS[which])
        rows = [{"id": r[0], "ref": r[1], "url": r[2], "held": r[3],
                 "in_universe": r[4]} for r in cur.fetchall()]
    return [r for r in rows if r["in_universe"]] if universe_only else rows


def _by_host(apps: list[dict], hosts: list[str]) -> list[dict]:
    """Scope a pass to named portal hosts — for re-measuring one council
    after its adapter is corrected, without re-listing the rest."""
    if not hosts:
        return apps
    wanted = {h.lower() for h in hosts}
    return [a for a in apps
            if (urlparse(a["url"]).hostname or "").lower() in wanted]


def _already(conn, source: str) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT application_id FROM document_listing_audit "
            "WHERE listing_source = %s", (source,))
        return {r[0] for r in cur.fetchall()}


def _compared(conn) -> set[int]:
    """Applications for which some listing has already been compared,
    whatever its source. The free passes cover most of the corpus, so the
    live pass goes to the ones nothing has measured first — a portal
    request spent on an application already measured from its own stored
    listing buys much less than one spent on an unmeasured one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT application_id FROM document_listing_audit "
            "WHERE status IN ('audited', 'empty_listing')")
        return {r[0] for r in cur.fetchall()}


# --------------------------------------------------------------------
# Passes
# --------------------------------------------------------------------

def pass_snapshot(conn, apps: list[dict], *, recheck: bool) -> Counter:
    """Audit against listings already in `source_snapshots`. No traffic."""
    seen = set() if recheck else _already(conn, "snapshot")
    tally: Counter = Counter()
    for app in apps:
        if app["id"] in seen:
            tally["skipped_done"] += 1
            continue
        result = relist_audit.audit_from_snapshot(
            conn, application_id=app["id"], application_ref=app["ref"],
            url=app["url"])
        if result is None:
            tally["no_stored_listing"] += 1
            continue
        listing, comparison = result
        relist_audit.record(
            conn, application_id=app["id"],
            adapter=relist_audit.listing_family(app["url"]) or "none",
            listing=listing, comparison=comparison,
            tool="scripts/relist_audit.py --pass snapshot")
        tally[listing.status] += 1
        if comparison and comparison["missing_count"]:
            tally["with_shortfall"] += 1
            tally["documents_missing"] += comparison["missing_count"]
    return tally


def pass_harvest(conn, apps: list[dict], *, recheck: bool) -> Counter:
    """Audit Salesforce registers against their harvested listings."""
    listings = salesforce_pr.load_listings()
    seen = set() if recheck else _already(conn, "harvest")
    tally: Counter = Counter()
    for app in apps:
        if relist_audit.listing_family(app["url"]) != "salesforce_pr":
            continue
        if app["id"] in seen:
            tally["skipped_done"] += 1
            continue
        listing = relist_audit.listing_from_harvest(app["ref"], listings)
        comparison = (
            relist_audit.compare(
                listing, relist_audit.stored_urls(conn, app["id"]))
            if listing.status in ("audited", "empty_listing") else None)
        relist_audit.record(
            conn, application_id=app["id"], adapter="salesforce_pr",
            listing=listing, comparison=comparison,
            tool="scripts/relist_audit.py --pass harvest")
        tally[listing.status] += 1
        if comparison and comparison["missing_count"]:
            tally["with_shortfall"] += 1
            tally["documents_missing"] += comparison["missing_count"]
    return tally


HOST_STRIKES = 3


def pass_live(conn, apps: list[dict], *, args, camp) -> Counter:
    """Re-list live, one client per host, round-robin across hosts."""
    seen = set() if args.recheck else _already(conn, "live")
    compared = _compared(conn)
    tally: Counter = Counter()

    # Portals with no listing path, and hosts we do not touch, are
    # recorded once and leave the queue. Both are honest gaps; neither is
    # a measured zero.
    queue: dict[str, deque] = defaultdict(deque)
    later: dict[str, deque] = defaultdict(deque)
    for app in apps:
        if app["id"] in seen:
            tally["skipped_done"] += 1
            continue
        if args.only_unaudited and app["id"] in compared:
            tally["skipped_measured"] += 1
            continue
        reason = relist_audit.skip_reason(app["url"])
        if reason:
            if not args.dry_run:
                relist_audit.record(
                    conn, application_id=app["id"],
                    adapter=camp.portal_family(app["url"]),
                    listing=relist_audit.Listing(status="host_skipped",
                                                 detail=reason),
                    comparison=None,
                    tool="scripts/relist_audit.py --pass live")
            tally["host_skipped"] += 1
            continue
        family = relist_audit.listing_family(app["url"])
        if family is None:
            if not args.dry_run:
                relist_audit.record(
                    conn, application_id=app["id"],
                    adapter=camp.portal_family(app["url"]),
                    listing=relist_audit.Listing(
                        status="no_adapter",
                        detail=f"no listing-only path for "
                               f"{camp.portal_family(app['url'])}"),
                    comparison=None,
                    tool="scripts/relist_audit.py --pass live")
            tally["no_adapter"] += 1
            continue
        host = (urlparse(app["url"]).hostname or "").lower()
        (later if app["id"] in compared else queue)[host].append(
            (family, app))

    def _round_robin(shards: dict[str, deque]) -> list[tuple]:
        """Interleave hosts rather than marching alphabetically, so one
        slow council costs only its own applications (the reasoning is
        fetch_outstanding.py's, and so is the shape)."""
        out: list[tuple] = []
        queues = list(shards.values())
        while queues:
            for q in list(queues):
                if q:
                    out.append(q.popleft())
                if not q:
                    queues.remove(q)
        return out

    n_hosts = len(set(queue) | set(later))
    n_unmeasured = sum(len(q) for q in queue.values())
    todo = _round_robin(queue) + _round_robin(later)
    if args.limit:
        todo = todo[:args.limit]
    log.info("live pass: %d applications across %d hosts "
             "(%d never measured, first in the queue)",
             len(todo), n_hosts, n_unmeasured)
    if args.dry_run:
        for fam, n in Counter(f for f, _ in todo).most_common():
            log.info("   %-14s %4d", fam, n)
        return tally

    clients: dict[tuple, object] = {}

    def make(family):
        if family == "idox":
            return idox.IdoxClient(delay_seconds=args.delay,
                                   backoff_seconds=args.backoff,
                                   max_retries=args.max_retries)
        if family == "ocella":
            return ocella.OcellaClient(delay_seconds=args.delay,
                                       backoff_seconds=args.backoff,
                                       max_retries=args.max_retries)
        if family == "agile":
            return agile.AgileClient(delay_seconds=args.delay,
                                     max_retries=args.max_retries)
        if family == "arcus":
            return arcus.ArcusClient(delay_seconds=args.delay,
                                     max_retries=args.max_retries)
        # aifusion and salesforce_pr both speak through the Idox client.
        return idox.IdoxClient(delay_seconds=args.delay,
                               backoff_seconds=args.backoff,
                               max_retries=args.max_retries)

    def client_for(family, url):
        key = (family, (urlparse(url).hostname or "").lower())
        if key not in clients:
            clients[key] = make(family)
        return clients[key]

    source_ids: dict[str, int] = {}

    def source_id_for(family):
        if family not in source_ids:
            source_ids[family] = repo.ensure_source(
                conn, name=family, kind="council",
                base_url=f"(per-council {family} host)")
            conn.commit()
        return source_ids[family]

    strikes: Counter = Counter()
    started = time.monotonic()
    try:
        for i, (family, app) in enumerate(todo, 1):
            if args.time_budget and (time.monotonic() - started) > \
                    args.time_budget * 60:
                log.info("time budget reached at %d/%d; resume by re-running",
                         i, len(todo))
                break
            host = (urlparse(app["url"]).hostname or "").lower()
            if strikes[host] >= HOST_STRIKES:
                # A host that keeps refusing is skipped rather than
                # hammered. Recorded as an error, which is retryable — not
                # as a zero, which would be a lie about the register.
                relist_audit.record(
                    conn, application_id=app["id"], adapter=family,
                    listing=relist_audit.Listing(
                        status="error",
                        detail=f"skipped: {host} refused {HOST_STRIKES} "
                               f"times this run"),
                    comparison=None,
                    tool="scripts/relist_audit.py --pass live")
                tally["host_gave_up"] += 1
                continue
            listing = relist_audit.listing_live(
                conn, client=client_for(family, app["url"]),
                application_ref=app["ref"], url=app["url"], family=family,
                source_id=source_id_for(family)
                if family in ("idox", "ocella", "arcus") else None)
            if listing.status in ("error", "rate_limited"):
                strikes[host] += 1
            else:
                strikes[host] = 0
            comparison = (
                relist_audit.compare(
                    listing, relist_audit.stored_urls(conn, app["id"]))
                if listing.status in ("audited", "empty_listing") else None)
            relist_audit.record(
                conn, application_id=app["id"], adapter=family,
                listing=listing, comparison=comparison,
                tool="scripts/relist_audit.py --pass live")
            tally[listing.status] += 1
            short = comparison["missing_count"] if comparison else 0
            if short:
                tally["with_shortfall"] += 1
                tally["documents_missing"] += short
            log.info("[%d/%d] %-30s %-8s %-14s offered=%s held=%s missing=%s",
                     i, len(todo), app["ref"][:30], family, listing.status,
                     comparison["offered_count"] if comparison else "-",
                     app["held"], short or "-")
    finally:
        for c in clients.values():
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
    return tally


# --------------------------------------------------------------------
# Report
# --------------------------------------------------------------------

LATEST_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (application_id) *
    FROM document_listing_audit
    ORDER BY application_id, id DESC
)
SELECT l.application_id, a.application_ref, a.url, l.adapter,
       l.listing_source, l.listing_url, l.listing_captured_at, l.status,
       l.detail,
       l.offered_count, l.stored_count, l.matched_count, l.missing_count,
       l.unmatched_stored_count, l.offered, l.missing,
       s.site_key, s.display_name
FROM latest l
JOIN applications a ON a.id = l.application_id
-- LATERAL rather than a plain join: an application can sit in more than
-- one live site, and counting its shortfall twice would inflate exactly
-- the number this is meant to protect.
LEFT JOIN LATERAL (
    SELECT s.site_key, s.display_name
    FROM site_members m
    JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
    WHERE m.application_id = l.application_id AND m.retired_at IS NULL
    ORDER BY s.id LIMIT 1) s ON true
"""


def _latest(conn, *, only: set[int] | None = None) -> list[dict]:
    """The current audit per application, with its shortfall split into
    filed-elsewhere, duplicate-listing and genuinely-absent.

    The split is derived on read rather than stored: the offered and
    missing sets are the measurement and they are kept verbatim, so a
    better rule for reading them costs a re-read and not a re-list.

    `only` restricts the rows to one population. The two populations
    answer different questions and their numbers must not be added up
    together: a shortfall against an application holding documents is a
    fetch that stopped short, and a shortfall against one settled
    `none_published` is a register we recorded as empty that is not.
    """
    with conn.cursor() as cur:
        cur.execute(LATEST_SQL)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if only is not None:
            rows = [r for r in rows if r["application_id"] in only]
        cur.execute("SELECT application_id, url FROM documents")
        held_by_app: dict[int, set[str]] = defaultdict(set)
        held_anywhere: set[str] = set()
        for app_id, url in cur.fetchall():
            if url:
                held_by_app[app_id].add(url)
                held_anywhere.add(url)
    for r in rows:
        split = relist_audit.classify_missing(
            r["offered"] or [], r["missing"] or [],
            held_by_app[r["application_id"]], held_anywhere)
        r["split"] = split
        r["absent"] = split[relist_audit.ABSENT]
        r["absent_count"] = len(r["absent"])
        r["elsewhere_count"] = len(split[relist_audit.FILED_ELSEWHERE])
        r["duplicate_count"] = len(split[relist_audit.DUPLICATE_LISTING])
    return rows


def _snapshot_status(conn, ids: set[int]) -> dict[int, str]:
    """How the page the fetch itself stored reads, per application.

    Kept beside the latest reading because they answer different halves
    of the question. A live re-list says what the register offers *now*,
    which a register may have grown into since; the snapshot is the very
    body the fetch parsed before it awarded its verdict, so `blocked`
    there means the verdict was unearned when it was written.
    """
    if not ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (application_id) application_id, status
            FROM document_listing_audit
            WHERE listing_source = 'snapshot' AND application_id = ANY(%s)
            ORDER BY application_id, id DESC
            """,
            (list(ids),))
        return dict(cur.fetchall())


def _settled_verdict(rows: list[dict], ids: set[int],
                     snapshot_status: dict[int, str]) -> None:
    """The only three things a settled `none_published` can turn out to be.

    Printed apart from the shortfall arithmetic because the question is
    different: not "how much did this fetch miss" but "was this
    application entitled to leave the queue at all". The third bucket is
    the one that has to stay visible — an application nobody could
    re-list is unmeasured, and reading it as a confirmed empty register
    is the very substitution that produced the defect.
    """
    offers = sorted((r for r in rows if (r["offered_count"] or 0) > 0),
                    key=lambda r: -(r["offered_count"] or 0))
    empty = [r for r in rows if r["status"] == "empty_listing"]
    withdrawn = [r for r in rows if r["status"] == "withdrawn"]
    measured = {r["application_id"] for r in rows
                if r["status"] in ("audited", "empty_listing", "withdrawn")}
    print()
    print("=== settled `none_published`: was the verdict earned? ===")
    print(f"  register OFFERS documents (defect realised) {len(offers):>5}   "
          f"{sum(r['offered_count'] or 0 for r in offers)} documents offered "
          "and none held")
    print(f"  register confirmed empty                    {len(empty):>5}")
    print(f"  register reports the application withdrawn  {len(withdrawn):>5}"
          "   (a fact about the register, not a fetch failure)")
    print(f"  NOT MEASURED                                "
          f"{len(ids - measured):>5}   (see the reasons below; not a "
          "confirmed empty register)")
    unmeasured = Counter(
        f"{r['status']}: {(r['detail'] or '')[:60]}"
        for r in rows if r["application_id"] not in measured)
    for reason, n in unmeasured.most_common():
        print(f"      {n:4d}  {reason}")
    never = len(ids - {r["application_id"] for r in rows})
    if never:
        print(f"      {never:4d}  no audit row at all — the sweep has not "
              "reached these yet")
    if offers:
        print()
        print("  applications whose register offers documents. `fetch read` "
              "is what the page the\n  fetch itself stored says: `blocked` "
              "means the verdict was unearned when it was\n  written, "
              "whatever the register has published since.")
        for r in offers:
            host = (urlparse(r["url"] or "").hostname or "?")
            print(f"    [fetch read: {snapshot_status.get(r['application_id'], 'none'):>14s}] ", end="")
            print(f"    {r['offered_count']:5d} offered  "
                  f"{r['application_ref']:32s} {host:38s} "
                  f"{r['site_key'] or '-'}")


def report(conn, *, top: int = 25, which: str = "holding") -> None:
    ids = {a["id"] for a in _population(conn, universe_only=False,
                                        which=which)}
    rows = _latest(conn, only=ids)
    population = len(ids)

    by_status = Counter(r["status"] for r in rows)
    audited = [r for r in rows
               if r["status"] in ("audited", "empty_listing")]
    short = [r for r in audited if r["absent_count"]]

    def total(key):
        return sum(r[key] or 0 for r in audited)

    print(f"population ({POPULATION_LABEL[which]})  {population:>6}")
    print(f"  measured against a listing                 {len(audited):>6}")
    print(f"  still unmeasured                           "
          f"{population - len(audited):>6}")
    print(f"  audit rows by status: {dict(by_status.most_common())}")
    print(f"  by listing source:    "
          f"{dict(Counter(r['listing_source'] for r in rows).most_common())}")
    if which == "none-published":
        _settled_verdict(rows, ids, _snapshot_status(conn, ids))
    print()
    print(f"offered by the registers    {total('offered_count'):>7}")
    print(f"held for those applications {total('stored_count'):>7}")
    print(f"matched by URL              {total('matched_count'):>7}")
    print(f"short on this application   {total('missing_count'):>7}   across "
          f"{sum(1 for r in audited if r['missing_count']):>4} applications")
    print(f"  less: held under a twin application "
          f"{total('elsewhere_count'):>7}")
    print(f"  less: the register listed the same file twice "
          f"{total('duplicate_count'):>7}")
    print(f"ABSENT FROM THE CORPUS      {total('absent_count'):>7}   across "
          f"{len(short):>4} applications")
    print(f"held but not offered        "
          f"{total('unmatched_stored_count'):>7}   "
          "(withdrawn, re-published, or a changed URL scheme)")
    empty_but_held = [r for r in audited
                      if not r["offered_count"] and (r["stored_count"] or 0)]
    if empty_but_held:
        print(f"listing empty yet documents held   {len(empty_but_held):>4}   "
              "applications — the listing path is not where these came "
              "from (a separate docstore, or a manual harvest whose "
              "documents carry file:// URLs no listing can match)")
    print()
    buckets = Counter()
    for r in short:
        m = r["absent_count"]
        buckets["1" if m == 1 else "2-5" if m <= 5 else "6-20" if m <= 20
                else "21-100" if m <= 100 else "100+"] += 1
    print("shortfall distribution (documents absent from the corpus):",
          {k: buckets[k] for k in ("1", "2-5", "6-20", "21-100", "100+")
           if buckets[k]})
    print()
    print("worst applications:")
    for r in sorted(short, key=lambda r: -r["absent_count"])[:top]:
        print(f"  {r['absent_count']:5d} absent of {r['offered_count']:5d} "
              f"offered  {r['application_ref']:34s} {r['adapter']:16s} "
              f"{r['site_key'] or '-'}")
    print()
    per_site: dict[str, list] = defaultdict(lambda: [0, 0, 0, None])
    for r in short:
        key = r["site_key"] or "(no site)"
        per_site[key][0] += r["absent_count"]
        per_site[key][1] += r["offered_count"] or 0
        per_site[key][2] += 1
        per_site[key][3] = r["display_name"]
    print("worst sites — per-site document counts are the reporter-facing "
          "number at risk:")
    for key, (absent, offered, n, name) in sorted(
            per_site.items(), key=lambda kv: -kv[1][0])[:top]:
        print(f"  {absent:5d} absent of {offered:5d} offered, {n:3d} apps  "
              f"{key:18s} {(name or '')[:50]}")

    # The register's own document-type label, which is what a refetch
    # pass would triage on: the corpus samples the repetitive drawing
    # classes at one in five by policy, so a shortfall made of drawings
    # costs the reading far less than one made of statements.
    kinds = Counter()
    for r in short:
        for d in r["absent"]:
            kinds[(d.get("kind") or "(unlabelled)").strip().lower()] += 1
    print()
    print("absent documents by the register's own document type:")
    for kind, n in kinds.most_common(12):
        print(f"  {n:5d}  {kind[:60]}")


def write_refetch_list(conn, path: Path, *, which: str = "holding") -> int:
    """The measurement's output: every offered document the corpus does
    not hold, with the listing that named it.

    Deliberately a file for a human to read and act on rather than a
    queue something drains automatically. A refetch pass re-visits
    council portals at scale, and which of these are worth the traffic is
    an editorial decision — a Glasgow university masterplan and a
    Northumberland data-centre application both appear here, and only one
    of them is the investigation. Sorted by the site the shortfall
    belongs to, then by its size, so that decision can be taken a site at
    a time.
    """
    import csv
    ids = {a["id"] for a in _population(conn, universe_only=False,
                                        which=which)}
    rows = [r for r in _latest(conn, only=ids) if r["absent_count"]]
    site_weight = defaultdict(int)
    for r in rows:
        site_weight[r["site_key"] or ""] += r["absent_count"]
    rows.sort(key=lambda r: (-site_weight[r["site_key"] or ""],
                             r["site_key"] or "", -r["absent_count"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["site_key", "site_name", "application_ref",
                    "application_url", "adapter", "listing_source",
                    "listing_url", "listing_captured_at", "offered_count",
                    "stored_count", "absent_count", "document_url",
                    "filename", "kind"])
        for r in rows:
            for d in r["absent"]:
                w.writerow([
                    r["site_key"], r["display_name"], r["application_ref"],
                    r["url"], r["adapter"], r["listing_source"],
                    r["listing_url"], r["listing_captured_at"],
                    r["offered_count"], r["stored_count"], r["absent_count"],
                    d.get("url"), d.get("filename"), d.get("kind")])
                n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pass", dest="which",
                   choices=["snapshot", "harvest", "live"], default=None)
    p.add_argument("--report", action="store_true")
    p.add_argument("--refetch-list", type=Path, default=None,
                   metavar="PATH",
                   help="write the prioritised refetch list (one row per "
                        "offered document the corpus does not hold) to CSV")
    p.add_argument("--population", choices=sorted(POPULATIONS),
                   default="holding",
                   help="which applications to audit: 'holding' (the "
                        "default — applications holding documents, where a "
                        "shortfall means a fetch stopped short) or "
                        "'none-published' (applications settled as registers "
                        "that publish nothing, where an offer means the "
                        "verdict was never earned)")
    p.add_argument("--universe-only", action="store_true",
                   help="restrict to applications in a live site")
    p.add_argument("--recheck", action="store_true",
                   help="re-audit applications already audited this way")
    p.add_argument("--only-unaudited", action="store_true",
                   help="live pass: stop after the applications no listing "
                        "has measured, rather than continuing into the ones "
                        "already measured from a stored listing")
    p.add_argument("--host", action="append", default=[],
                   help="scope the pass to this portal host (repeatable)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--time-budget", type=float, default=None,
                   help="minutes; the live pass stops cleanly and resumes "
                        "on the next run")
    p.add_argument("--delay", type=float, default=10.0,
                   help="inter-request spacing per host (default 10s)")
    p.add_argument("--backoff", type=float, default=30.0)
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with db.connect() as conn:
        if args.refetch_list:
            n = write_refetch_list(conn, args.refetch_list,
                                   which=args.population)
            log.info("refetch list: %d documents -> %s", n, args.refetch_list)
            if not args.which:
                return 0
        if args.report or args.which is None:
            report(conn, which=args.population)
            return 0
        apps = _by_host(_population(conn, universe_only=args.universe_only,
                                    which=args.population),
                        args.host)
        log.info("population: %d %s", len(apps),
                 POPULATION_LABEL[args.population])
        if args.which == "snapshot":
            tally = pass_snapshot(conn, apps, recheck=args.recheck)
        elif args.which == "harvest":
            tally = pass_harvest(conn, apps, recheck=args.recheck)
        else:
            tally = pass_live(conn, apps, args=args, camp=_campaign())
    log.info("done: %s", dict(tally.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
