"""
Observer Intelligence Platform - Feed Registry Management Routes
API endpoints for CRUD operations on feed registry

Features:
- Get/Update full registry
- Test individual feeds
- Track feed health/status
"""

import json
import asyncio
import re
import threading
import aiohttp
import feedparser
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Literal, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

# Sub-router: mounted under /api/v1/feeds by routes_feeds.py
feed_registry_router = APIRouter(tags=["feed-management"])

from services.feed_manager import get_feed_manager

class FeedHealthTracker:
    """Thread-safe feed health tracking with bounded size."""

    _MAX_ENTRIES = 1000

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def update(self, url: str, status: str, error: Optional[str] = None,
               article_count: Optional[int] = None) -> None:
        """Record health status for a feed URL."""
        with self._lock:
            entry: Dict[str, Any] = {
                "status": status,
                "last_check": datetime.now().isoformat(),
                "error": error,
            }
            if article_count is not None:
                entry["article_count"] = article_count
            self._data[url] = entry
            self._evict()

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Return snapshot of all health data."""
        with self._lock:
            return dict(self._data)

    def get_counts(self) -> Dict[str, int]:
        """Return counts of healthy/error feeds."""
        with self._lock:
            healthy = sum(1 for h in self._data.values() if h.get('status') == 'good')
            errors = sum(1 for h in self._data.values() if h.get('status') == 'error')
            return {"healthy": healthy, "errors": errors}

    def clear(self) -> None:
        """Clear all health data."""
        with self._lock:
            self._data.clear()

    def _evict(self) -> None:
        """Evict oldest entries when exceeding cap (called under lock)."""
        if len(self._data) <= self._MAX_ENTRIES:
            return
        sorted_urls = sorted(
            self._data,
            key=lambda u: self._data[u].get('last_check', ''),
        )
        for url in sorted_urls[:len(self._data) - self._MAX_ENTRIES]:
            del self._data[url]


_health_tracker = FeedHealthTracker()


# ==================== REGISTRY I/O ====================

def load_registry() -> Dict[str, Any]:
    """Load the feed registry from the FeedManager (DB-backed)."""
    try:
        fm = get_feed_manager()
        return fm.feed_registry
    except Exception as e:
        logger.error(f"Error loading feed registry: {e}")
        return {}


def save_registry(registry: Dict[str, Any]) -> bool:
    """Update the in-memory feed registry in the FeedManager.

    Callers should also call ``await sync_registry_to_db(registry)`` to
    persist changes to PostgreSQL.
    """
    try:
        fm = get_feed_manager()
        fm.feed_registry = registry
        logger.info("Feed registry updated in memory")
        return True
    except Exception as e:
        logger.error(f"Error saving feed registry: {e}")
        return False


async def sync_registry_to_db(registry: Dict[str, Any]) -> None:
    """Sync the full registry dict into PostgreSQL and reload collectors.

    Called after scraper routes modify the JSON registry so the DB
    (the runtime source of truth) stays current.
    """
    try:
        from api.deps import db
        await db.feed_sources.seed_from_json(registry)
    except Exception as e:
        logger.warning(f"Registry → DB sync failed: {e}")

    # Reload collectors so they pick up the changes
    try:
        from services.collectors import get_collector_registry
        cr = get_collector_registry()
        for collector in cr.get_all_collectors():
            if hasattr(collector, 'load_registry_from_db'):
                await collector.load_registry_from_db()
    except Exception as e:
        logger.warning(f"Collector reload after sync failed: {e}")


# ==================== REGISTRY QUERY HELPERS ====================

async def get_all_scraper_sites() -> List[Dict[str, Any]]:
    """Get all scraper sites from all groups (PostgreSQL-backed)."""
    try:
        from api.deps import db
        rows = await db.feed_sources.get_by_type('scraper')
        sites = []
        for row in rows:
            sites.append({
                'name': row.get('name', ''),
                'url': row.get('url', ''),
                'language': row.get('language', 'en'),
                'enabled': row.get('enabled', True),
                'group': row.get('group_key', ''),
            })
        return sites
    except Exception as e:
        logger.error(f"Error loading scraper sites from DB: {e}")
        return []


async def get_enabled_scraper_sites() -> List[Dict[str, Any]]:
    """Get scraper sites from enabled groups only (PostgreSQL-backed)."""
    try:
        from api.deps import db
        from services.source_state import get_source_state_manager
        state_manager = get_source_state_manager()
        enabled_groups = list(state_manager.enabled_groups)
    except ImportError:
        logger.warning("Could not import source_state - returning all sites")
        return await get_all_scraper_sites()

    try:
        rows = await db.feed_sources.get_by_groups(enabled_groups)
        sites = []
        for row in rows:
            if row.get('feed_type') == 'scraper':
                sites.append({
                    'name': row.get('name', ''),
                    'url': row.get('url', ''),
                    'language': row.get('language', 'en'),
                    'enabled': row.get('enabled', True),
                    'group': row.get('group_key', ''),
                })
        return sites
    except Exception as e:
        logger.error(f"Error loading enabled scraper sites from DB: {e}")
        return []


# ==================== MODELS ====================

class FeedTestRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class FeedHealthUpdate(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    status: Literal['good', 'error', 'unknown']
    error: Optional[str] = None


# ==================== REGISTRY ENDPOINTS ====================

@feed_registry_router.get("/registry")
async def get_registry_endpoint():
    """Get the full feed registry (from DB)."""
    try:
        from api.deps import db
        registry = await db.feed_sources.as_registry_dict()
        if not registry or len(registry) <= 1:  # only _metadata
            return JSONResponse({
                "_metadata": {"version": "5.0", "description": "Empty registry"}
            })
        return JSONResponse(registry)
    except Exception as e:
        logger.error(f"Error reading registry from DB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@feed_registry_router.put("/registry")
async def update_registry_endpoint(registry: Dict[str, Any]):
    """Update the full feed registry."""
    try:
        if not isinstance(registry, dict):
            raise HTTPException(status_code=400, detail="Registry must be an object")

        if '_metadata' not in registry:
            registry['_metadata'] = {
                "version": "3.0",
                "description": "Observer Feed Registry",
                "last_updated": datetime.now().isoformat()
            }
        else:
            registry['_metadata']['last_updated'] = datetime.now().isoformat()

        total_feeds = sum(
            len(group.get('feeds', []))
            for key, group in registry.items()
            if key != '_metadata' and isinstance(group, dict)
        )

        if not save_registry(registry):
            raise HTTPException(status_code=500, detail="Failed to save registry")

        # Sync to DB and reload collectors from DB
        await sync_registry_to_db(registry)

        logger.info(f"Registry updated: {total_feeds} feeds in {len(registry) - 1} groups")

        return JSONResponse({
            "status": "ok",
            "total_feeds": total_feeds,
            "total_groups": len(registry) - 1
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@feed_registry_router.get("/registry/download")
async def download_registry():
    """
    Download registry as a JSON file
    """
    registry = load_registry()
    if not registry:
        raise HTTPException(status_code=404, detail="Registry is empty")

    return JSONResponse(
        content=registry,
        headers={"Content-Disposition": "attachment; filename=feed_registry.json"}
    )


# ==================== FEED TESTING ====================

@feed_registry_router.post("/test")
async def test_feed(request: FeedTestRequest):
    """
    Test a feed URL and return results
    """
    url = request.url.strip()
    
    if not url:
        return JSONResponse({
            "success": False,
            "error": "URL is required"
        }, status_code=400)
    
    try:
        # Fetch feed
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={'User-Agent': 'Observer Feed Manager/1.0'}
            ) as response:
                if response.status != 200:
                    return JSONResponse({
                        "success": False,
                        "error": f"HTTP {response.status}: {response.reason}"
                    }, status_code=400)
                
                content = await response.text()
        
        # Parse feed
        feed = feedparser.parse(content)
        
        if feed.bozo and not feed.entries:
            return JSONResponse({
                "success": False,
                "error": f"Parse error: {str(feed.bozo_exception)[:100]}"
            }, status_code=400)
        
        # Get sample titles
        sample_titles = [
            entry.get('title', 'No title')[:80]
            for entry in feed.entries[:5]
        ]
        
        # Update health tracking
        _health_tracker.update(url, "good", article_count=len(feed.entries))
        
        return JSONResponse({
            "success": True,
            "article_count": len(feed.entries),
            "feed_title": feed.feed.get('title', 'Unknown'),
            "sample_titles": sample_titles
        })
    
    except asyncio.TimeoutError:
        _health_tracker.update(url, "error", error="Timeout")
        return JSONResponse({
            "success": False,
            "error": "Connection timeout (15s)"
        }, status_code=500)
    
    except aiohttp.ClientError as e:
        _health_tracker.update(url, "error", error=str(e))
        return JSONResponse({
            "success": False,
            "error": f"Connection error: {str(e)[:100]}"
        }, status_code=500)
    
    except Exception as e:
        _health_tracker.update(url, "error", error=str(e))
        return JSONResponse({
            "success": False,
            "error": f"Error: {str(e)[:100]}"
        }, status_code=500)


# ==================== HEALTH TRACKING ====================

@feed_registry_router.get("/health")
async def get_feed_health():
    """Get health status for all tracked feeds."""
    return JSONResponse(_health_tracker.get_all())


@feed_registry_router.post("/health")
async def update_feed_health(update: FeedHealthUpdate):
    """Update health status for a feed."""
    _health_tracker.update(update.url, update.status, error=update.error)
    return JSONResponse({"status": "ok"})


@feed_registry_router.delete("/health")
async def clear_feed_health():
    """Clear all health tracking data."""
    _health_tracker.clear()
    return JSONResponse({"status": "ok"})


# ==================== STATS ====================

@feed_registry_router.get("/stats")
async def get_feed_stats():
    """
    Get statistics about the feed registry (PostgreSQL-backed).
    """
    try:
        from api.deps import db
        stats = await db.feed_sources.get_stats()
        if not stats:
            return JSONResponse({
                "total_groups": 0,
                "total_feeds": 0,
                "enabled_feeds": 0,
                "by_language": {},
                "by_country": {}
            })

        # Count healthy/error feeds
        health_counts = _health_tracker.get_counts()
        healthy = health_counts["healthy"]
        errors = health_counts["errors"]
        total_feeds = stats.get('total', 0)

        return JSONResponse({
            "total_groups": stats.get('group_count', 0),
            "total_feeds": total_feeds,
            "enabled_feeds": stats.get('enabled_count', 0),
            "rss_feeds": stats.get('rss_count', 0),
            "scraper_sites": stats.get('scraper_count', 0),
            "by_language": stats.get('by_language', {}),
            "by_country": stats.get('by_group', {}),
            "health": {
                "healthy": healthy,
                "errors": errors,
                "unknown": total_feeds - healthy - errors
            }
        })

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FEED DISCOVERY (RSSGuard) ====================

# HTML <link> autodiscovery patterns
# ---------------------------------------------------------------------------
# Feed extraction — trafilatura (preferred) with regex fallback
# ---------------------------------------------------------------------------
_HAS_TRAFILATURA_FEEDS = False
try:
    from trafilatura.feeds import (
        determine_feed as _traf_determine_feed,
        FeedParameters as _TrafFeedParams,
    )
    _HAS_TRAFILATURA_FEEDS = True
except ImportError:
    pass

# Regex patterns (fallback when trafilatura is unavailable)
_LINK_TAG_RE = re.compile(
    r'<link[^>]+type=["\']application/(?:rss\+xml|atom\+xml)["\'][^>]*/?>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_FEED_MARKERS = ('<rss', '<feed', '<channel', '<?xml')

_ANCHOR_TAG_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
_RSS_HREF_PATTERN = re.compile(
    r'(?:/rss|/feed|/atom|\.rss|\.atom|\.xml|/syndication)',
    re.IGNORECASE,
)

# Well-known RSS paths (fallback)
_RSS_PROBE_PATHS = [
    '/feed', '/rss', '/atom.xml', '/feed/rss', '/feed.xml',
    '/rss.xml', '/feeds/posts/default', '/index.xml',
    '/rss/headlines', '/feed/atom', '/rss/news',
    '/?feed=rss2', '/en/rss', '/english/rss',
]

# Paths that commonly host an RSS listing page (HTML page full of feed links)
_RSS_LISTING_PATHS = ['/rss', '/rss/', '/feeds', '/feeds/', '/rss.aspx']

_DISCOVER_UA = 'Observer Feed Discovery/1.0'


async def _validate_rss_url(
    session: aiohttp.ClientSession, url: str,
) -> Optional[str]:
    """Return the final URL if it looks like a valid RSS/Atom feed, else None."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True, ssl=False,
        ) as resp:
            if resp.status != 200:
                return None
            ct = resp.headers.get('content-type', '').lower()
            if any(t in ct for t in ('xml', 'rss', 'atom', 'text/plain')):
                chunk = await resp.content.read(1024)
                text = chunk.decode('utf-8', errors='ignore').lower()
                if any(m in text for m in _FEED_MARKERS):
                    return str(resp.url)
            if 'html' not in ct:
                chunk = await resp.content.read(1024)
                text = chunk.decode('utf-8', errors='ignore').lower()
                if any(m in text for m in ('<rss', '<feed', '<channel')):
                    return str(resp.url)
    except Exception:
        pass
    return None


