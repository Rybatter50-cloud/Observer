"""
Observer Intelligence Platform - Collector Registry (Streaming)
=============================================================
Central registry for all data collectors with streaming support.

@created 2026-02-03 by Claude - v1.5.0 Collector Architecture Refactor
@updated 2026-02-04 by Mr Cat + Claude - STREAMING ARCHITECTURE
                                         Added stream_all() for continuous article flow

The registry:
1. Tracks all available collectors (RSS, NewsAPI, Scraper, etc.)
2. Manages which collectors are enabled
3. Orchestrates collection across all enabled collectors
4. Provides unified status/health reporting
5. NEW: stream_all() yields articles as they arrive from any collector

Usage:
    from services.collectors import get_collector_registry
    
    # Get the singleton registry
    registry = get_collector_registry()
    
    # STREAMING: Process articles as they arrive
    async for article in registry.stream_all(groups):
        await process_article(article)  # Immediate processing!
"""

import asyncio
from typing import Dict, Any, List, Set, Optional, Type, AsyncGenerator
from datetime import datetime

from utils.logging import get_logger
from .base import BaseCollector, CollectorInfo, CollectorStats

logger = get_logger(__name__)


class CollectorRegistry:
    """
    Central registry managing all data collectors
    
    STREAMING ARCHITECTURE (v1.5.0+)
    =================================
    Use stream_all() for continuous article flow:
    
        async for article in registry.stream_all(groups):
            await route_signal(article)  # Process immediately
    
    This provides:
    - Immediate processing: No waiting for all collectors to finish
    - Smooth UX: Signals appear steadily instead of in bursts  
    - Better resource usage: Lower peak memory
    - Error isolation: One failing source doesn't block others
    
    @updated 2026-02-04 by Mr Cat + Claude - Streaming architecture
    """
    
    def __init__(self):
        """Initialize empty registry"""
        # Registered collector classes (not instances)
        self._collector_classes: Dict[str, Type[BaseCollector]] = {}
        
        # Instantiated collectors (lazy-loaded)
        self._collectors: Dict[str, BaseCollector] = {}
        
        # Which collectors are enabled
        self._enabled: Set[str] = set()
        
        # Per-collector configuration
        self._configs: Dict[str, Dict[str, Any]] = {}
        
        # Collection statistics
        self._last_collection: Optional[datetime] = None
        self._total_collected: int = 0
        
        logger.debug("CollectorRegistry initialized")
    
    # === REGISTRATION ===
    
    def register(self, collector_class: Type[BaseCollector]) -> bool:
        """
        Register a collector class with the registry
        
        Args:
            collector_class: Class (not instance) extending BaseCollector
        
        Returns:
            True if registration successful
        """
        name = collector_class.name
        
        if name in self._collector_classes:
            logger.warning(f"Collector '{name}' already registered, replacing")
        
        self._collector_classes[name] = collector_class
        logger.info(f"✓ Registered collector: {name} ({collector_class.display_name})")
        
        # Auto-enable if default_enabled is True
        if collector_class.default_enabled:
            self.enable_collector(name)
        
        return True
    
    def _get_or_create_instance(self, name: str) -> Optional[BaseCollector]:
        """Get existing instance or create new one"""
        if name not in self._collector_classes:
            return None
        
        if name not in self._collectors:
            collector_class = self._collector_classes[name]
            instance = collector_class()
            
            # Apply stored configuration
            if name in self._configs:
                instance.configure(self._configs[name])
            
            # Set enabled state
            if name in self._enabled:
                instance.enable()
            
            self._collectors[name] = instance
        
        return self._collectors[name]
    
    # === ENABLE/DISABLE ===
    
    def enable_collector(self, name: str) -> bool:
        """Enable a collector"""
        if name not in self._collector_classes:
            logger.warning(f"Cannot enable unknown collector: {name}")
            return False
        
        self._enabled.add(name)
        
        if name in self._collectors:
            self._collectors[name].enable()
        
        logger.info(f"✓ Enabled collector: {name}")
        return True
    
    def disable_collector(self, name: str) -> bool:
        """Disable a collector"""
        self._enabled.discard(name)
        
        if name in self._collectors:
            self._collectors[name].disable()
        
        logger.info(f"✗ Disabled collector: {name}")
        return True
    
    def get_collector(self, name: str) -> Optional[BaseCollector]:
        """Get a collector instance by name"""
        return self._get_or_create_instance(name)
    
    def get_available_collector_names(self) -> List[str]:
        """Get names of all registered collectors"""
        return list(self._collector_classes.keys())
    
    def get_enabled_collector_names(self) -> List[str]:
        """Get names of enabled collectors"""
        return list(self._enabled)
    
    def set_enabled_collectors(self, names: Set[str]):
        """Set which collectors are enabled"""
        # Disable collectors not in the new set
        for name in list(self._enabled):
            if name not in names:
                self.disable_collector(name)
        
        # Enable collectors in the new set
        for name in names:
            if name not in self._enabled:
                self.enable_collector(name)
    
    # === CONFIGURATION ===
    
    def configure_collector(self, name: str, config: Dict[str, Any]) -> bool:
        """Apply configuration to a collector"""
        self._configs[name] = config
        
        if name in self._collectors:
            return self._collectors[name].configure(config)
        
        return True
    
    # =========================================================================
    # STREAMING COLLECTION - THE NEW WAY
    # =========================================================================
    
    async def stream_all(self, groups: Set[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream articles from all enabled collectors concurrently.

        Collectors run in parallel via background tasks that push articles
        into a shared asyncio.Queue. The caller yields articles as they
        arrive from any collector, so a slow collector no longer blocks
        the others.

        Args:
            groups: Set of enabled geographic/topic groups

        Yields:
            Article dictionaries, one at a time, as they arrive

        Example:
            async for article in registry.stream_all(groups):
                await self._route_signal(article)  # Process immediately

        @added 2026-02-04 by Mr Cat + Claude - Streaming architecture
        @updated 2026-02-07 by Mr Cat + Claude - Run collectors concurrently
        """
        enabled_collectors = self.get_enabled_collectors()

        if not enabled_collectors:
            logger.warning("No collectors enabled for streaming")
            return

        available = [c for c in enabled_collectors if c.is_available()]
        for c in enabled_collectors:
            if c not in available:
                logger.warning(f"Collector '{c.name}' not available, skipping")

        if not available:
            return

        logger.info(f"Starting concurrent streaming from {len(available)} collectors")

        start_time = datetime.now()
        total_yielded = 0

        # Per-collector timeout: safeguard against truly hanging collectors
        # (e.g. newspaper4k with unresponsive servers). Generous enough to
        # let the RSS collector finish all feeds with stagger delays.
        from config import config as _cfg
        collector_timeout = getattr(_cfg, 'COLLECTOR_TIMEOUT', 600)

        # Shared queue: collectors push articles, we yield them
        queue: asyncio.Queue = asyncio.Queue()
        _SENTINEL = object()  # Marks a collector as finished

        async def _run_collector(collector):
            """Background task: drain a collector into the shared queue."""
            count = 0
            try:
                async with asyncio.timeout(collector_timeout):
                    async for article in collector.collect(groups):
                        await queue.put(article)
                        count += 1
            except TimeoutError as e:
                logger.warning(
                    f"Collector '{collector.name}' timed out after "
                    f"{collector_timeout}s ({count} articles before timeout)"
                )
                collector.stats.record_error(e)
            except Exception as e:
                # Use logger.exception to capture full traceback
                logger.exception(f"Collector '{collector.name}' failed: {e}")
                collector.stats.record_error(e)
            finally:
                if count > 0:
                    logger.info(f"Collector '{collector.name}': {count} articles streamed")
                else:
                    logger.debug(f"Collector '{collector.name}': 0 articles")
                await queue.put(_SENTINEL)

        # Launch all collectors concurrently
        tasks = [asyncio.create_task(_run_collector(c)) for c in available]
        finished_count = 0

        try:
            while finished_count < len(available):
                item = await queue.get()
                if item is _SENTINEL:
                    finished_count += 1
                else:
                    total_yielded += 1
                    yield item
        finally:
            # Ensure all tasks are cleaned up
            for t in tasks:
                if not t.done():
                    t.cancel()

        # Update registry stats
        self._last_collection = datetime.now()
        self._total_collected += total_yielded

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Streaming complete: {total_yielded} total articles in {elapsed:.1f}s")
    
    # === STATUS ===
    
    def get_enabled_collectors(self) -> List[BaseCollector]:
        """Get list of enabled collector instances"""
        collectors = []
        for name in self._enabled:
            instance = self._get_or_create_instance(name)
            if instance:
                collectors.append(instance)
        return collectors
    
    def get_all_collectors(self) -> List[BaseCollector]:
        """Get list of all registered collector instances"""
        collectors = []
        for name in self._collector_classes:
            instance = self._get_or_create_instance(name)
            if instance:
                collectors.append(instance)
        return collectors
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all collectors"""
        collectors_status = {}
        
        for name in self._collector_classes:
            instance = self._get_or_create_instance(name)
            if instance:
                collectors_status[name] = instance.get_status()
        
        return {
            'registered_collectors': list(self._collector_classes.keys()),
            'enabled_collectors': list(self._enabled),
            'available_collectors': [
                name for name, inst in self._collectors.items()
                if inst.is_available()
            ],
            'collectors': collectors_status,
            'last_collection': self._last_collection.isoformat() if self._last_collection else None,
            'total_collected': self._total_collected,
            'streaming_enabled': True,  # Flag for dashboard
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_registry_instance: Optional[CollectorRegistry] = None


def get_collector_registry() -> CollectorRegistry:
    """
    Get the singleton CollectorRegistry instance
    
    Creates the registry and auto-registers available collectors
    on first call.
    """
    global _registry_instance
    
    if _registry_instance is None:
        _registry_instance = CollectorRegistry()
        _auto_register_collectors()
    
    return _registry_instance


def _auto_register_collectors():
    """
    Auto-discover and register available collectors
    
    Called once when registry is first accessed.
    """
    global _registry_instance
    import os

    if _registry_instance is None:
        return

    # =========================================================================
    # RSS COLLECTOR (always available)
    # =========================================================================
    try:
        from .rss_collector import RSSCollector
        _registry_instance.register(RSSCollector)
    except ImportError as e:
        logger.error(f"RSSCollector import failed: {e}")
    except Exception as e:
        import traceback
        logger.error(f"RSSCollector registration failed: {type(e).__name__}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    # =========================================================================
    # NP4K WEB SCRAPER COLLECTOR
    # @added 2026-02-04 by Mr Cat + Claude - v1.5.0 Collector Integration
    # =========================================================================
    try:
        from .np4k_collector import NP4KCollector
        _registry_instance.register(NP4KCollector)

        # NP4K defaults to off (specialist tool, conserves tokens)
        np4k_enabled = os.getenv('NP4K_ENABLED', 'false').lower() in ('true', '1', 'yes')
        if np4k_enabled:
            _registry_instance.enable_collector('np4k')
            logger.info("NP4K collector enabled at startup (NP4K_ENABLED=true)")
        else:
            _registry_instance.disable_collector('np4k')
            logger.info("NP4K collector registered but disabled (enable via dashboard)")
    except ImportError as e:
        logger.debug(f"NP4KCollector not available: {e}")
    
    # =========================================================================
    # Observer: Only RSS and NP4K collectors available
    # NewsAPI, DVIDS, WikiRumours removed
    # =========================================================================
    
    registered = _registry_instance.get_available_collector_names()
    enabled = _registry_instance.get_enabled_collector_names()
    logger.info(f"✓ Auto-registration complete: {len(registered)} collectors, {len(enabled)} enabled")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'CollectorRegistry',
    'get_collector_registry',
    'BaseCollector',
    'CollectorInfo', 
    'CollectorStats',
]
