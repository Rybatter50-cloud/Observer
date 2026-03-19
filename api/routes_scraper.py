"""
Observer Intelligence Platform - News Scraper API Routes
API endpoints for the trafilatura scraper manager

===============================================================================
CHANGELOG:
-------------------------------------------------------------------------------
2026-02-04 | Mr Cat + Claude | FIX - Correct BoondocksScraper method calls
    - Fixed: scrape_site() → collect_from_site() (method didn't exist)
    - Fixed: test_site() → collect_from_site() with limit (method didn't exist)
    - All three collection endpoints now use correct API
-------------------------------------------------------------------------------
2026-02-02 | Mr Cat + Claude | MAJOR REWRITE - Unified with Feed Registry
    - Scraper sites now stored in PostgreSQL (feed_sources table)
    - Each group has optional scraper_sites[] array
    - Sites follow group enable/disable from Feed Manager
    - Removed separate scraper_sites.json dependency
    - New endpoints for registry-based operations
===============================================================================

Endpoints:
- GET  /scraper                       - Scraper manager page
- GET  /api/v1/scraper/sites          - List all scraper sites (all groups)
- GET  /api/v1/scraper/stats          - Get collection statistics
- POST /api/v1/scraper/test           - Test a site URL
- POST /api/v1/scraper/collect-all    - Run full collection
- POST /api/v1/scraper/collect-site   - Collect from specific site
- POST /api/v1/scraper/save-registry  - Save registry changes from UI
- POST /api/v1/scraper/deep-dive      - Trigger deep dive analysis (premium)
"""

from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.routes_feed_registry import (
    save_registry, sync_registry_to_db,
    get_all_scraper_sites, get_enabled_scraper_sites,
)
from utils.logging import get_logger

logger = get_logger(__name__)

# Router
scraper_router = APIRouter(tags=["scraper"])

# Check if trafilatura is available
HAS_TRAFILATURA = False
try:
    from services.news_scraper import BoondocksScraper
    HAS_TRAFILATURA = True
except ImportError:
    logger.warning("trafilatura not installed - scraper collection disabled")
    logger.warning("Install with: pip install trafilatura[all]")


# ==================== MODELS ====================

class TestSiteRequest(BaseModel):
    url: str


class CollectSiteRequest(BaseModel):
    group: str
    index: int


class SaveRegistryRequest(BaseModel):
    registry: Dict[str, Any]


class ToggleFeedSiteRequest(BaseModel):
    group: str
    url: str
    site_type: str  # "rss" or "scraper"


class DeleteFeedSiteRequest(BaseModel):
    group: str
    url: str
    site_type: str  # "rss" or "scraper"


# ==================== STATS ====================
# Scraper stats now live in MetricsCollector (thread-safe, centralized)


# ==================== API ROUTES ====================

@scraper_router.get("/api/v1/feed-registry/groups")
async def get_registry_groups():
    """
    Get all groups from feed registry (PostgreSQL-backed).
    Used by scraper manager UI.
    """
    from api.deps import db
    groups = await db.feed_sources.get_groups_summary()
    return JSONResponse({
        "groups": groups,
        "total_groups": len(groups),
    })


@scraper_router.get("/api/v1/scraper/sites")
async def list_all_sites():
    """List all scraper sites from all groups"""
    sites = await get_all_scraper_sites()
    enabled_sites = [s for s in sites if s.get('enabled', True)]
    error_sites = [s for s in sites if s.get('status') == 'error']

    return JSONResponse({
        "sites": sites,
        "stats": {
            "total": len(sites),
            "enabled": len(enabled_sites),
            "errors": len(error_sites),
            "articles_today": sum(s.get('article_count', 0) for s in sites)
        }
    })


