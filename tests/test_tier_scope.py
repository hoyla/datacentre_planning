"""`--tier` names a set of tiers, and the set is what gets read.

The phase 3 read wants tiers A and B in one cohort: B is the bulk of the
outstanding prose, and A has to stay in scope so that prose arriving
later — a new Environmental Statement is tier A — is picked up by the
next start instead of needing a run of its own.

Before this the flag took a single tier, so the only way to express
"A and B" was to omit it. That is not the same request: an unscoped run
takes tier C as well, and `load_cohort` plans the sample *after* the
unread filter, so the fifth of tier C it would read is not the fifth the
global policy chose (tests/test_coverage_language.py demonstrates the
hazard; `universe_plan` is the fix, and the runner does not use it yet).
Scoping explicitly to A,B keeps the runner away from that entirely,
which is why the flag learned to take a list rather than the caller
learning to drop it.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.modules.setdefault("mlx_lm", types.SimpleNamespace(
    load=lambda *a, **k: (None, None), generate=lambda *a, **k: ""))

import deepread_run as D  # noqa: E402


# (document_id, application_id, application_ref, sha, kind) as the cohort
# query returns them. Kinds chosen so classify_kind puts one in each tier.
CORPUS = [
    (1, 100, "Test/1", "sha_a", "Planning Statement"),      # A
    (2, 100, "Test/1", "sha_b", "Plans"),                   # B
    (3, 100, "Test/1", "sha_c", "Public Comment"),          # C
]


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return FakeCursor(self.rows)


def _cohort(tiers):
    rows = D.load_cohort(FakeConn(CORPUS), tiers=tiers, ref=None, site=None)
    return {r["tier"] for r in rows}


def test_the_fixture_covers_all_three_tiers():
    """Otherwise the assertions below pass without meaning anything."""
    assert _cohort(None) == {"A", "B", "C"}


def test_a_single_tier_still_means_that_tier_alone():
    assert _cohort(["A"]) == {"A"}


def test_two_tiers_means_both_and_nothing_else():
    """The request this exists for: A and B, never C."""
    assert _cohort(["A", "B"]) == {"A", "B"}


@pytest.mark.parametrize("given,expected", [
    ("A", ["A"]),
    ("A,B", ["A", "B"]),
    ("a, b", ["A", "B"]),
    ("A,B,C", ["A", "B", "C"]),
])
def test_the_flag_parses_a_list(given, expected, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["deepread_run.py", "--tier", given,
                                      "--dry-run"])
    assert D.parse_tiers(D.build_parser().parse_args().tier) == expected


def test_an_unknown_tier_is_refused_rather_than_silently_dropped():
    """A typo that empties the cohort should not look like a finished read."""
    with pytest.raises(SystemExit):
        D.parse_tiers("A,Z")


def test_tier_a_is_still_read_first_within_a_mixed_cohort():
    """Tier A carries the disclosures, so an interrupted run has value.

    The ordering lived in main() before A and B ever shared a cohort,
    which is exactly when it starts to matter.
    """
    rows = [{"tier": t, "application_ref": "Test/1", "sampled_out": False}
            for t in ("B", "C", "A", "skip")]
    rows.sort(key=D.cohort_sort_key)
    assert [r["tier"] for r in rows] == ["A", "B", "C", "skip"]
