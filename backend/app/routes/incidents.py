"""Incidents API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..agents.ops_agent import OpsAgent
from ..models.context import UserContext
from ..models.schemas import IncidentReport
from .session import get_current_session

router = APIRouter()


@router.post("/incidents", response_model=IncidentReport)
async def report_incident(
    note: str,
    context: Annotated[UserContext, Depends(get_current_session)],
) -> IncidentReport:
    """Report a new incident via free text."""
    agent = OpsAgent()
    return await agent.create_incident(context, note)


@router.get("/incidents/summary", response_model=dict)
async def get_shift_summary(
    context: Annotated[UserContext, Depends(get_current_session)],
    hours_ago: float = Query(4.0, description="Hours since shift start"),
) -> dict:
    """Get a natural-language shift summary."""
    agent = OpsAgent()
    shift_start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    summary = await agent.shift_summary(context, shift_start)
    return {"summary": summary}
