"""Aggregate corpus-level statistics — universe, triage, filters, signals,
documents, findings.

Public collection helpers are used in two places:

  - `scripts/corpus_stats.py` renders the full standalone methodology block
    (long form: every discovery-path tag, every exclude reason).
  - `dcp.export` embeds a shorter "At a glance" form in the worklist header
    so the universe-and-triage framing travels with the document.

No editorial overlay — every number is a direct DB aggregate.
"""

from __future__ import annotations

from dcp import worklist


def _scalar(cur, sql: str, params: dict | tuple | None = None) -> int:
    cur.execute(sql, params or {})
    row = cur.fetchone()
    return row[0] if row else 0


def universe(conn) -> dict:
    with conn.cursor() as cur:
        total = _scalar(cur, "SELECT count(*) FROM applications")
        date_min, date_max = None, None
        cur.execute(
            "SELECT min(date_received), max(date_received) FROM applications "
            "WHERE date_received IS NOT NULL"
        )
        row = cur.fetchone()
        if row:
            date_min, date_max = row
        cur.execute(
            "SELECT s.name, count(*) FROM applications a "
            "JOIN sources s ON s.id = a.source_id GROUP BY s.name ORDER BY count(*) DESC"
        )
        by_source = list(cur.fetchall())
        cur.execute(
            """
            SELECT tag, count(*) AS n FROM (
                SELECT unnest(discovered_via) AS tag FROM applications
            ) t
            GROUP BY tag
            HAVING count(*) >= 5
            ORDER BY n DESC
            """
        )
        discovery_tags = list(cur.fetchall())
    return {
        "total": total,
        "date_min": date_min,
        "date_max": date_max,
        "by_source": by_source,
        "discovery_tags": discovery_tags,
    }


