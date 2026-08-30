"""Which sites a piece of adjacent power stands beside, and on what evidence.

`adjacent_power` under the dc_build rubric is power consented in its own
right next to a data centre — a substation, an energy centre, a standby
fleet. It is not a data centre, and migration 032 records why membership
of one is the wrong model for it. This module builds the relationship
that replaces it.

**The three bases rank, and a consumer must not flatten them.**

- ``discovery`` is documentary. ``applications.discovered_via`` records
  how a record entered the corpus, and an ``energy_national:<site_key>``
  token names the site the search ran outward from. 26 of the 48 carry
  one. It says this record was found *because of* that site — not that
  it supplies it, which no discovery token can establish.
- ``cohort`` is documentary but weaker: a spatial sweep outward from a
  named application, or a Barbour project, resolved to whichever site
  now holds that record. A ``cohort:`` token is deliberately *not* one
  of these — a cohort is a set of sites rather than a site, so there is
  no single record to relate to.
- ``proximity`` is distance and nothing else. One kilometre is the
  clustering radius, not a supply relationship. The Slough solar PV
  installation lies within reach of eleven sites and supplies none of
  them by being close.

So ``proximity`` rows are candidates for a person to look at, and the
sentence "shares grid infrastructure with" cannot rest on one. That
sentence needs the applications to name the same substation, grid supply
point or connection, and this module does not attempt to extract that —
issue #252 leaves it open deliberately, because a confident claim about
an electrical relationship inferred from a map pin is the failure the
whole change exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, cos, radians, sin

# The radius a proximity row is allowed to span, matching the clustering
# radius in dcp.sites. Beyond it a record is not "adjacent" in any sense
# the corpus can defend.
PROXIMITY_KM = 1.0

VERDICT_SQL = """
SELECT DISTINCT ON (application_id) application_id, verdict
FROM triage
WHERE raw_response->>'rubric' = 'dc_build'
ORDER BY application_id, inserted_at DESC
"""

ADJACENT_SQL = f"""
WITH v AS ({VERDICT_SQL})
SELECT a.id, a.application_ref, a.discovered_via,
       (a.raw_metadata->>'location_y')::float AS lat,
       (a.raw_metadata->>'location_x')::float AS lon
FROM applications a
JOIN v ON v.application_id = a.id
WHERE v.verdict = 'adjacent_power'
"""

SITES_SQL = """
SELECT id, site_key, latitude, longitude
FROM sites
WHERE retired_at IS NULL
"""

# A `spatial:` or `barbour:` token names the record the sweep ran from,
# not the site it landed in — an application reference or a Barbour Ptno.
# Resolving them is the difference between seven documentary rows and
# seven records demoted to bare distance.
SITE_OF_APP_SQL = """
SELECT a.application_ref, s.site_key
FROM applications a
JOIN site_members sm ON sm.application_id = a.id AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id AND s.retired_at IS NULL
"""

SITE_OF_PROJECT_SQL = """
SELECT p.external_ref, s.site_key
FROM projects p
JOIN site_members sm ON sm.project_id = p.id AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id AND s.retired_at IS NULL
"""

# Barbour links some adjacent-power applications directly to a project
# (project_applications) — the documentary tie that used to put them in
# the project's site through the clusterer's linked_ids set, until the
# adjacent_power veto was extended to it. The linkage itself is evidence
# and survives here as a cohort row to the project's site.
PROJECT_LINKED_SQL = """
SELECT pa.application_id, p.external_ref, s.site_key
FROM project_applications pa
JOIN projects p ON p.id = pa.project_id
JOIN site_members sm ON sm.project_id = p.id AND sm.retired_at IS NULL
JOIN sites s ON s.id = sm.site_id AND s.retired_at IS NULL
"""


@dataclass(frozen=True)
class Relation:
    site_id: int
    site_key: str
    application_id: int
    application_ref: str
    basis: str
    distance_m: float | None
    evidence: str


def _metres(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance, the same arithmetic the clustering uses."""
    inner = (cos(radians(lat1)) * cos(radians(lat2))
             * cos(radians(lon2) - radians(lon1))
             + sin(radians(lat1)) * sin(radians(lat2)))
    return 6371000.0 * acos(min(1.0, max(-1.0, inner)))


def resolve_token(token: str, *, site_of_app: dict, site_of_project: dict
                  ) -> tuple[str | None, str | None]:
    """A `discovered_via` token as (site_key, basis), or (None, None).

    Pulled out of `relations` because it is the part that fails quietly.
    A token names the record a sweep ran outward from, and only
    `energy_national:` names a site directly — `spatial:` gives an
    application reference and `barbour:` a Ptno, both of which have to be
    resolved to whichever site now holds them. Left unresolved they do not
    error; they simply produce no documentary row, and the record drops to
    bare proximity with nothing to say it lost anything. That is what
    happened on the first run of this module: four records with recorded
    provenance were demoted to distance because the tokens were compared
    against site keys they were never going to match.
    """
    if token.startswith("energy_national:"):
        return token.split(":", 1)[1], "discovery"
    if token.startswith("spatial:"):
        key = site_of_app.get(token.split(":", 1)[1])
        return (key, "cohort") if key else (None, None)
    if token.startswith("barbour:"):
        key = site_of_project.get(token.split(":", 1)[1])
        return (key, "cohort") if key else (None, None)
    # A cohort is a set of sites, not a site: there is no single record to
    # relate to, so this attaches nothing. Stated rather than dropped.
    return None, None


