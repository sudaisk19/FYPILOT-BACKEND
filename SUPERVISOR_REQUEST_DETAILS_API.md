# Supervisor Request Details API Guide

## Overview

This API endpoint allows supervisors to view comprehensive group information when they receive a request from a student group. It provides all the details needed for supervisors to make an informed decision about accepting or rejecting the request.

## Endpoint

```
GET /api/invites/supervisor/{request_id}/details
```

**Authentication**: Required (Bearer token)  
**Authorization**: Only supervisors can access, and only for requests sent to them

## Request

**Path Parameters:**
- `request_id` (UUID): The ID of the request to view details for

**Headers:**
```
Authorization: Bearer <token>
```

## Response Structure

The response includes:

1. **Request Information**
   - Request ID, Group ID, Supervisor ID
   - Status (pending, accepted, rejected)
   - Message from students
   - Created and expiration dates

2. **Project Information**
   - Project name, description, objectives
   - Tech stack
   - Project type (research/product/both)
   - GitHub repositories
   - Associated domains

3. **Student Information**
   - For each group member:
     - Personal info (name, roll number, department, CGPA)
     - Skills and skill levels
     - Interests
     - Experience
     - Portfolio projects

## Example Response

```json
{
  "request_id": "req-1a23bc",
  "group_id": "grp-101",
  "supervisor_id": "sup-001",
  "status": "pending",
  "message": "We would love your guidance on this AI-based project.",
  "created_at": "2025-10-05T10:00:00Z",
  "expires_at": "2025-10-12T10:00:00Z",
  "project_brief": "A comprehensive platform for real-time feedback...",
  "project": {
    "name": "FYPilot: AI-Powered FYP Assistant",
    "description": "A platform for real-time feedback...",
    "objectives": [
      "Enable students to get instant proposal feedback",
      "Reduce supervisor load through AI suggestions"
    ],
    "tech_stack": ["Next.js", "FastAPI", "PostgreSQL"],
    "project_type": "Product",
    "github_repositories": [
      "https://github.com/fypilot/frontend",
      "https://github.com/fypilot/backend"
    ],
    "domains": [
      {"name": "Artificial Intelligence"},
      {"name": "Natural Language Processing"}
    ]
  },
  "students": [
    {
      "user_id": "stu-201",
      "name": "Azka Sahar",
      "roll_number": "CS-21-045",
      "department": "Computer Science",
      "cgpa": 3.82,
      "skills": ["React", "Next.js", "Python", "FastAPI"],
      "skills_levels": {
        "React": 3,
        "Next.js": 3,
        "Python": 3,
        "FastAPI": 3
      },
      "interests": ["AI", "Full Stack Development"],
      "experience": "Frontend Developer Intern at Techverse",
      "portfolio_projects": [
        {
          "title": "AI Chat Assistant",
          "link": "https://github.com/azka/ai-chat"
        }
      ]
    }
  ]
}
```

## Data Build-Up Explanation

### Step 1: Fetch Request
```python
# Query: Get the request and verify it belongs to the supervisor
SELECT * FROM requests 
WHERE request_id = :request_id 
  AND supervisor_id = :current_user_id
```

**What we get:**
- Request metadata (ID, group_id, supervisor_id, status, message)
- Timestamps (created_at, updated_at)

**Security Check:**
- Ensures the supervisor can only view requests sent to them
- Returns 404 if request doesn't exist or doesn't belong to them

### Step 2: Calculate Expiration
```python
expires_at = created_at + timedelta(days=7)
```

**Logic:**
- Requests expire 7 days after creation
- This is calculated dynamically (not stored in database)

### Step 3: Fetch Group Information
```python
# Query: Get basic group info
SELECT * FROM groups WHERE group_id = :group_id
```

**What we get:**
- Group name, stage, cycle, cohort year
- Used for validation (ensure group exists)

### Step 4: Fetch Project Information

**Main Query:**
```python
# Query: Get project details
SELECT * FROM projects WHERE group_id = :group_id
```

**What we get:**
- Project name, description
- Objectives (JSONB array)
- Tech stack (JSONB array)
- Project type (enum: research/product/both)
- Repository links (JSONB array)

**Domains Query:**
```python
# Query: Get project domains through join table
SELECT d.name 
FROM domains d
JOIN project_domains pd ON d.domain_id = pd.domain_id
WHERE pd.project_id = :project_id
```

**What we get:**
- List of domain names associated with the project

**Data Transformation:**
- JSONB fields (objectives, tech_stack, repo_links) are parsed as lists
- Project type enum is converted to string
- Domains are mapped to `ProjectDomainInfo` objects

### Step 5: Fetch Student Information

**Main Query:**
```python
# Query: Get all group members with their student and user details
SELECT gm.*, u.*, s.*
FROM group_members gm
JOIN users u ON u.user_id = gm.student_id
JOIN students s ON s.user_id = u.user_id
WHERE gm.group_id = :group_id
ORDER BY gm.joined_at ASC
```

**What we get (per student):**
- User info: user_id, full_name, email, profile_avatar
- Student info: roll_number, department, cgpa, skills, interests, experience, portfolio_projects

**Data Transformation:**

1. **Skills Array:**
   ```python
   skills = student.skills or []  # Direct array from database
   ```

