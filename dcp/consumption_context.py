"""Per-site consumption context from DESNZ local-authority electricity data.

The premise, stated because it is a domain fact and not a style choice:
data centres are half-hourly-metered non-domestic consumers, and DESNZ
publishes Half-Hourly consumption **only** at local-authority level —
every per-MSOA row in the source workbook carries zero HH meters
(verified 2026-08-12, recorded in data/external_sources/README.md). Local
authority is therefore the finest honest granularity, and nothing in this
module goes below it.

What this module computes is context, not attribution: the change in an
authority's large-user consumption between 2019 and 2024, beside the
national change. The wording it emits never implies the figure is the
site's own consumption — an authority's total includes more than its data
centres, the series ends in 2024 (missing 2025–26 energisations), and
DESNZ's national "Unallocated" bucket means authority figures are floors.
Those caveats travel with the number wherever it appears.

The council → DESNZ authority mapping is an inference and is emitted
alongside the source values, never written over them (house principle 3):
exporters show the matched DESNZ authority name beside the council
prefixes it was derived from. A site whose councils map to more than one
authority gets no sentence unless the Barbour-recorded planning authority
selects one of the candidates — LA boundary data is not held, so
coordinates cannot break the tie. Northern Ireland sites are legitimately
unmapped (the DESNZ file is GB-only), as are Mayoral Development
Corporations (planning authorities, not local authorities) and Crown
dependencies. Deterministic throughout: no API calls, same inputs → same
sentence.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

# Committed snapshot: HH ("All MSOAs" rollup) rows extracted from the
# DESNZ MSOA workbook. Provenance, licence, sha256 and the sanity anchors
# any re-ingest must reproduce are in data/external_sources/README.md.
# Anchored on the repository root, not the working directory, so the
# exporters and the tests read the same file from anywhere.
CSV_PATH = (Path(__file__).resolve().parent.parent
            / "data/external_sources/desnz_la_nondom_halfhourly_2010-2024.csv")

# Headline window. 2019 is the last pre-pandemic year and pre-dates the
# data-centre building wave; 2024 is where the series ends — a fact the
# emitted text states rather than hides. Earlier years (back to 2015 on
# current geography) stay available in the loaded series for longer arcs.
BASE_YEAR = 2019
END_YEAR = 2024

SOURCE_LABEL = "DESNZ sub-national electricity statistics"


# ---------------------------------------------------------------------------
# Series

def load_series(path: Path = CSV_PATH) -> dict[str, dict[int, float]]:
    """Authority name → {year: kWh} for Half-Hourly non-domestic rows.

    Welsh authorities appear under their bare English name up to 2014 and
    under a dual name ("Newport / Casnewydd") from 2015; the two never
    overlap in years, so both are folded onto the English name and the
    fold is asserted. Treat the result as read-only: it is cached.
    """
    return _load_series_cached(str(path))


@lru_cache(maxsize=2)
def _load_series_cached(path_str: str) -> dict[str, dict[int, float]]:
    series: dict[str, dict[int, float]] = {}
    with open(path_str, newline="") as f:
        for row in csv.DictReader(f):
            # "Newport / Casnewydd" → "Newport"; names never otherwise
            # contain " / ".
            name = row["local_authority"].split(" / ")[0].strip()
            year = int(row["year"])
            years = series.setdefault(name, {})
            assert year not in years, \
                f"duplicate year {year} for {name!r} — dual-name fold broke"
            years[year] = float(row["total_kwh"])
    return series


def change_pct(years: dict[int, float],
               y0: int = BASE_YEAR, y1: int = END_YEAR) -> float | None:
    """Percent change y0 → y1, or None where either year is absent.

    Absence is a geography fact, not an error: pre-reorganisation
    districts (Aylesbury Vale, Selby, Sedgemoor…) exist in the file only
    to 2014, because DESNZ backcasts current authorities to 2015.
    """
    if y0 not in years or y1 not in years or not years[y0]:
        return None
    return (years[y1] - years[y0]) / years[y0] * 100.0


def national_change(series: dict[str, dict[int, float]],
                    y0: int = BASE_YEAR, y1: int = END_YEAR) -> float:
    """Percent change in the GB total across authorities holding both years.

    Excludes any "Unallocated" row: DESNZ could not place ~2.9 TWh of
    2024 HH consumption in any authority, and that remainder describes
    the gap between authorities and the nation, not an authority. The
    committed extract holds only authority rollups, so the filter guards
    a future re-ingest rather than changing today's result. Must
    reproduce the −9% anchor in data/external_sources/README.md.
    """
    y0_total = y1_total = 0.0
    for name, years in series.items():
        if "unallocated" in name.casefold():
            continue
        if y0 in years and y1 in years:
            y0_total += years[y0]
            y1_total += years[y1]
    assert y0_total > 0, "national baseline sum is empty — wrong file?"
    return (y1_total - y0_total) / y0_total * 100.0


# ---------------------------------------------------------------------------
# Council → DESNZ authority

# Application-ref prefixes the camel-case split cannot derive: renames
# ("Aberdeen City"), suffixes the refs drop ("Barking and Dagenham"),
# and 2019–2023 reorganisations folded into their current authority —
# the same legacy→current handling as the council_aliases table, in
# static form so it is testable against the committed CSV without a
# database.
PREFIX_ALIASES: dict[str, str] = {
    "Aberdeen": "Aberdeen City",
    "Anglesey": "Isle of Anglesey",
    "Argyll": "Argyll and Bute",
    "AylesburyVale": "Buckinghamshire",
    "Barking": "Barking and Dagenham",
    "Barrow": "Westmorland and Furness",
    "Basingstoke": "Basingstoke and Deane",
    "BCP": "Bournemouth, Christchurch and Poole",
    "Bracknell": "Bracknell Forest",
    "Brighton": "Brighton and Hove",
    "Bristol": "Bristol, City of",
    "Bucks": "Buckinghamshire",
    "Chester": "Cheshire West and Chester",
    "ChilternSouthBucks": "Buckinghamshire",
    "City": "City of London",
    "Dumfries": "Dumfries and Galloway",
    "Dundee": "Dundee City",
    "EastRiding": "East Riding of Yorkshire",
    "Edinburgh": "City of Edinburgh",
    "Glamorgan": "Vale of Glamorgan",
    "Glasgow": "Glasgow City",
    "Hammersmith": "Hammersmith and Fulham",
    "Hull": "Kingston upon Hull, City of",
    "Kettering": "North Northamptonshire",
    "Kingston": "Kingston upon Thames",
    "Neath": "Neath Port Talbot",
    "Newark": "Newark and Sherwood",
    "NorthLincs": "North Lincolnshire",
    "Oadby": "Oadby and Wigston",
    "Redcar": "Redcar and Cleveland",
    "Reigate": "Reigate and Banstead",
    "Rhondda": "Rhondda Cynon Taf",
    "Sedgemoor": "Somerset",
    "Selby": "North Yorkshire",
    "SouthCambs": "South Cambridgeshire",
    "Southend": "Southend-on-Sea",
    "Stockton": "Stockton-on-Tees",
    "Stoke": "Stoke-on-Trent",
    "Wellingborough": "North Northamptonshire",
    "WhiteHorse": "Vale of White Horse",
    "Windsor": "Windsor and Maidenhead",
    "Wycombe": "Buckinghamshire",
}

# Shared planning services whose single ref prefix names several current
# authorities. The prefix alone cannot say which one the site is in;
# only the Barbour-recorded authority can select among them.
PREFIX_SHARED: dict[str, tuple[str, ...]] = {
    "AdurWorthing": ("Adur", "Worthing"),
    "BromsgroveRedditch": ("Bromsgrove", "Redditch"),
    "MidKent": ("Maidstone", "Swale", "Tunbridge Wells"),
    "SouthNorfolkBroadland": ("South Norfolk", "Broadland"),
}

# Recognised and deliberately unmapped: Northern Ireland (the DESNZ file
# is GB-only), Crown dependencies, and Mayoral Development Corporations
# (planning authorities whose areas sit inside London boroughs — placing
# them would need boundary work this dataset does not hold).
PREFIX_NOT_MAPPABLE: frozenset[str] = frozenset({
    "CausewayGlens", "DerryStrabane",   # Northern Ireland
    "Jersey",                            # Crown dependency
    "LondonLegacy", "OldOakParkRoyal",   # Mayoral Development Corporations
})

# References from the routes that bypass the local planning authority,
# which therefore name a project rather than a council: NSIP register
# refs ("EN010030/...") and the gov.uk publication slugs the Section 35
# watcher uses as its application_ref
# ("data-centre-campus-wapseys-wood-buckinghamshire-section-35-direction-
# planning-act-2008"). A slug carries no "/", so the camel-case split
# hands the whole of it over as a prefix, and the build then asks for it
# to be added to this table — which would be the wrong fix twice over:
# it is not a council, and a direction has no council by construction.
_NO_LPA_REF_RE = re.compile(r"^EN\d|section-35-direction")

# Barbour authority names that need more than normalisation. Legacy
# districts fold to their current authority, exactly as the prefixes do.
BARBOUR_ALIASES: dict[str, str] = {
    "Anglesey": "Isle of Anglesey",
    "Barking": "Barking and Dagenham",
    "Chiltern": "Buckinghamshire",
    "City": "City of London",
    "Durham": "County Durham",
    "Edinburgh": "City of Edinburgh",
    "Glasgow": "Glasgow City",
    "Kingston upon Hull": "Kingston upon Hull, City of",
    "Neath": "Neath Port Talbot",
    "Newark": "Newark and Sherwood",
    "Rhondda": "Rhondda Cynon Taf",
    "Selby": "North Yorkshire",
    "South Buckinghamshire": "Buckinghamshire",
    "St Alban": "St Albans",
    "Wycombe": "Buckinghamshire",
}

BARBOUR_NOT_MAPPABLE: frozenset[str] = frozenset({
    "Jersey", "London Legacy", "Old Oak and Park Royal",
})

_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_PHONE_RE = re.compile(r"\s*\(Phone:[^)]*\)\s*$")
# Barbour styles authorities as e.g. "Charnwood Borough Council";
# DESNZ names carry no such suffix.
_COUNCIL_SUFFIX_RE = re.compile(
    r"\s+(?:Borough\s+|City\s+|County\s+|District\s+)?Council$")


def _norm(name: str) -> str:
    """Hyphens and case are typography, not identity: "Newcastle-under-
    Lyme" and "Newcastle Under Lyme" are the same authority."""
    return re.sub(r"[-\s]+", " ", name).casefold().strip()


