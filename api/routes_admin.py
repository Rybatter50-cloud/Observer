"""
Observer Intelligence Platform - Admin Control Panel API
======================================================
Endpoints for the admin control panel sidebar:
  - Filter editor (read/write filter file contents + pattern lists)
  - Collector environment config (env vars + registry stats)
  - Collector env editor (read/write .env settings per collector)
  - App controls (pipeline restart, full app restart)
  - AI control (Ollama model selector + generation config)

2026-02-17 | Mr Cat + Claude | Collector env editor
2026-02-16 | Mr Cat + Claude | Initial implementation
"""

import asyncio
import os
import re
import signal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import db
from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

FILTERS_DIR = Path(os.getenv('FILTERS_DIR', './filters'))


# ==================== FILTER EDITOR ====================

class FilterContentRequest(BaseModel):
    filename: str
    content: str


class FilterPatternsRequest(BaseModel):
    filename: str
    patterns: list[str]


@admin_router.get("/filter/content")
async def get_filter_content(filename: str):
    """Read the raw text content of a filter file."""
    if not _validate_filter_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filter filename")

    filepath = FILTERS_DIR / f"{filename}.txt"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Filter file not found: {filename}")

    content = filepath.read_text(encoding='utf-8')
    return JSONResponse({
        "filename": filename,
        "content": content,
        "line_count": len([l for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]),
    })


@admin_router.post("/filter/content")
async def save_filter_content(req: FilterContentRequest):
    """Save raw text content to a filter file."""
    if not _validate_filter_filename(req.filename):
        raise HTTPException(status_code=400, detail="Invalid filter filename")

    filepath = FILTERS_DIR / f"{req.filename}.txt"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Filter file not found: {req.filename}")

    # Validate that each non-comment, non-blank line is valid regex
    errors = []
    valid_count = 0
    for i, line in enumerate(req.content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        try:
            re.compile(stripped, re.IGNORECASE)
            valid_count += 1
        except re.error as e:
            errors.append(f"Line {i}: {e}")

    if errors and valid_count == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No valid patterns found. Errors: {'; '.join(errors[:5])}"
        )

    # Write the file
    filepath.write_text(req.content, encoding='utf-8')

    # Reload the content filter if this file is currently active
    _reload_active_filter(req.filename)

    logger.info(f"Filter file saved: {req.filename} ({valid_count} patterns)")

    return JSONResponse({
        "success": True,
        "filename": req.filename,
        "valid_patterns": valid_count,
        "errors": errors[:10] if errors else [],
    })


@admin_router.get("/filter/patterns")
async def get_filter_patterns(filename: str):
    """Get patterns from a filter file as a structured list."""
    if not _validate_filter_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filter filename")

    filepath = FILTERS_DIR / f"{filename}.txt"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Filter file not found: {filename}")

    patterns = []
    for line in filepath.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        valid = True
        try:
            re.compile(stripped, re.IGNORECASE)
        except re.error:
            valid = False
        patterns.append({"pattern": stripped, "valid": valid})

    return JSONResponse({
        "filename": filename,
        "patterns": patterns,
        "total": len(patterns),
    })


@admin_router.post("/filter/patterns")
async def save_filter_patterns(req: FilterPatternsRequest):
    """Save patterns as a list to a filter file (overwrites non-comment content)."""
    if not _validate_filter_filename(req.filename):
        raise HTTPException(status_code=400, detail="Invalid filter filename")

    filepath = FILTERS_DIR / f"{req.filename}.txt"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Filter file not found: {req.filename}")

    # Read existing file to preserve header comments
    existing = filepath.read_text(encoding='utf-8')
    header_lines = []
    for line in existing.splitlines():
        if line.strip().startswith('#') or not line.strip():
            header_lines.append(line)
        else:
            break

    # Validate patterns
    errors = []
    valid_patterns = []
    for i, pattern in enumerate(req.patterns):
        pattern = pattern.strip()
        if not pattern:
            continue
        try:
            re.compile(pattern, re.IGNORECASE)
            valid_patterns.append(pattern)
        except re.error as e:
            errors.append(f"Pattern {i+1}: {e}")

    # Build new file content
    content_lines = header_lines + [''] + valid_patterns + ['']
    filepath.write_text('\n'.join(content_lines), encoding='utf-8')

    _reload_active_filter(req.filename)

    logger.info(f"Filter patterns saved: {req.filename} ({len(valid_patterns)} patterns)")

    return JSONResponse({
        "success": True,
        "filename": req.filename,
        "valid_patterns": len(valid_patterns),
        "errors": errors[:10] if errors else [],
    })


