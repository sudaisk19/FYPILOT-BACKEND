# Hybrid API Architecture Guide

This guide documents the new hybrid API architecture implemented for role-based dashboard and profile management.

## Architecture Overview

The hybrid approach provides:
1. **Lightweight Login** - Returns JWT + basic user info
2. **Role-Specific Dashboard API** - Returns dashboard data based on user role
3. **Detailed Profile APIs** - Returns comprehensive profile data when needed
4. **React Query Integration** - Optimized for frontend caching and state management

## New API Endpoints

### 1. Dashboard API

#### `GET /api/dashboard`
Returns role-specific dashboard data including profile summary, groups, and statistics.

**Authentication:** Required (JWT Bearer token)

**Response Examples:**

**Student Dashboard:**
```json
{
  "student_profile": {
    "student_id": "STU001",
    "department": "Computer Science",
    "year": "2024",
    "enrollment_date": "2023-09-01T00:00:00",
    "cgpa": 3.8,
    "status": "active"
  },
  "groups": [
    {
      "group_id": "123e4567-e89b-12d3-a456-426614174000",
      "group_name": "FYP Group A",
      "project_title": "AI Chatbot Development",
      "status": "active",
      "created_at": "2023-09-01T00:00:00",
      "updated_at": "2023-12-01T00:00:00",
      "role": "member"
    }
  ],
  "stats": {
    "total_groups": 1,
    "active_groups": 1,
    "pending_tasks": 0
  }
}
```

**Supervisor Dashboard:**
```json
{
  "supervisor_profile": {
    "supervisor_id": "SUP001",
    "department": "Computer Science",
    "expertise": ["AI", "Machine Learning"],
    "max_groups": 10,
    "current_groups": 3,
    "status": "active"
  },
  "managed_groups": [
    {
      "group_id": "123e4567-e89b-12d3-a456-426614174000",
      "group_name": "FYP Group A",
      "project_title": "AI Chatbot Development",
      "status": "active",
      "created_at": "2023-09-01T00:00:00",
      "updated_at": "2023-12-01T00:00:00",
      "members_count": 3,
      "members": [
        {
          "user_id": "456e7890-e89b-12d3-a456-426614174000",
          "full_name": "Alice Johnson",
          "email": "alice@example.com",
          "role": "student"
        }
      ]
    }
  ],
  "stats": {
    "total_groups": 3,
    "active_groups": 2,
    "total_students": 8
  }
}
```

**Admin Dashboard:**
```json
{
  "admin_profile": {
    "admin_id": "ADM001",
    "department": "Computer Science",
    "permissions": ["all"],
    "status": "active"
  },
  "stats": {
    "total_groups": 25,
    "active_groups": 20,
    "total_students": 75
  }
}
```

### 2. Profile APIs

#### `GET /api/student/profile`
Returns detailed student profile information.

**Authentication:** Required (Student role only)

**Response:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Alice Johnson",
  "email": "alice@example.com",
  "profile_avatar": null,
  "student_profile": {
    "student_id": "STU001",
    "department": "Computer Science",
    "year": "2024",
    "enrollment_date": "2023-09-01T00:00:00",
    "status": "active",
    "cgpa": 3.8,
    "phone": "+1234567890",
    "address": "123 University St",
    "interests": ["AI", "Web Development"],
    "skills": ["Python", "React", "Machine Learning"],
    "bio": "Passionate about AI and web development",
    "linkedin_url": "https://linkedin.com/in/alice",
    "github_url": "https://github.com/alice",
    "portfolio_url": "https://alice.dev"
  },
  "created_at": "2023-09-01T00:00:00",
  "updated_at": "2023-12-01T00:00:00"
}
```

#### `GET /api/supervisor/profile`
Returns detailed supervisor profile information.

**Authentication:** Required (Supervisor role only)

**Response:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Dr. Smith",
  "email": "smith@university.edu",
  "profile_avatar": null,
  "supervisor_profile": {
    "supervisor_id": "SUP001",
    "department": "Computer Science",
    "status": "active",
    "expertise": ["AI", "Machine Learning", "Data Science"],
    "max_groups": 10,
    "phone": "+1234567890",
    "office_location": "CS Building Room 101",
    "office_hours": "Mon-Fri 2-4 PM",
    "bio": "Professor of Computer Science specializing in AI",
    "qualifications": ["PhD Computer Science", "MSc AI"],
    "research_interests": ["Deep Learning", "NLP"],
    "linkedin_url": "https://linkedin.com/in/drsmith",
    "google_scholar_url": "https://scholar.google.com/citations?user=smith",
    "website_url": "https://cs.university.edu/smith"
  },
  "created_at": "2023-09-01T00:00:00",
  "updated_at": "2023-12-01T00:00:00"
}
```

