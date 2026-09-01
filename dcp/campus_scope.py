"""How a multi-facility campus presents its power, adjudicated by hand.

`data/priors/campus_scope.yaml` holds every site made of several
Barbour projects. Most are `unreviewed` and nothing here changes what
they show — an unreviewed site keeps today's behaviour, the largest
single figure framed as a floor.

What this module reads is the one reviewed decision that changes a
number on a page: **displacement**. Where a site's planning record
states a load of its own, but the facility layer shows that figure
describes one facility of a campus, a reviewed entry may name the
operator's own campus claim and let it fill the cell instead
(docs/PLAN_OPERATOR_RUNG.md, decision 2 — Luke's, conditional on the
rendering).

Nothing computes this. #247 rejected every automatic alternative: 29
of the 35 multi-project sites hold adjudicated figures of two or more
quantity kinds, so the Stockley incomparability is the corpus norm
rather than a detectable exception, and the crude classifier in the
file's own `proposed` field could not place 17 of the 35.

The contract is `site_partitions.yaml`'s, with one addition:

- an entry naming a site key that is not live **fails the build**;
- an entry naming a claim no claims file holds **fails the build**;
- an entry whose claim has **moved value** since the adjudication
  **fails the build**.

That last one replaces the plan's `claim_name` + `as_at` pin, and is
stronger. Measured 2026-09-01: the Vantage Cardiff claim carries no
`as_at` at all, and nor do four others, so a date pin would have been
unenforceable on exactly the site it was written for. A value pin
holds whether or not a reading is dated, and it fails in the direction
that matters — the operator's figure moved, so the judgement that
accepted the old figure has not been made about the new one. CyrusOne
LON1 going from 8.72 MW to 9 MW in eight days, with no announcement on
the page, is why this is not hypothetical.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Resolved against the package root, never the working directory: a
# relative default plus an empty return is a silent disappearance, and
# a displacement that quietly stopped applying would put the narrower
# planning figure back on the row with nothing to say it had happened.
ROOT = Path(__file__).resolve().parent.parent
SCOPE_PATH = ROOT / "data" / "priors" / "campus_scope.yaml"

SCOPES = ("distinct_facilities", "phases", "masterplan_and_parts",
          "co_located", "unreviewed")
TOTALS = ("sum", "withhold", "unreviewed")


@dataclass(frozen=True)
class Displacement:
    """A reviewed decision that an operator's campus figure ranks a site."""
    site_key: str
    claim_name: str
    expected_value_mw: float
    note: str = ""


def load_scopes(path: Path = SCOPE_PATH) -> dict[str, dict]:
    """site_key -> the entry, in file order. Empty when the file is absent."""
    import yaml
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    out: dict[str, dict] = {}
    for entry in payload.get("campuses") or []:
        key = str(entry["site_key"])
        if key in out:
            raise ValueError(f"campus_scope.yaml: duplicate entry for {key}")
        scope = str(entry.get("scope", "unreviewed"))
        total = str(entry.get("total", "unreviewed"))
        if scope not in SCOPES:
            raise ValueError(
                f"campus_scope.yaml: {key} has scope {scope!r}, not one of "
                + ", ".join(SCOPES))
        if total not in TOTALS:
            raise ValueError(
                f"campus_scope.yaml: {key} has total {total!r}, not one of "
                + ", ".join(TOTALS))
        out[key] = entry
    return out


def load_displacements(path: Path = SCOPE_PATH) -> dict[str, Displacement]:
    """site_key -> Displacement, for the reviewed entries that carry one.

    A `power_cell` block on an unreviewed entry is rejected rather than
    honoured: the displacement *is* the review's output, so it cannot
    precede it.
    """
    out: dict[str, Displacement] = {}
    for key, entry in load_scopes(path).items():
        cell = entry.get("power_cell")
        if not cell:
            continue
        if str(entry.get("scope", "unreviewed")) == "unreviewed":
            raise ValueError(
                f"campus_scope.yaml: {key} carries a power_cell while its "
                f"scope is still unreviewed — the displacement is the "
                f"review's conclusion, so it cannot be written before it")
        missing = [f for f in ("operator_claim", "expected_value_mw")
                   if cell.get(f) in (None, "")]
        if missing:
            raise ValueError(
                f"campus_scope.yaml: {key}'s power_cell is missing "
                + ", ".join(missing))
        if not str(entry.get("reason", "")).strip():
            raise ValueError(
                f"campus_scope.yaml: {key} displaces a planning figure with "
                f"no reason written — the evidence is the point, as it is in "
                f"site_partitions.yaml")
        out[key] = Displacement(
            site_key=key,
            claim_name=str(cell["operator_claim"]),
            expected_value_mw=float(cell["expected_value_mw"]),
            note=str(cell.get("note", "")).strip())
    return out


def require_live(scopes: dict[str, dict], live_keys: set[str]) -> None:
    """Every entry must name a live site, or the build stops.

    The `site_aliases.yaml` contract. A key changes when its cluster's
    anchor changes, and this file's whole population is the sites most
    likely to be re-partitioned.
    """
    unknown = sorted(k for k in scopes if k not in live_keys)
    if unknown:
        raise ValueError(
            "campus_scope.yaml names sites that are not live: "
            + ", ".join(unknown)
            + " — repoint or remove the entry rather than letting the scope "
              "decision silently stop applying")


def require_claims_unmoved(displacements: dict[str, Displacement],
                           claims_by_site: dict[str, list[dict]]) -> None:
    """Each displacement's claim must exist on its site at its own value.

    Two failures, deliberately loud and deliberately separate. A claim
    the site does not hold means the match was retired or the claim
    renamed, and the entry now displaces a planning figure with nothing.
    A claim whose value has moved means the operator republished: the
    adjudication was made about the old figure, and accepting the new
    one silently would let a marketing page change a ranked number with
    nobody having looked.
    """
    problems: list[str] = []
    for key, d in sorted(displacements.items()):
        by_name = {c["claim_name"]: c for c in claims_by_site.get(key, [])}
        claim = by_name.get(d.claim_name)
        if claim is None:
            problems.append(
                f"{key}: no live claim named {d.claim_name!r} is matched to "
                f"this site — the match may have been retired, or the claim "
                f"renamed in its own file")
            continue
        actual = claim.get("value_mw")
        if actual is None or abs(float(actual) - d.expected_value_mw) > 1e-6:
            problems.append(
                f"{key}: {d.claim_name!r} now reads {actual} MW against the "
                f"{d.expected_value_mw} MW this entry was adjudicated "
                f"against — re-read the operator's page and the scope "
                f"decision before updating the pin")
    if problems:
        raise ValueError("campus_scope.yaml displacements no longer hold:\n  "
                         + "\n  ".join(problems))
