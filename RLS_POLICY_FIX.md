# Quick Fix: RLS Policy Error

## Error
```
Failed to upload file: {'statusCode': 403, 'error': Unauthorized, 'message': new row violates row-level security policy}
```

## Cause
Supabase Storage has Row-Level Security (RLS) enabled on the `storage.objects` table, blocking file uploads.

## Quick Solution (Development)

Run this SQL in your **Supabase SQL Editor**:

```sql
-- Disable RLS on storage.objects to allow uploads
ALTER TABLE storage.objects DISABLE ROW LEVEL SECURITY;
```

✅ This immediately allows file uploads from your backend.

## Production Solution (Recommended)

For production, keep RLS enabled and add proper policies:

```sql
-- Enable RLS
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read files
CREATE POLICY "Public read announcement_files"
ON storage.objects FOR SELECT
USING (bucket_id = 'announcement_files');

-- Allow authenticated users to upload
CREATE POLICY "Authenticated upload announcement_files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'announcement_files');

-- Allow authenticated users to delete
CREATE POLICY "Authenticated delete announcement_files"
ON storage.objects FOR DELETE
TO authenticated
USING (bucket_id = 'announcement_files');
```

## Verify Fix

After applying the SQL, retry your curl command:

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/admin/submission-tasks' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'title=Test Submission' \
  -F 'assignTo=Students' \
  -F 'uploaded_files=@document.docx'
```

## Changes Made to API

### Required Fields (Updated)
- ✅ **title** - Required
- ✅ **assignTo** - Required
- ❌ description - Optional
- ❌ dueDate - Optional  
- ❌ total_marks - Optional
- ❌ uploaded_files - Optional

### Minimal Request Example

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/admin/submission-tasks' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'title=SRS Submission' \
  -F 'assignTo=Students'
```

### Full Request Example

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/admin/submission-tasks' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'title=SRS Submission' \
  -F 'assignTo=Students' \
  -F 'description=Submit SRS document' \
  -F 'dueDate=2026-02-14T23:59:59Z' \
  -F 'total_marks=100' \
  -F 'uploaded_files=@template.pdf'
```

## Summary

1. **Run SQL** to disable RLS (dev) or add policies (prod)
2. **Required fields** now only `title` and `assignTo`
3. **Retry** your request - should work now!
