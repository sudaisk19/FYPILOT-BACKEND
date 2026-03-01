# Submission Tasks API Documentation

**Base URL:** `http://localhost:8000/api/admin`

---

## Endpoints

### 1. **GET** `/submission-tasks` - List All Submission Tasks

Fetch paginated list of submission announcements.

**Query Parameters:**
- `search` (optional): string - Search by submission title or description
- `page` (optional): number - Page number (default: 1, min: 1)
- `per_page` (optional): number - Items per page (default: 10, min: 1, max: 50)

**Response:** `PaginatedSubmissionTasksResponse`

```typescript
{
  tasks: SubmissionTaskInfo[],
  total: number,
  page: number,
  per_page: number,
  total_pages: number,
  has_next: boolean,
  has_prev: boolean
}
```

**Example Request:**
```
GET /api/admin/submission-tasks?page=1&per_page=10&search=proposal
```

**Example Response:**
```json
{
  "tasks": [
    {
      "submission_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Project Proposal",
      "description": "Submit your initial project proposal",
      "created_at": "2026-02-10T10:30:00Z",
      "due_at": "2026-02-20T23:59:59Z",
      "total_points": 10.0,
      "assigned_to": "Students",
      "attachments": [
        {
          "file_id": "123e4567-e89b-12d3-a456-426614174000",
          "file_name": "proposal_template.docx",
          "storage_key": "announcements/proposal_template.docx",
          "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "size_bytes": 25600,
          "file_type": "Template",
          "uploaded_at": "2026-02-10T10:30:00Z"
        }
      ]
    }
  ],
  "total": 15,
  "page": 1,
  "per_page": 10,
  "total_pages": 2,
  "has_next": true,
  "has_prev": false
}
```

---

### 2. **POST** `/submission-tasks` - Create New Submission Task

Create a new submission announcement with optional file attachments.

**Content-Type:** `multipart/form-data`

