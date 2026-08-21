# Session handover — 2026-08-21

Written at the end of the day the capacity-claims work landed and the
2.2 release was built. Replaces the 2026-08-11 handover, which described
the 2.1 release as in flight; 2.1 shipped, and everything in it is now
history. Read [ROADMAP.md](../ROADMAP.md) for what is outstanding,
[HISTORY.md](../HISTORY.md) for why things are as they are, and
[REGENERATION_RUNBOOK.md](REGENERATION_RUNBOOK.md) for the release chain.
This document covers what is *in flight*, what is easy to get wrong, and
the one substantial piece of work that has been scoped but not started.

---

## What is running right now

**Nothing.** The Studio deep-read has not been restarted since the 2.1
boundary. No new documents were acquired and no new reading happened in
any of this work — everything added is *external* evidence about sites
the corpus already held.

---

## What 2.2 is

A source release, not a reading release. It answers the question Luke
opened the arc with: **how do we find out the real power demands, when
so few planning applications state one?** 344 of 442 sites still have no
demand figure in their own documents, and the answer turned out not to
be better extraction but other audiences.

A data centre's size is stated to at least four of them, and the release
now holds all four:

| Audience | Source | In the store |
|---|---|---|
| The planning authority | the site's own application documents | `power_adjudication` (unchanged) |
| The grid operator | NESO's Existing Agreements Register | 119 claims |
| The auditors | accounts filed at Companies House | 12 claims |
| Customers | operators' own websites | 59 claims |

190 claims, 42 matched to 26 sites, across 15 operators. Every figure is
machine-verified against a committed snapshot — a spreadsheet row, the
OCR of a filed-accounts page, or a captured web page — and every match
to a site is a hand-adjudicated inference carrying written evidence.

**The findings worth knowing, because they are what the release is for:**

- **Utilisation is about a fifth of capacity, from three independent
  directions.** Ark's audited accounts give ~21% of built capacity
  drawn; VIRTUS's give ~15% of capacity *billed to customers*; UK Power
  Networks' half-hourly metering of ~100 real data centres gives a
  median of 18.1%. The VIRTUS figure is the sharpest because its
  denominator is capacity customers are paying for.
- **The same quantity, told differently to two audiences.** Only three
  sites currently qualify, and the comparison is deliberately narrow —
  IT load is *supposed* to be smaller than total site power, so most
  differences are not disagreements. Kingsnorth is 340 MW to the grid
  operator and 49.9 MW to the planning authority; the former Mercure
  Hotel 435 MW and 120 MW. South Mimms is 400 MW to both, which is the
  useful one: two audiences given the same number, reached here by two
  independent routes.
- **Digital Realty publishes per-site capacity and renders none of it.**
  Eleven UK facilities carry a figure in embedded page state under
  `field_utility_power_capacity`; the visible page shows only "UPS
  redundancy: 2N". The eleven sum to exactly 179,900, matching the
  aggregate in the same payload, which is what establishes the unit.
- **Ark's Elstree page identifies the operator** behind the former
  Mercure Hotel scheme, which the planning record does not foreground.

---

## What is left of the 2.2 release

Built and **not yet deployed.** EdgeOne builds from git, so writing
`index.html` is not publishing it — **the merge is the deploy.**

1. **Merge the release branch.** Then and only then, re-probe the gate
   from outside: `scripts/probe_gate.sh https://dc-review-gdn-hoyla.edgeone.app`.
   A browser with a session cannot show you what that checks.
2. **Drive staging and sync** (runbook steps 5 and 6) — not run.
   `build_drive_staging.py` must run *after* the artefacts exist, and it
   prints which release folder it chose. Read that line.
3. **The Google Sheet** (step 8) — not run. It writes into the sheet
   people are using, so it is Luke's call rather than the runner's.
4. **Backup** — done, `dcp_2026-08-21T0746.dump.gpg`, 141 MB, verified,
   on Drive.

Artefacts are in `data/exports/phase2.2_build/`.

---

## Things that will bite

**`backup_db.py` never loaded `.env`.** Fixed today. Every other entry
point loads it for `DATABASE_URL`; this one talks to Postgres through
Docker and so never needed to, which meant the passphrase sitting in
`.env` was invisible to it and the script exited telling you to export a
variable you had already set. A backup that quietly does not happen is
the worst kind.

**The pre-push hook stopped a stranded commit today.** A PR had been
merged while work continued on its branch; pushing there would have put
the commit somewhere nobody would read again. It refuses and tells you
to re-cut from main. Trust it.

**Two corrections were made to conclusions stated confidently.** Both
are worth knowing as a pattern rather than as facts:

- *"Per-site megawatts are peculiar to Ark"* was wrong because for
  VIRTUS I read the operating company (06762600), which states no
  capacity, and not the property company (09840065), which states a
  great deal. Checking one entity of a group and generalising is the
  same error the corpus's site-fragmentation keeps teaching.
