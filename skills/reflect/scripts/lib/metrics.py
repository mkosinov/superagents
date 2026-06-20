"""Reflection process metrics (the meta layer)."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable
from .proposals import list_pending_proposals, list_decisions


def compute_proposal_metrics(base_dir: Path) -> dict:
    """Compute proposal adoption + false-positive rates."""
    pending = list_pending_proposals(base_dir)
    decisions = list_decisions(base_dir)
    applied = sum(1 for d in decisions if d["outcome"] == "applied")
    rejected = sum(1 for d in decisions if d["outcome"] == "rejected")
    modified = sum(1 for d in decisions if d["outcome"] == "modified")
    total = applied + rejected + modified + len(pending)
    decided = applied + rejected + modified
    return {
        "total": total,
        "applied": applied,
        "rejected": rejected,
        "modified": modified,
        "pending": len(pending),
        "adoption_rate": applied / decided if decided else 0.0,
        "false_positive_rate": rejected / decided if decided else 0.0,
    }


def compute_compliance_trend(
    sessions: Iterable[dict], violations: Iterable[dict], days: int = 7
) -> list[dict]:
    """For last N days, compute compliance % (sessions without violations)."""
    now = datetime.now(timezone.utc)
    trend = []
    for d in range(days):
        day = now - timedelta(days=days - d - 1)
        day_start = int(day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        day_end = day_start + 24 * 60 * 60 * 1000
        day_sessions = [s for s in sessions if day_start <= s.get("time_created", 0) < day_end]
        day_violations = [v for v in violations if v.session_id and any(
            s["id"] == v.session_id for s in day_sessions
        )]
        total = len(day_sessions)
        viol_count = len({v.session_id for v in day_violations if v.session_id})
        compliance = (total - viol_count) / total if total else 1.0
        trend.append({
            "date": day.strftime("%Y-%m-%d"),
            "total_sessions": total,
            "violations": viol_count,
            "compliance": compliance,
        })
    return trend
