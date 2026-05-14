"""Idempotent upserts for sources, councils, applications, and source_snapshots.

All operations are append-only or upsert-friendly. Reruns of the same fetch are no-ops
when content hasn't changed (source_snapshots) or refresh metadata (applications).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import Json


def ensure_source(conn: PgConnection, *, name: str, kind: str, base_url: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (name, kind, base_url) VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url
            RETURNING id
            """,
            (name, kind, base_url),
        )
        return cur.fetchone()[0]


def record_snapshot(
    conn: PgConnection,
    *,
    source_id: int,
    key: str,
    raw_bytes: bytes,
    status_code: int | None = 200,
) -> bool:
    """Insert a raw-response snapshot. Returns True if a new row was inserted, False if duplicate."""
    sha = hashlib.sha256(raw_bytes).hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_snapshots (source_id, key, content_sha256, raw_bytes_inline, status_code)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_id, key, content_sha256) DO NOTHING
            RETURNING id
            """,
            (source_id, key, sha, raw_bytes, status_code),
        )
        return cur.fetchone() is not None


def find_cached_response(
    conn: PgConnection, *, source_id: int, key: str
) -> bytes | None:
    """Return the most recent successful (200) snapshot body for (source_id, key), or None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT raw_bytes_inline FROM source_snapshots
            WHERE source_id = %s AND key = %s AND status_code = 200
              AND raw_bytes_inline IS NOT NULL
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (source_id, key),
        )
        row = cur.fetchone()
        return bytes(row[0]) if row else None


def upsert_council(conn: PgConnection, area: dict[str, Any]) -> str | None:
    """Upsert a council row from a PlanIt area record. Returns gss_code or None if skipped."""
    gss = area.get("gss_code")
    if not gss or not area.get("is_planning"):
        return None
    notes = {
        "long_name": area.get("long_name"),
        "area_name": area.get("area_name"),
        "parent_name": area.get("parent_name"),
        "in_region": area.get("in_region"),
        "min_date": area.get("min_date"),
        "max_date": area.get("max_date"),
        "total_applications": area.get("total"),
        "scraper_name": area.get("scraper_name"),
    }
    portal_kind = (area.get("scraper_type") or "").strip().lower() or None
    name = area.get("long_name") or area.get("area_name") or gss
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO councils (gss_code, name, portal_kind, base_url, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (gss_code) DO UPDATE SET
                name = EXCLUDED.name,
                portal_kind = EXCLUDED.portal_kind,
                base_url = EXCLUDED.base_url,
                notes = EXCLUDED.notes
            """,
            (gss, name, portal_kind, area.get("planning_url"), Json(notes)),
        )
    return gss


def upsert_application(
    conn: PgConnection,
    *,
    source_id: int,
    app: dict[str, Any],
    council_gss: str | None = None,
    discovered_via: list[str] | None = None,
) -> int:
    """Upsert an application row from a PlanIt record. Returns the row id.

    `discovered_via` records the discovery path(s) — e.g. ['dc_keyword'],
    ['operator:Greystoke'], ['spatial:Northumberland/24/04112/OUTES']. On
    conflict, paths are appended to the existing array (deduped) rather
    than overwritten — same application found via two paths keeps both.
    """
    raw_meta = {
        "app_type": app.get("app_type"),
        "app_size": app.get("app_size"),
        "associated_id": app.get("associated_id"),
        "area_name": app.get("area_name"),
        "area_id": app.get("area_id"),
        "scraper_name": app.get("scraper_name"),
        "other_fields": app.get("other_fields"),
        "last_changed": app.get("last_changed"),
        "last_scraped": app.get("last_scraped"),
        "planit_link": app.get("link"),
        "uid": app.get("uid"),
        "altid": app.get("altid"),
        "consulted_date": app.get("consulted_date"),
        "location_x": app.get("location_x"),
        "location_y": app.get("location_y"),
    }
    via = list(discovered_via) if discovered_via else []
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO applications (
                source_id, application_ref, council_gss, description, address, postcode,
                date_received, date_decided, status, url, raw_metadata, discovered_via
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, application_ref) DO UPDATE SET
                description = EXCLUDED.description,
                address = EXCLUDED.address,
                postcode = EXCLUDED.postcode,
                date_received = EXCLUDED.date_received,
                date_decided = EXCLUDED.date_decided,
                status = EXCLUDED.status,
                url = EXCLUDED.url,
                council_gss = COALESCE(EXCLUDED.council_gss, applications.council_gss),
                raw_metadata = EXCLUDED.raw_metadata,
                discovered_via = ARRAY(
                    SELECT DISTINCT unnest(applications.discovered_via || EXCLUDED.discovered_via)
                ),
                last_seen_at = now()
            RETURNING id
            """,
            (
                source_id,
                app["name"],
                council_gss,
                app.get("description"),
                app.get("address"),
                app.get("postcode"),
                app.get("start_date"),
                app.get("decided_date"),
                app.get("app_state"),
                app.get("url"),
                Json(raw_meta),
                via,
            ),
        )
        return cur.fetchone()[0]


