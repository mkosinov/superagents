"""Tests for config loader."""
import json
from pathlib import Path
from reflect.scripts.lib.config import load_config, ReflectConfig, CheckConfig


def test_load_default_config(tmp_path: Path):
    cfg = load_config(tmp_path)  # no file → defaults
    assert isinstance(cfg, ReflectConfig)
    assert cfg.workflow_checks["controller_never_implements"].enabled


def test_load_custom_config(tmp_path: Path):
    config_file = tmp_path / "reflect.config.json"
    config_file.write_text(json.dumps({
        "workflow_checks": {
            "controller_never_implements": {"enabled": False, "severity": "info"},
        }
    }))
    cfg = load_config(tmp_path)
    assert not cfg.workflow_checks["controller_never_implements"].enabled
    assert cfg.workflow_checks["controller_never_implements"].severity == "info"


def test_check_config_severity_validation():
    c = CheckConfig(enabled=True, severity="critical")
    assert c.severity == "critical"
