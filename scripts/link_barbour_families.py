"""Family-aware linking of Barbour projects to applications.

Three passes, all idempotent:

1. **barbour_tag** — any application whose `discovered_via` carries a
   `barbour:<Ptno>` tag links to that project. Catches the family-pointer
   cases where PlanIt's id_match surfaced a relative with a different suffix
   (e.g. Barbour ref `13/00531/MAJOR` → PlanIt `Hart/13/00531/DCON6`), which
   the adapter's suffix matcher correctly declines to link on its own.

2. **manual** — curated links where Barbour's own metadata is wrong but the
   right application is identifiable. Currently: Feltham (Barbour's
   planning_ref field holds a legacy number, but their portal link's URL
   names the real ref `P/2023/0642`, which we hold).

3. **family_ref** — one hop up the family tree: for every linked
   application, refs mined from its `associated_id` that resolve to a
   same-council application in our universe get linked too. This is what
   makes project-level coverage read correctly when Barbour cites a
   procedural child of a campus whose outline we already hold (Google
   Waltham Cross → Broxbourne/07/18/1181/O).

Usage: .venv/bin/python scripts/link_barbour_families.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources.planit import _extract_candidate_refs  # noqa: E402

# Barbour Ptno → our application_ref, with the reason the adapter can't
# derive it. Reviewed by hand; keep the reason with the entry.
MANUAL_LINKS = {
    # Barbour planning_ref '01492/I/P1' is a legacy/internal number; the
    # project's own planning_link URL carries applicationNumber=P/2023/0642
    # (Feltham DC, £570M). Verified 2026-08-02.
    "12697612": "Hounslow/P/2023/0642",
}


def main() -> None:
    counts = {"barbour_tag": 0, "manual": 0, "family_ref": 0}
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, external_ref FROM projects")
            ptno_to_project = {ext: pid for pid, ext in cur.fetchall()}

            # Pass 1: barbour:<Ptno> tags.
            cur.execute(
                """SELECT a.id, a.application_ref, tag
                   FROM applications a, unnest(a.discovered_via) AS tag
                   WHERE tag LIKE 'barbour:%'"""
            )
            for app_id, app_ref, tag in cur.fetchall():
                ptno = tag.split(":", 1)[1]
                project_id = ptno_to_project.get(ptno)
                if project_id and repo.link_project_application(
                    conn, project_id=project_id, application_id=app_id,
                    match_method="barbour_tag",
                ):
                    counts["barbour_tag"] += 1
                    print(f"  barbour_tag  {app_ref}  <- Ptno {ptno}")

            # Pass 2: manual curation.
            for ptno, app_ref in MANUAL_LINKS.items():
                project_id = ptno_to_project.get(ptno)
                if not project_id:
                    continue
                cur.execute("SELECT id FROM applications WHERE application_ref = %s",
                            (app_ref,))
                row = cur.fetchone()
                if row and repo.link_project_application(
                    conn, project_id=project_id, application_id=row[0],
                    match_method="manual",
                ):
                    counts["manual"] += 1
                    print(f"  manual       {app_ref}  <- Ptno {ptno}")

            # Pass 3: one hop up via associated_id of every linked application.
            cur.execute(
                """SELECT pa.project_id, a.id, a.application_ref,
                          a.raw_metadata->>'associated_id'
                   FROM project_applications pa
                   JOIN applications a ON a.id = pa.application_id"""
            )
            linked = cur.fetchall()
            for project_id, app_id, app_ref, assoc in linked:
                if not assoc:
                    continue
                council = app_ref.split("/", 1)[0]
                for cand in _extract_candidate_refs(assoc):
                    cur.execute(
                        """SELECT id, application_ref FROM applications
                           WHERE application_ref = %s OR application_ref = %s""",
                        (f"{council}/{cand}", cand),
                    )
                    for rel_id, rel_ref in cur.fetchall():
                        if rel_id == app_id:
                            continue
                        if repo.link_project_application(
                            conn, project_id=project_id, application_id=rel_id,
                            match_method="family_ref",
                        ):
                            counts["family_ref"] += 1
                            print(f"  family_ref   {rel_ref}  <- via {app_ref}")
        conn.commit()

    print(f"\nSummary: {counts}")
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT count(DISTINCT project_id), count(*)
               FROM project_applications"""
        )
        projects_linked, total_links = cur.fetchone()
        print(f"Projects with >=1 link: {projects_linked}/253; total links: {total_links}")


if __name__ == "__main__":
    main()
