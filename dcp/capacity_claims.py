"""External capacity claims: the NESO Existing Agreements Register.

The permitted form of external site-level megawatts, per the design
consequence in docs/EXTERNAL_DATA_SOURCES.md §1: one row per claim as the
source states it, append-only, never merged into a planning-derived
field. The register is the only public NESO artefact naming transmission
demand customers with MW — 119 rows, 49,440 MW — and the claims here are
its demand rows verbatim. Matching a claim to a site is a separate,
hand-adjudicated inference recorded with written evidence in
data/external_sources/neso-ea-register-matches.yaml; a claim with no
match is a normal, permanent state, not a backlog item.

Quantity discipline: every register figure is contracted transmission
connection capacity — a ceiling someone once agreed with NESO, not IT
load, not built capacity, not observed draw. `quantity_type` says so, and
any consumer that renders a claim renders its quantity_type beside it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl
import yaml
from dcp.site_aliases import displayed

ROOT = Path(__file__).parent.parent
REGISTER_PATH = ROOT / "data" / "external_sources" / "neso-ea-register.xlsx"
MATCHES_PATH = ROOT / "data" / "external_sources" / "neso-ea-register-matches.yaml"

SOURCE_KEY = "neso_ea_register"
SOURCE_URL = "https://www.neso.energy/document/373996/download"

# The file's own banner: "PUBLIC - last updated 11/6/25". Read as 11 June
# 2025 — British format, consistent with the Gate 2 timeline — but the
# format is not stated in the file; data/external_sources/README.md
# records the ambiguity.
AS_AT = date(2025, 6, 11)

HEADER_ROW = 5  # 1-based, as Excel displays it

# The register's own label, which it cannot spell consistently: 3,400 and
# 3,402 carry "Transmission connected demand" against 117 title-case rows.
# Variant forms are synonymous; compare case-insensitively.
DEMAND_TECHNOLOGY = "Transmission Connected Demand"

CONFIDENCE_VOCAB = ("strong", "probable", "tentative")

# ---------------------------------------------------------------------------
# Rendering support. Both artefacts — the reader's site panels and the
# workbook's Capacity claims sheet — draw their wording and their rows
# from here, so they cannot disagree about what a claim is or what it
# does not mean (the two-prose-definitions lesson).

SOURCE_TITLES = {
    "neso_ea_register": "NESO Existing Agreements Register",
    "companies_house": "Companies House filed accounts",
    # Operator claims override this with the operator's own name, since
    # "who is saying it" is the whole point of the weakest-authority
    # source; this is the fallback if that attribute is ever missing.
    "operator_website": "Operator's own website",
    "ea_permit": "Environment Agency public register",
}

QUANTITY_LABELS = {
    "it_load": "IT load",
    "grid_connection": "contracted grid connection",
    "total_site": "total site power",
    "onsite_generation": "on-site generation",
    "cooling": "cooling capacity",
    "energy_storage": "energy storage",
    "thermal_input": "thermal input",
    "built_capacity": "built capacity",
    "metered_consumption": "metered consumption",
    "announced_capacity": "announced capacity",
    "let_capacity": "capacity let to customers",
    "scheme_capacity": "capacity the valuation assumes",
    "investment_property_fair_value": "valuation of the scheme",
}

# Where each panel's numbers come from, said in the artefacts rather than
# left for a reader to infer from a heading. The two panels sit side by
# side and both are megawatts, which is precisely why the difference in
# provenance has to be stated: one is what an applicant told a planning
# authority, the other is an accumulating mixture of registers, filed
# accounts and operators' own marketing, of varying authority and
# measuring different quantities.

DECLARED_POWER_NOTE = (
    "Every figure here is read from this site's own planning documents — "
    "the application, its environmental statement and supporting reports — "
    "and adjudicated as describing this site rather than the market or "
    "another scheme.")

INDICATORS_NOTE = (
    "These come from outside the planning system: grid registers, accounts "
    "filed at Companies House, operators' own websites. Each measures a "
    "different quantity with different authority behind it, so they are "
    "not directly comparable with the declared figures or with each other. "
    "Where they diverge, the divergence is the finding — not an error to "
    "reconcile.")

# One line per quantity, shown only for the quantities a site actually
# has. A single flat caveat stopped working once the sources multiplied:
# what needs saying about a contracted ceiling is not what needs saying
# about a marketing figure.
QUANTITY_CAVEATS = {
    "grid_connection": (
        "A connection ceiling contracted with the grid operator — not what "
        "is built, and not what the site draws. Consent-based registers "
        "also mean absence proves nothing, and entries can lapse."),
    "built_capacity": (
        "Capacity the operator reports as already built, from audited "
        "accounts filed at Companies House."),
    "announced_capacity": (
        "The operator's own published figure for the site. Marketing "
        "material, not an audited or regulatory disclosure, and it may "
        "count capacity not yet built."),
    "metered_consumption": (
        "Energy actually metered over a period, not a power rating. Where "
        "it is a company total it covers every site that company operates "
        "and cannot be attributed to this one."),
    "let_capacity": (
        "How much of the estate has been contracted or billed to "
        "customers — not what is built, and not what those customers "
        "then draw."),
    "scheme_capacity": (
        "The capacity a single-asset company's audited accounts say its "
        "valuation of this scheme assumes it will deliver. Not a "
        "contracted grid connection, which is headroom the network "
        "agreed to supply, and not built capacity, because nothing is "
        "built yet: it is what an external valuer priced and an auditor "
        "signed off on. Where it disagrees with the planning record the "
        "two are measuring different things at different dates, and both "
        "figures are shown."),
    "investment_property_fair_value": (
        "What the scheme was valued at, in pounds, in the same note that "
        "states the capacity assumption. It is here because the "
        "megawatts are stated in order to support it — the valuation is "
        "what the assumption is holding up. Not a power figure, so it "
        "has no megawatt equivalent."),
    "thermal_input": (
        "The rated thermal input of the site's standby generators, from "
        "its environmental permit. It is fuel burned, not electricity "
        "delivered, and the two are not interchangeable: the one permit "
        "here that states both — Telehouse Docklands — gives engines of "
        "1.6 to 2.4 MW electrical at an average 5.1 MWth, so thermal "
        "input runs somewhere between two and three times the electrical "
        "rating, and where a site sits in that range is not something "
        "this figure says. Nor is a fleet the same as a load: five of "
        "these permits state their redundancy, and each says the fleet "
        "is larger than the site needs — Ark Spring Park's is \u201cN+1\u201d, "
        "\u201cone generator more than would be required to provide the total "
        "power for the site\u201d. Plant of 1\u20135 MWth needs no permit until "
        "1 January 2029, so no permit is not no generators."),
}

# Tentative matches are rendered as what they are. The matches file says
# it in its header; the artefacts say it beside each tentative row.
TENTATIVE_NOTE = "a lead, not an attribution"


# ---------------------------------------------------------------------------
# Companies House: filed accounts, hand-transcribed.
#
# A different acquisition problem from the NESO register. Companies House
# scans what it publishes, so there is no text layer and no cell to read a
# number out of: every figure is transcribed by eye from the page rendered
# at 300 DPI. OCR of the cited pages is committed beside the PDFs, not to
# source the figures — a silent digit misread is exactly what this project
# cannot afford in a number — but so the transcription can be re-checked
# without re-rendering, and so a test can assert each figure still appears
# on the page it cites.
#
# Scope, established by probing six other operators on 2026-08-20: per-site
# megawatts are peculiar to Ark. What is statutory is SECR energy
# reporting, and that yields company totals only, which is why consumption
# claims here carry company_level and are never matched to a site.

CH_CLAIMS_PATH = ROOT / "data" / "external_sources" / "companies-house-claims.yaml"
CH_OCR_DIR = ROOT / "data" / "external_sources" / "companies_house_ocr"
CH_SOURCE_KEY = "companies_house"


@dataclass(frozen=True)
class FiledClaim:
    source_key: str
    company_name: str
    company_number: str
    claim_name: str
    quantity_type: str
    value: float
    unit: str
    stage: str | None
    as_at: date | None
    locator: str
    quote: str
    url: str
    company_level: bool
    attrs: dict


def load_ch_document(path: Path = CH_CLAIMS_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def load_ch_claims(path: Path = CH_CLAIMS_PATH) -> list[FiledClaim]:
    cfg = load_ch_document(path)
    sources = {s["key"]: s for s in cfg.get("sources", [])}
    out = []
    for c in cfg.get("claims", []):
        src = sources[c["source"]]
        attrs = dict(c.get("attrs") or {})
        attrs.update({
            "company_name": src["company_name"],
            "company_number": src["company_number"],
            "filing": src["filing"],
            "filed": str(src["filed"]),
            "holder": c.get("holder"),
            "note": c.get("note"),
            "quote": c["quote"].strip(),
            "company_level": bool(c.get("company_level")),
            "source_document": src["key"],
            # The committed PDF's stem is also the OCR filename stem, so
            # the quote check can find the right page without a mapping.
            "document_stem": Path(src["local_pdf"]).stem,
        })
        as_at = c.get("as_at")
        out.append(FiledClaim(
            source_key=CH_SOURCE_KEY,
            company_name=src["company_name"],
            company_number=src["company_number"],
            claim_name=c["claim_name"],
            quantity_type=c["quantity_type"],
            value=float(c["value"]),
            unit=c["unit"],
            stage=c.get("stage"),
            as_at=as_at if isinstance(as_at, date) else None,
            locator=c["locator"],
            quote=c["quote"].strip(),
            url=src["url"],
            company_level=bool(c.get("company_level")),
            attrs=attrs,
        ))
    return out


def mw_of(value: float, unit: str) -> float | None:
    """Megawatts beside the original, never instead of it. Returns None
    where the unit does not convert — MWh is energy, not power, and a
    consumption figure has no megawatt value however much a column would
    like one."""
    u = unit.strip().lower()
    if u == "mw":
        return value
    if u == "kw":
        return value / 1000
    return None


def _digit_blob(text: str) -> str:
    """Every digit in the page, separators removed.

    OCR of these scans drops decimal points and sometimes commas, so
    "121,962.26" comes back as "121,962 26". Matching a digit run against
    a separator-free blob survives that, while a wrong digit — the error
    this check exists to catch — still fails to match. Deliberately not
    tokenised: token boundaries are exactly what the scan loses.
    """
    return re.sub(r"[^0-9]", "", text)


def verify_ch_quotes(claims: list[FiledClaim] | None = None,
                     ocr_dir: Path = CH_OCR_DIR) -> list[str]:
    """Problems as strings; empty means every transcribed figure is still
    present in the OCR of the page it cites."""
    claims = claims if claims is not None else load_ch_claims()
    problems = []
    for c in claims:
        page = c.locator.replace("page ", "p")
        f = ocr_dir / f"{c.attrs['document_stem']}-{page}.txt"
        if not f.exists():
            problems.append(f"{c.claim_name}: no OCR for {c.locator} ({f.name})")
            continue
        blob = _digit_blob(f.read_text())
        printed = f"{c.value:f}".rstrip("0").rstrip(".")
        want = _digit_blob(printed)
        if want and want not in blob:
            problems.append(
                f"{c.claim_name}: {c.value} {c.unit} not found on {c.locator}")
    return problems


# ---------------------------------------------------------------------------
# Operator websites: what a company tells its customers.
#
# The weakest authority in the store and labelled so wherever it renders.
# It earns its place for two reasons: it is the only source describing a
# site's whole intended build-out, and it is published by the same
# companies that file audited accounts — so where the two disagree, both
# numbers are the company's own and the divergence is reportable rather
# than a question of whose source to believe.
#
# Verification is the same shape as the filings: a verbatim span that must
# still appear in the committed snapshot. Operator pages change without
# notice, so a figure that has moved fails the check instead of drifting.

OPERATOR_CLAIMS_PATH = ROOT / "data" / "external_sources" / "operator-claims.yaml"
OPERATOR_SNAPSHOT_DIR = ROOT / "data" / "external_sources" / "operator_snapshots"
OPERATOR_SOURCE_KEY = "operator_website"


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_operator_document(path: Path = OPERATOR_CLAIMS_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def load_operator_claims(path: Path = OPERATOR_CLAIMS_PATH) -> list[FiledClaim]:
    cfg = load_operator_document(path)
    sources = {s["key"]: s for s in cfg.get("sources", [])}
    out = []
    for c in cfg.get("claims", []):
        src = sources[c["source"]]
        snap = OPERATOR_SNAPSHOT_DIR / f"{c['snapshot']}.txt"
        url = ""
        if snap.exists():
            m = re.search(r"^# url: (.+)$", snap.read_text(), re.MULTILINE)
            url = m.group(1).strip() if m else ""
        as_at = c.get("as_at")
        out.append(FiledClaim(
            source_key=OPERATOR_SOURCE_KEY,
            company_name=src["operator"],
            company_number="",
            claim_name=c["claim_name"],
            quantity_type=c["quantity_type"],
            value=float(c["value"]),
            unit=c["unit"],
            stage=c.get("stage"),
            as_at=as_at if isinstance(as_at, date) else None,
            locator=c["snapshot"],
            quote=c["quote"].strip(),
            url=url,
            company_level=False,
            attrs={
                "operator": src["operator"],
                # The operator's own word for the quantity, kept because
                # "Total Capacity", "Total compute capacity" and "IT load"
                # are not synonyms and the difference is the story.
                "operator_term": c.get("term"),
                "note": c.get("note"),
                "quote": c["quote"].strip(),
                "snapshot": c["snapshot"],
                "source_document": c["snapshot"],
                "document_stem": c["snapshot"],
            },
        ))
    return out


def load_operator_matches(path: Path = OPERATOR_CLAIMS_PATH) -> list[dict]:
    return list(load_operator_document(path).get("matches", []))


def verify_operator_quotes(claims: list[FiledClaim] | None = None,
                           snapshot_dir: Path = OPERATOR_SNAPSHOT_DIR) -> list[str]:
    """Every claim's verbatim span must still appear in its snapshot.

    Whitespace-normalised on both sides: the snapshots are extracted text
    and JSON, where line breaks carry no meaning, but the digits and words
    do.
    """
    claims = claims if claims is not None else load_operator_claims()
    problems = []
    for c in claims:
        f = snapshot_dir / f"{c.attrs['snapshot']}.txt"
        if not f.exists():
            problems.append(f"{c.claim_name}: no snapshot {f.name}")
            continue
        if _norm_ws(c.quote) not in _norm_ws(f.read_text()):
            problems.append(
                f"{c.claim_name}: quote not found in {f.name} — the page may "
                f"have changed; re-run scripts/fetch_operator_snapshots.py "
                f"and re-read the figure")
    return problems


def validate_operator(claims: list[FiledClaim],
                      matches: list[dict]) -> list[str]:
    problems = []
    names = [c.claim_name for c in claims]
    dupes = {n for n in names if names.count(n) > 1}
    problems += [f"duplicate claim_name {n!r}" for n in sorted(dupes)]
    for m in matches:
        if m["claim_name"] not in names:
            problems.append(f"match names no claim: {m['claim_name']!r}")
        if m["confidence"] not in CONFIDENCE_VOCAB:
            problems.append(f"{m['claim_name']}: confidence {m['confidence']!r}")
        if len(m.get("evidence", "").strip()) < 40:
            problems.append(f"{m['claim_name']}: evidence too thin to defend")
    return problems + verify_operator_quotes(claims)


def load_site_claims(cur) -> dict[str, list[dict]]:
    """Live matches joined to their claims, keyed by site_key.

    Only sites with a live (unretired) match appear; most claims match
    nothing and are reachable through load_claim_rows instead.
    """
    cur.execute("""
        SELECT s.site_key, cl.claim_name, cl.value_mw, cl.quantity_type,
               cl.attrs->>'connection_point',
               cl.attrs->>'existing_connection_date',
               cl.as_at, cl.source_key, cl.source_url, cl.source_locator,
               m.method, m.confidence, m.evidence,
               cl.attrs->>'operator', cl.attrs->>'operator_term',
               cl.value_original, cl.unit_original, cl.stage
        FROM capacity_claim_matches m
        JOIN capacity_claims cl ON cl.id = m.claim_id
        JOIN sites s ON s.id = m.site_id
        WHERE m.retired_at IS NULL AND s.retired_at IS NULL
        ORDER BY cl.value_mw DESC NULLS LAST, cl.claim_name, cl.id""")
    out: dict[str, list[dict]] = {}
    for (key, name, mw, qty, point, conn_date, as_at, src, url, locator,
         method, confidence, evidence, operator, term,
         value_original, unit_original, stage) in cur.fetchall():
        out.setdefault(key, []).append({
            "claim_name": name, "value_mw": mw, "quantity_type": qty,
            "connection_point": point, "connection_date": conn_date,
            "as_at": as_at, "source_key": src, "source_url": url,
            "source_locator": locator, "method": method,
            "confidence": confidence, "evidence": evidence,
            "operator": operator, "operator_term": term,
            "value_original": value_original, "unit_original": unit_original,
            "stage": stage,
        })
    return out


def load_claim_rows(cur) -> list[dict]:
    """Every claim, with its live match where one exists — the workbook
    sheet's rows. Unmatched claims are most of the register and belong in
    the artefact: they are the demand pipeline the planning system may
    not have seen yet."""
    cur.execute("""
        SELECT cl.claim_name, cl.value_mw, cl.quantity_type,
               cl.attrs->>'connection_point',
               cl.attrs->>'existing_connection_date',
               cl.as_at, cl.source_key, cl.source_url, cl.source_locator,
               s.site_key, s.display_name,
               m.method, m.confidence, m.evidence
        FROM capacity_claims cl
        LEFT JOIN capacity_claim_matches m
               ON m.claim_id = cl.id AND m.retired_at IS NULL
        LEFT JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
        ORDER BY cl.value_mw DESC NULLS LAST, cl.claim_name, cl.id""")
    cols = ("claim_name", "value_mw", "quantity_type", "connection_point",
            "connection_date", "as_at", "source_key", "source_url",
            "source_locator", "site_key", "site_name",
            "method", "confidence", "evidence")
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    # A matched claim names its site in the workbook sheet and the
    # reader's claims table, both of which the alias covers. Unmatched
    # claims have no site to name.
    for row in rows:
        if row["site_key"]:
            row["site_name"] = displayed(row["site_key"], row["site_name"])
    return rows


@dataclass(frozen=True)
class Claim:
    claim_name: str
    value_mw: float
    excel_row: int
    connection_point: str | None
    existing_connection_date: date | None
    gate1_interest: str | None
    technology_verbatim: str

    @property
    def source_locator(self) -> str:
        return f"row {self.excel_row}"


@dataclass(frozen=True)
class Match:
    excel_row: int
    claim_name: str
    site_id: int
    method: str
    confidence: str
    evidence: str
    matched_by: str


def load_register_demand_claims(path: Path = REGISTER_PATH) -> list[Claim]:
    """The register's demand rows, verbatim, in file order."""
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    claims = []
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i <= HEADER_ROW:
            continue
        name, capacity, conn_date, point, gate1, tech = row
        if str(tech).strip().lower() != DEMAND_TECHNOLOGY.lower():
            continue
        if isinstance(conn_date, datetime):
            conn_date = conn_date.date()
        claims.append(Claim(
            claim_name=str(name).strip(),
            value_mw=float(capacity),
            excel_row=i,
            connection_point=str(point).strip() if point else None,
            existing_connection_date=conn_date,
            gate1_interest=str(gate1).strip() if gate1 else None,
            technology_verbatim=str(tech).strip(),
        ))
    return claims