2. **Skills Levels:**
   ```python
   # Note: skills_levels is not stored in database
   # Currently returns default level 3 for each skill
   # You may need to add a skills_levels JSONB field to students table
   skills_levels = {skill: 3 for skill in student.skills}
   ```

3. **Portfolio Projects:**
   ```python
   # Parse JSONB portfolio_projects field
   if student.portfolio_projects and isinstance(student.portfolio_projects, list):
       for proj in student.portfolio_projects:
           if isinstance(proj, dict):
               portfolio_projects.append(
                   PortfolioProject(
                       title=proj.get("title", ""),
                       link=proj.get("link", "")
                   )
               )
   ```

4. **CGPA:**
   ```python
   cgpa = float(student.cgpa) if student.cgpa else None
   ```

## Complete SQL Query Breakdown

If you were to write this as a single SQL query, it would look like:

```sql
-- Main query structure (conceptual - actual implementation uses multiple queries)
WITH request_data AS (
    SELECT 
        r.request_id,
        r.group_id,
        r.supervisor_id,
        r.status,
        r.message,
        r.created_at,
        r.created_at + INTERVAL '7 days' AS expires_at
    FROM requests r
    WHERE r.request_id = :request_id
      AND r.supervisor_id = :supervisor_id
),
project_data AS (
    SELECT 
        p.project_id,
        p.name,
        p.description,
        p.objectives,
        p.tech_stack,
        p.project_type,
        p.repo_links,
        ARRAY_AGG(d.name) AS domains
    FROM projects p
    LEFT JOIN project_domains pd ON p.project_id = pd.project_id
    LEFT JOIN domains d ON pd.domain_id = d.domain_id
    WHERE p.group_id = (SELECT group_id FROM request_data)
    GROUP BY p.project_id, p.name, p.description, p.objectives, 
             p.tech_stack, p.project_type, p.repo_links
),
student_data AS (
    SELECT 
        u.user_id,
        u.full_name AS name,
        s.roll_number,
        s.department,
        s.cgpa,
        s.skills,
        s.interests,
        s.experience,
        s.portfolio_projects
    FROM group_members gm
    JOIN users u ON u.user_id = gm.student_id
    JOIN students s ON s.user_id = u.user_id
    WHERE gm.group_id = (SELECT group_id FROM request_data)
)
SELECT 
    rd.*,
    pd.*,
    json_agg(json_build_object(
        'user_id', sd.user_id,
        'name', sd.name,
        'roll_number', sd.roll_number,
        'department', sd.department,
        'cgpa', sd.cgpa,
        'skills', sd.skills,
        'interests', sd.interests,
        'experience', sd.experience,
        'portfolio_projects', sd.portfolio_projects
    )) AS students
FROM request_data rd
LEFT JOIN project_data pd ON pd.group_id = rd.group_id
LEFT JOIN student_data sd ON true
GROUP BY rd.request_id, rd.group_id, ...
```

## Important Notes

### Skills Levels
The `skills_levels` field is currently not stored in the database. The implementation returns a default level of 3 for each skill. 

**To add real skill levels, you would need to:**

1. **Option 1: Add JSONB field to students table**
   ```sql
   ALTER TABLE students 
   ADD COLUMN skills_levels JSONB DEFAULT '{}'::jsonb;
   ```

2. **Option 2: Create separate skills_levels table**
   ```sql
   CREATE TABLE student_skills (
       student_id UUID REFERENCES students(user_id),
       skill_name TEXT,
       level INTEGER CHECK (level >= 1 AND level <= 5),
       PRIMARY KEY (student_id, skill_name)
   );
   ```

### Portfolio Projects Structure
The `portfolio_projects` field in the `students` table is a JSONB field. Expected structure:

```json
[
  {
    "title": "Project Name",
    "link": "https://github.com/user/project"
  },
  {
    "title": "Another Project",
    "link": "https://github.com/user/another"
  }
]
```

### Expiration Date
The `expires_at` is calculated as 7 days from `created_at`. This is not stored in the database but calculated on-the-fly. If you want to store it, you could:

1. Add `expires_at` column to `requests` table
2. Set it when creating the request: `expires_at = created_at + timedelta(days=7)`

## Error Handling

- **403 Forbidden**: User is not a supervisor
- **404 Not Found**: Request doesn't exist or doesn't belong to the supervisor
- **404 Not Found**: Group not found (shouldn't happen if request exists)

## Frontend Integration

```typescript
const getRequestDetails = async (requestId: string) => {
  const response = await fetch(
    `/api/invites/supervisor/${requestId}/details`,
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  if (!response.ok) {
    throw new Error('Failed to fetch request details');
  }
  
  return response.json();
};

// Usage
const details = await getRequestDetails('req-1a23bc');
console.log(details.project.name);
console.log(details.students[0].name);
```

## Performance Considerations

The endpoint performs multiple database queries:
1. Request lookup (1 query)
2. Group validation (1 query)
3. Project lookup (1 query)
4. Project domains (1 query)
5. Group members with student/user data (1 query)

**Total: ~5 queries per request**

For better performance, you could:
- Use a single complex JOIN query
- Add database indexes on frequently queried fields
- Cache project and student data if it doesn't change often

## Testing

Test the endpoint with:

```bash
curl -X GET "http://localhost:8000/api/invites/supervisor/{request_id}/details" \
  -H "Authorization: Bearer <supervisor_token>"
```

Replace `{request_id}` with an actual request ID that belongs to the authenticated supervisor.

