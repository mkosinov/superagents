"""LLM proposal generator + template filler.

In MVP: produces proposal markdown from violations + heuristics.
LLM call (via opencode subprocess) is added in Task 14.
"""
from __future__ import annotations
import json
import re
import subprocess
from datetime import datetime
from typing import Iterable
from .redactor import redact_secrets
from .config import ReflectConfig
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


# ===== LLM integration =====


def call_llm(
    prompt: str,
    config: ReflectConfig,
    model: str = "omniroute/flash",
) -> str:
    """Call opencode via subprocess to run LLM."""
    safe_prompt = redact_secrets(prompt)
    try:
        result = subprocess.run(
            ["opencode", "run", "--model", model, safe_prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return f"[LLM error: {result.stderr[:200]}]"
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"[LLM unavailable: {e}]"


def generate_proposal_with_llm(
    *,
    violation: Violation,
    template_str: str,
    config: ReflectConfig,
) -> dict:
    """Generate proposal content using LLM based on violation."""
    prompt = f"""You are a workflow analyst. Given this violation, generate a concrete proposal.

Violation: {violation.check_name} ({violation.severity})
Title: {violation.title}
Message: {violation.message}
Context: {violation.context}

Respond with JSON: {{"title": "...", "target": "path/to/file", "rationale": "...", "diff": "..."}}
"""
    response = call_llm(prompt, config)
    try:
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1:
            return json.loads(response[start:end + 1])
    except json.JSONDecodeError:
        pass
    return {
        "title": violation.title,
        "target": "",
        "rationale": violation.message,
        "diff": "",
    }
