"""Who a documentary door may admit, and what retires with a site.

Two things measured on 2026-09-02 and pinned here:

- **A membership row retires with its site.** The materialise retired a
  site and left its `site_members` rows unretired, so a row on a dead
  site read `retired_at IS NULL` to every "is this a member" test — 65
  such rows, and four adjacent-power applications whose only membership
  was on a #252-retired site were staged nowhere.
- **The family door can be told to refuse `not_dc`.** The family
  expansion admits any application a family reference touches, vetoing
  `adjacent_power` alone, so 159 live members carried a `not_dc` verdict
  the universe rule would never have admitted. `not_dc_veto="family"`
  refuses them there; the default keeps the old behaviour until the
  choice is made from a dry run.
"""

from __future__ import annotations

import pytest

from dcp import repo, sites

A1 = "Testing/24/1001/FUL"
A2 = "Testing/24/1002/DISCON"


def _seed_app(conn, ref, lat, lon, *, verdict="new_build", description="data centre"):
    source_id = repo.ensure_source(
        conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": description,
             "location_y": lat, "location_x": lon},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response) "
            "VALUES (%s, 'fake', %s, '{\"rubric\": \"dc_build\"}')",
            (app_id, verdict))
    conn.commit()
    return app_id


def _member_rows(conn, app_id):
    with conn.cursor() as cur:
        cur.execute("SELECT retired_at IS NOT NULL FROM site_members "
                    "WHERE application_id = %s", (app_id,))
        return [r[0] for r in cur.fetchall()]


@pytest.mark.integration
def test_a_retired_site_retires_its_membership_rows(db_conn, tmp_path):
    a1 = _seed_app(db_conn, A1, 51.5011, -0.4070)
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    assert _member_rows(db_conn, a1) == [False], "A1 is a live member"

    # A later dc_build verdict takes A1 out of the universe.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response, inserted_at) "
            "VALUES (%s, 'fake', 'not_dc', '{\"rubric\": \"dc_build\"}', now() + interval '1 second')",
            (a1,))
    db_conn.commit()
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    assert all(a["id"] != a1 for c in clusters for a in c["apps"])

    pre = sites.preflight(db_conn, clusters)
    assert f"SITE-{A1}" in pre["retiring"]
    assert (A1, f"SITE-{A1}") in pre["leaving"], \
        "an application leaving the universe is named, not only its site"

    summary = sites.materialise(db_conn, clusters)
    db_conn.commit()
    assert summary["sites_retired"] == 1
    assert summary["members_retired_with_site"] >= 1
    assert _member_rows(db_conn, a1) == [True], \
        "the membership row retires with its site"
    assert sites.preflight(db_conn, clusters)["stale_member_rows"] == 0


@pytest.mark.integration
def test_the_family_door_admits_not_dc_by_default_and_refuses_it_when_told(db_conn, tmp_path):
    a1 = _seed_app(db_conn, A1, 51.5011, -0.4070)
    # A conditions discharge whose description names A1, triaged not_dc,
    # at the same place: the family door admits it, the radius glues it.
    a2 = _seed_app(db_conn, A2, 51.5011, -0.4070, verdict="not_dc",
                   description=f"Discharge of condition 2 of {A1}")

    default = sites.build_clusters(db_conn, data_dir=tmp_path)
    members = {a["id"] for c in default for a in c["apps"]}
    assert {a1, a2} <= members, "off: the family door admits the not_dc discharge"
    assert len(default) == 1, "and the radius puts both in one site"

    vetoed = sites.build_clusters(db_conn, data_dir=tmp_path, not_dc_veto="family")
    members = {a["id"] for c in vetoed for a in c["apps"]}
    assert a1 in members and a2 not in members, \
        "family: the not_dc application is refused at the door"

    with pytest.raises(ValueError):
        sites.build_clusters(db_conn, data_dir=tmp_path, not_dc_veto="sometimes")
