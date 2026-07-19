"""UserContext — the central object driving all agent decision-making.

Every agent receives a UserContext and branches its behavior on role,
language, and accessibility needs.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Immutable per-request context that every agent must consult.

    Design rationale
    ----------------
    * ``role`` gates what data the user may see (e.g. organizer → raw
      metrics, fan → plain-language summary).
    * ``accessibility_needs`` constrains physical-path computation
      (wheelchair → step-free only) and frontend rendering (visual
      impairment → high-contrast).
    * ``language`` drives every LLM narration and PA announcement.
    """

    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session identifier.",
    )
    role: Literal["fan", "volunteer", "organizer"] = Field(
        description="Stakeholder role — determines visible features and data granularity.",
    )
    language: str = Field(
        default="en",
        description="ISO 639-1 language code: en, es, fr, pt, hi.",
    )
    accessibility_needs: list[
        Literal["wheelchair", "visual_impairment", "hearing_impairment", "none"]
    ] = Field(
        default=["none"],
        description="Accessibility requirements that constrain navigation and UI.",
    )
    ticket_zone: str | None = Field(
        default=None,
        description="Ticketed seating zone, if applicable.",
    )
    current_location_node: str | None = Field(
        default=None,
        description="Current node ID on the stadium graph.",
    )

    @property
    def needs_wheelchair_access(self) -> bool:
        """Convenience: True when step-free paths are required."""
        return "wheelchair" in self.accessibility_needs

    @property
    def has_visual_impairment(self) -> bool:
        """Convenience: True when high-contrast / screen-reader mode applies."""
        return "visual_impairment" in self.accessibility_needs
