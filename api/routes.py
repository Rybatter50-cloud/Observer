"""
Observer Intelligence Platform - API Routes
Defines all HTTP and WebSocket endpoints
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import List
from pathlib import Path

import time

from config import config
from api.deps import db, intel_service
from api.security import verify_ws_api_key
from services.websocket import manager
from utils.logging import get_logger
from utils.sanitizers import validate_time_window

# Import feed routes (Phase 4)
from api.routes_feeds import feeds_router

logger = get_logger(__name__)

# Initialize router
core_router = APIRouter()

# Include feed management routes (Phase 4)
core_router.include_router(feeds_router)

# Setup templates
BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Cache-bust token: changes on each server restart so browsers fetch fresh static assets
CACHE_BUST = str(int(time.time()))



@core_router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the dev console (minimal debug/config interface)"""
    try:
        resp = templates.TemplateResponse("dev.html", {
            "request": request,
            "v": CACHE_BUST,
        })
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    except Exception as e:
        logger.error(f"Error serving dev console: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@core_router.get("/client", response_class=HTMLResponse)
async def client_view(request: Request):
    """Serve the read-only client interface"""
    try:
        resp = templates.TemplateResponse("client.html", {"request": request, "v": CACHE_BUST})
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    except Exception as e:
        logger.error(f"Error serving client view: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@core_router.get("/console/obs", response_class=HTMLResponse)
async def obs_overlay_view(request: Request):
    """Serve the OBS Browser Source overlay (analyst panel only, transparent bg)"""
    try:
        resp = templates.TemplateResponse("obs.html", {"request": request, "v": CACHE_BUST})
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    except Exception as e:
        logger.error(f"Error serving OBS overlay: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@core_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    # API key auth (if enabled)
    if not verify_ws_api_key(websocket):
        await websocket.close(code=4403, reason="Invalid or missing API key")
        return

    # Extract client IP for per-IP rate limiting
    client_ip = "unknown"
    if websocket.client:
        client_ip = websocket.client.host
    # Respect X-Forwarded-For behind a reverse proxy (first hop only)
    forwarded = websocket.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    accepted = await manager.connect(websocket, client_ip=client_ip)
    if not accepted:
        return

    try:
        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break

    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)


@core_router.get("/api/v1/intelligence")
async def get_intelligence(
    time_window: str = "all",
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=500),
    source_groups: str = Query(default="", max_length=2000),
    content_search: str = Query(default="", max_length=5000),
    min_score: int = Query(default=0, ge=0, le=100),
    risk_indicators: str = Query(default="", max_length=200),
    translated_only: bool = Query(default=False),
    screening_only: bool = Query(default=False),
):
    """
    Get intelligence signals with optional time filtering, server-side
    search/filter, and pagination.

    Args:
        time_window: Time filter ('4h', '24h', '72h', '7d', or 'all')
        limit: Maximum number of signals to return (1–5000, default 200)
        offset: Number of signals to skip for pagination (default 0)
        search: Text search across title, description, location, source, author
        source_groups: Comma-separated source_group names for region filtering
        min_score: Minimum relevance_score (0 = no filter)
        risk_indicators: Comma-separated risk indicator codes (e.g. 'T,K,U')
        translated_only: Only return translated signals
        screening_only: Only return signals with screening hits

    Returns:
        JSON with intelligence data, pagination metadata, logs, and status
    """
    try:
        # Validate and sanitize input
        time_window = validate_time_window(time_window)

        # Parse comma-separated filter lists
        groups_list = [g.strip() for g in source_groups.split(",") if g.strip()] if source_groups else None
        content_list = [c.strip() for c in content_search.split(",") if c.strip()] if content_search else None
        risk_list = [r.strip().upper() for r in risk_indicators.split(",") if r.strip()] if risk_indicators else None

        # Build shared filter kwargs
        filter_kwargs = dict(
            search=search or None,
            source_groups=groups_list,
            content_search=content_list,
            min_score=min_score if min_score > 0 else None,
            risk_indicators=risk_list,
            translated_only=translated_only,
            screening_only=screening_only,
        )

        # Fetch intelligence signals with server-side filtering
        signals = await db.get_signals(
            time_window, limit=limit, offset=offset, **filter_kwargs
        )

        # Total matching count (ignores LIMIT/OFFSET) for accurate feed display
        total_count = await db.count_signals(time_window, **filter_kwargs)

        # Get system logs from logging handler
        import logging
        system_logs = []
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'get_logs'):
                system_logs = handler.get_logs()
                break

        # Use cumulative pipeline counters for accept rate
        articles_processed = 0
        articles_rejected = 0
        try:
            from services.metrics import metrics_collector
            pipeline_stats = metrics_collector.get_pipeline_stats()
            articles_processed = pipeline_stats.get('collected', 0)
            articles_rejected = pipeline_stats.get('received', 0) - articles_processed
        except Exception as e:
            logger.debug(f"Could not get pipeline stats: {e}")

        return JSONResponse({
            "intel": signals,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "count": len(signals),
                "total_count": total_count,
            },
            "logs": system_logs,
            "connection_count": manager.get_connection_count(),
            "articles_processed": articles_processed,
            "articles_rejected": articles_rejected,
        })

    except Exception as e:
        logger.error(f"Error fetching intelligence: {e}")
        raise HTTPException(status_code=500, detail="Error fetching intelligence data")


