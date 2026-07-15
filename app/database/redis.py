from __future__ import annotations

from typing import Optional

import redis

from app.core.config import get_settings


def get_redis_client() -> Optional[redis.Redis]:
    settings = get_settings()
    if not settings.enable_redis:
        return None
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)