**Request Body (Form Data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | **Yes** | Announcement title |
| `assignTo` | string | **Yes** | Target audience: `"Students"`, `"Supervisors"`, `"FYP-I Students"`, `"FYP-II Students"`, or `"Both"` |
| `dueDate` | string | **Yes** | Due date in ISO format (e.g., `2026-02-20T23:59:59Z`) |
| `description` | string | No | Announcement description |
| `total_marks` | number | No | Total marks for the submission |
| `uploaded_files` | File[] | No | Array of file attachments |
| `file_types` | string | No | Comma-separated file types: `"Document"` or `"Template"` (e.g., `"Template,Document"`) |

**Response:** `SubmissionAnnouncementResponse`

```typescript
{
  id: string,                    // UUID
  title: string,
  description: string | null,
  dueDate: string | null,        // ISO date string
  total_marks: number | null,
  assignTo: "Students" | "Supervisors" | "FYP-I Students" | "FYP-II Students" | "Both" | null,
  isSubmission: boolean,
  files: FileOutput[],
  createdAt: string,             // ISO date string
  updatedAt: string              // ISO date string
}
```

**Example Request (JavaScript/Fetch):**
```javascript
const formData = new FormData();
formData.append('title', 'Project Proposal');
formData.append('assignTo', 'Students');
formData.append('dueDate', '2026-02-20T23:59:59Z');
formData.append('description', 'Submit your initial project proposal');
formData.append('total_marks', '10');

// Optional: Add files
formData.append('uploaded_files', fileObject1);
formData.append('uploaded_files', fileObject2);
formData.append('file_types', 'Template,Document');

const response = await fetch('/api/admin/submission-tasks', {
  method: 'POST',
  body: formData,
  credentials: 'include'
});
```

**Example Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Project Proposal",
  "description": "Submit your initial project proposal",
  "dueDate": "2026-02-20T23:59:59Z",
  "total_marks": 10.0,
  "assignTo": "Students",
  "isSubmission": true,
  "files": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "proposal_template.docx",
      "url": "announcements/proposal_template.docx",
      "type": "Template",
      "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "size": 25600
    }
  ],
  "createdAt": "2026-02-10T10:30:00Z",
  "updatedAt": "2026-02-10T10:30:00Z"
}
```

---

### 3. **PATCH** `/submission-tasks/{announcement_id}` - Edit Submission Task

Update an existing submission announcement. All fields are optional.

**Path Parameters:**
- `announcement_id`: string (UUID) - ID of the announcement to update

**Content-Type:** `multipart/form-data`

**Request Body (Form Data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | No | New announcement title |
| `description` | string | No | New announcement description |
| `assignTo` | string | No | New target audience: `"Students"`, `"Supervisors"`, `"FYP-I Students"`, `"FYP-II Students"`, or `"Both"` |
| `dueDate` | string | No | New due date in ISO format |
| `total_marks` | string | No | New total marks (sent as string in form data) |
| `keep_file_ids` | string | No | Comma-separated UUIDs of **existing** files to keep (e.g., `"uuid1,uuid2"`). Files not in this list will be deleted. If empty string `""`, all existing files are deleted. If not provided, all existing files remain unchanged. |
| `uploaded_files` | File[] | No | **New** files to add |
| `file_types` | string | No | Comma-separated file types for **new** files only (e.g., `"Template,Document"`) |

**Important - File Handling in PATCH:**

This endpoint handles **two separate groups of files**:

1. **Existing Files** (already in database):
   - Controlled by `keep_file_ids` parameter
  - These files already have their `type` (Document/Template) stored in database
  - `file_types` **DO NOT** apply to existing files
   - Example: To keep files with IDs `abc123` and `def456`, send `keep_file_ids=abc123,def456`

2. **New Files** (being uploaded now):
   - Sent via `uploaded_files` parameter
  - Their types specified in `file_types` parameter
  - Example: Upload 2 new files with `file_types=Template,Document`

**File Management Scenarios:**

| Scenario | `keep_file_ids` | `uploaded_files` | `file_types` | Result |
|----------|----------------|------------------|--------------|---------|
| Keep all existing, add new | Not provided | 2 files | `Template,Document` | All existing files kept, 2 new files added |
| Delete all existing, add new | `""` (empty) | 1 file | `Template` | All existing files deleted, 1 new file added |
| Keep some, add new | `uuid1,uuid2` | 1 file | `Document` | Only files `uuid1` and `uuid2` kept, 1 new file added |
| Keep all, no changes | Not provided | None | None | All existing files kept, no new files |
| Delete all, no new files | `""` (empty) | None | None | All existing files deleted, no new files |

**Response:** `SubmissionAnnouncementResponse` (same structure as POST)

**Example Request (JavaScript/Fetch):**

```javascript
// Scenario: Keep 2 existing files, add 1 new Template file
const formData = new FormData();
formData.append('title', 'Updated Project Proposal');
formData.append('total_marks', '15');

// Keep these existing files (with their original types)
formData.append('keep_file_ids', 'uuid-existing-1,uuid-existing-2');

// Add 1 new Template file
formData.append('uploaded_files', newFileObject);
formData.append('file_types', 'Template');

