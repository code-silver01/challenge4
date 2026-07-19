"""Predictive Crowd Surge Forecaster — trend analysis + LLM narration.

Not just "alert at 85% now" — this agent:
1. Keeps rolling occupancy history per gate (via CrowdAgent)
2. Fits a linear trend (moving average + extrapolation) in pure Python
3. Hands the trend + context to Gemini for a plain-language forecast
4. Falls back to rules-based alerting if the Gemini call fails

Gives organizers *lead time* instead of reactive alerts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Literal

from ..agents.crowd_agent import CrowdAgent, ZONE_DEFINITIONS
from ..models.context import UserContext
from ..models.schemas import ForecastResult
from ..services.gemini_client import generate_json

logger = logging.getLogger(__name__)

# ── Forecast prompt ──────────────────────────────────────────────────

_FORECAST_SYSTEM = """You are a crowd-management forecasting assistant for FIFA World Cup 2026 stadiums.

Given current occupancy data and a computed trend for a zone, produce a concise forecast.

Zone: {zone_name}
Current occupancy: {current_occ}/{capacity} ({current_pct:.1f}%)
Trend: {trend} (slope: {slope:+.2f}% per minute)
Minutes to capacity (estimated): {eta}
Recent history (last 5 readings): {history_summary}

Respond in JSON:
{{
  "forecast_message": "A 1-2 sentence forecast for the organizer in {language}",
  "recommendation": "A concrete action recommendation in {language}"
}}

