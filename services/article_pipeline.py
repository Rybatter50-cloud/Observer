"""
Observer Lite - Article Pipeline (Single-Pass)
============================================
Single-pass article pipeline: collect -> translate -> persist -> broadcast.

No AI scoring, no embeddings, no entity extraction.
Articles are collected, translated (NLLB), and persisted.

Architecture:
  Collectors -> stream_all() -> work_queue -> Workers -> DB + WebSocket
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional

from config import config
from services.websocket import manager
from utils.logging import get_logger

_IN_FLIGHT_TTL = 600  # 10 minutes

logger = get_logger(__name__)


class ArticlePipeline:
    """
    Single-pass article pipeline: collect -> translate -> persist -> broadcast.

    Args:
        intel_service: IntelligenceService instance (owns prepare/finalize methods)
        num_workers: Number of concurrent workers (default 3)
    """

    def __init__(self, intel_service, num_workers: int = 3):
        self._intel = intel_service
        self._num_workers = num_workers

        self._state_manager = None
        self._collector_registry = None

        self._work_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._in_flight: Dict[str, float] = {}
        self._running = False

        from services.metrics import metrics_collector
        self._metrics = metrics_collector

    async def run(self):
        """Main entry point. Starts workers, recovers pending, then collects."""
        self._running = True

        if not await self._init_collectors():
            logger.error("Pipeline: collector init failed -- cannot start")
            return

        await self._recover_pending()

        workers = [
            asyncio.create_task(self._worker(i), name=f"pipeline_worker_{i}")
            for i in range(self._num_workers)
        ]
        logger.info(
            f"Article pipeline started ({self._num_workers} workers, "
            f"queue_max={self._work_queue.maxsize})"
        )

        cycle_num = 0
        try:
            while self._running:
                cycle_num += 1
                logger.info(
                    f"Pipeline: cycle {cycle_num} starting "
                    f"(queue={self._work_queue.qsize()}/{self._work_queue.maxsize})"
                )
                try:
                    await self._collect_cycle()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Pipeline collection error: {e}")
                logger.info(
                    f"Pipeline: cycle {cycle_num} done, "
                    f"sleeping {config.FEED_CHECK_INTERVAL}s "
                    f"(queue={self._work_queue.qsize()}/{self._work_queue.maxsize})"
                )
                await asyncio.sleep(config.FEED_CHECK_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Pipeline cancelled -- shutting down workers")
        finally:
            self._running = False
            for _ in workers:
                try:
                    self._work_queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            await asyncio.gather(*workers, return_exceptions=True)
            logger.info("Article pipeline stopped")

    def get_status(self) -> dict:
        """Return pipeline metrics for the diagnostic endpoint."""
        stats = self._metrics.get_pipeline_stats()
        stats.update({
            'running': self._running,
            'num_workers': self._num_workers,
            'work_queue_depth': self._work_queue.qsize(),
            'work_queue_maxsize': self._work_queue.maxsize,
            'in_flight': len(self._in_flight),
        })
        return stats

    @property
    def collector_registry(self):
        return self._collector_registry

    async def _init_collectors(self) -> bool:
        """Initialize SourceStateManager and CollectorRegistry."""
        try:
            from services.source_state import get_source_state_manager
            from services.collectors import get_collector_registry

            self._state_manager = get_source_state_manager()
            self._collector_registry = get_collector_registry()

            enabled = set(self._collector_registry.get_enabled_collector_names())
            self._state_manager.enabled_collectors = enabled
            self._collector_registry.set_enabled_collectors(enabled)

            rss_config = {
                'max_articles_per_feed': config.FEED_MAX_ARTICLES_PER_SOURCE,
                'concurrency': config.FEED_CONCURRENCY,
            }
            self._collector_registry.configure_collector('rss', rss_config)
            logger.info(
                f"RSS collector config: "
                f"max_per_feed={rss_config['max_articles_per_feed']}, "
                f"concurrency={rss_config['concurrency']}"
            )

            for name, cfg in self._state_manager.collector_configs.items():
                self._collector_registry.configure_collector(name, cfg)

            state = self._state_manager.get_status()
            reg = self._collector_registry.get_status()
            logger.info(
                f"Pipeline collectors initialized: "
                f"{len(state['enabled_groups'])} groups, "
                f"{len(state['enabled_collectors'])} collectors"
            )
            logger.info(f"Enabled: {', '.join(reg['enabled_collectors'])}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize collectors: {e}")
            return False

    async def _collect_cycle(self):
        """Stream articles from all enabled collectors into the work queue."""
        if not self._state_manager or not self._collector_registry:
            logger.error("Collector architecture not initialized")
            return

        enabled_groups = self._state_manager.enabled_groups

        from services.translation import get_translation_service
        from services.content_filter import get_content_filter
        translator = get_translation_service()
        content_filter = get_content_filter()

        cycle_start = datetime.now()
        cycle_collected = 0
        cycle_in_flight = 0
        cycle_db_dup = 0
        cycle_title_dup = 0
        cycle_whitelist = 0
        cycle_errors = 0

        collector_stats: Dict[str, Dict[str, int]] = {}

        # Evict stale in-flight URLs
        now_ts = datetime.now().timestamp()
        stale = [u for u, t in self._in_flight.items() if now_ts - t > _IN_FLIGHT_TTL]
        for u in stale:
            del self._in_flight[u]
        if stale:
            logger.warning(f"Pipeline: evicted {len(stale)} stale in-flight URLs")

        async for article in self._collector_registry.stream_all(enabled_groups):
            url = ''
            collector_name = 'unknown'
            try:
                url = (article.get('url') or '').strip()
                collector_name = article.get('collector', 'unknown')

                if collector_name not in collector_stats:
                    collector_stats[collector_name] = {
                        'received': 0, 'queued': 0, 'in_flight': 0,
                        'db_dup': 0, 'title_dup': 0, 'errors': 0,
                    }
                cstats = collector_stats[collector_name]
                cstats['received'] += 1
                self._metrics.record_pipeline_received()

                if url and url in self._in_flight:
                    self._metrics.record_pipeline_duplicate()
                    cycle_in_flight += 1
                    cstats['in_flight'] += 1
                    continue

                if url and await self._intel.db.url_exists(url):
                    self._metrics.record_pipeline_duplicate()
                    cycle_db_dup += 1
                    cstats['db_dup'] += 1
                    continue

                if url:
                    self._in_flight[url] = datetime.now().timestamp()

                prepared = await self._intel._prepare_article(article, translator)
                if prepared == 'duplicate':
                    self._metrics.record_pipeline_duplicate()
                    cycle_title_dup += 1
                    cstats['title_dup'] += 1
                    if url:
                        self._in_flight.pop(url, None)
                    continue
                if prepared is None:
                    self._metrics.record_pipeline_error()
                    cycle_errors += 1
                    cstats['errors'] += 1
                    if url:
                        self._in_flight.pop(url, None)
                    continue

                wl_title = prepared.get('title', '')
                wl_desc = prepared.get('description', '') or ''
                wl_accept, _wl_reason = content_filter.should_accept(
                    wl_title, wl_desc, skip_whitelist=False
                )
                if not wl_accept:
                    cycle_whitelist += 1
                    if url:
                        self._in_flight.pop(url, None)
                    continue

                self._metrics.record_pipeline_prepared()
                self._metrics.record_pipeline_collected()
                cycle_collected += 1
                cstats['queued'] += 1

                prepared_url = prepared.get('url', '')
                if prepared_url and prepared_url != url:
                    self._in_flight[prepared_url] = datetime.now().timestamp()
                    self._in_flight.pop(url, None)

                await self._work_queue.put(prepared)
                self._metrics.increment_queue()

            except Exception as e:
                self._metrics.record_pipeline_error()
                cycle_errors += 1
                if collector_name in collector_stats:
                    collector_stats[collector_name]['errors'] += 1
                logger.error(
                    f"Pipeline: error processing article: {e} "
                    f"(collector={collector_name}, url={url[:80]})"
                )

        elapsed = (datetime.now() - cycle_start).total_seconds()
        skipped = cycle_in_flight + cycle_db_dup + cycle_title_dup + cycle_whitelist + cycle_errors
        if cycle_collected > 0 or skipped > 0:
            logger.info(
                f"Pipeline: {cycle_collected} queued, "
                f"{skipped} skipped "
                f"(in-flight={cycle_in_flight}, db-dup={cycle_db_dup}, "
                f"title-dup={cycle_title_dup}, wl-reject={cycle_whitelist}, "
                f"err={cycle_errors}) "
                f"[{elapsed:.1f}s]"
            )
            for cname, cs in collector_stats.items():
                logger.info(
                    f"  [{cname}] received={cs['received']}, "
                    f"queued={cs['queued']}, "
                    f"db-dup={cs['db_dup']}, title-dup={cs['title_dup']}, "
                    f"in-flight={cs['in_flight']}, err={cs['errors']}"
                )
        else:
            logger.info(f"Pipeline: 0 articles from collectors ({elapsed:.1f}s)")

        await self._sync_collector_health()

    async def _sync_collector_health(self):
        """Push collector per-feed/site health into manager-facing stores."""
        if not self._collector_registry:
            return

        try:
            rss = self._collector_registry.get_collector('rss')
            if rss and hasattr(rss, 'feed_health') and rss.feed_health:
                from api.routes_feed_registry import _health_tracker
                for url, health in rss.feed_health.items():
                    status = health.get('status', 'unknown')
                    if status == 'healthy':
                        _health_tracker.update(
                            url, 'good',
                            article_count=health.get('last_count', 0),
                        )
                    elif status in ('error', 'timeout'):
                        _health_tracker.update(
                            url, 'error',
                            error=health.get('error', status),
                        )
        except Exception as e:
            logger.debug(f"RSS health sync failed: {e}")

        try:
            np4k = self._collector_registry.get_collector('np4k')
            if np4k and hasattr(np4k, 'site_health') and np4k.site_health:
                from api.routes_feed_registry import _health_tracker
                for url, health in np4k.site_health.items():
                    status = health.get('status', 'unknown')
                    if status == 'healthy':
                        _health_tracker.update(
                            url, 'good',
                            article_count=health.get('last_count', 0),
                        )
                    elif status in ('error', 'timeout'):
                        _health_tracker.update(
                            url, 'error',
                            error=health.get('error', status),
                        )
        except Exception as e:
            logger.debug(f"NP4K health sync failed: {e}")

    async def _worker(self, worker_id: int):
        """Pull prepared articles, finalize, persist, broadcast."""
        logger.debug(f"Pipeline worker {worker_id} started")

        while True:
            try:
                prepared = await self._work_queue.get()
                if prepared is None:
                    break

                url = prepared.get('url', '')

                try:
                    finalized = await self._intel.finalize_article(prepared)

                    # No scoring in Lite — default relevance_score = 0
                    finalized['relevance_score'] = 0
                    finalized['analysis_mode'] = 'SKIPPED'

                    signal = await self._intel.db.insert_final_signal(finalized)
                    if signal:
                        self._metrics.record_pipeline_persisted()
                        await manager.broadcast_new_signal(signal)
                        self._metrics.record_pipeline_broadcast()

                except Exception as e:
                    self._metrics.record_pipeline_error()
                    logger.error(
                        f"Pipeline worker {worker_id} error: {e} "
                        f"(url={url[:60]})"
                    )
                finally:
                    self._in_flight.pop(url, None)
                    self._metrics.decrement_queue()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._metrics.record_pipeline_error()
                logger.error(f"Pipeline worker {worker_id} fatal: {e}")
                await asyncio.sleep(1)

        logger.debug(f"Pipeline worker {worker_id} stopped")

    async def _recover_pending(self):
        """Process any processed=FALSE signals left from a previous crash."""
        try:
            from database.models import record_to_dict

            rows = await self._intel.db.pool.fetch(
                "SELECT * FROM intel_signals WHERE processed = FALSE "
                "ORDER BY id LIMIT 500"
            )

            if not rows:
                return

            logger.info(f"Pipeline: recovering {len(rows)} unprocessed signals from DB")

            recovered = 0
            for row in rows:
                signal = record_to_dict(row)
                sid = signal['id']

                try:
                    result = await self._intel.db.update_signal_analysis(
                        sid,
                        {
                            'location': signal.get('location', 'Unknown'),
                            'casualties': 0,
                            'risk_indicators': [],
                            'relevance_score': 0,
                            'source_confidence': 0,
                            'author_confidence': 0,
                            'analysis_mode': 'SKIPPED',
                            'source_name': signal.get('source', 'Unknown'),
                            'author_name': signal.get('author', ''),
                        },
                    )
                    if result:
                        await manager.broadcast_new_signal(result)
                    recovered += 1

                except Exception as e:
                    logger.error(f"Pipeline recovery error for signal {sid}: {e}")
                    try:
                        await self._intel.db.update_signal_analysis(
                            sid,
                            {
                                'location': 'Unknown', 'casualties': 0,
                                'risk_indicators': [],
                                'relevance_score': 0,
                                'source_confidence': 0, 'author_confidence': 0,
                                'analysis_mode': 'SKIPPED',
                                'source_name': 'Unknown', 'author_name': '',
                            },
                        )
                    except Exception as e2:
                        logger.error(f"Pipeline recovery fallback also failed for {sid}: {e2}")

            if recovered > 0:
                logger.info(f"Pipeline: recovered {recovered} signals")

        except Exception as e:
            logger.error(f"Pipeline recovery failed: {e}")
