"""
db/models.py
SQLAlchemy ORM models for all database tables.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
    BigInteger, Enum as SAEnum, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────
#  USERS
# ──────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id:            Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:         Mapped[str]        = mapped_column(String(255), unique=True, nullable=False, index=True)
    username:      Mapped[str]        = mapped_column(String(64),  unique=True, nullable=False, index=True)
    hashed_password: Mapped[str]     = mapped_column(String(255), nullable=False)
    is_active:     Mapped[bool]       = mapped_column(Boolean, default=True, nullable=False)
    is_superuser:  Mapped[bool]       = mapped_column(Boolean, default=False, nullable=False)
    created_at:    Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at:    Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    downloads: Mapped[list["DownloadHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys:  Mapped[list["APIKey"]]          = relationship(back_populates="user", cascade="all, delete-orphan")


# ──────────────────────────────────────────────────────────
#  DOWNLOAD HISTORY
# ──────────────────────────────────────────────────────────
class DownloadHistory(Base):
    __tablename__ = "download_history"

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    source_url:  Mapped[str]            = mapped_column(Text, nullable=False)
    media_type:  Mapped[str]            = mapped_column(String(50), nullable=False)   # image|video|audio|document
    platform:    Mapped[str]            = mapped_column(String(50), nullable=False)   # youtube|instagram|direct|...
    filename:    Mapped[str]            = mapped_column(String(512), nullable=True)
    file_size:   Mapped[Optional[int]]  = mapped_column(BigInteger, nullable=True)    # bytes
    mime_type:   Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    status:      Mapped[str]            = mapped_column(
        SAEnum("pending", "processing", "completed", "failed", name="download_status"),
        default="completed", nullable=False,
    )
    error_msg:   Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    ip_address:  Mapped[Optional[str]]  = mapped_column(String(45), nullable=True)
    created_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    user: Mapped[Optional["User"]] = relationship(back_populates="downloads")


# ──────────────────────────────────────────────────────────
#  API KEYS
# ──────────────────────────────────────────────────────────
class APIKey(Base):
    __tablename__ = "api_keys"

    id:          Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:     Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name:        Mapped[str]          = mapped_column(String(100), nullable=False)
    key_hash:    Mapped[str]          = mapped_column(String(64), unique=True, nullable=False)
    key_prefix:  Mapped[str]          = mapped_column(String(10), nullable=False)       # first 8 chars for display
    is_active:   Mapped[bool]         = mapped_column(Boolean, default=True)
    last_used:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    requests_count: Mapped[int]       = mapped_column(Integer, default=0)
    rate_limit:  Mapped[int]          = mapped_column(Integer, default=100)             # req/minute
    created_at:  Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")


# ──────────────────────────────────────────────────────────
#  AUDIT LOGS
# ──────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    action:      Mapped[str]            = mapped_column(String(100), nullable=False)    # "download_attempt", "login", etc.
    resource:    Mapped[Optional[str]]  = mapped_column(String(512), nullable=True)
    ip_address:  Mapped[Optional[str]]  = mapped_column(String(45), nullable=True)
    user_agent:  Mapped[Optional[str]]  = mapped_column(String(512), nullable=True)
    status_code: Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    detail:      Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
