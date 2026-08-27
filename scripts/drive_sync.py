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

The sync is additive by default: a file that disappears locally stays on
Drive. That is the right default for a document archive, and wrong after
anything that renames staged files, which leaves the old name sitting
beside the new one. `--prune` moves those orphans to the Drive bin,
working from the upload ledger — the only record of what this tool put
there, since `drive.file` cannot list the folder. Dry-run it first.

Usage:
    .venv/bin/python scripts/drive_sync.py --auth          # first-time consent
    .venv/bin/python -u scripts/drive_sync.py --sync data/exports/drive_staging \
        --prune --dry-run                                  # what would be binned
    .venv/bin/python -u scripts/drive_sync.py --sync data/exports/drive_staging \
        --prune
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import threading
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "datacentre_planning"
CLIENT_SECRET = CONFIG_DIR / "client_secret.json"
TOKEN_PATH = CONFIG_DIR / "drive_token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
STATE_PATH = Path("data/exports/.drive_sync_state.json")

# The one destination. Operator-supplied, and the same ID the workbook and
# the reader link to, so there is a single place to change it and no way
# for the three to disagree about where the archive lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dcp.drive import FOLDER_ID as HANDOVER_FOLDER_ID  # noqa: E402


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

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
    return creds


def get_service(creds=None):
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds or get_credentials())


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Sync:
    def __init__(self, service, credentials=None):
        # googleapiclient service objects are NOT thread-safe (their
        # httplib2 transport keeps per-connection state), so each worker
        # thread builds its own from the shared credentials, which are.
        # Tests inject a fake by assigning `sync.svc = ...`; the setter
        # clears the credentials so a fake is never bypassed by a
        # thread-local real service.
        self._default_svc = service
        self._creds = credentials
        self._tls = threading.local()
        # One lock over the ledger. The state dict is mutated per file
        # and dumped by save(); either racing a worker corrupts the one
        # record that makes syncs resumable and moves recognisable. API
        # calls happen OUTSIDE the lock — it guards memory, not network.
        self._lock = threading.RLock()
        self.state: dict = (json.loads(STATE_PATH.read_text())
                            if STATE_PATH.exists() else {"folders": {}, "files": {}})
        self._dirty = 0

    @property
    def svc(self):
        tls = getattr(self._tls, "svc", None)
        if tls is not None:
            return tls
        if self._creds is None or threading.current_thread() is threading.main_thread():
            return self._default_svc
        from googleapiclient.discovery import build
        self._tls.svc = build("drive", "v3", credentials=self._creds)
        return self._tls.svc

    @svc.setter
    def svc(self, service):
        self._default_svc = service
        self._creds = None

    def save(self, force: bool = False) -> None:
        with self._lock:
            self._dirty += 1
            if force or self._dirty >= 50:
                payload = json.dumps(self.state)
                self._dirty = 0
            else:
                return
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(payload)

    # Server-side pushback: the API is reachable and saying "not now".
    _API_TRANSIENT = ("429", "500", "502", "503", "rateLimit",
                      "userRateLimit", "timed out", "Broken pipe")

    # The network went away underneath us — DNS failure, dropped route, a
    # laptop that slept. Worth separating from the above because the
    # right patience is different: an outage lasts minutes, not seconds,
    # and treating it as fatal is what ended the 2026-08-25 overnight run
    # after 2,800 of 54,293 files. httplib2 raises ServerNotFoundError,
    # whose text matched none of the API signatures, so every file failed
    # instantly and the first folder creation to hit it killed the run —
    # folder creation being the one call not inside the loop's own
    # try/except.
    _NET_TRANSIENT = ("Unable to find the server", "ServerNotFoundError",
                      "nodename nor servname", "Name or service not known",
                      "Temporary failure in name resolution",
                      "Connection reset", "Connection aborted",
                      "Connection refused", "Network is unreachable",
                      "EOF occurred in violation of protocol")

    def _retry(self, fn, tries: int = 5, net_tries: int = 9):
        """Retry transient failures. Network outages get their own, more
        patient schedule — roughly 20 minutes of waiting rather than 75
        seconds — because the alternative is losing a whole overnight
        pass to a blip. A genuinely permanent failure still raises, and
        the run is resumable either way: the ledger is written as it
        goes, so a re-run skips everything already uploaded."""
        attempt = 0
        while True:
            try:
                return fn()
            except Exception as exc:
                text = str(exc)
                is_net = any(t in text for t in self._NET_TRANSIENT)
                is_api = any(t in text for t in self._API_TRANSIENT)
                limit = net_tries if is_net else tries
                if not (is_net or is_api) or attempt >= limit - 1:
                    raise
                delay = min(2 ** attempt * 5, 300 if is_net else 120)
                if is_net and attempt == 0:
                    print(f"  network unreachable — retrying for up to "
                          f"~20 min: {text[:80]}")
                time.sleep(delay)
                attempt += 1

    def folder(self, name: str, parent: str | None) -> str:
        key = f"{parent or 'root'}/{name}"
        with self._lock:
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
        with self._lock:
            self.state["folders"][key] = fid
        self.save()
        return fid

    def _moved_source(self, local_md5: str, name: str) -> tuple[str, str] | None:
        """A ledger entry for the same bytes under the same filename whose
        local path has since gone — i.e. this file was re-filed, not
        created. Returns (old_rel, file_id), or None.

        Re-partitioning a site moves whole application folders between
        site folders, and the ledger is keyed on local path, so every
        moved document reads as brand new. Uploading it again would send
        bytes Drive already holds and leave the original orphaned in a
        folder nobody links to. Drive can reparent instead, which costs
        one API call and no bandwidth.

        Deliberately strict. The match needs identical bytes AND an
        identical filename, and it needs the old path to be *gone* — a
        file still present locally is a genuine second copy, not a move.
        Ambiguity is declined: two candidates mean the tree holds the
        same document in two places and there is no way to say which one
        this is, so it uploads rather than guess and strand the other.
        """
        index = self._md5_index()
        candidates = [(rel, meta["id"]) for rel, meta in index.get(local_md5, [])
                      if Path(rel).name == name and not Path(rel).exists()]
        return candidates[0] if len(candidates) == 1 else None

    def _md5_index(self) -> dict[str, list]:
        # Callers hold self._lock; the cache and the ledger it is built
        # from are guarded together.
        if getattr(self, "_md5_cache", None) is None:
            idx: dict[str, list] = {}
            for rel, meta in self.state["files"].items():
                if meta.get("md5") and meta.get("id"):
                    idx.setdefault(meta["md5"], []).append((rel, meta))
            self._md5_cache = idx
        return self._md5_cache

    def upload(self, local: Path, parent: str) -> str:
        from googleapiclient.http import MediaFileUpload

        rel = str(local)
        local_md5 = md5_of(local)
        with self._lock:
            cached = self.state["files"].get(rel)
            if cached and cached.get("md5") == local_md5:
                return "cached"
        name = local.name

        with self._lock:
            moved = self._moved_source(local_md5, name)
        if moved:
            old_rel, fid = moved
            meta = self._retry(lambda: self.svc.files().get(
                fileId=fid, fields="parents, trashed").execute())
            if not meta.get("trashed"):
                old_parents = ",".join(meta.get("parents") or [])
                if parent not in (meta.get("parents") or []):
                    self._retry(lambda: self.svc.files().update(
                        fileId=fid, addParents=parent,
                        removeParents=old_parents, fields="id").execute())
                with self._lock:
                    self.state["files"][rel] = {"md5": local_md5, "id": fid}
                    self.state["files"].pop(old_rel, None)
                    self._md5_cache = None
                self.save()
                return "moved"
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
                with self._lock:
                    self.state["files"][rel] = {"md5": local_md5, "id": remote["id"]}
                    self._md5_cache = None
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
        with self._lock:
            self.state["files"][rel] = {"md5": local_md5, "id": fid}
            self._md5_cache = None
        self.save()
        return outcome

    def prune(self, root_dir: Path, dry_run: bool, force: bool) -> dict:
        """Trash uploads whose local file no longer exists.

        The ledger is the only thing that can drive this. The grant is
        `drive.file`, so the API cannot list the handover folder's
        contents — there is no far side to diff against, only the record
        of what this tool put there. That is a real limitation and it
        cuts the safe way: a file this tool never uploaded is invisible
        to it and therefore cannot be deleted by it.

        Trashed, never deleted. A wrong prune is then a restore from the
        Drive bin rather than a re-upload of 70GB.
        """
        prefix = str(root_dir)
        tracked = [rel for rel in self.state["files"]
                   if rel == prefix or rel.startswith(prefix + "/")]
        # Release artefacts sit at the top level of the tree and are the
        # one thing here that accumulates on purpose. Phase 1 published
        # `dc_handover_phase1.xlsx`; phase 2 publishes its own alongside,
        # and anything already citing phase 1 has to keep resolving. They
        # leave the local build directory as soon as the next release is
        # built, which to a path-based prune is indistinguishable from a
        # rename — so the prune does not look at them at all.
        kept_root = [rel for rel in tracked
                     if Path(rel).parent == root_dir and not Path(rel).exists()]
        gone = [rel for rel in tracked
                if not Path(rel).exists() and Path(rel).parent != root_dir]
        if kept_root:
            print(f"prune: keeping {len(kept_root)} released artefact(s) at the "
                  f"tree root that are no longer built locally — "
                  f"{', '.join(Path(r).name for r in sorted(kept_root))}")
        counts = {"tracked": len(tracked), "trashed": 0,
                  "already gone": 0, "failed": 0}
        if not gone:
            print("prune: nothing to remove — every tracked file still exists")
            return counts
        # A staging tree that failed halfway through its build looks
        # exactly like a tree whose files were all legitimately renamed.
        # The difference matters and the ledger cannot tell them apart,
        # so a prune of most of the archive has to be asked for twice.
        share = len(gone) / len(tracked) if tracked else 0
        print(f"prune: {len(gone)} of {len(tracked)} tracked files "
              f"({share:.0%}) no longer exist locally")
        for rel in gone[:10]:
            print(f"    - {rel}")
        if len(gone) > 10:
            print(f"    ... and {len(gone) - 10} more")
        if share > 0.5 and not force:
            print("prune: REFUSED — that is more than half the tree. If the "
                  "staging build did not finish, pruning now would empty the "
                  "archive. Rebuild and re-run, or pass --prune-anyway if "
                  "this really is intended.")
            counts["failed"] = len(gone)
            return counts
        if dry_run:
            print("prune: --dry-run, nothing trashed")
            return counts
        for rel in gone:
            fid = self.state["files"][rel].get("id")
            if not fid:
                del self.state["files"][rel]
                counts["already gone"] += 1
                continue
            try:
                self._retry(lambda: self.svc.files().update(
                    fileId=fid, body={"trashed": True}).execute())
                counts["trashed"] += 1
            except Exception as exc:
                if "404" in str(exc) or "notFound" in str(exc):
                    counts["already gone"] += 1
                else:
                    counts["failed"] += 1
                    print(f"  PRUNE FAILED {rel}: {str(exc)[:140]}")
                    continue
            del self.state["files"][rel]
            self.save()
        self.save(force=True)
        return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", action="store_true",
                    help="Run the consent flow and exit.")
    ap.add_argument("--sync", type=Path)
    ap.add_argument("--dest", default=None,
                    help="Top-level folder NAME to create or reuse. Almost "
                         "never what you want — see --dest-id.")
    ap.add_argument("--dest-id", default=HANDOVER_FOLDER_ID,
                    help="Drive folder ID to sync into (from the folder's "
                         "URL). Defaults to the handover folder. The "
                         "drive.file scope can create files inside a folder "
                         "it did not create but cannot list that folder's "
                         "other contents, so pre-existing files are "
                         "invisible to this tool by design.")
    ap.add_argument("--prune", action="store_true",
                    help="After uploading, move to the Drive bin every file "
                         "this tool uploaded from under --sync whose local "
                         "copy has since gone. Required after anything that "
                         "renames staged files, because the upload pass adds "
                         "the new name and leaves the old one in place.")
    ap.add_argument("--prune-anyway", action="store_true",
                    help="Let --prune proceed when it would remove more than "
                         "half the tracked tree. Almost always means the "
                         "staging build did not finish.")
    ap.add_argument("--workers", type=int, default=1,
                    help="concurrent upload/move workers. 1 (default) is "
                         "the historical sequential behaviour; the sync "
                         "is latency-bound, not quota-bound, so 8-16 is "
                         "safe. Folder resolution stays sequential "
                         "regardless.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what --prune would bin and stop, uploading "
                         "nothing. Run this first.")
    ap.add_argument("--probe-id",
                    help="Write a single tiny file into this folder ID to "
                         "verify access, then report and stop.")
    args = ap.parse_args()

    creds = get_credentials()
    svc = get_service(creds)
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

    sync = Sync(svc, credentials=creds)
    # Resolving the destination by name is how a second, parallel copy of
    # the whole archive came to exist. The handover folder was created by
    # the operator, so `drive.file` cannot see it — a name lookup found
    # nothing, silently created "DC Planning Dataset" at My Drive root,
    # and every later run filled that instead. Both trees then held 429
    # site folders and the exports landed in the one nobody was reading.
    #
    # The ID is therefore the default and a name has to be asked for.
    if args.dest and args.dest_id != HANDOVER_FOLDER_ID:
        ap.error("give --dest or --dest-id, not both")
    if args.dest:
        print(f"WARNING: resolving destination by name {args.dest!r}. If a "
              f"folder of that name is not visible to this tool it will "
              f"create a new one, which is rarely intended.")
        root = sync.folder(args.dest, None)
    else:
        root = args.dest_id
    print(f"destination folder id: {root}")
    if args.dry_run:
        if not args.prune:
            ap.error("--dry-run only describes --prune; pass both")
        sync.prune(args.sync, dry_run=True, force=args.prune_anyway)
        return
    counts = {"uploaded": 0, "updated": 0, "moved": 0, "skipped": 0,
              "cached": 0, "failed": 0}
    t0 = time.time()
    files = sorted(p for p in args.sync.rglob("*")
                   if p.is_file() and not p.name.startswith("."))
    print(f"{len(files)} files to consider -> Drive folder {root} "
          f"({args.workers} worker{'s' if args.workers != 1 else ''})")
    folder_ids: dict[Path, str] = {args.sync: root}

    def parent_id(f: Path):
        # Sequential and main-thread only: concurrent folder-by-name
        # resolution could create the same folder twice, which is the
        # duplicate-archive failure the ID-only rule exists to prevent.
        parent_path = f.parent
        if parent_path not in folder_ids:
            fid = root
            for part in parent_path.relative_to(args.sync).parts:
                fid = sync.folder(part, fid)
            folder_ids[parent_path] = fid
        return folder_ids[parent_path]

    def progress(i):
        if i % 200 == 0:
            rate = i / (time.time() - t0)
            eta = (len(files) - i) / rate / 3600
            print(f"  {i}/{len(files)}  {counts}  eta {eta:.1f}h", flush=True)

    if args.workers <= 1:
        for i, f in enumerate(files, 1):
            try:
                # Inside the try deliberately: resolving the folder chain
                # calls the API too, and when it sat outside, one failure
                # there ended the whole pass rather than one file. That is
                # how the 2026-08-25 overnight run died at 2,800 of 54,293.
                outcome = sync.upload(f, parent_id(f))
                counts[outcome] += 1
            except Exception as exc:
                counts["failed"] += 1
                print(f"  FAILED {f}: {str(exc)[:140]}")
            progress(i)
    else:
        # Workers do API calls only; the ledger is guarded by Sync's own
        # lock, and every count and print stays on this thread.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {}
            for f in files:
                try:
                    futures[pool.submit(sync.upload, f, parent_id(f))] = f
                except Exception as exc:
                    counts["failed"] += 1
                    print(f"  FAILED {f}: {str(exc)[:140]}")
            for i, fut in enumerate(as_completed(futures), 1):
                try:
                    counts[fut.result()] += 1
                except Exception as exc:
                    counts["failed"] += 1
                    print(f"  FAILED {futures[fut]}: {str(exc)[:140]}")
                progress(i)
    sync.save(force=True)
    print(f"done: {counts}")
    # After the uploads, never before: pruning first would bin a file and
    # then re-upload it under the same name if the local tree still had it.
    if args.prune:
        print(f"prune: {sync.prune(args.sync, dry_run=False, force=args.prune_anyway)}")


if __name__ == "__main__":
    main()
