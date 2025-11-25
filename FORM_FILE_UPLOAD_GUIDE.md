# Single Form Submission - Upload and Remove Files

## How It Works

The create and edit endpoints now support **direct file uploads** in the same form submission, eliminating the need for a separate upload step.

## Frontend Implementation

### Creating Announcement with Files

```javascript
// Form component with file upload
const CreateAnnouncementForm = () => {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    dueDate: '2026-02-12T00:00:00Z',
    total_marks: 100,
    assignTo: 'Students',
  });
  const [newFiles, setNewFiles] = useState([]); // Files to upload

  const handleFileSelect = (e) => {
    setNewFiles(Array.from(e.target.files));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Create FormData for multipart submission
    const formDataObj = new FormData();
    
    // Add form fields directly (NOT as JSON)
    formDataObj.append('title', formData.title);
    formDataObj.append('description', formData.description);
    formDataObj.append('dueDate', formData.dueDate);
    formDataObj.append('total_marks', formData.total_marks);
    formDataObj.append('assignTo', formData.assignTo);

    // Add files
    newFiles.forEach(file => {
      formDataObj.append('uploaded_files', file);
    });

    // Submit
    const response = await fetch('/api/admin/submission-tasks', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
        // DON'T set Content-Type - let browser set it with boundary
      },
      body: formDataObj
    });

    const result = await response.json();
    console.log('Created:', result);
  };

  return (
    <form onSubmit={handleSubmit}>
      <input 
        type="text" 
        value={formData.title}
        onChange={(e) => setFormData({...formData, title: e.target.value})}
        placeholder="Title"
        required
      />
      
      <textarea 
        value={formData.description}
        onChange={(e) => setFormData({...formData, description: e.target.value})}
        placeholder="Description"
        required
      />

      <input 
        type="datetime-local" 
        value={formData.dueDate.slice(0, 16)}
        onChange={(e) => setFormData({...formData, dueDate: e.target.value + ':00Z'})}
        required
      />
      
      <input 
        type="number" 
        value={formData.total_marks}
        onChange={(e) => setFormData({...formData, total_marks: +e.target.value})}
        placeholder="Total Marks"
        required
      />

      <select 
        value={formData.assignTo}
        onChange={(e) => setFormData({...formData, assignTo: e.target.value})}
        required
      >
        <option value="Students">Students</option>
        <option value="Supervisors">Supervisors</option>
        <option value="Both">Both</option>
      </select>

      <input 
        type="file" 
        multiple 
        onChange={handleFileSelect}
      />

      {newFiles.length > 0 && (
        <ul>
          {newFiles.map((file, idx) => (
            <li key={idx}>{file.name} ({(file.size / 1024).toFixed(1)} KB)</li>
          ))}
        </ul>
      )}

      <button type="submit">Create Announcement</button>
    </form>
  );
};
```

### Editing Announcement - Upload New Files & Remove Existing

