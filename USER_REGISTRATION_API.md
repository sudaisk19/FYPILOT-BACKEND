# User Registration API — Admin Documentation & Frontend Integration Guide

> **Base URL:** `POST /api/admin/user-registration`
> **Auth:** All endpoints require a valid Admin JWT (`Authorization: Bearer <token>`)
> **Swagger Tag:** `admin-user-registration`

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Tables](#database-tables)
3. [Single User Registration](#single-user-registration)
   - [Register Single Student](#1-register-single-student)
   - [Register Single Supervisor](#2-register-single-supervisor)
4. [Bulk Registration (CSV / Excel)](#bulk-registration-csv--excel)
   - [Upload File](#3-upload-bulk-import-file)
   - [Poll Job Status](#4-poll-job-status)
   - [Get Full Report](#5-get-full-job-report)
   - [Download Results CSV](#6-download-results-csv)
   - [Retry Failed Items](#7-retry-failed-items)
   - [Resume After Crash](#8-resume-interrupted-job)
   - [Manual Trigger](#9-manual-process-all-pending)
5. [CSV / Excel File Format](#csv--excel-file-format)
6. [Field Defaults Set Automatically](#field-defaults-set-automatically)
7. [Error Handling Reference](#error-handling-reference)
8. [Frontend Integration Plan](#frontend-integration-plan)
   - [Single Registration Flow](#single-registration-flow)
   - [Bulk Registration Flow](#bulk-registration-flow)
   - [Component Breakdown](#component-breakdown)
   - [State Management](#state-management)
   - [Polling Strategy](#polling-strategy)

---

## Architecture Overview

```
Admin Action
    │
    ├── Single Form Fill  ──►  POST /register/student
    │                          POST /register/supervisor
    │                               │
    │                               └── User + Profile created instantly
    │                                   Temp password returned in response
    │
    └── CSV / Excel Upload ──►  POST /
                                     │
                                     ├── Parses file
                                     ├── Creates bulk_import_jobs row  (status: pending)
                                     ├── Creates N bulk_import_items rows (status: pending)
                                     └── Returns 201 immediately  ◄── Admin gets job_id
                                              │
                                              └── BackgroundTask kicks off (no cron needed)
                                                       │
                                                       ├── For each item:
                                                       │     ├── Validates data
                                                       │     ├── Creates user + profile  ◄── User created here
                                                       │     ├── Generates temp password (encrypted in DB)
                                                       │     └── Sets item status: success / skipped / failed
                                                       │
                                                       └── Marks job: done
                                                              │
                                                   Admin polls GET /{job_id}
                                                   Admin fetches GET /{job_id}/report
                                                   Admin downloads GET /{job_id}/results.csv
```

---

## Database Tables

> **Note:** Run `sql/create_bulk_import_tables.sql` in your Supabase SQL Editor if these tables don't exist yet.

### `bulk_import_jobs`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `created_by` | UUID → `users.user_id` | Admin who triggered the import |
| `target_role` | enum: `student \| supervisor` | Which role is being imported |
| `status` | enum: `pending \| processing \| done \| failed` | Job lifecycle status |
| `total_rows` | integer | Total rows parsed from file |
| `processed_rows` | integer | How many rows have been processed |
| `success_count` | integer | Users successfully created |
| `failed_count` | integer | Rows that errored |
| `skipped_count` | integer | Rows skipped (duplicate email/roll) |
| `created_at` | timestamptz | When admin uploaded the file |
| `updated_at` | timestamptz | Last update time |

### `bulk_import_items`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `job_id` | UUID → `bulk_import_jobs.id` | Parent job |
| `row_number` | integer | Row number from original file (for error reporting) |
| `payload` | JSONB | Original CSV row data |
| `status` | enum: `pending \| success \| failed \| skipped` | Item outcome |
| `error` | text | Error message if failed/skipped |
| `created_user_id` | UUID → `users.user_id` | Created user (if success) |
| `temp_password_enc` | text | Encrypted temp password (expires after 24h) |
| `expires_at` | timestamptz | When temp password is purged |
| `created_at` | timestamptz | Item creation time |

### Student / Supervisor Fields Set During Registration

**Students** (`students` table):

| Field | Value Set |
|-------|-----------|
| `roll_number` | From CSV / form |
| `department` | From CSV / form (optional) |
| `fyp_start_semester` | From CSV / form — `Fall`, `Spring`, or `Summer` |
| `fyp_start_year` | From CSV / form — e.g. `2026` |
| `is_active` | `true` (auto) |
| `cgpa` | `null` (student fills later) |
| `interests`, `skills` | `[]` (student fills later) |

**Supervisors** (`supervisors` table):

| Field | Value Set |
|-------|-----------|
| `department` | From CSV / form (required) |
| `designation` | From CSV / form (required) |
| `is_supervisor` | `true` (auto) |
| `is_jury` | `true` (auto) |
| `is_active` | `true` (auto) |
| `project_type` | `"research"` (default) |
| `capacity_max` | `8` (default) |
| `description` | `null` (supervisor fills from profile later) |

---

## Single User Registration

### 1. Register Single Student

```
POST /api/admin/user-registration/register/student
Content-Type: application/json
Authorization: Bearer <admin_token>
```

**Request Body:**
```json
{
  "full_name": "John Doe",
  "email": "john.doe@university.edu.pk",
  "roll_number": "22K-1001",
  "fyp_start_semester": "Fall",
  "fyp_start_year": 2026,
  "department": "Computer Science"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `full_name` | string | ✅ | Max 200 chars |
| `email` | string (email) | ✅ | Must be unique |
| `roll_number` | string | ✅ | Must be unique |
| `fyp_start_semester` | `"Fall" \| "Spring" \| "Summer"` | ✅ | Case-sensitive enum |
| `fyp_start_year` | integer | ✅ | Between 2000–2100 |
| `department` | string | ❌ | Optional; student fills later |

**Success Response `201`:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "full_name": "John Doe",
  "email": "john.doe@university.edu.pk",
  "role": "student",
  "temp_password": "aB3xK9mP2qLw",
  "message": "Student John Doe registered successfully."
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `409 Conflict` | Email already registered |
| `409 Conflict` | Roll number already exists |
| `422 Unprocessable Entity` | Invalid field (e.g. bad semester value, year out of range) |
| `403 Forbidden` | Not an admin |

---

### 2. Register Single Supervisor

```
POST /api/admin/user-registration/register/supervisor
Content-Type: application/json
Authorization: Bearer <admin_token>
```

**Request Body:**
```json
{
  "full_name": "Dr. Ahmad Ali",
  "email": "ahmad.ali@university.edu.pk",
  "department": "Computer Science",
  "designation": "Associate Professor"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `full_name` | string | ✅ | Max 200 chars |
| `email` | string (email) | ✅ | Must be unique |
| `department` | string | ✅ | |
| `designation` | string | ✅ | e.g. "Professor", "Assistant Professor" |

**Success Response `201`:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440001",
  "full_name": "Dr. Ahmad Ali",
  "email": "ahmad.ali@university.edu.pk",
  "role": "supervisor",
  "temp_password": "Xm7nQ2pLrJ4s",
  "message": "Supervisor Dr. Ahmad Ali registered successfully."
}
```

**Error Responses:** Same pattern as student (409 on duplicate email, 422 on bad input).

---

## Bulk Registration (CSV / Excel)

### 3. Upload Bulk Import File

```
POST /api/admin/user-registration/
Content-Type: multipart/form-data
Authorization: Bearer <admin_token>
```

**Form Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | file | ✅ | `.csv`, `.xlsx`, or `.xls` |
| `target_role` | string | ✅ | `"student"` or `"supervisor"` |

**Success Response `201`:**
```json
{
  "job_id": "a1b2c3d4-...",
  "total_rows": 120,
  "status": "pending",
  "message": "Job created successfully. 120 rows queued — processing started automatically."
}
```

> **Important:** Processing starts immediately as a background task — no polling for start, only for completion.

---

### 4. Poll Job Status

```
GET /api/admin/user-registration/{job_id}
Authorization: Bearer <admin_token>
```

**Response:**
```json
{
  "job": {
    "id": "a1b2c3d4-...",
    "target_role": "student",
    "status": "processing",
    "total_rows": 120,
    "processed_rows": 75,
    "success_count": 70,
    "failed_count": 3,
    "skipped_count": 2,
    "progress_percent": 62.5,
    "created_at": "2026-03-01T08:30:00Z",
    "updated_at": "2026-03-01T08:30:45Z"
  },
  "recent_errors": [
    {
      "row_number": 14,
      "email": "bad@email",
      "full_name": "Jane Smith",
      "status": "failed",
      "error": "Invalid email format: bad@email"
    }
  ]
}
```

**Job Status Values:**

| Status | Meaning |
|--------|---------|
| `pending` | Job queued, background task not started yet |
| `processing` | Background task is actively processing items |
| `done` | All items processed (some may be failed/skipped) |
| `failed` | Fatal error occurred during processing |

---

### 5. Get Full Job Report

```
GET /api/admin/user-registration/{job_id}/report
Authorization: Bearer <admin_token>
```

**Response:**
```json
{
  "job_id": "a1b2c3d4-...",
  "target_role": "student",
  "status": "done",
  "total_rows": 120,
  "success_count": 115,
  "failed_count": 3,
  "skipped_count": 2,
  "pending_count": 0,
  "progress_percent": 100.0,
  "created_at": "2026-03-01T08:30:00Z",
  "updated_at": "2026-03-01T08:31:10Z",
  "created_users": [
    {
      "row_number": 2,
      "full_name": "John Doe",
      "email": "john.doe@university.edu.pk",
      "roll_number": "22K-1001",
      "status": "success",
      "error": null,
      "user_id": "550e8400-..."
    }
  ],
  "skipped_items": [
    {
      "row_number": 5,
      "full_name": "Sara Ahmed",
      "email": "sara@university.edu.pk",
      "roll_number": "22K-1004",
      "status": "skipped",
      "error": "Email already registered",
      "user_id": null
    }
  ],
  "failed_items": [
    {
      "row_number": 14,
      "full_name": "Jane Smith",
      "email": "bad@email",
      "roll_number": "22K-1010",
      "status": "failed",
      "error": "Invalid email format: bad@email",
      "user_id": null
    }
  ],
  "pending_items": []
}
```

> Use this endpoint to show the admin a **summary dashboard** after job completion.

---

### 6. Download Results CSV

```
GET /api/admin/user-registration/{job_id}/results.csv
Authorization: Bearer <admin_token>
```

Returns a `.csv` file with columns:

```
row_number, full_name, email, roll_number, department, status, error, user_id, temp_password
```

> ⏰ **`temp_password` is only populated for 24 hours** after creation. After expiry it returns empty. Download promptly.

---

### 7. Retry Failed Items

```
POST /api/admin/user-registration/{job_id}/retry
Authorization: Bearer <admin_token>
```

Resets all `failed` items back to `pending` and restarts background processing.

**Response:**
```json
{
  "job_id": "a1b2c3d4-...",
  "items_reset": 3,
  "message": "3 failed items reset to pending — reprocessing started."
}
```

> Use this when items failed due to transient errors (e.g. DB timeout). Skipped items are NOT retried.

---

### 8. Resume Interrupted Job

```
POST /api/admin/user-registration/{job_id}/resume
Authorization: Bearer <admin_token>
```

Resumes a job stuck in `processing` after a server crash or power failure. Remaining `pending` items are processed. Already-completed items are **never reprocessed**.

**Response:**
```json
{
  "job_id": "a1b2c3d4-...",
  "items_reset": 45,
  "message": "Job resumed — 45 pending items will be processed."
}
```

---

### 9. Manual Process All Pending

```
POST /api/admin/user-registration/run-pending
Authorization: Bearer <admin_token>
```

Fallback endpoint. Processes one batch of pending items across all jobs. Use if background task failed silently.

---

## CSV / Excel File Format

### Student Template (`templates/student_import_template.csv`)

```csv
full_name,email,roll_number,fyp_start_semester,fyp_start_year,department
John Doe,john.doe@university.edu.pk,22K-1001,Fall,2026,Computer Science
Jane Smith,jane.smith@university.edu.pk,22K-1002,Spring,2026,Software Engineering
```

**Required columns:** `full_name`, `email`, `roll_number`, `fyp_start_semester`, `fyp_start_year`
**Optional columns:** `department`

| Column | Valid Values |
|--------|-------------|
| `fyp_start_semester` | `Fall`, `Spring`, `Summer` (case-insensitive in CSV) |
| `fyp_start_year` | Integer, e.g. `2026` |

---

### Supervisor Template (`templates/supervisor_import_template.csv`)

```csv
full_name,email,department,designation
Dr. Ahmad Ali,ahmad.ali@university.edu.pk,Computer Science,Associate Professor
Dr. Fatima Zahra,fatima.zahra@university.edu.pk,Software Engineering,Assistant Professor
```

**Required columns:** `full_name`, `email`, `department`, `designation`

---

## Field Defaults Set Automatically

These fields are **never** in the CSV — they are set by the system during registration:

| Role | Field | Auto Value |
|------|-------|------------|
| Student | `is_active` | `true` |
| Student | `cgpa` | `null` |
| Student | `interests`, `skills` | `[]` |
| Student | `skills_levels` | `{}` |
| Supervisor | `is_supervisor` | `true` |
| Supervisor | `is_jury` | `true` |
| Supervisor | `is_active` | `true` |
| Supervisor | `project_type` | `"research"` |
| Supervisor | `capacity_max` | `8` |
| Supervisor | `capacity_filled` | `0` |
| Both | `password_hash` | Bcrypt of generated temp password |
| Both | `role` | `"student"` or `"supervisor"` |

---

## Error Handling Reference

### Item-Level Errors (Bulk Import)

| Error Message | Cause | Resolution |
|---------------|-------|------------|
| `Email already registered` | Duplicate email in system | Skipped — user already exists |
| `Roll number already exists: 22K-1001` | Duplicate roll number | Skipped |
| `Invalid email format: bad@email` | Malformed email in CSV | Fix in CSV, retry |
| `full_name is required and cannot be empty` | Empty name cell | Fix in CSV, retry |
| `fyp_start_semester is required for students` | Missing column | Add column to CSV |
| `Invalid fyp_start_semester: 'Autumn'` | Wrong semester value | Use Fall, Spring, or Summer |
| `Invalid fyp_start_year: 99` | Year out of range | Use year between 2000–2100 |
| `department is required for supervisors` | Empty department | Ensure all rows have department |
| `designation is required for supervisors` | Empty designation | Ensure all rows have designation |

### Job-Level Status Codes

| HTTP Code | Scenario |
|-----------|---------|
| `201` | Upload accepted / user created |
| `400` | Bad file format, missing columns, empty file |
| `403` | Not an admin |
| `404` | Job ID not found |
| `409` | Duplicate email or roll number (single registration) |
| `422` | Invalid field value in request body |
| `500` | Server error during processing |

---

## Frontend Integration Plan

### Single Registration Flow

#### UX Flow

```
Admin clicks "Add User"
    │
    └──► Modal / Drawer opens with two tabs:
              ├── "Student"
              └── "Supervisor"
                       │
                       └── Admin fills form → clicks "Register"
                                │
                                ├── POST /register/student OR /register/supervisor
                                ├── Show loading spinner
                                └── On success → show temp password in a modal alert
                                         │
                                         └── "Copy Password" button
                                             "Done" closes modal
```

#### Recommended Components

```
<AddUserModal>
  <Tabs value={role} onChange={setRole}>
    <Tab label="Student" value="student" />
    <Tab label="Supervisor" value="supervisor" />
  </Tabs>

  {role === "student" && <StudentRegistrationForm />}
  {role === "supervisor" && <SupervisorRegistrationForm />}
</AddUserModal>

<CredentialsDialog
  open={showCredentials}
  email={createdUser.email}
  tempPassword={createdUser.temp_password}
/>
```

#### Student Form Fields

```
Full Name*          → text input
Email*              → email input (validate format on client)
Roll Number*        → text input
FYP Start Semester* → dropdown: Fall | Spring | Summer
FYP Start Year*     → number input (default: current year)
Department          → text input (optional, labelled "can be set later")
```

#### Supervisor Form Fields

```
Full Name*    → text input
Email*        → email input
Department*   → text input
Designation*  → text input or dropdown (Professor, Assoc. Prof, Asst. Prof, Lecturer)
```

#### API Call (Single Student)

```typescript
// hooks/useCreateStudent.ts
const createStudent = async (data: CreateStudentPayload) => {
  const res = await apiClient.post('/admin/user-registration/register/student', data);
  return res.data; // { user_id, full_name, email, role, temp_password, message }
};

// On success:
setCreatedCredentials({ email: res.email, password: res.temp_password });
setShowCredentialsModal(true);

// On 409:
toast.error('This email or roll number already exists in the system.');

// On 422:
// Show field-level validation errors from the response body
```

---

### Bulk Registration Flow

#### UX Flow

```
Admin clicks "Bulk Import"
    │
    └──► Upload Page / Drawer
              │
              ├── Step 1: Choose Role (Student / Supervisor)
              ├── Step 2: Download Template  ◄── Link to CSV template
              ├── Step 3: Upload File  ◄── Drag & drop or file picker
              └── Step 4: Click "Import"
                       │
                       └── POST / (multipart)
                                │
                                ├── Receive { job_id, total_rows, status }
                                │
                                └── Redirect to Job Status Page  /admin/imports/{job_id}
                                         │
                                         ├── Poll GET /{job_id} every 3 seconds
                                         ├── Show progress bar (processed_rows / total_rows)
                                         └── When status === "done":
                                                  │
                                                  ├── Show summary cards:
                                                  │     ✅ X Created
                                                  │     ⏭️ Y Skipped
                                                  │     ❌ Z Failed
                                                  │
                                                  ├── Show full report via GET /{job_id}/report
                                                  │
                                                  ├── "Download Results CSV" button
                                                  │     → GET /{job_id}/results.csv
                                                  │
                                                  └── If failed_count > 0:
                                                        "Retry Failed" button
                                                        → POST /{job_id}/retry
```

---

#### Component Breakdown

```
<BulkImportPage>
  │
  ├── <BulkImportUploader>          // Step 1-3: Role select + file pick + submit
  │     ├── RoleSelector            // "Student" | "Supervisor" toggle
  │     ├── TemplateDownloadLinks   // Student CSV | Supervisor CSV
  │     └── FileDropzone            // Drag & drop, shows file name preview
  │
  ├── <BulkImportJobList>           // List of past imports (GET /)
  │     └── <JobListItem>           // Shows status badge, date, counts
  │
  └── <BulkImportJobDetail>         // /admin/imports/:jobId
        ├── <JobStatusBanner>       // pending | processing | done | failed
        ├── <ProgressBar>           // processed_rows / total_rows * 100
        ├── <SummaryCards>          // Created / Skipped / Failed counts
        ├── <JobReportTable>        // From GET /{job_id}/report — tabs: Created | Skipped | Failed
        ├── <DownloadButton>        // GET /{job_id}/results.csv
        └── <RetryButton>           // POST /{job_id}/retry (only if failed_count > 0)
```

---

#### State Management

```typescript
// Zustand / React Query approach

// 1. Upload state
interface BulkImportUploadState {
  targetRole: 'student' | 'supervisor';
  file: File | null;
  isUploading: boolean;
  jobId: string | null;
  error: string | null;
}

// 2. Job polling hook
function useJobStatus(jobId: string) {
  return useQuery({
    queryKey: ['bulk-import-job', jobId],
    queryFn: () => api.get(`/admin/user-registration/${jobId}`),
    refetchInterval: (data) => {
      // Stop polling when job is done or failed
      const status = data?.job?.status;
      if (status === 'done' || status === 'failed') return false;
      return 3000; // Poll every 3 seconds while processing
    },
    enabled: !!jobId,
  });
}

// 3. Report (fetch once when done)
function useJobReport(jobId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['bulk-import-report', jobId],
    queryFn: () => api.get(`/admin/user-registration/${jobId}/report`),
    enabled: enabled && !!jobId,
    staleTime: Infinity, // Don't refetch — report doesn't change after done
  });
}
```

---

#### Polling Strategy

```typescript
// When to poll vs. not

// ✅ Poll when status is: "pending" or "processing"
// 🛑 Stop polling when status is: "done" or "failed"

// Recommended interval: 3 seconds
// Show a pulsing indicator while polling

// Recommended UX for pending items:
// - Show spinner with "Processing... X of Y rows"
// - Update progress bar in real-time as processed_rows increments
// - When done: animate to 100% then show report

// On "failed" job status:
// - Show error banner: "Processing failed. Please contact support or retry."
// - Show "Retry" button which calls POST /{job_id}/retry
// - After retry, resume polling
```

---

#### Handling Resume After Crash (Power Failure)

```typescript
// If admin sees a job stuck in "processing" for > 5 minutes:
// Show "Job Interrupted?" banner with a "Resume" button

const isStuck = (job) => {
  if (job.status !== 'processing') return false;
  const lastUpdate = new Date(job.updated_at);
  const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
  return lastUpdate < fiveMinutesAgo;
};

// Resume call
await api.post(`/admin/user-registration/${jobId}/resume`);
// Then restart polling
```

---

#### Download Results CSV (Credentials Sheet)

```typescript
// Trigger file download in browser
const downloadResults = async (jobId: string) => {
  const response = await fetch(`/api/admin/user-registration/${jobId}/results.csv`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `import_results_${jobId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
};
```

> ⚠️ **Important Note for Frontend:** Temp passwords in the CSV **expire after 24 hours**. Show a prominent warning message on the Job Detail page:
>
> *"Download the results CSV within 24 hours to access temporary passwords."*

---

## Complete Endpoint Summary

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 1 | `POST` | `/register/student` | Create a single student (form) |
| 2 | `POST` | `/register/supervisor` | Create a single supervisor (form) |
| 3 | `POST` | `/` | Upload CSV/Excel for bulk import |
| 4 | `GET` | `/` | List all import jobs (paginated) |
| 5 | `GET` | `/{job_id}` | Poll job status + recent errors |
| 6 | `GET` | `/{job_id}/report` | Full report (created/skipped/failed) |
| 7 | `GET` | `/{job_id}/results.csv` | Download credentials CSV |
| 8 | `POST` | `/{job_id}/retry` | Retry failed items |
| 9 | `POST` | `/{job_id}/resume` | Resume after server crash |
| 10 | `POST` | `/run-pending` | Manual fallback trigger (admin) |

All endpoints are under: **`/api/admin/user-registration`**
All endpoints require: **Admin JWT Bearer token**
