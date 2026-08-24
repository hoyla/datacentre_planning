"""Organisation identity by evidence, never by similarity.

`dcp/entities.py` already does the safe normalisations — legal suffixes,
centre/center, conjunctions, spacing — and stops there on purpose: the
SPV-per-site pattern in this sector means near-identical names are
routinely different companies, which is exactly the distinction an
ownership story turns on. What it cannot do is say that "Ark Estates 5
Ltd" is Ark Data Centres, or that "VDC LHR11 Limited" is Vantage. Those
are claims about corporate structure, and they need evidence: a Barbour
client/end-user record, a Companies House filing, a document that says
"a subsidiary of".

This module reads those claims from `data/priors/organisation_aliases.yaml`,
validates them, and answers one question: which group does this raw name
belong to? The raw name is never rewritten anywhere — the group label
sits beside it (workbook column, reader badge) with the evidence one
lookup away, per the third principle.

Two rules the loader enforces rather than trusts:

**Every member carries evidence.** An entry with a name and no source
is a guess with a YAML indent, and is rejected at load.

**Nothing takes effect until a person has confirmed it.** Members are
`proposed` or `confirmed`; the index the exporters use is built from
confirmed members only. A session, a batch (READER_REDESIGN_PLAN §5b) or
a research note can propose; the checkpoint confirms. Proposed entries
are still validated, so a proposal cannot be malformed when someone
comes to read it.

Relations are a closed set, because "X is Y" hides four different
facts: the same organisation under another legal form or spelling; a
subsidiary; a trading name; a special-purpose vehicle. The badge shows
the group; the relation is what a reporter needs before writing that
the group "is behind" the site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from dcp import entities

ROOT = Path(__file__).resolve().parent.parent
ALIASES_PATH = ROOT / "data" / "priors" / "organisation_aliases.yaml"

RELATIONS = frozenset({"same_organisation", "subsidiary_of", "trading_name_of", "spv_of"})
STATUSES = frozenset({"proposed", "confirmed"})
# `register` here means the COUNCIL PLANNING register, which is what the
# word means everywhere else in this project. A company register is
# named for itself — `companies_house`, or `cro` for the Irish Companies
# Registration Office — because "the source is the CRO, not Companies
# House" (Luke, 2026-08-24) and a provenance line that misnames its own
# source is worse than a vague one: someone will follow it.
SOURCES = frozenset({"barbour", "companies_house", "cro", "document",
                     "operator_website", "register", "reporter"})

# Which company register a `source` value speaks for, where it speaks
# for one. Used to check that evidence cited for a number comes from the
# register that number belongs to.
SOURCE_REGISTER = {"companies_house": "companies_house", "cro": "cro"}


class AliasError(ValueError):
    """The aliases file says something the loader will not accept."""


@dataclass(frozen=True)
class Evidence:
    source: str
    ref: str = ""          # Barbour project ref, company number, document id, URL
    quote: str = ""        # verbatim, where the source is a document
    note: str = ""
    date: str = ""
    site_key: str = ""     # when the evidence is about one site


# A company number, and the register it belongs to. Validated because
# this is a JOIN KEY — the newsroom's other datasets are tied together
# on it, so a malformed or mistyped number does not fail loudly, it
# silently attaches a site to the wrong company. Format is all that can
# be checked here; that the number is the RIGHT company is what the
# evidence beside it is for.
#
# The register travels WITH the number because the two registers
# overlap in shape and not in meaning (Luke, 2026-08-24, on Amazon Data
# Services Ireland): a Companies House number is eight digits, or two
# letters and six; an Irish CRO number is up to six digits, so CRO
# 123456 is a perfectly well-formed nothing in Companies House. A
# consumer joining on Companies House IDs must be able to filter the
# CRO rows out rather than half-match them, so the join key is the
# PAIR, and a bare number is never enough.
REGISTERS = {
    "companies_house": re.compile(r"^(?:[A-Z]{2}\d{6}|\d{8})$"),
    "cro": re.compile(r"^\d{1,6}$"),          # Ireland
}
DEFAULT_REGISTER = "companies_house"

# Kept: the Companies House pattern under its old name, for anything
# that imported it before the register existed.
COMPANY_NUMBER_RE = REGISTERS["companies_house"]


@dataclass(frozen=True)
class Member:
    name: str              # as the documents or Barbour write it — never rewritten
    relation: str
    status: str
    evidence: tuple[Evidence, ...]
    company_number: str = ""   # this entity's own, where it is known
    register: str = ""         # which register that number is in

    @property
    def key(self) -> str:
        return entities.canonical_key(self.name)


@dataclass(frozen=True)
class Group:
    group: str             # the display label
    note: str = ""
    members: tuple[Member, ...] = field(default_factory=tuple)
    company_number: str = ""   # the parent's, where the group has one
    register: str = ""

    def member_for(self, key: str) -> Member | None:
        for m in self.members:
            if m.key == key:
                return m
        return None


def _require(cond: bool, where: str, what: str) -> None:
    if not cond:
        raise AliasError(f"{where}: {what}")


class _StrictLoader(yaml.SafeLoader):
    """A YAML loader that refuses a repeated key.

    PyYAML keeps the LAST of two identical keys and says nothing, which
    in this file destroys evidence: a member given a second `evidence:`
    block — the natural way to write "and here is another source" —
    silently loses the first, and the file still shows both. Found
    2026-08-24 when Luke added a Companies House lookup beside a Barbour
    reference and the Barbour reference stopped existing.

    An append-only record cannot be one where appending deletes.
    """


def _no_duplicate_keys(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise AliasError(
                f"line {key_node.start_mark.line + 1}: '{key}' is given twice "
                f"in the same block. YAML keeps only the last one, so the "
                f"first would be lost — if you are adding evidence, add "
                f"another item to the existing list instead of a second "
                f"'{key}:' key")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def _company_number(raw: dict, where: str) -> tuple[str, str]:
    """The number and its register, checked against that register's shape.

    A number with no register named is a Companies House number, which
    is what the file held before Ireland appeared in it and what most
    entries will always be.
    """
    number = str(raw.get("company_number") or "").strip().upper()
    register = str(raw.get("register") or "").strip().lower()
    _require(not register or register in REGISTERS, where,
             f"register {register!r} is not one of {sorted(REGISTERS)}")
    if not number:
        return "", register
    register = register or DEFAULT_REGISTER
    shapes = {"companies_house": "eight digits, or two letters and six",
              "cro": "up to six digits"}
    _require(bool(REGISTERS[register].match(number)), where,
             f"company_number {number!r} is not a {register} number "
             f"({shapes[register]})")
    # Evidence that names a company register must name the one the
    # number is in. Luke, 2026-08-24, reading a worked example for an
    # Irish company: "in your example 'source: companies_house' is not
    # true — the source is the cro". A provenance line that misnames its
    # own source is worse than a vague one, because someone will follow
    # it to a register that has never heard of the company.
    for e in raw.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        src = str(e.get("source") or "").strip().lower()
        cited = SOURCE_REGISTER.get(src)
        _require(cited is None or cited == register, where,
                 f"the number is in the {register} register but evidence "
                 f"cites {src!r}. Cite the register the number is in — or, "
                 f"if the company really has a record in both, give each "
                 f"its own member")
    return number, register


def load_groups(path: Path = ALIASES_PATH) -> list[Group]:
    """Read and validate the file. Raises AliasError on the first problem."""
    doc = (yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)
           if path.exists() else None)
    groups_raw = (doc or {}).get("groups") or []
    groups: list[Group] = []
    seen_labels: set[str] = set()
    seen_keys: dict[str, str] = {}
    for gi, g in enumerate(groups_raw):
        where = f"group {gi + 1}"
        _require(isinstance(g, dict) and g.get("group"), where, "needs a 'group' label")
        label = str(g["group"]).strip()
        where = f"group '{label}'"
        _require(label not in seen_labels, where, "label appears twice")
        seen_labels.add(label)
        members: list[Member] = []
        for mi, m in enumerate(g.get("members") or []):
            mwhere = f"{where} member {mi + 1}"
            _require(isinstance(m, dict) and m.get("name"), mwhere, "needs a 'name'")
            name = str(m["name"]).strip()
            mwhere = f"{where} member '{name}'"
            relation = str(m.get("relation") or "").strip()
            _require(relation in RELATIONS, mwhere,
                     f"relation must be one of {sorted(RELATIONS)}, got {relation!r}")
            status = str(m.get("status") or "").strip()
            _require(status in STATUSES, mwhere,
                     f"status must be one of {sorted(STATUSES)}, got {status!r}")
            ev_raw = m.get("evidence") or []
            _require(bool(ev_raw), mwhere, "has no evidence; a name alone is a guess")
            evidence = []
            for ei, e in enumerate(ev_raw):
                ewhere = f"{mwhere} evidence {ei + 1}"
                _require(isinstance(e, dict), ewhere, "must be a mapping")
                source = str(e.get("source") or "").strip()
                _require(source in SOURCES, ewhere,
                         f"source must be one of {sorted(SOURCES)}, got {source!r}")
                _require(bool(e.get("ref") or e.get("quote")), ewhere,
                         "needs a ref or a quote — something a person can open")
                evidence.append(Evidence(
                    source=source, ref=str(e.get("ref") or ""),
                    quote=str(e.get("quote") or ""), note=str(e.get("note") or ""),
                    date=str(e.get("date") or ""), site_key=str(e.get("site_key") or "")))
            number, register = _company_number(m, mwhere)
            member = Member(name, relation, status, tuple(evidence), number,
                            register)
            _require(len(member.key) >= 3, mwhere, "name is too short to key")
            _require(member.key not in seen_keys, mwhere,
                     f"also listed under '{seen_keys.get(member.key)}' — one name, one group")
            seen_keys[member.key] = label
            members.append(member)
        gnumber, gregister = _company_number(g, where)
        groups.append(Group(label, str(g.get("note") or ""), tuple(members),
                            gnumber, gregister))
    return groups


def alias_index(groups: list[Group], *, confirmed_only: bool = True) -> dict[str, Group]:
    """Canonical key -> group, over confirmed members unless told otherwise."""
    index: dict[str, Group] = {}
    for g in groups:
        for m in g.members:
            if confirmed_only and m.status != "confirmed":
                continue
            index[m.key] = g
    return index


def group_for(name: str | None, index: dict[str, Group]) -> Group | None:
    """The group a raw organisation string belongs to, or None.

    Matching is by `entities.canonical_key`, so a member listed as
    'Vantage Data Centers Ltd' also catches 'Vantage Data Centres Limited'
    — the spelling and legal-form variants the key already treats as one.
    Anything further needs its own member entry with its own evidence.
    """
    if not name:
        return None
    e = entities.parse_entity(name)
    key = e.key if e else entities.canonical_key(name)
    return index.get(key)


def summary(groups: list[Group]) -> str:
    confirmed = sum(1 for g in groups for m in g.members if m.status == "confirmed")
    proposed = sum(1 for g in groups for m in g.members if m.status == "proposed")
    return (f"{len(groups)} groups, {confirmed} confirmed member{'s' if confirmed != 1 else ''}, "
            f"{proposed} proposed")
