import redis.asyncio as redis
from redis.asyncio import ConnectionPool
from typing import Optional
from app.core.config import get_settings

settings = get_settings()

_pool: Optional[ConnectionPool] = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=False,
        )
    return _pool


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=get_redis_pool())


async def close_redis_pool():
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None
