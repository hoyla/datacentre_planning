"""Companies House: the register as an ownership source, not a capacity one.

The 2026-08-20 survey concluded that filed accounts are mostly a null for
capacity, and for *operators* that stands: Kao, Yondr, Vantage UK, Global
Switch and CloudHQ UK state no figure of any kind, and Ark's per-campus
megawatts are a narrative choice in a business review that generalises to
nobody. The correction of 2026-08-24 is that a **single-asset scheme SPV
is a different kind of filer**. Its investment property IS the scheme, so
under FRS 102 the directors must state what the valuation assumes, and a
capacity assumption is in the accounts by construction rather than by
choice. UK Court Lane DC Ltd (14045228) is the worked example: a £205m
valuation that assumes "successful delivery of a 103.3 MW hyperscale data
centre", against 140 MW of reserved grid connection in the same scheme's
own planning documents.

This module is the acquisition half of that. It does four things and
deliberately not a fifth.

**It resolves names to numbers.** A name in Barbour's client-of-record
slot or an applicant finding is a string; a company number is a join key
the newsroom already uses. `search_companies` is the only resolution
route here, and it returns candidates — the adjudication of which
candidate is the company stays with a person and lands in
`data/priors/organisation_aliases.yaml`, which is where this repository
already records what a name turned out to be.

**It pulls the ownership record, which is four documents and not one.**
The PSC register alone is structurally unable to describe a US-parented
scheme: an overseas LP is not a registrable relevant legal entity, so
the page reads "no registrable person" and says nothing. The chain has
to be assembled from the charges register (who lent, and what they took
security over — the most honest statement of who controls an asset), the
confirmation statement (shareholders), the officers, and the accounts'
related-party and parent-undertaking notes. All four are fetched;
none of them is treated as sufficient on its own.

**It caches every raw response as a timestamped snapshot.** Append-only,
under `data/raw/companies_house/`, one file per (path, fetch date), so a
re-run is a no-op on unchanged content and a changed register is visible
as a new file beside the old rather than as an overwrite. The register
changes — a charge is satisfied, an SPV is renamed, a PSC is added —
and losing the earlier state would destroy exactly the evidence a
reporter needs.

**It fetches filed documents through the redirect that breaks naive
clients.** `/company/{n}/filing-history/{id}/document` 302s to S3, and
S3 rejects a request still carrying the Companies House Authorization
header. The signed URL it returns expires in sixty seconds, so it is
followed immediately and unauthenticated rather than passed around.

What it does not do is read a number out of a PDF. Companies House scans
what it publishes; there is no text layer, and OCR misreads a digit
silently. Figures are transcribed by eye from pages rendered at 300 DPI
and re-checked against committed OCR of the cited page, exactly as
`dcp.capacity_claims.verify_ch_quotes` already asserts for the filings
in the store.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
EXTERNAL = ROOT / "data" / "external_sources"

# Raw API responses and filed PDFs. Not committed, for the same reason
# the Environment Agency permits are not: data/raw/ is gitignored, and
# these are public documents at permanent URLs. What is committed is the
# derived, quoted, checkable pair — the SPV register below and the
# claims YAML — which pins the bytes rather than redistributing them.
RAW_DIR = ROOT / "data" / "raw" / "companies_house"

# The hand-adjudicated register of scheme SPVs: which name resolved to
# which company, on what evidence, and which scheme it belongs to.
SPV_REGISTER_PATH = EXTERNAL / "companies-house-spvs.yaml"

API = "https://api.company-information.service.gov.uk"
WEB = "https://find-and-update.company-information.service.gov.uk"

# 600 requests per five minutes. Paced rather than raced: a 0.55s floor
# between calls is ~545/5min, comfortably inside the window, and the
# 429 handler below backs off on the header rather than guessing.
MIN_INTERVAL_S = 0.55
USER_AGENT = ("datacentre-planning research (Guardian); "
              "contact via github.com/hoyla/datacentre_planning")


class RateLimited(RuntimeError):
    """A 429 that survived the backoff — the caller should stop, not retry."""


@dataclass
class Client:
    """A paced, snapshotting Companies House client.

    Every JSON response is written to `RAW_DIR/<utc-date>/<slug>.json`
    before it is returned, so the analysis downstream always has a raw
    artefact behind it. Re-fetching the same path on the same day
    overwrites nothing: the file is written once and re-read.
    """

    api_key: str = field(default_factory=lambda: os.environ.get("CH_API_KEY", ""))
    raw_dir: Path = RAW_DIR
    as_at: str = field(default_factory=lambda: datetime.now(UTC)
                       .date().isoformat())
    use_cache: bool = True
    _last_call: float = 0.0
    calls: int = 0
    cache_hits: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise RuntimeError("CH_API_KEY is not set; see .env")

    # -- plumbing ---------------------------------------------------------

    def _auth(self) -> str:
        token = base64.b64encode(f"{self.api_key}:".encode()).decode()
        return f"Basic {token}"

    def _pace(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - gap)
        self._last_call = time.monotonic()

    def _snapshot_path(self, path: str, params: dict | None) -> Path:
        slug = path.strip("/").replace("/", "_")
        if params:
            q = urllib.parse.urlencode(sorted(params.items()))
            slug += "__" + q.replace("&", "_").replace("=", "-")
        slug = "".join(c if c.isalnum() or c in "-_." else "_" for c in slug)
        return self.raw_dir / self.as_at / f"{slug[:180]}.json"

    def get(self, path: str, params: dict | None = None,
            tries: int = 4) -> dict | None:
        """A JSON endpoint, snapshotted. None on a 404 — which is a fact
        about the company (no charges filed, no PSC statement), not an
        error to raise past the caller."""
        snap = self._snapshot_path(path, params)
        if self.use_cache and snap.exists():
            self.cache_hits += 1
            return json.loads(snap.read_text())["body"]

        url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        for attempt in range(tries):
            self._pace()
            req = urllib.request.Request(url)
            req.add_header("Authorization", self._auth())
            req.add_header("User-Agent", USER_AGENT)
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    self.calls += 1
                    body = json.load(r)
                    headers = {k: v for k, v in r.headers.items()}
                break
            except urllib.error.HTTPError as e:
                self.calls += 1
                if e.code == 404:
                    # Recorded as a measured absence, with the snapshot to
                    # prove the question was asked.
                    body, headers = None, dict(e.headers)
                    break
                if e.code == 429:
                    reset = e.headers.get("X-Ratelimit-Reset")
                    wait = 30.0
                    if reset and reset.isdigit():
                        wait = max(5.0, int(reset) - time.time() + 2)
                    if attempt == tries - 1:
                        raise RateLimited(f"429 on {path} after {tries} tries")
                    time.sleep(min(wait, 330))
                    continue
                if 500 <= e.code < 600 and attempt < tries - 1:
                    time.sleep(2 ** attempt)
                    continue
                self.failures.append((path, f"HTTP {e.code}"))
                return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                if attempt == tries - 1:
                    self.failures.append((path, repr(e)))
                    return None
                time.sleep(2 ** attempt)
        else:  # pragma: no cover - loop always breaks or returns
            return None

        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({
            "fetched_at": datetime.now(UTC).isoformat(),
            "url": url,
            "status": 200 if body is not None else 404,
            "ratelimit_remain": headers.get("X-Ratelimit-Remain"),
            "body": body,
        }, indent=1))
        return body

    # -- the endpoints this project needs ---------------------------------

    def search_companies(self, q: str, n: int = 8) -> list[dict]:
        d = self.get("/search/companies",
                     {"q": q, "items_per_page": n}) or {}
        return d.get("items", []) or []

    def profile(self, number: str) -> dict | None:
        return self.get(f"/company/{number}")

    def filing_history(self, number: str, n: int = 100) -> list[dict]:
        d = self.get(f"/company/{number}/filing-history",
                     {"items_per_page": n}) or {}
        return d.get("items", []) or []

    def charges(self, number: str) -> list[dict]:
        d = self.get(f"/company/{number}/charges", {"items_per_page": 100}) or {}
        return d.get("items", []) or []

    def psc(self, number: str) -> dict:
        """Both halves of the PSC page: the people, and the *statements*
        that stand in for them. "no-individual-or-entity-with-signficant-
        control" (Companies House's own misspelling) is the disclosure a
        US-LP-parented SPV actually makes, and reading only the first
        half would record it as an empty register rather than as the
        statement it is."""
        return {
            "items": ((self.get(f"/company/{number}/persons-with-significant-control",
                                {"items_per_page": 100}) or {}).get("items") or []),
            "statements": ((self.get(
                f"/company/{number}/persons-with-significant-control-statements",
                {"items_per_page": 100}) or {}).get("items") or []),
        }

    def officers(self, number: str) -> list[dict]:
        d = self.get(f"/company/{number}/officers", {"items_per_page": 100}) or {}
        return d.get("items", []) or []

    # -- documents --------------------------------------------------------

    def document(self, document_id: str, dest: Path) -> Path | None:
        """A filed document's PDF.

        Two-step and both steps matter. The metadata endpoint is
        authenticated; the content endpoint 302s to a signed S3 URL that
        **rejects** a request still carrying the Companies House
        Authorization header, and the signature expires in 60 seconds.
        So the redirect is followed by hand, immediately, with no auth.
        """
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        url = (f"https://document-api.company-information.service.gov.uk"
               f"/document/{document_id}/content")

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise _Redirect(newurl)

        opener = urllib.request.build_opener(_NoRedirect)
        self._pace()
        req = urllib.request.Request(url)
        req.add_header("Authorization", self._auth())
        req.add_header("Accept", "application/pdf")
        req.add_header("User-Agent", USER_AGENT)
        signed: str | None = None
        try:
            with opener.open(req, timeout=45) as r:
                data = r.read()          # some documents return 200 directly
        except _Redirect as e:
            signed = e.url
            data = b""
        except urllib.error.HTTPError as e:
            if e.code in (302, 303, 307) and e.headers.get("Location"):
                signed = e.headers["Location"]
                data = b""
            else:
                self.failures.append((document_id, f"HTTP {e.code}"))
                return None
        except (urllib.error.URLError, TimeoutError) as e:
            self.failures.append((document_id, repr(e)))
            return None
        self.calls += 1

        if signed:
            # Unauthenticated, and now — the signature is good for 60s.
            plain = urllib.request.Request(signed)
            plain.add_header("User-Agent", USER_AGENT)
            try:
                with urllib.request.urlopen(plain, timeout=90) as r:
                    data = r.read()
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError) as e:
                self.failures.append((document_id, f"s3: {e!r}"))
                return None

        if not data:
            self.failures.append((document_id, "empty document body"))
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest


class _Redirect(Exception):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


# ---------------------------------------------------------------------------
# Reading a company, once fetched.

# `AA` is the accounts filing and `AAMD` an amended one. **`AA01` is not
# accounts** — it is a change of accounting reference date, and it sits
# in the same part of the filing history under a name one letter and one
# digit away. Including it fetched eight change-of-ARD forms in place of
# eight sets of accounts, each a single page reading "The accounting
# reference period ending … is shortened", which is a document that
# discloses nothing and would have been recorded as a company that
# disclosed nothing.
ACCOUNTS_TYPES = {"AA", "AAMD"}
CONFIRMATION_TYPES = {"CS01", "AR01", "CS01(PAPER)"}
# The mortgage/charge codes. MR01 creates, MR04 satisfies; the charges
# endpoint carries the same facts in a structured form, and both are
# kept because the filing history dates a charge's *creation* even after
# the charge itself is recorded as satisfied.
CHARGE_TYPES = {"MR01", "MR02", "MR04", "MR05", "MG01", "MG02", "MG04",
                "395", "403a"}


def latest_accounts(items: list[dict]) -> dict | None:
    """The most recent accounts filing, by the date it was made up to.

    Not by filing date: a company can file two years' accounts on
    consecutive days, and the later *filing* may be the earlier *year*.
    """
    accts = [i for i in items if i.get("type") in ACCOUNTS_TYPES]
    if not accts:
        return None

    def key(i: dict) -> str:
        return (i.get("action_date") or i.get("date") or "")
    return sorted(accts, key=key)[-1]


def accounts_history(items: list[dict]) -> list[dict]:
    return sorted((i for i in items if i.get("type") in ACCOUNTS_TYPES),
                  key=lambda i: i.get("action_date") or i.get("date") or "")


def latest_confirmation(items: list[dict]) -> dict | None:
    cs = [i for i in items if i.get("type") in CONFIRMATION_TYPES]
    return sorted(cs, key=lambda i: i.get("date") or "")[-1] if cs else None


def document_id_of(item: dict) -> str | None:
    """The document id inside a filing-history item's metadata link."""
    link = (item.get("links") or {}).get("document_metadata")
    return link.rstrip("/").rsplit("/", 1)[-1] if link else None


