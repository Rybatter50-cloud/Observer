"""
Observer Intelligence Platform - Collector Management API Routes
==============================================================
API endpoints for runtime control of collectors (RSS, NP4K)

@created 2026-02-04 by Mr Cat + Claude - v1.5.0 Collector Architecture

These endpoints enable dashboard UI control of collectors:
- View status and configuration of all collectors
- Enable/disable collectors at runtime
- Change collector configuration (presets, queries, intervals)
- Force immediate collection

Endpoints:
- GET  /api/v1/collectors              - List all collectors with status
- GET  /api/v1/collectors/{name}       - Get specific collector status
- POST /api/v1/collectors/{name}/configure - Update collector config
- POST /api/v1/collectors/{name}/enable    - Enable a collector
- POST /api/v1/collectors/{name}/disable   - Disable a collector
- POST /api/v1/collectors/{name}/collect   - Force immediate collection
Future:
- Persist configuration changes to file/database
- WebSocket notifications for config changes
- Rate limit management per collector
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import config, Config
from utils.logging import get_logger

logger = get_logger(__name__)

# Initialize router
collectors_router = APIRouter(prefix="/api/v1/collectors", tags=["collectors"])


# ==================== IMPORTS ====================

# Try to import collector registry
COLLECTORS_AVAILABLE = False
try:
    from services.collectors import get_collector_registry
    COLLECTORS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Collector registry not available: {e}")

import os


def _collector_enabled(env_key: str) -> bool:
    """Read collector enabled state from os.environ (set by _update_env_vars)."""
    return os.environ.get(env_key, 'false').lower() in ('true', '1', 'yes')


# ==================== REQUEST MODELS ====================

class CollectorConfigRequest(BaseModel):
    """
    Request model for configuring a collector
    
    All fields are optional - only provided fields will be updated.
    """
    # Common fields
    enabled: Optional[bool] = None
    
    # NewsAPI specific
    query_preset: Optional[str] = None
    queries: Optional[List[str]] = None
    language: Optional[str] = None
    page_size: Optional[int] = None
    sort_by: Optional[str] = None
    check_interval: Optional[int] = None
    force_next_collection: Optional[bool] = None
    
    # RSS/NP4K specific
    max_articles_per_source: Optional[int] = None
    delay_between_requests: Optional[float] = None


# ==================== HELPER FUNCTIONS ====================

def _check_collectors_available():
    """Raise 503 if collector system not available"""
    if not COLLECTORS_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="Collector system not available"
        )


def _get_collector_or_404(name: str):
    """Get a collector by name or raise 404"""
    _check_collectors_available()
    
    registry = get_collector_registry()
    collector = registry.get_collector(name)
    
    if not collector:
        available = registry.get_available_collector_names()
        raise HTTPException(
            status_code=404,
            detail=f"Collector '{name}' not found. Available: {available}"
        )
    
    return collector


# ==================== ENDPOINTS ====================

@collectors_router.get("")
async def list_all_collectors():
    """
    List all registered collectors with their current status
    
    Returns:
        List of collector status objects including:
        - name, display_name, enabled, available
        - Configuration details
        - Health and statistics
    
    Example response:
    {
        "collectors": [
            {"name": "rss", "display_name": "RSS Feeds", "enabled": true, ...},
            {"name": "np4k", "display_name": "NP4K Web Scraper", "enabled": true, ...},
            {"name": "newsapi", "display_name": "NewsAPI", "enabled": false, ...}
        ],
        "summary": {
            "total": 3,
            "enabled": 2,
            "available": 2
        }
    }
    """
    _check_collectors_available()
    
    registry = get_collector_registry()
    status = registry.get_status()
    
    collectors_list = []
    for name, collector_status in status.get('collectors', {}).items():
        collectors_list.append(collector_status)
    
    return JSONResponse({
        "collectors": collectors_list,
        "summary": {
            "total": len(status.get('registered_collectors', [])),
            "enabled": len(status.get('enabled_collectors', [])),
            "available": len(status.get('available_collectors', []))
        },
        "registered": status.get('registered_collectors', []),
        "enabled": status.get('enabled_collectors', []),
        "last_collection": status.get('last_collection'),
        "total_collected": status.get('total_collected', 0)
    })


# ==================== NP4K SPECIFIC ENDPOINTS ====================

@collectors_router.get("/np4k/status")
async def get_np4k_status():
    """
    Get NP4K collector status - dedicated endpoint for dashboard toggle.
    NP4K is a specialist web scraper for local/rural news sites not on RSS.
    Default state: off (to conserve tokens).
    """
    has_trafilatura = False
    try:
        from services.collectors.np4k_collector import HAS_TRAFILATURA
        has_trafilatura = HAS_TRAFILATURA
    except ImportError:
        pass

    enabled = _collector_enabled('NP4K_ENABLED')

    return JSONResponse({
        "name": "np4k",
        "available": has_trafilatura,
        "enabled": enabled,
        "has_trafilatura": has_trafilatura
    })


@collectors_router.post("/np4k/enable")
async def enable_np4k():
    """Enable NP4K collector via dashboard toggle"""
    from api.routes_admin import _update_env_vars
    _update_env_vars({"NP4K_ENABLED": "true"})

    if COLLECTORS_AVAILABLE:
        try:
            registry = get_collector_registry()
            registry.enable_collector('np4k')
        except Exception as e:
            logger.debug(f"Could not enable np4k in registry: {e}")

    return JSONResponse({"success": True, "enabled": True})


@collectors_router.post("/np4k/disable")
async def disable_np4k():
    """Disable NP4K collector via dashboard toggle"""
    from api.routes_admin import _update_env_vars
    _update_env_vars({"NP4K_ENABLED": "false"})

    if COLLECTORS_AVAILABLE:
        try:
            registry = get_collector_registry()
            registry.disable_collector('np4k')
        except Exception as e:
            logger.debug(f"Could not disable np4k in registry: {e}")

    return JSONResponse({"success": True, "enabled": False})


# ==================== GENERIC COLLECTOR ENDPOINTS ====================

@collectors_router.get("/{name}")
async def get_collector_status(name: str):
    """
    Get detailed status for a specific collector
    
    Args:
        name: Collector name (rss, np4k, newsapi)
    
    Returns:
        Full collector status including configuration
    """
    collector = _get_collector_or_404(name)
    return JSONResponse(collector.get_status())


@collectors_router.post("/{name}/configure")
async def configure_collector(name: str, config: CollectorConfigRequest):
    """
    Update collector configuration at runtime
    
    Args:
        name: Collector name
        config: Configuration updates (only provided fields are changed)
    
    Returns:
        Updated collector status
    
    Example:
        POST /api/v1/collectors/newsapi/configure
        {"query_preset": "terrorism", "force_next_collection": true}
    """
    collector = _get_collector_or_404(name)
    
    # Convert Pydantic model to dict, excluding None values
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}
    
    # Handle enable/disable separately
    if 'enabled' in config_dict:
        registry = get_collector_registry()
        if config_dict.pop('enabled'):
            registry.enable_collector(name)
        else:
            registry.disable_collector(name)
    
    # Apply remaining configuration
    if config_dict:
        success = collector.configure(config_dict)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Configuration failed - check parameters"
            )
    
    logger.info(f"Collector '{name}' configured via API")
    
    return JSONResponse({
        "success": True,
        "message": f"Collector '{name}' configured",
        "status": collector.get_status()
    })


@collectors_router.post("/{name}/enable")
async def enable_collector(name: str):
    """
    Enable a collector
    
    Args:
        name: Collector name
    """
    _check_collectors_available()
    
    registry = get_collector_registry()
    
    # Check collector exists
    if name not in registry.get_available_collector_names():
        raise HTTPException(
            status_code=404,
            detail=f"Collector '{name}' not found"
        )
    
    success = registry.enable_collector(name)

    if success:
        # Persist to .env for known collectors
        _COLLECTOR_ENV_MAP = {'rss': 'FEED_COLLECTION_ENABLED'}
        env_key = _COLLECTOR_ENV_MAP.get(name)
        if env_key:
            from api.routes_admin import _update_env_vars
            _update_env_vars({env_key: "true"})

        logger.info(f"Collector '{name}' enabled via API")
        return JSONResponse({
            "success": True,
            "message": f"Collector '{name}' enabled"
        })
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to enable collector '{name}'"
        )


@collectors_router.post("/{name}/disable")
async def disable_collector(name: str):
    """
    Disable a collector
    
    Args:
        name: Collector name
    """
    _check_collectors_available()
    
    registry = get_collector_registry()
    success = registry.disable_collector(name)

    if success:
        # Persist to .env for known collectors
        _COLLECTOR_ENV_MAP = {'rss': 'FEED_COLLECTION_ENABLED'}
        env_key = _COLLECTOR_ENV_MAP.get(name)
        if env_key:
            from api.routes_admin import _update_env_vars
            _update_env_vars({env_key: "false"})

        logger.info(f"Collector '{name}' disabled via API")
        return JSONResponse({
            "success": True,
            "message": f"Collector '{name}' disabled"
        })
    else:
        # May already be disabled
        return JSONResponse({
            "success": True,
            "message": f"Collector '{name}' was already disabled"
        })


@collectors_router.post("/{name}/collect")
async def force_collection(name: str):
    """
    Force immediate collection from a specific collector
    
    Bypasses throttling and runs collection now.
    Use sparingly - respects API rate limits.
    
    Args:
        name: Collector name
    
    Returns:
        Collection results (article count, etc.)
    """
    collector = _get_collector_or_404(name)
    
    if not collector.is_available():
        raise HTTPException(
            status_code=400,
            detail=f"Collector '{name}' is not available (missing API key or dependency)"
        )
    
    # Reset throttle timer if collector has one
    if hasattr(collector, 'last_collection_time'):
        collector.last_collection_time = None
    
    # Get enabled groups from state manager
    try:
        from services.source_state import get_source_state_manager
        state = get_source_state_manager()
        groups = state.enabled_groups
    except ImportError:
        groups = set()
    
    logger.info(f"Forcing collection from '{name}' via API")

    try:
        # collect() is an async generator — must iterate, not await
        count = 0
        async for _article in collector.collect(groups):
            count += 1

        return JSONResponse({
            "success": True,
            "collector": name,
            "articles_collected": count,
            "message": f"Collected {count} articles from {name}"
        })
    except Exception as e:
        logger.error(f"Forced collection from '{name}' failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Collection failed: {str(e)}"
        )


# ==================== API KEY MANAGEMENT ====================

ALLOWED_API_KEYS = {'INTERPOL_API_KEY'}

class ApiKeyRequest(BaseModel):
    key_name: str
    value: str

from pathlib import Path as _Path

def _get_env_path() -> _Path:
    """Return path to .env file in project root."""
    return _Path(__file__).resolve().parent.parent / '.env'


@collectors_router.get("/apikey/{key_name}")
async def get_api_key_status(key_name: str):
    """Check whether an API key is set (returns masked value, never the full key)."""
    if key_name not in ALLOWED_API_KEYS:
        raise HTTPException(status_code=400, detail=f"Key '{key_name}' not manageable")

    current = os.getenv(key_name, '').strip()
    if current:
        masked = current[:4] + '...' + current[-4:] if len(current) > 8 else '****'
    else:
        masked = ''

    return JSONResponse({
        "key_name": key_name,
        "is_set": bool(current),
        "masked": masked,
    })


@collectors_router.post("/apikey")
async def save_api_key(req: ApiKeyRequest):
    """Save an API key to the .env file and reload it into os.environ."""
    if req.key_name not in ALLOWED_API_KEYS:
        raise HTTPException(status_code=400, detail=f"Key '{req.key_name}' not manageable")

    value = req.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="API key value cannot be empty")

    env_path = _get_env_path()

    # Read existing .env (or start fresh)
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines(keepends=True)

    # Find and replace, or append
    found = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(f'{req.key_name}=') or stripped.startswith(f'# {req.key_name}='):
            new_lines.append(f'{req.key_name}={value}\n')
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines.append('\n')
        new_lines.append(f'{req.key_name}={value}\n')

    env_path.write_text(''.join(new_lines))

    # Hot-reload into current process
    os.environ[req.key_name] = value

    logger.info(f"API key '{req.key_name}' saved to .env and reloaded")

    return JSONResponse({
        "success": True,
        "key_name": req.key_name,
        "masked": value[:4] + '...' + value[-4:] if len(value) > 8 else '****',
    })


# ==================== API TOGGLE (ON/OFF) ====================

# Mapping of toggle key -> env var name
_API_TOGGLE_ENV_MAP = {
    'INTERPOL_API_KEY': 'INTERPOL_ENABLED',
    'FBI': 'FBI_ENABLED',
    'SANCTIONS_NETWORK': 'SANCTIONS_NET_ENABLED',
}

_API_TOGGLE_DEFAULTS = {
    'INTERPOL_ENABLED': 'false',
    'FBI_ENABLED': 'true',
    'SANCTIONS_NET_ENABLED': 'true',
}


class ApiToggleRequest(BaseModel):
    key_name: str
    enabled: bool



@collectors_router.get("/api-toggles")
async def get_api_toggles():
    """Return current enabled/disabled state for all toggleable APIs.

    Logic per API:
      - If the *_ENABLED env var is explicitly set, use that value.
      - Otherwise fall back to sensible operational defaults:
        * Keyed APIs: ON if the key is present, OFF if missing.
        * Public APIs: always ON (no key needed, free endpoints).
      - NewsAPI uses the collector runtime flag (already env-aware).
    """
    toggles = {}

    # --- Keyed APIs ---
    toggles['INTERPOL_API_KEY'] = Config.INTERPOL_ENABLED if os.environ.get('INTERPOL_ENABLED') is not None else bool(os.environ.get('INTERPOL_API_KEY', ''))

    # --- Public APIs (no key required) ---
    toggles['FBI'] = Config.FBI_ENABLED
    toggles['SANCTIONS_NETWORK'] = Config.SANCTIONS_NET_ENABLED

    logger.debug(f"API toggle state: {toggles}")
    return JSONResponse({"toggles": toggles})


@collectors_router.post("/api-toggle")
async def toggle_api(req: ApiToggleRequest):
    """Toggle an API on/off. Persists to .env and updates os.environ."""
    if req.key_name not in _API_TOGGLE_ENV_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown toggle: {req.key_name}. Valid: {', '.join(_API_TOGGLE_ENV_MAP.keys())}",
        )

    env_var = _API_TOGGLE_ENV_MAP[req.key_name]
    value = 'true' if req.enabled else 'false'

    # Write to .env using shared helper
    from api.routes_admin import _update_env_vars
    _update_env_vars({env_var: value})

    # Sync runtime Config class attributes for services that read from Config
    from config import Config as _ConfigCls
    _TOGGLE_CONFIG_MAP = {
        'INTERPOL_API_KEY': 'INTERPOL_ENABLED',
        'FBI': 'FBI_ENABLED',
        'SANCTIONS_NETWORK': 'SANCTIONS_NET_ENABLED',
    }
    config_attr = _TOGGLE_CONFIG_MAP.get(req.key_name)
    if config_attr:
        setattr(_ConfigCls, config_attr, req.enabled)

    logger.info(f"API toggle '{req.key_name}' ({env_var}) set to {value}")

    return JSONResponse({
        "success": True,
        "key_name": req.key_name,
        "enabled": req.enabled,
        "env_var": env_var,
    })


# ==================== API CONNECTION CHECK ====================

import aiohttp as _aiohttp

class _PingRequest(BaseModel):
    url: str

@collectors_router.post("/ping")
async def ping_api(req: _PingRequest):
    """Check if an external API endpoint is reachable."""
    try:
        timeout = _aiohttp.ClientTimeout(total=8)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(req.url) as resp:
                return JSONResponse({"reachable": resp.status < 500, "status": resp.status})
    except Exception:
        return JSONResponse({"reachable": False, "status": 0})


# ==================== FUTURE: PERSISTENCE ====================
# 
# To persist configuration changes across restarts:
#
# Option 1: JSON file
#   - Save to data/collector_config.json
#   - Load on startup, apply to collectors
#
# Option 2: Database table
#   - collector_config (collector_name, config_json, updated_at)
#   - Query on startup
#
# Option 3: .env override file
#   - Write to .env.local or data/runtime_config.env
#   - Load after main .env
#
# For now, configuration is runtime-only and resets on restart.
# .env provides startup defaults.
# ==================== END FUTURE ====================
