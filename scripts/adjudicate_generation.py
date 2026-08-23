#!/usr/bin/env python3
"""The two generation questions, and the sample that has to pass first.

READER_REDESIGN_PLAN §4.1e asks every adjudicated on-site generation
figure two things the original adjudication never asked: is this one
machine, the site's stated fleet of generators, or the site; and is the
plant standby
combustion, prime combustion, renewable or storage. The prompt lives in
scripts/adjudicate_power.py with the others, under its own prompt
version; this script is the route that runs it.

It does not run the full batch. 1,667 figures across 145 applications
and 72 sites is a few dollars and an hour of batch window, and it is not
the expensive part — the
expensive part is a wrong answer reaching a reader through a rollup, a
workbook column and, later, a cohort. So the order is the one the
dc_build sweep used: a sample, hand-checked by a person, scored, and
only then the batch.

    scripts/adjudicate_generation.py --sample     # the sheet, blank
    scripts/adjudicate_generation.py --run        # the model, same rows
    scripts/adjudicate_generation.py --score      # the two, compared

The sample is forty rows and is chosen, not sampled at random, because
the cases that matter are known by name (§4.1e and the review of
2026-08-23):

  Elsham Wolds   twenty gas engines that "operate continuously", a
                 49.9 MW consented cap, a 2,499 kW engine, a 5,678 kW
                 thermal INPUT that is not generation at all, and 650
                 back-up diesels in the same sentence as the gas
  Watford Bypass the per-unit case the panel got wrong: 3.2 MW above
                 "112 units"
  Amazon Didcot  a large fleet stated by count and rating
  Graven Hill    86.12 kW of rooftop PV — generation, but not plant
  Trident Way    219 kW of solar, the same trap in a second form
  the five other sites whose headline dcp.site_profile.generation_figure
                 labels per-unit, since a disagreement there is a
                 disagreement with something already shipping
  a dozen more   spread across the size range of the sites the same
                 function labels "as stated", because a prompt tested
                 only on the largest sites is tested on one end of the
                 corpus

Nothing here writes to the database. The generation verdicts get their
own table when the sample says the prompt is good enough to spend on,
and not before: a table whose vocabulary might still change is a table
that will be migrated twice.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from dcp import db, extract  # noqa: E402
from dcp.site_profile import generation_figure  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "adjudicate_power", ROOT / "scripts" / "adjudicate_power.py")
_ap = importlib.util.module_from_spec(_spec)
sys.modules["adjudicate_power"] = _ap
_spec.loader.exec_module(_ap)

PROMPT = _ap.GENERATION_PROMPT
SCHEMA = _ap.GENERATION_SCHEMA
PROMPT_VERSION = _ap.GENERATION_PROMPT_VERSION
CANDIDATES_SQL = _ap.GENERATION_CANDIDATES_SQL

OUT_DIR = ROOT / "data" / "generation_sample"
SAMPLE_SIZE = 40
# Reasoning tokens are output tokens. Elsham's fifty-eight figures with
# their passages overran 16,000 and the JSON came back cut off, twice;
# the chunk is now twenty figures and the ceiling 32,000.
MAX_COMPLETION_TOKENS = 32000
# The batch's chunk size, mirrored here so the sample measures the
# request the batch will actually send.
FIGURES_PER_REQUEST = 20

# The named cases, with how many rows each is worth and why. Order is the
# sheet's order, so the reasons a person is being asked about arrive
# grouped rather than interleaved.
NAMED_CASES: tuple[tuple[str, int, str], ...] = (
    ("PTNO-12849818", 6, "gas engines, a consented cap, an engine rating, "
                         "a thermal input, and 650 back-up diesels"),
    ("PTNO-12879308", 2, "the per-unit case the 2.2 panel got wrong"),
    ("PTNO-12549436", 4, "a large fleet stated by count and rating"),
    ("PTNO-12651066", 3, "rooftop PV, not plant"),
    ("PTNO-12842719", 3, "solar, the same trap in a second form"),
)

# The other five sites whose headline generation_figure calls per-unit.
# Named by site_key rather than found by the label, so that a change to
# generation_figure cannot silently change what the sample tests.
PER_UNIT_SITES: tuple[tuple[str, int, str], ...] = (
    ("PTNO-12645087", 2, "headline labelled per unit (Thorney)"),
    ("SITE-ChilternSouthBucks/PL/22/0728/EIASR", 2,
     "headline labelled per unit (Wexham Springs)"),
    ("PTNO-12839274", 2, "headline labelled per unit (Kao KLON-03)"),
    ("SITE-NorthAyrshire/26/00138/EIA", 2,
     "headline labelled per unit (Hunterston)"),
    ("SITE-Hillingdon/39707/APP/2022/3243", 2,
     "headline labelled per unit (Woodlands Park)"),
)

BASIS_VALUES = ("per_generator", "stated_group_total", "installation_total",
                "site_total", "not_generation", "unclear")
PLANT_VALUES = ("standby_combustion", "prime_combustion", "renewable",
                "storage", "mixed", "unclear")

SHEET_COLUMNS = ("row", "site_key", "site", "finding_id", "figure_mw",
                 "as_extracted", "signal_label", "why_in_sample", "quote",
                 "passage", "figure_basis", "plant_type", "unit_count",
                 "unit_rating_mw", "note")


# ---------------------------------------------------------------------------
# Choosing the forty
# ---------------------------------------------------------------------------

def load_candidates(conn) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Every adjudicated on-site generation figure, grouped by site."""
    by_site: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}
    with conn.cursor() as cur:
        cur.execute(CANDIDATES_SQL)
        for (site_key, name, app_id, ref, desc, fid, doc_id, stype,
             value_mw, number, unit, vtext, quote, page, sha) in cur.fetchall():
            names[site_key] = name or site_key
            by_site[site_key].append({
                "site_key": site_key, "site": name or site_key,
                "application_id": app_id, "application_ref": ref,
                "description": desc[:400], "finding_id": fid,
                "document_id": doc_id, "signal_type": stype,
                "value_mw": float(value_mw), "value_number": float(number),
                "value_unit": unit, "value_text": vtext,
                "evidence_text": quote, "evidence_page": page,
                "passage": _passage(ref, sha, page, quote),
            })
    return by_site, names


