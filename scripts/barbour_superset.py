"""Full DC superset: our DC-verdict universe × Barbour's project list.

Extends the deep-read-only reverse test to every application whose latest
triage verdict is 'DC', so the coverage statement can be made cleanly in
both directions: what we missed (Barbour-only), what Barbour missed
(ours-only), what both hold, and the combined site total.

Method — site-level, because the two sources count different units
(Barbour: construction projects; us: planning applications, often several
per site):

1. Nodes are our DC-verdict applications and all Barbour projects.
2. Edges: explicit project↔application links (project_applications), and
   spatial proximity ≤ 1 km between any pair of nodes (campus-scale sites;
   the observed same-scheme screening/application pairs sit at 0.7–1.0 km).
   Application coords come from the raw PlanIt record with the
   inferred-coords priors as fallback (same as dcp/map.py).
3. Union-find clusters nodes into sites; each site is classified
   both / ours_only / barbour_only. No-coordinate, no-link applications
   stay singleton sites and are flagged (their absence from Barbour can't
   be distinguished from a geocoding gap).

Caveats stated in the report: 1 km merges dense city clusters (e.g.
Docklands) conservatively — the "both" classification is robust to this,
but site *counts* in dense clusters are a lower bound; Barbour procurement
notices (Find a Tender refs) are excluded from the site universe as
non-sites unless they carry coords that join an existing site.

Usage: .venv/bin/python scripts/barbour_superset.py [--radius-km 1.0]
       [--out data/new_lists/barbour_superset.md]
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402


def hav_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class UF:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius-km", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=Path("data/new_lists/barbour_superset.md"))
    args = ap.parse_args()

    inferred = {}
    prior_path = Path("data/priors/inferred_coords.yaml")
    if prior_path.exists():
        payload = yaml.safe_load(prior_path.read_text()) or {}
        for e in payload.get("entries") or []:
            inferred[e["ref"]] = (float(e["lat"]), float(e["lon"]))

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            WITH latest AS (
              SELECT DISTINCT ON (application_id) application_id, verdict
              FROM triage ORDER BY application_id, inserted_at DESC)
            SELECT a.id, a.application_ref, left(coalesce(a.description,''),120),
                   a.raw_metadata->>'location_x', a.raw_metadata->>'location_y',
                   coalesce(l.verdict, '?'), a.raw_metadata->>'associated_id'
            FROM applications a LEFT JOIN latest l ON l.application_id = a.id
            ORDER BY a.application_ref""")
        apps = []
        for aid, ref, desc, lx, ly, verdict, assoc in cur.fetchall():
            if lx and ly:
                lat, lon = float(ly), float(lx)
            elif ref in inferred:
                lat, lon = inferred[ref]
            else:
                lat = lon = None
            apps.append({"id": aid, "ref": ref, "desc": desc, "lat": lat,
                         "lon": lon, "verdict": verdict, "assoc": assoc})
        dc_apps = [a for a in apps if a["verdict"] == "DC"]

        cur.execute("""
            SELECT p.id, p.external_ref, p.title, p.latitude, p.longitude,
                   p.stage_summary, coalesce(p.planning_ref,'')
            FROM projects p""")
        projects = [{"id": r[0], "ptno": r[1], "title": r[2], "lat": r[3],
                     "lon": r[4], "stage": r[5],
                     "is_tender": r[6].upper().startswith("FIND A TENDER")}
                    for r in cur.fetchall()]

        cur.execute("SELECT project_id, application_id FROM project_applications")
        links = cur.fetchall()

    # Node universe: DC-verdict applications, every application linked to a
    # Barbour project (any verdict — they prove the site is in our universe),
    # plus applications reachable by family edges from those.
    from dcp.sources.planit import _extract_candidate_refs

    by_id = {a["id"]: a for a in apps}
    by_ref = {a["ref"].upper(): a for a in apps}
    linked_ids = {aid for _pid, aid in links}
    node_ids = {a["id"] for a in dc_apps} | linked_ids

    # Family edges: an application's associated_id names another ref —
    # same-council prefix match (mirrors the parent-backfill convention).
    fam_edges = []
    for a in apps:
        cands = _extract_candidate_refs(a["assoc"]) if a["assoc"] else []
        council = a["ref"].split("/", 1)[0]
        for cand in cands:
            other = by_ref.get(f"{council}/{cand}".upper()) or by_ref.get(cand.upper())
            if other is not None and other["id"] != a["id"]:
                fam_edges.append((a["id"], other["id"]))
    # Grow the node set one hop along family edges so unlocatable procedurals
    # fold into their located parents.
    for x, y in fam_edges:
        if x in node_ids or y in node_ids:
            node_ids.add(x)
            node_ids.add(y)

    uf = UF()
    for nid in node_ids:
        uf.find(("A", nid))
    for p in projects:
        uf.find(("P", p["id"]))
    for pid, aid in links:
        uf.union(("P", pid), ("A", aid))
    for x, y in fam_edges:
        if x in node_ids and y in node_ids:
            uf.union(("A", x), ("A", y))

    # Spatial edges among located nodes.
    located = ([("A", a["id"], a["lat"], a["lon"])
                for a in (by_id[n] for n in node_ids) if a["lat"] is not None]
               + [("P", p["id"], p["lat"], p["lon"]) for p in projects
                  if p["lat"] is not None and not p["is_tender"]])
    for i in range(len(located)):
        k1, id1, la1, lo1 = located[i]
        for j in range(i + 1, len(located)):
            k2, id2, la2, lo2 = located[j]
            if abs(la1 - la2) > 0.02 or abs(lo1 - lo2) > 0.03:
                continue  # cheap prefilter ~2km
            if hav_km(la1, lo1, la2, lo2) <= args.radius_km:
                uf.union((k1, id1), (k2, id2))

    clusters: dict = defaultdict(lambda: {"apps": [], "projects": []})
    for nid in node_ids:
        clusters[uf.find(("A", nid))]["apps"].append(by_id[nid])
    for p in projects:
        clusters[uf.find(("P", p["id"]))]["projects"].append(p)

    both, ours_only, barbour_only, barbour_covered, unlocatable = [], [], [], [], []
    for root, c in clusters.items():
        has_dc = any(a["verdict"] == "DC" for a in c["apps"])
        has_any_ours = bool(c["apps"])
        real_projects = [p for p in c["projects"] if not p["is_tender"]]
        has_barbour = bool(real_projects)
        if has_dc and has_barbour:
            both.append(c)
        elif has_dc:
            if all(a["lat"] is None for a in c["apps"]):
                unlocatable.append(c)
            else:
                ours_only.append(c)
        elif has_barbour and has_any_ours:
            # Site is in our universe, but our applications for it carry
            # non-DC verdicts (adjacent / procedural / etc.).
            barbour_covered.append(c)
        elif has_barbour:
            barbour_only.append(c)
        # tender-only clusters drop out of the site universe

    n_sites = (len(both) + len(ours_only) + len(barbour_only)
               + len(barbour_covered) + len(unlocatable))

    lines = [
        "# The full DC superset — our universe × Barbour ABI",
        "",
        f"Site-level reconciliation of every application with a latest triage "
        f"verdict of **DC** ({len(apps)} applications) against all "
        f"{len(projects)} Barbour projects. Sites are clusters of "
        f"applications + projects joined by explicit links or proximity "
        f"≤ {args.radius_km:g} km. Generated by `scripts/barbour_superset.py`.",
        "",
        "## Headline",
        "",
        f"- **Combined DC site universe: {n_sites} sites**",
        f"- In both sources: **{len(both)}**",
        f"- Ours only (Barbour omissions): **{len(ours_only)}**"
        f" (+ {len(unlocatable)} unlocatable ours-only — see caveat)",
        f"- In both, but our applications for the site carry non-DC verdicts "
        f"(adjacent / procedural): **{len(barbour_covered)}**",
        f"- Barbour only (genuinely absent from our universe, incl. "
        f"pre-application schemes with no planning application yet): "
        f"**{len(barbour_only)}**",
        "",
        "Application-level: "
        f"{sum(len(c['apps']) for c in both)} of our DC applications sit on "
        f"shared sites; {sum(len(c['apps']) for c in ours_only)} on "
        f"ours-only sites.",
        "",
        "Caveats: 1 km clustering merges dense urban clusters (Docklands) "
        "conservatively, so site counts there are lower bounds; 'unlocatable' "
        "means no source or inferred coordinates and no Barbour link — absence "
        "from Barbour can't be distinguished from a geocoding gap; Barbour "
        "procurement notices (Find a Tender) are excluded as non-sites.",
        "",
        "## Barbour-only sites",
        "",
    ]
    for c in sorted(barbour_only, key=lambda c: c["projects"][0]["title"] or ""):
        for p in c["projects"]:
            if not p["is_tender"]:
                lines.append(f"- {p['title']} (Ptno {p['ptno']}, {p['stage']})")
    lines += ["", "## Barbour sites we hold under non-DC verdicts", ""]
    for c in sorted(barbour_covered, key=lambda c: c["projects"][0]["title"] or ""):
        ps = ", ".join(p["title"] or "?" for p in c["projects"] if not p["is_tender"])
        our = ", ".join(f"{a['ref']} ({a['verdict']})" for a in c["apps"][:4])
        lines.append(f"- {ps} — ours: {our}")
    lines += ["", "## Ours-only sites (Barbour omissions)", ""]
    for c in sorted(ours_only, key=lambda c: -len(c["apps"])):
        lead = max(c["apps"], key=lambda a: len(a["desc"]))
        extra = len(c["apps"]) - 1
        suffix = f" (+{extra} more application{'s' if extra != 1 else ''})" if extra else ""
        lines.append(f"- **{lead['ref']}**{suffix} — {lead['desc']}")
    lines += ["", "## Unlocatable ours-only applications", ""]
    for c in unlocatable:
        for a in c["apps"]:
            lines.append(f"- {a['ref']} — {a['desc'][:100]}")

    args.out.write_text("\n".join(lines) + "\n")
    print(f"sites: {n_sites} = both {len(both)} + ours-only {len(ours_only)} "
          f"+ barbour-covered-non-DC {len(barbour_covered)} "
          f"+ barbour-only {len(barbour_only)} + unlocatable {len(unlocatable)}")
    print(f"report: {args.out}")


if __name__ == "__main__":
    main()
