"""A zero-length body is a failed fetch, not a document.

Three zero-byte documents reached the corpus before anyone noticed, and
they were only found because an empty file is conspicuous in an export.
All three came back HTTP 200 with `Content-Type: application/pdf` and no
bytes, from the councils' own servers; the fetcher stored them faithfully
and everything downstream — the corpus totals, the Pinpoint staging, the
deep read — treated them as documents held and read. Two were consultee
responses and one an s106.

The guard sits in two places, and both are tested here:

* `repo.record_document` refuses the empty hash. Every fetch and ingest
  path in the project passes through it, so nothing can record an empty
  document even from a path nobody has updated.
* Each adapter checks the body before it hashes or writes, so no empty
  file is created and the application is left with an error — which
  keeps it out of any completed set and makes a re-run retry it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from dcp import repo
from dcp.sources import idox


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------


def test_check_document_body_rejects_empty():
    with pytest.raises(repo.EmptyDocumentBody):
        repo.check_document_body(b"", url="https://x/pdf/empty.pdf")


def test_check_document_body_rejects_none():
    with pytest.raises(repo.EmptyDocumentBody):
        repo.check_document_body(None, url="https://x/pdf/empty.pdf")


def test_check_document_body_passes_real_bytes():
    repo.check_document_body(b"%PDF-1.4", url="https://x/pdf/real.pdf")


def test_empty_sha256_is_the_well_known_constant():
    """Guards against a future refactor computing it over the wrong input:
    this is the published sha256 of the empty string."""
    assert repo.EMPTY_SHA256 == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


# ---------------------------------------------------------------------------
# The chokepoint: repo.record_document
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_record_document_refuses_the_empty_hash(db_conn):
    """The backstop. Even handed a bytes_path, no row is written."""
    source_id = repo.ensure_source(db_conn, name="planit", kind="aggregator")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": "Wakefield/23/00100/S7301", "url": "https://x/a"})
    with pytest.raises(repo.EmptyDocumentBody):
        repo.record_document(
            db_conn, application_id=app_id,
            url="https://x/pdf/005 - Section 106 Agreement.pdf",
            kind="Legal Agreement",
            content_sha256=repo.EMPTY_SHA256,
            bytes_path="data/raw/documents/x/e3b0c442.pdf",
        )
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents WHERE application_id = %s",
                    (app_id,))
        assert cur.fetchone()[0] == 0


@pytest.mark.integration
def test_record_document_still_accepts_a_real_document(db_conn):
    source_id = repo.ensure_source(db_conn, name="planit", kind="aggregator")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": "Wakefield/23/00100/S7301", "url": "https://x/a"})
    sha = hashlib.sha256(b"%PDF-1.4 real").hexdigest()
    doc_id = repo.record_document(
        db_conn, application_id=app_id, url="https://x/pdf/real.pdf",
        content_sha256=sha, bytes_path="data/raw/documents/x/real.pdf")
    assert doc_id > 0


# ---------------------------------------------------------------------------
# The adapter path: an empty body is an error, not a stored document
# ---------------------------------------------------------------------------


DOCS_HTML = """
<html><body><table>
  <tr><th>Date Published</th><th>Document Type</th><th>Description</th></tr>
  <tr><td>9 Jan 2025</td><td>Consultation Response</td><td>silent</td>
    <td><a href="/online-applications/files/AAAA/pdf/empty.pdf"
           title="View Document">view</a></td></tr>
  <tr><td>9 Jan 2025</td><td>Report</td><td>real</td>
    <td><a href="/online-applications/files/BBBB/pdf/real.pdf"
           title="View Document">view</a></td></tr>
