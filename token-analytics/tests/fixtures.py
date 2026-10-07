"""fixtures.py — synthetic source-DB generators for token-analytics tests.

Builds the two source schemas from spec §Sources and access into
caller-provided tmp paths at test time (nothing generated is committed):

* host-style      — `session` + `turn_usage` + `model_usage` (zcode CLI DB);
* container-style — one `session` table carrying agent, JSON model and
                    tokens_* counts on the row (opencode DB inside the
                    container, read via `docker exec ... sqlite3`).

All values are deterministic (a fixed epoch-ms anchor plus arithmetic
offsets) so later snapshot tests stay byte-stable. Timestamps are UTC
epoch milliseconds, like both real DBs. Stdlib only.
"""

import json
import sqlite3

BASE_TIME_MS = 1_700_000_000_000  # synthetic UTC anchor, epoch ms
MIN = 60_000
HOUR = 3_600_000

# The 5 canonical token components (spec §Token accounting).
TOKEN_COLUMNS = (
    "tokens_input",
    "tokens_output",
    "tokens_reasoning",
    "tokens_cache_read",
    "tokens_cache_write",
)

DEFAULT_TOKENS = (1_000, 200, 50, 5_000, 300)

# Host marathon sub-session agents (implement/compliance/quality story).
MARATHON_AGENTS = ("zcode-implement", "zcode-compliance", "zcode-quality", "zcode-coder")

HOST_SCHEMA = """\
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    parent_id TEXT,
    directory TEXT NOT NULL,
    title TEXT NOT NULL,
    task_type TEXT,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL
);
CREATE TABLE turn_usage (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    tokens_input INTEGER NOT NULL,
    tokens_output INTEGER NOT NULL,
    tokens_reasoning INTEGER NOT NULL,
    tokens_cache_read INTEGER NOT NULL,
    tokens_cache_write INTEGER NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE model_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    agent TEXT,
    duration_ms INTEGER NOT NULL,
    tokens_input INTEGER NOT NULL,
    tokens_output INTEGER NOT NULL,
    tokens_reasoning INTEGER NOT NULL,
    tokens_cache_read INTEGER NOT NULL,
    tokens_cache_write INTEGER NOT NULL
);
"""

CONTAINER_SCHEMA = """\
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    directory TEXT NOT NULL,
    title TEXT NOT NULL,
    agent TEXT,
    model TEXT NOT NULL,
    tokens_input INTEGER NOT NULL,
    tokens_output INTEGER NOT NULL,
    tokens_reasoning INTEGER NOT NULL,
    tokens_cache_read INTEGER NOT NULL,
    tokens_cache_write INTEGER NOT NULL,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL
);
"""


def _scaled(k):
    """DEFAULT_TOKENS multiplied by k — deterministic per-row token variety."""
    return tuple(value * k for value in DEFAULT_TOKENS)


def make_host_session(id, directory, title, *, parent_id=None, created, updated):
    """A host `session` row with exactly the columns the reader selects."""
    return {
        "id": id,
        "parent_id": parent_id,
        "directory": directory,
        "title": title,
        "time_created": created,
        "time_updated": updated,
    }


def make_turn(session_id, turn_id, *, status="ok", duration_ms=5 * MIN,
              tokens=DEFAULT_TOKENS, retries=0, tool_calls=0, errors=0):
    """A host `turn_usage` row (flat token columns, like the reader output)."""
    row = {
        "session_id": session_id,
        "turn_id": turn_id,
        "status": status,
        "duration_ms": duration_ms,
    }
    row.update(dict(zip(TOKEN_COLUMNS, tokens)))
    row["retries"] = retries
    row["tool_calls"] = tool_calls
    row["errors"] = errors
    return row


