-- Add audio_path column for Kokoro TTS generated audio files
-- Stores the filename (e.g. "cluster_42.mp3") relative to /static/audio/

ALTER TABLE article_clusters ADD COLUMN IF NOT EXISTS audio_path TEXT;