@lru_cache(maxsize=2)
def _names_by_norm(path_str: str) -> dict[str, str]:
    return {_norm(name): name for name in _load_series_cached(path_str)}


def _prefix_candidates(prefix: str, path_str: str) -> tuple[tuple[str, ...], bool]:
    """(candidate DESNZ names, recognised?) for one application-ref prefix.

    Empty-but-recognised means deliberately unmapped (NI, MDC, NSIP);
    empty-and-unrecognised means a prefix this table has never seen,
    which the exporters print rather than swallow.
    """
    if prefix in PREFIX_NOT_MAPPABLE or _NO_LPA_REF_RE.search(prefix):
        return (), True
    if prefix in PREFIX_SHARED:
        return PREFIX_SHARED[prefix], True
    if prefix in PREFIX_ALIASES:
        return (PREFIX_ALIASES[prefix],), True
    derived = _names_by_norm(path_str).get(_norm(_CAMEL_RE.sub(" ", prefix)))
    if derived:
        return (derived,), True
    return (), False


def _barbour_candidate(authority: str | None, path_str: str) -> str | None:
    """DESNZ name for a Barbour authority_name, or None.

    Barbour appends a phone number and styles names as councils
    ("Wiltshire Council (Phone: …)"); both are stripped before matching.
    County councils (minerals and waste authorities) stay None: the site
    is in one of the county's districts, and which one is not recorded.
    """
    if not authority:
        return None
    name = _PHONE_RE.sub("", authority).replace("&", "and").strip()
    if name in BARBOUR_NOT_MAPPABLE:
        return None
    if name in BARBOUR_ALIASES:
        return BARBOUR_ALIASES[name]
    direct = _names_by_norm(path_str).get(_norm(name))
    if direct:
        return direct
    stripped = _COUNCIL_SUFFIX_RE.sub("", name)
    if stripped in BARBOUR_ALIASES:
        return BARBOUR_ALIASES[stripped]
    return _names_by_norm(path_str).get(_norm(stripped))


