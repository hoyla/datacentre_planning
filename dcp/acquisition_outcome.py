"""What a fetch attempt is allowed to conclude about an application.

`none_published` is a *settled* verdict: it takes an application out of
the outstanding queue for good. So it has to mean "the register was
reached and it holds nothing" and never "we reached the register and
failed to retrieve what it listed". Storing the second as the first is
the mistake HISTORY records in six costumes already — a blocked page
logged as a council that publishes nothing, a missing text cache logged
as an empty one, a short fetch logged as complete. The rule it settled
on is mechanical: **a stage that could not look must not record that it
looked and found nothing.**

Two shapes of that mistake are possible here, and both were reachable
in `fetch_outstanding.py` before this module existed, because its
mapping consulted `error_class` — which describes the *listing* fetch —
and never the per-document error count sitting in the same summary:

* the register listed documents and every one of them failed to
  download, leaving `downloaded == 0` and `error_class is None`;
* the register listed documents and every one was already held, so
  nothing was downloaded this run and, again, `error_class is None`.

The first is a failure and must stay queued. The second is a success.
Neither is a register that publishes nothing.

The summary keys come from the adapters' `fetch_documents_for_application`:
`downloaded`, `errors`, `links_found` (what the register listed) and
`skipped_existing` (listed, and already held from a previous run).
"""

from __future__ import annotations

# Verdicts that remove an application from the outstanding queue. Kept
# here beside the rule that awards them so the two cannot drift apart.
SETTLED = ("none_published", "portal_blocked", "login_required", "no_adapter")


def classify_outcome(summary: dict) -> tuple[str, str | None]:
    """The outcome for one fetch attempt, and the detail to record with it.

    Returns one of `partial`, `fetched`, `none_published` or `error`.
    """
    got = summary.get("downloaded") or 0
    errs = summary.get("errors") or 0
    listed = summary.get("links_found") or 0
    held = got + (summary.get("skipped_existing") or 0)
    error_class = summary.get("error_class")

    # Something was listed and is still not held. Whether anything at all
    # arrived this run only changes the wording, not the verdict: the
    # application is unfinished either way and stays queued.
    if listed and held < listed and (got or errs):
        return "partial", (f"{held} of {listed} listed documents retrieved"
                           + (f" ({errs} failed)" if errs else ""))
    # Documents arrived, or everything the register listed is already
    # held from an earlier run.
    if got or (listed and held >= listed):
        return "fetched", None
    # The only route to a settled negative: nothing was listed, and
    # nothing failed on the way to finding that out.
    #
    # `no_documents_in_store` is deliberately NOT on this list, though
    # `scripts/relist_refetch.py` once accepted it. Newport publishes
    # from a separate docstore, and `fetch_newport_docstore.fetch_doc_list`
    # still ends `return parse_doc_list(r.text) or []` — so a page it
    # could not parse and a store that is genuinely empty arrive here as
    # the same empty list. Until that `or []` is removed and an
    # unparseable page carries its own error class, the signal cannot
    # earn a settled verdict. It cost 17 applications: every Newport
    # entry in the settled population offered documents and held none,
    # 350 of them at Uskmouth Power Station alone.
    if listed == 0 and errs == 0 and error_class in (None, "no_documents"):
        return "none_published", error_class
    return "error", (error_class
                     or f"{errs} document failures, {listed} listed, "
                        "none retrieved")
