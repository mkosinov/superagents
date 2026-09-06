"""Integration test for in_session pipeline."""
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock
import sqlite3


def test_in_session_creates_report(tmp_path, sample_db_path):
    # Find any real session ID from the test DB
    conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
    row = conn.execute("SELECT id FROM session LIMIT 1").fetchone()
    conn.close()
    if not row:
        return  # no sessions in test DB
    args = Namespace(
        session=row[0],
        notes="websearch was failing",
    )
    with patch("subprocess.run") as mock_llm:
        mock_llm.return_value = MagicMock(
            returncode=0,
            stdout='{"title":"t","target":"x","rationale":"r","diff":"d"}',
        )
        with patch("reflect.scripts.lib.in_session.REFLECT_HOME", tmp_path):
            with patch("reflect.scripts.lib.db.open_db") as mock_db:
                conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                mock_db.return_value = conn
                from reflect.scripts.lib.in_session import run_in_session
                rc = run_in_session(args)
    assert rc == 0


def test_in_session_handles_no_subagents(tmp_path, sample_db_path):
    """Session with no subagents should not crash."""
    # Find a session with no subagents in our test DB
    conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
    row = conn.execute(
        "SELECT id FROM session WHERE parent_id IS NULL AND id NOT IN (SELECT parent_id FROM session WHERE parent_id IS NOT NULL) LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return  # no such session in test DB
    args = Namespace(session=row[0], notes="")
    with patch("subprocess.run") as mock_llm:
        mock_llm.return_value = MagicMock(returncode=0, stdout='{"title":"t","target":"x","rationale":"r","diff":"d"}')
        with patch("reflect.scripts.lib.in_session.REFLECT_HOME", tmp_path):
            with patch("reflect.scripts.lib.db.open_db") as mock_db:
                conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                mock_db.return_value = conn
                from reflect.scripts.lib.in_session import run_in_session
                rc = run_in_session(args)
    assert rc == 0


def test_in_session_nonexistent_session_returns_error(tmp_path, sample_db_path):
    """Nonexistent session ID should return error code."""
    args = Namespace(session="ses_nonexistent_12345", notes="")
    with patch("reflect.scripts.lib.in_session.REFLECT_HOME", tmp_path):
        with patch("reflect.scripts.lib.db.open_db") as mock_db:
            conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            mock_db.return_value = conn
            from reflect.scripts.lib.in_session import run_in_session
            rc = run_in_session(args)
    assert rc == 1
