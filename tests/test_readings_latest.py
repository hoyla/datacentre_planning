"""`site_machine_readings` folds to the latest row, asserted in Postgres.

The store is append-only: a re-read adds a row and never overwrites.
Every consumer therefore reads through `LATEST_SQL`, a `DISTINCT ON`
whose `ORDER BY` decides which row a site's reading *is*. The unit
tests hand `machine_reading` a fake cursor that returns fixture rows
whatever SQL it is given, so until 2026-09-16 reversing that ORDER BY
passed the suite. This runs the real query on the real table, which
the test database has carried only since the same day.
"""

from __future__ import annotations

import json

import pytest

from dcp import machine_reading as mr

pytestmark = pytest.mark.integration


def _reading(cur, site_key, reading, inserted_at):
    cur.execute(
        "INSERT INTO site_machine_readings (site_key, model, prompt_version, "
        "input_hash, gate_version, documents_read, pages_read, input_chars, "
        "reading, inserted_at) VALUES (%s, 'm', 'p', md5(%s), 'g', 1, 1, 10, %s, %s)",
        (site_key, reading, json.dumps({"summary": reading}), inserted_at))


def test_the_later_reading_is_the_reading(db_conn):
    with db_conn.cursor() as cur:
        _reading(cur, "SITE-A", "first", "2026-09-01T10:00:00Z")
        _reading(cur, "SITE-A", "second", "2026-09-02T10:00:00Z")
        _reading(cur, "SITE-B", "only", "2026-09-01T10:00:00Z")
        cur.execute(mr.LATEST_SQL)
        rows = {r[0]: r[3]["summary"] for r in cur.fetchall()}
    assert rows == {"SITE-A": "second", "SITE-B": "only"}


def test_a_shared_timestamp_falls_to_the_higher_id(db_conn):
    """Two rows written in one second are a real case (a retry in the
    same batch); the tie must break the same way every build."""
    with db_conn.cursor() as cur:
        _reading(cur, "SITE-A", "first", "2026-09-01T10:00:00Z")
        _reading(cur, "SITE-A", "second", "2026-09-01T10:00:00Z")
        cur.execute(mr.LATEST_SQL)
        rows = cur.fetchall()
    assert len(rows) == 1 and rows[0][3]["summary"] == "second"
