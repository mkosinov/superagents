"""Tests for workflow compliance checks."""
from reflect.scripts.lib.workflow_checks import (
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
    ALL_CHECKS,
)
from reflect.scripts.lib.config import ReflectConfig


def test_controller_never_implements_detects_edits():
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "edit", "status": "completed", "error": None, "cmd": None, "time_created": 10, "duration_ms": 5},
    ]
    v = check_controller_never_implements(sessions, tool_calls, ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].check_name == "controller_never_implements"
    assert v[0].severity == "critical"


def test_controller_never_implements_clean():
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "read", "status": "completed", "error": None, "cmd": None, "time_created": 10, "duration_ms": 5},
    ]
    assert check_controller_never_implements(sessions, tool_calls, ReflectConfig.from_dict({})) == []


def test_stuck_in_retry_detects_repeated_command():
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "frontend-coder", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None, "cmd": "npm install", "time_created": 10, "duration_ms": 100},
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None, "cmd": "npm install", "time_created": 20, "duration_ms": 100},
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None, "cmd": "npm install", "time_created": 30, "duration_ms": 100},
    ]
    v = check_stuck_in_retry(sessions, tool_calls, ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].context["repeats"] == 3


def test_same_error_repeated_detects():
    sessions = [
        {"id": "a", "title": "t1", "parent_id": None, "agent": "researcher", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "b", "title": "t2", "parent_id": None, "agent": "researcher", "time_created": 200, "time_updated": 300, "time_archived": 300},
        {"id": "c", "title": "t3", "parent_id": None, "agent": "researcher", "time_created": 400, "time_updated": 500, "time_archived": 500},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "websearch", "status": "error", "error": "Decode error", "cmd": None, "time_created": 10, "duration_ms": 100},
        {"session_id": "b", "tool": "websearch", "status": "error", "error": "Decode error", "cmd": None, "time_created": 210, "duration_ms": 100},
        {"session_id": "c", "tool": "websearch", "status": "error", "error": "Decode error", "cmd": None, "time_created": 410, "duration_ms": 100},
    ]
    v = check_same_error_repeated(sessions, tool_calls, ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].context["tool"] == "websearch"
    assert v[0].context["session_count"] == 3


def test_mandatory_reviewer_for_code_clean():
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "b", "title": "Wave 1 1", "parent_id": "a", "agent": "frontend-coder", "time_created": 10, "time_updated": 50, "time_archived": 50},
        {"id": "c", "title": "Wave 1 1 review1", "parent_id": "b", "agent": "spec-reviewer", "time_created": 55, "time_updated": 70, "time_archived": 70},
        {"id": "d", "title": "Wave 1 1 review2", "parent_id": "b", "agent": "code-quality-reviewer", "time_created": 75, "time_updated": 90, "time_archived": 90},
    ]
    assert check_mandatory_reviewer_for_code(sessions, [], ReflectConfig.from_dict({})) == []


def test_mandatory_reviewer_for_code_missing():
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "b", "title": "Wave 1 1", "parent_id": "a", "agent": "frontend-coder", "time_created": 10, "time_updated": 50, "time_archived": 50},
    ]
    v = check_mandatory_reviewer_for_code(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert "spec-reviewer" in str(v[0].context.get("missing", []))


def test_gate_compliance_returns_empty():
    """Gate compliance is a stub — no gate markers in opencode.db yet."""
    assert check_gate_compliance([], [], ReflectConfig.from_dict({})) == []


def test_check_disabled_returns_empty():
    """When check is disabled in config, returns empty list regardless of data."""
    from reflect.scripts.lib.config import CheckConfig
    cfg = ReflectConfig.from_dict({})
    cfg.workflow_checks["stuck_in_retry"].enabled = False
    sessions = [
        {"id": "a", "title": "t", "parent_id": None, "agent": "frontend-coder",
         "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None,
         "cmd": "x", "time_created": 10, "duration_ms": 1},
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None,
         "cmd": "x", "time_created": 20, "duration_ms": 1},
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None,
         "cmd": "x", "time_created": 30, "duration_ms": 1},
    ]
    from reflect.scripts.lib.workflow_checks import check_stuck_in_retry
    assert check_stuck_in_retry(sessions, tool_calls, cfg) == []


