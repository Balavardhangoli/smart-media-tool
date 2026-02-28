"""
services/cache.py
Redis-backed async cache for media analysis results.
Avoids re-fetching the same URL repeatedly.
"""
import json
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    try:
        client = await get_redis()
        value = await client.get(key)
        if value:
            logger.debug("cache_hit", key=key)
            return json.loads(value)
    except Exception as e:
        logger.warning("cache_get_error", key=key, error=str(e))
    return None


async def cache_set(key: str, value: Any, ttl: int = settings.cache_ttl_seconds) -> None:
    try:
        client = await get_redis()
        await client.setex(key, ttl, json.dumps(value, default=str))
        logger.debug("cache_set", key=key, ttl=ttl)
    except Exception as e:
        logger.warning("cache_set_error", key=key, error=str(e))


async def cache_delete(key: str) -> None:
    try:
        client = await get_redis()
        await client.delete(key)
    except Exception as e:
        logger.warning("cache_delete_error", key=key, error=str(e))


def make_cache_key(prefix: str, url: str) -> str:
    """Deterministic cache key from URL."""
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return f"smf:{prefix}:{url_hash}"


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
