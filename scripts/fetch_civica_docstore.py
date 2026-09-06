"""Download documents from a council's Civica "Planning Documents" store.

Four Idox registers whose documents tab refuses with an HTTP 200 —
Gateshead, Chelmsford, Reigate & Banstead, Southend — link from their
External Documents tab to a Civica portal page,
`…/planning/planning-documents?SDescription=<ref>`, an empty shell that
fills its document list by API (found 2026-09-06 by watching the page's
own requests; every call is session-free):

    POST <host>/w2webparts/Resource/Civica/Handler.ashx/keyobject/search
         {"refType": "GFPlanning", "fromRow": 1, "toRow": 100,
          "searchFields": {"SDescription": "<ref>"}}
      -> [ {KeyNumber, KeyText, KeyObjectType, Items: [{FieldName, Value}, …]}, … ]
    POST …/Handler.ashx/doc/list
         {"KeyNumb": <KeyNumber>, "KeyText": <KeyText>, "RefType": "GFPlanning"}
      -> {"CompleteDocument": [ {DocNo, FileName, DocDesc, TypeCode, FileExtension, DocDate}, … ],
          "RowCount": "<n>"}
    GET  …/Handler.ashx/Doc/pagestream?cd=download&pdf=false&docno=<DocNo>
      -> the file (application/pdf, %PDF)

Typed, the Newport docstore's lesson. The search is trusted only when
exactly one case comes back and its `SDescription` item equals the
reference — the same endpoint answers an unfiltered search with the
whole register, so a shape mismatch would otherwise fetch someone
else's documents. The list is trusted only when the rows match
`RowCount`; a list of zero rows on a found case is the store's own
empty and settles through `classify_outcome`; anything else is
`UnrecognisedListing` and stays retryable. Outcomes are recorded under
`<council>_docstore`; bytes land in the standard per-application layout
with the pagestream URL as provenance. Idempotent on URL + bytes on disk.

Usage:
    .venv/bin/python scripts/fetch_civica_docstore.py --dry-run
    .venv/bin/python scripts/fetch_civica_docstore.py --council Gateshead
    .venv/bin/python scripts/fetch_civica_docstore.py --ref Southend/19/00237/FUL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.acquisition_outcome import SETTLED, classify_outcome, record  # noqa: E402
from dcp.sources import idox as _idox  # noqa: E402

log = logging.getLogger("civica_docstore")

# council prefix -> Civica host. Every one of the four carries the same
# `Civica.APIUrl` and `PlanningApplicationRefType` in its shell page.
STORES = {
    "Gateshead": "https://myserviceplanning.gateshead.gov.uk",
    "Chelmsford": "https://planning.chelmsford.gov.uk",
    "Reigate": "https://dmdocs.reigate-banstead.gov.uk",
    "Southend": "https://publicedrms.southend.gov.uk",
}
API_PATH = "/w2webparts/Resource/Civica/Handler.ashx"
REF_TYPE = "GFPlanning"
UA = ("Mozilla/5.0 (compatible; datacentre_planning research; "
      "+mailto:luke.hoyland@gmail.com)")

COHORT = """
SELECT a.id, a.application_ref
FROM applications a
WHERE split_part(a.application_ref, '/', 1) = %s
  AND EXISTS (SELECT 1 FROM site_members m JOIN sites s ON s.id = m.site_id
              WHERE m.application_id = a.id
                AND m.retired_at IS NULL AND s.retired_at IS NULL)
  AND (%s OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id))
