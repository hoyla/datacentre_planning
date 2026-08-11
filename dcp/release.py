"""Which release the tools should act on when nobody says.

Every exporter and sync takes a path, and every one of them had a
default naming a specific release. That is a default which is correct
for exactly one release and silently wrong from the next one onwards,
and on 2026-08-11 two of them were:

  build_drive_staging.py  --release-dir  data/exports/phase2_build
  sheet_sync.py           --workbook     .../dc_handover_phase2.xlsx

The first staged phase 2's workbook and database beside 2.1's per-site
files and announced it in a line that reads like success. The second
would have written phase 2's numbers into the Google Sheet people are
working in — refreshed in place precisely so their formatting and
annotations survive, which means a stale Sheet looks exactly like a live
one. Both were called bare by the automated chains
(`overnight_chain.sh`, `phase1_finalise.sh`), so neither needed anyone
to type the mistake.

The rule this module exists to enforce: **a default may describe how to
find the current release, but must never name one.** Explicit flags
still win, and the runbook passes them; this is what happens when they
are omitted.

tests/test_release_defaults.py fails the build if a release path or
phase number reappears as a hardcoded default anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

EXPORTS = Path("data/exports")

# `phase2.1_build` -> `2.1`. Anything else keeps its whole stem, so an
# unconventional folder name degrades to something visible rather than
# to a wrong number.
_PHASE_RE = re.compile(r"^phase([0-9][0-9.]*)_build$")


def release_dirs() -> list[Path]:
    """Release folders under data/exports, newest first."""
    return sorted((d for d in EXPORTS.glob("*_build") if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)


def latest_release_dir(fallback: Path | None = None) -> Path | None:
    """The most recently written release folder, or `fallback`.

    Mtime rather than a version sort: a rebuild of an older release is
    still the thing most recently produced, and guessing which of
    `phase2_build` and `phase2.1_build` is "later" from the name alone
    is how this goes wrong in the other direction.
    """
    dirs = release_dirs()
    return dirs[0] if dirs else fallback


def latest_workbook(fallback: Path | None = None) -> Path | None:
    """The workbook from the newest release folder that has one."""
    for d in release_dirs():
        books = sorted(d.glob("*.xlsx"))
        if books:
            return books[0]
    return fallback


def phase_of(release_dir: Path | None) -> str | None:
    """`2.1` from `data/exports/phase2.1_build`, else None.

    Never guessed at from anything but the folder name. The phase stamps
    the reader's title and the database's filename, so inferring it from
    the corpus or the date would put a confident wrong answer on the
    front page.
    """
    if release_dir is None:
        return None
    m = _PHASE_RE.match(release_dir.name)
    return m.group(1) if m else None
