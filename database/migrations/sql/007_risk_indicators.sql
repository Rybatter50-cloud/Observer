-- =====================================================================
-- Migration 007: US State Dept Risk Indicators (multi-label)
-- =====================================================================
-- Replaces single-label classification ENUM with:
--   risk_indicators TEXT[]   (multi-label: ['T','K'], ['U','F'], etc.)
--   advisory_level  SMALLINT (State Dept 1-4 severity)
--
-- Idempotent: handles both fresh DBs (schema already has risk_indicators)
-- and legacy DBs (still have classification column).
-- 2026-02-13 | Mr Cat + Claude
-- =====================================================================

-- Step 1: Add new columns (IF NOT EXISTS handles fresh DBs)
ALTER TABLE intel_signals
    ADD COLUMN IF NOT EXISTS risk_indicators TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE intel_signals
    ADD COLUMN IF NOT EXISTS advisory_level SMALLINT;

-- Step 2: CHECK constraint for advisory_level (1-4 or NULL)
DO $$ BEGIN
    ALTER TABLE intel_signals
        ADD CONSTRAINT chk_advisory_level
        CHECK (advisory_level IS NULL OR advisory_level BETWEEN 1 AND 4);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Step 3: Backfill risk_indicators from classification (only if column exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'classification'
    ) THEN
        EXECUTE '
            UPDATE intel_signals SET risk_indicators = CASE classification::text
                WHEN ''CONFLICT''      THEN ARRAY[''U'']
                WHEN ''TERRORISM''     THEN ARRAY[''T'']
                WHEN ''POLITICAL''     THEN ARRAY[''U'']
                WHEN ''ECONOMIC''      THEN ARRAY[''F'']
                WHEN ''HUMANITARIAN''  THEN ARRAY[''H'']
                WHEN ''CYBER''         THEN ARRAY[''X'']
                WHEN ''ENVIRONMENTAL'' THEN ARRAY[''N'']
                ELSE ARRAY[]::TEXT[]
            END
            WHERE risk_indicators = ''{}'' OR risk_indicators IS NULL
        ';

        -- Step 4: Rename old column (keep for rollback safety)
        ALTER TABLE intel_signals RENAME COLUMN classification TO classification_legacy;
    END IF;
END $$;

-- Step 5: GIN index for array containment queries (@>, &&)
CREATE INDEX IF NOT EXISTS idx_signals_risk_indicators
    ON intel_signals USING GIN (risk_indicators);

-- Step 6: Drop old classification index (if it exists)
DROP INDEX IF EXISTS idx_signals_classification;
