-- Migration 009: Gemini discover call persistence
-- Tracks /discover API calls so the daily counter survives restarts.
--
-- 2026-02-14 | Mr Cat + Claude

CREATE TABLE IF NOT EXISTS gemini_discover_calls (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for the daily window query (time range)
CREATE INDEX IF NOT EXISTS idx_gemini_discover_calls_time
    ON gemini_discover_calls (created_at DESC);