def relations(conn, *, proximity_km: float = PROXIMITY_KM) -> list[Relation]:
    """Every relationship an adjacent-power record has to a live site.

    A record can hold more than one: found through site A and standing
    within the radius of B and C is three rows, because each says
    something different and none of them supersedes the others.
    """
    with conn.cursor() as cur:
        cur.execute(SITES_SQL)
        sites = cur.fetchall()
        cur.execute(ADJACENT_SQL)
        records = cur.fetchall()
        cur.execute(SITE_OF_APP_SQL)
        site_of_app = dict(cur.fetchall())
        cur.execute(SITE_OF_PROJECT_SQL)
        site_of_project = dict(cur.fetchall())
        cur.execute(PROJECT_LINKED_SQL)
        project_linked: dict[int, list[tuple[str, str]]] = {}
        for app_id, ptno, skey in cur.fetchall():
            project_linked.setdefault(app_id, []).append((ptno, skey))

    by_key = {key: (sid, lat, lon) for sid, key, lat, lon in sites}
    located = [(sid, key, lat, lon) for sid, key, lat, lon in sites
               if lat is not None and lon is not None]

    out: list[Relation] = []
    for app_id, ref, via, lat, lon in records:
        seen: set[tuple[int, str]] = set()

        # Barbour's own linkage first: a project_applications row ties
        # the record to a project, and the project to its site. This is
        # the strongest documentary basis here — the catalogue asserts
        # the connection outright — and it is what carried these records
        # into membership before the veto reached linked_ids.
        for ptno, key in project_linked.get(app_id, ()):
            if key not in by_key or (by_key[key][0], "cohort") in seen:
                continue
            sid, slat, slon = by_key[key]
            d = (_metres(lat, lon, slat, slon)
                 if None not in (lat, lon, slat, slon) else None)
            seen.add((sid, "cohort"))
            out.append(Relation(sid, key, app_id, ref, "cohort", d,
                                f"linked by Barbour to project {ptno}, "
                                f"whose site this is"))

        # Documentary next. `energy_national:<site_key>` names the site
        # the search ran outward from, so the corpus already holds the
        # relationship that membership was standing in for.
        for token in via or []:
            key, basis = resolve_token(token, site_of_app=site_of_app,
                                       site_of_project=site_of_project)
            if not key or key not in by_key or (by_key[key][0], basis) in seen:
                continue
            sid, slat, slon = by_key[key]
            d = (_metres(lat, lon, slat, slon)
                 if None not in (lat, lon, slat, slon) else None)
            seen.add((sid, basis))
            out.append(Relation(sid, key, app_id, ref, basis, d,
                                f"discovered_via {token}"))

        # Then distance, which finds candidates and settles nothing.
        if lat is None or lon is None:
            continue
        for sid, key, slat, slon in located:
            d = _metres(lat, lon, slat, slon)
            if d > proximity_km * 1000 or (sid, "proximity") in seen:
                continue
            seen.add((sid, "proximity"))
            out.append(Relation(sid, key, app_id, ref, "proximity", d,
                                f"within {proximity_km:g} km of the site pin "
                                f"({d / 1000:.2f} km) — proximity is a "
                                f"candidate, not a supply relationship"))
    return out


def materialise(conn, *, proximity_km: float = PROXIMITY_KM) -> dict:
    """Write the relationships, retiring rows that no longer hold.

    Idempotent on unchanged input: a row already live under the same
    (site, application, basis) keeps its `materialised_at`, so a re-run
    that changes nothing writes nothing.
    """
    found = relations(conn, proximity_km=proximity_km)
    wanted = {(r.site_id, r.application_id, r.basis): r for r in found}
    with conn.cursor() as cur:
        cur.execute("""SELECT site_id, application_id, basis
                       FROM site_adjacent_power WHERE retired_at IS NULL""")
        live = {tuple(r) for r in cur.fetchall()}
        added = retired = 0
        for key, r in wanted.items():
            if key in live:
                continue
            cur.execute(
                """INSERT INTO site_adjacent_power
                       (site_id, application_id, basis, distance_m, evidence)
                   VALUES (%s, %s, %s, %s, %s)""",
                (r.site_id, r.application_id, r.basis, r.distance_m, r.evidence))
            added += 1
        for key in live - set(wanted):
            cur.execute(
                """UPDATE site_adjacent_power SET retired_at = now()
                   WHERE site_id=%s AND application_id=%s AND basis=%s
                     AND retired_at IS NULL""", key)
            retired += 1
    conn.commit()
    by_basis: dict[str, int] = {}
    for r in found:
        by_basis[r.basis] = by_basis.get(r.basis, 0) + 1
    return {"relations": len(found), "added": added, "retired": retired,
            "by_basis": by_basis,
            "applications": len({r.application_id for r in found}),
            "sites": len({r.site_id for r in found})}
