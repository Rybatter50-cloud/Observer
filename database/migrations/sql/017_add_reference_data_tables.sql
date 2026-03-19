-- Migration 017: Add reference data tables for UCDP, GNS, and signal linkage
-- Supports Observer Data Integration Plan: conflict context, location resolution,
-- and enriched reporting.
-- 2026-02-25

-- =====================================================
-- SANCTIONS: Add source discriminator
-- =====================================================
ALTER TABLE sanctions_entities ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'opensanctions';
CREATE INDEX IF NOT EXISTS idx_sanctions_entities_source ON sanctions_entities (source);

-- =====================================================
-- UCDP REFERENCE DATA
-- =====================================================

-- Core: Individual conflict events (GED + Candidate)
CREATE TABLE IF NOT EXISTS ucdp_events (
    id                  INTEGER PRIMARY KEY,
    year                INTEGER NOT NULL,
    type_of_violence    SMALLINT NOT NULL,
    conflict_id         INTEGER NOT NULL,
    conflict_name       TEXT NOT NULL,
    dyad_id             INTEGER NOT NULL,
    dyad_name           TEXT NOT NULL,
    side_a_id           INTEGER,
    side_a              TEXT NOT NULL,
    side_b_id           INTEGER,
    side_b              TEXT,
    country             TEXT NOT NULL,
    country_id          INTEGER NOT NULL,
    region              TEXT NOT NULL,
    adm_1               TEXT,
    adm_2               TEXT,
    location_name       TEXT,
    latitude            NUMERIC(9,6) NOT NULL,
    longitude           NUMERIC(9,6) NOT NULL,
    geo_precision       SMALLINT NOT NULL DEFAULT 6,
    date_start          DATE NOT NULL,
    date_end            DATE NOT NULL,
    date_precision      SMALLINT NOT NULL DEFAULT 5,
    deaths_best         INTEGER NOT NULL DEFAULT 0,
    deaths_high         INTEGER NOT NULL DEFAULT 0,
    deaths_low          INTEGER NOT NULL DEFAULT 0,
    deaths_side_a       INTEGER DEFAULT 0,
    deaths_side_b       INTEGER DEFAULT 0,
    deaths_civilians    INTEGER DEFAULT 0,
    deaths_unknown      INTEGER DEFAULT 0,
    event_clarity       SMALLINT DEFAULT 1,
    active_year         BOOLEAN DEFAULT FALSE,
    source_dataset      TEXT NOT NULL DEFAULT 'ged',
    code_status         TEXT,
    source_article      TEXT,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ucdp_events_conflict ON ucdp_events (conflict_id);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_country ON ucdp_events (country);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_region ON ucdp_events (region);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_date ON ucdp_events (date_start DESC);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_year ON ucdp_events (year);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_type ON ucdp_events (type_of_violence);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_location ON ucdp_events (latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_dyad ON ucdp_events (dyad_id);

-- pg_trgm fuzzy indexes on actor names
CREATE INDEX IF NOT EXISTS idx_ucdp_events_side_a ON ucdp_events USING GIN (side_a gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ucdp_events_side_b ON ucdp_events USING GIN (side_b gin_trgm_ops);

-- Conflict-level aggregates (Armed Conflict Dataset)
CREATE TABLE IF NOT EXISTS ucdp_conflicts (
    conflict_id         INTEGER NOT NULL,
    year                INTEGER NOT NULL,
    conflict_name       TEXT NOT NULL,
    type_of_conflict    SMALLINT,
    incompatibility     SMALLINT,
    intensity_level     SMALLINT,
    region              TEXT,
    country             TEXT,
    side_a              TEXT,
    side_b              TEXT,
    territory_name      TEXT,
    cumulative_intensity SMALLINT,
    start_date          DATE,
    ep_end              BOOLEAN DEFAULT FALSE,
    ep_end_date         DATE,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (conflict_id, year)
);

CREATE INDEX IF NOT EXISTS idx_ucdp_conflicts_country ON ucdp_conflicts (country);
CREATE INDEX IF NOT EXISTS idx_ucdp_conflicts_region ON ucdp_conflicts (region);
CREATE INDEX IF NOT EXISTS idx_ucdp_conflicts_year ON ucdp_conflicts (year);

-- Actor reference data
CREATE TABLE IF NOT EXISTS ucdp_actors (
    actor_id            INTEGER PRIMARY KEY,
    actor_name          TEXT NOT NULL,
    actor_aliases       TEXT,
    org_type            TEXT,
    conflicts           TEXT,
    dyads               TEXT,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ucdp_actors_name ON ucdp_actors USING GIN (actor_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ucdp_actors_aliases ON ucdp_actors USING GIN (actor_aliases gin_trgm_ops);

-- Conflict termination episodes
CREATE TABLE IF NOT EXISTS ucdp_terminations (
    conflict_id         INTEGER NOT NULL,
    dyad_id             INTEGER,
    episode_id          TEXT,
    start_date          DATE,
    end_date            DATE,
    termination_type    TEXT,
    outcome             TEXT,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ucdp_term_conflict ON ucdp_terminations (conflict_id);

-- Battle-related deaths aggregates
CREATE TABLE IF NOT EXISTS ucdp_brd (
    conflict_id         INTEGER NOT NULL,
    dyad_id             INTEGER NOT NULL,
    year                INTEGER NOT NULL,
    deaths_best         INTEGER DEFAULT 0,
    deaths_high         INTEGER DEFAULT 0,
    deaths_low          INTEGER DEFAULT 0,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dyad_id, year)
);

CREATE INDEX IF NOT EXISTS idx_ucdp_brd_conflict ON ucdp_brd (conflict_id);

-- One-sided violence (civilian targeting)
CREATE TABLE IF NOT EXISTS ucdp_one_sided (
    actor_id            INTEGER NOT NULL,
    actor_name          TEXT NOT NULL,
    year                INTEGER NOT NULL,
    is_government       BOOLEAN DEFAULT FALSE,
    deaths_best         INTEGER DEFAULT 0,
    deaths_high         INTEGER DEFAULT 0,
    deaths_low          INTEGER DEFAULT 0,
    country             TEXT,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (actor_id, year)
);

-- =====================================================
-- GNS GEOSPATIAL REFERENCE DATA
-- =====================================================

CREATE TABLE IF NOT EXISTS gns_features (
    uni                 INTEGER PRIMARY KEY,
    ufi                 INTEGER NOT NULL,
    full_name           TEXT NOT NULL,
    full_name_nd        TEXT NOT NULL,
    country_code        TEXT NOT NULL,
    adm1_code           TEXT,
    feature_class       CHAR(1) NOT NULL,
    designation_code    TEXT,
    latitude            NUMERIC(9,6) NOT NULL,
    longitude           NUMERIC(9,6) NOT NULL,
    name_type           TEXT,
    language_code       TEXT,
    sort_name           TEXT,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gns_ufi ON gns_features (ufi);
CREATE INDEX IF NOT EXISTS idx_gns_country ON gns_features (country_code);
CREATE INDEX IF NOT EXISTS idx_gns_fc ON gns_features (feature_class);
CREATE INDEX IF NOT EXISTS idx_gns_name_nd ON gns_features USING GIN (full_name_nd gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_gns_location ON gns_features (latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_gns_adm1 ON gns_features (country_code, adm1_code);
-- Partial index: populated places and admin regions for fast location matching
CREATE INDEX IF NOT EXISTS idx_gns_populated ON gns_features (country_code, full_name_nd)
    WHERE feature_class IN ('P', 'A');

-- GNS admin division reference
CREATE TABLE IF NOT EXISTS gns_admin_divisions (
    country_code        TEXT NOT NULL,
    adm1_code           TEXT NOT NULL,
    adm1_name           TEXT NOT NULL,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (country_code, adm1_code)
);

-- =====================================================
-- LINKAGE TABLES
-- =====================================================

-- Links intel_signals to matched UCDP conflicts/events
CREATE TABLE IF NOT EXISTS signal_conflict_links (
    id                  SERIAL PRIMARY KEY,
    signal_id           INTEGER NOT NULL REFERENCES intel_signals(id) ON DELETE CASCADE,
    ucdp_conflict_id    INTEGER NOT NULL,
    ucdp_event_id       INTEGER,
    match_type          TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scl_signal ON signal_conflict_links (signal_id);
CREATE INDEX IF NOT EXISTS idx_scl_conflict ON signal_conflict_links (ucdp_conflict_id);

-- Links intel_signals to resolved GNS locations
CREATE TABLE IF NOT EXISTS signal_location_links (
    id                  SERIAL PRIMARY KEY,
    signal_id           INTEGER NOT NULL REFERENCES intel_signals(id) ON DELETE CASCADE,
    gns_ufi             INTEGER NOT NULL,
    match_type          TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.0,
    resolved_country    TEXT,
    resolved_adm1       TEXT,
    resolved_lat        NUMERIC(9,6),
    resolved_lon        NUMERIC(9,6),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sll_signal ON signal_location_links (signal_id);
CREATE INDEX IF NOT EXISTS idx_sll_ufi ON signal_location_links (gns_ufi);

-- Track reference data load metadata
INSERT INTO metadata (key, value)
VALUES ('ucdp_last_load', NULL)
ON CONFLICT (key) DO NOTHING;

INSERT INTO metadata (key, value)
VALUES ('gns_last_load', NULL)
ON CONFLICT (key) DO NOTHING;

INSERT INTO metadata (key, value)
VALUES ('un_sanctions_last_load', NULL)
ON CONFLICT (key) DO NOTHING;
