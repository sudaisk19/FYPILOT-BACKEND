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
- Me: Get current user profil
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
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
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
from app.models.admin import Admin
from app.models.domain import Domain
from app.models.group import Group, GroupMember
from app.models.industry import Industry
from app.models.password_reset import PasswordResetToken
from app.models.project import Project
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.supervisor_domain import SupervisorDomain
from app.models.supervisor_industry import SupervisorIndustry
from app.models.user import RoleEnum, User
from app.schemas.auth_schema import (
    AdminInfo,
    DomainInfo,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GroupInfo,
    IndustryInfo,
    LoginRequest,
    LoginResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RoleUpdateRequest,
    RoleUpdateResponse,
    SignupResponse,
    StudentInfo,
    SupervisedGroup,
    SupervisorInfo,
    SystemStats,
    UserProfileResponse,
)

# Schema imports
from app.schemas.user import MeResponse
from app.schemas.user import UserCreate as UserCreateSchema
from app.services.mailer import send_password_reset_email

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(tags=["authentication"])

# Simple Bearer token scheme for JWT extraction
from fastapi.security import HTTPBearer

oauth2_scheme = HTTPBearer()


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=SignupResponse
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
        SignupResponse: Success message, JWT token and user data

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

        # Generate and return JWT token with role
        token = create_access_token(sub=str(user.user_id), role=user.role.value)

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
        LoginResponse: JWT token and user data

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
        user = result.scalars().first()

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

        # Generate and return JWT token with role
        token = create_access_token(sub=str(user.user_id), role=role_val)

        logger.info(f"Successful login for user: {user.email}")

        # Return enhanced response with full user data
        return {
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
async def logout(
    request: Request, response: Response, token: str = Depends(oauth2_scheme)
):
    """
    Enhanced logout endpoint with cookie clearing.

    This endpoint:
    1. Validates the current token
    2. Clears any authentication cookies
    3. Returns success response

    Args:
        request (Request): FastAPI request object
        response (Response): FastAPI response object
           token_str = token.credentials  # HTTPBearer returns an object with .credentials
        decode_access_token(token_str)


    Returns:
        Response: 204 No Content on successful logout

    Raises:
        HTTPException(401): Invalid token
    """
    try:
        # Extract token from HTTPBearer object
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


@router.get("/me", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user's profile information with role-specific data.

    This endpoint returns:
    - Basic user information (id, name, email, role, avatar)
    - Role-specific information:
      * Students: Group information (group_id, project_id, supervisor_ids, etc.)
      * Supervisors: Supervised groups, domains, industries, capacity info
      * Admins: System statistics and admin profile info

    Args:
        current_user (User): Current authenticated user (from dependency)
        db (AsyncSession): Database session

    Returns:
        UserProfileResponse: User profile data with role-specific information

    Note:
        This endpoint is useful for:
        - Initial app load to determine user state and get all necessary IDs
        - UI customization based on user role and relationships
        - Client-side state management with all required IDs
    """
    # Handle role value for both enum and string types
    role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )

    # Initialize role-specific information
    group_info = None
    supervisor_info = None
    admin_info = None
    student_info = None

    try:
        if role == "student":
            student_info = await get_student_info(current_user.user_id, db)
            group_info = await get_student_group_info(current_user.user_id, db)
        elif role == "supervisor":
            supervisor_info = await get_supervisor_info(current_user.user_id, db)
        elif role == "admin":
            admin_info = await get_admin_info(current_user.user_id, db)
    except Exception as e:
        logger.error(
            f"Error fetching role-specific info for user {current_user.user_id}: {e}"
        )
        # Continue with basic info even if role-specific info fails

    response = UserProfileResponse(
        user_id=current_user.user_id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=role,
        profile_avatar=current_user.profile_avatar,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        student_info=student_info,
        group_info=group_info,
        supervisor_info=supervisor_info,
        admin_info=admin_info,
    )

    logger.debug(
        f"Profile data retrieved for user: {current_user.email} (role: {role})"
    )
    return response


# Helper functions for role-specific data fetching
async def get_student_info(user_id: UUID, db: AsyncSession) -> Optional[StudentInfo]:
    """Get student profile information"""
    try:
        # Get student profile
        student_result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = student_result.scalar_one_or_none()

        if not student:
            return None

        return StudentInfo(
            roll_number=student.roll_number,
            department=student.department,
            cgpa=float(student.cgpa) if student.cgpa else None,
            interests=student.interests,
            experience=student.experience,
            portfolio_projects=student.portfolio_projects,
            skills=student.skills,
            skills_levels=student.skills_levels_normalized,
        )
    except Exception as e:
        logger.error(f"Error fetching student info for user {user_id}: {e}")
        return None


async def get_student_group_info(
    user_id: UUID, db: AsyncSession
) -> Optional[GroupInfo]:
    """Get group information for a student"""
    try:
        # Get group membership
        group_membership = await db.execute(
            select(GroupMember).where(GroupMember.student_id == user_id)
        )
        membership = group_membership.scalar_one_or_none()

        if not membership:
            return None

        # Get group details
        group_result = await db.execute(
            select(Group).where(Group.group_id == membership.group_id)
        )
        group = group_result.scalar_one_or_none()

        if not group:
            return None

        # Get project ID if exists
        project_result = await db.execute(
            select(Project).where(Project.group_id == group.group_id)
        )
        project = project_result.scalar_one_or_none()

        return GroupInfo(
            group_id=group.group_id,
            group_name=group.name,
            fyp_stage=(
                group.fyp_stage.value
                if hasattr(group.fyp_stage, "value")
                else str(group.fyp_stage)
            ),
            fyp_cycle=(
                group.fyp_cycle.value
                if hasattr(group.fyp_cycle, "value")
                else str(group.fyp_cycle)
            ),
            cohort_year=group.cohort_year,
            supervisor_id=group.supervisor_id,
            cosupervisor_id=(
                group.cosupervisor_ids[0]
                if group.cosupervisor_ids and len(group.cosupervisor_ids) > 0
                else None
            ),
            project_id=project.project_id if project else None,
        )
    except Exception as e:
        logger.error(f"Error fetching student group info for user {user_id}: {e}")
        return None


async def get_supervisor_info(
    user_id: UUID, db: AsyncSession
) -> Optional[SupervisorInfo]:
    """Get supervisor information"""
    try:
        # Get supervisor profile
        supervisor_result = await db.execute(
            select(Supervisor).where(Supervisor.user_id == user_id)
        )
        supervisor = supervisor_result.scalar_one_or_none()

        if not supervisor:
            return None

        # Get supervised groups
        groups_result = await db.execute(
            select(Group).where(
                or_(
                    Group.supervisor_id == user_id,
                    Group.cosupervisor_ids.contains([user_id]),
                )
            )
        )
        groups = groups_result.scalars().all()

        supervised_groups = []
        for group in groups:
            # Get member count
            member_count_result = await db.execute(
                select(func.count())
                .select_from(GroupMember)
                .where(GroupMember.group_id == group.group_id)
            )
            member_count = member_count_result.scalar_one()

            # Get project ID
            project_result = await db.execute(
                select(Project).where(Project.group_id == group.group_id)
            )
            project = project_result.scalar_one_or_none()

            supervised_groups.append(
                SupervisedGroup(
                    group_id=group.group_id,
                    group_name=group.name,
                    fyp_stage=group.fyp_stage,
                    fyp_cycle=group.fyp_cycle,
                    member_count=member_count,
                    project_id=project.project_id if project else None,
                )
            )

        # Get domains
        domains_result = await db.execute(
            select(Domain)
            .join(SupervisorDomain, SupervisorDomain.domain_id == Domain.domain_id)
            .where(SupervisorDomain.supervisor_id == user_id)
        )
        domains = [
            DomainInfo(domain_id=d.domain_id, name=d.name)
            for d in domains_result.scalars().all()
        ]

        # Get industries
        industries_result = await db.execute(
            select(Industry)
            .join(
                SupervisorIndustry,
                SupervisorIndustry.industry_id == Industry.industry_id,
            )
            .where(SupervisorIndustry.supervisor_id == user_id)
        )
        industries = [
            IndustryInfo(industry_id=i.industry_id, name=i.name)
            for i in industries_result.scalars().all()
        ]

        return SupervisorInfo(
            department=supervisor.department,
            designation=supervisor.designation,
            office=supervisor.office,
            capacity_max=supervisor.capacity_max,
            capacity_filled=supervisor.capacity_filled,
            project_types=[supervisor.project_type] if supervisor.project_type else [],
            requirements=supervisor.requirements or [],
            supervised_groups=supervised_groups,
            domains=domains,
            industries=industries,
        )
    except Exception as e:
        logger.error(f"Error fetching supervisor info for user {user_id}: {e}")
        return None


async def get_admin_info(user_id: UUID, db: AsyncSession) -> Optional[AdminInfo]:
    """Get admin information with system stats"""
    try:
        # Get admin profile
        admin_result = await db.execute(select(Admin).where(Admin.user_id == user_id))
        admin = admin_result.scalar_one_or_none()

        if not admin:
            return None

        # Get system stats
        stats = await get_system_stats(db)

        return AdminInfo(
            phone=admin.phone, profile_pic=admin.profile_pic, system_stats=stats
        )
    except Exception as e:
        logger.error(f"Error fetching admin info for user {user_id}: {e}")
        return None


async def get_system_stats(db: AsyncSession) -> SystemStats:
    """Get system statistics for admin"""
    try:
        # Count students
        students_count = await db.execute(select(func.count()).select_from(Student))
        total_students = students_count.scalar_one()

        # Count supervisors
        supervisors_count = await db.execute(
            select(func.count()).select_from(Supervisor)
        )
        total_supervisors = supervisors_count.scalar_one()

        # Count groups
        groups_count = await db.execute(select(func.count()).select_from(Group))
        total_groups = groups_count.scalar_one()

        # Count projects
        projects_count = await db.execute(select(func.count()).select_from(Project))
        total_projects = projects_count.scalar_one()

        # Count pending invites using raw SQL to avoid enum constraint issues
        from sqlalchemy import text

        invites_count = await db.execute(
            text(
                """
                SELECT COUNT(*) 
                FROM group_invites 
                WHERE status = 'pending'::invite_status_enum
            """
            )
        )
        pending_invites = invites_count.scalar_one()

        return SystemStats(
            total_students=total_students,
            total_supervisors=total_supervisors,
            total_groups=total_groups,
            total_projects=total_projects,
            pending_invites=pending_invites,
        )
    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        # Return default stats if there's an error
        return SystemStats(
            total_students=0,
            total_supervisors=0,
            total_groups=0,
            total_projects=0,
            pending_invites=0,
        )


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
    # Strip trailing slash to prevent double slashes in the redirect URI
    redirect_uri = f"{str(settings.oauth_redirect_origin).rstrip('/')}/auth/oauth/{provider}/callback"

    logger.info(f"Initiating {provider} OAuth flow with redirect_uri: {redirect_uri}")
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

        logger.info(
            f"OAuth token data received: {list(token_data.keys()) if token_data else 'None'}"
        )

        # Extract user information based on provider
        email = None
        full_name = None

        if provider == "google":
            # Google provides user info in ID token
            try:
                userinfo = await client.parse_id_token(request, token_data)
                email = userinfo.get("email")
                full_name = userinfo.get("name")
            except Exception as e:
                logger.warning(
                    f"Failed to parse ID token: {e}, trying userinfo endpoint"
                )
                # Fallback to userinfo endpoint if ID token parsing fails
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo", token=token_data
                )
                userinfo = resp.json()
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
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.supervisor_profile),
                selectinload(User.admin_profile),
            )
            .where(User.email == email)
        )
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
                select(User)
                .options(
                    selectinload(User.student_profile),
                    selectinload(User.supervisor_profile),
                    selectinload(User.admin_profile),
                )
                .where(User.user_id == user_id)
                .where(User.role == role)
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
        role_data (RoleUpdateRequest): New role selection (student or supervisor only)
        current_user (User): Current authenticated user
        db (AsyncSession): Database session

    Returns:
        RoleUpdateResponse: Updated user data with new role

    Raises:
        HTTPException(400): Invalid role (must be student or supervisor)
        HTTPException(500): Database error
    """
    try:
        new_role = role_data.role

        # Validate role - only allow student or supervisor
        if new_role not in ["student", "supervisor"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be 'student' or 'supervisor'",
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
            message="Role updated successfully", role=role_val, user=updated_user
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

        # Set token expiration (1 hour from now) - use timezone-aware datetime
        from datetime import timezone

        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

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

        # Generate reset link with correct format: /reset-password?token={token}
        reset_link = f"{settings.frontend_app_url}/reset-password?token={reset_token}"

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

        # Check if token is expired (use timezone-aware datetime)
        from datetime import timezone

        now = datetime.now(timezone.utc)
        if now > reset_token_record.expires_at:
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
        user.updated_at = now

        # Mark token as used
        reset_token_record.used = True
        reset_token_record.updated_at = now

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
