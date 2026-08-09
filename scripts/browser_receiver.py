#!/usr/bin/env python3
"""Local sink for documents harvested in the browser.

Some registers only serve documents to a real browser — Coventry's WAF
rejects scripted clients outright, and several Idox document stores will
not honour a download URL outside a browser session. The browser can
fetch them, but getting the bytes back out meant a file download, and
every download needs a human to press Save. That makes an overnight run
impossible, which is the wrong reason to leave documents unfetched.

So: a loopback HTTP server. The page POSTs each harvested document here
and it lands on disk immediately — no dialog, no human, no clipboard.

Three things make this safe to run:

- It binds 127.0.0.1 only, so nothing off this machine can reach it.
- It accepts one path, writes only under --out, and refuses a filename
  containing a path separator, so a page cannot choose where bytes land.
- It exits on --max-seconds regardless, so a forgotten server does not
  outlive the job it was started for.

Cross-origin is not a problem despite the page being HTTPS: loopback
counts as a potentially-trustworthy origin, and the page sends the POST
with `mode: 'no-cors'` — it never needs to read our response, only to
deliver the bytes.

    scripts/browser_receiver.py --out data/raw/browser_harvest --max-seconds 7200
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


class Receiver(BaseHTTPRequestHandler):
    out_dir: Path = Path("data/raw/browser_harvest")
    written = 0
    lock = threading.Lock()

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self) -> None:            # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:                # noqa: N802
        """Health check, so the page can confirm the sink is up."""
        body = json.dumps({"ok": True, "written": Receiver.written}).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:               # noqa: N802
        if self.path.rstrip("/") != "/put":
            self.send_response(404); self._cors(); self.end_headers(); return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            payload = json.loads(raw)
            name = payload["name"]
            if not SAFE_NAME.match(name):
                raise ValueError(f"unsafe name {name!r}")
            data = base64.b64decode(payload["b64"])
            target = (Receiver.out_dir / name).resolve()
            # Belt and braces: the name regex already forbids separators,
            # but confirm the resolved path really is inside out_dir.
            if not str(target).startswith(str(Receiver.out_dir.resolve())):
                raise ValueError("path escapes output directory")
            target.write_bytes(data)
            with Receiver.lock:
                Receiver.written += 1
            print(f"  received {name}  {len(data):,} bytes "
                  f"(total {Receiver.written})", flush=True)
            self.send_response(200)
        except Exception as exc:
            print(f"  REJECTED: {type(exc).__name__}: {exc}", flush=True)
            self.send_response(400)
        self._cors()
        self.end_headers()

    def log_message(self, *a) -> None:       # quiet; we print our own
        return


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("data/raw/browser_harvest"))
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--max-seconds", type=int, default=7200)
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    Receiver.out_dir = args.out
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Receiver)
    print(f"receiver listening on http://127.0.0.1:{args.port}/put -> {args.out}",
          flush=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    deadline = time.monotonic() + args.max_seconds
    try:
        while time.monotonic() < deadline:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    print(f"stopped after writing {Receiver.written} files", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