const response = await fetch('/api/admin/submission-tasks/550e8400-e29b-41d4-a716-446655440000', {
  method: 'PATCH',
  body: formData,
  credentials: 'include'
});
```

**Example Response:** Same structure as POST response

---

## Data Types

### `SubmissionTaskInfo`
```typescript
{
  submission_id: string,         // UUID
  name: string,
  description: string | null,
  created_at: string,            // ISO date string
  due_at: string | null,         // ISO date string
  total_points: number | null,
  assigned_to: "Students" | "Supervisors" | "FYP-I Students" | "FYP-II Students" | "Both" | null,
  attachments: AttachmentInfo[]
}
```

### `AttachmentInfo`
```typescript
{
  file_id: string,               // UUID
  file_name: string,
  storage_key: string,
  mime_type: string | null,
  size_bytes: number | null,
  file_type: "Template" | "Document",
  uploaded_at: string | null     // ISO date string
}
```

### `FileOutput`
```typescript
{
  id: string,                    // UUID
  name: string,
  url: string,                   // Storage key/path
  type: "Template" | "Document",
  mimeType: string | null,
  size: number | null            // Size in bytes
}
```

### `SubmissionAnnouncementResponse`
```typescript
{
  id: string,                    // UUID
  title: string,
  description: string | null,
  dueDate: string | null,        // ISO date string
  total_marks: number | null,
  assignTo: "Students" | "Supervisors" | "FYP-I Students" | "FYP-II Students" | "Both" | null,
  isSubmission: boolean,         // Always true for submission tasks
  files: FileOutput[],
  createdAt: string,             // ISO date string
  updatedAt: string              // ISO date string
}
```

### `PaginatedSubmissionTasksResponse`
```typescript
{
  tasks: SubmissionTaskInfo[],
  total: number,                 // Total number of items
  page: number,                  // Current page
  per_page: number,              // Items per page
  total_pages: number,           // Total number of pages
  has_next: boolean,             // Has next page
  has_prev: boolean              // Has previous page
}
```

---

## Important Notes

### 1. **File Uploads:**
- Use `multipart/form-data` encoding for CREATE and EDIT endpoints
- Attach files using the field name `uploaded_files` (can be multiple files)
- Specify file types in `file_types` as comma-separated values matching the order of uploaded files
- Only `file_types` is needed; modules are not tracked for submission files

**Example:**
```javascript
// Uploading 3 files: Template, Document, Template
formData.append('uploaded_files', file1);
formData.append('uploaded_files', file2);
formData.append('uploaded_files', file3);
formData.append('file_types', 'Template,Document,Template');
```

### 2. **Date Format:**
- All dates must be in ISO 8601 format
- Include timezone (UTC recommended): `2026-02-20T23:59:59Z`
- Backend will parse dates sent with `Z` suffix or timezone offset

### 3. **File Management in EDIT:**
- **Two separate file groups:**
  - **Existing files** (already in database): Controlled by `keep_file_ids`
    - These files **already have** their type (Document/Template) stored
    - The `file_types` parameter **DOES NOT** apply to existing files
    - You only specify which ones to keep via their UUIDs
  - **New files** (being uploaded): Controlled by `uploaded_files`
    - Types are specified via `file_types`
    - These are completely new uploads
    
- `keep_file_ids` behavior:
  - **Not provided** (field absent): All existing files are kept unchanged
  - **Empty string** `""`: All existing files are deleted
  - **Comma-separated UUIDs**: Only specified existing files are kept, others are deleted
  
- New files in `uploaded_files` are **always added** (independent of `keep_file_ids`)

**Example:**
```javascript
// Current announcement has 3 existing files:
// - file1 (uuid-1): Template
// - file2 (uuid-2): Document
// - file3 (uuid-3): Template

// To: Keep file1 and file2, delete file3, add 1 new Template file
formData.append('keep_file_ids', 'uuid-1,uuid-2'); // Keep these existing files
formData.append('uploaded_files', newFile);        // Add new file
formData.append('file_types', 'Template');         // Type for NEW file only

// Result: 
// - file1 remains (Template) - from keep_file_ids
// - file2 remains (Document) - from keep_file_ids  
// - file3 deleted - not in keep_file_ids
// - newFile added (Template) - from uploaded_files with its type entry
```

### 4. **Authentication:**
- All endpoints require admin authentication
- Include credentials in requests: `credentials: 'include'` for fetch API
- Returns `403 Forbidden` if user is not an admin

### 5. **Field Mapping:**
Note the field name differences between GET (list) and POST/PATCH responses:

| List Response (`SubmissionTaskInfo`) | Create/Edit Response (`SubmissionAnnouncementResponse`) |
|--------------------------------------|-----------------------------------------------------|
| `submission_id` | `id` |
| `name` | `title` |
| `due_at` | `dueDate` |
| `total_points` | `total_marks` |
| `assigned_to` | `assignTo` |
| `attachments` | `files` |

---

## Troubleshooting File Uploads

If file uploads are not working, check the following:

### 1. **Content-Type Header**
- **DO NOT** manually set `Content-Type: multipart/form-data`
- Let the browser/fetch API set it automatically (it needs to include the boundary parameter)
  
```javascript
// ❌ WRONG - Don't do this
fetch('/api/admin/submission-tasks', {
  method: 'POST',
  headers: { 'Content-Type': 'multipart/form-data' }, // ❌ WRONG!
  body: formData
});

// ✅ CORRECT - Let browser set Content-Type
fetch('/api/admin/submission-tasks', {
  method: 'POST',
  body: formData,  // Browser automatically sets correct Content-Type
  credentials: 'include'
});
```

### 2. **File Field Name**
- Must use `uploaded_files` (plural) as the field name
- Can append multiple files with the same field name

```javascript
// ✅ CORRECT
formData.append('uploaded_files', file1);
formData.append('uploaded_files', file2);