def make_model_call(session_id, turn_id, *, model_id, agent,
                    provider_id="anthropic", duration_ms=4 * MIN,
                    tokens=DEFAULT_TOKENS):
    """A host `model_usage` row (one model call with agent attribution)."""
    row = {
        "session_id": session_id,
        "turn_id": turn_id,
        "provider_id": provider_id,
        "model_id": model_id,
        "agent": agent,
        "duration_ms": duration_ms,
    }
    row.update(dict(zip(TOKEN_COLUMNS, tokens)))
    return row


def make_container_session(id, directory, title, *, parent_id=None,
                           agent="frontend-coder", model="claude-opus-4-6",
                           tokens=DEFAULT_TOKENS, created, updated):
    """A container `session` row; `model` is stored as a JSON id string."""
    row = {
        "id": id,
        "parent_id": parent_id,
        "directory": directory,
        "title": title,
        "agent": agent,
        "model": json.dumps({"id": model}),
    }
    row.update(dict(zip(TOKEN_COLUMNS, tokens)))
    row["time_created"] = created
    row["time_updated"] = updated
    return row


def host_scenario(*, memo_dir="/root/workspace/memo",
                  unattributed_dir="/tmp/scratch",
                  parallel_children=2,
                  with_grandchildren=True,
                  marathon_children=("T1: scaffold", "T1: tests", "Fix crash"),
                  childless_roots=1,
                  with_errored_turns=True):
    """Deterministic host-side scenario covering every shape the mapping and
    aggregation tasks need:

    * design root («Разведка issue #327») with parallel OVERLAPPING panel
      children and a grandchild under the last panel child;
    * marathon root (leading-number title) with T-labeled children (T1 twice
      — folds into one node later) plus a standalone «Fix ...» child and a
      grandchild under the first T-child;
    * childless roots (own turns only);
    * a session in an unattributed directory (matches no project);
    * one errored turn (real spend attempt — all turn rows count).
    """
    t0 = BASE_TIME_MS
    sessions, turns, models = [], [], []

    # --- design family -----------------------------------------------------
    sessions.append(make_host_session(
        "h-design", memo_dir, "Разведка issue #327",
        created=t0, updated=t0 + 50 * MIN))
    turns.append(make_turn("h-design", "h-design/t1", duration_ms=9 * MIN, tokens=_scaled(2)))
    turns.append(make_turn("h-design", "h-design/t2", duration_ms=7 * MIN, tool_calls=3))
    models.append(make_model_call("h-design", "h-design/t1", model_id="claude-sonnet-4-5",
                                  agent="zcode-Explore", duration_ms=8 * MIN, tokens=_scaled(2)))
    models.append(make_model_call("h-design", "h-design/t2", model_id="claude-sonnet-4-5",
                                  agent="zcode-Explore", duration_ms=6 * MIN))

    last_child = None
    for k in range(1, parallel_children + 1):
        sid = "h-design-p" + str(k)
        last_child = sid
        title = "panel scout" if k == 1 else "spec panel " + str(k)
        agent = "zcode-Explore" if k == 1 else "zcode-spec-panel-security"
        model_id = "claude-sonnet-4-5" if k == 1 else "claude-opus-4-6"
        # each child starts 10 min after the previous one but overlaps it
        created = t0 + (10 * k - 9) * MIN
        updated = t0 + (10 * k + 11) * MIN
        sessions.append(make_host_session(
            sid, memo_dir, title, parent_id="h-design", created=created, updated=updated))
        turns.append(make_turn(sid, sid + "/t1", duration_ms=5 * MIN, tool_calls=2))
        models.append(make_model_call(sid, sid + "/t1", model_id=model_id, agent=agent))
        if with_errored_turns and k == parallel_children:
            turns.append(make_turn(sid, sid + "/t2", status="error", duration_ms=3_000,
                                   tokens=_scaled(1), retries=1, errors=1))
            models.append(make_model_call(sid, sid + "/t2", model_id=model_id, agent=agent,
                                          duration_ms=3_000))

    if with_grandchildren and last_child is not None:
        gid = last_child + "-g1"
        sessions.append(make_host_session(
            gid, memo_dir, "panel nested probe", parent_id=last_child,
            created=t0 + 12 * MIN, updated=t0 + 16 * MIN))
        turns.append(make_turn(gid, gid + "/t1", duration_ms=4 * MIN))
        models.append(make_model_call(gid, gid + "/t1", model_id="glm-4.7",
                                      agent="zcode-plan-reviewer", provider_id="zhipu",
                                      duration_ms=4 * MIN))

    # --- marathon family ---------------------------------------------------
    m0 = t0 + 2 * HOUR
    sessions.append(make_host_session(
        "h-marathon", memo_dir, "327 cascade marathon",
        created=m0, updated=m0 + 4 * HOUR))
    turns.append(make_turn("h-marathon", "h-marathon/t1", duration_ms=11 * MIN, tokens=_scaled(3)))
    models.append(make_model_call("h-marathon", "h-marathon/t1", model_id="claude-sonnet-4-5",
                                  agent="zcode-manager", duration_ms=10 * MIN, tokens=_scaled(3)))
    for k, title in enumerate(marathon_children, start=1):
        sid = "h-marathon-c" + str(k)
        created = m0 + (k - 1) * 40 * MIN
        agent = MARATHON_AGENTS[(k - 1) % len(MARATHON_AGENTS)]
        model_id = "claude-sonnet-4-5" if k % 2 else "claude-opus-4-6"
        sessions.append(make_host_session(
            sid, memo_dir, title, parent_id="h-marathon",
            created=created, updated=created + 35 * MIN))
        turns.append(make_turn(sid, sid + "/t1", duration_ms=6 * MIN))
        models.append(make_model_call(sid, sid + "/t1", model_id=model_id, agent=agent))
        if with_grandchildren and k == 1:
            gid = sid + "-g1"
            sessions.append(make_host_session(
                gid, memo_dir, "T1 nested compliance", parent_id=sid,
                created=created + 5 * MIN, updated=created + 15 * MIN))
            turns.append(make_turn(gid, gid + "/t1", duration_ms=3 * MIN))
            models.append(make_model_call(gid, gid + "/t1", model_id="glm-4.7",
                                          agent="zcode-compliance", provider_id="zhipu"))

    # --- childless roots ---------------------------------------------------
    for i in range(1, childless_roots + 1):
        sid = "h-solo-" + str(i)
        sessions.append(make_host_session(
            sid, memo_dir, "solo quick check #" + str(330 + i),
            created=t0 + 8 * HOUR + (i - 1) * 10 * MIN,
            updated=t0 + 8 * HOUR + i * 10 * MIN))
        turns.append(make_turn(sid, sid + "/t1", duration_ms=2 * MIN))
        models.append(make_model_call(sid, sid + "/t1", model_id="claude-sonnet-4-5",
                                      agent="zcode-coder", duration_ms=2 * MIN))

    # --- unattributed directory --------------------------------------------
    sessions.append(make_host_session(
        "h-loose", unattributed_dir, "random experiment",
        created=t0 + 9 * HOUR, updated=t0 + 9 * HOUR + 15 * MIN))
    turns.append(make_turn("h-loose", "h-loose/t1", duration_ms=90_000))
    models.append(make_model_call("h-loose", "h-loose/t1", model_id="glm-4.7",
                                  agent="zcode-Explore", provider_id="zhipu",
                                  duration_ms=90_000))

    return {"sessions": sessions, "turns": turns, "models": models}


