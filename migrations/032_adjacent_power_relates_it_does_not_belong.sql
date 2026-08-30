-- Adjacent power stands beside a data centre; it is not part of one.
--
-- A substation, an energy centre or a standby fleet consented in its own
-- right is `adjacent_power` under the dc_build rubric. All 49 of them are
-- currently members of a site, because `build_clusters` admits every
-- verdict except `not_dc` and the only thing the clusterer can do with an
-- in-universe record is put it in a site. Membership then makes three
-- claims the documents do not support.
--
-- ## What membership gets wrong
--
-- **It lends the data centre a capacity that is not its own.** Seven sites
-- take their headline power figure from an adjacent-power application:
-- Cardiff Ipswich Road shows 93 MW from a battery storage and 132kV
-- substation scheme, Kingsnorth 49.9 MW from a figure the reader redesign
-- review already identified as an *export* figure, Colt Project Brenda
-- 22.5 MW across five Welwyn Hatfield applications. Not one of the seven
-- is a clean IT load for the data centre. Luke's rule, 2026-08-30: the
-- capacity of adjacent power is valuable, but it must not define the
-- capacity of the data centre, because that power could serve many
-- purposes.
--
-- **It forces a false choice where infrastructure is shared.** Eight of
-- the 39 adjacent-power records carrying coordinates sit within a
-- kilometre of more than one live site. A three-storey low voltage plant
-- building in Park Royal stands inside the radius of five separate
-- schemes including Microsoft's; a site clearance at North Hyde, of seven.
-- One partition has to take each of them, decided by whichever spatial
-- edge formed first.
--
-- **It cannot express the finding that matters.** Membership can only say
-- *this substation belongs to that site*. Data centres cluster around
-- substations because substations are what make a location viable, so the
-- interesting sentence is the one membership has no way to write: these
-- five schemes stand around one piece of infrastructure. That is a
-- resilience question about assets the state calls nationally significant.
--
-- ## Why a table and not a computation
--
-- The relationship decides what a reader is told about shared
-- infrastructure, so it is recorded with the evidence that supports it and
-- retired rather than deleted, as `site_members` and
-- `capacity_claim_matches` are. `basis` is the strength of the claim, and
-- the three tiers are not interchangeable:
--
--   `discovery`  — the record was found by searching outward from a named
--                  site, which `applications.discovered_via` already
--                  stores as `energy_national:<site_key>`. 26 of the 48
--                  carry one. This is documentary: it says how the record
--                  entered the corpus, and it names the site it entered
--                  through.
--   `cohort`     — provenance through a cohort, a neighbour or Barbour.
--                  Seven records. Weaker, but still recorded rather than
--                  inferred.
--   `proximity`  — nothing but distance. The remaining fifteen arrived on
--                  a keyword sweep and have no recorded relationship to
--                  anything.
--
-- **A proximity row is a candidate, never a claim.** One kilometre is the
-- clustering radius, not evidence of shared supply: two schemes near one
-- substation may connect at entirely different points, and the Slough
-- solar PV installation sits within reach of eleven sites while supplying
-- none of them by virtue of being close. Rendering "shares grid
-- infrastructure with" from a proximity row would reproduce the failure
-- this table exists to remove — a confident statement about an electrical
-- relationship inferred from a map pin. Only documents naming the same
-- substation, grid supply point or connection can carry that sentence.
--
-- ## What this migration does not do
--
-- Nothing changes in any output. The table is populated alongside the
-- existing membership, which stays exactly as it is. Removing
-- `adjacent_power` from `site_members` retires seven headline figures and
-- touches 34 sites, and it needs somewhere for the records to go first —
-- including six sites made of nothing but adjacent power, two of which
-- (a generator serving Plymouth University's relocated data centre, a
-- DRUPS supporting the Newton Data Centre) are the only trace this corpus
-- holds of the data centre they serve. See issue #252.

CREATE TABLE IF NOT EXISTS site_adjacent_power (
    id              bigserial PRIMARY KEY,
    site_id         bigint NOT NULL REFERENCES sites(id),
    application_id  bigint NOT NULL REFERENCES applications(id),
    -- discovery | cohort | proximity — see the note above; these rank,
    -- and a consumer must not treat proximity as documentary.
    basis           text NOT NULL,
    -- Metres between the record and the site's pin, where both carry
    -- coordinates. Null is not zero: it means one of them has no pin.
    distance_m      real,
    -- Why this row exists, in words a reporter can read: the
    -- `discovered_via` token, the cohort name, or the radius used.
    evidence        text NOT NULL,
    materialised_at timestamptz NOT NULL DEFAULT now(),
    retired_at      timestamptz,
    CONSTRAINT site_adjacent_power_basis_known
        CHECK (basis IN ('discovery', 'cohort', 'proximity'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_site_adjacent_power
    ON site_adjacent_power (site_id, application_id, basis)
    WHERE retired_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_site_adjacent_power_site
    ON site_adjacent_power (site_id);

CREATE INDEX IF NOT EXISTS idx_site_adjacent_power_application
    ON site_adjacent_power (application_id);
