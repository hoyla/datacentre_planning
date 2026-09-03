"""A withheld reading must not stop the site being read again.

The readings pass skips a site when a row already exists for its
current input hash. A reading withheld because the site changed
between submission and collection is stored against the *rebuilt*
input's hash — the one that was never read — so the skip matches it,
and a site whose documents then settle at that hash is never read
again.

Latent when found (2026-09-03), not yet suffered: 11 live sites have
been withheld this way and all 11 hold a live reading now, because
their inputs moved again and produced a hash no row carried. It was
found while accounting for three withheld readings that turned out to
have nothing to do with it — two belong to sites retired on 27 August,
and the third is Mary Somerville, which holds no documents. Nothing
would have said so if a site had stuck: the reader renders a withheld
reading, which reads as a judgement about the site rather than as a
queue that cannot advance.

A reading withheld by the GATE is a different fact — a verdict on
content the model did read — and re-reading the same input would
re-spend on every run for a result already refused. Only the
inputs-moved reason is discounted.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
mro = importlib.import_module("machine_reading_openai")


class _Cur:
    """Records the SQL and answers from a tiny fixture of rows."""

    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()
        self._answer = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.sql, self.params = " ".join(sql.split()), params
        site_key, model, prompt, input_hash, gate, *rest = params
        excluded = rest[0] if rest else None
        self._answer = None
        for row in self.rows:
            if (row["site_key"], row["model"], row["input_hash"]) != (
                    site_key, model, input_hash):
                continue
            if excluded is not None and (row.get("withheld_reason") or "") == excluded:
                continue
            self._answer = (1,)
            break

    def fetchone(self):
        return self._answer


class _Conn:
    def __init__(self, rows):
        self.cur = _Cur(rows)

    def cursor(self):
        return self.cur


def _row(**kw):
    base = {"site_key": "SITE-X", "model": "gpt-5", "input_hash": "abc",
            "withheld_reason": None}
    base.update(kw)
    return base


def test_a_live_reading_of_this_input_still_skips_the_site():
    conn = _Conn([_row()])
    assert mro._already(conn, "SITE-X", "gpt-5", "abc") is True


def test_a_reading_withheld_because_the_site_moved_does_not_skip_it():
    conn = _Conn([_row(withheld_reason=mro.INPUTS_MOVED)])
    assert mro._already(conn, "SITE-X", "gpt-5", "abc") is False, (
        "the row was stored against a hash nothing read")


def test_a_reading_the_gate_refused_still_skips_the_site():
    """Re-reading an unchanged input would re-spend on every run."""
    conn = _Conn([_row(withheld_reason="a quote is not verbatim in the document")])
    assert mro._already(conn, "SITE-X", "gpt-5", "abc") is True


def test_the_exclusion_is_sent_to_postgres_rather_than_filtered_here():
    conn = _Conn([])
    mro._already(conn, "SITE-X", "gpt-5", "abc")
    assert "withheld_reason" in conn.cur.sql
    assert conn.cur.params[-1] == mro.INPUTS_MOVED


def test_the_reason_string_is_the_one_the_collector_writes():
    src = (Path(__file__).resolve().parent.parent / "scripts"
           / "machine_reading_openai.py").read_text()
    assert "mr.GateResult(False, INPUTS_MOVED)" in src, (
        "the collector must write the same constant the skip discounts")
    assert src.count("inputs changed between submission") == 1, (
        "the reason exists once, as INPUTS_MOVED")
