"""Curated display names for sites whose derived name misleads.

The default display name is derived (Barbour title, else the lead
application's address) and can produce a name nobody uses for the
place — see data/priors/site_aliases.yaml for the cases and the
design, which is issue #169's. This module is the one loader both
exporters use, so the reader and the workbook cannot disagree about
what a site is called.

The contract matches the other priors: an alias naming a site key that
is not live **fails the build** rather than silently not applying. A
site key changes when its cluster's anchor changes, and an alias that
quietly stopped applying would put the misleading derived name back in
front of reporters with nothing to say it had happened.
"""

from __future__ import annotations

from pathlib import Path

ALIASES_PATH = Path("data/priors/site_aliases.yaml")


def load_aliases(path: Path = ALIASES_PATH) -> dict[str, str]:
    """site_key → alias. Empty when the priors file is absent."""
    import yaml
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text()) or {}
    out: dict[str, str] = {}
    for e in payload.get("aliases") or []:
        key, alias = str(e["site_key"]), str(e["alias"]).strip()
        if not alias:
            raise ValueError(f"site_aliases.yaml: empty alias for {key}")
        if key in out:
            raise ValueError(f"site_aliases.yaml: duplicate entry for {key}")
        out[key] = alias
    return out


def require_live(aliases: dict[str, str], live_keys: set[str]) -> None:
    """Every alias must attach to a live site, or the build stops."""
    unknown = sorted(k for k in aliases if k not in live_keys)
    if unknown:
        raise ValueError(
            "site_aliases.yaml names sites that are not live: "
            + ", ".join(unknown)
            + " — a key changes when its cluster's anchor changes; "
              "repoint or remove the entry rather than letting the "
              "alias silently stop applying")
