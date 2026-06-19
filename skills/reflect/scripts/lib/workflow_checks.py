"""17 workflow compliance checks mapped to SuperAgents Key Principles.

Each check is a function: (sessions, tool_calls, config) -> list[Violation]
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from .config import ReflectConfig


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

def check_controller_never_implements(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
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


def check_stuck_in_retry(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
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


def check_same_error_repeated(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
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


def check_mandatory_reviewer_for_code(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
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


def check_gate_compliance(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Stub: returns []. No gate markers in opencode.db yet."""
    cfg = config.workflow_checks["gate_compliance"]
    if not cfg.enabled:
        return []
    return []


# ===== WARNING CHECKS =====


def check_tdd_red_first(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """First tool in implementer session should be a test run, not edit."""
    cfg = config.workflow_checks["tdd_red_first"]
    if not cfg.enabled:
        return []
    implementer_agents = {"frontend-coder", "backend-coder"}
    violations = []
    for s in sessions:
        if s["agent"] not in implementer_agents:
            continue
        session_tcs = sorted(
            [tc for tc in tool_calls if tc["session_id"] == s["id"]],
            key=lambda t: t["time_created"],
        )
        if not session_tcs:
            continue
        first = session_tcs[0]
        if first["tool"] in ("edit", "write", "apply_patch"):
            violations.append(Violation(
                check_name="tdd_red_first",
                severity="warning",
                session_id=s["id"],
                title=s["title"],
                message=f"First tool was '{first['tool']}', not a test run. TDD violated.",
                context={"first_tool": first["tool"]},
            ))
    return violations


def check_max_review_loops(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """More than max_loops reviewers per parent (warning)."""
    cfg = config.workflow_checks["max_review_loops"]
    if not cfg.enabled:
        return []
    max_loops = cfg.options.get("max_loops", 3)
    reviewers = {"spec-reviewer", "code-quality-reviewer"}
    by_parent = Counter()
    for s in sessions:
        if s["agent"] in reviewers and s["parent_id"]:
            by_parent[s["parent_id"]] += 1
    violations = []
    for parent_id, count in by_parent.items():
        if count > max_loops:
            parent = next((s for s in sessions if s["id"] == parent_id), None)
            if parent:
                violations.append(Violation(
                    check_name="max_review_loops",
                    severity="warning",
                    session_id=parent_id,
                    title=parent["title"],
                    message=f"{count} review iterations > max {max_loops}. Task too large.",
                    context={"loops": count, "max": max_loops},
                ))
    return violations


def check_regression_test_on_bugfix(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Bug-fix session should have new test added."""
    cfg = config.workflow_checks["regression_test_on_bugfix"]
    if not cfg.enabled:
        return []
    bugfix_keywords = ("fix", "bug", "patch", "hotfix")
    violations = []
    for s in sessions:
        if not any(kw in s["title"].lower() for kw in bugfix_keywords):
            continue
        session_tcs = [tc for tc in tool_calls if tc["session_id"] == s["id"]]
        has_test_run = any(
            tc["tool"] == "bash" and tc.get("cmd") and
            any(p in tc["cmd"] for p in ("vitest", "pytest", "playwright", "test"))
            for tc in session_tcs
        )
        if not has_test_run:
            violations.append(Violation(
                check_name="regression_test_on_bugfix",
                severity="warning",
                session_id=s["id"],
                title=s["title"],
                message="Bug-fix session has no test run. Add regression test.",
                context={},
            ))
    return violations


def check_arch_session_too_long(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Architect session > max_minutes without subagent dispatch."""
    cfg = config.workflow_checks["arch_session_too_long"]
    if not cfg.enabled:
        return []
    max_min = cfg.options.get("max_minutes_without_subagent", 30)
    children = {s["parent_id"] for s in sessions if s["parent_id"]}
    violations = []
    for s in sessions:
        if s["agent"] != "architect" or s["parent_id"] is not None:
            continue
        duration_min = (s["time_updated"] - s["time_created"]) / 1000 / 60
        if duration_min > max_min and s["id"] not in children:
            violations.append(Violation(
                check_name="arch_session_too_long",
                severity="warning",
                session_id=s["id"],
                title=s["title"],
                message=f"Architect session {duration_min:.1f}min without subagent. Over-thinking or self-implementing.",
                context={"duration_min": duration_min, "max_min": max_min},
            ))
    return violations


def check_skill_triggered_when_should(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Stub: requires per-project skill_triggers config."""
    cfg = config.workflow_checks["skill_triggered_when_should"]
    if not cfg.enabled:
        return []
    return []


def check_subagent_completion_rate(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Subagent completion rate below threshold (warning)."""
    cfg = config.workflow_checks["subagent_completion_rate"]
    if not cfg.enabled:
        return []
    min_rate = cfg.options.get("min_rate", 0.8)
    by_agent: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in sessions:
        if s["parent_id"] is None:
            continue
        by_agent[s["agent"]][1] += 1
        if s["time_archived"] is not None:
            by_agent[s["agent"]][0] += 1
    violations = []
    for agent, (archived, total) in by_agent.items():
        if total < 3:
            continue
        rate = archived / total
        if rate < min_rate:
            violations.append(Violation(
                check_name="subagent_completion_rate",
                severity="warning",
                session_id=None,
                title=f"{agent} completion",
                message=f"{agent} completion rate {rate:.0%} < target {min_rate:.0%}",
                context={"agent": agent, "rate": rate, "archived": archived, "total": total},
            ))
    return violations


def check_first_time_right(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Warning: >3 review iterations for any wave."""
    cfg = config.workflow_checks["first_time_right"]
    if not cfg.enabled:
        return []
    reviewers = {"spec-reviewer", "code-quality-reviewer"}
    by_parent = Counter()
    for s in sessions:
        if s["agent"] in reviewers and s["parent_id"]:
            by_parent[s["parent_id"]] += 1
    violations = []
    three_plus = sum(1 for c in by_parent.values() if c >= 3)
    total = len(by_parent)
    if total > 0:
        three_plus_rate = three_plus / total
        target_rate = cfg.options.get("target_rate", 0.5)
        if three_plus_rate > target_rate:
            violations.append(Violation(
                check_name="first_time_right",
                severity="warning",
                session_id=None,
                title="First-time-right rate",
                message=f"{three_plus_rate:.0%} of waves need 3+ iterations. Tasks may be too large.",
                context={"three_plus_rate": three_plus_rate, "three_plus": three_plus, "total": total},
            ))
    return violations


def check_over_orchestration(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Main session with >max_subagents (warning)."""
    cfg = config.workflow_checks["over_orchestration"]
    if not cfg.enabled:
        return []
    max_sub = cfg.options.get("max_subagents", 6)
    children_by_parent = Counter()
    for s in sessions:
        if s["parent_id"]:
            children_by_parent[s["parent_id"]] += 1
    violations = []
    for parent_id, count in children_by_parent.items():
        if count > max_sub:
            parent = next((s for s in sessions if s["id"] == parent_id), None)
            if parent:
                violations.append(Violation(
                    check_name="over_orchestration",
                    severity="warning",
                    session_id=parent_id,
                    title=parent["title"],
                    message=f"Main session spawned {count} subagents. Task too large.",
                    context={"subagent_count": count, "max": max_sub},
                ))
    return violations


# ===== INFO CHECKS =====


def check_dead_end_sessions(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Session < 60s without subagent (info)."""
    cfg = config.workflow_checks["dead_end_sessions"]
    if not cfg.enabled:
        return []
    max_sec = cfg.options.get("max_duration_sec", 60)
    children = {s["parent_id"] for s in sessions if s["parent_id"]}
    violations = []
    for s in sessions:
        if s["parent_id"] is None and s["id"] not in children:
            dur_sec = (s["time_updated"] - s["time_created"]) / 1000
            if dur_sec < max_sec:
                violations.append(Violation(
                    check_name="dead_end_sessions",
                    severity="info",
                    session_id=s["id"],
                    title=s["title"],
                    message=f"Session {dur_sec:.1f}s — failed fast or context issue.",
                    context={"duration_sec": dur_sec},
                ))
    return violations


def check_skill_orphan(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Stub: needs cross-reference to skills/ directory."""
    cfg = config.workflow_checks["skill_orphan"]
    if not cfg.enabled:
        return []
    return []


def check_context_overflow(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Session with time_compacting set (info)."""
    cfg = config.workflow_checks["context_overflow"]
    if not cfg.enabled:
        return []
    violations = []
    for s in sessions:
        if s.get("time_compacting") is not None:
            violations.append(Violation(
                check_name="context_overflow",
                severity="info",
                session_id=s["id"],
                title=s["title"],
                message="Session triggered context compaction. Long session or complex task.",
                context={"time_compacting": s["time_compacting"]},
            ))
    return violations


def check_missed_parallelism(
    sessions: list[dict],
    tool_calls: list[dict],
    config: ReflectConfig,
) -> list[Violation]:
    """Positive check: subagent calls in same wave that could be parallel."""
    cfg = config.workflow_checks["missed_parallelism"]
    if not cfg.enabled:
        return []
    siblings: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        if s["parent_id"]:
            siblings[s["parent_id"]].append(s)
    violations = []
    for parent_id, kids in siblings.items():
        if len(kids) >= 2:
            parent = next((s for s in sessions if s["id"] == parent_id), None)
            if parent:
                violations.append(Violation(
                    check_name="missed_parallelism",
                    severity="info",
                    session_id=parent_id,
                    title=parent["title"],
                    message=f"{len(kids)} subagents could potentially be parallel (no dependency detected).",
                    context={"subagent_count": len(kids)},
                ))
    return violations


# ===== ALL CHECKS LIST =====

ALL_CHECKS = [
    check_controller_never_implements,
    check_stuck_in_retry,
    check_same_error_repeated,
    check_mandatory_reviewer_for_code,
    check_gate_compliance,
    check_tdd_red_first,
    check_max_review_loops,
    check_regression_test_on_bugfix,
    check_arch_session_too_long,
    check_skill_triggered_when_should,
    check_subagent_completion_rate,
    check_first_time_right,
    check_over_orchestration,
    check_dead_end_sessions,
    check_skill_orphan,
    check_context_overflow,
    check_missed_parallelism,
]
