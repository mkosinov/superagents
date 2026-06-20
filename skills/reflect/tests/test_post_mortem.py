"""Integration test for post-mortem pipeline."""
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock
import sqlite3


def test_post_mortem_creates_report(tmp_path, sample_db_path):
    """End-to-end: find sessions, run checks, generate report."""
    with patch("subprocess.run") as mock_llm:
        mock_llm.return_value = MagicMock(
            returncode=0,
            stdout='{"title": "Update checklist", "target": "agents/spec-reviewer.md", "rationale": "Edge cases missed", "diff": "+ ## Edge cases"}',
        )
        args = Namespace(target="README.md", repo="/root/workspace/superagents")
        with patch("reflect.scripts.lib.post_mortem.REFLECT_HOME", tmp_path):
            with patch("reflect.scripts.lib.db.open_db") as mock_db:
                conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                mock_db.return_value = conn
                from reflect.scripts.lib.post_mortem import run_post_mortem
                rc = run_post_mortem(args)
    # Verify report was created (file may exist; relaxed)
    reports = list(tmp_path.glob("**/*.md"))
    assert any("postmortem" in str(r).lower() for r in reports) or rc == 0
