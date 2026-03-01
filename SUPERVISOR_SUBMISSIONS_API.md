# Supervisor Submissions — API Reference & Frontend Integration Guide

> **Base URL:** `/api/supervisors/submissions`
> **Auth:** All endpoints require a valid supervisor JWT token in the `Authorization: Bearer <token>` header.

---

## 📋 Overview — 8 Endpoints

| #  | Method   | Path                                                        | Purpose                            | Frontend Page               |
|----|----------|-------------------------------------------------------------|------------------------------------|-----------------------------|
| 1  | `POST`   | `/submission-create`                                        | Create a new submission task       | Create Task Modal/Page      |
| 2  | `GET`    | `/submission-list`                                          | List all my submission tasks       | Submissions List Page       |
| 3  | `GET`    | `/submission-details/{announcement_id}`                     | Get single task details            | Task Detail Page            |
| 4  | `PATCH`  | `/submission-update/{announcement_id}`                      | Edit an existing task              | Edit Task Modal/Page        |
| 5  | `GET`    | `/submission-responses/{announcement_id}`                   | List group submissions for a task  | Task → Submissions Table    |
| 6  | `GET`    | `/submission-evaluation/{submission_id}`                    | Get submission for grading         | Evaluation/Grading Page     |
| 7  | `POST`   | `/submission-evaluation-update/{submission_id}`             | Save supervisor marks & feedback   | Evaluation/Grading Page     |
| 8  | `GET`    | `/submission-files/{submission_id}/{file_id}/download`      | Download a student's submitted file| Evaluation Page (file link) |
| 9  | `GET`    | `/announcement-files/{file_id}/download`                    | Download an announcement file      | Task Detail (file link)     |

---

## 🔄 User Flow (Page-by-Page)

```
┌─────────────────────┐
│  Submissions List   │  ← API #2 (GET /submission-list)
│  (all tasks I made) │
└────────┬────────────┘
         │ click a task
         ▼
┌─────────────────────┐
│  Task Detail Page   │  ← API #3 (GET /submission-details/{id})
│  (title, due date,  │  ← API #9 (download announcement files)
│   description, etc) │
└────────┬────────────┘
         │ "View Submissions" button
         ▼
┌─────────────────────────┐
│  Group Submissions      │  ← API #5 (GET /submission-responses/{id})
│  Table                  │
│  ┌───────────────────┐  │
│  │ FYP-001 Submitted │──┼──→ click row (only if submission_id != null)
│  │ FYP-002 Missing   │  │
│  │ FYP-003 Graded    │  │
│  └───────────────────┘  │
└─────────────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Evaluation / Grading    │  ← API #6 (GET /submission-evaluation/{submission_id})
│  Page                    │  ← API #8 (download student files)
│                          │
│  Files: [📄 report.pdf]  │
│  Total Marks: 100        │
│  Supervisor Marks: [___] │
│  Feedback: [___________] │
│  [Save]                  │  ← API #7 (POST /submission-evaluation-update/{submission_id})
└──────────────────────────┘
```

---

## 📝 API #1 — Create Submission Task

```
POST /api/supervisors/submissions/submission-create
Content-Type: multipart/form-data
```

### Purpose
Supervisor creates a new submission task (assignment) for their managed groups.

### Request Body (FormData)

| Field            | Type     | Required | Description                                              |
|------------------|----------|----------|----------------------------------------------------------|
| `title`          | string   | ✅       | Title of the submission task                             |
| `dueDate`        | string   | ✅       | Due date in ISO format (e.g., `2026-03-01T23:59:59Z`)   |
| `group_id`       | string   | ✅       | UUID of a specific group, or `"all"` for all groups      |
| `description`    | string   | ❌       | Description of the task                                  |
| `total_marks`    | number   | ❌       | Total marks for the submission                           |
| `uploaded_files`  | File[]   | ❌       | Attachment files (templates, reference docs)             |
| `file_types`     | string   | ❌       | Comma-separated: `"Document,Template"` (per file)        |

### Frontend Example
```javascript
const formData = new FormData();
formData.append('title', 'Project Proposal');
formData.append('dueDate', '2026-03-01T23:59:59Z');
formData.append('group_id', 'all'); // or specific UUID
formData.append('description', 'Submit your final proposal');
formData.append('total_marks', '100');
formData.append('uploaded_files', file1);
formData.append('uploaded_files', file2);
formData.append('file_types', 'Template,Document');

const res = await fetch('/api/supervisors/submissions/submission-create', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData,
});
```

