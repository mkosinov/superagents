"""Tests for analyze.py — template filler."""
import pytest

from reflect.scripts.lib.analyze import (
    fill_template,
    format_violations_table,
    format_violations_with_context,
    generate_proposal_id,
)
from reflect.scripts.lib.workflow_checks import Violation


def test_fill_template_substitutes_vars():
    template = "Hello {name}, you have {count} messages"
    out = fill_template(template, name="Alice", count=5)
    assert out == "Hello Alice, you have 5 messages"


def test_fill_template_value_with_braces():
    """Values containing {word} should not be flagged as unfilled."""
    template = "Description: {desc}"
    out = fill_template(template, desc="use {curl} for HTTP requests")
    assert out == "Description: use {curl} for HTTP requests"


def test_fill_template_raises_on_unfilled_known_placeholder():
    template = "Hello {name}, you have {count} messages"
    with pytest.raises(ValueError, match="Unfilled template placeholders"):
        fill_template(template, name="Alice")  # missing 'count'


def test_format_violations_table():
    violations = [
        Violation("controller_never_implements", "critical", "a", "Wave 1", "test", {"edits": 5}),
        Violation("stuck_in_retry", "critical", "b", "Wave 2", "test2", {"repeats": 3, "cmd": "npm install"}),
    ]
    table = format_violations_table(violations)
    assert "| critical | controller_never_implements |" in table
    assert "| critical | stuck_in_retry |" in table


def test_format_violations_with_context():
    violations = [
        Violation("stuck_in_retry", "critical", "b", "Wave 2", "test",
                  {"repeats": 3, "cmd": "npm install"}),
        Violation("controller_never_implements", "critical", "a", "Wave 1",
                  "edited 5", {"edits": 5}),
    ]
    table = format_violations_with_context(violations)
    # Should include context fields
    assert "repeats=3" in table
    assert "cmd=npm install" in table
    assert "edits=5" in table


def test_generate_proposal_id_format():
    from datetime import datetime
    pid = generate_proposal_id(date=datetime(2026, 6, 19), seq=1)
    assert pid == "prop-2026-06-19-001"
    pid42 = generate_proposal_id(date=datetime(2026, 6, 19), seq=42)
    assert pid42 == "prop-2026-06-19-042"