async def _fetch_homepage(
    session: aiohttp.ClientSession, url: str, max_bytes: int = 65536,
) -> Optional[str]:
    """Fetch page HTML (up to *max_bytes*). Returns None on failure."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=12),
            allow_redirects=True, ssl=False,
        ) as resp:
            if resp.status != 200:
                return None
            ct = resp.headers.get('content-type', '').lower()
            if 'html' not in ct and 'text' not in ct:
                return None
            chunk = await resp.content.read(max_bytes)
            return chunk.decode('utf-8', errors='ignore')
    except Exception:
        return None


def _extract_feeds_from_html(html: str, page_url: str) -> List[str]:
    """
    Extract candidate feed URLs from an HTML page.

    Uses trafilatura.feeds.determine_feed (XPath-based, handles both
    <link rel="alternate"> and <a href> tags) when available, falling
    back to regex scanning otherwise.
    """
    from urllib.parse import urljoin, urlparse

    if _HAS_TRAFILATURA_FEEDS:
        try:
            parsed = urlparse(page_url)
            domain = parsed.netloc.lower().removeprefix('www.')
            baseurl = f'{parsed.scheme}://{parsed.netloc}'
            params = _TrafFeedParams(
                baseurl=baseurl, domain=domain, reference=page_url,
            )
            result = _traf_determine_feed(html, params)
            if result:
                return list(result)
        except Exception:
            pass  # fall through to regex

    # --- Regex fallback ---
    urls: List[str] = []

    # 1) <link type="application/rss+xml|atom+xml"> autodiscovery
    for tag_match in _LINK_TAG_RE.finditer(html):
        tag = tag_match.group(0)
        href_match = _HREF_RE.search(tag)
        if not href_match:
            continue
        href = href_match.group(1).strip()
        if not href:
            continue
        href = _resolve_url(href, page_url)
        if href and href not in urls:
            urls.append(href)

    # 2) <a href> anchors whose path looks RSS-ish (listing pages)
    parsed_base = urlparse(page_url)
    base_netloc = parsed_base.netloc.lower()
    for m in _ANCHOR_TAG_RE.finditer(html):
        href = m.group(1).strip()
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        href = _resolve_url(href, page_url)
        if not href or not _RSS_HREF_PATTERN.search(href):
            continue
        try:
            if urlparse(href).netloc.lower() != base_netloc:
                continue
        except Exception:
            continue
        if href not in urls:
            urls.append(href)

    return urls


def _resolve_url(href: str, base_url: str) -> str:
    """Resolve a potentially relative URL against a base URL."""
    from urllib.parse import urljoin, urlparse
    if href.startswith('//'):
        return 'https:' + href
    if href.startswith('/'):
        parsed = urlparse(base_url)
        return f'{parsed.scheme}://{parsed.netloc}{href}'
    if not href.startswith('http'):
        return urljoin(base_url, href)
    return href


async def _scrape_rss_listing_pages(
    session: aiohttp.ClientSession,
    base_url: str,
    already_found: List[str],
) -> List[str]:
    """
    Fetch common RSS listing pages and extract feed URLs via trafilatura or
    regex fallback.

    Many news sites (IRNA, Al Jazeera, etc.) host a page at /rss/ that lists
    dozens of category-specific RSS feeds.  trafilatura's XPath parser handles
    both <link rel="alternate"> and <a href> patterns; the regex fallback does
    the same with less coverage.

    Returns newly discovered feed URLs not already in *already_found*.
    """
    from urllib.parse import urlparse
    new_feeds: List[str] = []
    parsed = urlparse(base_url)
    base_no_path = f'{parsed.scheme}://{parsed.netloc}'

    listing_urls = []
    for path in _RSS_LISTING_PATHS:
        url = f'{base_no_path}{path}'
        if url not in listing_urls:
            listing_urls.append(url)

    for listing_url in listing_urls:
        # Use a larger read limit for listing pages (256 KB)
        html = await _fetch_homepage(session, listing_url, max_bytes=262144)
        if not html:
            continue

        # If the page itself is an RSS feed (not HTML listing), skip
        html_lower = html[:500].lower()
        if any(m in html_lower for m in ('<rss', '<feed', '<channel')):
            continue

        candidates = _extract_feeds_from_html(html, listing_url)
        if not candidates:
            continue

        # Deduplicate against already-found feeds
        candidates = [u for u in candidates if u not in already_found and u not in new_feeds]
        if not candidates:
            continue

        # Validate in batches (cap at 80 to cover sites with many categories)
        candidates = candidates[:80]
        tasks = [_validate_rss_url(session, u) for u in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, str) and r and r not in already_found and r not in new_feeds:
                new_feeds.append(r)

        # If we found feeds from a listing page, no need to try other paths
        if new_feeds:
            break

    return new_feeds


async def _get_feed_title(
    session: aiohttp.ClientSession, url: str,
) -> str:
    """Fetch a feed URL and extract its title via feedparser."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True, ssl=False,
        ) as resp:
            if resp.status != 200:
                return ''
            content = await resp.text()
        feed = feedparser.parse(content)
        return feed.feed.get('title', '') or ''
    except Exception:
        return ''


