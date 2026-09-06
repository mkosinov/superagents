"""Quality / effectiveness scoring for skills and agents.

Heuristics only in MVP. LLM-based classification added in Task 14.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import Iterable


@dataclass
class EffectivenessScore:
    name: str
    type: str  # "skill" | "agent"
    usage_count: int
    success_rate: float
    token_efficiency: float
    duration_impact_ms: float
    composite_score: float
    confidence: float
    extras: dict = field(default_factory=dict)


def _is_success(s: dict) -> bool:
    """Heuristic: session completed (archived) without BLOCKED."""
    return s.get("time_archived") is not None and s.get("cost", 0) >= 0


def _composite(success: float, efficiency: float, samples: int) -> float:
    """Weighted aggregate: 50% success + 30% efficiency + 20% confidence penalty."""
    confidence = min(samples / 10, 1.0)
    return 0.5 * success + 0.3 * efficiency + 0.2 * confidence


def score_agents(sessions: Iterable[dict], min_samples: int = 5) -> dict[str, EffectivenessScore]:
    """Score agents by usage, success rate, token efficiency."""
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        if s.get("agent"):
            by_agent[s["agent"]].append(s)
    out = {}
    for agent, sess_list in by_agent.items():
        if len(sess_list) < min_samples:
            continue
        successes = sum(1 for s in sess_list if _is_success(s))
        success_rate = successes / len(sess_list)
        tokens_list = [
            (s.get("tokens_input", 0) + s.get("tokens_output", 0))
            for s in sess_list
        ]
        median_tokens = sorted(tokens_list)[len(tokens_list) // 2] if tokens_list else 0
        efficiency = 1.0 / (1.0 + median_tokens / 1000)
        composite = _composite(success_rate, efficiency, len(sess_list))
        out[agent] = EffectivenessScore(
            name=agent,
            type="agent",
            usage_count=len(sess_list),
            success_rate=success_rate,
            token_efficiency=efficiency,
            duration_impact_ms=mean(
                (s["time_updated"] - s["time_created"]) for s in sess_list
            ),
            composite_score=composite,
            confidence=min(len(sess_list) / 10, 1.0),
        )
    return out


def score_skills(
    sessions: Iterable[dict],
    tool_calls: Iterable[dict],
    min_samples: int = 5,
) -> dict[str, EffectivenessScore]:
    """Score skills by tool='skill' invocations in tool_calls."""
    by_skill: dict[str, list[dict]] = defaultdict(list)
    for tc in tool_calls:
        if tc.get("tool") == "skill" and tc.get("cmd"):
            by_skill[tc["cmd"]].append(tc)
    out = {}
    for skill, calls in by_skill.items():
        if len(calls) < min_samples:
            continue
        successes = sum(1 for c in calls if c.get("status") == "completed" and not c.get("error"))
        success_rate = successes / len(calls)
        durations = [c.get("duration_ms", 0) for c in calls]
        median_duration = sorted(durations)[len(durations) // 2] if durations else 0
        efficiency = 1.0 / (1.0 + median_duration / 1000)
        composite = _composite(success_rate, efficiency, len(calls))
        out[skill] = EffectivenessScore(
            name=skill,
            type="skill",
            usage_count=len(calls),
            success_rate=success_rate,
            token_efficiency=efficiency,
            duration_impact_ms=median_duration,
            composite_score=composite,
            confidence=min(len(calls) / 10, 1.0),
        )
    return out
