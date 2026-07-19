"""FastAPI application entry point.

Wires together all agents, routes, middleware (CORS, rate limiting),
and background tasks (crowd simulation).
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from .agents.crowd_agent import CrowdAgent
from .config.settings import get_settings
from .routes import (
    announcements,
    chat,
    crowd,
    dispatch,
    incidents,
    lost_found,
    session,
    wellbeing,
)
from .services.repository import get_repository

logger = logging.getLogger(__name__)

# ── Background task: crowd simulation ────────────────────────────────

_crowd_agent: CrowdAgent | None = None


async def _crowd_simulation_loop() -> None:
    """Periodically tick the crowd simulator for demo realism."""
    global _crowd_agent
    _crowd_agent = CrowdAgent(repo=get_repository())
    await _crowd_agent.seed_initial_data()
    logger.info("Crowd simulation started.")

    while True:
        try:
            await _crowd_agent.simulate_tick()
        except Exception:
            logger.exception("Crowd simulation tick failed.")
        await asyncio.sleep(5)  # Tick every 5 seconds


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — start/stop background tasks."""
    # Seed demo volunteers
    await _seed_demo_data()

    task = asyncio.create_task(_crowd_simulation_loop())
    logger.info("OffsideOperations backend started.")
    yield
    task.cancel()
    logger.info("OffsideOperations backend stopped.")


async def _seed_demo_data() -> None:
    """Seed demo volunteers and initial data for the hackathon demo."""
    from datetime import datetime, timedelta, timezone
    from .models.schemas import VolunteerProfile

    repo = get_repository()
    now = datetime.now(timezone.utc)

    demo_volunteers = [
        VolunteerProfile(
            volunteer_id="vol-001", name="Priya Sharma",
            skills=["medical", "accessibility", "crowd_control"],
            current_zone="Concourse_N",
            shift_start=now - timedelta(hours=2.5),
            incidents_handled=7, open_incident_count=2,
        ),
        VolunteerProfile(
            volunteer_id="vol-002", name="Carlos Rodriguez",
            skills=["security", "crowd_control", "maintenance"],
            current_zone="Gate_1",
            shift_start=now - timedelta(hours=1),
            incidents_handled=3, open_incident_count=0,
        ),
        VolunteerProfile(
            volunteer_id="vol-003", name="Aisha Bello",
            skills=["medical", "lost_found", "accessibility"],
            current_zone="Concourse_E",
            shift_start=now - timedelta(hours=4),
            incidents_handled=9, open_incident_count=1,
        ),
        VolunteerProfile(
            volunteer_id="vol-004", name="Jean-Pierre Dubois",
            skills=["security", "crowd_control"],
            current_zone="Gate_3",
            shift_start=now - timedelta(hours=3),
            incidents_handled=5, open_incident_count=1,
        ),
        VolunteerProfile(
            volunteer_id="vol-005", name="Ravi Patel",
            skills=["maintenance", "accessibility", "lost_found"],
            current_zone="Concourse_W",
            shift_start=now - timedelta(hours=0.5),
            incidents_handled=1, open_incident_count=0,
        ),
    ]
    for vol in demo_volunteers:
        await repo.save_volunteer(vol)

    logger.info("Seeded %d demo volunteers.", len(demo_volunteers))


# ── App factory ──────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="OffsideOperations — GenAI Stadium Companion",
        description="Multi-agent GenAI assistant for FIFA World Cup 2026 stadiums.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── CORS (locked to explicit origins, never '*') ─────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # ── Security Headers ─────────────────────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Append strict security headers to all responses."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # ── Global Exception Handler ─────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch all unhandled exceptions to prevent stack trace leaks."""
        logger.error(f"Unhandled Exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred. Please try again later."},
        )

    # ── Routes ───────────────────────────────────────────────────
    app.include_router(session.router, prefix="/api", tags=["Session"])
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(crowd.router, prefix="/api", tags=["Crowd"])
    app.include_router(incidents.router, prefix="/api", tags=["Incidents"])
    app.include_router(dispatch.router, prefix="/api", tags=["Dispatch"])
    app.include_router(lost_found.router, prefix="/api", tags=["Lost & Found"])
    app.include_router(wellbeing.router, prefix="/api", tags=["Wellbeing"])
    app.include_router(announcements.router, prefix="/api", tags=["Announcements"])

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "offsideoperations"}

    # ── Serve React Frontend ─────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    
    if os.path.isdir(static_dir):
        # Mount the static directory to serve assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
        
        # Catch-all route to serve index.html for React Router compatibility
        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str) -> FileResponse:
            """Serve frontend assets or fallback to index.html."""
            # If the file exists directly (like favicon, vite.svg), serve it
            file_path = os.path.join(static_dir, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            # Otherwise, fall back to React's index.html
            return FileResponse(os.path.join(static_dir, "index.html"))
    else:
        logger.warning(f"Static directory not found at {static_dir}. Frontend will not be served.")

    return app


app = create_app()
