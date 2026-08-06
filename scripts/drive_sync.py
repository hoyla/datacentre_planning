"""Sync the Drive staging tree to the Guardian Google Drive.

Credentials: the OAuth client secret lives at
`~/.config/datacentre_planning/client_secret.json` (operator-supplied);
the granted token is cached alongside as `drive_token.json`. The first
run opens a browser for the operator to authorise — the operator clicks
consent, never this tool — and subsequent runs refresh silently. Neither
file's contents are read by anything except Google's own libraries.

Scope is deliberately **drive.file**: this tool can create and manage
only the files and folders it itself uploads. It cannot see, list, or
touch anything else in the Drive.

Sync semantics: mirrors a local tree into a named top-level folder,
skipping files already uploaded with matching md5 (Drive computes
md5Checksum server-side, so re-runs are cheap and interrupted runs
resume). Local state is also cached to avoid re-querying unchanged
paths; the cache is advisory and safe to delete.

Usage:
    .venv/bin/python scripts/drive_sync.py --auth          # first-time consent
    .venv/bin/python -u scripts/drive_sync.py --sync data/exports/drive_staging \
        --dest "DC Planning Dataset"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "datacentre_planning"
CLIENT_SECRET = CONFIG_DIR / "client_secret.json"
TOKEN_PATH = CONFIG_DIR / "drive_token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
STATE_PATH = Path("data/exports/.drive_sync_state.json")


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES)
            print("Opening a browser for you to authorise — the grant is "
                  "drive.file (only files this tool creates).")
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
        TOKEN_PATH.chmod(0o600)
    return build("drive", "v3", credentials=creds)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Sync:
    def __init__(self, service):
        self.svc = service
        self.state: dict = (json.loads(STATE_PATH.read_text())
                            if STATE_PATH.exists() else {"folders": {}, "files": {}})
        self._dirty = 0

    def save(self, force: bool = False) -> None:
        self._dirty += 1
        if force or self._dirty >= 50:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(self.state))
            self._dirty = 0

    def _retry(self, fn, tries: int = 5):
        for attempt in range(tries):
            try:
                return fn()
            except Exception as exc:
                transient = any(t in str(exc) for t in
                                ("429", "500", "502", "503", "rateLimit",
                                 "userRateLimit", "timed out", "Broken pipe"))
                if attempt == tries - 1 or not transient:
                    raise
                time.sleep(min(2 ** attempt * 5, 120))

    def folder(self, name: str, parent: str | None) -> str:
        key = f"{parent or 'root'}/{name}"
        if key in self.state["folders"]:
            return self.state["folders"][key]
        q = (f"name = '{name.replace(chr(39), chr(92)+chr(39))}' and "
             f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
             + (f" and '{parent}' in parents" if parent else ""))
        res = self._retry(lambda: self.svc.files().list(
            q=q, fields="files(id)", pageSize=1).execute())
        if res.get("files"):
            fid = res["files"][0]["id"]
        else:
            body = {"name": name,
                    "mimeType": "application/vnd.google-apps.folder"}
            if parent:
                body["parents"] = [parent]
            fid = self._retry(lambda: self.svc.files().create(
                body=body, fields="id").execute())["id"]
        self.state["folders"][key] = fid
        self.save()
        return fid

    def upload(self, local: Path, parent: str) -> str:
        from googleapiclient.http import MediaFileUpload

        rel = str(local)
        local_md5 = md5_of(local)
        cached = self.state["files"].get(rel)
        if cached and cached.get("md5") == local_md5:
            return "cached"
        name = local.name
        q = (f"name = '{name.replace(chr(39), chr(92)+chr(39))}' and "
             f"'{parent}' in parents and trashed = false")
        res = self._retry(lambda: self.svc.files().list(
            q=q, fields="files(id, md5Checksum)", pageSize=1).execute())
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        media = MediaFileUpload(str(local), mimetype=mime,
                                resumable=local.stat().st_size > 5_000_000)
        if res.get("files"):
            remote = res["files"][0]
            if remote.get("md5Checksum") == local_md5:
                self.state["files"][rel] = {"md5": local_md5, "id": remote["id"]}
                self.save()
                return "skipped"
            fid = self._retry(lambda: self.svc.files().update(
                fileId=remote["id"], media_body=media, fields="id").execute())["id"]
            outcome = "updated"
        else:
            fid = self._retry(lambda: self.svc.files().create(
                body={"name": name, "parents": [parent]},
                media_body=media, fields="id").execute())["id"]
            outcome = "uploaded"
        self.state["files"][rel] = {"md5": local_md5, "id": fid}
        self.save()
        return outcome


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", action="store_true",
                    help="Run the consent flow and exit.")
    ap.add_argument("--sync", type=Path)
    ap.add_argument("--dest", default="DC Planning Dataset",
                    help="Top-level folder name to create/reuse.")
    ap.add_argument("--dest-id",
                    help="Existing Drive folder ID to sync into (from the "
                         "folder's URL). Takes precedence over --dest. Note "
                         "the drive.file scope can create files inside a "
                         "folder it did not create, but cannot list that "
                         "folder's other contents — so pre-existing files "
                         "are invisible to this tool by design.")
    ap.add_argument("--probe-id",
                    help="Write a single tiny file into this folder ID to "
                         "verify access, then report and stop.")
    args = ap.parse_args()

    svc = get_service()
    if args.auth:
        about = svc.about().get(fields="user(emailAddress)").execute()
        print(f"authorised as: {about['user']['emailAddress']}")
        return
    if args.probe_id:
        import tempfile
        from googleapiclient.http import MediaFileUpload
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("drive_sync access probe — safe to delete.\n")
            probe = fh.name
        created = svc.files().create(
            body={"name": "_drive_sync_probe.txt", "parents": [args.probe_id]},
            media_body=MediaFileUpload(probe, mimetype="text/plain"),
            fields="id, name, parents, webViewLink").execute()
        print(f"wrote {created['name']} -> {created.get('webViewLink')}")
        print(f"  file id: {created['id']}  parents: {created.get('parents')}")
        svc.files().delete(fileId=created["id"]).execute()
        print("  probe file deleted; write access to that folder confirmed")
        return

    if not args.sync:
        print("nothing to do — pass --sync DIR")
        return

    sync = Sync(svc)
    root = args.dest_id or sync.folder(args.dest, None)
    counts = {"uploaded": 0, "updated": 0, "skipped": 0, "cached": 0, "failed": 0}
    t0 = time.time()
    files = sorted(p for p in args.sync.rglob("*")
                   if p.is_file() and not p.name.startswith("."))
    print(f"{len(files)} files to consider -> Drive folder {args.dest!r}")
    folder_ids: dict[Path, str] = {args.sync: root}
    for i, f in enumerate(files, 1):
        parent_path = f.parent
        if parent_path not in folder_ids:
            fid = root
            for part in parent_path.relative_to(args.sync).parts:
                sub = Path(fid) / part  # key only
                fid = sync.folder(part, fid)
            folder_ids[parent_path] = fid
        try:
            outcome = sync.upload(f, folder_ids[parent_path])
            counts[outcome] += 1
        except Exception as exc:
            counts["failed"] += 1
            print(f"  FAILED {f}: {str(exc)[:140]}")
        if i % 200 == 0:
            rate = i / (time.time() - t0)
            eta = (len(files) - i) / rate / 3600
            print(f"  {i}/{len(files)}  {counts}  eta {eta:.1f}h")
    sync.save(force=True)
    print(f"done: {counts}")


if __name__ == "__main__":
    main()
