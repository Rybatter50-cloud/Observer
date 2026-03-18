"""
RYBAT Intelligence Platform - News Scraper Module
==================================================
Uses trafilatura to scrape news from sites with broken/missing RSS feeds.

Trafilatura provides best-in-class content extraction (0.909 F-score) with
a three-stage fallback pipeline: custom extractor → readability → jusText.
In fast mode it still beats every other tool at 0.900 F-score.

URL discovery uses trafilatura's built-in sitemap search + focused crawler.

Usage:
    from services.news_scraper import BoondocksScraper

    scraper = BoondocksScraper()
    articles = await scraper.collect_from_site("https://sketchy-news-site.ly")

Configuration:
    All settings are controlled via .env file. See config.py for SCRAPER_* variables.

@updated 2026-02-19 by Mr Cat + Claude - Replaced newspaper4k with trafilatura
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse
import hashlib

try:
    import trafilatura
    from trafilatura import sitemaps
    from trafilatura.spider import focused_crawler
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False
    print("WARNING: trafilatura not installed. Run: pip install trafilatura[all]")

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)


class BoondocksScraper:
    """
    Scrapes news sites that don't have working RSS feeds.
    Designed for rickety servers in remote regions.

    Uses trafilatura for content extraction (best-in-class F-score 0.909)
    and URL discovery via sitemap search + focused crawling.

    Features:
    - Gentle rate limiting (don't kill small servers)
    - SSL tolerance (expired certs are common)
    - Three-stage extraction fallback (custom → readability → jusText)
    - Built-in language detection
    - Deduplication
    """

    def __init__(self):
        if not HAS_TRAFILATURA:
            raise ImportError("trafilatura required. Install with: pip install trafilatura[all]")

        self.seen_urls: set = set()
        self._seen_urls_max = 10_000
        self.last_fetch_time: Dict[str, datetime] = {}
        self.request_counts: Dict[str, int] = {}

        logger.debug(
            f"BoondocksScraper initialized (trafilatura): "
            f"min_words={config.SCRAPER_MIN_WORD_COUNT}, "
            f"max_articles={config.SCRAPER_MAX_ARTICLES_PER_SITE}, "
            f"delay={config.SCRAPER_DELAY_BETWEEN_ARTICLES}s, "
            f"fast_mode={config.SCRAPER_FAST_MODE}"
        )

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _can_fetch(self, url: str) -> Tuple[bool, str]:
        domain = self._get_domain(url)
        now = datetime.now()

        count = self.request_counts.get(domain, 0)
        if count >= config.SCRAPER_MAX_REQUESTS_PER_HOUR:
            return False, f"Hourly limit reached for {domain}"

        last_fetch = self.last_fetch_time.get(domain)
        if last_fetch:
            elapsed = (now - last_fetch).total_seconds()
            if elapsed < config.SCRAPER_DELAY_BETWEEN_ARTICLES:
                return False, f"Rate limit: wait {config.SCRAPER_DELAY_BETWEEN_ARTICLES - elapsed:.1f}s"

        return True, "OK"

    def _record_fetch(self, url: str) -> None:
        domain = self._get_domain(url)
        self.last_fetch_time[domain] = datetime.now()
        self.request_counts[domain] = self.request_counts.get(domain, 0) + 1

    async def _discover_urls(self, site_url: str) -> List[str]:
        """
        Discover article URLs from a site using trafilatura's built-in discovery.

        Phase 1: XML sitemap search (most efficient — sitemaps list all URLs).
        Phase 2: Focused crawler fallback (follows internal links from homepage).

        Returns a list of discovered article URLs.
        """
        loop = asyncio.get_running_loop()
        build_timeout = config.SCRAPER_REQUEST_TIMEOUT * 3
        urls: List[str] = []

        # Phase 1: Sitemap search
        try:
            sitemap_urls = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: sitemaps.sitemap_search(site_url)),
                timeout=build_timeout,
            )
            if sitemap_urls:
                urls = list(sitemap_urls)
                logger.debug(f"[Boondocks] Sitemap discovery: {len(urls)} URLs from {site_url}")
        except asyncio.TimeoutError:
            logger.debug(f"[Boondocks] Sitemap search timed out for {site_url}")
        except Exception as e:
            logger.debug(f"[Boondocks] Sitemap search failed for {site_url}: {e}")

        # Phase 2: Focused crawler fallback
        if not urls:
            try:
                max_seen = config.SCRAPER_MAX_ARTICLES_PER_SITE * 3
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: focused_crawler(site_url, max_seen_urls=max_seen, max_known_urls=max_seen * 2),
                    ),
                    timeout=build_timeout,
                )
                to_visit, known_links = result
                urls = list(to_visit) + list(known_links)
                logger.debug(f"[Boondocks] Crawler discovery: {len(urls)} URLs from {site_url}")
            except asyncio.TimeoutError:
                logger.debug(f"[Boondocks] Focused crawl timed out for {site_url}")
            except Exception as e:
                logger.debug(f"[Boondocks] Focused crawl failed for {site_url}: {e}")

        return urls

    async def collect_from_site(
        self,
        site_url: str,
        source_name: str = None,
        max_articles: int = None
    ) -> List[Dict[str, Any]]:
        """Collect articles from a news site using sitemap/crawl discovery + trafilatura extraction."""
        if not source_name:
            source_name = self._get_domain(site_url)

        max_articles = max_articles or config.SCRAPER_MAX_ARTICLES_PER_SITE
        logger.info(f"[Boondocks] Scanning site: {site_url}")

        try:
            discovered_urls = await self._discover_urls(site_url)

            logger.info(f"[Boondocks] Found {len(discovered_urls)} potential articles on {source_name}")

            articles = []
            for article_url in discovered_urls[:max_articles * 2]:
                if len(articles) >= max_articles:
                    break

                if article_url in self.seen_urls:
                    continue

                can_fetch, reason = self._can_fetch(article_url)
                if not can_fetch:
                    logger.debug(f"[Boondocks] Skipping {article_url}: {reason}")
                    await asyncio.sleep(1)
                    continue

                article_data = await self._fetch_article(article_url, source_name)
                if article_data:
                    articles.append(article_data)
                    self.seen_urls.add(article_url)
                    if len(self.seen_urls) > self._seen_urls_max:
                        self.seen_urls.clear()

                await asyncio.sleep(config.SCRAPER_DELAY_BETWEEN_ARTICLES)

            logger.info(f"[Boondocks] Collected {len(articles)} articles from {source_name}")
            return articles

        except asyncio.TimeoutError:
            logger.warning(f"[Boondocks] Timeout scanning {site_url}")
            return []
        except Exception as e:
            logger.error(f"[Boondocks] Error scanning {site_url}: {e}")
            return []

    async def _fetch_article(self, url: str, source_name: str) -> Optional[Dict[str, Any]]:
        """Fetch and extract a single article using trafilatura."""
        try:
            loop = asyncio.get_running_loop()
            timeout = config.SCRAPER_REQUEST_TIMEOUT

            # Download the page
            downloaded = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: trafilatura.fetch_url(url)),
                timeout=timeout,
            )

            if not downloaded:
                logger.debug(f"[Boondocks] Empty response: {url}")
                return None

            # Build url_blacklist set from comma-separated config
            url_blacklist = None
            if config.SCRAPER_URL_BLACKLIST:
                url_blacklist = set(
                    p.strip() for p in config.SCRAPER_URL_BLACKLIST.split(',') if p.strip()
                )

            # Extract content using trafilatura's three-stage pipeline
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: trafilatura.bare_extraction(
                        downloaded,
                        url=url,
                        fast=config.SCRAPER_FAST_MODE,
                        favor_precision=config.SCRAPER_FAVOR_PRECISION,
                        favor_recall=config.SCRAPER_FAVOR_RECALL,
                        include_tables=config.SCRAPER_INCLUDE_TABLES,
                        include_links=config.SCRAPER_INCLUDE_LINKS,
                        include_images=config.SCRAPER_INCLUDE_IMAGES,
                        include_comments=config.SCRAPER_INCLUDE_COMMENTS,
                        deduplicate=config.SCRAPER_DEDUPLICATE,
                        url_blacklist=url_blacklist,
                    ),
                ),
                timeout=timeout,
            )

            self._record_fetch(url)

            if not result:
                logger.debug(f"[Boondocks] Extraction returned nothing: {url}")
                return None

            title = (result.title or '').strip()
            if not title:
                logger.debug(f"[Boondocks] No title found: {url}")
                return None

            text = result.text or ''
            if len(text.split()) < config.SCRAPER_MIN_WORD_COUNT:
                logger.debug(f"[Boondocks] Article too short ({len(text.split())} words): {url}")
                return None

            # Build published date — trafilatura returns date as 'YYYY-MM-DD' string
            published = datetime.now()
            if result.date:
                try:
                    published = datetime.fromisoformat(result.date)
                except (ValueError, TypeError):
                    pass

            # Build author string
            author = (result.author or '').strip()
            authors = [a.strip() for a in author.split(';')] if author else []

            return {
                'title': title,
                'url': url,
                'description': (text[:500]).strip(),
                'full_text': text,
                'published': published.isoformat(),
                'source': source_name,
                'collected_at': datetime.now().isoformat(),
                'authors': authors,
                'author': author,
                'keywords': list(result.tags) if result.tags else [],
                'language': result.language or 'unknown',
                'collection_method': 'trafilatura',
                'entry_id': hashlib.md5(f"{url}{title}".encode()).hexdigest(),
                'sitename': result.sitename or '',
                'categories': list(result.categories) if result.categories else [],
            }

        except asyncio.TimeoutError:
            logger.debug(f"[Boondocks] Timeout fetching {url}")
            return None
        except Exception as e:
            logger.debug(f"[Boondocks] Failed to fetch {url}: {e}")
            return None

    async def collect_from_url_list(
        self,
        urls: List[str],
        source_name: str = "Custom"
    ) -> List[Dict[str, Any]]:
        """Collect articles from a list of direct article URLs."""
        articles = []

        for url in urls:
            if url in self.seen_urls:
                continue

            can_fetch, reason = self._can_fetch(url)
            if not can_fetch:
                await asyncio.sleep(config.SCRAPER_DELAY_BETWEEN_ARTICLES)
                continue

            article = await self._fetch_article(url, source_name)
            if article:
                articles.append(article)
                self.seen_urls.add(url)
                if len(self.seen_urls) > self._seen_urls_max:
                    self.seen_urls.clear()

            await asyncio.sleep(config.SCRAPER_DELAY_BETWEEN_ARTICLES)

        return articles

    def reset_rate_limits(self) -> None:
        """Reset hourly rate limit counters."""
        self.request_counts.clear()
