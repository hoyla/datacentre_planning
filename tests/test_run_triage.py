"""Integration tests for the production triage path: repo.record_triage +
repo.applications_pending_triage + the end-to-end orchestrator wiring.

Uses FakeBackend so no Ollama dependency. The orchestrator opens its own
db.connect() — we monkeypatch that to return the test connection.
"""

from __future__ import annotations

import json

import pytest

from dcp import repo, triage


pytestmark = pytest.mark.integration


def _seed_app(db_conn, source_id, ref, description, *, app_type="Outline"):
    return repo.upsert_application(
        db_conn, source_id=source_id,
        app={
            "name": ref, "uid": ref.split("/", 1)[-1],
            "area_name": None, "description": description, "address": "Somewhere",
            "postcode": None, "start_date": "2024-01-15", "decided_date": None,
            "app_state": "Undecided", "app_type": app_type, "app_size": "Large",
            "url": "https://example.invalid/app",
        },
    )


def _canned(verdict, deep="yes", signals=None, why="x", confidence="probable"):
    return json.dumps({
        "verdict": verdict, "worth_deep_read": deep,
        "signals": signals or [], "why": why, "confidence": confidence,
    })


def test_record_triage_writes_all_v1_fields(db_conn):
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    app_id = _seed_app(db_conn, source_id, "X/1", "Outline DC build.")
    tid = repo.record_triage(
        db_conn, application_id=app_id, model="granite4.1:30b",
        verdict="DC", worth_deep_read="yes",
        signals=["substation", "generator"], why="Explicit DC.",
        confidence="sure", raw_response={"text": "{...}"},
    )
    assert isinstance(tid, int) and tid > 0
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT verdict, worth_deep_read, signals, why, confidence, raw_response "
            "FROM triage WHERE id = %s", (tid,),
        )
        v, dr, sigs, why, conf, raw = cur.fetchone()
    assert v == "DC"
    assert dr == "yes"
    assert sorted(sigs) == ["generator", "substation"]
    assert why == "Explicit DC."
    assert conf == "sure"
    assert raw == {"text": "{...}"}


def test_record_triage_versions_repeated_verdicts(db_conn):
    """Same (app, model) twice creates two rows — verdicts are append-only."""
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    app_id = _seed_app(db_conn, source_id, "X/1", "Outline DC build.")
    for verdict in ("unknown", "DC"):
        repo.record_triage(
            db_conn, application_id=app_id, model="granite4.1:30b",
            verdict=verdict, worth_deep_read="maybe", signals=[],
            why="x", confidence="guessing",
        )
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT verdict FROM triage WHERE application_id = %s "
            "ORDER BY inserted_at, id", (app_id,),
        )
        assert [r[0] for r in cur.fetchall()] == ["unknown", "DC"]


def test_applications_pending_triage_excludes_already_triaged(db_conn):
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    a = _seed_app(db_conn, source_id, "X/1", "first")
    b = _seed_app(db_conn, source_id, "X/2", "second")
    repo.record_triage(
        db_conn, application_id=a, model="granite4.1:30b",
        verdict="DC", worth_deep_read="yes", signals=[], why="x", confidence="sure",
    )
    pending = repo.applications_pending_triage(db_conn, model="granite4.1:30b")
    refs = [r["application_ref"] for r in pending]
    assert refs == ["X/2"]


def test_applications_pending_triage_is_model_scoped(db_conn):
    """A verdict from model A doesn't suppress queueing under model B."""
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    a = _seed_app(db_conn, source_id, "X/1", "first")
    repo.record_triage(
        db_conn, application_id=a, model="modelA",
        verdict="DC", worth_deep_read="yes", signals=[], why="x", confidence="sure",
    )
    pending = repo.applications_pending_triage(db_conn, model="modelB")
    assert [r["application_ref"] for r in pending] == ["X/1"]


def test_applications_pending_triage_respects_limit(db_conn):
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    for i in range(5):
        _seed_app(db_conn, source_id, f"X/{i}", f"app {i}")
    pending = repo.applications_pending_triage(db_conn, model="m", limit=2)
    assert len(pending) == 2