ORDER BY a.application_ref
"""


class UnrecognisedListing(RuntimeError):
    """The store answered with something that is not a measurement of
    what it holds for this case — a search that did not name the case
    exactly once, a document list whose rows do not match its own
    count, or a body that is not the JSON the page reads. Retryable."""


def council_of(ref: str) -> str:
    council = ref.split("/", 1)[0]
    if council not in STORES:
        raise ValueError(f"no Civica document store recorded for {council!r}")
    return council


def api(council: str, path: str) -> str:
    return f"{STORES[council]}{API_PATH}/{path}"


def document_url(council: str, docno: str) -> str:
    return api(council, f"Doc/pagestream?cd=download&pdf=false&docno={docno}")


def parse_search(body: str, ref: str) -> tuple[str, str]:
    """(KeyNumber, KeyText) of the one case whose reference is `ref`.

    Zero matches, more than one, or a match whose `SDescription` is not
    the reference: `UnrecognisedListing`. The endpoint answers a search
    it does not understand with the whole register, so "one result"
    is not enough — the result has to say the reference back.
    """
    short = ref.split("/", 1)[1]
    try:
        objs = json.loads(body)
    except ValueError as exc:
        raise UnrecognisedListing(f"search body is not JSON: {exc}") from exc
    if not isinstance(objs, list):
        raise UnrecognisedListing(f"search body is not a list: {type(objs).__name__}")
    matches = []
    for o in objs:
        items = {i.get("FieldName"): i.get("Value") for i in o.get("Items", [])}
        if (items.get("SDescription") or "").strip().upper() == short.upper():
            matches.append(o)
    if len(matches) != 1:
        raise UnrecognisedListing(
            f"search for {short!r} returned {len(objs)} case(s), "
            f"{len(matches)} naming the reference")
    o = matches[0]
    if not o.get("KeyNumber") or not o.get("KeyText"):
        raise UnrecognisedListing(f"case for {short!r} carries no key: {o!r}"[:200])
    return str(o["KeyNumber"]), str(o["KeyText"])


def parse_doclist(body: str) -> list[dict]:
    """[{docno, filename, kind, description, ext, date}] from `doc/list`;
    an empty list only when the store says `RowCount` 0."""
    try:
        obj = json.loads(body)
    except ValueError as exc:
        raise UnrecognisedListing(f"document list is not JSON: {exc}") from exc
    if not isinstance(obj, dict) or "RowCount" not in obj:
        raise UnrecognisedListing("document list carries no RowCount")
    rows = obj.get("CompleteDocument") or []
    docs = []
    for r in rows:
        if not r.get("DocNo"):
            raise UnrecognisedListing(f"document row without DocNo: {r!r}"[:200])
        docs.append({"docno": str(r["DocNo"]), "filename": r.get("FileName"),
                     "kind": r.get("DocDesc"), "type_code": r.get("TypeCode"),
                     "ext": (r.get("FileExtension") or "").lower(),
                     "date": (r.get("DocDate") or "")[:10]})
    if len(docs) != int(obj["RowCount"]):
        raise UnrecognisedListing(
            f"store says RowCount {obj['RowCount']}, list carries {len(docs)}")
    return docs


def list_documents(client: httpx.Client, council: str, ref: str) -> list[dict]:
    short = ref.split("/", 1)[1]
    r = client.post(api(council, "keyobject/search"),
                    json={"refType": REF_TYPE, "fromRow": 1, "toRow": 100,
                          "searchFields": {"SDescription": short}})
    r.raise_for_status()
    key_numb, key_text = parse_search(r.text, ref)
    r = client.post(api(council, "doc/list"),
                    json={"KeyNumb": key_numb, "KeyText": key_text,
                          "RefType": REF_TYPE, "ProcessNo": "", "OrderBy": "",
                          "PageSize": "", "Filters": ""})
    r.raise_for_status()
    return parse_doclist(r.text)


def _record(conn, app_id: int, summary: dict, *, dry_run: bool, adapter: str,
            note: str | None = None) -> None:
    outcome, detail = classify_outcome(summary)
    if note:
        detail = note if outcome in SETTLED else (f"{detail} — {note}" if detail else note)
    if dry_run:
        log.info("        would record %s (%s)", outcome, detail)
        return
    record(conn, app_id, outcome, adapter, detail, found=summary.get("downloaded") or 0)


def fetch_one(conn, client: httpx.Client, *, app_id: int, ref: str,
              data_dir: Path, delay: float, dry_run: bool) -> dict:
    council = council_of(ref)
    adapter = f"{council.lower()}_docstore"
    docs = list_documents(client, council, ref)
    time.sleep(delay)
    with conn.cursor() as cur:
        cur.execute("SELECT url, bytes_path FROM documents WHERE application_id=%s", (app_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}
    summary = {"links_found": len(docs), "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    if not docs:
        summary["error_class"] = "no_documents"
        _record(conn, app_id, summary, dry_run=dry_run, adapter=adapter,
                note="Civica store found the case and listed no documents (RowCount 0)")
        return summary
    if dry_run:
        for d in docs:
            log.info("        would fetch %-24s %s", (d["kind"] or "?")[:24], (d["filename"] or "")[:60])
        return summary
    for d in docs:
        url = document_url(council, d["docno"])
        bp = prior.get(url)
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            resp = client.get(url)
            resp.raise_for_status()
            body = resp.content
            repo.check_document_body(body, url=url)
        except Exception as exc:
            log.warning("  FAIL %s (%s): %s", d["docno"], (d["filename"] or "")[:50], exc)
            summary["errors"] += 1
            time.sleep(delay)
            continue
        sha = hashlib.sha256(body).hexdigest()
        ctype = resp.headers.get("content-type") or ""
        ext = ("pdf" if "pdf" in ctype or body[:4] == b"%PDF"
               else (d["ext"] if d["ext"].isalnum() and len(d["ext"]) <= 4 else "bin"))
        target = _idox._bytes_path(data_dir, ref, sha, ext)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(conn, application_id=app_id, url=url,
                             kind=d["kind"], content_sha256=sha, bytes_path=str(target))
        conn.commit()
        summary["downloaded"] += 1
        time.sleep(delay)
    _idox._write_manifest(conn, application_id=app_id, application_ref=ref,
                          app_dir=_idox._app_dir(data_dir, ref), summary=summary)
    _record(conn, app_id, summary, dry_run=dry_run, adapter=adapter)
    conn.commit()
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ref", help="one application, e.g. Gateshead/23/00495/DOC4")
    p.add_argument("--council", choices=sorted(STORES),
                   help="one council's cohort; default every council in STORES")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=5.0)
    p.add_argument("--include-held", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with db.connect() as conn, conn.cursor() as cur:
        if args.ref:
            cur.execute("SELECT id, application_ref FROM applications WHERE application_ref=%s",
                        (args.ref,))
            targets = cur.fetchall()
        else:
            targets = []
            for council in ([args.council] if args.council else sorted(STORES)):
                cur.execute(COHORT, (council, args.include_held))
                targets += cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]
    log.info("%d application(s) to try at Civica document stores", len(targets))
    if not targets:
        return 0

    totals = {"apps": 0, "stored": 0, "existing": 0, "empty": 0, "errors": 0}
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True,
                      timeout=120) as client, db.connect() as conn:
        for council in STORES:
            repo.ensure_source(conn, name=f"{council.lower()}_docstore", kind="council",
                               base_url=STORES[council])
        conn.commit()
        for i, (app_id, ref) in enumerate(targets, 1):
            totals["apps"] += 1
            adapter = f"{council_of(ref).lower()}_docstore"
            try:
                s = fetch_one(conn, client, app_id=app_id, ref=ref,
                              data_dir=args.data_dir, delay=args.delay,
                              dry_run=args.dry_run)
            except UnrecognisedListing as exc:
                log.error("[%d/%d] %s unrecognised listing: %s", i, len(targets), ref, exc)
                totals["errors"] += 1
                _record(conn, app_id, {"errors": 1, "links_found": 0,
                                       "error_class": "unrecognised_listing"},
                        dry_run=args.dry_run, adapter=adapter, note=str(exc)[:120])
                continue
            except Exception as exc:
                log.error("[%d/%d] %s failed: %s", i, len(targets), ref, exc)
                totals["errors"] += 1
                _record(conn, app_id, {"errors": 1, "links_found": 0,
                                       "error_class": type(exc).__name__},
                        dry_run=args.dry_run, adapter=adapter, note=str(exc)[:120])
                continue
            if not s["links_found"]:
                totals["empty"] += 1
            totals["stored"] += s["downloaded"]
            totals["existing"] += s["skipped_existing"]
            totals["errors"] += s["errors"]
            log.info("[%d/%d] %-26s listed=%d stored=%d existing=%d errors=%d",
                     i, len(targets), ref, s["links_found"], s["downloaded"],
                     s["skipped_existing"], s["errors"])
    log.info("done: %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
