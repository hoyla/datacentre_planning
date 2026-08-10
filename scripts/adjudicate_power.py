"""Adjudicate which power figures actually describe each development.

The deep-read captured every power fact in every document. That was the
right instruction — but it means the corpus cannot answer the question the
reporting team most wants ("how big is this site?"), because planning
statements quote the market far more often than they quote themselves.
Measured on the Sonnet pass: of the twenty-two largest MW/GW findings in
the corpus, *all twenty-two* are market forecasts, policy targets or grid
statistics. Ranking sites by their largest figure would be nonsense.

This pass reads no documents. It takes the findings already extracted and
gate-verified, groups them by application, and asks a much narrower
question per application: of these candidate figures, which describe THIS
development, and which quantity does each measure? Reusing paid-for
extractions makes it a fraction of the bulk pass's cost, and every answer
still points back at a verbatim quote that survived the gate.

Four quantities are kept apart deliberately. IT load, grid connection
capacity, on-site generation and cooling capacity routinely differ by
more than a factor of two for the same site — a 100MW campus may hold
120MW of standby diesel behind a 150MW grid offer. Collapsing them into
"the site's MW" would replace one error with another.

Exclusions are recorded with a reason rather than dropped, so "why doesn't
this site show the 30GW figure in its documents?" resolves to a row.

Usage:
    scripts/adjudicate_power.py --measure    # token count + cost, spends nothing
    scripts/adjudicate_power.py --submit
    scripts/adjudicate_power.py --collect
    scripts/adjudicate_power.py --report     # per-site power profile
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402

MODEL = "claude-sonnet-5"
# power-1.0 is what the corpus was adjudicated under and must not change:
# it is half of the (finding_id, model, prompt_version) key, so editing it
# in place would leave two different prompts sharing one version and make
# the audit trail a lie.
#
# power-1.1 adds the quantity-kind rules below — the six families that
# reached readers on 2026-08-10 — so that errors are not created and then
# corrected by scripts/correct_adjudications.py, but mostly not created.
#
# It is NOT the default, because selecting it re-adjudicates the entire
# corpus: no figure carries a 1.1 verdict, so every one re-enters the
# cohort. That is roughly $20-40 of batch and a deliberate decision, not
# a side effect of an import. It is also UNVALIDATED: the 229-figure
# ground-truth set in the scratchpad is the way to check it improves the
# specific cases before spending that.
PROMPT_VERSION = "power-1.0"
PROMPT_VERSION_LATEST = "power-1.1"
STATE_PATH = ROOT / "data" / "power_adjudication_batch.json"

# Units that carry a real-power meaning we can normalise to MW. MVA and
# kVA are apparent power — related to MW only through a power factor we
# do not know — so they are recorded but never silently converted.
TO_MW = {
    "mw": 1.0, "megawatt": 1.0, "megawatts": 1.0, "mwe": 1.0,
    "kw": 0.001, "kilowatt": 0.001, "kilowatts": 0.001,
    "gw": 1000.0, "gigawatt": 1000.0, "gigawatts": 1000.0,
}
APPARENT = {"mva", "kva"}

PROMPT = """\
You are auditing extracted figures from UK planning documents for an
investigative journalism project on data centres.

Below are power-related figures extracted from the documents of ONE
planning application, each with the verbatim quote it came from.

Your task: decide which figures describe **the power capacity of the
development that this application is for**, and which do not.

This matters because planning statements argue for approval by citing
market demand, national policy and grid statistics. Those figures are
about the industry, not about this building. A figure is only
`site_capacity` if the quote shows it describes THIS development's own
plant, load, or connection.

