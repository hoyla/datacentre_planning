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