#### `GET /api/admin/profile`
Returns detailed admin profile information.

**Authentication:** Required (Admin role only)

**Response:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Admin User",
  "email": "admin@university.edu",
  "profile_avatar": null,
  "admin_profile": {
    "admin_id": "ADM001",
    "department": "Computer Science",
    "status": "active",
    "permissions": ["all"],
    "access_level": "full",
    "phone": "+1234567890",
    "office_location": "Admin Building Room 201",
    "bio": "System administrator for FYP management",
    "responsibilities": ["User Management", "System Configuration"],
    "linkedin_url": "https://linkedin.com/in/admin"
  },
  "created_at": "2023-09-01T00:00:00",
  "updated_at": "2023-12-01T00:00:00"
}
```

## Frontend Integration

### React Query Hooks

```javascript
// hooks/useDashboard.js
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../stores/authStore';

export const useDashboard = () => {
  const token = useAuthStore(state => state.token);
  
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const response = await fetch('/api/dashboard', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      return response.json();
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: true
  });
};

// hooks/useProfile.js
export const useProfile = () => {
  const token = useAuthStore(state => state.token);
  const role = useAuthStore(state => state.user?.role);
  
  return useQuery({
    queryKey: ['profile', role],
    queryFn: async () => {
      const response = await fetch(`/api/${role}/profile`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      return response.json();
    },
    enabled: !!token && !!role,
    staleTime: 10 * 60 * 1000 // 10 minutes
  });
};
```

### Dashboard Components

```javascript
// components/StudentDashboard.jsx
import { useDashboard } from '../hooks/useDashboard';

const StudentDashboard = () => {
  const { data, isLoading, error } = useDashboard();
  
  if (isLoading) return <Loading />;
  if (error) return <Error />;
  
  return (
    <div>
      <h1>Welcome, {data.student_profile.student_id}</h1>
      <StudentProfile profile={data.student_profile} />
      <GroupsList groups={data.groups} />
      <Stats stats={data.stats} />
    </div>
  );
};

// components/SupervisorDashboard.jsx
const SupervisorDashboard = () => {
  const { data, isLoading, error } = useDashboard();
  
  if (isLoading) return <Loading />;
  if (error) return <Error />;
  
  return (
    <div>
      <h1>Welcome, Dr. {data.supervisor_profile.supervisor_id}</h1>
      <SupervisorProfile profile={data.supervisor_profile} />
      <ManagedGroups groups={data.managed_groups} />
      <Stats stats={data.stats} />
    </div>
  );
};
```

### Role-Based Routing

```javascript
// App.jsx
import { useAuthStore } from './stores/authStore';

const App = () => {
  const { user, isAuthenticated } = useAuthStore();
  
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      
      {/* Student Routes */}
      <Route path="/student/dashboard" element={
        <ProtectedRoute allowedRoles={['student']}>
          <StudentDashboard />
        </ProtectedRoute>
      } />
      
      {/* Supervisor Routes */}
      <Route path="/supervisor/dashboard" element={
        <ProtectedRoute allowedRoles={['supervisor']}>
          <SupervisorDashboard />
        </ProtectedRoute>
      } />
      
      {/* Admin Routes */}
      <Route path="/admin/dashboard" element={
        <ProtectedRoute allowedRoles={['admin']}>
          <AdminDashboard />
        </ProtectedRoute>
      } />
    </Routes>
  );
};
```

## Benefits of This Architecture

### ✅ Performance Benefits
- **Fast Login**: No heavy data loading during authentication
- **Efficient Caching**: React Query handles intelligent caching
- **Background Refresh**: Data stays fresh automatically
- **Optimistic Updates**: UI updates instantly

### ✅ Developer Experience
- **Separation of Concerns**: Each endpoint has a single responsibility
- **Type Safety**: Strongly typed responses
- **Easy Testing**: Each endpoint can be tested independently
- **Scalable**: Easy to add new endpoints

### ✅ User Experience
- **Instant Redirects**: Role-based routing works immediately
- **Progressive Loading**: Dashboard loads while profile loads in background
- **Offline Support**: React Query provides offline capabilities
- **Real-time Updates**: Data refreshes automatically

## Error Handling

All endpoints return appropriate HTTP status codes:

- **200**: Success
- **401**: Unauthorized (invalid/missing token)
- **403**: Forbidden (wrong role)
- **404**: Profile not found
- **500**: Internal server error

## Security Features

- **JWT Authentication**: All endpoints require valid JWT tokens
- **Role-Based Access**: Each profile endpoint checks user role
- **Input Validation**: All inputs are validated using Pydantic
- **SQL Injection Protection**: Using SQLAlchemy ORM
- **CORS Configuration**: Proper CORS setup for frontend integration

This hybrid architecture provides the perfect balance of performance, maintainability, and user experience for your FYPilot application!



