#!/usr/bin/env python3
"""Choose the 20-30 drawings the vision pilot looks at, and say why.

The deep read skips drawings by design (dcp/deepread_select.py, reduction
1): a location plan carries no extractable prose, and 23% of the corpus
goes unread on that rule. The rule is right about location plans and
wrong about a class it cannot distinguish from them -- an electrical
single-line diagram, a generator schedule, a transformer arrangement.
Those are drawings whose annotations are the engineering figures the
prose never states.

ROADMAP parks a "Multimodal pass over drawings" and rejects the blanket
version on two conditions: PDFs are overwhelmingly text-layered, and
concealed plant will not be in the drawings. It reopens "for a specific
application where both conditions fail". This selects those applications
rather than assuming them.

Two cohorts, and the weighting between them is deliberate.

**Cohort 1 -- follow-on plant applications with no MW anywhere.** The
accretion pattern in ROADMAP item 4 and docs/EXTERNAL_DATA_SOURCES.md
§5: generator capacity does not arrive once in the main consent, it
accumulates through minor separately-referenced applications, none of
which states a figure. An application whose description is *about* plant
and whose entire finding set holds no MW, kW, MVA or kVA is exactly the
case where the prose demonstrably fails to carry the figure.

**Cohort 2 -- electrical drawings at sites with no disclosed capacity.**
These are the sites whose published number is `Estimated from floorspace`
at 1.71 kW/m2 (dcp/site_scale.py) -- an inference with a factor-of-two
caveat. A transformer rating read off a substation drawing would convert
one of those into a sourced figure.

Selection is by title, which is the only description of a drawing's
content the corpus holds: `documents` has a coarse `kind` ("Drawing",
"Plans") and no title column, so the title is the portal's own filename
from `document_listing_audit.offered` where that application was
audited, and the Idox URL slug otherwise. 44,902 of 55,687 documents
carry one.

**Cohort 3 -- the targeted scale-up.** Added 2026-08-26, after the
pilot. The two cohorts above pick documents by the *application* they
belong to; the pilot's own result was that what predicts a hit is the
*sheet*, not the application. A manufacturer's generator specification
yielded eight items and a transformer detail thirty-five, while four
energy-centre floor plans between them yielded one. So cohort 3 drops
the application-level gates and keeps the title gates: every unread
graphical document in the corpus whose title names plant, minus the
sheet kinds the pilot demonstrated are empty. It is not a wider net --
the subject gate and the veto are unchanged -- it is the same net cast
over the whole corpus instead of two application sets.

    scripts/drawings_pilot_select.py --report      # both cohorts, full
    scripts/drawings_pilot_select.py --select      # the capped pilot set
    scripts/drawings_pilot_select.py --scale       # the cohort-3 scale run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from dcp import db

OUT_DIR = ROOT / "data" / "drawings_pilot"

# The pilot's size. Luke approved 20-30 documents, weighted to cohort 1.
CAP_TOTAL = 28
CAP_COHORT_1 = 18
CAP_COHORT_2 = 10

# What the sheet has to be *of*. This is a gate, not a score: a title
# that names no plant is not a candidate however promising its document
# type sounds. The first cut of this file scored on the document type
# alone and the top of cohort 2 came back "Door entry schematic",
# "Window & Door Schedule Level 0" and "PROPOSED PARKING SCHEDULE" --
# all three genuinely schematics and schedules, none of them carrying a
# rating in any unit. `schematic` describes how a sheet is drawn and
# says nothing about what is on it.
SUBJECT_SCORES: tuple[tuple[int, str], ...] = (
    (9, r"switch ?room|switch ?gear|\bHV\b|\bLV\b|\d{2,3} ?kv\b|"
        r"\bMVA\b|\bkVA\b"),
    (8, r"transformer|substation|\bDNO\b|\bIDNO\b|\bUKPN\b|\bSSE\b"),
    (8, r"generator|gen ?set|\bCHP\b|\bUPS\b"),
    (7, r"energy cent(re|er)|plant ?room|power (distribution|supply|plant)"),
    (6, r"electrical|\bM ?& ?E\b|mechanical (and|&) electrical|"
        r"site services|external services|utilit(y|ies)"),
    (5, r"chiller|cooling|air ?con|condens(er|ing)|\bAHU\b|dry ?cooler"),
    (5, r"fuel (tank|storage|store)|oil tank|diesel|bulk storage|bund"),
)

# How the sheet is drawn. A booster on top of a subject match, because
# a single-line diagram of a substation is worth more of the pilot's
# budget than an elevation of the same substation -- the diagram is
# where ratings are annotated and the elevation is where the cladding is.
FORM_BONUS: tuple[tuple[int, str], ...] = (
    (6, r"single[- ]?line|one[- ]?line|\bSLD\b|schematic|diagram"),
    (4, r"schedule|specification|\bspec\b|data ?sheet|\bdetails?\b"),
    (2, r"layout|general arrangement|\bGA\b|floor plan"),
)

# Titles that match the vocabulary above but are certainly not carrying
# an electrical rating. Excluded explicitly rather than by scoring, so
# the exclusion is visible in the report instead of silent.
TITLE_VETO = re.compile(
    r"planting|tree |shrub|landscap|manhole|drainage|foul |surface water|"
    r"soft ?works|hard ?works|verified view|photomontage|photograph|"
    r"visualis|street ?scene|location plan|site location|red ?line|"
    r"boundary|topograph|land ?scape|ecolog|habitat|arboricultur|"
    r"furniture|accommodation schedule|area schedule|parking|"
    r"materials? (and|&) |schedule of materials|refuse|bin store|cycle|"
    r"window|door |luminaire|luminarie|lighting column|obstruction|"
    r"below ground|acoustic (fence|barrier)|screen elevation|"
    r"fencing|signage|wayfinding",
    re.IGNORECASE)

# The plant vocabulary an application description has to be *about*.
# `signals.py` is not reused here: it is tuned to find any mention
# anywhere in a document, and this needs the much narrower question of
# whether the proposal itself is a piece of plant.
PLANT_DESCRIPTION = (
    r"(generator|gen[- ]?set|energy centre|sub[- ]?station|switch ?room|"
    r"switchgear|transformer|chp|combined heat and power|standby power|"
    r"backup power|plant room)")

# Above this the description is a full scheme description, not a minor
# follow-on consent. 672 Galvin Road's is 150 characters; Hemel's is 52.
MAX_FOLLOW_ON_DESCRIPTION = 400

# Only documents the deep read never read. That is the pilot's whole
# premise, so it is a filter and not a preference: a document with a
# `deepread_log` row has already been through the extractor and its
# silence is a result, not a gap. Skipped drawings do not log -- only
# four rows in the whole table say `skipped_graphical` -- so absence
# from the log is what "unread" means here.
DOC_TITLES_SQL = """
create temporary table doc_titles as
select d.id            as document_id,
       d.application_id,
       d.kind,
       d.url,
       d.bytes_path,
       d.page_count,
       coalesce(nullif(o.filename, ''),
                regexp_replace(
                  regexp_replace(split_part(d.url, '/pdf/', 2), '\\.pdf$', '', 'i'),
                  '[_+]', ' ', 'g')) as title
