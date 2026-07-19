"""Volunteer Fatigue & Wellbeing Monitor.

Tracks each volunteer's shift duration + incidents handled.  When
thresholds are crossed, generates a human wellbeing nudge for the
organizer dashboard.  This is a genuine worker-welfare feature, not
just an ops metric.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from ..models.context import UserContext
from ..models.schemas import VolunteerProfile, WellbeingAlert
from ..services.gemini_client import generate_text
from ..services.repository import RepositoryInterface, get_repository

logger = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────

FATIGUE_THRESHOLDS = {
    "caution": {"max_hours": 3.0, "max_incidents": 6},
    "warning": {"max_hours": 4.5, "max_incidents": 9},
    "critical": {"max_hours": 6.0, "max_incidents": 12},
}

_WELLBEING_SYSTEM = """You are a compassionate volunteer wellbeing advisor for FIFA World Cup 2026.

A volunteer needs attention. Write a short, caring wellbeing nudge for their organizer.

Volunteer: {name}
Shift duration: {hours:.1f} hours
Incidents handled: {incidents}
Alert level: {level}

Write a 1-2 sentence nudge in {language} that:
- Is warm and human, not robotic
- Frames it as worker welfare, not productivity
- Suggests a specific action (break, rotation, hydration)
- Acknowledges the volunteer's hard work

Example: "Volunteer Priya has handled 9 high-priority incidents in 2.5 hrs — recommend a 15-min rotation and hydration break. She's been amazing today."
"""


class WellbeingAgent:
    """Monitors volunteer fatigue and generates wellbeing nudges.

    Usage::

        agent = WellbeingAgent()
        alerts = await agent.check_all(context)
    """

    def __init__(self, repo: RepositoryInterface | None = None) -> None:
        self._repo = repo or get_repository()

    async def check_volunteer(
        self,
        context: UserContext,
        volunteer: VolunteerProfile,
    ) -> WellbeingAlert | None:
        """Check a single volunteer's fatigue level.

        Parameters
        ----------
        context:
            Organizer context for language.
        volunteer:
            The volunteer to check.

        Returns
        -------
        WellbeingAlert | None
            An alert if thresholds are crossed, else None.
        """
        if volunteer.on_break:
            return None

        hours = self._shift_duration_hours(volunteer)
        level = self._classify_fatigue(hours, volunteer.incidents_handled)

        if level is None:
            return None

        nudge = await self._generate_nudge(
            context, volunteer, hours, level
        )

        return WellbeingAlert(
            volunteer_id=volunteer.volunteer_id,
            volunteer_name=volunteer.name,
            shift_duration_hours=hours,
            incidents_handled=volunteer.incidents_handled,
            alert_level=level,
            nudge_message=nudge,
        )

    async def check_all(
        self, context: UserContext
    ) -> list[WellbeingAlert]:
        """Check all volunteers and return any fatigue alerts.

        Returns
        -------
        list[WellbeingAlert]
            Alerts sorted by severity (critical first).
        """
        volunteers = await self._repo.get_all_volunteers()
        import asyncio
        tasks = [self.check_volunteer(context, vol) for vol in volunteers]
        results = await asyncio.gather(*tasks)
        alerts = [a for a in results if a]

        priority = {"critical": 0, "warning": 1, "caution": 2}
        alerts.sort(key=lambda a: priority.get(a.alert_level, 3))
        return alerts

    # ── Fatigue classification ───────────────────────────────────────

    @staticmethod
    def _shift_duration_hours(volunteer: VolunteerProfile) -> float:
        """Calculate hours since shift start."""
        now = datetime.now(timezone.utc)
        delta = now - volunteer.shift_start
        return delta.total_seconds() / 3600.0

    @staticmethod
    def _classify_fatigue(
        hours: float, incidents: int
    ) -> Literal["caution", "warning", "critical"] | None:
        """Classify fatigue level based on thresholds.

        A volunteer triggers an alert if they exceed EITHER the hours
        OR the incidents threshold for a given level.

        Returns the highest matching level, or None.
        """
        result: Literal["caution", "warning", "critical"] | None = None

        for level in ("caution", "warning", "critical"):
            thresholds = FATIGUE_THRESHOLDS[level]
            if (
                hours >= thresholds["max_hours"]
                or incidents >= thresholds["max_incidents"]
            ):
                result = level  # type: ignore[assignment]

        return result

    # ── Nudge generation ─────────────────────────────────────────────

    async def _generate_nudge(
        self,
        context: UserContext,
        volunteer: VolunteerProfile,
        hours: float,
        level: str,
    ) -> str:
        """Generate a human wellbeing nudge via Gemini."""
        prompt = _WELLBEING_SYSTEM.format(
            name=volunteer.name,
            hours=hours,
            incidents=volunteer.incidents_handled,
            level=level,
            language=context.language,
        )

        nudge = await generate_text(prompt, temperature=0.5)
        if nudge:
            return nudge

        # Fallback: template-based nudge
        return self._fallback_nudge(volunteer, hours, level)

    @staticmethod
    def _fallback_nudge(
        volunteer: VolunteerProfile, hours: float, level: str
    ) -> str:
        """Generate a nudge without the LLM."""
        action = {
            "caution": "a short hydration break",
            "warning": "a 15-minute rest rotation",
            "critical": "immediate relief and a proper break",
        }.get(level, "a break")

        return (
            f"🧢 {volunteer.name} has been on shift for {hours:.1f} hours "
            f"and handled {volunteer.incidents_handled} incidents. "
            f"Recommend {action}. They've been doing great work! 💪"
        )
