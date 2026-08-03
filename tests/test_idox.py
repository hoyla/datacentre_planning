"""Idox adapter tests. The parser runs against a captured fixture (Halton's
documents-tab HTML — 4 documents, canonical Idox layout); other unit tests
exercise URL translation and the polite-client retry shape with mock transport.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dcp.sources import idox


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "idox"


@pytest.fixture
def halton_fixture() -> str:
    """Real Halton documents-tab HTML captured 2026-05-15.
    Canonical Idox `/online-applications/` layout."""
    return (FIXTURE_DIR / "halton_22_00028_documents.html").read_text()


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def test_is_idox_url_recognises_both_variants():
    assert idox._is_idox_url(
        "https://pa.halton.gov.uk/online-applications/applicationDetails.do?keyVal=X"
    )
    assert idox._is_idox_url(
        "https://newplanningaccess.eastriding.gov.uk/newplanningaccess/"
        "applicationDetails.do?keyVal=X"
    )


def test_is_idox_url_recognises_nonstandard_mount_paths():
    # The endpoint is the signal, not the path prefix — Fife mounts Idox at
    # /online/, Horsham at /public-access/, Stockport at /PlanningData-live/.
    assert idox._is_idox_url(
        "https://planning.fife.gov.uk/online/applicationDetails.do?keyVal=X"
    )
    assert idox._is_idox_url(
        "https://public-access.horsham.gov.uk/public-access/applicationDetails.do?keyVal=X"
    )
    assert idox._is_idox_url(
        "https://planning.stockport.gov.uk/PlanningData-live/applicationDetails.do?keyVal=X"
    )


def test_is_idox_url_rejects_other_portals():
    # Hillingdon uses Ocella, not Idox
    assert not idox._is_idox_url(
        "https://planning.hillingdon.gov.uk/OcellaWeb/planningDetails?reference=X"
    )
    assert not idox._is_idox_url(None)
    assert not idox._is_idox_url("")


def test_documents_tab_url_swaps_active_tab():
    """`activeTab=summary` is replaced with `activeTab=documents`; other params
    (including the order-sensitive `keyVal`) are preserved."""
    url = ("https://pa.halton.gov.uk/online-applications/applicationDetails.do"
           "?activeTab=summary&keyVal=R5K0ZSHTI6H00")
    out = idox._documents_tab_url(url)
    assert "activeTab=documents" in out
    assert "activeTab=summary" not in out
    assert "keyVal=R5K0ZSHTI6H00" in out


def test_documents_tab_url_appends_when_missing():
    url = ("https://pa.halton.gov.uk/online-applications/applicationDetails.do"
           "?keyVal=ABC123")
    out = idox._documents_tab_url(url)
    assert "activeTab=documents" in out
    assert "keyVal=ABC123" in out


# ---------------------------------------------------------------------------
# Parser (real Halton fixture)
# ---------------------------------------------------------------------------


def test_parse_documents_page_extracts_halton_direct_pdf_docs(halton_fixture):
    """Halton's documents tab has 4 rows: 3 plain direct-PDF rows + 1 'Plans'
    row that carries an OMT-viewer "Measure document" anchor (`docKey=`)
    *before* its direct "View" anchor. All 4 direct PDFs must come through —
    the Plans row resolves to its direct link, not the viewer."""
    base = ("https://pa.halton.gov.uk/online-applications/applicationDetails.do"
            "?activeTab=documents&keyVal=R5K0ZSHTI6H00")
    links = idox.parse_documents_page(halton_fixture, base_url=base)
    assert len(links) == 4
    kinds = sorted(link.kind for link in links if link.kind)
    assert kinds == [
        "Application Correspondence",
        "Application Form",
        "Decision / Officer Report",
        "Plans",
    ]
    for link in links:
        assert link.href.startswith("https://pa.halton.gov.uk/online-applications/files/")
        assert link.href.endswith(".pdf")
        assert "docKey=" not in link.href


def test_parse_documents_page_prefers_direct_link_over_measure_anchor():
    """Drawing rows on OMT-enabled councils (Glasgow, Fife, East Cambs, …)
    carry two anchors: "Measure document" (docKey=, first in the row) and
    "View Document" (direct PDF, later). The row must resolve to the direct
    PDF — taking the first anchor and skipping on docKey used to drop the
    whole row, silently losing the drawing."""
    html = """
    <html><body><table>
      <tr><th>Date Published</th><th>Document Type</th><th>Description</th></tr>
      <tr><td>7 Nov 2016</td><td>Drawing</td><td>CYCLING PROVISIONS</td>
        <td><a href="https://pa.example.gov.uk/omt-server/omt.html#docKey=XXXX"
               title="Measure document">measure</a></td>
        <td><a href="/online-applications/files/AAAA/pdf/drawing.pdf"
               title="View Document">view</a></td>
      </tr>
    </table></body></html>
    """
    links = idox.parse_documents_page(html, base_url="https://pa.example.gov.uk/online-applications/")
    assert len(links) == 1
    assert links[0].href == "https://pa.example.gov.uk/online-applications/files/AAAA/pdf/drawing.pdf"


def test_parse_documents_page_skips_viewer_only_rows():
    """A row whose only anchor is an OMT viewer link (no direct PDF anywhere
    in the row) still gets dropped — there are no bytes to fetch. Unobserved
    in the wild (all 1,622 docKey rows across 14 councils' snapshots carry a
    direct link too), but the guard keeps the viewer URL out of the corpus."""
    html = """
    <html><body><table>
      <tr><th>Date Published</th><th>Document Type</th><th>Description</th></tr>
      <tr><td>1 Jan 2025</td><td>Application Form</td><td>
        <a href="/online-applications/files/AAAA/pdf/form.pdf">form.pdf</a>
      </td></tr>
      <tr><td>2 Jan 2025</td><td>Plans</td><td>
        <a href="https://pa.example.gov.uk/omt/viewer.html#docKey=XXXX">map.pdf</a>
      </td></tr>
    </table></body></html>
    """
    links = idox.parse_documents_page(html, base_url="https://pa.example.gov.uk/online-applications/")
    refs = [link.kind for link in links]
    assert refs == ["Application Form"]


def test_parse_documents_page_handles_no_table():
    """Some councils return a 'No documents available' message in place of the
    table. Parser must return [] without raising."""
    assert idox.parse_documents_page("<html><body>No documents</body></html>",
                                     base_url="https://x") == []


# ---------------------------------------------------------------------------
# Bytes-path layout
# ---------------------------------------------------------------------------


def test_bytes_path_sanitises_slashes_in_application_ref(tmp_path):
    """`<DATA_DIR>/raw/idox/<safe_ref>/<sha[:16]>.pdf` — slashes inside the
    application_ref are preserved as nested subdirectories so each council's
    documents sit in their own folder."""
    p = idox._bytes_path(tmp_path, "Halton/22/00028/S73", "abcd" * 16, "pdf")
    # Path structure: <tmp>/raw/idox/Halton/22/00028/S73/<sha>.pdf
    rel = p.relative_to(tmp_path)
    assert rel.parts == ("raw", "idox", "Halton", "22", "00028", "S73",
                          "abcdabcdabcdabcd.pdf")


def test_bytes_path_strips_dangerous_chars(tmp_path):
    """Application refs with spaces / colons / parentheses must not appear in
    the filesystem path verbatim."""
    p = idox._bytes_path(tmp_path, "Council/abc (def):ghi", "deadbeef" * 8, "pdf")
    # All non-(alnum, ., _, /, -) chars replaced with underscores
    assert " " not in str(p)
    assert ":" not in str(p)
    assert "(" not in str(p)


# ---------------------------------------------------------------------------
# Polite client retry / backoff shape (mock transport)
# ---------------------------------------------------------------------------


def test_idox_client_retries_on_429(monkeypatch):
    """A 429 response triggers exponential backoff; a subsequent 200 succeeds."""
    sleeps: list[float] = []
    monkeypatch.setattr(idox.time, "sleep", lambda s: sleeps.append(s))

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, content=b"slow down")
        return httpx.Response(200, content=b"OK")

    client = idox.IdoxClient(delay_seconds=0.0, backoff_seconds=0.0)
    client.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        timeout=30,
        headers={"User-Agent": "test"},
    )
    r = client.get("https://x/online-applications/applicationDetails.do?keyVal=X")
    assert r.status_code == 200
    assert call_count["n"] == 2  # retried once after 429
