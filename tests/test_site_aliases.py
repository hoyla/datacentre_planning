"""The alias prior's contract: beside the derived name, never silently off.

The design is issue #169's: a curated alias displays everywhere, the
derived default stays visible on the site's own page, and — the part
these tests exist for — an alias whose site key is no longer live
fails the build rather than quietly not applying, because a key
changes when its cluster's anchor changes and the misleading derived
name coming back unannounced is the regression nobody would see.
"""

from __future__ import annotations

import pytest

from dcp import site_aliases


def _write(tmp_path, body: str):
    p = tmp_path / "site_aliases.yaml"
    p.write_text(body)
    return p


def test_loads_key_to_alias(tmp_path):
    p = _write(tmp_path, """
aliases:
  - site_key: SITE-A/1
    alias: West Burton Power Station
    source: the documents name it
""")
    assert site_aliases.load_aliases(p) == {
        "SITE-A/1": "West Burton Power Station"}


def test_absent_file_is_no_aliases(tmp_path):
    assert site_aliases.load_aliases(tmp_path / "missing.yaml") == {}


def test_empty_alias_fails(tmp_path):
    p = _write(tmp_path, """
aliases:
  - site_key: SITE-A/1
    alias: "  "
    source: x
""")
    with pytest.raises(ValueError, match="empty alias"):
        site_aliases.load_aliases(p)


def test_duplicate_key_fails(tmp_path):
    p = _write(tmp_path, """
aliases:
  - site_key: SITE-A/1
    alias: One
    source: x
  - site_key: SITE-A/1
    alias: Two
    source: x
""")
    with pytest.raises(ValueError, match="duplicate"):
        site_aliases.load_aliases(p)


def test_alias_for_a_dead_key_fails_the_build():
    with pytest.raises(ValueError, match="not live"):
        site_aliases.require_live({"SITE-GONE/1": "Anything"},
                                  live_keys={"SITE-A/1"})


def test_live_aliases_pass():
    site_aliases.require_live({"SITE-A/1": "Name"},
                              live_keys={"SITE-A/1", "SITE-B/2"})


def test_the_committed_file_parses_and_names_only_wellformed_entries():
    """The real priors file loads under the same contract the exporters
    apply. Liveness is checked against the database at build time, not
    here — a unit test has no corpus."""
    aliases = site_aliases.load_aliases()
    for key, alias in aliases.items():
        assert key.startswith(("SITE-", "PTNO-")), key
        assert len(alias) > 3, (key, alias)


def test_the_priors_path_is_absolute_so_a_build_cannot_lose_the_aliases():
    """The path resolves against the package root, not the cwd.

    The mechanism is pinned rather than the number of aliases, which
    grows. A relative default is invisible from inside the module:
    `load_aliases` returns {} for an absent file by design, so from
    another directory nothing applies and nothing complains.
    """
    assert site_aliases.ALIASES_PATH.is_absolute()


def test_the_prior_loads_the_same_from_another_working_directory(
        tmp_path, monkeypatch):
    """The failure this is for: a build run from anywhere else.

    Asserts the key *set* against a live read rather than a count, so
    curation can add aliases without flaking the test.
    """
    from_root = site_aliases.load_aliases()
    assert from_root, "the committed prior is not empty"

    monkeypatch.chdir(tmp_path)
    assert set(site_aliases.load_aliases()) == set(from_root)


def test_an_empty_load_cannot_satisfy_require_live(tmp_path, monkeypatch):
    """The vacuous pass is the reason the relative default mattered.

    `require_live` checks the keys it is handed, so a load that
    returned nothing agreed with *any* corpus — including one holding
    none of these sites. The guard written to stop an alias silently
    ceasing to apply was the thing reporting clean while every alias
    silently ceased to apply. From another directory it must now
    raise, exactly as it does from the root.
    """
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="not live"):
        site_aliases.require_live(site_aliases.load_aliases(), live_keys=set())
