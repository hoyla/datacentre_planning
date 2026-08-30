"""A readable one-line proposal, lifted verbatim from the application.

Planning descriptions are written for the register, not for a reader. The
first words are almost always procedural — which condition is being
discharged, which permission is being varied, which reference is being
amended — and the sentence that says what is actually being built arrives
somewhere in the middle, if at all:

    Discharge of condition 20 - wildlife management plan - pursuant to
    13/00531/MAJOR; Hybrid planning application comprising 1) application
    for full planning permission for the development of two data centres
    and a gatehouse with associated highway works…

Truncating that to a table cell yields "Discharge of condition 20 -
wildlife management plan - pursuant to…", which tells a reporter nothing.
The useful clause is right there in the same string.

So this splits a description into clauses, scores each on whether it
describes a development rather than an administrative act, and returns
the best one. Across a site it scores every clause of every application
and picks the single best, which also solves the related problem — a site
whose original full application is one row among forty condition
discharges.

**The result is always verbatim.** It is a substring of what the council
published, never a paraphrase, so a reporter can quote it and the
provenance is the application itself. Nothing is generated, nothing is
inferred, and the original description is untouched and still shown in
full alongside. Where no clause describes a development — 42 sites have
nothing but condition discharges on record — the opening of the
description is returned unchanged rather than inventing a summary, and
the caller can see that from the returned flag.
"""

from __future__ import annotations

import re

# Openers that mark a clause as procedural. Matched at the start of a
# clause only: "variation of condition 2" as an opener is administrative,
# but "…for the variation of the approved scheme" mid-sentence is not.
_ADMIN = re.compile(
    r"^\s*(?:an?\s+)?("
    r"variation|discharge|to discharge|part discharge|partial discharge"
    r"|non[-\s]material|reserved matters|approval of (?:details|condition)"
    r"|application (?:for approval|pursuant|to replace|under section|submitted under)"
    r"|removal of condition|submission of|details? (?:pursuant|required|reserved|of)"
    r"|consultation (?:from|with)|out of borough|prior (?:notification|approval)"
    r"|certificate of|request for|screening opinion|scoping opinion"
    r"|eia (?:screening|scoping)|condition \d|conditions? \d"
    r"|amendment to|amend the|s\.?\s?73\b|section \d+[a-z]?\b|minor material"
    r"|compliance with|notification of|confirmation of|deed of|discharge of"
    r"|approval of|submission pursuant|further to"
    r")\b", re.I)

# Openers that mark a clause as describing a development.
_DEVELOPMENT = re.compile(
    r"^\s*(?:the\s+|a\s+|an\s+|proposed\s+)?("
    r"erection|construction|demolition|redevelopment|re[-\s]development"
    r"|development of|installation|provision of|change of use|conversion"
    r"|outline (?:planning )?(?:application|permission)|hybrid (?:planning )?application"
    r"|full planning (?:application|permission)|erection|extension|creation of"
    r"|replacement of|alterations?|refurbishment|demolition of|use of (?:the )?(?:land|site)"
    r"|proposed development|new \w+|build|siting of|laying out"
    r")\b", re.I)

# Subject matter that makes a clause worth showing over its neighbours.
_SUBJECT = re.compile(
    r"data\s?cent(?:re|er)|data\s+storage|digital infrastructure|server"
    r"|technology (?:park|campus)|substation|energy centre|switch\s?room"
    r"|generator|battery|compute|colocation|co-location|hyperscale", re.I)

# Quantities that indicate the scale of a scheme. Deliberately narrow:
# an earlier version also counted heights and item counts, and "28no 2m
# high lighting protection finials" then out-scored "construction of a
# Data Centre" at the same site. Floor area, land area and electrical
# capacity say how big a development is; the height of a finial does not.
_SCALE = re.compile(
    r"\d[\d,.]*\s?(?:sq\.?\s?m|sqm|m2|m²|hectares?|\bha\b|MW|MVA|GW|kVA)", re.I)

# The subject is the object of the development, rather than something
# already standing that the application merely attaches to.
_BUILDS_SUBJECT = re.compile(
    r"(?:erection|construction|development|redevelopment|provision|creation|"
    r"delivery)\s+of\s+(?:\S+\s+){0,8}?"
    r"(?:data\s?cent|technology (?:park|campus)|digital infrastructure|"
    r"energy centre|substation)", re.I)

# Works to something that already exists: an ancillary application, not
# the scheme itself. Clearing an existing building is the opposite — the
# start of a redevelopment — so the guard excludes that reading, which
# otherwise demoted every "demolition of existing buildings and erection
# of…" below the minor applications at the same site.
_ANCILLARY = re.compile(
    r"(?<!demolition of )(?<!removal of )(?<!replacement of )"
    r"(?<!clearance of )(?<!demolish )"
    r"existing\s+(?:data\s?cent(?:re|er)|building|facility|premises|"
    r"structure|unit|plant)", re.I)

