#!/usr/bin/env python3
"""Send the selected drawings to a vision model and store what comes back.

This is the pilot ROADMAP's parked "Multimodal pass over drawings"
reopens for -- the specific applications where the prose demonstrably
fails to carry the figure. Selection is
scripts/drawings_pilot_select.py; rasterisation is
dcp/drawings_raster.py; the question is dcp/drawings_prompt.py.

Everything written lands in `drawing_transcriptions`, which is
quarantined by design: nothing joins it to power_adjudication, to the
site capacity panels or to any artefact, and `human_verdict` is NULL
until somebody has put each transcription beside the tile image it came
from. See migrations/027 for why -- the project's quote round-trip
cannot verify a transcription against an image, so every row is
unverified by construction, and a vision misread of "2 x 3MVA" as
"23 MVA" is a confident figure wrong by a factor of four.

    scripts/drawings_pilot_run.py --sample --limit 3   # hone the prompt
    scripts/drawings_pilot_run.py --run                # the batch
    scripts/drawings_pilot_run.py --review-sheet       # the hand check
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from dcp import db
from dcp import drawings_prompt as dp
from dcp import drawings_raster as dr

PILOT_DIR = ROOT / "data" / "drawings_pilot"
TILE_DIR = PILOT_DIR / "tiles"
RAW_DIR = PILOT_DIR / "raw"

DEFAULT_MODEL = "gpt-5.6-sol"
MAX_COMPLETION_TOKENS = 24_000

# Measured 2026-08-26 against the models list on this key. The pilot
# must not silently fall back to a different model: a transcription is
# only interpretable beside the model that made it, and a run that says
# gpt-5.6-sol in the table while gpt-4o did the reading is a provenance
# failure, not a convenience.
def _require_model(client, model: str) -> None:
    try:
        available = {m.id for m in client.models.list()}
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"could not list models to verify {model!r}: {exc}")
    if model not in available:
        sys.exit(f"model {model!r} is not available on this key. "
                 f"Nearest: {sorted(m for m in available if m.startswith('gpt-5'))}")


def _client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set (add it to .env)")
    return OpenAI()


SELECTION_PATH = PILOT_DIR / "selection.json"


def load_selection(path: Path | None = None) -> list[dict]:
    path = path or SELECTION_PATH
    if not path.exists():
        sys.exit(f"{path} missing -- run scripts/drawings_pilot_select.py --select")
    return json.loads(path.read_text())


def _messages(row: dict, sheet: dr.RenderedSheet) -> list[dict]:
    content: list[dict] = [
        {"type": "text",
         "text": dp.render(row["application_ref"], row.get("description") or "",
                           row.get("title") or "")},
        {"type": "text",
         "text": f"Image 0 of {len(sheet.tiles) + 1}: the whole sheet, "
                 f"reduced — the OVERVIEW, and the only image on which you "
                 f"may count symbols. Sheet is {sheet.width_pt:.0f} x "
                 f"{sheet.height_pt:.0f} points; tiles are rendered at "
                 f"{sheet.dpi:.0f} DPI."},
        {"type": "image_url",
         "image_url": {"url": sheet.overview_data_url, "detail": "high"}},
    ]
    for t in sheet.tiles:
        content.append({"type": "text",
                        "text": f"Image {t.index}: {t.position}. This is a "
                                f"CROP of the sheet — read detail here, do "
                                f"not count here."})
        content.append({"type": "image_url",
                        "image_url": {"url": t.data_url(), "detail": "high"}})
    return [{"role": "system", "content": dp.SYSTEM},
            {"role": "user", "content": content}]


def read_sheet(client, row: dict, sheet: dr.RenderedSheet, model: str,
               effort: str) -> tuple[dict, object]:
    resp = client.chat.completions.create(
        model=model, max_completion_tokens=MAX_COMPLETION_TOKENS,
        reasoning_effort=effort,
        response_format={"type": "json_schema", "json_schema": {
            "name": "drawing_transcription", "strict": True,
            "schema": dp.SCHEMA}},
        messages=_messages(row, sheet))
    return json.loads(resp.choices[0].message.content or "{}"), resp.usage


def write_tiles(row: dict, sheet: dr.RenderedSheet) -> dict[int, str]:
    """Write the images a reviewer will look at. Returns {tile_index: path}."""
    d = TILE_DIR / f"doc{row['document_id']}"
    d.mkdir(parents=True, exist_ok=True)
    paths = {0: str((d / "overview.png").relative_to(ROOT))}
    (d / "overview.png").write_bytes(sheet.overview)
    for t in sheet.tiles:
        p = d / f"tile{t.index:02d}.png"
        p.write_bytes(t.png)
        paths[t.index] = str(p.relative_to(ROOT))
    return paths


def store(conn, row: dict, sheet: dr.RenderedSheet, answer: dict,
          paths: dict[int, str], outcome: str, usage, elapsed: float,
          model: str) -> None:
    # Enforced here rather than trusted to the prompt: the pilot's "4
    # gensets" was counted on a tile that had cut the fourth machine,
    # and an instruction the storage does not check is a preference.
    items, demoted = dp.enforce_count_provenance(answer.get("items") or [])
    tile_pos = {t.index: t.position for t in sheet.tiles}
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO drawing_transcription_log
              (document_id, application_id, cohort, page_index, tiles_sent,
               render_dpi, sheet_width_pt, sheet_height_pt, outcome,
               items_found, notes, input_tokens, output_tokens, elapsed_s,
               model, prompt_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (document_id, page_index, model, prompt_version)
            DO NOTHING""",
            (row["document_id"], row["application_id"], row["cohort"], 0,
             len(sheet.tiles), sheet.dpi, sheet.width_pt, sheet.height_pt,
             outcome, len(items),
             json.dumps({"sheet_ref": answer.get("sheet_ref"),
                         "drawing_kind": answer.get("drawing_kind"),
                         "sheet_summary": answer.get("sheet_summary"),
                         "sheet_illegible": answer.get("sheet_illegible"),
                         "counts_demoted": demoted}),
             getattr(usage, "prompt_tokens", None),
             getattr(usage, "completion_tokens", None),
             elapsed, model, dp.PROMPT_VERSION))
        for it in items:
            ti = it.get("tile_index") or 0
            cur.execute("""
                INSERT INTO drawing_transcriptions
                  (document_id, application_id, cohort, page_index, tile_index,
                   tile_position, render_dpi, sheet_ref, location_on_sheet,
                   item_kind, value_text, equipment, quantity, column_header,
                   legibility, tile_image_path, model, prompt_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (document_id, page_index, tile_index, model,
                             prompt_version, item_kind, value_text,
                             coalesce(column_header, ''),
                             coalesce(location_on_sheet, ''))
                DO NOTHING""",
                (row["document_id"], row["application_id"], row["cohort"], 0,
                 ti, tile_pos.get(ti), sheet.dpi,
                 it.get("sheet_ref") or answer.get("sheet_ref"),
                 " | ".join(x for x in (it.get("location_on_sheet"),
                                        it.get("note")) if x),
                 it.get("item_kind") or "other", it.get("value_text") or "",
                 it.get("equipment"), it.get("quantity"),
                 it.get("column_header"),
                 it.get("legibility"), paths.get(ti), model,
                 dp.PROMPT_VERSION))