def verdicts(conn, *, model: str) -> dict:
    sql = """
    WITH latest_triage AS (
      SELECT DISTINCT ON (application_id) *
      FROM triage WHERE model = %(model)s
      ORDER BY application_id, inserted_at DESC
    )
    SELECT
      count(*) AS triaged,
      count(*) FILTER (WHERE t.verdict = 'DC') AS dc,
      count(*) FILTER (WHERE t.verdict = 'adjacent') AS adjacent,
      count(*) FILTER (WHERE t.verdict = 'unrelated') AS unrelated,
      count(*) FILTER (WHERE t.verdict = 'unknown') AS unknown,
      count(*) FILTER (
        WHERE t.verdict IN ('DC','adjacent') AND t.worth_deep_read = 'yes'
      ) AS deep_read_yes,
      count(*) FILTER (
        WHERE t.verdict IN ('DC','adjacent') AND t.worth_deep_read = 'maybe'
      ) AS deep_read_maybe,
      count(*) FILTER (
        WHERE t.verdict IN ('DC','adjacent') AND t.worth_deep_read = 'no'
      ) AS deep_read_no
    FROM applications a JOIN latest_triage t ON t.application_id = a.id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"model": model})
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))


def editorial_filters(conn) -> dict:
    """`exclude:*` and `duplicate_of:*` tag counts. These sit alongside
    the verdict — never replace it — so the audit trail survives.
    """
    with conn.cursor() as cur:
        excluded = _scalar(
            cur,
            "SELECT count(*) FROM applications "
            "WHERE EXISTS (SELECT 1 FROM unnest(discovered_via) AS tag WHERE tag LIKE 'exclude:%%')",
        )
        duplicates = _scalar(
            cur,
            "SELECT count(*) FROM applications "
            "WHERE EXISTS (SELECT 1 FROM unnest(discovered_via) AS tag WHERE tag LIKE 'duplicate_of:%%')",
        )
        cur.execute(
            """
            SELECT split_part(tag, ':', 1) || ':' || split_part(tag, ':', 2) AS reason,
                   count(*) AS n
            FROM (SELECT unnest(discovered_via) AS tag FROM applications) t
            WHERE tag LIKE 'exclude:%%'
            GROUP BY reason ORDER BY n DESC
            """
        )
        exclude_reasons = list(cur.fetchall())
    return {
        "excluded": excluded,
        "duplicates": duplicates,
        "exclude_reasons": exclude_reasons,
    }


def signals_in_worklist(conn, *, model: str) -> dict:
    """For the editorial worklist (verdict ∈ {DC, adjacent} + deep-read
    ∈ {yes, maybe}, after exclude/duplicate filtering), classify by which
    rubric tiers their triage `signals` array hit. Mutually exclusive in
    display order: tier1 > storage > backup-only > none.
    """
    sql = """
    WITH latest_triage AS (
      SELECT DISTINCT ON (application_id) *
      FROM triage WHERE model = %(model)s
      ORDER BY application_id, inserted_at DESC
    ),
    worklist AS (
      SELECT a.id, t.signals
      FROM applications a JOIN latest_triage t ON t.application_id = a.id
      WHERE
        (
          (t.verdict IN ('DC','adjacent') AND t.worth_deep_read IN ('yes','maybe'))
          OR 'foxglove_top10' = ANY(a.discovered_via)
        )
        AND NOT EXISTS (
          SELECT 1 FROM unnest(a.discovered_via) AS tag
          WHERE tag LIKE 'exclude:%%' OR tag LIKE 'duplicate_of:%%'
        )
    ),
    hits AS (
      SELECT
        id,
        (SELECT count(*) FROM unnest(signals) s WHERE lower(s) ~ %(tier1)s)   AS tier1,
        (SELECT count(*) FROM unnest(signals) s WHERE lower(s) ~ %(storage)s) AS storage,
        (SELECT count(*) FROM unnest(signals) s WHERE lower(s) ~ %(backup)s)  AS backup
      FROM worklist
    )
    SELECT
      count(*) AS total,
      count(*) FILTER (WHERE tier1 > 0) AS tier1_any,
      count(*) FILTER (WHERE tier1 = 0 AND storage > 0) AS storage_only,
      count(*) FILTER (WHERE tier1 = 0 AND storage = 0 AND backup > 0) AS backup_only,
      count(*) FILTER (WHERE tier1 = 0 AND storage = 0 AND backup = 0) AS no_power_signal
    FROM hits
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "model": model,
                "tier1": worklist.TIER1_REGEX,
                "storage": worklist.TIER_STORAGE_REGEX,
                "backup": worklist.TIER_BACKUP_REGEX,
            },
        )
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))


def documents(conn) -> dict:
    with conn.cursor() as cur:
        docs_total = _scalar(cur, "SELECT count(*) FROM documents")
        apps_with_docs = _scalar(
            cur,
            "SELECT count(DISTINCT application_id) FROM documents",
        )
    return {"docs_total": docs_total, "apps_with_docs": apps_with_docs}


def findings(conn) -> dict:
    """Phase-4 findings aggregates. Categories (NEW / REFINEMENT /
    CONFIRMATION) are derived at render time in `dcp.findings.classify`,
    not stored on the row — so counts here are by raw `signal_type`."""
    with conn.cursor() as cur:
        total = _scalar(cur, "SELECT count(*) FROM findings")
        apps = _scalar(cur, "SELECT count(DISTINCT application_id) FROM findings")
        docs = _scalar(
            cur,
            "SELECT count(DISTINCT document_id) FROM findings WHERE document_id IS NOT NULL",
        )
        cur.execute(
            "SELECT signal_type, count(*) AS n FROM findings "
            "GROUP BY signal_type ORDER BY n DESC"
        )
        by_signal = list(cur.fetchall())
    return {
        "findings_total": total,
        "apps_with_findings": apps,
        "documents_with_findings": docs,
        "by_signal": by_signal,
    }


def collect(conn, *, model: str) -> dict:
    """One-shot bundle of all corpus statistics. Used by both the standalone
    script and the export header so the numbers stay consistent.
    """
    return {
        "universe": universe(conn),
        "verdicts": verdicts(conn, model=model),
        "filters": editorial_filters(conn),
        "signals": signals_in_worklist(conn, model=model),
        "documents": documents(conn),
        "findings": findings(conn),
    }
