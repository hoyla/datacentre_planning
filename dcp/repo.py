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
) -> None:
    """Upsert an application row from a PlanIt record."""
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
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO applications (
                source_id, application_ref, council_gss, description, address, postcode,
                date_received, date_decided, status, url, raw_metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                last_seen_at = now()
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
            ),
        )
