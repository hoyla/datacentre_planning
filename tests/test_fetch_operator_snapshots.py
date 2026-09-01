"""The snapshot fetcher's write decision, with no network in it.

The store is append-only (WP-A of docs/HANDOVER_SNAPSHOT_CHAIN.md), so
what matters here is when a fetch adds a file and what it calls it. Both
are pure functions of the bytes served and the store already held, which
is why they can be tested without touching an operator's website:
`held_digest` reads what the newest held file says it is, and `next_name`
allocates the name a change gets written to.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fetcher():
    spec = importlib.util.spec_from_file_location(
        "fetch_operator_snapshots",
        ROOT / "scripts" / "fetch_operator_snapshots.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(dirpath, name, digest="a" * 64, kind="html"):
    p = dirpath / name
    p.write_text(f"# url: https://example.com\n\n# fetched: 2026-08-30\n\n"
                 f"# sha256({kind}): {digest}\n\n## STRUCTURED\n\n(none)\n\n"
                 f"## VISIBLE TEXT\n\nthe page")
    return p


def test_the_held_digest_is_read_from_the_newest_file(tmp_path):
    f = _fetcher()
    _write(tmp_path, "op.2026-08-20.txt", digest="b" * 64)
    _write(tmp_path, "op.2026-08-28.txt", digest="c" * 64)
    from dcp.capacity_claims import snapshot_path
    assert f.held_digest(snapshot_path("op", tmp_path)) == "c" * 64


def test_a_pdf_snapshot_records_its_digest_under_its_own_spelling(tmp_path):
    """`# sha256(pdf):` since a spec sheet became a page like any other
    (PR #310); a skip decision that only knew `html` would re-write
    every PDF on every run."""
    f = _fetcher()
    p = _write(tmp_path, "op.2026-09-01.txt", digest="d" * 64, kind="pdf")
    assert f.held_digest(p) == "d" * 64


def test_an_unreadable_header_never_matches(tmp_path):
    """None is not equal to any digest, so a file the fetcher cannot
    make sense of causes a write rather than a silent skip — an
    unrecognised file must never be mistaken for a match."""
    f = _fetcher()
    p = tmp_path / "op.2026-08-30.txt"
    p.write_text("nothing that looks like a snapshot")
    assert f.held_digest(p) is None
    assert f.held_digest(None) is None


def test_the_first_change_of_a_day_takes_the_plain_dated_name(tmp_path):
    f = _fetcher()
    assert f.next_name("op", "2026-09-01", tmp_path) == "op.2026-09-01.txt"


def test_a_second_change_the_same_day_is_suffixed(tmp_path):
    f = _fetcher()
    _write(tmp_path, "op.2026-09-01.txt")
    assert f.next_name("op", "2026-09-01", tmp_path) == "op.2026-09-01_2.txt"
    _write(tmp_path, "op.2026-09-01_2.txt")
    assert f.next_name("op", "2026-09-01", tmp_path) == "op.2026-09-01_3.txt"


def test_a_same_day_suffix_never_predates_the_reading_it_follows(tmp_path):
    """The property the whole naming scheme rests on: sorting the names
    lexicographically has to put them in the order they were fetched.
    A `-2` suffix would fail this, because `-` sorts before `.`."""
    f = _fetcher()
    names = []
    for _ in range(3):
        n = f.next_name("op", "2026-09-01", tmp_path)
        _write(tmp_path, n)
        names.append(n)
    assert names == sorted(names)
    assert names[0] < f.next_name("op", "2026-09-02", tmp_path)


def test_a_page_that_is_a_pdf_is_sniffed_not_taken_from_the_url():
    f = _fetcher()
    assert f.is_pdf(b"%PDF-1.7 ...") is True
    assert f.is_pdf(b"<!DOCTYPE html>") is False
