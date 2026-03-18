-- 006: Add screening_hits JSONB column for auto-screening results
-- Stores entity screening hits (FBI, Interpol, OpenSanctions) for high-threat articles

ALTER TABLE intel_signals
    ADD COLUMN IF NOT EXISTS screening_hits JSONB;

-- Partial index: only rows that actually have screening hits
CREATE INDEX IF NOT EXISTS idx_signals_screening_hits
    ON intel_signals USING gin (screening_hits)
    WHERE screening_hits IS NOT NULL;
