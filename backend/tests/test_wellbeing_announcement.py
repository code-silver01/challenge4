"""Tests for Wellbeing Agent + Announcement Agent.

Covers:
* Fatigue threshold classification
* Nudge generation (mock Gemini)
* Edge cases (just started, on break)
* Announcement in all 5 languages (mock Gemini)
* Announcement fallback
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.announcement_agent import AnnouncementAgent
from app.agents.wellbeing_agent import WellbeingAgent
from app.models.context import UserContext
from app.models.schemas import AnnouncementRequest, VolunteerProfile
from app.services.repository import InMemoryRepository


# ── Wellbeing ────────────────────────────────────────────────────────

@pytest.fixture
def wellbeing_agent(repository: InMemoryRepository) -> WellbeingAgent:
    return WellbeingAgent(repo=repository)


def _make_volunteer(
    hours_ago: float = 1.0,
    incidents: int = 0,
    on_break: bool = False,
) -> VolunteerProfile:
    """Create a volunteer with parametrised shift duration."""
    return VolunteerProfile(
        volunteer_id="v1",
        name="Priya",
        skills=["security"],
        current_zone="Gate_1",
        shift_start=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        incidents_handled=incidents,
        on_break=on_break,
    )


class TestFatigueClassification:
    """Verify threshold logic."""

    def test_no_fatigue_below_thresholds(self) -> None:
        """Short shift, few incidents → None."""
        result = WellbeingAgent._classify_fatigue(1.0, 2)
        assert result is None

    def test_caution_level(self) -> None:
        """3+ hours → caution."""
        result = WellbeingAgent._classify_fatigue(3.0, 2)
        assert result == "caution"

    def test_caution_by_incidents(self) -> None:
        """6+ incidents → caution even if short shift."""
        result = WellbeingAgent._classify_fatigue(1.0, 6)
        assert result == "caution"

    def test_warning_level(self) -> None:
        """4.5+ hours → warning."""
        result = WellbeingAgent._classify_fatigue(4.5, 5)
        assert result == "warning"

    def test_warning_by_incidents(self) -> None:
        """9+ incidents → warning."""
        result = WellbeingAgent._classify_fatigue(2.0, 9)
        assert result == "warning"

    def test_critical_level(self) -> None:
        """6+ hours → critical."""
        result = WellbeingAgent._classify_fatigue(6.0, 5)
        assert result == "critical"

    def test_critical_by_incidents(self) -> None:
        """12+ incidents → critical."""
        result = WellbeingAgent._classify_fatigue(2.0, 12)
        assert result == "critical"


class TestWellbeingChecks:
    """Integration tests for wellbeing checks."""

    @pytest.mark.asyncio
    async def test_on_break_no_alert(
        self,
        wellbeing_agent: WellbeingAgent,
        organizer_context: UserContext,
    ) -> None:
        """Volunteer on break → no alert."""
        vol = _make_volunteer(hours_ago=5.0, incidents=10, on_break=True)
        with patch(
            "app.agents.wellbeing_agent.generate_text",
            new_callable=AsyncMock,
            return_value=None,
        ):
            alert = await wellbeing_agent.check_volunteer(
                organizer_context, vol
            )
            assert alert is None

    @pytest.mark.asyncio
    async def test_fatigued_volunteer_generates_alert(
        self,
        wellbeing_agent: WellbeingAgent,
        organizer_context: UserContext,
    ) -> None:
        """Tired volunteer → wellbeing alert with nudge."""
        vol = _make_volunteer(hours_ago=5.0, incidents=10)
        with patch(
            "app.agents.wellbeing_agent.generate_text",
            new_callable=AsyncMock,
            return_value=None,
        ):
            alert = await wellbeing_agent.check_volunteer(
                organizer_context, vol
            )
            assert alert is not None
            assert alert.alert_level in ("warning", "critical")
            assert "Priya" in alert.nudge_message

    @pytest.mark.asyncio
    async def test_fallback_nudge_includes_name(
        self,
        wellbeing_agent: WellbeingAgent,
        organizer_context: UserContext,
    ) -> None:
        """Fallback nudge mentions volunteer by name."""
        vol = _make_volunteer(hours_ago=3.5, incidents=7)
        with patch(
            "app.agents.wellbeing_agent.generate_text",
            new_callable=AsyncMock,
            return_value=None,
        ):
            alert = await wellbeing_agent.check_volunteer(
                organizer_context, vol
            )
            assert alert is not None
            assert "Priya" in alert.nudge_message
            assert "🧢" in alert.nudge_message


# ── Announcement Agent ───────────────────────────────────────────────


@pytest.fixture
def announcement_agent() -> AnnouncementAgent:
    return AnnouncementAgent()


class TestAnnouncementAgent:
    """Multilingual PA announcement drafting."""

    @pytest.mark.asyncio
    async def test_all_five_languages_present(
        self,
        announcement_agent: AnnouncementAgent,
        organizer_context: UserContext,
    ) -> None:
        """Gemini produces announcements in all 5 languages."""
        mock_result = {
            "en": "Gate 3 will reopen shortly.",
            "es": "La puerta 3 reabrirá pronto.",
            "fr": "La porte 3 rouvrira bientôt.",
            "pt": "O portão 3 reabrirá em breve.",
            "hi": "गेट 3 जल्द ही फिर से खुलेगा।",
        }
        with patch(
            "app.agents.announcement_agent.generate_json",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            request = AnnouncementRequest(
                situation_note="Gate 3 temporarily closed for security check",
                priority="warning",
            )
            response = await announcement_agent.draft(
                organizer_context, request
            )
            assert len(response.announcements) == 5
            for lang in ("en", "es", "fr", "pt", "hi"):
                assert lang in response.announcements
                assert len(response.announcements[lang]) > 0

    @pytest.mark.asyncio
    async def test_fallback_provides_all_languages(
        self,
        announcement_agent: AnnouncementAgent,
        organizer_context: UserContext,
    ) -> None:
        """Fallback still provides entries for all 5 languages."""
        with patch(
            "app.agents.announcement_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            request = AnnouncementRequest(
                situation_note="Test announcement",
                priority="info",
            )
            response = await announcement_agent.draft(
                organizer_context, request
            )
            assert len(response.announcements) == 5
            assert "Test announcement" in response.announcements["en"]

    @pytest.mark.asyncio
    async def test_urgent_priority_prefix(
        self,
        announcement_agent: AnnouncementAgent,
        organizer_context: UserContext,
    ) -> None:
        """Urgent fallback announcements include attention prefix."""
        with patch(
            "app.agents.announcement_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            request = AnnouncementRequest(
                situation_note="Emergency evacuation",
                priority="urgent",
            )
            response = await announcement_agent.draft(
                organizer_context, request
            )
            assert "⚠️" in response.announcements["en"]
