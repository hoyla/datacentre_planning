"""What kind of site each row in the sites list is, derived from verdicts.

Issue #159, specced in the ROADMAP. The sites list does not say which of
its rows are datacentres, and the corridor split made the consequence
visible: the Clearstone gas generator, the Western International Market
substation and the Old Vinyl Factory sit in the list as their own rows,
indistinguishable at a glance from the campuses beside them.

**A class is never an ejection.** The corpus keeps adjacency and
disguise-suspects deliberately — a substation beside a campus is how the
energy story is told, and a disguise suspect is precisely the thing this
investigation exists to find. The class is a filter and a row treatment,
so a reporter can say "show me only the datacentres" or "show me what
else is here", and never a reason to drop a row from the corpus.

**The fold-in is the clustering's, reused rather than reinvented.**
Verdicts are append-only and multi-generational: an application
classified `DC` under the v1 rubric may later be classified `new_build`
(or `procedural`, or `adjacent_power`) under `dc_build`. `dcp/sites.py`
already resolves this for universe membership — latest verdict per
(application, rubric), the rubric read from `raw_response->>'rubric'`
with NULL meaning v1 — and the comment above that SQL records what
happens when it is done more simply: the 2026-08-06 catalogue sweep
collapsed the universe from 1,046 applications to 629 mid-run. This
module folds the same way, so a site cannot be in the universe on one
rule and classified on another.

**Derived, never stored.** Like `dcp/site_cohorts.py`, this is computed
from the database at build time. A stored class would be a fourth thing
to keep in step with re-triage, re-materialisation and adjudication, and
the first one to go stale silently.

**Every class carries its provenance.** A site's class names the member
applications and folded verdicts that produced it, so a reporter asking
"why is this row greyed out?" gets an answer with references in it
rather than an assertion. Principle 7: provenance is non-negotiable.
"""

from __future__ import annotations

from dataclasses import dataclass

# The two triage vocabularies, as the corpus actually holds them
# (measured 2026-08-27). Naming them here is not decoration: an
# unrecognised verdict must fail loudly rather than fall quietly into
# `procedural_only`, which is the class that would hide a new rubric's
# arrival.
DC_BUILD_VERDICTS = frozenset({
    "new_build", "expansion_refurb", "pre_application", "enabling_works",
    "procedural", "adjacent_power", "unknown", "not_dc"})
V1_VERDICTS = frozenset({"DC", "adjacent", "unknown", "unrelated"})

# DC-positive under dc_build. `pre_application` and `enabling_works` are
# in by decision (ROADMAP, agreed with Luke 2026-08-27): a site whose
# only application is a datacentre pre-app is a datacentre site in the
# pipeline, which is what this investigation is for, and enabling works
# are the earthworks and accesses of a scheme that is one.
DC_POSITIVE = frozenset({
    "new_build", "expansion_refurb", "pre_application", "enabling_works"})

DATACENTRE = "datacentre"
DISGUISE_SUSPECT = "disguise_suspect"
ADJACENT_POWER = "adjacent_power"
PROCEDURAL_ONLY = "procedural_only"
# The fifth state, which the ROADMAP's four did not anticipate and the
# measurement found: 19 live sites are Barbour project records with no
# planning application at all, so there is no verdict to fold. They are
# not procedural — "NEXT GENERATION DATA - DATA CENTRE EXTENSION" greyed
# out as procedural would be a plain error — and they are not asserted
# as datacentres either, because that would adopt Barbour's own
# categorisation as ours. The class says what is true: the corpus knows
# this site from the project catalogue and has no planning record to
# read.
BARBOUR_ONLY = "barbour_only"

# Registry order is precedence order, and precedence is what makes the
# classification assert the least. A site holding both a disguise
# suspect and a substation is filed as the suspect, because calling it
# adjacency would dismiss the very thing worth looking at; "unclear
# beats wrong" (HISTORY, the ranking rule). BARBOUR_ONLY sits outside
# the contest — it applies only where there is nothing to contest.
CLASS_ORDER = (DATACENTRE, DISGUISE_SUSPECT, ADJACENT_POWER,
               PROCEDURAL_ONLY, BARBOUR_ONLY)