### Response — `SubmissionAnnouncementResponse` (201)
```json
{
  "id": "531b8db5-e52f-4c9f-9bd1-ec7accfeed7e",
  "title": "Project Proposal",
  "description": "Submit your final proposal",
  "dueDate": "2026-03-01T23:59:59Z",
  "total_marks": 100,
  "assignTo": "Group: Smart Campus (FYP-001)",
  "isSubmission": true,
  "files": [
    {
      "id": "uuid",
      "name": "template.docx",
      "url": "storage-url",
      "type": "Template",
      "mimeType": "application/vnd.openxmlformats...",
      "size": 45000
    }
  ],
  "createdAt": "2026-02-25T10:00:00Z",
  "updatedAt": "2026-02-25T10:00:00Z"
}
```

---

## 📝 API #2 — List All My Submission Tasks

```
GET /api/supervisors/submissions/submission-list?search=&page=1&per_page=10
```

### Purpose
Fetches all submission tasks created by the logged-in supervisor (paginated).

### Query Parameters

| Param      | Type   | Default | Description                    |
|------------|--------|---------|--------------------------------|
| `search`   | string | null    | Filter by task title           |
| `page`     | int    | 1       | Page number                    |
| `per_page` | int    | 10      | Items per page (max 50)        |

### Frontend Example
```javascript
const res = await fetch(
  `/api/supervisors/submissions/submission-list?page=1&per_page=10&search=${searchTerm}`,
  { headers: { 'Authorization': `Bearer ${token}` } }
);
```

### Response — `PaginatedSubmissionTasksResponse` (200)
```json
{
  "tasks": [
    {
      "submission_id": "531b8db5-...",
      "name": "Project Proposal",
      "description": "Submit your final proposal",
      "created_at": "2026-02-25T10:00:00Z",
      "due_at": "2026-03-01T23:59:59Z",
      "total_points": 100,
      "assigned_to": "All Groups",
      "attachments": [
        {
          "file_id": "uuid",
          "file_name": "template.docx",
          "storage_key": "key",
          "mime_type": "application/...",
          "size_bytes": 45000,
          "file_type": "Template",
          "uploaded_at": "2026-02-25T10:00:00Z"
        }
      ]
    }
  ],
  "total": 5,
  "page": 1,
  "per_page": 10,
  "total_pages": 1,
  "has_next": false,
  "has_prev": false
}
```

> **Note:** `submission_id` here is actually the `announcement_id`. Use it for API #3, #4, #5.

---

## 📝 API #3 — Get Single Task Details

```
GET /api/supervisors/submissions/submission-details/{announcement_id}
```

### Purpose
Fetch full details of a specific submission task.

### Response — `SubmissionAnnouncementResponse` (200)
Same shape as API #1 response.

---

## 📝 API #4 — Edit a Submission Task

```
PATCH /api/supervisors/submissions/submission-update/{announcement_id}
Content-Type: multipart/form-data
```

### Purpose
Update an existing submission task (title, description, due date, marks, files, targets).

### Request Body (FormData) — All fields optional

| Field            | Type     | Description                                                  |
|------------------|----------|--------------------------------------------------------------|
| `title`          | string   | Updated title                                                |
| `description`    | string   | Updated description                                          |
| `group_id`       | string   | New target group UUID or `"all"`                             |
| `dueDate`        | string   | New due date (ISO format)                                    |
| `total_marks`    | string   | New total marks                                              |
| `keep_file_ids`  | string   | Comma-separated UUIDs of files to KEEP. Omit = keep all. Empty string = delete all. |
| `uploaded_files`  | File[]   | New files to upload                                          |
| `file_types`     | string   | Comma-separated types for new files                          |

### Frontend Example
```javascript
const formData = new FormData();
formData.append('title', 'Updated Title');
formData.append('dueDate', '2026-03-15T23:59:59Z');
formData.append('keep_file_ids', 'uuid1,uuid2'); // keep these, delete the rest

const res = await fetch(
  `/api/supervisors/submissions/submission-update/${announcementId}`,
  {
    method: 'PATCH',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  }
);
```

### Response — `SubmissionAnnouncementResponse` (200)
Same shape as API #1 response.

---

## 📝 API #5 — List Group Submissions (Responses to a Task)

```
GET /api/supervisors/submissions/submission-responses/{announcement_id}?page=1&per_page=10
```

### Purpose
See which groups have submitted and which are missing for a specific task. This is used to build the submissions table.

### Query Parameters

| Param           | Type   | Default | Description                                          |
|-----------------|--------|---------|------------------------------------------------------|
| `search`        | string | null    | Search by group name or FYP ID                       |
| `status_filter` | string | null    | Filter: `submitted`, `missing`, `graded`, `returned` |
| `page`          | int    | 1       | Page number                                          |
| `per_page`      | int    | 10      | Items per page                                       |

### Frontend Example
```javascript
const res = await fetch(
  `/api/supervisors/submissions/submission-responses/${announcementId}?page=1&per_page=50`,
  { headers: { 'Authorization': `Bearer ${token}` } }
);
```

