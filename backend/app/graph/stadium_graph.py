"""Stadium graph — hand-built ~25-node venue map + Dijkstra.

Strict LLM/algorithm separation
--------------------------------
The LLM **never** invents paths.  Dijkstra computes the shortest route;
the LLM only *narrates* the result in the user's language.  This module
owns all graph logic; no agent may bypass it.

Wheelchair accessibility
------------------------
Some edges are tagged ``stairs_only=True``.  When
``exclude_stairs=True`` is passed to ``dijkstra()``, those edges are
filtered out *before* solving, guaranteeing step-free paths for
wheelchair users.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Edge:
    """A directed (but stored bidirectionally) weighted edge."""

    target: str
    weight: int  # seconds of walk time
    stairs_only: bool = False
    description: str = ""


@dataclass
class Node:
    """A named location in the stadium."""

    node_id: str
    name: str
    category: str  # gate | section | restroom | food | medical | exit | concourse
    x: float = 0.0  # normalised SVG x (0-100)
    y: float = 0.0  # normalised SVG y (0-100)


class StadiumGraph:
    """25-node stadium graph with Dijkstra shortest-path solver.

    The default graph is built automatically on construction.  Tests
    can also build custom graphs via ``add_node`` / ``add_edge``.
    """

    def __init__(self, *, build_default: bool = True) -> None:
        self.nodes: dict[str, Node] = {}
        self.adjacency: dict[str, list[Edge]] = {}
        if build_default:
            self._build_default_graph()

    # ── Graph construction ───────────────────────────────────────────

    def add_node(self, node: Node) -> None:
        """Register a node; initialise its adjacency list."""
        self.nodes[node.node_id] = node
        self.adjacency.setdefault(node.node_id, [])

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        weight: int,
        *,
        stairs_only: bool = False,
        description: str = "",
    ) -> None:
        """Add a *bidirectional* edge between two existing nodes.

        Raises
        ------
        KeyError
            If either node has not been added yet.
        """
        if from_id not in self.nodes:
            raise KeyError(f"Unknown node: {from_id}")
        if to_id not in self.nodes:
            raise KeyError(f"Unknown node: {to_id}")

        self.adjacency[from_id].append(
            Edge(to_id, weight, stairs_only, description)
        )
        self.adjacency[to_id].append(
            Edge(from_id, weight, stairs_only, description)
        )

    # ── Dijkstra ─────────────────────────────────────────────────────

    def dijkstra(
        self, start: str, end: str, *, exclude_stairs: bool = False
    ) -> Optional[tuple[list[str], int]]:
        """Compute the shortest path from *start* to *end*.

        Parameters
        ----------
        start:
            Source node ID.
        end:
            Destination node ID.
        exclude_stairs:
            When ``True``, edges with ``stairs_only=True`` are ignored,
            ensuring a fully step-free route.

        Returns
        -------
        tuple[list[str], int] | None
            ``(path_node_ids, total_seconds)`` or ``None`` when no path
            exists.
        """
        if start not in self.nodes or end not in self.nodes:
            return None

        distances: dict[str, float] = {n: float("inf") for n in self.nodes}
        distances[start] = 0.0
        previous: dict[str, str | None] = {n: None for n in self.nodes}
        visited: set[str] = set()

        # (distance, node_id) — Python's heapq is a min-heap
        pq: list[tuple[float, str]] = [(0.0, start)]

        while pq:
            current_dist, current = heapq.heappop(pq)

            if current in visited:
                continue
            visited.add(current)

            if current == end:
                break

            for edge in self.adjacency.get(current, []):
                if exclude_stairs and edge.stairs_only:
                    continue
                if edge.target in visited:
                    continue

                new_dist = current_dist + edge.weight
                if new_dist < distances[edge.target]:
                    distances[edge.target] = new_dist
                    previous[edge.target] = current
                    heapq.heappush(pq, (new_dist, edge.target))

        # Unreachable?
        if distances[end] == float("inf"):
            return None

        # Reconstruct path
        path: list[str] = []
        current_node: str | None = end
        while current_node is not None:
            path.append(current_node)
            current_node = previous[current_node]
        path.reverse()

        return path, int(distances[end])

    def get_node_name(self, node_id: str) -> str:
        """Human-readable name for a node, falling back to the ID."""
        node = self.nodes.get(node_id)
        return node.name if node else node_id

    def get_nodes_by_category(self, category: str) -> list[Node]:
        """Return all nodes matching a category (e.g. 'restroom')."""
        return [n for n in self.nodes.values() if n.category == category]

    # ── Default graph ────────────────────────────────────────────────

    def _build_default_graph(self) -> None:
        """Construct the ~25-node FIFA World Cup 2026 stadium layout.

        Layout (bird's-eye view)::

                         Gate_1 (N)
                           │
                   ┌── Concourse_N ──┐
                   │       │         │
               Gate_5    Food_N    Gate_2  (NE/E entries)
                   │   Restroom_N    │
            Concourse_W           Concourse_E
              │    │                 │    │
           Gate_4  Food_W   Food_E  Gate_3
          Medical_W │                │  Medical_Main
                   │   Section ring  │
            Concourse_S (lower ring) │
                   │       │         │
               Gate_6  Restroom_S  Exit_South
                   │                 │
                  Exit_North      ───┘

        Sections A-F form an inner ring (all step-free).
        3 concourse→section edges are stairs-only; wheelchair users
        route via adjacent sections instead.
        """
        # ── Nodes ────────────────────────────────────────────────────
        nodes = [
            # Concourse ring
            Node("Concourse_N", "North Concourse", "concourse", 50, 10),
            Node("Concourse_E", "East Concourse", "concourse", 85, 50),
            Node("Concourse_S", "South Concourse", "concourse", 50, 90),
            Node("Concourse_W", "West Concourse", "concourse", 15, 50),
            # Gates
            Node("Gate_1", "Gate 1 (North)", "gate", 50, 2),
            Node("Gate_2", "Gate 2 (East)", "gate", 92, 35),
            Node("Gate_3", "Gate 3 (Southeast)", "gate", 92, 65),
            Node("Gate_4", "Gate 4 (West)", "gate", 8, 35),
            Node("Gate_5", "Gate 5 (Northeast)", "gate", 75, 15),
            Node("Gate_6", "Gate 6 (Southwest)", "gate", 25, 85),
            # Seating sections (inner ring, all connected step-free)
            Node("Section_A", "Section A (North Stand)", "section", 50, 30),
            Node("Section_B", "Section B (NE Stand)", "section", 70, 38),
            Node("Section_C", "Section C (East Stand)", "section", 70, 62),
            Node("Section_D", "Section D (South Stand)", "section", 50, 70),
            Node("Section_E", "Section E (SW Stand)", "section", 30, 62),
            Node("Section_F", "Section F (West Stand)", "section", 30, 38),
            # Restrooms
            Node("Restroom_North", "North Restroom", "restroom", 60, 15),
            Node("Restroom_South", "South Restroom", "restroom", 40, 85),
            # Food courts
            Node("Food_East", "East Food Court", "food", 88, 55),
            Node("Food_West", "West Food Court", "food", 12, 55),
            Node("Food_North", "North Food Court", "food", 42, 12),
            # Medical
            Node("Medical_Main", "Main Medical Center", "medical", 90, 50),
            Node("Medical_West", "West Medical Point", "medical", 10, 50),
            # Exits
            Node("Exit_North", "North Exit", "exit", 45, 5),
            Node("Exit_South", "South Exit", "exit", 55, 95),
        ]
        for n in nodes:
            self.add_node(n)

        # ── Edges ────────────────────────────────────────────────────
        # Concourse ring (outer walkway)
        self.add_edge("Concourse_N", "Concourse_E", 120,
                       description="East along north concourse")
        self.add_edge("Concourse_E", "Concourse_S", 120,
                       description="South along east concourse")
        self.add_edge("Concourse_S", "Concourse_W", 120,
                       description="West along south concourse")
        self.add_edge("Concourse_W", "Concourse_N", 120,
                       description="North along west concourse")

        # Gates → concourse
        self.add_edge("Gate_1", "Concourse_N", 30,
                       description="Enter through Gate 1")
        self.add_edge("Gate_2", "Concourse_E", 30,
                       description="Enter through Gate 2")
        self.add_edge("Gate_3", "Concourse_S", 45,
                       description="Enter through Gate 3")
        self.add_edge("Gate_4", "Concourse_W", 30,
                       description="Enter through Gate 4")
        self.add_edge("Gate_5", "Concourse_N", 60,
                       description="Enter through Gate 5 to north")
        self.add_edge("Gate_5", "Concourse_E", 60,
                       description="Enter through Gate 5 to east")
        self.add_edge("Gate_6", "Concourse_S", 60,
                       description="Enter through Gate 6 to south")
        self.add_edge("Gate_6", "Concourse_W", 60,
                       description="Enter through Gate 6 to west")

        # Concourse → sections (some STAIRS ONLY)
        self.add_edge("Concourse_N", "Section_A", 60,
                       description="Ramp down to Section A")
        self.add_edge("Concourse_N", "Section_B", 90, stairs_only=True,
                       description="Stairs down to Section B")
        self.add_edge("Concourse_N", "Section_F", 90, stairs_only=True,
                       description="Stairs down to Section F")
        self.add_edge("Concourse_E", "Section_B", 60,
                       description="Ramp down to Section B")
        self.add_edge("Concourse_E", "Section_C", 60,
                       description="Ramp down to Section C")
        self.add_edge("Concourse_S", "Section_C", 90, stairs_only=True,
                       description="Stairs down to Section C")
        self.add_edge("Concourse_S", "Section_D", 60,
                       description="Ramp down to Section D")
        self.add_edge("Concourse_W", "Section_E", 60,
                       description="Ramp down to Section E")
        self.add_edge("Concourse_W", "Section_F", 60,
                       description="Ramp down to Section F")

        # Section inner ring (ALL step-free)
        self.add_edge("Section_A", "Section_B", 45,
                       description="Walk along stands A→B")
        self.add_edge("Section_B", "Section_C", 45,
                       description="Walk along stands B→C")
        self.add_edge("Section_C", "Section_D", 45,
                       description="Walk along stands C→D")
        self.add_edge("Section_D", "Section_E", 45,
                       description="Walk along stands D→E")
        self.add_edge("Section_E", "Section_F", 45,
                       description="Walk along stands E→F")
        self.add_edge("Section_F", "Section_A", 45,
                       description="Walk along stands F→A")

        # Facilities
        self.add_edge("Concourse_N", "Restroom_North", 30,
                       description="Walk to North Restroom")
        self.add_edge("Concourse_S", "Restroom_South", 30,
                       description="Walk to South Restroom")
        self.add_edge("Concourse_E", "Food_East", 25,
                       description="Walk to East Food Court")
        self.add_edge("Concourse_W", "Food_West", 25,
                       description="Walk to West Food Court")
        self.add_edge("Concourse_N", "Food_North", 20,
                       description="Walk to North Food Court")
        self.add_edge("Concourse_E", "Medical_Main", 40,
                       description="Walk to Main Medical Center")
        self.add_edge("Concourse_W", "Medical_West", 40,
                       description="Walk to West Medical Point")

        # Exits
        self.add_edge("Concourse_N", "Exit_North", 45,
                       description="Walk to North Exit")
        self.add_edge("Concourse_S", "Exit_South", 45,
                       description="Walk to South Exit")


# ── Module-level singleton ───────────────────────────────────────────

_graph: StadiumGraph | None = None


def get_stadium_graph() -> StadiumGraph:
    """Return the application-wide stadium graph (lazy singleton)."""
    global _graph  # noqa: PLW0603
    if _graph is None:
        _graph = StadiumGraph()
    return _graph
