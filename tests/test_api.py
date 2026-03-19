"""
Observer Test Suite - API Endpoint Tests
=======================================
Tests for FastAPI routes using TestClient.

Uses the test database with patched deps module.
"""

import pytest
from tests.conftest import make_signal_data


# ======================================================================
# Health & basic endpoints
# ======================================================================

class TestHealthEndpoints:

    def test_health_check(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"

    def test_root_returns_html(self, client):
        resp = client.get("/")
        # Main dashboard page should return HTML
        assert resp.status_code in (200, 307)


# ======================================================================
# Signal (intelligence) endpoints
# ======================================================================

class TestSignalEndpoints:

    def test_get_intelligence_empty(self, client):
        resp = client.get("/api/v1/intelligence")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_get_intelligence_with_data(self, client, intel_db, event_loop):
        event_loop.run_until_complete(
            intel_db.insert_final_signal(make_signal_data())
        )
        resp = client.get("/api/v1/intelligence")
        assert resp.status_code == 200


# ======================================================================
# Metrics endpoints
# ======================================================================

class TestMetricsEndpoints:

    def test_ai_metrics(self, client):
        resp = client.get("/api/v1/metrics/ai")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ======================================================================
# Feed registry endpoints
# ======================================================================

class TestFeedRegistryEndpoints:

    def test_get_feed_stats(self, client):
        resp = client.get("/api/v1/feeds/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_groups" in data
        assert "total_feeds" in data

    def test_get_feed_health(self, client):
        resp = client.get("/api/v1/feeds/health")
        assert resp.status_code == 200


# ======================================================================
# Scraper endpoints
# ======================================================================

class TestScraperEndpoints:

    def test_list_scraper_sites(self, client):
        resp = client.get("/api/v1/scraper/sites")
        assert resp.status_code == 200
        data = resp.json()
        assert "sites" in data
        assert "stats" in data

    def test_scraper_stats(self, client):
        resp = client.get("/api/v1/scraper/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_sites" in data


# ======================================================================
# Debug endpoints
# ======================================================================

class TestDebugEndpoints:

    def test_pipeline_debug(self, client):
        resp = client.get("/api/v1/debug/pipeline")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
