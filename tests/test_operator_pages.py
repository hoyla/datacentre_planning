"""Tests for the operator-pages prior and its loading contract.

The prior puts links on the one page a reporter reads, labelled by the
audience they address, so the failures that matter are quiet ones: an
entry that half-loads, a link whose site key silently stopped applying,
a kind the reader would mislabel. Everything here fails loudly instead.
"""

from __future__ import annotations

import textwrap

import pytest

from dcp import operator_pages as op


def _write(tmp_path, body):
    p = tmp_path / "operator_pages.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_loads_pages_in_order_and_keyed_by_site():
    pages = op.load_pages()
    assert pages, "the real prior should load"
    # Every entry the loader accepted is well-formed by construction;
    # spot-check the double-page site keeps both kinds and file order.
    both = pages.get("PTNO-12671637")
    assert both and [p["kind"] for p in both] == ["corporate", "consultation"]


def test_real_prior_names_only_wellformed_urls():
    for key, entries in op.load_pages().items():
        for e in entries:
            assert e["url"].startswith("https://"), (key, e["url"])


def test_unknown_kind_fails_loudly(tmp_path):
    p = _write(tmp_path, """
        pages:
          - site_key: PTNO-1
            url: https://example.com/
            kind: marketing
    """)
    with pytest.raises(ValueError, match="kind"):
        op.load_pages(p)


def test_non_http_url_fails_loudly(tmp_path):
    p = _write(tmp_path, """
        pages:
          - site_key: PTNO-1
            url: ftp://example.com/
            kind: corporate
    """)
    with pytest.raises(ValueError, match="non-http"):
        op.load_pages(p)


def test_duplicate_page_for_a_site_fails_loudly(tmp_path):
    p = _write(tmp_path, """
        pages:
          - site_key: PTNO-1
            url: https://example.com/
            kind: corporate
          - site_key: PTNO-1
            url: https://example.com/
            kind: consultation
    """)
    with pytest.raises(ValueError, match="duplicate"):
        op.load_pages(p)


def test_dead_site_key_stops_the_build():
    """Same contract as site_aliases: silence is the failure mode.

    A key changes when its cluster's anchor changes, and a link that
    quietly stopped applying would drop the operator's own account of
    a scheme from the page.
    """
    pages = {"PTNO-GONE": [{"url": "https://example.com/",
                            "kind": "corporate", "label": ""}]}
    with pytest.raises(ValueError, match="PTNO-GONE"):
        op.require_live(pages, {"PTNO-LIVE"})
    op.require_live(pages, {"PTNO-GONE"})  # live key passes silently


def test_link_text_states_the_audience_and_only_needed_labels():
    assert op.link_text({"url": "u", "kind": "corporate", "label": ""}) == (
        "Operator’s website")
    assert op.link_text({"url": "u", "kind": "consultation", "label": ""}) == (
        "Public consultation website")
    assert op.link_text({"url": "u", "kind": "corporate",
                         "label": "LON4"}) == "Operator’s website (LON4)"


def test_missing_file_is_an_empty_prior(tmp_path):
    assert op.load_pages(tmp_path / "absent.yaml") == {}


def test_the_priors_path_is_absolute_so_a_build_cannot_lose_the_links():
    """The path resolves against the package root, not the cwd.

    The mechanism is pinned rather than the number of pages, which
    grows. A relative default is invisible from inside the module:
    `load_pages` returns {} for an absent file by design, so from
    another directory every link vanishes and nothing complains.
    """
    assert op.PAGES_PATH.is_absolute()


def test_the_prior_loads_the_same_from_another_working_directory(
        tmp_path, monkeypatch):
    """The failure this is for: a build run from anywhere else.

    Asserts the key *set* against a live read rather than a count, so
    curation can add pages without flaking the test.
    """
    from_root = op.load_pages()
    assert from_root, "the committed prior is not empty"

    monkeypatch.chdir(tmp_path)
    assert set(op.load_pages()) == set(from_root)


def test_an_empty_load_cannot_satisfy_require_live(tmp_path, monkeypatch):
    """The vacuous pass is the reason the relative default mattered.

    `require_live` checks the keys it is handed, so a load that
    returned nothing agreed with *any* corpus. The guard written to
    stop one link silently ceasing to apply was reporting clean while
    every link silently ceased to apply — and the operator's own
    account of a scheme is what drops off the page. From another
    directory it must now raise, exactly as it does from the root.
    """
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="not live"):
        op.require_live(op.load_pages(), set())
