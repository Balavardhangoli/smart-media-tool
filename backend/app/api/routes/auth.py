"""
api/routes/auth.py
Authentication endpoints: register, login, token refresh, API keys.
"""
from datetime import timezone, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, generate_api_key, verify_api_key,
)
from app.core.config import settings
from app.db.session import get_db
from app.db.models import User, APIKey
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse,
    UserOut, APIKeyCreate, APIKeyOut,
)

router  = APIRouter(prefix="/auth", tags=["auth"])
bearer  = HTTPBearer(auto_error=False)


# ── Dependency: get current user from JWT ──────────────────
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db:    AsyncSession = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=401, detail="Authentication required.")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user_id = payload.get("sub")
    result  = await db.execute(select(User).where(User.id == user_id))
    user    = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive.")
    return user


# ──────────────────────────────────────────────────────────
#  REGISTER
# ──────────────────────────────────────────────────────────
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Check username uniqueness
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken.")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut(id=str(user.id), email=user.email, username=user.username,
                   is_active=user.is_active, is_superuser=user.is_superuser)


# ──────────────────────────────────────────────────────────
#  LOGIN
# ──────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user   = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled.")

    access  = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ──────────────────────────────────────────────────────────
#  REFRESH TOKEN
# ──────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db:    AsyncSession = Depends(get_db),
):
    if not creds:
        raise HTTPException(status_code=401, detail="Refresh token required.")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    user_id = payload.get("sub")
    result  = await db.execute(select(User).where(User.id == user_id))
    user    = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found.")

    access  = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ──────────────────────────────────────────────────────────
#  CURRENT USER INFO
# ──────────────────────────────────────────────────────────
@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
    )


# ──────────────────────────────────────────────────────────
#  API KEYS
# ──────────────────────────────────────────────────────────
@router.post("/keys", response_model=APIKeyOut, status_code=201)
async def create_api_key(
    body:         APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    raw, hashed = generate_api_key()
    key = APIKey(
        user_id=current_user.id,
        name=body.name,
        key_hash=hashed,
        key_prefix=raw[:10],
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return APIKeyOut(
        id=key.id, name=key.name, key_prefix=key.key_prefix,
        is_active=key.is_active, created_at=str(key.created_at),
        raw_key=raw,   # Only returned here — never stored in plaintext
    )


@router.get("/keys", response_model=List[APIKeyOut])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id, APIKey.is_active == True)
    )
    keys = result.scalars().all()
    return [
        APIKeyOut(id=k.id, name=k.name, key_prefix=k.key_prefix,
                  is_active=k.is_active, created_at=str(k.created_at))
        for k in keys
    ]


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id:       int,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.user_id == current_user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")
    key.is_active = False
    await db.commit()
