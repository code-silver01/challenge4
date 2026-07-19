"""Repository interface + in-memory implementation.

Design
------
* ``RepositoryInterface`` — abstract base class that defines CRUD for
  sessions, zone occupancy, incidents, volunteers, and lost/found.
* ``InMemoryRepository`` — zero-dependency implementation backed by
  plain Python dicts.  This is the default; the app runs with no
  external DB at all.
* ``get_repository()`` — factory that returns the right implementation
  based on ``Settings.USE_FIRESTORE``.

The Firestore implementation can be added later behind the same
interface — all agents code to ``RepositoryInterface``, never to a
concrete class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Literal

from ..models.context import UserContext
from ..models.schemas import (
    FoundItem,
    IncidentReport,
    LostItem,
    VolunteerProfile,
    ZoneStatus,
)


class RepositoryInterface(ABC):
    """Abstract storage contract for all persistent/shared state."""

    # ── Sessions ─────────────────────────────────────────────────────

    @abstractmethod
    async def save_session(self, context: UserContext) -> None:
        """Persist or update a user session."""

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[UserContext]:
        """Retrieve a session by ID, or None if not found."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Remove a session."""

    # ── Zone Occupancy ───────────────────────────────────────────────

    @abstractmethod
    async def update_zone_occupancy(
        self, zone_id: str, occupancy: int, capacity: int, zone_name: str
    ) -> None:
        """Record a new occupancy reading for a zone."""

    @abstractmethod
    async def get_zone_status(self, zone_id: str) -> Optional[ZoneStatus]:
        """Get the latest status snapshot for a single zone."""

    @abstractmethod
    async def get_all_zones(self) -> list[ZoneStatus]:
        """Get the latest status for every zone."""

    @abstractmethod
    async def get_zone_history(
        self, zone_id: str, minutes: int = 30
    ) -> list[tuple[datetime, int]]:
        """Return ``(timestamp, occupancy)`` tuples for the last *minutes*."""

    # ── Incidents ────────────────────────────────────────────────────

    @abstractmethod
    async def save_incident(self, incident: IncidentReport) -> None:
        """Store a new incident report."""

    @abstractmethod
    async def get_incidents(
        self, resolved: Optional[bool] = None
    ) -> list[IncidentReport]:
        """List incidents, optionally filtered by resolved status."""

    @abstractmethod
    async def get_incidents_for_shift(
        self, since: datetime
    ) -> list[IncidentReport]:
        """All incidents logged since *since* (for shift summaries)."""

    @abstractmethod
    async def update_incident(self, incident_id: str, **updates: object) -> None:
        """Partial update on an incident (e.g. mark resolved)."""

    # ── Volunteers ───────────────────────────────────────────────────

    @abstractmethod
    async def save_volunteer(self, volunteer: VolunteerProfile) -> None:
        """Add or overwrite a volunteer profile."""

    @abstractmethod
    async def get_volunteer(
        self, volunteer_id: str
    ) -> Optional[VolunteerProfile]:
        """Retrieve a single volunteer."""

    @abstractmethod
    async def get_all_volunteers(self) -> list[VolunteerProfile]:
        """List every volunteer in the roster."""

    @abstractmethod
    async def update_volunteer(
        self, volunteer_id: str, **updates: object
    ) -> None:
        """Partial update on a volunteer profile."""

    # ── Lost & Found ─────────────────────────────────────────────────

    @abstractmethod
    async def save_lost_item(self, item: LostItem) -> None:
        """Record a lost-item report."""

    @abstractmethod
    async def save_found_item(self, item: FoundItem) -> None:
        """Record a found-item report."""

    @abstractmethod
    async def get_lost_items(
        self, unmatched_only: bool = True
    ) -> list[LostItem]:
        """List lost items, optionally only those not yet matched."""

    @abstractmethod
    async def get_found_items(
        self, unclaimed_only: bool = True
    ) -> list[FoundItem]:
        """List found items, optionally only those not yet claimed."""

    @abstractmethod
    async def mark_lost_item_matched(self, item_id: str) -> None:
        """Flag a lost item as matched."""

    @abstractmethod
    async def mark_found_item_claimed(self, item_id: str) -> None:
        """Flag a found item as claimed."""


# =====================================================================
# In-Memory Implementation
# =====================================================================


def _occupancy_status(pct: float) -> Literal["green", "yellow", "red"]:
    """Map occupancy percentage → traffic-light status."""
    if pct < 60.0:
        return "green"
    if pct < 85.0:
        return "yellow"
    return "red"


