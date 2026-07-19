"""Input sanitisation — defence-in-depth against prompt injection.

Called on every user-supplied string *before* it is interpolated into
any LLM prompt.  This is not a silver bullet (no regex-only approach
is), but it strips known injection patterns and caps input length to
reduce the attack surface.
"""

from __future__ import annotations

import re

# ── Injection pattern catalogue ──────────────────────────────────────
# Each regex is applied case-insensitively.  We replace matches with
# ``[filtered]`` rather than silently deleting them, so the user gets
# feedback that something was stripped.

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(previous|above|all|prior)\s+(instructions?|prompts?|context)",
        r"disregard\s+(previous|above|all|prior)\s+(instructions?|prompts?|context)",
        r"you\s+are\s+now\s+",
        r"new\s+instructions?\s*:",
        r"system\s*:\s*",
        r"<\s*/?\s*system\s*>",
        r"```\s*(system|instruction)",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<\s*SYS\s*>>",
        r"<<\s*/\s*SYS\s*>>",
        r"</?(im_start|im_end|human|assistant|user|tool)>",
        r"BEGININSTRUCTION",
        r"ENDINSTRUCTION",
    ]
]

MAX_INPUT_LENGTH: int = 2000
"""Hard cap on user input character count."""

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "es", "fr", "pt", "hi"})
"""ISO 639-1 codes the system can handle."""


def sanitize_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """Sanitise a raw user string for safe LLM interpolation.

    1. Truncate to *max_length* characters.
    2. Strip null bytes and ASCII control characters (keep newlines).
    3. Replace known injection patterns with ``[filtered]``.

    Parameters
    ----------
    text:
        Raw user input.
    max_length:
        Maximum allowed character count.

    Returns
    -------
    str
        Sanitised text, stripped of leading/trailing whitespace.
    """
    # 1 — Truncate
    text = text[:max_length]

    # 2 — Remove control characters (preserve \\n, \\r, \\t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 3 — Neutralise injection patterns
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[filtered]", text)

    return text.strip()


def validate_language_code(code: str) -> str:
    """Normalise and clamp a language code to supported set.

    Parameters
    ----------
    code:
        Raw language code from client.

    Returns
    -------
    str
        A valid ISO code from ``SUPPORTED_LANGUAGES``, defaulting to
        ``"en"`` when the input is unrecognised.
    """
    normalised = code.lower().strip()[:5]
    return normalised if normalised in SUPPORTED_LANGUAGES else "en"
