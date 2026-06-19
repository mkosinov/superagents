"""16 workflow compliance checks mapped to SuperAgents Key Principles.

Each check is a function: (sessions, tool_calls, config) -> list[Violation]
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from typing import Any


@dataclass
class Violation:
    check_name: str
    severity: str  # critical | warning | info
    session_id: str | None
    title: str
    message: str
    context: dict = field(default_factory=dict)
    
    def to_proposal_dict(self) -> dict:
        return {
            "check": self.check_name,
            "severity": self.severity,
            "session_id": self.session_id,
            "title": self.title,
            "message": self.message,
            **self.context,
        }


# ===== CRITICAL CHECKS =====

def check_controller_never_implements(sessions, tool_calls, config):
    """Principle 1: architect must not call edit/write/apply_patch."""
    if not config.workflow_checks["controller_never_implements"].enabled:
        return []
    arch_sessions = {s["id"] for s in sessions if s["agent"] == "architect"}
    code_tools = {"edit", "write", "apply_patch"}
    edits_by_session = Counter(
        tc["session_id"] for tc in tool_calls
        if tc["session_id"] in arch_sessions
        and tc["tool"] in code_tools
        and tc.get("status") == "completed"
    )
    violations = []
    for sid, count in edits_by_session.items():
        session = next((s for s in sessions if s["id"] == sid), None)
        if session:
            violations.append(Violation(
                check_name="controller_never_implements",
                severity="critical",
                session_id=sid,
                title=session["title"],
                message=f"Architect edited {count} file(s) directly. Violates Principle 1.",
                context={"edits": count},
            ))
    return violations


def check_stuck_in_retry(sessions, tool_calls, config):
    """Same bash command 3+ times in one session without variation."""
    cfg = config.workflow_checks["stuck_in_retry"]
    if not cfg.enabled:
        return []
    min_repeats = cfg.options.get("min_repeats", 3)
    cmds_by_session = defaultdict(Counter)
    for tc in tool_calls:
        if tc["tool"] == "bash" and tc.get("cmd"):
            cmds_by_session[tc["session_id"]][tc["cmd"]] += 1
    violations = []
    for sid, counter in cmds_by_session.items():
        for cmd, repeats in counter.items():
            if repeats >= min_repeats:
                session = next((s for s in sessions if s["id"] == sid), None)
                if session:
                    violations.append(Violation(
                        check_name="stuck_in_retry",
                        severity="critical",
                        session_id=sid,
                        title=session["title"],
                        message=f"Bash command repeated {repeats}× without variation. Diagnose before retry.",
                        context={"cmd": cmd, "repeats": repeats},
                    ))
    return violations


def check_same_error_repeated(sessions, tool_calls, config):
    """Same tool+error in 3+ different sessions."""
    cfg = config.workflow_checks["same_error_repeated"]
    if not cfg.enabled:
        return []
    min_sessions = cfg.options.get("min_sessions", 3)
    errs_by_key = defaultdict(set)
    for tc in tool_calls:
        if tc.get("error"):
            errs_by_key[(tc["tool"], tc["error"])].add(tc["session_id"])
    violations = []
    for (tool, error), sids in errs_by_key.items():
        if len(sids) >= min_sessions:
            violations.append(Violation(
                check_name="same_error_repeated",
                severity="critical",
                session_id=None,
                title=f"{tool} failing in {len(sids)} sessions",
                message=f"Tool '{tool}' fails with same error in {len(sids)} sessions. Systemic issue.",
                context={"tool": tool, "error": error, "session_count": len(sids)},
            ))
    return violations


def check_mandatory_reviewer_for_code(sessions, tool_calls, config):
    """Every implementer session must have spec-reviewer + code-quality-reviewer as children."""
    cfg = config.workflow_checks["mandatory_reviewer_for_code"]
    if not cfg.enabled:
        return []
    children_by_parent = defaultdict(list)
    for s in sessions:
        if s["parent_id"]:
            children_by_parent[s["parent_id"]].append(s)
    implementer_agents = {"frontend-coder", "backend-coder"}
    violations = []
    for s in sessions:
        if s["agent"] not in implementer_agents:
            continue
        children = children_by_parent.get(s["id"], [])
        child_agents = {c["agent"] for c in children}
        missing = []
        if "spec-reviewer" not in child_agents:
            missing.append("spec-reviewer")
        if "code-quality-reviewer" not in child_agents:
            missing.append("code-quality-reviewer")
        if missing:
            violations.append(Violation(
                check_name="mandatory_reviewer_for_code",
                severity="critical",
                session_id=s["id"],
                title=s["title"],
                message=f"Implementer session missing reviewers: {', '.join(missing)}",
                context={"missing": missing, "present": list(child_agents)},
            ))
    return violations


def check_gate_compliance(sessions, tool_calls, config):
    """Stub: returns []. No gate markers in opencode.db yet."""
    cfg = config.workflow_checks["gate_compliance"]
    if not cfg.enabled:
        return []
    return []
