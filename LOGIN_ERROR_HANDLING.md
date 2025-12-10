# 🔐 Login Error Handling Guide

## Overview

This document provides comprehensive information about all possible error scenarios in the `/auth/login` endpoint, including status codes, response objects, and frontend integration guidance.

**Endpoint:** `POST /auth/login`

---

## Table of Contents

1. [Success Response](#-success-response)
2. [Client Error Responses (4xx)](#-client-error-responses)
3. [Server Error Responses (5xx)](#-server-error-responses)
4. [Network Errors](#-network-errors)
5. [Error Handling Strategy](#-error-handling-strategy)
6. [Frontend Integration Examples](#-frontend-integration-examples)

---

## ✅ Success Response

### Status Code: 200 OK

Returned when authentication is successful.

**Response Body:**
```json
{
  "success": true,
  "message": "Login successful",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjNlNDU2Ny1lODliLTEyZDMtYTQ1Ni00MjY2MTQxNzQwMDAiLCJyb2xlIjoic3R1ZGVudCIsImV4cCI6MTcwMjE2NDA0Nn0.abc123...",
  "token_type": "bearer",
  "role": "student",
  "user": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "Ahmed Hassan",
    "email": "ahmed@example.com",
    "role": "student",
    "profile_avatar": "https://example.com/avatars/ahmed.jpg",
    "has_student_profile": true,
    "has_supervisor_profile": false,
    "has_admin_profile": false
  }
}
```

**Content-Type:** `application/json`

**Headers:** Standard HTTP headers

**What to do on Frontend:**
- ✅ Check `success: true` to confirm successful login
- ✅ Store `access_token` in secure storage (localStorage, sessionStorage, or HttpOnly cookie)
- ✅ Store `user_role` for routing logic
- ✅ Store `user_data` for UI customization
- ✅ Redirect user based on role and profile status

---

## ❌ Client Error Responses

### ✨ Normalized Error Structure

**All error responses now follow this consistent structure:**

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

- `success`: Always `false` for errors
- `error`: Main error message for display
- `error_code`: Machine-readable code for programmatic handling
- `details`: Array of field-specific errors (for validation errors, null for others)
- `timestamp`: ISO format timestamp

---

### Status Code: 422 Unprocessable Entity

Returned when request validation fails (missing fields, invalid formats, type errors).

#### Scenario 1: Missing Email Field

**Request:**
```json
{
  "password": "SecureP@ss123"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Field required",
  "error_code": "VALIDATION_INVALID_EMAIL",
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

**Cause:** Email field is required but not provided

**Frontend Action:**
```javascript
if (response.status === 422) {
  const error = await response.json();
  
  // Check error code for programmatic handling
  if (error.error_code === 'VALIDATION_INVALID_EMAIL') {
    displayFieldError('email', error.error);
  }
  
  // Or iterate through details for multiple errors
  error.details?.forEach(detail => {
    displayFieldError(detail.field, detail.message);
  });
}
```

---

#### Scenario 2: Missing Password Field

**Request:**
```json
{
  "email": "ahmed@example.com"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Field required",
  "error_code": "VALIDATION_MISSING_PASSWORD",
  "details": [
    {
      "field": "password",
      "message": "Field required",
      "code": "missing"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Password field is required but not provided

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_MISSING_PASSWORD') {
  displayFieldError('password', 'Password is required');
}
```

---

#### Scenario 3: Invalid Email Format

**Request:**
```json
{
  "email": "invalid-email",
  "password": "SecureP@ss123"
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

**Cause:** Email format is invalid (doesn't contain @, domain, etc.)

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_INVALID_EMAIL') {
  displayFieldError('email', 'Please enter a valid email address');
}
```

---

### Status Code: 401 Unauthorized

Returned when authentication fails.

#### Scenario 4: Invalid Email or Password

**Request:**
```json
{
  "email": "nonexistent@example.com",
  "password": "SecureP@ss123"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Invalid email or password",
  "error_code": "AUTH_INVALID_CREDENTIALS",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Headers:**
```
WWW-Authenticate: Bearer
```

**Cause:** Email doesn't exist OR password is incorrect

**Notes:**
- Generic message for security (doesn't reveal if email exists)
- Applies to both wrong email and wrong password scenarios

**Frontend Action:**
```javascript
if (error.error_code === 'AUTH_INVALID_CREDENTIALS') {
  displayError('Invalid email or password');
  
  // Optional: Show password recovery link
  showPasswordRecoveryOption();
  
  // Optional: Implement failed attempt tracking
  trackFailedLoginAttempt(email);
}
```

---

#### Scenario 5: Email Exists But Password Wrong

**Request:**
```json
{
  "email": "ahmed@example.com",
  "password": "WrongPassword123!"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Invalid email or password",
  "error_code": "AUTH_INVALID_CREDENTIALS",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Email exists in database but password doesn't match

**Frontend Action:**
```javascript
if (error.error_code === 'AUTH_INVALID_CREDENTIALS') {
  displayError('Invalid email or password');

  // Optionally implement account lockout after N failed attempts
  if (failedAttempts >= 5) {
    showAccountLockoutMessage();
    disableLoginForm();
    startLockoutTimer(15); // Lock for 15 minutes
  }
}
```

---

#### Scenario 6: Email Doesn't Exist

**Request:**
```json
{
  "email": "doesnotexist@example.com",
  "password": "SecureP@ss123"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Invalid email or password",
  "error_code": "AUTH_INVALID_CREDENTIALS",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Email is not registered in the system

**Frontend Action:**
```javascript
if (error.error_code === 'AUTH_INVALID_CREDENTIALS') {
  displayError('Invalid email or password');

  // For better UX, you could provide signup option
  showSignupSuggestion();
}
```

---

### Status Code: 422 Unprocessable Entity

Returned when request validation fails (schema mismatch, invalid data types).

#### Scenario 7: Email Not String Type

**Request:**
```json
{
  "email": 12345,
  "password": "SecureP@ss123"
}
```

**Response:**
```json
{
  "success": false,
  "error": "Input should be a valid string",
  "error_code": "VALIDATION_INVALID_EMAIL",
  "details": [
    {
      "field": "email",
      "message": "Input should be a valid string",
      "code": "string_type"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Email must be string, not number

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_INVALID_EMAIL') {
  displayFieldError('email', 'Please check your input format');
}
```

---

#### Scenario 8: Password Not String Type

**Request:**
```json
{
  "email": "ahmed@example.com",
  "password": 123456
}
```

**Response:**
```json
{
  "success": false,
  "error": "Input should be a valid string",
  "error_code": "VALIDATION_MISSING_PASSWORD",
  "details": [
    {
      "field": "password",
      "message": "Input should be a valid string",
      "code": "string_type"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Password must be string, not number

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_MISSING_PASSWORD') {
  displayFieldError('password', 'Password must be text');
}
```

---

#### Scenario 9: Multiple Validation Errors

**Request:**
```json
{
  "email": 123,
  "password": 456
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
      "field": "email",
      "message": "Input should be a valid string",
      "code": "string_type"
    },
    {
      "field": "password",
      "message": "Input should be a valid string",
      "code": "string_type"
    }
  ],
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Multiple fields have validation errors

**Frontend Action:**
```javascript
if (error.error_code === 'VALIDATION_ERROR' && error.details) {
  error.details.forEach(detail => {
    displayFieldError(detail.field, detail.message);
  });
}
```

---

## ❌ Server Error Responses

### Status Code: 500 Internal Server Error

Returned when server encounters an unexpected error.

#### Scenario 10: Database Connection Failure

**Response:**
```json
{
  "success": false,
  "error": "Login process failed",
  "error_code": "SERVER_DATABASE_ERROR",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Database connection pool exhausted or database is down

**Log Entry (Backend):**
```
ERROR - Error during login: connection pool overflow
```

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_DATABASE_ERROR') {
  displayError('Server error. Please try again later.');
  
  // Suggest retry
  showRetryButton();
  
  // Log to monitoring service
  logError({
    endpoint: '/auth/login',
    errorCode: error.error_code,
    timestamp: error.timestamp,
    email: emailUsed
  });
}
```

---

#### Scenario 11: Database Query Error

**Response:**
```json
{
  "success": false,
  "error": "Login process failed",
  "error_code": "SERVER_DATABASE_ERROR",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Error executing SQL query (e.g., connection timeout, syntax error)

**Log Entry (Backend):**
```
ERROR - Error during login: Query timed out after 30 seconds
```

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_DATABASE_ERROR') {
  displayError('Database error. Please try again in a moment.');
  showRetryButton();
}
```

---

#### Scenario 12: Token Generation Failure

**Response:**
```json
{
  "success": false,
  "error": "Login process failed",
  "error_code": "SERVER_INTERNAL_ERROR",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** JWT token generation failed (e.g., signing key issue)

**Log Entry (Backend):**
```
ERROR - Error during login: JWT signing failed
```

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_INTERNAL_ERROR') {
  displayError('Authentication failed. Please try again.');
}
```

---

#### Scenario 13: Unexpected Server Exception

**Response:**
```json
{
  "success": false,
  "error": "An unexpected error occurred",
  "error_code": "SERVER_INTERNAL_ERROR",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Unhandled exception in login flow

**Log Entry (Backend):**
```
ERROR - Error during login: NoneType object is not subscriptable
```

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_INTERNAL_ERROR') {
  displayError('An unexpected error occurred. Please try again later.');
  logErrorToMonitoring({
    endpoint: '/auth/login',
    errorCode: error.error_code,
    timestamp: error.timestamp
  });
}
```

---

### Status Code: 503 Service Unavailable

Returned when server is temporarily unavailable.

#### Scenario 14: Server Under Maintenance

**Response:**
```json
{
  "success": false,
  "error": "Service temporarily unavailable",
  "error_code": "SERVER_UNAVAILABLE",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Server is under maintenance or temporarily down

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_UNAVAILABLE') {
  displayError('Service is temporarily unavailable. Please try again shortly.');
  
  showMaintenanceNotice();
  disableLoginForm();
  
  // Auto-retry after delay
  setTimeout(() => {
    enableLoginForm();
    showRetryMessage();
  }, 300000); // Retry after 5 minutes
}
```

---

#### Scenario 15: Database Not Available

**Response:**
```json
{
  "success": false,
  "error": "Service temporarily unavailable",
  "error_code": "SERVER_UNAVAILABLE",
  "details": null,
  "timestamp": "2025-12-10T10:30:00Z"
}
```

**Cause:** Database server is down or unreachable

**Frontend Action:**
```javascript
if (error.error_code === 'SERVER_UNAVAILABLE') {
  displayError('Database service is temporarily down.');
  showRetryButton();
}
```

---

## 🌐 Network Errors

Network errors occur **before** the backend responds.

### Network Timeout

**Scenario 16: Request Takes Too Long**

**When:** Request doesn't receive response within timeout period (typically 30+ seconds)

**Frontend Implementation:**
```javascript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 seconds

try {
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
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

**Scenario 17: Complete Network Failure**

**When:** No internet connection or network is unreachable

**Frontend Implementation:**
```javascript
try {
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
} catch (error) {
  if (error instanceof TypeError) {
    // Network error - no connection
    if (!navigator.onLine) {
      displayError('No internet connection. Please check your network.');
      showOfflineIndicator();
    } else {
      displayError('Failed to reach server. Please try again.');
    }
  }
}
```

---

### CORS Error (Cross-Origin Request Blocked)

**Scenario 18: Security Policy Violation**

**When:** Frontend origin doesn't match backend allowed origins

**Browser Error:**
```
Access to fetch at 'https://api.example.com/auth/login' 
from origin 'https://frontend.example.com' 
has been blocked by CORS policy
```

**Frontend Implementation:**
```javascript
try {
  const response = await fetch('/auth/login', { /* ... */ });
} catch (error) {
  if (error.message.includes('CORS')) {
    displayError('Connection blocked by security policy. Contact support.');
    logError({
      type: 'CORS_ERROR',
      origin: window.location.origin,
      endpoint: '/auth/login'
    });
  }
}
```

**Backend Fix (if needed):**
```python
# In settings
CORS_ORIGINS = [
  "https://frontend.example.com",
  "http://localhost:3000"
]
```

---

### DNS Resolution Failure

**Scenario 19: Server Hostname Cannot Be Resolved**

**When:** DNS lookup fails for backend domain

**Browser Error:**
```
getaddrinfo ENOTFOUND api.example.com
```

**Frontend Implementation:**
```javascript
displayError('Cannot reach the server. Please check your connection or try again later.');
logError({
  type: 'DNS_ERROR',
  endpoint: '/auth/login'
});
```

---

### Connection Refused

**Scenario 20: Server Actively Refused Connection**

**When:** Backend server is down or port is closed

**Browser Error:**
```
Connection refused (ECONNREFUSED)
```

**Frontend Implementation:**
```javascript
displayError('Server is not responding. Please try again later.');
showStatusPageLink(); // Link to status page
```

---

## 📊 Error Handling Strategy

### Status Code Summary Table

| Status | Category | Retry? | User Message | Action |
|--------|----------|--------|--------------|--------|
| **200** | ✅ Success | - | Login successful | Store token & redirect |
| **400** | ❌ Client Error | No | Invalid input | Show validation errors |
| **401** | ❌ Auth Error | No* | Invalid credentials | Show password recovery |
| **422** | ❌ Validation Error | No | Check your input | Display field errors |
| **500** | ❌ Server Error | Yes (3x) | Try again later | Retry with exponential backoff |
| **503** | ⚠️ Maintenance | Yes (delayed) | Service down | Show maintenance message |
| **Timeout** | ⚠️ Network | Yes (3x) | Connection timeout | Retry with backoff |
| **No Network** | ⚠️ Offline | Yes (auto) | No internet | Show offline indicator |

*401 can retry after showing forgot password option

---

## 🎯 Frontend Integration Examples

### React Hook Implementation

```javascript
import { useState } from 'react';

const LoginForm = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [failedAttempts, setFailedAttempts] = useState(0);

  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    // Client-side validation
    if (!email || !password) {
      setError('Email and password are required');
      setIsLoading(false);
      return;
    }

    if (!isValidEmail(email)) {
      setError('Please enter a valid email address');
      setIsLoading(false);
      return;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: controller.signal,
        credentials: 'include'
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        // 200 OK - Success
        const data = await response.json();
        if (data.success) {
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('user_role', data.role);
          localStorage.setItem('user_data', JSON.stringify(data.user));
          
          // Redirect based on role
          if (data.user.has_student_profile) {
            window.location.href = '/dashboard/student';
          } else if (data.user.has_supervisor_profile) {
            window.location.href = '/dashboard/supervisor';
          } else {
            window.location.href = '/dashboard';
          }
        }
      } else {
        // All error responses now have normalized structure
        const errorData = await response.json();
        
        // Handle based on error_code for programmatic control
        switch (errorData.error_code) {
          case 'VALIDATION_MISSING_EMAIL':
          case 'VALIDATION_MISSING_PASSWORD':
          case 'VALIDATION_INVALID_EMAIL':
            // Display field-specific errors
            if (errorData.details && errorData.details.length > 0) {
              const fieldError = errorData.details[0];
              setError(`${fieldError.field}: ${fieldError.message}`);
            } else {
              setError(errorData.error);
            }
            break;
            
          case 'AUTH_INVALID_CREDENTIALS':
            // Track failed attempts
            setFailedAttempts(failedAttempts + 1);
            setError(errorData.error);
            
            if (failedAttempts >= 4) {
              showPasswordRecoveryModal();
            }
            break;
            
          case 'SERVER_INTERNAL_ERROR':
          case 'SERVER_DATABASE_ERROR':
            // Retry-eligible errors
            setError(errorData.error);
            showRetryButton();
            break;
            
          case 'SERVER_UNAVAILABLE':
            // Service unavailable
            setError(errorData.error);
            break;
            
          case 'VALIDATION_ERROR':
            // Multiple validation errors
            if (errorData.details && errorData.details.length > 0) {
              const allErrors = errorData.details.map(d => `${d.field}: ${d.message}`).join(', ');
              setError(allErrors);
            } else {
              setError(errorData.error);
            }
            break;
            
          default:
            // Fallback for unknown errors
            setError(errorData.error || 'An error occurred');
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        setError('Request timeout. Please check your connection and try again.');
      } else if (error instanceof TypeError) {
        if (!navigator.onLine) {
          setError('No internet connection. Please check your network.');
        } else {
          setError('Connection failed. Please try again.');
        }
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const isValidEmail = (email) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  return (
    <form onSubmit={handleLogin}>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        disabled={isLoading}
        required
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        disabled={isLoading}
        required
      />
      {error && <div className="error-message">{error}</div>}
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Logging in...' : 'Login'}
      </button>
    </form>
  );
};

export default LoginForm;
```

---

### Retry Logic with Exponential Backoff

```javascript
class LoginService {
  async login(email, password) {
    const maxRetries = 3;
    const baseDelay = 1000; // 1 second
    let retryCount = 0;

    const attemptLogin = async () => {
      try {
        const response = await fetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });

        // Handle response
        if (response.ok) {
          const data = await response.json();
          return data;
        }
        
        const errorData = await response.json();
        
        // Retry on server errors based on error_code
        if (errorData.error_code === 'SERVER_INTERNAL_ERROR' || 
            errorData.error_code === 'SERVER_DATABASE_ERROR' ||
            errorData.error_code === 'SERVER_UNAVAILABLE') {
          if (retryCount < maxRetries) {
            retryCount++;
            const delay = baseDelay * Math.pow(2, retryCount - 1); // Exponential backoff
            await this.sleep(delay);
            return attemptLogin();
          }
        }
        
        // Don't retry on client/auth/validation errors
        throw errorData;
      } catch (error) {
        if (retryCount < maxRetries && this.isRetryableError(error)) {
          retryCount++;
          const delay = baseDelay * Math.pow(2, retryCount - 1);
          await this.sleep(delay);
          return attemptLogin();
        }
        throw error;
      }
    };

    return attemptLogin();
  }

  isRetryableError(error) {
    return (
      error.name === 'AbortError' || // Timeout
      error instanceof TypeError // Network error
    );
  }

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
```

---

### Account Lockout After Failed Attempts

```javascript
class LoginController {
  async handleLogin(email, password) {
    const MAX_FAILED_ATTEMPTS = 5;
    const LOCKOUT_DURATION = 15 * 60 * 1000; // 15 minutes

    // Check if account is locked
    const lockoutKey = `login_lockout_${email}`;
    const lockoutTime = localStorage.getItem(lockoutKey);

    if (lockoutTime && Date.now() < parseInt(lockoutTime)) {
      const remainingMinutes = Math.ceil(
        (parseInt(lockoutTime) - Date.now()) / 60000
      );
      throw new Error(`Account locked. Try again in ${remainingMinutes} minutes`);
    }

    // Check failed attempts
    const attemptsKey = `login_attempts_${email}`;
    let attempts = parseInt(localStorage.getItem(attemptsKey) || '0');

    if (attempts >= MAX_FAILED_ATTEMPTS) {
      // Lock account
      localStorage.setItem(lockoutKey, (Date.now() + LOCKOUT_DURATION).toString());
      localStorage.removeItem(attemptsKey);
      throw new Error('Too many failed login attempts. Account locked for 15 minutes.');
    }

    try {
      const response = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();
      
      if (response.ok && data.success) {
        // Clear attempts on success
        localStorage.removeItem(attemptsKey);
        return data;
      } else if (data.error_code === 'AUTH_INVALID_CREDENTIALS') {
        // Increment failed attempts
        attempts++;
        localStorage.setItem(attemptsKey, attempts.toString());

        if (attempts >= MAX_FAILED_ATTEMPTS) {
          localStorage.setItem(lockoutKey, (Date.now() + LOCKOUT_DURATION).toString());
          throw new Error('Too many failed attempts. Account locked for 15 minutes.');
        }

        throw new Error(`Invalid credentials. ${MAX_FAILED_ATTEMPTS - attempts} attempts remaining.`);
      }

      throw new Error(data.error || 'Login failed');
    } catch (error) {
      throw error;
    }
  }
}
```

---

## 📋 Best Practices

### Do's ✅

- ✅ Always store tokens securely (HttpOnly cookies preferred)
- ✅ Implement timeout for network requests
- ✅ Show generic error messages for security
- ✅ Implement failed attempt tracking
- ✅ Provide password recovery option
- ✅ Handle all status codes (including 503)
- ✅ Log errors to monitoring service
- ✅ Implement exponential backoff for retries
- ✅ Show offline indicator when network fails

### Don'ts ❌

- ❌ Store sensitive tokens in localStorage (use HttpOnly cookies)
- ❌ Show detailed error messages that reveal system info
- ❌ Retry on 401 (auth errors) endlessly
- ❌ Block user after 1 failed attempt
- ❌ Ignore CORS errors
- ❌ Don't implement any timeout
- ❌ Don't validate input on frontend only
- ❌ Send credentials in URL or unencrypted
- ❌ Hardcode API endpoints in frontend

---

## 🔒 Security Considerations

1. **Never reveal if email exists:** Both "email not found" and "wrong password" return the same message
2. **Use HTTPS only:** Always transmit login data over encrypted connection
3. **Implement rate limiting:** Prevent brute force attacks
4. **Account lockout:** Lock after N failed attempts
5. **JWT expiration:** Tokens should expire (typically 1 hour)
6. **Refresh tokens:** Implement refresh token rotation
7. **CORS validation:** Ensure frontend origin is whitelisted
8. **Input validation:** Validate on both frontend and backend

---

## 🧪 Testing Scenarios

Use these test cases to verify error handling:

```bash
# Test 1: Valid credentials
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"ValidPass123!"}'

# Test 2: Invalid email format
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"invalid","password":"ValidPass123!"}'

# Test 3: Missing email
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"ValidPass123!"}'

# Test 4: Wrong password
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"WrongPassword!"}'

# Test 5: Non-existent email
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"nonexistent@example.com","password":"ValidPass123!"}'
```

---

## 📞 Support

For issues or questions about login error handling:
1. Check this documentation first
2. Review backend logs for detailed error messages
3. Contact the backend team with error details and timestamp
4. Include browser console logs and network tab information

---

## 📑 Error Code Reference

### Authentication Errors
- `AUTH_INVALID_CREDENTIALS` - Invalid email or password combination

### Validation Errors
- `VALIDATION_MISSING_EMAIL` - Email field is required but not provided
- `VALIDATION_MISSING_PASSWORD` - Password field is required but not provided
- `VALIDATION_INVALID_EMAIL` - Email format is invalid or wrong data type
- `VALIDATION_ERROR` - Multiple validation errors occurred

### Server Errors
- `SERVER_INTERNAL_ERROR` - Unexpected server error (JWT signing, exceptions)
- `SERVER_DATABASE_ERROR` - Database connection or query error
- `SERVER_UNAVAILABLE` - Service temporarily unavailable (maintenance, database down)

### Frontend Usage Example
```javascript
switch (error.error_code) {
  case 'AUTH_INVALID_CREDENTIALS':
    // Show forgot password option
    break;
  case 'VALIDATION_INVALID_EMAIL':
    // Focus email field
    break;
  case 'SERVER_DATABASE_ERROR':
    // Show retry button
    break;
  default:
    // Generic error handling
}
```

---

## Version History

- **v2.0** (2025-12-10) - Normalized error response structure
  - 🎉 Added consistent error format with `success`, `error`, `error_code`, `details`, `timestamp`
  - ✅ Added machine-readable error codes for programmatic handling
  - ✅ Updated all 15 error scenarios with new format
  - ✅ Updated all frontend examples (React Hook, retry logic, account lockout)
  - ✅ Added error code reference section

- **v1.0** (2025-12-10) - Initial comprehensive login error handling documentation
