"""Acquisition campaign: document fetch for every DC-verdict application
without documents, across the portals we have adapters for.

The cohort is the agreed campaign definition (2026-08-03): applications
whose LATEST triage verdict is 'DC' and which have no rows in `documents`.
Of the 606 such applications, ~400 sit on Idox or Ocella portals and are
fetchable today; the rest are counted per portal family in the closing
report (Agile → Arcus → Salesforce/Northgate/NEC is the agreed adapter
order, bespoke handled manually by site value).

Built to survive interruption (the operator is travelling):

- **Frozen cohort.** The fetchable cohort is computed once and persisted
  to `data/raw/_dc_campaign_state.json`; relaunches load it from there.
  Without this, an application interrupted mid-fetch (some documents
  already recorded) would vanish from a recomputed zero-documents cohort
  and never be completed.
- **Per-application progress.** Each cleanly-finished application is
  recorded in the state file as it completes; relaunches skip straight
  past them. Applications that ended with errors stay eligible and are
  re-walked (cheap: content-hash dedup + the adapter's URL-level skip
  mean only missing bytes are downloaded).
- **Offline-aware.** A DNS/connect/timeout failure triggers a
  connectivity probe (DNS resolution of a stable public host). While
  offline the campaign WAITS — printing a heartbeat, not burning the
  cohort as spurious SKIPs — and retries the same application once
  connectivity returns (3 attempts before a genuine SKIP, which is what
  a defunct portal produces).
- If the process itself is killed (laptop sleep, session teardown),
  relaunching the same command resumes from the state file in seconds.

Parallel across portals, strictly serial within each: applications are
sharded by portal *hostname* (not council — a few councils share a
host) and a small worker pool (--workers, default 6) runs one shard at
a time each, every worker holding its own clients and database
connection. Politeness is a per-host property — the delay, the backoff
ladders, and the one-request-in-flight rule are unchanged from any
individual portal's point of view; a Newham backoff no longer idles
Norwich.

Writes a campaign manifest to `data/raw/_dc_campaign_<date>.json` at the
end: cohort, per-application results, per-family needs-adapter lists —
the completeness accounting the data team's coverage statement draws on.

Usage:
    .venv/bin/python -u scripts/fetch_dc_campaign.py [--delay 5] [--limit N] [--dry-run]
    # relaunch after any interruption: same command, resumes automatically
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox, ocella  # noqa: E402


STATE_PATH = Path("data/raw/_dc_campaign_state.json")

# Error classes that mean "the network (or the laptop) is the problem, not
# the portal" — these trigger the offline wait-and-retry path rather than
# a SKIP.
NETWORK_ERROR_CLASSES = {"dns_failure", "connect_failure", "timeout"}


def _online() -> bool:
    """Cheap connectivity probe: DNS resolution of a stable public host.
    Resolution needs no HTTP round-trip and fails fast when offline."""
    import socket
    try:
        socket.getaddrinfo("www.gov.uk", 443)
        return True
    except OSError:
        return False


def _wait_for_connectivity() -> None:
    """Block until DNS resolution works again, with a once-a-minute
    heartbeat so the log shows the campaign is waiting, not wedged."""
    import time
    waited = 0
    while not _online():
        if waited % 300 == 0:
            print(f"  … offline; waiting for connectivity "
                  f"({waited // 60} min so far)")
        time.sleep(60)
        waited += 60
    if waited:
        print(f"  … back online after {waited // 60} min; resuming")


def _load_state() -> dict | None:
    """Return the persisted campaign state, or None if no campaign is in
    progress. A state file marked finished belongs to a completed campaign;
    a new run then starts fresh with a recomputed cohort."""
    if not STATE_PATH.exists():
        return None
    state = json.loads(STATE_PATH.read_text())
    return None if state.get("finished") else state


def _save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(STATE_PATH)


def portal_family(url: str | None) -> str:
    if not url:
        return "no_url"
    u = url.lower()
    if idox._is_idox_url(url):
        return "idox"
    if "/ocellaweb/planningdetails" in u:
        return "ocella"
    if "agileapplications.co.uk" in u:
        return "agile"
    # Northern Ireland's portal is on a planningregister.* host and is not
    # Arcus: it is a Next.js application whose documents come from an API,
    # not from links in the page. Matching the hostname sent the Arcus
    # adapter at seven NI applications, which failed with 'not_arcus_url'
    # — honest, but it cost a retry each sweep and hid a real coverage
    # gap behind an adapter error.
    if "planningsystemni.gov.uk" in u:
        return "ni_planning"
    if "planningregister." in u or "/planning/display/" in u:
        return "arcus"
    # Match the product, not the hostname. "planningexplorer" in a host
    # name proves nothing: Barnsley runs a bespoke MVC app at
    # planningexplorer.barnsley.gov.uk and Charnwood an NEC Assure install
    # at planningexplorer.charnwood.gov.uk. Counting both as Northgate
    # made the outstanding-work breakdown report a family of nine where
    # there were really three products, and sent the wrong adapter after
    # them.
    if "/assure/" in u:
        return "nec"
    if ("stddetails.aspx" in u or "/northgate/planningexplorer/" in u
            or "/necsws/planningexplorer/" in u):
        return "northgate"
    # Salesforce Lightning communities, whose councils each pick their own
    # object path. Anglesey publishes /s/papplication/, Bracknell
    # /s/detail/; matching only the latter filed three Anglesey
    # applications as "no adapter for this portal type" when the adapter
    # handles them fine.
    if any(p in u for p in ("/s/detail/", "/s/papplication/",
                            "/s/planning-application/")):
        return "salesforce"
    if "lpassure" in u or "necsws" in u:
        return "nec"
    return "bespoke/other"


# Cohort, revised 2026-08-08. The original targeted the v1 rubric's 'DC'
# verdict, which was right when v1 was the only taxonomy. Since the
# dc_build sweep ran, that definition silently excludes most of the
# universe: 166 new-build data centres, 83 expansions and 48
# pre-applications had portal URLs and no documents simply because they
# carry a dc_build verdict rather than a v1 one.
#
# Rubrics are separate universes of judgement, so membership is the union:
# any dc_build verdict except not_dc, OR a v1 'DC'. NSIP energy records
# are excluded — they are an adjacency layer with no council portal to
# fetch from.
#
# Ordered by editorial value rather than alphabetically. The cohort is
# frozen at first run and worked through in order, so an interruption
# leaves the new-builds fetched and the condition discharges outstanding,
# rather than a random alphabetical slice of both. `procedural` is last
# but deliberately included: a discharge-of-conditions application is
# often where the substantive technical report finally appears (the
# wildlife management plan, the drainage strategy, the noise assessment),
# so the class is low priority, not low value.
COHORT_SQL = """
WITH latest_dc_build AS (
  SELECT DISTINCT ON (application_id) application_id, verdict
  FROM triage WHERE raw_response->>'rubric' = 'dc_build'
  ORDER BY application_id, inserted_at DESC),
