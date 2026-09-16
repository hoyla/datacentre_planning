"""The reader and the workbook refuse the same dead curation.

Five curated priors are keyed by site: aliases, operator pages, facility
rosters, the snapshots those rosters cite, and campus-scope decisions.
The reader build calls a `require_*` guard for each before rendering;
until 2026-09-16 the workbook build called two of the five, so a dead
key in `site_facilities.yaml` failed one artefact and shipped in the
other. Both scripts need a corpus to run, so this asserts the set of
guards each names rather than driving a build; a new guard added to one
script and not the other fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = re.compile(r"\b(_\w+)\.(require_live|require_held_snapshots)\(")
MODULE = re.compile(r"from dcp import (\w+) as (_\w+)")


def _guards(script: str) -> set[tuple[str, str]]:
    src = (ROOT / "scripts" / script).read_text()
    aliases = {alias: module for module, alias in MODULE.findall(src)}
    found = {(aliases.get(alias, alias), fn) for alias, fn in GUARD.findall(src)}
    assert found, f"{script} names no liveness guard at all"
    return found


def test_the_workbook_runs_every_liveness_guard_the_reader_runs():
    reader, workbook = _guards("export_reader.py"), _guards("export_handover.py")
    assert reader <= workbook, (
        f"the reader refuses on {sorted(reader - workbook)} and the workbook "
        f"does not; a dead site key would ship in the xlsx")


def test_the_guards_are_the_five_the_priors_need():
    assert _guards("export_reader.py") == {
        ("site_aliases", "require_live"), ("operator_pages", "require_live"),
        ("site_facilities", "require_live"),
        ("site_facilities", "require_held_snapshots"),
        ("campus_scope", "require_live")}