- A tentative match of two 57 MW NESO rows to the Hoddesdon site rested
  on that site being *"the corpus's only Hoddesdon data centre"* — a
  fact about the corpus, not about Hoddesdon. Surveying operators
  turned up a second one. Retired, with the reason on the row.

**Site fragmentation is still the main matching hazard.** Cody Park
spans six site records across four councils; JVC Business Park four;
Colt's Hayes campus three, which is why Colt's claims are loaded
unmatched. Site 61 was split during this work (International Trading
Estate moved to 443) and that split is what made the Union Park match
safe.

**Never let an external figure become a site's own number.** The two
reader panels now say where their figures come from, and per-quantity
caveats replace the single flat one. A test asserts every quantity type
that can reach the indicators panel has a caveat, so a new source
cannot arrive unlabelled.

---

## The next substantial piece: Environment Agency permit schedules

Scoped, costed and **not started**. This is the biggest remaining lever
on the 344 sites with no disclosed figure, and the only item on the list
that is real engineering rather than curation.

**Why it works.** Data-centre standby generator fleets are sized to peak
load plus redundancy, and they need environmental permits. The permit
*documents* state what the register does not: Virtus Slough gives 31
generators totalling 180.5 MWth with per-engine ratings; Ark Cody Park
69 generators at ~260 MWth; Amazon Hayes 14 × 8.01 MWth. Thermal input
divided by roughly 2.4–2.5 bounds a site's electrical demand, from a
statutory document.

**What exists.** The Environment Agency's Installations register is a
daily-refreshed bulk CSV at
`https://environment.data.gov.uk/public-register/downloads/industrial-installations`
(5,199 rows), with a query API supporting `name-search`, `number-search`,
`local-authority` and radius search via `easting`/`northing`/`dist`.
Around 78 permits match data-centre operators — Amazon 11, Equinix 8,
Virtus 6, Ark 5, Digital Realty 4, NTT 3 and others. Records carry
eastings and northings, so they **join to sites on geography without
fuzzy name matching**. Roughly half carry a `Document URL` to a permit
PDF on gov.uk; the rest, mostly newer, do not.

**The design question to settle first.** Permits attach to *sites*, not
to planning applications, and this pipeline's whole findings layer is
keyed on `application_id`. Deep-reading a permit PDF through the
existing machinery would need an application to hang it on, and there
isn't one. Decide this before writing an adapter — the honest options
are a site-keyed document table, or claims carrying their own evidence
the way `capacity_claims` already does. The second is cheaper and fits
what is already built.

**Known limits, so nobody discovers them late.** Existing plant of
1–5 MWth needs no permit until 1 January 2029, so smaller and older
sites are under-represented. Emergency-only backup is excluded from
specified-generator permitting altogether — but that exclusion is void
if the plant provides balancing services or Capacity Market/DSR, which
is why the Capacity Market register turned out to be a dead end and also
why it explains itself. Wales is NRW's register, Scotland SEPA's, both
under different regimes.

---

## The other open threads

- **Regulator responses.** NESO and Ofgem were written to on 2026-08-12,
  replies due ~10 September. A CCA site-level consumption FoI to
  DESNZ/EA and EIR requests to the DNOs are worth sending and have not
  been; ~28 days each, so starting them is cheap and waiting is the
  cost. EIR is the right frame for the DNOs — address the *licensed*
  plc, not the management company, and note that section 105 of the
  Utilities Act is near-absolute under FOIA but disapplied for
  environmental information by EIR regulation 5(6).
- **Two VIRTUS filings** made up to 31 December 2025 were filed on 19
  and 20 August 2026 and their images are still not retrievable from
  the Companies House document API. Worth retrying.
- **A fourth operator tranche** would be cheap: add URLs to `PAGES` in
  `fetch_operator_snapshots.py`, run it, add curated claims with
  verbatim quotes. Colt is blocked on the Hayes fragmentation.
- **UKPN's gated datasets** — the Large Demand List and "Data Centres by
  Local Authority" — are behind Luke's portal login and unpulled.

---

## How Luke works

Unchanged from the last handover and worth repeating. He is a journalist
who has spent three decades on newsroom software, on the product and UX
side, and he finds defects by opening the thing and poking it. Several
of this session's fixes came from him reading a rendered panel: the
layout break the claims box caused, the pompous sentence in a lede, the
invented term in a column headed "terms the operator uses".

He wants pushback, and he is right often enough that the pushback has to
be grounded rather than reflexive. He asked for a raw megawatt figure on
the main site row; the argument against it — that a number there reads
as comparable to the planning figure beside it when the quantities
differ — was accepted on its merits, and the column now shows a
confidence tier instead.

**When he corrects something, build the durable form** — a constant, a
test, a shared function — rather than resolving to remember.
