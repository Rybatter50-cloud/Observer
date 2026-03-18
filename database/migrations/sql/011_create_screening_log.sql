-- 011: Create screening_log table for tracking screening checks by IP
-- Tracks each screening check: who ran it (IP), what was searched, hit count

CREATE TABLE IF NOT EXISTS screening_log (
    id              SERIAL PRIMARY KEY,
    queried_name    TEXT NOT NULL,
    hit_count       INTEGER NOT NULL DEFAULT 0,
    sources_checked TEXT,                        -- comma-separated source list
    client_ip       TEXT NOT NULL DEFAULT 'unknown',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_screening_log_created
    ON screening_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_screening_log_ip
    ON screening_log (client_ip);
