"""Site clustering and materialisation for the dc_build universe.

A *site* is the unit the investigation reasons about: a cluster of
planning applications and/or Barbour projects joined by explicit
project↔application links, family edges (``associated_id`` references),
or spatial proximity (≤ 1 km by default — campus scale). The clustering
method is the one validated by the Barbour superset reconciliation
(scripts/barbour_superset.py, 2026-08-03); this module is its reusable
extraction, plus materialisation into the ``sites`` / ``site_members``
tables (migration 006).

The spatial join treats proximity as same-site evidence, which is false
in dense corridors: two campuses can sit closer together than the
radius. ``data/priors/site_partitions.yaml`` holds the hand-adjudicated
campus boundaries the radius cannot see — a partitioned node takes no
spatial edge to a node outside its partition, while documentary edges
(project links, family references) are honoured and extend the
partition to the nodes they attach.

Identity rules (stable across re-materialisation):

- A cluster containing at least one real (non-tender) Barbour project is
  keyed ``PTNO-<lowest Ptno>``.
- Otherwise ``SITE-<alphabetically first application_ref whose figures
  stand as the site's>`` — a ``not_dc`` member the family door admitted
  never names the site (since 2026-09-10); a cluster with no such
  member keys on its first application.

Membership is recomputable; keys persist. A re-run updates membership,
retires sites that no longer emerge from the clustering (``retired_at``
set, never deleted), and revives them if they re-emerge. Derived data is
kept out of ``projects`` deliberately: that table holds Barbour records
verbatim, and clustering is our inference (principle 3).

Membership is not standing. A member the family door admitted with a
latest dc_build verdict of ``not_dc`` stays a member, with its documents,
and its adjudicated figures do not stand as the site's capacity
(``site_members.figure_standing``, migration 034) unless
``data/priors/not_dc_standing.yaml`` admits that one application with
its evidence; ``procedural`` paperwork whose only family parents are
excluded follows them. Every site-level capacity rollup carries the
predicate; ``tests/test_figure_standing.py`` asserts it over the tree.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

# `build_clusters`' data directory resolves against the package root,
# never the working directory. Both loaders below return empty for an
# absent file, and both guards beside them check only the keys they are
# handed — so a relative default makes a run from anywhere else load no
# priors, raise nothing, and re-merge the campuses the partitions exist
# to keep apart, changing site keys while reporting clean. Same form as
# site_facilities, map and site_aliases, for the same reason; here the
# default is a parameter's rather than a module constant's, so callers
# passing `data_dir` explicitly are untouched.
ROOT = Path(__file__).resolve().parent.parent


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


def _load_inferred_coords(
    data_dir: Path,
) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    """Coordinate priors, two kinds in one file: `ref:` entries backfill
    applications whose raw record carries no coordinates; `ptno:` entries
    override a Barbour project's own pin where the record contradicts
    itself (its address names one place, its coordinates another). The
    provider's figures stay untouched in projects/raw_metadata per the
    never-mutate principle — the prior applies at clustering time."""
    import yaml
    by_ref: dict[str, tuple[float, float]] = {}
    by_ptno: dict[str, tuple[float, float]] = {}
    prior_path = data_dir / "priors" / "inferred_coords.yaml"
    if prior_path.exists():
        payload = yaml.safe_load(prior_path.read_text()) or {}
        for e in payload.get("entries") or []:
            if e.get("ref"):
                by_ref[e["ref"]] = (float(e["lat"]), float(e["lon"]))
            elif e.get("ptno"):
                by_ptno[str(e["ptno"])] = (float(e["lat"]), float(e["lon"]))
    return by_ref, by_ptno


def _load_project_exclusions(data_dir: Path) -> dict[str, str]:
    """ptno -> reason, from `data/priors/project_exclusions.yaml`.

    A Barbour project a person has read and excluded, by exception and
    with its evidence in the file: it anchors no site and joins none.
    Empty when the file is absent. Validation — every entry must name a
    project the corpus holds — happens in `build_clusters`, where the
    projects are in hand, and fails the run as the other priors do.
    """
    import yaml
    path = data_dir / "priors" / "project_exclusions.yaml"
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    out: dict[str, str] = {}
    for e in payload.get("exclusions") or []:
        ptno = str(e["ptno"]).strip()
        for field in ("reason", "evidence", "date"):
            if not str(e.get(field) or "").strip():
                raise ValueError(f"project_exclusions.yaml: {ptno} has no {field}")
        if ptno in out:
            raise ValueError(f"project_exclusions.yaml: duplicate entry for {ptno}")
        out[ptno] = str(e["reason"]).strip()
    return out


FIGURE_STANDINGS = ("counts", "not_dc_excluded", "not_dc_admitted")


def _load_not_dc_standing(data_dir: Path) -> dict[str, dict]:
    """application_ref (upper) -> entry, from
    `data/priors/not_dc_standing.yaml`.

    An application triage calls `not_dc` whose documents a person has
    read and found to be the data centre's own paperwork — a reserved
    matters on a data-centre outline, or the outline itself — so its
    adjudicated figures may stand as the site's (migration 034). Empty
    when the file is absent. Validation — every entry must name an
    application the corpus holds, a live member of the site it names,
    with a `not_dc` verdict — happens in `build_clusters`, where the
    clusters are in hand, and fails the run as the other priors do.
    """
    import yaml
    path = data_dir / "priors" / "not_dc_standing.yaml"
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    out: dict[str, dict] = {}
    for e in payload.get("admissions") or []:
        ref = str(e.get("application_ref") or "").strip()
        if not ref:
            raise ValueError("not_dc_standing.yaml: an entry has no application_ref")
        for field in ("site_key", "reason", "evidence", "date", "decided_by"):
            if not str(e.get(field) or "").strip():
                raise ValueError(f"not_dc_standing.yaml: {ref} has no {field}")
        if ref.upper() in out:
            raise ValueError(f"not_dc_standing.yaml: duplicate entry for {ref}")
        out[ref.upper()] = {"ref": ref, "site_key": str(e["site_key"]).strip(),
                            "reason": str(e["reason"]).strip()}
    return out


def _assign_standing(groups: list[list[dict]], admitted: dict[str, dict],
                     fam_edges: list[tuple[int, int, str]] = ()) -> None:
    """Set `figure_standing` and `standing_reason` on every application
    in every group, a group being the applications of one site-to-be.
    Runs before the site key is derived, because the key reads it
    (`_check_admissions` validates the admissions afterwards, once the
    keys exist).

    The rule (ROADMAP, the `not_dc` item; migration 034): a member whose
    latest dc_build verdict is `not_dc` keeps its membership and its
    documents, and its adjudicated figures do not stand as the site's —
    unless an entry in not_dc_standing.yaml says, with evidence, that
    the application is the data centre's own paperwork. The verdict is
    the dc_build one alone: the universe rule admits on either rubric,
    but dc_build is the rubric that has the concept, and it is the one
    `site_class` folds first. A v1 verdict never sets a standing.

    **Procedural paperwork follows its parents.** A `procedural`
    application is in the universe on the premise that its parent is a
    data centre's permission (a conditions discharge belongs to its
    parent's site). Where every family neighbour it has in the site is
    an excluded `not_dc` application, that premise has failed: it is
    the paperwork of the scheme triage said is not a data centre, and
    its figures describe that scheme — Eggborough's second discharge
    carried the station's 2,500 MW exactly as the first did (measured
    2026-09-10: 77 such members, 11 carrying figures, on 5 sites). So
    it inherits the exclusion, to a fixpoint, with the parents named in
    its reason. An admitted parent admits its paperwork the same way;
    a procedural with any counting neighbour, or with no family edge
    at all, keeps counting. `unknown` is never touched — a disguise
    suspect is what must not be dropped.

    An entry that names an application the corpus does not hold, one
    that is not a member of the site it names, or one whose verdict is
    not `not_dc` fails the run: a key moves when a cluster's anchor
    changes, and an admission that quietly stopped applying would put
    the site back on its largest excluded figure with nothing to say
    it had happened — the same contract as site_aliases.yaml.
    """
    for group in groups:
        for a in group:
            entry = admitted.get(a["ref"].upper())
            if a["verdict"] != "not_dc":
                a["figure_standing"], a["standing_reason"] = "counts", None
                if entry:
                    raise ValueError(
                        f"not_dc_standing.yaml admits {entry['ref']} for figures, "
                        f"but its latest dc_build verdict is {a['verdict']!r}, not "
                        f"not_dc; the entry asserts something the rule never "
                        f"asks — remove it")
            elif entry:
                a["figure_standing"] = "not_dc_admitted"
                a["standing_reason"] = entry["reason"]
            else:
                a["figure_standing"], a["standing_reason"] = "not_dc_excluded", None

    # Procedural paperwork follows its parents (docstring). Family edges
    # are undirected here — a discharge cites its parent, and the parent
    # is a neighbour either way — and only edges inside one site count:
    # a reference across two sites is a partition question, not standing.
    by_id = {a["id"]: a for group in groups for a in group}
    site_of = {a["id"]: i for i, group in enumerate(groups) for a in group}
    nbrs: dict[int, set[int]] = defaultdict(set)
    for x, y, _src in fam_edges:
        if x in by_id and y in by_id and site_of[x] == site_of[y]:
            nbrs[x].add(y)
            nbrs[y].add(x)
    changed = True
    while changed:
        changed = False
        for aid, a in by_id.items():
            if a["verdict"] != "procedural" or a["figure_standing"] != "counts":
                continue
            n = nbrs.get(aid)
            if n and all(by_id[i]["figure_standing"] == "not_dc_excluded"
                         for i in n):
                a["figure_standing"] = "not_dc_excluded"
                a["standing_reason"] = (
                    "procedural paperwork of "
                    + ", ".join(sorted(by_id[i]["ref"] for i in n))
                    + ", which triage calls not a data centre")
                changed = True


def _check_admissions(clusters: list[dict], admitted: dict[str, dict]) -> None:
    """Every admission names an application that is a member of the site
    it names, or the run fails — the alias file's contract, for the
    reason `_assign_standing`'s docstring gives. Runs once the keys
    exist, because the key of a `SITE-` site is derived from the
    standing the admission sets (an admitted outline keeps its key)."""
    seen: dict[str, tuple[str, str]] = {}
    for c in clusters:
        for a in c["apps"]:
            entry = admitted.get(a["ref"].upper())
            if entry:
                seen[a["ref"].upper()] = (c["site_key"], entry["site_key"])
    missing = sorted(e["ref"] for k, e in admitted.items() if k not in seen)
    if missing:
        raise ValueError(
            "not_dc_standing.yaml names applications that are not members "
            "of any site: " + ", ".join(missing)
            + " — a typo, or an application that left the universe; "
              "repoint or remove the entry")
    moved = sorted(f"{admitted[k]['ref']} (entry says {want}, cluster is {have})"
                   for k, (have, want) in seen.items() if have != want)
    if moved:
        raise ValueError(
            "not_dc_standing.yaml names a site its application is not a "
            "member of: " + "; ".join(moved)
            + " — the site key moved; repoint the entry")


def _load_site_partitions(data_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Hand-adjudicated campus boundaries: application_ref → partition
    name and Barbour Ptno → partition name. Empty when the priors file
    is absent."""
    import yaml
    app_part: dict[str, str] = {}
    proj_part: dict[str, str] = {}
    path = data_dir / "priors" / "site_partitions.yaml"
    if path.exists():
        payload = yaml.safe_load(path.read_text()) or {}
        for p in payload.get("partitions") or []:
            for ref in p.get("applications") or []:
                app_part[str(ref).upper()] = p["name"]
            for ptno in p.get("projects") or []:
                proj_part[str(ptno)] = p["name"]
    return app_part, proj_part


