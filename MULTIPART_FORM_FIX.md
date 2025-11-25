# Fixed: Multipart Form Data & Supabase Bucket Setup

## Issues Resolved

### 1. ❌ Bucket Not Found Error (500)
**Problem**: Supabase Storage bucket "announcements" didn't exist
**Solution**: Created [SUPABASE_BUCKET_SETUP.md](SUPABASE_BUCKET_SETUP.md) with setup instructions

**Action Required**:
```bash
# Go to Supabase Dashboard → Storage → New bucket
# Name: announcements
# Public: ✅ Enable
# File size limit: 50 MB
```

### 2. ❌ No Structured Request Body in Swagger (422)
**Problem**: Using `Form(...)` with JSON string didn't show schema in Swagger UI
**Solution**: Changed endpoints to accept individual form fields instead of JSON string

## Changes Made

### Before (JSON String Approach)
```python
async def create_submission_announcement(
    body: str = Form(...),  # JSON string - not visible in Swagger
    uploaded_files: List[UploadFile] = File(None),
):
    body_dict = json.loads(body)  # Manual parsing
    body = CreateSubmissionAnnouncementRequest(**body_dict)
```

### After (Direct Form Fields)
```python
async def create_submission_announcement(
    title: str = Form(..., description="Announcement title"),
    description: str = Form(..., description="Announcement description"),
    assignTo: str = Form(..., description="Target audience: Students, Supervisors, or Both"),
    dueDate: str = Form(..., description="Due date in ISO format"),
    total_marks: float = Form(..., description="Total marks"),
    uploaded_files: List[UploadFile] = File(None),
):
    # Direct usage - no parsing needed
```

## Benefits

✅ **Swagger UI shows all fields** - proper documentation
✅ **Type validation** - FastAPI validates each field automatically
✅ **Better error messages** - field-specific validation errors
✅ **Simpler frontend** - submit form fields directly, no JSON stringification
✅ **curl-friendly** - easier to test with curl/Postman

## API Changes

### Create Endpoint: `POST /api/admin/submission-tasks`

**Old Request**:
```bash
curl -X POST \
  -F 'body={"title":"SRS","description":"...","dueDate":"...","total_marks":100,"assignTo":"Students","files":[]}' \
  -F 'uploaded_files=@file.pdf'
```

**New Request**:
```bash
curl -X POST \
  -F 'title=SRS Submission' \
  -F 'description=Submit SRS document' \
  -F 'dueDate=2026-02-12T00:00:00Z' \
  -F 'total_marks=100' \
  -F 'assignTo=Students' \
  -F 'uploaded_files=@FYP_I_SRS_FYPilot.pdf'
```

### Edit Endpoint: `PATCH /api/admin/submission-tasks/{id}`

**Old Request**:
```bash
curl -X PATCH \
  -F 'body={"title":"Updated","files":[{"id":"uuid","name":"..."}]}' \
  -F 'uploaded_files=@new.pdf'
```

**New Request**:
```bash
curl -X PATCH \
  -F 'title=Updated Title' \
  -F 'description=Updated description' \
  -F 'keep_file_ids=uuid-456,uuid-789' \  # Files to keep
  -F 'uploaded_files=@new_file.pdf'
```

## Frontend Changes

### Create Form

**Old**:
```javascript
const formData = new FormData();
formData.append('body', JSON.stringify({
  title, description, dueDate, total_marks, assignTo, files: []
}));
formData.append('uploaded_files', file);
```

**New**:
```javascript
const formData = new FormData();
formData.append('title', title);
formData.append('description', description);
formData.append('dueDate', dueDate);
formData.append('total_marks', total_marks);
formData.append('assignTo', assignTo);
formData.append('uploaded_files', file);
```

### Edit Form - File Management

**Old**:
```javascript
// Send full file objects to keep
formData.append('body', JSON.stringify({
  ...fields,
  files: [{id, name, url, type, mimeType, size, module}, ...]
}));
```

**New**:
```javascript
// Just send comma-separated file IDs to keep
const keepIds = existingFiles.map(f => f.id).join(',');
formData.append('keep_file_ids', keepIds);  // Simple!
```

## File Deletion Logic

Files are deleted if they're **NOT in `keep_file_ids`**:

```javascript
// Keep file-456 and file-789, delete all others
formData.append('keep_file_ids', 'file-456,file-789');
```

Backend automatically:
1. Deletes removed files from Supabase Storage
2. Deletes removed file records from database
3. Keeps specified files intact

## Testing

### Test Create
```bash
curl -X 'POST' \
  'http://localhost:8000/api/admin/submission-tasks' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'title=SRS Submission' \
  -F 'description=Submit SRS document' \
  -F 'dueDate=2026-02-12T00:00:00Z' \
  -F 'total_marks=100' \
  -F 'assignTo=Students' \
  -F 'uploaded_files=@document.pdf'
```

### Test Edit
```bash
curl -X 'PATCH' \
  'http://localhost:8000/api/admin/submission-tasks/{announcement_id}' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'title=Updated SRS' \
  -F 'keep_file_ids=uuid-1,uuid-2' \
  -F 'uploaded_files=@new.pdf'
```

## Documentation Updated

- ✅ [SUPABASE_BUCKET_SETUP.md](SUPABASE_BUCKET_SETUP.md) - Bucket creation guide
- ✅ [FORM_FILE_UPLOAD_GUIDE.md](FORM_FILE_UPLOAD_GUIDE.md) - Updated with new API format
- ✅ [admin_submissions.py](app/api/http/admin_submissions.py) - Detailed docstrings

## Next Steps

1. **Create Supabase bucket** (see [SUPABASE_BUCKET_SETUP.md](SUPABASE_BUCKET_SETUP.md))
2. **Test endpoints** in Swagger UI at `http://localhost:8000/docs`
3. **Update frontend** to use new form field approach
4. **Verify file uploads/deletions** work correctly

## Summary

✅ Structured request body now visible in Swagger UI  
✅ Simpler frontend code (no JSON stringification)  
✅ Better error messages with field-level validation  
✅ Easier testing with curl/Postman  
✅ File management simplified with `keep_file_ids`  
✅ Complete documentation provided