# A planning reference, which is where the procedural half of a sentence
# usually ends and the descriptive half begins.
_REF = re.compile(
    r"\b(?:[A-Z]{1,4}[./])?\d{2,6}[/.]\d{3,6}(?:[/.][A-Z0-9]{1,8})*\b"
    r"|\b\d{2}/\d{4,5}/[A-Z]+\b", re.I)

# Register housekeeping that is never part of the proposal.
_NOISE = re.compile(
    r"\s*[-–—(\[]?\s*(?:amended|revised|additional|further)\s+"
    r"(?:plans?|drawings?|information|documents?)\s+(?:received|submitted)"
    r"[)\]]?\s*\.?\s*$|\s*\(?(?:as amended|re-?consultation|readvertis\w+)\)?\s*\.?\s*$",
    re.I)

# Clause boundaries. Semicolons and dashes separate the procedural
# preamble from the description far more reliably than full stops do,
# because these strings are rarely punctuated as sentences.
_SPLIT = re.compile(
    r"\s*(?:;|:|\s[-–—]\s|\.\s+(?=[A-Z])|\[|\]|\)\s+(?=[A-Z])"
    r"|\band\s+(?=[A-Z]))\s*")

_MIN_CLAUSE = 24          # shorter than this is a fragment, not a proposal
_TARGET = 200             # a clause longer than this is scored no better


def _clauses(text: str):
    """Candidate clauses, in the order they appear.

    Splits on the delimiters, then splits again after any planning
    reference: "…pursuant to 14/1190/OUT The re-development of the site…"
    has no delimiter at all between the procedure and the proposal.
    """
    for part in _SPLIT.split(text or ""):
        part = part.strip(" ,.-–—()[]")
        if not part:
            continue
        cuts, last = [], 0
        for m in _REF.finditer(part):
            if m.end() < len(part) - _MIN_CLAUSE:
                cuts.append(part[last:m.start()].strip(" ,.-–—()[]"))
                last = m.end()
        cuts.append(part[last:].strip(" ,.-–—()[]"))
        for c in cuts:
            if len(c) >= _MIN_CLAUSE:
                yield c


def score(clause: str) -> float:
    """How much this clause reads like a description of a development.

    Positive means it describes something being built; zero or below
    means it describes a procedural step. The weights are ordinal rather
    than calibrated — all that matters is the ranking within one site.
    """
    s = 0.0
    if _DEVELOPMENT.match(clause):
        s += 6
    if _ADMIN.match(clause):
        s -= 8
    if _SUBJECT.search(clause):
        s += 4
    if _BUILDS_SUBJECT.search(clause):
        s += 3.5
    if _ANCILLARY.search(clause):
        s -= 4
    if _SCALE.search(clause):
        s += 1.5
    # A clause that is mostly condition numbers is a list, not a proposal.
    s -= 1.2 * len(re.findall(r"\bconditions?\s+\d", clause, re.I))
    s -= 0.8 * len(_REF.findall(clause))
    # More closing brackets than opening ones means the clause began in
    # the middle of someone else's parenthesis: a fragment, not a summary.
    s -= 3 * (clause.count(")") > clause.count("("))
    # Prefer the informative over the terse, but stop rewarding length
    # once the clause is longer than a table cell can show anyway.
    s += min(len(clause), _TARGET) / 90
    return s


def best_clause(text: str) -> tuple[str, float]:
    """The highest-scoring clause in one description, and its score."""
    best, best_s = "", float("-inf")
    for c in _clauses(text or ""):
        sc = score(c)
        if sc > best_s:
            best, best_s = c, sc
    return best, best_s


def summarise(descriptions) -> tuple[str, bool, int | None]:
    """(one-line proposal, whether it describes a development, source).

    Scores every clause of every description given — pass all of a site's
    applications — and returns the best. The second value is False when
    nothing on record describes a development, which happens when a site
    is known only through condition discharges; the caller should say so
    rather than presenting the text as a summary.

    The third value is the index into `descriptions` of the text the
    clause was lifted from, or None when nothing usable was given. The
    clause is verbatim from exactly one application, so "which one" is
    part of its provenance — a caller can name and link the application
    rather than gesture at "an application below" (issue #256).
    """
    texts = [(i, _NOISE.sub("", (d or "").strip()))
             for i, d in enumerate(descriptions) if d]
    if not texts:
        return "", False, None
    best, best_s, best_i = "", float("-inf"), None
    for i, t in texts:
        c, sc = best_clause(t)
        if c and sc > best_s:
            best, best_s, best_i = c, sc, i
    if not best:
        i, longest = max(texts, key=lambda p: len(p[1]))
        return longest, False, i
    # A winning clause that still opens administratively means the site
    # has no descriptive text anywhere; say so rather than dressing it up.
    return best, not _ADMIN.match(best) and best_s > 0, best_i


