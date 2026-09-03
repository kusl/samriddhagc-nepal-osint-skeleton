"""Async PostgreSQL database configuration."""
import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on anything odd."""
    try:
        value = int(os.environ.get(name, "").strip())
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


# The worker runs 45 scheduled jobs on one AsyncIOScheduler, so several can hold
# a session at the same time. It used to get a *smaller* pool than the API
# (3 + 2 overflow), which it exhausted routinely:
#   "QueuePool limit of size 3 overflow 2 reached, connection timed out"
# Postgres allows 100 connections and typical usage sits near 14, so the cap was
# arbitrary rather than protective. Overridable via env for tuning without a
# rebuild. Note this is NOT the election-day leak fix — that lives in get_db()
# below, which still closes every transaction.
_is_scheduler = os.environ.get("RUN_SCHEDULER", "false").lower() == "true"
if _is_scheduler:
    _pool_size = _env_int("DB_POOL_SIZE", 10)
    _max_overflow = _env_int("DB_MAX_OVERFLOW", 10)
else:
    _pool_size = _env_int("DB_POOL_SIZE", 5)
    _max_overflow = _env_int("DB_MAX_OVERFLOW", 10)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_pre_ping=True,
    pool_recycle=300,     # Recycle connections every 5 min — prevents stale conn buildup
    pool_timeout=10,      # Fail fast (10s) instead of blocking 30s then crashing
    pool_reset_on_return="rollback",  # Always rollback on return — clears "idle in transaction"
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session.

    Always closes the transaction after the endpoint returns — prevents
    "idle in transaction" connection leaks that exhausted the pool on
    election day (2026-03-05).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # Close the transaction so the connection returns to the pool
            # immediately, not after response serialization/sending.
            await session.close()
