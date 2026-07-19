"""Tests for the Navigation Agent.

Covers:
* Wheelchair fans get step-free paths
* Narration fallback when Gemini is unavailable
* Node resolution (exact, name, category, substring)
* Error responses for invalid locations
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.navigation_agent import NavigationAgent
from app.graph.stadium_graph import StadiumGraph
from app.models.context import UserContext


@pytest.fixture
def nav_agent(graph: StadiumGraph) -> NavigationAgent:
    """NavigationAgent wired to the test graph fixture."""
    return NavigationAgent(graph=graph)


class TestNavigation:
    """Core navigation functionality."""

    @pytest.mark.asyncio
    async def test_basic_navigation(
        self, nav_agent: NavigationAgent, fan_context: UserContext
    ) -> None:
        """Fan at Gate 1 → Section A: correct path computed."""
        with patch(
            "app.agents.navigation_agent.generate_text",
            new_callable=AsyncMock,
            return_value="Head to Section A. ⚽",
        ):
            result = await nav_agent.navigate(fan_context, "Section_A")
            assert not result.get("error")
            assert result["path"] == ["Gate_1", "Concourse_N", "Section_A"]
            assert result["walk_time_seconds"] == 90

    @pytest.mark.asyncio
    async def test_wheelchair_route_avoids_stairs(
        self,
        nav_agent: NavigationAgent,
        wheelchair_fan_context: UserContext,
    ) -> None:
        """Wheelchair fan → Section B avoids stairs-only edges."""
        with patch(
            "app.agents.navigation_agent.generate_text",
            new_callable=AsyncMock,
            return_value="Ruta accesible. ⚽",
        ):
            result = await nav_agent.navigate(
                wheelchair_fan_context, "Section_B"
            )
            assert not result.get("error")
            assert result["wheelchair_safe"] is True
            # Must go via Section_A (step-free), not direct stairs
            assert "Section_A" in result["path"]
            assert result["walk_time_seconds"] == 105  # 60 + 45

    @pytest.mark.asyncio
    async def test_narration_fallback_without_gemini(
        self,
        nav_agent: NavigationAgent,
        fan_context: UserContext,
    ) -> None:
        """When Gemini is unavailable, fallback narration still works."""
        with patch(
            "app.agents.navigation_agent.generate_text",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await nav_agent.navigate(fan_context, "Restroom_North")
            assert not result.get("error")
            assert "⚽" in result["narration"]  # fallback includes emoji
            assert result["walk_time_seconds"] > 0


class TestNodeResolution:
    """Test fuzzy node name resolution."""

    @pytest.mark.asyncio
    async def test_resolve_by_exact_id(
        self, nav_agent: NavigationAgent, fan_context: UserContext
    ) -> None:
        """Exact node ID resolves directly."""
        with patch(
            "app.agents.navigation_agent.generate_text",
            new_callable=AsyncMock,
            return_value="Directions. ⚽",
        ):
            result = await nav_agent.navigate(fan_context, "Medical_Main")
            assert not result.get("error")
            assert result["path"][-1] == "Medical_Main"

    @pytest.mark.asyncio
    async def test_resolve_by_category_keyword(
        self, nav_agent: NavigationAgent, fan_context: UserContext
    ) -> None:
        """Category keywords like 'restroom' resolve to a node."""
        with patch(
            "app.agents.navigation_agent.generate_text",
            new_callable=AsyncMock,
            return_value="Directions. ⚽",
        ):
            result = await nav_agent.navigate(fan_context, "restroom")
            assert not result.get("error")
            assert len(result["path"]) > 0


class TestErrorHandling:
    """Edge cases and error responses."""

    @pytest.mark.asyncio
    async def test_unknown_destination(
        self, nav_agent: NavigationAgent, fan_context: UserContext
    ) -> None:
        """Unknown destination returns error response."""
        result = await nav_agent.navigate(fan_context, "Narnia")
        assert result.get("error") is True

    @pytest.mark.asyncio
    async def test_no_current_location(
        self, nav_agent: NavigationAgent
    ) -> None:
        """No current location → error."""
        ctx = UserContext(
            session_id="no-loc",
            role="fan",
            current_location_node=None,
        )
        result = await nav_agent.navigate(ctx, "Gate_1")
        assert result.get("error") is True


class TestFindNearest:
    """Test the find_nearest helper."""

    def test_nearest_restroom_from_gate_1(
        self, nav_agent: NavigationAgent, fan_context: UserContext
    ) -> None:
        """Nearest restroom from Gate 1 should be Restroom_North."""
        result = nav_agent.find_nearest(fan_context, "restroom")
        assert result is not None
        assert result["node_id"] == "Restroom_North"
        assert result["distance_seconds"] == 60  # 30 + 30

    def test_nearest_with_no_location(
        self, nav_agent: NavigationAgent
    ) -> None:
        """No current location → None."""
        ctx = UserContext(
            session_id="no-loc",
            role="fan",
            current_location_node=None,
        )
        assert nav_agent.find_nearest(ctx, "restroom") is None
