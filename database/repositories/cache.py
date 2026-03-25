"""
Observer Intelligence Platform - Cache Repository

General-purpose key/value cache backed by PostgreSQL JSONB.

2026-02-16 | Claude
"""

import asyncpg
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


class CacheRepository:
    """Key/value cache store with JSONB values."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get(self, key: str, max_age_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached value by key.

        Args:
            key: Cache key
            max_age_seconds: If set, only return if updated within this many seconds

        Returns:
            The cached JSONB value as a dict, or None if missing/stale
        """
        try:
            if max_age_seconds is not None:
                cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
                row = await self._pool.fetchrow(
                    "SELECT value FROM cache_store WHERE key = $1 AND updated_at >= $2",
                    key, cutoff,
                )
            else:
                row = await self._pool.fetchrow(
                    "SELECT value FROM cache_store WHERE key = $1",
                    key,
                )
            if row:
                import json
                val = row['value']
                # asyncpg returns JSONB as a Python dict/list already
                return val if isinstance(val, dict) else json.loads(val)
            return None
        except Exception as e:
            logger.error("Cache get error for key=%s: %s", key, e)
            return None

    async def set(self, key: str, value: Dict[str, Any]) -> bool:
        """
        Insert or update a cached value.

        Args:
            key: Cache key
            value: JSON-serializable dict to store

        Returns:
            True on success
        """
        try:
            await self._pool.execute(
                """INSERT INTO cache_store (key, value, updated_at)
                   VALUES ($1, $2, NOW())
                   ON CONFLICT (key)
                   DO UPDATE SET value = $2, updated_at = NOW()""",
                key, value,
            )
            return True
        except Exception as e:
            logger.error("Cache set error for key=%s: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cached value by key."""
        try:
            await self._pool.execute(
                "DELETE FROM cache_store WHERE key = $1", key
            )
            return True
        except Exception as e:
            logger.error("Cache delete error for key=%s: %s", key, e)
            return False
