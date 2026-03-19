"""
Observer Intelligence Platform - Base Collector
=============================================
Abstract base class that all collectors must implement.

@created 2026-02-03 by Claude - v1.5.0 Collector Architecture Refactor
@updated 2026-02-03 by Claude - Added enabled property for get_status() compatibility
@updated 2026-02-04 by Mr Cat + Claude - STREAMING ARCHITECTURE
                                         Changed collect() from List return to AsyncGenerator
                                         Articles now yield immediately as collected

All collectors (RSS, NewsAPI, Scraper, Telegram, etc.) inherit from this
class and implement the required methods. This ensures a consistent interface
for the IntelligenceService to work with any data source.

Usage:
    from services.collectors.base import BaseCollector
    
    class MyCollector(BaseCollector):
        name = 'my_source'
        
        async def collect(self, groups):
            for source in sources:
                article = await fetch_source(source)
                yield article  # Immediate processing!
        
        def get_status(self):
            return {'healthy': True, ...}
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Any, List, Set, Optional, AsyncGenerator
from datetime import datetime, timedelta

# 24-hour window for sliding counters
_24H = timedelta(hours=24)


def _is_transient(error: Exception) -> bool:
    """Classify an exception as transient (retry-worthy) vs. permanent."""
    import asyncio
    transient_types = (
        TimeoutError,
        asyncio.TimeoutError,
        ConnectionError,
        OSError,          # includes socket errors, DNS failures
    )
    # aiohttp errors are transient network issues
    try:
        import aiohttp
        transient_types = transient_types + (
            aiohttp.ClientError,
            aiohttp.ServerDisconnectedError,
        )
    except ImportError:
        pass
    return isinstance(error, transient_types)


@dataclass
class CollectorInfo:
    """
    Metadata about a collector for registration and UI display

    Attributes:
        name: Unique identifier ('rss', 'newsapi', 'telegram', etc.)
        display_name: Human-readable name for UI
        description: Brief description of the source
        requires_api_key: Whether an API key is needed
        api_key_env_var: Name of env var containing API key (if required)
        supports_groups: Whether collector uses geographic/topic groups
        default_enabled: Whether to enable by default on fresh install
        config_schema: Dict describing configurable options
    """
    name: str
    display_name: str = ""
    description: str = ""
    requires_api_key: bool = False
    api_key_env_var: Optional[str] = None
    supports_groups: bool = True
    default_enabled: bool = False
    config_schema: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name.upper()


@dataclass
class CollectorStats:
    """
    Runtime statistics for a collector

    Attributes:
        last_run: When collector last completed
        last_success: When collector last succeeded
        articles_collected: Total articles collected this session
        avg_response_time_ms: Exponential moving average fetch time
    """
    last_run: Optional[datetime] = None
    last_success: Optional[datetime] = None
    articles_collected: int = 0
    avg_response_time_ms: float = 0.0
    _current_run_count: int = 0  # Track articles in current run for stats
    _response_time_count: int = 0  # Number of samples in the average
    # Sliding-window timestamps for true 24h counts
    _article_times: deque = field(default_factory=deque)
    _error_times: deque = field(default_factory=deque)

    def _prune_old(self):
        """Remove timestamps older than 24 hours from sliding windows"""
        cutoff = datetime.now() - _24H
        while self._article_times and self._article_times[0] < cutoff:
            self._article_times.popleft()
        while self._error_times and self._error_times[0] < cutoff:
            self._error_times.popleft()

    @property
    def articles_24h(self) -> int:
        self._prune_old()
        return len(self._article_times)

    @property
    def errors_24h(self) -> int:
        self._prune_old()
        return len(self._error_times)

    def record_article(self):
        """
        Record a single article collected (for streaming mode)

        @added 2026-02-04 by Mr Cat + Claude - Streaming architecture
        """
        self.articles_collected += 1
        self._article_times.append(datetime.now())
        self._current_run_count += 1

    def record_run_start(self):
        """Mark the start of a collection run"""
        self._current_run_count = 0
        self.last_run = datetime.now()

    def record_run_complete(self, response_time_ms: float = 0):
        """
        Mark a collection run as complete

        @updated 2026-02-04 - Now works with streaming (articles already counted)
        """
        now = datetime.now()
        self.last_run = now
        self.last_success = now
        self._update_avg_response_time(response_time_ms)

    def record_error(self, error: Optional[Exception] = None):
        """Record a failed collection run, with optional error classification."""
        self.last_run = datetime.now()
        self._error_times.append(datetime.now())
        self.last_error_type: Optional[str] = type(error).__name__ if error else None
        self.last_error_msg: Optional[str] = str(error)[:200] if error else None
        self.last_error_transient: bool = _is_transient(error) if error else False

    def _update_avg_response_time(self, response_time_ms: float):
        """Update exponential moving average with proper weighting"""
        if response_time_ms <= 0:
            return
        self._response_time_count += 1
        # EMA with alpha = 2/(N+1), capped at N=20 for stability
        n = min(self._response_time_count, 20)
        alpha = 2.0 / (n + 1)
        self.avg_response_time_ms = (
            alpha * response_time_ms + (1 - alpha) * self.avg_response_time_ms
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        d = {
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'last_success': self.last_success.isoformat() if self.last_success else None,
            'articles_collected': self.articles_collected,
            'articles_24h': self.articles_24h,
            'errors_24h': self.errors_24h,
            'avg_response_time_ms': round(self.avg_response_time_ms, 2),
        }
        if getattr(self, 'last_error_type', None):
            d['last_error'] = {
                'type': self.last_error_type,
                'message': self.last_error_msg,
                'transient': self.last_error_transient,
            }
        return d


class BaseCollector(ABC):
    """
    Abstract base class for all data collectors
    
    All collectors must:
    1. Define a unique `name` class attribute
    2. Implement `collect()` as an async generator that yields articles
    3. Implement `get_status()` to report health
    
    Optionally override:
    - `is_available()` - Check if collector can run
    - `get_info()` - Return CollectorInfo metadata
    - `configure()` - Apply runtime configuration
    
    STREAMING ARCHITECTURE (v1.5.0+)
    ================================
    The collect() method is now an AsyncGenerator that yields articles
    one at a time as they are collected. This enables:
    
    - Immediate processing: Articles are queued for AI as they arrive
    - Smooth UX: Signals appear steadily instead of in bursts
    - Memory efficiency: No need to hold all articles in memory
    - Better error isolation: One feed failing doesn't block others
    
    @updated 2026-02-04 by Mr Cat + Claude - Streaming architecture
    """
    
    # === CLASS ATTRIBUTES (override in subclasses) ===
    name: str = "base"  # Unique identifier
    display_name: str = "Base Collector"
    description: str = "Abstract base collector"
    requires_api_key: bool = False
    api_key_env_var: Optional[str] = None
    supports_groups: bool = True
    default_enabled: bool = False
    
    def __init__(self):
        """Initialize collector with empty stats"""
        self.stats = CollectorStats()
        self.config: Dict[str, Any] = {}
        self._enabled = False
    
    # === ABSTRACT METHODS (must implement) ===
    
    @abstractmethod
    async def collect(self, groups: Set[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Collect articles from this source - STREAMING MODE
        
        This is an async generator that yields articles one at a time
        as they are collected. Each article is immediately available
        for processing.
        
        Args:
            groups: Set of enabled geographic/topic groups
                   (e.g., {'ukraine', 'global', 'osint'})
        
        Yields:
            Article dictionaries with at minimum:
            - title: str
            - url: str (unique identifier)
            - source: str (name of the source)
            - collected_at: str (ISO timestamp)
            
            Optional fields:
            - description: str
            - published: str (ISO timestamp)
            - author: str
            - language: str
            - location: str
            - lat/lon: float
        
        Example:
            async def collect(self, groups):
                for feed in self.get_feeds(groups):
                    articles = await self.fetch_feed(feed)
                    for article in articles:
                        self.stats.record_article()
                        yield article
                self.stats.record_run_complete()
        
        @updated 2026-02-04 by Mr Cat + Claude - Changed from List to AsyncGenerator
        """
        # This makes the method a generator (required for ABC)
        if False:
            yield {}
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status and health of this collector
        
        Returns:
            Dict containing at minimum:
            - name: str
            - enabled: bool
            - available: bool
            - healthy: bool
            - stats: Dict (from CollectorStats.to_dict())
            
            Additional collector-specific fields as needed
        """
        pass
    
    # === OPTIONAL OVERRIDES ===
    
    def is_available(self) -> bool:
        """
        Check if this collector can run
        
        Override to check for:
        - Required API keys present
        - Required dependencies installed
        - Network connectivity
        - Rate limit status
        
        Returns:
            True if collector is ready to run
        """
        if self.requires_api_key and self.api_key_env_var:
            import os
            return bool(os.getenv(self.api_key_env_var))
        return True
    
    def get_info(self) -> CollectorInfo:
        """
        Get metadata about this collector
        
        Returns:
            CollectorInfo with collector details
        """
        return CollectorInfo(
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            requires_api_key=self.requires_api_key,
            api_key_env_var=self.api_key_env_var,
            supports_groups=self.supports_groups,
            default_enabled=self.default_enabled
        )
    
    def configure(self, config: Dict[str, Any]) -> bool:
        """
        Apply runtime configuration to this collector
        
        Args:
            config: Dict of configuration options
        
        Returns:
            True if configuration was applied successfully
        """
        self.config = config
        return True
    
    def enable(self):
        """Enable this collector"""
        self._enabled = True
    
    def disable(self):
        """Disable this collector"""
        self._enabled = False
    
    @property
    def enabled(self) -> bool:
        """Check if collector is enabled"""
        return self._enabled
    
