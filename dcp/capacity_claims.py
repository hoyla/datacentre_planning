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
