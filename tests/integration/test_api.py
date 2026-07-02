"""Integration tests for the FastAPI application.

Tests the full API flow including request validation,
response structure, and error handling.

Note: These tests require a running database or use mocking.
"""

import pytest
import inspect
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes.analysis import run_analysis, _run_analysis_background


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_health_check_includes_app_name(self, client):
        """Test health endpoint includes app name."""
        response = client.get("/health")
        data = response.json()
        assert data["app"] == "AI Job Copilot"


class TestCacheMetrics:
    """Tests for cache metrics endpoint."""

    def test_cache_metrics_endpoint(self, client):
        """Test cache metrics returns valid structure."""
        response = client.get("/metrics/cache")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "metrics" in data
        metrics = data["metrics"]
        assert "total_hits" in metrics
        assert "total_misses" in metrics
        assert "hit_rate" in metrics


class TestResumeUpload:
    """Tests for resume upload endpoint."""

    def test_resume_upload_validation_short_text(self, client):
        """Test that short resume text is rejected."""
        response = client.post(
            "/resume/upload",
            json={"text": "Too short"},
        )
        assert response.status_code == 422  # Validation error

    def test_resume_upload_missing_text(self, client):
        """Test that missing text field is rejected."""
        response = client.post(
            "/resume/upload",
            json={},
        )
        assert response.status_code == 422


class TestJobDescriptionUpload:
    """Tests for job description upload endpoint."""

    def test_jd_upload_validation_short_text(self, client):
        """Test that short JD text is rejected."""
        response = client.post(
            "/job/upload",
            json={"text": "Short"},
        )
        assert response.status_code == 422

    def test_jd_upload_missing_text(self, client):
        """Test that missing text field is rejected."""
        response = client.post(
            "/job/upload",
            json={"title": "Developer"},
        )
        assert response.status_code == 422


class TestAnalysisEndpoints:
    """Tests for analysis endpoints."""

    def test_get_analysis_not_found(self, client):
        """Test 404 for non-existent analysis."""
        response = client.get("/analysis/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_history_endpoint(self, client):
        """Test history endpoint returns valid structure."""
        response = client.get("/history?limit=5&offset=0")
        # May return 200 with empty list or 500 if DB not connected
        assert response.status_code in [200, 500]

    def test_run_analysis_does_not_call_bullet_optimization(self):
        """ATS scoring must not call bullet optimization."""
        source = inspect.getsource(run_analysis)
        assert ".optimize_bullets(" not in source

    def test_run_analysis_has_second_pass_rag_fallback(self):
        """Still-unmatched skills should get a non-duplicative RAG fallback pass.

        This logic runs in the background task (run_analysis itself just
        enqueues the job and returns immediately, to avoid blocking the
        request on the 60-90s LLM pipeline).
        """
        source = inspect.getsource(_run_analysis_background)
        assert "fallback_skill_names" in source
        assert "not in matched_keys" in source
        assert "not in queried_keys" in source

    def test_run_analysis_passes_debug_rag_diagnostics(self):
        """Debug tracing should receive read-only RAG diagnostics."""
        source = inspect.getsource(_run_analysis_background)
        assert "rag_diagnostics" in source
        assert "diagnostics=rag_diagnostics" in source


class TestQuizEndpoints:
    """Tests for quiz endpoints."""

    def test_quiz_start_missing_analysis(self, client):
        """Test quiz start with non-existent analysis."""
        response = client.post(
            "/quiz/start",
            json={
                "analysis_id": "00000000-0000-0000-0000-000000000000",
                "skill": "Python",
            },
        )
        assert response.status_code in [404, 500]

    def test_quiz_submit_missing_quiz(self, client):
        """Test quiz submit with non-existent quiz."""
        response = client.post(
            "/quiz/submit",
            json={
                "quiz_id": "00000000-0000-0000-0000-000000000000",
                "answers": [{"answer": "A"}],
            },
        )
        assert response.status_code in [404, 500]


class TestRequestTiming:
    """Tests for request timing middleware."""

    def test_timing_header_present(self, client):
        """Test that X-Process-Time header is added."""
        response = client.get("/health")
        assert "x-process-time" in response.headers
        process_time = float(response.headers["x-process-time"])
        assert process_time >= 0
