"""Multilingual PA Announcement Drafter.

Organizer types a short situation note → Gemini drafts a calm, clear,
PA-ready announcement in all 5 supported languages simultaneously,
returned as structured JSON keyed by language code.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..models.context import UserContext
from ..models.schemas import AnnouncementRequest, AnnouncementResponse
from ..services.gemini_client import generate_json
from ..services.input_sanitizer import sanitize_input

logger = logging.getLogger(__name__)

_ANNOUNCEMENT_SYSTEM = """You are a professional PA announcement writer for FIFA World Cup 2026.

Given a situation note from an organizer, draft a calm, clear, PA-ready announcement in ALL FIVE of these languages:
- English (en)
- Spanish (es)
- French (fr)
- Portuguese (pt)
- Hindi (hi)

Situation note: "{note}"
Priority level: {priority}

Guidelines:
- Keep each announcement under 3 sentences
- Use a calm, reassuring tone even for urgent situations
- Be specific about what fans should do
- For "urgent" priority, start with "Attention please" in each language
- For "warning" priority, be informative but not alarming
- For "info" priority, be friendly and helpful
- Do NOT use all-caps or excessive punctuation

Respond in JSON:
{{
  "en": "English announcement text",
  "es": "Spanish announcement text",
  "fr": "French announcement text",
  "pt": "Portuguese announcement text",
  "hi": "Hindi announcement text"
}}"""


class AnnouncementAgent:
    """Drafts multilingual PA announcements from situation notes.

    Usage::

        agent = AnnouncementAgent()
        response = await agent.draft(context, request)
    """

    async def draft(
        self,
        context: UserContext,
        request: AnnouncementRequest,
    ) -> AnnouncementResponse:
        """Draft a multilingual PA announcement.

        Parameters
        ----------
        context:
            The organizer's context.
        request:
            Situation note and priority level.

        Returns
        -------
        AnnouncementResponse
            Announcements in all 5 languages + metadata.
        """
        clean_note = sanitize_input(request.situation_note)

        prompt = _ANNOUNCEMENT_SYSTEM.format(
            note=clean_note,
            priority=request.priority,
        )

        result = await generate_json(prompt, temperature=0.3)

        if result:
            # Validate all 5 languages are present
            languages = {"en", "es", "fr", "pt", "hi"}
            announcements = {
                lang: result.get(lang, "")
                for lang in languages
            }
            # Fill any missing languages with English fallback
            en_text = announcements.get("en", clean_note)
            for lang in languages:
                if not announcements[lang]:
                    announcements[lang] = en_text

            return AnnouncementResponse(
                announcements=announcements,
                priority=request.priority,
            )

        # Fallback: use the raw note as the announcement in all languages
        return self._fallback_announcement(clean_note, request.priority)

    @staticmethod
    def _fallback_announcement(
        note: str, priority: str
    ) -> AnnouncementResponse:
        """Generate a basic announcement without the LLM.

        Only produces English — in production, this would be
        supplemented by a translation service.
        """
        prefix = {
            "urgent": "⚠️ Attention please: ",
            "warning": "📢 ",
            "info": "ℹ️ ",
        }.get(priority, "")

        text = f"{prefix}{note}"

        return AnnouncementResponse(
            announcements={
                "en": text,
                "es": f"{prefix}{note} (traducción pendiente)",
                "fr": f"{prefix}{note} (traduction en attente)",
                "pt": f"{prefix}{note} (tradução pendente)",
                "hi": f"{prefix}{note} (अनुवाद लंबित)",
            },
            priority=priority,
            timestamp=datetime.now(timezone.utc),
        )
