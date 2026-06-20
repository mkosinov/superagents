"""Tests for db.py — SQLite access layer."""
from pathlib import Path
import pytest
import sqlite3
from reflect.scripts.lib.db import (
    open_db,
    list_sessions,
    list_tool_calls,
    aggregate_tool_usage,
)


def test_open_db_returns_readonly_connection(sample_db_path: Path):
    conn = open_db(sample_db_path)
    # Verify read-only: writing should fail
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("CREATE TABLE x (y INT)")
    conn.close()


def test_list_sessions_returns_rows(sample_db_path: Path):
    conn = open_db(sample_db_path)
    sessions = list_sessions(conn, since_ms=0)
    assert isinstance(sessions, list)
    assert len(sessions) > 0
    assert "id" in sessions[0]
    assert "agent" in sessions[0]
    conn.close()


def test_list_tool_calls_returns_tool_data(sample_db_path: Path):
    conn = open_db(sample_db_path)
    calls = list_tool_calls(conn, since_ms=0)
    assert isinstance(calls, list)
    assert len(calls) > 0
    assert "tool" in calls[0]
    assert "session_id" in calls[0]
    conn.close()


def test_aggregate_tool_usage_groups_by_tool(sample_db_path: Path):
    conn = open_db(sample_db_path)
    agg = aggregate_tool_usage(conn, since_ms=0)
    assert isinstance(agg, dict)
    assert "bash" in agg  # bash is used everywhere
    assert agg["bash"]["uses"] > 0
    conn.close()
