"""The findings idempotency contract, asserted against the real index.

Migration 012 (PR #32, 2026-08-10) put a unique index over the content
columns of `findings` so that a re-run adds no duplicate rows, and
`scripts/deepread_run.py` mirrors its column list as `CONTENT_KEY`, a
tuple of offsets into the value tuples it inserts. Until 2026-09-16 the
test database never received migration 012, so no test had ever
exercised the index, and nothing checked that the two column lists —
the index's and the mirror's — still agreed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import deepread_run  # noqa: E402

pytestmark = pytest.mark.integration

INDEX_SQL = (ROOT / "migrations" / "012_findings_idempotency.sql").read_text()


def _index_columns() -> list[str]:
    m = re.search(r"CREATE UNIQUE INDEX findings_content_key\s+ON findings \((.*?)\)"
                  r"\s*NULLS NOT DISTINCT", INDEX_SQL, re.S)
    assert m, "migration 012 no longer defines findings_content_key"
    cols = [c.strip() for c in m.group(1).split(",")]
    return [re.sub(r"^md5\((\w+)\)$", r"\1", c) for c in cols]


def _insert_columns() -> list[str]:
    src = Path(deepread_run.__file__).read_text()
    m = re.search(r"INSERT INTO findings \((.*?)\)\s*VALUES", src, re.S)
    assert m
    return [c.strip() for c in m.group(1).split(",")]


def test_the_mirror_names_the_index_columns_in_the_index_order():
    cols = _insert_columns()
    mirrored = [cols[i] for i in deepread_run.CONTENT_KEY]
    assert mirrored == _index_columns(), (
        "deepread_run.CONTENT_KEY no longer mirrors findings_content_key; "
        "dedupe_verified would keep rows the index then refuses, or drop "
        "rows it would have kept")


def _seed(cur) -> tuple[int, int]:
    cur.execute("INSERT INTO sources (name, kind, base_url) VALUES ('t', 'planning_portal', 'http://t') "
                "ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url "
                "RETURNING id")
    source_id = cur.fetchone()[0]
    cur.execute("INSERT INTO applications (source_id, application_ref) "
                "VALUES (%s, 'T/1') RETURNING id", (source_id,))
    app_id = cur.fetchone()[0]
    cur.execute("INSERT INTO documents (application_id, url) VALUES (%s, 'http://t/d') "
                "RETURNING id", (app_id,))
    return app_id, cur.fetchone()[0]


def test_the_index_is_in_the_test_database(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'findings_content_key'")
        assert cur.fetchone(), "the test database does not carry migration 012"


def test_the_same_finding_inserted_twice_lands_once(db_conn):
    """Two chunks producing one finding from one quote is the routine
    case; the NULLs (no number, no unit) are the case `NULLS NOT DISTINCT`
    exists for, since a plain unique index treats every NULL as new."""
    with db_conn.cursor() as cur:
        app_id, doc_id = _seed(cur)
    row = (app_id, doc_id, "power_capacity", "power", "rule",
           "substantial power", None, None,
           "a substantial power supply is required", 3, "test", "v0")
    assert deepread_run.insert_verified(db_conn, [row, row]) == 1
    assert deepread_run.insert_verified(db_conn, [row]) == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM findings")
        assert cur.fetchone()[0] == 1


def test_a_finding_differing_only_in_family_is_still_one_row(db_conn):
    """`signal_family` and `family_source` are derived and deliberately
    outside the key (the comment above CONTENT_KEY): a reclassification
    must not manufacture a second finding."""
    with db_conn.cursor() as cur:
        app_id, doc_id = _seed(cur)
    a = (app_id, doc_id, "power_capacity", "power", "rule", "10 MW", 10.0, "MW",
         "a 10 MW supply", 1, "test", "v0")
    b = a[:3] + ("unclassified", "model") + a[5:]
    assert deepread_run.insert_verified(db_conn, [a]) == 1
    assert deepread_run.insert_verified(db_conn, [b]) == 0
