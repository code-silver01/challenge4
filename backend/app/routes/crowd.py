"""Crowd API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..agents.crowd_agent import CrowdAgent
from ..agents.surge_forecaster import SurgeForecaster
from ..models.context import UserContext
from ..models.schemas import CrowdStatusResponse, ForecastResult
from .session import get_current_session

router = APIRouter()


@router.get("/crowd/status", response_model=CrowdStatusResponse)
async def get_crowd_status() -> CrowdStatusResponse:
    """Get real-time crowd status for all zones."""
    agent = CrowdAgent()
    return await agent.get_all_status()


@router.get("/crowd/forecast", response_model=list[ForecastResult])
async def get_crowd_forecast(
    context: Annotated[UserContext, Depends(get_current_session)]
) -> list[ForecastResult]:
    """Get predictive surge forecasts (organizer role recommended)."""
    # While fans could technically ask, this dashboard view is for organizers
    agent = CrowdAgent()
    forecaster = SurgeForecaster(agent)
    return await forecaster.forecast_all(context)