Be specific about time estimates and which alternative zones to redirect to.
If the trend is declining or stable, still provide a useful status update."""


class SurgeForecaster:
    """Predictive crowd surge forecasting with rules-based fallback.

    Usage::

        forecaster = SurgeForecaster(crowd_agent)
        result = await forecaster.forecast_zone(context, "Gate_1")
    """

    def __init__(self, crowd_agent: CrowdAgent) -> None:
        self._crowd = crowd_agent

    async def forecast_zone(
        self, context: UserContext, zone_id: str
    ) -> Optional[ForecastResult]:
        """Generate a surge forecast for a single zone.

        Parameters
        ----------
        context:
            User context (organizer typically).
        zone_id:
            The zone to forecast.

        Returns
        -------
        ForecastResult | None
            Forecast with trend, ETA, and recommendation.
        """
        status = await self._crowd.get_zone_status(zone_id)
        if status is None:
            return None

        history = await self._crowd.get_history(zone_id, minutes=30)
        trend, slope = self._compute_trend(history, status.max_capacity)
        eta = self._estimate_time_to_capacity(
            status.occupancy_pct, slope
        )
        confidence = self._compute_confidence(len(history))

        # Try Gemini for narration
        forecast_msg, recommendation = await self._generate_forecast(
            context,
            status.zone_name,
            status.current_occupancy,
            status.max_capacity,
            status.occupancy_pct,
            trend,
            slope,
            eta,
            history,
        )

        # If Gemini failed, use rules-based fallback
        if not forecast_msg:
            forecast_msg, recommendation = self._rules_fallback(
                status.zone_name,
                status.occupancy_pct,
                trend,
                slope,
                eta,
            )

        return ForecastResult(
            zone_id=zone_id,
            zone_name=status.zone_name,
            current_occupancy_pct=status.occupancy_pct,
            predicted_occupancy_pct=min(
                100.0, status.occupancy_pct + slope * 5
            ),  # 5-min prediction
            minutes_to_capacity=eta,
            trend=trend,
            forecast_message=forecast_msg,
            recommendation=recommendation or "",
            confidence=confidence,
        )

    async def forecast_all(
        self, context: UserContext
    ) -> list[ForecastResult]:
        """Forecast all zones, sorted by urgency (rising first)."""
        results: list[ForecastResult] = []
        for zone_id in ZONE_DEFINITIONS:
            result = await self.forecast_zone(context, zone_id)
            if result:
                results.append(result)

        # Sort: rising first, then by predicted occupancy descending
        priority = {"rising": 0, "stable": 1, "declining": 2}
        results.sort(
            key=lambda r: (
                priority.get(r.trend, 1),
                -r.predicted_occupancy_pct,
            )
        )
        return results

    # ── Trend computation (pure Python — no LLM) ────────────────────

    @staticmethod
    def _compute_trend(
        history: list[tuple[datetime, int]],
        capacity: int,
    ) -> tuple[Literal["rising", "stable", "declining"], float]:
        """Compute trend direction and slope from occupancy history.

        Uses simple linear regression on the percentage values.

        Parameters
        ----------
        history:
            Chronological ``(timestamp, occupancy)`` pairs.
        capacity:
            Zone maximum capacity.

        Returns
        -------
        tuple[str, float]
            ``(trend_direction, slope_pct_per_minute)``
            where trend_direction is "rising" | "stable" | "declining".
        """
        if len(history) < 2:
            return "stable", 0.0

        # Convert to (minutes_since_first, pct) pairs
        t0 = history[0][0].timestamp()
        points: list[tuple[float, float]] = []
        for ts, occ in history:
            minutes = (ts.timestamp() - t0) / 60.0
            pct = (occ / capacity) * 100.0 if capacity > 0 else 0.0
            points.append((minutes, pct))

        # Linear regression: slope = Σ(xi-x̄)(yi-ȳ) / Σ(xi-x̄)²
        n = len(points)
        x_mean = sum(p[0] for p in points) / n
        y_mean = sum(p[1] for p in points) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
        denominator = sum((x - x_mean) ** 2 for x, _ in points)

        if abs(denominator) < 1e-9:
            return "stable", 0.0

        slope = numerator / denominator  # pct per minute

        # Classify trend
        if slope > 0.5:
            return "rising", slope
        if slope < -0.5:
            return "declining", slope
        return "stable", slope

    @staticmethod
    def _estimate_time_to_capacity(
        current_pct: float, slope: float
    ) -> Optional[float]:
        """Estimate minutes until 100% capacity.

        Returns None if trend is flat/declining or already at capacity.
        """
        if slope <= 0.0 or current_pct >= 100.0:
            return None

        remaining_pct = 100.0 - current_pct
        eta = remaining_pct / slope
        return round(eta, 1)

    @staticmethod
    def _compute_confidence(history_length: int) -> float:
        """Confidence score based on data availability.

        More data points → higher confidence (caps at 0.95).
        """
        if history_length < 3:
            return 0.3
        if history_length < 10:
            return 0.5
        if history_length < 30:
            return 0.7
        return min(0.95, 0.7 + history_length * 0.005)

    # ── Gemini narration ─────────────────────────────────────────────

    async def _generate_forecast(
        self,
        context: UserContext,
        zone_name: str,
        current_occ: int,
        capacity: int,
        current_pct: float,
        trend: str,
        slope: float,
        eta: Optional[float],
        history: list[tuple[datetime, int]],
    ) -> tuple[Optional[str], Optional[str]]:
        """Ask Gemini to narrate the forecast."""
        eta_str = f"~{eta:.0f} minutes" if eta else "N/A (stable or declining)"
        last_5 = history[-5:] if history else []
        hist_summary = ", ".join(
            f"{occ}" for _, occ in last_5
        ) or "insufficient data"

        prompt = _FORECAST_SYSTEM.format(
            zone_name=zone_name,
            current_occ=current_occ,
            capacity=capacity,
            current_pct=current_pct,
            trend=trend,
            slope=slope,
            eta=eta_str,
            history_summary=hist_summary,
            language=context.language,
        )

        result = await generate_json(prompt, temperature=0.3)
        if result:
            return (
                result.get("forecast_message"),
                result.get("recommendation"),
            )
        return None, None

    # ── Rules-based fallback ─────────────────────────────────────────

    @staticmethod
    def _rules_fallback(
        zone_name: str,
        current_pct: float,
        trend: str,
        slope: float,
        eta: Optional[float],
    ) -> tuple[str, str]:
        """Generate a forecast without the LLM.

        This fires when Gemini is unavailable — ensuring organizers
        always get actionable intel.
        """
        if trend == "rising" and eta and eta < 15:
            msg = (
                f"⚠️ {zone_name} is at {current_pct:.0f}% and rising fast "
                f"(+{slope:.1f}%/min). Estimated to hit capacity in "
                f"~{eta:.0f} minutes."
            )
            rec = (
                f"Recommend opening alternative gates and redirecting "
                f"incoming fans away from {zone_name} immediately."
            )
        elif trend == "rising":
            msg = (
                f"📈 {zone_name} is at {current_pct:.0f}% and trending "
                f"upward (+{slope:.1f}%/min)."
            )
            eta_str = f" ETA to capacity: ~{eta:.0f} min." if eta else ""
            rec = f"Monitor closely.{eta_str}"
        elif trend == "declining":
            msg = (
                f"📉 {zone_name} is at {current_pct:.0f}% and easing "
                f"({slope:.1f}%/min)."
            )
            rec = "No action needed — crowd is dispersing."
        else:
            msg = f"➡️ {zone_name} is at {current_pct:.0f}% and stable."
            rec = "Normal operations. Continue monitoring."

        return msg, rec
