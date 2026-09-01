"""What an operator says about its power, beside what its sites disclose.

An operator's "100% renewable" claim and the on-site combustion its own
planning documents describe are both in this corpus, and neither is
worth much without the other. This module puts them in one row.

**It is built to resist the cheap reading, because the cheap reading is
wrong.** Four rules are enforced here rather than left to whoever
renders the table:

1. *The quote is the unit, not a boolean.* "100% renewable energy
   procurement" and "100% renewable energy powered" are different
   claims, and a column that flattened them would delete the finding.
   `kind` carries that distinction and every row carries the words.

2. *Generators existing is not generators running.* Standby plant is
   permitted at most 500 hours a year in emergency use, and the
   Environment Agency treats that threshold as the line below which
   emission limits do not apply. `REGULATORY_CAVEAT` says so and the
   renderers are required to show it.

3. *No permit is not no generators.* A permit is required only at
   50 MWth aggregated, so an operator missing from the permit register
   may simply be below it. `PERMIT_THRESHOLD_CAVEAT` says so.

4. *Counts are floors.* Generator counts come from
   `site_profile.generator_profile`, which takes the highest number
   disclosed in any one document, so phases described separately are
   not summed. Rendered as "at least N", never as N.

The direction of a mention decides its meaning, which is why the claims
file is curated and this module never infers a claim from a keyword:
Apatura's diesel passages argue for *eliminating* diesel, and counting
them as disclosure would invert the story. See the `considered` block
in data/external_sources/operator-green-claims.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from dcp import entities, organisations, site_profile

ROOT = Path(__file__).resolve().parent.parent
CLAIMS_PATH = ROOT / "data" / "external_sources" / "operator-green-claims.yaml"
SNAPSHOT_DIR = ROOT / "data" / "external_sources" / "operator_snapshots"

KINDS = ("procurement", "powered", "goal")

KIND_GLOSS = {
    "procurement": "buys renewable electricity",
    "powered": "describes the site as renewable-powered",
    "goal": "states a renewable or net-zero goal",
}

REGULATORY_CAVEAT = (
    "Standby generators existing is not standby generators running. These "
    "permits cap emergency operation at 500 hours a year, and the "
    "Environment Agency treats that as the emergency-only threshold: its "
    "own decision documents state that “Emission limit values (ELVs) "
    "to air are not applicable to MCPs operating less than 500 hours per "
    "year”. What the plant actually ran is reported to the Agency "
    "annually and is not published; this project has asked for it.")

PERMIT_THRESHOLD_CAVEAT = (
    "An environmental permit is required only where combustion plant "
    "reaches 50 MWth in aggregate. An operator with no permit may simply "
    "be below that threshold rather than free of on-site generation — "
    "Pulsant's entire disclosed estate is 22.12 MW of IT load. Absence "
    "from the permit column is not evidence of a cleaner site.")

COUNT_CAVEAT = (
    "Generator counts are floors: the highest number disclosed in any one "
    "of a site's documents, so phases described separately are not added "
    "together. They are not adjudicated for attribution, unlike the "
    "capacity figures.")


class GreenClaimError(ValueError):
    """The claims file is malformed, or a quote no longer verifies."""


@dataclass(frozen=True)
class GreenClaim:
    operator: str
    snapshot: str
    kind: str
    quote: str
    note: str = ""
    # The page the quote came from, read from the snapshot's own header
    # rather than repeated in the claims file: one source of truth for
    # where a snapshot came from, and it cannot drift from the file the
    # quote is verified against.
    source_url: str = ""

    @property
    def gloss(self) -> str:
        return KIND_GLOSS[self.kind]


@dataclass(frozen=True)
class OperatorRow:
    """One row of the table: the claim, and what the sites disclose."""
    claim: GreenClaim
    sites: tuple[str, ...] = ()            # site keys matched to the operator
    fuels: tuple[tuple[str, int], ...] = ()  # (label, sites mentioning it)
    generator_floor: int | None = None     # highest single-site disclosure
    chp_sites: int = 0                     # sites describing CHP, not standby
    permit_count: int = 0
    permit_mwth: float = 0.0
    permit_engines: int = 0

    @property
    def has_permit(self) -> bool:
        return self.permit_count > 0

    @property
    def generation_use(self) -> str:
        """Backup or primary, said carefully.

        CHP implies permanent generation with a heat offtake; everything
        else in this corpus is standby plant. Where a site describes
        both, both are named rather than the louder one winning.
        """
        if self.chp_sites and self.fuels:
            return "standby, and CHP at %d site%s" % (
                self.chp_sites, "" if self.chp_sites == 1 else "s")
        if self.chp_sites:
            return "CHP (permanent generation)"
        if self.fuels:
            return "standby / backup"
        # These two are not the same fact and must never render alike.
        # "No site matched" is a gap in this project's matching; "no
        # generation disclosed" is a statement about the documents. A
        # single "none" would let a reader take our silence for theirs.
        if not self.sites:
            return "no site matched to this operator"
        return "none disclosed in the matched site%s" % (
            "" if len(self.sites) == 1 else "s")

    @property
    def evidence_is_thin(self) -> bool:
        """True where the row says more about our coverage than theirs."""
        return not self.fuels


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def snapshot_url(snapshot: str, snapshot_dir: Path = SNAPSHOT_DIR) -> str:
    """The page a snapshot was taken from, from its `# url:` header."""
    from dcp.capacity_claims import snapshot_path

    f = snapshot_path(snapshot, snapshot_dir)
    if f is None:
        return ""
    for line in f.read_text(encoding="utf-8").splitlines()[:6]:
        if line.startswith("# url:"):
            return line.split(":", 1)[1].strip()
    return ""


def load_document(path: Path = CLAIMS_PATH) -> dict:
    import yaml
    return yaml.safe_load(path.read_text()) or {}


def load_claims(path: Path = CLAIMS_PATH) -> list[GreenClaim]:
    doc = load_document(path)
    out: list[GreenClaim] = []
    seen: set[str] = set()
    for c in doc.get("claims") or []:
        kind = str(c.get("kind", "")).strip()
        if kind not in KINDS:
            raise GreenClaimError(
                f"{c.get('operator')}: kind {kind!r} is not one of {KINDS}")
        op = str(c["operator"]).strip()
        if op in seen:
            raise GreenClaimError(f"duplicate operator {op!r}")
        seen.add(op)
        snap = str(c["snapshot"]).strip()
        out.append(GreenClaim(op, snap, kind, _norm(str(c["quote"])),
                              _norm(str(c.get("note", ""))),
                              snapshot_url(snap, path.parent / "operator_snapshots")))
    return out


def verify_quotes(claims: list[GreenClaim] | None = None,
                  snapshot_dir: Path = SNAPSHOT_DIR) -> list[str]:
    """Every quote must still appear in its committed snapshot."""
    from dcp.capacity_claims import snapshot_path

    problems = []
    for c in (claims if claims is not None else load_claims()):
        f = snapshot_path(c.snapshot, snapshot_dir)
        if f is None:
            problems.append(f"{c.operator}: snapshot {c.snapshot} is missing")
            continue
        if c.quote not in _norm(f.read_text(encoding="utf-8")):
            problems.append(
                f"{c.operator}: quote not found in {c.snapshot}.txt — the page "
                "may have changed; re-run scripts/fetch_operator_snapshots.py "
                "and re-read the wording")
    return problems


# The site's generation evidence, structured rather than rendered. The
# profile's `generator_fuel` is a display string ("Diesel (174
# mentions); also referenced: Gas") and parsing it back would be a
# second, divergent implementation of the ranking rule. This asks
# site_profile for the fuels themselves.
GENERATION_SQL = site_profile.GENERATOR_SQL


SITES_SQL = """
SELECT DISTINCT cl.attrs->>'operator' AS operator, s.site_key
FROM capacity_claim_matches m
JOIN capacity_claims cl ON cl.id = m.claim_id
JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
WHERE m.retired_at IS NULL
  AND cl.source_key = 'operator_website'
  AND cl.attrs->>'operator' IS NOT NULL
