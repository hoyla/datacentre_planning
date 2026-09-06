"""The fetch queue reaches the adjacent-power class, not only site members.

#252 took `adjacent_power` out of membership on 2026-08-30. The queue's
scope was "live member of a live site", so from that day it stopped
reaching the class: fifteen adjacent-power applications held nothing
and would never have been tried again, and a substation discovered
today would get a verdict, a relationship row and no fetch. Luke's
question on 2026-09-06 — what makes these different from the ones we
acquired? — found it.

`dcp.adjacent_power.staged_applications` is the one rule for the class;
`held_only=False` reads it without the documents clause the staging
build needs, and the queue's scope is "live member OR in that class".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from dcp import adjacent_power as ap, repo

ROOT = Path(__file__).resolve().parent.parent


def _queue():
    spec = importlib.util.spec_from_file_location("fetch_outstanding", ROOT / "scripts" / "fetch_outstanding.py")
    m = importlib.util.module_from_spec(spec); sys.modules["fetch_outstanding"] = m
    spec.loader.exec_module(m); return m


def _seed(conn, ref, verdict, *, url=None):
    source_id = repo.ensure_source(conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": "substation", "location_y": 51.5, "location_x": -0.1,
             "url": url or f"https://x/{ref}"},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute("INSERT INTO triage (application_id, model, verdict, raw_response) "
                    "VALUES (%s, 'fake', %s, '{\"rubric\": \"dc_build\"}')", (app_id, verdict))
    conn.commit()
    return app_id


@pytest.mark.integration
def test_the_class_without_the_held_clause_lists_a_scheme_holding_nothing(db_conn):
    a = _seed(db_conn, "Testing/24/4001/FUL", "adjacent_power")
    with db_conn.cursor() as cur:
        assert a not in ap.staged_applications(cur), "nothing held: not staged"
        assert a in ap.staged_applications(cur, held_only=False), "in the class regardless"


@pytest.mark.integration
def test_the_queue_takes_an_adjacent_power_scheme_that_is_in_no_site(db_conn):
    q = _queue()
    a = _seed(db_conn, "Testing/24/4002/FUL", "adjacent_power")
    n = _seed(db_conn, "Testing/24/4003/FUL", "not_dc")     # a stray, not paperwork of anything
    with db_conn.cursor() as cur:
        adjacent = list(ap.staged_applications(cur, held_only=False))
        cur.execute(q.OUTSTANDING_SQL, (adjacent, []))
        ids = {r[0] for r in cur.fetchall()}
    assert a in ids
    assert n not in ids, "not_dc outside any site and outside the class stays out of scope"


def test_the_queue_no_longer_scopes_by_membership_alone():
    src = (ROOT / "scripts" / "fetch_outstanding.py").read_text()
    assert "staged_applications(cur, held_only=False)" in src
    assert "OR a.id = ANY(%s)" in src
    assert "JOIN sites s ON s.id = m.site_id" in q_sql(src)


def q_sql(src: str) -> str:
    start = src.index('OUTSTANDING_SQL = """'); return src[start:src.index('"""', start + 25)]