def authority_for(councils, barbour_authority: str | None = None,
                  path: Path = CSV_PATH) -> str | None:
    """The single DESNZ authority a site's evidence agrees on, else None.

    Council prefixes come first: where they name exactly one current
    authority, that is the answer. Where they name several — a site
    spanning councils, or a shared planning service — the
    Barbour-recorded authority may select one of the candidates, but
    never introduce an authority the prefixes did not name. Sites with no
    prefixes at all (Barbour-anchored, pre-planning) map on the Barbour
    authority alone. None means: emit no sentence, and count it.
    """
    path_str = str(path)
    candidates: set[str] = set()
    for prefix in councils or ():
        cands, _recognised = _prefix_candidates(prefix, path_str)
        candidates.update(cands)
    if len(candidates) == 1:
        return next(iter(candidates))
    barbour = _barbour_candidate(barbour_authority, path_str)
    if barbour and (not candidates or barbour in candidates):
        return barbour
    return None


def unrecognised(councils, path: Path = CSV_PATH) -> tuple[str, ...]:
    """Prefixes this module has never seen — for the exporters' coverage
    print. A new council entering the universe must show up there, not
    silently join the unmapped count."""
    path_str = str(path)
    return tuple(p for p in (councils or ())
                 if not _prefix_candidates(p, path_str)[1])


