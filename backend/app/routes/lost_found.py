"""Lost & Found API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..agents.lost_found_agent import LostFoundAgent
from ..models.context import UserContext
from ..models.schemas import FoundItem, LostFoundMatch, LostItem
from .session import get_current_session

router = APIRouter()


@router.post("/lost-found/report", response_model=LostItem | FoundItem)
async def report_item(
    description: str,
    context: Annotated[UserContext, Depends(get_current_session)],
    zone: str | None = None,
) -> LostItem | FoundItem:
    """Report a lost (fan) or found (volunteer) item."""
    agent = LostFoundAgent()
    if context.role == "fan":
        return await agent.report_lost(context, description, zone)
    return await agent.report_found(context, description, zone)


@router.get("/lost-found/matches", response_model=list[LostFoundMatch])
async def get_matches(
    min_score: float = Query(0.3, description="Minimum similarity score")
) -> list[LostFoundMatch]:
    """Get high-confidence matches between lost and found items."""
    agent = LostFoundAgent()
    return await agent.find_matches(min_score=min_score)
