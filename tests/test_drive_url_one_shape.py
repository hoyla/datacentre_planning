"""A Drive URL is built in one place.

`dcp/drive.py` holds the two shapes — `/file/d/<id>/view` and
`/drive/folders/<id>` — and `file_url`, `folder_url` and `file_url_sql`
are how the rest of the project gets one. Until 2026-09-02 three scripts
spelled the file form themselves and two ledger maps the folder form;
each was correct, and each was a place the shape could drift on its own.
This asserts the rule over the whole tree rather than the instances,
the way `test_release_defaults.py` does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = (sorted((ROOT / "scripts").glob("*.py"))
         + sorted((ROOT / "dcp").glob("*.py")))
ALLOWED = {"dcp/drive.py"}
SHAPES = ("drive.google.com/file/d/", "drive.google.com/drive/folders/")


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_file_spells_a_drive_url_itself(path: Path):
    rel = str(path.relative_to(ROOT))
    if rel in ALLOWED:
        pytest.skip("the one place the shape lives")
    text = path.read_text()
    offenders = [(i, line.strip()) for i, line in enumerate(text.splitlines(), 1)
                 if any(shape in line for shape in SHAPES)]
    assert not offenders, (
        f"{rel} builds a Drive URL itself; use dcp.drive.file_url / "
        f"folder_url / file_url_sql: {offenders}")


def test_the_tree_was_actually_globbed():
    """A relative glob from the wrong directory parametrises nothing and
    passes — the guard skipping itself. Resolved against the root, both
    directories must contribute."""
    assert any("scripts/" in str(p) for p in FILES)
    assert any("dcp/" in str(p) for p in FILES)
