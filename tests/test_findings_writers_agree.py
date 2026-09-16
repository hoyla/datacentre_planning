"""Four scripts write findings; they must write the same row.

`scripts/deepread_run.py` is the local runner; `deepread_escalate.py`,
`deepread_escalate_openai.py` and `deepread_agent_escalate.py` each
reimplement its gate-and-insert for another model. By 2026-09-16 two of
the three had drifted: their INSERT omitted `signal_family` and
`family_source` — the defect `backfill_signal_family.py` was written to
repair after 557,747 OpenAI rows carried a NULL family — and the agent
writer never stripped NUL bytes, which Postgres refuses. This drives all
four through a fake cursor with the same finding and asserts they name
the same columns, derive the same family, and strip the same byte.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import deepread_run  # noqa: E402
import deepread_escalate  # noqa: E402
import deepread_escalate_openai  # noqa: E402
import deepread_agent_escalate  # noqa: E402
from dcp import signal_families  # noqa: E402

QUOTE = "The proposed data centre requires a 45 MW grid connection."
PAGES = ["Cover page.", f"Section 3. {QUOTE} Further detail follows."]
SENT = [1, 2]
ROW = {"application_id": 7, "document_id": 9, "application_ref": "T/1", "sha": "abc"}
FINDING = {"signal_type": "grid connection\x00 capacity", "value_text": "45 MW",
           "value_number": 45, "value_unit": "MW", "evidence_text": QUOTE,
           "evidence_page": 2}


class _Cursor:
    def __init__(self, log):
        self.log, self.rowcount = log, 1

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass


def _columns(sql: str) -> list[str]:
    m = re.search(r"INSERT INTO findings \((.*?)\)\s*VALUES", sql, re.S)
    assert m, sql
    return [c.strip() for c in m.group(1).split(",")]


def _run_local(conn):
    values, failed = deepread_run.verify_findings(ROW, [dict(FINDING)], PAGES, SENT)
    assert failed == 0
    deepread_run.insert_verified(conn, values)


def _run_sonnet(conn):
    deepread_escalate._insert_with_model(conn, ROW, [dict(FINDING)], PAGES, SENT)


def _run_openai(conn):
    deepread_escalate_openai._insert(conn, ROW, [dict(FINDING)], PAGES, SENT, "gpt-test")


def _run_agent(conn):
    deepread_agent_escalate._insert_agent(conn, ROW, [dict(FINDING)], PAGES, SENT)


WRITERS = {"local": _run_local, "sonnet": _run_sonnet, "openai": _run_openai,
           "agent": _run_agent}


@pytest.fixture
def no_escalation(monkeypatch):
    monkeypatch.setattr(deepread_run, "escalate", lambda **kw: None)


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_every_writer_names_the_runners_columns(name, no_escalation):
    conn = _Conn()
    WRITERS[name](conn)
    assert len(conn.log) == 1, conn.log
    sql, params = conn.log[0]
    assert _columns(sql) == _columns(deepread_run_insert_sql()), name
    assert len(params) == len(_columns(sql)), name


def deepread_run_insert_sql() -> str:
    conn = _Conn()
    _run_local(conn)
    return conn.log[0][0]


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_every_writer_derives_the_family_from_the_stored_label(name, no_escalation):
    conn = _Conn()
    WRITERS[name](conn)
    sql, params = conn.log[0]
    row = dict(zip(_columns(sql), params))
    label = row["signal_type"]
    assert row["signal_family"] == signal_families.family_for(label), name
    assert row["family_source"] == "derived", name


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_every_writer_strips_the_nul_byte(name, no_escalation):
    conn = _Conn()
    WRITERS[name](conn)
    sql, params = conn.log[0]
    assert not any(isinstance(v, str) and "\x00" in v for v in params), name
    row = dict(zip(_columns(sql), params))
    assert row["signal_type"] == "grid connection capacity"
    assert row["evidence_page"] == 2