def outcome_of(answer: dict) -> str:
    if answer.get("sheet_illegible"):
        return "illegible"
    if answer.get("items"):
        return "hit"
    return "null"


def do_run(model: str, effort: str, limit: int | None, only: list[int] | None,
           sample: bool) -> None:
    client = _client()
    _require_model(client, model)
    rows = load_selection()
    if only:
        rows = [r for r in rows if r["document_id"] in only]
    if limit:
        rows = rows[:limit]
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    totals = {"hit": 0, "null": 0, "illegible": 0, "error": 0}
    tok_in = tok_out = 0
    with db.connect() as conn:
        for i, row in enumerate(rows, 1):
            path = Path(row["bytes_path"])
            # Version-scoped from drawings-1.1 on. Under one flat name a
            # re-run at a new prompt overwrote the answer the old prompt
            # gave, which is the one thing a comparison between prompts
            # needs. drawings-pilot-1.0's 28 files keep their bare names
            # so the pilot's raw answers stay exactly where they are.
            raw_path = RAW_DIR / (
                f"doc{row['document_id']}.json"
                if dp.PROMPT_VERSION == "drawings-pilot-1.0"
                else f"{dp.PROMPT_VERSION}_doc{row['document_id']}.json")
            if not path.exists():
                print(f"[{i}/{len(rows)}] doc{row['document_id']}: FILE MISSING")
                totals["error"] += 1
                continue
            t0 = time.time()
            try:
                sheet = dr.render_sheet(path, 0)
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(rows)}] doc{row['document_id']}: render failed: {exc}")
                totals["error"] += 1
                continue
            paths = write_tiles(row, sheet)
            # The raw answer is written before anything is stored, so a
            # storage bug never costs a second call for the same sheet.
            if raw_path.exists() and not sample:
                cached = json.loads(raw_path.read_text())
                if cached.get("prompt_version") == dp.PROMPT_VERSION \
                        and cached.get("model") == model:
                    answer, usage, elapsed = cached["answer"], None, cached.get("elapsed_s")
                    oc = outcome_of(answer)
                    store(conn, row, sheet, answer, paths, oc, usage, elapsed, model)
                    conn.commit()
                    totals[oc] += 1
                    print(f"[{i}/{len(rows)}] doc{row['document_id']}: {oc} (cached)")
                    continue
            try:
                answer, usage = read_sheet(client, row, sheet, model, effort)
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(rows)}] doc{row['document_id']}: request failed: {exc}")
                totals["error"] += 1
                continue
            elapsed = time.time() - t0
            raw_path.write_text(json.dumps(
                {"document_id": row["document_id"], "model": model,
                 "prompt_version": dp.PROMPT_VERSION, "dpi": sheet.dpi,
                 "tiles": len(sheet.tiles), "elapsed_s": elapsed,
                 "usage": {"in": getattr(usage, "prompt_tokens", None),
                           "out": getattr(usage, "completion_tokens", None)},
                 "answer": answer}, indent=1))
            oc = outcome_of(answer)
            totals[oc] += 1
            tok_in += getattr(usage, "prompt_tokens", 0) or 0
            tok_out += getattr(usage, "completion_tokens", 0) or 0
            store(conn, row, sheet, answer, paths, oc, usage, elapsed, model)
            conn.commit()
            print(f"[{i}/{len(rows)}] doc{row['document_id']} "
                  f"c{row['cohort']} {oc}: {len(answer.get('items') or [])} items, "
                  f"{answer.get('drawing_kind')}, {len(sheet.tiles)} tiles @ "
                  f"{sheet.dpi:.0f}dpi, {elapsed:.0f}s -- {row['title'][:48]}")
    print(f"\n{totals}  tokens in={tok_in:,} out={tok_out:,}")


