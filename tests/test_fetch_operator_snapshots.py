"""The snapshot fetcher's write decision, with no network in it.

The store is append-only (WP-A of docs/HANDOVER_SNAPSHOT_CHAIN.md), so
what matters here is when a fetch adds a file and what it calls it. Both
are pure functions of the bytes served and the store already held, which
is why they can be tested without touching an operator's website:
`held_digest` reads what the newest held file says it is, and `next_name`
allocates the name a change gets written to.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fetcher():
    spec = importlib.util.spec_from_file_location(
        "fetch_operator_snapshots",
        ROOT / "scripts" / "fetch_operator_snapshots.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(dirpath, name, digest="a" * 64, kind="html"):
    p = dirpath / name
    p.write_text(f"# url: https://example.com\n\n# fetched: 2026-08-30\n\n"
                 f"# sha256({kind}): {digest}\n\n## STRUCTURED\n\n(none)\n\n"
                 f"## VISIBLE TEXT\n\nthe page")
    return p


def test_the_held_digest_is_read_from_the_newest_file(tmp_path):
    f = _fetcher()
    _write(tmp_path, "op.2026-08-20.txt", digest="b" * 64)
    _write(tmp_path, "op.2026-08-28.txt", digest="c" * 64)
    from dcp.capacity_claims import snapshot_path
    assert f.held_digest(snapshot_path("op", tmp_path)) == "c" * 64


def test_a_pdf_snapshot_records_its_digest_under_its_own_spelling(tmp_path):
    """`# sha256(pdf):` since a spec sheet became a page like any other
    (PR #310); a skip decision that only knew `html` would re-write
    every PDF on every run."""
    f = _fetcher()
    p = _write(tmp_path, "op.2026-09-01.txt", digest="d" * 64, kind="pdf")
    assert f.held_digest(p) == "d" * 64


def test_an_unreadable_header_never_matches(tmp_path):
    """None is not equal to any digest, so a file the fetcher cannot
    make sense of causes a write rather than a silent skip — an
    unrecognised file must never be mistaken for a match."""
    f = _fetcher()
    p = tmp_path / "op.2026-08-30.txt"
    p.write_text("nothing that looks like a snapshot")
    assert f.held_digest(p) is None
    assert f.held_digest(None) is None


def test_the_first_change_of_a_day_takes_the_plain_dated_name(tmp_path):
    f = _fetcher()
    assert f.next_name("op", "2026-09-01", tmp_path) == "op.2026-09-01.txt"


def test_a_second_change_the_same_day_is_suffixed(tmp_path):
    f = _fetcher()
    _write(tmp_path, "op.2026-09-01.txt")
    assert f.next_name("op", "2026-09-01", tmp_path) == "op.2026-09-01_2.txt"
    _write(tmp_path, "op.2026-09-01_2.txt")
    assert f.next_name("op", "2026-09-01", tmp_path) == "op.2026-09-01_3.txt"


def test_a_same_day_suffix_never_predates_the_reading_it_follows(tmp_path):
    """The property the whole naming scheme rests on: sorting the names
    lexicographically has to put them in the order they were fetched.
    A `-2` suffix would fail this, because `-` sorts before `.`."""
    f = _fetcher()
    names = []
    for _ in range(3):
        n = f.next_name("op", "2026-09-01", tmp_path)
        _write(tmp_path, n)
        names.append(n)
    assert names == sorted(names)
    assert names[0] < f.next_name("op", "2026-09-02", tmp_path)


def test_a_page_that_is_a_pdf_is_sniffed_not_taken_from_the_url():
    f = _fetcher()
    assert f.is_pdf(b"%PDF-1.7 ...") is True
    assert f.is_pdf(b"<!DOCTYPE html>") is False


# ---------------------------------------------------------------------------
# The browser-harvest route (WP-D). ironmountain.com sits behind Vercel
# Attack Challenge Mode and answers every scripted client 429, so those
# pages are captured in a browser and stored with --from-file. What has
# to hold is that a harvested page goes through the SAME rendering as a
# fetched one, and that the file records which route it came by.

def test_a_harvested_page_and_a_fetched_one_render_identically(tmp_path):
    f = _fetcher()
    html = (b"<html><head><script type=\"application/ld+json\">"
            b'{"a": 1}</script></head><body><details><summary>FAQ</summary>'
            b"<p>LON-1 offers 8.7 MW</p></details></body></html>")
    direct = f.render("https://x.test/p", html, "2026-09-01", "direct")
    browser = f.render("https://x.test/p", html, "2026-09-01", "browser")
    assert direct.replace("# obtained: direct", "# obtained: browser") == browser


def test_collapsed_details_content_survives_the_extraction():
    """The lesson the Iron Mountain capture is built on: content inside a
    collapsed <details> is in the DOM but not in rendered text, so a
    browser's innerText silently omits it. visible_text() strips tags and
    evaluates no collapse state, which is why the harvest must be the
    served bytes and the extraction must be this one."""
    f = _fetcher()
    html = (b"<html><body><details><summary>How big?</summary>"
            b"<p>LON-1 offers 17,000 square meters and 8.7 MW</p>"
            b"</details></body></html>")
    out = f.render("https://x.test/p", html, "2026-09-01", "browser")
    assert "17,000 square meters and 8.7 MW" in out


def test_the_route_a_page_came_by_is_recorded(tmp_path):
    f = _fetcher()
    out = f.render("https://x.test/p", b"<p>hi</p>", "2026-09-01", "browser")
    assert "# obtained: browser" in out


def test_obtained_sits_below_the_digest_so_the_skip_still_works(tmp_path):
    """`# obtained:` is last in the header on purpose: everything that
    reads a fixed number of header lines reads them from the top, and a
    digest pushed out of that window would make every re-fetch look
    changed — a silent failure of the append-only store's no-op."""
    f = _fetcher()
    p = tmp_path / "op.2026-09-01.txt"
    p.write_text(f.render("https://x.test/p", b"<p>hi</p>", "2026-09-01", "browser"))
    import hashlib
    assert f.held_digest(p) == hashlib.sha256(b"<p>hi</p>").hexdigest()


def test_storing_the_same_harvested_bytes_twice_writes_once(tmp_path):
    f = _fetcher()
    html = b"<p>unchanged</p>"
    first = f.store("op", "https://x.test/p", html, tmp_path, "browser")
    again = f.store("op", "https://x.test/p", html, tmp_path, "browser")
    assert first is not None and again is None
    assert len(list(tmp_path.glob("*.txt"))) == 1


def test_every_iron_mountain_page_is_registered_and_held():
    """LON-2 is absent on purpose — /lon-2 404s, and its 27 MW is
    published only in the campus FAQ and a 2021 investor announcement."""
    from dcp.capacity_claims import snapshot_path
    f = _fetcher()
    slugs = [s for s, _ in f.PAGES["ironmountain"]]
    assert slugs == ["ironmountain-london-campus", "ironmountain-lon1",
                     "ironmountain-lon3"]
    assert all(snapshot_path(s) is not None for s in slugs)