CLASS_LABELS = {
    DATACENTRE: "Datacentre",
    DISGUISE_SUSPECT: "Disguise suspect",
    ADJACENT_POWER: "Adjacent power",
    PROCEDURAL_ONLY: "Procedural only",
    BARBOUR_ONLY: "No planning record",
}

# What each class means, in the words the reader and the workbook both
# use. Written for a reporter who has not read this module: each says
# what the documents establish, never what it implies about the
# applicant.
CLASS_DESCRIPTIONS = {
    DATACENTRE: (
        "At least one application here is a datacentre proposal, "
        "expansion, pre-application or its enabling works."),
    DISGUISE_SUSPECT: (
        "No application here is stated as a datacentre, and at least "
        "one could not be ruled out — a large single-use building "
        "described without naming its use. Kept for exactly that "
        "reason."),
    ADJACENT_POWER: (
        "Energy infrastructure near a datacentre rather than a "
        "datacentre: substations, grid connections, generation. In the "
        "corpus because the energy story needs it."),
    PROCEDURAL_ONLY: (
        "Nothing here is stated as a datacentre: procedural "
        "applications such as conditions discharges, applications a "
        "later reading ruled out, or applications not yet triaged."),
    BARBOUR_ONLY: (
        "Known from the Barbour project catalogue, with no planning "
        "application in the corpus to read — so no verdict has been "
        "reached either way."),
}

CLASS_ERROR_HINT = (
    "add it to DC_BUILD_VERDICTS/V1_VERDICTS and decide its class "
    "deliberately; falling through to procedural_only would hide a new "
    "rubric's arrival")


class SiteClassError(ValueError):
    """A verdict this module does not know how to classify."""


@dataclass(frozen=True)
class Member:
    """One application's contribution to its site's class."""
    application_ref: str
    dc_build_verdict: str | None
    v1_verdict: str | None

    @property
    def folded(self) -> str | None:
        """The clustering's fold: dc_build wins where it has spoken."""
        return self.dc_build_verdict or self.v1_verdict


@dataclass(frozen=True)
class SiteClass:
    site_key: str
    key: str                        # one of CLASS_ORDER
    members: tuple[Member, ...]     # every live member, for provenance
    # Barbour project refs where the site has them. Carried for the
    # BARBOUR_ONLY case, whose provenance is a project rather than an
    # application, and so that a datacentre site can still show what
    # catalogue record it is joined to.
    project_refs: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return CLASS_LABELS[self.key]

    @property
    def description(self) -> str:
        return CLASS_DESCRIPTIONS[self.key]

    @property
    def is_datacentre(self) -> bool:
        return self.key == DATACENTRE

    @property
    def deciding(self) -> tuple[Member, ...]:
        """The members that produced the class — the provenance a reader
        is shown. For `procedural_only` every member is deciding, since
        the class is the absence of anything stronger."""
        if self.key == PROCEDURAL_ONLY:
            return self.members
        return tuple(m for m in self.members if _member_class(m) == self.key)


def _member_class(m: Member) -> str:
    """One member's own class, before the site's members are combined."""
    dc, v1 = m.dc_build_verdict, m.v1_verdict
    if dc is not None and dc not in DC_BUILD_VERDICTS:
        raise SiteClassError(
            f"{m.application_ref}: unknown dc_build verdict {dc!r} — "
            + CLASS_ERROR_HINT)
    if v1 is not None and v1 not in V1_VERDICTS:
        raise SiteClassError(
            f"{m.application_ref}: unknown v1 verdict {v1!r} — "
            + CLASS_ERROR_HINT)

    if dc in DC_POSITIVE:
        return DATACENTRE
    # A v1 `DC` counts only where dc_build has not spoken. Where it has,
    # its verdict is the later reading of the same application and the
    # one the clustering trusts; a dc_build `not_dc` over a v1 `DC` is a
    # correction, not a contradiction to be split.
    if dc is None and v1 == "DC":
        return DATACENTRE
    # The disguise-suspect class by the triage prompt's own definition
    # (dcp/triage.py: "unknown (disguise suspect: very large single-use
    # …)"). v1 `unknown` is not the same thing — that rubric used it for
    # sparse descriptions generally — so it does not qualify a site.
    if dc == "unknown":
        return DISGUISE_SUSPECT
    if dc == "adjacent_power" or (dc is None and v1 == "adjacent"):
        return ADJACENT_POWER
    return PROCEDURAL_ONLY


