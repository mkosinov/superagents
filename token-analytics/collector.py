"""collector.py — source readers, mapping, aggregation, snapshot writing.

Reads the host zcode DB and the opencode container DB, maps sessions to
issues, attributes design/IMPL phases, aggregates tokens and active time,
and writes atomic snapshots under data/. Mapping/aggregation/snapshots are
filled in by later tasks of #26; this file currently provides the source
readers (spec §Sources and access):

* `read_host(db_path)`       — sqlite3, read-only URI + PRAGMA busy_timeout=5000;
* `read_container(c, path)`  — `docker exec <c> sqlite3 -readonly -json <db>
  .timeout 5000 <SQL>`, argv list only.

Both return the FULL session set (every directory — filtering is the
mapping stage's job) plus, for the host, all turn_usage/model_usage rows.
Both are fail-open per source: any open/read failure yields a warning
line on stderr and None — the caller skips that source and the pipeline
exit code stays 0.

Safety invariants (grep-checked by tests/test_readers.py):
* subprocess calls are argv lists only — never through a shell;
* all SQL is static constants with parameter placeholders where values
  exist — no f-string/format-built SQL anywhere.
"""

import json
import os
import sqlite3
import subprocess
import sys
import urllib.parse

DOCKER_TIMEOUT_S = 30           # a wedged docker exec must not hang a collect run

# Static SELECT-only SQL — no interpolation anywhere (titles are free
# agent-written text and never appear in SQL text).
HOST_SESSION_SQL = (
    "SELECT id, parent_id, directory, title, time_created, time_updated"
    " FROM session ORDER BY id"
)
HOST_TURN_SQL = (
    "SELECT session_id, turn_id, status, duration_ms,"
    " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,"
    " retries, tool_calls, errors"
    " FROM turn_usage ORDER BY session_id, turn_id"
)
HOST_MODEL_SQL = (
    "SELECT session_id, turn_id, provider_id, model_id, agent, duration_ms,"
    " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write"
    " FROM model_usage ORDER BY session_id, turn_id, model_id"
)
CONTAINER_SESSION_SQL = (
    "SELECT id, parent_id, directory, title, agent, model,"
    " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,"
    " time_created, time_updated"
    " FROM session ORDER BY id"
)


def _warn(message: str) -> None:
    """One fail-open warning line on stderr; never fatal (spec §Sources and access)."""
    print("warning: " + message, file=sys.stderr)


def open_host_readonly(db_path: str | os.PathLike) -> sqlite3.Connection:
    """Open the host DB strictly read-only with the shared busy timeout."""
    uri = "file:" + urllib.parse.quote(os.fspath(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _fetch_all(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    columns = [description[0] for description in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def read_host(db_path: str | os.PathLike) -> dict | None:
    """Read every host session/turn/model row.

    Returns {"sessions": [...], "turns": [...], "models": [...]} or, on any
    open/read failure (missing file, not a database, missing table, busy
    beyond the timeout), a warning line + None (fail-open).
    """
    try:
        conn = open_host_readonly(db_path)
    except sqlite3.Error as exc:
        _warn("read_host " + os.fspath(db_path) + ": " + str(exc))
        return None
    try:
        sessions = _fetch_all(conn, HOST_SESSION_SQL)
        turns = _fetch_all(conn, HOST_TURN_SQL)
        models = _fetch_all(conn, HOST_MODEL_SQL)
    except sqlite3.Error as exc:
        _warn("read_host " + os.fspath(db_path) + ": " + str(exc))
        return None
    finally:
        conn.close()
    return {"sessions": sessions, "turns": turns, "models": models}


def _parse_json_output(stdout: str) -> list[dict] | None:
    """Parse `sqlite3 -json` output: a JSON array (classic) or JSON lines
    (newer CLs); empty output means zero rows. None = unparseable."""
    text = stdout.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                return None
            if isinstance(item, dict):
                rows.append(item)
        return rows
    if isinstance(data, dict):
        return [data]
    return [row for row in data if isinstance(row, dict)]


def read_container(container: str, db_path: str) -> dict | None:
    """Read every container session via docker exec + sqlite3 -readonly.

    Returns {"sessions": [...]} or, on any invocation/read failure (docker
    down, unknown container, sqlite error, busy beyond .timeout, unparseable
    output), a warning line + None (fail-open).
    """
    argv = [
        "docker", "exec", container,
        "sqlite3", "-readonly", "-json", os.fspath(db_path),
        ".timeout 5000",
        CONTAINER_SESSION_SQL,
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=DOCKER_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn("read_container " + container + ": " + str(exc))
        return None
    if proc.returncode != 0:
        stderr_lines = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else "no stderr"
        _warn("read_container " + container + ": exit " + str(proc.returncode)
              + ": " + detail)
        return None
    sessions = _parse_json_output(proc.stdout.decode("utf-8", errors="replace"))
    if sessions is None:
        _warn("read_container " + container + ": cannot parse sqlite3 output")
        return None
    return {"sessions": sessions}


def run_collect(config: dict) -> None:
    """Stub: one collection pass; filled in by later tasks of #26."""
