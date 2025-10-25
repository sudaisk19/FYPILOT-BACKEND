# Enhanced OAuth Flow Guide

This guide documents the enhanced OAuth implementation that provides different behaviors for login vs signup pages.

## Overview

The enhanced OAuth flow now supports:
- **Different behaviors** for login vs signup pages
- **Automatic role selection** for new OAuth users
- **Smart redirects** based on user status and source page
- **Role update endpoint** for post-OAuth role selection

## Enhanced OAuth Endpoints

### 1. OAuth Initiation (Enhanced)

#### **Endpoint:** `GET /auth/oauth/{provider}`
- **Parameters:**
  - `return_to` (optional): Frontend route to redirect to after OAuth
  - `source` (optional): Source page - "login" or "signup"

#### **Examples:**

**Login Page OAuth:**
```
GET /auth/oauth/google?return_to=/dashboard&source=login
GET /auth/oauth/github?return_to=/dashboard&source=login
```

**Signup Page OAuth:**
```
GET /auth/oauth/google?return_to=/dashboard&source=signup
GET /auth/oauth/github?return_to=/dashboard&source=signup
```

### 2. OAuth Callback (Enhanced Logic)

#### **Endpoint:** `GET /auth/oauth/{provider}/callback`

**Enhanced Behavior:**

| User Status | Source Page | Redirect Behavior |
|-------------|-------------|-------------------|
| **New User** | `signup` | → `/auth/role-selection` |
| **New User** | `login` | → `/dashboard` (default) |
| **Existing User** | `login` | → `/dashboard` |
| **Existing User** | `signup` | → `/dashboard` (already signed up) |

### 3. Role Update Endpoint (New)

#### **Endpoint:** `PATCH /auth/update-role`
- **Authentication:** Required (JWT Bearer token)
- **Purpose:** Update user role after OAuth signup

**Request Body:**
```json
{
  "role": "student"  // "student" or "supervisor" only
}
```

**Response:**
```json
{
  "message": "Role updated successfully",
  "role": "student",
  "user": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "Alice Johnson",
    "email": "alice@example.com",
    "role": "student",
    "profile_avatar": null,
    "has_student_profile": true,
    "has_supervisor_profile": false,
    "has_admin_profile": false
  }
}
```

## Frontend Integration

### 1. Login Page OAuth Buttons

```javascript
// pages/LoginPage.jsx
const LoginPage = () => {
  const handleGoogleAuth = () => {
    const returnTo = encodeURIComponent('/dashboard');
    window.location.href = `/auth/oauth/google?return_to=${returnTo}&source=login`;
  };

  const handleGitHubAuth = () => {
    const returnTo = encodeURIComponent('/dashboard');
    window.location.href = `/auth/oauth/github?return_to=${returnTo}&source=login`;
  };

  return (
    <div>
      <h1>Login</h1>
      
      {/* Traditional login form */}
      <form>
        {/* ... login form fields ... */}
      </form>
      
      <div className="divider">OR</div>
      
      {/* OAuth buttons */}
      <button onClick={handleGoogleAuth}>Continue with Google</button>
      <button onClick={handleGitHubAuth}>Continue with GitHub</button>
    </div>
  );
};
```

### 2. Signup Page OAuth Buttons

```javascript
// pages/SignupPage.jsx
const SignupPage = () => {
  const handleGoogleAuth = () => {
    const returnTo = encodeURIComponent('/dashboard');
    window.location.href = `/auth/oauth/google?return_to=${returnTo}&source=signup`;
  };

  const handleGitHubAuth = () => {
    const returnTo = encodeURIComponent('/dashboard');
    window.location.href = `/auth/oauth/github?return_to=${returnTo}&source=signup`;
  };

  return (
    <div>
      <h1>Sign Up</h1>
      
      {/* Traditional signup form */}
      <form>
        {/* ... signup form fields ... */}
      </form>
      
      <div className="divider">OR</div>
      
      {/* OAuth buttons */}
      <button onClick={handleGoogleAuth}>Continue with Google</button>
      <button onClick={handleGitHubAuth}>Continue with GitHub</button>
    </div>
  );
};
```

### 3. Role Selection Page

