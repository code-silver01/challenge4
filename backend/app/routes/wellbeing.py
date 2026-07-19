"""Wellbeing API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..agents.wellbeing_agent import WellbeingAgent
from ..models.context import UserContext
from ..models.schemas import WellbeingAlert
from .session import get_current_session

router = APIRouter()


@router.get("/wellbeing/alerts", response_model=list[WellbeingAlert])
async def get_wellbeing_alerts(
    context: Annotated[UserContext, Depends(get_current_session)]
) -> list[WellbeingAlert]:
    """Get active fatigue/wellbeing alerts for all volunteers."""
    agent = WellbeingAgent()
    return await agent.check_all(context)
