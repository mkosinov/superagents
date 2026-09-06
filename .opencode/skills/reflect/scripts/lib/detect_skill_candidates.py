"""Detect candidates for new skills based on session patterns."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class SkillCandidate:
    pattern_type: str
    suggested_name: str
    evidence: str
    confidence: float
    occurrences: int
    sessions: list[str] = field(default_factory=list)


def detect_recurring_recovery(
    sessions: Iterable[dict],
    tool_calls: Iterable[dict],
    min_count: int = 3,
) -> list[SkillCandidate]:
    """Detect: tool A error → tool B success pattern repeated N+ times across sessions."""
    by_session: dict[str, list[dict]] = defaultdict(list)
    for tc in tool_calls:
        by_session[tc["session_id"]].append(tc)

    pattern_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
    pattern_count: dict[tuple[str, str], int] = defaultdict(int)

    for sid, calls in by_session.items():
        calls = sorted(calls, key=lambda c: c["time_created"])
        for i, call in enumerate(calls[:-1]):
            if call.get("status") == "error" and call.get("error") and i + 1 < len(calls):
                next_call = calls[i + 1]
                if next_call.get("status") == "completed":
                    key = (call["tool"], next_call["tool"])
                    pattern_sessions[key].add(sid)
                    pattern_count[key] += 1

    out = []
    for (err_tool, succ_tool), count in pattern_count.items():
        if len(pattern_sessions[(err_tool, succ_tool)]) >= min_count:
            confidence = min(len(pattern_sessions[(err_tool, succ_tool)]) / 10, 1.0)
            out.append(SkillCandidate(
                pattern_type="recurring_recovery",
                suggested_name=f"{succ_tool}-after-{err_tool}-failure",
                evidence=(
                    f"Pattern '{err_tool} error' → '{succ_tool} success' "
                    f"seen in {len(pattern_sessions[(err_tool, succ_tool)])} sessions "
                    f"({count} total occurrences)"
                ),
                confidence=confidence,
                occurrences=count,
                sessions=list(pattern_sessions[(err_tool, succ_tool)]),
            ))
    return out


def detect_recurring_command_sequence(
    sessions: Iterable[dict],
    tool_calls: Iterable[dict],
    min_count: int = 5,
) -> list[SkillCandidate]:
    """Detect: same bash command appears N+ times across different sessions."""
    cmd_sessions: dict[str, set[str]] = defaultdict(set)
    for tc in tool_calls:
        if tc["tool"] == "bash" and tc.get("cmd"):
            cmd_sessions[tc["cmd"]].add(tc["session_id"])

    out = []
    for cmd, sids in cmd_sessions.items():
        if len(sids) >= min_count:
            out.append(SkillCandidate(
                pattern_type="recurring_command_sequence",
                suggested_name=f"run-{cmd.replace(' ', '-')[:30]}",
                evidence=f"Command '{cmd}' used in {len(sids)} sessions",
                confidence=min(len(sids) / 20, 1.0),
                occurrences=len(sids),
                sessions=list(sids),
            ))
    return out