REVIEW_COLUMNS = [
    "check", "cohort", "site", "application_ref", "document_title",
    "sheet_ref", "item_kind", "equipment", "quantity", "column_header",
    "transcribed_verbatim", "legibility", "model_says_location",
    "tile_position", "tile_image_path", "overview_image_path",
    "document_url", "document_id", "transcription_id",
]


def do_review_sheet(model: str, out: Path) -> None:
    """The hand check. One row per transcribed item, with its image."""
    sel = {r["document_id"]: r for r in load_selection()}
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT t.id, t.document_id, t.cohort, t.sheet_ref,
                   t.location_on_sheet, t.item_kind, t.value_text, t.equipment,
                   t.quantity, t.legibility, t.tile_position, t.tile_image_path,
                   t.column_header
              FROM drawing_transcriptions t
             WHERE t.model = %s AND t.prompt_version = %s
             ORDER BY t.cohort, t.document_id, t.tile_index, t.id""",
                    (model, dp.PROMPT_VERSION))
        rows = cur.fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        w.writeheader()
        for r in rows:
            s = sel.get(r[1], {})
            w.writerow({
                "check": "", "cohort": r[2], "site": s.get("site_name") or "",
                "application_ref": s.get("application_ref") or "",
                "document_title": s.get("title") or "",
                "sheet_ref": r[3] or "", "item_kind": r[5],
                "equipment": r[7] or "", "quantity": r[8] or "",
                "column_header": r[12] or "",
                "transcribed_verbatim": r[6], "legibility": r[9] or "",
                "model_says_location": r[4] or "", "tile_position": r[10] or "",
                "tile_image_path": r[11] or "",
                "overview_image_path": f"data/drawings_pilot/tiles/doc{r[1]}/overview.png",
                "document_url": s.get("url") or "", "document_id": r[1],
                "transcription_id": r[0]})
    print(f"{len(rows)} rows -> {out}")

    # The nulls, in their own sheet. A review that only lists the hits
    # cannot tell a reviewer what the pilot looked at and found nothing
    # in, and that number is the one that decides whether a scale-up is
    # worth running.
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT l.document_id, l.cohort, l.outcome, l.items_found,
                   l.render_dpi, l.tiles_sent, l.notes, l.input_tokens,
                   l.output_tokens, l.elapsed_s
              FROM drawing_transcription_log l
             WHERE l.model = %s AND l.prompt_version = %s
             ORDER BY l.cohort, l.outcome, l.document_id""",
                    (model, dp.PROMPT_VERSION))
        log = cur.fetchall()
    log_out = out.with_name(out.stem.replace("_review", "_log") + ".csv")
    cols = ["cohort", "outcome", "items_found", "application_ref", "site",
            "document_title", "drawing_kind", "sheet_ref", "sheet_summary",
            "render_dpi", "tiles_sent", "input_tokens", "output_tokens",
            "elapsed_s", "overview_image_path", "document_url", "document_id"]
    with log_out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in log:
            s = sel.get(r[0], {})
            notes = json.loads(r[6]) if r[6] else {}
            w.writerow({
                "cohort": r[1], "outcome": r[2], "items_found": r[3],
                "application_ref": s.get("application_ref") or "",
                "site": s.get("site_name") or "",
                "document_title": s.get("title") or "",
                "drawing_kind": notes.get("drawing_kind") or "",
                "sheet_ref": notes.get("sheet_ref") or "",
                "sheet_summary": notes.get("sheet_summary") or "",
                "render_dpi": r[4], "tiles_sent": r[5],
                "input_tokens": r[7], "output_tokens": r[8],
                "elapsed_s": r[9],
                "overview_image_path": f"data/drawings_pilot/tiles/doc{r[0]}/overview.png",
                "document_url": s.get("url") or "", "document_id": r[0]})
    print(f"{len(log)} documents -> {log_out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--sample", action="store_true",
                    help="ignore the cache; for honing the prompt")
    ap.add_argument("--review-sheet", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--doc", type=int, action="append")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--reasoning-effort", default="medium")
    ap.add_argument("--selection", type=Path,
                    default=PILOT_DIR / "selection.json",
                    help="Selection file to run (default the pilot's 28; "
                         "data/drawings_pilot/scale_selection.json for the "
                         "cohort-3 scale run).")
    ap.add_argument("--out", type=Path,
                    default=PILOT_DIR / f"{dp.PROMPT_VERSION}_review.csv")
    args = ap.parse_args()

    global SELECTION_PATH
    SELECTION_PATH = args.selection

    if args.run or args.sample:
        do_run(args.model, args.reasoning_effort, args.limit, args.doc,
               args.sample)
    if args.review_sheet:
        do_review_sheet(args.model, args.out)


if __name__ == "__main__":
    main()
