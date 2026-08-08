"""Canonical entity names from the prose the deep-read returns.

The party findings are the best-covered material in the corpus — 607
applications name an applicant, 617 name an adviser — and they answer the
question the adjacency work exists for: who is promoting these schemes,
and which consultants recur across them. But the model was asked for a
fact in a few words, not a database key, so one company arrives as:

    Applicant is Vantage Data Centers Ltd
    Vantage Data Centers Ltd is the applicant
    Applicant is Vantage Data Centers
    Vantage Data Centers Ltd is the applicant/client

Counting those as four developers would be worse than not counting at
all. This module reduces each to a display name and a canonical key, so
variants group while the original `value_text` stays untouched on the
findings row — the same principle as signal families.

Measured shapes across ~4,000 party values: a bare name dominates
(1,376), then `X is Y` (190), `X: Y` (152), `X (Y)` (112), `X prepared by
Y` (39), `X of Y` (29). The rules below follow that distribution rather
than an idea of how people ought to write.

Two things are deliberately NOT attempted. Fuzzy matching between
different-but-similar names ("Vantage Data Centers" vs "Vantage Data
Centres UK") is left alone: collapsing distinct legal entities in a
corporate-structure story would be a serious error, and the SPV-per-site
pattern common to data centres means near-identical names are often
genuinely different companies. And no attempt is made to resolve a person
to their firm beyond taking the firm when both appear — "Nick Heard of
Savills" becomes Savills, because the firm is the network node.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Role labels that wrap a name rather than being part of it. Matched at
# the start ("Applicant is X", "Agent: X") or the end ("X is the
# applicant", "X acting as planning agent").
_ROLES = (
    r"applicant(?:/client)?", r"agent", r"planning agent", r"consultant",
    r"planning consultant", r"client", r"developer", r"architect",
    r"author", r"engineer", r"contractor", r"operator", r"promoter",
    r"local planning authority", r"planning authority", r"authority",
    r"lpa", r"council", r"case officer", r"consultee", r"applicant name",
    r"agent name", r"landowner", r"appellant",
)
_ROLE_ALT = "|".join(_ROLES)

_PREFIX_RE = re.compile(
    rf"^\s*(?:the\s+)?(?:{_ROLE_ALT})\s*"
    rf"(?:is|are|was|were|identified as|named as|listed as|shown as|"
    rf"given as|recorded as|stated as|:|=|-|–)\s*(?:the\s+)?",
    re.I)
_SUFFIX_RE = re.compile(
    rf"\s*(?:,)?\s*(?:is|are|was|were|acting as|acts as|acted as|"
    rf"appointed as|named as|listed as|identified as|shown as|"
    rf"described as|serving as)\s+(?:the\s+)?(?:{_ROLE_ALT})\b.*$", re.I)
_PREPARED_RE = re.compile(
    r"\s*(?:prepared|submitted|produced|authored|written|made|lodged)\s+"
    r"(?:by|on behalf of|for)\s+", re.I)
# "AECOM prepared the Environmental Statement" — an arbitrary document
# name sits between the verb and the noun, so match up to the noun rather
# than requiring it to follow immediately.
_TRAILING_VERB_RE = re.compile(
    r"\s+(?:prepared|submitted|produced|authored|undertook|carried out|"
    r"completed|acted|acts|acting)\b.*$", re.I)
# Consultee lines name an officer and their body: "Ecology Consult
# (Internal) consultee: Mr Paul Howe, Hart District Council". The label
# before the colon is not the organisation.
_CONSULTEE_LEAD_RE = re.compile(
    r"^.*?\bconsultee\s*:\s*", re.I)

# "Emily Holton-Walsh of Arup" — the firm is the node worth counting.
#
# The leading part must look like a personal name, which means excluding
# organisational words: "The Council of the London Borough of Ealing" is
# not a person at a firm, and reading it as one both mangles the name and
# loses the authority flag.
_ORG_WORD_RE = re.compile(
    r"\b(?:council|borough|authority|corporation|agency|department|"
    r"government|ministry|inspectorate|trust|board|committee|society|"
    r"university|college|hospital|company|group|holdings?|partners?|"
    r"associates|consultants?)\b", re.I)
_PERSON_OF_FIRM_RE = re.compile(
    r"^(?P<head>[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})"
    r"\s+of\s+(?P<firm>.+)$")

# Legal forms, stripped for the grouping key only — never from display.
_LEGAL_SUFFIX_RE = re.compile(
    r"\b(?:limited|ltd|llp|llc|plc|inc|incorporated|holdings?|group|"
    r"uk|\(uk\)|international|company|co|partnership|"
    r"s\.?a\.?r\.?l|gmbh|bv|nv|as|ab)\b\.?", re.I)

_PUNCT_RE = re.compile(r"[^\w\s&]+")
_WS_RE = re.compile(r"\s+")

# Values that are a role with no name attached carry no entity at all.
_ROLE_ONLY_RE = re.compile(rf"^\s*(?:the\s+)?(?:{_ROLE_ALT})\s*$", re.I)

# An authority named in an adviser finding is a mis-assignment, not an
# adviser: the family came from the model's own signal_type label, which
# does not always match what the value turned out to describe.
_AUTHORITY_RE = re.compile(
    r"\b(?:city|county|borough|district|parish|town)\s+council\b|"
    r"\bcouncil\b|\bdevelopment corporation\b|"
    # "London Borough of Hillingdon" names no council but is one; without
    # this it sat among the advisers on 34 applications.
    r"\b(?:london\s+)?borough\s+of\b|\bcity\s+of\s+[A-Z]|"
    r"\benvironment agency\b|\bnatural (?:england|resources wales)\b|"
    r"\bhighways england\b|\bnational highways\b|\bhistoric england\b|"
    r"\bplanning inspectorate\b|\blocal planning authority\b|"
    r"\bcombined authority\b|\bgreater london authority\b", re.I)


@dataclass(frozen=True)
class Entity:
    display: str      # human-readable, close to how documents write it
    key: str          # canonical grouping key
    is_authority: bool


def _strip_roles(text: str) -> str:
    prev = None
    out = text.strip()
    # Iterate: "Applicant is X acting as agent" needs both ends removed,
    # and stripping one can expose another.
    while prev != out:
        prev = out
        out = _CONSULTEE_LEAD_RE.sub("", out).strip()
        out = _PREFIX_RE.sub("", out).strip()
        out = _SUFFIX_RE.sub("", out).strip()
        # "prepared by X" keeps X; "X prepared the report" keeps X. Try the
        # by-form first, since the trailing-verb rule would otherwise eat
        # the name that follows.
        parts = _PREPARED_RE.split(out)
        if len(parts) > 1 and parts[-1].strip():
            out = parts[-1].strip()
        else:
            out = _TRAILING_VERB_RE.sub("", out).strip()
    return out.strip(" .,;:-–—/")


def canonical_key(display: str) -> str:
    """Grouping key: case, punctuation, legal form and spacing removed.

    Legal suffixes go because 'Vantage Data Centers' and 'Vantage Data
    Centers Ltd' are the same company written two ways. They are stripped
    from the KEY only — the display name keeps whatever the document said.

    Three further normalisations, each added after seeing the same company
    split across the corpus, and each chosen because it cannot merge two
    genuinely different organisations:

    - `centre`/`center`: 'Vantage Data Centers Ltd' (69 applications) and
      'Vantage Data Centres Ltd' (26) are one company written in two
      Englishes.
    - conjunctions: 'Old Oak and Park Royal Development Corporation' (60)
      against 'Old Oak Park Royal Development Corporation' (19).
    - internal spacing: 'CityFibre' (70) against 'City Fibre' (32). Two
      distinct companies whose names differ only by a space do not
      meaningfully occur; the same name typed two ways does, constantly.

    Deliberately still NOT merged: different name forms of one firm, such
    as 'Arup' and 'Ove Arup & Partners Ltd'. Resolving those needs
    judgement about corporate structure, and the SPV-per-site pattern in
    this sector means near-identical names are often separate companies —
    exactly the distinction an ownership story turns on.
    """
    s = display.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = re.sub(r"\bcenters?\b", "centre", s)
    s = re.sub(r"\bcentres\b", "centre", s)
    s = _LEGAL_SUFFIX_RE.sub(" ", s)
    s = re.sub(r"\b(?:and|&)\b", " ", s)
    s = _WS_RE.sub("", s).strip()
    return s


def parse_entity(value_text: str | None) -> Entity | None:
    """One entity from a party finding's value_text, or None.

    None means the value carried no usable name — a bare role label, a
    fragment, or something too short to be a company.
    """
    if not value_text:
        return None
    text = _WS_RE.sub(" ", value_text).strip()
    if _ROLE_ONLY_RE.match(text):
        return None

    display = _strip_roles(text)

    # "Name: Company" and "Company (Trading Name)" both leave the useful
    # part after the separator or before the bracket respectively.
    if ":" in display:
        head, _, tail = display.partition(":")
        if tail.strip() and len(tail.strip()) >= 3:
            display = tail.strip() if _ROLE_ONLY_RE.match(head.strip()) \
                else display
    # Determined before any rewriting: "The Council of the London Borough
    # of Ealing" must stay flagged as an authority even though the words
    # that prove it sit in the part a naive rewrite would discard.
    is_authority = bool(_AUTHORITY_RE.search(display))

    m = _PERSON_OF_FIRM_RE.match(display)
    if m and not _ORG_WORD_RE.search(m.group("head")):
        display = m.group("firm").strip()
    display = re.sub(r"\s*\([^)]*\)\s*$", "", display).strip(" .,;:-–—/")

    if len(display) < 3 or not re.search(r"[A-Za-z]", display):
        return None
    key = canonical_key(display)
    if not key or len(key) < 3:
        return None
    return Entity(display=display, key=key,
                  is_authority=is_authority or
                  bool(_AUTHORITY_RE.search(display)))