# ---------------------------------------------------------------------------
# Journalist-facing text

def _verb(pct: float) -> str:
    rounded = round(pct)
    if rounded > 0:
        return f"rose {rounded}%"
    if rounded < 0:
        return f"fell {-rounded}%"
    return "was broadly flat"


def context_sentence(la: str,
                     series: dict[str, dict[int, float]] | None = None) -> str | None:
    """The per-site sentence, or None where the authority is unmapped or
    the series lacks either headline year. No hedged filler: absence of
    the sentence is the honest form of an absent number."""
    if series is None:
        series = load_series()
    years = series.get(la)
    if not years:
        return None
    la_pct = change_pct(years)
    if la_pct is None:
        return None
    return (f"Large-user electricity consumption in this site's local "
            f"authority {_verb(la_pct)} between {BASE_YEAR} and {END_YEAR}, "
            f"while nationally it {_verb(national_change(series))} "
            f"(DESNZ sub-national statistics; large users are "
            f"half-hourly-metered non-domestic consumers, which includes "
            f"datacentres).")


def context_note(la: str) -> str:
    """The caveats that travel with the sentence, naming the inferred
    authority so the mapping is visible beside its product."""
    return (f"DESNZ series for {la}. The series ends {END_YEAR}, so later "
            f"energisations are not in it; authority figures are floors "
            f"(DESNZ holds a national unallocated remainder); and the "
            f"authority's total covers all its large users, not only data "
            f"centres.")
