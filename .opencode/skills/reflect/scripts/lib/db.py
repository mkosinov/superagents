"""SQLite access layer for reflection-mode.

Read-only access to opencode.db. All queries parameterized by timestamp.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any


def open_db(path: Path) -> sqlite3.Connection:
    """Open opencode.db in read-only mode."""
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_sessions(conn: sqlite3.Connection, since_ms: int) -> list[dict]:
    """Return all sessions since timestamp (ms)."""
    cur = conn.execute(
        "SELECT id, title, parent_id, agent, model, cost, tokens_input, "
        "tokens_output, time_created, time_updated, time_archived, path, "
        "time_compacting FROM session WHERE time_created > ? ORDER BY time_created DESC",
        (since_ms,),
    )
    return [dict(r) for r in cur.fetchall()]


def list_tool_calls(conn: sqlite3.Connection, since_ms: int) -> list[dict]:
    """Return all tool calls since timestamp (ms)."""
    cur = conn.execute(
        "SELECT session_id, "
        "json_extract(data, '$.tool') AS tool, "
        "json_extract(data, '$.state.status') AS status, "
        "json_extract(data, '$.state.error') AS error, "
        "json_extract(data, '$.state.metadata.input.command') AS cmd, "
        "time_created, "
        "(time_updated - time_created) AS duration_ms "
        "FROM part WHERE json_extract(data, '$.type') = 'tool' "
        "AND time_created > ?",
        (since_ms,),
    )
    return [dict(r) for r in cur.fetchall()]


def aggregate_tool_usage(
    conn: sqlite3.Connection, since_ms: int
) -> dict[str, dict[str, Any]]:
    """Aggregate tool usage: count, avg duration, first/last used."""
    cur = conn.execute(
        "SELECT json_extract(data, '$.tool') AS tool, "
        "COUNT(*) AS uses, "
        "AVG(time_updated - time_created) AS avg_duration_ms, "
        "MIN(time_created) AS first_used, "
        "MAX(time_created) AS last_used "
        "FROM part WHERE json_extract(data, '$.type') = 'tool' "
        "AND time_created > ? GROUP BY tool ORDER BY uses DESC",
        (since_ms,),
    )
    return {
        r["tool"]: {
            "uses": r["uses"],
            "avg_duration_ms": r["avg_duration_ms"],
            "first_used": r["first_used"],
            "last_used": r["last_used"],
        }
        for r in cur.fetchall()
        if r["tool"]
    }