NOT_DC_VETO_MODES = ("off", "family", "family+project")


def _family_edges(apps: list[dict], by_ref: dict[str, dict]) -> list[tuple[int, int, str]]:
    """Family edges: an application naming another application's reference.

    `associated_id` is the clean signal, but many portals leave it empty
    and put the parent reference in the description instead — "Discharge
    of condition 20 (Travel Plan) on application P21/S0274/FUL". Without
    mining descriptions those applications cluster as singletons, which
    is how a Didcot condition-discharge ended up with its own "site"
    while its parent sat in the Amazon campus cluster.

    The description fallback fires only when `associated_id` is empty,
    and demands a stricter reference shape (3+ segments), mirroring the
    parent-backfill pass in dcp/sources/planit.py — dates like "1/2024"
    and use-class strings like "B1/B8" would otherwise create false
    links, and a false family edge silently merges two unrelated sites.
    """
    from dcp.sources.planit import _extract_candidate_refs

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
    return fam_edges


def _paperwork_of(seed: set[int], fam_edges: list[tuple[int, int, str]],
                  by_id: dict[int, dict]) -> set[int]:
    """The applications an excluded project's paperwork consists of.

    Starting from the applications the project linked, walk the family
    graph through nodes whose own verdict is `not_dc` or `procedural`
    and return every node reached, seeds included, that carries one of
    those verdicts. A `procedural` discharge is in the universe on the
    premise that its parent permission is a data centre's, and a person
    has just said this one's is not; a `not_dc` sibling was only ever
    admitted by the family door on the same premise. A node with a
    substantive verdict is neither taken nor walked through: an
    application that is a data centre on its own account stays whatever
    project once linked its parent, and so does its own paperwork.
    """
    neighbours: dict[int, set[int]] = {}
    for x, y, _src in fam_edges:
        neighbours.setdefault(x, set()).add(y)
        neighbours.setdefault(y, set()).add(x)
    taken: set[int] = set()
    frontier = [s for s in seed if s in by_id]
    while frontier:
        nid = frontier.pop()
        if nid in taken or by_id[nid]["verdict"] not in ("not_dc", "procedural"):
            continue
        taken.add(nid)
        frontier.extend(neighbours.get(nid, ()))
    return taken



