"""A figure we assemble is not a figure a source states (#248).

An adjudicated site-capacity figure is the extractor's number, and the
extractor sometimes did the applicant's arithmetic for it: "1 x 1.25MWe
and 57 x 2.4MWe diesel generators" became 138.05 MW; "57 MW from Iver
and 50 MW from Laleham" became 107. The arithmetic is right. What was
wrong, until migration 035, is that the page rendered each exactly as a
figure the document states, with a verbatim quote beneath that does not
contain the number.

This module answers two questions about a (value, quote) pair:

* `stated(value_mw, value_original, quote)` — does any number in the
  quote state the value, in megawatts, in kilowatts or as the original
  value? The quote is read as written AND as repaired for the
  substrate's habits (decimal commas, split digits, a hyphen for a
  decimal point, OCR'd letters in numbers), and a reading only ever
  adds: the repair that joins "2 4MW" into "24MW" also joins
  "PUMP 1 50kW" into 150 kW, which hid 64 stated figures on the first
  2026-09-10 run.

* `derive(value_mw, quote)` — if not stated, is the value reached by an
  operation whose operands are in the quote? Three operations are
  admissible (Luke, 2026-09-10): every fleet the quote names summed
  (`fleet_sum`), two stated numbers multiplied (`product`), stated
  figures added (`sum`). A scaling or a midpoint is a choice the source
  did not make and is not derived; those go to a person's row.

`classify()` names the class for the report in scripts/computed_figures.py;
`guard()` is the write-time rule for the adjudication scripts: a value no
number in its quote states is admitted as site_capacity only with a
derivation, and is stored as `unclear` otherwise.
"""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass, field

from dcp import site_profile as sp

DERIVATION_VERSION = "derive-1.0"

_OCR_DIGITS = str.maketrans("SOIl", "5011")
_UNIT = r"(?:MW|kW|MVA|kVA|MWe|MWt|kWe)"
_WORD_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                "twelve": 12, "sixteen": 16, "twenty": 20}


def repair(quote: str) -> str:
    """The quote with the substrate's habits undone, so a stated figure
    reads as stated. Nothing here changes what the quote asserts."""
    t = quote or ""
    t = re.sub(r"(?<=\d),(?=\d{1,2}(?!\d))", ".", t)              # 1720,71 -> 1720.71
    t = t.replace(",", "")                                          # 2,500 -> 2500
    t = re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", t)                      # 1 250 -> 1250
    t = re.sub(r"(?<=\d)\s\.\s?(?=\d)|(?<=\d)\s(?=\.\d)", ".", t)    # 3 .3 -> 3.3
    t = re.sub(r"(?<=\d)-(?=\d\s?" + _UNIT + ")", ".", t)               # 19-9MW -> 19.9MW
    # "2 4MW" -> "24MW": a single digit, a space, then at most two more
    # digits and the unit. Not "135 150 kW", which is two figures — a
    # first draft joined those and turned 400 stated figures into
    # computed ones.
    t = re.sub(r"(?<!\d)(\d)\s(?=\d{1,2}\s?" + _UNIT + ")", r"\1", t)
    t = re.sub(r"\b([SOIl\d]*[SOIl][SOIl\d]*)(?=\s?" + _UNIT + ")",
               lambda m: m.group(1).translate(_OCR_DIGITS), t)      # SMW, 7OMW, ISMW
    for word, n in _WORD_COUNTS.items():                            # eight 25kW units
        t = re.sub(rf"\b{word}\b(?=\s+(?:x\s+|further\s+)?\d)", str(n), t, flags=re.IGNORECASE)
    return t


def readings(quote: str) -> list[tuple[str, str]]:
    """The quote as written and as repaired, each labelled. A repair only
    ever ADDS a reading and never replaces the original."""
    raw = " ".join((quote or "").split())
    out = [("as written", raw)]
    if raw.replace(",", "") != raw:
        out.append(("as written", raw.replace(",", "")))
    rep = repair(raw)
    if rep != raw:
        out.append(("repaired", rep))
    return out


def numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.005 * abs(b), 0.0005)


def _stated_in(value_mw: float, value_original, text: str) -> bool:
    ns = numbers(text)
    return any(close(n, value_mw) or close(n / 1000, value_mw)
               or close(n * 1000, value_mw)
               or (value_original is not None and close(n, float(value_original)))
               for n in ns)


def stated(value_mw: float, value_original, quote: str) -> bool:
    """Does any number in the quote, as written or as repaired, state the
    value in megawatts, in kilowatts or as the original value?"""
    return any(_stated_in(value_mw, value_original, t) for _, t in readings(quote))


@dataclass(frozen=True)
class Derivation:
    """How a value the quote does not state is reached from numbers it does."""
    operation: str                      # fleet_sum | product | sum
    operands: list[dict] = field(default_factory=list)
    text: str = ""                      # "1 × 1.25 MW + 57 × 2.4 MW = 138.05 MW"
    reading: str = "as written"         # which reading of the quote it was read from
    version: str = DERIVATION_VERSION

    @property
    def cls(self) -> str:
        return "A" if self.operation in ("fleet_sum", "product") else "B"


def _fmt(x: float) -> str:
    return f"{x:g}"