// ❌ WRONG
formData.append('file', file1);           // Wrong field name
formData.append('files[]', file1);        // Wrong field name
formData.append('uploaded_files[]', file1); // Don't add []
```

### 3. **File Validation**
Files are only processed if they meet these criteria:
- Must be a valid `File` or `Blob` object
- Must have a `filename` property
- Must have `size > 0` (non-empty)

### 4. **File Types Format**
```javascript
// ✅ CORRECT - Comma-separated, one type per file
formData.append('file_types', 'Template,Document,Template');

// ❌ WRONG
formData.append('file_types', 'Template');        // Missing types for other files
formData.append('file_types', ['Template', 'Document']); // Don't use array
```

### 5. **Check Server Logs**
The endpoints now include detailed logging. Check your server console for:
```
INFO: Received 2 files for upload
INFO: Valid file 0: proposal.pdf (245760 bytes)
INFO: Valid file 1: template.docx (51200 bytes)
INFO: File types: ['Template', 'Document']
INFO: Uploading 2 files to storage...
INFO: Successfully uploaded 2 files to storage
INFO: Saving file to DB: proposal.pdf (type=Template)
INFO: Saving file to DB: template.docx (type=Document)
```

### 6. **Response Verification**
Check that uploaded files appear in the response:
```javascript
const response = await fetch('/api/admin/submission-tasks', {
  method: 'POST',
  body: formData,
  credentials: 'include'
});

const data = await response.json();
console.log('Uploaded files:', data.files);
// Should show array of FileOutput objects with id, name, url, and type
```

### 7. **Common Issues**

| Issue | Cause | Solution |
|-------|-------|----------|
| No files in response | Files not sent or invalid | Check field name is `uploaded_files` and files are valid |
| 400 Bad Request | Missing required fields | Ensure `title`, `assignTo`, `dueDate` are provided |
| Files uploaded but wrong type | file_types mismatch | Ensure `file_types` count matches file count |
| PATCH deletes wanted files | keep_file_ids missing | Include UUIDs of files to keep |

---

## Error Responses

All endpoints may return error responses:

**400 Bad Request:**
```json
{
  "detail": "Invalid dueDate format. Use ISO format: YYYY-MM-DDTHH:MM:SSZ"
}
```

**403 Forbidden:**
```json
{
  "detail": "Admin only"
}
```

**404 Not Found:**
```json
{
  "detail": "Announcement not found"
}
```

---

## Complete Integration Example

```typescript
// TypeScript Interface Definitions
interface SubmissionTaskInfo {
  submission_id: string;
  name: string;
  description: string | null;
  created_at: string;
  due_at: string | null;
  total_points: number | null;
  assigned_to: "Students" | "Supervisors" | "FYP-I Students" | "FYP-II Students" | "Both" | null;
  attachments: AttachmentInfo[];
}

interface AttachmentInfo {
  file_id: string;
  file_name: string;
  storage_key: string;
  mime_type: string | null;
  size_bytes: number | null;
  file_type: "Template" | "Document";
  uploaded_at: string | null;
}

interface SubmissionAnnouncementResponse {
  id: string;
  title: string;
  description: string | null;
  dueDate: string | null;
  total_marks: number | null;
  assignTo: "Students" | "Supervisors" | "FYP-I Students" | "FYP-II Students" | "Both" | null;
  isSubmission: boolean;
  files: FileOutput[];
  createdAt: string;
  updatedAt: string;
}

interface FileOutput {
  id: string;
  name: string;
  url: string;
  type: "Template" | "Document";
  mimeType: string | null;
  size: number | null;
}

interface PaginatedSubmissionTasksResponse {
  tasks: SubmissionTaskInfo[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

// API Client Functions
const BASE_URL = 'http://localhost:8000/api/admin';

async function listSubmissionTasks(
  page: number = 1,
  perPage: number = 10,
  search?: string
): Promise<PaginatedSubmissionTasksResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    per_page: perPage.toString(),
  });
  if (search) params.append('search', search);

  const response = await fetch(`${BASE_URL}/submission-tasks?${params}`, {
    credentials: 'include',
  });
  return response.json();
}

