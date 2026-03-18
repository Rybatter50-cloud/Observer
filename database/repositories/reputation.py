"""
RYBAT Intelligence Platform - Reputation Repository

Source and author reputation tracking with rolling-average upserts.

Uses REAL (float) arithmetic instead of INTEGER division to prevent
precision loss over time as sample_count grows.

2026-02-09 | Mr Cat + Claude | Extracted from monolithic IntelligenceDB
"""

import asyncpg
from typing import Dict, Any, Optional

from database.connection import record_to_dict
from utils.logging import get_logger

logger = get_logger(__name__)


class ReputationRepository:
    """Read/write operations for source_reputation and author_reputation."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ==================================================================
    # SOURCE REPUTATION
    # ==================================================================

    async def get_source(self, source_name: str) -> Optional[Dict[str, Any]]:
        """Look up stored reliability score for a source."""
        try:
            row = await self._pool.fetchrow(
                "SELECT * FROM source_reputation WHERE source_name = $1",
                source_name,
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting source reputation: {e}")
            return None

    async def upsert_source(self, source_name: str, new_score: int) -> None:
        """Update source reputation with a new AI score (rolling average)."""
        try:
            await ReputationRepository.upsert_source_on_conn(
                self._pool, source_name, new_score
            )
        except Exception as e:
            logger.error(f"Error upserting source reputation: {e}")

    @staticmethod
    async def upsert_source_on_conn(
        conn, source_name: str, new_score: int
    ) -> None:
        """
        Upsert source reputation on a given connection (for transactional use).

        Works with both asyncpg.Connection and asyncpg.Pool.
        """
        await conn.execute(
            """INSERT INTO source_reputation (source_name, reliability_score, sample_count)
               VALUES ($1, $2, 1)
               ON CONFLICT (source_name) DO UPDATE SET
                   reliability_score = (
                       source_reputation.reliability_score * source_reputation.sample_count
                       + EXCLUDED.reliability_score
                   ) / (source_reputation.sample_count + 1),
                   sample_count = source_reputation.sample_count + 1,
                   last_updated = NOW()""",
            source_name, float(new_score),
        )

    # ==================================================================
    # AUTHOR REPUTATION
    # ==================================================================

    async def get_author(self, author_name: str) -> Optional[Dict[str, Any]]:
        """Look up stored credibility score for an author."""
        try:
            row = await self._pool.fetchrow(
                "SELECT * FROM author_reputation WHERE author_name = $1",
                author_name,
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting author reputation: {e}")
            return None

    async def upsert_author(self, author_name: str, new_score: int) -> None:
        """Update author reputation with a new AI score (rolling average)."""
        try:
            await ReputationRepository.upsert_author_on_conn(
                self._pool, author_name, new_score
            )
        except Exception as e:
            logger.error(f"Error upserting author reputation: {e}")

    @staticmethod
    async def upsert_author_on_conn(
        conn, author_name: str, new_score: int
    ) -> None:
        """
        Upsert author reputation on a given connection (for transactional use).

        Works with both asyncpg.Connection and asyncpg.Pool.
        """
        await conn.execute(
            """INSERT INTO author_reputation (author_name, credibility_score, sample_count)
               VALUES ($1, $2, 1)
               ON CONFLICT (author_name) DO UPDATE SET
                   credibility_score = (
                       author_reputation.credibility_score * author_reputation.sample_count
                       + EXCLUDED.credibility_score
                   ) / (author_reputation.sample_count + 1),
                   sample_count = author_reputation.sample_count + 1,
                   last_updated = NOW()""",
            author_name, float(new_score),
        )
