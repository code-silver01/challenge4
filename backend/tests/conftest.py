"""Shared pytest fixtures for the OffsideOperations backend test suite."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.graph.stadium_graph import StadiumGraph
from app.models.context import UserContext
from app.services.repository import InMemoryRepository, reset_repository


# ── Graph ────────────────────────────────────────────────────────────


@pytest.fixture
def graph() -> StadiumGraph:
    """A fresh default stadium graph for each test."""
    return StadiumGraph(build_default=True)


@pytest.fixture
def empty_graph() -> StadiumGraph:
    """An empty graph for custom test topologies."""
    return StadiumGraph(build_default=False)


# ── UserContext variants ─────────────────────────────────────────────


@pytest.fixture
def fan_context() -> UserContext:
    """A typical English-speaking fan with no accessibility needs."""
    return UserContext(
        session_id="test-fan-001",
        role="fan",
        language="en",
        accessibility_needs=["none"],
        ticket_zone="Section_A",
        current_location_node="Gate_1",
    )


@pytest.fixture
def wheelchair_fan_context() -> UserContext:
    """A Spanish-speaking fan who needs wheelchair-accessible routes."""
    return UserContext(
        session_id="test-wheelchair-001",
        role="fan",
        language="es",
        accessibility_needs=["wheelchair"],
        ticket_zone="Section_B",
        current_location_node="Concourse_N",
    )


@pytest.fixture
def organizer_context() -> UserContext:
    """An organizer who sees raw metrics and ops dashboards."""
    return UserContext(
        session_id="test-org-001",
        role="organizer",
        language="en",
        accessibility_needs=["none"],
    )


@pytest.fixture
def volunteer_context() -> UserContext:
    """A volunteer with Hindi language preference."""
    return UserContext(
        session_id="test-vol-001",
        role="volunteer",
        language="hi",
        accessibility_needs=["none"],
        current_location_node="Concourse_E",
    )


# ── Repository ───────────────────────────────────────────────────────


@pytest.fixture
def repository() -> InMemoryRepository:
    """A fresh in-memory repository; also resets the singleton."""
    reset_repository()
    return InMemoryRepository()
