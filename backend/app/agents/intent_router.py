"""Intent Router Agent — classifies free-text into actionable intents.

Key design points
-----------------
* **Medical/emergency keyword bypass**: a hardcoded regex scan fires
  *before* any LLM call, guaranteeing sub-millisecond routing for
  safety-critical inputs.  This is intentional: we never want an LLM
  latency spike or hallucination between "heart attack" and routing
  to the medical agent.
* All other intents are classified via Gemini structured-JSON output.
* The agent is stateless — it receives ``UserContext`` but doesn't
  modify it.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..models.context import UserContext
from ..models.schemas import Intent
from ..services.gemini_client import generate_json
from ..services.input_sanitizer import sanitize_input

logger = logging.getLogger(__name__)

# ── Emergency keyword patterns ───────────────────────────────────────
# Compiled once at import time.  The bar is deliberately low (err on
# the side of routing to medical even for false positives).

_EMERGENCY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(heart\s*attack|cardiac|chest\s*pain)\b",
        r"\b(seizure|epilep|convuls)\b",
        r"\b(unconscious|unresponsive|faint(ed|ing)?|collapse[ds]?)\b",
        r"\b(can'?t\s*breathe?|choking|asphyxia|breathing\s*(difficult|problem|emergency))\b",
        r"\b(anaphyla|allergic\s*shock|epipen)\b",
        r"\b(stroke|cerebr(al|ovascular))\b",
        r"\b(bleeding\s*(heavily|profuse|won'?t\s*stop)|hemorrhag)\b",
        r"\b(medical\s*emergency|call\s*(an?\s*)?ambulance|need\s*(a\s*)?doctor|need\s*help\s*(urgent|now|immediate))\b",
        r"\b(fire|bomb\s*threat|active\s*shooter|evacuat\w*)",
        r"\b(defibrillat|AED|CPR)\b",
        r"\b(heat\s*stroke|heat\s*exhaustion|hypothermia)\b",
        r"\b(broken\s*bone|fracture|severe\s*injury)\b",
        # Spanish
        r"\b(emergencia\s*m[eé]dica|ambulancia|no\s*puede\s*respirar|ataque\s*al\s*coraz[oó]n)\b",
        # French
        r"\b(urgence\s*m[eé]dicale|crise\s*cardiaque|ne\s*peut\s*pas\s*respirer)\b",
        # Hindi (transliterated)
        r"\b(emergency|doctor\s*bulao|ambulance\s*bulao)\b",
    ]
]

# ── Intent classification prompt ─────────────────────────────────────

_CLASSIFICATION_SYSTEM_PROMPT = """You are an intent classifier for a FIFA World Cup 2026 stadium assistant called OffsideOperations.

Classify the user's message into exactly ONE of these intents:
- navigation: asking for directions, how to get somewhere, where something is located
- crowd_status: asking about crowd levels, how busy an area is, congestion
- transport: asking about shuttles, metro, buses, how to get to/from the stadium
- sustainability: asking about eco-friendly options, carbon footprint, green choices
- lost_found: reporting a lost or found item
- dispatch: requesting volunteer dispatch, reporting an incident that needs staff
- wellbeing: asking about volunteer wellbeing, fatigue, break schedules
- announcement: requesting a PA announcement or broadcast
- medical_emergency: any medical or safety emergency (but these are usually caught earlier)
- general_query: anything that doesn't fit the above categories

Consider the user's role: {role}
Consider the user's language: {language}

Respond with JSON: {{"intent": "<intent_name>", "entities": {{"location": "...", "item": "...", "zone": "..."}}}}
Only include entity keys that are relevant. The entities object can be empty."""


class IntentRouterAgent:
    """Classifies user messages into intents for downstream routing.

    Usage::

        router = IntentRouterAgent()
        intent, entities = await router.classify(context, "Where is the nearest restroom?")
    """

    async def classify(
        self,
        context: UserContext,
        message: str,
    ) -> tuple[Intent, dict]:
        """Classify a user message into an intent.

        Parameters
        ----------
        context:
            The current user's session context.
        message:
            Raw user message (will be sanitised internally).

        Returns
        -------
        tuple[Intent, dict]
            The classified intent and any extracted entities.
        """
        clean_message = sanitize_input(message)

        # ── Safety override: medical/emergency bypass ────────────────
        if self._is_emergency(clean_message):
            logger.info(
                "Emergency keyword detected — bypassing LLM (session=%s).",
                context.session_id,
            )
            return Intent.MEDICAL_EMERGENCY, {"emergency_detected": True}

        # ── LLM classification ───────────────────────────────────────
        return await self._classify_with_llm(context, clean_message)

    def _is_emergency(self, message: str) -> bool:
        """Check for emergency keywords — no LLM, no latency."""
        return any(p.search(message) for p in _EMERGENCY_PATTERNS)

    async def _classify_with_llm(
        self,
        context: UserContext,
        message: str,
    ) -> tuple[Intent, dict]:
        """Use Gemini structured JSON output to classify intent."""
        system_prompt = _CLASSIFICATION_SYSTEM_PROMPT.format(
            role=context.role,
            language=context.language,
        )
        user_prompt = f"Classify this message:\n\n{message}"

        result = await generate_json(
            user_prompt,
            system_instruction=system_prompt,
            temperature=0.1,
        )

        if result and "intent" in result:
            try:
                intent = Intent(result["intent"])
                entities = result.get("entities", {})
                if not isinstance(entities, dict):
                    entities = {}
                return intent, entities
            except ValueError:
                logger.warning(
                    "Unknown intent from LLM: %s — defaulting to general_query.",
                    result.get("intent"),
                )

        # Fallback: general query
        return Intent.GENERAL_QUERY, {}
