# File Upload/Download Workflow Explained

## How the Upload Endpoints Work with Create/Edit

### The Two-Step Upload Process

#### Step 1: Upload Files First (Separate Endpoint)
**POST** `/api/admin/files/upload`

- Frontend uploads files using multipart/form-data
- Backend saves files to Supabase Storage
- Returns file metadata (storage_key, name, size, mime_type, etc.)

```javascript
const formData = new FormData();
formData.append('files', file1);
formData.append('files', file2);

const response = await fetch('/api/admin/files/upload', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData
});

const { files } = await response.json();
// files = [
//   { name: "template.pdf", url: "announcements/uuid-123.pdf", mimeType: "application/pdf", size: 1024000, type: "Document" },
//   { name: "guide.docx", url: "announcements/uuid-456.docx", mimeType: "application/vnd...", size: 512000, type: "Document" }
// ]
```

#### Step 2: Create/Edit Announcement with File Metadata
**POST** `/api/admin/submission-tasks` or **PATCH** `/api/admin/submission-tasks/{id}`

- Frontend sends announcement data + file metadata from Step 1
- Backend creates database records linking files to announcement
- NO file upload happens here - just metadata reference

```javascript
await fetch('/api/admin/submission-tasks', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    title: "Final Project Submission",
    description: "Submit your final project",
    dueDate: "2026-03-01T23:59:59Z",
    total_marks: 100,
    assignTo: "Students",
    files: files  // Use the metadata from Step 1
  })
});
```

---

## Why Separate Upload Endpoint?

### Advantages:

1. **Better UX** - Upload files immediately, show progress, user gets instant feedback
2. **Validation** - Validate files (size, type) before form submission
3. **Draft Support** - User can upload files, leave page, come back later
4. **Error Handling** - Handle upload errors separately from form errors
5. **Resume/Retry** - Can retry failed uploads without resubmitting entire form
6. **Performance** - Parallel uploads, form submission is fast (just JSON)

### What Happens in Each Endpoint:

| Endpoint | Stores File in Supabase? | Creates DB Record? | Use Case |
|----------|--------------------------|-------------------|----------|
| `POST /files/upload` | ✅ Yes | ❌ No | Upload physical files |
| `POST /submission-tasks` | ❌ No | ✅ Yes | Link metadata to announcement |
| `PATCH /submission-tasks/{id}` | ❌ No | ✅ Update/Delete | Modify announcement + file links |

---

## File Deletion Workflow

### When Files Are Removed from Announcement

The **PATCH** `/api/admin/submission-tasks/{id}` endpoint handles file deletion:

```javascript
// User had 3 files, removes file #2, edits announcement
await fetch(`/api/admin/submission-tasks/${announcementId}`, {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    files: [
      { id: "file-uuid-1", name: "template.pdf", ... },  // Keep
      // file #2 removed
      { id: "file-uuid-3", name: "guide.docx", ... }      // Keep
    ]
  })
});
```

**Backend Process:**

1. Compares new file list with existing files
2. Identifies files to delete (file #2 in this case)
3. **Deletes from Supabase Storage** (physical file)
4. **Deletes from database** (metadata record)
5. Keeps/updates remaining files

**Code in Edit Endpoint:**

```python
# Delete files that are no longer in the list
for existing_file in list(announcement.files):
    if existing_file.file_id not in keep_ids:
        # Delete from Supabase Storage (physical file)
        try:
            await FileService.delete_file(existing_file.storage_key)
        except Exception as e:
            print(f"Warning: Could not delete file from storage: {e}")
        # Delete from database (metadata)
        await db.delete(existing_file)
```

---

## Complete Frontend Flow Examples

### Creating Announcement with Files

```javascript
// Component state
const [selectedFiles, setSelectedFiles] = useState([]);
const [uploadedFiles, setUploadedFiles] = useState([]);
const [uploading, setUploading] = useState(false);

// Step 1: User selects files
const handleFileSelect = (e) => {
  setSelectedFiles(Array.from(e.target.files));
};

// Step 2: Upload files immediately
const handleFileUpload = async () => {
  setUploading(true);
  
  const formData = new FormData();
  selectedFiles.forEach(file => formData.append('files', file));
  
  try {
    const response = await fetch('/api/admin/files/upload', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });
    
    const { files } = await response.json();
    setUploadedFiles(files);
    setSelectedFiles([]);
  } catch (error) {
    alert('Upload failed: ' + error.message);
  } finally {
    setUploading(false);
  }
};

// Step 3: Submit announcement with file metadata
const handleSubmit = async (formData) => {
  await fetch('/api/admin/submission-tasks', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ...formData,
      files: uploadedFiles  // Just metadata, not actual files
    })
  });
};
```

### Editing Announcement and Removing Files

```javascript
// Load existing announcement
const announcement = await fetch(`/api/admin/submission-tasks/${id}`).then(r => r.json());

// User removes file from UI
const handleRemoveFile = (fileId) => {
  setUploadedFiles(prev => prev.filter(f => f.id !== fileId));
};

// Save changes
const handleUpdate = async () => {
  await fetch(`/api/admin/submission-tasks/${id}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      files: uploadedFiles  // Only remaining files
    })
  });
  
  // Backend automatically deletes removed files from storage + database
};
```

### Adding More Files to Existing Announcement

```javascript
// User uploads new files
const newFiles = await uploadNewFiles(); // Calls POST /files/upload

// Combine with existing files
const allFiles = [
  ...announcement.files.map(f => ({ id: f.id, ...otherProps })), // Keep existing
  ...newFiles  // Add new (no id yet)
];

// Update announcement
await fetch(`/api/admin/submission-tasks/${id}`, {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    files: allFiles
  })
});
```

---

## File Download/Viewing

### Viewing Files Inline (PDF, Images)

```html
<!-- Announcement file -->
<iframe 
  src={`/api/admin/files/${file.id}/download`}
  style={{ width: '100%', height: '600px' }}
/>

<!-- Submission file -->
<iframe 
  src={`/api/admin/submissions/${submissionId}/files/${file.id}/download`}
  style={{ width: '100%', height: '600px' }}
/>
```

### Downloading Files

```javascript
const downloadFile = async (fileId, fileName) => {
  const response = await fetch(`/api/admin/files/${fileId}/download`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.click();
  window.URL.revokeObjectURL(url);
};
```

---

## Summary

### File Upload Flow:
1. ✅ **Upload** → `POST /files/upload` → Get metadata
2. ✅ **Create** → `POST /submission-tasks` → Link metadata to announcement
3. ✅ **Edit** → `PATCH /submission-tasks/{id}` → Update file links
4. ✅ **Delete** → Handled in edit → Removes from storage + DB
5. ✅ **Download** → `GET /files/{id}/download` → Stream file

### Key Points:
- **Physical files** stored in Supabase Storage once
- **Metadata** stored in database and linked to announcements
- **Deletion** removes both physical file and database record
- **No duplicates** - single upload endpoint, single download endpoint
- **Clean separation** - upload physical files separately from business logic