_page_cache: dict[tuple[str, str], list[str]] = {}


def _passage(ref: str, sha: str | None, page: int | None, quote: str) -> str:
    """The quote with its page around it, from the text cache; the quote
    alone where the page is not held. The gate verified every quote
    against this same cache, so a quote with no page here is rare."""
    if not sha or not page:
        return ""
    key = (ref, sha)
    if key not in _page_cache:
        path = extract.cache_path_for("documents", ref, sha)
        try:
            _page_cache[key] = [p or "" for p in
                                (json.loads(path.read_text()).get("pages") or [])]
        except Exception:
            _page_cache[key] = []
    pages = _page_cache[key]
    text = pages[page - 1] if 0 < page <= len(pages) else ""
    out = _ap.passage_for(quote, text)
    return out if out != " ".join((quote or "").split()) else ""


def _select_rows(rows: list[dict], limit: int) -> list[dict]:
    """Up to `limit` of a site's rows, spread across its figures.

    Two things would otherwise waste the quota. Elsham Wolds carries
    fifty-eight generation figures and eleven of them quote "The plans
    contain an energy centre with the capacity to generate 49.9 MW
    on-site" — asking a person the same question eleven times measures
    nothing, so a passage appears once. And twenty-one of them are the
    50 MW: taken largest first, six rows of Elsham would be six ways of
    saying 50 and none of them the 49.9 MW consented cap, the 2,499 kW
    engine or the 5,678 kW thermal input, which are the rows the sample
    exists to ask about.

    So: distinct passages, grouped by the figure they state, taken one
    figure at a time from largest down and round again. Ties break on
    finding_id, so the selection is stable while the corpus is.

    "Distinct" is per passage AND figure, not per passage. One sentence
    can carry several figures and the question is different for each:
    "Each engine has an energy input of 5,678 kW, capable of delivering
    2,499 kW electrical power, resulting in a total site capacity of
    just below 50 MWe" is a thermal input, a per-unit electrical rating
    and a site total, and dropping two of the three because the words
    repeat would drop the two hardest.
    """
    seen: set[tuple[float, str]] = set()
    by_figure: dict[float, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: (-r["value_mw"], r["finding_id"])):
        key = (r["value_mw"],
               " ".join((r["evidence_text"] or "").split()).lower())
        if key in seen:
            continue
        seen.add(key)
        by_figure[r["value_mw"]].append(r)

    out: list[dict] = []
    levels = [by_figure[v] for v in sorted(by_figure, reverse=True)]
    for depth in range(max((len(l) for l in levels), default=0)):
        for level in levels:
            if depth < len(level):
                out.append(level[depth])
                if len(out) >= limit:
                    return out
    return out