For each figure, return:
  "finding_id":  the id given
  "verdict":     one of
                 "site_capacity"  - describes this development
                 "market_context" - market/sector demand or supply
                 "policy_target"  - national/regional policy ambition
                 "comparator"     - a different named site or scheme
                 "unclear"        - cannot tell from the quote alone
  "quantity_type": only when site_capacity, else null. One of:
                 "it_load"           - IT/rack load the facility draws
                 "grid_connection"   - contracted or sought grid capacity
                 "onsite_generation" - standby/backup/CHP/renewable plant
                 "cooling"           - cooling system capacity
                 "total_site"        - total site demand where the quote
                                       explicitly says total, not IT-only
                 "other"
  "is_maximum":  true if the quote presents it as an ultimate or consented
                 ceiling rather than one phase; false otherwise; null when
                 not site_capacity
  "reasoning":   one short sentence citing what in the quote decided it

Be strict. If the quote does not make clear that the figure belongs to
this development, use "unclear" rather than guessing. Under-claiming is
recoverable; a wrong site capacity in a published chart is not.

BEFORE deciding whose figure it is, decide whether it is a power
capacity at all. These were all mis-filed as site capacity in an earlier
run of this task, and each put a wrong number in front of a reader:

- **Energy is not power.** "251,859,057.50 kW which equates to
  94,197.29 kWh/m2" is a year's consumption, not a capacity; converted
  it implied a site four times the national grid. A figure whose
  magnitude is absurd for a building — anything above about 3,000 MW —
  is wrong whatever unit it carries. Verdict "unclear".
- **Storage is not generation, and not demand.** A battery or UPS rating
  says how fast it can discharge. Use quantity_type "other" and say so
  in the reasoning; never "onsite_generation".
- **Thermal input is not electrical output.** "a Thermal Input of around
  1.2GW" is fuel entering a plant, typically two to three times the
  electricity leaving it. Verdict "unclear" unless the quote gives an
  electrical figure.
- **A number in a table is not a capacity.** If the quote carries no
  unit at all — "80% - 480W", "Data Centre 150 210 1,839,600", a row of
  pounds sterling — nothing establishes it is megawatts. Verdict
  "unclear".
- **A substation on a drawing is not a grid connection.** "- 6MW
  Substation 25.4m²" is an equipment schedule; "TEMPORARY 1MW
  SUBSTATION" is a construction supply. A grid connection is capacity
  sought, reserved, contracted or offered.
- **A single unit is not the fleet.** "38 no. 2,640kW generator units"
  is about 100 MW of plant, not 2.6 MW. Where a quote gives both a count
  and a per-unit rating, the figure for this development is the product.
  Where it gives only one machine's spec, say so in the reasoning.

Return strict JSON: {"adjudications": [...]}. No prose outside the JSON.

APPLICATION: %(ref)s
DESCRIPTION: %(desc)s

