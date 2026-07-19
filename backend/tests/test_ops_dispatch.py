"""Tests for Ops Agent + Dispatch Agent.

Covers:
* Incident schema validation
* Shift summary generation
* Dispatch considers workload not just proximity
* No-available-volunteers edge case
* Skill-matching logic
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.dispatch_agent import DispatchAgent
from app.agents.ops_agent import OpsAgent
from app.models.context import UserContext
from app.models.schemas import IncidentReport, VolunteerProfile
from app.services.repository import InMemoryRepository


@pytest.fixture
def ops_agent(repository: InMemoryRepository) -> OpsAgent:
    return OpsAgent(repo=repository)


@pytest.fixture
def dispatch_agent(repository: InMemoryRepository) -> DispatchAgent:
    return DispatchAgent(repo=repository)


# ── Ops Agent ────────────────────────────────────────────────────────


class TestOpsAgent:
    """Incident structuring and shift summaries."""

    @pytest.mark.asyncio
    async def test_create_incident_with_gemini(
        self,
        ops_agent: OpsAgent,
        volunteer_context: UserContext,
    ) -> None:
        """Gemini structures an incident from free text."""
        mock_result = {
            "category": "security",
            "priority": "high",
            "description": "Verbal altercation near Gate 2",
            "suggested_action": "Send security personnel",
        }
        with patch(
            "app.agents.ops_agent.generate_json",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            report = await ops_agent.create_incident(
                volunteer_context, "Fight breaking out near gate 2"
            )
            assert report.category == "security"
            assert report.priority == "high"
            assert report.incident_id

    @pytest.mark.asyncio
    async def test_create_incident_fallback(
        self,
        ops_agent: OpsAgent,
        volunteer_context: UserContext,
    ) -> None:
        """Without Gemini, incident stored with default classification."""
        with patch(
            "app.agents.ops_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            report = await ops_agent.create_incident(
                volunteer_context, "Spill in the food court"
            )
            assert report.category == "other"
            assert report.priority == "medium"
            assert "Spill in the food court" in report.description

    @pytest.mark.asyncio
    async def test_shift_summary_no_incidents(
        self,
        ops_agent: OpsAgent,
        organizer_context: UserContext,
    ) -> None:
        """Empty shift → clear message."""
        summary = await ops_agent.shift_summary(
            organizer_context, datetime.now(timezone.utc)
        )
        assert "No incidents" in summary or "All clear" in summary

    @pytest.mark.asyncio
    async def test_resolve_incident(
        self,
        ops_agent: OpsAgent,
        volunteer_context: UserContext,
    ) -> None:
        """Resolving an incident marks it as resolved."""
        with patch(
            "app.agents.ops_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            report = await ops_agent.create_incident(
                volunteer_context, "Broken seat"
            )
            await ops_agent.resolve_incident(report.incident_id)
            incidents = await ops_agent.get_incidents(resolved=True)
            assert any(i.incident_id == report.incident_id for i in incidents)


# ── Dispatch Agent ───────────────────────────────────────────────────

async def _seed_volunteers(repo: InMemoryRepository) -> list[VolunteerProfile]:
    """Seed 3 volunteers with different zones and workloads."""
    now = datetime.now(timezone.utc)
    volunteers = [
        VolunteerProfile(
            volunteer_id="v1", name="Alice", skills=["security", "crowd_control"],
            current_zone="Gate_1", open_incident_count=0,
            shift_start=now - timedelta(hours=1), incidents_handled=2,
        ),
        VolunteerProfile(
            volunteer_id="v2", name="Bob", skills=["medical", "accessibility"],
            current_zone="Gate_1", open_incident_count=5,
            shift_start=now - timedelta(hours=3), incidents_handled=8,
        ),
        VolunteerProfile(
            volunteer_id="v3", name="Carlos", skills=["security", "maintenance"],
            current_zone="Concourse_E", open_incident_count=1,
            shift_start=now - timedelta(hours=2), incidents_handled=3,
        ),
    ]
    for v in volunteers:
        await repo.save_volunteer(v)
    return volunteers


class TestDispatchAgent:
    """Smart volunteer dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_considers_workload(
        self,
        dispatch_agent: DispatchAgent,
        repository: InMemoryRepository,
        organizer_context: UserContext,
    ) -> None:
        """Dispatch should prefer low-workload volunteers over high."""
        await _seed_volunteers(repository)

        incident = IncidentReport(
            category="security",
            priority="high",
            description="Unauthorized entry attempt",
            suggested_action="Investigate",
            zone="Gate_1",
        )
        await repository.save_incident(incident)

        with patch(
            "app.agents.dispatch_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,  # Force fallback
        ):
            rec = await dispatch_agent.recommend(organizer_context, incident)
            assert rec is not None
            # Alice (v1) is at Gate_1 with 0 open incidents
            # Bob (v2) is at Gate_1 with 5 open incidents
            # Rules-based should pick Alice (same zone, lower workload)
            assert rec.recommended_volunteer_id == "v1"
            assert rec.reasoning
            assert rec.dispatch_message

    @pytest.mark.asyncio
    async def test_no_volunteers_returns_none(
        self,
        dispatch_agent: DispatchAgent,
        organizer_context: UserContext,
    ) -> None:
        """No available volunteers → None."""
        incident = IncidentReport(
            category="medical",
            priority="critical",
            description="Injury",
            suggested_action="Help",
            zone="Gate_1",
        )
        rec = await dispatch_agent.recommend(organizer_context, incident)
        assert rec is None

    @pytest.mark.asyncio
    async def test_dispatch_with_gemini(
        self,
        dispatch_agent: DispatchAgent,
        repository: InMemoryRepository,
        organizer_context: UserContext,
    ) -> None:
        """Gemini-based dispatch returns structured recommendation."""
        await _seed_volunteers(repository)

        incident = IncidentReport(
            category="medical",
            priority="high",
            description="Fan feeling faint",
            suggested_action="Medical assistance",
            zone="Concourse_E",
        )
        await repository.save_incident(incident)

        mock_result = {
            "recommended_volunteer_id": "v3",
            "reasoning": "Carlos is closest to Concourse_E and has low workload.",
            "dispatch_message": "Carlos, please head to Concourse E.",
            "confidence": 0.85,
        }
        with patch(
            "app.agents.dispatch_agent.generate_json",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            rec = await dispatch_agent.recommend(organizer_context, incident)
            assert rec is not None
            assert rec.recommended_volunteer_id == "v3"
            assert rec.confidence == 0.85