@scraper_router.get("/api/v1/scraper/stats")
async def get_stats():
    """Get scraper statistics"""
    sites = await get_all_scraper_sites()
    
    from services.metrics import metrics_collector
    scraper_stats = metrics_collector.get_scraper_stats()

    return JSONResponse({
        **scraper_stats,
        "total_sites": len(sites),
        "enabled_sites": len([s for s in sites if s.get('enabled', True)]),
        "healthy_sites": len([s for s in sites if s.get('status') == 'healthy']),
        "error_sites": len([s for s in sites if s.get('status') == 'error'])
    })


@scraper_router.post("/api/v1/scraper/save-registry")
async def save_registry_changes(request: SaveRegistryRequest):
    """
    Save registry changes from the UI.
    Used when adding/editing/deleting scraper sites.
    """
    if save_registry(request.registry):
        await sync_registry_to_db(request.registry)
        return JSONResponse({"success": True, "message": "Registry saved"})
    else:
        raise HTTPException(status_code=500, detail="Failed to save registry")


@scraper_router.post("/api/v1/scraper/test")
async def test_site(request: TestSiteRequest):
    """
    Test a scraper site URL
    
    @fixed 2026-02-04 by Mr Cat + Claude
    - Was calling non-existent scraper.test_site()
    - Now uses collect_from_site() with small limit for testing
    """
    if not HAS_TRAFILATURA:
        return JSONResponse({
            "success": False,
            "error": "trafilatura not installed"
        }, status_code=503)

    try:
        scraper = BoondocksScraper()

        # =====================================================================
        # FIX: Use collect_from_site with small limit instead of test_site
        # @fixed 2026-02-04 by Mr Cat + Claude
        # BoondocksScraper has collect_from_site(), not test_site()
        # =====================================================================
        articles = await scraper.collect_from_site(
            site_url=request.url,
            source_name="Test",
            max_articles=3  # Small limit for testing
        )
        
        return JSONResponse({
            "success": len(articles) > 0,
            "article_count": len(articles),
            "sample_titles": [a.get('title', '')[:80] for a in articles[:5]],
            "error": None if articles else "No articles found"
        })
    except Exception as e:
        logger.error(f"Site test error: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@scraper_router.post("/api/v1/scraper/collect-site")
async def collect_from_site_endpoint(request: CollectSiteRequest):
    """
    Collect articles from a specific site
    
    @fixed 2026-02-04 by Mr Cat + Claude
    - Was calling non-existent scraper.scrape_site()
    - Now uses collect_from_site() with correct parameters
    """
    if not HAS_TRAFILATURA:
        return JSONResponse({
            "success": False,
            "error": "trafilatura not installed"
        }, status_code=503)

    from api.deps import db
    group_sites = await db.feed_sources.get_by_group(request.group)
    scraper_sites = [s for s in group_sites if s.get('feed_type') == 'scraper']

    if not scraper_sites:
        raise HTTPException(status_code=404, detail=f"Group not found or has no scraper sites: {request.group}")

    if request.index < 0 or request.index >= len(scraper_sites):
        raise HTTPException(status_code=400, detail=f"Site index out of range: {request.index}")

    site = scraper_sites[request.index]

    try:
        scraper = BoondocksScraper()
        articles = await scraper.collect_from_site(
            site_url=site['url'],
            source_name=site.get('name', site['url']),
            max_articles=10
        )

        # Update probe status in DB
        if site.get('id'):
            await db.feed_sources.update_probe_status(site['id'], 'good')

        return JSONResponse({
            "success": True,
            "article_count": len(articles),
            "articles": articles[:5]  # Return first 5 for preview
        })
    except Exception as e:
        logger.error(f"Collection error for {site.get('name')}: {e}")

        if site.get('id'):
            await db.feed_sources.update_probe_status(site['id'], 'error')

        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@scraper_router.post("/api/v1/scraper/collect-all")
async def collect_all():
    """
    Run collection from all enabled scraper sites
    
    @fixed 2026-02-04 by Mr Cat + Claude
    - Was calling non-existent scraper.scrape_site()
    - Now uses collect_from_site() with correct parameters
    """
    if not HAS_TRAFILATURA:
        return JSONResponse({
            "success": False,
            "error": "trafilatura not installed"
        }, status_code=503)

    sites = await get_enabled_scraper_sites()
    
    if not sites:
        return JSONResponse({
            "success": True,
            "total_articles": 0,
            "message": "No enabled scraper sites in enabled groups"
        })
    
    from api.deps import db
    scraper = BoondocksScraper()
    total_articles = 0
    errors = []

    for site in sites:
        try:
            articles = await scraper.collect_from_site(
                site_url=site['url'],
                source_name=site.get('name', site['url']),
                max_articles=10
            )
            total_articles += len(articles)
            logger.info(f"Collected {len(articles)} articles from {site.get('name')}")

        except Exception as e:
            errors.append(f"{site.get('name')}: {e}")
            logger.error(f"Collection error for {site.get('name')}: {e}")

    # Update stats (thread-safe via MetricsCollector)
    from services.metrics import metrics_collector
    metrics_collector.record_scraper_collection(total_articles)
    
    return JSONResponse({
        "success": True,
        "total_articles": total_articles,
        "sites_processed": len(sites),
        "errors": errors if errors else None
    })


# ==================== FEED SITES (Unified RSS + Scraper) ====================

@scraper_router.get("/api/v1/feed-sites")
async def list_all_feed_sites():
    """List all feed sites (RSS + scraper) from PostgreSQL."""
    from api.deps import db
    sources = await db.feed_sources.get_all()
    stats = await db.feed_sources.get_stats()

    # Map to the shape the frontend expects
    sites = []
    for s in sources:
        sites.append({
            'id': s.get('id'),
            'name': s.get('name', ''),
            'url': s.get('url', ''),
            'group': s.get('group_key', ''),
            'type': s.get('feed_type', 'rss'),
            'enabled': s.get('enabled', True),
            'language': s.get('language', ''),
            'country': s.get('country', ''),
        })

    return JSONResponse({
        "sites": sites,
        "stats": {
            "total": stats.get('total', len(sites)),
            "rss": stats.get('rss_count', 0),
            "scraper": stats.get('scraper_count', 0),
            "enabled": stats.get('enabled_count', 0),
        }
    })


@scraper_router.post("/api/v1/feed-sites/toggle")
async def toggle_feed_site(request: ToggleFeedSiteRequest):
    """Toggle a feed site on/off by URL + type (PostgreSQL)."""
    from api.deps import db
    new_state = await db.feed_sources.toggle_by_url(request.url, request.site_type)
    if new_state is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return JSONResponse({"success": True, "enabled": new_state})


@scraper_router.post("/api/v1/feed-sites/delete")
async def delete_feed_site(request: DeleteFeedSiteRequest):
    """Delete a feed site from PostgreSQL by URL + type."""
    from api.deps import db
    deleted = await db.feed_sources.delete_by_url(request.url, request.site_type)
    if not deleted:
        raise HTTPException(status_code=404, detail="Site not found")
    return JSONResponse({"success": True})


# ==================== LEGACY COMPATIBILITY ====================
# These endpoints maintain backward compatibility with old code

@scraper_router.post("/api/v1/scraper/sites/{site_id}/toggle")
async def toggle_site_legacy(site_id: int):
    """Toggle site enabled state by ID (PostgreSQL-backed)."""
    from api.deps import db
    new_state = await db.feed_sources.toggle(site_id)
    if new_state is None:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")
    return JSONResponse({
        "success": True,
        "enabled": new_state
    })


@scraper_router.delete("/api/v1/scraper/sites/{site_id}")
async def delete_site_legacy(site_id: int):
    """Delete site by ID (PostgreSQL-backed)."""
    from api.deps import db
    deleted = await db.feed_sources.delete(site_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")
    return JSONResponse({"success": True})
