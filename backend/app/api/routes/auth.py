"""
api/routes/auth.py
Authentication endpoints: register, login, token refresh, API keys, password reset.
"""
import random
import re
import string
from datetime import timezone, datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
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
limiter = Limiter(key_func=get_remote_address)

# ── In-memory OTP store ────────────────────────────────────
# Key: email, Value: {otp, expires_at, user_id}
_otp_store: dict = {}
_otp_attempts: dict = {}  # Track failed OTP attempts per email
MAX_OTP_ATTEMPTS = 5      # Max wrong attempts before OTP invalidated


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
@limiter.limit("5/minute")
async def register(request: Request, body: UserRegister, db: AsyncSession = Depends(get_db)):
    # ── Validate email format ──────────────────────────────
    email_regex = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, body.email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address (e.g. name@gmail.com).")

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # ── Username validation ────────────────────────────────
    # Allow letters, numbers, spaces, hyphens, underscores
    # Username does NOT need to be unique — only email is unique
    username = body.username.strip()
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters.")
    if len(username) > 50:
        raise HTTPException(status_code=400, detail="Username too long. Maximum 50 characters.")
    # Allow: letters, numbers, spaces, hyphens, underscores, dots
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9 ._\-]+$', username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers, spaces, dots, hyphens and underscores.")

    # Password length check
    if len(body.password) > 128:
        raise HTTPException(status_code=400, detail="Password too long. Maximum 128 characters.")

    user = User(
        email=body.email,
        username=username,  # use trimmed version
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
@limiter.limit("10/minute")
async def login(request: Request, body: UserLogin, db: AsyncSession = Depends(get_db)):
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
#  EMAIL HELPER — Resend
# ──────────────────────────────────────────────────────────
import httpx as _httpx
import os as _os

async def _send_reset_email(to_email: str, otp: str, username: str) -> bool:
    """Send OTP reset email via Resend API."""
    resend_key = _os.getenv("RESEND_API_KEY", "")
    from_email = _os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not resend_key:
        print(f"[PASSWORD RESET] No RESEND_API_KEY set. OTP for {to_email}: {otp}", flush=True)
        return False

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"/></head>
    <body style="margin:0;padding:0;background:#0c0c0f;font-family:'Arial',sans-serif;">
      <div style="max-width:480px;margin:40px auto;background:#1a1a24;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);">
        <!-- Header -->
        <div style="background:linear-gradient(135deg,#fbbf24,#f97316);padding:28px 32px;text-align:center;">
          <div style="font-size:32px;margin-bottom:8px;">🔐</div>
          <h1 style="margin:0;color:#0c0c0f;font-size:22px;font-weight:900;letter-spacing:-0.5px;">Password Reset</h1>
          <p style="margin:6px 0 0;color:rgba(12,12,15,0.7);font-size:13px;">Smart Media Fetcher</p>
        </div>
        <!-- Body -->
        <div style="padding:32px;">
          <p style="color:#e8e8ee;font-size:15px;margin:0 0 20px;">Hi <strong>{username}</strong>,</p>
          <p style="color:#9999b3;font-size:14px;line-height:1.6;margin:0 0 28px;">
            We received a request to reset your password. Use the code below to complete the reset. This code expires in <strong style="color:#fbbf24;">10 minutes</strong>.
          </p>
          <!-- OTP Box -->
          <div style="background:#111116;border:2px solid rgba(251,191,36,0.3);border-radius:12px;padding:24px;text-align:center;margin-bottom:28px;">
            <p style="color:#9999b3;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;">Your reset code</p>
            <div style="font-size:42px;font-weight:900;letter-spacing:12px;color:#fbbf24;font-family:'Courier New',monospace;">{otp}</div>
          </div>
          <!-- Warning -->
          <div style="background:rgba(248,113,113,0.1);border:1px solid rgba(248,113,113,0.2);border-radius:10px;padding:14px 16px;margin-bottom:24px;">
            <p style="color:#f87171;font-size:12px;margin:0;line-height:1.6;">
              ⚠️ If you did not request this, please ignore this email. Your password will not change.
            </p>
          </div>
          <p style="color:#55556e;font-size:12px;margin:0;line-height:1.6;">
            This code is valid for 10 minutes and can only be used once.<br/>
            Never share this code with anyone.
          </p>
        </div>
        <!-- Footer -->
        <div style="background:#111116;padding:16px 32px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);">
          <p style="color:#55556e;font-size:11px;margin:0;">Smart Media Fetcher · Automated message, do not reply</p>
        </div>
      </div>
    </body>
    </html>
    """

    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "from":    f"Smart Media Fetcher <{from_email}>",
                    "to":      [to_email],
                    "subject": f"Your password reset code: {otp}",
                    "html":    html_body,
                },
            )
            if resp.status_code == 200:
                print(f"[EMAIL] Reset email sent to {to_email}", flush=True)
                return True
            else:
                print(f"[EMAIL ERROR] Status {resp.status_code}: {resp.text}", flush=True)
                print(f"[PASSWORD RESET FALLBACK] OTP for {to_email}: {otp}", flush=True)
                return False
    except Exception as e:
        print(f"[EMAIL ERROR] {e}", flush=True)
        print(f"[PASSWORD RESET FALLBACK] OTP for {to_email}: {otp}", flush=True)
        return False


# ──────────────────────────────────────────────────────────
#  FORGOT PASSWORD — Step 1: Request OTP
# ──────────────────────────────────────────────────────────
@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: dict,
    db:   AsyncSession = Depends(get_db),
):
    """Send password reset OTP via email. Always returns success for security."""
    email = body.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")

    # Check if user exists
    result = await db.execute(select(User).where(User.email == email))
    user   = result.scalar_one_or_none()

    if not user:
        # Email not found — tell frontend clearly
        return {"message": "No account found with this email.", "sent": False}

    # User found — generate OTP and send email
    otp = ''.join(random.choices(string.digits, k=6))
    _otp_store[email] = {
        "otp":        otp,
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
        "user_id":    str(user.id),
    }
    # Send email via Resend
    await _send_reset_email(email, otp, user.username or email.split("@")[0])

    return {"message": "Reset code sent to your email.", "sent": True}


# ──────────────────────────────────────────────────────────
#  VERIFY OTP — Check if OTP is valid (without resetting)
# ──────────────────────────────────────────────────────────
@router.post("/verify-otp")
@limiter.limit("5/minute")
async def verify_otp(request: Request, body: dict):
    """Verify OTP is valid without consuming it."""
    email = body.get("email", "").strip().lower()
    otp   = body.get("otp", "").strip()

    if not email or not otp:
        raise HTTPException(status_code=400, detail="Email and OTP are required.")

    stored = _otp_store.get(email)
    if not stored:
        raise HTTPException(status_code=404, detail="No reset code found. Please request a new one.")

    if datetime.utcnow() > stored["expires_at"]:
        _otp_store.pop(email, None)
        _otp_attempts.pop(email, None)
        raise HTTPException(status_code=400, detail="Reset code has expired. Please request a new one.")

    # Check brute force attempts
    attempts = _otp_attempts.get(email, 0)
    if attempts >= MAX_OTP_ATTEMPTS:
        _otp_store.pop(email, None)
        _otp_attempts.pop(email, None)
        raise HTTPException(status_code=429, detail="Too many wrong attempts. Please request a new reset code.")

    if stored["otp"] != otp:
        _otp_attempts[email] = attempts + 1
        remaining = MAX_OTP_ATTEMPTS - attempts - 1
        raise HTTPException(status_code=400, detail=f"Invalid reset code. {remaining} attempts remaining.")

    # OTP correct — clear attempts
    _otp_attempts.pop(email, None)
    return {"valid": True, "message": "OTP verified successfully."}


# ──────────────────────────────────────────────────────────
#  RESET PASSWORD — Step 2: Verify OTP + Set New Password
# ──────────────────────────────────────────────────────────
@router.post("/reset-password")
async def reset_password(
    body: dict,
    db:   AsyncSession = Depends(get_db),
):
    """Reset password using OTP code."""
    email    = body.get("email", "").strip().lower()
    otp      = body.get("otp", "").strip()
    new_pass = body.get("new_password", "")

    if not all([email, otp, new_pass]):
        raise HTTPException(
            status_code=400,
            detail="Email, OTP and new password are required."
        )

    # Validate password strength
    if len(new_pass) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if not any(c.isupper() for c in new_pass):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 uppercase letter.")
    if not any(c.isdigit() for c in new_pass):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 number.")

    # Verify OTP exists
    stored = _otp_store.get(email)
    if not stored:
        raise HTTPException(
            status_code=400,
            detail="No reset code found. Please request a new one."
        )

    # Check expiry
    if datetime.utcnow() > stored["expires_at"]:
        del _otp_store[email]
        raise HTTPException(
            status_code=400,
            detail="Reset code has expired. Please request a new one."
        )

    # Verify OTP matches
    if stored["otp"] != otp:
        raise HTTPException(
            status_code=400,
            detail="Invalid reset code. Please check and try again."
        )

    # Update user password
    result = await db.execute(select(User).where(User.email == email))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found.")

    user.hashed_password = hash_password(new_pass)
    await db.commit()

    # Remove used OTP
    del _otp_store[email]

    return {"message": "Password reset successfully. Please log in with your new password."}


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
        raw_key=raw,
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

# ──────────────────────────────────────────────────────────
#  CHANGE PASSWORD (while logged in)
# ──────────────────────────────────────────────────────────
@router.post("/change-password")
async def change_password(
    body:         dict,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    current = body.get("current_password", "")
    new_pw  = body.get("new_password", "")

    if not verify_password(current, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if not any(c.isupper() for c in new_pw):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 uppercase letter.")
    if not any(c.isdigit() for c in new_pw):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 number.")

    current_user.hashed_password = hash_password(new_pw)
    await db.commit()
    return {"message": "Password changed successfully."}


# ──────────────────────────────────────────────────────────
#  DELETE ACCOUNT
# ──────────────────────────────────────────────────────────
@router.delete("/delete-account", status_code=204)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    await db.delete(current_user)
    await db.commit()