def _spread(items: list, n: int) -> list:
    """`n` items spread evenly across `items`, ends included.

    A dozen "as stated" sites taken off the top of the ranking would all
    be campuses of a hundred megawatts and more; the corpus's median
    generation figure is a fraction of that, and a prompt that reads
    large fleets well can still read a single 400 kW standby set wrong.
    """
    if n <= 0 or not items:
        return []
    if n >= len(items):
        return list(items)
    if n == 1:
        return [items[0]]
    step = (len(items) - 1) / (n - 1)
    return [items[round(i * step)] for i in range(n)]


def choose_sample(by_site: dict[str, list[dict]]) -> list[dict]:
    """The forty rows, in sheet order. Deterministic given the corpus."""
    chosen: list[dict] = []
    used: set[str] = set()

    for site_key, quota, why in NAMED_CASES + PER_UNIT_SITES:
        used.add(site_key)
        for row in _select_rows(by_site.get(site_key, []), quota):
            chosen.append({**row, "why_in_sample": why})

    # The remainder: sites whose headline generation_figure calls "as
    # stated", one row each — the row that carries the headline, since
    # that is the row a reader sees.
    as_stated: list[tuple[float, str]] = []
    for site_key, rows in by_site.items():
        if site_key in used:
            continue
        g = generation_figure([(r["value_mw"], r["evidence_text"])
                               for r in rows])
        if g.basis == "as stated" and g.value_mw:
            as_stated.append((float(g.value_mw), site_key))
    ranked = [k for _, k in sorted(as_stated, key=lambda t: (-t[0], t[1]))]

    for site_key in _spread(ranked, SAMPLE_SIZE - len(chosen)):
        row = _select_rows(by_site[site_key], 1)[0]
        chosen.append({**row, "why_in_sample": "headline as stated"})
    return chosen


# ---------------------------------------------------------------------------
# The sheet
# ---------------------------------------------------------------------------

