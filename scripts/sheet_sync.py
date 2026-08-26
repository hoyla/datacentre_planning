#!/usr/bin/env python3
"""Refresh the Google Sheet's data without disturbing its formatting.

The workbook is regenerated on every export, and re-importing it into
Drive produces a *new* Sheet — losing the column widths, wrapping,
alignment and freezes that someone sat and did by hand. Doing that after
every regeneration is not sustainable, so the data is written in place
instead.

This works because Sheets keeps values and formatting in separate
layers. A values write replaces what a cell contains and touches nothing
about how it looks, so the tidying survives indefinitely.

Two things make it more than a values write:

**Columns move.** When the exporter adds a column — as it did when
Proposal and its flag arrived at D and E — writing values straight over
the top shifts every column right of the insertion point, and the
carefully set widths end up describing the wrong data. So the header row
is reconciled first: new columns are *inserted* and removed ones
*deleted*, which carries the existing formatting sideways with them.

**Not every tab is ours.** An annotation tab is the whole reason the
Sheet exists rather than the xlsx, and it must never be in scope. Only
tabs whose names match the generated workbook are written; anything else
is left strictly alone and reported.

Scope: this needs `spreadsheets`, which the Drive sync's `drive.file`
grant does not cover — that one is deliberately limited to files the tool
itself created, and the Sheet was made by converting the workbook. The
consent is separate and cached separately, so authorising this cannot
widen what the document sync can reach.

    scripts/sheet_sync.py --auth                 # one-off consent
    scripts/sheet_sync.py --dry-run              # what would change
    scripts/sheet_sync.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcp import release  # noqa: E402
from dcp.drive import WORKBOOK_SHEET_URL  # noqa: E402

CONFIG_DIR = Path.home() / ".config" / "datacentre_planning"
CLIENT_SECRET = CONFIG_DIR / "client_secret.json"
TOKEN_PATH = CONFIG_DIR / "sheets_token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DEFAULT_WORKBOOK = release.latest_workbook(
    Path("data/exports/phase1_build/dc_handover_phase1.xlsx"))

# Anything Sheets would read as a formula. The exporter emits deliberate
# =HYPERLINK() cells and those must stay live, but a council's own
# description beginning "+/- 40 dwellings" is text and must not be
# evaluated — the same guard as against spreadsheet injection.
_FORMULA_START = re.compile(r"^[=+\-@]")
_INTENDED = re.compile(r"^=HYPERLINK\(", re.I)


def spreadsheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if not m:
        raise SystemExit(f"cannot find a spreadsheet id in {url!r}")
    return m.group(1)


def get_service(force_consent: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists() and not force_consent:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token and not force_consent:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise SystemExit(f"no client secret at {CLIENT_SECRET}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES)
            print("Opening a browser to authorise spreadsheet access. This is a "
                  "separate grant from the document sync and does not widen it.")
            creds = flow.run_local_server(port=0)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        TOKEN_PATH.chmod(0o600)
    return build("sheets", "v4", credentials=creds)


def cell(value) -> str | float | int | bool:
    """One workbook cell as Sheets should receive it."""
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if _FORMULA_START.match(text) and not _INTENDED.match(text):
        return "'" + text          # shown as typed, never evaluated
    return text


def read_workbook(path: Path) -> dict[str, list[list]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=False)
    out: dict[str, list[list]] = {}
    for ws in wb.worksheets:
        rows = [[cell(c) for c in row]
                for row in ws.iter_rows(values_only=True)]
        # Trailing blank rows would otherwise clear formatting-only rows
        # the reader added below the data.
        while rows and not any(str(v).strip() for v in rows[-1]):
            rows.pop()
        out[ws.title] = rows
    return out


def named_prefix(want: list[str]) -> list[str]:
    """The generated header ends where its names do — see reconcile_columns."""
    return list(want[:next((i for i, n in enumerate(want)
                            if not n.strip()), len(want))])


def reordered_columns(have: list[str], want: list[str]) -> list[str]:
    """Columns present in both headers but in a different relative order.

    reconcile_columns never moves a column, deliberately. The cost of
    that choice is that a reordered export writes its values under
    columns formatted for something else, and the data is internally
    consistent so nothing looks wrong. Naming the columns here is what
    turns that into something a person can see.
    """
    if not any(h.strip() for h in have):
        return []
    want = named_prefix(want)
    common = [c for c in have if c in want]
    target = [c for c in want if c in common]
    return [c for c, t in zip(common, target) if c != t]


def reconcile_columns(have: list[str], want: list[str]) -> list[dict]:
    """Column edits that turn `have` into `want`, formatting carried along.

    Deliberately conservative: it only inserts and deletes, never moves.
    A move would be a delete plus an insert, which throws away the
    formatting of the column being moved — the one thing this script
    exists to preserve. Reordered columns are reported to the caller
    instead, for a human to decide about.
    """
    # An empty header row means a tab nobody has populated yet. It already
    # has blank columns, so asking to insert more would push the grid
    # sideways for nothing; the values write alone fills it.
    if not any(h.strip() for h in have):
        return []
    # Not every generated tab is a table. External aggregates is a report
    # — a title in A1, then several small tables down the sheet — so its
    # "header row" is one heading followed by blanks, padded out to the
    # width of the widest table below. Reconciling by name asked to
    # insert five nameless columns, which would have pushed that whole
    # tab five columns to the right and left the formatting describing
    # empty space. A column with no name cannot be matched by name, so
    # the header ends where the names do.
    want = named_prefix(want)
    edits: list[dict] = []
    cur = list(have)
    # Remove what the export no longer produces, right to left so the
    # indices of the untouched columns stay valid.
    for i in range(len(cur) - 1, -1, -1):
        if cur[i] and cur[i] not in want:
            edits.append({"delete": i})
            cur.pop(i)
    # Insert what is new, left to right, at its position in the target.
    for target, name in enumerate(want):
        if target >= len(cur) or cur[target] != name:
            if name in cur[target:]:
                continue           # present but out of order; leave it
            edits.append({"insert": target, "name": name})
            cur.insert(target, name)
    return edits


def a1(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    ap.add_argument("--url", default=WORKBOOK_SHEET_URL)
    ap.add_argument("--auth", action="store_true",
                    help="run the consent flow and exit")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-drift", action="store_true",
                    help="write anyway when the Sheet's shape no longer "
                         "matches the workbook's (missing tabs, reordered "
                         "columns) instead of refusing")
    args = ap.parse_args()

    if args.auth:
        get_service(force_consent=True)
        print(f"authorised; token cached at {TOKEN_PATH}")
        return 0

    if not args.workbook.exists():
        raise SystemExit(f"no workbook at {args.workbook}")
    data = read_workbook(args.workbook)
    svc = get_service()
    sid = spreadsheet_id(args.url)

    try:
        meta = svc.spreadsheets().get(spreadsheetId=sid).execute()
    except Exception as exc:
        # A converted workbook and an .xlsx being edited in Drive's Office
        # mode look identical in a browser and share a /spreadsheets/d/
        # URL, but only the former has an API behind it. This is the error
        # that distinguishes them, and the fix is not obvious from it.
        if "must not be an Office file" in str(exc):
            raise SystemExit(
                "That document is still an .xlsx opened in Drive's Office "
                "compatibility mode, not a Google Sheet, and the Sheets API "
                "cannot write to it.\n\n"
                "Convert it once — File > Save as Google Sheets — which "
                "keeps the column widths, wrapping and alignment and "
                "produces a new file id. Put that URL in dcp/drive.py as "
                "WORKBOOK_SHEET_URL and run this again.")
        raise
    tabs = {s["properties"]["title"]: s["properties"] for s in meta["sheets"]}
    print(f"{meta['properties']['title']!r}: {len(tabs)} tabs")

    theirs = [t for t in tabs if t not in data]
    if theirs:
        print(f"  leaving alone (not generated): {', '.join(sorted(theirs))}")

    # Drift is anything the reconciliation cannot carry across on its own.
    # It used to be printed and then ignored, which in an automated chain
    # is a warning nobody reads and a run that reports success — so it is
    # collected and refused instead.
    drift: list[str] = []
    missing = [t for t in data if t not in tabs]
    if missing:
        print(f"  NOT in the Sheet, skipped: {', '.join(missing)}")
        print("   create these tabs by hand first if they are wanted, so they "
              "can be formatted once and kept")
        drift += [f"tab {t!r} is in the workbook but not in the Sheet"
                  for t in missing]

    requests: list[dict] = []
    value_ranges: list[dict] = []
    clears: list[str] = []

    for title, rows in data.items():
        if title not in tabs or not rows:
            continue
        props = tabs[title]
        gid = props["sheetId"]
        grid = props["gridProperties"]
        want = [str(h) for h in rows[0]]

        head = svc.spreadsheets().values().get(
            spreadsheetId=sid,
            range=f"{a1(title)}!1:1").execute().get("values", [[]])
        have = [str(h) for h in (head[0] if head else [])]

        moved = reordered_columns(have, want)
        if moved:
            print(f"  {title:18} REORDERED: {', '.join(moved)}")
            drift.append(f"{title}: columns reordered ({', '.join(moved)}) — "
                         "the widths would describe the wrong data")

        edits = reconcile_columns(have, want)
        for e in edits:
            if "delete" in e:
                requests.append({"deleteDimension": {"range": {
                    "sheetId": gid, "dimension": "COLUMNS",
                    "startIndex": e["delete"], "endIndex": e["delete"] + 1}}})
            else:
                requests.append({"insertDimension": {
                    "range": {"sheetId": gid, "dimension": "COLUMNS",
                              "startIndex": e["insert"],
                              "endIndex": e["insert"] + 1},
                    "inheritFromBefore": e["insert"] > 0}})

        # Grow the grid if the data is now taller or wider than the tab.
        need_rows, need_cols = len(rows), max(len(r) for r in rows)
        if grid.get("rowCount", 0) < need_rows:
            requests.append({"appendDimension": {
                "sheetId": gid, "dimension": "ROWS",
                "length": need_rows - grid["rowCount"]}})
        if grid.get("columnCount", 0) < need_cols:
            requests.append({"appendDimension": {
                "sheetId": gid, "dimension": "COLUMNS",
                "length": need_cols - grid["columnCount"]}})

        value_ranges.append({"range": f"{a1(title)}!A1", "values": rows})
        # Anything below the new data is a leftover from a longer run.
        if grid.get("rowCount", 0) > need_rows:
            clears.append(f"{a1(title)}!A{need_rows + 1}:ZZZ{grid['rowCount']}")

        note = (f"{len(edits)} column edit{'' if len(edits) == 1 else 's'}"
                if edits else "columns unchanged")
        print(f"  {title:18} {len(rows):>5} rows x {need_cols:>3} cols   {note}")
        for e in edits:
            print(f"      {'insert ' + e['name'] if 'insert' in e else 'delete column ' + str(e['delete'] + 1)}")

    if drift:
        print("\nthe Sheet's shape no longer matches the workbook's:")
        for d in drift:
            print(f"  !! {d}")
        if not args.allow_drift:
            print("REFUSING — fix the Sheet by hand (create the tab, or put "
                  "the columns back in the exporter's order), or re-run with "
                  "--allow-drift to write the rest anyway.")
            return 1

    if args.dry_run:
        print("\ndry run — nothing written")
        return 0

    if requests:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=sid, body={"requests": requests}).execute()
        print(f"applied {len(requests)} structural change(s)")
    if clears:
        svc.spreadsheets().values().batchClear(
            spreadsheetId=sid, body={"ranges": clears}).execute()
    if value_ranges:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=sid,
            body={"valueInputOption": "USER_ENTERED", "data": value_ranges}
        ).execute()
        print(f"wrote {sum(len(v['values']) for v in value_ranges):,} rows "
              f"across {len(value_ranges)} tabs; formatting untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
