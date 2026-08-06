"""Site clustering and materialisation for the dc_build universe.

A *site* is the unit the investigation reasons about: a cluster of
planning applications and/or Barbour projects joined by explicit
project↔application links, family edges (``associated_id`` references),
or spatial proximity (≤ 1 km by default — campus scale). The clustering
method is the one validated by the Barbour superset reconciliation
(scripts/barbour_superset.py, 2026-08-03); this module is its reusable
extraction, plus materialisation into the ``sites`` / ``site_members``
tables (migration 006).

Identity rules (stable across re-materialisation):

- A cluster containing at least one real (non-tender) Barbour project is
  keyed ``PTNO-<lowest Ptno>``.
- Otherwise ``SITE-<alphabetically first application_ref>``.

Membership is recomputable; keys persist. A re-run updates membership,
retires sites that no longer emerge from the clustering (``retired_at``
set, never deleted), and revives them if they re-emerge. Derived data is
kept out of ``projects`` deliberately: that table holds Barbour records
verbatim, and clustering is our inference (principle 3).
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path


def hav_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class _UF:
    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _load_inferred_coords(data_dir: Path) -> dict[str, tuple[float, float]]:
    import yaml
    out: dict[str, tuple[float, float]] = {}
    prior_path = data_dir / "priors" / "inferred_coords.yaml"
    if prior_path.exists():
        payload = yaml.safe_load(prior_path.read_text()) or {}
        for e in payload.get("entries") or []:
            out[e["ref"]] = (float(e["lat"]), float(e["lon"]))
    return out


def build_clusters(conn, *, radius_km: float = 1.0,
                   data_dir: Path = Path("data")) -> list[dict]:
    """Cluster the dc_build universe into sites.

    Returns a list of cluster dicts:
      {"apps": [{id, ref, desc, lat, lon, coord_source, verdict, joined_via}],
       "projects": [{id, ptno, title, lat, lon, is_tender, joined_via}],
       "classification": 'both'|'ours_only'|'barbour_covered'|'barbour_only'|'unlocatable',
       "site_key": str, "display_name": str|None,
       "lat": float|None, "lon": float|None, "coord_source": str|None}
    """
    from dcp.sources.planit import _extract_candidate_refs

    inferred = _load_inferred_coords(data_dir)

    with conn.cursor() as cur:
        cur.execute("""
            WITH latest AS (
              SELECT DISTINCT ON (application_id) application_id, verdict
              FROM triage ORDER BY application_id, inserted_at DESC)
            SELECT a.id, a.application_ref, left(coalesce(a.description,''),120),
                   coalesce(a.address,''),
                   a.raw_metadata->>'location_x', a.raw_metadata->>'location_y',
                   coalesce(l.verdict, '?'), a.raw_metadata->>'associated_id'
            FROM applications a LEFT JOIN latest l ON l.application_id = a.id
            ORDER BY a.application_ref""")
        apps = []
        for aid, ref, desc, addr, lx, ly, verdict, assoc in cur.fetchall():
            if lx and ly:
                lat, lon, src = float(ly), float(lx), "application"
            elif ref in inferred:
                (lat, lon), src = inferred[ref], "inferred_prior"
            else:
                lat = lon = src = None
            apps.append({"id": aid, "ref": ref, "desc": desc, "addr": addr,
                         "lat": lat, "lon": lon, "coord_source": src,
                         "verdict": verdict, "assoc": assoc})

        cur.execute("""
            SELECT p.id, p.external_ref, p.title, p.latitude, p.longitude,
                   coalesce(p.planning_ref,'')
            FROM projects p""")
        projects = [{"id": r[0], "ptno": r[1], "title": r[2], "lat": r[3],
                     "lon": r[4],
                     "is_tender": r[5].upper().startswith("FIND A TENDER")}
                    for r in cur.fetchall()]

        cur.execute("SELECT project_id, application_id FROM project_applications")
        links = cur.fetchall()

    by_id = {a["id"]: a for a in apps}
    by_ref = {a["ref"].upper(): a for a in apps}
    dc_apps = [a for a in apps if a["verdict"] == "DC"]
    linked_ids = {aid for _pid, aid in links}
    node_ids = {a["id"] for a in dc_apps} | linked_ids

    fam_edges = []
    for a in apps:
        cands = _extract_candidate_refs(a["assoc"]) if a["assoc"] else []
        council = a["ref"].split("/", 1)[0]
        for cand in cands:
            other = by_ref.get(f"{council}/{cand}".upper()) or by_ref.get(cand.upper())
            if other is not None and other["id"] != a["id"]:
                fam_edges.append((a["id"], other["id"]))
    for x, y in fam_edges:
        if x in node_ids or y in node_ids:
            node_ids.add(x)
            node_ids.add(y)

    uf = _UF()
    for nid in node_ids:
        uf.find(("A", nid))
    for p in projects:
        uf.find(("P", p["id"]))

    # Edge provenance: strongest join wins (project_link > family > spatial).
    joined_via: dict[tuple, str] = {}

    def _join(node, via):
        order = {"project_link": 3, "family": 2, "spatial": 1}
        if order.get(via, 0) > order.get(joined_via.get(node), 0):
            joined_via[node] = via

    for pid, aid in links:
        if aid in node_ids:
            uf.union(("P", pid), ("A", aid))
            _join(("A", aid), "project_link")
            _join(("P", pid), "project_link")
    for x, y in fam_edges:
        if x in node_ids and y in node_ids:
            uf.union(("A", x), ("A", y))
            _join(("A", x), "family")
            _join(("A", y), "family")

    located = ([("A", a["id"], a["lat"], a["lon"])
                for a in (by_id[n] for n in node_ids) if a["lat"] is not None]
               + [("P", p["id"], p["lat"], p["lon"]) for p in projects
                  if p["lat"] is not None and not p["is_tender"]])
    for i in range(len(located)):
        k1, id1, la1, lo1 = located[i]
        for j in range(i + 1, len(located)):
            k2, id2, la2, lo2 = located[j]
            if abs(la1 - la2) > 0.02 or abs(lo1 - lo2) > 0.03:
                continue
            if hav_km(la1, lo1, la2, lo2) <= radius_km:
                uf.union((k1, id1), (k2, id2))
                _join((k1, id1), "spatial")
                _join((k2, id2), "spatial")

    raw: dict = defaultdict(lambda: {"apps": [], "projects": []})
    for nid in node_ids:
        a = dict(by_id[nid])
        a["joined_via"] = joined_via.get(("A", nid), "singleton")
        raw[uf.find(("A", nid))]["apps"].append(a)
    for p in projects:
        q = dict(p)
        q["joined_via"] = joined_via.get(("P", p["id"]), "singleton")
        raw[uf.find(("P", p["id"]))]["projects"].append(q)

    clusters = []
    for c in raw.values():
        real_projects = sorted(
            (p for p in c["projects"] if not p["is_tender"]),
            key=lambda p: p["ptno"])
        c["apps"].sort(key=lambda a: a["ref"])
        has_dc = any(a["verdict"] == "DC" for a in c["apps"])
        has_barbour = bool(real_projects)
        if has_dc and has_barbour:
            cls = "both"
        elif has_dc:
            cls = ("unlocatable"
                   if all(a["lat"] is None for a in c["apps"]) else "ours_only")
        elif has_barbour and c["apps"]:
            cls = "barbour_covered"
        elif has_barbour:
            cls = "barbour_only"
        else:
            # Tender-only or family-only clusters with no DC verdict and no
            # real Barbour project: not a site.
            continue
        if real_projects:
            key = f"PTNO-{real_projects[0]['ptno']}"
            display = real_projects[0]["title"]
            lat, lon, src = (real_projects[0]["lat"], real_projects[0]["lon"],
                             "barbour")
        else:
            lead = c["apps"][0]
            key = f"SITE-{lead['ref']}"
            display = lead["addr"] or lead["desc"] or lead["ref"]
            located_apps = [a for a in c["apps"] if a["lat"] is not None]
            if located_apps:
                lat, lon = located_apps[0]["lat"], located_apps[0]["lon"]
                src = located_apps[0]["coord_source"]
            else:
                lat = lon = src = None
        clusters.append({**c, "classification": cls, "site_key": key,
                         "display_name": display, "lat": lat, "lon": lon,
                         "coord_source": src})
    clusters.sort(key=lambda c: c["site_key"])
    return clusters


def materialise(conn, clusters: list[dict], *, radius_km: float = 1.0) -> dict:
    """Upsert clusters into sites/site_members. Stable keys; membership is
    replaced (retire + insert); sites that no longer emerge are retired,
    never deleted. Returns a summary dict."""
    summary = {"sites_new": 0, "sites_updated": 0, "sites_retired": 0,
               "sites_revived": 0, "members": 0}
    seen_keys = set()
    with conn.cursor() as cur:
        for c in clusters:
            seen_keys.add(c["site_key"])
            cur.execute("SELECT id, retired_at FROM sites WHERE site_key = %s",
                        (c["site_key"],))
            row = cur.fetchone()
            if row is None:
                cur.execute("""
                    INSERT INTO sites (site_key, classification, display_name,
                                       latitude, longitude, coord_source, radius_km)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (c["site_key"], c["classification"], c["display_name"],
                     c["lat"], c["lon"], c["coord_source"], radius_km))
                site_id = cur.fetchone()[0]
                summary["sites_new"] += 1
            else:
                site_id, retired = row
                if retired is not None:
                    summary["sites_revived"] += 1
                else:
                    summary["sites_updated"] += 1
                cur.execute("""
                    UPDATE sites SET classification=%s, display_name=%s,
                        latitude=%s, longitude=%s, coord_source=%s,
                        radius_km=%s, materialised_at=now(), retired_at=NULL
                    WHERE id=%s""",
                    (c["classification"], c["display_name"], c["lat"],
                     c["lon"], c["coord_source"], radius_km, site_id))
            # Replace membership: retire everything, then upsert-and-revive.
            cur.execute("UPDATE site_members SET retired_at=now() "
                        "WHERE site_id=%s AND retired_at IS NULL", (site_id,))
            for a in c["apps"]:
                cur.execute("""
                    INSERT INTO site_members (site_id, application_id, joined_via)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (site_id, application_id) WHERE application_id IS NOT NULL
                    DO UPDATE SET joined_via=EXCLUDED.joined_via,
                                  materialised_at=now(), retired_at=NULL""",
                    (site_id, a["id"], a["joined_via"]))
                summary["members"] += 1
            for p in c["projects"]:
                cur.execute("""
                    INSERT INTO site_members (site_id, project_id, joined_via)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (site_id, project_id) WHERE project_id IS NOT NULL
                    DO UPDATE SET joined_via=EXCLUDED.joined_via,
                                  materialised_at=now(), retired_at=NULL""",
                    (site_id, p["id"], p["joined_via"]))
                summary["members"] += 1
        cur.execute("""
            UPDATE sites SET retired_at=now()
            WHERE retired_at IS NULL AND NOT (site_key = ANY(%s))
            RETURNING site_key""", (sorted(seen_keys),))
        summary["sites_retired"] = len(cur.fetchall())
    return summary
