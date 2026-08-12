"""Published aggregate figures on UK data centre power demand, with provenance.

The premise, stated because it is a domain fact and not a style choice: none
of these sources measures the quantity a planning application states. The
2026-08-10 test of the commercial directories and the NESO registers
(docs/EXTERNAL_DATA_SOURCES.md) established that no external megawatt can
become a per-site column — contracted connection capacity, IT load, standby
generation and observed draw are different numbers for the same site. This
module is the permitted form of the same material: aggregates presented
*beside* the planning-derived data, deliberately never joined to it. The
anonymised sources here (UKPN's queue and profiles) could sometimes be
re-identified to a single site from capacity, location and date; if that is
ever done it is a separate adjudicated inference stored with its method
named, not a join, and not this table.

Everything here is data entered once, by hand, from a read of the primary
source, with the locator (table or paragraph number) and the date of access
recorded. The dictionary text three figures drifted apart in taught the
lesson: the numbers on our own side of any comparison are computed by the
exporter at generation time, never written here.

Both artefacts consume this module — the workbook's External aggregates
sheet and the reader's methodology section — so they cannot disagree about
what the external sources say.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    publisher: str
    published: str
    url: str
    accessed: str
    note: str


SOURCES = {
    "ofgem_curate": Source(
        "ofgem_curate",
        "Consultation Curate — Demand Connections Reform",
        "Ofgem", "29 July 2026",
        "https://www.ofgem.gov.uk/sites/default/files/2026-07/"
        "Proposed-data-centre-connection-reforms-curate-consultation-document.pdf",
        "12 August 2026",
        "Consultation on a data centre commitment fee and queue management "
        "milestones; response deadline 16 September 2026. Its evidence base "
        "(paragraphs 2.3–2.4) includes project-level data from NESO's "
        "mandatory Information Request Notice of 13 March 2026, which is "
        "not published."),
    "neso_cfi": Source(
        "neso_cfi",
        "Demand Call for Input (CFI) — High Level Summary",
        "National Energy System Operator", "March 2026",
        "https://www.neso.energy/document/378226/download",
        "12 August 2026",
        "Aggregated results of NESO's voluntary call for input on the "
        "transmission demand queue, November 2025. 243 responses, of which "
        "229 could be linked to connection records; around 16 GW of "
        "responses could not be linked to a transmission zone. NESO's own "
        "caveat: \"These CFI insights should be considered indicative "
        "only. They represent developer intent, not confirmed "
        "deliverability.\""),
    "ukpn_queue": Source(
        "ukpn_queue",
        "Large Demand List",
        "UK Power Networks (Open Data Portal)", "updated November 2025",
        "https://ukpowernetworks.opendatasoft.com/explore/dataset/"
        "ukpn-large-demand-list/",
        "12 August 2026",
        "Anonymised list of live, committed, not-yet-energised import "
        "projects of 5,000 kVA and above across UK Power Networks' three "
        "licence areas (London, South East, East). Fields: licence area, "
        "grid supply point, anonymised name, demand technology type, "
        "required import capacity (kVA), application date. Row access "
        "requires free portal registration; the record count and schema "
        "are public."),
    "ukpn_profiles": Source(
        "ukpn_profiles",
        "Data Centre Demand Profiles",
        "UK Power Networks (Open Data Portal)", "updated monthly",
        "https://ukpowernetworks.opendatasoft.com/explore/assets/"
        "ukpn-data-centre-demand-profiles/",
        "12 August 2026",
        "Half-hourly observed load of identified (anonymised) data centres "
        "in UK Power Networks' licence areas from 1 January 2023, expressed "
        "as a proportion of the site's meter capacity, by voltage level and "
        "data centre type. The only published measurement of what UK data "
        "centres actually draw, as opposed to what they secured."),
}


# Ofgem Table 1, "Analysis of data centre queue": the size distribution of
# the ~315 data centre projects holding ~73 GW of contracted connection
# offers in the GB demand queue at June 2025. Band edges are as printed;
# treated as [lower, upper) here so the bands partition cleanly.
# (band label, lower MW, upper MW or None, projects, total MW, share of
# data centre queue MW as printed)
OFGEM_QUEUE_BANDS = (
    ("0–10 MW", 0.0, 10.0, 11, 76, "0.1%"),
    ("10–50 MW", 10.0, 50.0, 47, 1_370, "1.9%"),
    ("50–100 MW", 50.0, 100.0, 51, 3_492, "4.8%"),
    ("100–500 MW", 100.0, 500.0, 166, 36_632, "50.2%"),
    ("500 MW and above", 500.0, None, 40, 31_408, "43.0%"),
)
OFGEM_QUEUE_TOTALS = (315, 72_978)  # projects, MW — the sums of Table 1


def band_counts(values_mw) -> list[tuple[str, int]]:
    """Count per-site figures into Ofgem's Table 1 bands.

    Takes the per-site best-available megawatt figures an exporter has
    already computed (its own universe, its own preference order), so the
    comparison always describes the artefact it appears in.
    """
    out = []
    for label, lo, hi, *_ in OFGEM_QUEUE_BANDS:
        n = sum(1 for v in values_mw
                if v is not None and v >= lo and (hi is None or v < hi))
        out.append((label, n))
    return out


# What each source of a megawatt figure measures. This table is the
# journalist-facing form of the finding that kept external figures out of
# the per-site columns: the quantities are not interchangeable, and a
# comparison that mixes them manufactures a story or buries one.
# (quantity, where it appears, what it is, what it is not)
MEASURES = (
    ("IT load",
     "Planning application documents (disclosed voluntarily)",
     "Power delivered to computing equipment, as stated by the applicant.",
     "Not total site demand: excludes cooling and other overhead, so the "
     "site's whole draw is higher."),
    ("Total site demand",
     "Planning application documents (disclosed voluntarily)",
     "The development's whole electrical demand including cooling and "
     "overhead.",
     "Not comparable with IT load figures, which are smaller for the same "
     "building."),
    ("Contracted connection capacity",
     "NESO and network operator connection queues; rarely stated in "
     "planning application documents",
     "Grid headroom a project has secured the right to draw.",
     "Not consumption: operators commonly secure more than they draw, "
     "phased sites draw it over years, and the queue includes projects "
     "that will never be built — Ofgem's consultation exists because of "
     "them."),
    ("Standby generation capacity",
     "Planning application documents",
     "On-site backup plant, normally sized to carry something near full "
     "load, so it approximates the site's demand.",
     "Not a demand figure: it is backup plant, and some sites "
     "over-provide."),
    ("Observed half-hourly draw",
     "UK Power Networks' Data Centre Demand Profiles",
     "Metered import, published as a proportion of the site's meter "
     "capacity.",
     "Not attributable to a named site: the operator anonymises it, and "
     "this dataset deliberately does not attempt to match it."),
    ("Floorspace-derived estimate",
     "This dataset, where nothing better exists",
     "Building floorspace converted at 1.71 kW/m², the median across the "
     "sites here that disclose both quantities.",
     "Not a disclosure: an inference with roughly a factor-of-two spread, "
     "usable for ranking and not for quotation."),
)


@dataclass(frozen=True)
class Aggregate:
    label: str
    figure: str
    source_key: str
    locator: str
    quote: str  # verbatim where held, else ""


# Published aggregates worth having beside the planning-derived data.
# Figures are transcribed from the primary documents named; the locator is
# precise enough to check in under a minute.
AGGREGATES = (
    Aggregate(
        "GB demand connection queue, November 2024",
        "41 GW (17 GW transmission, 24 GW distribution)",
        "ofgem_curate", "paragraph 2.7",
        "Between November 2024 and June 2025 total contracted offers in "
        "the demand queue rose sharply from 41 GW (17 GW transmission, 24 "
        "GW distribution) to 125 GW (97 GW transmission, 29 GW "
        "distribution) in June 2025."),
    Aggregate(
        "GB demand connection queue, June 2025",
        "125 GW (97 GW transmission, 29 GW distribution)",
        "ofgem_curate", "paragraph 2.7", ""),
    Aggregate(
        "Data centres' share of the demand queue",
        "≈73 GW across ≈315 projects, 1 MW to 1,500 MW",
        "ofgem_curate", "paragraph 2.8",
        "approximately 73 GW of the total demand queue are data centres, "
        "comprising around 315 data centre projects with total contracted "
        "capacity ranging from 1 MW to 1,500 MW."),
    Aggregate(
        "Peak GB electricity demand 2025/26, as the consultation cites it "
        "for scale",
        "45 GW — net system demand, net of embedded generation, so not "
        "total GB consumption at peak; the comparison with the 73 GW "
        "queue is Ofgem's, of two different quantities",
        "ofgem_curate", "paragraph 2.8 (source: NESO Triad Data 2025/26)",
        ""),
    Aggregate(
        "Connection requests reclassified from battery to data centre",
        "At least 9 GW, May 2024 – August 2025",
        "ofgem_curate", "paragraph 2.10",
        "between May 2024 and August 2025 at least 9 GW of data centres in "
        "the transmission queue had modified their connection request from "
        "a 'battery' technology to data centre."),
    Aggregate(
        "Average data centre build cost assumed by the regulator",
        "£9.5 million per MW (implying £693 billion for the full queue, "
        "around 23% of 2025 UK GDP)",
        "ofgem_curate", "paragraphs 2.8 and 4.12", ""),
    Aggregate(
        "Data centre demand in NESO's voluntary call for input",
        "50,802 MW across 152 project phases",
        "neso_cfi", "Technology tables, pages 4–5",
        "Data centres make up over half of responses, both in terms of "
        "volume and capacity"),
    Aggregate(
        "Data centre projects reporting financial commitment with FID "
        "evidence",
        "71 projects (21,598 MW) yes; 77 projects (29,590 MW) no",
        "neso_cfi", "chart: Project has received Financial Commitment "
        "with FID Evidence? (Data Centre only), page 5", ""),
    Aggregate(
        "All demand projects reporting financial commitment with FID "
        "evidence",
        "94 projects (27,726 MW) yes; 149 projects (64,274 MW) no",
        "neso_cfi", "chart: Project has received Financial Commitment "
        "with FID Evidence? (All), page 5", ""),
    Aggregate(
        "Data centre projects with a secured off-taker",
        "32% secured; 68% not yet secured",
        "neso_cfi", "Key insights, page 2",
        "Only 32% of data centre projects have secured off-takers, while "
        "68% have not yet secured one, often pending a firm connection "
        "date."),
    Aggregate(
        "Committed large demand projects in UK Power Networks' areas",
        "496 not-yet-energised import projects of 5 MVA and above "
        "(anonymised)",
        "ukpn_queue", "dataset record count at access", ""),
)


def check() -> None:
    """Internal consistency of the transcribed Table 1, run by tests."""
    projects = sum(b[3] for b in OFGEM_QUEUE_BANDS)
    mw = sum(b[4] for b in OFGEM_QUEUE_BANDS)
    assert (projects, mw) == OFGEM_QUEUE_TOTALS, (projects, mw)
    for agg in AGGREGATES:
        assert agg.source_key in SOURCES, agg.source_key
