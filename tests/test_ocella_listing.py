"""What an Ocella documents listing IS, before anything is parsed out of
it (the empty-listing item; Idox learned it on 2026-09-10). Two captured
bodies from `source_snapshots` pin the split: Havering's page says in
words that there are no documents, and Hillingdon's smallest real page
lists them."""
from pathlib import Path

from dcp.sources import ocella

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ocella"


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_a_populated_listing_is_a_listing():
    kind, detail, links = ocella.classify_listing(
        _fixture("hillingdon_populated.html"),
        base_url="https://planning.hillingdon.gov.uk/OcellaWeb/showDocuments")
    assert kind == "populated" and links and "listed" in detail


def test_an_empty_listing_is_recognised_by_the_portals_own_sentence():
    kind, detail, links = ocella.classify_listing(
        _fixture("havering_empty.html"),
        base_url="https://development.havering.gov.uk/OcellaWeb/showDocuments")
    assert kind == "empty" and links == []
    assert "no documents for this section" in detail


def test_a_refusal_page_is_not_an_empty_register():
    body = "<html><body>" + "<p>chrome</p>" * 100 + "<p>Permission Denied</p></body></html>"
    kind, detail, _ = ocella.classify_listing(body, base_url="https://x")
    assert kind == "refused" and "refusal page" in detail


def test_no_links_and_no_sentence_never_settles():
    body = "<html><body><p>No documents</p>" + "<p>site chrome</p>" * 100 + "</body></html>"
    kind, _, _ = ocella.classify_listing(body, base_url="https://x")
    assert kind == "unrecognised"


def test_a_body_under_the_floor_is_nothing():
    kind, _, _ = ocella.classify_listing("<html></html>", base_url="https://x")
    assert kind == "tiny"
