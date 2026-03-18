"""
RYBAT Intelligence Platform - Shared Dependencies
===================================================
Single source of truth for db and intel_service instances.

All route files import from here instead of cross-importing
from api.routes. Eliminates circular import risk.

Usage:
    from api.deps import db, intel_service

Lifecycle:
    - IntelligenceDB created at import time (no pool yet)
    - Pool opened via db.connect() during app lifespan (main.py)
    - Pool closed via db.close() during shutdown (main.py)

@created 2026-02-09 - Phase 3a: dependency injection cleanup
"""

from config import config
from database.models import IntelligenceDB
from services.intelligence import IntelligenceService

# Pool is created lazily via db.connect() during app startup (see main.py)
db = IntelligenceDB(config.DATABASE_URL)
intel_service = IntelligenceService(db)
