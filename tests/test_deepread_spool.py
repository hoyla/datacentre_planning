"""The deep read must survive the database going away.

The Studio reads; the database is on the laptop. A laptop sleeps, leaves
the building and changes network, and before the spool existed each of
those cost the *inference*: four retries over three minutes, then the
document was escalated and everything the model had produced for it was
thrown away.

What these assert is the property that makes that acceptable — an
unreachable database costs a write, never a read, and never the
verbatim-quote gate.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.modules.setdefault("mlx_lm", types.SimpleNamespace(
    load=lambda *a, **k: (None, None), generate=lambda *a, **k: ""))

import deepread_run as D  # noqa: E402


ROW = {"document_id": 11, "application_id": 22, "application_ref": "Test/1",
       "sha": "deadbeef", "tier": "A"}
PAGES = ["The proposal includes 12 MW of standby diesel generation on site."]


@pytest.fixture
def spool(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "SPOOL_PATH", tmp_path / "spool.jsonl")
    monkeypatch.setattr(D, "SPOOL_DONE_PATH", tmp_path / "drained.jsonl")
    monkeypatch.setattr(D, "ESCALATION_PATH", tmp_path / "escalations.jsonl")
    return tmp_path


class FakeCursor:
    def __init__(self, log):
        self.log = log
        self.rowcount = 1

    def execute(self, sql, params=None):
        table = "findings" if "INTO findings" in sql else "deepread_log"
        self.log.append((table, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self):
        self.log: list = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self.log)

    def commit(self):
        self.commits += 1


def test_gate_runs_without_a_database(spool):
    """The verbatim check needs the page text, not the database.

    This is why offline reading is worth anything: the finding that
    reaches the spool has already been judged admissible.
    """
    findings = [
        {"signal_type": "standby_capacity", "value_text": "12 MW standby",
         "value_number": 12, "value_unit": "MW",
         "evidence_text": "12 MW of standby diesel generation",
         "evidence_page": 1},
        {"signal_type": "fabricated", "value_text": "not in the document",
         "evidence_text": "the applicant admits liability", "evidence_page": 1},
    ]
    values, failed = D.verify_findings(ROW, findings, PAGES, [1])
    assert len(values) == 1, "the real quote should pass"
    assert failed == 1, "the invented quote should be rejected, not spooled"
    assert "12 MW of standby diesel generation" in values[0]


def test_offline_document_is_spooled_not_lost(spool):
    values, failed = D.verify_findings(
        ROW, [{"signal_type": "standby_capacity", "value_text": "12 MW",
               "evidence_text": "12 MW of standby diesel generation",
               "evidence_page": 1}], PAGES, [1])
    D.commit_or_spool(None, ROW, values=values, read_state="read",
                      pages_total=1, pages_sent=[1], failed=failed,
                      elapsed=9.0)

    lines = D.SPOOL_PATH.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["document_id"] == ROW["document_id"]
    assert record["read_state"] == "read"
    assert len(record["values"]) == 1
    # The evidence text survives the round trip through JSON — a spool
    # that lost the quote would be worse than no spool, because the
    # finding would be inserted without the thing that justifies it.
    assert "12 MW of standby diesel generation" in record["values"][0]


def test_drain_writes_findings_then_log_and_commits_once(spool):
    D.commit_or_spool(None, ROW, values=[(22, 11, "x", "power", "derived",
                                          "12 MW", 12, "MW", "quote", 1,
                                          D.MODEL_TAG, D.PROMPT_VERSION)],
                      read_state="read", pages_total=1, pages_sent=[1])
    conn = FakeConn()
    docs, found = D.drain_spool(conn)

    assert (docs, found) == (1, 1)
    assert [t for t, _ in conn.log] == ["findings", "deepread_log"], \
        "findings must be written before the log row that makes them visible"
    assert conn.commits == 1, "one commit per document, made by log_document"


def test_drained_spool_is_archived_and_not_replayed(spool):
    """Draining twice must not write twice.

    The content-key guard would absorb duplicate findings, but the spool
    should not be relying on it: a drained record moves to the archive
    and the live spool goes away.
    """
    D.commit_or_spool(None, ROW, values=[], read_state="no_text",
                      pages_total=0, pages_sent=None)
    conn = FakeConn()
    assert D.drain_spool(conn) == (1, 0)
    assert not D.SPOOL_PATH.exists()
    assert len(D.SPOOL_DONE_PATH.read_text().splitlines()) == 1
    assert D.drain_spool(conn) == (0, 0)


def test_torn_final_line_costs_one_document_not_the_drain(spool):
    """A process killed mid-write leaves half a line. It must not block
    the rest of the spool from landing."""
    D.commit_or_spool(None, ROW, values=[], read_state="read",
                      pages_total=1, pages_sent=[1])
    with D.SPOOL_PATH.open("a") as fh:
        fh.write('{"document_id": 99, "values": [')  # torn
    conn = FakeConn()
    docs, _ = D.drain_spool(conn)
    assert docs == 1, "the intact record still drains"


def test_states_that_never_reach_the_model_also_spool(spool):
    """`skipped_graphical`, `sampled_out`, `not_extracted` and `no_text`
    are database writes too, and an outage must not lose them either —
    they are what makes coverage honest."""
    for state in ("skipped_graphical", "sampled_out", "not_extracted",
                  "no_text"):
        D.commit_or_spool(None, ROW, values=[], read_state=state,
                          pages_total=None, pages_sent=None)
    records = [json.loads(x) for x in D.SPOOL_PATH.read_text().splitlines()]
    assert [r["read_state"] for r in records] == [
        "skipped_graphical", "sampled_out", "not_extracted", "no_text"]
