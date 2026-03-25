-- Add entities_json and entities_tier columns to intel_signals
-- entities_json stores extracted named entities as JSONB
-- entities_tier indicates the extraction quality level (0 = none)

ALTER TABLE intel_signals ADD COLUMN IF NOT EXISTS entities_json JSONB;
ALTER TABLE intel_signals ADD COLUMN IF NOT EXISTS entities_tier INTEGER NOT NULL DEFAULT 0;
