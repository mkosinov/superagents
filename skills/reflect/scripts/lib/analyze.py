"""LLM proposal generator + template filler.

In MVP: produces proposal markdown from violations + heuristics.
LLM call (via opencode subprocess) is added in Task 14.
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import Iterable
from .workflow_checks import Violation


def fill_template(template: str, **kwargs) -> str:
    """Substitute {var} placeholders in template."""
    # Extract known placeholders from the original template
    known_placeholders = set(re.findall(r"\{(\w+)\}", template))
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    # Only check placeholders that were in the original template
    leftover = [k for k in known_placeholders if "{" + k + "}" in result]
    if leftover:
        raise ValueError(f"Unfilled template placeholders: {leftover}")
    return result


def format_violations_table(violations: Iterable[Violation]) -> str:
    """Markdown table for violations list."""
    if not violations:
        return "_No violations._"
    lines = [
        "| Severity | Check | Session | Message |",
        "|----------|-------|---------|---------|",
    ]
    for v in violations:
        sid = v.session_id or "—"
        msg = v.message.replace("|", "\\|")
        lines.append(f"| {v.severity} | {v.check_name} | `{sid}` | {msg} |")
    return "\n".join(lines)


def format_violations_with_context(violations: Iterable[Violation]) -> str:
    """Markdown table including context fields."""
    if not violations:
        return "_No violations._"
    lines = [
        "| Severity | Check | Session | Message |",
        "|----------|-------|---------|---------|",
    ]
    for v in violations:
        sid = v.session_id or "—"
        msg = v.message.replace("|", "\\|")
        ctx = ", ".join(f"{k}={v.context[k]}" for k in v.context) if v.context else ""
        lines.append(f"| {v.severity} | {v.check_name} | `{sid}` | {msg} ({ctx}) |")
    return "\n".join(lines)


def generate_proposal_id(date: datetime, seq: int) -> str:
    """Generate proposal ID like 'prop-2026-06-19-001'."""
    return f"prop-{date.strftime('%Y-%m-%d')}-{seq:03d}"
