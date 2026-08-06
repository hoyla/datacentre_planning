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
                   data_dir: Path = Path("data"),
                   family_skips_not_dc: bool = True) -> list[dict]:
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

    # Universe membership is **rubric-aware**. Verdicts are append-only and
    # multi-generational: an application classified `DC` under v1 may later
    # be classified `new_build` (or `procedural`, or `adjacent_power`) under
    # dc_build. Taking simply the latest verdict and testing for the v1
    # label 'DC' silently ejects every application the dc_build sweep has
    # reached — during the 2026-08-06 catalogue sweep that collapsed the
    # universe from 1,046 applications to 629 mid-run, and would have
    # rewritten every site key.
    #
    # So: take the latest verdict *per rubric*, and treat an application as
    # in-universe if either generation calls it datacentre-related. Under
    # dc_build that is every class except `not_dc` — `procedural` and
    # `unknown` included, because a conditions discharge belongs to its
    # parent's site and a disguise suspect is precisely what we must not
    # drop.
    with conn.cursor() as cur:
        cur.execute("""
            WITH per_rubric AS (
              SELECT DISTINCT ON (application_id, coalesce(raw_response->>'rubric','v1'))
                     application_id,
                     coalesce(raw_response->>'rubric','v1') AS rubric,
                     verdict
              FROM triage
              ORDER BY application_id, 2, inserted_at DESC),
            membership AS (
              SELECT application_id,
                     bool_or(rubric = 'v1' AND verdict = 'DC'
                             OR rubric = 'dc_build' AND verdict <> 'not_dc')
                       AS in_universe,
                     max(verdict) FILTER (WHERE rubric = 'dc_build') AS dc_build_verdict,
                     max(verdict) FILTER (WHERE rubric = 'v1')       AS v1_verdict
              FROM per_rubric GROUP BY application_id)
            SELECT a.id, a.application_ref, left(coalesce(a.description,''),400),
                   coalesce(a.address,''),
                   a.raw_metadata->>'location_x', a.raw_metadata->>'location_y',
                   coalesce(m.dc_build_verdict, m.v1_verdict, '?'),
                   a.raw_metadata->>'associated_id',
                   coalesce(m.in_universe, false)
            FROM applications a LEFT JOIN membership m ON m.application_id = a.id
            ORDER BY a.application_ref""")
        apps = []
        for aid, ref, desc, addr, lx, ly, verdict, assoc, in_universe in cur.fetchall():
            if lx and ly:
                lat, lon, src = float(ly), float(lx), "application"
            elif ref in inferred:
                (lat, lon), src = inferred[ref], "inferred_prior"
            else:
                lat = lon = src = None
            apps.append({"id": aid, "ref": ref, "desc": desc, "addr": addr,
                         "lat": lat, "lon": lon, "coord_source": src,
                         "verdict": verdict, "assoc": assoc,
                         "in_universe": in_universe})

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
    dc_apps = [a for a in apps if a["in_universe"]]
    linked_ids = {aid for _pid, aid in links}
    node_ids = {a["id"] for a in dc_apps} | linked_ids

    # Family edges: an application naming another application's reference.
    #
    # `associated_id` is the clean signal, but many portals leave it empty
    # and put the parent reference in the description instead — "Discharge
    # of condition 20 (Travel Plan) on application P21/S0274/FUL". Without
    # mining descriptions those applications cluster as singletons, which
    # is how a Didcot condition-discharge ended up with its own "site"
    # while its parent sat in the Amazon campus cluster.
    #
    # The description fallback fires only when `associated_id` is empty,
    # and demands a stricter reference shape (3+ segments), mirroring the
    # parent-backfill pass in dcp/sources/planit.py — dates like "1/2024"
    # and use-class strings like "B1/B8" would otherwise create false
    # links, and a false family edge silently merges two unrelated sites.
    fam_edges = []
    for a in apps:
        council = a["ref"].split("/", 1)[0]
        cands = _extract_candidate_refs(a["assoc"]) if a["assoc"] else []
        source = "associated_id"
        if not cands and a.get("desc"):
            cands = [c for c in _extract_candidate_refs(a["desc"])
                     if c.count("/") >= 2]
            source = "description"
        for cand in cands:
            other = by_ref.get(f"{council}/{cand}".upper()) or by_ref.get(cand.upper())
            if other is not None and other["id"] != a["id"]:
                fam_edges.append((a["id"], other["id"], source))
    for x, y, _src in fam_edges:
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
        order = {"project_link": 4, "family": 3, "family_description": 2,
                 "spatial": 1}
        if order.get(via, 0) > order.get(joined_via.get(node), 0):
            joined_via[node] = via

    for pid, aid in links:
        if aid in node_ids:
            uf.union(("P", pid), ("A", aid))
            _join(("A", aid), "project_link")
            _join(("P", pid), "project_link")
    for x, y, src in fam_edges:
        if x in node_ids and y in node_ids:
            # Family edges do not traverse an application the taxonomy
            # calls not_dc. A mixed-use master plan otherwise drags its
            # whole estate into a site: Houghton Regis North joined 154
            # applications to one 5,150-dwelling outline, of which two
            # mention a data centre.
            #
            # The risk was bridges — a not_dc application sitting between
            # two datacentre ones, whose removal would sever a real family
            # — so it was measured across the corpus before adoption
            # (2026-08-06): 21 applications leave the universe, all of them
            # not_dc, no site disappears, and **zero** substantive
            # applications lose a substantive co-member. Set False to
            # restore the permissive behaviour.
            #
            # This trims but does not cure master-plan conflation: most of
            # the housing noise is classified `procedural` (procedural on a
            # housing parent), which a verdict test cannot distinguish from
            # procedural on a datacentre parent. That needs the parent link
            # itself — see ROADMAP, typed `parent_ref` column.
            if family_skips_not_dc and (
                    by_id[x]["verdict"] == "not_dc"
                    or by_id[y]["verdict"] == "not_dc"):
                continue
            uf.union(("A", x), ("A", y))
            via = "family" if src == "associated_id" else "family_description"
            _join(("A", x), via)
            _join(("A", y), via)

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
        has_dc = any(a["in_universe"] for a in c["apps"])
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