class ScoreIndicatorUpdate(BaseModel):
    """Request body for analyst score/indicator edits."""
    relevance_score: int = Field(..., ge=0, le=100)
    risk_indicators: List[str] = Field(...)


@core_router.patch("/api/v1/intelligence/{signal_id}")
async def update_signal_score(signal_id: int, body: ScoreIndicatorUpdate):
    """
    Update the relevance_score and risk_indicators for a signal.
    Used by analysts to hand-curate scoring from the feed interface.
    Sets analysis_mode to MANUAL to distinguish training data.
    Broadcasts the update to all connected WebSocket clients.
    """
    try:
        # Validate indicators (accept any uppercase letter codes)
        cleaned = [i.strip().upper() for i in body.risk_indicators if i.strip()]

        # Update in database
        updated = await db.signals.update_score_indicators(
            signal_id, body.relevance_score, cleaned
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Broadcast to all WS clients so feeds refresh in real-time
        await manager.broadcast({
            "type": "signal_update",
            "id": signal_id,
            "data": updated,
        })

        logger.info(
            f"Analyst edit: signal {signal_id} → "
            f"score={body.relevance_score}, indicators={cleaned}"
        )

        return JSONResponse({"success": True, "signal": updated})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating signal {signal_id}: {e}")
        raise HTTPException(status_code=500, detail="Error updating signal")


@core_router.get("/api/v1/intelligence/blocked-domains")
async def get_blocked_domains():
    """
    Return all domains flagged as having paywalls or subscriber walls.
    The client uses this to gray out the Fetch Full Text button.
    """
    try:
        blocked = await db.source_flags.get_blocked_domains()
        return JSONResponse({"domains": blocked})
    except Exception as e:
        logger.error(f"Error fetching blocked domains: {e}")
        return JSONResponse({"domains": {}})




@core_router.post("/api/v1/intelligence/{signal_id}/fetch-fulltext")
async def fetch_signal_fulltext(signal_id: int):
    """
    Fetch full article text via trafilatura, optionally translate,
    and store in the signal's full_text field.

    Detects paywalls / subscriber walls via Schema.org metadata and
    flags the domain persistently so future requests are blocked.
    """
    try:
        # Look up the signal to get its URL
        signal = await db.get_signal_by_id(signal_id)
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")

        url = signal.get('url', '')
        if not url:
            return JSONResponse({"success": False, "error": "Signal has no URL"})

        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()

        # Check if this domain is already flagged
        block_type = await db.source_flags.is_domain_blocked(domain)
        if block_type:
            label = 'paywall' if block_type == 'paywall' else 'subscriber wall'
            return JSONResponse({
                "success": False,
                "error": f"Source blocked: {label} detected",
                "block_type": block_type,
                "domain": domain,
            })

        # Import trafilatura
        try:
            import trafilatura
        except ImportError:
            return JSONResponse({
                "success": False,
                "error": "trafilatura not installed"
            })

        import asyncio

        # Fetch and extract in a thread (trafilatura is synchronous)
        loop = asyncio.get_running_loop()
        downloaded = await loop.run_in_executor(
            None, lambda: trafilatura.fetch_url(url)
        )
        if not downloaded:
            return JSONResponse({
                "success": False,
                "error": "Could not download article"
            })

        # Check Schema.org isAccessibleForFree metadata for subscriber walls
        paywall_detected = _detect_paywall_schema(downloaded)
        if paywall_detected:
            source_name = signal.get('source', domain)
            await db.source_flags.flag_domain(
                domain, 'subscriber_wall', source_name
            )
            return JSONResponse({
                "success": False,
                "error": "Source blocked: subscriber wall detected",
                "block_type": "subscriber_wall",
                "domain": domain,
            })

        # Extract with favor_precision for cleaner text (less junk)
        extracted = await loop.run_in_executor(
            None,
            lambda: trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                include_links=False,
                include_images=False,
                favor_precision=True,
                deduplicate=True,
            ),
        )
        if not extracted:
            return JSONResponse({
                "success": False,
                "error": "Could not extract text from article"
            })

        # Post-process: clean up junk lines
        full_text = _clean_extracted_text(extracted)

        if not full_text or len(full_text.strip()) < 50:
            return JSONResponse({
                "success": False,
                "error": "Extracted text too short or empty after cleanup"
            })

        # Detect language of the fetched text and translate if non-English
        try:
            from services.translation import get_translation_service
            translator = get_translation_service()
            if translator and translator.enabled and translator.needs_translation(full_text):
                source_lang = signal.get('source_language') or translator.detect_language(full_text)
                full_text = await translator.translate_long_text(
                    full_text, source_lang=source_lang
                )
        except Exception as te:
            logger.debug(f"Full-text translation skipped: {te}")

        # Store in DB
        updated = await db.signals.update_full_text(signal_id, full_text)
        if not updated:
            return JSONResponse({
                "success": False,
                "error": "Failed to store text in database"
            })

        return JSONResponse({
            "success": True,
            "full_text": full_text,
            "char_count": len(full_text),
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fetch full-text failed for signal {signal_id}: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)[:200]
        })