def test_violation_to_proposal_dict():
    from reflect.scripts.lib.workflow_checks import Violation
    v = Violation(
        check_name="test_check",
        severity="critical",
        session_id="abc",
        title="Test Title",
        message="Test message",
        context={"foo": 42, "bar": "x"},
    )
    d = v.to_proposal_dict()
    assert d["check"] == "test_check"
    assert d["severity"] == "critical"
    assert d["session_id"] == "abc"
    assert d["title"] == "Test Title"
    assert d["message"] == "Test message"
    assert d["foo"] == 42
    assert d["bar"] == "x"


# ===== WARNING CHECKS =====


def test_tdd_red_first_detects_edit_first():
    from reflect.scripts.lib.workflow_checks import check_tdd_red_first
    sessions = [
        {"id": "a", "title": "t", "parent_id": None, "agent": "frontend-coder", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "edit", "status": "completed", "error": None, "cmd": None, "time_created": 10, "duration_ms": 5},
    ]
    v = check_tdd_red_first(sessions, tool_calls, ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].check_name == "tdd_red_first"
    assert v[0].severity == "warning"


def test_tdd_red_first_clean_when_bash_first():
    from reflect.scripts.lib.workflow_checks import check_tdd_red_first
    sessions = [
        {"id": "a", "title": "t", "parent_id": None, "agent": "backend-coder", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None, "cmd": "uv run pytest", "time_created": 10, "duration_ms": 5},
        {"session_id": "a", "tool": "edit", "status": "completed", "error": None, "cmd": None, "time_created": 20, "duration_ms": 5},
    ]
    assert check_tdd_red_first(sessions, tool_calls, ReflectConfig.from_dict({})) == []


def test_max_review_loops_detects():
    from reflect.scripts.lib.workflow_checks import check_max_review_loops
    sessions = [
        {"id": "parent", "title": "task", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 200, "time_archived": 200},
        {"id": "r1", "title": "review1", "parent_id": "parent", "agent": "spec-reviewer", "time_created": 10, "time_updated": 20, "time_archived": 20},
        {"id": "r2", "title": "review2", "parent_id": "parent", "agent": "code-quality-reviewer", "time_created": 30, "time_updated": 40, "time_archived": 40},
        {"id": "r3", "title": "review3", "parent_id": "parent", "agent": "spec-reviewer", "time_created": 50, "time_updated": 60, "time_archived": 60},
        {"id": "r4", "title": "review4", "parent_id": "parent", "agent": "code-quality-reviewer", "time_created": 70, "time_updated": 80, "time_archived": 80},
    ]
    v = check_max_review_loops(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].context["loops"] == 4


def test_regression_test_on_bugfix_detects():
    from reflect.scripts.lib.workflow_checks import check_regression_test_on_bugfix
    sessions = [
        {"id": "a", "title": "fix: broken button", "parent_id": None, "agent": "frontend-coder", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "edit", "status": "completed", "error": None, "cmd": None, "time_created": 10, "duration_ms": 5},
    ]
    v = check_regression_test_on_bugfix(sessions, tool_calls, ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].check_name == "regression_test_on_bugfix"


def test_regression_test_on_bugfix_clean_with_test():
    from reflect.scripts.lib.workflow_checks import check_regression_test_on_bugfix
    sessions = [
        {"id": "a", "title": "fix: broken button", "parent_id": None, "agent": "frontend-coder", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "bash", "status": "completed", "error": None, "cmd": "uv run pytest tests/test_button.py", "time_created": 10, "duration_ms": 50},
        {"session_id": "a", "tool": "edit", "status": "completed", "error": None, "cmd": None, "time_created": 20, "duration_ms": 5},
    ]
    assert check_regression_test_on_bugfix(sessions, tool_calls, ReflectConfig.from_dict({})) == []


