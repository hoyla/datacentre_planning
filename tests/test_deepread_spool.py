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


def _value(signal_type="standby_capacity", family="power", source="derived",
           value_text="12 MW", number=12, unit="MW",
           evidence="12 MW of standby diesel generation", page=1):
    """One row in the shape `verify_findings` builds, positionally."""
    return (22, 11, signal_type, family, source, value_text, number, unit,
            evidence, page, D.MODEL_TAG, D.PROMPT_VERSION)


def test_spooled_count_is_what_will_land(spool):
    """The spool must not report more findings than the drain writes.

    Online the count is what Postgres inserted, which is after the
    content-key index has absorbed repeats. The spool used to report how
    many rows it wrote, which was before — so on 2026-08-12 two spooled
    documents claimed 230 and 142 findings against 73 and 32 actually
    stored, in the same column of the same log as the honest numbers.
    """
    dup = _value()
    # Same content key, different derived family: the index does not
    # distinguish these, so neither may the count.
    same_key = _value(family="power_generation", source="model")
    other = _value(signal_type="grid_connection", value_text="400 kV",
                   number=400, unit="kV", evidence="a 400 kV connection")

    spooled = D.commit_or_spool(None, ROW, values=[dup, same_key, other],
                                read_state="read", pages_total=1,
                                pages_sent=[1])
    assert spooled == 2, "rows the index would collapse must not be counted"

    record = json.loads(D.SPOOL_PATH.read_text().splitlines()[0])
    assert len(record["values"]) == 2, "nor written to the spool"

    conn = FakeConn()
    docs, drained = D.drain_spool(conn)
    assert (docs, drained) == (1, spooled), \
        "the drain's total must match what the spool already claimed"


def test_dedupe_keeps_the_first_row_and_its_evidence(spool):
    """Collapsing rows must not lose the quote or reorder the survivors."""
    first = _value(value_text="12 MW", evidence="12 MW of standby diesel")
    second = _value(signal_type="water_use", value_text="3 Ml/d",
                    number=3, unit="Ml/d", evidence="3 Ml/d of cooling water")
    kept = D.dedupe_verified([first, second, first])
    assert kept == [first, second]


class UnreachableDB:
    """`db.connect()` for a database that is not there, counting attempts."""

    def __init__(self):
        self.attempts = 0

    def __call__(self):
        import psycopg2
        self.attempts += 1
        raise psycopg2.OperationalError("could not connect to server")


def test_an_outage_costs_the_write_not_the_read(spool, monkeypatch):
    """A document read as the outage begins must not be read again.

    The connection used to be opened before the read and held across it,
    so the failure surfaced at commit and the retry re-read the whole
    document. On 2026-08-12 that cost 696s and 576s of Studio time on two
    documents whose inference was finished and whose findings had already
    passed the verbatim gate.
    """
    reads = []
    monkeypatch.setattr(D, "mlx_generate", lambda text, max_tokens, prompt=None:
                        (reads.append(text) or
                         (json.dumps({"findings": [
                             {"signal_type": "standby_capacity",
                              "value_text": "12 MW",
                              "evidence_text":
                                  "12 MW of standby diesel generation",
                              "evidence_page": 1}]}), 0.1)))
    cache = spool / "doc.json"
    cache.write_text(json.dumps({"engine": "pypdf", "pages": PAGES}))
    monkeypatch.setattr(D.extract, "cache_path_for", lambda *a, **k: cache)
    unreachable = UnreachableDB()
    monkeypatch.setattr(D.db, "connect", unreachable)
    monkeypatch.setattr(D.time, "sleep", lambda s: None)

    row = dict(ROW, sampled_out=False, kind="SUPPORTING INFORMATION")
    sink = D.Sink()
    status = D.process_document(sink, row, max_chars=16000, max_tokens=4000)

    assert len(reads) == 1, "the model must be run once, outage or not"
    assert sink.offline, "the run should now be offline"
    assert unreachable.attempts == 3, "three write attempts, then spool"
    assert "1 findings" in status
    record = json.loads(D.SPOOL_PATH.read_text().splitlines()[0])
    assert len(record["values"]) == 1, "the verified finding is spooled"


