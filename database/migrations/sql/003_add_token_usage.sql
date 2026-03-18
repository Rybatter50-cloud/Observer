-- Migration 003: Token usage persistence table
-- Tracks per-provider token consumption for rolling 24h budget meters.
-- Survives application restarts so TPD gauges remain accurate.
--
-- 2026-02-10 | Mr Cat + Claude

CREATE TABLE IF NOT EXISTS token_usage (
    id          BIGSERIAL PRIMARY KEY,
    provider    TEXT NOT NULL,        -- gemini_analyst, gemini
    tokens      INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for the rolling 24h window query (provider + time range)
CREATE INDEX IF NOT EXISTS idx_token_usage_provider_time
    ON token_usage (provider, created_at DESC);
