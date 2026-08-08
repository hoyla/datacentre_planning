#!/usr/bin/env python3
"""Test whether failing portals are rejecting our user-agent, not us.

Runnymede answers 403 to

    datacentre_planning research (luke.hoyland@gmail.com)

and 200 to

    Mozilla/5.0 (compatible; datacentre_planning research; +mailto:...)

Same identity, same contact address, same request — the difference is the
`Mozilla/5.0 (compatible; ...)` envelope that a good many WAFs and CDN
rules require before they will serve anything. That is the long-standing
convention for identified crawlers (Googlebot and Bingbot both use it),
so it is a formatting fix rather than a disguise: nothing here pretends
to be a browser, and the mailto stays in the string.

If that is what has been happening elsewhere, some of the applications
currently filed as "no adapter" or "portal blocked" need no new code at
all. This probes one sample page per host with each user-agent and
reports where the answers differ.

Read-only: it fetches one page per user-agent per host, never documents,
and spaces requests politely. Nothing is written to the database — the
output is a report for a human to act on.

    scripts/probe_user_agents.py
    scripts/probe_user_agents.py --out data/exports/ua_probe.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db  # noqa: E402
from dcp.sources import idox  # noqa: E402

log = logging.getLogger("ua_probe")

PLAIN = "datacentre_planning research (luke.hoyland@gmail.com)"
COMPATIBLE = ("Mozilla/5.0 (compatible; datacentre_planning research; "
              "+mailto:luke.hoyland@gmail.com)")

# Applications we hold no documents for, with one sample URL per host.
# Restricted to site members: hosts outside the site universe are not
# what this is trying to unblock.
SAMPLES_SQL = """
SELECT a.url, a.application_ref
FROM applications a
WHERE a.url IS NOT NULL
  AND a.url LIKE 'http%%'
  AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id)
  AND EXISTS (SELECT 1 FROM site_members m
              WHERE m.application_id = a.id AND m.retired_at IS NULL)
"""


def classify(plain: dict, compat: dict) -> str:
    """What the pair of responses means, in plain terms."""
    ps, cs = plain.get("status"), compat.get("status")
    if ps is None and cs is None:
        return "both failed to connect"
    if ps == cs and plain.get("bytes") and compat.get("bytes"):
        near = abs(plain["bytes"] - compat["bytes"]) < max(200, plain["bytes"] * 0.02)
        return "no difference" if near else "same status, different body"
    if (ps is None or ps >= 400) and cs is not None and cs < 400:
        return "UNBLOCKED by compatible UA"
    if (cs is None or cs >= 400) and ps is not None and ps < 400:
        return "plain UA works, compatible blocked"
    return f"differs ({ps} vs {cs})"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path,
                   default=Path("data/exports/ua_probe.json"))
    p.add_argument("--delay", type=float, default=3.0,
                   help="seconds between requests to the same host")
    p.add_argument("--timeout", type=float, default=45.0)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(SAMPLES_SQL)
        rows = cur.fetchall()
    by_host: dict[str, tuple[str, str]] = {}
    counts: dict[str, int] = defaultdict(int)
    for url, ref in rows:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            continue
        counts[host] += 1
        by_host.setdefault(host, (url, ref))
    log.info("%d documentless applications across %d hosts",
             len(rows), len(by_host))

    verify = idox._resolve_ssl_context()
    results = []
    for i, (host, (url, ref)) in enumerate(
            sorted(by_host.items(), key=lambda kv: -counts[kv[0]]), 1):
        pair = {}
        for label, ua in (("plain", PLAIN), ("compatible", COMPATIBLE)):
            try:
                with httpx.Client(headers={"User-Agent": ua}, timeout=args.timeout,
                                  follow_redirects=True, verify=verify) as cl:
                    r = cl.get(url)
                pair[label] = {"status": r.status_code, "bytes": len(r.content)}
            except Exception as exc:
                pair[label] = {"status": None,
                               "error": f"{type(exc).__name__}: {exc}"[:90]}
            time.sleep(args.delay)
        verdict = classify(pair["plain"], pair["compatible"])
        results.append({"host": host, "applications": counts[host],
                        "sample_ref": ref, "sample_url": url,
                        "plain": pair["plain"], "compatible": pair["compatible"],
                        "verdict": verdict})
        log.info("[%d/%d] %-44s %4d apps  %s", i, len(by_host), host[:44],
                 counts[host], verdict)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1) + "\n")

    unlocked = [r for r in results if r["verdict"].startswith("UNBLOCKED")]
    log.info("=" * 66)
    log.info("hosts probed: %d   applications behind them: %d",
             len(results), sum(r["applications"] for r in results))
    if unlocked:
        log.info("UNBLOCKED by the compatible user-agent: %d hosts, %d applications",
                 len(unlocked), sum(r["applications"] for r in unlocked))
        for r in sorted(unlocked, key=lambda r: -r["applications"]):
            log.info("   %-44s %4d applications", r["host"][:44], r["applications"])
    else:
        log.info("no host was unblocked by the user-agent change")
    log.info("report written to %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
