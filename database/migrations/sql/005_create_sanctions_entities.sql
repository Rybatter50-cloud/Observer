-- Migration 005: Create sanctions_entities table for local OpenSanctions screening
-- Replaces in-memory CSV scan with pg_trgm-indexed PostgreSQL queries.
-- 2026-02-12

CREATE TABLE IF NOT EXISTS sanctions_entities (
    id              TEXT PRIMARY KEY,          -- OpenSanctions entity ID (e.g. "Q7747")
    schema_type     TEXT NOT NULL DEFAULT 'Person',  -- Person, Organization, Company, etc.
    name            TEXT NOT NULL,
    aliases         TEXT,                      -- semicolon-separated alternate names
    birth_date      TEXT,
    countries       TEXT,                      -- semicolon-separated ISO codes
    sanctions       TEXT,                      -- sanctions program description
    dataset         TEXT,                      -- semicolon-separated dataset names
    identifiers     TEXT,                      -- passport/ID numbers
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Separate table for the name index: one row per name variant (primary + each alias).
-- This lets pg_trgm do fuzzy matching on a single column without parsing semicolons at query time.
CREATE TABLE IF NOT EXISTS sanctions_names (
    id              SERIAL PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES sanctions_entities(id) ON DELETE CASCADE,
    name_normalized TEXT NOT NULL,             -- NFKD-stripped, lowercased
    name_display    TEXT NOT NULL              -- original form for display
);

-- pg_trgm GIN index on the normalized name column — the core search index
CREATE INDEX IF NOT EXISTS idx_sanctions_names_trgm
    ON sanctions_names USING GIN (name_normalized gin_trgm_ops);

-- B-tree for fast entity_id lookups (join back to parent)
CREATE INDEX IF NOT EXISTS idx_sanctions_names_entity
    ON sanctions_names (entity_id);

-- Schema type filter
CREATE INDEX IF NOT EXISTS idx_sanctions_entities_schema
    ON sanctions_entities (schema_type);

-- Track last load metadata
INSERT INTO metadata (key, value)
VALUES ('sanctions_last_load', NULL)
ON CONFLICT (key) DO NOTHING;

-- Track HTTP Last-Modified header so If-Modified-Since works across restarts
INSERT INTO metadata (key, value)
VALUES ('sanctions_csv_last_modified', NULL)
ON CONFLICT (key) DO NOTHING;