def _validate_filter_filename(filename: str) -> bool:
    """Validate filter filename to prevent path traversal."""
    if not filename:
        return False
    if '/' in filename or '\\' in filename or '..' in filename:
        return False
    if not (filename.startswith('BL_') or filename.startswith('WL_')):
        return False
    return True


def _reload_active_filter(filename: str):
    """Reload the content filter if the saved file is currently active."""
    try:
        from services.content_filter import get_content_filter
        cf = get_content_filter()
        if cf.active_bl_file == filename or cf.active_wl_file == filename:
            cf.set_filters(bl_file=cf.active_bl_file, wl_file=cf.active_wl_file)
            logger.info(f"Content filter reloaded after editing {filename}")
    except Exception as e:
        logger.debug(f"Could not reload content filter: {e}")


# ==================== COLLECTOR CONFIG ====================

@admin_router.get("/collectors/config")
async def get_collectors_config():
    """
    Return environment variables and feed registry stats per collector.

    Groups config into RSS, NP4K, and NewsAPI sections with their
    relevant env vars and registry-level stats.
    """
    # RSS collector config
    rss_config = {
        "name": "rss",
        "display_name": "RSS Feeds",
        "env_vars": {
            "FEED_COLLECTION_ENABLED": {
                "value": str(config.FEED_COLLECTION_ENABLED),
                "description": "Enable/disable RSS feed collection",
            },
            "FEED_CHECK_INTERVAL": {
                "value": str(config.FEED_CHECK_INTERVAL),
                "description": "Seconds between collection cycles",
            },
            "FEED_MAX_ARTICLES_PER_SOURCE": {
                "value": str(config.FEED_MAX_ARTICLES_PER_SOURCE),
                "description": "Max articles per feed per cycle",
            },
            "FEED_CONCURRENCY": {
                "value": str(config.FEED_CONCURRENCY),
                "description": "Max concurrent feed fetches (semaphore-bounded)",
            },
            "COLLECTOR_TIMEOUT": {
                "value": str(config.COLLECTOR_TIMEOUT),
                "description": "Max seconds per collector run",
            },
        },
        "registry": _get_registry_stats(),
    }

    # NP4K collector config
    np4k_config = {
        "name": "np4k",
        "display_name": "NP4K Scraper",
        "env_vars": {
            "SCRAPER_COLLECTION_ENABLED": {
                "value": str(config.SCRAPER_COLLECTION_ENABLED),
                "description": "Enable/disable scraper collection",
            },
            "SCRAPER_REQUEST_TIMEOUT": {
                "value": str(config.SCRAPER_REQUEST_TIMEOUT),
                "description": "HTTP request timeout (seconds)",
            },
            "SCRAPER_FAST_MODE": {
                "value": str(config.SCRAPER_FAST_MODE),
                "description": "Use trafilatura fast mode (skips fallbacks, still high accuracy)",
            },
            "SCRAPER_DELAY_BETWEEN_ARTICLES": {
                "value": str(config.SCRAPER_DELAY_BETWEEN_ARTICLES),
                "description": "Seconds between article scrapes",
            },
            "SCRAPER_MAX_ARTICLES_PER_SITE": {
                "value": str(config.SCRAPER_MAX_ARTICLES_PER_SITE),
                "description": "Max articles per site per run",
            },
            "SCRAPER_MIN_WORD_COUNT": {
                "value": str(config.SCRAPER_MIN_WORD_COUNT),
                "description": "Minimum article word count",
            },
        },
        "registry": _get_scraper_registry_stats(),
    }

    # Attach collector stats if available
    for cfg in [rss_config, np4k_config]:
        cfg["stats"] = _get_collector_stats(cfg["name"])

    return JSONResponse({
        "collectors": [rss_config, np4k_config],
    })


def _get_registry_stats() -> dict:
    """Get feed registry statistics from the FeedManager (DB-backed)."""
    try:
        from services.feed_manager import get_feed_manager
        fm = get_feed_manager()
        registry = fm.feed_registry

        total_feeds = 0
        groups = 0
        for key, value in registry.items():
            if key == '_metadata':
                continue
            if isinstance(value, dict) and 'feeds' in value:
                groups += 1
                total_feeds += len(value.get('feeds', []))

        return {
            "total_feeds": total_feeds,
            "total_groups": groups,
        }
    except Exception as e:
        return {"error": str(e)}