### Response — `GroupSubmissionsResponse` (200)
```json
{
  "submissions": [
    {
      "group_id": "b6eb2426-...",
      "submission_id": "abc123-...",       // ← use this for evaluation. NULL if "Missing"
      "fyp_id": "FYP-001",
      "project_name": "Smart Campus",
      "status": "Submitted"                // Submitted | Missing | Graded | Returned | Pending
    },
    {
      "group_id": "c7430dba-...",
      "submission_id": null,               // ⚠️ NULL — group hasn't submitted yet
      "fyp_id": "FYP-002",
      "project_name": "AI Chatbot",
      "status": "Missing"
    }
  ],
  "total": 2,
  "page": 1,
  "per_page": 10,
  "total_pages": 1,
  "has_next": false,
  "has_prev": false
}
```

### ⚠️ IMPORTANT: Frontend Guard
```javascript
// When user clicks on a row to evaluate:
const handleEvaluate = (row) => {
  if (!row.submission_id) {
    // Show toast: "This group hasn't submitted yet"
    return;
  }
  navigate(`/supervisor/submissions/evaluate/${row.submission_id}`);
};
```

---

## 📝 API #6 — Get Submission for Evaluation (Grading Page)

```
GET /api/supervisors/submissions/submission-evaluation/{submission_id}
```

### Purpose
Fetch full submission details for grading. Shows student's files, notes, and supervisor's existing marks (if any). **Admin marks are NOT returned to supervisors.**

### Frontend Example
```javascript
const res = await fetch(
  `/api/supervisors/submissions/submission-evaluation/${submissionId}`,
  { headers: { 'Authorization': `Bearer ${token}` } }
);
```

### Response — `SubmissionEvaluationResponse` (200)
```json
{
  "submissionId": "abc123-...",
  "title": "Project Proposal Submission",
  "totalMarks": 100,
  "note": "Here is our proposal document",
  "adminMarks": null,              // always null for supervisor
  "adminFeedback": null,           // always null for supervisor
  "adminGradedAt": null,           // always null for supervisor
  "supervisorMarks": 85,           // supervisor's own marks (null if not graded yet)
  "supervisorFeedback": "Good work, needs more detail in section 3",
  "supervisorGradedAt": "2026-02-25T12:00:00Z",
  "files": [
    {
      "fileId": "file-uuid-1",
      "fileName": "proposal.pdf",
      "storageKey": "submissions/abc/proposal.pdf",
      "mimeType": "application/pdf",
      "sizeBytes": 1245678,
      "uploadedAt": "2026-02-24T15:30:00Z"
    }
  ],
  "submittedAt": "2026-02-24T15:30:00Z"
}
```

### Frontend Mapping for the Grading Form
```javascript
const data = await res.json();

// Pre-fill the form
setMarks(data.supervisorMarks ?? '');
setFeedback(data.supervisorFeedback ?? '');
setTotalMarks(data.totalMarks);
setFiles(data.files);
setTitle(data.title);
setNote(data.note);
```

---

## 📝 API #7 — Save Supervisor Marks & Feedback

```
POST /api/supervisors/submissions/submission-evaluation-update/{submission_id}
Content-Type: application/json
```

### Purpose
Supervisor submits/updates their marks and feedback for a student's submission.

### Request Body (JSON)
```json
{
  "supervisorMarks": 85,
  "supervisorFeedback": "Good work, needs more detail in section 3"
}
```

### Frontend Example
```javascript
const res = await fetch(
  `/api/supervisors/submissions/submission-evaluation-update/${submissionId}`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      supervisorMarks: parseFloat(marks),
      supervisorFeedback: feedback,
    }),
  }
);
```

### Response — `SubmissionEvaluationResponse` (200)
Same shape as API #6 response, with updated marks/feedback.

### Side Effects
- `supervisor_graded_at` is auto-set to current timestamp
- If submission status was `"submitted"`, it changes to `"graded"`

---

## 📝 API #8 — Download Student's Submitted File

```
GET /api/supervisors/submissions/submission-files/{submission_id}/{file_id}/download
```

### Purpose
Download or view a file uploaded by the student as part of their submission.

### Frontend Example
```javascript
// Open in new tab (for PDF, images) or trigger download
const fileUrl = `/api/supervisors/submissions/submission-files/${submissionId}/${fileId}/download`;
window.open(fileUrl, '_blank');

// Or with auth using fetch + blob:
const res = await fetch(fileUrl, {
  headers: { 'Authorization': `Bearer ${token}` },
});
const blob = await res.blob();
const url = URL.createObjectURL(blob);
window.open(url, '_blank');
```

### Response
Returns the binary file with appropriate `Content-Type` and `Content-Disposition: inline` header.

---

## 📝 API #9 — Download Announcement File

```
GET /api/supervisors/submissions/announcement-files/{file_id}/download
```

