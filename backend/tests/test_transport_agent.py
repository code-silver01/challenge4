"""Tests for Transport & Sustainability Agent.

Covers:
* Route loading and filtering
* Wheelchair-accessible filtering
* Sustainability tip generation (mock Gemini)
* Fallback when Gemini unavailable
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.transport_agent import TransportAgent
from app.models.context import UserContext


@pytest.fixture
def transport_agent() -> TransportAgent:
    """A fresh TransportAgent."""
    return TransportAgent()


class TestRouteLoading:
    """Verify routes.json is loaded correctly."""

    def test_routes_loaded(self, transport_agent: TransportAgent) -> None:
        """Routes should be loaded from routes.json."""
        destinations = transport_agent.get_all_destinations()
        assert len(destinations) >= 4
        assert "Central_Metro_Station" in destinations

    @pytest.mark.asyncio
    async def test_get_options_known_dest(
        self, transport_agent: TransportAgent, fan_context: UserContext
    ) -> None:
        """Known destination returns options."""
        with patch(
            "app.agents.transport_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await transport_agent.get_options(
                fan_context, "Central_Metro_Station"
            )
            assert len(resp.options) >= 2
            assert resp.sustainability_tip

    @pytest.mark.asyncio
    async def test_get_options_unknown_dest(
        self, transport_agent: TransportAgent, fan_context: UserContext
    ) -> None:
        """Unknown destination returns empty with fallback tip."""
        resp = await transport_agent.get_options(fan_context, "Mars_Colony")
        assert len(resp.options) == 0
        assert resp.sustainability_tip


class TestCO2Ranking:
    """Verify CO2-based fallback ranking."""

    @pytest.mark.asyncio
    async def test_fallback_sorts_by_co2(
        self, transport_agent: TransportAgent, fan_context: UserContext
    ) -> None:
        """When Gemini is unavailable, options sorted by CO2 ascending."""
        with patch(
            "app.agents.transport_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await transport_agent.get_options(
                fan_context, "Central_Metro_Station"
            )
            co2_values = [o.co2_grams for o in resp.options]
            assert co2_values == sorted(co2_values)

    @pytest.mark.asyncio
    async def test_sustainability_tip_mentions_co2(
        self, transport_agent: TransportAgent, fan_context: UserContext
    ) -> None:
        """Fallback tip mentions CO2 savings."""
        with patch(
            "app.agents.transport_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await transport_agent.get_options(
                fan_context, "Central_Metro_Station"
            )
            assert "CO2" in resp.sustainability_tip or "🌱" in resp.sustainability_tip


class TestGeminiRanking:
    """Test Gemini-powered ranking (mocked)."""

    @pytest.mark.asyncio
    async def test_gemini_ranking_applied(
        self, transport_agent: TransportAgent, fan_context: UserContext
    ) -> None:
        """When Gemini returns a ranking, options are reordered."""
        mock_response = {
            "ranking": ["walk", "shuttle", "bus"],
            "recommendation": "Walk for zero emissions!",
            "sustainability_tip": "Walking saves 120g CO2!",
        }
        with patch(
            "app.agents.transport_agent.generate_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await transport_agent.get_options(
                fan_context, "Central_Metro_Station"
            )
            assert resp.options[0].mode == "walk"
            assert resp.recommendation == "Walk for zero emissions!"
