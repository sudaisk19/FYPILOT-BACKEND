# Password Reset System Guide

This guide documents the complete password reset functionality implemented in the FYPilot backend.

## Overview

The password reset system provides:
- **Secure token generation** for password reset links
- **Email delivery** with professional HTML templates
- **Server-side validation** for password requirements
- **Token expiration** and one-time use security
- **Comprehensive error handling** and logging

## API Endpoints

### 1. Forgot Password

#### **Endpoint:** `POST /auth/forgot-password`
- **Purpose:** Send password reset email to user
- **Authentication:** Not required

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "message": "If the email exists, a password reset link has been sent"
}
```

**Security Features:**
- ✅ **Email Privacy**: Same response whether email exists or not
- ✅ **Token Expiration**: Reset tokens expire in 1 hour
- ✅ **One-time Use**: Tokens are marked as used after password reset
- ✅ **Token Cleanup**: Old unused tokens are deleted when new ones are created

### 2. Reset Password

#### **Endpoint:** `POST /auth/reset-password`
- **Purpose:** Reset user password using reset token
- **Authentication:** Not required (uses reset token)

**Request Body:**
```json
{
  "token": "secure-reset-token-from-email",
  "new_password": "NewSecureP@ss123",
  "confirm_password": "NewSecureP@ss123"
}
```

**Response:**
```json
{
  "message": "Password has been reset successfully"
}
```

**Password Requirements:**
- Minimum 8 characters
- At least 1 uppercase letter (A-Z)
- At least 1 lowercase letter (a-z)
- At least 1 number (0-9)
- At least 1 special character from: `!@#$%^&*(),.?":{}|<>`

## Database Schema

### Password Reset Token Model

```python
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship to user
    user = relationship("User", backref="password_reset_tokens")
```

## Email Template

The system sends professional HTML emails with:
- **Responsive design** that works on all devices
- **Clear call-to-action** button for password reset
- **Security warnings** about token expiration
- **Fallback link** for copy-paste access
- **Professional branding** with FYPilot logo

## Frontend Integration

### 1. Forgot Password Page

```javascript
// pages/ForgotPasswordPage.jsx
import { useState } from 'react';

const ForgotPasswordPage = () => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      const response = await fetch('/auth/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email })
      });

      if (response.ok) {
        const data = await response.json();
        setMessage(data.message);
      } else {
        const error = await response.json();
        setMessage('Error: ' + error.detail);
      }
    } catch (error) {
      setMessage('Network error: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="forgot-password-page">
      <h1>Forgot Password</h1>
      <p>Enter your email address and we'll send you a link to reset your password.</p>
      
      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Sending...' : 'Send Reset Link'}
        </button>
      </form>
      
      {message && (
        <div className={`message ${message.includes('Error') ? 'error' : 'success'}`}>
          {message}
        </div>
      )}
      
      <p>
        <a href="/auth/login">Back to Login</a>
      </p>
    </div>
  );
};
```

### 2. Reset Password Page

```javascript
// pages/ResetPasswordPage.jsx
import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

const ResetPasswordPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    new_password: '',
    confirm_password: ''
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [errors, setErrors] = useState({});

  const token = searchParams.get('token');

  useEffect(() => {
    if (!token) {
      navigate('/auth/forgot-password');
    }
  }, [token, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    setErrors({});

    // Client-side validation
    const newErrors = {};
    if (formData.new_password !== formData.confirm_password) {
      newErrors.confirm_password = 'Passwords do not match';
    }
    if (formData.new_password.length < 8) {
      newErrors.new_password = 'Password must be at least 8 characters';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      setLoading(false);
      return;
    }

    try {
      const response = await fetch('/auth/reset-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          token,
          new_password: formData.new_password,
          confirm_password: formData.confirm_password
        })
      });

      if (response.ok) {
        const data = await response.json();
        setMessage(data.message);
        setTimeout(() => {
          navigate('/auth/login');
        }, 2000);
      } else {
        const error = await response.json();
        setMessage('Error: ' + error.detail);
      }
    } catch (error) {
      setMessage('Network error: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return <div>Invalid reset link</div>;
  }

  return (
    <div className="reset-password-page">
      <h1>Reset Password</h1>
      <p>Enter your new password below.</p>
      
      <form onSubmit={handleSubmit}>
        <div>
          <input
            type="password"
            placeholder="New Password"
            value={formData.new_password}
            onChange={(e) => setFormData({...formData, new_password: e.target.value})}
            required
          />
          {errors.new_password && (
            <span className="error">{errors.new_password}</span>
          )}
        </div>
        
        <div>
          <input
            type="password"
            placeholder="Confirm New Password"
            value={formData.confirm_password}
            onChange={(e) => setFormData({...formData, confirm_password: e.target.value})}
            required
          />
          {errors.confirm_password && (
            <span className="error">{errors.confirm_password}</span>
          )}
        </div>
        
        <button type="submit" disabled={loading}>
          {loading ? 'Resetting...' : 'Reset Password'}
        </button>
      </form>
      
      {message && (
        <div className={`message ${message.includes('Error') ? 'error' : 'success'}`}>
          {message}
        </div>
      )}
      
      <div className="password-requirements">
        <h3>Password Requirements:</h3>
        <ul>
          <li>Minimum 8 characters</li>
          <li>At least 1 uppercase letter (A-Z)</li>
          <li>At least 1 lowercase letter (a-z)</li>
          <li>At least 1 number (0-9)</li>
          <li>At least 1 special character from: !@#$%^&*(),.?":{}|&lt;&gt;</li>
        </ul>
      </div>
    </div>
  );
};
```

