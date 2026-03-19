"""
Observer Intelligence Platform - Services Package
"""

from .websocket import manager, ConnectionManager
from .intelligence import IntelligenceService

__all__ = [
    'manager',
    'ConnectionManager',
    'IntelligenceService',
]
