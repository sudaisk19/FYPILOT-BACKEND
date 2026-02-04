# docs/pdo.md

# PDO — Bulk Registration via Cron Job (FYPilot)

## 1) Goal
Enable **Admin** to create **multiple student/supervisor accounts** by uploading an Excel/CSV file. The system:
- Validates rows
- Creates users with **randomly generated temporary passwords**
- Assigns role (`student` or `supervisor`)
- Creates role-specific profiles (student: roll_no, supervisor: details)
- Produces a **results CSV** containing created/skipped/failed rows + credentials for distribution

Constraint: app is hosted on **Render free-tier** → long-running requests may timeout/sleep.  
Solution: **DB-queued jobs + cron “tick” processor**.

---

## 2) Recommended Approach (Selected)
### DB Job Queue + Cron Runner (“Tick” Processing)

**Why this option**
- Upload request returns quickly (no timeouts)
- Processor runs in small batches (e.g., 25–50 rows per run)
- Resilient to server restarts/sleep
- Progress is trackable, export is reproducible

---

## 3) User Story
As an **Admin**, I can:
1. Select role to create: `student` or `supervisor`
2. Upload a file containing rows (name/email/roll_no/etc.)
3. Monitor progress (counts and status)
4. Download results CSV including temporary credentials (ID + password) to share with users

---

## 4) File Format
### Supported uploads
- Preferred: **CSV**
- If Excel is uploaded: backend converts to rows (same validation rules)

### Student template columns
Required:
- `full_name`
- `email`
- `roll_no`

Optional:
- `section`
- `batch_year`

### Supervisor template columns
Required:
- `full_name`
- `email`

Optional:
- `department`
- `designation`

> Role is selected from UI for the whole job, not per-row (simplifies validation + reduces file errors).

---

## 5) Data Model
### 5.1 `bulk_import_jobs`
Fields:
- `id` (uuid, pk)
- `created_by` (uuid → admin user id)
- `target_role` (`student` | `supervisor`)
- `status` (`pending` | `processing` | `done` | `failed`)
- `total_rows` (int)
- `processed_rows` (int)
- `success_count` (int)
- `failed_count` (int)
- `skipped_count` (int)
- `created_at`, `updated_at`

Indexes:
- `(status)`
- `(created_by)`

### 5.2 `bulk_import_items`
Fields:
- `id` (uuid, pk)
- `job_id` (uuid → bulk_import_jobs.id)
- `row_number` (int)
- `payload` (jsonb)  // row data
- `status` (`pending` | `success` | `failed` | `skipped`)
- `error` (text, nullable)
- `created_user_id` (uuid, nullable)

Credentials handling:
- `temp_password_enc` (text, nullable)  // encrypted temp password
- `expires_at` (timestamp, nullable)     // when temp password is no longer downloadable

Indexes:
- `(job_id, status)`
- `(job_id, row_number)`

### 5.3 Existing auth tables
Assumptions:
- `users.email` is **unique**
- Password stored as **hash** (bcrypt/argon2) in DB
- `users.role` in (`student`, `supervisor`, `admin`)
- `students` / `supervisors` profile tables keyed by `user_id`

Idempotency:
- Unique constraint on `users.email`
- If a job re-runs or retries → duplicate emails become `skipped`

---

## 6) Security & Access Control
### Admin-only
All endpoints under `/api/v1/admin/bulk-imports/*` require:
- Valid JWT
- Role check: `admin`

### Data protection
- Do **NOT** store plaintext passwords in DB
- Store only:
  - password hash in `users`
  - encrypted temp password in `bulk_import_items.temp_password_enc`

### Credential retention policy
- Encrypted temp passwords are downloadable for **24 hours** (configurable)
- After expiry, export omits password (or shows blank) and an admin must reset / regenerate

---

## 7) API Endpoints (Backend)
All endpoints require admin auth.

### 7.1 Create job (upload)
`POST /api/v1/admin/bulk-imports`
- Form-data:
  - `file`: CSV/XLSX
  - `target_role`: `student` | `supervisor`
- Response:
  - `job_id`
  - `total_rows`
  - counts initialized

Behavior:
- Parse file → build row list
- Validate columns exist
- Create job + items
- Items start as `pending`

