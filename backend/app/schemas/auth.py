"""
schemas/auth.py
Pydantic v2 models for authentication flows.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
import re


class UserRegister(BaseModel):
    email:    EmailStr
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]{3,32}$", v):
            raise ValueError("Username must be 3-32 chars: letters, numbers, _ and - only.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserLogin(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int          # seconds


class UserOut(BaseModel):
    id:          str
    email:       str
    username:    str
    is_active:   bool
    is_superuser: bool

    model_config = {"from_attributes": True}


class APIKeyCreate(BaseModel):
    name: str


class APIKeyOut(BaseModel):
    id:         int
    name:       str
    key_prefix: str
    is_active:  bool
    created_at: str
    raw_key:    Optional[str] = None   # Only returned on creation

    model_config = {"from_attributes": True}
