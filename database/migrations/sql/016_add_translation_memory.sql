-- Migration 016: Vector Translation Memory
-- ==========================================
-- Adds infrastructure for multilingual embedding-based "speed translation".
--
-- Two changes:
--   1. New `translation_memory` table: stores (source_embedding, english_text)
--      pairs from every NLLB translation. Used as a vector lookup table so
--      incoming foreign headlines can be matched to previously translated
--      headlines via cosine similarity, bypassing NLLB under load.
--
--   2. New `original_title` column on `intel_signals`: preserves the
--      pre-translation foreign-language title so future re-vectorization
--      passes can re-embed the original text (not the English translation).
--
-- Requires pgvector extension (installed by migration 015).
--
-- 2026-02-24 | Mr Cat + Claude | Vector Translation Memory

-- -----------------------------------------------------------------------
-- 1. original_title column on intel_signals
-- -----------------------------------------------------------------------
-- Stores the foreign-language title before translation overwrites it.
-- NULL for English-language articles (no translation needed).
ALTER TABLE intel_signals
    ADD COLUMN IF NOT EXISTS original_title TEXT;

-- -----------------------------------------------------------------------
-- 2. translation_memory table (pgvector-dependent)
-- -----------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN

    CREATE TABLE IF NOT EXISTS translation_memory (
        id                SERIAL PRIMARY KEY,

        -- The multilingual embedding of the source-language text.
        -- 384 dimensions = paraphrase-multilingual-MiniLM-L12-v2 output.
        source_embedding  vector(384) NOT NULL,

        -- ISO 639-1 language code of the source text (e.g. 'ru', 'ar', 'zh').
        source_language   TEXT NOT NULL,

        -- The original foreign-language text that was translated.
        source_text       TEXT NOT NULL,

        -- The English translation produced by NLLB (or Ollama fallback).
        english_text      TEXT NOT NULL,

        -- Which backend produced this translation.
        -- 'nllb', 'ollama', 'cache', or 'seed' (from migration seed script).
        translation_source TEXT NOT NULL DEFAULT 'nllb',

        -- Optional FK back to the signal this translation came from.
        -- NULL for cache-seeded entries that predate this column.
        signal_id         INTEGER REFERENCES intel_signals(id) ON DELETE SET NULL,

        created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- IVFFlat index for fast nearest-neighbor search on source embeddings.
    -- Uses cosine distance (vector_cosine_ops) to match the rest of the system.
    -- lists=100 is appropriate for tables up to ~100K rows; will need
    -- retuning if the table grows beyond that.
    BEGIN
        CREATE INDEX IF NOT EXISTS idx_translation_memory_embedding
            ON translation_memory USING ivfflat (source_embedding vector_cosine_ops)
            WITH (lists = 100);
    EXCEPTION WHEN others THEN
        -- IVFFlat requires rows to train on; deferred until first seed.
        RAISE WARNING 'IVFFlat index on translation_memory deferred: %', SQLERRM;
    END;

    -- Lookup index: find all memory entries for a given language.
    CREATE INDEX IF NOT EXISTS idx_translation_memory_lang
        ON translation_memory (source_language);

    -- Lookup index: find memory entries linked to a specific signal.
    CREATE INDEX IF NOT EXISTS idx_translation_memory_signal
        ON translation_memory (signal_id)
        WHERE signal_id IS NOT NULL;

    -- Prevent exact duplicate source texts per language from bloating the table.
    -- md5 keeps the index compact for potentially long TEXT values.
    CREATE UNIQUE INDEX IF NOT EXISTS idx_translation_memory_unique_source
        ON translation_memory (source_language, md5(source_text));

    RAISE NOTICE 'translation_memory table and indexes created successfully';

ELSE
    RAISE WARNING 'pgvector not available — skipping translation_memory table';
END IF;
END $$;
