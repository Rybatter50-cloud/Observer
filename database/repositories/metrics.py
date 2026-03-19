"""
Observer Intelligence Platform - Metrics Repository

Token budget persistence and usage tracking.

2026-02-09 | Mr Cat + Claude | Extracted from monolithic IntelligenceDB
2026-02-10 | Mr Cat + Claude | Added token usage persistence for budget meters
"""

import asyncpg
from datetime import datetime, timedelta
from typing import List, Tuple

from utils.logging import get_logger

logger = get_logger(__name__)


class MetricsRepository:
    """Token budget persistence and usage tracking."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ------------------------------------------------------------------
    # Token budget persistence
    # ------------------------------------------------------------------

    async def insert_token_usage(self, provider: str, tokens: int) -> bool:
        """Persist a token usage entry for rolling 24h budget tracking."""
        try:
            await self._pool.execute(
                "INSERT INTO token_usage (provider, tokens) VALUES ($1, $2)",
                provider, tokens,
            )
            return True
        except Exception as e:
            logger.error(f"Error persisting token usage: {e}")
            return False

    async def get_token_usage_24h(self) -> List[Tuple[str, datetime, int]]:
        """
        Load all token usage entries from the last 24 hours.

        Returns:
            List of (provider, created_at, tokens) tuples for hydrating
            the in-memory MetricsCollector ledger on startup.
        """
        try:
            cutoff = datetime.now() - timedelta(hours=24)
            rows = await self._pool.fetch(
                """SELECT provider, created_at, tokens
                   FROM token_usage
                   WHERE created_at >= $1
                   ORDER BY created_at ASC""",
                cutoff,
            )
            return [(r['provider'], r['created_at'], r['tokens']) for r in rows]
        except Exception as e:
            logger.error(f"Error loading token usage history: {e}")
            return []

    async def prune_old_token_usage(self, hours: int = 48) -> int:
        """Delete token usage entries older than given hours (housekeeping)."""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            result = await self._pool.execute(
                "DELETE FROM token_usage WHERE created_at < $1",
                cutoff,
            )
            # result is a string like "DELETE 42"
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.debug(f"Pruned {count} old token usage records (>{hours}h)")
            return count
        except Exception as e:
            logger.error(f"Error pruning token usage: {e}")
            return 0

    # ------------------------------------------------------------------
    # Gemini /discover call persistence
    # ------------------------------------------------------------------

    async def insert_discover_call(self) -> bool:
        """Persist a single /discover API call timestamp."""
        try:
            await self._pool.execute(
                "INSERT INTO gemini_discover_calls DEFAULT VALUES"
            )
            return True
        except Exception as e:
            logger.error(f"Error persisting discover call: {e}")
            return False

    async def get_discover_calls_48h(self) -> List[datetime]:
        """Load discover call timestamps from the last 48 hours."""
        try:
            cutoff = datetime.now() - timedelta(hours=48)
            rows = await self._pool.fetch(
                """SELECT created_at FROM gemini_discover_calls
                   WHERE created_at >= $1
                   ORDER BY created_at ASC""",
                cutoff,
            )
            return [r['created_at'].replace(tzinfo=None) for r in rows]
        except Exception as e:
            logger.error(f"Error loading discover call history: {e}")
            return []

    async def prune_old_discover_calls(self, hours: int = 48) -> int:
        """Delete discover call entries older than given hours."""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            result = await self._pool.execute(
                "DELETE FROM gemini_discover_calls WHERE created_at < $1",
                cutoff,
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.debug(f"Pruned {count} old discover call records (>{hours}h)")
            return count
        except Exception as e:
            logger.error(f"Error pruning discover calls: {e}")
            return 0
