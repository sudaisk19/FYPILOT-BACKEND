# Profile Management Endpoints

This document lists all profile-related endpoints in the FYPilot backend API.

## Overview

The profile system has been restructured to support two distinct use cases:
1. **Wizard Profile Completion** (POST endpoints) - For initial profile setup after signup
2. **Profile Updates** (PATCH endpoints) - For updating existing profiles

## Student Profile Endpoints

### 1. Get Student Profile
- **Method**: `GET`
- **Endpoint**: `/api/students/profile`
- **Purpose**: Retrieve current student profile information
- **Authentication**: Required (Student role only)
- **Response**: Complete student profile with user and student data

### 2. Complete Student Wizard Profile
- **Method**: `POST`
- **Endpoint**: `/api/students/wizard-profile`
- **Purpose**: Complete student profile through wizard form (initial setup)
- **Authentication**: Required (Student role only)
- **Required Fields**: `roll_number` (must be unique)
- **Optional Fields**: All other fields
- **Response**: Success message with complete profile data

### 3. Update Student Profile
- **Method**: `PATCH`
- **Endpoint**: `/api/students/profile`
- **Purpose**: Update existing student profile (partial updates)
- **Authentication**: Required (Student role only)
- **Prerequisites**: Student profile must exist (created via wizard)
- **Excluded Fields**: `roll_number` (cannot be changed after creation)
- **Response**: Success message with updated profile data

## Supervisor Profile Endpoints

### 1. Get Supervisor Profile
- **Method**: `GET`
- **Endpoint**: `/api/supervisors/profile`
- **Purpose**: Retrieve current supervisor profile information
- **Authentication**: Required (Supervisor role only)
- **Response**: Complete supervisor profile with user and supervisor data

### 2. Complete Supervisor Wizard Profile
- **Method**: `POST`
- **Endpoint**: `/api/supervisors/wizard-profile`
- **Purpose**: Complete supervisor profile through wizard form (initial setup)
- **Authentication**: Required (Supervisor role only)
- **Required Fields**: `project_types`, `capacity_max`, `capacity_filled`
- **Optional Fields**: All other fields
- **Response**: Success message with complete profile data

### 3. Update Supervisor Profile
- **Method**: `PATCH`
- **Endpoint**: `/api/supervisors/profile`
- **Purpose**: Update existing supervisor profile (partial updates)
- **Authentication**: Required (Supervisor role only)
- **Prerequisites**: Supervisor profile must exist (created via wizard)
- **Excluded Fields**: `project_types`, `capacity_max`, `capacity_filled` (cannot be changed after creation)
- **Response**: Success message with updated profile data

## Admin Profile Endpoints

### 1. Get Admin Profile
- **Method**: `GET`
- **Endpoint**: `/api/admins/profile`
- **Purpose**: Retrieve current admin profile information
- **Authentication**: Required (Admin role only)
- **Response**: Complete admin profile with user and admin data

### 2. Complete Admin Wizard Profile
- **Method**: `POST`
- **Endpoint**: `/api/admins/wizard-profile`
- **Purpose**: Complete admin profile through wizard form (initial setup)
- **Authentication**: Required (Admin role only)
- **Required Fields**: None (all fields optional for admins)
- **Response**: Success message with complete profile data

### 3. Update Admin Profile
- **Method**: `PATCH`
- **Endpoint**: `/api/admins/profile`
- **Purpose**: Update existing admin profile (partial updates)
- **Authentication**: Required (Admin role only)
- **Prerequisites**: Admin profile must exist (created via wizard)
- **Response**: Success message with updated profile data

## Field Requirements by Role

### Student Fields
- **Required**: `roll_number` (unique, not null)
- **Optional**: `department`, `cgpa`, `interests`, `experience`, `portfolio_projects`, `skills`

### Supervisor Fields
- **Required**: `project_types` (array, not null), `capacity_max` (integer, not null), `capacity_filled` (integer, not null)
- **Optional**: `department`, `designation`, `office`, `requirements`

### Admin Fields
- **Required**: None
- **Optional**: `phone`, `profile_pic`

### Common User Fields (All Roles)
- **Optional**: `full_name`, `email`, `profile_avatar`

## Usage Patterns

### Initial Profile Setup (Wizard Flow)
1. User signs up → gets JWT token
2. User redirected to wizard form
3. User calls `POST /api/{role}/wizard-profile` with required fields
4. Profile created successfully

### Profile Updates (Settings/Edit Flow)
1. User wants to update profile
2. User calls `PATCH /api/{role}/profile` with only fields to change
3. Only provided fields are updated, others remain unchanged

## Error Handling

### Common Error Responses
- **403 Forbidden**: Wrong role accessing endpoint
- **404 Not Found**: Profile doesn't exist (for PATCH endpoints)
- **400 Bad Request**: Missing required fields (for POST endpoints)
- **422 Validation Error**: Invalid field values or format
- **500 Internal Server Error**: Database or server issues

### Validation Rules
- Empty strings are converted to `None` and skipped
- Email validation for proper format
- Array fields must be non-empty to be updated
- Required fields must be provided for wizard completion

## Authentication

All endpoints require:
- Valid JWT token in Authorization header: `Bearer <token>`
- Correct role matching the endpoint (student/supervisor/admin)
- Token must not be expired

## Response Format

All endpoints return consistent response format:
```json
{
  "message": "Success message",
  "profile": {
    // Complete profile object with user and role-specific fields
  }
}
```