```javascript
// pages/RoleSelectionPage.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

const RoleSelectionPage = () => {
  const [selectedRole, setSelectedRole] = useState('student');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuthStore(state => state.setAuth);
  
  const handleRoleSelection = async () => {
    setLoading(true);
    
    try {
      const response = await fetch('/auth/update-role', {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ role: selectedRole })
      });
      
      if (response.ok) {
        const data = await response.json();
        
        // Update auth store with new role
        setAuth(localStorage.getItem('auth_token'), data.user);
        
        // Redirect to appropriate dashboard
        if (selectedRole === 'student') {
          navigate('/student/dashboard');
        } else if (selectedRole === 'supervisor') {
          navigate('/supervisor/dashboard');
        }
      } else {
        const error = await response.json();
        alert('Error updating role: ' + error.detail);
      }
    } catch (error) {
      alert('Network error: ' + error.message);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="role-selection">
      <h1>Choose Your Role</h1>
      <p>Please select your role to continue:</p>
      
      <div className="role-options">
        <label className="role-option">
          <input
            type="radio"
            value="student"
            checked={selectedRole === 'student'}
            onChange={(e) => setSelectedRole(e.target.value)}
          />
          <div className="role-card">
            <h3>Student</h3>
            <p>Join groups and work on projects</p>
          </div>
        </label>
        
        <label className="role-option">
          <input
            type="radio"
            value="supervisor"
            checked={selectedRole === 'supervisor'}
            onChange={(e) => setSelectedRole(e.target.value)}
          />
          <div className="role-card">
            <h3>Supervisor</h3>
            <p>Guide and mentor student groups</p>
          </div>
        </label>
        
        <label className="role-option">
          <input
            type="radio"
            value="admin"
            checked={selectedRole === 'admin'}
            onChange={(e) => setSelectedRole(e.target.value)}
          />
          <div className="role-card">
            <h3>Admin</h3>
            <p>Manage the system and users</p>
          </div>
        </label>
      </div>
      
      <button 
        onClick={handleRoleSelection} 
        disabled={loading}
        className="continue-btn"
      >
        {loading ? 'Updating...' : 'Continue'}
      </button>
    </div>
  );
};
```

### 4. React Query Integration

```javascript
// hooks/useRoleUpdate.js
import { useMutation } from '@tanstack/react-query';
import { useAuthStore } from '../stores/authStore';

export const useRoleUpdate = () => {
  const setAuth = useAuthStore(state => state.setAuth);
  
  return useMutation({
    mutationFn: async ({ role }) => {
      const response = await fetch('/auth/update-role', {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ role })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      
      return response.json();
    },
    onSuccess: (data) => {
      // Update auth store with new role
      setAuth(localStorage.getItem('auth_token'), data.user);
    }
  });
};
```

## Complete OAuth Flow Examples

### **Scenario 1: New User from Signup Page**

1. User clicks "Continue with Google" on signup page
2. OAuth flow: `GET /auth/oauth/google?source=signup&return_to=/dashboard`
3. User completes Google OAuth
4. Backend creates new user with default "student" role
5. Backend redirects to: `/auth/role-selection`
6. User selects role (e.g., "supervisor")
7. Frontend calls: `PATCH /auth/update-role` with `{"role": "supervisor"}`
8. Backend updates user role and returns new JWT
9. Frontend redirects to: `/supervisor/dashboard`

### **Scenario 2: Existing User from Login Page**

1. User clicks "Continue with Google" on login page
2. OAuth flow: `GET /auth/oauth/google?source=login&return_to=/dashboard`
3. User completes Google OAuth
4. Backend finds existing user
5. Backend redirects to: `/dashboard`
6. Frontend loads appropriate dashboard based on user's existing role

### **Scenario 3: Existing User from Signup Page**

1. User clicks "Continue with Google" on signup page
2. OAuth flow: `GET /auth/oauth/google?source=signup&return_to=/dashboard`
3. User completes Google OAuth
4. Backend finds existing user
5. Backend redirects to: `/dashboard` (they're already signed up)
6. Frontend loads appropriate dashboard based on user's existing role

## Benefits of Enhanced OAuth Flow

### ✅ **Better User Experience**
- **Clear Intent**: Different behaviors for login vs signup
- **Role Selection**: New users can choose their role
- **No Confusion**: Existing users don't get stuck in role selection

### ✅ **Flexible Architecture**
- **Source Tracking**: Know which page initiated OAuth
- **Smart Redirects**: Appropriate redirects based on user status
- **Role Updates**: Easy role changes after OAuth signup

### ✅ **Security & Validation**
- **Role Validation**: Only valid roles accepted
- **JWT Updates**: New tokens generated with updated roles
- **Session Management**: Proper session handling for OAuth state

## Error Handling

### **Common Error Responses:**

#### **400 Bad Request**
```json
{
  "detail": "Invalid role. Must be 'student', 'supervisor', or 'admin'"
}
```

#### **401 Unauthorized**
```json
{
  "detail": "Authentication failed"
}
```

#### **500 Internal Server Error**
```json
{
  "detail": "Failed to update user role"
}
```

This enhanced OAuth flow provides a much better user experience while maintaining security and flexibility!