from documents d
left join lateral (
  select e->>'filename' as filename
  from document_listing_audit a, jsonb_array_elements(a.offered) e
  where a.application_id = d.application_id and e->>'url' = d.url
  limit 1
) o on true
where d.bytes_path is not null
  and d.bytes_path ilike '%.pdf'
  and not exists (select 1 from deepread_log l where l.document_id = d.id);
"""

# Any figure at all, in any unit that could be a power rating, anywhere
# in the application's findings -- plus the adjudicated site capacities.
# An application in cohort 1 has to fail all of it.
HAS_POWER_SQL = """
select application_id from power_adjudication
 where verdict = 'site_capacity' and value_mw is not null
union
select application_id from findings
 where value_number is not null
   and value_unit ~* '^(MW|kW|MVA|kVA|MWe|MWth|kWp|MWp)$'
"""


def title_score(title: str) -> tuple[int, int, str]:
    """`(total, subject score, which rules fired)` for one title.

    Subject first and mandatory; form is a bonus on top of it. The
    subject score is returned separately because cohort 2 is defined as
    *electrical* drawings and needs to gate on it: a chiller schedule
    scores the same total as a switchroom layout and belongs in the
    other cohort.
    """
    if not title:
        return 0, 0, ""
    if TITLE_VETO.search(title):
        return 0, 0, "vetoed"
    subject = next(((s, p) for s, p in SUBJECT_SCORES
                    if re.search(p, title, re.IGNORECASE)), None)
    if subject is None:
        return 0, 0, "no subject"
    form = next(((s, p) for s, p in FORM_BONUS
                 if re.search(p, title, re.IGNORECASE)), (0, ""))
    return (subject[0] + form[0], subject[0],
            f"subject:{subject[1][:24]} form:{form[1][:24]}")


# --- cohort 3: what the pilot actually learned ----------------------------
#
# Every rule below is a count off data/drawings_pilot/drawings-pilot-1.0_log.csv
# (28 documents, 15 hits, 13 nulls), not a guess about what drawings
# contain. They are applied AFTER the subject gate and the veto, so they
# narrow an already-gated pool rather than widening it.

# Sheet kinds that paid. A manufacturer's specification sheet or general
# arrangement is a datasheet with a drawing border: the ratings are the
# point of the sheet. A DNO's engineering drawing is the same thing from
# the network side. A services layout carries the plant it serves,
# labelled, because the contractor has to install it.
SEND_PRIOR: tuple[tuple[str, str], ...] = (
    ("manufacturer_spec",
     r"specification|\bspec\b|data ?sheet|technical (data|details?)|"
     r"schedule of (plant|equipment|generators?|transformers?)|"
     r"(plant|equipment|generator|transformer|chiller) schedule"),
    ("general_arrangement",
     r"general arrangement|\bGA\b(?! ?[-–] ?elev)|\bdetails?\b"),
    ("dno_utility",
     r"\bDNO\b|\bIDNO\b|\bUKPN\b|\bWPD\b|\bSSE(N|PD)?\b|\bNGED\b|"
     r"\bSPEN?\b|\bENW\b|\bNPG\b|\bNorthern Power ?grid\b|"
     r"\b\d{2,3} ?kV\b|point of connection|\bPOC\b"),
    # "GROUND FLOOR MECH SERVICES PLANT ROOM LAYOUT" is the reason the
    # first two alternatives are loose about what sits between the
    # keyword and "layout": it hit in the pilot, and a stricter pattern
    # sent it to the architects'-floor-plan skip on the words "GROUND
    # FLOOR". A services layout is a services layout wherever in the
    # building it is drawn.
    ("services_layout",
     r"(electrical|mech(anical)?|\bM ?& ?E\b|services?)[^|]{0,40}layout|"
     r"plant ?room[^|]{0,20}layout|"
     r"external services|site services|services distribution"),
    ("single_line",
     r"single[- ]?line|one[- ]?line|\bSLD\b|schematic|wiring diagram"),
)

# Sheet kinds that did not. Four energy-centre floor plans between them
# produced one item; "Plan and Elevations of Customer Switchgear
# Building" and "Plan and Elevations - Low Voltage (LV) Cabinet"
# produced nothing at all. An architect's floor plan shows where the
# room is, and an elevation shows what its outside looks like; neither
# is where an engineer writes a rating.
#
# `PLAN_AND_ELEVATIONS` is separated out because it beats the send
# priors: those two sheets are nominally general arrangements, and were
# still empty. The rest yield to a send prior -- "GENERATOR GA PLAN AND
# ELEVATIONS" is a manufacturer's arrangement that happens to include an
# elevation, and is not the same document as "South Elevation".
PLAN_AND_ELEVATIONS = re.compile(
    r"plan (and|&|/) elevations? (of|-|–|for)", re.IGNORECASE)
SKIP_PRIOR: tuple[tuple[str, str], ...] = (
    ("architects_floor_plan",
     r"floor ?plan|ground floor|first floor|second floor|basement plan|"
     r"roof plan|level \d+ plan|\bplan level\b"),
    ("elevation_or_section",
     r"elevations?|\bsections?\b|\bcladding\b|\bfacade\b|\bfaçade\b"),
)


def prior_for(title: str) -> tuple[str, str]:
    """`(verdict, reason)` for one already-gated title.

    Order matters and is evidential: the Plan-and-Elevations pattern
    beats everything because the pilot sent two of them as general
    arrangements and got nothing; a send prior beats the generic
    elevation skip because a manufacturer's arrangement sheet that
    includes an elevation is still a manufacturer's arrangement sheet.
    """
    if PLAN_AND_ELEVATIONS.search(title):
        return "skip", "plan_and_elevations_of_building"
    for name, pat in SEND_PRIOR:
        if re.search(pat, title, re.IGNORECASE):
            return "send", name
    for name, pat in SKIP_PRIOR:
        if re.search(pat, title, re.IGNORECASE):
            return "skip", name
    # Neither prior fires: the title named plant, passed the veto and is
    # graphical, and nothing the pilot saw says it is empty. Send it.
    # The pilot's own biggest hit ("02 - TRANSFORMER DETAIL", 35 items)
    # is the argument against treating an unclassified sheet as a null.
    return "send", "no_prior_fired"


# Cohort 2's subject floor. 6 and above is the electrical vocabulary:
# switchgear, transformers, substations, generators, energy centres,
# power distribution, M&E. Below it are cooling and fuel, which are
# plant but not the thing a transformer rating is read off.
COHORT_2_SUBJECT_FLOOR = 6


def is_graphical(kind: str | None, title: str) -> bool:
    """Would `deepread_select` have called this a drawing?

    Asked of the title as well as the `kind`, because the corpus's kinds
    are coarse -- "Drawing", "Plans", "Other", "Supporting Documents" --
    and a sheet filed as "Other" whose title is "PROPOSED SUBSTATION
    COMPOUND PLAN AND ELEVATION" is a drawing whatever the portal called
    it. The `kind` alone would drop most of the electrical sheets in the
    corpus, because councils file them under whatever bucket the
    submission used.
    """
    from dcp.deepread_select import DRAWING_KINDS, LEGAL_INSTRUMENT_KINDS
    for text in (kind or "", title or ""):
        if LEGAL_INSTRUMENT_KINDS.search(text):
            return False
    if DRAWING_KINDS.search(kind or ""):
        return True
    return bool(re.search(
        r"\b(plan|elevation|section|layout|drawing|arrangement|schematic|"
        r"diagram|detail)s?\b", title or "", re.IGNORECASE))


def cohort_one(conn) -> list[dict]:
    """Follow-on plant applications whose prose yields no figure."""
    with conn.cursor() as cur:
        cur.execute(f"""
            with plant as (
              select a.id, a.application_ref, a.description, a.council_gss,
                     a.date_received, a.url
              from applications a
              where a.description ~* '{PLANT_DESCRIPTION}'
                and length(coalesce(a.description, '')) < {MAX_FOLLOW_ON_DESCRIPTION}
            ),
            haspower as ({HAS_POWER_SQL})
            select p.id, p.application_ref, p.description, p.date_received, p.url,
                   (select string_agg(distinct s.display_name, ' | ')
                      from site_members m join sites s on s.id = m.site_id
                     where m.application_id = p.id and m.retired_at is null
                       and s.retired_at is null) as site_name,
                   (select min(s.id)
                      from site_members m join sites s on s.id = m.site_id
                     where m.application_id = p.id and m.retired_at is null
                       and s.retired_at is null) as site_id
              from plant p
             where p.id not in (select application_id from haspower
                                 where application_id is not null)
             order by p.date_received desc nulls last""")
        return [dict(zip([c[0] for c in cur.description], r))
                for r in cur.fetchall()]


def cohort_two_sites(conn) -> list[dict]:
    """Live sites with no adjudicated capacity of any basis."""
    with conn.cursor() as cur:
        cur.execute("""
            with disclosed as (
              select sm.site_id
                from power_adjudication pa
                join site_members sm on sm.application_id = pa.application_id
                                    and sm.retired_at is null
               where pa.verdict = 'site_capacity' and pa.value_mw is not null
                 and pa.quantity_type in ('it_load', 'total_site',
                                          'grid_connection', 'onsite_generation')
               group by 1
            )
            select s.id, s.site_key, s.display_name, s.classification
              from sites s
             where s.retired_at is null
               and s.id not in (select site_id from disclosed)""")
        return [dict(zip([c[0] for c in cur.description], r))
                for r in cur.fetchall()]


def documents_for(conn, application_ids: list[int]) -> list[dict]:
    if not application_ids:
        return []
    with conn.cursor() as cur:
        cur.execute("""
            select document_id, application_id, kind, url, bytes_path,
                   page_count, title
              from doc_titles
             where application_id = any(%s)""", (application_ids,))
        return [dict(zip([c[0] for c in cur.description], r))
                for r in cur.fetchall()]


SCALE_COLUMNS = ["cohort", "document_id", "application_id", "application_ref",
                 "site_id", "site_name", "kind", "title", "title_score",
                 "subject_score", "prior", "prior_reason", "page_count",
                 "bytes_path", "url", "description"]


def do_scale(conn, out_dir: Path) -> None:
    """Cohort 3: every unread graphical sheet whose title names plant.

    No cap. The pilot was capped at 28 because a person had to look at
    every row of it; the scale run's size is whatever the gates and the
    priors leave, and if that is too many the answer is a tighter gate
    with a reason, not a truncation with none. Everything the gates
    admitted and the priors then rejected is written to
    scale_excluded.csv with the rule that rejected it.
    """
    with conn.cursor() as cur:
        cur.execute("""
            select t.document_id, t.application_id, t.kind, t.url,
                   t.bytes_path, t.page_count, t.title,
                   a.application_ref, a.description,
                   (select string_agg(distinct s.display_name, ' | ')
                      from site_members m join sites s on s.id = m.site_id
                     where m.application_id = t.application_id
                       and m.retired_at is null and s.retired_at is null)
                     as site_name,
                   (select min(s.id)
                      from site_members m join sites s on s.id = m.site_id
                     where m.application_id = t.application_id
                       and m.retired_at is null and s.retired_at is null)
                     as site_id
              from doc_titles t
              join applications a on a.id = t.application_id""")
        rows = [dict(zip([c[0] for c in cur.description], r))
                for r in cur.fetchall()]

    gated, sent, skipped = 0, [], []
    for d in rows:
        score, subject, rule = title_score(d["title"] or "")
        if score <= 0:
            continue
        if not is_graphical(d["kind"], d["title"]):
            continue
        gated += 1
        verdict, reason = prior_for(d["title"] or "")
        rec = dict(d, cohort=3, title_score=score, subject_score=subject,
                   title_rule=rule, prior=verdict, prior_reason=reason,
                   application_url=d.get("url"))
        (sent if verdict == "send" else skipped).append(rec)

    sent.sort(key=lambda r: (-r["title_score"], r["document_id"]))
    skipped.sort(key=lambda r: (r["prior_reason"], -r["title_score"]))

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scale_selection.json").write_text(
        json.dumps(sent, indent=1, default=str))
    for name, recs in (("scale_selection.csv", sent),
                       ("scale_excluded.csv", skipped)):
        with (out_dir / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=SCALE_COLUMNS,
                               extrasaction="ignore")
            w.writeheader()
            for r in recs:
                w.writerow(r)

    from collections import Counter
    print(f"cohort 3 pool (subject gate + veto + graphical): {gated}")
    print(f"  sent:    {len(sent)}")
    for k, v in Counter(r["prior_reason"] for r in sent).most_common():
        print(f"    {k:<28} {v}")
    print(f"  skipped: {len(skipped)}")
    for k, v in Counter(r["prior_reason"] for r in skipped).most_common():
        print(f"    {k:<28} {v}")
    apps = len({r["application_id"] for r in sent})
    pages = sum(r["page_count"] or 1 for r in sent)
    print(f"  across {apps} applications; {pages} PDF pages "
          f"(page 0 only is sent)")
    print(f"-> {out_dir / 'scale_selection.json'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--scale", action="store_true",
                    help="cohort 3: the corpus-wide targeted scale run")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    if args.scale:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(DOC_TITLES_SQL)
            do_scale(conn, args.out_dir)
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DOC_TITLES_SQL)

        c1_apps = cohort_one(conn)
        c1_docs = documents_for(conn, [a["id"] for a in c1_apps])
        by_app = {a["id"]: a for a in c1_apps}

        c2_sites = cohort_two_sites(conn)
        with conn.cursor() as cur:
            cur.execute("""
                select m.site_id, m.application_id
                  from site_members m
                 where m.retired_at is null and m.application_id is not null
                   and m.site_id = any(%s)""",
                        ([s["id"] for s in c2_sites],))
            pairs = cur.fetchall()
        app_site = {a: s for s, a in pairs}
        c2_docs = documents_for(conn, sorted({a for _, a in pairs}))
        site_by_id = {s["id"]: s for s in c2_sites}
        with conn.cursor() as cur:
            cur.execute("""select id, application_ref, description, url
                             from applications where id = any(%s)""",
                        (sorted({a for _, a in pairs}),))
            c2_app = {r[0]: {"application_ref": r[1], "description": r[2],
                             "url": r[3]} for r in cur.fetchall()}

    def enrich(docs, cohort, app_lookup, site_lookup):
        out = []
        for d in docs:
            score, subject, rule = title_score(d["title"] or "")
            if score <= 0:
                continue
            if cohort == 2 and subject < COHORT_2_SUBJECT_FLOOR:
                continue
            if not is_graphical(d["kind"], d["title"]):
                continue
            rec = dict(d)
            rec["cohort"] = cohort
            rec["title_score"] = score
            rec["subject_score"] = subject
            rec["title_rule"] = rule
            rec.update(app_lookup(d["application_id"]))
            rec.update(site_lookup(d["application_id"]))
            out.append(rec)
        return sorted(out, key=lambda r: -r["title_score"])

    c1 = enrich(
        c1_docs, 1,
        lambda a: {"application_ref": by_app[a]["application_ref"],
                   "description": by_app[a]["description"],
                   "application_url": by_app[a]["url"]},
        lambda a: {"site_id": by_app[a]["site_id"],
                   "site_name": by_app[a]["site_name"]})
    c2 = enrich(
        c2_docs, 2,
        lambda a: {"application_ref": c2_app[a]["application_ref"],
                   "description": c2_app[a]["description"],
                   "application_url": c2_app[a]["url"]},
        lambda a: {"site_id": app_site[a],
                   "site_name": site_by_id[app_site[a]]["display_name"]})

    if args.report:
        print(f"cohort 1 applications (plant description, no figure): {len(c1_apps)}")
        print(f"cohort 1 scoring documents: {len(c1)}")
        print(f"cohort 2 sites (no disclosed capacity): {len(c2_sites)}")
        print(f"cohort 2 scoring documents: {len(c2)}")

    # One document per application in cohort 1 would spread too thin --
    # a generator consent's figure may be on the schedule sheet and not
    # the elevation -- so allow two, but never more, so the pilot is not
    # one application's document set.
    def cap(rows, limit, per_app=2, per_site=None):
        seen, sites, out = {}, {}, []
        for r in rows:
            k = r["application_id"]
            s = r.get("site_id")
            if seen.get(k, 0) >= per_app:
                continue
            if per_site and s is not None and sites.get(s, 0) >= per_site:
                continue
            seen[k] = seen.get(k, 0) + 1
            sites[s] = sites.get(s, 0) + 1
            out.append(r)
            if len(out) >= limit:
                break
        return out

    # The two cohorts overlap: a follow-on generator application at a
    # site with no disclosed capacity qualifies twice. Cohort 1 keeps
    # the document, because the accretion pattern is the stronger claim
    # and the pilot is weighted toward it -- and a document sent twice
    # would be paid for twice and reviewed twice for one answer.
    c1_selected = cap(c1, CAP_COHORT_1, per_app=2, per_site=3)
    taken = {r["document_id"] for r in c1_selected}
    apps_taken = {r["application_id"] for r in c1_selected}
    # One per site in cohort 2, because its question is "does a
    # transformer rating exist anywhere at a site with no figure" and
    # ten sheets from one substation answer it once. Edinburgh's Mary
    # Somerville set alone is nineteen energy-centre and substation
    # sheets, and unchecked it would take two thirds of the cohort.
    c2_selected = cap([r for r in c2 if r["document_id"] not in taken
                       and r["application_id"] not in apps_taken],
                      CAP_COHORT_2, per_app=1, per_site=1)
    selected = (c1_selected + c2_selected)[:CAP_TOTAL]

    if args.select:
        path = args.out_dir / "selection.json"
        path.write_text(json.dumps(selected, indent=1, default=str))
        cols = ["cohort", "document_id", "application_id", "application_ref",
                "site_id", "site_name", "kind", "title", "title_score",
                "page_count", "bytes_path", "url", "description"]
        with (args.out_dir / "selection.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in selected:
                w.writerow(r)
        # Everything that scored and did not make the cap, so the
        # exclusion is a record rather than a silent truncation.
        chosen = {r["document_id"] for r in selected}
        with (args.out_dir / "excluded.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in c1 + c2:
                if r["document_id"] not in chosen:
                    w.writerow(r)
        print(f"selected {len(selected)} -> {path}")
        print(f"excluded {len(c1) + len(c2) - len(selected)} scoring documents")


if __name__ == "__main__":
    main()
