-- Migration 004: Add EMBEDDING to analysis_mode enum
-- Required for sentence-transformer local classification
-- 2026-02-12

-- Add new enum value (idempotent — skips if already exists)
DO $$ BEGIN
    ALTER TYPE analysis_mode ADD VALUE IF NOT EXISTS 'EMBEDDING';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
