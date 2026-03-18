-- ============================================================================
-- Migration 001: Upgrade old SQLite-ported schema to PostgreSQL-native types
-- ============================================================================
-- This migration handles the transition from the old schema (which used
-- INTEGER for booleans, TEXT for enums, "timeStr" for timestamps, and
-- lacked pg_trgm support) to the new canonical PostgreSQL schema.
--
-- It is safe to run on:
--   a) An existing database with old-style columns
--   b) A fresh database where the new schema was already created
--
-- Each operation is idempotent via IF EXISTS / DO NOTHING guards.
-- ============================================================================

-- ── 1. Extensions ──────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── 2. Enum types (if not already created by new schema.py) ────────────────

DO $$ BEGIN
    CREATE TYPE signal_classification AS ENUM (
        'CONFLICT', 'TERRORISM', 'POLITICAL', 'ECONOMIC',
        'HUMANITARIAN', 'CYBER', 'ENVIRONMENTAL', 'UNKNOWN'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE analysis_mode AS ENUM (
        'PENDING', 'FULL', 'LOCAL', 'FALLBACK', 'SKIPPED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE report_type AS ENUM (
        'deep_dive', 'lite_analysis'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── 3. Convert INTEGER booleans to BOOLEAN ─────────────────────────────────
-- Only runs if the column is still INTEGER type.

DO $$ BEGIN
    -- processed: INTEGER -> BOOLEAN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals'
          AND column_name = 'processed'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE intel_signals
            ALTER COLUMN processed DROP DEFAULT,
            ALTER COLUMN processed TYPE BOOLEAN USING (processed = 1),
            ALTER COLUMN processed SET DEFAULT FALSE,
            ALTER COLUMN processed SET NOT NULL;
    END IF;

    -- is_translated: INTEGER -> BOOLEAN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals'
          AND column_name = 'is_translated'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE intel_signals
            ALTER COLUMN is_translated DROP DEFAULT,
            ALTER COLUMN is_translated TYPE BOOLEAN USING (is_translated = 1),
            ALTER COLUMN is_translated SET DEFAULT FALSE,
            ALTER COLUMN is_translated SET NOT NULL;
    END IF;
END $$;

-- ── 4. Rename "timeStr" to published_at TIMESTAMPTZ ────────────────────────
-- If old column exists, migrate it. If new column already exists, skip.

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'timeStr'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'published_at'
    ) THEN
        ALTER TABLE intel_signals ADD COLUMN published_at TIMESTAMPTZ;
        -- "timeStr" was HH:MM format, can't meaningfully convert to timestamp.
        -- Set published_at = created_at as best approximation.
        UPDATE intel_signals SET published_at = created_at WHERE published_at IS NULL;
    END IF;
END $$;

-- ── 5. Convert TEXT columns to ENUM types ──────────────────────────────────
-- Only converts if the column is currently TEXT type.

DO $$ BEGIN
    -- classification: TEXT -> signal_classification
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals'
          AND column_name = 'classification'
          AND data_type = 'text'
    ) THEN
        -- Normalize any values that aren't valid enum members
        UPDATE intel_signals SET classification = 'UNKNOWN'
        WHERE classification NOT IN (
            'CONFLICT', 'TERRORISM', 'POLITICAL', 'ECONOMIC',
            'HUMANITARIAN', 'CYBER', 'ENVIRONMENTAL', 'UNKNOWN'
        );
        ALTER TABLE intel_signals
            ALTER COLUMN classification DROP DEFAULT,
            ALTER COLUMN classification TYPE signal_classification
                USING classification::signal_classification,
            ALTER COLUMN classification SET DEFAULT 'UNKNOWN';
    END IF;

    -- analysis_mode: TEXT -> analysis_mode enum
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals'
          AND column_name = 'analysis_mode'
          AND data_type = 'text'
    ) THEN
        UPDATE intel_signals SET analysis_mode = 'PENDING'
        WHERE analysis_mode NOT IN ('PENDING', 'FULL', 'LOCAL', 'FALLBACK', 'SKIPPED');
        ALTER TABLE intel_signals
            ALTER COLUMN analysis_mode DROP DEFAULT,
            ALTER COLUMN analysis_mode TYPE analysis_mode
                USING analysis_mode::analysis_mode,
            ALTER COLUMN analysis_mode SET DEFAULT 'PENDING';
    END IF;
