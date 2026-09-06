"""Pytest configuration for reflect skill tests."""
import shutil
from pathlib import Path
import pytest
import sqlite3

REAL_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


@pytest.fixture(scope="session")
def sample_db_path(tmp_path_factory) -> Path:
    """Copy real opencode.db to tmp for testing (read-only safe)."""
    if not REAL_DB.exists():
        pytest.skip(f"Real opencode.db not found at {REAL_DB}")
    tmp_db = tmp_path_factory.mktemp("data") / "opencode.db"
    shutil.copy(REAL_DB, tmp_db)
    return tmp_db


@pytest.fixture
def db_connection(sample_db_path) -> sqlite3.Connection:
    """Read-only SQLite connection."""
    conn = sqlite3.connect(f"file:{sample_db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
