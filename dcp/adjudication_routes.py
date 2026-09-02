"""Which route a power figure's adjudication belongs to.

Power adjudication is split by consequence, not by preference
(ARCHITECTURE, "Which model runs which task"; docs/MODELS.md). A figure
on a site that carries no adjudicated capacity at all can set that
site's headline number, so it goes to the Sonnet subagent route
(`scripts/adjudicate_subagent.py`), the same model as the primary pass.
Everything else is the long tail and goes to the OpenAI batch
(`scripts/adjudicate_openai.py`), which does the same work for a few
dollars.

The rule lived in one script's SQL and the other script's docstring
until 2026-09-02, when two figures on a site with no capacity — Creek
Way, Rainham, read for the first time that evening — were submitted to
the long tail because the runbook's step 1 named only that script.
This module is the rule, read by both routes, so neither can drift.
"""

from __future__ import annotations

# The rubric version both routes answer under. A figure adjudicated by
# either at this version is settled for both.
PROMPT_VERSION = "power-1.0"


def consequential_finding_ids(conn, prompt_version: str = PROMPT_VERSION) -> set[int]:
    """Ids of unadjudicated power figures on live sites holding no
    `site_capacity` verdict — the set where a verdict moves a headline."""
    with conn.cursor() as cur:
        cur.execute("""
            WITH capped AS (
              SELECT DISTINCT m.site_id
              FROM power_adjudication pa
              JOIN findings f ON f.id = pa.finding_id
              JOIN site_members m ON m.application_id = f.application_id
                                 AND m.retired_at IS NULL
              WHERE pa.verdict = 'site_capacity')
            SELECT DISTINCT f.id
            FROM findings f
            JOIN site_members m ON m.application_id = f.application_id
                               AND m.retired_at IS NULL
            JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
            WHERE f.value_number IS NOT NULL
              AND m.site_id NOT IN (SELECT site_id FROM capped)
              AND NOT EXISTS (
                    SELECT 1 FROM power_adjudication p
                    WHERE p.finding_id = f.id
                      AND p.prompt_version = %s)""", (prompt_version,))
        return {r[0] for r in cur.fetchall()}


def split_by_consequence(apps: list[dict], consequential: set[int]
                         ) -> tuple[list[dict], list[dict]]:
    """Divide a cohort of applications (each with `figures` carrying
    `finding_id`) into the long tail and the held consequential set.

    An application is held whole if any of its figures is consequential:
    the rubric asks "is this figure THIS development's", which needs the
    application's other figures beside it, so splitting one application
    across two adjudicators would remove exactly that context.
    """
    tail, held = [], []
    for app in apps:
        if any(f["finding_id"] in consequential for f in app["figures"]):
            held.append(app)
        else:
            tail.append(app)
    return tail, held
