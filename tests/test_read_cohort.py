"""What the deep read's cohort query offers, run against Postgres.

`deepread_run.load_cohort` is the resume predicate of the corpus sweep:
every document of every application on a live site, minus the ones
already logged under this model and prompt version — except a
`not_extracted` log row, which is a document waiting for the text
extractor and not a document that was read. The only test that called
it before 2026-09-16 handed it a fake cursor that ignored the SQL, so
nothing held any of that, and the query joined `site_members` without
`retired_at IS NULL` on the member row: an application that had left
a surviving site kept its documents in the cohort through the retired
row (42 applications, 807 documents, measured that day).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import deepread_run  # noqa: E402

pytestmark = pytest.mark.integration


def _seed(cur):
    cur.execute("INSERT INTO sources (name, kind, base_url) VALUES ('t', 'planning_portal', "
                "'http://t') ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url "
                "RETURNING id")
    src = cur.fetchone()[0]
    apps = {}
    for ref in ("T/live", "T/left", "T/retired-site"):
        cur.execute("INSERT INTO applications (source_id, application_ref) VALUES (%s, %s) "
                    "RETURNING id", (src, ref))
        apps[ref] = cur.fetchone()[0]
    cur.execute("INSERT INTO sites (site_key, classification, radius_km) VALUES "
                "('SITE-live', 'dc', 1.0) RETURNING id")
    live_site = cur.fetchone()[0]
    cur.execute("INSERT INTO sites (site_key, classification, radius_km, retired_at) VALUES "
                "('SITE-gone', 'dc', 1.0, now()) RETURNING id")
    gone_site = cur.fetchone()[0]
    cur.execute("INSERT INTO site_members (site_id, application_id, joined_via) VALUES (%s, %s, 'test')",
                (live_site, apps["T/live"]))
    # T/left was a member of the live site once; its only row there is retired.
    cur.execute("INSERT INTO site_members (site_id, application_id, joined_via, retired_at) "
                "VALUES (%s, %s, 'test', now())", (live_site, apps["T/left"]))
    cur.execute("INSERT INTO site_members (site_id, application_id, joined_via) VALUES (%s, %s, 'test')",
                (gone_site, apps["T/retired-site"]))
    docs = {}
    for ref, name in (("T/live", "unread"), ("T/live", "read"), ("T/live", "not-extracted"),
                      ("T/live", "read-under-old-prompt"), ("T/left", "left"),
                      ("T/retired-site", "gone")):
        cur.execute("INSERT INTO documents (application_id, url, kind, content_sha256, bytes_path) "
                    "VALUES (%s, %s, 'pdf', md5(%s), %s) RETURNING id",
                    (apps[ref], f"http://t/{name}", name, f"data/raw/{name}.pdf"))
        docs[name] = cur.fetchone()[0]
    for name, state, version in (("read", "read", deepread_run.PROMPT_VERSION),
                                 ("not-extracted", "not_extracted", deepread_run.PROMPT_VERSION),
                                 ("read-under-old-prompt", "read", "0.0")):
        cur.execute("INSERT INTO deepread_log (document_id, application_id, model, prompt_version, "
                    "tier, read_state) VALUES (%s, %s, %s, %s, 'A', %s)",
                    (docs[name], apps["T/live"], deepread_run.MODEL_TAG, version, state))
    return docs


def _cohort(conn) -> set[int]:
    rows = deepread_run.load_cohort(conn, tiers=None, ref=None, site=None)
    return {r["document_id"] for r in rows}


def test_a_document_already_read_is_not_offered_again(db_conn):
    with db_conn.cursor() as cur:
        docs = _seed(cur)
    got = _cohort(db_conn)
    assert docs["unread"] in got
    assert docs["read"] not in got


def test_not_extracted_is_offered_again_and_an_old_prompt_version_too(db_conn):
    """A `not_extracted` row is a document waiting for text, not one that
    was read; and a reading under another prompt version is not this
    version's reading."""
    with db_conn.cursor() as cur:
        docs = _seed(cur)
    got = _cohort(db_conn)
    assert docs["not-extracted"] in got
    assert docs["read-under-old-prompt"] in got


def test_only_live_members_of_live_sites_are_in_the_cohort(db_conn):
    with db_conn.cursor() as cur:
        docs = _seed(cur)
    got = _cohort(db_conn)
    assert docs["gone"] not in got, "a retired site's members are not read"
    assert docs["left"] not in got, (
        "an application whose only membership row is retired has left the "
        "site; its documents were still offered through that row until "
        "2026-09-16")
