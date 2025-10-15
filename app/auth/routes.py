# app/auth/routes.py

"""
Authentication Routes Module

This module implements all authentication-related endpoints including:
1. Traditional email/password authentication
2. OAuth2 social authentication (Google, GitHub)
3. User session management
4. Profile information retrieval

Authentication Flow:
- Sign up: Create new user account
- Login: Authenticate and receive JWT
- OAuth: Social login with external providers
- Me: Get current user profile
- Logout: Invalidate current session

Security Features:
- Password hashing
- JWT token-based authentication
- Role-based access control
- OAuth2 integration
"""

import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.oauth import oauth
from app.auth.supabase_auth import get_current_user
from app.auth.utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import settings

# Application imports
from app.db import get_db
from app.models.password_reset import PasswordResetToken
from app.models.user import RoleEnum, User
from app.schemas.auth_schema import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RoleUpdateRequest,
    RoleUpdateResponse,
)

# Schema imports
from app.schemas.user import MeResponse
from app.schemas.user import UserCreate as UserCreateSchema
from app.services.mailer import send_password_reset_email

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router with authentication tag for OpenAPI docs
router = APIRouter(tags=["auth"])

# Import the shared Bearer token scheme
from app.auth.supabase_auth import oauth2_scheme


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=LoginResponse
)
async def signup(user_in: UserCreateSchema, db: AsyncSession = Depends(get_db)):
    """
    Register a new user account with password validation.

    Flow:
    1. Validate password requirements
    2. Validate email uniqueness
    3. Create new user record
    4. Issue JWT token for immediate login

    Password Requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 number
    - At least 1 special character from: !@#$%^&*(),.?":{}|<>

    Args:
        user_in (UserCreateSchema): User registration data
        db (AsyncSession): Database session

    Returns:
        TokenResponse: JWT token and user role

    Raises:
        HTTPException(400):
            - Email already registered
            - Password requirements not met (with specific error messages)
        HTTPException(500): Database error
    """
    try:
        # Check for existing user with same email
        existing = await db.execute(select(User).where(User.email == user_in.email))
        if existing.scalars().first():
            logger.warning(f"Signup attempt with existing email: {user_in.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create new user record (base user only, no role-specific profiles)
        user = User(
            full_name=user_in.full_name,
            email=user_in.email,
            password_hash=hash_password(user_in.password),
            role=RoleEnum(user_in.role),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"New user registered: {user.email} with role {user.role}")

        # Determine token expiration based on remember_me
        if user_in.remember_me:
            # Remember me: 30 days for production, 7 days for development
            expires_delta = (
                timedelta(days=30)
                if settings.ENV.lower() == "production"
                else timedelta(days=7)
            )
        else:
            # Normal signup: 6 hours for dev, 1 hour for production (handled by create_access_token default)
            expires_delta = None

        # Generate and return JWT token with role
        token = create_access_token(
            sub=str(user.user_id), role=user.role.value, expires_delta=expires_delta
        )

        # Return enhanced response with full user data
        return {
            "message": "Account created successfully",
            "access_token": token,
            "token_type": "bearer",
            "role": user.role.value,
            "user": {
                "user_id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.value,
                "profile_avatar": user.profile_avatar,
                "has_student_profile": False,  # New user won't have profiles yet
                "has_supervisor_profile": False,
                "has_admin_profile": False,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during user signup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user account",
        )


@router.post("/login", response_model=LoginResponse)
async def login_for_access_token(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and issue JWT token.

    Flow:
    1. Find user by email
    2. Verify password
    3. Generate and return JWT token with full user data

    Args:
        login_data (LoginRequest): Login credentials with email and password
        db (AsyncSession): Database session

    Returns:
        LoginResponse: JWT token, role, and full user data

    Raises:
        HTTPException(401): Invalid credentials
        HTTPException(500): Database error
    """
    try:
        # Find user by email with all profile relationships loaded
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.supervisor_profile),
                selectinload(User.admin_profile),
            )
            .where(User.email == login_data.email)
        )
        user = result.scalar_one_or_none()

        # Verify user exists and password is correct
        if not user or not verify_password(login_data.password, user.password_hash):
            logger.warning(f"Failed login attempt for email: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Handle role value for both enum and string types
        role_val = user.role.value if hasattr(user.role, "value") else user.role

        # Determine token expiration based on remember_me
        if login_data.remember_me:
            # Remember me: 30 days for production, 7 days for development
            expires_delta = (
                timedelta(days=30)
                if settings.ENV.lower() == "production"
                else timedelta(days=7)
            )
        else:
            # Normal login: 6 hours for dev, 1 hour for production (handled by create_access_token default)
            expires_delta = None

        # Generate and return JWT token with role
        token = create_access_token(
            sub=str(user.user_id), role=role_val, expires_delta=expires_delta
        )

        logger.info(f"Successful login for user: {user.email}")

        # Return enhanced response with full user data
        return {
            "message": "Login successful",
            "access_token": token,
            "token_type": "bearer",
            "role": role_val,
            "user": {
                "user_id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "role": role_val,
                "profile_avatar": user.profile_avatar,
                "has_student_profile": user.student_profile is not None,
                "has_supervisor_profile": user.supervisor_profile is not None,
                "has_admin_profile": user.admin_profile is not None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login process failed",
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, token=Depends(oauth2_scheme)):
    """
    Enhanced logout endpoint with cookie clearing.

    This endpoint:
    1. Validates the current token
    2. Clears any authentication cookies
    3. Returns success response

    Args:
        request (Request): FastAPI request object
        response (Response): FastAPI response object
        token (str): Current JWT token

    Returns:
        Response: 204 No Content on successful logout

    Raises:
        HTTPException(401): Invalid token
    """
    try:
        # Verify token is valid before allowing logout
        token_str = token.credentials  # HTTPBearer returns an object with .credentials
        decode_access_token(token_str)

        # Clear authentication cookies
        response.delete_cookie(
            key="auth_token",
            httponly=True,
            secure=settings.ENV.lower() in {"prod", "production"},
            samesite="lax",
        )

        logger.info("User logged out successfully")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        logger.warning(f"Logout attempted with invalid token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's profile information.

    This endpoint returns:
    - Basic user information (id, name, email)
    - User role
    - Profile completion status flags

    Args:
        current_user (User): Current authenticated user (from dependency)

    Returns:
        MeResponse: User profile data with role and profile flags

    Note:
        This endpoint is useful for:
        - Initial app load to determine user state
        - UI customization based on user role
        - Profile completion workflows
    """
    # Handle role value for both enum and string types
    role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )

    # Build response with profile completion flags
    response = MeResponse(
        user_id=current_user.user_id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=role,
        # Profile flags for conditional UI rendering
        has_student_profile=current_user.student_profile is not None,
        has_supervisor_profile=current_user.supervisor_profile is not None,
        has_admin_profile=current_user.admin_profile is not None,
    )

    logger.debug(f"Profile data retrieved for user: {current_user.email}")
    return response


# ---- OAuth (Google / GitHub) Authentication Routes ----

# Supported OAuth providers
SUPPORTED_PROVIDERS = {"google", "github"}


@router.get("/oauth/{provider}")
async def oauth_login(
    provider: str,
    request: Request,
    return_to: str = Query(
        None, description="Frontend route to redirect to after successful OAuth"
    ),
    source: str = Query(
        None, description="Source page: 'login' or 'signup' to determine behavior"
    ),
):
    """
    Initiate OAuth login flow for specified provider.

    Flow:
    1. Validate provider
    2. Store return_to URL in session for post-auth redirect
    3. Generate OAuth redirect URL with state parameter
    4. Redirect user to provider login

    Args:
        provider (str): OAuth provider ("google" or "github")
        request (Request): FastAPI request object
        return_to (str, optional): Frontend route to redirect to after OAuth

    Returns:
        RedirectResponse: Redirect to provider's OAuth login

    Raises:
        HTTPException(400): Unsupported provider
    """
    if provider not in SUPPORTED_PROVIDERS:
        logger.warning(f"Attempted login with unsupported provider: {provider}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider"
        )

    # Store return_to and source in session for post-auth redirect
    if return_to:
        request.session["oauth_return_to"] = return_to
        logger.info(f"Stored return_to URL: {return_to}")

    if source:
        request.session["oauth_source"] = source
        logger.info(f"Stored OAuth source: {source}")

    # Generate callback URL for OAuth flow
    redirect_uri = f"{settings.oauth_redirect_origin}/auth/oauth/{provider}/callback"

    logger.info(f"Initiating {provider} OAuth flow")
    return await oauth.create_client(provider).authorize_redirect(request, redirect_uri)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    use_cookie: bool = Query(
        True, description="Use secure cookie instead of URL token"
    ),
):
    """
    Handle OAuth callback and create/login user.

    Flow:
    1. Validate provider
    2. Exchange OAuth code for tokens
    3. Fetch user profile from provider
    4. Create or update local user
    5. Issue JWT token and redirect to frontend

    Two redirect options:
    - Option A (use_cookie=True): Set secure HttpOnly cookie + redirect to frontend
    - Option B (use_cookie=False): Redirect to frontend with token in URL

    Args:
        provider (str): OAuth provider ("google" or "github")
        request (Request): FastAPI request object
        db (AsyncSession): Database session
        use_cookie (bool): Whether to use secure cookie (recommended)

    Returns:
        RedirectResponse: Redirect to frontend with authentication

    Raises:
        HTTPException(400): Invalid provider or missing email
        HTTPException(500): OAuth or database error
    """
    try:
        if provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider"
            )

        # Initialize OAuth client and get token
        client = oauth.create_client(provider)
        token_data = await client.authorize_access_token(request)

        # Extract user information based on provider
        email = None
        full_name = None

        if provider == "google":
            # Google provides user info in ID token
            userinfo = await client.parse_id_token(request, token_data)
            email = userinfo.get("email")
            full_name = userinfo.get("name")

        elif provider == "github":
            # GitHub requires additional API calls
            resp = await client.get("https://api.github.com/user", token=token_data)
            profile = resp.json()
            email = profile.get("email")

            # If email not in primary profile, check emails endpoint
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails", token=token_data
                )
                # Find primary and verified email
                for e in emails_resp.json():
                    if e.get("primary") and e.get("verified"):
                        email = e["email"]
                        break

            full_name = profile.get("name") or profile.get("login")

        if not email:
            logger.error(f"No email available from {provider} OAuth flow")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not available from provider",
            )

        # Find or create user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        # Track if this is a new user
        is_new_user = False

        if not user:
            # Create new user with default student role
            logger.info(f"Creating new user from {provider} OAuth: {email}")
            user = User(
                full_name=full_name,
                email=email,
                password_hash="oauth",  # Special marker for OAuth users
                role=RoleEnum.student,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            is_new_user = True
        else:
            logger.info(f"Existing user logged in via {provider}: {email}")

        # Generate JWT token
        role_val = user.role.value if hasattr(user.role, "value") else user.role
        jwt_token = create_access_token(sub=str(user.user_id), role=role_val)

        # Get return_to URL and source from session
        return_to = request.session.pop("oauth_return_to", "/dashboard")
        source = request.session.pop("oauth_source", None)

        # Build frontend redirect URL based on user status and source
        frontend_url = str(settings.frontend_app_url)

        # Determine redirect behavior
        if is_new_user:  # This is a new user (just created)
            if source == "signup":
                # New user from signup page → redirect to role selection
                redirect_url = f"{frontend_url}/auth/role-selection"
                logger.info(f"New user from signup page, redirecting to role selection")
            else:
                # New user from login page → redirect to default dashboard
                redirect_url = f"{frontend_url}{return_to}"
                logger.info(f"New user from login page, redirecting to: {return_to}")
        else:  # Existing user
            if source == "login":
                # Existing user from login page → redirect to dashboard
                redirect_url = f"{frontend_url}{return_to}"
                logger.info(
                    f"Existing user from login page, redirecting to: {return_to}"
                )
            else:
                # Existing user from signup page → redirect to dashboard (they're already signed up)
                redirect_url = f"{frontend_url}{return_to}"
                logger.info(
                    f"Existing user from signup page, redirecting to: {return_to}"
                )

        if use_cookie:
            # Option A: Set secure HttpOnly cookie and redirect
            response = RedirectResponse(
                url=redirect_url, status_code=status.HTTP_302_FOUND
            )

            # Set secure cookie with JWT token
            is_production = settings.ENV.lower() in {"prod", "production"}
            response.set_cookie(
                key="auth_token",
                value=jwt_token,
                httponly=True,  # Prevent XSS attacks
                secure=is_production,  # HTTPS only in production
                samesite="lax",  # CSRF protection
                max_age=60 * 60 * 24 * 7,  # 7 days
                domain=None,  # Will be set automatically based on request
            )

            logger.info(
                f"OAuth success: Redirecting to {redirect_url} with secure cookie"
            )
            return response
        else:
            # Option B: Redirect with token in URL (less secure, for development)
            params = {"token": jwt_token, "role": role_val}
            redirect_url_with_token = f"{redirect_url}?{urlencode(params)}"

            logger.info(
                f"OAuth success: Redirecting to {redirect_url_with_token} with URL token"
            )
            return RedirectResponse(
                url=redirect_url_with_token, status_code=status.HTTP_302_FOUND
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during {provider} OAuth callback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth authentication failed",
        )


@router.get("/oauth/callback")
async def oauth_callback_page(
    request: Request,
    token: str = Query(None, description="JWT token from OAuth flow"),
    role: str = Query(None, description="User role from OAuth flow"),
    error: str = Query(None, description="OAuth error message"),
):
    """
    Frontend OAuth callback page handler.

    This endpoint serves as a bridge for OAuth flows that use URL tokens.
    It provides a simple HTML page that can extract the token from URL
    and redirect to the appropriate frontend route.

    Args:
        request (Request): FastAPI request object
        token (str, optional): JWT token from OAuth flow
        role (str, optional): User role from OAuth flow
        error (str, optional): OAuth error message

    Returns:
        HTMLResponse: Simple HTML page for token handling
    """
    if error:
        # Handle OAuth errors
        error_url = f"{settings.frontend_app_url}/auth/error?error={error}"
        return RedirectResponse(url=error_url, status_code=status.HTTP_302_FOUND)

    if not token:
        # No token provided, redirect to login
        return RedirectResponse(
            url=f"{settings.frontend_app_url}/auth/login",
            status_code=status.HTTP_302_FOUND,
        )

    # Return HTML page that handles the token
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authentication Successful</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                   margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 400px; margin: 50px auto; background: white; 
                        padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .success {{ color: #10b981; font-size: 18px; margin-bottom: 20px; }}
            .loading {{ color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success">✓ Authentication Successful</div>
            <div class="loading">Redirecting to dashboard...</div>
        </div>
        <script>
            // Store token in localStorage and redirect
            localStorage.setItem('auth_token', '{token}');
            localStorage.setItem('user_role', '{role or "student"}');
            
            // Redirect to dashboard after a short delay
            setTimeout(() => {{
                window.location.href = '{settings.frontend_app_url}/dashboard';
            }}, 1000);
        </script>
    </body>
    </html>
    """

    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html_content, status_code=200)


@router.get("/verify-cookie")
async def verify_cookie_auth(request: Request):
    """
    Verify authentication via cookie and return user info.

    This endpoint allows the frontend to check if a user is authenticated
    via secure cookies without requiring the token in the Authorization header.

    Args:
        request (Request): FastAPI request object

    Returns:
        MeResponse: User profile data if authenticated

    Raises:
        HTTPException(401): No valid authentication cookie
    """
    # Check for auth token in cookies
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication cookie found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Verify the token
        claims = decode_access_token(auth_token)
        user_id = UUID(claims["sub"])
        role = claims.get("role")

        # Get database session
        async with get_db() as db:
            result = await db.execute(
                select(User).where(User.user_id == user_id).where(User.role == role)
            )
            user = result.scalars().first()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Return user profile
            role_val = user.role.value if hasattr(user.role, "value") else user.role
            return MeResponse(
                user_id=user.user_id,
                full_name=user.full_name,
                email=user.email,
                role=role_val,
                has_student_profile=user.student_profile is not None,
                has_supervisor_profile=user.supervisor_profile is not None,
                has_admin_profile=user.admin_profile is not None,
            )

    except Exception as e:
        logger.warning(f"Cookie authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication cookie",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.patch("/update-role", response_model=RoleUpdateResponse)
async def update_user_role(
    role_data: RoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user role after OAuth signup.

    This endpoint allows users to update their role after OAuth signup,
    typically used on the role selection page.

    Args:
        role_data (RoleUpdateRequest): New role selection
        current_user (User): Current authenticated user
        db (AsyncSession): Database session

    Returns:
        RoleUpdateResponse: Updated user data with new role

    Raises:
        HTTPException(400): Invalid role
        HTTPException(500): Database error
    """
    try:
        new_role = role_data.role

        # Validate role
        if new_role not in ["student", "supervisor", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be 'student', 'supervisor', or 'admin'",
            )

        # Update user role
        current_user.role = RoleEnum(new_role)
        await db.commit()
        await db.refresh(current_user)

        # Generate new JWT token with updated role
        role_val = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else current_user.role
        )
        new_token = create_access_token(sub=str(current_user.user_id), role=role_val)

        # Build updated user data
        updated_user = {
            "user_id": current_user.user_id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "role": role_val,
            "profile_avatar": current_user.profile_avatar,
            "has_student_profile": current_user.student_profile is not None,
            "has_supervisor_profile": current_user.supervisor_profile is not None,
            "has_admin_profile": current_user.admin_profile is not None,
        }

        logger.info(f"User {current_user.email} updated role to {new_role}")

        return RoleUpdateResponse(
            message="User role updated successfully", role=role_val, user=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role",
        )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    request_data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """
    Send password reset email to user.

    This endpoint:
    1. Validates that the email exists in the system
    2. Generates a secure reset token
    3. Stores the token in the database with expiration
    4. Sends password reset email with the reset link

    Args:
        request_data (ForgotPasswordRequest): Email address
        db (AsyncSession): Database session

    Returns:
        ForgotPasswordResponse: Success message

    Raises:
        HTTPException(404): Email not found
        HTTPException(500): Email sending failed
    """
    try:
        # Find user by email
        result = await db.execute(select(User).where(User.email == request_data.email))
        user = result.scalars().first()

        if not user:
            # Don't reveal if email exists or not for security
            logger.warning(
                f"Password reset requested for non-existent email: {request_data.email}"
            )
            return ForgotPasswordResponse(
                message="If the email exists, a password reset link has been sent"
            )

        # Generate secure reset token
        reset_token = secrets.token_urlsafe(32)

        # Set token expiration (1 hour from now)
        expires_at = datetime.utcnow() + timedelta(hours=1)

        # Create password reset token record
        reset_token_record = PasswordResetToken(
            user_id=user.user_id, token=reset_token, expires_at=expires_at, used=False
        )

        # Delete any existing unused tokens for this user
        await db.execute(
            delete(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.user_id)
            .where(PasswordResetToken.used == False)
        )

        # Save new token
        db.add(reset_token_record)
        await db.commit()

        # Generate reset link
        reset_link = (
            f"{settings.frontend_app_url}/auth/reset-password?token={reset_token}"
        )

        # Send password reset email
        try:
            await send_password_reset_email(
                to_email=user.email, user_name=user.full_name, reset_link=reset_link
            )
            logger.info(f"Password reset email sent to: {user.email}")
        except Exception as email_error:
            logger.error(f"Failed to send password reset email: {str(email_error)}")
            # Delete the token if email sending failed
            await db.delete(reset_token_record)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send password reset email",
            )

        return ForgotPasswordResponse(
            message="If the email exists, a password reset link has been sent"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in forgot password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process password reset request",
        )


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    request_data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """
    Reset user password using reset token.

    This endpoint:
    1. Validates the reset token
    2. Checks if token is not expired and not used
    3. Validates new password requirements
    4. Updates user password
    5. Marks token as used

    Args:
        request_data (ResetPasswordRequest): Reset token and new password
        db (AsyncSession): Database session

    Returns:
        ResetPasswordResponse: Success message

    Raises:
        HTTPException(400): Invalid or expired token
        HTTPException(404): Token not found
        HTTPException(500): Database error
    """
    try:
        # Find the reset token
        result = await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token == request_data.token)
            .where(PasswordResetToken.used == False)
        )
        reset_token_record = result.scalars().first()

        if not reset_token_record:
            logger.warning(
                f"Invalid or used reset token attempted: {request_data.token}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )

        # Check if token is expired
        if datetime.utcnow() > reset_token_record.expires_at:
            logger.warning(f"Expired reset token attempted: {request_data.token}")
            # Mark token as used to prevent reuse
            reset_token_record.used = True
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token has expired",
            )

        # Get the user
        user_result = await db.execute(
            select(User).where(User.user_id == reset_token_record.user_id)
        )
        user = user_result.scalars().first()

        if not user:
            logger.error(f"User not found for reset token: {request_data.token}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # Hash the new password
        new_password_hash = hash_password(request_data.new_password)

        # Update user password
        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()

        # Mark token as used
        reset_token_record.used = True
        reset_token_record.updated_at = datetime.utcnow()

        # Commit changes
        await db.commit()

        logger.info(f"Password reset successful for user: {user.email}")

        return ResetPasswordResponse(message="Password has been reset successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password",
        )
