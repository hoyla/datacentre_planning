"""Project metadata from Planning Inspectorate project pages.

The NSIP energy layer arrived from PlanIt's scrape, which carries the
applicant, application type, coordinates and the full date sequence — but
not the project name. Ingested that way, 197 nationally significant
energy projects read as `EN020021`, `EN010050`, `EN0110029`: correct, and
unusable by a reporter.

The Planning Inspectorate's own project page supplies what is missing:

    AQUIND Interconnector
    Type of application: Electric Lines
    Name of applicant: AQUIND Limited
    Development of AQUIND Interconnector with a nominal net capacity of
    2000MW between Great Britain and France ...
    This project is at the decision stage.

The description is the valuable part. It routinely states capacity, which
makes it grid-capacity evidence for the energy layer obtainable without
touching a document — and a single DCO document set runs to thousands of
files, so that distinction is the whole reason this module exists.

Three things about the parsing. The page is a JavaScript service that
renders its content as flat prose rather than labelled markup, so the
fields are recovered from text after tag-stripping rather than from a
DOM structure; there is no JSON API (three plausible endpoints answer 404
or 500). Layouts vary — a project still in pre-application does not carry
a stage sentence — so every field is optional and a miss stores null
rather than a guess. And the capacity figures are lifted verbatim from
the description, never computed, so a reader can always see the sentence
the number came from.

What this module deliberately does NOT do is overwrite. The PlanIt values
stay exactly as fetched; everything found here is stored beside them
under `raw_metadata['pins_page']` with the URL and the time it was read.
Where both sources name an applicant, both are kept.
"""

from __future__ import annotations

import re

BASE = "https://national-infrastructure-consenting.planninginspectorate.gov.uk"

# Capacity as written. Bare numbers are ignored: "2000MW" is a capacity,
# "2000 homes" is not, and the unit is what distinguishes them.
_CAPACITY_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(MW|GW|MWh|GWh|kV)\b", re.I)

_STRIP_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Everything between the applicant line and the next structural marker.
# The applicant name and the description run together with no delimiter
# ("Horizon Nuclear Power Proposed new nuclear power station..."), so the
# block is captured whole and split afterwards using the applicant name
# we already hold from PlanIt.
#
# An earlier version required the description to open with one of a list
# of words and to end in a full stop. That silently dropped half the
# corpus: "Energy from Waste facility with a gross electrical output
# capacity of 65 MWe" opens with an unlisted word, and "New Nuclear Power
# Station" is a complete description with no full stop at all.
_BLOCK_RE = re.compile(
    r"Name of applicant:\s*(.{2,1400}?)\s*"
    r"(?:View the developer|Project stage|Project information|$)",
    re.S)


def project_url(reference: str) -> str:
    return f"{BASE}/projects/{reference}"


def _field(text: str, label: str) -> str | None:
    m = re.search(
        re.escape(label) + r":\s*(.{2,90}?)\s*"
        r"(?:Type of application|Name of applicant|Development|The |This |View |Project stage)",
        text)
    return m.group(1).strip() or None if m else None


def parse_project(html: str, applicant_hint: str | None = None) -> dict:
    """Fields from a project page. Every value is optional.

    Missing means the page did not present it in a shape this recognises;
    it never means the project lacks the attribute.

    `applicant_hint` is the applicant as PlanIt recorded it. The page runs
    the applicant name straight into the description with no separator, so
    knowing the name is what makes the two separable. Without the hint the
    block is still captured, under `description_raw`, rather than dropped.
    """
    body = _STRIP_RE.sub(" ", html)
    dev = re.search(
        r'href="(https?://(?!national-infrastructure-consenting)[^"]{6,160})"'
        r'[^>]*>\s*View the developer', body)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", body)).strip()

    out: dict = {}
    m = re.search(r"^(.{2,140}?)\s*-\s*Project information", text)
    if m:
        out["name"] = m.group(1).strip()
    for key, label in (("app_type", "Type of application"),
                       ("applicant", "Name of applicant")):
        v = _field(text, label)
        if v:
            out[key] = v
    m = _BLOCK_RE.search(text)
    if m:
        block = _WS_RE.sub(" ", m.group(1)).strip()
        desc = block
        for name in (applicant_hint, out.get("applicant")):
            if name and desc.lower().startswith(name.lower().strip()):
                desc = desc[len(name.strip()):].strip(" .,–—-")
                break
        # A block that is only the applicant name carries no description.
        if desc and desc != block.strip():
            out["description"] = desc
        elif desc:
            out["description_raw"] = desc
        source = out.get("description") or out.get("description_raw") or ""
        caps = [f"{n.replace(',', '')} {u.upper()}" for n, u in _CAPACITY_RE.findall(source)]
        if caps:
            # Deduplicated but order-preserving: a description repeating
            # "2000MW" twice is one figure, not two.
            out["capacity_mentions"] = list(dict.fromkeys(caps))
    m = re.search(r"This project is at the\s+(.{3,40}?)\s+stage", text)
    if m:
        out["stage"] = m.group(1).strip()
    m = re.search(r"Latest update\s*-\s*(\d{1,2} \w+ \d{4})", text)
    if m:
        out["latest_update"] = m.group(1)
    if dev:
        out["developer_site"] = dev.group(1)
    return out
