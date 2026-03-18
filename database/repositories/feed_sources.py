"""
RYBAT Intelligence Platform - Feed Sources Repository

CRUD operations for the feed_sources table, which replaces the
feed_registry_comprehensive.json file with proper PostgreSQL storage.

Provides all query patterns needed by:
  - Feed registry API endpoints (list, toggle, delete, stats)
  - Dev console Feed Sites panel
  - RSS and NP4K collectors (startup feed loading)
  - /discover endpoint (dedup check, insert new feeds)
  - Chat commands (/feeds, /lang, /filter)

2026-02-22 | Mr Cat + Claude | JSON → PostgreSQL feed registry migration
"""

import asyncpg
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from database.connection import record_to_dict
from utils.logging import get_logger

logger = get_logger(__name__)


class FeedSourcesRepository:
    """CRUD for the feed_sources table."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ==================================================================
    # READ operations
    # ==================================================================

    async def get_all(self) -> List[Dict[str, Any]]:
        """Return all feed sources ordered by group then name."""
        try:
            rows = await self._pool.fetch(
                "SELECT * FROM feed_sources ORDER BY group_key, name"
            )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching all feed sources: {e}")
            return []

    async def get_by_type(self, feed_type: str) -> List[Dict[str, Any]]:
        """Return feed sources filtered by type ('rss' or 'scraper')."""
        try:
            rows = await self._pool.fetch(
                "SELECT * FROM feed_sources WHERE feed_type = $1 ORDER BY group_key, name",
                feed_type,
            )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching feed sources by type {feed_type}: {e}")
            return []

    async def get_enabled(self, feed_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return enabled feed sources, optionally filtered by type."""
        try:
            if feed_type:
                rows = await self._pool.fetch(
                    """SELECT * FROM feed_sources
                       WHERE enabled = TRUE AND feed_type = $1
                       ORDER BY group_key, name""",
                    feed_type,
                )
            else:
                rows = await self._pool.fetch(
                    "SELECT * FROM feed_sources WHERE enabled = TRUE ORDER BY group_key, name"
                )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching enabled feed sources: {e}")
            return []

    async def get_by_group(self, group_key: str) -> List[Dict[str, Any]]:
        """Return all feed sources for a specific group."""
        try:
            rows = await self._pool.fetch(
                "SELECT * FROM feed_sources WHERE group_key = $1 ORDER BY name",
                group_key,
            )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching feed sources for group {group_key}: {e}")
            return []

    async def get_by_groups(self, group_keys: List[str]) -> List[Dict[str, Any]]:
        """Return enabled feed sources for a list of groups."""
        if not group_keys:
            return []
        try:
            rows = await self._pool.fetch(
                """SELECT * FROM feed_sources
                   WHERE group_key = ANY($1) AND enabled = TRUE
                   ORDER BY group_key, name""",
                group_keys,
            )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching feed sources by groups: {e}")
            return []

    async def get_by_language(self, language: str) -> List[Dict[str, Any]]:
        """Return feed sources filtered by language code."""
        try:
            rows = await self._pool.fetch(
                "SELECT * FROM feed_sources WHERE language = $1 ORDER BY group_key, name",
                language,
            )
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching feed sources by language {language}: {e}")
            return []

    async def get_all_domains(self) -> set:
        """Return a set of all domains currently in the registry."""
        try:
            rows = await self._pool.fetch("SELECT DISTINCT domain FROM feed_sources")
            return {r['domain'] for r in rows}
        except Exception as e:
            logger.error(f"Error fetching domains: {e}")
            return set()

    async def get_all_urls(self) -> set:
        """Return a set of all feed URLs currently in the registry."""
        try:
            rows = await self._pool.fetch("SELECT url FROM feed_sources")
            return {r['url'] for r in rows}
        except Exception as e:
            logger.error(f"Error fetching URLs: {e}")
            return set()

    async def domain_exists(self, domain: str) -> bool:
        """Check if a domain is already in the registry."""
        try:
            result = await self._pool.fetchval(
                "SELECT EXISTS(SELECT 1 FROM feed_sources WHERE domain = $1)",
                domain.lower().lstrip('www.'),
            )
            return result
        except Exception as e:
            logger.error(f"Error checking domain existence: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics about feed sources."""
        try:
            row = await self._pool.fetchrow("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE feed_type = 'rss') AS rss_count,
                    COUNT(*) FILTER (WHERE feed_type = 'scraper') AS scraper_count,
                    COUNT(*) FILTER (WHERE enabled = TRUE) AS enabled_count,
                    COUNT(DISTINCT group_key) AS group_count,
                    COUNT(DISTINCT language) AS language_count
                FROM feed_sources
            """)
            stats = record_to_dict(row) if row else {}

            # Language breakdown
            lang_rows = await self._pool.fetch("""
                SELECT language, COUNT(*) AS count
                FROM feed_sources
                GROUP BY language
                ORDER BY count DESC
            """)
            stats['by_language'] = {r['language']: r['count'] for r in lang_rows}

            # Group breakdown (top 20)
            group_rows = await self._pool.fetch("""
                SELECT group_key, COUNT(*) AS count
                FROM feed_sources
                GROUP BY group_key
                ORDER BY count DESC
                LIMIT 20
            """)
            stats['by_group'] = {r['group_key']: r['count'] for r in group_rows}

            # Groups list
            groups = await self._pool.fetch("""
                SELECT DISTINCT group_key, group_label, lat, lon
                FROM feed_sources
                ORDER BY group_key
            """)
            stats['groups'] = [record_to_dict(g) for g in groups]

            return stats
        except Exception as e:
            logger.error(f"Error getting feed source stats: {e}")
            return {}

    async def get_groups_summary(self) -> List[Dict[str, Any]]:
        """Return summary of each group with feed counts."""
        try:
            rows = await self._pool.fetch("""
                SELECT
                    group_key,
                    MAX(group_label) AS group_label,
                    MAX(lat) AS lat,
                    MAX(lon) AS lon,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE feed_type = 'rss') AS rss_count,
                    COUNT(*) FILTER (WHERE feed_type = 'scraper') AS scraper_count,
                    COUNT(*) FILTER (WHERE enabled = TRUE) AS enabled_count
                FROM feed_sources
                GROUP BY group_key
                ORDER BY group_key
            """)
            return [record_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error getting groups summary: {e}")
            return []

    async def count(self) -> int:
        """Return total count of feed sources."""
        try:
            return await self._pool.fetchval("SELECT COUNT(*) FROM feed_sources") or 0
        except Exception as e:
            logger.error(f"Error counting feed sources: {e}")
            return 0

    # ==================================================================
    # WRITE operations
    # ==================================================================

    async def insert(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Insert a single feed source. Returns the inserted row or None on conflict.
        """
        try:
            # Extract domain from URL if not provided
            domain = source.get('domain', '')
            if not domain and source.get('url'):
                parsed = urlparse(source['url'])
                domain = (parsed.hostname or '').lower().lstrip('www.')

            row = await self._pool.fetchrow("""
                INSERT INTO feed_sources
                    (group_key, group_label, name, url, domain, feed_type,
                     language, city, country, enabled, lat, lon, description)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (url, feed_type) DO NOTHING
                RETURNING *
            """,
                source.get('group_key', ''),
                source.get('group_label', ''),
                source.get('name', 'Unknown'),
                source['url'],
                domain,
                source.get('feed_type', 'rss'),
                source.get('language', 'en'),
                source.get('city', ''),
                source.get('country', ''),
                source.get('enabled', True),
                source.get('lat'),
                source.get('lon'),
                source.get('description', ''),
            )
            return record_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error inserting feed source: {e}")
            return None

    async def insert_batch(self, sources: List[Dict[str, Any]]) -> int:
        """
        Insert multiple feed sources in a single transaction.
        Returns count of successfully inserted rows.
        """
        if not sources:
            return 0
        inserted = 0
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    for source in sources:
                        domain = source.get('domain', '')
                        if not domain and source.get('url'):
                            parsed = urlparse(source['url'])
                            domain = (parsed.hostname or '').lower().lstrip('www.')

                        result = await conn.execute("""
                            INSERT INTO feed_sources
                                (group_key, group_label, name, url, domain, feed_type,
                                 language, city, country, enabled, lat, lon, description)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                            ON CONFLICT (url, feed_type) DO NOTHING
                        """,
                            source.get('group_key', ''),
                            source.get('group_label', ''),
                            source.get('name', 'Unknown'),
                            source['url'],
                            domain,
                            source.get('feed_type', 'rss'),
                            source.get('language', 'en'),
                            source.get('city', ''),
                            source.get('country', ''),
                            source.get('enabled', True),
                            source.get('lat'),
                            source.get('lon'),
                            source.get('description', ''),
                        )
                        if result and 'INSERT 0 1' in result:
                            inserted += 1
            logger.info(f"Batch inserted {inserted}/{len(sources)} feed sources")
        except Exception as e:
            logger.error(f"Error batch inserting feed sources: {e}")
        return inserted

    async def toggle(self, feed_id: int) -> Optional[bool]:
        """Toggle enabled state for a feed source by ID. Returns new state."""
        try:
            new_state = await self._pool.fetchval("""
                UPDATE feed_sources
                SET enabled = NOT enabled
                WHERE id = $1
                RETURNING enabled
            """, feed_id)
            return new_state
        except Exception as e:
            logger.error(f"Error toggling feed source {feed_id}: {e}")
            return None

    async def toggle_by_url(self, url: str, feed_type: str) -> Optional[bool]:
        """Toggle enabled state by URL + type. Returns new state."""
        try:
            new_state = await self._pool.fetchval("""
                UPDATE feed_sources
                SET enabled = NOT enabled
                WHERE url = $1 AND feed_type = $2
                RETURNING enabled
            """, url, feed_type)
            return new_state
        except Exception as e:
            logger.error(f"Error toggling feed source {url}: {e}")
            return None

    async def set_enabled(self, feed_id: int, enabled: bool) -> bool:
        """Set enabled state for a feed source."""
        try:
            await self._pool.execute(
                "UPDATE feed_sources SET enabled = $1 WHERE id = $2",
                enabled, feed_id,
            )
            return True
        except Exception as e:
            logger.error(f"Error setting enabled for feed source {feed_id}: {e}")
            return False

    async def set_enabled_by_group(self, group_key: str, enabled: bool) -> int:
        """Enable or disable all feeds in a group. Returns count updated."""
        try:
            result = await self._pool.execute(
                "UPDATE feed_sources SET enabled = $1 WHERE group_key = $2",
                enabled, group_key,
            )
            count = int(result.split()[-1]) if result else 0
            return count
        except Exception as e:
            logger.error(f"Error bulk-toggling group {group_key}: {e}")
            return 0

    async def set_all_enabled(self, enabled: bool) -> int:
        """Enable or disable ALL feeds. Returns count updated."""
        try:
            result = await self._pool.execute(
                "UPDATE feed_sources SET enabled = $1", enabled,
            )
            count = int(result.split()[-1]) if result else 0
            return count
        except Exception as e:
            logger.error(f"Error setting all feeds enabled={enabled}: {e}")
            return 0

    async def set_enabled_by_language(self, language: str, enabled: bool) -> int:
        """Enable or disable all feeds matching a language. Returns count updated."""
        try:
            result = await self._pool.execute(
                "UPDATE feed_sources SET enabled = $1 WHERE language = $2",
                enabled, language,
            )
            count = int(result.split()[-1]) if result else 0
            return count
        except Exception as e:
            logger.error(f"Error toggling language {language}: {e}")
            return 0

    async def delete(self, feed_id: int) -> bool:
        """Delete a feed source by ID."""
        try:
            result = await self._pool.execute(
                "DELETE FROM feed_sources WHERE id = $1", feed_id,
            )
            return 'DELETE 1' in result
        except Exception as e:
            logger.error(f"Error deleting feed source {feed_id}: {e}")
            return False

    async def delete_by_url(self, url: str, feed_type: str) -> bool:
        """Delete a feed source by URL + type."""
        try:
            result = await self._pool.execute(
                "DELETE FROM feed_sources WHERE url = $1 AND feed_type = $2",
                url, feed_type,
            )
            return 'DELETE 1' in result
        except Exception as e:
            logger.error(f"Error deleting feed source {url}: {e}")
            return False

    async def update_probe_status(
        self, feed_id: int, status: str
    ) -> bool:
        """Update probe status and timestamp for a feed source."""
        try:
            await self._pool.execute("""
                UPDATE feed_sources
                SET probe_status = $1, last_probed = NOW()
                WHERE id = $2
            """, status, feed_id)
            return True
        except Exception as e:
            logger.error(f"Error updating probe status for {feed_id}: {e}")
            return False

    # ==================================================================
    # REGISTRY FORMAT helpers (backward compat with JSON structure)
    # ==================================================================

    async def as_registry_dict(self) -> Dict[str, Any]:
        """
        Return feed sources structured as the old JSON registry format.

        This allows a gradual migration — code that expects the old
        {group_key: {feeds: [...], scraper_sites: [...]}} structure
        can call this method until fully ported.
        """
        try:
            rows = await self._pool.fetch(
                "SELECT * FROM feed_sources ORDER BY group_key, name"
            )
            registry: Dict[str, Any] = {
                '_metadata': {
                    'version': '4.0',
                    'description': 'RYBAT Feed Registry (PostgreSQL-backed)',
                    'last_updated': datetime.now().isoformat(),
                }
            }
            for r in rows:
                gk = r['group_key']
                if gk not in registry:
                    registry[gk] = {
                        'label': r['group_label'] or gk,
                        'feeds': [],
                        'scraper_sites': [],
                    }
                    if r['lat'] is not None:
                        registry[gk]['lat'] = r['lat']
                    if r['lon'] is not None:
                        registry[gk]['lon'] = r['lon']

                entry = {
                    'name': r['name'],
                    'url': r['url'],
                    'language': r['language'] or 'en',
                    'enabled': r['enabled'],
                }
                if r['country']:
                    entry['country'] = r['country']
                if r['city']:
                    entry['city'] = r['city']

                if r['feed_type'] == 'rss':
                    registry[gk]['feeds'].append(entry)
                else:
                    registry[gk]['scraper_sites'].append(entry)

            return registry
        except Exception as e:
            logger.error(f"Error building registry dict: {e}")
            return {'_metadata': {'version': '4.0', 'error': str(e)}}

    # ==================================================================
    # SEEDING from JSON
    # ==================================================================

    async def seed_from_json(self, registry: Dict[str, Any]) -> int:
        """
        Seed the feed_sources table from a JSON registry dict.
        Skips entries that already exist (ON CONFLICT DO NOTHING).
        Returns count of newly inserted rows.
        """
        sources = []
        for group_key, group_data in registry.items():
            if group_key == '_metadata' or not isinstance(group_data, dict):
                continue

            group_label = group_data.get('label', group_key)
            lat = group_data.get('lat')
            lon = group_data.get('lon')

            for feed in group_data.get('feeds', []):
                url = feed.get('url', '').strip()
                if not url:
                    continue
                parsed = urlparse(url)
                domain = (parsed.hostname or '').lower().lstrip('www.')
                sources.append({
                    'group_key': group_key,
                    'group_label': group_label,
                    'name': feed.get('name', domain),
                    'url': url,
                    'domain': domain,
                    'feed_type': 'rss',
                    'language': feed.get('language', 'en'),
                    'city': feed.get('city', ''),
                    'country': feed.get('country', ''),
                    'enabled': feed.get('enabled', True),
                    'lat': lat,
                    'lon': lon,
                    'description': '',
                })

            for site in group_data.get('scraper_sites', []):
                url = site.get('url', '').strip()
                if not url:
                    continue
                parsed = urlparse(url)
                domain = (parsed.hostname or '').lower().lstrip('www.')
                sources.append({
                    'group_key': group_key,
                    'group_label': group_label,
                    'name': site.get('name', domain),
                    'url': url,
                    'domain': domain,
                    'feed_type': 'scraper',
                    'language': site.get('language', 'en'),
                    'city': site.get('city', ''),
                    'country': site.get('country', ''),
                    'enabled': site.get('enabled', True),
                    'lat': lat,
                    'lon': lon,
                    'description': '',
                })

        if not sources:
            return 0

        inserted = await self.insert_batch(sources)
        logger.info(f"Seeded {inserted} feed sources from JSON registry")
        return inserted