### Purpose
Download a template/document file attached to the submission task (announcement) itself.

### Frontend Example
Same pattern as API #8.

---

## 🏗️ Integration Plan — Step by Step

### Step 1: API Service Layer
Create a service file for all supervisor submission API calls:

```typescript
// src/services/supervisorSubmissionService.ts

const BASE = '/api/supervisors/submissions';

export const supervisorSubmissionApi = {
  // List all tasks
  listTasks: (params: { search?: string; page?: number; per_page?: number }) =>
    authFetch(`${BASE}/submission-list?${new URLSearchParams(params)}`),

  // Create task
  createTask: (formData: FormData) =>
    authFetch(`${BASE}/submission-create`, { method: 'POST', body: formData }),

  // Get single task
  getTask: (announcementId: string) =>
    authFetch(`${BASE}/submission-details/${announcementId}`),

  // Edit task
  editTask: (announcementId: string, formData: FormData) =>
    authFetch(`${BASE}/submission-update/${announcementId}`, { method: 'PATCH', body: formData }),

  // List group submissions for a task
  getSubmissions: (announcementId: string, params: { search?: string; status_filter?: string; page?: number; per_page?: number }) =>
    authFetch(`${BASE}/submission-responses/${announcementId}?${new URLSearchParams(params)}`),

  // Get submission for evaluation
  getEvaluation: (submissionId: string) =>
    authFetch(`${BASE}/submission-evaluation/${submissionId}`),

  // Save grading
  saveGrading: (submissionId: string, body: { supervisorMarks?: number; supervisorFeedback?: string }) =>
    authFetch(`${BASE}/submission-evaluation-update/${submissionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  // File download URL
  submissionFileUrl: (submissionId: string, fileId: string) =>
    `${BASE}/submission-files/${submissionId}/${fileId}/download`,

  announcementFileUrl: (fileId: string) =>
    `${BASE}/announcement-files/${fileId}/download`,
};
```

### Step 2: TypeScript Interfaces

```typescript
// src/types/supervisorSubmission.ts

interface SubmissionTaskInfo {
  submission_id: string; // This is actually announcement_id
  name: string;
  description: string | null;
  created_at: string;
  due_at: string | null;
  total_points: number | null;
  assigned_to: string | null;
  attachments: AttachmentInfo[];
}

interface AttachmentInfo {
  file_id: string;
  file_name: string;
  storage_key: string;
  mime_type: string | null;
  size_bytes: number | null;
  file_type: string;
  uploaded_at: string | null;
}

interface PaginatedTasks {
  tasks: SubmissionTaskInfo[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

interface GroupSubmissionStatus {
  group_id: string;
  submission_id: string | null; // ⚠️ can be null
  fyp_id: string;
  project_name: string;
  status: 'Submitted' | 'Missing' | 'Graded' | 'Returned' | 'Pending';
}

interface GroupSubmissionsResponse {
  submissions: GroupSubmissionStatus[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

interface SubmissionFileInfo {
  fileId: string;
  fileName: string;
  storageKey: string;
  mimeType: string | null;
  sizeBytes: number | null;
  uploadedAt: string | null;
}

interface SubmissionEvaluation {
  submissionId: string;
  title: string;
  totalMarks: number | null;
  note: string | null;
  supervisorMarks: number | null;
  supervisorFeedback: string | null;
  supervisorGradedAt: string | null;
  files: SubmissionFileInfo[];
  submittedAt: string | null;
}

interface SaveGradingRequest {
  supervisorMarks?: number;
  supervisorFeedback?: string;
}
```

### Step 3: Pages to Build

| Page                    | APIs Used      | Route Suggestion                                      |
|-------------------------|----------------|-------------------------------------------------------|
| Submissions List        | #2             | `/supervisor/submissions`                             |
| Create Task             | #1             | `/supervisor/submissions/create` (or modal)           |
| Task Detail             | #3, #9         | `/supervisor/submissions/:announcementId`             |
| Edit Task               | #3, #4         | `/supervisor/submissions/:announcementId/edit`         |
| Group Submissions Table | #5             | `/supervisor/submissions/:announcementId/responses`    |
| Evaluation / Grading    | #6, #7, #8     | `/supervisor/submissions/evaluate/:submissionId`       |

### Step 4: Key Frontend Guards

1. **Null submission_id check** — When navigating from group submissions table to evaluation:
   ```javascript
   if (!row.submission_id) {
     toast.error("This group hasn't submitted yet");
     return;
   }
   ```

2. **Marks validation** — Before saving:
   ```javascript
   if (marks > totalMarks) {
     toast.error(`Marks cannot exceed ${totalMarks}`);
     return;
   }
   ```

3. **Due date display** — Show overdue indicator:
   ```javascript
   const isOverdue = new Date(task.due_at) < new Date();
   ```
