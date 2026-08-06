"""Deterministic signal extraction from application descriptions.

The triage model emits power-related signals as part of its judgement.
Environmental subject matter — cooling water, discharge consents,
designated sites, air quality, flood risk — is extracted here instead,
by plain keyword matching, for three reasons:

1. **Reproducibility.** The same description always yields the same
   signals, with no model version or temperature in the chain. A reporter
   can verify a signal by reading the description; a reader can too.
2. **No accuracy risk.** Widening the model's signal vocabulary was tried
   (prompt v2.2, 2026-08-06) and cost two points of verdict accuracy on
   the adjudicated set — entirely on the rows that depend on the
   association rule. The prompt was reverted; this module delivers the
   same filtering capability without touching a validated prompt.
3. **Cost.** Free, and re-runnable over the whole corpus whenever the
   lexicon changes.

These are *signals*, not findings: they record that a description
mentions a subject, not what the documents say about it. Quantities
(cooling water volumes, emission rates) come from deep-read, with
verbatim quotes.

Matching notes: terms are matched case-insensitively on word boundaries,
and typographical variants of the same term count as that term
("gas-fired" ≡ "gas fired", "onsite" ≡ "on-site") — a convention Luke
set for the power lexicon and applied here too.
"""

from __future__ import annotations

import re

# Environmental subject matter. Grouped for reporting; the group name is
# what appears in exports alongside the matched term.
ENVIRONMENTAL_LEXICON: dict[str, tuple[str, ...]] = {
    "water": (
        "cooling water", "water cooling", "water abstraction", "abstraction",
        "water use", "water consumption", "potable water", "grey water",
        "closed loop", "evaporative cooling", "adiabatic",
        "discharge consent", "trade effluent", "effluent", "surface water discharge",
    ),
    "air": (
        "air quality", "emissions", "nitrogen dioxide", "NOx", "particulate",
        "PM10", "PM2.5", "stack height", "dispersion model", "odour",
    ),
    "designated sites": (
        "SSSI", "site of special scientific interest", "SAC",
        "special area of conservation", "SPA", "special protection area",
        "Ramsar", "ancient woodland", "local nature reserve",
        "national nature reserve", "green belt", "AONB",
        "national landscape", "conservation area", "scheduled monument",
    ),
    "ecology": (
        "ecological impact", "biodiversity net gain", "protected species",
        "great crested newt", "bat survey", "habitat regulations",
        "HRA", "ecological appraisal", "veteran tree",
    ),
    "flood and drainage": (
        "flood risk", "flood zone", "SuDS", "sustainable drainage",
        "surface water flooding", "attenuation", "watercourse",
    ),
    "land quality": (
        "contamination", "contaminated land", "remediation",
        "ground gas", "landfill gas", "geo-environmental",
    ),
    "noise": (
        "noise assessment", "noise impact", "acoustic", "plant noise",
    ),
    "heat": (
        "heat recovery", "waste heat", "heat network", "district heating",
    ),
}

_VARIANT = re.compile(r"[-\s]+")


def _pattern(term: str) -> re.Pattern[str]:
    """Match a term tolerantly: hyphen/space variants are equivalent, and
    matching is bounded so 'SAC' does not fire inside 'sacrificial'."""
    parts = [re.escape(p) for p in _VARIANT.split(term) if p]
    body = r"[-\s]*".join(parts)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


_COMPILED: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    group: tuple((term, _pattern(term)) for term in terms)
    for group, terms in ENVIRONMENTAL_LEXICON.items()
}


def environmental_signals(text: str | None) -> dict[str, list[str]]:
    """Return {group: [matched terms]} for terms present in `text`.

    Only terms genuinely present are returned — nothing is inferred from
    context, mirroring the rule the triage prompt applies to power terms.
    """
    if not text:
        return {}
    out: dict[str, list[str]] = {}
    for group, terms in _COMPILED.items():
        hits = [term for term, pat in terms if pat.search(text)]
        if hits:
            out[group] = hits
    return out


def flatten(signals: dict[str, list[str]]) -> list[str]:
    """`{"water": ["cooling water"]}` → `["water: cooling water"]`, for
    spreadsheet cells and simple filtering."""
    return [f"{group}: {term}" for group, terms in sorted(signals.items())
            for term in terms]
