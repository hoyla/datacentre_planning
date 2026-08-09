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

## Not a user-agent problem

`scripts/probe_user_agents.py` tested one page per host with the plain
research UA and the `Mozilla/5.0 (compatible; ...)` form. Runnymede is
the only host where it mattered. For Coventry, White Horse, Broxbourne
and Slough the answer was "no difference" — the blocks are real, not a
formatting quirk.
