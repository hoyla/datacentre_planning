"""Environment Agency permits: what a data centre's standby fleet is rated at.

The largest remaining lever on the sites whose planning documents disclose
no power figure, and it works because of a statutory accident. A data
centre's diesel standby fleet is sized to peak load plus redundancy, and
a fleet that size needs an environmental permit. The permit is a public
document, and it states the thing the application does not: how many
generators, at what rated thermal input each, totalling what.

Ark's Cody Park permit is the shape of it — "The combustion plant
comprises 69 diesel fuelled standby generators. 36 of the generators have
a thermal input of 2.71MWth, 24 generators at 5.38MWth and 9 generators
at 3.66MWth each. The aggregated total combustion capacity on site is
approximately 260MWth." — for a site whose planning record says nothing
about power at all.

Three things this module is careful about.

**The register is an index, not a source of megawatts.** The public
register download carries a permit number, a holder, an address,
coordinates and a link. It carries no capacity whatsoever. So a register
row is not a claim and is never loaded as one: it is a candidate that
points at a document, and the document is what a claim is made from.
Rows whose activity type is "Combustion; Any Fuel =>50MW" do imply a
floor — the permit exists because the plant crosses 50MWth — but a floor
is not a figure, and writing 50 into a numeric column would be exactly
the kind of number-that-means-something-else this project refuses.

**Thermal input is not electrical demand.** A 260MWth fleet is not a
260MW site. Dividing by roughly 2.4–2.5 for generator efficiency bounds
the electrical capacity the fleet can support, and that bound is an
inference to be made in the open by a reporter, not a conversion to be
done silently in a loader. So `value_mw` is null on every claim here:
MWth does not convert to MW, it *implies* a range in MW, and the two are
not the same operation. The quantity carries its own caveat and the
reader prints the thermal figure as the permit prints it.

**Neither a company name nor a postcode is an identity.** Two candidate
generators run over the register — the words "data centre" in the holder
or address, and a curated operator vocabulary in
data/external_sources/ea-permit-operators.yaml — and both are labelled
on the candidate rather than collapsed into a yes. Every attachment of a
permit to a site is then hand-adjudicated with written evidence, as the
capacity claims are, because an operator with several campuses in one
district is the Union Park failure waiting to happen again.

Licence: Environment Agency Conditional Licence. Attribution required —
"Contains Environment Agency information © Environment Agency and/or
database right" — and recorded in DATA-LICENSING.md.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from dcp.capacity_claims import CONFIDENCE_VOCAB, FiledClaim

ROOT = Path(__file__).parent.parent
EXTERNAL = ROOT / "data" / "external_sources"

REGISTER_PATH = EXTERNAL / "ea-industrial-installations.zip"
REGISTER_MEMBER = "industrial-installations.csv"
OPERATORS_PATH = EXTERNAL / "ea-permit-operators.yaml"
MANIFEST_PATH = EXTERNAL / "ea-permit-documents.json"
TEXT_DIR = EXTERNAL / "ea_permit_text"
CLAIMS_PATH = EXTERNAL / "ea-permit-claims.yaml"

# Where the permit PDFs land. Not committed — data/raw/ is gitignored and
# stays that way (DATA-LICENSING.md). The committed trail is the manifest,
# which carries each document's URL and sha256, plus the text of the pages
# the claims quote, so a claim can be re-checked without the PDFs.
PDF_DIR = ROOT / "data" / "raw" / "ea_permits"

SOURCE_KEY = "ea_permit"
REGISTER_URL = ("https://environment.data.gov.uk/public-register/downloads/"
                "industrial-installations")

# The register is regenerated daily and carries no internal version, so
# the download date is the only date it can speak as of. Update both when
# scripts/fetch_ea_permits.py --register re-pulls it.
AS_AT = date(2026, 8, 21)
REGISTER_SHA256 = ("769ec9fa7d1bd51aeaf564deb5daab6d7b74725ca4eba10b20d6eb"
                   "06466c57d0")

ATTRIBUTION = ("Contains Environment Agency information © Environment "
               "Agency and/or database right")

# A permit is only interesting here if it authorises combustion plant.
# Everything else in the register — poultry housing, landfill, chemicals,
# waste transfer — is noise, and it is the filter that removes the false
# positives a short operator token generates: Vantage Farm is intensive
# farming, Vantage Waste Solutions is hazardous waste storage.
#
# Measured against the 2026-08-21 register, these three words cover every
# combustion activity string it contains and no other: "MCP", "Combustion;
# Any Fuel =>50MW", "Medium Combustion Plant collectively =>50MW",
# "Medium Combustion Plant and Specified Generator", "Specified
# Generator", "New Medium Combustion Plant before 20th December 2018",
# "Directly Associated Activity (included and an MCP)". Gasification and
# refining strings deliberately do not match: a refinery is not a standby
# fleet.
COMBUSTION_WORDS = ("combustion", "mcp", "specified generator")

DC_WORDS = ("data centre", "data center")


@dataclass(frozen=True)
class RegisterRow:
    permission_number: str
    name: str
    activity: str
    document_url: str
    site_address: str
    postcode: str
    grid_reference: str
    easting: int | None
    northing: int | None
    local_authority: str
    permission_date: date | None

    @property
    def slug(self) -> str:
        """EPR/VP3235DJ -> vp3235dj. The filename stem for this permit's
        documents and text, and the key everything downstream joins on."""
        return self.permission_number.rsplit("/", 1)[-1].lower()

    @property
    def is_combustion(self) -> bool:
        return any(w in self.activity.lower() for w in COMBUSTION_WORDS)

    @property
    def names_a_data_centre(self) -> bool:
        blob = f"{self.name} {self.site_address}".lower()
        return any(w in blob for w in DC_WORDS)


@dataclass(frozen=True)
class Candidate:
    row: RegisterRow
    generators: tuple[str, ...]
    operator: str | None
    kind: str | None
    matched_token: str | None


def load_register(path: Path = REGISTER_PATH) -> list[RegisterRow]:
    """Every row of the committed register snapshot, verbatim.

    The download is a zip, not the bare CSV its URL implies — curling it
    gives 570 KB beginning `PK\\x03\\x04`. Unpacked in memory so the
    snapshot on disk stays byte-identical to what the Environment Agency
    served.
    """
    with zipfile.ZipFile(path) as z:
        raw = z.read(REGISTER_MEMBER).decode("utf-8-sig")
    out = []
    for r in csv.DictReader(io.StringIO(raw)):
        out.append(RegisterRow(
            permission_number=(r["Permission Number"] or "").strip(),
            name=(r["Name"] or "").strip(),
            activity=(r["Activity Type Description"] or "").strip(),
            document_url=(r["Document URL"] or "").strip(),
            site_address=(r["Site Address"] or "").strip(),
            postcode=(r["Site Postcode"] or "").strip(),
            grid_reference=(r["Site Grid Reference"] or "").strip(),
            easting=_int(r["Easting"]),
            northing=_int(r["Northing"]),
            local_authority=(r["Local Authority"] or "").strip(),
            permission_date=_date(r["Permission Date"]),
        ))
    return out


def _int(v: str | None) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat(str(v).strip())
    except (TypeError, ValueError):
        return None


def load_operators(path: Path = OPERATORS_PATH) -> list[dict]:
    return list(yaml.safe_load(path.read_text()).get("operators", []))


def candidates(rows: list[RegisterRow] | None = None,
               operators: list[dict] | None = None) -> list[Candidate]:
    """Register rows that could be a data centre's standby fleet.

    Two generators, both recorded on the candidate rather than reduced to
    a boolean, because they fail differently: `dc_in_name` misses every
    single-purpose vehicle ("SF LHR LTD", "GTR MANAGEMENT SERVICES
    LIMITED") and `operator` misses every operator not yet in the
    vocabulary. Neither is an identity; both are leads.
    """
    rows = rows if rows is not None else load_register()
    operators = operators if operators is not None else load_operators()
    out = []
    for row in rows:
        if not row.is_combustion:
            continue
        name = row.name.lower()
        addr = row.site_address.lower()
        hit = next((o for o in operators
                    if o["token"].lower() in name or o["token"].lower() in addr),
                   None)
        gens = []
        if row.names_a_data_centre:
            gens.append("dc_in_name")
        if hit and hit["token"].lower() in name:
            gens.append("operator_name")
        elif hit:
            # The token is in the address, not the holder. Weaker about
            # who runs the site and stronger about where it is: "Kao Data
            # Campus" as the address of HARLOW OPERATIONS LIMITED says
            # which campus, and leaves the corporate relationship to be
            # established rather than assumed.
            gens.append("operator_address")
        if not gens:
            continue
        out.append(Candidate(
            row=row,
            generators=tuple(gens),
            operator=(hit or {}).get("operator"),
            kind=(hit or {}).get("kind"),
            matched_token=(hit or {}).get("token"),
        ))
    return sorted(out, key=lambda c: (c.row.name.lower(),
                                      c.row.permission_number))


# ---------------------------------------------------------------------------
# Reading a permit.
#
# The Environment Agency writes these to a template, and the template is
# why this can be deterministic rather than a deep read. Every permit
# opens with an "Introductory note" that says in prose what Schedule 1
# then says in a table: how many generators, at what rating, totalling
# what. Both are quoted; the total is taken from whichever states one.
#
# Regex rather than a model because the sentence is formulaic and a
# formula that stops matching should fail loudly, not be smoothed over by
# something that will guess. Where no pattern matches, the permit is
# reported as unread and goes to the escalation list — an honest gap
# rather than an invented figure.

# Every "<number> MW" / "MWth", found with its position so the sentence
# around it can be read.
_MW_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:MW\s*\(?th\)?|MWth|MW)\b", re.I)

# Wording that makes a figure an aggregate rather than one engine's
# rating. Permits put it on either side: "aggregated total combustion
# capacity on site is approximately 260MWth", but also "(approximately
# 120MWth in total)".
_AGGREGATE_BEFORE = re.compile(
    r"(?:aggregat\w*|combined|total)\b[^.]{0,70}$", re.I)
_AGGREGATE_AFTER = re.compile(
    r"^[^.]{0,30}?\b(?:in total|in aggregate|aggregate|total)\b", re.I)

# What a per-engine rating looks like immediately *before* the number —
# the reason a figure in an aggregate-worded sentence still may not be
# the aggregate. Ark's Spring Park permit is one sentence reading "The
# total thermal input of the 33 standby generators is 5 generators of
# 3.9 MWth ... (approximately 120MWth in total)", and 3.9 sits inside
# "total" wording while being the smallest engine on the site.
_ENGINE_LEAD = re.compile(
    r"(?:\d\s*(?:x|×)\s*|generators?\s+(?:of|at|rated at|each of)\s*|"
    r"thermal input of\s*|capacit(?:y|ies)[^.]{0,20}?:\s*)$", re.I)

# "69 diesel fuelled standby generators", "33 standby generators",
# "14 generator sets", "comprises 12 x diesel generators". The lookbehind
# keeps the count out of a decimal: without it "21 x 8.877 MWth gas oil
# fuelled standby generators" reports a fleet of 877.
_COUNT_RE = re.compile(
    r"(?<![\d.])\b(\d{1,3})\s+(?:x\s+)?[\w\s\-,.]{0,40}?"
    r"generator(?:\s+set)?s\b", re.I)

# "36 of the generators have a thermal input of 2.71MWth",
# "24 generators at 5.38MWth", "12 x 8.01 MWth", "5 generators of 3.9 MWth".
#
# Two allowances for what the permits actually contain rather than what
# they ought to. The unit may run straight into the next word — Equinix's
# Slough permit prints "13 X 5.714 MWthgenerators" — so the unit is not
# followed by a word boundary. And a stray "th" may sit between the
# number and the unit: the same permit prints "2 X 6.857th MWth". Both
# groups were silently dropped before, and dropping them made a
# 331.084 MWth fleet read as 243.088.
_ENGINE_RE = re.compile(
    r"\b(\d{1,3})\s*(?:x|×|of the generators?[^.\d]{0,40}?|"
    r"generators?\s*(?:at|of|each\s+of|rated\s+at)?\s*)"
    r"\s*(\d{1,3}(?:\.\d+)?)\s*(?:th\s+)?(?:MW\s*\(?th\)?|MWth|MW)(?![\d.])",
    re.I)

# "N+1", "2N", "N+2" — how much of the fleet is spare, and so how much of
# it the site's load actually accounts for.
_REDUNDANCY_RE = re.compile(r"\b(2\s*N|N\s*\+\s*\d)\b")

# "across four sites", "across 3 data centres" — a permit whose figure
# covers more than one installation.
_MULTI_SITE_RE = re.compile(
    r"\bacross\s+(\w+)\s+(?:sites?|data\s?centres?|campuses|buildings)\b",
    re.I)

# How far a stated total may sit from the sum of the per-engine ratings
# and still be the same claim. The permits say "approximately" and round
# 259.62 to 260; they do not round it to 120.
TOTAL_TOLERANCE = 0.05


@dataclass
class PermitReading:
    slug: str
    permission_number: str
    total_mwth: float | None = None
    total_quote: str | None = None
    total_page: int | None = None
    generator_count: int | None = None
    engines: list[tuple[int, float]] = field(default_factory=list)
    engines_quote: str | None = None
    engines_page: int | None = None
    redundancy: str | None = None
    corroboration: str | None = None
    covers_sites: str | None = None

    @property
    def engines_total_mwth(self) -> float | None:
        """What the per-engine breakdown adds up to."""
        if not self.engines:
            return None
        return round(sum(n * mw for n, mw in self.engines), 3)


def _flat(text: str) -> str:
    """The permits wrap hard mid-sentence, and a line-based reader stops
    at the wrap. Whitespace-normalising first is what makes a quote a
    sentence rather than a line."""
    return re.sub(r"\s+", " ", text).strip()


def _sentence_span(text: str, start: int, end: int) -> str:
    """The smallest run of whole sentences covering [start, end).

    Used for the per-engine quote, because permits split a fleet across
    several sentences and bullets — "The standby emergency generators
    comprise: - 30 generators at 5.52MWth; - 6 generators at ..." — and a
    quote covering only the first line would under-count the fleet while
    looking complete.

    Sentences end at a full stop followed by a space and a capital or a
    digit. Deliberately not at a semicolon (the bullets use them) and not
    at any full stop (the ratings are decimals).
    """
    boundary = re.compile(r"(?<=[.])\s+(?=[A-Z0-9•\-])")
    left = 0
    for m in boundary.finditer(text, 0, start + 1):
        left = m.end()
    right = len(text)
    m = boundary.search(text, end)
    if m:
        right = m.start() + 1
    return text[left:right].strip()


def _read_page(page: str, out: "PermitReading", n: int) -> None:
    text = _flat(page)
    if not out.engines:
        ms = list(_ENGINE_RE.finditer(text))
        if ms:
            out.engines = [(int(m.group(1)), float(m.group(2))) for m in ms]
            out.engines_quote = _sentence_span(text, ms[0].start(),
                                               ms[-1].end())
            out.engines_page = n
    if out.redundancy is None:
        for m in _REDUNDANCY_RE.finditer(text):
            around = text[max(0, m.start() - 120):m.end() + 120].lower()
            if "redundan" in around:
                out.redundancy = re.sub(r"\s+", "", m.group(1)).upper()
                break


def _stated_totals(pages: list[str]) -> list[tuple[float, str, int]]:
    """Every megawatt figure the document presents as an aggregate.

    A figure qualifies if aggregate wording runs up to it, or "in total"
    follows it, and it is not led by an engine-list marker. That last
    condition is the one that matters: without it the first rating in a
    sentence beginning "The total thermal input of the 33 standby
    generators is 5 generators of 3.9 MWth" reads as the site total.
    """
    out = []
    for n, page in enumerate(pages, start=1):
        text = _flat(page)
        for m in _MW_RE.finditer(text):
            before = text[max(0, m.start() - 90):m.start()]
            after = text[m.end():m.end() + 40]
            if _ENGINE_LEAD.search(before):
                continue
            if not (_AGGREGATE_BEFORE.search(before)
                    or _AGGREGATE_AFTER.search(after)):
                continue
            value = float(m.group(1).replace(",", ""))
            out.append((value, _sentence_span(text, m.start(), m.end()), n))
    return out


def read_permit_text(pages: list[str], slug: str,
                     permission_number: str) -> PermitReading:
    """Total thermal input and the per-engine breakdown, with the verbatim
    sentences they came from and the pages those are on.

    The stated total is the claim, because it is what the document says.
    The per-engine breakdown is read alongside it as a check, and the two
    are compared: agreement is recorded, and so is disagreement. A
    disagreement is a flag on the claim, not a reason to prefer our
    arithmetic to the permit's own figure. It has meant three different
    things so far: a fleet listed across several named data centres in
    one paragraph (Equinix Slough), boilers counted into the total but
    not into the generator list (Equinix LD8), and a schedule that
    authorises more plant than is installed (Telehouse Docklands, 93.6
    MWth now and 145 MWth if the expansion is taken up).

    Where a permit lists engines and states no total, the sum is the
    claim and says so. Where it does neither, there is no claim: an MCP
    registration often carries no schedule, and a permit that states
    nothing should produce nothing.
    """
    out = PermitReading(slug=slug, permission_number=permission_number)
    for n, page in enumerate(pages, start=1):
        _read_page(page, out, n)

    totals = _stated_totals(pages)
    esum = out.engines_total_mwth
    if totals:
        agree = [t for t in totals
                 if esum and abs(t[0] - esum) <= TOTAL_TOLERANCE * esum]
        chosen = agree[0] if agree else max(totals)
        out.total_mwth, out.total_quote, out.total_page = chosen
        if agree:
            out.corroboration = (
                f"the per-engine ratings sum to {esum} MWth, which agrees "
                f"with the stated total")
        elif esum:
            out.corroboration = (
                f"the stated total is {chosen[0]} MWth and the per-engine "
                f"ratings read from this document sum to {esum} MWth; the "
                f"two do not agree, and why is worth reading the permit "
                f"for — Telehouse Docklands states 93.6 MWth for 19 "
                f"generators and schedules 27, the difference being an "
                f"expansion the permit already authorises")
        else:
            out.corroboration = ("no per-engine breakdown was found, so the "
                                 "stated total is unchecked")
    elif esum:
        out.total_mwth = esum
        out.total_quote = out.engines_quote
        out.total_page = out.engines_page
        out.corroboration = (
            "the document states no total; this is the sum of the "
            "per-engine ratings it lists, and is a floor if the list "
            "continues beyond the quoted passage")

    # The fleet size is read out of the sentence that states the figure,
    # not off whichever page mentioned generators first: a count taken
    # from a cover page or a definitions table is a number about nothing.
    for quote in (out.total_quote, out.engines_quote):
        m = _COUNT_RE.search(quote or "")
        if m:
            out.generator_count = int(m.group(1))
            break

    # A permit can cover more than one site. NTT's Hemel Hempstead permit
    # states "64 emergency standby generators across four sites" — a
    # figure that must not be attached to one of them as though it
    # described that one. Flagged here so the adjudication cannot miss it.
    for quote in (out.total_quote, out.engines_quote):
        m = _MULTI_SITE_RE.search(quote or "")
        if m:
            out.covers_sites = m.group(1).lower()
            break
    return out


# ---------------------------------------------------------------------------
# Rendering support, shared with dcp.capacity_claims so the artefacts
# cannot describe a thermal figure two different ways.

QUANTITY_LABEL = "rated thermal input"

QUANTITY_CAVEAT = (
    "The rated thermal input of the site's standby generators, from its "
    "environmental permit. It is fuel burned, not electricity delivered, "
    "and not what the site draws from the grid: a fleet is sized to carry "
    "peak load plus redundancy, and roughly 2.4 to 2.5 units of thermal "
    "input produce one of electrical output. It bounds a site's demand "
    "rather than stating it. Plant of 1–5 MWth needs no permit until "
    "1 January 2029, so an absent permit proves nothing.")

SOURCE_TITLE = "Environment Agency public register"


# ---------------------------------------------------------------------------
# From permits to claims.
#
# The shape is the NESO register's, not Companies House's: nothing here is
# transcribed by hand, because unlike a scanned filing these documents
# carry a text layer and the sentence that states the figure can be
# quoted verbatim and checked. So the claims are derived at load time from
# the committed page text, and the only hand-written file is the matches —
# which permit belongs to which site, and why.

MATCHES_PATH = EXTERNAL / "ea-permit-matches.yaml"

STAGE = "permitted standby generation"

# Which attachment a claim is read from, best first. A variation notice
# supersedes the permit it varies, so where both exist the variation is
# the current statement of what is permitted. The decision document is
# never read for a figure: it explains a decision rather than setting
# out the schedule, and the two can disagree by design.
DOCUMENT_PREFERENCE = ("variation", "permit", "other")


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def permit_pages(stem: str, text_dir: Path = TEXT_DIR) -> list[str]:
    """The committed text of one document, in page order."""
    pages, n = [], 1
    while (text_dir / f"{stem}-p{n}.txt").exists():
        pages.append((text_dir / f"{stem}-p{n}.txt").read_text())
        n += 1
    return pages


def _site_name(entry: dict) -> str:
    """The register's own name for the installation.

    Site Address repeats the installation name before the street — "A57,
    Cody Park, Cody Park Data Centre, Cody Park Data Centre, Old Ively
    Road, Farnborough, Hampshire, GU14 0LH" — so the components before
    the first one that looks like a street carry it. Deduplicated in
    order, joined back, and left otherwise verbatim: the repetition is
    the register's, and "Hayes Data Centre Emergency Back-up Generation
    Facility" is what it calls that installation whether or not a shorter
    name would read better.
    """
    parts = [p.strip() for p in entry["site_address"].split(",") if p.strip()]
    street = re.compile(r"\b(road|lane|street|way|avenue|drive|close|estate|"
                        r"park(?:way)?|industrial|business|boulevard|"
                        r"crescent|gardens|place|court|square|hill)\b", re.I)
    head = []
    for p in parts:
        if head and street.search(p):
            break
        head.append(p)
    seen, keep = set(), []
    for p in head:
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        keep.append(p)
    name = ", ".join(keep) or parts[0]
    # Some addresses carry the permit number inside the name; it is added
    # explicitly below, so strip a duplicate rather than print it twice.
    name = re.sub(r"\s*[-–]?\s*EPR/\w+(?:/\w+)?\s*", " ", name)
    name = re.sub(r"\s*/\s*A\d{3}\b", "", name)
    return re.sub(r"\s{2,}", " ", name).strip(" ,-/")


# Every permit repeats a running header on each page: "Permit number
# EPR/VP3235DJ 2 Cody Park Data Centre Permit number EPR/VP3235DJ". The
# text between the page number and the second "Permit number" is the
# Environment Agency's own name for the installation, and it is better
# than anything derivable from the address — "Cody Park Data Centre"
# rather than "A57", "Spring Park Data Centre" rather than "Ark Data
# Centres", "Union Park" rather than "Bulls Bridge Industrial Estate".
#
# A variation notice heads its pages the same way but opens with
# "Variation and consolidation application number" instead, which is why
# both are matched: without the second form, Virtus's Stockley Park
# campus is named after the business park it stands on.
_PERMIT_TITLE_RE = re.compile(
    r"(?:Permit number|Variation and consolidation application number)"
    r"\s+EPR/\w+(?:/\w+)?\s+\d{1,3}\s+(.{2,90}?)\s+Permit number",
    re.I)

# Boilerplate that turns up where a title should be when a permit's first
# pages are a covering notice rather than the permit body.
_NOT_A_TITLE = re.compile(
    r"environmental permitting|regulations|this introductory|"
    r"schedule|notice is", re.I)


def permit_title(pages: list[str]) -> str | None:
    """The installation's name as the permit itself heads its pages."""
    for page in pages[:4]:
        m = _PERMIT_TITLE_RE.search(_flat(page))
        if not m:
            continue
        title = re.sub(r"^(?:OFFICIAL\s+)+", "", m.group(1).strip(), flags=re.I)
        if title and not _NOT_A_TITLE.search(title):
            return title.strip(" ,-")
    return None


def claim_name_for(entry: dict, title: str | None = None) -> str:
    """Unique, and readable enough to appear in a reader panel.

    The permit number is part of the name rather than only a locator: an
    operator can hold several permits at one postcode, and a claim named
    for the site alone would collide with itself.
    """
    return f"{title or _site_name(entry)} ({entry['permission_number']})"


def load_ea_claims(manifest: dict | None = None,
                   text_dir: Path = TEXT_DIR) -> list[FiledClaim]:
    """One claim per permit that states a total thermal input.

    A permit with no readable total produces no claim. That is the
    honest outcome and not a gap to be filled by a model: an MCP
    registration often carries no schedule at all, and inventing a figure
    for one would be worse than the silence.
    """
    manifest = manifest if manifest is not None else load_manifest()
    out = []
    for slug, entry in sorted(manifest.items()):
        docs = {d.get("kind"): d for d in entry.get("documents", [])}
        doc = next((docs[k] for k in DOCUMENT_PREFERENCE if k in docs), None)
        if not doc:
            continue
        pages = permit_pages(doc["stem"], text_dir)
        reading = read_permit_text(pages, slug, entry["permission_number"])
        if reading.total_mwth is None:
            continue
        title = permit_title(pages)
        as_at = _date(entry.get("permission_date"))
        attrs = {
            "permission_number": entry["permission_number"],
            "permit_title": title,
            "holder": entry["holder"],
            # "unattributed" is a note to a reader, not a company. Left
            # null so that every consumer keyed on the operator falls
            # back to the permit holder, which is what the register
            # actually says.
            "operator": (None if entry.get("operator") == "unattributed"
                         else entry.get("operator")),
            "operator_kind": entry.get("kind"),
            "candidate_generators": entry.get("generators"),
            "activity": entry.get("activity"),
            "postcode": entry.get("postcode"),
            "local_authority": entry.get("local_authority"),
            "easting": entry.get("easting"),
            "northing": entry.get("northing"),
            "generator_count": reading.generator_count,
            "engines": [[n, mw] for n, mw in reading.engines],
            "engines_count": (sum(n for n, _ in reading.engines)
                              if reading.engines else None),
            "engines_total_mwth": reading.engines_total_mwth,
            "redundancy": reading.redundancy,
            "covers_sites": reading.covers_sites,
            "corroboration": reading.corroboration,
            # True where the document states no total and the figure is
            # the sum of the ratings it does state. The quote check
            # verifies those differently — there is no total in the
            # sentence to find.
            "summed_from_engines": reading.total_quote is reading.engines_quote,
            "quote": reading.total_quote,
            "document_kind": doc["kind"],
            "document_title": doc["title"],
            "document_stem": doc["stem"],
            "document_sha256": doc["sha256"],
            "document_url": doc["url"],
            "source_document": doc["stem"],
            "attribution": ATTRIBUTION,
        }
        out.append(FiledClaim(
            source_key=SOURCE_KEY,
            company_name=entry["holder"],
            company_number="",
            claim_name=claim_name_for(entry, title),
            quantity_type="thermal_input",
            value=float(reading.total_mwth),
            unit="MWth",
            stage=(STAGE if doc["kind"] != "variation"
                   else STAGE + ", as varied"),
            as_at=as_at,
            locator=f"{doc['kind']} page {reading.total_page}",
            quote=reading.total_quote or "",
            url=f"https://www.gov.uk{entry['publication_path']}",
            company_level=False,
            attrs=attrs,
        ))
    return out


def load_ea_matches(path: Path = MATCHES_PATH) -> list[dict]:
    if not path.exists():
        return []
    return list((yaml.safe_load(path.read_text()) or {}).get("matches", []))


def verify_ea_quotes(claims: list[FiledClaim] | None = None,
                     text_dir: Path = TEXT_DIR) -> list[str]:
    """Every claim's sentence must still be on the page it cites.

    The same check the operator snapshots get, for the same reason: a
    figure that has moved should fail loudly rather than drift. Here it
    also guards the extractor — a regex that silently starts matching the
    wrong sentence would still produce a quote, and the quote is what a
    reporter would publish.
    """
    claims = claims if claims is not None else load_ea_claims()
    problems = []
    for c in claims:
        page = c.locator.rpartition(" page ")[2]
        f = text_dir / f"{c.attrs['document_stem']}-p{page}.txt"
        if not f.exists():
            problems.append(f"{c.claim_name}: no text for {c.locator}")
            continue
        flat = re.sub(r"\s+", " ", f.read_text())
        if re.sub(r"\s+", " ", c.quote) not in flat:
            problems.append(
                f"{c.claim_name}: quote not found on {c.locator}")
            continue
        blob = re.sub(r"[,\s]", "", c.quote)
        if c.attrs.get("summed_from_engines"):
            # No total to find, so check the arithmetic instead: every
            # rating that was added up has to be in the sentence, and
            # they have to add up to the figure.
            engines = c.attrs.get("engines") or []
            missing = [f"{n}x{mw:g}" for n, mw in engines
                       if _printed(mw) not in blob]
            if missing:
                problems.append(
                    f"{c.claim_name}: ratings not in the quote they were "
                    f"summed from: {', '.join(missing)}")
            total = round(sum(n * mw for n, mw in engines), 3)
            if abs(total - c.value) > 0.001:
                problems.append(
                    f"{c.claim_name}: {c.value} is not the sum of its own "
                    f"engine list ({total})")
        elif _printed(c.value) not in blob:
            problems.append(
                f"{c.claim_name}: {c.value} {c.unit} is not in its own quote")
    return problems


def _printed(value: float) -> str:
    return f"{value:f}".rstrip("0").rstrip(".")


def validate_ea(claims: list[FiledClaim], matches: list[dict]) -> list[str]:
    """Problems as strings; empty means the batch is loadable."""
    problems = []
    names = [c.claim_name for c in claims]
    dupes = {n for n in names if names.count(n) > 1}
    problems += [f"duplicate claim_name {n!r}" for n in sorted(dupes)]
    for c in claims:
        if c.quantity_type != "thermal_input":
            problems.append(f"{c.claim_name}: quantity {c.quantity_type!r}")
        if c.unit != "MWth":
            problems.append(f"{c.claim_name}: unit {c.unit!r}")
    for m in matches:
        if m["claim_name"] not in names:
            problems.append(f"match names no claim: {m['claim_name']!r}")
        if m["confidence"] not in CONFIDENCE_VOCAB:
            problems.append(f"{m['claim_name']}: confidence {m['confidence']!r}")
        if len(m.get("evidence", "").strip()) < 40:
            problems.append(f"{m['claim_name']}: evidence too thin to defend")
    return problems + verify_ea_quotes(claims)


# ---------------------------------------------------------------------------
# Where a permit is.
#
# Every candidate carries an easting and northing, and every site carries
# a latitude and longitude, so the two can be put on the same map. That
# is all this is for: proximity generates candidates for adjudication and
# never decides one. Testing the geography join by postcode on 2026-08-21
# produced 36 permit-site pairs with obvious false positives among them —
# one site record matched Telehouse, Global Switch *and* Interxion
# because its applications span several Docklands postcodes, another
# picked up four operators because it aggregates half of Slough. Where
# one site record holds several campuses, proximity is not identity.
#
# Implemented here rather than by adding a projection library, because
# one transform used for one purpose does not justify a dependency, and
# the arithmetic is fixed, published and testable against control points.

_AIRY_A, _AIRY_B = 6377563.396, 6356256.909  # Airy 1830, OSGB36
_WGS_A, _WGS_B = 6378137.000, 6356752.3141   # WGS84
_F0 = 0.9996012717                            # National Grid scale factor
_LAT0, _LON0 = 49.0, -2.0                     # true origin
_E0, _N0 = 400000.0, -100000.0                # false origin

# Helmert OSGB36 -> WGS84 (Ordnance Survey published parameters).
_TX, _TY, _TZ = 446.448, -125.157, 542.060
_RX, _RY, _RZ = 0.1502, 0.2470, 0.8421        # arc-seconds
_S = -20.4894e-6                              # scale


def osgb_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """British National Grid metres to (latitude, longitude) degrees.

    Airy 1830 inverse projection followed by the Ordnance Survey's
    published Helmert transform — good to a few metres, which is three
    orders of magnitude better than this needs to be.
    """
    e2 = 1 - (_AIRY_B ** 2) / (_AIRY_A ** 2)
    n = (_AIRY_A - _AIRY_B) / (_AIRY_A + _AIRY_B)
    lat0, lon0 = math.radians(_LAT0), math.radians(_LON0)

    lat = lat0
    m = 0.0
    for _ in range(64):
        lat = (northing - _N0 - m) / (_AIRY_A * _F0) + lat
        dl, sl = lat - lat0, lat + lat0
        m = _AIRY_B * _F0 * (
            (1 + n + 1.25 * n ** 2 + 1.25 * n ** 3) * dl
            - (3 * n + 3 * n ** 2 + 2.625 * n ** 3) * math.sin(dl) * math.cos(sl)
            + (1.875 * n ** 2 + 1.875 * n ** 3)
            * math.sin(2 * dl) * math.cos(2 * sl)
            - (35 / 24) * n ** 3 * math.sin(3 * dl) * math.cos(3 * sl))
        if abs(northing - _N0 - m) < 1e-5:
            break

    s, c, t = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = _AIRY_A * _F0 / math.sqrt(1 - e2 * s * s)
    rho = _AIRY_A * _F0 * (1 - e2) / (1 - e2 * s * s) ** 1.5
    eta2 = nu / rho - 1
    t2, t4, t6 = t ** 2, t ** 4, t ** 6
    sec = 1 / c

    vii = t / (2 * rho * nu)
    viii = t / (24 * rho * nu ** 3) * (5 + 3 * t2 + eta2 - 9 * t2 * eta2)
    ix = t / (720 * rho * nu ** 5) * (61 + 90 * t2 + 45 * t4)
    x = sec / nu
    xi = sec / (6 * nu ** 3) * (nu / rho + 2 * t2)
    xii = sec / (120 * nu ** 5) * (5 + 28 * t2 + 24 * t4)
    xiia = sec / (5040 * nu ** 7) * (61 + 662 * t2 + 1320 * t4 + 720 * t6)

    de = easting - _E0
    lat = lat - vii * de ** 2 + viii * de ** 4 - ix * de ** 6
    lon = lon0 + x * de - xi * de ** 3 + xii * de ** 5 - xiia * de ** 7

    # Airy 1830 geodetic -> cartesian, Helmert, WGS84 cartesian -> geodetic.
    def _to_xyz(la, lo, a, b):
        ee = 1 - (b * b) / (a * a)
        v = a / math.sqrt(1 - ee * math.sin(la) ** 2)
        return (v * math.cos(la) * math.cos(lo),
                v * math.cos(la) * math.sin(lo),
                (1 - ee) * v * math.sin(la))

    x1, y1, z1 = _to_xyz(lat, lon, _AIRY_A, _AIRY_B)
    rx, ry, rz = (math.radians(r / 3600) for r in (_RX, _RY, _RZ))
    x2 = _TX + (1 + _S) * x1 - rz * y1 + ry * z1
    y2 = _TY + rz * x1 + (1 + _S) * y1 - rx * z1
    z2 = _TZ - ry * x1 + rx * y1 + (1 + _S) * z1

    ee = 1 - (_WGS_B ** 2) / (_WGS_A ** 2)
    p = math.hypot(x2, y2)
    la = math.atan2(z2, p * (1 - ee))
    for _ in range(16):
        v = _WGS_A / math.sqrt(1 - ee * math.sin(la) ** 2)
        la_new = math.atan2(z2 + ee * v * math.sin(la), p)
        if abs(la_new - la) < 1e-12:
            la = la_new
            break
        la = la_new
    return math.degrees(la), math.degrees(math.atan2(y2, x2))


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))
