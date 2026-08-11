"""No tool may default to a named release.

A default that names one release is correct for exactly that release and
silently wrong from the next onwards. Two were live on 2026-08-11:

  build_drive_staging.py  --release-dir  data/exports/phase2_build
  sheet_sync.py           --workbook     .../dc_handover_phase2.xlsx

The first staged phase 2's workbook and database beside 2.1's per-site
files, in a line of output that reads like success. The second would
have written phase 2's numbers into the Google Sheet people are working
in — refreshed in place so their formatting survives, which means a
stale Sheet is indistinguishable from a live one. export_reader.py had
the same shape twice over, defaulting to `phase1_build` and to phase
"1", which would have stamped the front page "phase 1 release".

Neither needed anyone to type the mistake: `overnight_chain.sh` and
`phase1_finalise.sh` both call these bare.

A default may describe how to FIND the current release. It must never
name one. dcp/release.py is the one implementation of finding it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPTS = sorted(Path("scripts").glob("*.py")) + sorted(Path("dcp").glob("*.py"))

# `phase2_build`, `phase2.1_build`, `dc_phase2.duckdb`, `dc_handover_phase1.xlsx`
NAMED_RELEASE = re.compile(r"phase\d[\d.]*(?:_build|\.duckdb|\.xlsx)")

# Where naming a release is legitimate: the module whose job is finding
# releases (its fallbacks), and anything purely explanatory.
ALLOWED = {"dcp/release.py"}


def _default_lines(path: Path) -> list[tuple[int, str]]:
    """Lines that set an argparse default or a module-level DEFAULT_*."""
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue          # a comment may cite the historical mistake
        if "default=" in line or re.match(r"^DEFAULT_[A-Z_]* *=", stripped):
            out.append((i, line))
    return out


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: str(p))
def test_no_default_names_a_release(path):
    if str(path) in ALLOWED:
        pytest.skip("dcp/release.py is where finding a release lives")
    offenders = [(i, l.strip()) for i, l in _default_lines(path)
                 if NAMED_RELEASE.search(l)]
    assert not offenders, (
        f"{path} defaults to a named release, which is wrong from the next "
        f"release onwards — derive it from dcp/release.py instead:\n" +
        "\n".join(f"  line {i}: {l}" for i, l in offenders))


def test_the_finder_actually_finds_the_newest():
    from dcp import release
    d = release.latest_release_dir()
    if d is None:
        pytest.skip("no release folders in this checkout")
    assert d.is_dir()
    others = [x for x in release.release_dirs() if x != d]
    for o in others:
        assert d.stat().st_mtime >= o.stat().st_mtime


def test_phase_is_read_from_the_folder_name_not_guessed():
    from dcp import release
    assert release.phase_of(Path("data/exports/phase2.1_build")) == "2.1"
    assert release.phase_of(Path("data/exports/phase1_build")) == "1"
    # Anything unconventional yields None rather than a confident wrong
    # answer — the phase stamps the reader's title.
    assert release.phase_of(Path("data/exports/adhoc_build")) is None
    assert release.phase_of(None) is None


def test_the_consumers_use_the_finder():
    """Three scripts had this defect; all three must now derive it."""
    for name in ("scripts/build_drive_staging.py", "scripts/sheet_sync.py",
                 "scripts/export_reader.py"):
        src = Path(name).read_text()
        assert "release" in src and (
            "latest_release_dir" in src or "latest_workbook" in src), (
            f"{name} does not derive its release from dcp/release.py")
