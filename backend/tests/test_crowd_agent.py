"""Tests for the Crowd Intelligence Agent.

Covers:
* Threshold classification (green/yellow/red)
* Occupancy updates and history recording
* Role-based summary formatting
* Seeding and simulation
"""

from __future__ import annotations

import pytest

from app.agents.crowd_agent import CrowdAgent
from app.models.context import UserContext
from app.services.repository import InMemoryRepository


@pytest.fixture
def crowd_agent(repository: InMemoryRepository) -> CrowdAgent:
    """CrowdAgent with a fresh in-memory repository."""
    return CrowdAgent(repo=repository)


class TestThresholdClassification:
    """Verify the green/yellow/red traffic-light logic."""

    def test_green_below_60(self) -> None:
        assert CrowdAgent.classify_occupancy(0.0) == "green"
        assert CrowdAgent.classify_occupancy(30.0) == "green"
        assert CrowdAgent.classify_occupancy(59.9) == "green"

    def test_yellow_60_to_85(self) -> None:
        assert CrowdAgent.classify_occupancy(60.0) == "yellow"
        assert CrowdAgent.classify_occupancy(75.0) == "yellow"
        assert CrowdAgent.classify_occupancy(84.9) == "yellow"

    def test_red_above_85(self) -> None:
        assert CrowdAgent.classify_occupancy(85.0) == "red"
        assert CrowdAgent.classify_occupancy(100.0) == "red"


class TestOccupancyUpdates:
    """Verify occupancy recording and retrieval."""

    @pytest.mark.asyncio
    async def test_update_and_get_zone(
        self, crowd_agent: CrowdAgent, repository: InMemoryRepository
    ) -> None:
        """Update a zone and verify retrieval."""
        await repository.update_zone_occupancy("Gate_1", 1500, 2000, "Gate 1")
        status = await crowd_agent.get_zone_status("Gate_1")
        assert status is not None
        assert status.current_occupancy == 1500
        assert status.max_capacity == 2000
        assert status.occupancy_pct == 75.0
        assert status.status == "yellow"

    @pytest.mark.asyncio
    async def test_unknown_zone_returns_none(
        self, crowd_agent: CrowdAgent
    ) -> None:
        """Querying an unseeded zone returns None."""
        status = await crowd_agent.get_zone_status("Nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_history_recorded(
        self, crowd_agent: CrowdAgent, repository: InMemoryRepository
    ) -> None:
        """Multiple updates create history entries."""
        for occ in [500, 600, 700]:
            await repository.update_zone_occupancy("Gate_1", occ, 2000, "Gate 1")
        history = await crowd_agent.get_history("Gate_1")
        assert len(history) == 3
        occupancies = [occ for _, occ in history]
        assert occupancies == [500, 600, 700]


class TestSeedAndSimulate:
    """Verify seeding and simulation ticks."""

    @pytest.mark.asyncio
    async def test_seed_populates_all_zones(
        self, crowd_agent: CrowdAgent
    ) -> None:
        """Seeding should create status for all defined zones."""
        await crowd_agent.seed_initial_data()
        all_status = await crowd_agent.get_all_status()
        assert len(all_status.zones) > 0

    @pytest.mark.asyncio
    async def test_simulate_tick_changes_occupancy(
        self, crowd_agent: CrowdAgent
    ) -> None:
        """A simulation tick should change at least some zone values."""
        await crowd_agent.seed_initial_data()
        before = await crowd_agent.get_all_status()
        before_map = {z.zone_id: z.current_occupancy for z in before.zones}

        await crowd_agent.simulate_tick()
        after = await crowd_agent.get_all_status()
        after_map = {z.zone_id: z.current_occupancy for z in after.zones}

        # At least some zones should have changed
        changes = sum(
            1
            for zid in before_map
            if before_map[zid] != after_map.get(zid, before_map[zid])
        )
        assert changes > 0


class TestRoleBasedSummary:
    """Verify fan vs organizer output formatting."""

    @pytest.mark.asyncio
    async def test_fan_gets_simplified_summary(
        self,
        crowd_agent: CrowdAgent,
        repository: InMemoryRepository,
        fan_context: UserContext,
    ) -> None:
        """Fans see plain-language crowd status (no raw numbers)."""
        await repository.update_zone_occupancy("Gate_1", 1800, 2000, "Gate 1")
        summary = await crowd_agent.get_zone_summary(fan_context, "Gate_1")
        assert "🟥" in summary  # red zone indicator
        assert "Gate 1" in summary

    @pytest.mark.asyncio
    async def test_organizer_gets_raw_numbers(
        self,
        crowd_agent: CrowdAgent,
        repository: InMemoryRepository,
        organizer_context: UserContext,
    ) -> None:
        """Organizers see occupancy numbers and percentages."""
        await repository.update_zone_occupancy("Gate_1", 1200, 2000, "Gate 1")
        summary = await crowd_agent.get_zone_summary(organizer_context, "Gate_1")
        assert "1200" in summary
        assert "2000" in summary
        assert "60.0%" in summary