### 3. React Query Integration

```javascript
// hooks/usePasswordReset.js
import { useMutation } from '@tanstack/react-query';

export const useForgotPassword = () => {
  return useMutation({
    mutationFn: async ({ email }) => {
      const response = await fetch('/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      
      return response.json();
    }
  });
};

export const useResetPassword = () => {
  return useMutation({
    mutationFn: async ({ token, new_password, confirm_password }) => {
      const response = await fetch('/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password, confirm_password })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      
      return response.json();
    }
  });
};
```

## Complete Password Reset Flow

### **Step 1: User Requests Password Reset**
1. User visits forgot password page
2. Enters email address
3. Frontend calls: `POST /auth/forgot-password`
4. Backend generates secure token and sends email
5. User receives email with reset link

### **Step 2: User Clicks Reset Link**
1. User clicks link in email: `https://yourapp.com/auth/reset-password?token=abc123`
2. Frontend extracts token from URL
3. Shows reset password form

### **Step 3: User Resets Password**
1. User enters new password and confirmation
2. Frontend calls: `POST /auth/reset-password`
3. Backend validates token and updates password
4. User is redirected to login page

## Security Features

### ✅ **Token Security**
- **Cryptographically Secure**: Uses `secrets.token_urlsafe(32)`
- **Unique Tokens**: Each token is unique in the database
- **Expiration**: Tokens expire after 1 hour
- **One-time Use**: Tokens are marked as used after password reset

### ✅ **Email Security**
- **No Email Enumeration**: Same response for existing/non-existing emails
- **Secure Links**: Reset links contain secure tokens
- **Clear Instructions**: Email includes security warnings

### ✅ **Password Security**
- **Strong Requirements**: Enforced server-side validation
- **Secure Hashing**: Passwords are hashed with bcrypt
- **Confirmation**: Password confirmation is validated

### ✅ **Database Security**
- **Token Cleanup**: Old unused tokens are automatically deleted
- **Audit Trail**: All password resets are logged
- **Foreign Key Constraints**: Proper database relationships

## Error Handling

### **Common Error Responses:**

#### **400 Bad Request**
```json
{
  "detail": "Invalid or expired reset token"
}
```

#### **400 Password Validation**
```json
{
  "detail": "Password must contain at least one uppercase letter (A-Z)"
}
```

#### **404 Not Found**
```json
{
  "detail": "User not found"
}
```

#### **500 Internal Server Error**
```json
{
  "detail": "Failed to send password reset email"
}
```

## Environment Configuration

Make sure your `.env` file has the email configuration:

```bash
# Email Configuration
MAILER_PROVIDER=ethereal  # or "sendgrid" for production

# For Ethereal (Development)
ETHEREAL_SMTP_HOST=smtp.ethereal.email
ETHEREAL_SMTP_PORT=587
ETHEREAL_SMTP_USER=your-ethereal-username
ETHEREAL_SMTP_PASS=your-ethereal-password

# For SendGrid (Production)
SENDGRID_API_KEY=your-sendgrid-api-key
FROM_EMAIL=noreply@yourdomain.com

# Frontend URL for reset links
FRONTEND_APP_URL=http://localhost:3000
```

## Testing the Password Reset Flow

### **1. Test Forgot Password**
```bash
curl -X POST http://localhost:8000/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

### **2. Test Reset Password**
```bash
curl -X POST http://localhost:8000/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{
    "token": "your-reset-token",
    "new_password": "NewSecureP@ss123",
    "confirm_password": "NewSecureP@ss123"
  }'
```

This password reset system provides enterprise-grade security with a user-friendly experience!








