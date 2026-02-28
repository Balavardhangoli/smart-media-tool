"""
schemas/download.py
Pydantic v2 models for download API request and response validation.
"""
from typing import List, Optional, Any
from pydantic import BaseModel, HttpUrl, field_validator, model_validator


class AnalyzeRequest(BaseModel):
    url: str
    quality: Optional[str] = "best"

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        from app.utils.ssrf_guard import validate_url, SSRFError
        try:
            return validate_url(v)
        except SSRFError as e:
            raise ValueError(str(e))


class BulkAnalyzeRequest(BaseModel):
    urls: List[str]
    quality: Optional[str] = "best"

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: List[str]) -> List[str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 URLs per bulk request.")
        return v


class FetchRequest(BaseModel):
    url:        str
    filename:   Optional[str] = None
    format:     Optional[str] = None     # mp4 | mp3 | webp | etc.


class MediaOptionSchema(BaseModel):
    label:      str
    url:        str
    media_type: str
    mime_type:  Optional[str] = None
    file_size:  Optional[int] = None
    width:      Optional[int] = None
    height:     Optional[int] = None
    format:     Optional[str] = None
    thumbnail:  Optional[str] = None


class AnalyzeResponse(BaseModel):
    success:      bool
    url:          str
    platform:     Optional[str] = None
    media_type:   Optional[str] = None
    title:        Optional[str] = None
    thumbnail:    Optional[str] = None
    description:  Optional[str] = None
    options:      List[MediaOptionSchema] = []
    error:        Optional[str] = None


class BulkAnalyzeResponse(BaseModel):
    results: List[AnalyzeResponse]
    total:   int
    success_count: int
    fail_count:    int
