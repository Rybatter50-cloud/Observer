"""
RYBAT Lite - Pipeline Debug & Diagnostics API
Provides runtime inspection of the article flow pipeline.

Endpoint: GET /api/v1/debug/pipeline
Returns full pipeline state: DB counts, pool stats,
analysis worker stats, collector status, and recent signals.

@created 2026-02-07 by Mr Cat + Claude - Article flow diagnostics
@updated 2026-02-08 by Mr Cat + Claude - PostgreSQL migration (removed DTC)
"""

from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

debug_router = APIRouter(tags=["debug"])


@debug_router.get("/api/v1/debug/pipeline")
async def pipeline_diagnostics():
    """
    Full pipeline state inspection for debugging article flow.

    Returns each pipeline stage's health:
      1. COLLECTION  - collector registry status
      2. PREPARATION - dedup / translation stats
      3. DATABASE    - signal counts by state
      4. ANALYSIS    - worker stats
      5. PROCESSED   - signals with processed=1
      6. BROADCAST   - WebSocket client count
      7. DASHBOARD   - API fetch readiness
    """
    from api.deps import db, intel_service
    from services.websocket import manager
    from services.metrics import metrics_collector
    from database.models import record_to_dict

    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "stages": {},
        "issues_detected": [],
    }

    # -- 0. PIPELINE STATUS (single-pass architecture) --
    try:
        from main import app
        pipeline = getattr(app.state, 'pipeline', None)
        if pipeline:
            diagnostics["stages"]["pipeline"] = pipeline.get_status()
        else:
            diagnostics["stages"]["pipeline"] = {"status": "not_configured"}
    except Exception as e:
        diagnostics["stages"]["pipeline"] = {"error": str(e)}

    # -- 1. DATABASE STATE --
    try:
        total = await db.pool.fetchval("SELECT COUNT(*) FROM intel_signals")
        queued = await db.pool.fetchval(
            "SELECT COUNT(*) FROM intel_signals WHERE processed = FALSE"
        )
        processed = await db.pool.fetchval(
            "SELECT COUNT(*) FROM intel_signals WHERE processed = TRUE"
        )
        by_mode_rows = await db.pool.fetch(
            "SELECT analysis_mode, COUNT(*) as cnt FROM intel_signals GROUP BY analysis_mode"
        )
        by_mode = {row['analysis_mode']: row['cnt'] for row in by_mode_rows}

        recent_rows = await db.pool.fetch(
            """SELECT id, title, processed, analysis_mode, collector,
                      source, created_at
               FROM intel_signals ORDER BY created_at DESC LIMIT 10"""
        )
        recent = [
            {
                "id": r['id'],
                "title": r['title'][:80] if r['title'] else None,
                "processed": r['processed'],
                "analysis_mode": r['analysis_mode'],
                "collector": r['collector'],
                "source": r['source'],
                "created_at": r['created_at'].isoformat() if r['created_at'] else None,
            }
            for r in recent_rows
        ]

        oldest_queued = None
        if queued > 0:
            row = await db.pool.fetchrow(
                """SELECT id, title, created_at FROM intel_signals
                   WHERE processed = FALSE ORDER BY created_at ASC LIMIT 1"""
            )
            if row:
                oldest_queued = {
                    "id": row['id'],
                    "title": row['title'][:80] if row['title'] else None,
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                }

        diagnostics["stages"]["database"] = {
            "total_signals": total,
            "queued_for_analysis": queued,
            "processed_complete": processed,
            "by_analysis_mode": by_mode,
            "recent_signals": recent,
            "oldest_unprocessed": oldest_queued,
            "pool_size": db.pool.get_size(),
            "pool_free": db.pool.get_idle_size(),
        }

        # Issue detection
        if total == 0:
            diagnostics["issues_detected"].append(
                "DB_EMPTY: No signals in database. "
                "Articles may not be reaching the ingest path."
            )
        if queued > 50:
            diagnostics["issues_detected"].append(
                f"ANALYSIS_BACKLOG: {queued} signals waiting for analysis. "
                "Analysis worker may be stalled or AI services unavailable."
            )
        if total > 0 and processed == 0:
            diagnostics["issues_detected"].append(
                "NO_PROCESSED: Signals exist but none are processed. "
                "Analysis worker may not be running or is failing."
            )

    except Exception as e:
        diagnostics["stages"]["database"] = {"error": str(e)}
        diagnostics["issues_detected"].append(f"DB_ERROR: {e}")

    # -- 2. PIPELINE WORKERS --
    try:
        diagnostics["stages"]["pipeline_workers"] = {
            "mode": "collect-only (no AI scoring)",
            "note": "Scoring fields populated offline (not at collection time)",
        }
    except Exception as e:
        diagnostics["stages"]["pipeline_workers"] = {"error": str(e)}

    # -- 3. COLLECTOR REGISTRY --
    try:
        from main import app
        pipeline = getattr(app.state, 'pipeline', None)
        registry = pipeline.collector_registry if pipeline else None
        if registry:
            reg_status = registry.get_status()
            diagnostics["stages"]["collectors"] = reg_status

            if not reg_status.get("enabled_collectors"):
                diagnostics["issues_detected"].append(
                    "NO_COLLECTORS: No collectors are enabled. "
                    "Articles cannot be collected."
                )
        else:
            diagnostics["stages"]["collectors"] = {
                "status": "not_initialized",
                "note": "Collector registry has not been initialized yet",
            }
            diagnostics["issues_detected"].append(
                "COLLECTORS_NOT_INIT: Collector registry not initialized. "
                "Feed collection may have failed to start."
            )
    except Exception as e:
        diagnostics["stages"]["collectors"] = {"error": str(e)}

    # -- 4. METRICS --
    try:
        metrics = metrics_collector.get_metrics()
        diagnostics["stages"]["metrics"] = metrics
    except Exception as e:
        diagnostics["stages"]["metrics"] = {"error": str(e)}

    # -- 5. WEBSOCKET / BROADCAST --
    try:
        ws_count = manager.get_connection_count()
        diagnostics["stages"]["websocket"] = {
            "active_connections": ws_count,
        }
        if ws_count == 0:
            diagnostics["issues_detected"].append(
                "NO_WS_CLIENTS: No WebSocket clients connected. "
                "Real-time broadcasts will have no recipients "
                "(dashboard may still fetch via polling)."
            )
    except Exception as e:
        diagnostics["stages"]["websocket"] = {"error": str(e)}

    # -- 6. CONFIGURATION --
    diagnostics["stages"]["config"] = {
        "feed_collection_enabled": config.FEED_COLLECTION_ENABLED,
        "feed_check_interval": config.FEED_CHECK_INTERVAL,
        "translator_mode": config.AI_TRANSLATOR_MODE,
    }

    # -- SUMMARY --
    diagnostics["pipeline_health"] = (
        "OK" if not diagnostics["issues_detected"] else "ISSUES_DETECTED"
    )
    diagnostics["issue_count"] = len(diagnostics["issues_detected"])

    return JSONResponse(diagnostics)
