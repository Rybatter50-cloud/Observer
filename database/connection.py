"""
RYBAT Lite - Database Connection Manager

Owns the asyncpg connection pool and provides it to repositories.
"""

import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, Any, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


def record_to_dict(record: asyncpg.Record) -> Dict[str, Any]:
    """Convert an asyncpg Record to a JSON-safe dict."""
    d = dict(record)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif hasattr(v, 'value'):
            d[k] = str(v)
    return d


class Database:
    """Manages the asyncpg connection pool and exposes repository accessors."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

        self._signals = None
        self._reputation = None
        self._metrics = None
        self._screening = None
        self._cache = None
        self._source_flags = None
        self._feed_sources = None

    async def connect(self) -> None:
        """Create the connection pool and create tables (phase 1 only)."""
        from config import config
        from database.schema import DatabaseSchema

        min_size = config.DB_POOL_MIN_SIZE
        max_size = config.DB_POOL_MAX_SIZE

        logger.info(f"Connecting to PostgreSQL (pool: {min_size}-{max_size})...")
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=30,
            statement_cache_size=256,
            server_settings={'jit': 'off'},
        )

        await DatabaseSchema.initialize_tables(self._pool)

        from database.repositories.signals import SignalRepository
        from database.repositories.reputation import ReputationRepository
        from database.repositories.metrics import MetricsRepository
        from database.repositories.screening import ScreeningRepository
        from database.repositories.cache import CacheRepository
        from database.repositories.source_flags import SourceFlagsRepository
        from database.repositories.feed_sources import FeedSourcesRepository

        self._signals = SignalRepository(self._pool)
        self._reputation = ReputationRepository(self._pool)
        self._metrics = MetricsRepository(self._pool)
        self._screening = ScreeningRepository(self._pool)
        self._cache = CacheRepository(self._pool)
        self._source_flags = SourceFlagsRepository(self._pool)
        self._feed_sources = FeedSourcesRepository(self._pool)

        logger.info("PostgreSQL connection pool ready")

    async def close(self) -> None:
        if self._pool:
            try:
                await asyncio.wait_for(self._pool.close(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Pool.close() timed out — terminating")
                self._pool.terminate()
            logger.info("PostgreSQL connection pool closed")

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    @property
    def signals(self):
        return self._signals

    @property
    def reputation(self):
        return self._reputation

    @property
    def metrics(self):
        return self._metrics

    @property
    def screening(self):
        return self._screening

    @property
    def cache(self):
        return self._cache

    @property
    def source_flags(self):
        return self._source_flags

    @property
    def feed_sources(self):
        return self._feed_sources
