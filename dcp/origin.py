"""How an application entered the dataset, in words a reader can use.

`applications.discovered_via` is an append-only audit trail, and it is
written for machines: `energy_national:PTNO-12548129`,
`spatial:Northumberland/24/04112/FUL`, `parent_backfill:Leeds/21/09982/FU`.
Three hundred distinct values, most of them appearing once, each carrying
the identifier of whatever prompted the search.

That precision is the point — it is what lets anyone retrace why a
particular application is here — but it cannot go in a column. This
reduces each tag to the *route* that found it, so a reporter can ask the
question they actually have: is this dataset finding these sites because
we searched for the word "data centre", or because Barbour told us, or
because something sat next to a site we already knew about?

The raw array stays on the application untouched.
"""

from __future__ import annotations

# Ordered: the first matching prefix wins, so the more specific routes are
# tested before the general ones.
_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("barbour:", "Barbour ABI",
     "Named in Barbour ABI project intelligence"),
    ("nsip_energy", "Planning Inspectorate",
     "Nationally significant energy project from the NSIP register"),
    ("nsip_register", "Planning Inspectorate",
     "From the NSIP register"),
    ("dc_keyword", "Keyword search",
     "Found by searching planning registers for data-centre language"),
    ("energy_national:", "Energy search near a site",
     "Found by searching for energy infrastructure around a known site"),
    ("spatial:", "Next to a known site",
     "Found because it sits within the boundary of a site we already held"),
    ("operator:", "Operator watch-list",
     "Found by searching for a named developer, operator or adviser"),
    ("cohort:", "Curated cohort",
     "Added as part of a hand-picked group of related schemes"),
    ("parent_backfill:", "Parent application",
     "Pulled in as the parent or child of an application we already held"),
    ("foxglove", "Foxglove list",
     "From the Foxglove campaign group's published list"),
    ("duplicate_of:", "Duplicate record",
     "A council's duplicate of another application here"),
    ("exclude:", "Reviewed and excluded",
     "Considered and judged not to be a data centre"),
)


def route_for(tag: str) -> tuple[str, str] | None:
    """(label, explanation) for one discovered_via tag."""
    if not tag:
        return None
    for prefix, label, note in _ROUTES:
        if tag == prefix or tag.startswith(prefix):
            return label, note
    return None


def routes_for(tags) -> list[str]:
    """Distinct route labels for an application's tags, order preserved.

    An application can arrive by more than one route — found by keyword
    and later confirmed by Barbour — and that is worth showing rather
    than collapsing, because two independent routes to the same site is a
    different quality of evidence from one.
    """
    out: list[str] = []
    for t in tags or ():
        r = route_for(t)
        if r and r[0] not in out:
            out.append(r[0])
    return out


def explain(labels) -> str:
    """One-line explanation of a set of route labels, for a tooltip."""
    seen: dict[str, str] = {}
    for _prefix, label, note in _ROUTES:
        seen.setdefault(label, note)
    return " · ".join(seen[l] for l in labels if l in seen)
