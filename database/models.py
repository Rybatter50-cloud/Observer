"""
Observer Lite - Database Models (Backward-Compatible Facade)

Delegates all operations to the repository layer.
"""

import asyncpg
from typing import List, Dict, Optional, Any

from database.connection import record_to_dict
from utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ['IntelligenceDB', 'record_to_dict']


class IntelligenceDB:
    """Backward-compatible database access layer for Observer."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._db = None

    async def connect(self) -> None:
        from database.connection import Database
        from database.schema import DatabaseSchema
        from database.migrations.runner import MigrationRunner

        self._db = Database(self.dsn)
        await self._db.connect()

        try:
            applied = await MigrationRunner.run(self._db.pool)
            if applied > 0:
                logger.info(f"Applied {applied} migration(s)")
        except Exception as e:
            logger.error(f"Migration runner failed: {e}")
            raise

        await DatabaseSchema.initialize_indexes(self._db.pool)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._db is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._db.pool

    # Repository accessors
    @property
    def signals(self):
        return self._db.signals

    @property
    def reputation(self):
        return self._db.reputation

    @property
    def metrics(self):
        return self._db.metrics

    @property
    def screening(self):
        return self._db.screening

    @property
    def cache(self):
        return self._db.cache

    @property
    def source_flags(self):
        return self._db.source_flags

    @property
    def feed_sources(self):
        return self._db.feed_sources

    # Legacy read methods
    async def url_exists(self, url: str) -> bool:
        return await self._db.signals.url_exists(url)

    async def find_similar_title(self, title: str, threshold: float = 0.85, hours: int = 24) -> bool:
        return await self._db.signals.find_similar_title(title, threshold, hours)

    async def get_recent_titles(self, hours: int = 24) -> List[str]:
        return await self._db.signals.get_recent_titles(hours)

    async def get_signals(
        self,
        time_window: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        **filters,
    ) -> List[Dict[str, Any]]:
        from config import config
        if limit is None:
            limit = config.MAX_SIGNALS_LIMIT
        return await self._db.signals.get_signals(time_window, limit, offset, **filters)

    async def count_signals(self, time_window: Optional[str] = None, **filters) -> int:
        return await self._db.signals.count_signals(time_window, **filters)

    async def get_signal_by_id(self, signal_id: int) -> Optional[Dict[str, Any]]:
        return await self._db.signals.get_by_id(signal_id)

    # Legacy write methods
    async def insert_signal(
        self, title, location, relevance_score, casualties, time_str, url, source,
        risk_indicators=None, is_translated=False, source_language=None,
        translation_source=None, description=None, full_text=None,
        collector=None, processed=0,
    ) -> Optional[Dict[str, Any]]:
        return await self._db.signals.insert_signal(
            title=title, url=url, source=source, location=location,
            relevance_score=relevance_score, casualties=casualties,
            published_at=time_str, risk_indicators=risk_indicators or [],
            description=description, full_text=full_text, collector=collector,
            processed=bool(processed), is_translated=is_translated,
            source_language=source_language, translation_source=translation_source,
        )

    async def cleanup_old_signals(self, days: int = 30) -> int:
        return await self._db.signals.cleanup_old(days)

    async def update_signal_analysis(self, signal_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._db.signals.update_analysis(signal_id, updates)

    async def insert_final_signal(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if 'time_str' in data and 'published_at' not in data:
            data['published_at'] = data['time_str']
        return await self._db.signals.insert_final_signal(data)

    # Legacy reputation methods
    async def get_source_reputation(self, source_name: str) -> Optional[Dict[str, Any]]:
        return await self._db.reputation.get_source(source_name)

    async def get_author_reputation(self, author_name: str) -> Optional[Dict[str, Any]]:
        return await self._db.reputation.get_author(author_name)

    async def upsert_source_reputation(self, source_name: str, new_score: int, conn=None) -> None:
        if conn is not None:
            from database.repositories.reputation import ReputationRepository
            await ReputationRepository.upsert_source_on_conn(conn, source_name, new_score)
        else:
            await self._db.reputation.upsert_source(source_name, new_score)

    async def upsert_author_reputation(self, author_name: str, new_score: int, conn=None) -> None:
        if conn is not None:
            from database.repositories.reputation import ReputationRepository
            await ReputationRepository.upsert_author_on_conn(conn, author_name, new_score)
        else:
            await self._db.reputation.upsert_author(author_name, new_score)