def load_ch_matches(path: Path = CH_CLAIMS_PATH) -> list[dict]:
    """Matches for the filed-accounts claims, keyed by claim_name rather
    than a row number — a filing has no rows, and the claim names in the
    file are unique by construction (asserted in validate_ch)."""
    return list(load_ch_document(path).get("matches", []))


def validate_ch(claims: list[FiledClaim], matches: list[dict]) -> list[str]:
    problems = []
    names = [c.claim_name for c in claims]
    dupes = {n for n in names if names.count(n) > 1}
    problems += [f"duplicate claim_name {n!r}" for n in sorted(dupes)]
    for m in matches:
        if m["claim_name"] not in names:
            problems.append(f"match names no claim: {m['claim_name']!r}")
        if m["confidence"] not in CONFIDENCE_VOCAB:
            problems.append(f"{m['claim_name']}: confidence {m['confidence']!r}")
        if len(m.get("evidence", "").strip()) < 40:
            problems.append(f"{m['claim_name']}: evidence too thin to defend")
    # A company-level figure must never carry a site match.
    company_level = {c.claim_name for c in claims if c.company_level}
    for m in matches:
        if m["claim_name"] in company_level:
            problems.append(
                f"{m['claim_name']}: company-level claim matched to a site")
    return problems + verify_ch_quotes(claims)


