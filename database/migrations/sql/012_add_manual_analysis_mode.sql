-- Add 'MANUAL' to analysis_mode enum for analyst hand-curated scoring
ALTER TYPE analysis_mode ADD VALUE IF NOT EXISTS 'MANUAL';
