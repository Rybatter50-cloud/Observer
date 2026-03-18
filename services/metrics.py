"""
RYBAT Intelligence Platform - Metrics Collector
Centralized metrics collection for AI services telemetry

This module provides thread-safe tracking of:
- API call counts with timestamps for rate calculation
- Queue sizes
- Service health status

Usage:
    from services.metrics import metrics_collector

    # Record an API call
    metrics_collector.record_call('analyst')
    metrics_collector.record_call('translator')

    # Update queue size
    metrics_collector.set_queue_size(5)

    # Get metrics for dashboard
    metrics = metrics_collector.get_metrics()
"""

import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import deque

from utils.logging import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """
    Thread-safe metrics collector for AI services
    
    Tracks API calls with timestamps to calculate calls-per-minute rates.
    Uses a sliding window approach for accurate rate calculation.
    """
    
    def __init__(self, window_seconds: int = 60):
        """
        Initialize metrics collector
        
        Args:
            window_seconds: Time window for rate calculation (default 60s)
        """
        self._lock = threading.Lock()
        self._window_seconds = window_seconds
        
        # Call timestamps for rate calculation (using deque for efficient pruning)
        self._analyst_calls: deque = deque()
        self._translator_calls: deque = deque()
        
        # Queue tracking
        self._queue_size: int = 0
        
        # Cumulative stats
        self._total_analyst_calls: int = 0
        self._total_translator_calls: int = 0
        self._total_cache_hits: int = 0

        # Pipeline stage counters (incremented by ArticlePipeline)
        self._pipeline_received: int = 0
        self._pipeline_collected: int = 0
        self._pipeline_prepared: int = 0
        self._pipeline_duplicates: int = 0
        self._pipeline_errors: int = 0
        self._pipeline_analysed: int = 0
        self._pipeline_persisted: int = 0
        self._pipeline_broadcast: int = 0

        # Analysis mode counters (incremented by IntelligenceService)
        self._analysis_local: int = 0
        self._analysis_fallback: int = 0
        self._analysis_skipped: int = 0

        # Scraper collection stats (moved from routes_scraper.py)
        self._scraper_collections: int = 0
        self._scraper_articles: int = 0
        self._scraper_last_collection: Optional[str] = None

        # Context scoring stats (escalation, novelty, reputation)
        self._ctx_escalation_count: int = 0
        self._ctx_escalation_total: int = 0
        self._ctx_novelty_count: int = 0
        self._ctx_novelty_total: int = 0
        self._ctx_reputation_count: int = 0
        self._ctx_reputation_total: int = 0
        self._ctx_refreshes: int = 0

        # ── Token budget ledger ──────────────────────────────────────────
        # Timestamped ring buffer per provider for rolling 24h budget tracking.
        # Each entry: (datetime, token_count)
        # Providers: 'gemini_analyst', 'gemini'
        self._token_ledger: Dict[str, deque] = {
            'gemini_analyst': deque(),
            'gemini': deque(),
        }
        # Daily limits (populated from throttle profile / env)
        self._token_daily_limits: Dict[str, int] = {
            'gemini_analyst': 0,
            'gemini': 0,
        }

        logger.info("Metrics collector initialized")
    
    def _prune_old_calls(self, calls: deque) -> None:
        """Remove calls older than the window"""
        cutoff = datetime.now() - timedelta(seconds=self._window_seconds)
        while calls and calls[0] < cutoff:
            calls.popleft()
    
    def record_analyst_call(self) -> None:
        """Record an analyst API call"""
        with self._lock:
            now = datetime.now()
            self._analyst_calls.append(now)
            self._total_analyst_calls += 1
            self._prune_old_calls(self._analyst_calls)
    
    def record_translator_call(self) -> None:
        """Record a translator API call"""
        with self._lock:
            now = datetime.now()
            self._translator_calls.append(now)
            self._total_translator_calls += 1
            self._prune_old_calls(self._translator_calls)
    
    def record_cache_hit(self) -> None:
        """Record a translation cache hit"""
        with self._lock:
            self._total_cache_hits += 1
    
    def record_call(self, service: str) -> None:
        """
        Record an API call for the specified service
        
        Args:
            service: 'analyst' or 'translator'
        """
        if service == 'analyst':
            self.record_analyst_call()
        elif service == 'translator':
            self.record_translator_call()
    
    def set_queue_size(self, size: int) -> None:
        """Update the current queue size"""
        with self._lock:
            self._queue_size = max(0, size)
    
    def increment_queue(self) -> None:
        """Increment queue size by 1"""
        with self._lock:
            self._queue_size += 1
    
    def decrement_queue(self) -> None:
        """Decrement queue size by 1"""
        with self._lock:
            self._queue_size = max(0, self._queue_size - 1)
    
    # ------------------------------------------------------------------
    # Pipeline stage recording
    # ------------------------------------------------------------------

    def record_pipeline_received(self) -> None:
        with self._lock:
            self._pipeline_received += 1

    def record_pipeline_collected(self) -> None:
        with self._lock:
            self._pipeline_collected += 1

    def record_pipeline_prepared(self) -> None:
        with self._lock:
            self._pipeline_prepared += 1

    def record_pipeline_duplicate(self) -> None:
        with self._lock:
            self._pipeline_duplicates += 1

    def record_pipeline_error(self) -> None:
        with self._lock:
            self._pipeline_errors += 1

    def record_pipeline_analysed(self) -> None:
        with self._lock:
            self._pipeline_analysed += 1

    def record_pipeline_persisted(self) -> None:
        with self._lock:
            self._pipeline_persisted += 1

    def record_pipeline_broadcast(self) -> None:
        with self._lock:
            self._pipeline_broadcast += 1

    def get_pipeline_stats(self) -> Dict[str, int]:
        """Pipeline stage counters for diagnostics."""
        with self._lock:
            return {
                'received': self._pipeline_received,
                'collected': self._pipeline_collected,
                'prepared': self._pipeline_prepared,
                'duplicates': self._pipeline_duplicates,
                'errors': self._pipeline_errors,
                'analysed': self._pipeline_analysed,
                'persisted': self._pipeline_persisted,
                'broadcast': self._pipeline_broadcast,
            }

    # ------------------------------------------------------------------
    # Analysis mode recording
    # ------------------------------------------------------------------

    def record_analysis_mode(self, mode: str) -> None:
        """Record which analysis mode was used (LOCAL/FALLBACK/SKIPPED)."""
        with self._lock:
            if mode == 'LOCAL':
                self._analysis_local += 1
            elif mode == 'FALLBACK':
                self._analysis_fallback += 1
            elif mode == 'SKIPPED':
                self._analysis_skipped += 1

    def get_analysis_stats(self) -> Dict[str, int]:
        """Analysis mode counters for dashboard/diagnostics."""
        with self._lock:
            return {
                'local_count': self._analysis_local,
                'fallback_count': self._analysis_fallback,
                'skipped_count': self._analysis_skipped,
            }

    # ------------------------------------------------------------------
    # Scraper collection stats
    # ------------------------------------------------------------------

    def record_scraper_collection(self, article_count: int) -> None:
        """Record a scraper collection run."""
        with self._lock:
            self._scraper_collections += 1
            self._scraper_articles += article_count
            self._scraper_last_collection = datetime.now().isoformat()

    def get_scraper_stats(self) -> Dict[str, Any]:
        """Scraper collection counters for dashboard."""
        with self._lock:
            return {
                'total_collections': self._scraper_collections,
                'total_articles': self._scraper_articles,
                'last_collection': self._scraper_last_collection,
            }

    # ------------------------------------------------------------------
    # Context scoring stats
    # ------------------------------------------------------------------

    def record_context_refresh(self) -> None:
        """Record a scoring context DB refresh."""
        with self._lock:
            self._ctx_refreshes += 1

    def record_context_escalation(self, boost: int) -> None:
        """Record an escalation boost applied to a pre-score."""
        if boost > 0:
            with self._lock:
                self._ctx_escalation_count += 1
                self._ctx_escalation_total += boost

    def record_context_novelty(self, boost: int) -> None:
        """Record a novelty boost applied to a pre-score."""
        if boost > 0:
            with self._lock:
                self._ctx_novelty_count += 1
                self._ctx_novelty_total += boost

    def record_context_reputation(self, mod: int) -> None:
        """Record a reputation modifier applied to a pre-score."""
        if mod != 0:
            with self._lock:
                self._ctx_reputation_count += 1
                self._ctx_reputation_total += mod

    def get_context_stats(self) -> Dict[str, Any]:
        """Context scoring stats for diagnostics/dashboard."""
        with self._lock:
            return {
                'refreshes': self._ctx_refreshes,
                'escalation_applied': self._ctx_escalation_count,
                'escalation_total_boost': self._ctx_escalation_total,
                'novelty_applied': self._ctx_novelty_count,
                'novelty_total_boost': self._ctx_novelty_total,
                'reputation_applied': self._ctx_reputation_count,
                'reputation_total_mod': self._ctx_reputation_total,
            }

    # ------------------------------------------------------------------
    # Token budget tracking (rolling 24h window)
    # ------------------------------------------------------------------

    def set_token_daily_limit(self, provider: str, limit: int) -> None:
        """Set the daily token limit for a provider."""
        if provider in self._token_daily_limits:
            self._token_daily_limits[provider] = limit

    def record_token_usage(self, provider: str, tokens: int) -> None:
        """Record tokens consumed by a provider with current timestamp."""
        if provider not in self._token_ledger or tokens <= 0:
            return
        with self._lock:
            self._token_ledger[provider].append((datetime.now(), tokens))

    def _prune_token_ledger(self, provider: str) -> None:
        """Remove entries older than 24 hours from a provider's ledger."""
        cutoff = datetime.now() - timedelta(hours=24)
        ledger = self._token_ledger[provider]
        while ledger and ledger[0][0] < cutoff:
            ledger.popleft()

    def get_token_budget(self, provider: str) -> Dict[str, Any]:
        """
        Get rolling 24h token budget status for a provider.

        Returns:
            dict with: limit, used_24h, remaining, pct_remaining,
                       recovering_per_hour (tokens about to age out)
        """
        if provider not in self._token_ledger:
            return {'limit': 0, 'used_24h': 0, 'remaining': 0,
                    'pct_remaining': 100, 'recovering_per_hour': 0}

        with self._lock:
            self._prune_token_ledger(provider)
            ledger = self._token_ledger[provider]
            limit = self._token_daily_limits.get(provider, 0)

            used_24h = sum(tokens for _, tokens in ledger)

            # Tokens about to recover: entries in the 23-24h ago window
            # (these will age out of the 24h window in the next hour)
            now = datetime.now()
            recovery_cutoff = now - timedelta(hours=23)
            recovering = sum(
                tokens for ts, tokens in ledger
                if ts < recovery_cutoff
            )

            remaining = max(0, limit - used_24h) if limit > 0 else 0
            pct = round(remaining / limit * 100, 1) if limit > 0 else 100

            return {
                'limit': limit,
                'used_24h': used_24h,
                'remaining': remaining,
                'pct_remaining': pct,
                'recovering_per_hour': recovering,
            }

    def get_all_token_budgets(self) -> Dict[str, Dict[str, Any]]:
        """Get token budget status for all providers."""
        return {
            provider: self.get_token_budget(provider)
            for provider in self._token_ledger
        }

    # ------------------------------------------------------------------
    # Gemini /discover call counter (resets daily at midnight Pacific)
    # ------------------------------------------------------------------

    def record_gemini_discover_call(self) -> None:
        """Record one /discover API call for the Gemini daily counter."""
        if not hasattr(self, '_gemini_discover_calls'):
            self._gemini_discover_calls: list = []
        self._gemini_discover_calls.append(datetime.now())

    def load_discover_call_history(self, timestamps) -> int:
        """
        Bulk-load historical discover call timestamps into memory.
        Called once at startup with rows from DB.
        """
        if not hasattr(self, '_gemini_discover_calls'):
            self._gemini_discover_calls: list = []
        count = 0
        for ts in timestamps:
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            self._gemini_discover_calls.append(ts)
            count += 1
        if count > 0:
            logger.info(f"Loaded {count} discover call entries from DB")
        return count

    def get_gemini_discover_usage(self, daily_limit: int = 20) -> Dict[str, Any]:
        """
        Get Gemini /discover usage for the current day (Pacific timezone).
        Resets at 12:00 AM Pacific Time.
        """
        if not hasattr(self, '_gemini_discover_calls'):
            self._gemini_discover_calls = []

        # Compute today's midnight Pacific in UTC
        import zoneinfo
        pacific = zoneinfo.ZoneInfo('America/Los_Angeles')
        now_pacific = datetime.now(tz=pacific)
        midnight_pacific = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0)
        # Convert back to naive UTC for comparison
        midnight_utc = midnight_pacific.astimezone(zoneinfo.ZoneInfo('UTC')).replace(tzinfo=None)

        # Count calls since midnight Pacific
        calls_today = sum(1 for ts in self._gemini_discover_calls if ts >= midnight_utc)

        # Prune old entries (older than 48h)
        cutoff = datetime.now() - timedelta(hours=48)
        self._gemini_discover_calls = [ts for ts in self._gemini_discover_calls if ts >= cutoff]

        remaining = max(0, daily_limit - calls_today)
        return {
            'used_today': calls_today,
            'daily_limit': daily_limit,
            'remaining': remaining,
            'resets_at': 'midnight Pacific Time',
        }

    def load_token_history(self, entries) -> int:
        """
        Bulk-load historical token usage into the in-memory ledger.
        Called once at startup with rows from DB (provider, timestamp, tokens).

        Args:
            entries: iterable of (provider, datetime, tokens) tuples

        Returns:
            Number of entries loaded
        """
        count = 0
        with self._lock:
            for provider, ts, tokens in entries:
                if provider in self._token_ledger and tokens > 0:
                    # Convert timezone-aware to naive if needed (ledger uses naive)
                    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                        ts = ts.replace(tzinfo=None)
                    self._token_ledger[provider].append((ts, tokens))
                    count += 1
        if count > 0:
            logger.info(f"Loaded {count} token usage entries from DB (rolling 24h)")
        return count

    # ------------------------------------------------------------------
    # Rate accessors
    # ------------------------------------------------------------------

    def get_analyst_calls_per_minute(self) -> float:
        """Get analyst API calls in the last minute"""
        with self._lock:
            self._prune_old_calls(self._analyst_calls)
            return len(self._analyst_calls)

    def get_translator_calls_per_minute(self) -> float:
        """Get translator API calls in the last minute"""
        with self._lock:
            self._prune_old_calls(self._translator_calls)
            return len(self._translator_calls)

    def get_queue_size(self) -> int:
        """Get current queue size"""
        with self._lock:
            return self._queue_size

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all metrics for dashboard display
        
        Returns:
            Dictionary with all current metrics
        """
        with self._lock:
            self._prune_old_calls(self._analyst_calls)
            self._prune_old_calls(self._translator_calls)
            
            return {
                'analyst_calls_per_min': len(self._analyst_calls),
                'translator_calls_per_min': len(self._translator_calls),
                'queue_size': self._queue_size,
                'total_analyst_calls': self._total_analyst_calls,
                'total_translator_calls': self._total_translator_calls,
                'total_cache_hits': self._total_cache_hits,
                'timestamp': datetime.now().isoformat()
            }
    
    def reset(self) -> None:
        """Reset all metrics (mainly for testing)"""
        with self._lock:
            self._analyst_calls.clear()
            self._translator_calls.clear()
            self._queue_size = 0
            self._total_analyst_calls = 0
            self._total_translator_calls = 0
            self._total_cache_hits = 0
            self._pipeline_received = 0
            self._pipeline_collected = 0
            self._pipeline_prepared = 0
            self._pipeline_duplicates = 0
            self._pipeline_errors = 0
            self._pipeline_analysed = 0
            self._pipeline_persisted = 0
            self._pipeline_broadcast = 0
            self._analysis_local = 0
            self._analysis_fallback = 0
            self._analysis_skipped = 0
            self._scraper_collections = 0
            self._scraper_articles = 0
            self._scraper_last_collection = None
            self._ctx_escalation_count = 0
            self._ctx_escalation_total = 0
            self._ctx_novelty_count = 0
            self._ctx_novelty_total = 0
            self._ctx_reputation_count = 0
            self._ctx_reputation_total = 0
            self._ctx_refreshes = 0
            for provider in self._token_ledger:
                self._token_ledger[provider].clear()


# Singleton instance
metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the singleton metrics collector instance"""
    return metrics_collector


async def persist_token_usage(provider: str, tokens: int) -> None:
    """
    Fire-and-forget DB persistence for token usage.
    Called via asyncio.create_task() from AI call sites.
    In-memory ledger is the primary source; this is best-effort backup.
    """
    try:
        from api.deps import db  # Lazy import to avoid circular dependency
        await db.metrics.insert_token_usage(provider, tokens)
    except Exception:
        pass  # Silent — in-memory ledger already has it


async def persist_discover_call() -> None:
    """
    Fire-and-forget DB persistence for a /discover API call.
    Called via asyncio.create_task() from the discover endpoint.
    """
    try:
        from api.deps import db
        await db.metrics.insert_discover_call()
    except Exception:
        pass
