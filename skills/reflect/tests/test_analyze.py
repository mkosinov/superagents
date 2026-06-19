"""Tests for analyze.py — template filler."""
from reflect.scripts.lib.analyze import (
    fill_template,
    format_violations_table,
    generate_proposal_id,
)
from reflect.scripts.lib.workflow_checks import Violation


def test_fill_template_substitutes_vars():
    template = "Hello {name}, you have {count} messages"
    out = fill_template(template, name="Alice", count=5)
    assert out == "Hello Alice, you have 5 messages"


def test_format_violations_table():
    violations = [
        Violation("controller_never_implements", "critical", "a", "Wave 1", "test", {"edits": 5}),
        Violation("stuck_in_retry", "critical", "b", "Wave 2", "test2", {"repeats": 3, "cmd": "npm install"}),
    ]
    table = format_violations_table(violations)
    assert "| critical | controller_never_implements |" in table
    assert "| critical | stuck_in_retry |" in table


def test_generate_proposal_id_format():
    from datetime import datetime
    pid = generate_proposal_id(date=datetime(2026, 6, 19), seq=1)
    assert pid == "prop-2026-06-19-001"
    pid42 = generate_proposal_id(date=datetime(2026, 6, 19), seq=42)
    assert pid42 == "prop-2026-06-19-042"
