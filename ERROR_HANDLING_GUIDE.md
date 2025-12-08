# Error Handling Guide - Login & Signup APIs

## Overview
The application uses a standardized error response format across all endpoints. Errors are handled through three main exception handlers in `app/core/exceptions.py`.

---

## Error Response Formats

### 1. **Validation Error (422 Unprocessable Entity)**

**When it occurs:**
- Invalid email format
- Missing required fields
- Invalid data types
- Password validation failures

**Response Format:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "field.name",
        "message": "Error message describing the validation failure"
      }
    ]
  }
}
```

**Examples:**

**Missing email field:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "email",
        "message": "Field required"
      }
    ]
  }
}
```

**Invalid email format:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "email",
        "message": "value is not a valid email address"
      }
    ]
  }
}
```

**Multiple validation errors:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "password",
        "message": "Password must be at least 8 characters long\nPassword must contain at least one uppercase letter (A-Z)"
      },
      {
        "field": "confirm_password",
        "message": "Passwords do not match"
      }
    ]
  }
}
```

---

### 2. **HTTP Exception Errors (400, 401, 404, 500, etc.)**

**When it occurs:**
- Business logic errors (email already exists)
- Authentication failures (wrong credentials)
- Not found errors
- Server errors

**Response Format:**
```json
{
  "status": "error",
  "error": {
    "code": <status_code>,
    "type": "HTTPException",
    "message": "Error message describing the issue"
  }
}
```

---

## Signup API Errors

### Error 1: Email Already Registered (400)
**Endpoint:** `POST /signup`
**When:** User tries to register with an email that already exists

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 400,
    "type": "HTTPException",
    "message": "Email already registered"
  }
}
```

### Error 2: Validation Error (422)
**Endpoint:** `POST /signup`
**When:** Request data doesn't meet schema requirements

**Valid Request Schema:**
```json
{
  "full_name": "John Doe",
  "email": "john@example.com",
  "password": "SecurePass123!",
  "role": "student"
}
```

**Password Requirements:**
- Minimum 8 characters
- At least 1 uppercase letter (A-Z)
- At least 1 lowercase letter (a-z)
- At least 1 number (0-9)
- At least 1 special character: `!@#$%^&*(),.?":{}|<>`

**Invalid password example:**
```json
{
  "full_name": "John Doe",
  "email": "john@example.com",
  "password": "simple",
  "role": "student"
}
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "password",
        "message": "Password must be at least 8 characters long\nPassword must contain at least one uppercase letter (A-Z)\nPassword must contain at least one lowercase letter (a-z)\nPassword must contain at least one number (0-9)\nPassword must contain at least one special character from: !@#$%^&*(),.?\"{|}|<>"
      }
    ]
  }
}
```

### Error 3: Server Error (500)
**Endpoint:** `POST /signup`
**When:** Unexpected database or server error

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 500,
    "type": "InternalServerError",
    "message": "An unexpected error occurred."
  }
}
```

---

## Login API Errors

### Error 1: Invalid Credentials (401)
**Endpoint:** `POST /login`
**When:** Email doesn't exist OR password is incorrect

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 401,
    "type": "HTTPException",
    "message": "Invalid email or password"
  }
}
```

### Error 2: Validation Error (422)
**Endpoint:** `POST /login`
**When:** Request data doesn't meet schema requirements

**Valid Request Schema:**
```json
{
  "email": "user@example.com",
  "password": "Password123!",
  "remember_me": false
}
```

**Missing email example:**
```json
{
  "password": "Password123!"
}
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "email",
        "message": "Field required"
      }
    ]
  }
}
```

**Invalid email format:**
```json
{
  "email": "invalid-email",
  "password": "Password123!"
}
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      {
        "field": "email",
        "message": "value is not a valid email address"
      }
    ]
  }
}
```

### Error 3: Server Error (500)
**Endpoint:** `POST /login`
**When:** Unexpected database or server error

**Response:**
```json
{
  "status": "error",
  "error": {
    "code": 500,
    "type": "InternalServerError",
    "message": "An unexpected error occurred."
  }
}
```

---

## Success Responses