latest_v1 AS (
  SELECT DISTINCT ON (application_id) application_id, verdict
  FROM triage WHERE coalesce(raw_response->>'rubric', 'v1') = 'v1'
  ORDER BY application_id, inserted_at DESC)
SELECT a.id, a.application_ref, a.url
FROM applications a
LEFT JOIN latest_dc_build b ON b.application_id = a.id
LEFT JOIN latest_v1 v ON v.application_id = a.id
WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id)
  AND (b.verdict IS NOT NULL AND b.verdict <> 'not_dc' OR v.verdict = 'DC')
  AND NOT (a.discovered_via @> ARRAY['nsip_energy'])
ORDER BY CASE coalesce(b.verdict, 'v1_dc')
           WHEN 'new_build' THEN 1
           WHEN 'expansion_refurb' THEN 2
           WHEN 'pre_application' THEN 3
           WHEN 'adjacent_power' THEN 4
           WHEN 'enabling_works' THEN 5
           WHEN 'v1_dc' THEN 6
           WHEN 'unknown' THEN 7
           ELSE 8
         END,
         a.application_ref
"""


def _run_shard(host: str, apps: list[tuple], *, args, state: dict,
               lock: threading.Lock, totals: dict, per_app: list,
               source_ids: dict) -> None:
    """Fetch one portal host's applications, strictly serially, with the
    worker's own clients and database connection. All shared-state
    mutation happens under the lock."""
    from dcp.sources import idox, ocella

    with db.connect() as conn:
        idox_client = idox.IdoxClient(
            delay_seconds=args.delay, max_retries=args.max_retries)
        ocella_client = ocella.OcellaClient(
            delay_seconds=args.delay, max_retries=args.max_retries)
        try:
            for app_id, ref, url in apps:
                with lock:
                    totals["apps"] += 1
                t0 = time.time()
                family = portal_family(url)

                def _fetch():
                    if family == "idox":
                        return idox.fetch_documents_for_application(
                            conn, client=idox_client, application_id=app_id,
                            application_ref=ref, application_url=url,
                            source_id=source_ids["idox"], data_dir=args.data_dir)
                    return ocella.fetch_documents_for_application(
                        conn, client=ocella_client, application_id=app_id,
                        application_ref=ref, application_url=url,
                        source_id=source_ids["ocella"], data_dir=args.data_dir)

                # Network-shaped failures get the offline wait-and-retry
                # treatment; only a failure WITH connectivity confirmed
                # counts as a genuine skip (defunct portal, etc.).
                for _attempt in range(3):
                    s = _fetch()
                    if s.get("error_class") not in NETWORK_ERROR_CLASSES:
                        break
                    print(f"  {ref:44} network failure "
                          f"[{s['error_class']}] — probing connectivity")
                    _wait_for_connectivity()

                cls = s.get("error_class")
                elapsed = time.time() - t0
                stamp = f"{dt.datetime.now():%H:%M:%S}"
                with lock:
                    totals["docs_downloaded"] += s.get("downloaded", 0)
                    totals["docs_existing"] += s.get("skipped_existing", 0)
                    totals["errors"] += s.get("errors", 0)
                    per_app.append({"ref": ref, "family": family, "summary": s})
                    if cls:
                        totals["by_error_class"][cls] = \
                            totals["by_error_class"].get(cls, 0) + 1
                        print(f"  {stamp}  {ref:44} SKIP[{cls}] ({elapsed:.0f}s)")
                    else:
                        totals["fully_successful"] += 1
                        print(f"  {stamp}  {ref:44} "
                              f"links={s.get('links_found', 0):3d} "
                              f"new={s.get('downloaded', 0):3d} ({elapsed:.0f}s)")
                    # Only cleanly-finished applications are recorded as
                    # done; anything with errors stays eligible for the
                    # next relaunch. Hard skips are reserved for the
                    # genuinely dead — never for rate limiting, which is
                    # a tonight problem, not a forever one.
                    if not cls and s.get("errors", 0) == 0:
                        state["completed_refs"].append(ref)
                        _save_state(state)
                    elif cls in ("withdrawn_from_view", "dns_failure",
                                 "persistent_5xx"):
                        state["hard_skips"][ref] = cls
                        _save_state(state)
                if cls == "rate_limited":
                    # This host is throttling us at page level — walking
                    # the rest of its shard would burn a ladder per
                    # application for nothing. Drop the shard; the
                    # applications stay un-completed for the next
                    # relaunch or the retry pass.
                    print(f"  … dropping remaining {host} applications "
                          f"this run (portal rate-limiting)")
                    break
        finally:
            idox_client.close()
            ocella_client.close()
        conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--max-retries", type=int, default=2,
                    help="Backoff-ladder length during the sweep (default 2: "
                         "~3 min worst-case per failing document). The sweep "
                         "is breadth-first; the retry pass is the patient "
                         "phase and uses the full ladder.")
    ap.add_argument("--workers", type=int, default=6,
                    help="Concurrent portal-host shards. Within a host, "
                         "fetching is always strictly serial.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the cohort by portal family and exit.")
    args = ap.parse_args()

    started_at = dt.datetime.now(dt.timezone.utc)

    state = _load_state()
    with db.connect() as conn:
        if state is None:
            # Fresh campaign: compute and freeze the cohort.
            with conn.cursor() as cur:
                cur.execute(COHORT_SQL)
                targets = cur.fetchall()
            state = {
                "started_at_utc": started_at.isoformat(timespec="seconds"),
                "cohort": [
                    {"id": id_, "ref": ref, "url": url}
                    for id_, ref, url in targets
                ],
                "completed_refs": [],
                "hard_skips": {},
                "finished": False,
            }
            resuming = False
        else:
            targets = [(t["id"], t["ref"], t["url"]) for t in state["cohort"]]
            resuming = True

        by_family: dict[str, list[str]] = {}
        for _id, ref, url in targets:
            by_family.setdefault(portal_family(url), []).append(ref)
        fetchable = [t for t in targets if portal_family(t[2]) in ("idox", "ocella")]
        state.setdefault("hard_skips", {})
        # Hard skips: portals proven dead (persistent 5xx, defunct DNS,
        # withdrawn applications). Re-probing them costs a full backoff
        # ladder per relaunch; they stay in the state file for the retry
        # pass to re-examine deliberately, and are not re-walked here.
        done = set(state["completed_refs"]) | set(state["hard_skips"])

        verb = "Resuming" if resuming else "Campaign cohort:"
        print(f"{verb} {len(targets)} DC-verdict applications without documents"
              + (f" ({len(state['completed_refs'])} completed, "
                 f"{len(state['hard_skips'])} known-dead skipped)"
                 if resuming else ""))
        for fam, refs in sorted(by_family.items(), key=lambda kv: -len(kv[1])):
            marker = "fetch now" if fam in ("idox", "ocella") else "needs adapter/manual"
            print(f"  {fam:15} {len(refs):4d}  [{marker}]")
        if args.dry_run:
            return
        if args.limit:
            fetchable = fetchable[: args.limit]
        if not resuming:
            _save_state(state)

        source_ids = {
            "idox": repo.ensure_source(
                conn, name="idox", kind="council",
                base_url="(per-council Idox host)"),
            "ocella": repo.ensure_source(
                conn, name="ocella", kind="council",
                base_url="(per-council Ocella host)"),
        }
        conn.commit()

    totals = {"apps": 0, "docs_downloaded": 0, "docs_existing": 0,
              "errors": 0, "by_error_class": {}, "fully_successful": 0}
    per_app: list[dict] = []
    lock = threading.Lock()

    # Shard by portal hostname: politeness (delay, ladders, one request
    # in flight) is a per-host property, so hosts may run concurrently
    # while each host's applications stay strictly serial.
    pending = [t for t in fetchable if t[1] not in done]
    shards: dict[str, list[tuple]] = {}
    for t in pending:
        host = urllib.parse.urlparse(t[2]).netloc
        shards.setdefault(host, []).append(t)
    # Longest shards first so the big queues start immediately.
    ordered = sorted(shards.items(), key=lambda kv: -len(kv[1]))
    print(f"  {len(pending)} applications across {len(shards)} portal hosts; "
          f"{args.workers} concurrent hosts")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(_run_shard, host, apps, args=args, state=state,
                        lock=lock, totals=totals, per_app=per_app,
                        source_ids=source_ids)
            for host, apps in ordered
        ]
        for f in futures:
            f.result()
        if not args.limit:
            # Natural end of the full campaign. Applications that ended
            # with errors keep their errored manifests — the retry pass
            # (scripts/retry_idox_errors.py pattern) is the follow-up, not
            # a fresh campaign cohort, since partially-fetched apps no
            # longer match the zero-documents cohort definition.
            state["finished"] = True
            _save_state(state)

    finished_at = dt.datetime.now(dt.timezone.utc)
    out_path = Path("data/raw") / f"_dc_campaign_{started_at.date().isoformat()}.json"
    out_path.write_text(json.dumps({
        "generated_at_utc": started_at.isoformat(timespec="seconds"),
        "finished_at_utc": finished_at.isoformat(timespec="seconds"),
        "cohort_definition": "latest triage verdict 'DC', zero documents rows",
        "cohort_size": len(targets),
        "by_portal_family": {f: sorted(r) for f, r in by_family.items()},
        "fetched_families": ["idox", "ocella"],
        "totals": totals,
        "apps": per_app,
    }, ensure_ascii=False, indent=2) + "\n")

    print(f"\nTotals: {totals}")
    print(f"Campaign manifest: {out_path}")
    needs = {f: len(r) for f, r in by_family.items() if f not in ("idox", "ocella")}
    if needs:
        print(f"Needs adapter/manual (not fetched this campaign): {needs}")


if __name__ == "__main__":
    main()
