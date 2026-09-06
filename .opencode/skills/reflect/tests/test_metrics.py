"""Tests for reflection metrics."""
from pathlib import Path
from reflect.scripts.lib.metrics import (
    compute_proposal_metrics,
    compute_compliance_trend,
)


def test_compute_proposal_metrics_empty(tmp_path: Path):
    m = compute_proposal_metrics(base_dir=tmp_path)
    assert m["total"] == 0
    assert m["adoption_rate"] == 0.0
    assert m["false_positive_rate"] == 0.0


def test_compute_proposal_metrics_with_data(tmp_path: Path):
    from reflect.scripts.lib.proposals import create_proposal, record_decision
    create_proposal(tmp_path, "p1", "A", "info", 0.9, "x", "r", "d", False)
    create_proposal(tmp_path, "p2", "B", "warning", 0.7, "y", "r", "d", False)
    create_proposal(tmp_path, "p3", "C", "warning", 0.6, "z", "r", "d", False)
    record_decision(tmp_path, "p1", "applied", "ok", "abc")
    record_decision(tmp_path, "p2", "rejected", "no", None)
    # p3 still pending
    m = compute_proposal_metrics(base_dir=tmp_path)
    assert m["total"] == 3
    assert m["applied"] == 1
    assert m["rejected"] == 1
    assert m["pending"] == 1
    assert m["adoption_rate"] == 0.5
    assert m["false_positive_rate"] == 0.5


def test_compute_compliance_trend_groups_by_day():
    from datetime import datetime, timezone
    sessions = [
        {"id": "a", "time_created": int(datetime(2026, 6, 19, tzinfo=timezone.utc).timestamp() * 1000),
         "time_updated": 100, "agent": "frontend-coder", "title": "t", "parent_id": "p"},
    ]
    trend = compute_compliance_trend(sessions, [], days=7)
    assert isinstance(trend, list)
    assert len(trend) == 7
