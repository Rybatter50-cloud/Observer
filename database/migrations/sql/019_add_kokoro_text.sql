-- Add kokoro_text column for TTS-ready cluster summaries
-- The column stores a Kokoro-friendly version of the Ollama-generated summary:
-- clean prose, no meta/IDs/dates, standard punctuation only.
-- Skips gracefully when pgvector (and article_clusters) is not available.

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables
           WHERE table_name = 'article_clusters') THEN
    ALTER TABLE article_clusters ADD COLUMN IF NOT EXISTS kokoro_text TEXT;
END IF;
END $$;
