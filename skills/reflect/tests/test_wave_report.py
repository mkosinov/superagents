"""Integration test for wave_report pipeline."""
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock
import sqlite3


def test_wave_report_creates_report(tmp_path, sample_db_path):
    with patch("subprocess.run") as mock_llm:
        mock_llm.return_value = MagicMock(
            returncode=0,
            stdout='{"title":"t","target":"x","rationale":"r","diff":"d"}',
        )
        args = Namespace(name="Wave 4.5")
        with patch("reflect.scripts.lib.wave_report.REFLECT_HOME", tmp_path):
            with patch("reflect.scripts.lib.db.open_db") as mock_db:
                conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                mock_db.return_value = conn
                from reflect.scripts.lib.wave_report import run_wave_report
                rc = run_wave_report(args)
    assert rc == 0
