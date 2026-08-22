# Session handover — 2026-08-21, extended 2026-08-22

Written at the end of the day the capacity-claims work landed, 2.2 was
built, and 2.2 shipped — the release chain ran to the end, so nothing
here is in flight. Replaces the 2026-08-11 handover, which described 2.1
as in flight; 2.1 shipped, and everything in it is now history.

Read [ROADMAP.md](../ROADMAP.md) for what is outstanding,
[HISTORY.md](../HISTORY.md) for why things are as they are, and
[REGENERATION_RUNBOOK.md](REGENERATION_RUNBOOK.md) for the release chain.
This document covers what is easy to get wrong, what landed late enough
that it is not yet in HISTORY, and the one substantial piece of work
that was scoped and not started — the Environment Agency permit
schedules. **That piece was built on 2026-08-22**; the section below now
records what it produced and what is left of it rather than what it
would cost.

---

## What is running right now

**A deep read is writing to the database.** Findings were still being
inserted at 20:09 UTC — around 5,900 in the preceding eight hours — so
the corpus is moving under the artefacts. Nothing is wrong with that,
but two consequences matter to whoever picks this up:

- **The published artefacts are a snapshot, and they will drift.**
  Rebuilding the workbook this evening moved sixteen cells on Sites and
  fifteen on Applications with no code change behind them: one site's
  mention counts, one application's verified-findings count 19,397 →
  21,485, and thirteen Drive links that had resolved since.
- **Before quoting a figure from an artefact, check its stamp.** Every
  one carries a generation time and a pipeline commit.

None of the capacity-claims work involved reading: everything added is
*external* evidence about sites the corpus already held.

---

## What 2.2 is

A source release, not a reading release. It answers the question Luke
opened the arc with: **how do we find out the real power demands, when
so few planning applications state one?** of 456 sites, 109 have a figure their own
documents disclose or their standby plant implies, 43 more can only be
estimated from floorspace, and 304 have neither. The answer turned out
not to be better extraction but other audiences.

A data centre's size is stated to at least five of them, and the store
now holds all five — the fifth arrived after 2.2 shipped, so it is in the
database and the artefacts rebuild with it, but not in the 2.2 files:

| Audience | Source | In the store |
|---|---|---|
| The planning authority | the site's own application documents | `power_adjudication` (unchanged) |
| The grid operator | NESO's Existing Agreements Register | 119 claims |
| The auditors | accounts filed at Companies House | 12 claims |
| Customers | operators' own websites | 59 claims |
| The environmental regulator | permits on the Environment Agency's public register | 42 claims (added 2026-08-22) |

190 claims, 41 matched to 25 sites, across 15 operators — 3 matches
have been retired, the last of them Union Park (see below). Every figure is
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

**Shipped.** Everything on the previous version of this list is done:
merged and deployed, gate re-probed from outside (22 paths refused,
forged cookie rejected), Drive synced, Sheet refreshed, backup taken
(`dcp_2026-08-21T0746.dump.gpg`, 141 MB, verified).

Artefacts are in `data/exports/phase2.2_build/` and on Drive, verified
by MD5 against the local files rather than by the sync reporting
success: workbook 849,813 bytes, database 205,008,896, reader
9,036,270.

**One PR is open:** #86, the canonical `operator` column in the DuckDB
export. The 205 MB file already carries it — it was rebuilt and
uploaded — so the PR is the generator catching up with the artefact,
not work the release is waiting on.

---

## What landed after the release, and why

Four things, all of them from Luke opening the thing and poking it.

**The Operators page counted and cited nothing.** "6 sites here",
"11 figures", no way to reach any of it. Rows now expand: the sites
named and linked, and every figure with its value, what it was
published as, the document or page it appeared in, the verbatim span it
was read from and — for external claims — the written evidence for
matching it to that site. All 157 figures on the page carry a source
link; a check counted them rather than an eye. The workbook gained a
"Which sites" column and source/locator/quote columns to match, plus
the four dictionary entries those two sheets never had.

