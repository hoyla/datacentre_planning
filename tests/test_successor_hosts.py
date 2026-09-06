"""A register that moved house is fetched and linked at its new address.

Selby District Council was abolished on 1 April 2023 and its Idox
register folded into North Yorkshire's, keyVals intact.
`public.selby.gov.uk` now answers with an expired certificate and,
behind it, "Permission Denied" on every documents tab — which the
adapter read on 2026-08-08 as a register publishing nothing and settled
18 applications on; the corpus held 70 Selby applications and not one
document, in six live sites including Eggborough and Drax. The same
`applicationDetails.do?keyVal=…` resolves on the successor host with its
documents (six of six sampled on 2026-09-06).

The recorded URL is what PlanIt said and stays so (principle 3). The
swap happens where a request is built and where a link is rendered —
one map, `idox.SUCCESSOR_HOSTS`, the `dcp/drive.py` shape for a fact
about the world.
"""

from __future__ import annotations

from pathlib import Path

from dcp.sources import idox

ROOT = Path(__file__).resolve().parent.parent
OLD = "https://public.selby.gov.uk/online-applications/applicationDetails.do?keyVal=P9AK13NXMPO00&activeTab=summary"
NEW = "https://publicaccess.northyorks.gov.uk/online-applications/applicationDetails.do?keyVal=P9AK13NXMPO00&activeTab=summary"


class TestSuccessorUrl:
    def test_a_retired_host_is_swapped_and_nothing_else_moves(self):
        assert idox.successor_url(OLD) == NEW

    def test_every_other_host_is_left_alone(self):
        u = "https://pl-bs.renfrewshire.gov.uk/online-applications/applicationDetails.do?keyVal=RFM8X0MW00B00&activeTab=summary"
        assert idox.successor_url(u) == u

    def test_none_and_empty_pass_through(self):
        assert idox.successor_url(None) is None
        assert idox.successor_url("") == ""

    def test_the_documents_tab_is_requested_from_the_successor(self):
        docs = idox._documents_tab_url(OLD)
        assert docs.startswith("https://publicaccess.northyorks.gov.uk/")
        assert "keyVal=P9AK13NXMPO00" in docs and "activeTab=documents" in docs
        assert "selby" not in docs

    def test_the_map_names_only_hosts_that_exist_in_lower_case(self):
        for old, new in idox.SUCCESSOR_HOSTS.items():
            assert old == old.lower() and new == new.lower()
            assert old != new


class TestTheSurfacesUseIt:
    def test_the_queue_keys_clients_by_the_host_requested(self):
        src = (ROOT / "scripts" / "fetch_outstanding.py").read_text()
        assert src.count("idox.successor_url(") >= 2

    def test_every_register_link_in_the_reader_goes_through_the_helper(self):
        """No register link may render `a[12]`, `r[12]`, `_reg`, `_aurl` or
        `u` raw: a raw link to a retired host fails silently for a
        reporter, which is the class of dead link 2.8 shipped 401 of."""
        src = (ROOT / "scripts" / "export_reader.py").read_text()
        raw = [line for line in src.splitlines()
               if 'rel="noopener">register</a>' in line and "register_url(" not in line
               and "href=" in line]
        assert not raw, raw
        assert src.count("register_url(") >= 5
        assert "moved_from(a[12])" in src and "moved_from(r[12])" in src


class TestTheQueueCanBeScopedToOneHost:
    def _mod(self):
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location(
            "fetch_outstanding", ROOT / "scripts" / "fetch_outstanding.py")
        m = importlib.util.module_from_spec(spec); sys.modules["fetch_outstanding"] = m
        spec.loader.exec_module(m); return m

    def test_matches_the_recorded_host_not_the_successor(self):
        """The scope is what PlanIt wrote, so the 70 Selby applications
        are selected by the host that no longer answers."""
        m = self._mod()
        assert m.host_matches(OLD, "public.selby.gov.uk")
        assert m.host_matches(OLD, "PUBLIC.SELBY.GOV.UK")
        assert not m.host_matches(OLD, "publicaccess.northyorks.gov.uk")
        assert not m.host_matches(None, "public.selby.gov.uk")