HOW_TO_READ = """\
# Generation sample — {n} rows to hand-check

Prompt version `{version}`. Every row below is a figure the pipeline
already treats as **this site's own on-site electricity generation**;
that question is settled and is not what is being asked.

Each row gives the quote the figure was extracted from AND the passage
around it on the same page — the paragraph before and after — which is
what the model is given too. The earlier version of this sheet gave the
quote alone, and most rows were, correctly, unanswerable from it.

Two questions per row, from the passage. **Where the passage does not
settle a question, `unclear` is the right answer** — for you and for
the model. Fill the two columns in `{csv}` — one value from each list,
exactly as written:

**figure_basis** — what is this figure a figure of?

- `per_generator` — the rating of one generating machine (an engine, a
  turbine, a generator set). Not a building called a "unit".
- `stated_group_total` — the combined rating of a stated number of
  machines ("20 no. 2,499 kW engines with a combined capacity of just
  under 50 MW"). The group may or may not be all the site's generation;
  that is not this question.
- `installation_total` — the rated total of one named installation or
  kind of plant, with no count of machines and no statement that it is
  the whole site's generation ("219kW of PV panels", "an energy centre
  with the capacity to generate 49.9 MW"). A solar array does not
  preclude a diesel fleet.
- `site_total` — the whole development's total generating capacity, all
  plant — only where the passage says so. A total for one building, one
  phase or one kind of plant is not the site's.
- `not_generation` — not an electrical generating capacity at all: a
  thermal or fuel input, an annual energy figure, a battery rating, a
  demand figure
- `unclear` — the passage does not settle it

**plant_type** — what kind of plant?

- `standby_combustion` — runs on grid failure and for testing
- `prime_combustion` — supplies the site's normal load or exports: CHP,
  an energy centre, gas engines running continuously, energy-from-waste
- `renewable` — solar, wind, hydro
- `storage` — battery, UPS, flywheel
- `mixed` — one figure covering more than one of these
- `unclear` — the passage does not say

Also, where and only where the passage states them: `unit_count` (how
many machines) and `unit_rating_mw` (one machine's rating, in MW). Never
multiply them. `note` is free text and is read, not scored.

The model has answered the same rows separately. Its answers are not in
this sheet on purpose — a sheet that showed them would measure
agreement with the model rather than the documents.

---

"""


