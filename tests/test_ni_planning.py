"""The NI register adapter's pure parts.

The API itself was established by hand on 2026-08-27 (module docstring
has the route map); these tests pin the local logic — id extraction and
the zip unwrapping — because both have failure modes that would store
the wrong bytes silently.
"""

from __future__ import annotations

import io
import zipfile

from dcp.sources import ni_planning


def _zip_of(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return buf.getvalue()


class TestAppId:
    def test_register_url_yields_id(self):
        assert ni_planning.app_id_from_url(
            "https://planningregister.planningsystemni.gov.uk/application/179744"
        ) == 179744

    def test_trailing_path_and_query_still_yield_id(self):
        assert ni_planning.app_id_from_url(
            "https://planningregister.planningsystemni.gov.uk/application/179744?tab=documents"
        ) == 179744

    def test_no_id_is_none_not_a_crash(self):
        assert ni_planning.app_id_from_url(
            "https://planningregister.planningsystemni.gov.uk/simple-search"
        ) is None


class TestUnwrap:
    def test_single_member_zip_yields_the_inner_file(self):
        """The register serves every document as a zip around one file;
        storing the zip would give the extractors bytes they cannot
        read, so the inner file is what lands in the canonical store."""
        body, ext = ni_planning._unwrap(
            _zip_of({"abc.pdf": b"%PDF-1.4 inner"}), "abc.zip")
        assert body == b"%PDF-1.4 inner"
        assert ext == "pdf"

    def test_multi_member_zip_is_stored_as_zip(self):
        """Taking the first member of many would silently drop material;
        an unexpected shape is stored as served and logged instead."""
        raw = _zip_of({"a.pdf": b"one", "b.pdf": b"two"})
        body, ext = ni_planning._unwrap(raw, "abc.zip")
        assert body == raw
        assert ext == "zip"

    def test_non_zip_passes_through_with_its_own_extension(self):
        body, ext = ni_planning._unwrap(b"%PDF-1.4 direct", "abc.pdf")
        assert body == b"%PDF-1.4 direct"
        assert ext == "pdf"

    def test_zip_magic_but_corrupt_is_passed_through(self):
        """PK magic with an unreadable directory must not crash the
        fetch; the bytes are stored as served."""
        body, ext = ni_planning._unwrap(b"PK\x03\x04garbage", "abc.zip")
        assert body == b"PK\x03\x04garbage"
        assert ext == "zip"

    def test_dedup_suffix_after_the_extension_is_stripped(self):
        """The register names duplicate members "x.pdf(2)" — the dedup
        suffix lands after the extension, and the first live fetch
        stored a file called `<sha>.pdf(2)` before this was caught."""
        body, ext = ni_planning._unwrap(
            _zip_of({"abc.pdf(2)": b"%PDF-1.4 dup"}), "abc.zip")
        assert body == b"%PDF-1.4 dup"
        assert ext == "pdf"
