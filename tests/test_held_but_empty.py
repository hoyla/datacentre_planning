"""A held but empty document is unavailable from the source, not read.

Three documents in the store are zero-byte files served as such by the
councils' portals; `repo.zero_byte_files` finds them every release. On
the page they were counted with the unreadable — corrupt PDFs, blank
scans — and a site report listed them among the documents held. An
empty file is a different fact from a file that yields no text, and a
reporter chases it in a different place. The marker is the empty body's
sha256, the constant the fetch guard refuses on the way in, so the
coverage query names it without a filesystem stat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dcp import repo, site_profile

ROOT = Path(__file__).resolve().parent.parent


def test_the_coverage_query_uses_the_one_constant():
    assert site_profile.EMPTY_BODY_SHA256 == repo.EMPTY_SHA256
    assert repo.EMPTY_SHA256 in site_profile.COVERAGE_DETAIL_SQL


def test_both_artefacts_say_unavailable_from_the_source():
    reader = (ROOT / "scripts" / "export_reader.py").read_text()
    staging = (ROOT / "scripts" / "build_drive_staging.py").read_text()
    assert "held but empty: unavailable from the source" in reader
    assert 'unavailable from the source' in staging
    assert "repo.EMPTY_SHA256" in staging


@pytest.mark.integration
def test_empty_is_its_own_bucket_and_never_prose(db_conn):
    source_id = repo.ensure_source(db_conn, name="planit", kind="aggregator",
                                   base_url="https://x")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": "Testing/24/3001/FUL", "description": "data centre",
             "location_y": 51.5, "location_x": -0.1},
        discovered_via=["test"])
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO sites (site_key, classification, radius_km, materialised_at) "
                    "VALUES ('SITE-empty', 'ours_only', 1.0, now()) RETURNING id")
        site_id = cur.fetchone()[0]
        cur.execute("INSERT INTO site_members (site_id, application_id, joined_via, "
                    "materialised_at) VALUES (%s, %s, 'singleton', now())", (site_id, app_id))

        def doc(sha, state):
            cur.execute("INSERT INTO documents (application_id, url, kind, content_sha256, "
                        "bytes_path, fetched_at) VALUES (%s, %s, 'Planning Statement', %s, "
                        "'x.pdf', now()) RETURNING id", (app_id, f"https://x/{sha}.pdf", sha))
            d = cur.fetchone()[0]
            cur.execute("INSERT INTO deepread_log (document_id, application_id, model, "
                        "prompt_version, tier, read_state, pages_total) "
                        "VALUES (%s, %s, 'fake', '1.0', 'A', %s, 1)", (d, app_id, state))
        doc("a" * 64, "read")               # prose, read
        doc("b" * 64, "no_text")            # has bytes, yields nothing
        doc(repo.EMPTY_SHA256, "no_text")   # zero bytes: logged the same way, a different fact
    db_conn.commit()

    c = site_profile.load_coverage_detail(db_conn)["SITE-empty"]
    assert c["held"] == 3
    assert c["empty"] == 1
    assert c["prose_unreadable"] == 1
    assert c["prose_held"] == 1 and c["prose_read"] == 1