```javascript
const EditAnnouncementForm = ({ announcementId }) => {
  const [formData, setFormData] = useState(null);
  const [existingFiles, setExistingFiles] = useState([]); // Files already in DB
  const [newFiles, setNewFiles] = useState([]); // New files to upload

  // Load existing announcement
  useEffect(() => {
    fetch(`/api/admin/submission-tasks/${announcementId}`)
      .then(r => r.json())
      .then(data => {
        setFormData({
          title: data.title,
          description: data.description,
          dueDate: data.dueDate,
          total_marks: data.total_marks,
          assignTo: data.assignTo,
        });
        setExistingFiles(data.files); // Keep track of existing files
      });
  }, [announcementId]);

  const handleRemoveExistingFile = (fileId) => {
    // Remove from the list - backend will delete it
    setExistingFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const handleAddNewFiles = (e) => {
    setNewFiles(Array.from(e.target.files));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const formDataObj = new FormData();
    
    // Add form fields directly
    formDataObj.append('title', formData.title);
    formDataObj.append('description', formData.description);
    formDataObj.append('dueDate', formData.dueDate);
    formDataObj.append('total_marks', formData.total_marks);
    formDataObj.append('assignTo', formData.assignTo);

    // Add comma-separated list of file IDs to keep
    const keepFileIds = existingFiles.map(f => f.id).join(',');
    if (keepFileIds) {
      formDataObj.append('keep_file_ids', keepFileIds);
    }

    // Add new files to upload
    newFiles.forEach(file => {
      formDataObj.append('uploaded_files', file);
    });

    // Submit
    const response = await fetch(`/api/admin/submission-tasks/${announcementId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formDataObj
    });

    const result = await response.json();
    console.log('Updated:', result);
  };

  if (!formData) return <div>Loading...</div>;

  return (
    <form onSubmit={handleSubmit}>
      <input 
        type="text" 
        value={formData.title}
        onChange={(e) => setFormData({...formData, title: e.target.value})}
      />

      <textarea 
        value={formData.description}
        onChange={(e) => setFormData({...formData, description: e.target.value})}
      />

      <h3>Existing Files</h3>
      {existingFiles.map(file => (
        <div key={file.id}>
          <span>{file.name}</span>
          <button 
            type="button"
            onClick={() => handleRemoveExistingFile(file.id)}
          >
            Remove
          </button>
        </div>
      ))}

      <h3>Add New Files</h3>
      <input 
        type="file" 
        multiple 
        onChange={handleAddNewFiles}
      />

      {newFiles.length > 0 && (
        <ul>
          {newFiles.map((file, idx) => (
            <li key={idx}>{file.name}</li>
          ))}
        </ul>
      )}

      <button type="submit">Save Changes</button>
    </form>
  );
};
```

## Backend Processing Flow

### Create Endpoint Flow:
1. ✅ Receive form fields (title, description, etc.) + uploaded files
2. ✅ Parse and validate form data
3. ✅ Create announcement record
4. ✅ Upload new files to Supabase Storage
5. ✅ Create file records in database
6. ✅ Return complete announcement with all files

### Edit Endpoint Flow:
1. ✅ Receive updated form fields + keep_file_ids + new uploaded files
2. ✅ Parse and validate form data
3. ✅ Update announcement fields
4. ✅ Compare `keep_file_ids` with existing files
5. ✅ **Delete removed files** from storage and database
6. ✅ **Upload new files** to Supabase Storage
7. ✅ Create new file records
8. ✅ Return updated announcement

## File Removal Logic

When editing, files are removed if they're **not in the `keep_file_ids` parameter**:

```javascript
// Example: Remove file with id "uuid-123"
const formData = new FormData();
formData.append('title', 'Updated Title');
formData.append('keep_file_ids', 'uuid-456,uuid-789'); // Keep these two
// uuid-123 is NOT in the list = will be deleted

