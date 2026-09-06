"""A corpus statistic in generated prose is computed, never typed.

The count of sites disclosing water consumption reached three published
surfaces as three hand-typed numbers written at three moments — "only 93
sites" in the reader's front-page caveat and the workbook's release row,
"119 of 429 sites" in the data dictionary, which the reader renders onto
the same page a scroll away — and on 2026-09-04 every one was wrong: the
live figure under the site profile's own predicate was 169 of 500. Each
had passed a full test run, because nothing asserted that a number in
prose matched the data it described. The determinism test would have
preserved a wrong constant byte for byte.

Two rules, on the `test_release_defaults.py` pattern — a rule over the
tree, verified by reintroducing the bug:

1. No string constant in either exporter may carry a literal count of
   sites, documents, findings, applications or figures, unless it is
   named in `ALLOWED` below. That list is a worklist, not a pardon:
   every entry must still match something, so an entry whose literal
   has since been computed fails the test until it is removed, and the
   list can only shrink.

2. The water count reaches all three surfaces from one function.

What the rule cannot see, said plainly: a number written in words
("twenty-two largest figures", "six campuses") and a count separated
from its noun by more than one word ("1,667 adjudicated on-site
generation figures"). Those are listed in ROADMAP under the same item.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXPORTERS = ("scripts/export_reader.py", "scripts/export_handover.py")

NOUN = r"(?:sites?|site rows|documents?|findings?|applications?|figures?)"
# `93 sites`, `119 of 429 sites`, `43 site rows`, `116 figures`; one word
# may sit between the number and the noun (`47 sites stating` needs
# none; `53 sites disclosing` none; `28 applications behind` none — the
# slot is for `1,667 adjudicated figures`-shaped phrases), but not a
# conjunction or preposition, which is how `row 1, and finding` and
# `2015 and sites` read as counts. A four-digit year is not a count.
STOPWORD = r"(?!(?:and|or|to|from|of|in|at|by|for|with|the|a|an)\s)"
LITERAL_COUNT = re.compile(
    r"\b(?!(?:19|20)\d\d\b)\d[\d,]*\s+(?:" + STOPWORD + r"[\w-]+\s+)?" + NOUN + r"\b",
    re.I)
# A string that is SQL is not prose: `SELECT 1 FROM documents d` carries
# a digit, a word and a noun and states nothing to a reader.
SQL_SHAPED = re.compile(r"\bSELECT\b.*\bFROM\b", re.S)
# Nor is a stylesheet or a script: the reader's `CSS` constant explains
# its rules in `/* … */` comments with worked examples ("56 of 69
# documents analysed", "190 of 429 sites"), which are commentary, not
# claims. A count typed into JS would be a different defect from this
# one, and is out of this rule's sight — said here so nobody assumes
# the rule covers it.
STYLE_OR_SCRIPT_SHAPED = re.compile(r"/\*.*?\*/", re.S)

# The remaining literals, each a corpus fact typed at a moment. The test
# fails if a new one appears, and fails again if one of these is fixed
# without being struck from here — so this is where the class is worked
# down. Keyed on a substring that identifies the sentence.
ALLOWED: dict[str, str] = {
    "116 figures rested on a quote": "reader methodology: the no-unit-quote adjudications, measured 2026-08-10",
    "on 43 site rows": "reader methodology: floor-area estimates, measured at 2.2",
    "855 findings across 51 sites": "reader methodology: the sub-50 MW bound, also typed in ROADMAP",
    "Across the 47 sites stating both": "reader methodology: the generation-to-load ratio median",
    "measured across the 53 sites disclosing both": "dictionary: the 1.71 kW/m² calibration, its own ROADMAP item",
    "28 applications behind bot protection": "release row: Coventry, countable from KNOWN_BLOCKED_HOSTS",
}


def _prose_constants(path: Path):
    """String constants that reach generated output: every `ast.Constant`
    str, including the literal parts of f-strings, minus bare-string
    statements (docstrings and comment-strings), which explain and do
    not render."""
    tree = ast.parse(path.read_text())
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            doc_ids.add(id(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in doc_ids:
            yield node.lineno, node.value


def _offenders(path: Path) -> list[tuple[int, str]]:
    out = []
    for lineno, text in _prose_constants(path):
        if SQL_SHAPED.search(text) or STYLE_OR_SCRIPT_SHAPED.search(text):
            continue
        for m in LITERAL_COUNT.finditer(text):
            snippet = text[max(0, m.start() - 40):m.end() + 30]
            out.append((lineno, " ".join(snippet.split())))
    return out


def _allowed(snippet: str) -> bool:
    return any(key in snippet for key in ALLOWED)


@pytest.mark.parametrize("rel", EXPORTERS)
def test_no_literal_corpus_count_in_generated_prose(rel):
    offenders = [(i, s) for i, s in _offenders(ROOT / rel) if not _allowed(s)]
    assert not offenders, (
        f"{rel} types a corpus count into generated prose. Compute it (the "
        f"water count is the pattern: dcp.site_profile.water_disclosure, "
        f"interpolated), or if it is a quotation of an external figure, "
        f"say so here in ALLOWED with its source:\n"
        + "\n".join(f"  line {i}: …{s}…" for i, s in offenders))


def test_every_allowed_literal_still_exists():
    """The list only shrinks. An entry for a literal that has since been
    computed is stale, and stale allowances are how a guard stops
    guarding."""
    snippets = [s for rel in EXPORTERS for _, s in _offenders(ROOT / rel)]
    orphans = [k for k in ALLOWED if not any(k in s for s in snippets)]
    assert not orphans, f"ALLOWED names literals no longer in the exporters: {orphans}"


def test_the_guard_examines_the_files_it_guards():
    for rel in EXPORTERS:
        assert (ROOT / rel).is_file(), rel
    # It must be able to see a literal at all: feed it one.
    fake = 'x = "only 93 sites disclose anything"\n'
    tree = ast.parse(fake)
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
    assert any(LITERAL_COUNT.search(c) for c in consts)


class TestTheWaterCountIsOneNumber:
    """Rule 2: the three surfaces read one function."""

    def _handover(self):
        spec = importlib.util.spec_from_file_location(
            "export_handover_for_test", ROOT / "scripts" / "export_handover.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["export_handover_for_test"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_the_old_literals_are_gone(self):
        """From the prose, not the source: a comment may cite the
        historical mistake, as the one above `DICTIONARY` does."""
        for rel in EXPORTERS:
            prose = "\n".join(text for _, text in _prose_constants(ROOT / rel))
            assert "only 93 sites" not in prose, rel
            assert "119 of 429" not in prose, rel

    def test_both_exporters_call_the_one_function(self):
        for rel in EXPORTERS:
            assert "site_profile.water_disclosure(" in (ROOT / rel).read_text(), rel

    def test_the_dictionary_entry_is_a_placeholder_until_filled(self):
        hv = self._handover()
        raw = [d for s, c, d in hv.DICTIONARY if c == "Water evidence"]
        assert len(raw) == 1
        assert "{water_sites}" in raw[0] and "{water_of}" in raw[0]
        filled = [d for s, c, d in hv.dictionary(water={"sites": 169, "of": 500, "pct": 34})
                  if c == "Water evidence"]
        assert "only 169 of the 500 sites read disclose" in filled[0]
        assert "{water_" not in filled[0]

    def test_the_renderers_use_the_filled_dictionary_not_the_template(self):
        """Rendering `DICTIONARY` directly would print the placeholder."""
        reader = (ROOT / "scripts/export_reader.py").read_text()
        handover = (ROOT / "scripts/export_handover.py").read_text()
        assert "hv.dictionary(water=water)" in reader
        assert "for sheet, col, desc in hv.DICTIONARY" not in reader
        assert "for row in dictionary(water=water)" in handover
        assert "for row in DICTIONARY:" not in handover

    def test_no_placeholder_survives_any_filled_entry(self):
        hv = self._handover()
        for _s, _c, d in hv.dictionary(water={"sites": 1, "of": 2, "pct": 50}):
            for ph in hv.DICTIONARY_PLACEHOLDERS:
                assert ph not in d


@pytest.mark.integration
def test_the_aggregate_counts_disclosure_over_the_sites_read(db_conn):
    """The roll-up is the per-site query counted, and its denominator is
    the sites read, not the sites that exist — asserted on a seeded
    corpus rather than recounted from a live one.

    The first version of this test recounted `db_conn`'s corpus and
    compared; `db_conn` is the truncated test database, so it compared
    0 with 0 and passed without testing anything. Three sites: one whose
    read document carries a consumption finding, one whose read document
    carries drainage findings only, one holding nothing read. A site that
    has disclosed nothing because nobody read it is not silent, and the
    denominator must not say it is (Luke, 2026-09-06).
    """
    from dcp import repo
    from dcp import site_profile as sp

    source_id = repo.ensure_source(db_conn, name="planit", kind="aggregator",
                                   base_url="https://x")

    def app(ref):
        return repo.upsert_application(
            db_conn, source_id=source_id,
            app={"name": ref, "description": "data centre",
                 "location_y": 51.5, "location_x": -0.1},
            discovered_via=["test"])

    def site(key, app_id):
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO sites (site_key, classification, radius_km, "
                        "materialised_at) VALUES (%s, 'ours_only', 1.0, now()) "
                        "RETURNING id", (key,))
            site_id = cur.fetchone()[0]
            cur.execute("INSERT INTO site_members (site_id, application_id, joined_via, "
                        "materialised_at) VALUES (%s, %s, 'singleton', now())",
                        (site_id, app_id))
        return site_id

    def read_document(app_id, sha):
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO documents (application_id, url, content_sha256, "
                        "bytes_path, fetched_at) VALUES (%s, %s, %s, 'x.pdf', now()) "
                        "RETURNING id", (app_id, f"https://x/{sha}.pdf", sha))
            doc_id = cur.fetchone()[0]
            cur.execute("INSERT INTO deepread_log (document_id, application_id, model, "
                        "prompt_version, tier, read_state, pages_total, pages_sent) "
                        "VALUES (%s, %s, 'fake', '1.0', 'A', 'read', 1, '{1}')",
                        (doc_id, app_id))
        return doc_id

    def finding(app_id, doc_id, signal_type):
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO findings (application_id, document_id, model, "
                        "signal_family, signal_type, value_text) "
                        "VALUES (%s, %s, 'fake', 'water', %s, 'x')",
                        (app_id, doc_id, signal_type))

    a1, a2, a3 = app("Testing/24/2001/FUL"), app("Testing/24/2002/FUL"), app("Testing/24/2003/FUL")
    site("SITE-discloses", a1); site("SITE-drainage-only", a2); site("SITE-nothing-read", a3)
    d1 = read_document(a1, "a" * 64)
    finding(a1, d1, "water_consumption_estimate")     # matches CONSUMPTION_SIGNAL_RE
    finding(a1, d1, "surface_water_discharge_rate")   # does not
    d2 = read_document(a2, "b" * 64)
    finding(a2, d2, "surface_water_discharge_rate")
    db_conn.commit()

    agg = sp.water_disclosure(db_conn)
    assert agg == {"sites": 1, "of": 2, "pct": 50}, agg

    with db_conn.cursor() as cur:
        cur.execute(sp.COOLING_TEXTS_SQL, (sp.CONSUMPTION_SIGNAL_RE.pattern,))
        per_site = {row[0]: row[2] for row in cur.fetchall()}
        cur.execute("SELECT count(*) FROM sites WHERE retired_at IS NULL")
        live = cur.fetchone()[0]
    assert per_site == {"SITE-discloses": 1, "SITE-drainage-only": 0}
    assert agg["sites"] == sum(1 for n in per_site.values() if n)
    assert live == 3 and agg["of"] < live, "nothing-read is not silent"
