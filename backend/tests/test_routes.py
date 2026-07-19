"""Integration tests for FastAPI endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.repository import InMemoryRepository


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestRoutes:
    """Integration tests for major endpoints."""

    def test_health_check(self, client: TestClient) -> None:
        """Health check returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_create_session(self, client: TestClient) -> None:
        """Create a new session via POST."""
        response = client.post(
            "/api/session",
            json={
                "role": "fan",
                "language": "es",
                "accessibility_needs": ["wheelchair"]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "fan"
        assert data["language"] == "es"
        assert "wheelchair" in data["accessibility_needs"]
        assert data["session_id"] is not None

    def test_chat_endpoint_rate_limit(self, client: TestClient) -> None:
        """Rate limiter should return 429 after too many requests."""
        # Create session first
        sess_resp = client.post("/api/session", json={"role": "fan"})
        session_id = sess_resp.json()["session_id"]
        
        # Bombard the endpoint
        with patch("app.routes.chat._intent_router.classify", new_callable=AsyncMock) as mock:
            # We use an enum for Intent.GENERAL_QUERY in the real code, so we need to mock it properly
            from app.models.schemas import Intent
            mock.return_value = (Intent.GENERAL_QUERY, {})
            
            status_codes = []
            for _ in range(35):  # default limit is 30
                resp = client.post(
                    "/api/chat",
                    params={"session_id": session_id},
                    json={"session_id": session_id, "message": "hello"},
                )
                status_codes.append(resp.status_code)
                
            assert 429 in status_codes
            assert status_codes.count(200) <= 30

    def test_chat_requires_session(self, client: TestClient) -> None:
        """Missing session parameter returns 422."""
        response = client.post(
            "/api/chat",
            json={"session_id": "invalid", "message": "hello"},
        )
        # It asks for session_id via Depends, but we didn't pass it as a query param
        assert response.status_code in (400, 422, 404)

    def test_get_crowd_status(self, client: TestClient) -> None:
        """Get crowd status for all zones."""
        response = client.get("/api/crowd/status")
        assert response.status_code == 200
        data = response.json()
        assert "zones" in data
        assert "timestamp" in data

    def test_draft_announcement(self, client: TestClient) -> None:
        """Draft announcement via POST."""
        # Create organizer session
        sess_resp = client.post("/api/session", json={"role": "organizer"})
        session_id = sess_resp.json()["session_id"]
        
        with patch("app.agents.announcement_agent.generate_json", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "en": "Test", "es": "Prueba", "fr": "Test", "pt": "Teste", "hi": "टेस्ट"
            }
            
            response = client.post(
                "/api/announcements/draft",
                params={"session_id": session_id},
                json={"situation_note": "Test note", "priority": "info"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "announcements" in data
            assert data["announcements"]["en"] == "Test"
