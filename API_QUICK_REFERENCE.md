# Admin Submission APIs - Quick Reference

## File Upload & Download

### Upload Announcement Files
**POST** `/api/admin/files/upload`

Uploads files to Supabase Storage for use in announcements.

**Headers:**
- `Authorization: Bearer {token}`
- `Content-Type: multipart/form-data`

**Body:**
- `files`: List of file objects

**Response:**
```json
{
  "files": [
    {
      "name": "template.pdf",
      "url": "announcements/uuid.pdf",
      "mimeType": "application/pdf",
      "size": 1048576,
      "type": "Document"
    }
  ]
}
```

---

### Download Announcement File
**GET** `/api/admin/files/{file_id}/download`

Downloads or views an announcement file.

**Response:** File content with appropriate headers

---

### Download Submission File
**GET** `/api/admin/submissions/{submission_id}/files/{file_id}/download`

Downloads or views a submission file.

**Response:** File content with appropriate headers

---

## Submission Announcements (CRUD)

### Create Submission Announcement
**POST** `/api/admin/submission-tasks`

**Body:**
```json
{
  "title": "Final Project Submission",
  "description": "Submit your final project documentation",
  "dueDate": "2026-03-01T23:59:59Z",
  "total_marks": 100,
  "assignTo": "Students",
  "files": [
    {
      "name": "template.docx",
      "url": "announcements/uuid.docx",
      "type": "Template",
      "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "size": 25600
    }
  ]
}
```

---

### Edit Submission Announcement
**PATCH** `/api/admin/submission-tasks/{announcement_id}`

**Body:** Same as create (all fields optional)

---

### List Submission Tasks
**GET** `/api/admin/submission-tasks`

**Query Params:**
- `search` - Search by title/description
- `page` - Page number (default: 1)
- `per_page` - Items per page (default: 10, max: 50)

**Response:**
```json
{
  "tasks": [...],
  "total": 45,
  "page": 1,
  "per_page": 10,
  "total_pages": 5,
  "has_next": true,
  "has_prev": false
}
```

---

### Get Group Submissions Status
**GET** `/api/admin/submission-tasks/{announcement_id}/submissions`

**Query Params:**
- `search` - Search by group name or FYP ID
- `status_filter` - Filter by: submitted, missing, graded, returned
- `page` - Page number
- `per_page` - Items per page

**Response:**
```json
{
  "submissions": [
    {
      "fyp_id": "FYP-2024-001",
      "project_name": "AI Healthcare System",
      "status": "Submitted"
    }
  ],
  "total": 30,
  "page": 1,
  "per_page": 10,
  "total_pages": 3,
  "has_next": true,
  "has_prev": false
}
```

---

## Submission Evaluation

### Get Submission for Evaluation
**GET** `/api/admin/submissions/{submission_id}/evaluation`

**Response:**
```json
{
  "submissionId": "uuid",
  "title": "Final Project Submission",
  "totalMarks": 100,
  "supervisorMarks": 45,
  "adminMarks": 50,
  "supervisorFeedback": "Good work on implementation",
  "adminFeedback": "Excellent documentation",
  "supervisorGradedAt": "2026-02-10T10:30:00Z",
  "adminGradedAt": "2026-02-11T14:20:00Z",
  "files": [
    {
      "fileId": "uuid",
      "fileName": "report.pdf",
      "storageKey": "submissions/uuid.pdf",
      "mimeType": "application/pdf",
      "sizeBytes": 2048000,
      "uploadedAt": "2026-02-09T18:00:00Z"
    }
  ],
  "submittedAt": "2026-02-09T18:00:00Z"
}
```

---

### Update Admin Grading
**POST** `/api/admin/submissions/{submission_id}/evaluation`

**Body:**
```json
{
  "adminMarks": 50,
  "adminFeedback": "Excellent work! Well documented and implemented."
}
```

**Response:** Same as GET evaluation endpoint

**Notes:**
- Only `adminMarks` and `adminFeedback` can be updated
- `supervisorMarks` and `supervisorFeedback` are read-only
- Auto-sets `admin_graded_at` timestamp
- Changes status from "submitted" to "graded"

---

## Workflow Examples

### Create Submission Request with Files

```javascript
// 1. Upload files first
const formData = new FormData();
formData.append('files', file1);
formData.append('files', file2);

const uploadRes = await fetch('/api/admin/files/upload', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData
});
const { files } = await uploadRes.json();

// 2. Create announcement
await fetch('/api/admin/submission-tasks', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    title: "Milestone 1 Submission",
    dueDate: "2026-03-15T23:59:59Z",
    total_marks: 50,
    assignTo: "Students",
    files: files
  })
});
```

### Grade a Submission

```javascript
// 1. Get submission details
const submission = await fetch(
  `/api/admin/submissions/${submissionId}/evaluation`,
  {
    headers: { 'Authorization': `Bearer ${token}` }
  }
).then(r => r.json());

// 2. Grade it
await fetch(`/api/admin/submissions/${submissionId}/evaluation`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    adminMarks: 45,
    adminFeedback: "Great implementation, minor documentation issues."
  })
});
```

---

## Status Codes

- `200` - Success
- `201` - Created successfully
- `400` - Bad request (validation error)
- `403` - Forbidden (admin only)
- `404` - Resource not found
- `500` - Server error

---

## Notes

1. **All endpoints require admin authentication**
2. **File uploads limited to 50MB per file**
3. **Pagination defaults**: page=1, per_page=10
4. **Date format**: ISO 8601 (e.g., "2026-02-11T14:30:00Z")
5. **UUIDs** used for all entity IDs
