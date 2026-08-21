"""Site partitions: campus boundaries the spatial radius cannot see.

The clustering premise — within the radius means the same site — fails
where two campuses sit closer together than the radius (Union Park and
the International Trading Estate are 0.28 km apart by portal
coordinates). data/priors/site_partitions.yaml is the hand-adjudicated
boundary; these tests pin its three behaviours: a partition splits what
proximity would merge, documentary edges extend the partition instead of
bridging around it, and a record that contradicts the adjudication fails
the run rather than being silently resolved.

Coordinates are the real corridor's, rounded: campus A at North Hyde
Gardens, campus B ~0.35 km east at Trident Way.
"""

from __future__ import annotations

import pytest

from dcp import repo, sites

A1 = "Testing/24/1001/FUL"
A2 = "Testing/24/1002/FUL"
B1 = "Testing/24/2001/FUL"
B2 = "Testing/24/2002/CND"

COORDS = {
    A1: (51.5011, -0.4070),
    A2: (51.5010, -0.4068),
    B1: (51.5003, -0.4020),
    B2: (51.5008, -0.4055),  # nearer campus A than B: the bridge case
}


def _seed(conn, refs, assoc=None):
    source_id = repo.ensure_source(
        conn, name="planit", kind="aggregator", base_url="https://x")
    ids = {}
    for ref in refs:
        lat, lon = COORDS[ref]
        ids[ref] = repo.upsert_application(
            conn, source_id=source_id,
            app={"name": ref, "description": "data centre",
                 "location_y": lat, "location_x": lon,
                 "associated_id": (assoc or {}).get(ref)},
            discovered_via=["test"])
    with conn.cursor() as cur:
        for app_id in ids.values():
            cur.execute(
                "INSERT INTO triage (application_id, model, verdict, raw_response) "
                "VALUES (%s, 'fake', 'new_build', '{\"rubric\": \"dc_build\"}')",
                (app_id,))
    conn.commit()
    return ids


def _partition_file(tmp_path, refs):
    priors = tmp_path / "priors"
    priors.mkdir()
    entries = "\n".join(f"      - {r}" for r in refs)
    (priors / "site_partitions.yaml").write_text(
        "partitions:\n"
        "  - name: campus-b\n"
        "    reason: test campuses closer together than the radius\n"
        "    applications:\n"
        f"{entries}\n")
    return tmp_path


def _keys(clusters):
    return {c["site_key"]: sorted(a["ref"] for a in c["apps"])
            for c in clusters}


@pytest.mark.integration
def test_radius_alone_merges_the_campuses(db_conn, tmp_path):
    _seed(db_conn, [A1, A2, B1])
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    assert _keys(clusters) == {f"SITE-{A1}": [A1, A2, B1]}


@pytest.mark.integration
def test_partition_splits_what_proximity_merged(db_conn, tmp_path):
    _seed(db_conn, [A1, A2, B1])
    clusters = sites.build_clusters(
        db_conn, data_dir=_partition_file(tmp_path, [B1]))
    assert _keys(clusters) == {f"SITE-{A1}": [A1, A2],
                               f"SITE-{B1}": [B1]}


@pytest.mark.integration
def test_family_edge_extends_the_partition_instead_of_bridging(db_conn, tmp_path):
    # B2 sits nearer campus A but its record names B1 as parent. Without
    # documentary closure it would union with B via family and with A
    # via space, re-merging everything the partition separates.
    _seed(db_conn, [A1, A2, B1, B2], assoc={B2: "24/2001/FUL"})
    clusters = sites.build_clusters(
        db_conn, data_dir=_partition_file(tmp_path, [B1]))
    assert _keys(clusters) == {f"SITE-{A1}": [A1, A2],
                               f"SITE-{B1}": [B1, B2]}


@pytest.mark.integration
def test_documentary_edge_across_partitions_fails_the_run(db_conn, tmp_path):
    _seed(db_conn, [A1, B1], assoc={B1: "24/1001/FUL"})
    data_dir = _partition_file(tmp_path, [B1])
    text = (data_dir / "priors" / "site_partitions.yaml").read_text()
    (data_dir / "priors" / "site_partitions.yaml").write_text(
        text + ("  - name: campus-a\n"
                "    reason: conflicting adjudication\n"
                "    applications:\n"
                f"      - {A1}\n"))
    with pytest.raises(ValueError, match="different site partitions"):
        sites.build_clusters(db_conn, data_dir=data_dir)


@pytest.mark.integration
def test_unknown_ref_in_partition_fails_the_run(db_conn, tmp_path):
    _seed(db_conn, [A1, B1])
    with pytest.raises(ValueError, match="not in the corpus"):
        sites.build_clusters(
            db_conn, data_dir=_partition_file(tmp_path, [B1, "Testing/24/9999/FUL"]))
