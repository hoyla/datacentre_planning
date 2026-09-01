# Portal access notes

How to reach documents on registers that ordinary HTTP cannot, and what
each one does when it refuses. Written because every one of these
presents the same way from the outside — zero documents, no error — and
that is indistinguishable from a council that publishes nothing.

Transport for all browser-assisted work is the loopback receiver
(`scripts/browser_receiver.py`): the page POSTs each document to
`http://127.0.0.1:8765/put` and it lands on disk. File downloads are not
usable for bulk work — each one needs a human to press Save.

Two rules learned the hard way, and they are not optional:

- **Sequential, >=2.5s.** Concurrency of 4 tripped Coventry's WAF inside
  a minute.
- **Never mark an application complete unless every listed document
  arrived.** An empty page is what a block looks like; recording it as
  "no documents" converts our access failure into a false claim about a
  council.

A third rule, added 2026-09-01 and not specific to registers:

- **Harvest the bytes the server sent, never the browser's rendered
  text.** `innerText` omits anything inside a collapsed `<details>`
  accordion — the content is in the DOM and not in the rendering — and
  it omits it silently. Same-origin `fetch(url, {credentials:'include'})`
  inside the page returns the served response body, which is what the
  receiver should be given. This is not theoretical: reading Iron
  Mountain's campus page through rendered text produced a wrong
  "published nowhere" finding about a figure that was in the HTML all
  along.

  Note the loopback receiver needs a browser that permits `fetch` to
  `http://127.0.0.1` from an HTTPS page. Chrome does, because loopback
  is a potentially-trustworthy origin. Some embedded browsers block it
  outright, and then the harvest has to run in Chrome.

## Operator pages behind a challenge — not a register, same problem

`scripts/fetch_operator_snapshots.py --slug <slug> --from-file <path>`
stores a page captured this way through exactly the code a direct fetch
uses, so the snapshot format cannot fork, and writes `# obtained:
browser` in the header so the route is part of the record. The URL comes
from the script's own `PAGES` rather than the command line, so a
snapshot always names a page this project curated.

**ironmountain.com** is the worked case. Every scripted client gets
`HTTP 429` — the whole host, its own homepage included — carrying
`x-vercel-mitigated: challenge` and an `x-vercel-challenge-token`. That
is Vercel Attack Challenge Mode, not a rate limit, so backoff can never
reach it and no header profile helps: a current Chrome UA, the full
`sec-ch-ua` / `Sec-Fetch-*` set and the exact UA of a passing browser
were each tried and each got 429. The campus page, `lon-1` and `lon-3`
are held; `lon-2` 404s and has no page to hold.

## Coventry — `planandregulatory.coventry.gov.uk` (28 applications)

AWS WAF. Scripted clients get `HTTP 202` with an empty body; a challenged
session gets `405` and a "Human Verification" page. A real browser is
fine, and a normal page load re-establishes the session after a block.

- Application page: `/planning/index.html?fa=getApplication&id=<portal id>`
- Documents: `<a href="...fa=downloadDocument&id=...">` in the page table
- Same-origin `fetch(..., {credentials:'include'})` returns the bytes
- Do not attempt the human-verification challenge; stop and report

## Vale of White Horse — migrated (33 applications)

`data.whitehorsedc.gov.uk` is retired. The register is now
`valeofwhitehorse.planning-register.co.uk`, and old references still
resolve. A disclaimer must be accepted once per session (Luke approved
this on 2026-08-08); search is behind invisible reCAPTCHA, which passes
without a challenge when the real form is submitted.

- Detail page: `/Planning/Display?applicationNumber=<ref urlencoded>`
  (a query parameter — `/Planning/Display/<ref>` returns 404)
- Page is JS-rendered; fetched HTML still contains the document rows
- Documents tab: `div.tabHeader#Documents`
- Rows: `tr.grid-dataRow[data-imageid]` — **the attribute filter is
  required**. `tr.grid-dataRow` alone also matches rows in the related
  applications, consultee and site history tables, which carry no
  document identifiers and return `204`. Without the filter a 127-document
  application reports 383 rows and 256 "failures", and those look exactly
  like a portal refusing us. Carrying `data-module`, `data-recordnumber`,
  `data-planid`, `data-imageid`
- Download: `POST /Document/GetFileBinary`, form-encoded

      module=PLA&recordNumber=130969&planID=4941345&imageID=20&isPlan=false

  `planID`/`imageID` are **integers** — the data attributes carry
  `4941345.0000` and passing that verbatim returns `204 No Content`.
  The response is a JSON-quoted **base64 string**, not raw bytes.

## Runnymede — Northgate + Idox docstore (33 applications)

Serves `403` to a bare research user-agent, `200` to
`Mozilla/5.0 (compatible; datacentre_planning research; +mailto:...)`.

- Document list: `https://docs.runnymede.gov.uk/PublicAccess_LIVE/SearchResult/`
  `RunThirdPartySearch?FileSystemId=PL&FOLDER1_REF=<application ref>` —
  constructible from the reference; no need to scrape the Northgate page
- The list is embedded as `var model = {...}` JSON with a `Guid` per
  document
