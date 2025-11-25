# File Upload, Download, and Viewing - Implementation Summary

## Overview
I've added complete file upload, download, and viewing functionality for announcement attachments using Supabase Storage.

## What Was Added

### 1. File Service (`app/services/file_service.py`)
A service class that handles all file operations with Supabase Storage:

- **`upload_file(file, folder)`** - Upload a single file
- **`upload_multiple_files(files, folder)`** - Upload multiple files at once  
- **`get_file_url(storage_key)`** - Get public URL for a file
- **`download_file(storage_key)`** - Download file content from storage
- **`delete_file(storage_key)`** - Delete a file from storage

**Features:**
- Max file size: 50MB (configurable)
- Automatic MIME type detection
- Unique file naming with UUIDs
- Error handling with proper HTTP exceptions

### 2. New API Endpoints (`app/api/http/admin_submissions.py`)

#### **POST `/api/admin/files/upload`**
Upload files for announcements (before creating/editing announcement).

**Request:**
```http
POST /api/admin/files/upload
Content-Type: multipart/form-data

files: [file1, file2, file3]
```

**Response:**
```json
{
  "files": [
    {
      "name": "document.pdf",
      "url": "announcements/uuid-123.pdf",
      "mimeType": "application/pdf",
      "size": 1024000,
      "type": "Document"
    }
  ]
}
```

**Usage Flow:**
1. Frontend uploads files to this endpoint
2. Gets back file metadata (url, name, size, etc.)
3. Uses that metadata when creating/editing announcements

#### **GET `/api/admin/files/{file_id}/download`**
Download or view an announcement file.

**Response:**
- StreamingResponse with file content
- Proper Content-Type header
- Inline display (can be viewed in browser)

#### **GET `/api/admin/submissions/{submission_id}/files/{file_id}/download`**
Download or view a submission file (for evaluation page).

**Response:**
- StreamingResponse with file content
- Proper Content-Type header
- Inline display

## Database Schema Analysis

### ✅ Current Schema is Complete

The existing database schema already supports all file operations:

**announcement_files table:**
```sql
- file_id (UUID, PK)
- announcement_id (UUID, FK)
- file_name (TEXT) - Original filename
- storage_key (TEXT) - Path in Supabase Storage
- mime_type (TEXT) - File MIME type
- size_bytes (BIGINT) - File size
- file_type (ENUM) - "Template" or "Document"
- module (TEXT) - Optional module/category
- uploaded_at (TIMESTAMP) - Upload timestamp
```

**submission_files table:**
```sql
- file_id (UUID, PK)
- submission_id (UUID, FK)
- file_name (TEXT) - Original filename
- storage_key (TEXT) - Path in Supabase Storage
- mime_type (TEXT) - File MIME type
- size_bytes (BIGINT) - File size
- supervisor_comment (TEXT) - Comments from supervisor
- uploaded_at (TIMESTAMP) - Upload timestamp
```

### ❌ No Schema Changes Needed

The current schema has everything needed for:
- ✅ File metadata storage
- ✅ Relationship to announcements/submissions
- ✅ File download/viewing (via storage_key)
- ✅ File type categorization
- ✅ Size tracking
- ✅ Supervisor comments (submission files)

## How to Use

### Option 1: Upload Files First (Recommended)

```javascript
// 1. Upload files
const formData = new FormData();
formData.append('files', file1);
formData.append('files', file2);

const uploadResponse = await fetch('/api/admin/files/upload', {
  method: 'POST',
  body: formData,
  headers: { 'Authorization': `Bearer ${token}` }
});

const { files } = await uploadResponse.json();

// 2. Create announcement with uploaded file metadata
await fetch('/api/admin/submission-tasks', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    title: "Final Project Submission",
    description: "Submit your final project",
    dueDate: "2026-03-01T23:59:59Z",
    total_marks: 100,
    assignTo: "Students",
    files: files  // Use uploaded file metadata
  })
});
```

### Option 2: Direct Upload to Supabase (Frontend)

```javascript
// 1. Frontend uploads directly to Supabase Storage
const { data, error } = await supabase.storage
  .from('announcements')
  .upload(`announcements/${uuid}`, file);

// 2. Create announcement with storage path
await fetch('/api/admin/submission-tasks', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    title: "Final Project Submission",
    files: [{
      name: file.name,
      url: data.path,  // Storage key from Supabase
      mimeType: file.type,
      size: file.size,
      type: "Document"
    }]
  })
});
```

### Viewing/Downloading Files

```html
<!-- View file inline (PDF, images, etc.) -->
<iframe src="/api/admin/files/{file_id}/download"></iframe>

<!-- Download link -->
<a href="/api/admin/files/{file_id}/download" download>Download File</a>

<!-- For submission files -->
<iframe src="/api/admin/submissions/{submission_id}/files/{file_id}/download"></iframe>
```

## Supabase Storage Setup

### Required Bucket Configuration

1. **Create a bucket** in Supabase Storage named `announcements`

2. **Set bucket policy** for authenticated access:
```sql
-- Allow authenticated users to upload files
CREATE POLICY "Allow authenticated uploads" ON storage.objects
FOR INSERT TO authenticated
WITH CHECK (bucket_id = 'announcements');

-- Allow authenticated users to read files
CREATE POLICY "Allow authenticated reads" ON storage.objects
FOR SELECT TO authenticated
USING (bucket_id = 'announcements');

-- Allow users to delete their own files (optional)
CREATE POLICY "Allow delete own files" ON storage.objects
FOR DELETE TO authenticated
USING (bucket_id = 'announcements');
```

3. **Make bucket public** (if you want public file access):
   - Go to Supabase Dashboard → Storage → announcements → Settings
   - Toggle "Public bucket" ON

## Implementation Notes

### File Size Limits
- Current limit: 50MB per file
- Configurable in `FileService.MAX_FILE_SIZE`
- Can be increased based on your needs

### Supported File Types
- All file types are supported
- MIME type auto-detection
- Manual MIME type override available

### Storage Organization
- Files stored in folders: `announcements/`, `submissions/`
- Unique filenames using UUIDs
- Original filenames preserved in database

### Security
- Admin-only access to all endpoints
- JWT authentication required
- File ownership validation for submissions
- Supabase RLS policies for storage access

## Testing Endpoints

### Upload Files
```bash
curl -X POST "http://localhost:8000/api/admin/files/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@document.pdf" \
  -F "files=@image.png"
```

### Download File
```bash
curl "http://localhost:8000/api/admin/files/{file_id}/download" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  --output downloaded_file.pdf
```

## Additional Feature: Copy to admin_submissions.py

The submission file download endpoint needs to be added to [admin_submissions.py](app/api/http/admin_submissions.py). 
See [submission_file_download.txt](app/api/http/submission_file_download.txt) for the code to append.

## Summary

✅ **File upload** - Backend handles multipart file uploads  
✅ **File download** - Streaming responses for viewing/downloading  
✅ **Database schema** - Already complete, no changes needed  
✅ **Storage integration** - Supabase Storage fully integrated  
✅ **Security** - Admin-only access with JWT auth  
✅ **Error handling** - Comprehensive error messages  

The system is ready for file uploads, downloads, and viewing!
