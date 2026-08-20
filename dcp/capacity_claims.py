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

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl
import yaml

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
}

# The caveat that must travel with every rendered claim. Contracted
# capacity is the quantity most often mistaken for a site's "real"
# demand, so the sentence names what it is not.
CLAIMS_CAVEAT = (
    "Contracted connection capacity is a ceiling a developer once agreed "
    "with the grid operator — not IT load, not built capacity, and not "
    "what the site draws. The register is consent-based and records "
    "pre-reform positions, so absence proves nothing and entries can "
    "shrink or lapse.")

# Tentative matches are rendered as what they are. The matches file says
# it in its header; the artefacts say it beside each tentative row.
TENTATIVE_NOTE = "a lead, not an attribution"


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
               m.method, m.confidence, m.evidence
        FROM capacity_claim_matches m
        JOIN capacity_claims cl ON cl.id = m.claim_id
        JOIN sites s ON s.id = m.site_id
        WHERE m.retired_at IS NULL AND s.retired_at IS NULL
        ORDER BY cl.value_mw DESC NULLS LAST, cl.claim_name""")
    out: dict[str, list[dict]] = {}
    for (key, name, mw, qty, point, conn_date, as_at, src, url, locator,
         method, confidence, evidence) in cur.fetchall():
        out.setdefault(key, []).append({
            "claim_name": name, "value_mw": mw, "quantity_type": qty,
            "connection_point": point, "connection_date": conn_date,
            "as_at": as_at, "source_key": src, "source_url": url,
            "source_locator": locator, "method": method,
            "confidence": confidence, "evidence": evidence,
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
        ORDER BY cl.value_mw DESC NULLS LAST, cl.claim_name""")
    cols = ("claim_name", "value_mw", "quantity_type", "connection_point",
            "connection_date", "as_at", "source_key", "source_url",
            "source_locator", "site_key", "site_name",
            "method", "confidence", "evidence")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


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