def _derive_in(value_mw: float, text: str, reading: str) -> Derivation | None:
    fleets = sp._fleets_disclosed(text)
    ns = numbers(text)
    if fleets and close(sum(c * r for c, r in fleets), value_mw):
        return Derivation(
            "fleet_sum",
            [{"count": c, "rating_mw": r} for c, r in fleets],
            " + ".join(f"{c} × {_fmt(r)} MW" for c, r in fleets) + f" = {_fmt(value_mw)} MW",
            reading)
    for c, r in fleets:
        if close(c * r, value_mw):
            return Derivation(
                "fleet_sum", [{"count": c, "rating_mw": r}],
                f"{c} × {_fmt(r)} MW = {_fmt(value_mw)} MW", reading)
    for a, b in itertools.permutations(ns, 2):
        if close(a * b, value_mw):
            return Derivation(
                "product", [{"value": a}, {"value": b}],
                f"{_fmt(a)} × {_fmt(b)} = {_fmt(value_mw)} MW", reading)
        if close(a * b / 1000, value_mw):
            return Derivation(
                "product", [{"value": a}, {"value": b, "unit": "kW"}],
                f"{_fmt(a)} × {_fmt(b)} kW = {_fmt(value_mw)} MW", reading)
    both = [(n / 1000, {"value": n, "unit": "kW"}) for n in ns] + \
           [(n, {"value": n, "unit": "MW"}) for n in ns]
    for k in (2, 3):
        for combo in itertools.combinations(both, k):
            if close(sum(v for v, _ in combo), value_mw):
                ops = [o for _, o in combo]
                return Derivation(
                    "sum", ops,
                    " + ".join(f"{_fmt(o['value'])} {o['unit']}" for o in ops)
                    + f" = {_fmt(value_mw)} MW", reading)
    return None


def derive(value_mw: float, quote: str) -> Derivation | None:
    """The first admissible derivation any reading of the quote reaches,
    the quote as written tried before the repaired one."""
    for reading, text in readings(quote):
        d = _derive_in(float(value_mw), text, reading)
        if d is not None:
            return d
    return None


# The report's classes (scripts/computed_figures.py). A and B are what
# `derive` returns; C and D are what it refuses, named for the reader.
def classify(value_mw: float, quote: str) -> str:
    d = derive(value_mw, quote)
    if d is not None:
        if d.operation == "fleet_sum":
            text = next((t for r, t in readings(quote) if r == d.reading), "")
            n_fleets = len(sp._fleets_disclosed(text))
            return ("A. a unit count times a rating, every fleet in the quote summed"
                    if len(d.operands) == n_fleets
                    else "A. a unit count times a rating, one fleet of several in the quote")
        if d.operation == "product":
            return "A. two stated numbers multiplied"
        return "B. a sum of stated figures"
    for _, text in readings(quote):
        ns = numbers(text)
        both = [n / 1000 for n in ns] + ns
        if len(ns) >= 2 and any(close((a + b) / 2, value_mw)
                                for a, b in itertools.combinations(both, 2)):
            return "C. the midpoint of a stated range"
        if any(close(n * f, value_mw) for n in both
               for f in (0.8, 0.9, 1.1, 1.25, 0.5, 2, 0.75, 5)):
            return "C. a stated figure scaled"
    return "D. no arithmetic on the quote reaches it"


# ---------------------------------------------------------------------------
# The record beside the adjudication, and the write-time guard
# ---------------------------------------------------------------------------

def record(cur, *, adjudication_id: int, finding_id: int, value_mw: float,
           d: Derivation) -> bool:
    """Append the derivation for one adjudication; a no-op if this version
    already has one. Returns whether a row was written."""
    cur.execute("""
        INSERT INTO figure_derivations (adjudication_id, finding_id, value_mw,
            operation, operands, operands_text, reading, derivation_version)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (adjudication_id, derivation_version) DO NOTHING""",
        (adjudication_id, finding_id, value_mw, d.operation,
         json.dumps(d.operands), d.text, d.reading, d.version))
    return cur.rowcount == 1


REFUSED_PREFIX = "[refused at write: no number in the quote states the value and no derivation reaches it] "


def guard(verdict: str | None, value_mw: float | None, value_original,
          quote: str, reasoning: str) -> tuple[str | None, str, Derivation | None]:
    """The rule at adjudication write. Returns (verdict, reasoning,
    derivation): a stated value passes untouched; a derivable one passes
    with its derivation to record beside the row; anything else is
    stored as `unclear` with the refusal in front of the model's own
    reasoning, so the abstention is visible and the model's sentence is
    kept. Only site_capacity verdicts with a value are examined."""
    if verdict != "site_capacity" or value_mw is None:
        return verdict, reasoning, None
    if stated(float(value_mw), value_original, quote):
        return verdict, reasoning, None
    d = derive(float(value_mw), quote)
    if d is not None:
        return verdict, reasoning, d
    return "unclear", (REFUSED_PREFIX + (reasoning or ""))[:600], None


def quote_for(cur, finding_id: int) -> str:
    """The finding's full evidence text — the adjudication scripts carry a
    truncated copy in their batch metadata, and a guard on a truncated
    quote would refuse figures the page states."""
    cur.execute("SELECT coalesce(evidence_text, '') FROM findings WHERE id = %s",
                (finding_id,))
    row = cur.fetchone()
    return row[0] if row else ""
