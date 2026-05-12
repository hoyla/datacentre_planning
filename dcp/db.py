"""Postgres connection helpers. Raw psycopg2, no ORM."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extensions import cursor as PgCursor
from psycopg2.extras import RealDictCursor


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set (cp .env.example .env and edit)")
    return url


@contextmanager
def connect() -> Iterator[PgConnection]:
    conn = psycopg2.connect(database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def cursor(dict_rows: bool = True) -> Iterator[PgCursor]:
    with connect() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor if dict_rows else None)
        try:
            yield cur
        finally:
            cur.close()
