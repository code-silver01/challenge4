"""Transport & Sustainability Agent — routes.json + Gemini ranking.

Reads the hand-authored mock transport dataset, filters by
accessibility, and asks Gemini to rank options with a sustainability
tip.  Keeps the demo fully offline-safe and key-free.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..models.context import UserContext
from ..models.schemas import RouteOption, TransportResponse
from ..services.gemini_client import generate_json

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_TRANSPORT_SYSTEM = """You are a transport and sustainability advisor for FIFA World Cup 2026.

Given these transport options from the stadium to the destination, rank them from best to worst, considering:
1. Time efficiency
2. Carbon footprint (lower CO2 is better)
3. Predicted crowd congestion at arrival
4. Accessibility needs: {accessibility}

Options:
{options_text}

User role: {role}

Respond in JSON in {language}:
{{
  "ranking": [list of mode names in order, best first],
  "recommendation": "A brief 1-2 sentence recommendation explaining the best choice",
  "sustainability_tip": "ONE specific, concrete sustainability tip comparing CO2 of the options (e.g., 'Taking the metro saves 75g CO2 compared to the shuttle — that's like skipping one plastic bottle!')"
}}"""


class TransportAgent:
    """Ranks transport options with sustainability tips.

    Usage::

        agent = TransportAgent()
        response = await agent.get_options(context, "Central_Metro_Station")
    """

    def __init__(self) -> None:
        self._routes = self._load_routes()

    async def get_options(
        self,
        context: UserContext,
        destination: str,
    ) -> TransportResponse:
        """Get ranked transport options to a destination.

        Parameters
        ----------
        context:
            User context (accessibility, language, role).
        destination:
            Destination identifier from routes.json.

        Returns
        -------
        TransportResponse
            Ranked options with recommendation and sustainability tip.
        """
        # Find matching route
        options = self._find_options(destination)
        if not options:
            return TransportResponse(
                options=[],
                recommendation=f"No transport data available for '{destination}'.",
                sustainability_tip="Walk when possible — zero emissions! 🌱",
            )

        # Filter by accessibility if needed
        route_options = [RouteOption(**opt) for opt in options]

        # Ask Gemini to rank
        ranked_options, recommendation, tip = await self._rank_with_gemini(
            context, route_options
        )

        return TransportResponse(
            options=ranked_options or route_options,
            recommendation=recommendation,
            sustainability_tip=tip,
        )

    def get_all_destinations(self) -> list[str]:
        """Return all available destination names."""
        return [r["destination"] for r in self._routes]

    # ── Internal ─────────────────────────────────────────────────────

    def _find_options(self, destination: str) -> list[dict]:
        """Find route options for a destination (case-insensitive)."""
        dest_lower = destination.lower().replace(" ", "_")
        for route in self._routes:
            if route["destination"].lower() == dest_lower:
                return [
                    {
                        "mode": opt["mode"],
                        "origin": route["origin"],
                        "destination": route["destination"],
                        "time_minutes": opt["time_minutes"],
                        "co2_grams": opt["co2_grams"],
                        "frequency_minutes": opt.get("frequency_minutes"),
                        "accessibility_notes": opt.get("accessibility_notes"),
                        "cost": opt.get("cost"),
                    }
                    for opt in route["options"]
                ]
        # Try substring match
        for route in self._routes:
            if dest_lower in route["destination"].lower():
                return [
                    {
                        "mode": opt["mode"],
                        "origin": route["origin"],
                        "destination": route["destination"],
                        "time_minutes": opt["time_minutes"],
                        "co2_grams": opt["co2_grams"],
                        "frequency_minutes": opt.get("frequency_minutes"),
                        "accessibility_notes": opt.get("accessibility_notes"),
                        "cost": opt.get("cost"),
                    }
                    for opt in route["options"]
                ]
        return []

    async def _rank_with_gemini(
        self,
        context: UserContext,
        options: list[RouteOption],
    ) -> tuple[Optional[list[RouteOption]], str, str]:
        """Ask Gemini to rank options and provide sustainability tip."""
        accessibility = (
            ", ".join(context.accessibility_needs)
            if "none" not in context.accessibility_needs
            else "no special needs"
        )
        options_text = "\n".join(
            f"- {o.mode}: {o.time_minutes}min, {o.co2_grams}g CO2"
            + (f", every {o.frequency_minutes}min" if o.frequency_minutes else "")
            + (f", {o.accessibility_notes}" if o.accessibility_notes else "")
            for o in options
        )

        prompt = _TRANSPORT_SYSTEM.format(
            accessibility=accessibility,
            options_text=options_text,
            role=context.role,
            language=context.language,
        )

        result = await generate_json(prompt, temperature=0.3)

        if result:
            ranking = result.get("ranking", [])
            recommendation = result.get("recommendation", "")
            tip = result.get("sustainability_tip", "")

            if ranking:
                mode_order = {mode: i for i, mode in enumerate(ranking)}
                ranked = sorted(
                    options,
                    key=lambda o: mode_order.get(o.mode, 99),
                )
                return ranked, recommendation, tip

            return None, recommendation, tip

        # Fallback: sort by CO2, provide static tip
        sorted_opts = sorted(options, key=lambda o: o.co2_grams)
        best = sorted_opts[0]
        worst = sorted_opts[-1]
        co2_diff = worst.co2_grams - best.co2_grams

        recommendation = (
            f"We recommend {best.mode} — it's the greenest option "
            f"at just {best.co2_grams}g CO2."
        )
        tip = (
            f"🌱 Choosing {best.mode} over {worst.mode} saves "
            f"{co2_diff:.0f}g CO2 per trip!"
        )

        return sorted_opts, recommendation, tip

    @staticmethod
    def _load_routes() -> list[dict]:
        """Load routes from the JSON dataset."""
        routes_file = _DATA_DIR / "routes.json"
        try:
            with open(routes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("routes", [])
        except FileNotFoundError:
            logger.error("routes.json not found at %s", routes_file)
            return []
        except json.JSONDecodeError:
            logger.error("Invalid JSON in routes.json")
            return []
