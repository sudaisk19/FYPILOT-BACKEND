"""
Unit tests for auth-layer helpers.
Note: There is no ``AuthService`` class in this codebase. Auth HTTP handlers live in
``app.auth.routes``; password/JWT utilities live in ``app.auth.utils``; request auth
dependencies live in ``app.auth.supabase_auth``. This module tests those units.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import allure
import jwt
import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import supabase_auth
from app.auth.utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import RoleEnum
from app.schemas.user import UserCreate

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Auth Service"),
]


@allure.epic("FYPilot Unit Tests")
@allure.feature("Auth Service")
class TestPasswordHashing:
    """``hash_password`` / ``verify_password`` (``app.auth.utils``)."""

    @allure.story("Hash password when plain password returns bcrypt prefix")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_hash_password_when_plain_password_returns_bcrypt_prefix(self):
        # ARRANGE
        plain = "ValidP@ssw0rd"
        # ACT
        hashed = hash_password(plain)
        # ASSERT
        assert hashed != plain
        assert hashed.startswith("$2b$")

    @allure.story("Verify password when correct returns true")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_verify_password_when_correct_returns_true(self):
        # ARRANGE
        plain = "AnotherV@lid9"
        hashed = hash_password(plain)
        # ACT
        ok = verify_password(plain, hashed)
        # ASSERT
        assert ok is True


@allure.epic("FYPilot Unit Tests")
@allure.feature("Auth Service")
class TestUserCreateValidation:
    """``UserCreate`` schema (used by signup) — weak passwords rejected."""

    @allure.story("User create when password missing special raises value error")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_user_create_when_password_missing_special_raises_value_error(self):
        # ARRANGE / ACT / ASSERT
        with pytest.raises(ValueError):
            UserCreate(
                full_name="Valid Name",
                email="a@b.com",
                password="NoSpecial1",
                role="student",
            )

    @allure.story("User create when password too short raises value error")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_user_create_when_password_too_short_raises_value_error(self):
        # ARRANGE / ACT / ASSERT
        with pytest.raises(ValueError):
            UserCreate(
                full_name="Valid Name",
                email="a@b.com",
                password="Ab1!",
                role="student",
            )


@allure.epic("FYPilot Unit Tests")
@allure.feature("Auth Service")
class TestJwtTokens:
    """``create_access_token`` / ``decode_access_token`` — access-only (no refresh token API)."""

    @allure.story("Create access token when called returns decodable jwt")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_access_token_when_called_returns_decodable_jwt(self):
        # ARRANGE
        uid = str(uuid4())
        # ACT
        token = create_access_token(sub=uid, role="student")
        payload = decode_access_token(token)
        # ASSERT
        assert payload["sub"] == uid
        assert payload["role"] == "student"

    @allure.story("Decode access token when expired raises http 401")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_decode_access_token_when_expired_raises_http_401(self):
        # ARRANGE
        past = datetime.utcnow() - timedelta(hours=1)
        payload = {
            "sub": str(uuid4()),
            "role": "student",
            "exp": past,
            "iat": past,
        }
        token = jwt.encode(
            payload,
            "test-jwt-secret-key-for-unit-tests",
            algorithm="HS256",
        )
        # ACT / ASSERT
        with pytest.raises(HTTPException) as exc:
            decode_access_token(token)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    @allure.story("New access token can replace expired token same user")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_new_access_token_can_replace_expired_token_same_user(self):
        """
        Stand-in for "refresh": this API does not expose a refresh-token endpoint;
        clients must obtain a new access token via login (or role update) flow.
        """
        # ARRANGE
        uid = str(uuid4())
        # ACT (two tokens minted in the same second may be identical strings)
        first = create_access_token(sub=uid, role="faculty")
        second = create_access_token(sub=uid, role="faculty")
        # ASSERT
        assert decode_access_token(first)["sub"] == decode_access_token(second)["sub"]
        assert decode_access_token(first)["role"] == "faculty"


@allure.epic("FYPilot Unit Tests")
@allure.feature("Auth Service")
class TestSupabaseAuthGetCurrentUser:
    """``get_current_user`` (`app.auth.supabase_auth`)."""

    @pytest.mark.asyncio
    @allure.story("Get current user when valid returns user")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_current_user_when_valid_returns_user(self, monkeypatch):
        # ARRANGE
        uid = uuid4()

        def _fake_decode(_token: str):
            return {"sub": str(uid), "role": "student"}

        monkeypatch.setattr(supabase_auth, "decode_access_token", _fake_decode)

        mock_user = MagicMock()
        mock_user.user_id = uid
        mock_user.role = RoleEnum.student

        exec_result = MagicMock()
        exec_result.scalars.return_value.first.return_value = mock_user

        db = AsyncMock()
        db.execute = AsyncMock(return_value=exec_result)

        request = MagicMock(spec=Request)
        request.state = MagicMock()

        creds = MagicMock(spec=HTTPAuthorizationCredentials)
        creds.credentials = "dummy.jwt.token"

        # ACT
        out = await supabase_auth.get_current_user(
            request=request,
            token=creds,
            db=db,
        )
        # ASSERT
        assert out is mock_user
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @allure.story("Get current user when decode raises returns 401")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_current_user_when_decode_raises_returns_401(self, monkeypatch):
        # ARRANGE
        def _boom(_token: str):
            raise HTTPException(status_code=401, detail="Authentication failed")

        monkeypatch.setattr(supabase_auth, "decode_access_token", _boom)

        request = MagicMock(spec=Request)
        creds = MagicMock()
        creds.credentials = "bad"
        db = AsyncMock()

        # ACT / ASSERT
        with pytest.raises(HTTPException) as exc:
            await supabase_auth.get_current_user(request=request, token=creds, db=db)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication failed"


@allure.epic("FYPilot Unit Tests")
@allure.feature("Auth Service")
class TestSupabaseAuthActiveUser:
    """``get_current_active_user`` (`app.auth.supabase_auth`)."""

    @pytest.mark.asyncio
    @allure.story("Get current active user when inactive raises 403")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_current_active_user_when_inactive_raises_403(self):
        # ARRANGE
        from app.auth.supabase_auth import get_current_active_user

        inactive = MagicMock()
        inactive.is_active = False

        # ACT / ASSERT
        with pytest.raises(HTTPException) as exc:
            await get_current_active_user(current_user=inactive)
        assert exc.value.status_code == 403


@allure.epic("FYPilot Unit Tests")
@allure.feature("Auth Service")
class TestRequireRoles:
    """``require_roles`` factory (`app.auth.supabase_auth`)."""

    @pytest.mark.asyncio
    @allure.story("Require roles when admin required and user student raises 403")
    @allure.severity(allure.severity_level.MINOR)
    async def test_require_roles_when_admin_required_and_user_student_raises_403(
        self,
    ):
        # ARRANGE
        student = MagicMock()
        # ``require_roles`` compares to string allow-list (see ``supabase_auth``).
        student.role = "student"
        guard = supabase_auth.require_roles("admin")

        # ACT / ASSERT
        with pytest.raises(HTTPException) as exc:
            await guard(user=student)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @allure.story("Require roles when admin required and user admin returns user")
    @allure.severity(allure.severity_level.MINOR)
    async def test_require_roles_when_admin_required_and_user_admin_returns_user(
        self,
    ):
        # ARRANGE
        admin = MagicMock()
        admin.role = "admin"
        guard = supabase_auth.require_roles("admin")

        # ACT
        out = await guard(user=admin)
        # ASSERT
        assert out is admin
