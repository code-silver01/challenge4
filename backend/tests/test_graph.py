"""Tests for the stadium graph and Dijkstra pathfinding.

Covers:
* Basic shortest-path computation
* Wheelchair accessibility (stairs-only edge exclusion)
* Unreachable node handling
* Graph integrity (all 25 nodes connected)
* Edge-case topologies
"""

from __future__ import annotations

import pytest

from app.graph.stadium_graph import Edge, Node, StadiumGraph


# ── Graph integrity ──────────────────────────────────────────────────


class TestGraphIntegrity:
    """Verify the default graph is well-formed."""

    def test_has_25_nodes(self, graph: StadiumGraph) -> None:
        """Default graph must contain exactly 25 nodes."""
        assert len(graph.nodes) == 25

    def test_all_nodes_have_adjacency(self, graph: StadiumGraph) -> None:
        """Every node must appear in the adjacency list."""
        for node_id in graph.nodes:
            assert node_id in graph.adjacency
            assert len(graph.adjacency[node_id]) > 0, (
                f"{node_id} has no edges"
            )

    def test_all_nodes_reachable_from_gate_1(
        self, graph: StadiumGraph
    ) -> None:
        """Every node should be reachable from Gate 1 (graph is connected)."""
        for node_id in graph.nodes:
            result = graph.dijkstra("Gate_1", node_id)
            assert result is not None, (
                f"{node_id} is unreachable from Gate_1"
            )

    def test_all_nodes_reachable_wheelchair(
        self, graph: StadiumGraph
    ) -> None:
        """Every node should be reachable even with stairs excluded."""
        for node_id in graph.nodes:
            result = graph.dijkstra(
                "Gate_1", node_id, exclude_stairs=True
            )
            assert result is not None, (
                f"{node_id} is unreachable from Gate_1 in wheelchair mode"
            )

    def test_node_categories_present(self, graph: StadiumGraph) -> None:
        """All required categories must be represented."""
        categories = {n.category for n in graph.nodes.values()}
        for expected in [
            "gate", "section", "restroom", "food",
            "medical", "exit", "concourse",
        ]:
            assert expected in categories, f"Missing category: {expected}"

    def test_six_gates(self, graph: StadiumGraph) -> None:
        """Stadium has exactly 6 entry gates."""
        gates = graph.get_nodes_by_category("gate")
        assert len(gates) == 6

    def test_six_sections(self, graph: StadiumGraph) -> None:
        """Stadium has exactly 6 seating sections."""
        sections = graph.get_nodes_by_category("section")
        assert len(sections) == 6

    def test_two_medical_points(self, graph: StadiumGraph) -> None:
        """Stadium has exactly 2 medical facilities."""
        medical = graph.get_nodes_by_category("medical")
        assert len(medical) == 2


# ── Shortest path ────────────────────────────────────────────────────


class TestShortestPath:
    """Verify Dijkstra produces correct paths and distances."""

    def test_gate1_to_section_a(self, graph: StadiumGraph) -> None:
        """Gate 1 → Section A: Gate_1 → Concourse_N → Section_A (90s)."""
        result = graph.dijkstra("Gate_1", "Section_A")
        assert result is not None
        path, weight = result
        assert path == ["Gate_1", "Concourse_N", "Section_A"]
        assert weight == 90  # 30 + 60

    def test_gate1_to_restroom_north(self, graph: StadiumGraph) -> None:
        """Gate 1 → Restroom North: via Concourse N (60s)."""
        result = graph.dijkstra("Gate_1", "Restroom_North")
        assert result is not None
        path, weight = result
        assert path == ["Gate_1", "Concourse_N", "Restroom_North"]
        assert weight == 60  # 30 + 30

    def test_same_node(self, graph: StadiumGraph) -> None:
        """Start == end → path is just [start], weight 0."""
        result = graph.dijkstra("Gate_1", "Gate_1")
        assert result is not None
        path, weight = result
        assert path == ["Gate_1"]
        assert weight == 0

    def test_section_a_to_medical_main(self, graph: StadiumGraph) -> None:
        """Section A → Medical Main via concourse (multiple hops)."""
        result = graph.dijkstra("Section_A", "Medical_Main")
        assert result is not None
        path, weight = result
        # Should go Section_A → Concourse_N → Concourse_E → Medical_Main
        assert path[0] == "Section_A"
        assert path[-1] == "Medical_Main"
        assert weight > 0

    def test_food_north_to_exit_south(self, graph: StadiumGraph) -> None:
        """Food North → Exit South — a cross-stadium traversal."""
        result = graph.dijkstra("Food_North", "Exit_South")
        assert result is not None
        path, weight = result
        assert path[0] == "Food_North"
        assert path[-1] == "Exit_South"
        assert weight > 0


