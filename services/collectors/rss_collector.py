"""
RYBAT Intelligence Platform - RSS Collector (Streaming)
=======================================================
Collects articles from RSS/Atom feeds with streaming output.

@created 2026-02-03 by Claude - v1.5.0 Collector Architecture Refactor
@updated 2026-02-04 by Mr Cat + Claude - STREAMING ARCHITECTURE
                                         Articles now yield immediately as collected
                                         No more batch accumulation - true conveyor belt
@updated 2026-02-20 by Mr Cat + Claude - CONCURRENT FETCHING + CONDITIONAL GET
                                         Semaphore-bounded concurrent fetching (default 10)
                                         ETag/Last-Modified caching for HTTP 304 fast-path

This collector:
1. Reads feeds from feed_registry_comprehensive.json
2. Fetches feeds concurrently (bounded by semaphore, default 10)
3. Uses ETag/Last-Modified headers to skip unchanged feeds (HTTP 304)
4. YIELDS each article immediately after parsing
5. Supports geographic group filtering
6. Integrates with content filter for noise reduction

PERFORMANCE:
    Conditional GET: Stores ETag + Last-Modified per feed URL across
    collection cycles. Unchanged feeds return 304 with no body, skipping
    both download and parsing entirely.

    Concurrent fetching: Uses asyncio.Semaphore to fetch N feeds in
    parallel instead of sequentially. With 100 feeds and concurrency=10,
    wall-clock time drops from ~4 minutes to ~30-40 seconds.
"""

import os
import json
import asyncio
import aiohttp
import feedparser
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from html import unescape
from typing import Dict, Any, List, Set, Optional, AsyncGenerator
import re

from .base import BaseCollector, CollectorStats
from utils.logging import get_logger
from utils.sanitizers import sanitize_url, strip_html_tags
from services.content_filter import get_content_filter

logger = get_logger(__name__)


def _parse_date_lenient(entry: Dict[str, Any]) -> Optional[datetime]:
    """
    Parse publication date from feed entry with multiple fallbacks
    """
    date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']
    
    for field in date_fields:
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (TypeError, ValueError):
                continue
    
    # Try string fields
    for field in ['published', 'updated', 'created']:
        date_str = entry.get(field, '')
        if date_str:
            try:
                from dateutil import parser as date_parser
                return date_parser.parse(date_str)
            except (ValueError, ImportError, OverflowError):
                continue
    
    return None


