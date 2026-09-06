"""Integration test for nightly pipeline."""
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock
import sqlite3


def test_nightly_creates_digest(tmp_path, sample_db_path):
    args = Namespace(days=7, auto_apply=False)
    with patch("subprocess.run") as mock_llm:
        mock_llm.return_value = MagicMock(
            returncode=0,
            stdout='{"title":"t","target":"x","rationale":"r","diff":"d"}',
        )
        with patch("reflect.scripts.lib.nightly.REFLECT_HOME", tmp_path):
            with patch("reflect.scripts.lib.db.open_db") as mock_db:
                conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                mock_db.return_value = conn
                from reflect.scripts.lib.nightly import run_nightly
                rc = run_nightly(args)
    assert rc == 0


# ===== Regression: batch LLM calls =====


def test_batch_violations_makes_one_llm_call():
    """400 violations should result in 1 LLM call, not 400.

    This is the root cause of the nightly hang — each violation was
    calling LLM via subprocess.run sequentially.
    """
    from reflect.scripts.lib.analyze import batch_violations_to_proposals
    from reflect.scripts.lib.workflow_checks import Violation
    from reflect.scripts.lib.config import ReflectConfig

    violations = [
        Violation(f"check_{i}", "warning", f"s_{i}", f"Title {i}", f"Message {i}", {})
        for i in range(400)
    ]
    with patch("reflect.scripts.lib.analyze.call_llm") as mock:
        mock.return_value = '[{"index":1,"title":"t","target":"x","rationale":"r","diff":"d"}]'
        result = batch_violations_to_proposals(violations, ReflectConfig.from_dict({}))

    # KEY: only 1 LLM call total (not 400)
    assert mock.call_count == 1, f"Expected 1 LLM call, got {mock.call_count}"
    assert len(result) == 30  # MAX_BATCH cap


def test_batch_violations_empty_list():
    """No violations → no LLM call."""
    from reflect.scripts.lib.analyze import batch_violations_to_proposals
    from reflect.scripts.lib.config import ReflectConfig

    with patch("reflect.scripts.lib.analyze.call_llm") as mock:
        result = batch_violations_to_proposals([], ReflectConfig.from_dict({}))
    assert result == []
    assert mock.call_count == 0


def test_batch_violations_prioritizes_critical():
    """Critical violations should appear first in the batch prompt."""
    from reflect.scripts.lib.analyze import batch_violations_to_proposals
    from reflect.scripts.lib.workflow_checks import Violation
    from reflect.scripts.lib.config import ReflectConfig

    # Use counts that fit under MAX_BATCH (30) so all are included
    violations = [
        Violation("info_check", "info", "s1", "Info", "msg", {}),
        Violation("critical_check", "critical", "s2", "Crit", "msg", {}),
        Violation("warning_check", "warning", "s3", "Warn", "msg", {}),
    ] * 5  # 15 total — under cap of 30
    with patch("reflect.scripts.lib.analyze.call_llm") as mock:
        mock.return_value = '[{"index":1,"title":"t","target":"x","rationale":"r","diff":"d"}]'
        result = batch_violations_to_proposals(violations, ReflectConfig.from_dict({}))

    assert mock.call_count == 1
    # The prompt passed to call_llm should mention critical check first
    prompt_arg = mock.call_args[0][0]
    # Find positions of check names in prompt
    crit_pos = prompt_arg.find("critical_check")
    warn_pos = prompt_arg.find("warning_check")
    info_pos = prompt_arg.find("info_check")
    # critical should appear before warning, which should appear before info
    assert crit_pos < warn_pos < info_pos, (
        f"Priority order wrong: critical@{crit_pos}, warning@{warn_pos}, info@{info_pos}"
    )


def test_batch_violations_heuristic_fallback():
    """When LLM returns garbage, should fall back to heuristic proposals."""
    from reflect.scripts.lib.analyze import batch_violations_to_proposals
    from reflect.scripts.lib.workflow_checks import Violation
    from reflect.scripts.lib.config import ReflectConfig

    violations = [
        Violation("check_a", "warning", "s1", "Title A", "Message A", {}),
        Violation("check_b", "info", "s2", "Title B", "Message B", {}),
    ]
    with patch("reflect.scripts.lib.analyze.call_llm") as mock:
        mock.return_value = "I don't understand, sorry!"
        result = batch_violations_to_proposals(violations, ReflectConfig.from_dict({}))

    assert len(result) == 2
    assert result[0]["title"] == "Title A"
    assert result[0]["rationale"] == "Message A"
    assert result[1]["title"] == "Title B"


def test_batch_violations_partial_json_response():
    """LLM returns array with missing indices → heuristic fills gaps."""
    from reflect.scripts.lib.analyze import batch_violations_to_proposals
    from reflect.scripts.lib.workflow_checks import Violation
    from reflect.scripts.lib.config import ReflectConfig

    violations = [
        Violation("check_a", "warning", "s1", "Title A", "Message A", {}),
        Violation("check_b", "info", "s2", "Title B", "Message B", {}),
        Violation("check_c", "critical", "s3", "Title C", "Message C", {}),
    ]
    with patch("reflect.scripts.lib.analyze.call_llm") as mock:
        # Only returns 1 of 3 — gaps should be filled by heuristic
        mock.return_value = '[{"index":2,"title":"LLM Title","target":"file.py","rationale":"r","diff":"d"}]'
        result = batch_violations_to_proposals(violations, ReflectConfig.from_dict({}))

    assert len(result) == 3
    # After sorting: [critical(Title C), warning(Title A), info(Title B)]
    # index 1 → result[0] critical (gap, filled by heuristic)
    assert result[0]["title"] == "Title C"
    # index 2 → result[1] warning (from LLM)
    assert result[1]["title"] == "LLM Title"
    # index 3 → result[2] info (gap, filled by heuristic)
    assert result[2]["title"] == "Title B"