Two things there were wrong rather than merely unsourced. *"The
operator calls this X"* was untrue for Digital Realty's eleven, where X
is the JSON key the figure is carried under in the page's data; it now
reads "published as". And the like-for-like ratios show match
confidence inline, so a 6.81x divergence resting on a tentative match
says so on the row.

**The map's sidebar described a different map.** Projecting Sites → Map
carried the filtered set but reset the map's controls, so the sidebar
reported "100 MW or greater: off" over exactly the >=100 MW set. Now
mirrored. The search box needed the haystacks unified first — the map
searched a thinner one, so copying the term across would have dropped
sites the projection contained; it now reads each site's haystack out
of the table row instead of keeping a second copy.

**The reader and the workbook disagreed about 43 sites.** The workbook
estimated power from floorspace at 1.71 kW/m2 where nothing better
existed; the reader passed `floorspace_sqm=None` and had since the day
it was written. So a site read "30 MW — Estimated from floorspace" in
the spreadsheet and "No capacity disclosed" on the page, with its own
proposal text stating 25,020 sqm of data centre floorspace. Eight of
the 43 are over 100 MW, and the reader's default filter hides anything
without a figure, so they were invisible in the artefact most people
open. The loader moved to `site_scale` and both artefacts call it.

`DISCLOSED_BASES` moved there too, and is the line worth knowing: a
figure somebody stated versus one this project calculated. The Ofgem
queue comparison counts only the former — both artefacts report 109
sites there — while the site rows show all 152.

**The DuckDB was a narrower view than the artefacts built on it.** Its
`capacity_claims` had no operator, term or quote, so the four-audience
comparison could not be reproduced from the file. Added, with the
canonical `operator` beside the printed `published_by` rather than over
it. Its note also still described the store as "currently NESO's
Existing Agreements Register".

**One trap in the release chain, now fixed.** `sheet_sync` reconciles
columns by name, and External aggregates is a report rather than a
table — a title in A1 and small tables down the page. Its header row is
one heading followed by blanks, so reconciling asked to insert five
nameless columns and would have pushed the whole tab sideways, leaving
every hand-set width describing empty space. The header now ends where
the names do. **Rename headers in the Sheet by hand before syncing a
rename:** reconcile sees a renamed column as a delete plus an insert
and throws its formatting away.

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
*unsafe* — reading district proximity as identity is what put it there,
and site 61 still holds around six campuses dominated by the former
Nestle factory's 286 applications. The six boundaries it still needs are
recorded in `data/priors/site_partitions.yaml`; until they are drawn,
treat any match to site 61 as suspect.

**Never let an external figure become a site's own number.** The two
reader panels now say where their figures come from, and per-quantity
caveats replace the single flat one. A test asserts every quantity type
that can reach the indicators panel has a caveat, so a new source
cannot arrive unlabelled.

---

## What the Environment Agency permits produced (2026-08-22)

Built. The full account is in HISTORY; this is what someone picking it
up needs and would otherwise get wrong.

**The register carries no capacity.** Not one column. It is an index —
permit number, holder, address, grid reference, and for some rows a link
to the permit on gov.uk — and the permit PDF is the source. So a
register row is never a claim. This is the opposite way round from every
other external source in the store, and it is why
`scripts/fetch_ea_permits.py` has two stages.

**What is on disk and what is not.** The permit PDFs and their extracted
text are under `data/raw/ea_permits/`, gitignored, on the same footing as
the 55,678 planning documents: public records at permanent URLs, fetched
rather than republished. Re-fetch with
`scripts/fetch_ea_permits.py --documents`.

Three committed files are what make a clone work without them. The
register snapshot (`environment-agency-industrial-installations.zip`, a
zip despite the URL), because it is regenerated daily with no archive
behind it and yesterday's is simply gone.
`environment-agency-permit-claims.yaml`, generated by
`scripts/read_ea_permits.py --write-claims`, holding all 42 claims with
the verbatim sentence each was read from — do not hand-edit it. And
`environment-agency-permit-documents.json`, pinning every document's
URL, sha256, byte count and page count.

