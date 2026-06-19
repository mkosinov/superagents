"""Tests for closing-the-loop."""
from pathlib import Path
from reflect.scripts.lib.closing_the_loop import (
    find_related_decisions,
    compute_loop_hit_rate,
)


def test_find_related_decisions_same_target(tmp_path: Path):
    from reflect.scripts.lib.proposals import create_proposal, record_decision
    create_proposal(tmp_path, "p1", "A", "info", 0.9, "agents/spec-reviewer.md", "r", "d", False)
    record_decision(tmp_path, "p1", "applied", "ok", "abc123")
    related = find_related_decisions(
        base_dir=tmp_path,
        target="agents/spec-reviewer.md",
    )
    assert len(related) == 1
    assert related[0]["outcome"] == "applied"


def test_find_related_decisions_no_match(tmp_path: Path):
    from reflect.scripts.lib.proposals import create_proposal, record_decision
    create_proposal(tmp_path, "p1", "A", "info", 0.9, "agents/foo.md", "r", "d", False)
    record_decision(tmp_path, "p1", "applied", "ok", "abc")
    related = find_related_decisions(
        base_dir=tmp_path,
        target="agents/bar.md",
    )
    assert len(related) == 0


def test_compute_loop_hit_rate_empty():
    rate = compute_loop_hit_rate([])
    assert rate == 0.0


def test_compute_loop_hit_rate_with_matches():
    decisions = [
        {"applied_days_ago": 10, "prevented_match": True},
        {"applied_days_ago": 10, "prevented_match": True},
        {"applied_days_ago": 10, "prevented_match": False},
    ]
    rate = compute_loop_hit_rate(decisions)
    assert abs(rate - 2/3) < 0.01
