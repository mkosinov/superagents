"""Per-project reflection-mode config loader."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["critical", "warning", "info"]

DEFAULT_CHECKS = {
    "controller_never_implements": ("critical", {}),
    "mandatory_reviewer_for_code": ("critical", {"file_patterns": ["*.ts", "*.tsx", "*.py"]}),
    "tdd_red_first": ("warning", {}),
    "max_review_loops": ("warning", {"max_loops": 3}),
    "gate_compliance": ("critical", {"gates": ["G1a", "G1b", "G2", "G7"]}),
    "regression_test_on_bugfix": ("warning", {}),
    "stuck_in_retry": ("critical", {"min_repeats": 3}),
    "same_error_repeated": ("critical", {"min_sessions": 3}),
    "arch_session_too_long": ("warning", {"max_minutes_without_subagent": 30}),
    "skill_triggered_when_should": ("warning", {}),
    "subagent_completion_rate": ("warning", {"min_rate": 0.8}),
    "first_time_right": ("warning", {"target_rate": 0.5}),
    "over_orchestration": ("warning", {"max_subagents": 6}),
    "dead_end_sessions": ("info", {"max_duration_sec": 60}),
    "skill_orphan": ("info", {"max_days_unused": 30}),
    "context_overflow": ("info", {}),
    "missed_parallelism": ("info", {}),
}


@dataclass
class CheckConfig:
    enabled: bool = True
    severity: Severity = "warning"
    options: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.severity, str) and self.severity not in ("critical", "warning", "info"):
            raise ValueError(f"Invalid severity: {self.severity}")


@dataclass
class AutoApplyConfig:
    enabled: bool = False
    max_confidence: float = 0.95
    allowed_severities: list[Severity] = field(default_factory=lambda: ["info"])
    allowed_types: list[str] = field(default_factory=lambda: ["archive-skill"])


@dataclass
class NotifyConfig:
    telegram_chat_id: str | None = None
    min_severity_to_notify: Severity = "warning"


@dataclass
class ThresholdsConfig:
    regression_delta_pct: float = 30.0
    min_confidence_for_proposal: float = 0.6
    min_samples_for_quality_score: int = 5


@dataclass
class ReflectConfig:
    workflow_checks: dict[str, CheckConfig]
    auto_apply: AutoApplyConfig
    notify: NotifyConfig
    thresholds: ThresholdsConfig
    
    @classmethod
    def from_dict(cls, data: dict) -> "ReflectConfig":
        checks_raw = data.get("workflow_checks", {})
        checks = {}
        for name, (default_sev, default_opts) in DEFAULT_CHECKS.items():
            entry = checks_raw.get(name, {})
            checks[name] = CheckConfig(
                enabled=entry.get("enabled", True),
                severity=entry.get("severity", default_sev),
                options={**default_opts, **entry.get("options", {})},
            )
        return cls(
            workflow_checks=checks,
            auto_apply=AutoApplyConfig(**data.get("auto_apply", {})),
            notify=NotifyConfig(**data.get("notify", {})),
            thresholds=ThresholdsConfig(**data.get("thresholds", {})),
        )


def load_config(config_dir: Path) -> ReflectConfig:
    """Load config from <config_dir>/reflect.config.json, or return defaults."""
    config_file = config_dir / "reflect.config.json"
    if not config_file.exists():
        return ReflectConfig.from_dict({})
    data = json.loads(config_file.read_text())
    return ReflectConfig.from_dict(data)
