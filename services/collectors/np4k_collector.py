"""
RYBAT Intelligence Platform - NP4K Web Scraper Collector (Streaming)
=====================================================================
Collects articles via trafilatura web scraping with streaming output.

@created 2026-02-04 by Mr Cat + Claude - v1.5.0 Collector Integration
@updated 2026-02-04 by Mr Cat + Claude - STREAMING ARCHITECTURE
                                         Articles now yield immediately as scraped
@updated 2026-02-19 by Mr Cat + Claude - Replaced newspaper4k with trafilatura

This collector wraps the BoondocksScraper (trafilatura) to provide web scraping
capabilities for sites without RSS feeds, now with streaming output.
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Set, Optional, AsyncGenerator

from .base import BaseCollector, CollectorStats
from utils.logging import get_logger
from utils.sanitizers import sanitize_url
from services.content_filter import get_content_filter

logger = get_logger(__name__)

# Check if trafilatura is available
HAS_TRAFILATURA = False
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    logger.debug("trafilatura not installed - NP4K collector will not be available")


class NP4KCollector(BaseCollector):
    """
    NP4K Web Scraper Collector - STREAMING MODE
    
    Wraps the BoondocksScraper to provide web scraping capabilities
    through the collector registry interface, now with streaming output.
    
    @updated 2026-02-04 by Mr Cat + Claude - Streaming architecture
    """
    
    # BaseCollector class attributes
    name = "np4k"
    display_name = "NP4K Web Scraper"
    description = "Scrapes articles from sites without RSS feeds using trafilatura"
    requires_api_key = False
    supports_groups = True
    default_enabled = False
    
    def __init__(self):
        """Initialize NP4K collector"""
        super().__init__()

        # Registry path for scraper sites
        env_registry_path = os.getenv('FEED_REGISTRY_PATH')
        if env_registry_path:
            self.registry_path = Path(env_registry_path)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.registry_path = project_root / 'feed_registry_comprehensive.json'

        # Lazy-load scraper instance
        self._scraper = None

        # Site health tracking
        self.site_health: Dict[str, Dict[str, Any]] = {}

        # Configuration
        self.config = {
            'max_articles_per_site': 10,
            'delay_between_sites': 5.0,
        }

        # Content filter (shared with RSS/NewsAPI for consistent filtering)
        self.content_filter = get_content_filter()

        # Cache registry data once at init (avoids re-reading JSON from disk
        # on every is_available()/get_status() call)
        self._registry_data: Dict[str, Any] = {}
        self._load_registry()

        site_count = len(self._get_all_scraper_sites())
        if site_count > 0:
            logger.info(f"NP4KCollector initialized: {site_count} scraper sites in registry")
        else:
            logger.debug("NP4KCollector initialized: no scraper sites configured")

    def _load_registry(self) -> None:
        """Load and cache the feed registry JSON (sync fallback for init)."""
        try:
            if not self.registry_path.exists():
                self._registry_data = {}
                return
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                self._registry_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading registry: {e}")
            self._registry_data = {}

    async def load_registry_from_db(self) -> None:
        """Reload feed registry from PostgreSQL (async)."""
        try:
            from api.deps import db
            self._registry_data = await db.feed_sources.as_registry_dict()
            site_count = len(self._get_all_scraper_sites())
            logger.info(f"NP4K registry reloaded from DB: {site_count} scraper sites")
        except Exception as e:
            logger.warning(f"DB registry reload failed, keeping cached: {e}")

    def _create_scraper(self):
        """Lazy-create BoondocksScraper instance"""
        if self._scraper is None:
            try:
                from services.news_scraper import BoondocksScraper
                self._scraper = BoondocksScraper()
            except ImportError as e:
                logger.error(f"Cannot create BoondocksScraper: {e}")
        return self._scraper
    
    def _get_all_scraper_sites(self) -> List[Dict[str, Any]]:
        """Get all scraper_sites from cached registry data"""
        sites = []
        for group_name, group_data in self._registry_data.items():
            if group_name == '_metadata':
                continue
            if not isinstance(group_data, dict):
                continue
            for site in group_data.get('scraper_sites', []):
                if site.get('enabled', True):
                    site_copy = site.copy()
                    site_copy['_group'] = group_name
                    sites.append(site_copy)
        return sites

    def _get_sites_for_groups(self, groups: Set[str]) -> List[Dict[str, Any]]:
        """Get scraper sites from enabled groups only (uses cached data)"""
        sites = []
        for group_name, group_data in self._registry_data.items():
            if group_name == '_metadata':
                continue
            if group_name not in groups:
                continue
            if not isinstance(group_data, dict):
                continue
            for site in group_data.get('scraper_sites', []):
                if site.get('enabled', True):
                    site_copy = site.copy()
                    site_copy['_group'] = group_name
                    sites.append(site_copy)
        return sites
    
    # =========================================================================
    # STREAMING COLLECT
    # =========================================================================
    
    async def collect(self, groups: Set[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Collect articles from scraper sites - STREAMING MODE
        
        Yields articles one at a time as they are scraped from each site.
        
        Args:
            groups: Set of enabled group names
        
        Yields:
            Article dictionaries, one at a time
        
        @updated 2026-02-04 by Mr Cat + Claude - Streaming architecture
        """
        if not HAS_TRAFILATURA:
            logger.debug("[NP4K] trafilatura not available, skipping")
            return
        
        scraper = self._create_scraper()
        if not scraper:
            logger.error("[NP4K] Could not create scraper instance")
            return
        
        sites = self._get_sites_for_groups(groups)
        
        if not sites:
            logger.debug("[NP4K] No scraper sites configured for enabled groups")
            return
        
        max_articles = self.config.get('max_articles_per_site', 10)
        delay = self.config.get('delay_between_sites', 5.0)
        
        logger.info(f"[NP4K] Starting streaming collection from {len(sites)} sites")
        
        self.stats.record_run_start()
        start_time = datetime.now()
        total_yielded = 0
        
        for i, site in enumerate(sites):
            site_name = site.get('name', site.get('url', 'unknown'))
            site_url = site.get('url')
            
            if not site_url:
                continue
            
            try:
                # Collect from site (returns list)
                articles = await scraper.collect_from_site(
                    site_url=site_url,
                    source_name=site_name,
                    max_articles=max_articles
                )
                
                # Yield each article immediately (with validation matching RSS collector)
                site_count = 0
                for article in articles:
                    # Reject empty titles (matches RSS collector)
                    title = (article.get('title', '') or '').strip()
                    if not title:
                        continue

                    # Sanitize URL (matches RSS collector)
                    url = sanitize_url((article.get('url', '') or '').strip())
                    if not url:
                        continue
                    article['url'] = url

                    # Content filter — blacklist only; whitelist runs post-translation
                    desc = (article.get('description', '') or '').strip()
                    should_accept, _reason = self.content_filter.should_accept(title, desc, skip_whitelist=True)
                    if not should_accept:
                        continue

                    # Add group + tier info
                    article['_group'] = site.get('_group', 'unknown')
                    article['_tier'] = site.get('tier', 3)
                    article['collector'] = self.name

                    # Track stats
                    self.stats.record_article()
                    site_count += 1
                    total_yielded += 1

                    # ==========================================
                    # YIELD IMMEDIATELY
                    # ==========================================
                    yield article
                
                if site_count > 0:
                    logger.debug(f"[NP4K] {site_name}: {site_count} articles")
                    self.site_health[site_url] = {
                        'status': 'healthy',
                        'last_success': datetime.now().isoformat(),
                        'last_count': site_count
                    }
                else:
                    self.site_health[site_url] = {'status': 'empty'}
            
            except Exception as e:
                logger.error(f"[NP4K] {site_name}: {e}")
                self.site_health[site_url] = {'status': 'error', 'error': str(e)}
                self.stats.record_error()
            
            # Delay between sites
            if i < len(sites) - 1:
                await asyncio.sleep(delay)
        
        # Record completion
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        self.stats.record_run_complete(elapsed_ms)
        
        logger.info(f"[NP4K] Streaming complete: {total_yielded} articles from {len(sites)} sites "
                   f"in {elapsed_ms/1000:.1f}s")
    
    # =========================================================================
    # STATUS & CONFIGURATION
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status and health"""
        all_sites = self._get_all_scraper_sites()
        
        healthy_count = sum(
            1 for url, health in self.site_health.items()
            if health.get('status') == 'healthy'
        )
        error_count = sum(
            1 for url, health in self.site_health.items()
            if health.get('status') == 'error'
        )
        
        return {
            'name': self.name,
            'display_name': self.display_name,
            'enabled': self.enabled,
            'available': self.is_available(),
            'healthy': HAS_TRAFILATURA and error_count < len(all_sites) * 0.5,
            'stats': self.stats.to_dict(),
            'site_count': len(all_sites),
            'healthy_sites': healthy_count,
            'error_sites': error_count,
            'has_trafilatura': HAS_TRAFILATURA,
            'last_article_count': self.stats._current_run_count,
            'config': {
                'max_articles_per_site': self.config.get('max_articles_per_site'),
                'delay_between_sites': self.config.get('delay_between_sites'),
            }
        }
    
    def is_available(self) -> bool:
        """Check if collector can run"""
        if not HAS_TRAFILATURA:
            return False
        return len(self._get_all_scraper_sites()) > 0
    
    def configure(self, config: Dict[str, Any]) -> bool:
        """Apply runtime configuration"""
        if 'max_articles_per_site' in config:
            self.config['max_articles_per_site'] = max(1, min(50, int(config['max_articles_per_site'])))
        if 'delay_between_sites' in config:
            self.config['delay_between_sites'] = max(1.0, float(config['delay_between_sites']))
        
        logger.info(f"NP4KCollector configured: max_articles={self.config['max_articles_per_site']}, "
                   f"delay={self.config['delay_between_sites']}s")
        return True
