"""Chat API routes — the main conversational endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ..agents.crowd_agent import CrowdAgent
from ..agents.dispatch_agent import DispatchAgent
from ..agents.intent_router import IntentRouterAgent
from ..agents.lost_found_agent import LostFoundAgent
from ..agents.navigation_agent import NavigationAgent
from ..agents.ops_agent import OpsAgent
from ..agents.transport_agent import TransportAgent
from ..agents.wellbeing_agent import WellbeingAgent
from ..config.settings import get_settings
from ..models.context import UserContext
from ..models.schemas import ChatRequest, ChatResponse, Intent
from ..services.rate_limiter import RateLimiter
from .session import get_current_session

logger = logging.getLogger(__name__)
router = APIRouter()

# Instantiate agents once
_intent_router = IntentRouterAgent()
_nav_agent = NavigationAgent()
_transport_agent = TransportAgent()
_ops_agent = OpsAgent()
_lf_agent = LostFoundAgent()

# Global rate limiter
_settings = get_settings()
_rate_limiter = RateLimiter(max_rpm=_settings.RATE_LIMIT_RPM)


def check_rate_limit(request: Request, chat_req: ChatRequest) -> None:
    """Enforce rate limits per session."""
    if not _rate_limiter.allow(chat_req.session_id):
        logger.warning("Rate limit exceeded for session %s", chat_req.session_id)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again in a few moments.",
        )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: Request,
    chat_req: ChatRequest,
    context: Annotated[UserContext, Depends(get_current_session)],
) -> ChatResponse:
    """Process a user message and dispatch to the right agent."""
    check_rate_limit(request, chat_req)

    # 1. Classify intent
    intent, entities = await _intent_router.classify(context, chat_req.message)
    response_text = "I'm not sure how to help with that."
    data = None

    # 2. Route to appropriate agent
    try:
        if intent == Intent.MEDICAL_EMERGENCY:
            # Immediate routing to medical
            response_text = (
                "🚨 MEDICAL EMERGENCY PROTOCOL INITIATED. "
                "Help has been dispatched to your location. Please stay where you are."
            )
            # In a real app, this would trigger an immediate push notification to ops

        elif intent == Intent.NAVIGATION:
            destination = entities.get("location")
            if destination:
                nav_result = await _nav_agent.navigate(context, destination)
                response_text = nav_result.pop("narration", "")
                data = nav_result
            else:
                response_text = "Where would you like to go?"

        elif intent == Intent.CROWD_STATUS:
            zone = entities.get("zone")
            # Lazy init to avoid circular deps during startup
            crowd_agent = CrowdAgent()
            response_text = await crowd_agent.get_zone_summary(context, zone)

        elif intent == Intent.TRANSPORT:
            destination = entities.get("destination", "Central_Metro_Station") # Default for demo
            transport_result = await _transport_agent.get_options(context, destination)
            if transport_result.options:
                response_text = (
                    f"{transport_result.recommendation}\n\n"
                    f"{transport_result.sustainability_tip}"
                )
                data = transport_result.model_dump()
            else:
                response_text = transport_result.recommendation

        elif intent == Intent.LOST_FOUND:
            item_desc = entities.get("item", chat_req.message)
            zone = entities.get("zone")
            if context.role == "fan":
                item = await _lf_agent.report_lost(context, item_desc, zone)
                response_text = (
                    f"I've logged your lost item ({item.features.get('item_type', 'item') if item.features else 'item'}). "
                    "We'll notify you if it's found."
                )
            else:
                found_item = await _lf_agent.report_found(context, item_desc, zone)
                response_text = "Found item logged. Thank you."

        elif intent == Intent.DISPATCH:
            if context.role == "fan":
                response_text = "I can only dispatch volunteers for organizers."
            else:
                report = await _ops_agent.create_incident(context, chat_req.message)
                dispatch_agent = DispatchAgent()
                rec = await dispatch_agent.recommend(context, report)
                if rec:
                    response_text = (
                        f"Incident logged. Recommended {rec.volunteer_name} for dispatch. "
                        f"Reasoning: {rec.reasoning}"
                    )
                    data = rec.model_dump()
                else:
                    response_text = "Incident logged, but no volunteers are currently available."

        elif intent == Intent.WELLBEING:
            if context.role == "organizer":
                wb_agent = WellbeingAgent()
                alerts = await wb_agent.check_all(context)
                if alerts:
                    response_text = "\n".join(a.nudge_message for a in alerts[:3])
                else:
                    response_text = "All volunteers are within healthy shift limits."
            else:
                response_text = "Wellbeing metrics are only available to organizers."

        elif intent == Intent.ANNOUNCEMENT:
            if context.role == "organizer":
                from ..agents.announcement_agent import AnnouncementAgent
                from ..models.schemas import AnnouncementRequest
                
                req = AnnouncementRequest(situation_note=chat_req.message, priority="info")
                announcement_agent = AnnouncementAgent()
                resp = await announcement_agent.draft(context, req)
                response_text = "Here is the drafted announcement in 5 languages:"
                data = resp.model_dump()
            else:
                response_text = "Only organizers can draft PA announcements."

        elif intent == Intent.GENERAL_QUERY:
            response_text = (
                "I'm OffsideOperations, your stadium assistant. You can ask me for directions, "
                "crowd status, transport options, or report lost items."
            )

    except Exception as e:
        logger.exception("Error processing chat intent: %s", intent)
        response_text = "I encountered an error trying to process your request."

    return ChatResponse(
        session_id=context.session_id,
        intent=intent,
        response=response_text,
        data=data,
        language=context.language,
    )