def _detect_paywall_schema(html: str) -> bool:
    """
    Check HTML for Schema.org paywall / subscriber-wall indicators.

    Looks for isAccessibleForFree: False in JSON-LD and meta tags.
    Returns True if a paywall/subscriber wall is detected.
    """
    import re
    import json

    html_lower = html.lower()

    # Check JSON-LD script blocks for isAccessibleForFree
    try:
        for match in re.finditer(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            try:
                ld = json.loads(match.group(1))
                # Handle both single objects and arrays
                items = ld if isinstance(ld, list) else [ld]
                for item in items:
                    if isinstance(item, dict):
                        accessible = item.get('isAccessibleForFree')
                        if accessible is not None:
                            # Schema.org uses "False" (string) or false (bool)
                            if str(accessible).lower() in ('false', '0', 'no'):
                                return True
                        # Also check nested @graph
                        for node in item.get('@graph', []):
                            if isinstance(node, dict):
                                accessible = node.get('isAccessibleForFree')
                                if accessible is not None:
                                    if str(accessible).lower() in ('false', '0', 'no'):
                                        return True
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception:
        pass

    # Check meta tags: <meta name="accessible_for_free" content="false">
    if re.search(
        r'<meta[^>]*name=["\']accessible.for.free["\'][^>]*content=["\']false["\']',
        html_lower,
    ):
        return True

    # Check for common paywall markers in meta tags
    if re.search(
        r'<meta[^>]*name=["\']paywall["\'][^>]*content=["\']true["\']',
        html_lower,
    ):
        return True

    return False


def _clean_extracted_text(text: str) -> str:
    """
    Post-process trafilatura output to remove common junk content:
    - Navigation remnants and link lists
    - "Related articles" / "Read more" sections
    - Cookie/newsletter/subscription notices
    - Excessive whitespace and short junk lines
    """
    import re

    lines = text.split('\n')
    cleaned = []

    # Patterns for junk lines to skip
    junk_patterns = [
        # Navigation / link-list remnants
        re.compile(r'^(home|menu|search|login|sign.?in|sign.?up|subscribe|register|log.?in)\s*$', re.I),
        # Social sharing
        re.compile(r'^(share|tweet|pin|email|print|comment|like)\s*$', re.I),
        # Related content headers
        re.compile(r'^(related\s+(articles?|stories|posts|news)|read\s+more|more\s+(from|stories|news)|also\s+read|trending|popular|recommended)\s*:?\s*$', re.I),
        # Cookie / subscription nags
        re.compile(r'(cookie|gdpr|privacy.?policy|terms.?of.?(use|service)|sign.?up.?for.?our|subscribe.?to.?our|newsletter|manage.?your.?subscription|already.?a.?subscriber)', re.I),
        # Boilerplate footers
        re.compile(r'^(all\s+rights\s+reserved|copyright\s+\d{4}|©\s*\d{4})', re.I),
        # Bare URLs or email addresses
        re.compile(r'^https?://\S+\s*$'),
        re.compile(r'^\S+@\S+\.\S+\s*$'),
        # "Click here" type prompts
        re.compile(r'(click\s+here|tap\s+here|download\s+our\s+app)', re.I),
    ]

    for line in lines:
        stripped = line.strip()

        # Skip empty lines (we'll re-add paragraph breaks)
        if not stripped:
            if cleaned and cleaned[-1] != '':
                cleaned.append('')
            continue

        # Skip very short lines (likely nav items) unless they end with punctuation
        if len(stripped) < 15 and not re.search(r'[.!?:;"\']$', stripped):
            continue

        # Skip lines matching junk patterns
        if any(p.search(stripped) for p in junk_patterns):
            continue

        cleaned.append(stripped)

    # Remove trailing empty lines
    while cleaned and cleaned[-1] == '':
        cleaned.pop()

    # Remove leading empty lines
    while cleaned and cleaned[0] == '':
        cleaned.pop(0)

    return '\n'.join(cleaned)


@core_router.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connectivity
        signals = await db.get_signals(limit=1)

        # Get feed status if available
        feed_status = {}
        try:
            from services.source_state import get_source_state_manager
            state_manager = get_source_state_manager()
            feed_status = {
                "enabled_groups": len(state_manager.enabled_groups),
            }
        except Exception as e:
            logger.debug(f"Could not get source state: {e}")

        return JSONResponse({
            "status": "healthy",
            "database": "connected",
            "websocket_clients": manager.get_connection_count(),
            "config": {
                "feed_collection": config.FEED_COLLECTION_ENABLED
            },
            "feeds": feed_status
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )
