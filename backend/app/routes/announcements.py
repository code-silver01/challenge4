"""Announcements API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..agents.announcement_agent import AnnouncementAgent
from ..models.context import UserContext
from ..models.schemas import AnnouncementRequest, AnnouncementResponse
from .session import get_current_session

router = APIRouter()


@router.post("/announcements/draft", response_model=AnnouncementResponse)
async def draft_announcement(
    request: AnnouncementRequest,
    context: Annotated[UserContext, Depends(get_current_session)],
) -> AnnouncementResponse:
    """Draft a multilingual PA announcement from a situation note."""
    agent = AnnouncementAgent()
    return await agent.draft(context, request)
