"""
core/config.py
Application configuration loaded from environment variables.
All secrets must be set in .env — never hardcode credentials.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────
    app_name:     str  = "SmartMediaFetcher"
    app_env:      str  = "production"
    debug:        bool = False
    secret_key:   str  = "change-me"
    api_v1_prefix: str = "/api/v1"

    # ── Server ─────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database ───────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://user:pass@localhost/smf"

    # ── Redis ──────────────────────────────────────────────
    redis_url:        str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    # ── Celery ─────────────────────────────────────────────
    celery_broker_url:     str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── JWT ────────────────────────────────────────────────
    jwt_algorithm:                str = "HS256"
    access_token_expire_minutes:  int = 60
    refresh_token_expire_days:    int = 30

    # ── File handling ──────────────────────────────────────
    max_file_size_mb:          int = 500
    temp_dir:                  str = "/tmp/smf_downloads"
    auto_delete_temp_minutes:  int = 30

    # ── Rate Limiting ──────────────────────────────────────
    rate_limit_requests_per_minute: int = 30
    rate_limit_burst:               int = 10

    # ── HTTP ───────────────────────────────────────────────
    http_timeout_seconds: int = 30
    max_redirects:        int = 5

    # ── Logging ────────────────────────────────────────────
    log_level: str = "INFO"
    log_file:  str = "/var/log/smf/app.log"

    # ── CORS ───────────────────────────────────────────────
    allowed_origins: str = "http://localhost"

    # ── FFmpeg ─────────────────────────────────────────────
    ffmpeg_path: str = "/usr/bin/ffmpeg"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
