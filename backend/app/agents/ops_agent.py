"""Volunteer/Organizer Ops Agent — incident structuring + shift summaries.

Converts free-text incident notes into structured IncidentReports via
Gemini structured output, and generates end-of-shift summaries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ..models.context import UserContext
from ..models.schemas import IncidentReport
from ..services.gemini_client import generate_json, generate_text
from ..services.input_sanitizer import sanitize_input
from ..services.repository import RepositoryInterface, get_repository

logger = logging.getLogger(__name__)

_INCIDENT_SYSTEM = """You are a stadium incident report assistant for FIFA World Cup 2026.

Convert this free-text incident note into a structured report.

Note: "{note}"
Reporter role: {role}
Reporter zone: {zone}

Respond in JSON:
{{
  "category": "one of: security, medical, maintenance, crowd_control, lost_child, accessibility, other",
  "priority": "one of: low, medium, high, critical",
  "description": "A clear, concise description of the incident",
  "suggested_action": "A concrete action to resolve this"
}}"""

_SHIFT_SUMMARY_SYSTEM = """You are an operations shift-summary writer for FIFA World Cup 2026.

Given these incidents from the current shift, write a concise briefing for
the incoming shift team. Keep it under 200 words, professional but warm.

Incidents:
{incidents}

Respond in {language}. Include:
1. Total incident count by category
2. Key ongoing issues (unresolved incidents)
3. Positive highlights if any
4. Handoff notes for the next team"""


class OpsAgent:
    """Structured incident reports + shift summaries.

    Usage::

        agent = OpsAgent()
        report = await agent.create_incident(context, "Fight near Gate 2")
        summary = await agent.shift_summary(context, shift_start)
    """

    def __init__(self, repo: RepositoryInterface | None = None) -> None:
        self._repo = repo or get_repository()

    async def create_incident(
        self,
        context: UserContext,
        note: str,
    ) -> IncidentReport:
        """Convert a free-text note into a structured incident report.

        Parameters
        ----------
        context:
            The reporter's context.
        note:
            Free-text incident description.

        Returns
        -------
        IncidentReport
            Structured, validated incident report.
        """
        clean_note = sanitize_input(note)
        zone = context.current_location_node or "unknown"

        prompt = _INCIDENT_SYSTEM.format(
            note=clean_note,
            role=context.role,
            zone=zone,
        )

        result = await generate_json(prompt, temperature=0.2)

        if result:
            report = IncidentReport(
                category=result.get("category", "other"),
                priority=result.get("priority", "medium"),
                description=result.get("description", clean_note),
                suggested_action=result.get("suggested_action", "Investigate and assess."),
                zone=zone,
            )
        else:
            # Fallback: store raw note with default classification
            report = IncidentReport(
                category="other",
                priority="medium",
                description=clean_note,
                suggested_action="Investigate and assess.",
                zone=zone,
            )

        await self._repo.save_incident(report)
        logger.info(
            "Incident created: %s (priority=%s, category=%s)",
            report.incident_id,
            report.priority,
            report.category,
        )
        return report

    async def get_incidents(
        self, resolved: Optional[bool] = None
    ) -> list[IncidentReport]:
        """List incidents, optionally filtered by status."""
        return await self._repo.get_incidents(resolved=resolved)

    async def resolve_incident(self, incident_id: str) -> None:
        """Mark an incident as resolved."""
        await self._repo.update_incident(incident_id, resolved=True)

    async def shift_summary(
        self,
        context: UserContext,
        shift_start: datetime,
    ) -> str:
        """Generate a natural-language shift summary.

        Parameters
        ----------
        context:
            The requesting organizer's context.
        shift_start:
            When the current shift began.

        Returns
        -------
        str
            A concise shift briefing.
        """
        incidents = await self._repo.get_incidents_for_shift(shift_start)

        if not incidents:
            return "No incidents logged during this shift. All clear! ✅"

        incidents_text = "\n".join(
            f"- [{i.priority.upper()}] {i.category}: {i.description} "
            f"(zone: {i.zone}, resolved: {i.resolved})"
            for i in incidents
        )

        prompt = _SHIFT_SUMMARY_SYSTEM.format(
            incidents=incidents_text,
            language=context.language,
        )

        summary = await generate_text(prompt, temperature=0.4)
        if summary:
            return summary

        # Fallback: simple count-based summary
        total = len(incidents)
        unresolved = sum(1 for i in incidents if not i.resolved)
        critical = sum(1 for i in incidents if i.priority == "critical")

        return (
            f"📋 Shift summary: {total} incidents logged, "
            f"{unresolved} unresolved, {critical} critical. "
            f"Please review the incident log for details."
        )