# ── Wheelchair accessibility ─────────────────────────────────────────


class TestWheelchairAccessibility:
    """Verify stairs-only edges are excluded for wheelchair users."""

    def test_wheelchair_route_excludes_stairs_to_section_b(
        self, graph: StadiumGraph
    ) -> None:
        """Concourse N → Section B: direct stair path excluded.

        Without stairs: Concourse_N → Section_A (60) → Section_B (45) = 105s
        With stairs:    Concourse_N → Section_B (90s via stairs)

        Wheelchair route must be longer but avoid stairs.
        """
        # Normal path uses stairs (shorter)
        normal = graph.dijkstra("Concourse_N", "Section_B")
        assert normal is not None
        normal_path, normal_weight = normal
        assert normal_weight == 90  # stairs shortcut

        # Wheelchair path avoids stairs (longer)
        wheelchair = graph.dijkstra(
            "Concourse_N", "Section_B", exclude_stairs=True
        )
        assert wheelchair is not None
        wc_path, wc_weight = wheelchair
        assert wc_weight == 105  # 60 + 45 via Section_A
        assert "Section_A" in wc_path
        # Verify no stairs-only edges in path
        self._assert_no_stairs_in_path(graph, wc_path)

    def test_wheelchair_route_excludes_stairs_to_section_f(
        self, graph: StadiumGraph
    ) -> None:
        """Concourse N → Section F: stairs excluded, routes via Section A."""
        wheelchair = graph.dijkstra(
            "Concourse_N", "Section_F", exclude_stairs=True
        )
        assert wheelchair is not None
        wc_path, wc_weight = wheelchair
        # Must go Concourse_N → Section_A → Section_F
        assert wc_weight == 105  # 60 + 45
        self._assert_no_stairs_in_path(graph, wc_path)

    def test_wheelchair_full_journey_gate_to_section(
        self, graph: StadiumGraph
    ) -> None:
        """Gate 1 → Section B: complete wheelchair journey."""
        result = graph.dijkstra(
            "Gate_1", "Section_B", exclude_stairs=True
        )
        assert result is not None
        path, weight = result
        assert path[0] == "Gate_1"
        assert path[-1] == "Section_B"
        # Gate_1(30) → Concourse_N(60) → Section_A(45) → Section_B = 135
        assert weight == 135
        self._assert_no_stairs_in_path(graph, path)

    def test_wheelchair_cross_stadium(self, graph: StadiumGraph) -> None:
        """Gate 1 → Exit South: wheelchair-safe across the venue."""
        result = graph.dijkstra(
            "Gate_1", "Exit_South", exclude_stairs=True
        )
        assert result is not None
        path, _ = result
        self._assert_no_stairs_in_path(graph, path)

    @staticmethod
    def _assert_no_stairs_in_path(
        graph: StadiumGraph, path: list[str]
    ) -> None:
        """Helper: assert no edge in the path is stairs-only."""
        for i in range(len(path) - 1):
            from_node = path[i]
            to_node = path[i + 1]
            for edge in graph.adjacency[from_node]:
                if edge.target == to_node:
                    assert not edge.stairs_only, (
                        f"Stairs-only edge found: {from_node} → {to_node}"
                    )
                    break


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary and error conditions."""

    def test_unknown_start_node(self, graph: StadiumGraph) -> None:
        """Unknown start node returns None."""
        result = graph.dijkstra("NonExistent", "Gate_1")
        assert result is None

    def test_unknown_end_node(self, graph: StadiumGraph) -> None:
        """Unknown end node returns None."""
        result = graph.dijkstra("Gate_1", "NonExistent")
        assert result is None

    def test_disconnected_node(self, empty_graph: StadiumGraph) -> None:
        """Disconnected nodes return None."""
        empty_graph.add_node(Node("A", "A", "test"))
        empty_graph.add_node(Node("B", "B", "test"))
        result = empty_graph.dijkstra("A", "B")
        assert result is None

    def test_add_edge_unknown_node_raises(
        self, empty_graph: StadiumGraph
    ) -> None:
        """Adding an edge with unknown node raises KeyError."""
        empty_graph.add_node(Node("A", "A", "test"))
        with pytest.raises(KeyError):
            empty_graph.add_edge("A", "Z", 10)

    def test_get_node_name(self, graph: StadiumGraph) -> None:
        """get_node_name returns human-readable label."""
        assert graph.get_node_name("Gate_1") == "Gate 1 (North)"
        assert graph.get_node_name("NonExistent") == "NonExistent"

    def test_get_nodes_by_category(self, graph: StadiumGraph) -> None:
        """Filtering by category returns correct subset."""
        restrooms = graph.get_nodes_by_category("restroom")
        assert len(restrooms) == 2
        ids = {r.node_id for r in restrooms}
        assert ids == {"Restroom_North", "Restroom_South"}


# ── Custom topology tests ───────────────────────────────────────────


class TestCustomTopology:
    """Verify Dijkstra on small hand-built graphs."""

    def test_linear_graph(self, empty_graph: StadiumGraph) -> None:
        """A→B→C: shortest path is the only path."""
        g = empty_graph
        g.add_node(Node("A", "A", "test"))
        g.add_node(Node("B", "B", "test"))
        g.add_node(Node("C", "C", "test"))
        g.add_edge("A", "B", 10)
        g.add_edge("B", "C", 20)

        result = g.dijkstra("A", "C")
        assert result is not None
        path, weight = result
        assert path == ["A", "B", "C"]
        assert weight == 30

    def test_prefers_shorter_path(self, empty_graph: StadiumGraph) -> None:
        """When two paths exist, Dijkstra picks the lighter one."""
        g = empty_graph
        for nid in ("A", "B", "C"):
            g.add_node(Node(nid, nid, "test"))
        g.add_edge("A", "B", 5)
        g.add_edge("B", "C", 5)
        g.add_edge("A", "C", 100)  # direct but heavy

        result = g.dijkstra("A", "C")
        assert result is not None
        path, weight = result
        assert path == ["A", "B", "C"]
        assert weight == 10

    def test_stairs_only_bypass(self, empty_graph: StadiumGraph) -> None:
        """When the only short path is stairs, wheelchair takes detour."""
        g = empty_graph
        for nid in ("A", "B", "C"):
            g.add_node(Node(nid, nid, "test"))
        g.add_edge("A", "B", 10, stairs_only=True)
        g.add_edge("A", "C", 5)
        g.add_edge("C", "B", 5)

        # Normal: A→B (10)
        normal = g.dijkstra("A", "B")
        assert normal is not None
        assert normal[1] == 10

        # Wheelchair: A→C→B (10)
        wheelchair = g.dijkstra("A", "B", exclude_stairs=True)
        assert wheelchair is not None
        assert wheelchair[0] == ["A", "C", "B"]
        assert wheelchair[1] == 10
