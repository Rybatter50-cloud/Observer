"""
RYBAT Lite - Metrics API Routes
API endpoints for system telemetry and monitoring

Endpoints:
- GET /api/v1/metrics/ai - System metrics (queue, translator, collectors)
"""

from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from utils.logging import get_logger

logger = get_logger(__name__)

# Initialize router
metrics_router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


# ==================== COLLECTOR STATUS HELPERS ====================

def get_collector_status() -> dict:
    """
    Get status for collectors (RSS, NP4K).
    Used by dashboard collector tiles.
    """
    collectors = {
        "rss": {"available": False, "healthy": 0, "errors": 0, "articles": 0},
        "np4k": {"available": False, "healthy": 0, "errors": 0, "articles": 0},
    }

    # ==================== RSS COLLECTOR ====================
    try:
        from services.collectors import get_collector_registry
        registry = get_collector_registry()
        rss_collector = registry.get_collector('rss')

        if rss_collector:
            status = rss_collector.get_status()
            collectors["rss"] = {
                "available": True,
                "healthy": status.get('healthy_feeds', 0),
                "errors": status.get('error_count', 0),
                "articles": status.get('last_article_count', 0)
            }
    except ImportError:
        try:
            from services.feed_manager import get_feed_manager
            fm = get_feed_manager()
            if fm:
                status = fm.get_status()
                collectors["rss"] = {
                    "available": True,
                    "healthy": status.get('total_enabled_feeds', 0),
                    "errors": 0,
                    "articles": 0
                }
        except Exception as e:
            logger.debug(f"Could not get RSS status from legacy: {e}")
    except Exception as e:
        logger.debug(f"Could not get RSS collector status: {e}")

    # ==================== NP4K (SCRAPER) COLLECTOR ====================
    try:
        from services.collectors import get_collector_registry
        registry = get_collector_registry()
        np4k_collector = registry.get_collector('np4k')

        if np4k_collector:
            status = np4k_collector.get_status()
            collectors["np4k"] = {
                "available": status.get('available', False),
                "healthy": status.get('healthy_sites', 0),
                "errors": status.get('error_sites', 0),
                "articles": status.get('last_article_count', 0)
            }
        else:
            try:
                import trafilatura
                collectors["np4k"]["available"] = True
            except ImportError:
                pass
    except Exception as e:
        logger.debug(f"Could not get NP4K status: {e}")

    return collectors


async def get_scraper_sites_from_registry() -> list:
    """Load scraper sites from PostgreSQL (delegates to shared helper)."""
    try:
        from api.routes_feed_registry import get_all_scraper_sites
        return await get_all_scraper_sites()
    except Exception as e:
        logger.debug(f"Error loading scraper sites from DB: {e}")
        return []


@metrics_router.get("/ai")
async def get_ai_metrics():
    """
    Get system metrics for dashboard telemetry.

    Returns:
        JSON with queue_size, translator stats, collector status.
    """
    try:
        # ==================== METRICS COLLECTOR ====================
        translator_calls_per_min = 0
        translator_cache_hits = 0
        queue_size = 0

        try:
            from services.metrics import get_metrics_collector
            collector = get_metrics_collector()
            metrics = collector.get_metrics()

            translator_calls_per_min = metrics.get('translator_calls_per_min', 0)
            translator_cache_hits = metrics.get('total_cache_hits', 0)
            queue_size = metrics.get('queue_size', 0)
        except Exception as e:
            logger.debug(f"Could not get metrics from collector: {e}")

        # ==================== QUEUE SIZE (LIVE) ====================
        try:
            from api.deps import db as _db
            if _db and _db._db:
                db_queue_size = await _db.pool.fetchval(
                    "SELECT COUNT(*) FROM intel_signals WHERE processed = FALSE"
                )
                queue_size = max(queue_size, db_queue_size or 0)
        except Exception as e:
            logger.debug(f"Could not get queue size from database: {e}")

        # ==================== COLLECTOR STATUS ====================
        collectors = get_collector_status()

        # ==================== SCRAPER METRICS ====================
        scraper_sites = await get_scraper_sites_from_registry()
        scraper_total = len(scraper_sites)
        scraper_healthy = sum(1 for s in scraper_sites if s.get('status') != 'error')
        scraper_errors = sum(1 for s in scraper_sites if s.get('status') == 'error')

        return JSONResponse({
            "queue_size": queue_size,
            "analyst_calls_per_min": 0,
            "translator_calls_per_min": translator_calls_per_min,
            "translator_cache_hits": translator_cache_hits,
            "scraper_total": scraper_total,
            "scraper_healthy": scraper_healthy,
            "scraper_errors": scraper_errors,
            "collectors": collectors,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return JSONResponse({
            "queue_size": 0,
            "analyst_calls_per_min": 0,
            "translator_calls_per_min": 0,
            "translator_cache_hits": 0,
            "scraper_total": 0,
            "scraper_healthy": 0,
            "scraper_errors": 0,
            "collectors": {
                "rss": {"available": False, "healthy": 0, "errors": 0, "articles": 0},
                "np4k": {"available": False, "healthy": 0, "errors": 0, "articles": 0},
            },
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })
