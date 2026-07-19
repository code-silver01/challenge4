"""Centralised Google Gemini API client.

Wraps the ``google-genai`` SDK with:
* Structured JSON output mode (``response_mime_type="application/json"``)
* Function-calling support
* Retry logic with exponential backoff
* Graceful fallback when ``GEMINI_API_KEY`` is empty (returns None)

No agent should call the Gemini API directly — always go through this
module so we have a single place to add logging, rate limiting, and
error handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from ..config.settings import get_settings

logger = logging.getLogger(__name__)

# Lazy-initialised client — avoids import-time errors when key is empty
_client: Any = None
_initialised: bool = False


def _get_client() -> Any:
    """Return the ``google.genai.Client``, or None if no API key."""
    global _client, _initialised  # noqa: PLW0603
    if _initialised:
        return _client

    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is empty — LLM features disabled.")
        _initialised = True
        return None

    try:
        from google import genai  # type: ignore[import-untyped]

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
        _initialised = True
        logger.info("Gemini client initialised (model=%s).", settings.GEMINI_MODEL)
    except Exception:
        logger.exception("Failed to initialise Gemini client.")
        _initialised = True

    return _client


async def generate_text(
    prompt: str,
    *,
    system_instruction: str | None = None,
    max_retries: int = 2,
    temperature: float = 0.3,
) -> Optional[str]:
    """Generate plain-text from Gemini.

    Parameters
    ----------
    prompt:
        The user/instruction prompt.
    system_instruction:
        Optional system prompt prepended by the model.
    max_retries:
        Number of retries on transient failures.
    temperature:
        Sampling temperature (lower = more deterministic).

    Returns
    -------
    str | None
        The model's text response, or ``None`` if the call failed.
    """
    client = _get_client()
    if client is None:
        return None

    settings = get_settings()
    config: dict[str, Any] = {"temperature": temperature}
    if system_instruction:
        config["system_instruction"] = system_instruction

    from google.genai import types  # type: ignore[import-untyped]

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(**config),
            )
            if response and response.text:
                return response.text.strip()
            return None
        except Exception as exc:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    "Gemini call failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    max_retries + 1,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Gemini call failed after %d attempts.", max_retries + 1)
                return None
    return None


async def generate_json(
    prompt: str,
    *,
    system_instruction: str | None = None,
    max_retries: int = 2,
    temperature: float = 0.2,
) -> Optional[dict[str, Any]]:
    """Generate structured JSON from Gemini.

    Uses ``response_mime_type="application/json"`` so the model is
    constrained to return valid JSON.

    Returns
    -------
    dict | None
        Parsed JSON, or ``None`` on failure.
    """
    client = _get_client()
    if client is None:
        return None

    settings = get_settings()

    from google.genai import types  # type: ignore[import-untyped]

    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
    )
    if system_instruction:
        config.system_instruction = system_instruction

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
            if response and response.text:
                return json.loads(response.text)
            return None
        except json.JSONDecodeError:
            logger.warning("Gemini returned invalid JSON on attempt %d.", attempt + 1)
            if attempt == max_retries:
                return None
        except Exception as exc:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    "Gemini JSON call failed (attempt %d/%d), retrying: %s",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Gemini JSON call failed after %d attempts.", max_retries + 1
                )
                return None
    return None


def reset_client() -> None:
    """Reset the lazy-initialised client — used in tests."""
    global _client, _initialised  # noqa: PLW0603
    _client = None
    _initialised = False