def test_offline_sink_does_not_probe_before_the_interval(spool, monkeypatch):
    """Already offline, the sink must not spend a connect timeout per
    document rediscovering the same outage."""
    unreachable = UnreachableDB()
    monkeypatch.setattr(D.db, "connect", unreachable)
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    sink = D.Sink()
    sink.commit(ROW, values=[], read_state="read", pages_total=1,
                pages_sent=[1])
    assert unreachable.attempts == 3 and sink.offline

    for _ in range(5):
        sink.commit(ROW, values=[], read_state="read", pages_total=1,
                    pages_sent=[1])
    assert unreachable.attempts == 3, "no further connections until the probe"
    assert len(D.SPOOL_PATH.read_text().splitlines()) == 6


def test_settle_warns_about_held_documents_when_the_db_is_away(spool,
                                                               monkeypatch,
                                                               capsys):
    """The exit that happens during an outage must not be the silent one.

    Ctrl-C used to `return` past the settle, so interrupting an offline
    run left every read-and-verified document on disk with nothing said
    about it — at the one moment an operator most needs telling.
    """
    D.commit_or_spool(None, ROW, values=[_value()], read_state="read",
                      pages_total=1, pages_sent=[1])
    D.commit_or_spool(None, ROW, values=[], read_state="no_text",
                      pages_total=0, pages_sent=None)
    monkeypatch.setattr(D.db, "connect", UnreachableDB())

    D.settle_spool()

    out = capsys.readouterr().out
    assert "WARNING" in out and "2 documents" in out
    assert D.SPOOL_PATH.exists(), "held work must stay on disk to be replayed"


def test_settle_drains_when_the_db_is_back(spool, monkeypatch, capsys):
    D.commit_or_spool(None, ROW, values=[_value()], read_state="read",
                      pages_total=1, pages_sent=[1])
    conn = FakeConn()

    import contextlib

    @contextlib.contextmanager
    def reachable():
        yield conn

    monkeypatch.setattr(D.db, "connect", reachable)
    D.settle_spool()

    assert "drained 1 spooled documents, 1 findings" in capsys.readouterr().out
    assert not D.SPOOL_PATH.exists()


def test_settle_is_a_no_op_with_nothing_held(spool, capsys):
    D.settle_spool()
    assert capsys.readouterr().out == ""


def test_term_asks_for_a_stop_rather_than_taking_one(capsys):
    """SIGTERM must not kill the process where it stands.

    The runbook has promised since before it was true that TERM lets the
    current document finish. It did not: there was no handler, so TERM
    took Python's default disposition and threw away whatever the model
    had produced — up to 86 minutes of it on a large Environmental
    Statement.
    """
    import signal

    D._STOP["requested"] = False
    previous = signal.getsignal(signal.SIGTERM)
    try:
        D.install_stop_handler()
        assert signal.getsignal(signal.SIGTERM) is D.request_stop, \
            "TERM must be handled, not left to kill the process"

        D.request_stop(signal.SIGTERM, None)
        assert D._STOP["requested"], "the loop checks this at each boundary"
        assert "finishing the current document" in capsys.readouterr().out

        # A second TERM is not an escalation: acknowledging once keeps the
        # log honest, and `kill -9` is the documented immediate stop.
        D.request_stop(signal.SIGTERM, None)
        assert capsys.readouterr().out == ""
    finally:
        signal.signal(signal.SIGTERM, previous)
        D._STOP["requested"] = False


def test_a_backgrounded_run_can_still_be_interrupted():
    """SIGINT must be deliverable to a run started with `nohup … &`.

    A shell sets SIGINT to SIG_IGN for a background command and Python
    honours an inherited SIG_IGN instead of installing its own handler.
    The reader is always started that way, so `except KeyboardInterrupt`
    was unreachable in production — measured by delivering `kill -INT` to
    a live run, which read on to completion as though nothing had been
    sent.
    """
    import signal

    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # as a shell leaves it
        D.install_stop_handler()
        assert signal.getsignal(signal.SIGINT) is signal.default_int_handler, \
            "an inherited SIG_IGN must be replaced, or INT is a no-op"
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


def test_an_existing_sigint_handler_is_left_alone():
    """Only an inherited SIG_IGN is overridden — a foreground run already
    has Python's handler, and a caller that installed its own keeps it."""
    import signal

    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)
    mine = lambda *a: None  # noqa: E731
    try:
        signal.signal(signal.SIGINT, mine)
        D.install_stop_handler()
        assert signal.getsignal(signal.SIGINT) is mine
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
