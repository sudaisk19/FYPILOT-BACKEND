-- ============================================================
-- Bulk Import Tables — Run in Supabase SQL Editor
-- Step 1: Drop old tables + enum types
-- Step 2: Recreate with VARCHAR columns (no enums)
-- ============================================================

-- ── Step 1: Clean up old tables & enums ──────────────────────
DROP TABLE IF EXISTS bulk_import_items CASCADE;
DROP TABLE IF EXISTS bulk_import_jobs CASCADE;
DROP TYPE IF EXISTS target_role_enum CASCADE;
DROP TYPE IF EXISTS bulk_job_status_enum CASCADE;
DROP TYPE IF EXISTS bulk_item_status_enum CASCADE;

-- ── Step 2: Create tables with VARCHAR columns ───────────────

CREATE TABLE bulk_import_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by  UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    target_role VARCHAR(20) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_rows     INTEGER NOT NULL DEFAULT 0,
    processed_rows INTEGER NOT NULL DEFAULT 0,
    success_count  INTEGER NOT NULL DEFAULT 0,
    failed_count   INTEGER NOT NULL DEFAULT 0,
    skipped_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_target_role CHECK (target_role IN ('student', 'supervisor')),
    CONSTRAINT chk_job_status CHECK (status IN ('pending', 'processing', 'done', 'failed'))
);

CREATE TABLE bulk_import_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES bulk_import_jobs(id) ON DELETE CASCADE,
    row_number      INTEGER NOT NULL,
    payload         JSONB NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    error           TEXT,
    created_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    temp_password_enc TEXT,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_item_status CHECK (status IN ('pending', 'success', 'failed', 'skipped'))
);

-- ── Step 3: Indexes ──────────────────────────────────────────
CREATE INDEX idx_bulk_jobs_status     ON bulk_import_jobs(status);
CREATE INDEX idx_bulk_jobs_created_by ON bulk_import_jobs(created_by);
CREATE INDEX idx_bulk_items_job_id    ON bulk_import_items(job_id);
CREATE INDEX idx_bulk_items_job_status ON bulk_import_items(job_id, status);
CREATE INDEX idx_bulk_items_job_row   ON bulk_import_items(job_id, row_number);

-- ── Step 4: RLS ──────────────────────────────────────────────
ALTER TABLE bulk_import_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE bulk_import_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on bulk_import_jobs"
    ON bulk_import_jobs FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on bulk_import_items"
    ON bulk_import_items FOR ALL USING (true) WITH CHECK (true);

-- ── Done! ────────────────────────────────────────────────────
SELECT 'bulk_import_jobs' AS table_name, count(*) FROM bulk_import_jobs
UNION ALL
SELECT 'bulk_import_items', count(*) FROM bulk_import_items;
