"""Tests for skill candidate detection."""
from reflect.scripts.lib.detect_skill_candidates import (
    detect_recurring_recovery,
    detect_recurring_command_sequence,
    SkillCandidate,
)


def test_detect_recurring_recovery_websearch_to_websearch_cited():
    """websearch error → websearch_cited success happens 3+ times."""
    sessions = [
        {"id": "a", "time_created": 1, "time_updated": 100, "agent": "researcher"},
        {"id": "b", "time_created": 200, "time_updated": 300, "agent": "researcher"},
        {"id": "c", "time_created": 400, "time_updated": 500, "agent": "researcher"},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "websearch", "status": "error", "error": "Decode error", "cmd": None, "time_created": 10, "duration_ms": 100},
        {"session_id": "a", "tool": "websearch_cited", "status": "completed", "error": None, "cmd": "test", "time_created": 20, "duration_ms": 100},
        {"session_id": "b", "tool": "websearch", "status": "error", "error": "Decode error", "cmd": None, "time_created": 210, "duration_ms": 100},
        {"session_id": "b", "tool": "websearch_cited", "status": "completed", "error": None, "cmd": "test2", "time_created": 220, "duration_ms": 100},
        {"session_id": "c", "tool": "websearch", "status": "error", "error": "Decode error", "cmd": None, "time_created": 410, "duration_ms": 100},
        {"session_id": "c", "tool": "websearch_cited", "status": "completed", "error": None, "cmd": "test3", "time_created": 420, "duration_ms": 100},
    ]
    candidates = detect_recurring_recovery(sessions, tool_calls, min_count=3)
    assert len(candidates) >= 1
    assert any("websearch_cited" in c.suggested_name for c in candidates)


def test_detect_recurring_command_sequence():
    """Same bash command appears 5+ times across sessions."""
    tool_calls = [
        {"session_id": f"s{i}", "tool": "bash", "status": "completed", "error": None, "cmd": "pnpm type-check", "time_created": i * 10, "duration_ms": 100}
        for i in range(5)
    ]
    sessions = [
        {"id": f"s{i}", "time_created": 1, "time_updated": 100, "agent": "frontend-coder"}
        for i in range(5)
    ]
    candidates = detect_recurring_command_sequence(sessions, tool_calls, min_count=5)
    assert len(candidates) >= 1
    assert candidates[0].suggested_name
    assert "pnpm type-check" in candidates[0].evidence
