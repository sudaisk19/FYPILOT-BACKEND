# Admin Submission Tasks API

## Overview

This API allows admins to fetch official submission tasks (announcements marked as submission requests) that have been created for student groups.

## Endpoint

### GET `/api/admin/submission-tasks`

Fetches paginated list of official submission tasks created by admin.

**Authentication**: Admin only

**Query Parameters**:
- `search` (optional): Search by submission name/title
- `page` (default: 1): Page number
- `per_page` (default: 10, max: 50): Items per page

**Response**: `PaginatedSubmissionTasksResponse`

```json
{
  "tasks": [
    {
      "submission_id": "uuid",
      "name": "FYP Proposal Submission",
      "description": "Submit your FYP proposal document",
      "created_at": "2026-02-09T10:00:00Z",
      "due_at": null,
      "total_points": null,
      "assigned_to": "All Students",
      "attachments": [
        {
          "file_id": "uuid",
          "file_name": "proposal_template.docx",
          "storage_key": "s3/path/to/file",
          "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "size_bytes": 45678,
          "file_type": "Template",
          "module": "FYP1",
          "uploaded_at": "2026-02-09T10:00:00Z"
        }
      ]
    }
  ],
  "total": 25,
  "page": 1,
  "per_page": 10,
  "total_pages": 3,
  "has_next": true,
  "has_prev": false
}
```

## Database Schema

### Models Created

1. **Announcement** (`announcements` table)
   - Stores announcement/submission request details
   - Links to creator (admin/supervisor)
   - Has `is_submission_request` boolean flag

2. **AnnouncementTarget** (`announcement_targets` table)
   - Links announcements to specific groups or role targets
   - Enforces exclusivity: either `group_id` OR `target_role`, not both

3. **AnnouncementFile** (`announcement_files` table)
   - Files attached to announcements (templates, documents)
   - Categorized by `file_type` enum

4. **Submission** (`submissions` table)
   - Student group submissions in response to announcements
   - Tracks status, grading, due dates
   - Links to announcement via `linked_announcement_id`

5. **SubmissionFile** (`submission_files` table)
   - Files uploaded by students for submissions

## Migration

Run the migration to create the tables:

```bash
alembic upgrade head
```

## Usage Example

**Request**:
```bash
GET /api/admin/submission-tasks?search=proposal&page=1&per_page=10
Authorization: Bearer <admin_token>
```

**Frontend Integration**:

The API is designed to work with the frontend's `ProjectMonitoringPage` component, which displays submission tasks in a card grid format.

## Notes

- Currently, `due_at` and `total_points` are stored in the `Submission` model (when students submit), not in `Announcement`
- If you need to set due dates and points at the announcement/task creation level, consider adding these fields to the `announcements` table
- The `assigned_to` field is derived from `announcement_targets`:
  - `"All Students"` if `target_role = all_students`
  - `"All Supervisors"` if `target_role = all_supervisors`
  - `"Group: {group_name}"` if targeted to specific group

## Future Enhancements

1. Add `due_at` and `total_marks` columns to `announcements` table
2. Add POST/PUT/DELETE endpoints for creating/editing/deleting submission tasks
3. Add GET endpoint for individual submission task details
4. Add endpoint to fetch actual submissions by students for a given task
5. Add grading endpoints for supervisors/admin
