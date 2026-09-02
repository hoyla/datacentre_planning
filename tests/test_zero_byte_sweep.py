"""The zero-byte sweep finds an empty file and only an empty file.

`repo.zero_byte_files` is the corpus-wide form of the fetch guard: the
guard stops an empty body being recorded, this notices one that is
already there (three are, from before the guard existed — HISTORY, 2.8).
`build_drive_staging.py` runs it over the tree it writes every release,
so the check has to be right about both directions: an empty file is
reported, and a file with bytes — however few — is not.
"""

from __future__ import annotations

from pathlib import Path

from dcp import repo


def test_reports_the_empty_file_and_nothing_else(tmp_path: Path):
    site = tmp_path / "sites" / "PTNO-1 — Somewhere" / "Council_25_0001"
    site.mkdir(parents=True)
    (site / "001 - Planning Statement.pdf").write_bytes(b"%PDF-1.4 real bytes")
    (site / "002 - Consultation Response.pdf").write_bytes(b"")
    (site / "003 - Decision Notice.pdf").write_bytes(b"\x00")   # one byte is not empty
    (tmp_path / "adjacent_power" / "Council_25_0002").mkdir(parents=True)
    (tmp_path / "adjacent_power" / "Council_25_0002" / "_index.md").write_text("# x\n")
    (tmp_path / "adjacent_power" / "Council_25_0002" / "001 - Section 106.pdf").write_bytes(b"")

    found = repo.zero_byte_files(tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in found] == [
        "adjacent_power/Council_25_0002/001 - Section 106.pdf",
        "sites/PTNO-1 — Somewhere/Council_25_0001/002 - Consultation Response.pdf",
    ]


def test_a_clean_tree_reports_nothing(tmp_path: Path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "sub").mkdir()            # an empty DIRECTORY is not a file
    assert repo.zero_byte_files(tmp_path) == []


def test_the_staging_build_runs_the_sweep_over_the_tree_it_wrote():
    """The durable home is the release chain, not a script somebody
    remembers. Read the source rather than run a build: the call has to
    be there, after the tree exists, printing what it found."""
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "build_drive_staging.py").read_text()
    assert "repo.zero_byte_files(" in src
    assert "zero-byte documents in the tree" in src
    # after the swap, so it sweeps what was actually written
    assert src.index("swap_in(out, final") < src.index("repo.zero_byte_files(")