def filing_url(number: str, item: dict) -> str:
    tid = item.get("transaction_id") or document_id_of(item) or ""
    return f"{WEB}/company/{number}/filing-history/{tid}/document?format=pdf"


def is_dormant_or_micro(profile: dict) -> bool:
    """Accounts type as filed. A dormant or micro-entity filing carries no
    investment-property note and therefore no capacity assumption — the
    absence is measured, not missing."""
    t = ((profile.get("accounts") or {}).get("last_accounts") or {}).get("type")
    return t in {"dormant", "micro-entity", "total-exemption-full",
                 "total-exemption-small"}


def has_filed_accounts(profile: dict) -> bool:
    last = (profile.get("accounts") or {}).get("last_accounts") or {}
    return bool(last.get("made_up_to"))


def summarise_charges(charges: list[dict]) -> list[dict]:
    """Who lent, over what, and whether the security is still live.

    The persons-entitled list is the part that carries the ownership
    signal: a scheme SPV's lender is frequently the only named party
    above it in any public record.
    """
    out = []
    for c in charges:
        persons = [p.get("name") for p in (c.get("persons_entitled") or [])]
        out.append({
            "charge_code": c.get("charge_code"),
            "status": c.get("status"),
            "created_on": c.get("created_on"),
            "delivered_on": c.get("delivered_on"),
            "satisfied_on": c.get("satisfied_on"),
            "persons_entitled": persons,
            "classification": (c.get("classification") or {}).get("description"),
            "particulars": (c.get("particulars") or {}).get("description"),
            "contains_floating_charge": c.get("particulars", {}).get(
                "contains_floating_charge"),
        })
    return out


def summarise_psc(psc: dict) -> dict:
    """What the PSC page actually says, including when it says nothing.

    A statement of "no registrable person" is a disclosure with a
    meaning — most often that the parent is an overseas entity which is
    not a registrable relevant legal entity — and it is recorded as such
    rather than as an empty list.
    """
    items = [{
        "name": i.get("name"),
        "kind": i.get("kind"),
        "nationality": i.get("nationality"),
        "country_of_residence": i.get("country_of_residence"),
        "natures_of_control": i.get("natures_of_control"),
        "notified_on": i.get("notified_on"),
        "ceased_on": i.get("ceased_on"),
        "identification": i.get("identification"),
    } for i in psc.get("items", [])]
    statements = [{"statement": s.get("statement"),
                   "notified_on": s.get("notified_on"),
                   "ceased_on": s.get("ceased_on")}
                  for s in psc.get("statements", [])]
    return {"persons": items, "statements": statements,
            "reads_as_no_registrable_person": bool(statements) and not [
                i for i in items if not i.get("ceased_on")]}