Anything that needs the text says so rather than quietly passing: the
loader prints whether it re-verified the quotes or only trusted the
committed ones, and `--readings` refuses to run without them.

**The numbers, as anchors for a re-pull.** 5,198 register rows → 97
candidates → 42 with a permit publication → 42 claims, 7,439 MWth, 31 of
them corroborated by their own per-engine breakdown. Eight matched.
Amazon Didcot North is the largest at 925 MWth over 129 generators.
`scripts/read_ea_permits.py --readings` prints all of it, including the
candidates that yielded nothing.

Six figures come from a variation notice rather than the original
permit — a variation supersedes what it varies, so it is the current
position. And gov.uk titles the VIRTUS Slough attachment "Pemit: Virtus
Holdco Limited"; `kind_of()` in the fetcher matches that typo on
purpose, because without it 180.5 MWth is silently classified as
"other" and never read.

**Three things that will bite.**

- **Never convert MWth to MW in code.** `value_mw` is null on all 42 and
  must stay null. It is a physical inference, not a unit conversion, and
  the reader prints "260 MWth" precisely because it would otherwise print
  "(260 MW)" beside it. A test asserts it. **And there is no divisor to
  use** — this document previously said 2.4–2.5, which had no source. The
  only permit stating both quantities is Telehouse Docklands, 1.6 to
  2.4 MWe against an average 5.1 MWth, so the ratio is somewhere between
  two and three and where a given site sits in it is unknown.
- **Re-pulling the register moves the candidate set.** It is regenerated
  daily with no internal version, so `ea_permits.AS_AT` and
  `REGISTER_SHA256` are the only record of which day's file the claims
  came from. `--register` refuses to write anything that is not a zip
  and tells you to update both.
- **The extraction is regex and is meant to fail loudly.** Two sentence
  shapes have already produced wrong figures — Ark Spring Park read
  120 MWth as 3.9, Equinix Slough read 331.084 as 243.088 — and both are
  now tests in `tests/test_ea_permits.py`. If a new permit shape stops
  matching, the permit reports as unread. Do not paper over that with a
  model; go and look at the sentence.

**Most claims are unmatched, and that is the useful part.** Thirty-four
of 42. Almost none of it is about the permits: a permit describes plant
that exists while most of this corpus describes schemes that were
proposed, and several site records hold a whole industrial estate.
**Nine permits from seven operators, 1,430 MWth, all fall inside site
23** — the only site record on the entire Slough Trading Estate. Site 5
holds Interxion, Global Switch and Telehouse. Site 59 holds Vantage,
Colt and Equinix as well as Microsoft. Site 11 holds Amazon and NTT.
VIRTUS's Stockley Park campus, 470 MWth, has no site record at all. Each
is written into `environment-agency-permit-matches.yaml` under
`considered`, with the reason, and together they are the sharpest
partition evidence the project has: every permit names a campus and
gives its grid reference.

**Two register errors, found by looking.** A Digital Realty permit gives
a Crawley address with Redhill coordinates and a Redhill local
authority. A Croydon installation is located at its holder's registered
office in the City of London. Neither is matched, both are recorded.

**What is left.** Fifty-five candidates have no permit publication —
mostly MCP registrations, which are lighter-touch; whether the
Environment Agency will supply those on request has not been asked.
Eleven claims are not fully self-corroborating and reading their
schedules would settle each one. And the
matching is blocked behind the site partitioning rather than behind
anything about the permits.

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
- **The reader build is not byte-reproducible.** Two runs against an
  unchanged database differ beyond the timestamp and commit stamp: some
  per-site findings lists come back in a different order, which is a
  query whose `ORDER BY` does not fully determine row order. It matters
  because diffing a build against the last release is how regressions
  get caught here, and non-determinism makes that diff noisy. Handed to
  a separate session on 2026-08-21; check whether it landed before
  chasing it.

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
