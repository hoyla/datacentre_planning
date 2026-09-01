"""The operator's own web pages for a site, curated and kind-labelled.

Issue #255: a site page links to what the scheme's promoters publish
about it. Every entry is hand-verified (the review sheet in
data/operator_pages_review/, Luke, 2026-08-30) and carries a `kind`,
because the pages speak to different audiences and routinely say
different things:

- ``corporate`` — the operator or developer marketing the asset to
  customers and investors. States the power figure almost without fail.
- ``consultation`` — the scheme's public-consultation presence,
  addressed to residents and interested parties (the tell is a stated
  consultation period). Almost never states the power figure.

That asymmetry is a finding of the audiences theme, not an accident of
sampling — five of the first five sites holding both kinds disclosed
MW on the corporate page and nothing on the consultation page — so the
kind must travel with the link: a reader clicking through should know
which audience they are about to read.

Consultation sites are campaign infrastructure and die when the
process closes; there is no register copy behind them. Capacity claims
lifted from either kind are snapshotted at claim time, and a
consultation page's *silence* on power is asserted only against a held
snapshot (a negative result needs a probe that could see).

The contract matches the other priors: an entry naming a site key that
is not live **fails the build** rather than silently not applying, and
a duplicate (site_key, url) is an error. `label` is optional and only
worth setting where one site carries several pages of the same kind
(Interxion's LON1/2/3, CyrusOne's LON4/LON5) so the links can be told
apart.
"""

from __future__ import annotations

from pathlib import Path

# Resolved against the package root, never the working directory. A
# relative default plus `load_pages`' empty-on-absent return is a
# silent disappearance: run a build from anywhere but the repository
# root and every operator and consultation link drops off the site
# pages, while `require_live` — written to stop a link silently
# ceasing to apply — has no keys to check and passes over the empty
# result.
# Same form as capacity_claims and green_claims, for the same reason.
ROOT = Path(__file__).resolve().parent.parent
PAGES_PATH = ROOT / "data" / "priors" / "operator_pages.yaml"

KINDS = ("corporate", "consultation")

KIND_LABELS = {
    "corporate": "Operator’s website",
    "consultation": "Public consultation website",
}


def load_pages(path: Path = PAGES_PATH) -> dict[str, list[dict]]:
    """site_key → [{url, kind, label}], in the file's order.

    Empty when the priors file is absent. Malformed entries raise:
    a prior that half-loads is worse than one that fails loudly.
    """
    import yaml
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    out: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for e in payload.get("pages") or []:
        key, url = str(e["site_key"]), str(e["url"]).strip()
        kind = str(e.get("kind", "")).strip()
        label = str(e.get("label", "")).strip()
        if kind not in KINDS:
            raise ValueError(
                f"operator_pages.yaml: {key} has kind {kind!r}; "
                f"known kinds are {', '.join(KINDS)}")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(
                f"operator_pages.yaml: {key} has a non-http url {url!r}")
        if (key, url) in seen:
            raise ValueError(
                f"operator_pages.yaml: duplicate page {url} for {key}")
        seen.add((key, url))
        out.setdefault(key, []).append(
            {"url": url, "kind": kind, "label": label})
    return out


def require_live(pages: dict[str, list[dict]], live_keys: set[str]) -> None:
    """Every page must attach to a live site, or the build stops.

    Same contract and same reason as site_aliases.require_live: a key
    changes when its cluster's anchor changes, and a link that quietly
    stopped applying would drop the operator's own account of a scheme
    from the one page a reporter reads.
    """
    unknown = sorted(k for k in pages if k not in live_keys)
    if unknown:
        raise ValueError(
            "operator_pages.yaml names sites that are not live: "
            + ", ".join(unknown)
            + " — repoint or remove the entry rather than letting the "
              "link silently stop applying")


def link_text(page: dict) -> str:
    """The reader-facing wording for one page's link.

    The kind is the load-bearing part — which audience the reader is
    about to join — so it is always stated; the label only disambiguates
    siblings of the same kind on one site.
    """
    text = KIND_LABELS[page["kind"]]
    if page["label"]:
        text += f" ({page['label']})"
    return text
