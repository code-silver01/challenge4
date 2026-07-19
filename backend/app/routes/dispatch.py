"""Dispatch API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..agents.dispatch_agent import DispatchAgent
from ..models.context import UserContext
from ..models.schemas import DispatchRecommendation, VolunteerProfile
from .session import get_current_session

router = APIRouter()


@router.get("/volunteers", response_model=list[VolunteerProfile])
async def get_volunteer_roster() -> list[VolunteerProfile]:
    """Get the full volunteer roster."""
    agent = DispatchAgent()
    return await agent.get_roster()


@router.post("/dispatch/recommend", response_model=DispatchRecommendation | None)
async def recommend_dispatch(
    incident_id: str,
    context: Annotated[UserContext, Depends(get_current_session)],
) -> DispatchRecommendation | None:
    """Get a smart dispatch recommendation for an incident."""
    from ..services.repository import get_repository
    
    repo = get_repository()
    # In a real app we'd query by ID. For demo, just find the incident.
    incidents = await repo.get_incidents()
    incident = next((i for i in incidents if i.incident_id == incident_id), None)
    
    if not incident:
        return None
        
    agent = DispatchAgent()
    return await agent.recommend(context, incident)
