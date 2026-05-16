"""Editorial cohort structure loader.

Reads `data/priors/cohorts.yaml` and provides typed lookups for the
export renderer. The YAML defines three things:

  - `highlights`: hand-picked headline apps shown as a bullet list at
    the top of the export.
  - `cohorts`: themed groupings (Humber Estuary cluster, Greystoke
    sites, Ark Project Union, etc.). The ORDER of cohorts in the YAML
    determines their editorial priority and resolves multi-cohort
    membership for individual apps (an app's "primary cohort" is the
    first cohort listing it; subsequent cohorts render the app as a
    cross-reference rather than a full card).
  - `exclusions`: applications confirmed NOT to be data centres after
    deep-read. Filtered from the primary worklist count via the
    `exclude:*` tag in `applications.discovered_via` (see
    `scripts/tag_cohorts.py`).

Module-cached: the YAML is parsed once on first access; downstream
callers (worklist.fetch, export.render_markdown) get cheap dict lookups.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

YAML_PATH = Path(__file__).parent.parent / "data" / "priors" / "cohorts.yaml"


@dataclass(frozen=True)
class Cohort:
    name: str
    display_name: str
    description: str
    apps: tuple[str, ...]


@dataclass(frozen=True)
class Highlight:
    app: str
    one_liner: str


@dataclass(frozen=True)
class Exclusion:
    app: str
    reason: str
    notes: str


@functools.lru_cache(maxsize=1)
def _config() -> dict:
    if not YAML_PATH.exists():
        return {"highlights": [], "cohorts": [], "exclusions": []}
    return yaml.safe_load(YAML_PATH.read_text()) or {}


@functools.lru_cache(maxsize=1)
def cohorts() -> tuple[Cohort, ...]:
    """All cohorts in the order they appear in the YAML — the order
    determines editorial priority and primary-cohort resolution."""
    return tuple(
        Cohort(
            name=c["name"],
            display_name=c.get("display_name", c["name"]),
            description=c.get("description", "").strip(),
            apps=tuple(c.get("apps", [])),
        )
        for c in _config().get("cohorts", [])
    )


@functools.lru_cache(maxsize=1)
def _cohort_index() -> dict[str, int]:
    """Cohort name → position in YAML order (used for primary-cohort
    resolution: the cohort with the lowest index wins)."""
    return {c.name: i for i, c in enumerate(cohorts())}


@functools.lru_cache(maxsize=1)
def highlights() -> tuple[Highlight, ...]:
    return tuple(
        Highlight(app=h["app"], one_liner=h.get("one_liner", "").strip())
        for h in _config().get("highlights", [])
    )


@functools.lru_cache(maxsize=1)
def exclusions() -> tuple[Exclusion, ...]:
    return tuple(
        Exclusion(
            app=e["app"],
            reason=e.get("reason", "unknown"),
            notes=e.get("notes", "").strip(),
        )
        for e in _config().get("exclusions", [])
    )


def cohort_by_name(name: str) -> Cohort | None:
    for c in cohorts():
        if c.name == name:
            return c
    return None


def resolve_membership(discovered_via: list[str] | None) -> tuple[str | None, list[str]]:
    """Given an app's `discovered_via` array, return `(primary_cohort, [other_cohorts])`.

    Primary cohort = the cohort name whose position in the YAML is earliest
    among the `cohort:<name>` tags on this app. `other_cohorts` lists every
    other cohort the app belongs to, also in YAML order. Returns
    `(None, [])` if the app isn't in any cohort.
    """
    if not discovered_via:
        return (None, [])
    names: list[tuple[int, str]] = []
    idx = _cohort_index()
    for tag in discovered_via:
        if not tag.startswith("cohort:"):
            continue
        name = tag.split(":", 1)[1]
        if name in idx:
            names.append((idx[name], name))
    if not names:
        return (None, [])
    names.sort()
    primary = names[0][1]
    others = [name for _, name in names[1:]]
    return (primary, others)
