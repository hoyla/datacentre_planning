"""What an Arcus application page IS, before anything is parsed out of it
(the empty-listing item; Idox learned it on 2026-09-10). Three captured
bodies from `source_snapshots` pin the split: Leicester lists documents,
Vale of Glamorgan's Documents tab says none were found, and Fylde served
its disclaimer interstitial in place of the application."""
from pathlib import Path

from dcp.sources import arcus

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "arcus"


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_a_populated_page_is_a_listing():
    kind, detail, links = arcus.classify_listing(
        _fixture("leicester_populated.html"),
        base_url="https://planning.leicester.gov.uk/Planning/Display/20251225")
    assert kind == "populated" and len(links) == 4 and "listed" in detail


def test_a_page_whose_links_sit_in_data_disabled_link_is_a_listing():
    """Fylde's rows carry the download URL in `data-disabled-link` and no
    href; four Fylde pages captured on 2026-08-06 listed documents and
    parsed to nothing until this shape was read."""
    kind, _detail, links = arcus.classify_listing(
        _fixture("fylde_populated_disabled_links.html"),
        base_url="https://pa.fylde.gov.uk/Planning/Display/23/0695")
    assert kind == "populated" and len(links) >= 5
    assert all("Document/Download" in l["href"] and l["filename"] for l in links)


def test_an_empty_documents_tab_is_recognised_by_its_own_sentence():
    kind, detail, links = arcus.classify_listing(
        _fixture("vog_empty_documents_tab.html"),
        base_url="https://vogonline.planning-register.co.uk/Planning/Display/2025/00528/OBS")
    assert kind == "empty" and links == []
    assert "no attachments found" in detail


def test_the_disclaimer_interstitial_is_not_the_application():
    """Fylde, since 2026-08-28: a page with the terms and an Accept form
    and no application on it. Four captured bodies, every one of which
    read as a council publishing nothing."""
    html = _fixture("fylde_disclaimer.html")
    kind, detail, _ = arcus.classify_listing(
        html, base_url="https://pa.fylde.gov.uk/Planning/Display/23/0695")
    assert kind == "disclaimer" and "interstitial" in detail
    form = arcus.disclaimer_form(html)
    assert form is not None and "/Disclaimer/Accept" in form.attributes["action"]
    assert form.attributes.get("method", "").lower() == "post"


def test_a_refusal_page_is_not_an_empty_register():
    body = "<html><body>" + "<p>chrome</p>" * 100 + "<p>you do not have permission to view</p></body></html>"
    kind, _, _ = arcus.classify_listing(body, base_url="https://x")
    assert kind == "refused"


def test_no_links_and_no_sentence_never_settles():
    body = ("<html><body><p>Application Number 1/1</p><div id='Documents'></div>"
            + "<p>site chrome</p>" * 100 + "</body></html>")
    kind, _, _ = arcus.classify_listing(body, base_url="https://x")
    assert kind == "unrecognised"
