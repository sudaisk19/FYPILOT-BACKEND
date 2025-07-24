# app/api/http/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models.user import User
from app.schemas.user import UserCreate

router = APIRouter(tags=["auth"])


@router.post("/signup")
async def signup(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    # 1) Check for existing email
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalars().first():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error",
                "error": {
                    "code": status.HTTP_400_BAD_REQUEST,
                    "type": "BadRequest",
                    "message": "Email already registered",
                },
            },
        )

    # 2) Create user
    user = User(
        full_name=user_in.full_name,
        email=user_in.email,
        password_hash=hash_password(user_in.password),
        role=user_in.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 3) Return success
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "status": "success",
            "data": {
                "user_id": str(user.user_id),
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
            },
            "message": "User created successfully",
        },
    )


@router.post("/login")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),  # ← now reads form fields username/password
    db: AsyncSession = Depends(get_db),
):
    # 1) Fetch by email (we treat form_data.username as the email)
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()

    # 2) Verify password
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3) Issue JWT
    access_token = create_access_token(sub=str(user.user_id))
    # 4) Return in OAuth2 password‑flow format
    return {"access_token": access_token, "token_type": "bearer"}
