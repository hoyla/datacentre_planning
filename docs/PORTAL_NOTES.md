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

## The manual inbox — documents obtained by hand

`data/raw/manual/` is the staging area for anything the adapters could
not fetch: a bulk zip downloaded through a browser, files sent by an
authority, a portal that blocks scripts. `scripts/ingest_inbox.py`
content-hashes each file into the single document store, records it
with the provenance a hand download can honestly carry (the
application's portal page plus the council's own filename), regenerates
the manifest, and empties the folder — so a non-empty inbox always
means work outstanding. Two folder layouts resolve: one folder per
application named after its reference with `_` or `:` for `/`
(`Havering_P0384.15`), or a council folder holding one folder per
reference (`Havering/P0384.15`); a trailing `(PTNO-…)` annotation is
ignored. A folder that does not resolve to exactly one application is
left in place and named, never guessed.

**A page capture is not a document.** A portal page printed to PDF for
an application that lists no documents is evidence of *absence*.
Dropping it in the inbox would file it as that application's one
document and invert the finding. `scripts/record_portal_check.py`
records the check instead — an append-only `acquisition_outcome` row
under the `browser_probe` route with who checked, when and what they
saw — and files the capture under `data/raw/manual_bundles/` with the
other hand-obtained material, naming the path in the row. Melville Gate
(`Midlothian/07/00051/FUL`, 2026-09-02) is the worked case: the Idox
adapter had recorded `none_published` on 8 August as
"no_documents_or_unparseable", which is two findings in one string;
Luke's check on the page settles which. A capture of a page that *does*
list documents may go in with them, under a filename that says what it
is — Creek Way's `OcellaWeb.pdf` was renamed to say so before ingest.

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

**One exception to that sentence, found 2026-09-04** while checking what
the Agile adapter had settled. Eleven Slough applications carry a settled
`none_published` from the Agile API. Ten are the `T/` and `SMI/` series
above, so the note covers them. The eleventh is **`Slough/P/20054/000`**,
a `P/` reference holding nothing while its own sibling `P/20054/001`
holds ten — the `P/` series is the one that does live in the legacy
store, so this is the shape of an application whose documents were never
asked for there. **Run on 2026-09-04**: the store answered "No results
found" for it and for the other ten, with six references known to hold
legacy documents returning their exact corpus counts as the control
that the search could see. All eleven now carry that check in
`acquisition_outcome` on the `slough_legacy` route — the script records
its own checks since PR #387 — so the sentence above rests on the record
rather than on this note.

**The Agile API can answer 200 with a body that is not a listing** — the
tenant-header failure returns `{"message": "Client has not beeing
selected"}` [sic] with a 200. Until 2026-09-04 the adapter read any
non-list body as an empty list, which is a settled `none_published`:
`AgileClient.documents()` now raises `UnrecognisedListing` instead, so
the application stays queued. An empty *list* is still a real answer and
still settles, because on this register it is usually true.

## Exeter — Idox refuses the documents tab; the council's own page serves them (7 applications)

`publicaccess.exeter.gov.uk`'s summary tab is public, and its documents
tab answers HTTP 200 with "Error — Permission Denied … restricted to
specific users" whether or not a session cookie from the summary page
is carried. That is the council's setting, not a block: Exeter is still
Exeter, and no successor host exists. The 8 August fetch read it as a
register publishing nothing and settled five applications on it.

The documents are published elsewhere, the Newport shape:

    https://exeter.gov.uk/planning-services/permissions-and-applications/related-documents/?appref=<ref>

lists every document under its correspondence type — 89 for
`19/0330/FUL` — as `onclick="window.open('https://planningdocs.exeter.gov.uk/servlets/direct/<token>/2/<id>/1/1/AS_PDF_FILE', …)"`,
and a plain GET on that servlet URL returns the PDF (7.9 MB,
`application/pdf`, `%PDF-1.4`), no session, no browser. An adapter is
the Newport docstore's shape: parse the `window.open` URLs, GET each,
store under the register's own filename. Not built, because six of the
seven Exeter applications are Exeter College's Hele Building, excluded
by exception on 2026-09-06 (`data/priors/project_exclusions.yaml`); the
seventh, `24/1536/OUT`, an energy-centre outline in no site, waits with
the adjacency review. The route is recorded here so the next Exeter
application does not start from "Permission Denied".

## Derby — Idox refuses the documents tab; the External Documents tab names the council's store (6 applications)

