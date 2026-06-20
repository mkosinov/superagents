"""Secret redactor for LLM-bound session text.

Replaces API keys, tokens, passwords with [REDACTED] before sending to LLM.
"""
from __future__ import annotations
import re

REDACT_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("google_api_key", re.compile(r"AIza[A-Za-z0-9_-]{35,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}")),
    ("password_env", re.compile(r"(?i)(password|passwd|secret|token|api_key|apikey)\s*[=:]\s*['\"]?([^\s'\"]+)")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("slack_token", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
]


def redact_secrets(text: str) -> str:
    """Replace secret-like patterns with [REDACTED]."""
    for _name, pattern in REDACT_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
