"""
RYBAT Lite v1.0.0 - Main Entry Point
Portable intelligence aggregation and screening system.

Collects RSS feeds, translates with NLLB, screens against sanctions,
and serves a real-time intelligence dashboard.
"""

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import config, ConfigurationError
from api.deps import db, intel_service
from api.security import APIKeyAuthMiddleware
from api.routes import core_router
from services.article_pipeline import ArticlePipeline
from utils.logging import setup_logging, get_logger
from api.routes_scraper import scraper_router
from api.routes_metrics import metrics_router
from api.routes_collectors import collectors_router
from api.routes_debug import debug_router
from api.routes_screening import screening_router
from api.routes_database import database_router
from api.routes_admin import admin_router

# Setup logging first
system_log_handler = setup_logging(config.DEBUG)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown tasks."""
    logger.info("Starting RYBAT Lite...")

    # Display configuration
    config.display()

    # Validate configuration
    try:
        config.validate()
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Initialize PostgreSQL connection pool + schema
    try:
        await db.connect()
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        sys.exit(1)

    # Seed feed_sources from JSON registry (first run only)
    try:
        count = await db.feed_sources.count()
        if count == 0:
            import json
            from pathlib import Path
            json_path = Path(config.FEED_REGISTRY_PATH)
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    registry_json = json.load(f)
                seeded = await db.feed_sources.seed_from_json(registry_json)
                logger.info(f"Seeded {seeded} feed sources from {json_path.name}")
            else:
                logger.warning(f"No JSON registry found at {json_path} — feed_sources table empty")
        else:
            logger.info(f"feed_sources table has {count} entries — skipping JSON seed")
    except Exception as e:
        logger.warning(f"Feed sources seeding skipped: {e}")

    # Reload collectors and feed manager from DB
    try:
        registry_dict = await db.feed_sources.as_registry_dict()

        from services.feed_manager import get_feed_manager
        fm = get_feed_manager()
        if fm:
            fm.feed_registry = registry_dict

        from services.collectors import get_collector_registry
        cr = get_collector_registry()
        for collector in cr.get_all_collectors():
            if hasattr(collector, 'load_registry_from_db'):
                await collector.load_registry_from_db()

        logger.info("Feed system loaded from DB")
    except Exception as e:
        logger.warning(f"DB feed reload failed (using JSON fallback): {e}")

    # Create background tasks
    tasks = []

    try:
        # Article pipeline (collect → translate → persist)
        if config.FEED_COLLECTION_ENABLED:
            app.state.pipeline = ArticlePipeline(
                intel_service, num_workers=3
            )
            tasks.append(asyncio.create_task(
                app.state.pipeline.run(),
                name="article_pipeline"
            ))
            logger.info("Article pipeline started (3 workers)")
        else:
            app.state.pipeline = None
            logger.warning("Feed collection disabled")
            logger.info("Set FEED_COLLECTION_ENABLED=true to enable")

        # Wire screening service to DB + pre-warm caches
        try:
            from services.entity_screening import get_screening_service
            screening_svc = get_screening_service()
            screening_svc.connect_db(db.screening)
            asyncio.create_task(screening_svc.warm_cache())
        except Exception as e:
            logger.debug(f"Screening service init skipped: {e}")

        logger.info(f"All background tasks started ({len(tasks)} tasks)")
        logger.info("=" * 60)
        logger.info("Profile: LITE (Portable)")
        logger.info(f"Dashboard: http://{config.HOST}:{config.PORT}")
        if config.SCRAPER_COLLECTION_ENABLED:
            logger.info(f"Scraper Manager: http://{config.HOST}:{config.PORT}/scraper")
        logger.info(f"Health Check: http://{config.HOST}:{config.PORT}/api/v1/health")
        logger.info("=" * 60)

        # Yield control to the application
        yield

    finally:
        # Cleanup: Cancel all background tasks
        logger.info("Shutting down background tasks...")
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await db.close()
        logger.info("Shutdown complete")


# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
    storage_uri="memory://",
)

# Create FastAPI application
app = FastAPI(
    title="RYBAT Lite",
    description="Portable intelligence aggregation and screening system",
    version="1.0.0",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ==========================================================================
# MIDDLEWARE STACK
# ==========================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Accept"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.headers.get("X-Forwarded-Proto") == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-src 'none'; "
            "media-src 'self'; "
            "form-action 'self'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(APIKeyAuthMiddleware)

# Include routers
app.include_router(scraper_router)
app.include_router(metrics_router)
app.include_router(core_router)
app.include_router(collectors_router)
app.include_router(debug_router)
app.include_router(screening_router)
app.include_router(database_router)
app.include_router(admin_router)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


def main():
    """Main entry point for running the application"""
    import uvicorn

    try:
        uvicorn.run(
            "main:app",
            host=config.HOST,
            port=config.PORT,
            reload=config.DEBUG,
            log_level="info" if not config.DEBUG else "debug"
        )
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