await fetch(`/api/admin/submission-tasks/${announcementId}`, {
  method: 'PATCH',
  body: formData
});
```

Backend automatically:
1. Deletes `uuid-123` from Supabase Storage
2. Deletes `uuid-123` from database
3. Keeps `uuid-456` and `uuid-789`

## Complete Example Component

```javascript
const AnnouncementForm = ({ announcementId = null }) => {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    dueDate: '2026-02-12T00:00:00Z',
    total_marks: 100,
    assignTo: 'Students',
  });
  const [existingFiles, setExistingFiles] = useState([]);
  const [newFiles, setNewFiles] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load existing if editing
  useEffect(() => {
    if (announcementId) {
      fetch(`/api/admin/submission-tasks/${announcementId}`)
        .then(r => r.json())
        .then(data => {
          setFormData({
            title: data.title,
            description: data.description,
            dueDate: data.dueDate,
            total_marks: data.total_marks,
            assignTo: data.assignTo,
          });
          setExistingFiles(data.files || []);
        });
    }
  }, [announcementId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const formDataObj = new FormData();
      
      // Add form fields
      formDataObj.append('title', formData.title);
      formDataObj.append('description', formData.description);
      formDataObj.append('dueDate', formData.dueDate);
      formDataObj.append('total_marks', formData.total_marks);
      formDataObj.append('assignTo', formData.assignTo);

      // For edit: add files to keep
      if (announcementId) {
        const keepFileIds = existingFiles.map(f => f.id).join(',');
        if (keepFileIds) {
          formDataObj.append('keep_file_ids', keepFileIds);
        }
      }

      // Add new files
      newFiles.forEach(file => {
        formDataObj.append('uploaded_files', file);
      });

      const url = announcementId 
        ? `/api/admin/submission-tasks/${announcementId}`
        : '/api/admin/submission-tasks';
      
      const method = announcementId ? 'PATCH' : 'POST';

      const response = await fetch(url, {
        method,
        headers: { 'Authorization': `Bearer ${token}` },
        body: formDataObj
      });

      const result = await response.json();
      alert(announcementId ? 'Updated!' : 'Created!');
      // Redirect or update UI
    } catch (error) {
      alert('Error: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>{announcementId ? 'Edit' : 'Create'} Announcement</h2>
      
      {/* Form fields */}
      <input 
        value={formData.title}
        onChange={(e) => setFormData({...formData, title: e.target.value})}
        placeholder="Title"
        required
      />

      <textarea 
        value={formData.description}
        onChange={(e) => setFormData({...formData, description: e.target.value})}
        placeholder="Description"
        required
      />

      <input 
        type="datetime-local" 
        value={formData.dueDate.slice(0, 16)}
        onChange={(e) => setFormData({...formData, dueDate: e.target.value + ':00Z'})}
        required
      />

      <input 
        type="number" 
        value={formData.total_marks}
        onChange={(e) => setFormData({...formData, total_marks: +e.target.value})}
        required
      />

      <select 
        value={formData.assignTo}
        onChange={(e) => setFormData({...formData, assignTo: e.target.value})}
        required
      >
        <option value="Students">Students</option>
        <option value="Supervisors">Supervisors</option>
        <option value="Both">Both</option>
      </select>

      {/* Existing files */}
      {existingFiles.length > 0 && (
        <div>
          <h3>Current Files</h3>
          {existingFiles.map(file => (
            <div key={file.id}>
              <span>{file.name}</span>
              <button 
                type="button"
                onClick={() => setExistingFiles(prev => prev.filter(f => f.id !== file.id))}
              >
                ✕ Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* New files */}
      <div>
        <h3>Add Files</h3>
        <input 
          type="file" 
          multiple 
          onChange={(e) => setNewFiles(Array.from(e.target.files))}
        />
        {newFiles.length > 0 && (
          <ul>
            {newFiles.map((file, idx) => (
              <li key={idx}>
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </li>
            ))}
          </ul>
        )}
      </div>

      <button type="submit" disabled={loading}>
        {loading ? 'Saving...' : (announcementId ? 'Save Changes' : 'Create')}
      </button>
    </form>
  );
};
```

## Summary

✅ **Create**: Direct form submission with individual fields + file uploads  
✅ **Edit**: Update fields, specify files to keep via `keep_file_ids`, add new files  
✅ **Remove**: Exclude file IDs from `keep_file_ids` → auto-deleted  
✅ **Swagger UI**: Shows structured request body with all form fields  
✅ **Simple**: No JSON parsing needed - submit form fields directly  

## Curl Example

### Create Announcement
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

### Edit Announcement
```bash
curl -X 'PATCH' \
  'http://localhost:8000/api/admin/submission-tasks/{announcement_id}' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'title=Updated SRS Submission' \
  -F 'description=Updated description' \
  -F 'keep_file_ids=uuid-456,uuid-789' \
  -F 'uploaded_files=@new_file.pdf'
```
