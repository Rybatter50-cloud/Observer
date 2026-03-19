"""
Observer Intelligence Platform - Database Package

Provides:
  - DatabaseSchema:  Schema creation and management
  - IntelligenceDB:  Backward-compatible facade (delegates to repositories)
  - Database:        New-style connection manager with repository accessors
  - record_to_dict:  asyncpg Record -> JSON-safe dict helper
  - Repositories:    SignalRepository, ReputationRepository, etc.
"""

from .schema import DatabaseSchema
from .models import IntelligenceDB, record_to_dict
from .connection import Database

__all__ = [
    'DatabaseSchema',
    'IntelligenceDB',
    'Database',
    'record_to_dict',
]
