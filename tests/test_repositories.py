"""
Observer Test Suite - Repository Unit Tests
==========================================
Tests for SignalRepository, ReputationRepository, MetricsRepository.

Each test gets a fresh (truncated) database via the autouse clean_tables fixture.
"""

import pytest
from datetime import datetime, timedelta
from tests.conftest import make_signal_data


# ======================================================================
# SignalRepository
# ======================================================================

class TestSignalRepository:

    async def test_insert_and_retrieve_signal(self, signals_repo):
        row = await signals_repo.insert_signal(
            title="Explosion in Beirut port",
            url="https://example.com/beirut",
            source="Reuters",
            location="Beirut",
            relevance_score=80,
            casualties=5,
            risk_indicators=["U", "C"],
        )
        assert row is not None
        assert row["title"] == "Explosion in Beirut port"
        assert row["url"] == "https://example.com/beirut"
        assert row["source"] == "Reuters"
        assert row["relevance_score"] == 80

    async def test_duplicate_url_skipped(self, signals_repo):
        await signals_repo.insert_signal(
            title="First article",
            url="https://example.com/dup",
            source="AP",
        )
        dup = await signals_repo.insert_signal(
            title="Different title, same URL",
            url="https://example.com/dup",
            source="BBC",
        )
        assert dup is None

    async def test_url_exists(self, signals_repo):
        assert await signals_repo.url_exists("https://example.com/nope") is False

        await signals_repo.insert_signal(
            title="Test", url="https://example.com/exists", source="T"
        )
        assert await signals_repo.url_exists("https://example.com/exists") is True

    async def test_find_similar_title(self, signals_repo):
        await signals_repo.insert_signal(
            title="Massive earthquake strikes Turkey causing destruction",
            url="https://example.com/quake1",
            source="AP",
        )
        # Very similar title should match
        found = await signals_repo.find_similar_title(
            "Massive earthquake strikes Turkey causing widespread destruction",
            threshold=0.7,
        )
        assert found is True

        # Completely different title should not match
        found = await signals_repo.find_similar_title(
            "Stock market reaches all-time high today",
            threshold=0.7,
        )
        assert found is False

    async def test_get_signals_time_window(self, signals_repo):
        # Insert a processed signal
        await signals_repo.insert_signal(
            title="Recent event",
            url="https://example.com/recent",
            source="BBC",
            processed=True,
            analysis_mode="SKIPPED",
        )
        signals = await signals_repo.get_signals(time_window="24h", limit=10)
        assert len(signals) == 1
        assert signals[0]["title"] == "Recent event"

    async def test_get_signals_excludes_unprocessed(self, signals_repo):
        await signals_repo.insert_signal(
            title="Unprocessed",
            url="https://example.com/unproc",
            source="T",
            processed=False,
        )
        signals = await signals_repo.get_signals(time_window="24h", limit=10)
        assert len(signals) == 0

    async def test_get_by_id(self, signals_repo):
        row = await signals_repo.insert_signal(
            title="By ID test",
            url="https://example.com/byid",
            source="T",
        )
        fetched = await signals_repo.get_by_id(row["id"])
        assert fetched is not None
        assert fetched["title"] == "By ID test"

        assert await signals_repo.get_by_id(999999) is None

    async def test_insert_final_signal(self, signals_repo):
        data = make_signal_data()
        result = await signals_repo.insert_final_signal(data)
        assert result is not None
        assert result["title"] == data["title"]
        assert result["processed"] is True
        assert result["source_confidence"] == 65

    async def test_insert_final_signal_duplicate(self, signals_repo):
        data = make_signal_data()
        first = await signals_repo.insert_final_signal(data)
        assert first is not None

        second = await signals_repo.insert_final_signal(data)
        assert second is None

    async def test_update_analysis(self, signals_repo):
        row = await signals_repo.insert_signal(
            title="Pending analysis",
            url="https://example.com/pending",
            source="T",
            processed=False,
            analysis_mode="PENDING",
        )
        sid = row["id"]

        updated = await signals_repo.update_analysis(sid, {
            "location": "Kyiv",
            "casualties": 3,
            "risk_indicators": ["U"],
            "relevance_score": 75,
            "source_confidence": 70,
            "author_confidence": 65,
            "analysis_mode": "LOCAL",
            "source_name": "Reuters",
            "author_name": "John Doe",
        })
        assert updated is not None
        assert updated["location"] == "Kyiv"
        assert updated["processed"] is True
        assert updated["relevance_score"] == 75

    async def test_count_unprocessed(self, signals_repo):
        assert await signals_repo.count_unprocessed() == 0

        await signals_repo.insert_signal(
            title="Unproc 1", url="https://example.com/u1", source="T", processed=False
        )
        await signals_repo.insert_signal(
            title="Unproc 2", url="https://example.com/u2", source="T", processed=False
        )
        assert await signals_repo.count_unprocessed() == 2

    async def test_cleanup_old(self, signals_repo, pool):
        # Insert a signal, then backdate it
        row = await signals_repo.insert_signal(
            title="Old signal", url="https://example.com/old", source="T"
        )
        old_date = datetime.now() - timedelta(days=60)
        await pool.execute(
            "UPDATE intel_signals SET created_at = $1 WHERE id = $2",
            old_date, row["id"],
        )
        deleted = await signals_repo.cleanup_old(days=30)
        assert deleted == 1

    async def test_get_recent_titles(self, signals_repo):
        await signals_repo.insert_signal(
            title="Title A", url="https://example.com/a", source="T"
        )
        await signals_repo.insert_signal(
            title="Title B", url="https://example.com/b", source="T"
        )
        titles = await signals_repo.get_recent_titles(hours=1)
        assert "Title A" in titles
        assert "Title B" in titles