@feed_registry_router.post("/discover")
async def discover_feeds_for_url(body: dict):
    """
    Discover RSS feeds on a website using three-phase autodiscovery.

    Body: {"url": "https://example.com"}
    Returns: {"success": true, "domain": "...", "feeds": [...]}

    Phase 1: Fetch user-provided URL, extract feed URLs via trafilatura
             XPath parser (handles <link> + <a> tags) or regex fallback.
    Phase 2: Scrape RSS listing pages (/rss/, /feeds/) for more feeds.
    Phase 3: If still nothing, fall back to well-known path brute-force.
    For each confirmed feed, fetch the feed title via feedparser.
    """
    raw_url = (body.get('url') or '').strip()
    if not raw_url:
        return JSONResponse({"success": False, "error": "URL is required"}, status_code=400)

    # Normalise to a base URL
    base = raw_url.rstrip('/')
    if not base.startswith('http'):
        base = f'https://{base}'

    from urllib.parse import urlparse
    parsed = urlparse(base)
    domain = parsed.netloc or parsed.path
    domain_display = domain.lower().removeprefix('www.')

    found: List[str] = []

    try:
        async with aiohttp.ClientSession(
            headers={'User-Agent': _DISCOVER_UA}
        ) as session:
            # --- Phase 1: Homepage feed extraction (trafilatura / regex) ---
            html = await _fetch_homepage(session, base)
            phase = 'autodiscovery'
            if html:
                candidates = _extract_feeds_from_html(html, base)
                if candidates:
                    tasks = [_validate_rss_url(session, u) for u in candidates]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, str) and r and r not in found:
                            found.append(r)

            # --- Phase 2: RSS listing page scrape ---
            listing_feeds = await _scrape_rss_listing_pages(session, base, found)
            if listing_feeds:
                phase = 'listing-scrape' if not found else phase
                found.extend(listing_feeds)

            # --- Phase 3: Well-known path brute-force (fallback) ---
            if not found:
                phase = 'path-probe'
                urls_to_try = [f"{base}{path}" for path in _RSS_PROBE_PATHS]
                tasks = [_validate_rss_url(session, u) for u in urls_to_try]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, str) and r and r not in found:
                        found.append(r)

            if not found:
                return JSONResponse({
                    "success": True,
                    "domain": domain_display,
                    "feeds": [],
                    "message": f"No RSS feeds found on {domain_display}",
                })

            # --- Fetch titles for each discovered feed ---
            title_tasks = [_get_feed_title(session, u) for u in found]
            titles = await asyncio.gather(*title_tasks, return_exceptions=True)

        feeds = []
        for i, url in enumerate(found):
            title = titles[i] if isinstance(titles[i], str) else ''
            feeds.append({
                'url': url,
                'title': title,
                'name': title or domain_display,
            })

        logger.info(
            f"Feed discover: {domain_display} → {len(feeds)} feeds "
            f"(phase: {phase})"
        )

        return JSONResponse({
            "success": True,
            "domain": domain_display,
            "feeds": feeds,
        })

    except Exception as e:
        logger.error(f"Feed discover error for {raw_url}: {e}")
        return JSONResponse({"success": False, "error": str(e)})
