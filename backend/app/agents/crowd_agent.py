"""Crowd Intelligence Agent — simulated zone occupancy with threshold alerting.

This agent owns:
* A simulated occupancy data store (seeded per zone, varies over time)
* Traffic-light status classification (green / yellow / red)
* History recording for the Surge Forecaster to consume

The Surge Forecaster (``surge_forecaster.py``) builds *on top of* this
agent's data rather than duplicating state.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

from ..models.context import UserContext
from ..models.schemas import CrowdStatusResponse, ZoneStatus
from ..services.repository import RepositoryInterface, get_repository

logger = logging.getLogger(__name__)

# ── Zone definitions ─────────────────────────────────────────────────
# zone_id → (display_name, max_capacity)

ZONE_DEFINITIONS: dict[str, tuple[str, int]] = {
    "Gate_1": ("Gate 1 (North)", 2000),
    "Gate_2": ("Gate 2 (East)", 2000),
    "Gate_3": ("Gate 3 (Southeast)", 1500),
    "Gate_4": ("Gate 4 (West)", 2000),
    "Gate_5": ("Gate 5 (Northeast)", 1500),
    "Gate_6": ("Gate 6 (Southwest)", 1500),
    "Section_A": ("Section A (North Stand)", 5000),
    "Section_B": ("Section B (NE Stand)", 5000),
    "Section_C": ("Section C (East Stand)", 5000),
    "Section_D": ("Section D (South Stand)", 5000),
    "Section_E": ("Section E (SW Stand)", 5000),
    "Section_F": ("Section F (West Stand)", 5000),
    "Concourse_N": ("North Concourse", 3000),
    "Concourse_E": ("East Concourse", 3000),
    "Concourse_S": ("South Concourse", 3000),
    "Concourse_W": ("West Concourse", 3000),
    "Food_East": ("East Food Court", 800),
    "Food_West": ("West Food Court", 800),
    "Food_North": ("North Food Court", 600),
}


class CrowdAgent:
    """Manages zone occupancy data with simulated real-time updates.

    Usage::

        agent = CrowdAgent()
        await agent.seed_initial_data()      # call once at startup
        status = await agent.get_all_status() # call from API
    """

    def __init__(self, repo: RepositoryInterface | None = None) -> None:
        self._repo = repo or get_repository()
        self._seeded = False

    async def seed_initial_data(self) -> None:
        """Populate all zones with realistic initial occupancy."""
        if self._seeded:
            return

        for zone_id, (name, capacity) in ZONE_DEFINITIONS.items():
            # Seed between 30-75% capacity for demo realism
            initial_pct = random.uniform(0.30, 0.75)
            initial_occ = int(capacity * initial_pct)
            await self._repo.update_zone_occupancy(
                zone_id, initial_occ, capacity, name
            )

        self._seeded = True
        logger.info("Seeded occupancy data for %d zones.", len(ZONE_DEFINITIONS))

    async def simulate_tick(self) -> None:
        """Advance occupancy by a small random delta (call periodically).

        Each zone drifts ±1-5% per tick, with slight upward bias to
        simulate pre-match filling.  Clamped to [0, capacity].
        """
        for zone_id, (name, capacity) in ZONE_DEFINITIONS.items():
            status = await self._repo.get_zone_status(zone_id)
            if status is None:
                continue

            # Random walk with slight upward bias
            delta_pct = random.gauss(0.5, 2.0)  # mean +0.5%, stddev 2%
            delta = int(capacity * delta_pct / 100)
            new_occ = max(0, min(capacity, status.current_occupancy + delta))

            await self._repo.update_zone_occupancy(
                zone_id, new_occ, capacity, name
            )

    async def get_zone_status(self, zone_id: str) -> Optional[ZoneStatus]:
        """Get the current status of a single zone.

        Parameters
        ----------
        zone_id:
            The zone identifier (e.g. ``"Gate_1"``).

        Returns
        -------
        ZoneStatus | None
            Current occupancy snapshot, or None if zone unknown.
        """
        return await self._repo.get_zone_status(zone_id)

    async def get_all_status(self) -> CrowdStatusResponse:
        """Get current occupancy status for all zones.

        Returns
        -------
        CrowdStatusResponse
            All zone snapshots + timestamp.
        """
        zones = await self._repo.get_all_zones()
        return CrowdStatusResponse(
            zones=zones,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_zone_summary(
        self, context: UserContext, zone_id: str | None = None
    ) -> str:
        """Human-readable crowd summary, adapted to user role.

        Parameters
        ----------
        context:
            The requesting user's context (role drives verbosity).
        zone_id:
            Optional specific zone.  If None, summarises all zones.

        Returns
        -------
        str
            Plain-text summary.
        """
        if zone_id:
            status = await self.get_zone_status(zone_id)
            if not status:
                return f"No data available for zone '{zone_id}'."
            return self._format_zone(status, context.role)

        all_status = await self.get_all_status()
        if not all_status.zones:
            return "No crowd data available at this time."

        if context.role == "fan":
            # Fans get a simplified overview
            red_zones = [z for z in all_status.zones if z.status == "red"]
            yellow_zones = [z for z in all_status.zones if z.status == "yellow"]

            parts = []
            if red_zones:
                names = ", ".join(z.zone_name for z in red_zones[:3])
                parts.append(f"🟥 Very busy: {names}")
            if yellow_zones:
                names = ", ".join(z.zone_name for z in yellow_zones[:3])
                parts.append(f"🟧 Moderately busy: {names}")
            if not parts:
                parts.append("🟨 All areas are flowing smoothly!")

            return "\n".join(parts)
        else:
            # Organizers/volunteers get raw data
            lines = []
            for z in sorted(all_status.zones, key=lambda x: x.occupancy_pct, reverse=True):
                icon = {"red": "🟥", "yellow": "🟧", "green": "🟨"}.get(z.status, "⬜")
                lines.append(
                    f"{icon} {z.zone_name}: {z.current_occupancy}/{z.max_capacity} "
                    f"({z.occupancy_pct:.1f}%)"
                )
            return "\n".join(lines)

    async def get_history(
        self, zone_id: str, minutes: int = 30
    ) -> list[tuple[datetime, int]]:
        """Get occupancy history for forecasting.

        Parameters
        ----------
        zone_id:
            Zone to query.
        minutes:
            How far back to look.

        Returns
        -------
        list[tuple[datetime, int]]
            Chronological ``(timestamp, occupancy)`` pairs.
        """
        return await self._repo.get_zone_history(zone_id, minutes)

    # ── Internal ─────────────────────────────────────────────────────

    @staticmethod
    def _format_zone(zone: ZoneStatus, role: str) -> str:
        """Format a single zone's status for display."""
        icon = {"red": "🟥", "yellow": "🟧", "green": "🟨"}.get(zone.status, "⬜")

        if role == "fan":
            level = {
                "red": "very crowded — consider an alternative area",
                "yellow": "moderately busy",
                "green": "plenty of space",
            }.get(zone.status, "unknown")
            return f"{icon} {zone.zone_name} is {level}."

        return (
            f"{icon} {zone.zone_name}: {zone.current_occupancy}/{zone.max_capacity} "
            f"({zone.occupancy_pct:.1f}%) — status: {zone.status.upper()}"
        )

    @staticmethod
    def classify_occupancy(pct: float) -> str:
        """Classify an occupancy percentage into a traffic-light status.

        Parameters
        ----------
        pct:
            Occupancy as a percentage (0-100).

        Returns
        -------
        str
            ``"green"``, ``"yellow"``, or ``"red"``.
        """
        if pct < 60.0:
            return "green"
        if pct < 85.0:
            return "yellow"
        return "red"
