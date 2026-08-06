"""Fetch portal copies for applications whose only documents were ingested by hand.

The acquisition campaign's cohort is "DC-verdict applications with zero
documents", which silently excluded every application an operator had
already supplied manually — the hand-ingested files were protecting
their own applications from ever being visited by an adapter. Those
applications' documents therefore carry `file://` provenance URIs and
appear linkless in exports.

This pass visits them on whatever portal family they belong to. Where
the portal serves the same bytes, `record_document` upserts the row and
the `file://` URI is replaced by the real portal URL (the manual working
copy on disk is untouched — principle 3). Where the portal serves
different documents, both sets are kept: manual hauls routinely include
documents the portal no longer lists, and portal hauls include documents
the operator did not take.

Applications on portal families we cannot reach (Northgate, NEC, most
bespoke) keep their `file://` provenance permanently; those are reported
so exports can label them "manually obtained" rather than leaving a
reader to infer a gap.

Usage:
    .venv/bin/python -u scripts/fetch_manual_holders.py [--delay 4]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fetch_dc_campaign import portal_family  # noqa: E402

from dcp import db, repo  # noqa: E402
from dcp.sources import agile, arcus, idox, ocella  # noqa: E402

REACHABLE = ("idox", "ocella", "agile", "arcus")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT a.id, a.application_ref, a.url
                FROM documents d JOIN applications a ON a.id = d.application_id
                WHERE d.url LIKE 'file://%'
                ORDER BY a.application_ref""")
            rows = cur.fetchall()

        targets, unreachable = [], []
        for app_id, ref, url in rows:
            fam = portal_family(url)
            (targets if fam in REACHABLE else unreachable).append((app_id, ref, url, fam))

        print(f"{len(rows)} applications hold hand-ingested documents; "
              f"{len(targets)} reachable by adapter, {len(unreachable)} not")

        sources = {
            "idox": repo.ensure_source(conn, name="idox", kind="council",
                                       base_url="(per-council Idox host)"),
            "ocella": repo.ensure_source(conn, name="ocella", kind="council",
                                         base_url="(per-council Ocella host)"),
            "agile": repo.ensure_source(conn, name=agile.SOURCE_NAME, kind="council",
                                        base_url="planning.agileapplications.co.uk"),
            "arcus": repo.ensure_source(conn, name=arcus.SOURCE_NAME, kind="council",
                                        base_url="(per-council Arcus register)"),
        }
        clients = {
            "idox": idox.IdoxClient(delay_seconds=args.delay),
            "ocella": ocella.OcellaClient(delay_seconds=args.delay),
            "agile": agile.AgileClient(delay_seconds=args.delay),
            "arcus": arcus.ArcusClient(delay_seconds=args.delay),
        }
        fetchers = {
            "idox": idox.fetch_documents_for_application,
            "ocella": ocella.fetch_documents_for_application,
            "agile": agile.fetch_documents_for_application,
            "arcus": arcus.fetch_documents_for_application,
        }
        try:
            for app_id, ref, url, fam in targets:
                s = fetchers[fam](
                    conn, client=clients[fam], application_id=app_id,
                    application_ref=ref, application_url=url,
                    source_id=sources[fam], data_dir=args.data_dir)
                print(f"  {ref:38} [{fam:6}] links={s['links_found']:3d} "
                      f"new={s['downloaded']:3d} {s.get('error_class') or ''}")
        finally:
            for c in clients.values():
                c.close()

    if unreachable:
        print("\nManual-only, no adapter available (label these in exports):")
        for _id, ref, _u, fam in unreachable:
            print(f"  {ref:38} [{fam}]")


if __name__ == "__main__":
    main()
