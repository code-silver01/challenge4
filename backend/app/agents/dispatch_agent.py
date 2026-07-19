"""Smart Volunteer Dispatch Agent — proximity + workload reasoning.

When a new incident is logged, this agent:
1. Examines the volunteer roster (skills, zone, current workload)
2. Uses Gemini to reason about the best pick (not just nearest)
3. Drafts a short dispatch message
4. Logs the reasoning so organizers can trust or override
"""

from __future__ import annotations

import logging
from typing import Optional

from ..models.context import UserContext
from ..models.schemas import DispatchRecommendation, IncidentReport, VolunteerProfile
from ..services.gemini_client import generate_json
from ..services.repository import RepositoryInterface, get_repository

logger = logging.getLogger(__name__)

_DISPATCH_SYSTEM = """You are a volunteer dispatch optimizer for FIFA World Cup 2026.

An incident has been reported. Choose the BEST volunteer to dispatch.

Incident:
- Category: {category}
- Priority: {priority}
- Description: {description}
- Zone: {zone}

Available volunteers:
{volunteers_text}

IMPORTANT: Consider BOTH zone proximity AND current workload. Don't just pick the nearest volunteer — a nearby volunteer with 5 open incidents is worse than a slightly farther one with 0.

Respond in JSON:
{{
  "recommended_volunteer_id": "the volunteer_id of the best pick",
  "reasoning": "2-3 sentences explaining WHY this volunteer was chosen, covering both proximity and workload factors",
  "dispatch_message": "A short, friendly dispatch message to send to the volunteer in {language} (e.g., 'Hi Priya, there's a [category] issue at [zone] — could you head there? Details: ...')",
  "confidence": 0.0 to 1.0
}}"""


class DispatchAgent:
    """Smart volunteer dispatch with transparent reasoning.

    Usage::

        agent = DispatchAgent()
        rec = await agent.recommend(context, incident)
    """

    def __init__(self, repo: RepositoryInterface | None = None) -> None:
        self._repo = repo or get_repository()

    async def recommend(
        self,
        context: UserContext,
        incident: IncidentReport,
    ) -> Optional[DispatchRecommendation]:
        """Recommend the best volunteer for an incident.

        Parameters
        ----------
        context:
            The requesting organizer's context.
        incident:
            The incident that needs a volunteer.

        Returns
        -------
        DispatchRecommendation | None
            Recommendation with reasoning, or None if no volunteers.
        """
        volunteers = await self._repo.get_all_volunteers()
        available = [v for v in volunteers if not v.on_break]

        if not available:
            logger.warning("No available volunteers for dispatch.")
            return None

        # Try Gemini for intelligent dispatch
        rec = await self._dispatch_with_gemini(
            context, incident, available
        )
        if rec:
            # Update volunteer workload
            await self._repo.update_volunteer(
                rec.recommended_volunteer_id,
                open_incident_count=self._get_volunteer_oic(
                    available, rec.recommended_volunteer_id
                ) + 1,
            )
            # Assign to incident
            await self._repo.update_incident(
                incident.incident_id,
                assigned_volunteer_id=rec.recommended_volunteer_id,
            )
            return rec

        # Fallback: rules-based dispatch
        return await self._rules_dispatch(context, incident, available)

    async def get_roster(self) -> list[VolunteerProfile]:
        """Return the current volunteer roster."""
        return await self._repo.get_all_volunteers()

    # ── Internal ─────────────────────────────────────────────────────

    async def _dispatch_with_gemini(
        self,
        context: UserContext,
        incident: IncidentReport,
        volunteers: list[VolunteerProfile],
    ) -> Optional[DispatchRecommendation]:
        """Use Gemini to pick the best volunteer with reasoning."""
        vol_text = "\n".join(
            f"- ID: {v.volunteer_id}, Name: {v.name}, Zone: {v.current_zone}, "
            f"Skills: {', '.join(v.skills)}, Open incidents: {v.open_incident_count}, "
            f"Total handled: {v.incidents_handled}"
            for v in volunteers
        )

        prompt = _DISPATCH_SYSTEM.format(
            category=incident.category,
            priority=incident.priority,
            description=incident.description,
            zone=incident.zone or "unknown",
            volunteers_text=vol_text,
            language=context.language,
        )

        result = await generate_json(prompt, temperature=0.2)

        if result and "recommended_volunteer_id" in result:
            vol_id = result["recommended_volunteer_id"]
            vol = next(
                (v for v in volunteers if v.volunteer_id == vol_id), None
            )
            if vol:
                return DispatchRecommendation(
                    incident_id=incident.incident_id,
                    recommended_volunteer_id=vol_id,
                    volunteer_name=vol.name,
                    reasoning=result.get("reasoning", "Selected by AI."),
                    dispatch_message=result.get(
                        "dispatch_message",
                        f"Please head to {incident.zone} for a {incident.category} issue.",
                    ),
                    confidence=min(1.0, max(0.0, result.get("confidence", 0.7))),
                )

        return None

    async def _rules_dispatch(
        self,
        context: UserContext,
        incident: IncidentReport,
        volunteers: list[VolunteerProfile],
    ) -> Optional[DispatchRecommendation]:
        """Fallback: score volunteers by zone match + workload."""
        if not volunteers:
            return None

        scored: list[tuple[float, VolunteerProfile]] = []
        for vol in volunteers:
            score = 0.0
            # Zone match bonus
            if vol.current_zone == incident.zone:
                score += 50.0
            # Skill match bonus
            if incident.category in vol.skills:
                score += 30.0
            # Workload penalty (fewer open incidents = better)
            score -= vol.open_incident_count * 15.0
            scored.append((score, vol))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_vol = scored[0]

        reasoning = (
            f"Rules-based selection: {best_vol.name} was chosen based on "
            f"zone match ({'yes' if best_vol.current_zone == incident.zone else 'no'}), "
            f"skill match, and workload ({best_vol.open_incident_count} open incidents)."
        )

        # Update workload
        await self._repo.update_volunteer(
            best_vol.volunteer_id,
            open_incident_count=best_vol.open_incident_count + 1,
        )
        await self._repo.update_incident(
            incident.incident_id,
            assigned_volunteer_id=best_vol.volunteer_id,
        )

        return DispatchRecommendation(
            incident_id=incident.incident_id,
            recommended_volunteer_id=best_vol.volunteer_id,
            volunteer_name=best_vol.name,
            reasoning=reasoning,
            dispatch_message=(
                f"Hi {best_vol.name}, please head to {incident.zone or 'the reported area'} "
                f"for a {incident.category} issue: {incident.description}"
            ),
            confidence=0.6,
        )

    @staticmethod
    def _get_volunteer_oic(
        volunteers: list[VolunteerProfile], vol_id: str
    ) -> int:
        """Get a volunteer's open incident count."""
        for v in volunteers:
            if v.volunteer_id == vol_id:
                return v.open_incident_count
        return 0