def test_arch_session_too_long_detects():
    from reflect.scripts.lib.workflow_checks import check_arch_session_too_long
    long_ms = 40 * 60 * 1000  # 40 minutes
    sessions = [
        {"id": "a", "title": "big task", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 1 + long_ms, "time_archived": 1 + long_ms},
    ]
    v = check_arch_session_too_long(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].check_name == "arch_session_too_long"


def test_arch_session_too_long_clean_with_subagent():
    from reflect.scripts.lib.workflow_checks import check_arch_session_too_long
    long_ms = 40 * 60 * 1000
    sessions = [
        {"id": "a", "title": "big task", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 1 + long_ms, "time_archived": 1 + long_ms},
        {"id": "b", "title": "sub", "parent_id": "a", "agent": "backend-coder", "time_created": 10, "time_updated": 20, "time_archived": 20},
    ]
    assert check_arch_session_too_long(sessions, [], ReflectConfig.from_dict({})) == []


def test_skill_triggered_when_should_stub():
    from reflect.scripts.lib.workflow_checks import check_skill_triggered_when_should
    assert check_skill_triggered_when_should([], [], ReflectConfig.from_dict({})) == []


def test_subagent_completion_rate_detects():
    from reflect.scripts.lib.workflow_checks import check_subagent_completion_rate
    sessions = [
        {"id": "a", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 1, "time_updated": 10, "time_archived": None},  # not archived
        {"id": "b", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 20, "time_updated": 30, "time_archived": None},
        {"id": "c", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 40, "time_updated": 50, "time_archived": 50},
        {"id": "d", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 60, "time_updated": 70, "time_archived": None},
        {"id": "e", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 80, "time_updated": 90, "time_archived": None},
    ]
    v = check_subagent_completion_rate(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].context["rate"] < 0.8


def test_subagent_completion_rate_clean():
    from reflect.scripts.lib.workflow_checks import check_subagent_completion_rate
    # 4/5 archived = 80% = meets threshold exactly
    sessions = [
        {"id": "a", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 1, "time_updated": 10, "time_archived": 10},
        {"id": "b", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 20, "time_updated": 30, "time_archived": 30},
        {"id": "c", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 40, "time_updated": 50, "time_archived": 50},
        {"id": "d", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 60, "time_updated": 70, "time_archived": 70},
        {"id": "e", "title": "t", "parent_id": "p", "agent": "frontend-coder", "time_created": 80, "time_updated": 90, "time_archived": None},
    ]
    assert check_subagent_completion_rate(sessions, [], ReflectConfig.from_dict({})) == []