### Signup Success (201)
```json
{
  "message": "Account created successfully",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "student",
  "user": {
    "user_id": "a5be8e06-8f5c-4f89-9169-25ca19d54c1c",
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

### Login Success (200)
```json
{
  "message": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "student",
  "user": {
    "user_id": "a5be8e06-8f5c-4f89-9169-25ca19d54c1c",
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

---

## Error Response Structure Breakdown

All error responses follow this consistent structure:

```
{
  "status": "error",                    // Always "error" for error responses
  "error": {
    "code": <http_status_code>,         // HTTP status code (400, 401, 422, 500, etc.)
    "type": "ValidationError" | "HTTPException" | "InternalServerError",
    "message": "...",                   // Single message (for HTTP exceptions)
    "details": [                        // Array of field-specific errors (validation only)
      {
        "field": "field.name",
        "message": "Error description"
      }
    ]
  }
}
```

### Key Differences:

**Validation Errors (422):**
- Contains `details` array with field-level errors
- Each error has `field` and `message`
- Can have multiple field errors

**HTTP Exceptions (400, 401, 404, 500):**
- Contains single `message` field
- No `details` array
- One error per response

---

## Implementation Locations

1. **Exception Handlers:** `app/core/exceptions.py`
   - `validation_exception_handler()` - Handles 422 errors
   - `http_exception_handler()` - Handles 400, 401, 404, 500 errors
   - `unhandled_exception_handler()` - Catches all unhandled exceptions

2. **Auth Routes:** `app/auth/routes.py`
   - `signup()` - Signup endpoint (lines 100-160)
   - `login_for_access_token()` - Login endpoint (lines 175-250)

3. **Auth Schema:** `app/schemas/auth_schema.py`
   - `UserCreateSchema` - Signup request schema with password validation
   - `LoginRequest` - Login request schema
   - `SignupResponse` - Signup response schema
   - `LoginResponse` - Login response schema

---

## Common Error Scenarios

| Scenario | Status Code | Type | Message |
|----------|-------------|------|---------|
| Missing email field | 422 | ValidationError | Field required |
| Invalid email format | 422 | ValidationError | value is not a valid email address |
| Weak password | 422 | ValidationError | Password must contain... (detailed requirements) |
| Email already exists (signup) | 400 | HTTPException | Email already registered |
| Wrong email/password (login) | 401 | HTTPException | Invalid email or password |
| Database error | 500 | InternalServerError | An unexpected error occurred. |

---

## Frontend-friendly Error Messages and Implementation Guide ✅

This section provides short, user-friendly messages for each HTTP error code and shows how your frontend can render them consistently using the error object our API returns.

### Why this helps
- The backend returns structured error objects (see above). You can use the same mapping across your UI to present clear messages for forms, modals, toasts, and pages.
- The samples below are copy-paste-ready and include suggested i18n keys.

---

### 400 Bad Request — User-friendly message
- Backend reason: Business logic or invalid request that isn't a schema validation failure (e.g. email already exists).
- Short message to show: "Something's wrong with your request — please review and try again." (or use the examples below for specific cases.)
- Suggested UI treatment: inline error or toast depending on context.

Common case (Signup):
- Backend error: `Email already registered` (code 400)
- Frontend text (recommended): "This email is already registered. Try logging in or reset your password."
- i18n key suggestion: `auth.signup.email_already_registered`

Example server response (400):
```json
{
  "status": "error",
  "error": {
    "code": 400,
    "type": "HTTPException",
    "message": "Email already registered"
  }
}
```

Frontend behaviour (example): show inline banner near email field and a link to the login page.

---

### 401 Unauthorized — User-friendly message
- Backend reason: Invalid authentication or expired/invalid token (login failures).
- Short message to show: "Invalid email or password. Please try again or reset your password." or for token errors: "Please sign in to continue."
- Suggested UI treatment: form-level error for login; protected routes should redirect to sign-in and show a small toast.

Example server response (401):
```json
{
  "status": "error",
  "error": {
    "code": 401,
    "type": "HTTPException",
    "message": "Invalid email or password"
  }
}
```

Frontend behaviour (example): display inline message near submit button and trigger password reset link if user chooses.

---

### 404 Not Found — User-friendly message
- Backend reason: Resource missing, invalid URL, or user not allowed to access resource.
- Short message to show: "We couldn't find what you were looking for." or contextual: "Group not found — it might have been removed."
- Suggested UI treatment: show a friendly page or a toast depending on where it occurs.
- i18n key suggestion: `errors.not_found`

Example server response (404):
```json
{
  "status": "error",
  "error": {
    "code": 404,
    "type": "HTTPException",
    "message": "Group not found"
  }
}
```

Frontend behaviour (example): show a 404 page with suggested next actions (go to dashboard, contact admin).

---

### 422 Validation Error — User-friendly message
- Backend reason: Pydantic validation errors (missing fields / wrong formats / password rules). The response includes a `details` array identifying exact fields.
- Short message to show: "Please check the highlighted fields and fix any mistakes."
- Suggested UI treatment: map `details` to form fields and show inline errors; also show a short general message at the top of the form.

Example server response (422):
```json
{
  "status": "error",
  "error": {
    "code": 422,
    "type": "ValidationError",
    "details": [
      { "field": "email", "message": "value is not a valid email address" },
      { "field": "password", "message": "Password must be at least 8 characters long" }
    ]
  }
}
```

Frontend mapping example (JS/TS):
```js
// errorObj is the whole JSON returned from server
if (errorObj?.error?.type === 'ValidationError') {
  const fieldErrors = (errorObj.error.details || []).reduce((acc, err) => {
    // `field` might be 'project.name' or 'email' depending on the endpoint
    acc[err.field] = err.message;
    return acc;
  }, {});

  // set form errors with your form library
  // e.g., form.setErrors(fieldErrors)
}
```

Recommended top-level message for forms: `"Please fix the highlighted fields to continue."` (i18n: `forms.validation.fix_fields`)

---

### 500 Internal Server Error — User-friendly message
- Backend reason: Unexpected server/database errors.
- Short message to show: "Something went wrong on our end — please try again in a few minutes." (Avoid exposing technical details.)
- Suggested UI treatment: a central toast and a retry button; optionally send an error report.
- i18n key suggestion: `errors.internal_server`

Example server response (500):
```json
{
  "status": "error",
  "error": {
    "code": 500,
    "type": "InternalServerError",
    "message": "An unexpected error occurred."
  }
}
```

Frontend behaviour: show a friendly toast that lets the user retry; if the problem persists, show a helpful next-step (contact support link).

---

## Quick mapping cheat-sheet for frontend

1. If `error.type === 'ValidationError'` → map `error.details` to form fields; show inline errors + small banner message. (Status 422)
2. If `error.code === 400` and message contains a specific string (e.g. "Email already registered") → show contextual helper (e.g., "Try logging in" button). (Status 400)
3. If `error.code === 401` → show sign-in modal or redirect to login, with message "Please sign in to continue" or "Invalid credentials" as appropriate. (Status 401)
4. If `error.code === 404` → show friendly 404 page with next steps. (Status 404)
5. If `error.code === 500` → show toast "Something went wrong" and offer retry/contact support. (Status 500)

### Example i18n keys (single source of truth)
- `errors.email_already_registered`
- `errors.invalid_credentials`
- `errors.not_found`
- `errors.validation.fix_fields`
- `errors.internal_server`

---

If you'd like, I can also add small code snippets for React (Formik / React Hook Form) or Vue to map errors into form libraries — tell me which framework you use and I'll append tailored examples.

---

## Copy-ready frontend snippets
Below are tiny drop-in helpers you can adapt to your codebase (React Hook Form, Formik and a simple Vue example). They demonstrate parsing the server error object returned by our API and converting it into UI-friendly form errors and toasts.

### React Hook Form — example
```js
// parseApiError.js
export function parseApiError(errorObj) {
  // Default fallback message
  const fallback = 'Something went wrong. Please try again.';

  if (!errorObj || !errorObj.error) return { message: fallback };

  const { code, type, message, details } = errorObj.error;

  if (type === 'ValidationError' && Array.isArray(details)) {
    // Map to field errors
    const fieldErrors = details.reduce((acc, err) => {
      acc[err.field] = err.message;
      return acc;
    }, {});
    return { code, type, fieldErrors, message: 'Please fix the highlighted fields.' };
  }

  // HTTP exceptions have a single message
  if (code === 400 && message?.includes('Email already registered')) {
    return { code, message: 'This email is already registered. Try logging in.' };
  }

  if (code === 401) return { code, message: 'Invalid credentials. Try again.' };
  if (code === 404) return { code, message: 'Not found. The resource might have been removed.' };
  if (code === 500) return { code, message: 'Something went wrong on our end. Please try in a few minutes.' };

  return { code, message: message || fallback };
}

/* Usage in a React Hook Form submit handler
try {
  await api.signup(values);
} catch (err) {
  const parsed = parseApiError(err.response?.data);
  if (parsed.fieldErrors) form.setError(parsed.fieldErrors);
  else showToast(parsed.message);
}
*/
```

### Formik — example
```js
// inside your onSubmit
try {
  await api.login(values);
} catch (err) {
  const parsed = parseApiError(err.response?.data);
  if (parsed.fieldErrors) formik.setErrors(parsed.fieldErrors);
  else formik.setStatus({ globalError: parsed.message });
}
```

### Minimal Vue (Composition API) — example
```js
import { ref } from 'vue'

const globalError = ref(null)

async function submit() {
  try {
    await api.call(payload)
  } catch (err) {
    const parsed = parseApiError(err.response?.data)
    if (parsed.fieldErrors) {
      // your field error integration here
      // setFieldErrors(parsed.fieldErrors)
    } else {
      globalError.value = parsed.message
    }
  }
}
```

---

If you'd like, I can tailor these further for a different framework or add i18n-aware helpers that pick messages from a translation bundle instead of using hard-coded strings.

