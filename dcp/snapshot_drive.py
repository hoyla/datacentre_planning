"""Where each operator snapshot's copy lives on Drive, by file id.

The claims channel rests on committed snapshots — an operator's page as
it read on the day a figure was taken from it — and a reporter checking
a claim should reach that copy the same way they reach a planning
document: a Drive link beside the source URL, not an instruction to
clone a repository. This module answers "which Drive file is this
snapshot", and nothing else.

**By id, never by derivation.** The same rule as
`document_drive_files`, and for the same reason: a derived location
either finds nothing, silently dropping a link, or finds the
neighbouring file — a working link to the wrong evidence under a
citation naming different evidence. A Drive file id survives the file
being moved or renamed; a derived path survives nothing being renamed.

**Keyed on the snapshot's own filename**, `<slug>.<date>.txt`, because
that is the unit a claim's evidence actually is. A slug is not enough:
the store is append-only, so one slug has many readings, and a claim
read on 2026-08-20 is evidenced by the file that existed then rather
than by today's.

**The ledger is committed, not a database table.** `document_drive_files`
is a table because a document is a database row and its id is the key.
A snapshot is not: it is a file in this repository, cited by name from
committed YAML — `operator-claims.yaml`, `operator-green-claims.yaml`,
`site_facilities.yaml`. Its Drive id is a fact about a committed
artefact, so it travels with it in git, survives a database rebuilt from
migrations, and is reviewable as a diff of 81 lines rather than as an
invisible insert.
"""

from __future__ import annotations

from pathlib import Path

from dcp import drive

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "data" / "external_sources" / "operator_snapshots_drive.yaml"


class SnapshotDriveError(ValueError):
    """The ledger cannot be trusted, so nothing reads from it."""


def load_ledger(path: Path = LEDGER_PATH) -> dict[str, dict]:
    """filename -> {"file_id", "md5", "uploaded"}; empty if not yet synced.

    Raises rather than degrading if the ledger names a different Drive
    folder from the one `dcp.drive` addresses. That mismatch means the
    ids in it were recorded against a folder this repository no longer
    points at — every link would resolve somewhere nobody is looking,
    which is the duplicate-archive failure wearing a link's clothes.
    """
    import yaml

    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    folder = str(payload.get("folder_id") or "")
    if folder and drive.SNAPSHOTS_FOLDER_ID and folder != drive.SNAPSHOTS_FOLDER_ID:
        raise SnapshotDriveError(
            f"{path.name} records folder {folder} but dcp/drive.py addresses "
            f"{drive.SNAPSHOTS_FOLDER_ID} — one of the two is stale, and every "
            f"link built from this ledger would point into the wrong folder")
    out: dict[str, dict] = {}
    for name, meta in (payload.get("files") or {}).items():
        if not str((meta or {}).get("file_id", "")).strip():
            raise SnapshotDriveError(f"{path.name}: {name} has no file_id")
        out[str(name)] = dict(meta)
    return out


def url_for(filename: str, ledger: dict[str, dict] | None = None) -> str:
    """The Drive viewer URL for a snapshot file, or "" if none is held.

    An empty string rather than a raise: a snapshot fetched since the
    last sync has no copy on Drive yet, and the honest rendering is the
    source URL alone. What must never happen is a link that resolves to
    a different file, which is why nothing here falls back to a guess.
    """
    ledger = load_ledger() if ledger is None else ledger
    meta = ledger.get(filename)
    return drive.file_url(meta["file_id"]) if meta else ""


def unsynced(snapshot_dir: Path, ledger: dict[str, dict] | None = None) -> list[Path]:
    """Held snapshots with no Drive id recorded, in name order."""
    ledger = load_ledger() if ledger is None else ledger
    return sorted(p for p in snapshot_dir.glob("*.txt") if p.name not in ledger)