async function createSubmissionTask(data: {
  title: string;
  assignTo: string;
  dueDate: string;
  description?: string;
  total_marks?: number;
  files?: File[];
  fileTypes?: string[];
}): Promise<SubmissionAnnouncementResponse> {
  const formData = new FormData();
  formData.append('title', data.title);
  formData.append('assignTo', data.assignTo);
  formData.append('dueDate', data.dueDate);
  
  if (data.description) formData.append('description', data.description);
  if (data.total_marks) formData.append('total_marks', data.total_marks.toString());
  
  if (data.files && data.files.length > 0) {
    data.files.forEach(file => formData.append('uploaded_files', file));
    if (data.fileTypes) formData.append('file_types', data.fileTypes.join(','));
  }

  const response = await fetch(`${BASE_URL}/submission-tasks`, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });
  return response.json();
}

async function editSubmissionTask(
  announcementId: string,
  data: {
    title?: string;
    description?: string;
    assignTo?: string;
    dueDate?: string;
    total_marks?: number;
    keepFileIds?: string[];
    newFiles?: File[];
    fileTypes?: string[];
  }
): Promise<SubmissionAnnouncementResponse> {
  const formData = new FormData();
  
  if (data.title) formData.append('title', data.title);
  if (data.description !== undefined) formData.append('description', data.description);
  if (data.assignTo) formData.append('assignTo', data.assignTo);
  if (data.dueDate) formData.append('dueDate', data.dueDate);
  if (data.total_marks !== undefined) formData.append('total_marks', data.total_marks.toString());
  
  if (data.keepFileIds !== undefined) {
    formData.append('keep_file_ids', data.keepFileIds.join(','));
  }
  
  if (data.newFiles && data.newFiles.length > 0) {
    data.newFiles.forEach(file => formData.append('uploaded_files', file));
    if (data.fileTypes) formData.append('file_types', data.fileTypes.join(','));
  }

  const response = await fetch(`${BASE_URL}/submission-tasks/${announcementId}`, {
    method: 'PATCH',
    body: formData,
    credentials: 'include',
  });
  return response.json();
}

---

## Submission Evaluation APIs

These endpoints power the admin grading flow for a single group submission.

### 1. **GET** `/submissions/{submission_id}/evaluation` – Fetch Submission Details

- **Path Params**
  - `submission_id` (UUID) – Target submission
- **Response:** `SubmissionEvaluationResponse`

```typescript
interface SubmissionEvaluationResponse {
  submissionId: string;
  title: string;
  totalMarks: number | null;
  note: string | null;
  adminMarks: number | null;
  adminFeedback: string | null;
  adminGradedAt: string | null; // ISO timestamp
  submittedAt: string | null;   // Group's submission timestamp
  files: SubmissionFileInfo[];
}

interface SubmissionFileInfo {
  fileId: string;
  fileName: string;
  storageKey: string;
  mimeType: string | null;
  sizeBytes: number | null;
  uploadedAt: string | null;
}
```

> **Note:** Supervisor grading details are deliberately excluded; admins only see/manage their own marks.

### 2. **POST** `/submissions/{submission_id}/evaluation` – Update Admin Grading

- **Path Params**
  - `submission_id` (UUID)
- **Request Body (JSON):**

| Field        | Type   | Required | Description                  |
|--------------|--------|----------|------------------------------|
| `adminMarks` | number | No       | Admin-awarded marks          |
| `adminFeedback` | string | No    | Admin feedback/remarks       |

- **Response:** Updated `SubmissionEvaluationResponse` (same shape as GET)

**Example:**

```json
{
  "adminMarks": 18.5,
  "adminFeedback": "Great demo, minor UI tweaks needed."
}
```

### 3. **GET** `/submissions/{submission_id}/files/{file_id}/download` – Download Submission File

- **Path Params**
  - `submission_id` (UUID) – Used to verify ownership
  - `file_id` (UUID) – Target submission file
- **Response:** Binary file stream with `Content-Disposition: inline; filename="..."`
- **Errors:** `404` if the submission or file cannot be found; `403` if requester is not an admin.

Use the returned `storageKey` from the evaluation payload to correlate files on the frontend if needed.
```