class RSSCollector(BaseCollector):
    """
    RSS/Atom Feed Collector - STREAMING MODE

    Collects articles from feeds defined in feed_registry_comprehensive.json.
    Now yields articles immediately as they are parsed, enabling real-time
    processing instead of batch accumulation.

    Configuration options (via collector_configs['rss'] or .env):
        - concurrency: Max concurrent feed fetches (default: 10)
        - max_articles_per_feed: Max articles to take from each feed (default: 5)

    @updated 2026-02-04 by Mr Cat + Claude - Streaming architecture
    @updated 2026-02-20 by Mr Cat + Claude - Concurrent fetching + conditional GET
    """
    
    # BaseCollector class attributes
    name = "rss"
    display_name = "RSS Feeds"
    description = "Collects articles from RSS/Atom feeds worldwide"
    requires_api_key = False
    supports_groups = True
    default_enabled = True
    
    def __init__(self):
        """Initialize RSS collector"""
        super().__init__()
        
        # =====================================================================
        # Feed registry path resolution
        # =====================================================================
        env_registry_path = os.getenv('FEED_REGISTRY_PATH')
        if env_registry_path:
            self.registry_path = Path(env_registry_path)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.registry_path = project_root / 'feed_registry_comprehensive.json'
        
        self.feed_registry: Dict[str, Any] = {}
        
        # Rate limiting
        self.last_check: Dict[str, datetime] = {}
        self.min_check_interval: int = 300  # 5 minutes
        
        # Content filtering
        self.content_filter = get_content_filter()
        self.rejection_stats: Dict[str, int] = {
            'blacklist_match': 0,
            'whitelist_fail': 0,
            'total_rejected': 0,
            'total_accepted': 0
        }
        
        # Feed health tracking
        self.feed_health: Dict[str, Dict[str, Any]] = {}

        # Conditional-GET cache: stores ETag/Last-Modified per feed URL.
        # Persists across collection cycles (within process lifetime) so
        # subsequent runs skip unchanged feeds via HTTP 304 responses.
        self._feed_cache: Dict[str, Dict[str, str]] = {}
        self._cache_stats = {'hits': 0, 'misses': 0}

        # Per-group article timestamps for 24h counting
        self._group_article_timestamps: Dict[str, List[datetime]] = defaultdict(list)
        
        # Load the registry
        self._load_registry()
        
        logger.info(f"RSSCollector initialized: {self._get_total_feed_count()} feeds in registry")
    
    def _load_registry(self) -> None:
        """Load feed registry from JSON file (sync fallback for init)."""
        try:
            abs_path = self.registry_path.resolve()
            logger.debug(f"Looking for feed registry at: {abs_path}")

            if not self.registry_path.exists():
                logger.error(f"Feed registry not found: {abs_path}")
                return

            with open(self.registry_path, 'r', encoding='utf-8') as f:
                self.feed_registry = json.load(f)

            feed_count = self._get_total_feed_count()
            group_count = len([k for k in self.feed_registry.keys() if k != '_metadata'])
            logger.info(f"Feed registry loaded: {feed_count} feeds in {group_count} groups")

        except json.JSONDecodeError as e:
            logger.error(f"Feed registry JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Error loading feed registry: {e}")

    async def load_registry_from_db(self) -> None:
        """Reload feed registry from PostgreSQL (async)."""
        try:
            from api.deps import db
            self.feed_registry = await db.feed_sources.as_registry_dict()
            feed_count = self._get_total_feed_count()
            group_count = len([k for k in self.feed_registry.keys() if k != '_metadata'])
            logger.info(f"RSS registry reloaded from DB: {feed_count} feeds in {group_count} groups")
        except Exception as e:
            logger.warning(f"DB registry reload failed, keeping cached: {e}")
    
    def _get_total_feed_count(self) -> int:
        """Get total number of feeds in registry"""
        return sum(
            len(group.get('feeds', []))
            for key, group in self.feed_registry.items()
            if key != '_metadata' and isinstance(group, dict)
        )
    
    def _get_feeds_for_groups(self, groups: Set[str]) -> List[Dict[str, Any]]:
        """Get all feeds from enabled groups"""
        feeds = []
        
        for group_name, group_data in self.feed_registry.items():
            if group_name == '_metadata':
                continue
            if not isinstance(group_data, dict):
                continue
            if group_name not in groups:
                continue
            
            for feed in group_data.get('feeds', []):
                if feed.get('enabled', True):
                    feed_copy = feed.copy()
                    feed_copy['_group'] = group_name
                    feeds.append(feed_copy)
        
        return feeds
    
    def _parse_entry(self, entry: Dict[str, Any], feed_name: str) -> Optional[Dict[str, Any]]:
        """Parse a single feed entry into article format"""
        try:
            # Extract title (truncate to 300 chars to prevent display issues)
            # @updated 2026-02-05 by Mr Cat + Claude - Added title truncation
            title = strip_html_tags(entry.get('title', ''))
            if not title:
                return None
            if len(title) > 300:
                title = title[:297] + '...'

            # Extract description
            description = strip_html_tags(entry.get('summary', entry.get('description', '')))
            
            # Content filter — blacklist only; whitelist runs post-translation
            should_accept, reason = self.content_filter.should_accept(title, description, skip_whitelist=True)
            
            if not should_accept:
                self.rejection_stats['total_rejected'] += 1
                if reason == 'blacklist_match':
                    self.rejection_stats['blacklist_match'] += 1
                elif reason == 'whitelist_fail':
                    self.rejection_stats['whitelist_fail'] += 1
                return None
            
            self.rejection_stats['total_accepted'] += 1
            
            # Extract URL
            url = entry.get('link', '').strip()
            url = sanitize_url(url)
            if not url:
                return None
            
            # Parse publication date
            published = _parse_date_lenient(entry)
            if not published:
                published = datetime.now()
            
            # Extract author if present
            author = strip_html_tags(entry.get('author', ''))

            return {
                'title': title,
                'url': url,
                'description': description[:1000] if description else '',
                'published': published.isoformat(),
                'source': feed_name,
                'collected_at': datetime.now().isoformat(),
                'collector': self.name,
                'author': author
            }
        
        except Exception as e:
            logger.debug(f"Error parsing entry from {feed_name}: {e}")
            return None
    
    # =========================================================================
    # STREAMING COLLECT - CONCURRENT + CONDITIONAL GET
    # =========================================================================

    async def collect(self, groups: Set[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Collect articles from RSS feeds - STREAMING MODE

        Fetches feeds concurrently (bounded by semaphore) and uses
        ETag/Last-Modified headers to skip unchanged feeds (HTTP 304).
        Yields articles one at a time as they are parsed.

        Args:
            groups: Set of enabled group names

        Yields:
            Article dictionaries, one at a time

        @updated 2026-02-04 by Mr Cat + Claude - Streaming architecture
        @updated 2026-02-20 by Mr Cat + Claude - Concurrent fetching + conditional GET
        """
        # Get feeds for enabled groups
        enabled_feeds = self._get_feeds_for_groups(groups)

        if not enabled_feeds:
            logger.warning("No RSS feeds enabled for collection")
            return

        # Get configuration
        max_articles = self.config.get('max_articles_per_feed', 5)
        concurrency = self.config.get('concurrency', 10)

        logger.info(f"[RSS] Starting concurrent collection from {len(enabled_feeds)} feeds "
                    f"(concurrency={concurrency}, cache={len(self._feed_cache)} entries)")

        # Reset statistics for this run
        self.stats.record_run_start()
        self.rejection_stats = {
            'blacklist_match': 0,
            'whitelist_fail': 0,
            'total_rejected': 0,
            'total_accepted': 0
        }
        run_cache_hits = 0

        start_time = datetime.now()
        total_yielded = 0

        # Semaphore bounds how many feeds are fetched + parsed concurrently.
        # force_close=True prevents keep-alive connection accumulation.
        # limit=0 removes the default 100-connection cap on the connector;
        # the semaphore is the real concurrency knob.
        sem = asyncio.Semaphore(concurrency)
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(limit=0, force_close=True)

        queue: asyncio.Queue = asyncio.Queue()
        _DONE = object()

        async def _fetch_one(session: aiohttp.ClientSession, feed: Dict[str, Any]):
            """Fetch a single feed, parse entries, push articles to queue."""
            nonlocal run_cache_hits
            feed_name = feed.get('name', feed.get('url', 'unknown'))
            feed_url = feed.get('url')

            if not feed_url:
                return

            async with sem:
                try:
                    # ----- Conditional GET headers -----
                    headers = {}
                    cached = self._feed_cache.get(feed_url)
                    if cached:
                        if cached.get('etag'):
                            headers['If-None-Match'] = cached['etag']
                        if cached.get('last_modified'):
                            headers['If-Modified-Since'] = cached['last_modified']

                    async with session.get(feed_url, headers=headers) as response:
                        if response.status == 304:
                            # Feed unchanged — skip download + parse entirely
                            run_cache_hits += 1
                            self._cache_stats['hits'] += 1
                            self.feed_health[feed_url] = {
                                'status': 'healthy',
                                'last_success': datetime.now().isoformat(),
                                'cached': True
                            }
                            return

                        if response.status != 200:
                            logger.debug(f"[RSS] {feed_name}: HTTP {response.status}")
                            return

                        self._cache_stats['misses'] += 1

                        # ----- Store response cache headers for next cycle -----
                        resp_etag = response.headers.get('ETag')
                        resp_last_mod = response.headers.get('Last-Modified')
                        if resp_etag or resp_last_mod:
                            entry: Dict[str, str] = {}
                            if resp_etag:
                                entry['etag'] = resp_etag
                            if resp_last_mod:
                                entry['last_modified'] = resp_last_mod
                            self._feed_cache[feed_url] = entry

                        content = await response.text()

                    # ----- Parse outside the response context manager -----
                    parsed = feedparser.parse(content)

                    feed_count = 0
                    for feed_entry in parsed.entries[:max_articles]:
                        article = self._parse_entry(feed_entry, feed_name)
                        if article:
                            article['_group'] = feed.get('_group', 'unknown')
                            article['_tier'] = feed.get('tier', 3)

                            if feed.get('lat') and feed.get('lon'):
                                article['lat'] = feed['lat']
                                article['lon'] = feed['lon']
                            if feed.get('city'):
                                article['city'] = feed['city']
                            if feed.get('country'):
                                article['country'] = feed['country']

                            self.stats.record_article()
                            self._group_article_timestamps[article['_group']].append(datetime.now())
                            feed_count += 1
                            await queue.put(article)

                    if feed_count > 0:
                        logger.debug(f"[RSS] {feed_name}: {feed_count} articles")
                        self.feed_health[feed_url] = {
                            'status': 'healthy',
                            'last_success': datetime.now().isoformat(),
                            'last_count': feed_count
                        }

                except asyncio.TimeoutError:
                    logger.debug(f"[RSS] {feed_name}: timeout")
                    self.feed_health[feed_url] = {'status': 'timeout'}
                except Exception as e:
                    logger.debug(f"[RSS] {feed_name}: {e}")
                    self.feed_health[feed_url] = {'status': 'error', 'error': str(e)}

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            # Launch all feed fetches concurrently (semaphore bounds in-flight)
            tasks = [asyncio.create_task(_fetch_one(session, f)) for f in enabled_feeds]

            async def _signal_done():
                """Wait for all tasks then signal the queue."""
                await asyncio.gather(*tasks, return_exceptions=True)
                await queue.put(_DONE)

            done_task = asyncio.create_task(_signal_done())

            try:
                while True:
                    item = await queue.get()
                    if item is _DONE:
                        break
                    total_yielded += 1
                    yield item
            finally:
                if not done_task.done():
                    done_task.cancel()
                for t in tasks:
                    if not t.done():
                        t.cancel()

        # Record completion
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        self.stats.record_run_complete(elapsed_ms)

        # Prune stale group article timestamps (prevents unbounded growth)
        cutoff = datetime.now() - timedelta(hours=24)
        for group_name in list(self._group_article_timestamps):
            recent = [ts for ts in self._group_article_timestamps[group_name] if ts >= cutoff]
            if recent:
                self._group_article_timestamps[group_name] = recent
            else:
                del self._group_article_timestamps[group_name]

        accepted = self.rejection_stats['total_accepted']
        rejected = self.rejection_stats['total_rejected']
        logger.info(f"[RSS] Streaming complete: {total_yielded} articles yielded "
                    f"({accepted} accepted, {rejected} filtered, "
                    f"{run_cache_hits} cached/304) in {elapsed_ms/1000:.1f}s")
    
    # =========================================================================
    # STATUS & CONFIGURATION
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status and health
        
        Returns all fields expected by routes_feeds.py and routes_metrics.py
        """
        # Count feeds
        total_in_registry = self._get_total_feed_count()
        all_groups = set(k for k in self.feed_registry.keys() if k != '_metadata')
        enabled_feeds = self._get_feeds_for_groups(all_groups)
        enabled_feed_count = len(enabled_feeds)
        
        # Health counts
        healthy = sum(1 for h in self.feed_health.values() if h.get('status') == 'healthy')
        unhealthy = sum(1 for h in self.feed_health.values() if h.get('status') in ('error', 'timeout'))
        
        return {
            'name': self.name,
            'display_name': self.display_name,
            'enabled': self.enabled,
            'available': self.is_available(),
            'healthy': unhealthy < healthy or len(self.feed_health) == 0,
            'stats': self.stats.to_dict(),
            
            # Fields expected by routes_feeds.py /api/v1/feeds/status
            'total_feeds': total_in_registry,
            'enabled_feeds': enabled_feed_count,
            'error_count': unhealthy,
            
            # Fields expected by routes_metrics.py /api/v1/metrics/ai
            'healthy_feeds': healthy,
            'last_article_count': self.stats._current_run_count,
            
            # Health dict with keys expected by routes_feeds.py
            'health': {
                'healthy': healthy,
                'errors': unhealthy,
                'total': len(self.feed_health)
            },
            
            # Legacy field names (backward compatibility)
            'total_feeds_in_registry': total_in_registry,
            'feed_health': {
                'healthy': healthy,
                'unhealthy': unhealthy,
                'tracked': len(self.feed_health)
            },
            
            'rejection_stats': self.rejection_stats.copy(),
            'conditional_get_cache': {
                'cached_feeds': len(self._feed_cache),
                'total_hits': self._cache_stats['hits'],
                'total_misses': self._cache_stats['misses'],
            },
            'config': {
                'concurrency': self.config.get('concurrency', 10),
                'max_articles_per_feed': self.config.get('max_articles_per_feed', 5),
            }
        }
    
    def is_available(self) -> bool:
        """Check if collector can run"""
        return bool(self.feed_registry)
    
    def configure(self, config: Dict[str, Any]) -> bool:
        """Apply runtime configuration"""
        if 'concurrency' in config:
            self.config['concurrency'] = max(1, min(50, int(config['concurrency'])))
        if 'max_articles_per_feed' in config:
            self.config['max_articles_per_feed'] = max(1, min(20, int(config['max_articles_per_feed'])))

        logger.info(f"RSSCollector configured: concurrency={self.config.get('concurrency', 10)}, "
                   f"max_articles={self.config.get('max_articles_per_feed', 5)}")
        return True
    
    # =========================================================================
    # API COMPATIBILITY METHODS
    # @added 2026-02-04 by Mr Cat + Claude - Required by routes_feeds.py
    # =========================================================================
    
    def get_group_names(self) -> List[str]:
        """Get list of all group names in registry"""
        return [k for k in self.feed_registry.keys() if k != '_metadata']
    
    def get_group_articles_24h(self, group_name: str) -> int:
        """
        Get the number of articles collected for a group in the last 24 hours.

        Prunes stale entries older than 24h as a side effect.

        Args:
            group_name: Name of the feed group

        Returns:
            Count of articles collected in the last 24 hours
        """
        timestamps = self._group_article_timestamps.get(group_name)
        if not timestamps:
            return 0

        cutoff = datetime.now() - timedelta(hours=24)
        # Prune old entries and keep only those within the window
        recent = [ts for ts in timestamps if ts >= cutoff]
        self._group_article_timestamps[group_name] = recent
        return len(recent)

    def get_group_info(self, group_name: str) -> Optional[Dict[str, Any]]:
        """
        Get info about a specific feed group

        Args:
            group_name: Name of the group

        Returns:
            Group info dict or None if not found
        """
        if group_name not in self.feed_registry or group_name == '_metadata':
            return None

        group_data = self.feed_registry.get(group_name, {})
        if not isinstance(group_data, dict):
            return None

        return {
            'name': group_name,
            'description': group_data.get('description', ''),
            'feed_count': len(group_data.get('feeds', [])),
            'articles_24h': self.get_group_articles_24h(group_name),
            'enabled_by_default': group_data.get('enabled_by_default', False),
            'tier': 1 if group_name in ('global', 'osint') else 2
        }
    
    def get_all_groups(self) -> List[Dict[str, Any]]:
        """
        Get all feed groups with their details
        
        Returns:
            List of group info dicts, sorted by tier then name
        """
        groups = []
        for group_name in self.get_group_names():
            info = self.get_group_info(group_name)
            if info:
                groups.append(info)
        
        # Sort: Tier 1 first, then alphabetically
        groups.sort(key=lambda x: (x['tier'], x['name']))
        return groups