def write_sheet(rows: list[dict], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{PROMPT_VERSION}_sheet.csv"
    md_path = out_dir / f"{PROMPT_VERSION}_sheet.md"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({
                "row": i, "site_key": r["site_key"], "site": r["site"],
                "finding_id": r["finding_id"],
                "figure_mw": f'{r["value_mw"]:g}',
                "as_extracted": f'{r["value_number"]:g} {r["value_unit"]}',
                "signal_label": r["signal_type"],
                "why_in_sample": r["why_in_sample"],
                "quote": " ".join((r["evidence_text"] or "").split()),
                "passage": r.get("passage") or "(page not held; quote only)",
                "figure_basis": "", "plant_type": "", "unit_count": "",
                "unit_rating_mw": "", "note": "",
            })

    lines = [HOW_TO_READ.format(n=len(rows), version=PROMPT_VERSION,
                                csv=csv_path.name)]
    for i, r in enumerate(rows, 1):
        quote = " ".join((r["evidence_text"] or "").split())
        passage = r.get("passage") or ""
        lines.append(
            f'**{i}. {r["site"]}** — {r["value_mw"]:g} MW '
            f'(as extracted: {r["value_number"]:g} {r["value_unit"]}; '
            f'label `{r["signal_type"]}`; finding {r["finding_id"]}; '
            f'{r["why_in_sample"]})\n\n> **Quote:** {quote}\n'
            + (f'>\n> **Passage:** {passage}\n' if passage else
               '>\n> *(the page is not held; the quote is all there is)*\n'))
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path, md_path


# ---------------------------------------------------------------------------
# The model, over the same rows
# ---------------------------------------------------------------------------

def _client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set (add it to .env)")
    return OpenAI()


def run_model(rows: list[dict], all_rows: list[dict], model: str,
              effort: str) -> dict:
    """The sampled rows, asked the way the batch will ask them.

    A request carries one application's generation figures, and the
    batch will carry all of them — which is how the model gets to see
    that "26 generator systems each system providing 104 megawatts" and
    "26 4 MW generators" are the same twenty-six machines. Sending only
    the sampled row would measure a harder question than the one that
    will actually be asked, and would flatter or damn the prompt for the
    wrong reason. So the whole application goes in, chunked at the
    batch's size, and only the chunks holding a sampled figure are sent.

    Synchronous rather than batched: forty rows is a couple of dozen
    requests, and the batch API's twenty-four-hour window would put a
    day between a prompt edit and knowing whether it helped.
    """
    client = _client()
    wanted = {r["finding_id"] for r in rows}
    by_app: dict[int, list[dict]] = defaultdict(list)
    for r in all_rows:
        by_app[r["application_id"]].append(r)

    chunks: list[list[dict]] = []
    for app_id in sorted({r["application_id"] for r in rows}):
        figs = sorted(by_app[app_id],
                      key=lambda r: (-r["value_mw"], r["finding_id"]))
        for i in range(0, len(figs), FIGURES_PER_REQUEST):
            chunk = figs[i:i + FIGURES_PER_REQUEST]
            if any(f["finding_id"] in wanted for f in chunk):
                chunks.append(chunk)

    answers: dict[str, dict] = {}
    failures: list[dict] = []
    for chunk in chunks:
        app_id = chunk[0]["application_id"]
        content = PROMPT % {
            "ref": chunk[0]["application_ref"],
            "desc": chunk[0]["description"],
            "figures": _ap.render_generation_figures(chunk)}
        resp = client.chat.completions.create(
            model=model, max_completion_tokens=MAX_COMPLETION_TOKENS,
            reasoning_effort=effort,
            response_format={"type": "json_schema", "json_schema": {
                "name": "generation_adjudication", "strict": True,
                "schema": SCHEMA}},
            messages=[{"role": "user", "content": content}])
        text = resp.choices[0].message.content or ""
        finish = resp.choices[0].finish_reason
        try:
            parsed = json.loads(text).get("generation", [])
        except json.JSONDecodeError:
            failures.append({"application_id": app_id,
                             "reason": f"response was not JSON "
                                       f"(finish_reason={finish})"})
            continue
        # The span is asked for from the passage, and checked against it.
        quotes = {r["finding_id"]: (r.get("passage") or r["evidence_text"])
                  for r in chunk}
        for a in parsed:
            fid = a.get("finding_id")
            if fid not in quotes:
                failures.append({"application_id": app_id,
                                 "finding_id": fid,
                                 "reason": "answer names a figure "
                                           "that was not asked about"})
                continue
            if fid not in wanted:
                # Asked so the model could read it as context; not part
                # of what a person is being asked to check.
                continue
            a["span_verified"] = _ap.verify_span(
                a.get("evidence_span", ""), quotes[fid])
            answers[str(fid)] = a
        kept = sum(1 for a in parsed if a.get("finding_id") in wanted)
        print(f"  application {app_id}: {len(parsed)} answers, "
              f"{kept} in the sample")
    return {"prompt_version": PROMPT_VERSION, "model": model,
            "reasoning_effort": effort, "answers": answers,
            "failures": failures}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score(rows: list[dict], hand: dict[str, dict],
          model_run: dict) -> list[str]:
    """Agreement, per question and per row, printed as lines.

    Rows the person left blank are reported as unchecked rather than
    scored: a blank is not a verdict, and counting it as one would make
    an unfinished sheet look like agreement.
    """
    answers = model_run.get("answers", {})
    out, basis_hit, plant_hit, checked, unverified = [], 0, 0, 0, 0
    disagreements: list[str] = []

    for i, r in enumerate(rows, 1):
        fid = str(r["finding_id"])
        h, m = hand.get(fid), answers.get(fid)
        if m and not m.get("span_verified"):
            unverified += 1
        if not h or not h.get("figure_basis"):
            continue
        checked += 1
        if not m:
            disagreements.append(f"  {i:>2}. {r['site'][:34]:34} "
                                 f"finding {fid}: no model answer")
            continue
        b_ok = h["figure_basis"] == m.get("figure_basis")
        p_ok = (h.get("plant_type") or "") == m.get("plant_type")
        basis_hit += b_ok
        plant_hit += p_ok
        if not (b_ok and p_ok):
            parts = []
            if not b_ok:
                parts.append(f"basis {m.get('figure_basis')} "
                             f"vs {h['figure_basis']}")
            if not p_ok:
                parts.append(f"plant {m.get('plant_type')} "
                             f"vs {h.get('plant_type')}")
            disagreements.append(
                f"  {i:>2}. {r['site'][:34]:34} finding {fid}: "
                + "; ".join(parts)
                + f"\n      model: {m.get('reasoning', '')[:150]}")

    out.append(f"{checked} of {len(rows)} rows hand-checked")
    if checked:
        out.append(f"  figure_basis  {basis_hit}/{checked} "
                   f"({basis_hit / checked:.0%})")
        out.append(f"  plant_type    {plant_hit}/{checked} "
                   f"({plant_hit / checked:.0%})")
    out.append(f"  spans that did not verify against their quote: "
               f"{unverified}")
    if disagreements:
        out.append("\nwhere they differ:")
        out.extend(disagreements)
    for f in model_run.get("failures", []):
        out.append(f"  request failure: {f}")
    return out


def read_hand_sheet(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    hand: dict[str, dict] = {}
    for r in rows:
        fid = (r.get("finding_id") or "").strip()
        basis = (r.get("figure_basis") or "").strip()
        plant = (r.get("plant_type") or "").strip()
        if basis and basis not in BASIS_VALUES:
            sys.exit(f"row {r.get('row')}: figure_basis {basis!r} is not "
                     f"one of {', '.join(BASIS_VALUES)}")
        if plant and plant not in PLANT_VALUES:
            sys.exit(f"row {r.get('row')}: plant_type {plant!r} is not "
                     f"one of {', '.join(PLANT_VALUES)}")
        if fid:
            hand[fid] = {"figure_basis": basis, "plant_type": plant,
                         "note": (r.get("note") or "").strip()}
    return hand


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sample", action="store_true",
                    help="write the blank sheet")
    ap.add_argument("--run", action="store_true",
                    help="answer the same rows with the model")
    ap.add_argument("--score", action="store_true",
                    help="compare a filled sheet with the model's answers")
    ap.add_argument("--hand", type=Path,
                    help="the filled sheet (default: <version>_hand.csv)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--reasoning-effort", default="medium",
                    choices=["minimal", "low", "medium", "high"])
    args = ap.parse_args()
    if not (args.sample or args.run or args.score):
        ap.error("pass --sample, --run or --score")

    with db.connect() as conn:
        by_site, _ = load_candidates(conn)
    rows = choose_sample(by_site)
    all_rows = [r for v in by_site.values() for r in v]
    print(f"{sum(len(v) for v in by_site.values()):,} adjudicated "
          f"generation figures across {len(by_site)} sites; "
          f"sample is {len(rows)} rows")

    run_path = args.out_dir / f"{PROMPT_VERSION}_model.json"
    if args.sample:
        csv_path, md_path = write_sheet(rows, args.out_dir)
        print(f"wrote {csv_path}\n      {md_path}")
    if args.run:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        run = run_model(rows, all_rows, args.model, args.reasoning_effort)
        run_path.write_text(json.dumps(run, indent=1), encoding="utf-8")
        bad = sum(1 for a in run["answers"].values()
                  if not a["span_verified"])
        print(f"wrote {run_path}: {len(run['answers'])} answers, "
              f"{bad} spans unverified, {len(run['failures'])} failures")
    if args.score:
        hand_path = args.hand or (args.out_dir /
                                  f"{PROMPT_VERSION}_hand.csv")
        if not hand_path.exists():
            sys.exit(f"no filled sheet at {hand_path}")
        if not run_path.exists():
            sys.exit(f"no model answers at {run_path} — run --run first")
        print("\n".join(score(rows, read_hand_sheet(hand_path),
                              json.loads(run_path.read_text()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
