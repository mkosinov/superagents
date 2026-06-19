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