END $$;

-- ── 6. Convert deep_dive_reports.report_type TEXT -> ENUM ──────────────────

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deep_dive_reports'
          AND column_name = 'report_type'
          AND data_type = 'text'
    ) THEN
        UPDATE deep_dive_reports SET report_type = 'deep_dive'
        WHERE report_type NOT IN ('deep_dive', 'lite_analysis');
        ALTER TABLE deep_dive_reports
            ALTER COLUMN report_type DROP DEFAULT,
            ALTER COLUMN report_type TYPE report_type
                USING report_type::report_type,
            ALTER COLUMN report_type SET DEFAULT 'deep_dive';
    END IF;
END $$;

-- ── 7. Convert TIMESTAMP to TIMESTAMPTZ ────────────────────────────────────
-- Upgrades all timestamp columns to timezone-aware.

DO $$ BEGIN
    -- intel_signals.created_at
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals'
          AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE intel_signals
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
    END IF;

    -- intel_signals.updated_at
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals'
          AND column_name = 'updated_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE intel_signals
            ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';
    END IF;

    -- executive_reports: rename "timestamp" to created_at and convert
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'executive_reports'
          AND column_name = 'timestamp'
    ) THEN
        ALTER TABLE executive_reports RENAME COLUMN "timestamp" TO created_at;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'executive_reports'
          AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE executive_reports
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
    END IF;

    -- gemini_usage: rename "timestamp" to created_at and convert
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'gemini_usage'
          AND column_name = 'timestamp'
    ) THEN
        ALTER TABLE gemini_usage RENAME COLUMN "timestamp" TO created_at;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'gemini_usage'
          AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE gemini_usage
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
    END IF;

    -- deep_dive_reports.created_at
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'deep_dive_reports'
          AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE deep_dive_reports
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
    END IF;

    -- source_reputation.last_updated
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'source_reputation'
          AND column_name = 'last_updated'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE source_reputation
            ALTER COLUMN last_updated TYPE TIMESTAMPTZ USING last_updated AT TIME ZONE 'UTC';
    END IF;

    -- author_reputation.last_updated
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'author_reputation'
          AND column_name = 'last_updated'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE author_reputation
            ALTER COLUMN last_updated TYPE TIMESTAMPTZ USING last_updated AT TIME ZONE 'UTC';
    END IF;
END $$;

-- ── 8. Upgrade reputation scores from INTEGER to REAL ──────────────────────

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'source_reputation'
          AND column_name = 'reliability_score'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE source_reputation
            ALTER COLUMN reliability_score TYPE REAL;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'author_reputation'
          AND column_name = 'credibility_score'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE author_reputation
            ALTER COLUMN credibility_score TYPE REAL;
    END IF;
END $$;

-- ── 9. Add title_tsvector column if missing ────────────────────────────────

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'intel_signals' AND column_name = 'title_tsvector'
    ) THEN
        ALTER TABLE intel_signals ADD COLUMN title_tsvector tsvector;
    END IF;
END $$;

-- ── 10. Backfill title_tsvector for existing rows ──────────────────────────

UPDATE intel_signals
SET title_tsvector = to_tsvector('english', COALESCE(title, ''))
WHERE title_tsvector IS NULL;

-- ── 11. Drop obsolete indexes (replaced by composite ones) ─────────────────

DROP INDEX IF EXISTS idx_signals_processed;
DROP INDEX IF EXISTS idx_gemini_timestamp;

-- ── Done ───────────────────────────────────────────────────────────────────
