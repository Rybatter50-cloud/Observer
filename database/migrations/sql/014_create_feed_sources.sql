-- Migration 014: Create feed_sources and discover_runs tables
--
-- Replaces feed_registry_comprehensive.json with proper PostgreSQL storage.
-- feed_sources holds all RSS feeds and scraper sites.
-- discover_runs tracks automated discovery crawl history.
--
-- 2026-02-22 | Mr Cat + Claude | Feed registry → PostgreSQL migration

-- ============================================================
-- feed_sources: unified table for RSS feeds + scraper sites
-- ============================================================
CREATE TABLE IF NOT EXISTS feed_sources (
    id              SERIAL PRIMARY KEY,
    group_key       TEXT NOT NULL,
    group_label     TEXT,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    domain          TEXT NOT NULL,
    feed_type       TEXT NOT NULL DEFAULT 'rss',
    language        TEXT DEFAULT 'en',
    city            TEXT,
    country         TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    lat             REAL,
    lon             REAL,
    description     TEXT,
    discovered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_probed     TIMESTAMPTZ,
    probe_status    TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(url, feed_type)
);

-- Indexes for hot query paths
CREATE INDEX IF NOT EXISTS idx_feed_sources_group     ON feed_sources (group_key);
CREATE INDEX IF NOT EXISTS idx_feed_sources_type      ON feed_sources (feed_type);
CREATE INDEX IF NOT EXISTS idx_feed_sources_enabled   ON feed_sources (enabled);
CREATE INDEX IF NOT EXISTS idx_feed_sources_domain    ON feed_sources (domain);
CREATE INDEX IF NOT EXISTS idx_feed_sources_language  ON feed_sources (language);
CREATE INDEX IF NOT EXISTS idx_feed_sources_group_type ON feed_sources (group_key, feed_type);

-- Ensure the shared trigger function exists (schema.py creates it later,
-- but migrations run first so it may not be there yet on fresh installs)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auto-update updated_at trigger
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_feed_sources_updated_at'
    ) THEN
        CREATE TRIGGER trg_feed_sources_updated_at
            BEFORE UPDATE ON feed_sources
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ============================================================
-- discover_runs: tracks automated /discover crawl history
-- ============================================================
CREATE TABLE IF NOT EXISTS discover_runs (
    id              SERIAL PRIMARY KEY,
    country         TEXT NOT NULL,
    country_key     TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'pending',
    rss_found       INTEGER NOT NULL DEFAULT 0,
    scraper_found   INTEGER NOT NULL DEFAULT 0,
    skipped         INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    gemini_tokens   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discover_runs_country  ON discover_runs (country_key);
CREATE INDEX IF NOT EXISTS idx_discover_runs_status   ON discover_runs (status);
CREATE INDEX IF NOT EXISTS idx_discover_runs_started  ON discover_runs (started_at DESC);
