"""An application whose last attempt ended in `error` stays queued even
when it holds documents.

A fetch that hits its wall-clock budget after storing some of the
register's documents is recorded `error`, not `partial` — the adapter
never returned a summary to classify. The queue admitted an application
holding documents only when it was `partial`, so the timed-out ones
left the queue for good: thirteen live members on 2026-09-06 — nine
behind a host that refused a whole run — three of
them Selby applications that afternoon holding 34, 17 and 18 documents
of registers listing more. A stored failure is not a result.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from dcp import acquisition_outcome, adjacent_power as ap, repo

ROOT = Path(__file__).resolve().parent.parent


def _queue():
    spec = importlib.util.spec_from_file_location("fetch_outstanding", ROOT / "scripts" / "fetch_outstanding.py")
    m = importlib.util.module_from_spec(spec); sys.modules["fetch_outstanding"] = m
    spec.loader.exec_module(m); return m


def _seed(conn, ref, *, outcome, held):
    source_id = repo.ensure_source(conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": "substation", "location_y": 51.5, "location_x": -0.1,
             "url": f"https://x/{ref}"},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute("INSERT INTO triage (application_id, model, verdict, raw_response) "
                    "VALUES (%s, 'fake', 'adjacent_power', '{\"rubric\": \"dc_build\"}')", (app_id,))
        for i in range(held):
            cur.execute("INSERT INTO documents (application_id, url, content_sha256) VALUES (%s, %s, %s)",
                        (app_id, f"https://x/{ref}/doc{i}.pdf", f"{i:064x}"))
    conn.commit()
    acquisition_outcome.record(conn, app_id, outcome, "idox",
                               "exceeded 900s" if outcome == "error" else None, 0)
    return app_id


def _ids(conn, q):
    with conn.cursor() as cur:
        adjacent = list(ap.staged_applications(cur, held_only=False))
        cur.execute(q.OUTSTANDING_SQL, (adjacent, []))
        return {r[0] for r in cur.fetchall()}


@pytest.mark.integration
def test_a_timed_out_application_holding_documents_is_still_outstanding(db_conn):
    q = _queue()
    timed_out = _seed(db_conn, "Testing/24/5001/FUL", outcome="error", held=3)
    finished = _seed(db_conn, "Testing/24/5002/FUL", outcome="fetched", held=3)
    ids = _ids(db_conn, q)
    assert timed_out in ids, "error after storing some documents: unfinished, stays queued"
    assert finished not in ids, "fetched with documents held: done"


def test_the_predicate_names_error_beside_partial():
    src = (ROOT / "scripts" / "fetch_outstanding.py").read_text()
    start = src.index('OUTSTANDING_SQL = """'); sql = src[start:src.index('"""', start + 25)]
    assert "OR o.outcome IN ('partial', 'error')" in sql
