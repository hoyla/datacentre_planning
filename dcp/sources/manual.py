"""Manual-ingest "source" — storage shim for documents downloaded by hand.

There's no fetcher here (the operator does the downloading), only the
storage-layout helpers (`_app_dir`, `_bytes_path`, `_write_manifest`)
that the ingest script uses to write docs into the canonical
`data/raw/manual/<application_ref>/<sha[:16]>.<ext>` layout — the same
shape as the Idox and Ocella adapters, so downstream consumers
(extract.py, the export, findings.py) treat manual docs identically
to adapter-fetched ones.

`manual` is the right `source` value when an application's *entire*
document bundle had to be sourced by hand because no adapter exists
yet for its portal (currently: NorthLincs, plus any bespoke
council-built portals). For partial-manual additions to an
adapter-covered app — e.g. visual plans we missed because the Idox
adapter skips `docKey=` links — keep the bytes under the original
adapter's subtree (`data/raw/idox/<ref>/Manual/...`) and ingest with
`--source idox`. That preserves the editorial provenance of "adapter
got these N, operator got these M extras for the same app".
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path


SOURCE_NAME = "manual"
MANIFEST_FILENAME = "_manifest.json"
MANIFEST_VERSION = 1

_SAFE_REF_RE = re.compile(r"[^A-Za-z0-9._/-]+")


def _sanitised_ref(application_ref: str) -> str:
    return _SAFE_REF_RE.sub("_", application_ref)


def _app_dir(data_dir: Path, application_ref: str) -> Path:
    """`<DATA_DIR>/raw/manual/<safe_ref>/`."""
    return data_dir / "raw" / "manual" / _sanitised_ref(application_ref)


def _bytes_path(data_dir: Path, application_ref: str, content_sha256: str, ext: str) -> Path:
    return _app_dir(data_dir, application_ref) / f"{content_sha256[:16]}.{ext}"


def _write_manifest(
    conn,
    *,
    application_id: int,
    application_ref: str,
    app_dir: Path,
    summary: dict,
) -> None:
    """Manifest in the same shape as Idox / Ocella — same keys, same
    completion-signal semantic, with `manual` as the fetcher name."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT url, kind, content_sha256, bytes_path, fetched_at
            FROM documents WHERE application_id = %s
            ORDER BY fetched_at, id
            """,
            (application_id,),
        )
        rows = cur.fetchall()
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "application_ref": application_ref,
        "fetcher": f"dcp.sources.manual v{MANIFEST_VERSION}",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "links_found": summary.get("links_found", 0),
        "downloaded": summary.get("downloaded", 0),
        "skipped_existing": summary.get("skipped_existing", 0),
        "errors": summary.get("errors", 0),
        "complete": summary.get("errors", 0) == 0,
        "documents": [
            {
                "kind": kind,
                "content_sha256": sha,
                "bytes_path": bytes_path,
                "source_url": url,
                "fetched_at": fetched_at.isoformat(timespec="seconds")
                              if fetched_at else None,
            }
            for url, kind, sha, bytes_path, fetched_at in rows
        ],
    }
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / MANIFEST_FILENAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