def _get_scraper_registry_stats() -> dict:
    """Get scraper sites count from the FeedManager registry (DB-backed)."""
    try:
        from services.feed_manager import get_feed_manager
        fm = get_feed_manager()
        registry = fm.feed_registry

        total_sites = 0
        for key, value in registry.items():
            if key == '_metadata':
                continue
            if isinstance(value, dict):
                total_sites += len(value.get('scraper_sites', []))

        return {"total_scraper_sites": total_sites}
    except Exception:
        return {}


def _get_collector_stats(name: str) -> dict:
    """Get 24h stats from a collector's CollectorStats object."""
    try:
        from services.collectors import get_collector_registry
        registry = get_collector_registry()
        collector = registry.get_collector(name)
        if collector and hasattr(collector, 'stats'):
            d = collector.stats.to_dict()
            return {
                "articles_24h": d.get("articles_24h", 0),
                "errors_24h": d.get("errors_24h", 0),
                "last_collection": d.get("last_run"),
            }
    except Exception:
        pass
    return {}


# ==================== COLLECTOR ENV EDITOR ====================

# Editable env vars per collector (excludes API keys)
COLLECTOR_ENV_DEFS: dict[str, dict] = {
    "rss": {
        "display_name": "RSS Collector",
        "vars": {
            "FEED_COLLECTION_ENABLED": {
                "description": "Enable/disable RSS feed collection",
                "type": "bool",
                "default": "true",
            },
            "FEED_CHECK_INTERVAL": {
                "description": "Seconds between collection cycles",
                "type": "int",
                "default": "300",
            },
            "FEED_MAX_ARTICLES_PER_SOURCE": {
                "description": "Max articles per feed per cycle (1-20)",
                "type": "int",
                "default": "5",
            },
            "FEED_CONCURRENCY": {
                "description": "Max concurrent feed fetches (1-50)",
                "type": "int",
                "default": "10",
            },
            "COLLECTOR_TIMEOUT": {
                "description": "Max seconds per collector run",
                "type": "int",
                "default": "1200",
            },
        },
    },
    "np4k": {
        "display_name": "Trafilatura Scraper",
        "vars": {
            "SCRAPER_COLLECTION_ENABLED": {
                "description": "Enable/disable scraper collection",
                "type": "bool",
                "default": "true",
            },
            "SCRAPER_REQUEST_TIMEOUT": {
                "description": "HTTP request timeout (seconds)",
                "type": "int",
                "default": "30",
            },
            "SCRAPER_DELAY_BETWEEN_ARTICLES": {
                "description": "Seconds between article scrapes",
                "type": "float",
                "default": "2.0",
            },
            "SCRAPER_MAX_ARTICLES_PER_SITE": {
                "description": "Max articles per site per run",
                "type": "int",
                "default": "20",
            },
            "SCRAPER_MIN_WORD_COUNT": {
                "description": "Minimum article word count",
                "type": "int",
                "default": "100",
            },
            "SCRAPER_MAX_REQUESTS_PER_HOUR": {
                "description": "Max requests per site per hour",
                "type": "int",
                "default": "100",
            },
            "SCRAPER_DEFAULT_LANGUAGE": {
                "description": "Default language (ISO 639-1)",
                "type": "str",
                "default": "en",
            },
            # --- Content Inclusion/Exclusion ---
            "SCRAPER_INCLUDE_TABLES": {
                "description": "Include HTML tables in extraction",
                "type": "bool",
                "default": "false",
            },
            "SCRAPER_INCLUDE_LINKS": {
                "description": "Include hyperlinks in extraction",
                "type": "bool",
                "default": "false",
            },
            "SCRAPER_INCLUDE_IMAGES": {
                "description": "Include image references in extraction",
                "type": "bool",
                "default": "false",
            },
            "SCRAPER_INCLUDE_COMMENTS": {
                "description": "Include page comments in extraction",
                "type": "bool",
                "default": "false",
            },
            # --- Algorithm Tuning (Precision vs. Recall) ---
            "SCRAPER_FAST_MODE": {
                "description": "Fast mode (skip fallback extractors)",
                "type": "bool",
                "default": "true",
            },
            "SCRAPER_FAVOR_PRECISION": {
                "description": "Favor precision (stricter extraction)",
                "type": "bool",
                "default": "false",
            },
            "SCRAPER_FAVOR_RECALL": {
                "description": "Favor recall (extract more content)",
                "type": "bool",
                "default": "false",
            },
            # --- Metadata & Processing Filters ---
            "SCRAPER_DEDUPLICATE": {
                "description": "Deduplicate extracted content",
                "type": "bool",
                "default": "true",
            },
            "SCRAPER_URL_BLACKLIST": {
                "description": "Comma-separated URL patterns to skip",
                "type": "str",
                "default": "",
            },
        },
    },
}


