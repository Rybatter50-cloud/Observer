-- Migration 008: Scoring schema cleanup
-- =======================================
-- Renames scoring columns to match new offline-scoring pipeline,
-- drops columns that are no longer populated or displayed.
--
-- Changes:
--   score        -> relevance_score   (populated by Claude re-scoring)
--   source_score -> source_confidence (populated from lookup table)
--   author_score -> author_confidence (populated from lookup table)
--   confidence   -> DROPPED (replaced by separate source/author fields)
--   advisory_level -> DROPPED (was Gemini-generated, no longer relevant)
--   short_outlook  -> DROPPED (no display, no AI can generate)
--   medium_outlook -> DROPPED (no display, no AI can generate)
--
-- analysis_mode enum: FULL and EMBEDDING values retired.
-- PG can't remove enum values, so we remap existing rows.
--
-- 2026-02-14 | Mr Cat + Claude
-- 2026-02-25 | Made idempotent for fresh installs (schema already has new names)

-- 1. Rename columns (only if old names still exist)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'score'
    ) THEN
        ALTER TABLE intel_signals RENAME COLUMN score TO relevance_score;
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'source_score'
    ) THEN
        ALTER TABLE intel_signals RENAME COLUMN source_score TO source_confidence;
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'author_score'
    ) THEN
        ALTER TABLE intel_signals RENAME COLUMN author_score TO author_confidence;
    END IF;
END $$;

-- 2. Drop deleted columns
ALTER TABLE intel_signals DROP COLUMN IF EXISTS confidence;
ALTER TABLE intel_signals DROP COLUMN IF EXISTS advisory_level;
ALTER TABLE intel_signals DROP COLUMN IF EXISTS short_outlook;
ALTER TABLE intel_signals DROP COLUMN IF EXISTS medium_outlook;

-- 3. Rebuild indexes for renamed columns
DROP INDEX IF EXISTS idx_signals_score;
CREATE INDEX IF NOT EXISTS idx_signals_relevance_score ON intel_signals (relevance_score DESC);
DROP INDEX IF EXISTS idx_signals_confidence;

-- 4. Remap retired analysis_mode values to valid ones (cast through TEXT
--    so PG doesn't reject unknown enum literals on fresh installs)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'analysis_mode'::regtype AND enumlabel = 'FULL'
    ) THEN
        UPDATE intel_signals SET analysis_mode = 'LOCAL' WHERE analysis_mode = 'FULL';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'analysis_mode'::regtype AND enumlabel = 'EMBEDDING'
    ) THEN
        UPDATE intel_signals SET analysis_mode = 'LOCAL' WHERE analysis_mode = 'EMBEDDING';
    END IF;
END $$;
