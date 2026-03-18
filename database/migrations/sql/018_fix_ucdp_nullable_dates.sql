-- Migration 018: Make date_start/date_end nullable on ucdp_events
-- Some UCDP GED records have empty date fields (e.g. event 244657).
-- 2026-02-26

ALTER TABLE ucdp_events ALTER COLUMN date_start DROP NOT NULL;
ALTER TABLE ucdp_events ALTER COLUMN date_end DROP NOT NULL;