class CollectorEnvSaveRequest(BaseModel):
    collector: str
    values: dict[str, str]


def _get_env_path() -> Path:
    """Return path to .env file in project root."""
    return Path(__file__).resolve().parent.parent / '.env'


_SENSITIVE_KEY_FRAGMENTS = ('KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'DSN', 'URL')


def _mask_value(key: str, value: str) -> str:
    """Mask values for sensitive keys in audit logs (show last 4 chars only)."""
    if any(frag in key.upper() for frag in _SENSITIVE_KEY_FRAGMENTS):
        return f"***{value[-4:]}" if len(value) > 4 else "***"
    return value


def _update_env_vars(updates: dict[str, str]) -> None:
    """Write/update multiple key=value pairs in the .env file."""
    env_path = _get_env_path()

    # Capture previous values for audit trail
    prev_values = {key: os.environ.get(key, '') for key in updates}

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines(keepends=True)

    remaining = dict(updates)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        matched_key = None
        for key in remaining:
            if stripped.startswith(f'{key}=') or stripped.startswith(f'# {key}='):
                matched_key = key
                break
        if matched_key:
            new_lines.append(f'{matched_key}={remaining.pop(matched_key)}\n')
        else:
            new_lines.append(line)

    # Append any keys not found in existing file
    for key, value in remaining.items():
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines.append('\n')
        new_lines.append(f'{key}={value}\n')

    env_path.write_text(''.join(new_lines))

    # Hot-reload into current process
    for key, value in updates.items():
        os.environ[key] = value

    # Audit trail
    for key, new_val in updates.items():
        old_val = prev_values.get(key, '')
        if old_val != new_val:
            logger.info(
                f"ENV_CHANGE: {key} "
                f"old={_mask_value(key, old_val)!r} "
                f"new={_mask_value(key, new_val)!r}"
            )


@admin_router.get("/collectors/env")
async def get_collector_env(collector: str):
    """
    Return editable .env settings for a specific collector.

    Returns field definitions with current values for the form editor.
    API keys are excluded.
    """
    if collector not in COLLECTOR_ENV_DEFS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collector: {collector}. Valid: {', '.join(COLLECTOR_ENV_DEFS.keys())}",
        )

    defn = COLLECTOR_ENV_DEFS[collector]
    fields = []
    for key, meta in defn["vars"].items():
        fields.append({
            "key": key,
            "value": os.getenv(key, meta["default"]),
            "description": meta["description"],
            "type": meta["type"],
            "default": meta["default"],
            "options": meta.get("options"),
        })

    return JSONResponse({
        "collector": collector,
        "display_name": defn["display_name"],
        "fields": fields,
    })


@admin_router.get("/collectors/env/list")
async def list_collector_env_editors():
    """Return the list of available collectors for the env editor dropdown."""
    collectors = []
    for key, defn in COLLECTOR_ENV_DEFS.items():
        collectors.append({
            "name": key,
            "display_name": defn["display_name"],
            "field_count": len(defn["vars"]),
        })
    return JSONResponse({"collectors": collectors})