- Download: `GET /PublicAccess_Live/Document/ViewDocument?id=<Guid>`

  The parameter is **`id`**, not `guid`, and there is no `fileSystemId`.
  `DownloadFile` is a decoy: it answers `200` with the 20-byte body
  "File does not exist" for every id, correct or not — which reads as a
  broken document rather than a wrong endpoint, and cost several rounds
  of guessing before the page was made to reveal what it actually calls.

  Finding it needed the click handler, and the handler ignores
  `element.click()` on the anchor: it is bound to the inner `<span>` and
  fires only on a dispatched `MouseEvent`. Wrapping `window.open` then
  shows the real URL.

## Broxbourne — NEC LPAssure (26 applications)

The overview page returns "UnsupportedWebBrowser" to scripted clients,
so the work happens in a browser. The document list does not need the
page at all:

    POST /LPAssure/ES/Presentation/Planning/OnlinePlanning/GetOnlineDocuments
         ?applicationNumber=<ref>&currentPageIndex=<n>
         &IsDatePublishSortedDescending=false&pageSize=50

**`pageSize` is required.** Omit it and the endpoint answers `500` for
every page index — which reads as a broken or protected endpoint rather
than a missing parameter, and is what made this look harder than it is.
Walk `currentPageIndex` until no new links appear; the reference needs no
space-padding despite the padding visible in the document hrefs.

Documents: `/LPAssure/ES/Presentation/Planning/OnlineDisplayDocument/`
`DisplaySearchDocument/<name>?applicationNumber=...&FileName=...`
`&fileType=.tif&aspectGuid=<guid>` — `fileType=.tif` is misleading, the
server returns `application/pdf`.

## Slough — Agile register, legacy document store (37 applications)

The Agile API truthfully reports zero documents: they live on
`sbcplanning.co.uk`, a separate PHP system reached from the application
page ("View the decision notice for this application at Planning
Search"). That passing sentence is the only evidence the material exists.

**No browser needed** — `scripts/fetch_slough_legacy.py` does it with a
plain session:

    GET  /plansearch.php                       (establish the session)
    POST /search.php   Referer: /plansearch.php
         st=<ref>&DBName=planapp&Searchfield=Number&plannsearch=Search+for+number

The Referer is what makes it work; without it the search appears to
return nothing, which is what wrongly sent this down the browser route.

Filenames are a lossy transformation of the reference — `P/00072/096`
becomes `P72-96`, leading zeros stripped, further documents suffixed
`(2)`, `(3)` — and the series vary (`P/`, `SMI/`, `T/`, some with their
own parenthetical suffixes). Reconstructing them is guesswork, so ask
the site's search to resolve each reference and take the links it
returns. Filter out `scaling.pdf`: it is help material linked on every
results page.

Coverage: 26 of 37 hold documents; the `T/` and `SMI/` series genuinely
hold none.

## Northern Ireland — planningregister.planningsystemni.gov.uk (whole nation)

No browser needed after all, despite the Next.js front end: the pages
draw everything from an anonymous TerraQuest API, mapped 2026-08-27
with the fetch/XHR hooks in a page session. `dcp/sources/ni_planning.py`
is the adapter; the module docstring carries the details. The essentials:

- Backend: `https://api-planningregister-planningportal.pr.tqinfra.co.uk/api/v1`
- Every call needs header `TQ-Tenant: <NEXT_APP_PP_TENANT_ID>` — the
  value is public, shipped to every visitor in the page's `__ENV.js`.
  **Without it the API answers `200` with a JSON `null` body**, which is
  indistinguishable from an application that does not exist.
- `GET /application/{id}` — full metadata including
  `supportingDocuments` (documentId, guid filename, description, type).
  `{id}` is the numeric tail of the register URL we already store, and
  ids minted by the old register still resolve.
- `GET /application/{appId}/{docId}` — JSON with `documentUri`: a
  time-limited Azure blob SAS URL (~30 minutes). Redeem per document at
  download time; store the API route as the document URL, never the SAS.
- The blob is a zip wrapping a single guid-named file (a PDF, in every
  case observed). The adapter stores the inner file; a multi-member zip
  is stored as-is and logged.

## The Tascomi family — Hackney, Liverpool (and Coventry's gate)

Probed 2026-08-27. Hackney and Liverpool both retired their Northgate
registers for the same Tascomi "Council Direct" platform
(`developmentandhousing.hackney.gov.uk`, `lar.liverpool.gov.uk`), and
both serve the Coventry signature to scripted clients: landing pages
answer 200, everything behind `?fa=` answers **HTTP 202 with an empty
body**. Hackney's own page says why — "inaccessible outside the United
Kingdom due to supplier security restrictions" — and a real browser
passes without any challenge. Harvest route when needed: the browser
pane + `browser_receiver.py`, as for Coventry.

What the registers actually hold is the sharper finding:

- **Hackney did not migrate its history.** `2020/1287` (the Interxion
  energy-centre emissions detail) is absent by reference AND by
  proposal text, while the control `2026/1779` resolves. The page
  invites email to planning@hackney.gov.uk; recorded `none_published`
  with the evidence.
- **Liverpool renumbered** (`26H/2405`-style, year first). Neither the
  old `PL/INV/1646/21` nor the `21INV/1646` transposition resolves,
  and a proposal-text search returned the server's own 502 — at which
  point probing stopped for the day. Recorded as a retryable error.

## Not a user-agent problem

`scripts/probe_user_agents.py` tested one page per host with the plain
research UA and the `Mozilla/5.0 (compatible; ...)` form. Runnymede is
the only host where it mattered. For Coventry, White Horse, Broxbourne
and Slough the answer was "no difference" — the blocks are real, not a
formatting quirk.
