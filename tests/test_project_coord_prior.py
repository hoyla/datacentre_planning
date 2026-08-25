"""Project coordinate priors: overriding a Barbour pin the record itself
contradicts.

A provider pin in the wrong place creates spatial edges into whatever
campus it lands inside — Barbour placed the Wapseys Wood scheme 8.5 km
south of its own address line, within the former Akzo Nobel cluster's
radius, and the false edge merged two unrelated campuses. A `ptno:`
entry in data/priors/inferred_coords.yaml moves the pin at clustering
time (the raw Barbour row is untouched); an entry naming a Ptno the
corpus does not hold fails the run, as site_partitions.yaml does,
because a typo would silently leave the false edges standing.

Coordinates echo the real case's shape: an application campus, and a
project pinned falsely inside its radius whose true site is far away.
"""

from __future__ import annotations

import pytest

from dcp import repo, sites

A1 = "Testing/24/1001/FUL"
PTNO = "99001122"
FALSE_PIN = (51.5010, -0.4069)   # inside A1's 1 km radius
TRUE_PIN = (51.6000, -0.4070)    # ~11 km north: the site the record names


def _seed(conn, *, project_lat, project_lon):
    source_id = repo.ensure_source(
        conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": A1, "description": "data centre",
             "location_y": 51.5011, "location_x": -0.4070},
        discovered_via=["test"])
    proj_source = repo.ensure_source(
        conn, name="barbour_abi", kind="projects", base_url="https://x")
    repo.upsert_project(
        conn, source_id=proj_source,
        project={"external_ref": PTNO, "title": "TEST CAMPUS",
                 "latitude": project_lat, "longitude": project_lon,
                 "raw_metadata": {}})
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response) "
            "VALUES (%s, 'fake', 'new_build', '{\"rubric\": \"dc_build\"}')",
            (app_id,))
    conn.commit()


def _prior_file(tmp_path, ptno, lat, lon):
    priors = tmp_path / "priors"
    priors.mkdir()
    (priors / "inferred_coords.yaml").write_text(
        "entries:\n"
        f"  - ptno: \"{ptno}\"\n"
        f"    lat: {lat}\n"
        f"    lon: {lon}\n"
        "    source: test override\n")
    return tmp_path


@pytest.mark.integration
def test_wrong_pin_merges_project_into_the_campus(db_conn, tmp_path):
    _seed(db_conn, project_lat=FALSE_PIN[0], project_lon=FALSE_PIN[1])
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["site_key"] == f"PTNO-{PTNO}"
    assert c["classification"] == "both"
    assert c["coord_source"] == "barbour"


@pytest.mark.integration
def test_prior_severs_the_false_edge_and_repins(db_conn, tmp_path):
    _seed(db_conn, project_lat=FALSE_PIN[0], project_lon=FALSE_PIN[1])
    clusters = sites.build_clusters(
        db_conn, data_dir=_prior_file(tmp_path, PTNO, *TRUE_PIN))
    by_key = {c["site_key"]: c for c in clusters}
    assert set(by_key) == {f"SITE-{A1}", f"PTNO-{PTNO}"}
    proj_site = by_key[f"PTNO-{PTNO}"]
    assert proj_site["classification"] == "barbour_only"
    assert proj_site["lat"] == pytest.approx(TRUE_PIN[0])
    assert proj_site["lon"] == pytest.approx(TRUE_PIN[1])
    assert proj_site["coord_source"] == "inferred_prior"


@pytest.mark.integration
def test_unknown_ptno_fails_the_run(db_conn, tmp_path):
    _seed(db_conn, project_lat=FALSE_PIN[0], project_lon=FALSE_PIN[1])
    with pytest.raises(ValueError, match="not in the corpus"):
        sites.build_clusters(
            db_conn, data_dir=_prior_file(tmp_path, "88880000", *TRUE_PIN))


@pytest.mark.integration
def test_ref_prior_overrides_a_wrong_application_coordinate(db_conn, tmp_path):
    # The Mulberry Place case: the record carries coordinates, and they
    # are wrong. A prior with a written derivation beats a portal pin,
    # so it wins rather than being ignored as it would be if priors were
    # only a fallback for absent coordinates.
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": A1, "description": "data centre",
             "location_y": 51.5152, "location_x": -0.0658},   # 4 km out
        discovered_via=["test"])
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response) "
            "VALUES (%s, 'fake', 'new_build', '{\"rubric\": \"dc_build\"}')",
            (app_id,))
    db_conn.commit()
    priors = tmp_path / "priors"
    priors.mkdir()
    (priors / "inferred_coords.yaml").write_text(
        "entries:\n"
        f"  - ref: {A1}\n"
        "    lat: 51.509868\n"
        "    lon: -0.005808\n"
        "    source: five sibling records carry this address\n")
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    assert len(clusters) == 1
    assert clusters[0]["coord_source"] == "inferred_prior"
    assert clusters[0]["lat"] == pytest.approx(51.509868)
    assert clusters[0]["lon"] == pytest.approx(-0.005808)


@pytest.mark.integration
def test_ref_entries_still_backfill_applications(db_conn, tmp_path):
    # The pre-existing entry kind: an application with no source coords
    # takes its pin from a `ref:` entry and reports inferred_prior.
    source_id = repo.ensure_source(
        db_conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        db_conn, source_id=source_id,
        app={"name": A1, "description": "data centre"},
        discovered_via=["test"])
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response) "
            "VALUES (%s, 'fake', 'new_build', '{\"rubric\": \"dc_build\"}')",
            (app_id,))
    db_conn.commit()
    priors = tmp_path / "priors"
    priors.mkdir()
    (priors / "inferred_coords.yaml").write_text(
        "entries:\n"
        f"  - ref: {A1}\n"
        "    lat: 51.9\n"
        "    lon: -0.5\n"
        "    source: test backfill\n")
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    assert len(clusters) == 1
    assert clusters[0]["coord_source"] == "inferred_prior"
    assert clusters[0]["lat"] == pytest.approx(51.9)
