"""Per-case dossier for the non-pre-2018 Barbour gap classes.

Reads ONLY cached PlanIt responses (source_snapshots) — no API calls. For
every unmatched Barbour project that isn't a plain pre-2018 window artefact,
prints: the Barbour view (title/stage/value/authority/link), the PlanIt view
(ref, dates, state, full description), and a family analysis — whether the
application's parents/siblings are already in our universe, via PlanIt's
associated_id, refs mined from the description, and same-council base-number
stems.

Usage: .venv/bin/python scripts/barbour_gap_dossier.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402
from dcp.sources.planit import APPS_SELECT, _extract_candidate_refs  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "pm", Path(__file__).parent / "barbour_gap_postmortem.py")
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)


def cached_lookup(conn, planit_source_id: int, ref: str) -> list[dict]:
    """Replay the id_match page(s) for a bare ref from source_snapshots."""
    params = {"pg_sz": 20, "page": 1, "sort": "-start_date",
              "select": APPS_SELECT, "id_match": ref}
    url = f"https://www.planit.org.uk/api/applics/json?{urllib.parse.urlencode(params)}"
    with conn.cursor() as cur:
        cur.execute(
            """SELECT raw_bytes_inline FROM source_snapshots
               WHERE source_id = %s AND key = %s AND status_code = 200
               ORDER BY fetched_at DESC LIMIT 1""",
            (planit_source_id, url),
        )
        row = cur.fetchone()
    if not row:
        return []
    return json.loads(bytes(row[0])).get("records", [])


def family_in_db(conn, planit_rec: dict) -> dict:
    """What of this application's family do we already hold?

    Three probes:
    - associated_id refs (council-prefixed and bare) present in applications
    - refs mined from the description present in applications
    - same-council applications sharing a 'base stem' (the ref's leading
      number groups) — catches outline/RM/DRC families with suffix drift
    """
    council = (planit_rec.get("name") or "").split("/", 1)[0]
    out = {"assoc_hits": [], "descr_hits": [], "stem_hits": []}

    def db_lookup(bare: str) -> list[str]:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT application_ref FROM applications
                   WHERE upper(application_ref) LIKE upper(%s)""",
                (f"%/{bare}",),
            )
            return [r[0] for r in cur.fetchall()]

    for field, key in (("associated_id", "assoc_hits"), ("description", "descr_hits")):
        for cand in _extract_candidate_refs(planit_rec.get(field)):
            hits = db_lookup(cand)
            if hits:
                out[key].extend(hits)

    # Base-stem probe: for 'Cherwell/25/03310/REM' the stem is '25/03310';
    # find same-council rows whose ref contains it.
    name = planit_rec.get("name") or ""
    bare = name.split("/", 1)[1] if "/" in name else name
    m = re.match(r"([A-Z]*[/.]?\d{2,4}[/.]\d{3,6})", bare.upper())
    if m and council:
        stem = m.group(1)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT application_ref FROM applications
                   WHERE application_ref ILIKE %s AND application_ref != %s""",
                (f"{council}/%{stem}%", name),
            )
            out["stem_hits"] = [r[0] for r in cur.fetchall()]
    return out


def main() -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE name = 'planit'")
            planit_source_id = cur.fetchone()[0]
            cur.execute(
                """SELECT p.external_ref, p.planning_ref, p.title, p.stage_summary,
                          p.authority_name, p.planning_link, p.value_gbp, p.description
                   FROM projects p
                   WHERE p.planning_ref IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM project_applications pa
                                     WHERE pa.project_id = p.id)
                   ORDER BY p.external_ref""",
            )
            cols = [d[0] for d in cur.description]
            targets = [dict(zip(cols, row)) for row in cur.fetchall()]

        for t in targets:
            ref = t["planning_ref"]
            if ref.upper().startswith("FIND A TENDER"):
                verdict, rec = "procurement_notice", None
            else:
                records = cached_lookup(conn, planit_source_id, ref)
                verdict, rec = pm.classify(records, authority=t["authority_name"])
                if verdict == "ref_collision":
                    rec = records[0]
            if verdict == "pre_2018":
                continue  # window artefact; not in scope for the dossier

            print("=" * 78)
            print(f"[{verdict}] {ref}  —  {t['title']}")
            print(f"  Barbour: Ptno {t['external_ref']} | {t['stage_summary']} | "
                  f"value £{t['value_gbp']:,.0f}" if t["value_gbp"] else
                  f"  Barbour: Ptno {t['external_ref']} | {t['stage_summary']} | value n/a")
            print(f"  Authority: {t['authority_name'] or 'n/a'}")
            print(f"  Link: {t['planning_link'] or 'n/a'}")
            if t["description"]:
                print(f"  Barbour details: {t['description'][:250]}")
            if rec:
                print(f"  PlanIt: {rec.get('name')} | start {rec.get('start_date')} | "
                      f"decided {rec.get('decided_date')} | {rec.get('app_state')} | "
                      f"type {rec.get('app_type')}")
                if rec.get("associated_id"):
                    print(f"  associated_id: {rec['associated_id']}")
                desc = (rec.get("description") or "").strip().replace("\n", " ")
                print(f"  PlanIt description: {desc[:400]}")
                fam = family_in_db(conn, rec)
                for k, label in (("assoc_hits", "family via associated_id"),
                                 ("descr_hits", "family via description refs"),
                                 ("stem_hits", "family via base stem")):
                    if fam[k]:
                        print(f"  {label} ALREADY IN DB: {sorted(set(fam[k]))}")
                if not any(fam.values()):
                    print("  family: nothing related found in our universe")
            print()


if __name__ == "__main__":
    main()
