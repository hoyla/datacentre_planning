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

# Resolved against the package root, never the working directory. Every
# tool in the release chain reads this location to decide what to build
# — the newest release folder, the phase it stamps, the Drive sync
# ledger, the staging tree, the release diff — so it is one repository
# location and not "wherever the command was run". Relative, a build
# from any other directory found no release folder, fell through to
# the phase-1 fallbacks below-stairs and stamped the reader "phase 1"
# into a folder several releases old, reporting success (R7,
# docs/HANDOVER_RUNG_RELEASE.md). Explicit --out/--release-dir flags
# still win everywhere.
ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "data" / "exports"

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


def current_release_dir(explicit: Path | None = None) -> Path:
    """The release folder a tool should act on, or a refusal.

    An explicit folder wins and must exist. Otherwise the newest release
    folder — and if there is none, the tool stops and says so rather
    than inventing one: a fresh checkout has no releases, and the phase
    a reader stamps or the artefacts a staging tree carries are not
    things to guess. The scripts used to fall back to `phase1_build`
    here, which is correct for exactly one release and silently wrong
    from the next onwards.
    """
    if explicit is not None:
        if not explicit.is_dir():
            raise SystemExit(
                f"release folder {explicit} is not a directory; nothing "
                f"to act on")
        return explicit
    latest = latest_release_dir()
    if latest is None:
        raise SystemExit(
            f"no release folder (*_build) under {EXPORTS} to derive the "
            f"current release from; pass the folder explicitly")
    return latest


def current_phase(explicit: str | None,
                  release_dir: Path | None) -> str:
    """The phase a tool should stamp, or a refusal.

    Explicit wins; else the phase read from the release folder's name;
    else stop. Never "1": the phase stamps the reader's title, its
    header and the database's filename, and a default that names a
    phase is right for one release and wrong for every later one.
    """
    if explicit:
        return str(explicit)
    derived = phase_of(release_dir)
    if derived:
        return derived
    where = release_dir if release_dir is not None else EXPORTS
    raise SystemExit(
        f"cannot derive a phase from {where}; pass --phase explicitly "
        f"(it stamps the title, the header and the database filename)")


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


# Suffixes of a published artefact at the Drive tree root. The root
# accumulates these on purpose — phase 1's workbook has to keep
# resolving after phase 2 ships beside it — so the staging builder
# carries them across a rebuild and `drive_sync.py --prune` declines to
# bin them. Everything else at the root is regenerated or dropped, and
# since 2026-09-02 that includes the reader: nobody read it on Drive
# (Luke), git holds every release's index.html and the container image
# holds the one deployed, so it is not staged and a copy already on
# Drive is pruned like any other file. The workbook and the database
# stay (Luke, the same evening: "should definitely stay" — they are what
# the team's R user works from, and Drive is where that person finds them).
RELEASED_SUFFIXES = (".xlsx", ".duckdb")


def is_released_root_artefact(rel: str, root_dir) -> bool:
    """True for a file at the tree root whose suffix marks a release."""
    from pathlib import Path as _P
    q = _P(rel)
    return q.parent == _P(root_dir) and q.suffix.lower() in RELEASED_SUFFIXES