`eplanning.derby.gov.uk`'s documents tab answers HTTP 200 with
"Permission Denied … restricted to specific users" — the Exeter shape —
and the 8 August fetch settled five live applications as
`none_published` on it; a sixth, `18/01557/NONM`, had been recorded
`withdrawn_from_view`. The register itself says where the documents
are: its *External Documents* tab
(`applicationDetails.do?activeTab=externalDocuments&keyVal=…`, Luke's
pointer, 2026-09-06) links to

    https://docs.derby.gov.uk/padocumentserver/index.html?caseref=<ref>

a page whose script loads `MainTable.aspx?caseref=<ref>`: a table of
type, description, published date and document id, headed "Documents
found N", with each row opening `DownloadDocument.aspx?docid=<id>` —
which serves the PDF to a plain GET, no session, no browser
(`application/pdf`, 110 KB for the first covering letter). 62 documents
across the six: 12, 6, 4, 13 and 23 for the five refused, 4 for the one
"withdrawn from view", which the store lists like any other.

`scripts/fetch_derby_docstore.py` is the route, on the Newport docstore
and Slough legacy pattern: the listing is typed (the count present and
matching the rows, or the page is unrecognised and stays retryable), the
verdict comes from `classify_outcome` under the adapter `derby_docstore`,
and bytes land in the standard per-application layout with the download
URL as provenance. The captured listing is `tests/fixtures/derby/`.

The `externalDocuments` tab is an Idox feature, not Derby's: it is the
first place to look on any Idox register whose documents tab refuses.

## Doncaster — Newport's document store, second council (5 applications)

`planning.doncaster.gov.uk`'s Idox documents tab refuses with an HTTP
200 ("Permission Denied"), and five live applications — a gas-engine
station, a cabin data centre, two battery schemes and a BESS — were
settled `none_published` on it on 8 August. The register's *External
Documents* tab (Luke, 2026-09-06: "Doncaster works the same way") links to

    https://necdm.doncaster.gov.uk/PublicAccess_LIVE/SearchResult/RunThirdPartySearch?FileSystemId=DP&FOLDER1_REF=<ref>

which is Newport's store to the letter — the Public Access document
module, the listing embedded as `var model = {...}` with a `Guid` per
document, each served by `Document/ViewDocument?id=<guid>` to a plain
GET — under a different host and file system id. The Newport parser
read the captured page unchanged: 16 documents for `19/01957/FUL`; 30,
12, 53 and 86 for the other four, 197 in all.

`scripts/fetch_newport_docstore.py` now carries a `STORES` table
(council prefix → host, FileSystemId) and picks the store from the
reference; `--council Doncaster --all-missing --dry-run` lists what the
store holds. The listing audit routes `planning.doncaster.gov.uk` to
`doncaster_docstore` as it routes Newport, so a re-list measures the
store and not the tab; the refetch handles both. Captured listing in
`tests/fixtures/doncaster/`. The third council on this module gets a
row in `STORES`, not a script.

## The External Documents tab, read across every refused Idox register (2026-09-06)

After Derby and Doncaster, one GET of `activeTab=externalDocuments` on
one application per remaining council with a refused documents tab.
Every one but Brighton (212 bytes on every tab) links off-host, in
four shapes:

- **The Public Access document module** (Newport's, `RunThirdPartySearch?FileSystemId=…&FOLDER1_REF=…`,
  `var model` page, `ViewDocument?id=<guid>`): Adur & Worthing (`docs.adur-worthing.gov.uk`, `DA`),
  Horsham (`iawpa.horsham.gov.uk`, `DH`), Huntingdonshire (`docs.huntingdonshire.gov.uk`, `PS`),
  Mid Sussex (`padocs.midsussex.gov.uk`, `DM`). The Newport parser read
  all four captured pages unchanged — 24, 37, 14 and 80 documents — so
  each is a row in `fetch_newport_docstore.STORES` and an entry in
  `relist_audit.DOCSTORE_HOSTS`. Ten applications, 417 documents
  listed, across the four.