FIGURES:
%(figures)s
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "adjudications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "integer"},
                    "verdict": {"type": "string", "enum": [
                        "site_capacity", "market_context", "policy_target",
                        "comparator", "unclear"]},
                    # A nullable enum must be expressed as anyOf: pairing
                    # "type": ["string","null"] with an enum containing
                    # null is rejected by the schema validator.
                    "quantity_type": {"anyOf": [
                        {"type": "string", "enum": [
                            "it_load", "grid_connection", "onsite_generation",
                            "cooling", "total_site", "other"]},
                        {"type": "null"}]},
                    "is_maximum": {"type": ["boolean", "null"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["finding_id", "verdict", "quantity_type",
                             "is_maximum", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["adjudications"],
    "additionalProperties": False,
}


def load_candidates(conn) -> dict[int, dict]:
    """Power-ish findings grouped by application, excluding any already
    adjudicated under this model+prompt_version."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT f.application_id, a.application_ref,
                   coalesce(a.description, ''), f.id, f.document_id,
                   f.signal_type, f.value_number, f.value_unit,
                   f.value_text, f.evidence_text
            FROM findings f
            JOIN applications a ON a.id = f.application_id
            WHERE f.value_number IS NOT NULL
              AND lower(f.value_unit) = ANY(%s)
              AND NOT EXISTS (
                    SELECT 1 FROM power_adjudication p
                    WHERE p.finding_id = f.id AND p.model = %s
                      AND p.prompt_version = %s)
            ORDER BY f.application_id, f.value_number DESC""",
            (list(TO_MW) + list(APPARENT), MODEL, PROMPT_VERSION))
        rows = cur.fetchall()

    apps: dict[int, dict] = {}
    for (app_id, ref, desc, fid, doc_id, stype, num, unit,
         vtext, evidence) in rows:
        app = apps.setdefault(app_id, {"application_id": app_id, "ref": ref,
                                       "desc": desc[:400], "figures": []})
        app["figures"].append({
            "finding_id": fid, "document_id": doc_id, "signal_type": stype,
            "value_number": float(num), "value_unit": unit,
            "value_text": vtext, "evidence_text": evidence,
        })
    return apps


def render_figures(figures: list[dict]) -> str:
    out = []
    for f in figures:
        quote = (f["evidence_text"] or "").replace("\n", " ")[:300]
        out.append(
            f'- finding_id {f["finding_id"]}: {f["value_number"]:g} '
            f'{f["value_unit"]} (label: {f["signal_type"]}; '
            f'value: {(f["value_text"] or "")[:80]})\n'
            f'  quote: "{quote}"')
    return "\n".join(out)


def build_requests(apps: dict[int, dict]) -> list[dict]:
    reqs = []
    for app_id, app in apps.items():
        # Cap per request: a handful of applications carry hundreds of
        # figures; split them so no single prompt gets unwieldy.
        figs = app["figures"]
        for i in range(0, len(figs), 60):
            chunk = figs[i:i + 60]
            content = PROMPT % {"ref": app["ref"], "desc": app["desc"],
                                "figures": render_figures(chunk)}
            reqs.append({
                "custom_id": f"{app_id}-{i // 60}",
                "params": {
                    "model": MODEL, "max_tokens": 8000,
                    "output_config": {"format": {"type": "json_schema",
                                                 "schema": SCHEMA}},
                    "messages": [{"role": "user", "content": content}],
                },
            })
    return reqs


def do_measure(submit: bool = False) -> None:
    with db.connect() as conn:
        apps = load_candidates(conn)
    reqs = build_requests(apps)
    n_figs = sum(len(a["figures"]) for a in apps.values())
    print(f"{len(apps)} applications, {n_figs} candidate figures, "
          f"{len(reqs)} requests")
    if not reqs:
        return

    # Measure real tokens rather than guessing from characters — the
    # bulk pass taught that lesson at a cost of $150.
    import anthropic
    client = anthropic.Anthropic()
    sample = reqs[:min(25, len(reqs))]
    counted = 0
    for r in sample:
        counted += client.messages.count_tokens(
            model=MODEL, messages=r["params"]["messages"]).input_tokens
    mean_in = counted / len(sample)
    total_in = mean_in * len(reqs)
    # Output is one small object per figure; measured shape ~60 tokens each.
    total_out = n_figs * 60
    cost = total_in / 1e6 * 1.0 + total_out / 1e6 * 5.0
    print(f"measured mean input: {mean_in:,.0f} tokens/request "
          f"(sampled {len(sample)})")
    print(f"projected: {total_in/1e6:.2f}M input + ~{total_out/1e6:.2f}M "
          f"output -> ${cost:,.2f} at Sonnet batch rates")
    if not submit:
        print("\n(measurement only — nothing spent; re-run with --submit)")
        return

    batch = client.messages.batches.create(requests=reqs)
    STATE_PATH.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "applications": {str(k): {"application_id": v["application_id"],
                                  "figures": v["figures"]}
                         for k, v in apps.items()},
    }, indent=1))
    print(f"submitted {batch.id} ({batch.processing_status})")