"""

PERMITS_SQL = """
SELECT cl.attrs->>'operator' AS operator, count(*),
       coalesce(sum(cl.value_original), 0),
       coalesce(sum((cl.attrs->>'engines_count')::int), 0)
FROM capacity_claims cl
WHERE cl.source_key = 'ea_permit' AND cl.attrs->>'operator' IS NOT NULL
GROUP BY 1
"""


def build_rows(conn, profiles: dict[str, dict],
               claims: list[GreenClaim] | None = None) -> list[OperatorRow]:
    """One row per loaded claim, joined to its sites' disclosures.

    `profiles` is site_profile.load_site_profiles's result, passed in
    rather than loaded here: it is a corpus-wide query and the callers
    already hold it.
    """
    claims = claims if claims is not None else load_claims()
    # Which sites belong to an operator. The first version asked only
    # `capacity_claim_matches`, which meant "sites with a matched
    # website capacity claim" — a much narrower thing than "sites this
    # operator runs", and it reported "no site matched" for Vantage
    # while the corpus held five of them (Luke, 2026-08-28). The
    # association now uses the project's own identity machinery: the
    # confirmed alias group, or the operator named on the site resolved
    # through that same group. Substring matching is deliberately not
    # used — "Ark" is three characters and matches things that are not
    # Ark Data Centres.
    alias_index = organisations.alias_index(organisations.load_groups())

    def _belongs(prof: dict, operator: str) -> bool:
        want = entities.canonical_key(operator)
        if entities.canonical_key(prof.get("operator_group") or "") == want:
            return True
        primary = (prof.get("operator_primary") or "").split(",")[0].strip()
        if not primary:
            return False
        if entities.canonical_key(primary) == want:
            return True
        g = organisations.group_for(primary, alias_index)
        return bool(g) and entities.canonical_key(g.group) == want

    by_op: dict[str, list[str]] = {}
    permits: dict[str, tuple[int, float, int]] = {}
    gen_fuels: dict[str, tuple[str, ...]] = {}
    with conn.cursor() as cur:
        cur.execute(SITES_SQL)
        for op, key in cur.fetchall():
            by_op.setdefault(op, []).append(key)
        cur.execute(PERMITS_SQL)
        for op, n, mwth, eng in cur.fetchall():
            permits[op] = (int(n), float(mwth), int(eng))
        # Fuels per site, from site_profile's own ranking rather than
        # from its rendered label.
        cur.execute(GENERATION_SQL)
        for key, counts, texts in cur.fetchall():
            gp = site_profile.generator_profile(counts or (), texts or ())
            gen_fuels[key] = tuple(label for label, _n in gp.fuels)

    rows = []
    for c in claims:
        keys = sorted(set(by_op.get(c.operator, []))
                      | {k for k, prof in profiles.items()
                         if _belongs(prof, c.operator)})
        fuel_sites: dict[str, int] = {}
        floor = None
        chp = 0
        for k in keys:
            p = profiles.get(k) or {}
            for name in (gen_fuels.get(k) or ()):
                fuel_sites[name] = fuel_sites.get(name, 0) + 1
            if p.get("generator_is_chp"):
                chp += 1
            n = p.get("generator_count")
            if isinstance(n, int) and (floor is None or n > floor):
                floor = n
        n, mwth, eng = permits.get(c.operator, (0, 0.0, 0))
        rows.append(OperatorRow(
            claim=c, sites=tuple(keys),
            fuels=tuple(sorted(fuel_sites.items(), key=lambda kv: (-kv[1], kv[0]))),
            generator_floor=floor, chp_sites=chp,
            permit_count=n, permit_mwth=mwth, permit_engines=eng))
    return rows


def validate(claims: list[GreenClaim] | None = None) -> list[str]:
    """Problems as strings; empty means the file is loadable."""
    claims = claims if claims is not None else load_claims()
    problems = [f"{c.operator}: quote is too short to be checkable"
                for c in claims if len(c.quote) < 15]
    return problems + verify_quotes(claims)
