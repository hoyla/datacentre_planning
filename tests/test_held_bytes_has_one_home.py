"""`repo.held_bytes` is the one query that says what a run already holds.

Its docstring says "six adapters carried the same three-line rule; this
is the one place it lives now" — and four docstore scripts kept the
older inline query, without the clause that keeps a zero-byte row from
counting as held (found 2026-09-16). This is the rule over the tree,
in the shape of tests/test_drive_url_one_shape.py: nothing but
dcp/repo.py may spell the query, and a file that does is named.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = (sorted((ROOT / "scripts").glob("*.py"))
         + sorted((ROOT / "dcp").rglob("*.py")))
ALLOWED = {"dcp/repo.py"}
SHAPE = "SELECT url, bytes_path FROM documents"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_file_asks_what_is_held_by_itself(path: Path):
    rel = str(path.relative_to(ROOT))
    if rel in ALLOWED:
        pytest.skip("the one place the query lives")
    offenders = [(i, line.strip()) for i, line in
                 enumerate(path.read_text().splitlines(), 1) if SHAPE in line]
    assert not offenders, (
        f"{rel} asks the documents table what is held itself; use "
        f"repo.held_bytes, which knows an empty hash is not held: {offenders}")


def test_the_tree_was_actually_globbed():
    assert any("scripts/" in str(p) for p in FILES)
    assert any("dcp/" in str(p) for p in FILES)
    assert any(str(p.relative_to(ROOT)) in ALLOWED for p in FILES)