def do_collect() -> None:
    if not STATE_PATH.exists():
        print("no batch state — run --submit first")
        return
    state = json.loads(STATE_PATH.read_text())
    if state.get("collected"):
        print("already collected")
        return

    import anthropic
    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        c = batch.request_counts
        print(f"{state['batch_id']}: {batch.processing_status} "
              f"(succ {c.succeeded}, err {c.errored}, proc {c.processing})")
        return

    # finding_id -> its original metadata, for units and provenance.
    by_finding: dict[int, dict] = {}
    for app in state["applications"].values():
        for f in app["figures"]:
            by_finding[f["finding_id"]] = f

    inserted = skipped = 0
    with db.connect() as conn, conn.cursor() as cur:
        for result in client.messages.batches.results(state["batch_id"]):
            if result.result.type != "succeeded":
                continue
            msg = result.result.message
            if msg.stop_reason == "refusal":
                continue
            text = next((b.text for b in msg.content if b.type == "text"), "")
            try:
                adjs = json.loads(text).get("adjudications", [])
            except Exception:
                continue
            app_id = int(result.custom_id.rsplit("-", 1)[0])
            for a in adjs:
                fid = a.get("finding_id")
                meta = by_finding.get(fid)
                if meta is None:
                    skipped += 1
                    continue
                unit = (meta["value_unit"] or "").lower()
                value_mw = unit_note = None
                if a.get("verdict") == "site_capacity":
                    if unit in TO_MW:
                        value_mw = meta["value_number"] * TO_MW[unit]
                    elif unit in APPARENT:
                        unit_note = ("apparent power (kVA/MVA); not "
                                     "converted to MW — power factor unknown")
                cur.execute("""
                    INSERT INTO power_adjudication (application_id,
                        finding_id, document_id, verdict, quantity_type,
                        value_mw, value_original, unit_original, unit_note,
                        is_maximum, reasoning, model, prompt_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (finding_id, model, prompt_version)
                    DO NOTHING""",
                    (app_id, fid, meta["document_id"], a.get("verdict"),
                     a.get("quantity_type"), value_mw, meta["value_number"],
                     meta["value_unit"], unit_note, a.get("is_maximum"),
                     (a.get("reasoning") or "")[:600], MODEL,
                     PROMPT_VERSION))
                inserted += 1
        conn.commit()
    state["collected"] = True
    STATE_PATH.write_text(json.dumps(state, indent=1))
    print(f"inserted {inserted} adjudications"
          + (f" ({skipped} referenced unknown finding_ids)" if skipped else ""))


def do_report() -> None:
    """Per-site power profile, highest IT load first."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key, s.display_name, p.quantity_type,
                   max(p.value_mw) AS mw, count(*) AS n
            FROM power_adjudication p
            JOIN site_members sm ON sm.application_id = p.application_id
            JOIN sites s ON s.id = sm.site_id
            WHERE p.verdict = 'site_capacity' AND p.value_mw IS NOT NULL
              AND s.retired_at IS NULL
            GROUP BY s.site_key, s.display_name, p.quantity_type
            ORDER BY s.site_key, p.quantity_type""")
        rows = cur.fetchall()
    sites: dict[str, dict] = {}
    for site_key, name, qty, mw, n in rows:
        s = sites.setdefault(site_key, {"name": name})
        s[qty] = float(mw)
    order = sorted(sites.items(),
                   key=lambda kv: -(kv[1].get("it_load")
                                    or kv[1].get("total_site")
                                    or kv[1].get("grid_connection") or 0))
    print(f"{'site':38} {'IT load':>9} {'grid':>9} {'gen':>9}")
    for key, s in order[:40]:
        print(f"{(s['name'] or key)[:38]:38} "
              f"{s.get('it_load', float('nan')):9.1f} "
              f"{s.get('grid_connection', float('nan')):9.1f} "
              f"{s.get('onsite_generation', float('nan')):9.1f}")
    print(f"\n{len(sites)} sites with at least one adjudicated capacity")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.measure or args.submit:
        do_measure(submit=args.submit)
    elif args.collect:
        do_collect()
    elif args.report:
        do_report()
    else:
        print("pass --measure, --submit, --collect or --report")


if __name__ == "__main__":
    main()
