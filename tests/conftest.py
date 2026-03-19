"""
Observer Test Suite - Shared Fixtures
===================================
Provides a test database, repository instances, and FastAPI test client.

Each test function gets a fresh database (tables truncated between tests).
"""

import asyncio
import os
import sys

import asyncpg
import pytest
import pytest_asyncio

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://observer@/observer_test?host=/var/run/postgresql",
)


# ---------------------------------------------------------------------------
# Event loop — single loop for the entire session so the pool persists
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database pool (session-scoped — created once, shared across all tests)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def pool():
    """Create a connection pool and initialize the schema once per session."""
    _pool = await asyncpg.create_pool(
        TEST_DSN,
        min_size=2,
        max_size=5,
        command_timeout=10,
        server_settings={"jit": "off"},
    )

    # Initialize schema (extensions, enums, tables, indexes)
    from database.schema import DatabaseSchema
    await DatabaseSchema.initialize_database(_pool)

    yield _pool
    await _pool.close()


# ---------------------------------------------------------------------------
# Per-test cleanup — truncate all tables so each test starts fresh
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def clean_tables(pool):
    """Truncate all data tables before each test."""
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE intel_signals, source_reputation, author_reputation "
            "RESTART IDENTITY CASCADE"
        )
    yield


# ---------------------------------------------------------------------------
# Repository fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session")
async def signals_repo(pool):
    from database.repositories.signals import SignalRepository
    return SignalRepository(pool)


@pytest_asyncio.fixture(loop_scope="session")
async def reputation_repo(pool):
    from database.repositories.reputation import ReputationRepository
    return ReputationRepository(pool)


@pytest_asyncio.fixture(loop_scope="session")
async def metrics_repo(pool):
    from database.repositories.metrics import MetricsRepository
    return MetricsRepository(pool)


# ---------------------------------------------------------------------------
# IntelligenceDB facade fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session")
async def intel_db(pool):
    """IntelligenceDB facade wired to the test pool (skips connect())."""
    from database.models import IntelligenceDB
    from database.connection import Database

    db = IntelligenceDB.__new__(IntelligenceDB)
    db.dsn = TEST_DSN

    inner = Database.__new__(Database)
    inner.dsn = TEST_DSN
    inner._pool = pool

    from database.repositories.signals import SignalRepository
    from database.repositories.reputation import ReputationRepository
    from database.repositories.metrics import MetricsRepository

    inner._signals = SignalRepository(pool)
    inner._reputation = ReputationRepository(pool)
    inner._metrics = MetricsRepository(pool)

    db._db = inner
    return db


# ---------------------------------------------------------------------------
# IntelligenceService fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session")
async def intel_service(intel_db):
    from services.intelligence import IntelligenceService
    return IntelligenceService(intel_db)


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def app(intel_db, pool):
    """Create a FastAPI app wired to the test database, without running lifespan."""
    import api.deps as deps
    from contextlib import asynccontextmanager

    # Routes use `from api.deps import db` at module level, which binds the
    # NAME at import time. We can't replace deps.db after that.  Instead,
    # mutate the *existing* IntelligenceDB's inner Database to use the test pool.
    original_inner = deps.db._db
    deps.db._db = intel_db._db   # swap the inner Database (holds pool + repos)

    from main import app as _app

    # Replace lifespan so TestClient doesn't start the real pipeline
    original_lifespan = _app.router.lifespan_context

    @asynccontextmanager
    async def _test_lifespan(app):
        yield

    _app.router.lifespan_context = _test_lifespan

    yield _app

    # Restore
    _app.router.lifespan_context = original_lifespan
    deps.db._db = original_inner


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def make_signal_data(**overrides):
    """Return a minimal dict for insert_final_signal."""
    defaults = {
        "title": "Test explosion in test city",
        "description": "A test event occurred",
        "full_text": None,
        "url": "https://example.com/test-article",
        "published_at": None,
        "source_label": "TestSource",
        "collector_name": "test",
        "location": "Test City",
        "relevance_score": 55,
        "casualties": 0,
        "risk_indicators": ["U"],
        "analysis_mode": "SKIPPED",
        "source_confidence": 65,
        "author_confidence": 60,
        "is_translated": False,
        "source_language": None,
        "translation_source": None,
        "author": "Test Author",
        "source_name": "TestSource",
        "author_name": "Test Author",
        "pre_score": 55,
    }
    defaults.update(overrides)
    return defaults