def test_first_time_right_detects():
    from reflect.scripts.lib.workflow_checks import check_first_time_right
    # 2 parent tasks, each with 3+ review iterations → >50% rate
    sessions = [
        {"id": "p1", "title": "t1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "p2", "title": "t2", "parent_id": None, "agent": "architect", "time_created": 200, "time_updated": 300, "time_archived": 300},
        {"id": "r1", "title": "r", "parent_id": "p1", "agent": "spec-reviewer", "time_created": 10, "time_updated": 20, "time_archived": 20},
        {"id": "r2", "title": "r", "parent_id": "p1", "agent": "code-quality-reviewer", "time_created": 30, "time_updated": 40, "time_archived": 40},
        {"id": "r3", "title": "r", "parent_id": "p1", "agent": "spec-reviewer", "time_created": 50, "time_updated": 60, "time_archived": 60},
        {"id": "r4", "title": "r", "parent_id": "p2", "agent": "spec-reviewer", "time_created": 210, "time_updated": 220, "time_archived": 220},
        {"id": "r5", "title": "r", "parent_id": "p2", "agent": "code-quality-reviewer", "time_created": 230, "time_updated": 240, "time_archived": 240},
        {"id": "r6", "title": "r", "parent_id": "p2", "agent": "spec-reviewer", "time_created": 250, "time_updated": 260, "time_archived": 260},
    ]
    v = check_first_time_right(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].check_name == "first_time_right"


def test_over_orchestration_detects():
    from reflect.scripts.lib.workflow_checks import check_over_orchestration
    sessions = [
        {"id": "main", "title": "big wave", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 200, "time_archived": 200},
    ]
    # 7 subagents > default max of 6
    for i in range(7):
        sessions.append({"id": f"s{i}", "title": f"sub{i}", "parent_id": "main", "agent": "backend-coder", "time_created": 10, "time_updated": 20, "time_archived": 20})
    v = check_over_orchestration(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].context["subagent_count"] == 7


def test_over_orchestration_clean():
    from reflect.scripts.lib.workflow_checks import check_over_orchestration
    sessions = [
        {"id": "main", "title": "big wave", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 200, "time_archived": 200},
    ]
    for i in range(3):
        sessions.append({"id": f"s{i}", "title": f"sub{i}", "parent_id": "main", "agent": "backend-coder", "time_created": 10, "time_updated": 20, "time_archived": 20})
    assert check_over_orchestration(sessions, [], ReflectConfig.from_dict({})) == []


# ===== INFO CHECKS =====


def test_dead_end_sessions_detects():
    from reflect.scripts.lib.workflow_checks import check_dead_end_sessions
    # 30 seconds = 30,000 ms → well under 60s threshold
    sessions = [
        {"id": "a", "title": "quick fail", "parent_id": None, "agent": "frontend-coder", "time_created": 1000, "time_updated": 31_000, "time_archived": 31_000},
    ]
    v = check_dead_end_sessions(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].severity == "info"


def test_dead_end_sessions_clean_with_children():
    from reflect.scripts.lib.workflow_checks import check_dead_end_sessions
    sessions = [
        {"id": "a", "title": "parent", "parent_id": None, "agent": "architect", "time_created": 1000, "time_updated": 1030_000, "time_archived": 1030_000},
        {"id": "b", "title": "child", "parent_id": "a", "agent": "backend-coder", "time_created": 10, "time_updated": 20, "time_archived": 20},
    ]
    assert check_dead_end_sessions(sessions, [], ReflectConfig.from_dict({})) == []


def test_skill_orphan_stub():
    from reflect.scripts.lib.workflow_checks import check_skill_orphan
    assert check_skill_orphan([], [], ReflectConfig.from_dict({})) == []


def test_context_overflow_detects():
    from reflect.scripts.lib.workflow_checks import check_context_overflow
    sessions = [
        {"id": "a", "title": "long", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100, "time_compacting": 50},
    ]
    v = check_context_overflow(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].severity == "info"


def test_context_overflow_clean():
    from reflect.scripts.lib.workflow_checks import check_context_overflow
    sessions = [
        {"id": "a", "title": "normal", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
    ]
    assert check_context_overflow(sessions, [], ReflectConfig.from_dict({})) == []


def test_missed_parallelism_detects():
    from reflect.scripts.lib.workflow_checks import check_missed_parallelism
    sessions = [
        {"id": "parent", "title": "wave", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "c1", "title": "sub1", "parent_id": "parent", "agent": "backend-coder", "time_created": 10, "time_updated": 20, "time_archived": 20},
        {"id": "c2", "title": "sub2", "parent_id": "parent", "agent": "frontend-coder", "time_created": 30, "time_updated": 40, "time_archived": 40},
    ]
    v = check_missed_parallelism(sessions, [], ReflectConfig.from_dict({}))
    assert len(v) == 1
    assert v[0].context["subagent_count"] == 2


def test_missed_parallelism_clean_single_subagent():
    from reflect.scripts.lib.workflow_checks import check_missed_parallelism
    sessions = [
        {"id": "parent", "title": "wave", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "c1", "title": "sub1", "parent_id": "parent", "agent": "backend-coder", "time_created": 10, "time_updated": 20, "time_archived": 20},
    ]
    assert check_missed_parallelism(sessions, [], ReflectConfig.from_dict({})) == []


# ===== ALL CHECKS LIST =====


def test_all_checks_has_17_entries():
    assert len(ALL_CHECKS) == 17


def test_all_checks_are_callable():
    """Every entry in ALL_CHECKS should be callable with (sessions, tool_calls, config)."""
    for fn in ALL_CHECKS:
        result = fn([], [], ReflectConfig.from_dict({}))
        assert isinstance(result, list)