</table></body></html>
"""


@pytest.mark.integration
def test_idox_records_a_zero_byte_document_as_a_failed_fetch(
        db_conn, tmp_path, monkeypatch):
    """The portal offers two documents and serves one of them as nothing.

    The real document is stored; the empty one leaves no file, no row and
    an error on the application. `links_found` still counts both, so the
    campaign runner's `held < listed` test records the application
    `partial` and a later pass retries it.
    """
    monkeypatch.setattr(idox.time, "sleep", lambda s: None)
    host = "https://pa.example.gov.uk"
    app_url = f"{host}/online-applications/applicationDetails.do?keyVal=ZZZ"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "applicationDetails.do" in url:
            return httpx.Response(200, content=DOCS_HTML.encode())
        if url.endswith("empty.pdf"):
            # Exactly what Wakefield, Warwick and Medway serve.
            return httpx.Response(
                200, content=b"", headers={"content-type": "application/pdf"})
        return httpx.Response(
            200, content=b"%PDF-1.4 real document",
            headers={"content-type": "application/pdf"})

    client = idox.IdoxClient(delay_seconds=0.0, backoff_seconds=0.0)
    client.client = httpx.Client(transport=httpx.MockTransport(handler),
                                 timeout=30, headers={"User-Agent": "test"})

    source_id = repo.ensure_source(db_conn, name="idox", kind="council")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": "Example/25/00001/FUL", "url": app_url})

    data_dir = tmp_path / "data"
    summary = idox.fetch_documents_for_application(
        db_conn, client=client, application_id=app_id,
        application_ref="Example/25/00001/FUL", application_url=app_url,
        source_id=source_id, data_dir=data_dir)

    assert summary["links_found"] == 2
    assert summary["downloaded"] == 1
    assert summary["errors"] == 1
    assert summary["zero_byte"] == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT url FROM documents WHERE application_id = %s",
                    (app_id,))
        stored = [r[0] for r in cur.fetchall()]
    assert len(stored) == 1
    assert stored[0].endswith("real.pdf")

    # Nothing empty on disk — the whole point. `find -size -1c` over the
    # canonical store is the corpus-wide version of this assertion.
    written = [p for p in data_dir.rglob("*")
               if p.is_file() and p.suffix in (".pdf", ".bin")]
    assert written, "the real document should have been written"
    assert all(p.stat().st_size > 0 for p in written)


@pytest.mark.integration
def test_idox_zero_byte_is_retried_on_a_later_run(db_conn, tmp_path,
                                                  monkeypatch):
    """The failure must not be sticky in the wrong direction: once the
    council fixes its server, the next run picks the document up. Nothing
    was stored for it, so the adapter's URL-level resume skip does not
    fire and the document is attempted again."""
    monkeypatch.setattr(idox.time, "sleep", lambda s: None)
    host = "https://pa.example.gov.uk"
    app_url = f"{host}/online-applications/applicationDetails.do?keyVal=ZZZ"
    serve_empty = {"yes": True}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "applicationDetails.do" in url:
            return httpx.Response(200, content=DOCS_HTML.encode())
        if url.endswith("empty.pdf") and serve_empty["yes"]:
            return httpx.Response(200, content=b"")
        return httpx.Response(200, content=b"%PDF-1.4 " + url[-12:].encode())

    def run() -> dict:
        client = idox.IdoxClient(delay_seconds=0.0, backoff_seconds=0.0)
        client.client = httpx.Client(transport=httpx.MockTransport(handler),
                                     timeout=30,
                                     headers={"User-Agent": "test"})
        return idox.fetch_documents_for_application(
            db_conn, client=client, application_id=app_id,
            application_ref="Example/25/00001/FUL", application_url=app_url,
            source_id=source_id, data_dir=tmp_path / "data")

    source_id = repo.ensure_source(db_conn, name="idox", kind="council")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": "Example/25/00001/FUL", "url": app_url})

    first = run()
    assert first["errors"] == 1 and first["downloaded"] == 1

    serve_empty["yes"] = False
    second = run()
    assert second["errors"] == 0
    assert second["downloaded"] == 1          # the previously-empty one
    assert second["skipped_existing"] == 1    # the one already held

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents WHERE application_id = %s",
                    (app_id,))
        assert cur.fetchone()[0] == 2