class InMemoryRepository(RepositoryInterface):
    """Dict-backed repository — zero setup, zero dependencies.

    Thread-safety note: for the hackathon single-process uvicorn this
    is fine.  In production, swap for ``FirestoreRepository`` or add
    a lock layer.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, UserContext] = {}
        self._zones: dict[str, ZoneStatus] = {}
        self._zone_history: dict[str, list[tuple[datetime, int]]] = {}
        self._incidents: dict[str, IncidentReport] = {}
        self._volunteers: dict[str, VolunteerProfile] = {}
        self._lost_items: dict[str, LostItem] = {}
        self._found_items: dict[str, FoundItem] = {}

    # ── Sessions ─────────────────────────────────────────────────────

    async def save_session(self, context: UserContext) -> None:
        """Store/update a user session in memory."""
        self._sessions[context.session_id] = context

    async def get_session(self, session_id: str) -> Optional[UserContext]:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Remove a session from memory."""
        self._sessions.pop(session_id, None)

    # ── Zone Occupancy ───────────────────────────────────────────────

    async def update_zone_occupancy(
        self, zone_id: str, occupancy: int, capacity: int, zone_name: str
    ) -> None:
        """Record an occupancy reading; maintain rolling history."""
        now = datetime.now(timezone.utc)
        pct = (occupancy / capacity) * 100.0 if capacity > 0 else 0.0

        self._zones[zone_id] = ZoneStatus(
            zone_id=zone_id,
            zone_name=zone_name,
            current_occupancy=occupancy,
            max_capacity=capacity,
            occupancy_pct=round(pct, 1),
            status=_occupancy_status(pct),
            last_updated=now,
        )

        history = self._zone_history.setdefault(zone_id, [])
        history.append((now, occupancy))
        # Keep at most 360 readings (~30 min at 5-sec intervals)
        if len(history) > 360:
            self._zone_history[zone_id] = history[-360:]

    async def get_zone_status(self, zone_id: str) -> Optional[ZoneStatus]:
        """Get the latest status for a single zone."""
        return self._zones.get(zone_id)

    async def get_all_zones(self) -> list[ZoneStatus]:
        """Get the latest status for every zone."""
        return list(self._zones.values())

    async def get_zone_history(
        self, zone_id: str, minutes: int = 30
    ) -> list[tuple[datetime, int]]:
        """Return occupancy history for the last *minutes*."""
        cutoff = datetime.now(timezone.utc).timestamp() - minutes * 60
        return [
            (ts, occ)
            for ts, occ in self._zone_history.get(zone_id, [])
            if ts.timestamp() >= cutoff
        ]

    # ── Incidents ────────────────────────────────────────────────────

    async def save_incident(self, incident: IncidentReport) -> None:
        """Store an incident report."""
        self._incidents[incident.incident_id] = incident

    async def get_incidents(
        self, resolved: Optional[bool] = None
    ) -> list[IncidentReport]:
        """List incidents, optionally filtered by resolved flag."""
        incidents = list(self._incidents.values())
        if resolved is not None:
            incidents = [i for i in incidents if i.resolved == resolved]
        return sorted(incidents, key=lambda i: i.timestamp, reverse=True)

    async def get_incidents_for_shift(
        self, since: datetime
    ) -> list[IncidentReport]:
        """Incidents logged since a given timestamp."""
        return sorted(
            [i for i in self._incidents.values() if i.timestamp >= since],
            key=lambda i: i.timestamp,
        )

    async def update_incident(
        self, incident_id: str, **updates: object
    ) -> None:
        """Partial update on an existing incident."""
        incident = self._incidents.get(incident_id)
        if incident is None:
            return
        data = incident.model_dump()
        data.update(updates)
        self._incidents[incident_id] = IncidentReport(**data)

    # ── Volunteers ───────────────────────────────────────────────────

    async def save_volunteer(self, volunteer: VolunteerProfile) -> None:
        """Add or overwrite a volunteer profile."""
        self._volunteers[volunteer.volunteer_id] = volunteer

    async def get_volunteer(
        self, volunteer_id: str
    ) -> Optional[VolunteerProfile]:
        """Retrieve a single volunteer by ID."""
        return self._volunteers.get(volunteer_id)

    async def get_all_volunteers(self) -> list[VolunteerProfile]:
        """Return the full volunteer roster."""
        return list(self._volunteers.values())

    async def update_volunteer(
        self, volunteer_id: str, **updates: object
    ) -> None:
        """Partial update on a volunteer profile."""
        vol = self._volunteers.get(volunteer_id)
        if vol is None:
            return
        data = vol.model_dump()
        data.update(updates)
        self._volunteers[volunteer_id] = VolunteerProfile(**data)

    # ── Lost & Found ─────────────────────────────────────────────────

    async def save_lost_item(self, item: LostItem) -> None:
        """Record a lost-item report."""
        self._lost_items[item.item_id] = item

    async def save_found_item(self, item: FoundItem) -> None:
        """Record a found-item report."""
        self._found_items[item.item_id] = item

    async def get_lost_items(
        self, unmatched_only: bool = True
    ) -> list[LostItem]:
        """List lost items, optionally only those still unmatched."""
        items = list(self._lost_items.values())
        if unmatched_only:
            items = [i for i in items if not i.matched]
        return sorted(items, key=lambda i: i.timestamp, reverse=True)

    async def get_found_items(
        self, unclaimed_only: bool = True
    ) -> list[FoundItem]:
        """List found items, optionally only those still unclaimed."""
        items = list(self._found_items.values())
        if unclaimed_only:
            items = [i for i in items if not i.claimed]
        return sorted(items, key=lambda i: i.timestamp, reverse=True)

    async def mark_lost_item_matched(self, item_id: str) -> None:
        """Flag a lost item as matched."""
        item = self._lost_items.get(item_id)
        if item:
            data = item.model_dump()
            data["matched"] = True
            self._lost_items[item_id] = LostItem(**data)

    async def mark_found_item_claimed(self, item_id: str) -> None:
        """Flag a found item as claimed."""
        item = self._found_items.get(item_id)
        if item:
            data = item.model_dump()
            data["claimed"] = True
            self._found_items[item_id] = FoundItem(**data)


# ── Factory ──────────────────────────────────────────────────────────

_singleton: RepositoryInterface | None = None


def get_repository() -> RepositoryInterface:
    """Return the application-wide repository instance.

    Uses ``InMemoryRepository`` by default.  When
    ``Settings.USE_FIRESTORE`` is ``True``, this would return a
    ``FirestoreRepository`` instead (same interface).
    """
    global _singleton  # noqa: PLW0603
    if _singleton is None:
        _singleton = InMemoryRepository()
    return _singleton


def reset_repository() -> None:
    """Reset the singleton — used in tests to get a fresh store."""
    global _singleton  # noqa: PLW0603
    _singleton = None
