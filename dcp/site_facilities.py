"""The facility roster for a site, hand-curated, with its sources.

The missing object in the capacity model is the facility (ROADMAP,
"The missing object is the facility, not a sharper site"): figures
attach to applications, applications aggregate to sites, and the thing
a figure is actually about — one building with one operator and one
identity — exists nowhere else in the model. This prior is that
relation, `site_adjacent_power`'s sibling in role: per site, the
facility roster with the source that names it, and per facility any
figure attribution a document or claim supports. Issue #247.

Two cautions bound the layer, and both are enforced here rather than
remembered. **A roster gives campus structure, never planning-figure
attribution** — an attribution either references a claim in the
external-claims store (the operator's own figure, snapshot-backed) or
a planning document by application and content hash; there is no way
to write "the roster says the planning figure is X". And **no
megawatt is ever restated into this file** — an attribution that
carries a value of its own is rejected, because a figure copied out
of its store is a figure that can move under us (the CyrusOne 8.72 →
9 lesson).

The contract matches the other priors: an entry naming a site key
that is not live **fails the build**, and a claim reference that
matches nothing in the claims files fails validation — a dangling
reference is the dead-key failure one level down.

Scope decisions — whether a campus's figures ever roll up, what its
table cell shows — live in `data/priors/campus_scope.yaml`, never
here. A roster is evidence a scope decision can cite; listing a
facility records that a source names it as part of the campus
associated with this site, not that the site's planning record
contains it.
"""

from __future__ import annotations

from pathlib import Path

FACILITIES_PATH = Path("data/priors/site_facilities.yaml")

IDENTITY_SOURCES = ("operator_roster", "planning_document", "barbour_title")

# What each identity source must carry to be citable.
_IDENTITY_REQUIRED = {
    "operator_roster": ("url", "date"),
    "planning_document": ("application", "document"),
    "barbour_title": ("ptno", "title"),
}

# Keys that would restate a figure into this file. Forbidden anywhere
# in an attribution: the value lives in the claims store or the
# document, and the attribution points at it.
_VALUE_KEYS = frozenset({"value", "mw", "value_mw", "value_number", "capacity"})


def load_facilities(path: Path = FACILITIES_PATH) -> dict[str, dict]:
    """site_key -> {"facilities": [...], "note": str}, in file order.

    Empty when the priors file is absent. Malformed entries raise: a
    prior that half-loads is worse than one that fails loudly.
    """
    import yaml
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    out: dict[str, dict] = {}
    for entry in payload.get("sites") or []:
        key = str(entry["site_key"])
        if key in out:
            raise ValueError(f"site_facilities.yaml: duplicate entry for {key}")
        note = str(entry.get("note", "")).strip()
        facilities = entry.get("facilities") or []
        if not facilities and not note:
            raise ValueError(
                f"site_facilities.yaml: {key} lists no facilities and gives "
                f"no note saying why — an empty entry must explain itself")
        seen_ids: set[str] = set()
        loaded = []
        for f in facilities:
            fid = str(f.get("id", "")).strip()
            if not fid:
                raise ValueError(f"site_facilities.yaml: {key} has a facility "
                                 f"with no id")
            if fid in seen_ids:
                raise ValueError(f"site_facilities.yaml: {key} lists facility "
                                 f"{fid} twice")
            seen_ids.add(fid)
            identity = f.get("identity") or []
            if not identity:
                raise ValueError(f"site_facilities.yaml: {key}/{fid} has no "
                                 f"identity source — every facility carries "
                                 f"the source that names it")
            for src in identity:
                kind = str(src.get("source", "")).strip()
                if kind not in IDENTITY_SOURCES:
                    raise ValueError(
                        f"site_facilities.yaml: {key}/{fid} identity source "
                        f"{kind!r}; known sources are "
                        f"{', '.join(IDENTITY_SOURCES)}")
                missing = [k for k in _IDENTITY_REQUIRED[kind]
                           if not str(src.get(k, "")).strip()]
                if missing:
                    raise ValueError(
                        f"site_facilities.yaml: {key}/{fid} {kind} identity "
                        f"is missing {', '.join(missing)} — a source that "
                        f"cannot be found again is not a source")
            for a in f.get("attributions") or []:
                forbidden = _VALUE_KEYS & set(a)
                if forbidden:
                    raise ValueError(
                        f"site_facilities.yaml: {key}/{fid} attribution "
                        f"carries {sorted(forbidden)} — no figure is ever "
                        f"restated here; reference the claim or the document "
                        f"that states it")
                if not str(a.get("kind", "")).strip():
                    raise ValueError(
                        f"site_facilities.yaml: {key}/{fid} attribution has "
                        f"no kind — what kind of quantity, in the source's "
                        f"own terms")
                has_claim = bool(str(a.get("claim", "")).strip())
                has_doc = bool(str(a.get("document", "")).strip())
                if has_claim == has_doc:
                    raise ValueError(
                        f"site_facilities.yaml: {key}/{fid} attribution must "
                        f"reference exactly one of a claim (by claim_name) "
                        f"or a planning document (by content hash)")
                if has_doc and not str(a.get("application", "")).strip():
                    raise ValueError(
                        f"site_facilities.yaml: {key}/{fid} document "
                        f"attribution names no application")
            loaded.append(f)
        out[key] = {"facilities": loaded, "note": note}
    return out


def require_live(facilities: dict[str, dict], live_keys: set[str]) -> None:
    """Every roster must attach to a live site, or the build stops.

    Same contract and same reason as site_aliases.require_live: a key
    changes when its cluster's anchor changes, and a roster that
    quietly stopped applying would drop the facility layer from the
    one place the capacity model records it.
    """
    unknown = sorted(k for k in facilities if k not in live_keys)
    if unknown:
        raise ValueError(
            "site_facilities.yaml names sites that are not live: "
            + ", ".join(unknown)
            + " — repoint or remove the entry rather than letting the "
              "roster silently stop applying")


def require_known_claims(facilities: dict[str, dict],
                         known_claim_names: set[str]) -> None:
    """Every claim reference must resolve, or validation stops.

    A dangling claim reference is the dead-key failure one level down:
    a claim renamed in the claims file would silently orphan the
    attribution that cites it.
    """
    missing = sorted({
        a["claim"]
        for entry in facilities.values()
        for f in entry["facilities"]
        for a in f.get("attributions") or []
        if str(a.get("claim", "")).strip()
        and a["claim"] not in known_claim_names})
    if missing:
        raise ValueError(
            "site_facilities.yaml references claims that no claims file "
            "holds: " + "; ".join(missing))
