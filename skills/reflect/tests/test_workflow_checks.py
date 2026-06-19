"""Tests for workflow compliance checks."""
from reflect.scripts.lib.workflow_checks import (
    check_controller_never_implements,
    check_stuck_in_retry,
    check_same_error_repeated,
    check_mandatory_reviewer_for_code,
    check_gate_compliance,
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