@admin_router.post("/collectors/env")
async def save_collector_env(req: CollectorEnvSaveRequest):
    """
    Save .env settings for a specific collector.

    Validates types, writes to .env, and hot-reloads into os.environ.
    """
    if req.collector not in COLLECTOR_ENV_DEFS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collector: {req.collector}",
        )

    defn = COLLECTOR_ENV_DEFS[req.collector]
    allowed_keys = set(defn["vars"].keys())
    errors = []
    updates: dict[str, str] = {}

    for key, value in req.values.items():
        if key not in allowed_keys:
            errors.append(f"Unknown setting: {key}")
            continue

        meta = defn["vars"][key]
        value = value.strip()

        # Type validation
        if meta["type"] == "int":
            try:
                int(value)
            except ValueError:
                errors.append(f"{key}: must be an integer")
                continue
        elif meta["type"] == "float":
            try:
                float(value)
            except ValueError:
                errors.append(f"{key}: must be a number")
                continue
        elif meta["type"] == "bool":
            if value.lower() not in ("true", "false"):
                errors.append(f"{key}: must be 'true' or 'false'")
                continue
            value = value.lower()
        elif meta["type"] == "select":
            if value not in meta.get("options", []):
                errors.append(f"{key}: must be one of {meta['options']}")
                continue

        updates[key] = value

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    if not updates:
        raise HTTPException(status_code=400, detail="No valid settings to save")

    _update_env_vars(updates)

    logger.info(
        f"Collector env saved: {req.collector} ({len(updates)} settings updated)"
    )

    return JSONResponse({
        "success": True,
        "collector": req.collector,
        "updated": len(updates),
    })


# ==================== APP CONTROLS ====================

@admin_router.post("/restart/pipeline")
async def restart_pipeline(request: Request):
    """
    Restart the article collection pipeline.

    Cancels the running pipeline task and starts a new one.
    Does NOT restart the entire application.
    """
    app = request.app

    pipeline = getattr(app.state, 'pipeline', None)
    if pipeline is None:
        raise HTTPException(
            status_code=400,
            detail="Pipeline not running (FEED_COLLECTION_ENABLED=false)"
        )

    try:
        # Find and cancel the pipeline task
        pipeline_task = None
        for task in asyncio.all_tasks():
            if task.get_name() == 'article_pipeline':
                pipeline_task = task
                break

        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(pipeline_task),
                    timeout=5.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Create a new pipeline instance and start it
        from services.article_pipeline import ArticlePipeline
        from api.deps import intel_service

        app.state.pipeline = ArticlePipeline(intel_service, num_workers=3)
        asyncio.create_task(
            app.state.pipeline.run(),
            name="article_pipeline"
        )

        logger.info("Article pipeline restarted via admin panel")

        return JSONResponse({
            "success": True,
            "message": "Pipeline restarted successfully",
        })

    except Exception as e:
        logger.error(f"Pipeline restart failed: {e}")
        raise HTTPException(status_code=500, detail=f"Restart failed: {str(e)}")


@admin_router.post("/restart/app")
async def restart_app():
    """
    Restart the entire Observer application.

    Sends SIGHUP to the current process to trigger uvicorn reload.
    The response may not be received if the process restarts immediately.
    """
    logger.info("Full application restart requested via admin panel")

    # Schedule the signal after a brief delay so the response can be sent
    async def _delayed_restart():
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGHUP)

    asyncio.create_task(_delayed_restart())

    return JSONResponse({
        "success": True,
        "message": "Application restart initiated. Page will reload shortly.",
    })



# ==================== SCREENING STATUS ====================

@admin_router.get("/screening/status")
async def get_screening_status():
    """Get entity screening service status and stats."""
    try:
        from services.entity_screening import get_screening_service
        svc = get_screening_service()
        status = await svc.get_status()

        # Merge screening log stats if DB is available
        try:
            log_stats = await db.screening.get_screening_log_stats()
            status['log_stats'] = log_stats
        except Exception:
            pass

        return JSONResponse(status)
    except Exception as e:
        return JSONResponse({
            "available": False,
            "error": str(e),
            "total_screens": 0,
        })


# ==================== TRANSFORMER STATUS ====================

@admin_router.get("/transformers/status")
async def get_transformers_status():
    """Get status of all transformer/AI model services."""
    result = {
        "nllb": {"enabled": False, "model": None, "loaded": False},
    }

    # NLLB Translation service
    try:
        from services.translation import get_translation_service
        tsvc = get_translation_service()
        stats = tsvc.get_stats()
        result["nllb"] = {
            "enabled": stats.get("enabled", False),
            "mode": stats.get("mode", "off"),
            "model": stats.get("model"),
            "loaded": stats.get("nllb_loaded", False),
            "translations": stats.get("translations", 0),
            "cache_size": stats.get("cache_size", 0),
            "languages": stats.get("supported_language_count", 0),
        }
    except Exception as e:
        result["nllb"]["error"] = str(e)

    return JSONResponse(result)


# ==================== BROADCAST CONTROL (MOCK) ====================

