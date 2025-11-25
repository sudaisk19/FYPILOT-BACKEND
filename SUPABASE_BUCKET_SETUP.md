# Supabase Storage Bucket Setup

## Create the "announcement_files" Bucket

The application requires a Supabase Storage bucket named `announcement_files` to store announcement attachment files.

### Option 1: Via Supabase Dashboard (Recommended)

1. Go to your Supabase project dashboard
2. Navigate to **Storage** in the left sidebar
3. Click **New bucket**
4. Configure the bucket:
   - **Name**: `announcement_files`
   - **Public bucket**: ✅ Enable (for public access to files)
   - **Allowed MIME types**: Leave empty (allow all file types)
   - **File size limit**: 50 MB (or adjust as needed)
5. Click **Create bucket**

### Option 2: Via SQL

Run this SQL in your Supabase SQL Editor:

```sql
-- Create the announcement_files bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('announcement_files', 'announcement_files', true, 52428800, NULL);
```

**Note**: `52428800` = 50 MB in bytes

### Option 3: Via Supabase Python Client

```python
from supabase import create_client

supabase = create_client("YOUR_SUPABASE_URL", "YOUR_SUPABASE_KEY")

# Create bucket
supabase.storage.create_bucket(
    "announcement_files",
    options={
        "public": True,
        "fileSizeLimit": 52428800  # 50 MB
    }
)
```

## Folder Structure

The application organizes files into subfolders within the bucket:

```
announcement_files/
├── announcements/     # Admin announcement attachments
│   ├── <uuid1>.pdf
│   ├── <uuid2>.docx
│   └── ...
└── submissions/       # Student submission files (future use)
    ├── <uuid3>.pdf
    ├── <uuid4>.zip
    └── ...
```

## Bucket Policies (Required for File Upload)

⚠️ **IMPORTANT**: You must disable RLS or add policies to allow file uploads.

### Option 1: Disable RLS on Storage (Quick Setup)

Run this in your Supabase SQL Editor:

```sql
-- Disable RLS on storage.objects to allow uploads
ALTER TABLE storage.objects DISABLE ROW LEVEL SECURITY;
```

### Option 2: Add RLS Policies (Production Recommended)

If you want to keep RLS enabled, add these policies:

```sql
-- Enable RLS
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read files from announcement_files bucket
CREATE POLICY "Public Access to announcement_files"
ON storage.objects FOR SELECT
USING (bucket_id = 'announcement_files');

-- Allow authenticated users to upload to announcement_files bucket
CREATE POLICY "Authenticated users can upload to announcement_files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'announcement_files');

-- Allow users to update their own files
CREATE POLICY "Users can update announcement_files"
ON storage.objects FOR UPDATE
TO authenticated
USING (bucket_id = 'announcement_files');

-- Allow users to delete from announcement_files
CREATE POLICY "Users can delete from announcement_files"
ON storage.objects FOR DELETE
TO authenticated
USING (bucket_id = 'announcement_files');
```

### Option 3: Admin-Only Policies (Most Secure)

For production where only admins should manage files:

```sql
-- Enable RLS
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Public read access
CREATE POLICY "Public read access to announcement_files"
ON storage.objects FOR SELECT
USING (bucket_id = 'announcement_files');

-- Admin-only upload
CREATE POLICY "Admin upload to announcement_files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'announcement_files' AND
    (auth.jwt() -> 'user_metadata' ->> 'role' = 'admin' OR
     auth.jwt() ->> 'role' = 'admin')
);

-- Admin-only delete
CREATE POLICY "Admin delete from announcement_files"
ON storage.objects FOR DELETE
TO authenticated
USING (
    bucket_id = 'announcement_files' AND
    (auth.jwt() -> 'user_metadata' ->> 'role' = 'admin' OR
     auth.jwt() ->> 'role' = 'admin')
);
```

**Note**: Adjust the role check based on how you store roles in your JWT token.

## Verify Bucket Creation

After creating the bucket, verify it exists:

### Via Dashboard
- Go to **Storage** → You should see `announcement_files` in the bucket list

### Via API
```bash
curl https://YOUR_PROJECT.supabase.co/storage/v1/bucket/announcement_files \
  -H "Authorization: Bearer YOUR_SUPABASE_KEY"
```

### Via Python
```python
buckets = supabase.storage.list_buckets()
print([b['name'] for b in buckets])
# Should output: ['announcement_files']
```

## Common Issues

### "new row violates row-level security policy" Error
- **Cause**: RLS is blocking file uploads to storage.objects table
- **Solution**: 
  1. **Quick fix**: Disable RLS: `ALTER TABLE storage.objects DISABLE ROW LEVEL SECURITY;`
  2. **Production fix**: Add appropriate RLS policies (see "Bucket Policies" section above)

### "Bucket not found" Error
- **Cause**: The bucket hasn't been created yet
- **Solution**: Create the bucket using one of the methods above

### "Permission denied" Error
- **Cause**: RLS policies are blocking access
- **Solution**: 
  1. Make bucket public in dashboard
  2. Or add appropriate RLS policies (see above)

### "File size limit exceeded" Error
- **Cause**: File is larger than bucket limit
- **Solution**: 
  1. Increase bucket file size limit in dashboard
  2. Or adjust `MAX_FILE_SIZE` in [file_service.py](app/services/file_service.py#L16)

## Configuration

The bucket name is configured in [app/services/file_service.py](app/services/file_service.py):

```python
class FileService:
    BUCKET_NAME = "announcement_files"  # Supabase bucket name
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
```

If you want to use a different bucket name, update `BUCKET_NAME` in the FileService class.
