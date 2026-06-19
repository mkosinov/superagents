"""Tests for quality scoring."""
from reflect.scripts.lib.quality_scoring import (
    EffectivenessScore,
    score_skills,
    score_agents,
)


def test_score_agents_basic():
    sessions = [
        {"id": "a", "agent": "frontend-coder", "time_created": 1, "time_updated": 100, "time_archived": 100, "cost": 0.5, "tokens_input": 1000, "tokens_output": 500},
        {"id": "b", "agent": "frontend-coder", "time_created": 200, "time_updated": 300, "time_archived": None, "cost": 0.3, "tokens_input": 800, "tokens_output": 400},
    ]
    scores = score_agents(sessions, min_samples=1)
    assert "frontend-coder" in scores
    s = scores["frontend-coder"]
    assert s.usage_count == 2
    assert 0.0 <= s.success_rate <= 1.0
    assert s.composite_score > 0


def test_score_agents_filters_below_min_samples():
    sessions = [
        {"id": "a", "agent": "rare", "time_created": 1, "time_updated": 100, "time_archived": 100, "cost": 0.1, "tokens_input": 100, "tokens_output": 50},
    ]
    scores = score_agents(sessions, min_samples=5)
    assert "rare" not in scores


def test_score_skills_extracts_from_parts():
    sessions = [
        {"id": "a", "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100, "cost": 0.0, "tokens_input": 0, "tokens_output": 0},
    ]
    tool_calls = [
        {"session_id": "a", "tool": "skill", "status": "completed", "error": None, "cmd": "vitest-playwright-patterns", "time_created": 10, "duration_ms": 100},
    ]
    scores = score_skills(sessions, tool_calls, min_samples=1)
    assert "vitest-playwright-patterns" in scores