def build_clusters(conn, *, radius_km: float = 1.0,
                   data_dir: Path = ROOT / "data",
                   family_skips_not_dc: bool = True,
                   not_dc_veto: str = "off") -> list[dict]:
    """Cluster the dc_build universe into sites.

    `not_dc_veto` decides whether an application whose latest dc_build
    verdict is `not_dc` may be ADMITTED through the two documentary
    doors that ignore the universe test: the family expansion
    ("family") and, additionally, a Barbour project link
    ("family+project"). "off" is the behaviour to 2026-09-02, under
    which 159 live members carried a `not_dc` verdict the universe rule
    would never have admitted — 29 of them carrying 360 adjudicated
    site-capacity figures — because both doors vetoed `adjacent_power`
    alone. Measured that day; the choice is Luke's and is made from a
    dry run of each mode (ROADMAP, the `not_dc` item).

    Returns a list of cluster dicts:
      {"apps": [{id, ref, desc, lat, lon, coord_source, verdict, joined_via}],
       "projects": [{id, ptno, title, lat, lon, is_tender, joined_via}],
       "classification": 'both'|'ours_only'|'barbour_covered'|'barbour_only'|'unlocatable',
       "site_key": str, "display_name": str|None,
       "lat": float|None, "lon": float|None, "coord_source": str|None}
    """

    inferred, inferred_proj = _load_inferred_coords(data_dir)

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
    #
    # `adjacent_power` is the one exception, and it vetoes (issue #252,
    # decided 2026-08-30): a substation, an energy centre or a standby
    # fleet consented in its own right relates to a data centre, it is
    # not part of one. Membership lent seven sites a capacity that was
    # not their own and forced shared infrastructure to pick one owner.
    # The veto applies whenever the latest dc_build verdict says
    # adjacent_power, a v1 'DC' notwithstanding — dc_build introduced
    # the concept precisely because v1 could not express it. These
    # records stay in the corpus and relate to sites through
    # site_adjacent_power (migration 032), which the reader renders.
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
                     AND coalesce(
                           max(verdict) FILTER (WHERE rubric = 'dc_build')
                             <> 'adjacent_power', true)
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
            # The prior wins where one exists. It was written as a
            # fallback for records that carry no coordinates, and every
            # entry is still one of those — but a portal can also publish
            # a coordinate that is simply wrong, and a wrong coordinate
            # does more damage than a missing one: it invents spatial
            # edges into whatever it lands on. Two Tower Hamlets records
            # for "Mulberry Place Town Hall, 5 Clove Crescent" are
            # geocoded 4.1 km west of the five other records carrying
            # that same address, and the pair welded the Shoreditch
            # cluster to the Docklands one. A prior is hand-written with
            # its derivation recorded, so where the two disagree the
            # prior is the better evidence.
            if ref in inferred:
                (lat, lon), src = inferred[ref], "inferred_prior"
            elif lx and ly:
                lat, lon, src = float(ly), float(lx), "application"
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

    # Project pin overrides, before any spatial reasoning: a wrong
    # provider pin creates spatial edges into whatever campus it lands
    # inside (Barbour placed the Wapseys Wood scheme 8.5 km south of its
    # own address line, within the former Akzo Nobel cluster's radius).
    # An unknown Ptno is a typo, and a typo silently leaves the false
    # edges standing — so it fails the run, as site_partitions.yaml does.
    unknown_pins = set(inferred_proj) - {str(p["ptno"]) for p in projects}
    if unknown_pins:
        raise ValueError(
            "inferred_coords.yaml names Barbour projects not in the corpus: "
            + ", ".join(sorted(unknown_pins)))
    for p in projects:
        if str(p["ptno"]) in inferred_proj:
            p["lat"], p["lon"] = inferred_proj[str(p["ptno"])]
            p["coord_inferred"] = True

    # A project a person has excluded anchors nothing and joins nothing,
    # and its paperwork leaves with it once the family edges exist to
    # say what that paperwork is (below, `_paperwork_of`). Unknown Ptno:
    # the same failure as the pins, for the same reason.
    excluded = _load_project_exclusions(data_dir)
    unknown_excl = set(excluded) - {str(p["ptno"]) for p in projects}
    if unknown_excl:
        raise ValueError(
            "project_exclusions.yaml names Barbour projects not in the corpus: "
            + ", ".join(sorted(unknown_excl)))
    excluded_ids = {p["id"] for p in projects if str(p["ptno"]) in excluded}
    excluded_links = {aid for pid, aid in links if pid in excluded_ids}
    projects = [p for p in projects if p["id"] not in excluded_ids]
    links = [(pid, aid) for pid, aid in links if pid not in excluded_ids]

    # The `not_dc` applications a person has admitted for figures
    # (migration 034). Loaded here beside the other priors; validated
    # against the clusters once they exist, at the end, because an
    # entry has to name the site its application is a member of.
    admitted = _load_not_dc_standing(data_dir)

    by_id = {a["id"]: a for a in apps}
    by_ref = {a["ref"].upper(): a for a in apps}

    # Campus partitions. An entry naming a ref or Ptno the corpus does
    # not hold is a typo, and a typo silently re-merges the campuses the
    # file exists to keep apart — so unknowns fail the run rather than
    # weaken the boundary.
    app_part, proj_part = _load_site_partitions(data_dir)
    ptnos = {str(p["ptno"]) for p in projects}
    unknown = ([r for r in app_part if r not in by_ref]
               + [n for n in proj_part if n not in ptnos])
    if unknown:
        raise ValueError(
            "site_partitions.yaml names records not in the corpus: "
            + ", ".join(sorted(unknown)))
    partition: dict[tuple, str] = {}
    for a in apps:
        name = app_part.get(a["ref"].upper())
        if name:
            partition[("A", a["id"])] = name
    for p in projects:
        name = proj_part.get(str(p["ptno"]))
        if name:
            partition[("P", p["id"])] = name

    if not_dc_veto not in NOT_DC_VETO_MODES:
        raise ValueError(f"not_dc_veto must be one of {NOT_DC_VETO_MODES}, "
                         f"not {not_dc_veto!r}")
    veto_family = not_dc_veto in ("family", "family+project")
    veto_project = not_dc_veto == "family+project"

    def _door_admits(aid: int, *, project: bool = False) -> bool:
        """Whether a documentary door may admit an application the
        universe test did not. `adjacent_power` is always refused
        (issue #252); `not_dc` is refused when the veto says so."""
        verdict = by_id[aid]["verdict"]
        if verdict == "adjacent_power":
            return False
        if verdict == "not_dc" and (veto_project if project else veto_family):
            return False
        return True

    fam_edges = _family_edges(apps, by_ref)
    if excluded_links:
        # An excluded project's paperwork leaves with it. Left in, the
        # one `procedural` discharge of Exeter College's extension —
        # in the universe because a discharge is presumed to be a data
        # centre's — re-anchored the same six applications as a new site
        # keyed on the parent, and the exclusion had changed a title for
        # a key (measured 2026-09-06). Only the project's direct link
        # was a link; the other five cite the parent's reference, so the
        # walk follows the family edges.
        taken = _paperwork_of(excluded_links, fam_edges, by_id)
        apps = [a for a in apps if a["id"] not in taken]
        by_id = {a["id"]: a for a in apps}
        by_ref = {a["ref"].upper(): a for a in apps}
        fam_edges = [e for e in fam_edges if e[0] not in taken and e[1] not in taken]

    dc_apps = [a for a in apps if a["in_universe"]]
    # A project-linked application joins its project's cluster whatever
    # triage made of it — Barbour's linkage is documentary evidence the
    # verdicts cannot see. The adjacent_power veto has to hold here too,
    # or it holds nowhere that matters: 18 of the 42 sited adjacent-power
    # records were project-linked and re-entered membership through this
    # set on the first materialisation after the veto shipped, Kingsnorth's
    # export-figure application among them. The Barbour linkage is not
    # discarded — dcp/adjacent_power.py records it as a documentary
    # (cohort) relationship to the project's site.
    linked_ids = {aid for _pid, aid in links
                  if aid in by_id and _door_admits(aid, project=True)}
    node_ids = {a["id"] for a in dc_apps} | linked_ids

    # The edges through which the family door admitted a node. Admission
    # used to be all the door did: the union below skips any edge with a
    # `not_dc` end (`family_skips_not_dc`), so an admitted `not_dc` node
    # was left to the spatial pass to glue in — and one with no
    # coordinates became a singleton and silently dropped out. Measured
    # 2026-09-02: 15 applications holding 2,130 documents, 14 of them
    # unlocated reserved matters citing an outline that is a member,
    # excluded from every artefact by an accident of geocoding while
    # their located siblings were members. So an edge that admits a node
    # also unites it with the node that admitted it, whatever the
    # verdict. Bridging is not reopened: a `not_dc` node is admitted by
    # exactly one edge — the first processed — and every later edge
    # between it and another admitted node is still skipped, so two
    # datacentre clusters cannot merge through it.
    admitting_edges: set[tuple[int, int]] = set()
    for x, y, _src in fam_edges:
        if x in node_ids or y in node_ids:
            # The adjacent_power veto holds here too: a family reference
            # from an in-universe application — a conditions discharge
            # citing the substation consent it discharges against, say —
            # would otherwise pull the vetoed record straight back into
            # membership. This expansion exists to admit *untriaged*
            # paperwork a family knows about, not to overrule a verdict.
            admitted_here = False
            if x not in node_ids and _door_admits(x):
                node_ids.add(x)
                admitted_here = True
            if y not in node_ids and _door_admits(y):
                node_ids.add(y)
                admitted_here = True
            if admitted_here:
                admitting_edges.add((x, y))

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
            if family_skips_not_dc and (x, y) not in admitting_edges and (
                    by_id[x]["verdict"] == "not_dc"
                    or by_id[y]["verdict"] == "not_dc"):
                continue
            uf.union(("A", x), ("A", y))
            via = "family" if src == "associated_id" else "family_description"
            _join(("A", x), via)
            _join(("A", y), via)

    # Documentary closure of the partitions, before any spatial edge is
    # considered: a node the record itself attaches to a partitioned
    # node (project link, family reference) belongs to that campus, so
    # it inherits the partition rather than acting as a bridge — without
    # this, one family edge into a partition plus one spatial edge out
    # of it would re-merge the campuses the partition separates. Two
    # partitions joined documentarily means the record contradicts the
    # hand adjudication; that is surfaced, never silently resolved.
    if partition:
        proj_by_id = {p["id"]: p for p in projects}
        comp = defaultdict(list)
        for node in ([("A", n) for n in node_ids]
                     + [("P", p["id"]) for p in projects]):
            comp[uf.find(node)].append(node)
        for members in comp.values():
            names = {partition[m] for m in members if m in partition}
            if len(names) > 1:
                labelled = sorted(
                    (by_id[i]["ref"] if k == "A"
                     else f"PTNO-{proj_by_id[i]['ptno']}")
                    + f"={partition[(k, i)]}"
                    for k, i in members if (k, i) in partition)
                raise ValueError(
                    "documentary edges join records from different site "
                    "partitions: " + ", ".join(labelled))
            if names:
                name = next(iter(names))
                for m in members:
                    partition.setdefault(m, name)

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
            # A spatial edge never crosses a partition boundary: within
            # the radius but on different campuses is exactly the case
            # the priors file adjudicates.
            if partition.get((k1, id1)) != partition.get((k2, id2)):
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

    # Standing first, keys second: a `SITE-` key is derived from the
    # first application whose figures stand as the site's, so the
    # standing has to be known before the key is (migration 034; the
    # key rule decided by Luke, 2026-09-10).
    _assign_standing([c["apps"] for c in raw.values()], admitted, fam_edges)

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
                             "inferred_prior"
                             if real_projects[0].get("coord_inferred")
                             else "barbour")
        else:
            # The first application whose figures stand as the site's,
            # in reference order — not merely the first. A key derived
            # from a `not_dc` member named eighteen sites after the
            # scheme triage said they were not (Eggborough's data
            # centres after the station's discharge, West Burton's
            # after the battery), and lent the derived name to it; an
            # admitted outline counts and keeps its key. A site with no
            # counting member at all — Rhondda's, one application, in
            # the universe on its v1 verdict — keys on what it has.
            lead = next((a for a in c["apps"]
                         if a["figure_standing"] != "not_dc_excluded"),
                        c["apps"][0])
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
    # The standing was assigned above and is written to site_members by
    # `materialise`; with the keys now known, check every admission
    # names the site its application is in.
    _check_admissions(clusters, admitted)
    return clusters


