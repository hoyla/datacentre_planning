"""Where `build_clusters` looks for its priors.

The clustering priors are the only thing standing between the 1 km
radius and the campuses it would otherwise weld together:
`inferred_coords.yaml` moves a Barbour pin its own record contradicts,
and `site_partitions.yaml` draws the boundaries proximity cannot see.
Both loaders return empty for an absent file, and both guards beside
them — unknown Ptno, unknown partitioned record — iterate the keys
they were handed, so an empty load gives each of them nothing to
object to.

That combination is what makes the directory a correctness question
rather than a convenience one. Measured before the fix: from the
repository root 29 `ref` pins, 2 `ptno` pins, 476 partitioned
applications and 34 partitioned projects; from anywhere else, none of
each, no error raised, and a materialise that re-merges the campuses
and changes site keys while reporting clean.

These tests pin the mechanism — an absolute default, and the same keys
read from a different working directory — never the counts, which move
with the priors.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from dcp import sites

# Built here rather than read from `sites.ROOT`, so the comparisons
# below still describe the repository when run against a module whose
# default has not been fixed.
REPO_DATA = Path(sites.__file__).resolve().parent.parent / "data"


def _default_data_dir() -> Path:
    return inspect.signature(sites.build_clusters).parameters["data_dir"].default


def test_the_data_dir_default_is_absolute():
    """`build_clusters` is the only caller of both loaders.

    Its default is where a materialise gets its priors from, so the
    default is the thing to pin. `data_dir` stays a parameter — three
    test modules pass it explicitly — and only the default moves.
    """
    default = _default_data_dir()
    assert default.is_absolute()
    assert default == sites.ROOT / "data"


def test_the_coordinate_pins_load_the_same_from_another_directory(
        tmp_path, monkeypatch):
    """A Barbour pin in the wrong place merges two unrelated campuses.

    Wapseys Wood is the case: Barbour placed the scheme 8.5 km from the
    address on its own record, inside another cluster's radius, and the
    `ptno:` entry is what moves it back. Losing the file silently puts
    that pin back at clustering time.
    """
    root_ref, root_ptno = sites._load_inferred_coords(REPO_DATA)
    assert root_ref and root_ptno, "the committed prior holds pins of both kinds"

    monkeypatch.chdir(tmp_path)
    # The historical default, kept to show what it did rather than only
    # that it is gone: no file, no pins, and nothing raised.
    assert sites._load_inferred_coords(Path("data")) == ({}, {})

    by_ref, by_ptno = sites._load_inferred_coords(_default_data_dir())
    assert set(by_ref) == set(root_ref)
    assert set(by_ptno) == set(root_ptno)


def test_the_partitions_load_the_same_from_another_directory(
        tmp_path, monkeypatch):
    """Partitions are the boundaries; empty means every one is gone.

    An absent file is indistinguishable from an unpartitioned corpus,
    and the guard below it only checks the keys it was handed — so the
    run merges the campuses and reports clean.
    """
    root_apps, root_projs = sites._load_site_partitions(REPO_DATA)
    assert root_apps and root_projs, "the committed prior partitions both kinds"

    monkeypatch.chdir(tmp_path)
    assert sites._load_site_partitions(Path("data")) == ({}, {})

    app_part, proj_part = sites._load_site_partitions(_default_data_dir())
    assert set(app_part) == set(root_apps)
    assert set(proj_part) == set(root_projs)