def classify(site_key: str, members: list[Member] | tuple[Member, ...],
             project_refs: tuple[str, ...] = ()) -> SiteClass:
    """A site's class from its live members, strongest class winning."""
    members, project_refs = tuple(members), tuple(project_refs)
    if not members:
        # Nothing to fold. With a Barbour record behind it the site is
        # BARBOUR_ONLY; without one it should not exist, and saying so
        # is better than filing it under a class that reads as a
        # finding.
        return SiteClass(site_key,
                         BARBOUR_ONLY if project_refs else PROCEDURAL_ONLY,
                         members, project_refs)
    seen = {_member_class(m) for m in members}
    for key in CLASS_ORDER:
        if key in seen:
            return SiteClass(site_key, key, members, project_refs)
    return SiteClass(site_key, PROCEDURAL_ONLY, members, project_refs)


MEMBERS_SQL = """
    WITH per_rubric AS (
      SELECT DISTINCT ON (application_id, coalesce(raw_response->>'rubric','v1'))
             application_id,
             coalesce(raw_response->>'rubric','v1') AS rubric,
             verdict
      FROM triage
      ORDER BY application_id, 2, inserted_at DESC),
    folded AS (
      SELECT application_id,
             max(verdict) FILTER (WHERE rubric = 'dc_build') AS dc_build_verdict,
             max(verdict) FILTER (WHERE rubric = 'v1')       AS v1_verdict
      FROM per_rubric GROUP BY application_id)
    SELECT s.site_key, a.application_ref,
           f.dc_build_verdict, f.v1_verdict
    FROM sites s
    JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
    JOIN applications a ON a.id = m.application_id
    LEFT JOIN folded f ON f.application_id = a.id
    WHERE s.retired_at IS NULL
    ORDER BY s.site_key, a.application_ref
"""

# Every live site, so that a site with no application members still gets
# a class. Joining only through applications silently dropped 19 sites
# — the Barbour project-only records — which is how BARBOUR_ONLY came to
# exist.
SITES_SQL = """
    SELECT s.site_key,
           array_remove(array_agg(DISTINCT p.external_ref), NULL)
    FROM sites s
    LEFT JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
    LEFT JOIN projects p ON p.id = m.project_id
    WHERE s.retired_at IS NULL
    GROUP BY s.site_key
"""


def compute_all(conn) -> dict[str, SiteClass]:
    """Every live site's class, keyed by site_key.

    One pair of queries for the corpus, in the manner of
    site_cohorts.compute_all: the exporters call this once and index it,
    rather than asking per row. Every live site appears in the result —
    a site missing from the map would be a row the reader cannot filter
    and cannot explain.
    """
    by_site: dict[str, list[Member]] = {}
    with conn.cursor() as cur:
        cur.execute(MEMBERS_SQL)
        for site_key, ref, dc, v1 in cur.fetchall():
            by_site.setdefault(site_key, []).append(Member(ref, dc, v1))
        cur.execute(SITES_SQL)
        sites = {k: tuple(refs or ()) for k, refs in cur.fetchall()}
    return {k: classify(k, by_site.get(k, ()), projects)
            for k, projects in sites.items()}


def counts(classes: dict[str, SiteClass]) -> dict[str, int]:
    """Class counts in registry order, for the measurement the ROADMAP
    asks for before any styling."""
    out = {k: 0 for k in CLASS_ORDER}
    for sc in classes.values():
        out[sc.key] += 1
    return out
