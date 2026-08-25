"""Does a model's citation actually appear in the text it cites?

One rule, in one place, because two callers need it and they must not
drift: `scripts/adjudicate_power.py` applies it before storing a verdict,
and `scripts/export_reader.py` applies it again before acting on one. A
boolean stored months ago was decided by whatever the gate was then; the
question a build has to answer is whether the citation stands now.
"""

from __future__ import annotations

import re

_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026)\s*")
# Below this a fragment carries no evidence — but ONLY where an ellipsis
# joins it to another, because that is the case where two short words
# could be stapled together into something the document does not say.
# A single short span is a plain substring check and was always fine:
# applied to those, this rule threw away 22 correct verdicts whose
# finding text is the whole of "No" or "Yes" — a form field answered,
# which is exactly what `not_a_finding` is for.
_MIN_FRAGMENT = 4


def verify_span(span: str, quote: str) -> bool:
    """Is `span` a verbatim run of `quote`, ignoring how it was wrapped?

    The findings gate's rule, applied to a classification rather than a
    figure: whitespace differs between a PDF's line breaks and a model's
    copy of them, so it is normalised on both sides; nothing else is.
    An empty span verifies against nothing.

    An ellipsis joins two runs that are both in the text. Every flag the
    label audit made on an unverified span turned out to be one of these
    — "'active cooling' ... passive design measures" — a citation form
    rather than an invention, rejected by a gate that could only see one
    contiguous run. Each fragment still has to appear verbatim, and they
    have to appear IN ORDER, so an ellipsis cannot be used to staple
    together two distant phrases into something the document does not
    say. Fragments shorter than four characters are refused, because "a
    ... the" would otherwise verify against anything.
    """
    if not span or not span.strip():
        return False
    flat = " ".join((quote or "").split())
    parts = [" ".join(p.split()) for p in re.split(r"\s*(?:\.\.\.|\u2026)\s*", span)]
    parts = [p for p in parts if p]
    if not parts:
        return False
    if len(parts) > 1 and any(len(p) < _MIN_FRAGMENT for p in parts):
        return False
    at = 0
    for part in parts:
        found = flat.find(part, at)
        if found < 0:
            return False
        at = found + len(part)
    return True
