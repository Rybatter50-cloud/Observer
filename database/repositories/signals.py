"""
Observer Intelligence Platform - Signal Repository

All CRUD operations for intel_signals table.
Includes PostgreSQL-native fuzzy deduplication via pg_trgm.

2026-02-09 | Mr Cat + Claude | Extracted from monolithic IntelligenceDB
"""

import asyncpg
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from database.connection import record_to_dict
from utils.logging import get_logger

logger = get_logger(__name__)


class SignalRepository:
    """Read/write operations for intel_signals."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ==================================================================
    # READ
    # ==================================================================

    async def url_exists(self, url: str) -> bool:
        """Check if a URL already exists."""
        try:
            val = await self._pool.fetchval(
                "SELECT 1 FROM intel_signals WHERE url = $1 LIMIT 1", url
            )
            return val is not None
        except Exception as e:
            logger.error(f"Error checking URL existence: {e}")
            return False

    async def get_recent_titles(self, hours: int = 24) -> List[str]:
        """Get titles of recent signals for deduplication."""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            rows = await self._pool.fetch(
                "SELECT title FROM intel_signals WHERE created_at >= $1 ORDER BY created_at DESC",
                cutoff,
            )
            return [r['title'] for r in rows if r['title']]
        except Exception as e:
            logger.error(f"Error getting recent titles: {e}")
            return []

    async def find_similar_title(
        self, title: str, threshold: float = 0.85, hours: int = 24
    ) -> bool:
        """
        Check for a fuzzy-duplicate title using pg_trgm similarity().

        This replaces the O(n) Python SequenceMatcher loop with an
        indexed database query. The GIN index on title makes this O(1).
        """
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            val = await self._pool.fetchval(
                """SELECT 1 FROM intel_signals
                   WHERE created_at >= $1
                     AND similarity(title, $2) >= $3
                   LIMIT 1""",
                cutoff, title, threshold,
            )
            return val is not None
        except Exception as e:
            logger.error(f"Error in fuzzy title check: {e}")
            return False

    def _build_filter_clause(
        self,
        time_window: Optional[str] = None,
        search: Optional[str] = None,
        source_groups: Optional[List[str]] = None,
        content_search: Optional[List[str]] = None,
        min_score: Optional[int] = None,
        risk_indicators: Optional[List[str]] = None,
        translated_only: bool = False,
        screening_only: bool = False,
    ):
        """
        Build a reusable (WHERE clause, params, next_idx) tuple from filters.
        Used by both get_signals() and count_signals().

        When both source_groups and content_search are provided, they are
        OR'd together: (source_group IN (...) OR title/desc/loc ILIKE ...).
        This enables "stacked" AOR Region + AOR News compound filters.
        """
        conditions = ["processed = TRUE"]
        params: list = []
        idx = 1  # asyncpg $1, $2, ...

        # Time window
        windows = {
            "4h": timedelta(hours=4),
            "24h": timedelta(hours=24),
            "72h": timedelta(hours=72),
            "7d": timedelta(days=7),
        }
        if time_window in windows:
            conditions.append(f"created_at >= ${idx}")
            params.append(datetime.now() - windows[time_window])
            idx += 1

        # Text search (ILIKE across multiple columns)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            conditions.append(
                f"(title ILIKE ${idx} OR description ILIKE ${idx}"
                f" OR location ILIKE ${idx} OR source ILIKE ${idx}"
                f" OR author ILIKE ${idx})"
            )
            params.append(pattern)
            idx += 1

        # Source groups (AOR Region) and/or content search (AOR News)
        # When both are present, OR them: feeds FROM the region + articles ABOUT the region
        sg_clause = None
        cs_clause = None

        if source_groups:
            placeholders = ", ".join(f"${idx + i}" for i in range(len(source_groups)))
            sg_clause = f"source_group IN ({placeholders})"
            params.extend(source_groups)
            idx += len(source_groups)

        if content_search:
            # Build OR'd ILIKE conditions for each country name
            ilike_parts = []
            for term in content_search:
                pattern = f"%{term}%"
                ilike_parts.append(
                    f"(title ILIKE ${idx} OR description ILIKE ${idx}"
                    f" OR location ILIKE ${idx})"
                )
                params.append(pattern)
                idx += 1
            cs_clause = "(" + " OR ".join(ilike_parts) + ")"

        if sg_clause and cs_clause:
            # Stacked: Region OR News
            conditions.append(f"({sg_clause} OR {cs_clause})")
        elif sg_clause:
            conditions.append(sg_clause)
        elif cs_clause:
            conditions.append(cs_clause)

        # Minimum score
        if min_score is not None and min_score > 0:
            conditions.append(f"relevance_score >= ${idx}")
            params.append(min_score)
            idx += 1

        # Risk indicators (overlap with ANY)
        if risk_indicators:
            conditions.append(f"risk_indicators && ${idx}")
            params.append(risk_indicators)
            idx += 1

        # Translated only
        if translated_only:
            conditions.append("is_translated = TRUE")

        # Screening only
        if screening_only:
            conditions.append(
                "screening_hits IS NOT NULL"
                " AND (screening_hits->>'hit_count')::int > 0"
            )

        where = " AND ".join(conditions)
        return where, params, idx

    async def get_signals(
        self,
        time_window: Optional[str] = None,
        limit: int = 75000,
        offset: int = 0,
        search: Optional[str] = None,
        source_groups: Optional[List[str]] = None,
        content_search: Optional[List[str]] = None,
        min_score: Optional[int] = None,
        risk_indicators: Optional[List[str]] = None,
        translated_only: bool = False,
        screening_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve processed signals with optional time filtering, server-side
        search/filter, and pagination.

        Args:
            time_window: '4h', '24h', '72h', '7d', or None for all
            limit: Maximum rows
            offset: Number of rows to skip (for pagination)
            search: Text search across title, description, location, source, author
            source_groups: Filter by source_group IN (...)
            content_search: Country names for content ILIKE (AOR News)
            min_score: Minimum relevance_score
            risk_indicators: Filter by signals containing ANY of these indicators
            translated_only: Only return translated signals
            screening_only: Only return signals with screening hits
        """
        try:
            where, params, idx = self._build_filter_clause(
                time_window, search, source_groups, content_search,
                min_score, risk_indicators, translated_only, screening_only,
            )

            params.append(limit)
            limit_idx = idx
            idx += 1
            params.append(offset)
            offset_idx = idx

            query = (
                f"SELECT * FROM intel_signals WHERE {where}"
                f" ORDER BY created_at DESC"
                f" LIMIT ${limit_idx} OFFSET ${offset_idx}"
            )

            rows = await self._pool.fetch(query, *params)
            return [record_to_dict(r) for r in rows]

        except Exception as e:
            logger.error(f"Error retrieving signals: {e}")
            return []

    async def count_signals(
        self,
        time_window: Optional[str] = None,
        search: Optional[str] = None,
        source_groups: Optional[List[str]] = None,
        content_search: Optional[List[str]] = None,
        min_score: Optional[int] = None,
        risk_indicators: Optional[List[str]] = None,
        translated_only: bool = False,
        screening_only: bool = False,
    ) -> int:
        """
        Count processed signals matching the given filters (no LIMIT/OFFSET).
        Returns total matching row count for pagination metadata.
        """
        try:
            where, params, _ = self._build_filter_clause(
                time_window, search, source_groups, content_search,
                min_score, risk_indicators, translated_only, screening_only,
            )
            query = f"SELECT COUNT(*) FROM intel_signals WHERE {where}"
            return await self._pool.fetchval(query, *params) or 0
        except Exception as e:
            logger.error(f"Error counting signals: {e}")
            return 0

    async def get_by_id(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a single signal by ID."""
        try:
            row = await self._pool.fetchrow(
                "SELECT * FROM intel_signals WHERE id = $1", signal_id
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving signal {signal_id}: {e}")
            return None

    async def count_unprocessed(self) -> int:
        """Count signals with processed=FALSE (for crash recovery)."""
        try:
            return await self._pool.fetchval(
                "SELECT COUNT(*) FROM intel_signals WHERE processed = FALSE"
            ) or 0
        except Exception as e:
            logger.error(f"Error counting unprocessed: {e}")
            return 0

    async def get_next_unprocessed(self) -> Optional[Dict[str, Any]]:
        """Get a single unprocessed signal for recovery."""
        try:
            row = await self._pool.fetchrow(
                "SELECT * FROM intel_signals WHERE processed = FALSE LIMIT 1"
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting unprocessed signal: {e}")
            return None

    # ==================================================================
    # WRITE
    # ==================================================================

    async def insert_signal(
        self,
        title: str,
        url: str,
        source: str,
        location: str = "Unknown",
        relevance_score: int = 0,
        casualties: int = 0,
        published_at: Optional[str] = None,
        risk_indicators: Optional[List[str]] = None,
        description: Optional[str] = None,
        full_text: Optional[str] = None,
        collector: Optional[str] = None,
        processed: bool = False,
        analysis_mode: str = "PENDING",
        is_translated: bool = False,
        source_language: Optional[str] = None,
        translation_source: Optional[str] = None,
        author: Optional[str] = None,
        source_confidence: int = 0,
        author_confidence: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Insert a signal. Returns the inserted row or None if duplicate URL.
        """
        try:
            row = await self._pool.fetchrow(
                """INSERT INTO intel_signals
                   (title, description, full_text, location, relevance_score,
                    casualties, published_at, url, source, collector,
                    risk_indicators, processed, analysis_mode,
                    is_translated, source_language, translation_source,
                    author, source_confidence, author_confidence)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                   ON CONFLICT (url) DO NOTHING
                   RETURNING *""",
                title, description, full_text, location, relevance_score,
                casualties, published_at, url, source, collector,
                risk_indicators or [], processed, analysis_mode,
                is_translated, source_language, translation_source,
                author, source_confidence, author_confidence,
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error inserting signal: {e}")
            return None

    async def insert_final_signal(
        self, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Insert a fully-processed signal in a single transaction.
        Also upserts source/author reputation atomically.

        Returns the complete signal dict for broadcast, or None on dup/error.
        """
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    import json as _json
                    _entities_json = data.get('entities_json')
                    _entities_json_str = _json.dumps(_entities_json) if _entities_json else None

                    row = await conn.fetchrow(
                        """INSERT INTO intel_signals
                           (title, description, full_text, url, published_at,
                            source, collector, location, relevance_score,
                            casualties, risk_indicators, processed,
                            analysis_mode, source_confidence,
                            author_confidence, is_translated, source_language,
                            translation_source, author, source_group,
                            original_title, entities_json, entities_tier)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22::jsonb,$23)
                           ON CONFLICT (url) DO NOTHING
                           RETURNING *""",
                        data['title'],
                        data.get('description'),
                        data.get('full_text'),
                        data['url'],
                        data.get('published_at'),
                        data.get('source_label', data.get('source_name', 'Unknown')),
                        data.get('collector_name', 'unknown'),
                        data.get('location', 'Unknown'),
                        data.get('relevance_score', 0),
                        data.get('casualties', 0),
                        data.get('risk_indicators', []),
                        True,
                        data.get('analysis_mode', 'SKIPPED'),
                        data.get('source_confidence', 0),
                        data.get('author_confidence', 0),
                        data.get('is_translated', False),
                        data.get('source_language'),
                        data.get('translation_source'),
                        data.get('author'),
                        data.get('source_group'),
                        data.get('original_title'),
                        _entities_json_str,
                        data.get('entities_tier', 0),
                    )

                    if row is not None:
                        # Reputation upserts in the same transaction
                        from database.repositories.reputation import ReputationRepository
                        source_name = data.get('source_name', data.get('source_label', 'Unknown'))
                        await ReputationRepository.upsert_source_on_conn(
                            conn, source_name, data.get('source_confidence', 0)
                        )
                        author = data.get('author_name', data.get('author', ''))
                        if author and author.strip():
                            await ReputationRepository.upsert_author_on_conn(
                                conn, author.strip(), data.get('author_confidence', 0)
                            )

            if row is None:
                logger.warning(
                    f"Duplicate URL skipped: {data.get('url', '?')[:80]}"
                )
            return record_to_dict(row) if row else None

        except Exception as e:
            logger.error(f"Final signal insert failed: {e} (url={data.get('url', '?')[:60]})")
            return None

    async def update_analysis(
        self, signal_id: int, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a signal with analysis results + reputation upserts.
        Returns the complete signal dict for broadcast.
        """
        u = updates
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """UPDATE intel_signals SET
                           location = $1, casualties = $2,
                           risk_indicators = $3,
                           relevance_score = $4,
                           source_confidence = $5, author_confidence = $6,
                           processed = TRUE, analysis_mode = $7
                           WHERE id = $8""",
                        u['location'], u['casualties'],
                        u.get('risk_indicators', []),
                        u['relevance_score'],
                        u['source_confidence'], u['author_confidence'],
                        u['analysis_mode'], signal_id,
                    )

                    from database.repositories.reputation import ReputationRepository
                    await ReputationRepository.upsert_source_on_conn(
                        conn, u['source_name'], u['source_confidence']
                    )
                    author = u.get('author_name', '')
                    if author and author.strip():
                        await ReputationRepository.upsert_author_on_conn(
                            conn, author.strip(), u['author_confidence']
                        )

                    row = await conn.fetchrow(
                        "SELECT * FROM intel_signals WHERE id = $1", signal_id
                    )

            return record_to_dict(row) if row else None

        except Exception as e:
            logger.error(f"Analysis update failed for signal {signal_id}: {e}")
            return None

    async def update_score_indicators(
        self, signal_id: int, relevance_score: int, risk_indicators: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Update only the relevance_score and risk_indicators for a signal.
        Used by analyst manual re-scoring from the feed interface.
        Sets analysis_mode to 'MANUAL' to distinguish hand-curated labels.
        Returns the updated signal dict for broadcast, or None on error.
        """
        try:
            row = await self._pool.fetchrow(
                """UPDATE intel_signals
                   SET relevance_score = $1,
                       risk_indicators = $2,
                       analysis_mode = 'MANUAL'
                   WHERE id = $3
                   RETURNING *""",
                relevance_score, risk_indicators, signal_id,
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Score/indicator update failed for signal {signal_id}: {e}")
            return None

    async def update_screening_hits(
        self, signal_id: int, screening_data: Dict[str, Any]
    ) -> None:
        """Store auto-screening results as JSONB on a signal row."""
        try:
            import json
            await self._pool.execute(
                "UPDATE intel_signals SET screening_hits = $1::jsonb WHERE id = $2",
                json.dumps(screening_data),
                signal_id,
            )
        except Exception as e:
            logger.error(f"Failed to store screening hits for signal {signal_id}: {e}")

    async def update_full_text(
        self, signal_id: int, full_text: str
    ) -> Optional[Dict[str, Any]]:
        """Store fetched full article text. Returns updated signal dict."""
        try:
            row = await self._pool.fetchrow(
                """UPDATE intel_signals SET full_text = $1
                   WHERE id = $2 RETURNING *""",
                full_text, signal_id,
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Full text update failed for signal {signal_id}: {e}")
            return None

    async def cleanup_old(self, days: int = 30) -> int:
        """Delete signals older than the given number of days."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            status = await self._pool.execute(
                "DELETE FROM intel_signals WHERE created_at < $1", cutoff
            )
            deleted = int(status.split()[-1])
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old signals")
            return deleted
        except Exception as e:
            logger.error(f"Error cleaning up old signals: {e}")
            return 0
