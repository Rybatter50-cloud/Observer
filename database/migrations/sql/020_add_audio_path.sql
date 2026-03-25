-- Add audio_path column for Kokoro TTS generated audio files
-- Stores the filename (e.g. "cluster_42.mp3") relative to /static/audio/
-- Skips gracefully when pgvector (and article_clusters) is not available.

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables
           WHERE table_name = 'article_clusters') THEN
    ALTER TABLE article_clusters ADD COLUMN IF NOT EXISTS audio_path TEXT;
END IF;
END $$;
