-- Add kokoro_text column for TTS-ready cluster summaries
-- The column stores a Kokoro-friendly version of the Ollama-generated summary:
-- clean prose, no meta/IDs/dates, standard punctuation only.

ALTER TABLE article_clusters ADD COLUMN IF NOT EXISTS kokoro_text TEXT;
