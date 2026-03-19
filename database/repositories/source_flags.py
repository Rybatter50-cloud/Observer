"""
Observer Intelligence Platform - Source Fetch Flags Repository

Tracks domains flagged as having paywalls or subscriber walls.
Used by the fetch-fulltext endpoint and the client modal to
disable the Fetch Full Text button for unfetchable sources.

2026-02-21 | Mr Cat + Claude | Paywall/subscriber-wall detection
"""

import asyncpg
from typing import Dict, Any, List, Optional

from database.connection import record_to_dict
from utils.logging import get_logger

logger = get_logger(__name__)


class SourceFlagsRepository:
    """CRUD for source_fetch_flags table."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_all_flags(self) -> List[Dict[str, Any]]:
        """Return all flagged domains."""
        try:
            rows = await self._pool.fetch(
                "SELECT * FROM source_fetch_flags ORDER BY detected_at DESC"
            )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching source flags: {e}")
            return []

    async def get_blocked_domains(self) -> Dict[str, str]:
        """
        Return a domain -> flag_type map for all blocked domains.
        flag_type is 'paywall' or 'subscriber_wall'.
        """
        try:
            rows = await self._pool.fetch(
                """SELECT domain, has_paywall, has_subscriber_wall
                   FROM source_fetch_flags
                   WHERE has_paywall = TRUE OR has_subscriber_wall = TRUE"""
            )
            result = {}
            for r in rows:
                if r['has_paywall']:
                    result[r['domain']] = 'paywall'
                else:
                    result[r['domain']] = 'subscriber_wall'
            return result
        except Exception as e:
            logger.error(f"Error fetching blocked domains: {e}")
            return {}

    async def is_domain_blocked(self, domain: str) -> Optional[str]:
        """
        Check if a domain is blocked. Returns the flag type
        ('paywall' or 'subscriber_wall') or None if not blocked.
        """
        try:
            row = await self._pool.fetchrow(
                """SELECT has_paywall, has_subscriber_wall
                   FROM source_fetch_flags
                   WHERE domain = $1""",
                domain,
            )
            if not row:
                return None
            if row['has_paywall']:
                return 'paywall'
            if row['has_subscriber_wall']:
                return 'subscriber_wall'
            return None
        except Exception as e:
            logger.error(f"Error checking domain flags for {domain}: {e}")
            return None

    async def flag_domain(
        self,
        domain: str,
        flag_type: str,
        source_name: Optional[str] = None,
    ) -> None:
        """
        Flag a domain as having a paywall or subscriber wall.
        flag_type must be 'paywall' or 'subscriber_wall'.
        """
        try:
            if flag_type == 'paywall':
                await self._pool.execute(
                    """INSERT INTO source_fetch_flags (domain, has_paywall, source_name)
                       VALUES ($1, TRUE, $2)
                       ON CONFLICT (domain) DO UPDATE
                       SET has_paywall = TRUE, detected_at = NOW()""",
                    domain, source_name,
                )
            elif flag_type == 'subscriber_wall':
                await self._pool.execute(
                    """INSERT INTO source_fetch_flags (domain, has_subscriber_wall, source_name)
                       VALUES ($1, TRUE, $2)
                       ON CONFLICT (domain) DO UPDATE
                       SET has_subscriber_wall = TRUE, detected_at = NOW()""",
                    domain, source_name,
                )
            logger.info(f"Flagged domain {domain} as {flag_type}")
        except Exception as e:
            logger.error(f"Error flagging domain {domain}: {e}")

    async def unflag_domain(self, domain: str) -> None:
        """Remove all flags for a domain."""
        try:
            await self._pool.execute(
                "DELETE FROM source_fetch_flags WHERE domain = $1", domain
            )
        except Exception as e:
            logger.error(f"Error unflagging domain {domain}: {e}")
