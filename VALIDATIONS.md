# API Validation & Success Messages Documentation

This document provides comprehensive validation rules, error messages, and success responses for all signup and profile APIs to help with frontend integration.

## Table of Contents

1. [Authentication APIs](#authentication-apis)
2. [Student Profile APIs](#student-profile-apis)
3. [Supervisor Profile APIs](#supervisor-profile-apis)
4. [Admin Profile APIs](#admin-profile-apis)
5. [Password Change API](#password-change-api)
6. [Common Error Codes](#common-error-codes)

---

## Authentication APIs

### 1. User Signup

**Endpoint**: `POST /auth/signup`

#### Request Validation

| Field | Type | Required | Validation Rules | Error Messages |
|-------|------|----------|------------------|----------------|
| `full_name` | string | ✅ | 2-120 characters, no numbers | "Full name cannot be empty"<br>"Full name should not contain numbers" |
| `email` | email | ✅ | Valid email format | "Invalid email format" |
| `password` | string | ✅ | See password rules below | Multiple validation messages |
| `role` | string | ✅ | "student", "supervisor", or "admin" | "Invalid role" |
| `remember_me` | boolean | ❌ | true/false | - |

#### Password Validation Rules

| Rule | Error Message |
|------|---------------|
| Minimum 8 characters | "Password must be at least 8 characters long" |
| At least 1 uppercase letter | "Password must contain at least one uppercase letter (A-Z)" |
| At least 1 lowercase letter | "Password must contain at least one lowercase letter (a-z)" |
| At least 1 number | "Password must contain at least one number (0-9)" |
| At least 1 special character | "Password must contain at least one special character from: !@#$%^&*(),.?\":{}|<>" |

#### Success Response (201 Created)

```json
{
  "message": "Account created successfully",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "student",
  "user": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "John Doe",
    "email": "john@example.com",
    "role": "student",
    "profile_avatar": null,
    "has_student_profile": false,
    "has_supervisor_profile": false,
    "has_admin_profile": false
  }
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 400 | "Email already registered" | Email already exists in system |
| 400 | "Password must be at least 8 characters long" | Password too short |
| 400 | "Password must contain at least one uppercase letter (A-Z)" | Missing uppercase |
| 400 | "Password must contain at least one lowercase letter (a-z)" | Missing lowercase |
| 400 | "Password must contain at least one number (0-9)" | Missing number |
| 400 | "Password must contain at least one special character from: !@#$%^&*(),.?\":{}|<>" | Missing special char |
| 400 | "Full name should not contain numbers" | Invalid full name |
| 400 | "Invalid email format" | Malformed email |
| 500 | "Error creating user account" | Database/server error |

### 2. User Login

**Endpoint**: `POST /auth/login`

#### Request Validation

| Field | Type | Required | Validation Rules | Error Messages |
|-------|------|----------|------------------|----------------|
| `email` | email | ✅ | Valid email format | "Invalid email format" |
| `password` | string | ✅ | Non-empty | "Password cannot be empty" |
| `remember_me` | boolean | ❌ | true/false | - |

#### Success Response (200 OK)

```json
{
  "message": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "student",
  "user": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "John Doe",
    "email": "john@example.com",
    "role": "student",
    "profile_avatar": null,
    "has_student_profile": true,
    "has_supervisor_profile": false,
    "has_admin_profile": false
  }
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 401 | "Invalid email or password" | Wrong credentials |
| 400 | "Invalid email format" | Malformed email |
| 500 | "Login process failed" | Server error |

---

## Student Profile APIs

### 1. Get Student Profile

**Endpoint**: `GET /students/profile`

#### Success Response (200 OK)

```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "John Doe",
  "email": "john@example.com",
  "role": "student",
  "profile_avatar": "https://example.com/avatar.jpg",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "roll_number": "2021-CS-001",
  "department": "Computer Science",
  "cgpa": 3.5,
  "interests": ["AI", "Machine Learning"],
  "experience": "2 years of programming experience",
  "portfolio_projects": {
    "project1": "AI Chatbot",
    "project2": "Web Application"
  },
  "skills": ["Python", "JavaScript", "React"]
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 403 | "Access denied. This endpoint is only for students." | Wrong user role |
| 404 | "User not found" | User doesn't exist |
| 401 | "Invalid authentication token" | Invalid/missing JWT |

### 2. Update Student Profile

**Endpoint**: `PATCH /students/profile`

#### Request Validation

| Field | Type | Required | Validation Rules | Error Messages |
|-------|------|----------|------------------|----------------|
| `full_name` | string | ❌ | 1-255 characters | "Full name must be between 1 and 255 characters" |
| `email` | email | ❌ | Valid email format | "Invalid email format" |
| `profile_avatar` | string | ❌ | Max 500 characters | "Profile avatar URL too long" |
| `roll_number` | string | ❌ | 1-50 characters | "Roll number must be between 1 and 50 characters" |
| `department` | string | ❌ | Max 255 characters | "Department name too long" |
| `cgpa` | float | ❌ | 0.0-4.0 | "CGPA must be between 0.0 and 4.0" |
| `interests` | array | ❌ | Max 20 items | "Too many interests (max 20)" |
| `experience` | string | ❌ | Max 2000 characters | "Experience description too long" |
| `portfolio_projects` | object | ❌ | Valid JSON object | "Invalid portfolio projects format" |
| `skills` | array | ❌ | Max 50 items | "Too many skills (max 50)" |

#### Success Response (200 OK)

```json
{
  "message": "Student profile updated successfully",
  "profile": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "John Doe",
    "email": "john@example.com",
    "role": "student",
    "profile_avatar": "https://example.com/avatar.jpg",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T12:00:00",
    "roll_number": "2021-CS-001",
    "department": "Computer Science",
    "cgpa": 3.5,
    "interests": ["AI", "Machine Learning"],
    "experience": "2 years of programming experience",
    "portfolio_projects": {
      "project1": "AI Chatbot",
      "project2": "Web Application"
    },
    "skills": ["Python", "JavaScript", "React"]
  }
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 403 | "Access denied. This endpoint is only for students." | Wrong user role |
| 400 | "Full name must be between 1 and 255 characters" | Invalid full name length |
| 400 | "Invalid email format" | Malformed email |
| 400 | "Profile avatar URL too long" | Avatar URL exceeds limit |
| 400 | "Roll number must be between 1 and 50 characters" | Invalid roll number |
| 400 | "Department name too long" | Department name exceeds limit |
| 400 | "CGPA must be between 0.0 and 4.0" | Invalid CGPA range |
| 400 | "Too many interests (max 20)" | Too many interests |
| 400 | "Experience description too long" | Experience text too long |
| 400 | "Invalid portfolio projects format" | Invalid JSON format |
| 400 | "Too many skills (max 50)" | Too many skills |
| 401 | "Invalid authentication token" | Invalid/missing JWT |
| 500 | "Failed to update profile" | Database/server error |

---

## Supervisor Profile APIs

### 1. Get Supervisor Profile

**Endpoint**: `GET /supervisors/profile`

#### Success Response (200 OK)

```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Dr. Jane Smith",
  "email": "jane@example.com",
  "role": "supervisor",
  "profile_avatar": "https://example.com/avatar.jpg",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "department": "Computer Science",
  "designation": "Associate Professor",
  "office": "Room 101, CS Building",
  "requirements": ["Strong programming skills", "Research experience"],
  "project_types": ["AI/ML", "Web Development"],
  "capacity_max": 8,
  "capacity_filled": 3
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 403 | "Access denied. This endpoint is only for supervisors." | Wrong user role |
| 404 | "User not found" | User doesn't exist |
| 401 | "Invalid authentication token" | Invalid/missing JWT |

### 2. Update Supervisor Profile

**Endpoint**: `PATCH /supervisors/profile`

#### Request Validation

| Field | Type | Required | Validation Rules | Error Messages |
|-------|------|----------|------------------|----------------|
| `full_name` | string | ❌ | 1-255 characters | "Full name must be between 1 and 255 characters" |
| `email` | email | ❌ | Valid email format | "Invalid email format" |
| `profile_avatar` | string | ❌ | Max 500 characters | "Profile avatar URL too long" |
| `department` | string | ❌ | Max 255 characters | "Department name too long" |
| `designation` | string | ❌ | Max 255 characters | "Designation too long" |
| `office` | string | ❌ | Max 255 characters | "Office location too long" |
| `requirements` | array | ❌ | Max 20 items | "Too many requirements (max 20)" |
| `project_types` | array | ❌ | Max 10 items | "Too many project types (max 10)" |
| `capacity_max` | integer | ❌ | 0-20 | "Capacity must be between 0 and 20" |

#### Success Response (200 OK)

```json
{
  "message": "Supervisor profile updated successfully",
  "profile": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "Dr. Jane Smith",
    "email": "jane@example.com",
    "role": "supervisor",
    "profile_avatar": "https://example.com/avatar.jpg",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T12:00:00",
    "department": "Computer Science",
    "designation": "Associate Professor",
    "office": "Room 101, CS Building",
    "requirements": ["Strong programming skills", "Research experience"],
    "project_types": ["AI/ML", "Web Development"],
    "capacity_max": 8,
    "capacity_filled": 3
  }
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 403 | "Access denied. This endpoint is only for supervisors." | Wrong user role |
| 400 | "Full name must be between 1 and 255 characters" | Invalid full name length |
| 400 | "Invalid email format" | Malformed email |
| 400 | "Profile avatar URL too long" | Avatar URL exceeds limit |
| 400 | "Department name too long" | Department name exceeds limit |
| 400 | "Designation too long" | Designation exceeds limit |
| 400 | "Office location too long" | Office location exceeds limit |
| 400 | "Too many requirements (max 20)" | Too many requirements |
| 400 | "Too many project types (max 10)" | Too many project types |
| 400 | "Capacity must be between 0 and 20" | Invalid capacity range |
| 401 | "Invalid authentication token" | Invalid/missing JWT |
| 500 | "Failed to update profile" | Database/server error |

---

## Admin Profile APIs

### 1. Get Admin Profile

**Endpoint**: `GET /admins/profile`

#### Success Response (200 OK)

```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Admin User",
  "email": "admin@example.com",
  "role": "admin",
  "profile_avatar": "https://example.com/avatar.jpg",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "phone": "+1234567890",
  "profile_pic": "https://example.com/profile.jpg"
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 403 | "Access denied. This endpoint is only for admins." | Wrong user role |
| 404 | "User not found" | User doesn't exist |
| 401 | "Invalid authentication token" | Invalid/missing JWT |

### 2. Update Admin Profile

**Endpoint**: `PATCH /admins/profile`

#### Request Validation

| Field | Type | Required | Validation Rules | Error Messages |
|-------|------|----------|------------------|----------------|
| `full_name` | string | ❌ | 1-255 characters | "Full name must be between 1 and 255 characters" |
| `email` | email | ❌ | Valid email format | "Invalid email format" |
| `profile_avatar` | string | ❌ | Max 500 characters | "Profile avatar URL too long" |
| `phone` | string | ❌ | Max 20 characters | "Phone number too long" |
| `profile_pic` | string | ❌ | Max 500 characters | "Profile picture URL too long" |

#### Success Response (200 OK)

```json
{
  "message": "Admin profile updated successfully",
  "profile": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "Admin User",
    "email": "admin@example.com",
    "role": "admin",
    "profile_avatar": "https://example.com/avatar.jpg",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T12:00:00",
    "phone": "+1234567890",
    "profile_pic": "https://example.com/profile.jpg"
  }
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 403 | "Access denied. This endpoint is only for admins." | Wrong user role |
| 400 | "Full name must be between 1 and 255 characters" | Invalid full name length |
| 400 | "Invalid email format" | Malformed email |
| 400 | "Profile avatar URL too long" | Avatar URL exceeds limit |
| 400 | "Phone number too long" | Phone number exceeds limit |
| 400 | "Profile picture URL too long" | Profile picture URL exceeds limit |
| 401 | "Invalid authentication token" | Invalid/missing JWT |
| 500 | "Failed to update profile" | Database/server error |

---

## Password Change API

### Change Password

**Endpoint**: `PATCH /api/users/change-password`

#### Request Validation

| Field | Type | Required | Validation Rules | Error Messages |
|-------|------|----------|------------------|----------------|
| `current_password` | string | ✅ | Non-empty | "Current password cannot be empty" |
| `new_password` | string | ✅ | See password rules below | Multiple validation messages |

#### Password Validation Rules (Same as Signup)

| Rule | Error Message |
|------|---------------|
| Minimum 8 characters | "Password must be at least 8 characters long" |
| At least 1 uppercase letter | "Password must contain at least one uppercase letter (A-Z)" |
| At least 1 lowercase letter | "Password must contain at least one lowercase letter (a-z)" |
| At least 1 number | "Password must contain at least one number (0-9)" |
| At least 1 special character | "Password must contain at least one special character from: !@#$%^&*(),.?\":{}|<>" |

#### Success Response (200 OK)

```json
{
  "message": "Password updated successfully"
}
```

#### Error Responses

| Status Code | Error Message | Description |
|-------------|---------------|-------------|
| 400 | "Current password is incorrect" | Wrong current password |
| 400 | "Password must be at least 8 characters long" | New password too short |
| 400 | "Password must contain at least one uppercase letter (A-Z)" | Missing uppercase |
| 400 | "Password must contain at least one lowercase letter (a-z)" | Missing lowercase |
| 400 | "Password must contain at least one number (0-9)" | Missing number |
| 400 | "Password must contain at least one special character from: !@#$%^&*(),.?\":{}|<>" | Missing special char |
| 401 | "Invalid authentication token" | Invalid/missing JWT |
| 500 | "Failed to update password" | Database/server error |

---

## Common Error Codes

### HTTP Status Codes

| Code | Description | Usage |
|------|-------------|-------|
| 200 | OK | Successful GET/PATCH requests |
| 201 | Created | Successful POST requests (signup) |
| 400 | Bad Request | Validation errors, invalid input |
| 401 | Unauthorized | Invalid/missing authentication |
| 403 | Forbidden | Access denied (wrong role) |
| 404 | Not Found | Resource doesn't exist |
| 500 | Internal Server Error | Database/server errors |

### Authentication Errors

| Error Message | Status Code | Description |
|---------------|-------------|-------------|
| "Invalid authentication token" | 401 | JWT token is invalid/expired |
| "Token has expired" | 401 | JWT token has expired |
| "Access denied. This endpoint is only for [role]." | 403 | User doesn't have required role |

### Validation Error Format

All validation errors return in this format:

```json
{
  "detail": "Error message here"
}
```

For multiple validation errors (like password validation), the error message contains newline-separated messages:

```json
{
  "detail": "Password must be at least 8 characters long\nPassword must contain at least one uppercase letter (A-Z)"
}
```

---

## Frontend Integration Tips

### 1. Error Handling

```javascript
try {
  const response = await fetch('/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData)
  });
  
  if (!response.ok) {
    const error = await response.json();
    // Handle validation errors
    if (response.status === 400) {
      // Split multiple validation messages
      const errors = error.detail.split('\n');
      errors.forEach(err => showError(err));
    }
  }
} catch (error) {
  console.error('Network error:', error);
}
```

### 2. Success Handling

```javascript
const data = await response.json();
if (data.message) {
  showSuccess(data.message);
  // Store token
  localStorage.setItem('auth_token', data.access_token);
}
```

### 3. Form Validation

```javascript
// Client-side validation before API call
const validateForm = (formData) => {
  const errors = [];
  
  if (formData.password.length < 8) {
    errors.push("Password must be at least 8 characters long");
  }
  
  // Add more validations...
  
  return errors;
};
```

This documentation provides all the validation rules, error messages, and success responses you need for proper frontend integration!
