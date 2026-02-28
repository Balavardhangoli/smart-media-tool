"""
api/routes/history.py
Download history endpoints for authenticated users.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import DownloadHistory, User
from app.api.routes.auth import get_current_user

router = APIRouter(prefix="/history", tags=["history"])


class HistoryItem(BaseModel):
    id:          int
    source_url:  str
    media_type:  str
    platform:    str
    filename:    Optional[str] = None
    file_size:   Optional[int] = None
    status:      str
    created_at:  str

    model_config = {"from_attributes": True}


@router.get("/", response_model=List[HistoryItem])
async def get_history(
    page:         int          = Query(1, ge=1),
    per_page:     int          = Query(20, ge=1, le=100),
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Return paginated download history for the logged-in user."""
    offset = (page - 1) * per_page
    result = await db.execute(
        select(DownloadHistory)
        .where(DownloadHistory.user_id == current_user.id)
        .order_by(desc(DownloadHistory.created_at))
        .offset(offset)
        .limit(per_page)
    )
    items = result.scalars().all()
    return [
        HistoryItem(
            id=h.id, source_url=h.source_url, media_type=h.media_type,
            platform=h.platform, filename=h.filename, file_size=h.file_size,
            status=h.status, created_at=str(h.created_at),
        )
        for h in items
    ]


@router.delete("/{item_id}", status_code=204)
async def delete_history_item(
    item_id:      int,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DownloadHistory).where(
            DownloadHistory.id == item_id,
            DownloadHistory.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item:
        await db.delete(item)
        await db.commit()