def backfill_council_gss(conn: PgConnection) -> dict[str, int]:
    """Fill in NULL `applications.council_gss` from the `area_name` carried in
    `raw_metadata`. Two passes:

    1. Direct match: `raw_metadata->area_name` equals a `councils.notes->area_name`.
    2. Alias match: `raw_metadata->area_name` equals a `council_aliases.alias_name`.

    Per principle 3 (never mutate originals), `raw_metadata.area_name` is left
    untouched — `council_gss` is the alongside-the-original derived column. Any
    application whose area_name doesn't match a council or an alias stays NULL
    (e.g. Mayoral Development Corporations like OPDC/LLDC, intentionally
    unmapped). Returns counts for each pass plus the residual NULLs.
    """
    out = {"matched_council": 0, "matched_alias": 0, "remaining_null": 0}
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE applications a
            SET council_gss = c.gss_code
            FROM councils c
            WHERE a.council_gss IS NULL
              AND c.notes->>'area_name' = a.raw_metadata->>'area_name'
            """,
        )
        out["matched_council"] = cur.rowcount
        cur.execute(
            """
            UPDATE applications a
            SET council_gss = al.gss_code
            FROM council_aliases al
            WHERE a.council_gss IS NULL
              AND al.alias_name = a.raw_metadata->>'area_name'
            """,
        )
        out["matched_alias"] = cur.rowcount
        cur.execute("SELECT count(*) FROM applications WHERE council_gss IS NULL")
        out["remaining_null"] = cur.fetchone()[0]
    return out


def append_discovered_via(
    conn: PgConnection, *, application_refs: list[str], tag: str,
) -> int:
    """Append `tag` to the `discovered_via` array of every application whose
    `application_ref` is in `application_refs`. Idempotent — duplicates are
    deduped via the same ARRAY-distinct pattern used by `upsert_application`.
    Returns the number of rows touched (matches the number of refs that exist
    in `applications`; missing refs are silently no-ops).

    Used by the priors-tagging pass (see scripts/tag_priors.py): operator and
    research priors (e.g. Foxglove top-10) get a `discovered_via` flag so the
    export filter surfaces them even when triage classifies a procedural
    follow-on as 'unrelated'."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE applications
            SET discovered_via = ARRAY(
                SELECT DISTINCT unnest(discovered_via || ARRAY[%s])
            )
            WHERE application_ref = ANY(%s)
            """,
            (tag, application_refs),
        )
        return cur.rowcount


def record_triage(
    conn: PgConnection,
    *,
    application_id: int,
    model: str,
    verdict: str,
    worth_deep_read: str | None,
    signals: list[str],
    why: str | None,
    confidence: str | None,
    raw_response: dict | str | None = None,
) -> int:
    """Append a triage verdict for an application. Versioned — latest by
    inserted_at is current; prior verdicts are retained so prompt revisions
    can be compared. Returns the row id."""
    raw = Json(raw_response) if raw_response is not None else None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO triage (
                application_id, model, verdict, worth_deep_read,
                signals, why, confidence, raw_response
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (application_id, model, verdict, worth_deep_read,
             signals, why, confidence, raw),
        )
        return cur.fetchone()[0]


def applications_pending_triage(
    conn: PgConnection, *, model: str, limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return applications that have no triage row for the given `model`.
    Selection order is deterministic (date_received DESC NULLS LAST, id) so
    a resumed sweep picks up where it left off without re-ordering."""
    sql = """
        SELECT a.id, a.application_ref, a.description, a.address,
               a.date_received, a.status, a.council_gss,
               a.raw_metadata->>'app_type' AS app_type,
               c.name AS council_name
        FROM applications a
        LEFT JOIN councils c ON c.gss_code = a.council_gss
        WHERE NOT EXISTS (
            SELECT 1 FROM triage t
            WHERE t.application_id = a.id AND t.model = %s
        )
        ORDER BY a.date_received DESC NULLS LAST, a.id
    """
    params: tuple[Any, ...] = (model,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (model, limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def upsert_colocated_candidate(
    conn: PgConnection,
    *,
    anchor_app_id: int,
    candidate_app_id: int,
    distance_m: float | None,
    radius_used_km: float,
    keyword_hits: list[str],
) -> None:
    """Record a spatial-proximity link from an anchor DC application to a candidate
    application within radius_used_km. ON CONFLICT updates distance and keyword_hits
    in case the lexicon evolved between runs."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO colocated_candidates
                (anchor_app_id, candidate_app_id, distance_m, radius_used_km, keyword_hits)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (anchor_app_id, candidate_app_id, radius_used_km) DO UPDATE SET
                distance_m = EXCLUDED.distance_m,
                keyword_hits = EXCLUDED.keyword_hits
            """,
            (anchor_app_id, candidate_app_id, distance_m, radius_used_km, keyword_hits),
        )
