# Session handover — 2026-08-11

For whoever picks this up next. Written at the end of the day the 2.1
release was regenerated, with nothing running.

Read [ROADMAP.md](../ROADMAP.md) for what is outstanding,
[HISTORY.md](../HISTORY.md) for why things are the way they are, and
[REGENERATION_RUNBOOK.md](REGENERATION_RUNBOOK.md) for the release chain
and its traps. This document covers only what is *in flight* and what is
easy to get wrong.

---

## What is running right now

**Nothing.** The Studio reader was stopped deliberately with `TERM` at
12:15 so the 2.1 boundary would be clean — everything read is
adjudicated, and nothing was written underneath the exports.

**Restart it once 2.1 is merged**, and not before, or the boundary stops
being the thing the release was stamped at:

```sh
ssh hoyla@192.168.50.113 'cd Code/datacentre_planning &&
  HF_HUB_OFFLINE=1 nohup .venv/bin/python -u scripts/deepread_run.py --tier A \
    >> data/deepread_run.log 2>&1 &'
```

Resume is a database query — documents already logged for this
(model, prompt_version) are skipped — so stopping cost nothing but the
time it has been off. [MAC_STUDIO.md](MAC_STUDIO.md) has the live-check
that does not lie (`pgrep -f deepread_run` matches a leftover `tail -f`).

---

## What 2.1 is, and what is left of it

A correctness release. **No new documents were acquired and almost no new
reading happened** — 2 documents were recovered from a parse-failure
backlog. What changed is what the artefacts are willing to claim, and
several things they were claiming wrongly.

Left to do, in order:

1. **Merge the release branch.** That is what deploys — EdgeOne builds
   from git, so writing `index.html` is not publishing it. This was a
   correction Luke made mid-session and it is worth keeping straight.
2. **Re-probe the gate from outside**, after the merge:
   `scripts/probe_gate.sh https://dc-review-gdn-hoyla.edgeone.app`. 22
   paths plus a forged cookie. A browser with a session cannot show you
   what this checks.
3. **Restart the Studio** (above).
4. **Luke is archiving the phase 2 workbook and database** from the Drive
   root by hand.

---

## What was wrong, and is now not

Each of these reached a released artefact, and each was reported by
someone using it rather than found by a test.

**A number that did not say what it counted.** A site panel read
"Standby generators: 109" above "Diesel (147), HVO (39)". 109 is plant;
147 and 39 are passages of text mentioning a fuel. Both correct, neither
saying what it was of, two lines apart. Now "109 units" and "Diesel (147
mentions)". The same idiom was in three places — fuels, cooling methods,
party names — and is now one function.

**A page number that was not a page.** 17,724 findings cite an index that
is not a page: a `.docx` has sections, a workbook has sheets. The
extractor has recorded which since the format loaders landed, but the
caches are files and every export is SQL, so it never reached a reader.
`documents.pagination` now carries it (migration 020) and
`extract.cite_page` renders it once for everyone.

**Map card links that did nothing.** The card is a child of the map, so
pressing a link started a map drag, and the first pixel of movement hid
the card before the mouseup. All three links failed at once, which reads
as "links are broken" rather than a map bug.

**An 800 MW site that was 300.** North Hyde Gardens published 800 MW of
on-site generation against a 256 MW site. The document says plainly:
"100 generators across the site giving a thermal output of over 800mw and
nearly 300MWe". Two readers described it as thermal in their own
reasoning and filed it as generation anyway.

---

## Things that will bite

**The release folder default.** `build_drive_staging.py` used to default
`--release-dir` to a hardcoded `phase2_build`, so the 2.1 run staged
phase 2's workbook and database beside 2.1's per-site files and said so
in one line that reads like success. Now defaults to the newest
`*_build` and prints which it chose. **Read that line.**

**Numbers hardcoded in the data dictionary drift.** The count of sites
disclosing water consumption exists as three independent figures written
at three moments — HISTORY 93, the dictionary 76, live 119 — and only
the third is currently true. Making them computed is ROADMAP work, not
done. Until then, measure before quoting any dictionary statistic.

**`FLOOR_AREA_KW_PER_SQM = 1.71` is due a re-measurement**, not a change.
It drives the published estimate for every site with no disclosed
capacity. An ad-hoc query suggested it may have moved, but with different
criteria from the original calibration, so it is a flag and nothing more.
Reproduce the original criteria from git history first.

**Two prose definitions is one too many.** `load_coverage_detail` counts
prose as tiers A and B and reports the repetitive tier separately. Any
new consumer must use that definition, or the page shows two numbers for
one quantity — which it briefly did during this release, caught only by
building the artefact and reading it.

**Verify the built artefact, not the diff.** Three of this session's
defects — the two prose definitions, a chip that took its own flex
column, an energy checkbox that went dead — were invisible in review and
obvious in a browser.

---

## How Luke works

He is a journalist who has spent three decades on newsroom software, on
the product and UX side, and he finds bugs by opening the thing and
poking it. Every reader defect fixed today came from him or a reporter
using the release, not from a test.

He wants pushback, not agreement, and he is right often enough that the
pushback has to be grounded rather than reflexive — twice today he
challenged a change and was right to, and once he overrode a documented
convention for a reason I did not have (he knew which users were on which
artefact).

**When he corrects something, build the durable form** — a default, a
constant, a shared function, a test — rather than resolving to remember.
And when a claim is retracted, sweep every place it was asserted: code,
comments, commit messages, PR bodies, the runbook, HISTORY, and the
reader's own dictionary text.
