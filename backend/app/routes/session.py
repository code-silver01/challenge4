"""Session API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..models.context import UserContext
from ..models.schemas import SessionCreateRequest, SessionResponse
from ..services.repository import RepositoryInterface, get_repository

router = APIRouter()


async def get_current_session(
    session_id: str,
    repo: Annotated[RepositoryInterface, Depends(get_repository)],
) -> UserContext:
    """Dependency to retrieve a session by ID."""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    context = await repo.get_session(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    return context


@router.post("/session", response_model=SessionResponse)
async def create_or_update_session(
    request: SessionCreateRequest,
    repo: Annotated[RepositoryInterface, Depends(get_repository)],
) -> SessionResponse:
    """Create a new session or update an existing one."""
    context = UserContext(
        role=request.role,
        language=request.language,
        accessibility_needs=request.accessibility_needs,
        ticket_zone=request.ticket_zone,
    )
    await repo.save_session(context)
    return SessionResponse(
        session_id=context.session_id,
        role=context.role,
        language=context.language,
        accessibility_needs=[str(x) for x in context.accessibility_needs],
        ticket_zone=context.ticket_zone,
    )
