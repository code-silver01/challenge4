"""Pydantic v2 schemas for all API request/response contracts.

Every model here validates and sanitizes data *before* it reaches any
agent or LLM prompt.  Field-level constraints (``max_length``,
``ge``/``le``) enforce limits at the boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Enums ────────────────────────────────────────────────────────────


class Intent(str, Enum):
    """All classifiable intents recognised by the Intent Router Agent."""

    NAVIGATION = "navigation"
    CROWD_STATUS = "crowd_status"
    TRANSPORT = "transport"
    SUSTAINABILITY = "sustainability"
    LOST_FOUND = "lost_found"
    DISPATCH = "dispatch"
    WELLBEING = "wellbeing"
    ANNOUNCEMENT = "announcement"
    MEDICAL_EMERGENCY = "medical_emergency"
    GENERAL_QUERY = "general_query"


# ── Chat ─────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Inbound chat message from a user session."""

    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Reject blank messages and normalise whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message cannot be empty or whitespace-only.")
        return stripped


class ChatResponse(BaseModel):
    """Outbound chat response returned to the frontend."""

    session_id: str
    intent: Intent
    response: str
    data: dict | None = None
    language: str = "en"


# ── Crowd / Zones ────────────────────────────────────────────────────


class ZoneStatus(BaseModel):
    """Real-time occupancy snapshot for a single stadium zone."""

    zone_id: str
    zone_name: str
    current_occupancy: int = Field(ge=0)
    max_capacity: int = Field(gt=0)
    occupancy_pct: float = Field(ge=0.0, le=100.0)
    status: Literal["green", "yellow", "red"]
    last_updated: datetime


class CrowdStatusResponse(BaseModel):
    """Aggregated crowd status across all zones."""

    zones: list[ZoneStatus]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Forecasting ──────────────────────────────────────────────────────


class ForecastResult(BaseModel):
    """Predictive crowd surge forecast for a single zone."""

    zone_id: str
    zone_name: str
    current_occupancy_pct: float = Field(ge=0.0, le=100.0)
    predicted_occupancy_pct: float = Field(ge=0.0)
    minutes_to_capacity: float | None = None
    trend: Literal["rising", "stable", "declining"]
    forecast_message: str
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)


# ── Transport ────────────────────────────────────────────────────────


class RouteOption(BaseModel):
    """A single transport option with time and CO₂ estimates."""

    mode: Literal["shuttle", "metro", "walk", "bus"]
    origin: str
    destination: str
    time_minutes: int = Field(gt=0)
    co2_grams: float = Field(ge=0.0)
    frequency_minutes: int | None = None
    accessibility_notes: str | None = None
    cost: str | None = None


class TransportResponse(BaseModel):
    """Ranked transport options with sustainability tip."""

    options: list[RouteOption]
    recommendation: str
    sustainability_tip: str


# ── Incidents / Ops ──────────────────────────────────────────────────


class IncidentReport(BaseModel):
    """Structured incident report generated from free-text notes."""

    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    priority: Literal["low", "medium", "high", "critical"]
    description: str = Field(..., max_length=2000)
    suggested_action: str
    zone: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved: bool = False
    assigned_volunteer_id: str | None = None


# ── Volunteers ───────────────────────────────────────────────────────


class VolunteerProfile(BaseModel):
    """In-memory/Firestore volunteer roster entry."""

    volunteer_id: str
    name: str
    skills: list[str]
    current_zone: str
    open_incident_count: int = Field(default=0, ge=0)
    shift_start: datetime
    incidents_handled: int = Field(default=0, ge=0)
    on_break: bool = False


class DispatchRecommendation(BaseModel):
    """Smart dispatch recommendation with transparent reasoning."""

    incident_id: str
    recommended_volunteer_id: str
    volunteer_name: str
    reasoning: str
    dispatch_message: str
    confidence: float = Field(ge=0.0, le=1.0)


# ── Lost & Found ─────────────────────────────────────────────────────


class LostItem(BaseModel):
    """Fan-submitted lost item description."""

    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    description: str = Field(..., max_length=500)
    features: dict | None = None  # Extracted by Gemini
    zone_last_seen: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    matched: bool = False


class FoundItem(BaseModel):
    """Volunteer-submitted found item description."""

    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    volunteer_id: str
    description: str = Field(..., max_length=500)
    features: dict | None = None  # Extracted by Gemini
    zone_found: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    claimed: bool = False


class LostFoundMatch(BaseModel):
    """Scored match between a lost item and a found item."""

    lost_item_id: str
    found_item_id: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    match_reasoning: str


# ── Wellbeing ────────────────────────────────────────────────────────


class WellbeingAlert(BaseModel):
    """Fatigue/wellbeing alert for an organizer dashboard."""

    volunteer_id: str
    volunteer_name: str
    shift_duration_hours: float = Field(ge=0.0)
    incidents_handled: int = Field(ge=0)
    alert_level: Literal["caution", "warning", "critical"]
    nudge_message: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── Announcements ───────────────────────────────────────────────────


class AnnouncementRequest(BaseModel):
    """Organizer inputs a situation note to draft PA announcements."""

    situation_note: str = Field(..., min_length=1, max_length=1000)
    priority: Literal["info", "warning", "urgent"] = "info"


class AnnouncementResponse(BaseModel):
    """Multilingual PA announcement drafts (keyed by language code)."""

    announcements: dict[str, str]  # e.g. {"en": "...", "es": "..."}
    priority: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── Session ──────────────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    """Payload sent by the frontend to create or update a session."""

    role: Literal["fan", "volunteer", "organizer"]
    language: str = Field(default="en", max_length=5)
    accessibility_needs: list[
        Literal["wheelchair", "visual_impairment", "hearing_impairment", "none"]
    ] = ["none"]
    ticket_zone: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Normalise and validate supported language codes."""
        supported = {"en", "es", "fr", "pt", "hi"}
        code = v.lower().strip()
        if code not in supported:
            return "en"
        return code


class SessionResponse(BaseModel):
    """Returned after session creation / update."""

    session_id: str
    role: str
    language: str
    accessibility_needs: list[str]
    ticket_zone: str | None = None