def preflight(conn, clusters: list[dict]) -> dict:
    """What a materialise() of these clusters would change, before it
    changes it.

    Retiring a site is not the destructive part — the row survives and
    the clustering is reproducible. What does not survive is anything
    hand-adjudicated *against* a site id: a capacity claim matched to a
    site by a person, with written evidence, renders through a join on
    `retired_at IS NULL` and so vanishes from the reader without failing
    anything. That is the one outcome here a re-run cannot undo by
    itself, because re-pointing the match needs the same human judgement
    that made it.

    Returns {"new": [...], "retiring": [...], "orphaned_claims": [...],
    "leaving": [...], "moved": [...], "standing": [...],
    "stale_member_rows": n}, where an orphaned claim carries the site
    it would lose, the cluster its members move to, and enough of the
    claim to identify it; a moved application carries the key it leaves
    and the key it joins; and a standing change carries the member, its
    site, and the figure standing it has and would have — because a
    member whose figures stop counting changes what its site reports
    without any site, membership or claim moving at all.
    """
    keys = {c["site_key"] for c in clusters}
    app_to_key, proj_to_key = {}, {}
    app_refs: set[str] = set()
    standing_of: dict[int, str] = {}
    for c in clusters:
        for a in c["apps"]:
            app_to_key[a["id"]] = c["site_key"]
            app_refs.add(a["ref"])
            standing_of[a["id"]] = a.get("figure_standing", "counts")
        for p in c["projects"]:
            proj_to_key[p["id"]] = c["site_key"]

    with conn.cursor() as cur:
        cur.execute("SELECT site_key FROM sites")
        known = {r[0] for r in cur.fetchall()}
        cur.execute("""
            SELECT s.id, s.site_key FROM sites s
            WHERE s.retired_at IS NULL ORDER BY s.site_key""")
        live = cur.fetchall()
        retiring = [(sid, key) for sid, key in live if key not in keys]

        orphaned = []
        for site_id, site_key in retiring:
            cur.execute("""
                SELECT cl.claim_name, m.confidence, m.method
                FROM capacity_claim_matches m
                JOIN capacity_claims cl ON cl.id = m.claim_id
                WHERE m.site_id = %s AND m.retired_at IS NULL
                ORDER BY cl.claim_name""", (site_id,))
            claims = cur.fetchall()
            if not claims:
                continue
            cur.execute("""
                SELECT application_id, project_id FROM site_members
                WHERE site_id = %s AND retired_at IS NULL""", (site_id,))
            dests = sorted({(app_to_key.get(a) if a else proj_to_key.get(p))
                            or "(leaves the universe)"
                            for a, p in cur.fetchall()})
            for claim_name, confidence, method in claims:
                orphaned.append({
                    "site_id": site_id, "site_key": site_key,
                    "claim_name": claim_name, "confidence": confidence,
                    "method": method, "members_move_to": dests,
                })

        # Applications that are live members today and in no cluster
        # tomorrow: they leave the universe, and every figure, document
        # and finding on them leaves the site with them. Retiring a site
        # is visible; a member quietly dropping from a site that survives
        # is not, which is why it is listed here by name.
        cur.execute("""
            SELECT a.id, a.application_ref, s.site_key, m.figure_standing
            FROM site_members m
            JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
            JOIN applications a ON a.id = m.application_id
            WHERE m.retired_at IS NULL
            ORDER BY s.site_key, a.application_ref""")
        _rows = cur.fetchall()
        live_members = [(aid, ref, key) for aid, ref, key, _st in _rows]
        live_standing = {aid: st for aid, _ref, _key, st in _rows}
        leaving = [(ref, key) for _aid, ref, key in live_members
                   if ref not in app_refs]
        # Members whose figure standing would change (migration 034):
        # nothing above sees them — the site survives, the member stays,
        # no claim moves — and yet the site's headline figure, its
        # cohort memberships and its reading input all change. Listed
        # by name, old standing to new, the way a move is.
        standing = sorted(
            (ref, app_to_key[aid], live_standing[aid], standing_of[aid])
            for aid, ref, _key in live_members
            if aid in app_to_key and live_standing[aid] != standing_of[aid])
        # Applications that are live members today and members of a
        # DIFFERENT surviving site tomorrow. Neither list above sees
        # them: the site is not retiring, the application is not
        # leaving, and yet its documents change folder, its findings
        # change page and the site it left may change key. This is the
        # one thing "build the clusters both ways and diff" needs that
        # nothing here reported until 2026-09-06 — the relation-table
        # work (ROADMAP) switches no consumer until this list is empty
        # or explained. Applications only: a project moving between
        # sites is a Barbour linkage question, not a family-edge one.
        moved = [(ref, key, app_to_key[aid]) for aid, ref, key in live_members
                 if aid in app_to_key and app_to_key[aid] != key]
        # Membership rows still live on sites already retired. The
        # materialise used to retire the site and leave these standing,
        # so a row on a dead site read `retired_at IS NULL` to every
        # "is this a member" test — which is how four adjacent-power
        # applications' documents lost their Drive home (2026-09-02).
        # `materialise` now retires them; this says how many.
        cur.execute("""
            SELECT count(*) FROM site_members m
            JOIN sites s ON s.id = m.site_id
            WHERE s.retired_at IS NOT NULL AND m.retired_at IS NULL""")
        stale_member_rows = cur.fetchone()[0]

    return {"new": sorted(keys - known),
            "retiring": [k for _sid, k in retiring],
            "orphaned_claims": orphaned,
            "leaving": leaving,
            "moved": moved,
            "standing": standing,
            "stale_member_rows": stale_member_rows}


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
                # The standing travels with the membership row and is
                # rewritten on revive exactly as `joined_via` is: it is
                # a fact about this materialise's verdicts and priors,
                # not history, and the history is the materialise log.
                cur.execute("""
                    INSERT INTO site_members (site_id, application_id, joined_via,
                                              figure_standing, standing_reason)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (site_id, application_id) WHERE application_id IS NOT NULL
                    DO UPDATE SET joined_via=EXCLUDED.joined_via,
                                  figure_standing=EXCLUDED.figure_standing,
                                  standing_reason=EXCLUDED.standing_reason,
                                  materialised_at=now(), retired_at=NULL""",
                    (site_id, a["id"], a["joined_via"],
                     a.get("figure_standing", "counts"),
                     a.get("standing_reason")))
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
        # A retired site's membership rows retire with it. Until
        # 2026-09-02 they did not, so a row on a dead site still read
        # `retired_at IS NULL` to every query asking "is this application
        # a member of something" — 65 such rows on 63 applications, and
        # four adjacent-power applications whose only membership was on a
        # #252-retired site were staged nowhere and lost their Drive
        # copies to the 2.11 prune. This sweeps every retired site, not
        # only this run's, so the legacy rows go with the first run after
        # the fix. The revive path above already re-inserts a member on
        # its way back, so nothing is lost by retiring here.
        cur.execute("""
            UPDATE site_members m SET retired_at=now()
            FROM sites s
            WHERE s.id = m.site_id AND s.retired_at IS NOT NULL
              AND m.retired_at IS NULL
            RETURNING m.id""")
        summary["members_retired_with_site"] = len(cur.fetchall())
    return summary
