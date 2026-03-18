-- ============================================================================
-- Migration 002: Add source_group column to intel_signals
-- ============================================================================
-- Stores the feed registry group name (e.g. 'ukraine', 'middle_east')
-- for display on dashboard intel cards.
-- ============================================================================

ALTER TABLE intel_signals ADD COLUMN IF NOT EXISTS source_group TEXT;
