"""Closing-the-loop: match new proposals/violations with past decisions."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from .proposals import list_decisions


def _decision_date(content: str) -> datetime | None:
    """Extract decision date from markdown content."""
    m = re.search(r"\*\*Decided at:\*\*\s*([\d\-T:+\.]+)", content)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1))
    except ValueError:
        return None


def find_related_decisions(
    *,
    base_dir: Path,
    target: str,
    keywords: list[str] | None = None,
) -> list[dict]:
    """Find past decisions with matching target file or keywords."""
    decisions = list_decisions(base_dir)
    out = []
    now = datetime.now(timezone.utc)
    keywords = keywords or []
    for d in decisions:
        target_match = re.search(r"`([^`]+)`", d["content"])
        d_target = target_match.group(1) if target_match else ""
        match = False
        if target and d_target and (
            target in d_target or d_target in target
        ):
            match = True
        if not match and keywords:
            for kw in keywords:
                if kw.lower() in d["content"].lower():
                    match = True
                    break
        if not match:
            continue
        decided = _decision_date(d["content"])
        days_ago = (now - decided).days if decided else None
        out.append({
            "id": d["id"],
            "outcome": d["outcome"],
            "target": d_target,
            "days_since_decision": days_ago,
            "content": d["content"],
        })
    return out


def evaluate_prevention(
    decision: dict, current_violation: dict, window_days: int = 30
) -> str:
    """Return one of: 'should_have_prevented', 'didnt_prevent', 'rejected', 'unknown'."""
    if decision["outcome"] == "rejected":
        return "rejected"
    days = decision.get("days_since_decision")
    if days is None or days > window_days:
        return "didnt_prevent"
    d_target = decision.get("target", "")
    v_session = current_violation.get("session_id", "")
    if d_target and v_session:
        return "should_have_prevented"
    return "didnt_prevent"


def compute_loop_hit_rate(decisions_with_prevention: list[dict]) -> float:
    """Compute: % of applied decisions that 'should_have_prevented' a later violation."""
    if not decisions_with_prevention:
        return 0.0
    prevented = sum(1 for d in decisions_with_prevention if d.get("prevented_match"))
    return prevented / len(decisions_with_prevention)
