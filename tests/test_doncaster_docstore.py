"""Doncaster runs Newport's document store, and is read as one.

`planning.doncaster.gov.uk`'s Idox documents tab refuses with an HTTP
200; the register's External Documents tab links to
`necdm.doncaster.gov.uk`, the same Public Access document module as
Newport's — same search page, same `var model` page model, same
ViewDocument URL — under `FileSystemId=DP`. The Newport script's
`STORES` table names both; the council prefix of the reference picks
the store, and a council without an entry cannot be fetched from the
wrong store by accident. The listing audit and the refetch route both
councils the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dcp import relist_audit as ra

ROOT = Path(__file__).resolve().parent.parent
newport = ra._newport_module()
FIXTURE = (ROOT / "tests" / "fixtures" / "doncaster" / "19_01957_FUL_store.html").read_text()


def test_the_council_prefix_picks_the_store():
    assert newport.council_of("Doncaster/19/01957/FUL") == "Doncaster"
    assert newport.search_url("19/01957/FUL", "Doncaster") == (
        "https://necdm.doncaster.gov.uk/PublicAccess_LIVE/SearchResult/"
        "RunThirdPartySearch?FileSystemId=DP&FOLDER1_REF=19/01957/FUL")
    assert newport.view_url("G1", "Doncaster").startswith("https://necdm.doncaster.gov.uk/")
    # Newport unchanged, by default and by name.
    assert newport.search_url("26/0191") == newport.search_url("26/0191", "Newport")
    assert newport.search_url("26/0191").startswith("https://documents.newport.gov.uk/")
    assert newport.view_url("G1") == f"{newport.VIEW_URL}?id=G1"


def test_a_council_without_a_store_is_refused():
    with pytest.raises(ValueError, match="Derby"):
        newport.council_of("Derby/19/01343/FUL")


def test_the_captured_doncaster_page_parses_with_the_newport_parser():
    docs = newport.parse_doc_list(FIXTURE)
    assert docs is not None and len(docs) == 16
    guid, kind = docs[0]
    assert len(guid) == 32 and kind


def test_the_audit_routes_doncaster_to_the_store_not_the_tab():
    url = ("https://planning.doncaster.gov.uk/online-applications/"
           "applicationDetails.do?activeTab=summary&keyVal=PW8FA7FXJSB00")
    assert ra.listing_family(url) == "doncaster_docstore"
    assert ra.listing_key(url, "doncaster_docstore") is None
    assert "doncaster_docstore" in ra.SUPPORTED
    assert ra.listing_family("https://publicaccess.newport.gov.uk/online-applications/x") == "newport_docstore"


def test_the_refetch_handles_both_stores():
    src = (ROOT / "scripts" / "relist_refetch.py").read_text()
    assert '"doncaster_docstore"' in src
    assert 't.adapter.endswith("_docstore")' in src


def test_the_store_table_and_the_audit_agree_on_every_council():
    """Every council in STORES has an audit host routed to
    `<council>_docstore`, and every such family is supported by the audit
    and handled by the refetch — a row added to one table and not the
    others would fetch from the store and audit the refusing tab."""
    from_stores = {f"{c.lower()}_docstore" for c in newport.STORES}
    from_hosts = set(ra.DOCSTORE_HOSTS.values())
    assert from_stores == from_hosts
    assert from_stores <= set(ra.SUPPORTED)
    src = (ROOT / "scripts" / "relist_refetch.py").read_text()
    for fam in from_stores:
        assert f'"{fam}"' in src
    assert len(newport.STORES) == 6
