"""Who tells what to whom: the same companies, across four audiences.

A data centre's size is stated to at least four different audiences, and
this project now holds all four — the planning authority (the site's own
application documents), the grid operator (NESO's register of contracted
connections), the auditors (accounts filed at Companies House) and
customers (the operator's own website). This module puts them beside each
other, one row per operator, computed from `capacity_claims` so nothing
here can drift from the figures the site panels show.

**The subject is the pattern of disclosure, not a scoreboard of secrecy.**
Almost none of these companies has any duty to publish capacity at all,
and several that publish nothing are meeting every obligation they have.
What is reportable is narrower and firmer: where a company states
different figures to different audiences, and where a company publishes a
figure with no statement of what it measures. Both are visible only
because the claims are kept apart rather than reconciled.

Operator identity comes from the claim itself where the source names one
(website claims carry the operator, filed accounts the company), and by
inference through a shared site otherwise — a NESO register row is
attributed to an operator when it matches a site that operator's own
claims also match. That inference is mediated by the site matches, each
of which carries written evidence, so it inherits their confidence rather
than inventing any.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Filed accounts name a legal entity; websites name a brand. Mapped by
# hand because there are few enough to check, and a fuzzy match here
# would silently merge two companies that share a word.
COMPANY_TO_OPERATOR = {
    "ARK DATA CENTRES LIMITED": "Ark Data Centres",
    "KAO DATA LIMITED": "Kao Data",
}

AUDIENCES = (
    ("planning", "The planning authority",
     "Figures stated in the site's own planning documents."),
    ("grid", "The grid operator",
     ("Contracted connection capacity in NESO's Existing Agreements "
      "Register.")),
    ("auditors", "The auditors",
     ("Built capacity and metered consumption in accounts filed at "
      "Companies House.")),
    ("customers", "Customers",
     "Capacity published on the operator's own website."),
)

SOURCE_TO_AUDIENCE = {
    "neso_ea_register": "grid",
    "companies_house": "auditors",
    "operator_website": "customers",
}

FAIRNESS_NOTE = (
    "Almost none of these companies is under any obligation to publish "
    "capacity, and an empty column is not evidence of concealment. What "
    "this table is for is the opposite comparison: where one company "
    "tells different audiences different things, and where a figure is "
    "published with nothing to say what it measures.")

METHOD_NOTE = (
    "Built from the capacity claims, so every figure here is the same "
    "figure the site panels show, with the same provenance. An operator "
    "is credited with a grid-register entry when that entry matches a "
    "site the operator's own claims also match — an inference carried by "
    "the site match, not a new one.")


@dataclass
class OperatorRow:
    operator: str
    sites: set = field(default_factory=set)
    by_audience: dict = field(default_factory=dict)
    terms: set = field(default_factory=set)

    @property
    def audiences(self) -> int:
        return sum(1 for a in self.by_audience.values() if a)


def load_rows(cur) -> list[OperatorRow]:
    """One row per operator, with the claims it makes to each audience."""
    cur.execute("""
        SELECT cl.source_key,
               coalesce(cl.attrs->>'operator', cl.attrs->>'company_name'),
               cl.claim_name, cl.value_original, cl.unit_original,
               cl.quantity_type, cl.attrs->>'operator_term',
               m.site_id
        FROM capacity_claims cl
        LEFT JOIN capacity_claim_matches m
               ON m.claim_id = cl.id AND m.retired_at IS NULL
        ORDER BY cl.id""")
    raw = cur.fetchall()

    # Which operator owns which site, from the claims that name one.
    site_operator: dict[int, str] = {}
    for src, who, _n, _v, _u, _q, _t, site_id in raw:
        if site_id and who:
            site_operator.setdefault(
                site_id, COMPANY_TO_OPERATOR.get(who, who))

    rows: dict[str, OperatorRow] = {}
    for src, who, name, value, unit, qty, term, site_id in raw:
        operator = COMPANY_TO_OPERATOR.get(who, who) if who else None
        # An unattributed register row belongs to whoever else claims the
        # site it matched. Without a match it belongs to nobody, which is
        # the honest answer for most of the register.
        if operator is None:
            operator = site_operator.get(site_id) if site_id else None
        if operator is None:
            continue
        row = rows.setdefault(operator, OperatorRow(operator))
        audience = SOURCE_TO_AUDIENCE.get(src)
        if audience:
            row.by_audience.setdefault(audience, []).append({
                "claim_name": name, "value": value, "unit": unit,
                "quantity_type": qty, "term": term, "site_id": site_id,
            })
        if site_id:
            row.sites.add(site_id)
        if term:
            row.terms.add(term)

    # An operator is credited with the planning audience where any site
    # it claims has a figure adjudicated from its own application
    # documents — the fourth column, and the only one none of these
    # companies chose to fill.
    all_sites = {s for r in rows.values() for s in r.sites}
    planning = load_planning_figures(cur, list(all_sites))
    for row in rows.values():
        told = [p for s in row.sites for p in planning.get(s, [])]
        if told:
            row.by_audience["planning"] = told
    return sorted(rows.values(),
                  key=lambda r: (-r.audiences, -len(r.sites), r.operator))


def load_planning_figures(cur, site_ids) -> dict[int, list[dict]]:
    """What each site told its planning authority.

    These do not live in capacity_claims and must not: they are the
    project's own adjudicated readings of the application documents, and
    the whole design keeps them apart from external claims. For this
    comparison they are read from power_adjudication directly, which is
    the same place the site panels read them from.
    """
    if not site_ids:
        return {}
    cur.execute("""
        SELECT DISTINCT ON (sm.site_id, pa.quantity_type)
               sm.site_id, pa.quantity_type, pa.value_mw, a.application_ref
        FROM power_adjudication pa
        JOIN applications a ON a.id = pa.application_id
        JOIN site_members sm ON sm.application_id = a.id
                            AND sm.retired_at IS NULL
        WHERE sm.site_id = ANY(%s)
          AND pa.verdict = 'site_capacity'
          AND pa.value_mw IS NOT NULL
          AND pa.quantity_type IN ('it_load', 'total_site', 'grid_connection')
        ORDER BY sm.site_id, pa.quantity_type, pa.value_mw DESC""",
                (list(site_ids),))
    out: dict[int, list[dict]] = {}
    for site_id, qty, mw, ref in cur.fetchall():
        out.setdefault(site_id, []).append({
            "audience": "planning", "source_key": "planning_documents",
            "claim_name": ref, "value": mw, "unit": "MW",
            "quantity_type": qty, "term": None, "confidence": None,
        })
    return out


def load_divergences(cur) -> list[dict]:
    """Sites where more than one audience was given a figure.

    The point of the whole store, reduced to a list: one site, several
    numbers, each with the audience it was told to. Consumption figures
    are excluded — MWh is not a capacity and would read as a wild
    outlier beside megawatts.
    """
    cur.execute("""
        SELECT s.id, s.display_name,
               cl.source_key, cl.claim_name, cl.value_original,
               cl.unit_original, cl.quantity_type,
               cl.attrs->>'operator_term', m.confidence
        FROM capacity_claim_matches m
        JOIN capacity_claims cl ON cl.id = m.claim_id
        JOIN sites s ON s.id = m.site_id
        WHERE m.retired_at IS NULL AND s.retired_at IS NULL
          AND cl.quantity_type <> 'metered_consumption'
        ORDER BY s.id, cl.source_key""")
    by_site: dict[int, dict] = {}
    for (sid, name, src, claim, value, unit, qty, term, conf) in cur.fetchall():
        d = by_site.setdefault(sid, {"site_id": sid, "site": name,
                                     "claims": []})
        d["claims"].append({
            "audience": SOURCE_TO_AUDIENCE.get(src, src),
            "source_key": src, "claim_name": claim, "value": value,
            "unit": unit, "quantity_type": qty, "term": term,
            "confidence": conf,
        })
    planning = load_planning_figures(cur, list(by_site))
    for sid, d in by_site.items():
        d["claims"] = planning.get(sid, []) + d["claims"]
    out = []
    for d in by_site.values():
        audiences = {c["audience"] for c in d["claims"]}
        if len(audiences) > 1:
            # The range of figures on record for the site. Deliberately
            # not called a discrepancy: IT load is *expected* to be lower
            # than total site power, so a wide range is usually four
            # different quantities rather than four answers to one
            # question.
            mws = [float(c["value"]) for c in d["claims"]
                   if c["unit"] == "MW"]
            d["low"], d["high"] = (min(mws), max(mws)) if mws else (None, None)

            # The sharp comparison: the same quantity, stated to two
            # different audiences. Here a gap is a gap — a contracted
            # grid connection is one number however many people are
            # asked — and agreement is corroboration rather than
            # coincidence.
            same: dict[str, list] = {}
            for c in d["claims"]:
                if c["unit"] == "MW":
                    same.setdefault(c["quantity_type"], []).append(c)
            d["like_for_like"] = [
                {"quantity_type": q,
                 "values": sorted(v, key=lambda c: -float(c["value"])),
                 "ratio": (max(float(c["value"]) for c in v)
                           / min(float(c["value"]) for c in v))}
                for q, v in same.items()
                if len({c["audience"] for c in v}) > 1]
            out.append(d)
    return sorted(out, key=lambda d: -(d["high"] or 0))
