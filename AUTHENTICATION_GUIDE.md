# FYPilot Backend Authentication Guide

This guide covers all authentication endpoints, OAuth flows, and frontend integration patterns for the FYPilot backend.

## Table of Contents
1. [Environment Configuration](#environment-configuration)
2. [Authentication Endpoints](#authentication-endpoints)
3. [OAuth Integration](#oauth-integration)
4. [Frontend Integration](#frontend-integration)
5. [Security Features](#security-features)
6. [Error Handling](#error-handling)

## Environment Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/fypilot

# JWT Configuration
JWT_SECRET=your-super-secret-jwt-key-here
JWT_ALGORITHM=HS256

# Session Configuration (for OAuth state)
SESSION_SECRET=your-session-secret-key-here

# Frontend URLs
FRONTEND_APP_URL=http://localhost:3000  # Your Next.js app
OAUTH_REDIRECT_ORIGIN=http://127.0.0.1:8000  # Your FastAPI backend

# OAuth Providers
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id  # Optional
GITHUB_CLIENT_SECRET=your-github-client-secret  # Optional

# Environment
ENV=development  # or "production"
```

## Authentication Endpoints

### 1. User Registration
**POST** `/auth/signup`

Creates a new user account with email/password authentication.

**Request Body:**
```json
{
  "full_name": "Alice Johnson",
  "email": "alice@example.com",
  "password": "SecureP@ss123",
  "role": "student"  // "student", "supervisor", or "admin"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "role": "student"
}
```

**Password Requirements:**
- Minimum 8 characters
- At least 1 uppercase letter (A-Z)
- At least 1 lowercase letter (a-z)
- At least 1 number (0-9)
- At least 1 special character from: `!@#$%^&*(),.?":{}|<>`

### 2. User Login
**POST** `/auth/login`

Authenticates user with email/password and returns JWT token.

**Request Body (Form Data):**
```
username: alice@example.com  # Note: "username" field contains email
password: SecureP@ss123
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "role": "student"
}
```

### 3. Get Current User Profile
**GET** `/auth/me`

Returns current authenticated user's profile information.

**Headers:**
```
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Alice Johnson",
  "email": "alice@example.com",
  "role": "student",
  "profile_avatar": null,
  "has_student_profile": true,
  "has_supervisor_profile": false,
  "has_admin_profile": false
}
```

### 4. Logout
**POST** `/auth/logout`

Logs out the current user and clears authentication cookies.

**Headers:**
```
Authorization: Bearer <jwt_token>
```

**Response:**
```
204 No Content
```

### 5. Verify Cookie Authentication
**GET** `/auth/verify-cookie`

Verifies authentication via secure cookies (for frontend cookie-based auth).

**Response:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Alice Johnson",
  "email": "alice@example.com",
  "role": "student",
  "profile_avatar": null,
  "has_student_profile": true,
  "has_supervisor_profile": false,
  "has_admin_profile": false
}
```

## OAuth Integration

### Supported Providers
- **Google** (OpenID Connect)
- **GitHub** (OAuth 2.0)

### OAuth Flow

#### 1. Initiate OAuth Login
**GET** `/auth/oauth/{provider}`

Starts OAuth flow with the specified provider.

**Parameters:**
- `provider`: "google" or "github"
- `return_to` (optional): Frontend route to redirect to after successful OAuth

**Example:**
```
GET /auth/oauth/google?return_to=/dashboard
GET /auth/oauth/github?return_to=/profile
```

**Response:** Redirects to provider's OAuth login page.

#### 2. OAuth Callback (Backend)
**GET** `/auth/oauth/{provider}/callback`

Handles OAuth callback from provider. This endpoint:
1. Exchanges OAuth code for tokens
2. Fetches user profile from provider
3. Creates or updates local user
4. Issues JWT token
5. Redirects to frontend

**Parameters:**
- `provider`: "google" or "github"
- `use_cookie` (optional, default: true): Use secure cookie instead of URL token

**Response:** Redirects to frontend with authentication.

#### 3. OAuth Callback Page (Frontend Bridge)
**GET** `/auth/oauth/callback`

Frontend bridge page for OAuth flows using URL tokens.

**Parameters:**
- `token` (optional): JWT token from OAuth flow
- `role` (optional): User role from OAuth flow
- `error` (optional): OAuth error message

**Response:** HTML page that handles token storage and redirects to frontend.

## Frontend Integration

### Option A: Secure Cookie Flow (Recommended)

1. **Initiate OAuth:**
   ```javascript
   // Redirect to OAuth provider
   window.location.href = 'http://127.0.0.1:8000/auth/oauth/google?return_to=/dashboard';
   ```

2. **Backend sets secure cookie and redirects to frontend**

3. **Frontend verifies authentication:**
   ```javascript
   // Check if user is authenticated via cookie
   const response = await fetch('http://127.0.0.1:8000/auth/verify-cookie', {
     credentials: 'include'  // Include cookies
   });
   
   if (response.ok) {
     const user = await response.json();
     // User is authenticated
   }
   ```

### Option B: URL Token Flow (Development)

1. **Initiate OAuth with use_cookie=false:**
   ```javascript
   window.location.href = 'http://127.0.0.1:8000/auth/oauth/google?return_to=/dashboard&use_cookie=false';
   ```

2. **Backend redirects to frontend with token in URL:**
   ```
   http://localhost:3000/dashboard?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...&role=student
   ```

3. **Frontend extracts token from URL:**
   ```javascript
   const urlParams = new URLSearchParams(window.location.search);
   const token = urlParams.get('token');
   const role = urlParams.get('role');
   
   if (token) {
     localStorage.setItem('auth_token', token);
     localStorage.setItem('user_role', role);
     // Clean URL
     window.history.replaceState({}, document.title, window.location.pathname);
   }
   ```

### Frontend Authentication State Management

```javascript
// Example React hook for authentication
const useAuth = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        // Try cookie-based auth first
        const response = await fetch('/auth/verify-cookie', {
          credentials: 'include'
        });
        
        if (response.ok) {
          const userData = await response.json();
          setUser(userData);
        } else {
          // Fallback to localStorage token
          const token = localStorage.getItem('auth_token');
          if (token) {
            const response = await fetch('/auth/me', {
              headers: {
                'Authorization': `Bearer ${token}`
              }
            });
            
            if (response.ok) {
              const userData = await response.json();
              setUser(userData);
            } else {
              localStorage.removeItem('auth_token');
            }
          }
        }
      } catch (error) {
        console.error('Auth check failed:', error);
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = (email, password) => {
    // Traditional login implementation
  };

  const logout = async () => {
    try {
      await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'include'
      });
    } catch (error) {
      console.error('Logout failed:', error);
    } finally {
      setUser(null);
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user_role');
    }
  };

  return { user, loading, login, logout };
};
```

## Security Features

### JWT Token Security
- **Algorithm:** HS256
- **Expiration:** Configurable (default: 7 days)
- **Claims:** User ID, role, expiration
- **Storage:** Secure HttpOnly cookies (recommended) or localStorage

### Password Security
- **Hashing:** bcrypt with salt rounds
- **Validation:** Strong password requirements
- **Storage:** Hashed passwords only

### OAuth Security
- **State Parameter:** CSRF protection
- **Secure Redirects:** Validated redirect URIs
- **Token Exchange:** Secure server-to-server communication
- **Email Verification:** Required for account creation

### Cookie Security
- **HttpOnly:** Prevents XSS attacks
- **Secure:** HTTPS only in production
- **SameSite:** CSRF protection
- **Domain:** Automatic domain setting

## Error Handling

### Common Error Responses

#### 400 Bad Request
```json
{
  "detail": "Email already registered"
}
```

#### 401 Unauthorized
```json
{
  "detail": "Invalid username or password"
}
```

#### 403 Forbidden
```json
{
  "detail": "Role student not authorized"
}
```

#### 500 Internal Server Error
```json
{
  "detail": "Error creating user account"
}
```

### OAuth Error Handling

OAuth errors are redirected to the frontend with error parameters:
```
http://localhost:3000/auth/error?error=access_denied
```

## Frontend Routes

### Recommended Frontend Routes

1. **`/auth/login`** - Login page with email/password and OAuth buttons
2. **`/auth/signup`** - Registration page
3. **`/auth/error`** - OAuth error handling page
4. **`/dashboard`** - Main dashboard (protected)
5. **`/profile`** - User profile page (protected)

### OAuth Button Implementation

```jsx
// Google OAuth Button
const GoogleLoginButton = () => {
  const handleGoogleLogin = () => {
    const returnTo = encodeURIComponent('/dashboard');
    window.location.href = `http://127.0.0.1:8000/auth/oauth/google?return_to=${returnTo}`;
  };

  return (
    <button onClick={handleGoogleLogin}>
      Continue with Google
    </button>
  );
};

// GitHub OAuth Button
const GitHubLoginButton = () => {
  const handleGitHubLogin = () => {
    const returnTo = encodeURIComponent('/dashboard');
    window.location.href = `http://127.0.0.1:8000/auth/oauth/github?return_to=${returnTo}`;
  };

  return (
    <button onClick={handleGitHubLogin}>
      Continue with GitHub
    </button>
  );
};
```

## Production Deployment

### Environment Variables for Production

```bash
# Production URLs
FRONTEND_APP_URL=https://app.yourdomain.com
OAUTH_REDIRECT_ORIGIN=https://api.yourdomain.com

# OAuth Redirect URIs (configure in provider dashboards)
# Google: https://api.yourdomain.com/auth/oauth/google/callback
# GitHub: https://api.yourdomain.com/auth/oauth/github/callback

# Security
ENV=production
JWT_SECRET=your-production-jwt-secret
SESSION_SECRET=your-production-session-secret
```

### CORS Configuration

Update `main.py` CORS origins for production:
```python
origins = [
    "https://app.yourdomain.com",
    "https://yourdomain.com",
]
```

This completes the comprehensive authentication system with OAuth integration and frontend support!
