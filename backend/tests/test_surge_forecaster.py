"""Tests for the Predictive Crowd Surge Forecaster.

Covers:
* Trend computation with known data series
* ETA-to-capacity estimation
* Confidence scoring
* Rules-based fallback when Gemini unavailable
* Edge cases (flat, declining, already at capacity)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.crowd_agent import CrowdAgent
from app.agents.surge_forecaster import SurgeForecaster
from app.models.context import UserContext
from app.services.repository import InMemoryRepository


@pytest.fixture
def crowd_agent(repository: InMemoryRepository) -> CrowdAgent:
    """CrowdAgent with fresh repo."""
    return CrowdAgent(repo=repository)


@pytest.fixture
def forecaster(crowd_agent: CrowdAgent) -> SurgeForecaster:
    """SurgeForecaster wired to crowd agent."""
    return SurgeForecaster(crowd_agent)


# ── Trend computation ────────────────────────────────────────────────


class TestTrendComputation:
    """Verify the linear regression trend calculator."""

    def test_rising_trend(self) -> None:
        """Steadily increasing occupancy → 'rising' trend."""
        now = datetime.now(timezone.utc)
        # Chronological: oldest first, occupancy increasing over time
        history = [
            (now - timedelta(minutes=10 - i), 100 + i * 50)
            for i in range(10)
        ]
        trend, slope = SurgeForecaster._compute_trend(history, 1000)
        assert trend == "rising"
        assert slope > 0

    def test_declining_trend(self) -> None:
        """Steadily decreasing occupancy → 'declining' trend."""
        now = datetime.now(timezone.utc)
        # Chronological: oldest first, occupancy decreasing over time
        history = [
            (now - timedelta(minutes=10 - i), 800 - i * 50)
            for i in range(10)
        ]
        trend, slope = SurgeForecaster._compute_trend(history, 1000)
        assert trend == "declining"
        assert slope < 0

    def test_stable_trend(self) -> None:
        """Flat occupancy → 'stable' trend."""
        now = datetime.now(timezone.utc)
        history = [
            (now - timedelta(minutes=i), 500)
            for i in range(10, 0, -1)
        ]
        trend, slope = SurgeForecaster._compute_trend(history, 1000)
        assert trend == "stable"
        assert abs(slope) < 0.5

    def test_insufficient_data(self) -> None:
        """Less than 2 data points → stable with zero slope."""
        now = datetime.now(timezone.utc)
        trend, slope = SurgeForecaster._compute_trend(
            [(now, 500)], 1000
        )
        assert trend == "stable"
        assert slope == 0.0

    def test_empty_history(self) -> None:
        """Empty history → stable with zero slope."""
        trend, slope = SurgeForecaster._compute_trend([], 1000)
        assert trend == "stable"
        assert slope == 0.0


# ── ETA to capacity ─────────────────────────────────────────────────


class TestETAEstimation:
    """Verify time-to-capacity estimates."""

    def test_rising_eta(self) -> None:
        """Rising at 2%/min from 80% → ~10 minutes."""
        eta = SurgeForecaster._estimate_time_to_capacity(80.0, 2.0)
        assert eta is not None
        assert abs(eta - 10.0) < 0.1

    def test_flat_trend_no_eta(self) -> None:
        """Flat slope → no ETA."""
        assert SurgeForecaster._estimate_time_to_capacity(50.0, 0.0) is None

    def test_declining_no_eta(self) -> None:
        """Declining slope → no ETA."""
        assert SurgeForecaster._estimate_time_to_capacity(50.0, -1.0) is None

    def test_already_at_capacity(self) -> None:
        """Already at 100% → no ETA."""
        assert SurgeForecaster._estimate_time_to_capacity(100.0, 1.0) is None


# ── Confidence scoring ───────────────────────────────────────────────


class TestConfidence:
    """Verify confidence scales with data availability."""

    def test_low_confidence_few_points(self) -> None:
        assert SurgeForecaster._compute_confidence(2) == 0.3

    def test_medium_confidence(self) -> None:
        assert SurgeForecaster._compute_confidence(5) == 0.5

    def test_high_confidence_many_points(self) -> None:
        assert SurgeForecaster._compute_confidence(30) >= 0.7

    def test_confidence_capped(self) -> None:
        assert SurgeForecaster._compute_confidence(1000) <= 0.95


# ── Rules-based fallback ────────────────────────────────────────────


class TestRulesFallback:
    """Verify fallback produces useful output without Gemini."""

    def test_urgent_rising_fallback(self) -> None:
        """Fast-rising zone with <15min ETA → urgent message."""
        msg, rec = SurgeForecaster._rules_fallback(
            "Gate 4", 88.0, "rising", 2.0, 6.0
        )
        assert "⚠️" in msg
        assert "6" in msg
        assert "redirect" in rec.lower() or "alternative" in rec.lower()

    def test_rising_fallback(self) -> None:
        """Rising but not urgent → monitoring message."""
        msg, rec = SurgeForecaster._rules_fallback(
            "Gate 1", 60.0, "rising", 1.0, 40.0
        )
        assert "📈" in msg
        assert "monitor" in rec.lower()

    def test_declining_fallback(self) -> None:
        """Declining → positive message."""
        msg, rec = SurgeForecaster._rules_fallback(
            "Gate 2", 70.0, "declining", -1.0, None
        )
        assert "📉" in msg
        assert "no action" in rec.lower()

    def test_stable_fallback(self) -> None:
        """Stable → neutral message."""
        msg, rec = SurgeForecaster._rules_fallback(
            "Gate 3", 50.0, "stable", 0.1, None
        )
        assert "stable" in msg.lower()


# ── Integration with crowd agent ─────────────────────────────────────


class TestForecasterIntegration:
    """Test forecast_zone with real crowd agent data."""

    @pytest.mark.asyncio
    async def test_forecast_zone_with_data(
        self,
        forecaster: SurgeForecaster,
        repository: InMemoryRepository,
        organizer_context: UserContext,
    ) -> None:
        """Forecast a zone that has occupancy data."""
        # Seed data with rising pattern
        for occ in [1000, 1100, 1200, 1300, 1400]:
            await repository.update_zone_occupancy(
                "Gate_1", occ, 2000, "Gate 1"
            )

        with patch(
            "app.agents.surge_forecaster.generate_json",
            new_callable=AsyncMock,
            return_value=None,  # Force fallback
        ):
            result = await forecaster.forecast_zone(
                organizer_context, "Gate_1"
            )
            assert result is not None
            assert result.zone_id == "Gate_1"
            assert result.forecast_message  # Fallback should produce text
            assert result.recommendation

    @pytest.mark.asyncio
    async def test_forecast_unknown_zone(
        self,
        forecaster: SurgeForecaster,
        organizer_context: UserContext,
    ) -> None:
        """Forecasting an unknown zone returns None."""
        result = await forecaster.forecast_zone(
            organizer_context, "Nonexistent"
        )
        assert result is None