def container_scenario(*, memo_dir="/root/workspace/memo",
                       unattributed_dir="/opt/playground",
                       marathon_children=("T1: api", "T1: ui", "hotfix db"),
                       with_grandchildren=True,
                       childless_roots=1):
    """Deterministic container-side scenario: marathon wrapper root with
    T-labeled children (overlapping spans) + grandchild under the first
    T-child + standalone child, a childless root, and an unattributed
    directory session. Root wrapper carries tokens (they count)."""
    t0 = BASE_TIME_MS
    sessions = []

    # marathon root wrapper — its tokens count, its time does not
    sessions.append(make_container_session(
        "c-marathon", memo_dir, "#327 IMPL marathon", agent="manager",
        model="claude-opus-4-6", tokens=_scaled(4),
        created=t0 + 2 * HOUR, updated=t0 + 6 * HOUR))

    for k, title in enumerate(marathon_children, start=1):
        sid = "c-marathon-c" + str(k)
        created = t0 + 2 * HOUR + (k - 1) * 80 * MIN
        updated = created + 90 * MIN if k <= 2 else created + 30 * MIN
        agent = "backend-coder" if k != 2 else "frontend-coder"
        model_id = "glm-4.7" if k == 2 else "claude-opus-4-6"
        tokens = _scaled(3) if k == 1 else _scaled(1)
        sessions.append(make_container_session(
            sid, memo_dir, title, parent_id="c-marathon", agent=agent,
            model=model_id, tokens=tokens, created=created, updated=updated))
        if with_grandchildren and k == 1:
            sessions.append(make_container_session(
                sid + "-g1", memo_dir, "T1 nested seed", parent_id=sid,
                agent="backend-coder", model="claude-sonnet-4-5", tokens=_scaled(1),
                created=created + 10 * MIN, updated=created + 25 * MIN))

    for i in range(1, childless_roots + 1):
        sessions.append(make_container_session(
            "c-solo-" + str(i), memo_dir, "#335 tiny fix", agent="plan",
            model="claude-sonnet-4-5", tokens=_scaled(1),
            created=t0 + 7 * HOUR, updated=t0 + 7 * HOUR + 40 * MIN))

    sessions.append(make_container_session(
        "c-play", unattributed_dir, "песочница эксперимент", agent="architect",
        model="glm-4.7", tokens=_scaled(1),
        created=t0 + 9 * HOUR, updated=t0 + 9 * HOUR + 10 * MIN))

    return {"sessions": sessions}