def test_run_triage_processes_pending_apps_and_records_verdicts(db_conn, monkeypatch):
    """End-to-end: seed two apps, run with a FakeBackend serving canned JSON,
    verify both end up with a triage row and the summary aggregates verdicts."""
    from dcp import triage as triage_mod
    from dcp.llm import FakeBackend

    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    _seed_app(db_conn, source_id, "X/DC1", "Outline application for a hyperscale data centre.")
    _seed_app(db_conn, source_id, "X/PROC1",
              "Variation of conditions 2 and 3 of parent permission.",
              app_type="Conditions")
    db_conn.commit()

    fake = FakeBackend(responses={
        "Application: X/DC1": _canned("DC", deep="yes", signals=["data centre"]),
        "Application: X/PROC1": _canned("unrelated", deep="no", confidence="sure"),
    })

    # Stub OllamaBackend so run_triage uses our FakeBackend regardless of model.
    class _FakeBackend(FakeBackend):
        def __init__(self, *a, **kw):
            kw.pop("model", None); kw.pop("request_timeout", None)
            super().__init__(responses=fake.responses)
            self.model = "fake-granite"
    import dcp.llm as llm_mod
    # run_triage does `from dcp.llm import OllamaBackend` at call time, so
    # patching the attribute on the source module is what intercepts it.
    monkeypatch.setattr(llm_mod, "OllamaBackend", _FakeBackend)

    # The orchestrator opens its own db.connect(); reuse our test connection
    # via a context-manager that yields it without closing.
    from contextlib import contextmanager
    @contextmanager
    def _conn_ctx():
        yield db_conn
    import dcp.db as db_mod
    monkeypatch.setattr(db_mod, "connect", _conn_ctx)

    seen: list[dict] = []
    summary = triage_mod.run_triage(model="fake-granite", progress=seen.append)

    assert summary["scanned"] == 2
    assert summary["errors"] == 0
    assert summary["by_verdict"]["DC"] == 1
    assert summary["by_verdict"]["unrelated"] == 1
    assert summary["model"] == "fake-granite"

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT a.application_ref, t.verdict, t.worth_deep_read, t.confidence "
            "FROM triage t JOIN applications a ON a.id = t.application_id "
            "WHERE t.model = 'fake-granite' ORDER BY a.application_ref"
        )
        rows = cur.fetchall()
    assert rows == [
        ("X/DC1", "DC", "yes", "probable"),
        ("X/PROC1", "unrelated", "no", "sure"),
    ]

    # Progress callback fired once per app, in DB order
    assert [r["ref"] for r in seen] == ["X/DC1", "X/PROC1"]
    assert [r["verdict"] for r in seen] == ["DC", "unrelated"]


def test_run_triage_skips_already_triaged_on_resume(db_conn, monkeypatch):
    """If an app already has a verdict for the chosen model, the orchestrator
    must skip it on the next run — even if the FakeBackend would answer."""
    from dcp import triage as triage_mod
    from dcp.llm import FakeBackend

    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    app_id_a = _seed_app(db_conn, source_id, "Y/DONE", "Already classified.")
    _seed_app(db_conn, source_id, "Y/TODO", "Still pending.")
    repo.record_triage(
        db_conn, application_id=app_id_a, model="fake-granite",
        verdict="DC", worth_deep_read="yes", signals=[], why="prior", confidence="sure",
    )
    db_conn.commit()

    fake = FakeBackend(responses={
        "Application: Y/TODO": _canned("adjacent", deep="maybe"),
    })

    class _FakeBackend(FakeBackend):
        def __init__(self, *a, **kw):
            kw.pop("model", None); kw.pop("request_timeout", None)
            super().__init__(responses=fake.responses)
            self.model = "fake-granite"
            self.calls_log: list[str] = []

        def complete(self, prompt, *, system=None):
            self.calls_log.append(prompt[:40])
            return super().complete(prompt, system=system)

    import dcp.llm as llm_mod
    # run_triage does `from dcp.llm import OllamaBackend` at call time, so
    # patching the attribute on the source module is what intercepts it.
    monkeypatch.setattr(llm_mod, "OllamaBackend", _FakeBackend)

    from contextlib import contextmanager
    @contextmanager
    def _conn_ctx():
        yield db_conn
    import dcp.db as db_mod
    monkeypatch.setattr(db_mod, "connect", _conn_ctx)

    summary = triage_mod.run_triage(model="fake-granite")

    assert summary["scanned"] == 1  # only Y/TODO

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT a.application_ref, count(*) AS n FROM triage t "
            "JOIN applications a ON a.id = t.application_id "
            "WHERE t.model = 'fake-granite' "
            "GROUP BY a.application_ref ORDER BY a.application_ref"
        )
        rows = cur.fetchall()
    # Y/DONE keeps its single prior verdict; Y/TODO got exactly one.
    assert rows == [("Y/DONE", 1), ("Y/TODO", 1)]


def test_run_triage_records_error_without_crashing(db_conn, monkeypatch):
    """A backend that returns unparseable text after retry must not abort the
    sweep — the row is counted as an error and the next app proceeds."""
    from dcp import triage as triage_mod
    from dcp.llm import LLMResponse

    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x",
    )
    _seed_app(db_conn, source_id, "Z/BAD", "junk that won't parse")
    _seed_app(db_conn, source_id, "Z/OK", "Outline DC build.")
    db_conn.commit()

    class _MixedBackend:
        def __init__(self, *a, **kw):
            self.model = "fake-granite"
            self.calls = 0
        def complete(self, prompt, *, system=None):
            self.calls += 1
            if "Z/BAD" in prompt:
                return LLMResponse(text="no JSON here", model=self.model)
            return LLMResponse(
                text=_canned("DC", deep="yes", confidence="probable"),
                model=self.model,
            )
    import dcp.llm as llm_mod
    monkeypatch.setattr(llm_mod, "OllamaBackend", _MixedBackend)

    from contextlib import contextmanager
    @contextmanager
    def _conn_ctx():
        yield db_conn
    import dcp.db as db_mod
    monkeypatch.setattr(db_mod, "connect", _conn_ctx)

    summary = triage_mod.run_triage(model="fake-granite")

    assert summary["scanned"] == 2
    assert summary["errors"] == 1
    assert summary["by_verdict"]["DC"] == 1
    # Z/BAD has no triage row, Z/OK has one
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT a.application_ref FROM triage t "
            "JOIN applications a ON a.id = t.application_id "
            "WHERE t.model = 'fake-granite' ORDER BY a.application_ref"
        )
        assert [r[0] for r in cur.fetchall()] == ["Z/OK"]