@admin_router.get("/broadcast/status")
async def get_broadcast_status():
    """Mock broadcast status — always returns not configured."""
    return JSONResponse({
        "mock": True,
        "status": "not_configured",
        "uplink": None,
        "scheduled_reports": 2,
    })




# ==================== NLLB / CTranslate2 TUNING ====================

@admin_router.get("/nllb/params")
async def get_nllb_params():
    """Get current CTranslate2 translation tuning parameters."""
    try:
        from services.translation import get_translation_service
        tsvc = get_translation_service()
        stats = tsvc.get_stats()
        return JSONResponse({
            "params": tsvc.get_nllb_params(),
            "device": stats.get("nllb_device", "auto"),
            "compute_type": stats.get("nllb_compute_type", "auto"),
            "inter_threads": stats.get("nllb_inter_threads", 1),
            "intra_threads": stats.get("nllb_intra_threads", 4),
            "loaded": stats.get("nllb_loaded", False),
            "model": stats.get("model"),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/nllb/params")
async def set_nllb_params(request: Request):
    """Update CTranslate2 translation tuning parameters at runtime and persist to .env."""
    # Map from set_nllb_params key names → .env var names
    _PARAM_ENV_MAP = {
        'beam_size':            'NLLB_BEAM_SIZE',
        'length_penalty':       'NLLB_LENGTH_PENALTY',
        'repetition_penalty':   'NLLB_REPETITION_PENALTY',
        'no_repeat_ngram_size': 'NLLB_NO_REPEAT_NGRAM',
        'max_batch_size':       'NLLB_BATCH_SIZE',
        'batch_type':           'NLLB_BATCH_TYPE',
        'max_decoding_length':  'NLLB_MAX_LENGTH',
        'max_input_length':     'NLLB_MAX_INPUT_LENGTH',
        'sampling_topk':        'NLLB_SAMPLING_TOPK',
        'sampling_topp':        'NLLB_SAMPLING_TOPP',
        'sampling_temperature': 'NLLB_SAMPLING_TEMPERATURE',
    }

    try:
        from services.translation import get_translation_service
        body = await request.json()
        tsvc = get_translation_service()
        applied = tsvc.set_nllb_params(body)

        # Persist every applied param to .env so they survive restarts
        env_updates = {}
        for key, value in applied.items():
            env_name = _PARAM_ENV_MAP.get(key)
            if env_name:
                env_updates[env_name] = str(value)

        if env_updates:
            _update_env_vars(env_updates)
            logger.info(f"NLLB tuning params saved to .env: {env_updates}")

        logger.info(f"NLLB params updated: {applied}")
        return JSONResponse({"applied": applied, "params": tsvc.get_nllb_params()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/nllb/model-params")
async def save_nllb_model_params(request: Request):
    """Save NLLB model-loading params to .env and restart the application.

    These params (device, compute_type, inter_threads, intra_threads) are
    set at Translator init time and require a full restart to take effect.
    """
    VALID_DEVICES = ('auto', 'cpu', 'cuda')
    VALID_COMPUTE = ('auto', 'int8', 'int8_float16', 'int8_float32',
                     'int8_bfloat16', 'int16', 'float16', 'bfloat16', 'float32')

    try:
        body = await request.json()
        env_updates = {}

        device = body.get('device')
        if device and device in VALID_DEVICES:
            env_updates['NLLB_DEVICE'] = device

        compute_type = body.get('compute_type')
        if compute_type and compute_type in VALID_COMPUTE:
            env_updates['NLLB_COMPUTE_TYPE'] = compute_type

        inter_threads = body.get('inter_threads')
        if inter_threads is not None:
            val = max(1, min(16, int(inter_threads)))
            env_updates['NLLB_INTER_THREADS'] = str(val)

        intra_threads = body.get('intra_threads')
        if intra_threads is not None:
            val = max(1, min(32, int(intra_threads)))
            env_updates['NLLB_INTRA_THREADS'] = str(val)

        if not env_updates:
            return JSONResponse({"success": False, "message": "No valid params provided"}, status_code=400)

        _update_env_vars(env_updates)
        logger.info(f"NLLB model params saved to .env: {env_updates} — restarting")

        async def _delayed_restart():
            await asyncio.sleep(0.5)
            os.kill(os.getpid(), signal.SIGHUP)

        asyncio.create_task(_delayed_restart())

        return JSONResponse({
            "success": True,
            "saved": env_updates,
            "message": "Saved to .env. Restarting...",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