def write_host_db(path, rows):
    """Create a host-style sqlite DB at `path` from scenario row dicts."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(HOST_SCHEMA)
        for s in rows["sessions"]:
            conn.execute(
                "INSERT INTO session"
                " (id, project_id, parent_id, directory, title, task_type, time_created, time_updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (s["id"], "proj-zcode", s["parent_id"], s["directory"], s["title"],
                 "default", s["time_created"], s["time_updated"]))
        for t in rows["turns"]:
            conn.execute(
                "INSERT INTO turn_usage"
                " (turn_id, session_id, status, duration_ms,"
                " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,"
                " retries, tool_calls, errors)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t["turn_id"], t["session_id"], t["status"], t["duration_ms"],
                 t["tokens_input"], t["tokens_output"], t["tokens_reasoning"],
                 t["tokens_cache_read"], t["tokens_cache_write"],
                 t["retries"], t["tool_calls"], t["errors"]))
        for m in rows["models"]:
            conn.execute(
                "INSERT INTO model_usage"
                " (session_id, turn_id, provider_id, model_id, agent, duration_ms,"
                " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (m["session_id"], m["turn_id"], m["provider_id"], m["model_id"],
                 m["agent"], m["duration_ms"],
                 m["tokens_input"], m["tokens_output"], m["tokens_reasoning"],
                 m["tokens_cache_read"], m["tokens_cache_write"]))
        conn.commit()
    finally:
        conn.close()


def write_container_db(path, rows):
    """Create a container-style sqlite DB at `path` from scenario row dicts."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(CONTAINER_SCHEMA)
        for s in rows["sessions"]:
            conn.execute(
                "INSERT INTO session"
                " (id, parent_id, directory, title, agent, model,"
                " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,"
                " time_created, time_updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (s["id"], s["parent_id"], s["directory"], s["title"], s["agent"],
                 s["model"], s["tokens_input"], s["tokens_output"], s["tokens_reasoning"],
                 s["tokens_cache_read"], s["tokens_cache_write"],
                 s["time_created"], s["time_updated"]))
        conn.commit()
    finally:
        conn.close()
