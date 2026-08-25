"""Preflight: what a materialise would destroy, before it destroys it.

Retiring a site is recoverable — the row stays and the clustering is
reproducible. A capacity claim matched to that site by a person, with
written evidence, is not: it renders through a `retired_at IS NULL`
join, so when its site retires the claim does not error, it silently
stops appearing. These tests pin that the preflight names such a claim,
says where the site's members went (which is where a human would
re-point the match), and stays quiet when nothing is at stake.
"""

from __future__ import annotations

import pytest

from dcp import repo, sites

A1 = "Testing/24/1001/FUL"
A2 = "Testing/24/1002/FUL"


def _seed_app(conn, ref, lat, lon):
    source_id = repo.ensure_source(
        conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": "data centre",
             "location_y": lat, "location_x": lon},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response) "
            "VALUES (%s, 'fake', 'new_build', '{\"rubric\": \"dc_build\"}')",
            (app_id,))
    conn.commit()
    return app_id


def _claim_on(conn, site_id, claim_name):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO capacity_claims
                   (source_key, claim_name, quantity_type, value_original,
                    unit_original, value_mw, as_at, source_url, source_locator)
               VALUES ('test', %s, 'total_site', 100, 'MW', 100,
                       '2026-01-01', 'https://x', 'row 1')
               RETURNING id""", (claim_name,))
        claim_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO capacity_claim_matches
                   (claim_id, site_id, method, confidence, evidence, matched_by)
               VALUES (%s, %s, 'name_identity', 'strong',
                       %s, 'hand:test')""",
            (claim_id, site_id,
             "Evidence long enough to be weighed by a reader of the file."))
    conn.commit()


@pytest.mark.integration
def test_preflight_is_quiet_when_nothing_retires(db_conn, tmp_path):
    _seed_app(db_conn, A1, 51.5011, -0.4070)
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    pre = sites.preflight(db_conn, clusters)
    assert pre["retiring"] == []
    assert pre["orphaned_claims"] == []
    assert pre["new"] == []


@pytest.mark.integration
def test_preflight_names_a_site_that_would_retire(db_conn, tmp_path):
    _seed_app(db_conn, A1, 51.5011, -0.4070)
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    # A second application 200 m away merges the two into one cluster
    # keyed by the first ref, so nothing retires; move it far instead so
    # the original key survives and a *new* key appears.
    _seed_app(db_conn, A2, 55.0, -3.0)
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    pre = sites.preflight(db_conn, clusters)
    assert pre["retiring"] == []
    assert pre["new"] == [f"SITE-{A2}"]


@pytest.mark.integration
def test_preflight_reports_the_claim_a_retirement_would_empty(db_conn, tmp_path):
    # Two distant sites, materialised, with a claim adjudicated onto the
    # second. Then the second application is pulled into the first's
    # cluster by moving it next door: its own site key retires, and the
    # claim matched to it is the thing that silently empties.
    _seed_app(db_conn, A1, 51.5011, -0.4070)
    a2_id = _seed_app(db_conn, A2, 55.0, -3.0)
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM sites WHERE site_key = %s", (f"SITE-{A2}",))
        site_id = cur.fetchone()[0]
    _claim_on(db_conn, site_id, "Test Campus grid supply")

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE applications SET raw_metadata = "
            "jsonb_set(jsonb_set(raw_metadata, '{location_y}', '51.5012'), "
            "'{location_x}', '-0.4071') WHERE id = %s", (a2_id,))
    db_conn.commit()

    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    pre = sites.preflight(db_conn, clusters)
    assert pre["retiring"] == [f"SITE-{A2}"]
    assert len(pre["orphaned_claims"]) == 1
    orphan = pre["orphaned_claims"][0]
    assert orphan["claim_name"] == "Test Campus grid supply"
    assert orphan["site_key"] == f"SITE-{A2}"
    assert orphan["confidence"] == "strong"
    # Where a person would re-point the match.
    assert orphan["members_move_to"] == [f"SITE-{A1}"]
