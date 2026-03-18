-- Migration 010: General-purpose key/value cache table
-- Stores JSON-serializable data with timestamps for cache freshness.
-- Used for Wikipedia current events and other periodically fetched data.
--
-- 2026-02-16 | Claude

CREATE TABLE IF NOT EXISTS cache_store (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
