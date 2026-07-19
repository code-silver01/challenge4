"""Navigation Agent — computes and narrates step-free stadium paths.

Strict LLM/algorithm separation: Dijkstra finds the route, Gemini only
*narrates* it in the user's language.  The LLM never invents directions.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..graph.stadium_graph import StadiumGraph, get_stadium_graph
from ..models.context import UserContext
from ..services.gemini_client import generate_text
from ..services.input_sanitizer import sanitize_input

logger = logging.getLogger(__name__)

# ── Narration system prompt ──────────────────────────────────────────

_NARRATION_SYSTEM = """You are a friendly stadium navigation assistant for FIFA World Cup 2026.

Given a computed route (list of node names and estimated walk time), produce
clear, concise walking directions in {language}.

Rules:
- Use landmark names, not node IDs.
- If the user has wheelchair accessibility needs, mention that the route is fully step-free.
- Keep it under 4 sentences.
- Be warm and encouraging — the fan is at a World Cup match!
- Use the ⚽ emoji once at the end as a confirmation.

Route: {route_description}
Estimated walk time: {walk_time} seconds (~{walk_minutes} minutes).
User role: {role}
Wheelchair accessible: {wheelchair}"""


class NavigationAgent:
    """Finds paths through the stadium graph and narrates them.

    The graph computation is deterministic; the LLM layer is purely
    for natural-language presentation.
    """

    def __init__(self, graph: StadiumGraph | None = None) -> None:
        self._graph = graph or get_stadium_graph()

    async def navigate(
        self,
        context: UserContext,
        destination: str,
        origin: str | None = None,
    ) -> dict:
        """Compute a route and narrate it for the user.

        Parameters
        ----------
        context:
            Current user context (language, accessibility, location).
        destination:
            Target node ID (or a natural-language name to resolve).
        origin:
            Starting node ID.  Defaults to ``context.current_location_node``.

        Returns
        -------
        dict
            ``{"path", "walk_time_seconds", "walk_time_minutes",
              "narration", "wheelchair_safe"}``
        """
        start = origin or context.current_location_node
        if not start:
            return self._error_response("I don't know your current location. Please select a starting point.")

        # Resolve destination — try exact match, then fuzzy by name/category
        dest_node = self._resolve_node(sanitize_input(destination))
        if not dest_node:
            return self._error_response(
                f"I couldn't find '{destination}' in the stadium. "
                "Try asking for a gate, section, restroom, food court, or medical center."
            )

        start_node = self._resolve_node(sanitize_input(start))
        if not start_node:
            return self._error_response(f"Unknown starting location: '{start}'.")

        # ── Dijkstra ─────────────────────────────────────────────────
        wheelchair = context.needs_wheelchair_access
        result = self._graph.dijkstra(
            start_node, dest_node, exclude_stairs=wheelchair
        )

        if result is None:
            return self._error_response(
                "Sorry, I couldn't find a route. The path may be temporarily blocked."
            )

        path, total_seconds = result
        path_names = [self._graph.get_node_name(n) for n in path]
        walk_minutes = round(total_seconds / 60, 1)

        # ── LLM narration ────────────────────────────────────────────
        route_desc = " → ".join(path_names)
        narration = await self._narrate(
            context, route_desc, total_seconds, walk_minutes, wheelchair
        )

        return {
            "path": path,
            "path_names": path_names,
            "walk_time_seconds": total_seconds,
            "walk_time_minutes": walk_minutes,
            "narration": narration,
            "wheelchair_safe": wheelchair,
        }

    def find_nearest(
        self, context: UserContext, category: str
    ) -> Optional[dict]:
        """Find the nearest node of a given category from current location.

        Parameters
        ----------
        context:
            Must have ``current_location_node`` set.
        category:
            Node category to search (e.g. 'restroom', 'medical', 'food').

        Returns
        -------
        dict | None
            ``{"node_id", "node_name", "distance_seconds"}`` or None.
        """
        start = context.current_location_node
        if not start or start not in self._graph.nodes:
            return None

        wheelchair = context.needs_wheelchair_access
        candidates = self._graph.get_nodes_by_category(category)
        best: Optional[tuple[str, int]] = None

        for node in candidates:
            result = self._graph.dijkstra(
                start, node.node_id, exclude_stairs=wheelchair
            )
            if result:
                _, dist = result
                if best is None or dist < best[1]:
                    best = (node.node_id, dist)

        if best is None:
            return None

        return {
            "node_id": best[0],
            "node_name": self._graph.get_node_name(best[0]),
            "distance_seconds": best[1],
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _resolve_node(self, query: str) -> Optional[str]:
        """Resolve a user query to a node ID.

        Tries: exact ID match → case-insensitive name search →
        category search → substring match.
        """
        q = query.strip()

        # Exact ID
        if q in self._graph.nodes:
            return q

        # Case-insensitive name match
        q_lower = q.lower()
        for nid, node in self._graph.nodes.items():
            if node.name.lower() == q_lower:
                return nid

        # Category match (e.g. "restroom" → nearest restroom)
        category_map = {
            "restroom": "restroom", "bathroom": "restroom",
            "toilet": "restroom", "washroom": "restroom", "baño": "restroom",
            "food": "food", "eat": "food", "snack": "food",
            "restaurant": "food", "comida": "food",
            "medical": "medical", "doctor": "medical", "nurse": "medical",
            "first aid": "medical", "médico": "medical",
            "exit": "exit", "leave": "exit", "salida": "exit",
            "gate": "gate", "entrance": "gate", "puerta": "gate",
        }
        for keyword, category in category_map.items():
            if keyword in q_lower:
                nodes = self._graph.get_nodes_by_category(category)
                if nodes:
                    return nodes[0].node_id

        # Substring match on node names
        for nid, node in self._graph.nodes.items():
            if q_lower in node.name.lower() or q_lower in nid.lower():
                return nid

        return None

    async def _narrate(
        self,
        context: UserContext,
        route_desc: str,
        walk_seconds: int,
        walk_minutes: float,
        wheelchair: bool,
    ) -> str:
        """Ask Gemini to narrate the route in the user's language."""
        prompt = _NARRATION_SYSTEM.format(
            language=context.language,
            route_description=route_desc,
            walk_time=walk_seconds,
            walk_minutes=walk_minutes,
            role=context.role,
            wheelchair="yes" if wheelchair else "no",
        )

        narration = await generate_text(prompt, temperature=0.4)

        if narration:
            return narration

        # Fallback: plain English narration without LLM
        prefix = "♿ Wheelchair-accessible route: " if wheelchair else ""
        return (
            f"{prefix}{route_desc}. "
            f"Estimated walk time: ~{walk_minutes} minutes. ⚽"
        )

    @staticmethod
    def _error_response(message: str) -> dict:
        """Return a structured error response."""
        return {
            "path": [],
            "path_names": [],
            "walk_time_seconds": 0,
            "walk_time_minutes": 0,
            "narration": message,
            "wheelchair_safe": False,
            "error": True,
        }
