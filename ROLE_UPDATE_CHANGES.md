# Role Update Endpoint Changes

## Overview

The `/auth/update-role` endpoint has been updated to restrict role selection to only **"student"** and **"supervisor"** options, excluding the **"admin"** role.

## Changes Made

### 1. Backend Validation (app/auth/routes.py)

**Before:**
```python
if new_role not in ["student", "supervisor", "admin"]:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid role. Must be 'student', 'supervisor', or 'admin'"
    )
```

**After:**
```python
if new_role not in ["student", "supervisor"]:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid role. Must be 'student' or 'supervisor'"
    )
```

### 2. Schema Validation (app/schemas/auth_schema.py)

**Before:**
```python
class RoleUpdateRequest(BaseModel):
    role: str  # "student", "supervisor", or "admin"
```

**After:**
```python
class RoleUpdateRequest(BaseModel):
    role: str  # "student" or "supervisor" only
    
    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        """Validate that role is either student or supervisor"""
        if v not in ["student", "supervisor"]:
            raise ValueError("Role must be 'student' or 'supervisor'")
        return v
```

### 3. Documentation Updates

#### Endpoint Documentation (app/auth/routes.py)
- Updated docstring to specify "student or supervisor only"
- Updated error message documentation

#### OAuth Guide (ENHANCED_OAUTH_GUIDE.md)
- Updated request body example
- Removed admin role from frontend redirect logic

## Validation Levels

The role restriction is now enforced at **two levels**:

### 1. Pydantic Schema Validation
- **When**: During request parsing
- **Error**: 422 Validation Error
- **Message**: "Role must be 'student' or 'supervisor'"

### 2. Backend Logic Validation
- **When**: During endpoint execution
- **Error**: 400 Bad Request
- **Message**: "Invalid role. Must be 'student' or 'supervisor'"

## API Behavior

### Valid Requests
```json
POST /auth/update-role
{
  "role": "student"
}
```

```json
POST /auth/update-role
{
  "role": "supervisor"
}
```

### Invalid Requests
```json
POST /auth/update-role
{
  "role": "admin"
}
```
**Response:** 422 Validation Error

```json
POST /auth/update-role
{
  "role": "teacher"
}
```
**Response:** 422 Validation Error

## Frontend Impact

### Role Selection UI
- **Remove**: Admin role option from role selection page
- **Keep**: Student and Supervisor options only

### Redirect Logic
- **Remove**: Admin dashboard redirect
- **Keep**: Student and Supervisor dashboard redirects

## Testing

All changes have been tested and verified:
- ✅ Valid roles ("student", "supervisor") are accepted
- ✅ Invalid roles ("admin", "teacher", etc.) are rejected
- ✅ Both Pydantic and backend validation work correctly
- ✅ Error messages are clear and helpful

## Summary

The role update endpoint now properly restricts role selection to only "student" and "supervisor" options, with comprehensive validation at both the schema and backend levels. This ensures that users cannot select the "admin" role through the OAuth flow.