# ======================================================================
# ReputationRepository
# ======================================================================

class TestReputationRepository:

    async def test_source_reputation_lifecycle(self, reputation_repo):
        # Initially empty
        assert await reputation_repo.get_source("Reuters") is None

        # First upsert creates the record
        await reputation_repo.upsert_source("Reuters", 80)
        rep = await reputation_repo.get_source("Reuters")
        assert rep is not None
        assert rep["reliability_score"] == 80.0
        assert rep["sample_count"] == 1

        # Second upsert updates via rolling average
        await reputation_repo.upsert_source("Reuters", 60)
        rep = await reputation_repo.get_source("Reuters")
        assert rep["sample_count"] == 2
        assert rep["reliability_score"] == pytest.approx(70.0, abs=0.1)

    async def test_author_reputation_lifecycle(self, reputation_repo):
        assert await reputation_repo.get_author("Jane Doe") is None

        await reputation_repo.upsert_author("Jane Doe", 90)
        rep = await reputation_repo.get_author("Jane Doe")
        assert rep is not None
        assert rep["credibility_score"] == 90.0
        assert rep["sample_count"] == 1

        await reputation_repo.upsert_author("Jane Doe", 70)
        rep = await reputation_repo.get_author("Jane Doe")
        assert rep["sample_count"] == 2
        assert rep["credibility_score"] == pytest.approx(80.0, abs=0.1)

    async def test_upsert_on_conn(self, pool):
        """Test the static upsert_*_on_conn methods used in transactions."""
        from database.repositories.reputation import ReputationRepository

        async with pool.acquire() as conn:
            async with conn.transaction():
                await ReputationRepository.upsert_source_on_conn(conn, "CNN", 75)
                await ReputationRepository.upsert_author_on_conn(conn, "Bob", 85)

        from database.repositories.reputation import ReputationRepository as RR
        repo = RR(pool)
        src = await repo.get_source("CNN")
        assert src is not None and src["reliability_score"] == 75.0
        auth = await repo.get_author("Bob")
        assert auth is not None and auth["credibility_score"] == 85.0


# ======================================================================
# MetricsRepository
# ======================================================================

class TestMetricsRepository:
    pass
