"""
RYBAT Test Suite - Pipeline Integration Tests
===============================================
Tests for IntelligenceService._prepare_article, ArticlePipeline recovery,
and insert_final_signal + reputation upsert.

Uses the real database but mocks external AI services.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from tests.conftest import make_signal_data


# ======================================================================
# IntelligenceService._prepare_article
# ======================================================================

class TestPrepareArticle:

    async def test_prepare_valid_article(self, intel_service):
        article = {
            "title": "Major earthquake in Japan causes devastation",
            "url": "https://example.com/japan-quake",
            "source": "Reuters",
            "description": "A 7.2 magnitude earthquake struck Japan.",
            "collector": "rss",
        }
        translator = MagicMock()
        translator.enabled = False

        result = await intel_service._prepare_article(article, translator)
        assert isinstance(result, dict)
        assert result["title"] == "Major earthquake in Japan causes devastation"
        assert result["url"] == "https://example.com/japan-quake"
        assert result["source_label"] == "Reuters"
        assert result["pre_score"] >= 0

    async def test_prepare_rejects_empty_title(self, intel_service):
        article = {"title": "", "url": "https://example.com/x", "source": "T"}
        result = await intel_service._prepare_article(article, None)
        assert result is None

    async def test_prepare_rejects_empty_url(self, intel_service):
        article = {"title": "Valid title", "url": "", "source": "T"}
        result = await intel_service._prepare_article(article, None)
        assert result is None

    async def test_prepare_detects_duplicate_title(self, intel_service, intel_db):
        # Insert a signal directly
        await intel_db.signals.insert_signal(
            title="Airstrike hits hospital in Gaza",
            url="https://example.com/gaza1",
            source="AP",
        )
        # Very similar title should be flagged as duplicate
        article = {
            "title": "Airstrike hits hospital in Gaza Strip",
            "url": "https://example.com/gaza2",
            "source": "BBC",
            "collector": "rss",
        }
        translator = MagicMock()
        translator.enabled = False

        result = await intel_service._prepare_article(article, translator)
        assert result == "duplicate"

    async def test_prepare_scraper_source_label(self, intel_service):
        article = {
            "title": "Test scraper article",
            "url": "https://example.com/scraper1",
            "source": "AlJazeera",
            "collection_method": "scraper",
            "collector": "np4k",
        }
        translator = MagicMock()
        translator.enabled = False

        result = await intel_service._prepare_article(article, translator)
        assert isinstance(result, dict)
        assert result["source_label"] == "Scraper:AlJazeera"

    async def test_prepare_with_translation(self, intel_service):
        article = {
            "title": "Erdbeben in der Turkei",
            "url": "https://example.com/de-quake",
            "source": "DW",
            "collector": "rss",
        }
        translator = MagicMock()
        translator.enabled = True
        translator.needs_translation.return_value = True

        tr_result = MagicMock()
        tr_result.was_translated = True
        tr_result.text = "Earthquake in Turkey"
        tr_result.source_language = "de"
        tr_result.translation_source = "nllb"
        translator.translate_with_metadata = AsyncMock(return_value=tr_result)

        result = await intel_service._prepare_article(article, translator)
        assert isinstance(result, dict)
        assert result["title"] == "Earthquake in Turkey"
        assert result["is_translated"] is True
        assert result["source_language"] == "de"


# ======================================================================
# Pipeline recovery
# ======================================================================

class TestPipelineRecovery:

    async def test_recover_pending_empty(self, intel_service, intel_db):
        """Recovery with no pending signals should be a no-op."""
        from services.article_pipeline import ArticlePipeline

        pipeline = ArticlePipeline(intel_service, num_workers=1)
        pipeline._intel = intel_service

        # Should not raise
        await pipeline._recover_pending()

    async def test_recover_pending_processes_signals(self, intel_service, intel_db):
        """Recovery should process unprocessed signals."""
        from services.article_pipeline import ArticlePipeline

        # Insert an unprocessed signal
        await intel_db.signals.insert_signal(
            title="Unprocessed recovery test",
            url="https://example.com/recover1",
            source="TestSource",
            processed=False,
            analysis_mode="PENDING",
        )

        count = await intel_db.signals.count_unprocessed()
        assert count == 1

        pipeline = ArticlePipeline(intel_service, num_workers=1)
        pipeline._intel = intel_service

        with patch("services.article_pipeline.manager") as mock_ws:
            mock_ws.broadcast_new_signal = AsyncMock()
            await pipeline._recover_pending()

        # Should now be processed
        count = await intel_db.signals.count_unprocessed()
        assert count == 0


# ======================================================================
# Pipeline insert_final_signal + reputation upsert
# ======================================================================

class TestFinalSignalInsert:

    async def test_insert_final_signal_creates_reputation(self, intel_db):
        """insert_final_signal should also upsert source and author reputation."""
        data = make_signal_data(
            source_name="NewSource",
            author_name="NewAuthor",
            source_confidence=72,
            author_confidence=68,
        )
        result = await intel_db.insert_final_signal(data)
        assert result is not None

        src_rep = await intel_db.get_source_reputation("NewSource")
        assert src_rep is not None
        assert src_rep["reliability_score"] == pytest.approx(72.0, abs=0.1)

        auth_rep = await intel_db.get_author_reputation("NewAuthor")
        assert auth_rep is not None
        assert auth_rep["credibility_score"] == pytest.approx(68.0, abs=0.1)

    async def test_insert_final_signal_no_author(self, intel_db):
        """When author is empty, author reputation should not be created."""
        data = make_signal_data(
            author="",
            author_name="",
            url="https://example.com/no-author",
        )
        result = await intel_db.insert_final_signal(data)
        assert result is not None

        # No author reputation should exist
        auth_rep = await intel_db.get_author_reputation("")
        assert auth_rep is None
