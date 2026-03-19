"""
Observer Intelligence Platform - Feed Management API Routes
API Endpoints for feed control and regional filtering.

@updated 2026-02-09 by Mr Cat + Claude - Phase 2 cleanup, removed legacy fallbacks

Endpoints:
- POST /api/v1/feeds/groups/enable - Enable specific groups
- POST /api/v1/feeds/groups/disable - Disable specific groups
- GET /api/v1/feeds/status - Get comprehensive feed status
- POST /api/v1/feeds/mode - Switch filter mode (from_within/about)
- GET /api/v1/feeds/groups - List all available feed groups
- POST /api/v1/feeds/reset - Reset feed settings to defaults
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List

from services.source_state import get_source_state_manager
from services.collectors import get_collector_registry
from api.routes_feed_registry import feed_registry_router
from utils.logging import get_logger

logger = get_logger(__name__)

feeds_router = APIRouter(prefix="/api/v1/feeds", tags=["feeds"])

# Include registry CRUD routes (same /api/v1/feeds prefix)
feeds_router.include_router(feed_registry_router)


class GroupsRequest(BaseModel):
    groups: List[str] = Field(..., min_length=1, description="List of group names")




@feeds_router.get("/status")
async def get_status():
    """
    Get comprehensive feed status.

    Returns filter mode, enabled groups, feed counts,
    per-group statistics, and feed health overview.
    """
    try:
        state_manager = get_source_state_manager()
        collector_registry = get_collector_registry()

        state_status = state_manager.get_status()
        collector_status = collector_registry.get_status()

        rss_collector = collector_registry.get_collector('rss')
        rss_status = rss_collector.get_status() if rss_collector else {}

        total_feeds = rss_status.get('total_feeds', 0)
        total_enabled_feeds = rss_status.get('enabled_feeds', 0)
        feed_errors = rss_status.get('error_count', 0)

        group_details = {}
        for group in state_status.get('enabled_groups', []):
            group_info = (rss_collector.get_group_info(group) if rss_collector else None) or {}
            group_details[group] = {
                'feed_count': group_info.get('feed_count', 0),
                'articles_24h': group_info.get('articles_24h', 0)
            }

        health_stats = rss_status.get('health', {})

        # Use cumulative pipeline counters for accept rate
        # (received = total from all collectors, collected = accepted into queue)
        from services.metrics import metrics_collector
        pipeline_stats = metrics_collector.get_pipeline_stats()
        articles_processed = pipeline_stats.get('collected', 0)
        articles_rejected = pipeline_stats.get('received', 0) - articles_processed

        return JSONResponse({
            "enabled_groups": state_status.get('enabled_groups', []),
            "total_enabled_feeds": total_enabled_feeds,
            "total_feeds": total_feeds,
            "feed_errors": feed_errors,
            "tier1_groups": ['global', 'osint'],
            "tier2_enabled": [g for g in state_status.get('enabled_groups', [])
                             if g not in ('global', 'osint')],
            "group_details": group_details,
            "rejection_stats": pipeline_stats,
            "articles_processed": articles_processed,
            "articles_rejected": articles_rejected,
            "health_summary": {
                "healthy_feeds": health_stats.get('healthy', 0),
                "unhealthy_feeds": health_stats.get('errors', 0),
                "total_tracked": health_stats.get('total', 0)
            },
            "collector_info": {
                "architecture": "v1.5.0",
                "active_collectors": collector_status.get('active_collectors', []),
                "total_collectors": collector_status.get('total_registered', 0)
            },
            "last_updated": state_status.get('last_updated')
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@feeds_router.post("/groups/enable")
async def enable_groups(request: GroupsRequest):
    """Enable specific feed groups."""
    try:
        state_manager = get_source_state_manager()

        enabled = []
        already_enabled = []

        for group in request.groups:
            if state_manager.enable_group(group):
                enabled.append(group)
            else:
                already_enabled.append(group)

        return JSONResponse({
            "success": True,
            "enabled": enabled,
            "already_enabled": already_enabled,
            "total_enabled": list(state_manager.enabled_groups),
            "message": f"Enabled {len(enabled)} groups"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@feeds_router.post("/groups/disable")
async def disable_groups(request: GroupsRequest):
    """
    Disable specific feed groups.
    Tier 1 groups (global, osint) cannot be disabled.
    """
    try:
        state_manager = get_source_state_manager()

        disabled = []
        protected = []
        not_enabled = []

        for group in request.groups:
            if group in ('global', 'osint'):
                protected.append(group)
            elif state_manager.disable_group(group):
                disabled.append(group)
            else:
                not_enabled.append(group)

        return JSONResponse({
            "success": True,
            "disabled": disabled,
            "protected": protected,
            "not_enabled": not_enabled,
            "total_enabled": list(state_manager.enabled_groups),
            "message": f"Disabled {len(disabled)} groups" +
                      (f", {len(protected)} protected (Tier 1)" if protected else "")
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@feeds_router.get("/groups")
async def list_groups():
    """List all available feed groups with their status (from DB)."""
    try:
        from api.deps import db
        state_manager = get_source_state_manager()

        db_groups = await db.feed_sources.get_groups_summary()

        groups = []
        for g in db_groups:
            group_key = g.get('group_key', '')
            groups.append({
                'name': group_key,
                'description': g.get('group_label', ''),
                'feed_count': g.get('total', 0),
                'rss_count': g.get('rss_count', 0),
                'scraper_count': g.get('scraper_count', 0),
                'enabled_feed_count': g.get('enabled_count', 0),
                'enabled_by_default': group_key in ('global', 'osint'),
                'currently_enabled': group_key in state_manager.enabled_groups,
                'tier': 1 if group_key in ('global', 'osint') else 2
            })

        groups.sort(key=lambda x: (x['tier'], x['name']))

        return JSONResponse({
            "total_groups": len(groups),
            "enabled_count": len(state_manager.enabled_groups),
            "groups": groups
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@feeds_router.post("/reset")
async def reset_feeds():
    """Reset feed settings to defaults."""
    try:
        state_manager = get_source_state_manager()
        state_manager.reset_to_defaults()

        return JSONResponse({
            "success": True,
            "enabled_groups": list(state_manager.enabled_groups),
            "message": "Feed settings reset to defaults"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting feeds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CONTENT FILTER ENDPOINTS ====================

@feeds_router.get("/content-filter/status")
async def get_content_filter_status():
    """Get current content filter status and available filter files."""
    from services.content_filter import get_content_filter, list_filter_files
    cf = get_content_filter()
    files = list_filter_files()
    return JSONResponse({
        **cf.get_status(),
        "available_bl": files["blacklist"],
        "available_wl": files["whitelist"],
    })


@feeds_router.post("/content-filter/mode")
async def set_content_filter_mode(request: dict):
    """Change content filter mode (blacklist / whitelist / both)."""
    from services.content_filter import get_content_filter
    mode = request.get('mode', '')
    if mode not in ('blacklist', 'whitelist', 'both'):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Must be 'blacklist', 'whitelist', or 'both'"
        )
    cf = get_content_filter()
    cf.set_mode(mode)

    # Persist to .env
    from api.routes_admin import _update_env_vars
    _update_env_vars({"CONTENT_FILTER_MODE": mode})

    return JSONResponse({"success": True, **cf.get_status()})


@feeds_router.post("/content-filter/select")
async def select_content_filters(request: dict):
    """
    Switch active blacklist/whitelist filter files.

    Body: {"bl_file": "BL_default", "wl_file": "WL_geopolitical"}
    Either field can be omitted to keep the current selection.
    """
    from services.content_filter import get_content_filter
    cf = get_content_filter()
    bl = request.get('bl_file')
    wl = request.get('wl_file')

    if not bl and not wl:
        raise HTTPException(status_code=400, detail="Provide bl_file and/or wl_file")

    ok = cf.set_filters(bl_file=bl, wl_file=wl)
    if not ok:
        raise HTTPException(status_code=400, detail="Filter file not found")

    # Persist active filter selections to .env
    from api.routes_admin import _update_env_vars
    env_updates = {}
    if bl:
        env_updates["CONTENT_FILTER_BL"] = bl
    if wl:
        env_updates["CONTENT_FILTER_WL"] = wl
    if env_updates:
        _update_env_vars(env_updates)

    return JSONResponse({"success": True, **cf.get_status()})


@feeds_router.delete("/content-filter/file")
async def delete_content_filter_file(request: dict):
    """
    Delete an AI-generated filter file (WL_ollama_* only).

    Body: {"filename": "WL_ollama_iran_crisis"}
    """
    from services.content_filter import get_content_filter, list_filter_files, FILTERS_DIR

    filename = request.get('filename', '').strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    # Safety: only allow deleting AI-generated WL files
    if not filename.startswith('WL_ollama_'):
        raise HTTPException(
            status_code=403,
            detail="Only AI-generated filters (WL_ollama_*) can be deleted"
        )

    filepath = FILTERS_DIR / f"{filename}.txt"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Filter file not found: {filename}")

    # If this file is currently active, switch to the first available WL file
    cf = get_content_filter()
    status = cf.get_status()
    if status.get('active_wl') == filename:
        files = list_filter_files()
        fallback = next(
            (f for f in files['whitelist'] if f != filename),
            None,
        )
        if fallback:
            cf.set_filters(wl_file=fallback)

    filepath.unlink()
    logger.info(f"Deleted AI-generated filter: {filename}")

    files = list_filter_files()
    return JSONResponse({
        "success": True,
        "deleted": filename,
        **cf.get_status(),
        "available_bl": files["blacklist"],
        "available_wl": files["whitelist"],
    })