- **Civica "Planning Documents"** (`…/planning/planning-documents?SDescription=<ref>`):
  Gateshead (`myserviceplanning.gateshead.gov.uk`), Chelmsford
  (`planning.chelmsford.gov.uk`), Reigate & Banstead
  (`dmdocs.reigate-banstead.gov.uk`), Southend
  (`publicedrms.southend.gov.uk`). The page is an empty shell that
  loads `civica/Bundles/civica.loader.js` and fills the document list
  by API. **Built the same evening** — `scripts/fetch_civica_docstore.py`,
  the API found by watching the page's own requests: `POST
  Handler.ashx/keyobject/search` with `{"refType": "GFPlanning",
  "searchFields": {"SDescription": "<ref>"}}` gives the case's
  `KeyNumber`; `POST Handler.ashx/doc/list` with it gives
  `CompleteDocument[]` and `RowCount`; `GET
  Handler.ashx/Doc/pagestream?cd=download&pdf=false&docno=<DocNo>`
  serves the file. All session-free; all four councils carry the same
  `APIUrl` and RefType in their shell page. Two guards the shape
  demands: the search endpoint answers a search it does not understand
  with the *whole register*, so a result is trusted only when exactly
  one case says the reference back; and the list is trusted only when
  its rows match `RowCount`. Eight applications, 407 documents
  (Chelmsford's `25/01716/FUL` 219, Reigate's 89, Gateshead's `DC/25/00366/FUL` 52).
  Captured search and list JSON in `tests/fixtures/civica/`.
- **Bedford** (`edrms.bedford.gov.uk/SearchResults.aspx?appNumber=<ref>`,
  "Objective" planning): a server-rendered table naming each file —
  fourteen for `24/02188/FUL` (`24 02188 FUL APP FORM..pdf`, the
  decision notice and officer's report, drawings V01–V06, the
  consultation list, an environmental-health response) — each a
  single-quoted `href='https://edrms.bedford.gov.uk/OpenDocument.aspx?id=<token>&name=<file>'`,
  plus one `PlanningBrowse.aspx?id=<token>` folder link. (The opaque
  `/<base64>.html` link on the page is not a document: a plain GET
  answers 404 "Blocked".) **Behind a validation gate**: the fifth
  request of the evening — the first `OpenDocument` GET — and every
  request since answers a 1 KB "User validation required" page asking
  for the text in an image — "validation needed due to the detection of
  invalid input from this client IP address, error code: 338, number
  of attempts left: 5".
  That is a CAPTCHA, which this project does not work around; the
  gate is the council's. So the two Bedford applications went by hand
  the same evening: Luke opened the links in a browser (the gate lets
  a person through), saved into `data/raw/manual/`, and
  `scripts/ingest_inbox.py` filed them under the `manual` route —
  `24/02188/FUL` 15 of 15, `26/00355/MAO` 50 of 51, the CIL question
  form refusing to download. Two notes for next time: the inbox wants
  one folder per application (`Bedford_26_00355_MAO`), and filenames
  with a single dot before the extension (`V12.pdf`) came down in a
  separate batch from the double-dot ones (`V11..pdf`), which is how
  fifteen were missed on the first pass. Whether the gate is a burst
  limit a slower client stays under is untested, and not to be tested
  by hammering it.
- **Neath Port Talbot** (`appsportal2.npt.gov.uk/ords/idocs12/f?p=Planning:2:0::NO::P2_REFERENCE:<ref>`,
  Oracle APEX): a results table, paged "1 - N of N", with direct
  `maps.npt.gov.uk/iDocsPublic/ShowDocument.aspx?id=<n>` links served
  to a plain GET (`Application/pdf`, 504 KB). **Built the same
  evening** — `scripts/fetch_neath_docstore.py`, the count present and
  matching the rows or the page is unrecognised; two documents for
  `P2024/0791`, the EIA screening request and its decision. The audit
  and the refetch route `planningonline.npt.gov.uk` to it.

## Selby — register moved to North Yorkshire (70 applications)

Selby District Council was abolished on 1 April 2023 and its Idox Public
Access register was folded into North Yorkshire's. `public.selby.gov.uk`
now answers with an **expired certificate** and, behind it, "Error —
Permission Denied. You do not have permission to view the page" on every
documents tab, served with HTTP 200 and full council chrome — which the
adapter read on 2026-08-08 as a register publishing nothing, and settled
18 applications on. PlanIt still records the old URL.

The same page resolves on the successor, **keyVals intact**:

    https://publicaccess.northyorks.gov.uk/online-applications/applicationDetails.do?keyVal=<KEY>&activeTab=documents

Six of six sampled on 2026-09-06 answered with documents (10, 10, 6, 6,
60 and 81), read by the Idox parser unchanged. The corpus held 70 Selby
applications and not one document, across six live sites — 19 of them
on Eggborough Power Station's two data centres, plus Drax. Selby is the
only host in the corpus from a council abolished in 2023.

`idox.SUCCESSOR_HOSTS` holds the swap; `_documents_tab_url` and the
reader's register links apply it, `applications.url` keeps what PlanIt
said, and the reader shows "moved from public.selby.gov.uk" beside the
link. The 18 verdicts are superseded by the fetch's own rows, never
edited.

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
