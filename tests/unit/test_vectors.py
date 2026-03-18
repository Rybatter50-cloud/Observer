"""
Tests for VectorRepository — focused on search_similar query construction.

These tests mock asyncpg to verify the SQL includes the right WHERE clauses
for the country filter without needing a live PostgreSQL + pgvector instance.
"""

import os
import sys
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.repositories.vectors import VectorRepository


def _fake_pool():
    """Create a mock asyncpg pool whose conn.fetch captures the SQL and params."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    pool = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx

    return pool, conn


def _random_embedding(dim=384):
    return np.random.randn(dim).astype(np.float32)


class TestSearchSimilarCountryFilter:
    """Verify that the country parameter produces correct SQL."""

    @pytest.mark.asyncio
    async def test_no_country_filter(self):
        """Without country param, query should NOT contain ILIKE."""
        pool, conn = _fake_pool()
        repo = VectorRepository(pool)

        await repo.search_similar(_random_embedding(), top_k=10)

        sql = conn.fetch.call_args[0][0]
        assert "ILIKE" not in sql
        assert "signal_location_links" not in sql

    @pytest.mark.asyncio
    async def test_country_filter_present(self):
        """With country param, query should include ILIKE on location, title, description."""
        pool, conn = _fake_pool()
        repo = VectorRepository(pool)

        await repo.search_similar(_random_embedding(), top_k=10, country="Iran")

        sql = conn.fetch.call_args[0][0]
        # Should search location, title, AND description
        assert "location ILIKE" in sql
        assert "title ILIKE" in sql
        assert "description ILIKE" in sql
        # Should NOT use the unpopulated signal_location_links table
        assert "signal_location_links" not in sql

    @pytest.mark.asyncio
    async def test_country_passed_as_parameter(self):
        """Country value should be passed as a query parameter, not inlined."""
        pool, conn = _fake_pool()
        repo = VectorRepository(pool)

        await repo.search_similar(_random_embedding(), top_k=10, country="Sudan")

        # params are positional args after the SQL string
        params = conn.fetch.call_args[0][1:]
        assert "Sudan" in params

    @pytest.mark.asyncio
    async def test_country_with_time_window(self):
        """Country and time_window_hours should coexist without conflicting params."""
        pool, conn = _fake_pool()
        repo = VectorRepository(pool)

        await repo.search_similar(
            _random_embedding(), top_k=10,
            time_window_hours=168, country="Ukraine",
        )

        sql = conn.fetch.call_args[0][0]
        params = conn.fetch.call_args[0][1:]

        # Both filters present
        assert "created_at > NOW()" in sql
        assert "location ILIKE" in sql
        # time_window_hours (168) and country ("Ukraine") both in params
        assert 168 in params
        assert "Ukraine" in params

    @pytest.mark.asyncio
    async def test_country_none_same_as_omitted(self):
        """country=None should produce the same query as not passing country."""
        pool1, conn1 = _fake_pool()
        pool2, conn2 = _fake_pool()
        repo1 = VectorRepository(pool1)
        repo2 = VectorRepository(pool2)

        emb = _random_embedding()
        await repo1.search_similar(emb, top_k=5)
        await repo2.search_similar(emb, top_k=5, country=None)

        sql1 = conn1.fetch.call_args[0][0]
        sql2 = conn2.fetch.call_args[0][0]
        assert sql1 == sql2
