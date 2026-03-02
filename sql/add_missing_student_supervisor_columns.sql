-- ============================================================
-- Add missing columns to students + supervisors tables
-- Run in Supabase SQL Editor
-- Safe to run multiple times (uses IF NOT EXISTS equivalent)
-- ============================================================

-- ── Students: new columns ────────────────────────────────────

ALTER TABLE students
    ADD COLUMN IF NOT EXISTS fyp_start_semester TEXT,
    ADD COLUMN IF NOT EXISTS fyp_start_year     INTEGER,
    ADD COLUMN IF NOT EXISTS is_active          BOOLEAN NOT NULL DEFAULT FALSE;

-- ── Supervisors: new columns ─────────────────────────────────

ALTER TABLE supervisors
    ADD COLUMN IF NOT EXISTS is_supervisor BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_jury       BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_active     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS description   TEXT;

-- ── Verify (run this after to confirm) ───────────────────────

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name IN ('students', 'supervisors')
  AND column_name IN (
    'fyp_start_semester', 'fyp_start_year', 'is_active',
    'is_supervisor', 'is_jury', 'description'
  )
ORDER BY table_name, column_name;
