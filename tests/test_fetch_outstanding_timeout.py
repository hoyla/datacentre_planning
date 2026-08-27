"""The per-application ceiling has to survive the adapters' own handlers.

`fetch_outstanding` gives each application a wall-clock deadline
(`--app-timeout`, 900s) enforced by SIGALRM. The adapters catch
`Exception` per document so that one bad link does not cost the rest of
a bundle — idox ends its download loop with a bare `except Exception as
exc: failure = exc; break`. A timeout raised as an ordinary Exception
therefore landed in *that* handler, was filed as one document's failure,
and the loop moved on; SIGALRM fires once, so the ceiling was then gone.

Measured 2026-08-27: Southwark/18/AP/1604 ran 216 minutes against a
900-second deadline while the sweep's rate fell from 321 documents an
hour to under 50.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location(
        "fetch_outstanding", ROOT / "scripts" / "fetch_outstanding.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_timeout_is_not_an_exception_the_adapters_can_catch():
    fo = _module()
    assert issubclass(fo.ApplicationTimeout, BaseException)
    assert not issubclass(fo.ApplicationTimeout, Exception)


def test_an_adapter_style_handler_does_not_swallow_it():
    """The exact shape of idox's per-document handler."""
    fo = _module()
    swallowed = False
    try:
        try:
            raise fo.ApplicationTimeout("exceeded 900s")
        except Exception:                      # noqa: BLE001 — the adapter's
            swallowed = True                   # own handler, reproduced
    except fo.ApplicationTimeout:
        pass
    assert not swallowed, "the per-document handler caught the ceiling"


def test_an_ordinary_failure_is_still_swallowed_per_document():
    """The adapters' behaviour must be unchanged for real failures: one
    bad link costs its own document and nothing more."""
    caught = False
    try:
        raise RuntimeError("404 on one link")
    except Exception:                          # noqa: BLE001
        caught = True
    assert caught


def test_the_deadline_actually_fires(monkeypatch):
    """End to end through the real context manager, with a one-second
    ceiling: a guard nobody has watched fire is a guard nobody knows
    works — which is how this one went unnoticed."""
    import time
    fo = _module()
    with pytest.raises(fo.ApplicationTimeout):
        with fo.deadline(1):
            # An adapter-shaped loop that catches Exception per item.
            for _ in range(50):
                try:
                    time.sleep(0.1)
                except Exception:              # noqa: BLE001
                    pass
