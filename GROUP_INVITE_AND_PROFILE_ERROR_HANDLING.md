# 🤝 Group Invite & Profile Error Handling Guide

## Overview

This document provides comprehensive error handling information for group invitation and profile update APIs, including all possible error scenarios, status codes, response formats, and frontend integration guidance.

**Endpoints:**
- `POST /groups/{group_id}/invite` - Send invitation to member
- `POST /groups/invites/{token}/accept` - Accept group invitation
- `POST /groups/invites/{token}/reject` - Reject group invitation
- `POST /groups/{group_id}/invites/{token}/cancel` - Cancel sent invitation
- `PATCH /groups/{group_id}/profile` - Update group profile

---

## Table of Contents

1. [Normalized Error Response Structure](#-normalized-error-response-structure)
2. [Invite API Errors](#-invite-api-errors)
3. [Group Profile Update Errors](#-group-profile-update-errors)
4. [Network & Timeout Errors](#-network--timeout-errors)
5. [Error Handling Strategy](#-error-handling-strategy)
6. [Frontend Integration Examples](#-frontend-integration-examples)
7. [Error Code Reference](#-error-code-reference)

---

## ✨ Normalized Error Response Structure

**All error responses follow this consistent structure:**

```json
{
  "success": false,
  "error": "Human-readable error message",
  "error_code": "MACHINE_READABLE_CODE",
  "details": [
    {
      "field": "field_name",
      "message": "Specific field error",
      "code": "error_type"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

---

## 🫂 Invite API Errors

### POST /groups/{group_id}/invite

Send invitation to a student to join your group.

#### Status Code: 200 OK ✅

**Success Response:**
```json
{
  "success": true,
  "message": "Invitation sent successfully",
  "timestamp": "2025-12-10T10:30:00Z"
}
```

---

### Status Code: 400 Bad Request

#### Scenario 1: User is Already in a Group

**Request:**
```json
{
  "email": "student@example.com"
}
```

**Response:**
```json
{
  "success": false,
  "error": "User is already in a group",
  "error_code": "GROUP_INVITE_USER_ALREADY_MEMBER",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** The invitee is already a member of another group

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_USER_ALREADY_MEMBER') {
  displayError('This student is already in another group');
  // Could offer to suggest other students
}
```

---

#### Scenario 2: Group is Full

**Request:**
```json
{
  "email": "student@example.com"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Group is full or has 2 pending invites",
  "error_code": "GROUP_INVITE_CAPACITY_EXCEEDED",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Group has 3 members or 2 pending invitations already

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_CAPACITY_EXCEEDED') {
  displayError('Group has reached maximum capacity (3 members)');
  showCurrentMembers();
}
```

---

#### Scenario 3: Pending Invite Already Exists

**Request:**
```json
{
  "email": "student@example.com"
}
```

**Response:**
```json
{
  "success": false,
  "error": "This user already has a pending invite to this group",
  "error_code": "GROUP_INVITE_ALREADY_PENDING",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** An invitation was already sent to this student for this group

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_ALREADY_PENDING') {
  displayError('Invitation already sent to this student');
  showPendingInvites(); // Show list of pending invitations
}
```

---

### Status Code: 403 Forbidden

#### Scenario 4: User Not a Group Member

**Request:**
```json
{
  "email": "student@example.com"
}
```

**Response:**
```json
{
  "success": false,
  "error": "You're not a member of that group",
  "error_code": "GROUP_INVITE_NOT_MEMBER",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Only group members can send invitations

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_NOT_MEMBER') {
  displayError('You must be a group member to send invitations');
  redirectTo('/groups/my-group');
}
```

---

### Status Code: 404 Not Found

#### Scenario 5: Email Not Found

**Request:**
```json
{
  "email": "nonexistent@example.com"
}
```

**Response:**
```json
{
  "success": false,
  "error": "That email isn't a registered student",
  "error_code": "GROUP_INVITE_EMAIL_NOT_FOUND",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Email is not registered or user is not a student

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_EMAIL_NOT_FOUND') {
  displayFieldError('email', 'This email is not registered as a student');
  showSuggestion('Ask them to sign up first');
}
```

#### Scenario 6: Group Not Found

**Request:** (Invalid group_id)

**Response:**
```json
{
  "success": false,
  "error": "Group not found",
  "error_code": "GROUP_INVITE_GROUP_NOT_FOUND",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Group ID doesn't exist

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_GROUP_NOT_FOUND') {
  displayError('Group no longer exists');
  redirectTo('/groups');
}
```

---

### Status Code: 422 Unprocessable Entity

#### Scenario 7: Invalid Email Format

**Request:**
```json
{
  "email": "invalid-email"
}
```

**Response:**
```json
{
  "success": false,
  "error": "value is not a valid email address",
  "error_code": "VALIDATION_INVALID_EMAIL",
  "details": [
    {
      "field": "email",
      "message": "value is not a valid email address",
      "code": "value_error.email"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_INVALID_EMAIL') {
  displayFieldError('email', 'Please enter a valid email address');
}
```

#### Scenario 8: Missing Email Field

**Request:**
```json
{}
```

**Response:**
```json
{
  "success": false,
  "error": "Field required",
  "error_code": "VALIDATION_MISSING_EMAIL",
  "details": [
    {
      "field": "email",
      "message": "Field required",
      "code": "missing"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_MISSING_EMAIL') {
  displayFieldError('email', 'Email address is required');
}
```

---

### Status Code: 500 Internal Server Error

#### Scenario 9: Email Sending Failed

**Response:**
```json
{
  "success": false,
  "error": "Failed to send invitation email",
  "error_code": "GROUP_INVITE_EMAIL_FAILED",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Email service error (SMTP failure, invalid config)

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_EMAIL_FAILED') {
  displayError('Invitation created but email failed to send. Student will be notified on login.');
  // Invite was still created, just email failed
}
```

#### Scenario 10: Database Error

**Response:**
```json
{
  "success": false,
  "error": "Failed to create invitation",
  "error_code": "SERVER_DATABASE_ERROR",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Database connection or query error

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_DATABASE_ERROR') {
  displayError('Server error. Please try again later.');
  showRetryButton();
}
```

---

## 📝 Accept/Reject Invite Errors

### POST /groups/invites/{token}/accept

#### Status Code: 200 OK ✅

**Success Response:**
```json
{
  "success": true,
  "message": "Successfully joined the group",
  "timestamp": "2025-12-10T10:30:00Z"
}
```

---

### Status Code: 400 Bad Request

#### Scenario 1: Invite Already Accepted/Rejected

**Response:**
```json
{
  "success": false,
  "error": "Invite has already been processed",
  "error_code": "GROUP_INVITE_ALREADY_PROCESSED",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Invite was already accepted or rejected

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_ALREADY_PROCESSED') {
  displayError('This invitation has already been responded to');
  checkMembership(); // Check if user is already in group
}
```

---

#### Scenario 2: Invite Token Expired

**Response:**
```json
{
  "success": false,
  "error": "Invitation has expired",
  "error_code": "GROUP_INVITE_EXPIRED",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Invitation token expired (valid for 7 days)

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_EXPIRED') {
  displayError('This invitation has expired. Ask the group to send a new one.');
  contactGroupOption();
}
```

---

#### Scenario 3: User Already in Group

**Response:**
```json
{
  "success": false,
  "error": "You are already in a group",
  "error_code": "GROUP_USER_ALREADY_MEMBER",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** User is trying to join a group but already in another one

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_USER_ALREADY_MEMBER') {
  displayError('You are already a member of another group');
  redirectTo('/groups/my-group');
}
```

---

### Status Code: 404 Not Found

#### Scenario 4: Invalid Invite Token

**Response:**
```json
{
  "success": false,
  "error": "Invitation not found",
  "error_code": "GROUP_INVITE_NOT_FOUND",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Token is invalid or doesn't exist

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_INVITE_NOT_FOUND') {
  displayError('This invitation link is invalid');
  showContactSupport();
}
```

---

## 🔧 Group Profile Update Errors

### PATCH /groups/{group_id}/profile

Update group and project information.

#### Status Code: 200 OK ✅

**Success Response:**
```json
{
  "success": true,
  "message": "Group profile updated successfully",
  "updated_at": "2025-12-10T10:30:00Z",
  "timestamp": "2025-12-10T10:30:00Z"
}
```

---

### Status Code: 400 Bad Request

#### Scenario 1: Invalid Group Name

**Request:**
```json
{
  "group": {
    "name": ""
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "Group name cannot be empty",
  "error_code": "GROUP_PROFILE_INVALID_NAME",
  "details": [
    {
      "field": "group.name",
      "message": "ensure this value has at least 1 characters",
      "code": "string_too_short"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_INVALID_NAME') {
  displayFieldError('groupName', 'Group name cannot be empty');
}
```

---

#### Scenario 2: Invalid Project Type

**Request:**
```json
{
  "project": {
    "project_type": "invalid_type"
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "Invalid project type",
  "error_code": "GROUP_PROFILE_INVALID_PROJECT_TYPE",
  "details": [
    {
      "field": "project.project_type",
      "message": "Input should be 'research' or 'product'",
      "code": "enum"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_INVALID_PROJECT_TYPE') {
  displayFieldError('projectType', 'Project type must be "research" or "product"');
}
```

---

#### Scenario 3: Invalid Cohort Year

**Request:**
```json
{
  "group": {
    "cohort_year": 1500
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "Cohort year must be between 2020 and current year + 1",
  "error_code": "GROUP_PROFILE_INVALID_COHORT_YEAR",
  "details": [
    {
      "field": "group.cohort_year",
      "message": "Value must be >= 2020 and <= 2026",
      "code": "value_error"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_INVALID_COHORT_YEAR') {
  displayFieldError('cohortYear', `Year must be between 2020 and ${currentYear + 1}`);
}
```

---

#### Scenario 4: Invalid Supervisor ID

**Request:**
```json
{
  "group": {
    "supervisor_id": "invalid-uuid"
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "Supervisor not found",
  "error_code": "GROUP_PROFILE_SUPERVISOR_NOT_FOUND",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Supervisor ID doesn't exist or is not a valid supervisor

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_SUPERVISOR_NOT_FOUND') {
  displayFieldError('supervisor', 'Selected supervisor is not available');
  reloadSupervisorList();
}
```

---

#### Scenario 5: Invalid Domain IDs

**Request:**
```json
{
  "project": {
    "domain_ids": ["invalid-uuid-1", "invalid-uuid-2"]
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "One or more domains not found",
  "error_code": "GROUP_PROFILE_DOMAINS_NOT_FOUND",
  "details": [
    {
      "field": "project.domain_ids",
      "message": "Invalid domain IDs: invalid-uuid-1, invalid-uuid-2",
      "code": "not_found"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_DOMAINS_NOT_FOUND') {
  displayFieldError('domains', 'Some selected domains are no longer available');
  reloadDomainList();
}
```

---

#### Scenario 6: Same Supervisor and Co-supervisor

**Request:**
```json
{
  "group": {
    "supervisor_id": "uuid-1",
    "cosupervisor_id": "uuid-1"
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "Supervisor and co-supervisor cannot be the same person",
  "error_code": "GROUP_PROFILE_DUPLICATE_SUPERVISORS",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_DUPLICATE_SUPERVISORS') {
  displayError('Supervisor and co-supervisor must be different people');
}
```

---

### Status Code: 403 Forbidden

#### Scenario 7: User Not Group Member

**Request:** (Valid PATCH data)

**Response:**
```json
{
  "success": false,
  "error": "You are not a member of this group",
  "error_code": "GROUP_PROFILE_NOT_MEMBER",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Only group members can update profile

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_NOT_MEMBER') {
  displayError('You do not have permission to update this group');
  redirectTo('/groups');
}
```

---

#### Scenario 8: User Not a Student

**Request:** (Valid PATCH data)

**Response:**
```json
{
  "success": false,
  "error": "Only students can update group profiles",
  "error_code": "GROUP_PROFILE_NOT_STUDENT",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Only students can manage group profiles

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_NOT_STUDENT') {
  displayError('Only student accounts can update group profiles');
}
```

---

### Status Code: 404 Not Found

#### Scenario 9: Group Not Found

**Request:** (Invalid group_id)

**Response:**
```json
{
  "success": false,
  "error": "Group not found",
  "error_code": "GROUP_PROFILE_GROUP_NOT_FOUND",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'GROUP_PROFILE_GROUP_NOT_FOUND') {
  displayError('Group no longer exists');
  redirectTo('/groups');
}
```

---

### Status Code: 422 Unprocessable Entity

#### Scenario 10: Invalid Request Format

**Request:**
```json
{
  "group": {
    "cohort_year": "not-a-number"
  }
}
```

**Response:**
```json
{
  "success": false,
  "error": "Multiple validation errors",
  "error_code": "VALIDATION_ERROR",
  "details": [
    {
      "field": "group.cohort_year",
      "message": "Input should be a valid integer",
      "code": "int_parsing"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_ERROR' && error.details) {
  error.details.forEach(detail => {
    displayFieldError(detail.field, detail.message);
  });
}
```

---

### Status Code: 500 Internal Server Error

#### Scenario 11: Database Error

**Response:**
```json
{
  "success": false,
  "error": "Failed to update group profile",
  "error_code": "SERVER_DATABASE_ERROR",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_DATABASE_ERROR') {
  displayError('Server error. Please try again later.');
  showRetryButton();
}
```

---

## 🌐 Network & Timeout Errors

### Network Timeout

**When:** Request takes too long (>30 seconds)

**Frontend Implementation:**
```javascript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 30000);

try {
  const response = await fetch(`/groups/${groupId}/invite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
    signal: controller.signal
  });
  clearTimeout(timeoutId);
} catch (error) {
  clearTimeout(timeoutId);
  if (error.name === 'AbortError') {
    displayError('Request timeout. Please check your connection and try again.');
    showRetryButton();
  }
}
```

---

### No Internet Connection

**Frontend Implementation:**
```javascript
if (!navigator.onLine) {
  displayError('No internet connection. Please check your network.');
}

window.addEventListener('offline', () => {
  displayError('Connection lost. Please reconnect.');
  disableForm();
});

window.addEventListener('online', () => {
  enableForm();
  showMessage('Connection restored');
});
```

---

## 📊 Error Handling Strategy

### Status Code Summary Table

| Status | Category | Retry? | User Message | Action |
|--------|----------|--------|--------------|--------|
| **200** | ✅ Success | - | Operation successful | Proceed |
| **400** | ❌ Client Error | No | Check your input | Show validation errors |
| **403** | ❌ Permission Error | No | Access denied | Redirect/Login |
| **404** | ❌ Not Found | No | Resource doesn't exist | Show error |
| **422** | ❌ Validation Error | No | Check highlighted fields | Display field errors |
| **500** | ❌ Server Error | Yes (3x) | Try again later | Retry with backoff |
| **Timeout** | ⚠️ Network | Yes (3x) | Connection timeout | Retry with backoff |

---

## 🎯 Frontend Integration Examples

### React Hook Implementation

```javascript
import { useState } from 'react';

const InviteForm = ({ groupId }) => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [successMessage, setSuccessMessage] = useState('');

  const handleInvite = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrors({});
    setSuccessMessage('');

    try {
      const response = await fetch(`/groups/${groupId}/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });

      if (response.ok) {
        const data = await response.json();
        setSuccessMessage(data.message);
        setEmail('');
      } else {
        const errorData = await response.json();
        
        // Handle based on error_code
        switch (errorData.error_code) {
          case 'VALIDATION_INVALID_EMAIL':
          case 'VALIDATION_MISSING_EMAIL':
            setErrors({ email: errorData.error });
            break;
            
          case 'GROUP_INVITE_USER_ALREADY_MEMBER':
            setErrors({ submit: 'This student is already in a group' });
            break;
            
          case 'GROUP_INVITE_CAPACITY_EXCEEDED':
            setErrors({ submit: 'Group has reached max capacity' });
            break;
            
          case 'GROUP_INVITE_ALREADY_PENDING':
            setErrors({ submit: 'Invitation already sent to this student' });
            break;
            
          case 'GROUP_INVITE_EMAIL_NOT_FOUND':
            setErrors({ email: 'Email not registered as student' });
            break;
            
          default:
            setErrors({ submit: errorData.error });
        }
      }
    } catch (error) {
      setErrors({ submit: 'Network error. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleInvite}>
      {errors.submit && <div className="alert alert-error">{errors.submit}</div>}
      {successMessage && <div className="alert alert-success">{successMessage}</div>}
      
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Student email"
        disabled={loading}
      />
      {errors.email && <span className="error">{errors.email}</span>}
      
      <button type="submit" disabled={loading}>
        {loading ? 'Sending...' : 'Send Invitation'}
      </button>
    </form>
  );
};
```

---

### Retry Logic with Exponential Backoff

```javascript
class GroupService {
  async inviteStudent(groupId, email, maxRetries = 3) {
    let retryCount = 0;
    const baseDelay = 1000;

    const attemptInvite = async () => {
      try {
        const response = await fetch(`/groups/${groupId}/invite`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email })
        });

        if (response.ok) {
          return await response.json();
        }

        const errorData = await response.json();
        
        // Retry on server errors
        if (errorData.error_code === 'SERVER_DATABASE_ERROR' || 
            errorData.error_code === 'SERVER_UNAVAILABLE') {
          if (retryCount < maxRetries) {
            retryCount++;
            const delay = baseDelay * Math.pow(2, retryCount - 1);
            await new Promise(resolve => setTimeout(resolve, delay));
            return attemptInvite();
          }
        }

        throw errorData;
      } catch (error) {
        if (retryCount < maxRetries && this.isNetworkError(error)) {
          retryCount++;
          const delay = baseDelay * Math.pow(2, retryCount - 1);
          await new Promise(resolve => setTimeout(resolve, delay));
          return attemptInvite();
        }
        throw error;
      }
    };

    return attemptInvite();
  }

  isNetworkError(error) {
    return error instanceof TypeError || error.name === 'AbortError';
  }
}
```

---

### Group Profile Update Handler

```javascript
const updateGroupProfile = async (groupId, updateData) => {
  try {
    const response = await fetch(`/groups/${groupId}/profile`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updateData)
    });

    if (response.ok) {
      const data = await response.json();
      showSuccessMessage('Group profile updated successfully');
      return data;
    }

    const errorData = await response.json();
    
    // Handle field-specific errors
    if (errorData.error_code === 'VALIDATION_ERROR' && errorData.details) {
      const fieldErrors = {};
      errorData.details.forEach(detail => {
        fieldErrors[detail.field] = detail.message;
      });
      
      // Apply errors to form
      Object.entries(fieldErrors).forEach(([field, message]) => {
        displayFieldError(field, message);
      });
    } else if (errorData.error_code === 'GROUP_PROFILE_DUPLICATE_SUPERVISORS') {
      displayError('Supervisor and co-supervisor must be different');
    } else if (errorData.error_code === 'GROUP_PROFILE_NOT_MEMBER') {
      redirectTo('/groups');
    } else {
      displayError(errorData.error);
    }
  } catch (error) {
    displayError('Network error. Please try again.');
  }
};
```

---

## 📑 Error Code Reference

### Invite API Error Codes

**Capacity & Status Errors:**
- `GROUP_INVITE_USER_ALREADY_MEMBER` - Invitee is in another group
- `GROUP_INVITE_CAPACITY_EXCEEDED` - Group is full or has 2 pending invites
- `GROUP_INVITE_ALREADY_PENDING` - Pending invite exists for this user
- `GROUP_INVITE_ALREADY_PROCESSED` - Invite already accepted/rejected
- `GROUP_INVITE_EXPIRED` - Invitation token expired (7 days)

**Permission & Membership Errors:**
- `GROUP_INVITE_NOT_MEMBER` - User not a member of group
- `GROUP_USER_ALREADY_MEMBER` - User already in another group

**Not Found Errors:**
- `GROUP_INVITE_EMAIL_NOT_FOUND` - Email not registered as student
- `GROUP_INVITE_GROUP_NOT_FOUND` - Group doesn't exist
- `GROUP_INVITE_NOT_FOUND` - Invalid invitation token

**Server Errors:**
- `GROUP_INVITE_EMAIL_FAILED` - Email sending failed
- `SERVER_DATABASE_ERROR` - Database error

### Group Profile API Error Codes

**Validation Errors:**
- `GROUP_PROFILE_INVALID_NAME` - Empty group name
- `GROUP_PROFILE_INVALID_PROJECT_TYPE` - Invalid project type
- `GROUP_PROFILE_INVALID_COHORT_YEAR` - Year out of range
- `GROUP_PROFILE_DUPLICATE_SUPERVISORS` - Same supervisor and co-supervisor

**Not Found Errors:**
- `GROUP_PROFILE_SUPERVISOR_NOT_FOUND` - Supervisor doesn't exist
- `GROUP_PROFILE_DOMAINS_NOT_FOUND` - One or more domains invalid
- `GROUP_PROFILE_GROUP_NOT_FOUND` - Group doesn't exist

**Permission Errors:**
- `GROUP_PROFILE_NOT_MEMBER` - Not a member of this group
- `GROUP_PROFILE_NOT_STUDENT` - Only students can update profiles

**Server Errors:**
- `SERVER_DATABASE_ERROR` - Database error

---

## 📞 Support

For issues or questions:
1. Check this documentation first
2. Review error_code and error message
3. Check if error is retryable (5xx, timeout)
4. Contact backend team with error_code and timestamp
5. Include request details and browser logs

---

## Version History

- **v1.0** (2025-12-10) - Initial comprehensive error handling documentation for group invite and profile update APIs