def tidy(clause: str) -> str:
    """Sentence-case a clause that arrived shouting, and close its brackets."""
    c = (clause or "").strip()
    if not c:
        return c
    letters = [ch for ch in c if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.8:
        c = c.capitalize()
    elif c[0].islower():
        c = c[0].upper() + c[1:]
    if c.count("(") > c.count(")"):
        c += ")"
    return c


# ---------------------------------------------------------------------------
# Site names, as a reader should see them
# ---------------------------------------------------------------------------

# Registers and Barbour disagree about case: 178 of the 430 named sites
# arrive shouting ("SAUNDERTON DATA CENTRE - 4 VIRTUS DATA CENTRES") and
# the rest do not, so a list of them reads as two datasets stapled
# together. The design handoff sets every headline in sentence case.
#
# This changes nothing in the database. The register's own spelling is
# what is stored, exported and cited; this is the display rule the
# reader applies on the way out, the same way `tidy` is.

# Kept as they are, because lower-casing them would be a mistake rather
# than a style: an initialism, a compass point in a postcode, a unit, or
# a name its owner writes in capitals. The last is not the same kind of
# thing as the others — VIRTUS is not an abbreviation of anything, it is
# a brand's own spelling — but it fails the same way, coming back as a
# company's name written how the company does not write it.
_KEEP_CAPS = {
    "DC", "UK", "US", "EU", "GB", "IT", "AI", "HQ", "PLC", "LLP", "NHS",
    "BBC", "EE", "AWS", "IBM", "BT", "GW", "MW", "KW", "MVA", "KVA",
    "PV", "EV", "HGV", "CHP", "UPS", "HV", "LV", "EIA", "SUDS", "AONB",
    "SSSI", "SAC", "SPA", "M25", "II", "III", "IV",
    # Company and place initialisms that occur in this corpus's names.
    # Checked against the all-caps tokens the corpus actually contains,
    # not guessed: NTT and JVC are companies, MK is Milton Keynes, ONS
    # and AOC are the bodies of those names, RAF and MOD are estates.
    "NTT", "JVC", "MK", "ONS", "AOC", "RAF", "MOD", "EDF", "SSE", "RWE",
    "UKPN", "SSEN", "CBRE", "VDC", "GLP", "DP",
    # The brand styling: VIRTUS is how the operator writes its name, on its
    # website and in the group label this corpus already holds for it
    # (organisation_aliases.yaml). Title-cased it read "Virtus" — the
    # operator's name spelled the way the operator does not (Luke,
    # 2026-08-30). Checked, per the rule above: two live sites carry
    # the token in a derived Barbour title, and six Barbour projects.
    "VIRTUS",
}
# Deliberately not here: the single letters N, S, E and W. As a
# compass point one is worth keeping, but as the tail of an apostrophe
# it is not — "KING'S" came back "King'S" — and a postcode half that
# needs them carries a digit, which is kept anyway.
# Lower-cased inside a name, never at its start.
_SMALL = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or",
          "the", "to", "with", "from", "into", "per", "via"}


def _cap_word(word: str) -> str:
    """One whitespace-delimited token, title-cased through its punctuation.

    Split on the marks that join two words into one — hyphen, slash,
    apostrophe, full stop — so "KING'S" becomes "King's" rather than
    "King'S", and "DATA-CENTRE" becomes "Data-Centre".
    """
    out, part, sep = [], "", ""
    for ch in word:
        if ch in "-/.'’":
            out.append((part, sep)); part, sep = "", ch
        else:
            part += ch
    out.append((part, sep))
    built = ""
    for piece, mark in out:
        built += mark
        if not piece:
            continue
        if piece in _KEEP_CAPS or any(c.isdigit() for c in piece):
            built += piece
        elif mark and mark in "'\u2019" and len(piece) <= 2:
            # The tail of a possessive or a contraction: "KING'S" is
            # "King's", never "King'S". Two characters covers "'ll" and
            # "'re"; O'BRIEN is longer and capitalises normally.
            built += piece.lower()
        else:
            built += piece[:1].upper() + piece[1:].lower()
    return built


def title_case(name: str) -> str:
    """A site name in title case, leaving the parts already cased alone.

    Only tokens that arrive entirely in capitals are changed, so a name
    the register already cased keeps its own spelling — including the
    capitals inside it that a blanket `.title()` would destroy
    ("Land East Of South Mimms" stays; "NEWCASTLE UPON TYNE" in the
    middle of it does not). A token carrying a digit is left alone, which
    covers postcodes, plot numbers and "1GW".
    """
    words = (name or "").split()
    out = []
    for i, w in enumerate(words):
        if not w.isupper() or not any(c.isalpha() for c in w):
            out.append(w)
            continue
        cased = _cap_word(w)
        low = cased.lower().strip(",.")
        if i and low in _SMALL and w.strip(",.") not in _KEEP_CAPS:
            cased = cased.lower()
        out.append(cased)
    return " ".join(out)