### 7.2 Get job status
`GET /api/v1/admin/bulk-imports/{job_id}`
- Response:
  - status, counts, total_rows, processed_rows
  - optional: last errors summary

### 7.3 Download results CSV
`GET /api/v1/admin/bulk-imports/{job_id}/results.csv`
- Includes:
  - row_number, name, email, role, roll_no (if student), user_id, status, error
  - temp_password (decrypted) ONLY if not expired

### 7.4 Cron processor (tick)
`POST /api/v1/admin/bulk-imports/run-pending`
- Protected by:
  - admin auth **OR**
  - internal cron token header (recommended) e.g. `X-CRON-TOKEN`

Behavior per run:
- Fetch up to `BATCH_SIZE` pending items across jobs (or per job)
- Mark them “in-progress” (optional) / lock them
- Process each row:
  1) Validate payload
  2) If user exists by email → item = `skipped`
  3) Else generate temp password
  4) Hash password, insert user with role
  5) Insert profile row (student/supervisor)
  6) Encrypt temp password → store `temp_password_enc` with `expires_at = now + TTL`
  7) Mark item `success`
- Update job counters
- If all items done → job `done`

Locking note:
- Use `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres) to avoid two cron runs processing same row.

---

## 8) Password Generation Rules
- Length: 12–16 chars
- Include: letters + digits (optional: symbols if your login supports)
- Example policy: at least 1 uppercase, 1 lowercase, 1 digit

---

## 9) Encryption Plan (for exported passwords)
Approach:
- `temp_password_enc = Encrypt(temp_password, APP_ENCRYPTION_KEY)`
- Decrypt only inside the admin export endpoint

Requirements:
- `APP_ENCRYPTION_KEY` stored in Render env vars (never in repo)
- TTL cleanup:
  - export endpoint hides expired passwords
  - optional cron cleanup task to null out `temp_password_enc` after expiry

---

## 10) Cron Job Implementation (GitHub Actions)
Use GitHub Actions scheduled workflow:
- Runs every 5 minutes (or 1 minute if acceptable)
- Calls the processor endpoint

### Required secrets (GitHub repo secrets)
- `CRON_PROCESSOR_URL` → e.g. https://api.yourdomain.com/api/v1/admin/bulk-imports/run-pending
- `CRON_TOKEN` → same as Render env `CRON_TOKEN`

### Example workflow (reference)
- Schedule: `*/5 * * * *`
- Step: `curl -X POST -H "X-CRON-TOKEN: $CRON_TOKEN" $CRON_PROCESSOR_URL`

Note:
- If Render sleeps, GitHub will still call it; the first call wakes it up and runs the tick.

---

## 11) Admin UI Requirements
Screen: **Bulk Registration**
- Dropdown: target role (student/supervisor)
- Upload file input
- Progress card:
  - total, processed, success, failed, skipped
  - status badge
- Buttons:
  - Download results CSV
  - Download failed-only CSV (optional)

---

## 12) Validation Rules
Common:
- `email` must be valid format
- `full_name` must be non-empty
- Trim whitespace

Student:
- `roll_no` required, non-empty
- Optional uniqueness check for roll_no within batch (recommended)

Supervisor:
- roll_no ignored

---

## 13) Failure Handling & Reporting
- A bad row does not fail the whole job
- Each item gets:
  - `status=failed`
  - `error` message
- Export always includes failures for correction + re-upload

---

## 14) Acceptance Criteria
- Admin can upload file and receive `job_id`
- Cron tick processes rows in batches without timeouts
- Duplicate email rows are marked `skipped`
- Results CSV downloads successfully and includes:
  - status + error per row
  - user_id for success
  - temp password for success if not expired
- Non-admin cannot access endpoints
- Temp passwords are not stored in plaintext and expire

---

## 15) Test Plan
### API (pytest + httpx)
- upload creates job + items
- run-pending processes N items, updates counters
- duplicates become skipped
- results.csv returns decrypted passwords for non-expired only
- unauthorized access denied
- two parallel run-pending calls do not double-process (SKIP LOCKED)

### Web (jest + rtl)
- upload flow starts job and shows progress polling
- download results button appears when done
- error rows visible

---

## 16) Operational Notes
- Tune `BATCH_SIZE` (25–50) based on Render performance
- Add rate-limits to upload + processor endpoints
- Consider email notification later (optional)