def load_matches(path: Path = MATCHES_PATH) -> list[Match]:
    cfg = yaml.safe_load(path.read_text())
    return [Match(
        excel_row=m["row"],
        claim_name=m["claim_name"],
        site_id=m["site_id"],
        method=m["method"],
        confidence=m["confidence"],
        evidence=m["evidence"].strip(),
        matched_by=m["matched_by"],
    ) for m in cfg.get("matches", [])]


def validate_matches(claims: list[Claim], matches: list[Match]) -> list[str]:
    """Problems as strings; empty means the batch is loadable.

    A match must name a demand claim that exists, at the row it says, with
    the confidence vocabulary the schema enforces and evidence a reader
    could weigh. Validated here as well as by the database constraints so
    a bad batch fails before it half-loads.
    """
    by_row = {c.excel_row: c for c in claims}
    problems = []
    seen_rows: set[int] = set()
    for m in matches:
        claim = by_row.get(m.excel_row)
        if claim is None:
            problems.append(f"row {m.excel_row}: no demand claim at this row")
        elif claim.claim_name != m.claim_name:
            problems.append(
                f"row {m.excel_row}: claim_name {m.claim_name!r} does not "
                f"match register {claim.claim_name!r}")
        if m.confidence not in CONFIDENCE_VOCAB:
            problems.append(f"row {m.excel_row}: confidence {m.confidence!r}")
        if len(m.evidence) < 40:
            problems.append(f"row {m.excel_row}: evidence too thin to defend")
        if m.excel_row in seen_rows:
            problems.append(f"row {m.excel_row}: matched more than once")
        seen_rows.add(m.excel_row)
    return problems
