"""collector.py — source readers, mapping, aggregation, snapshot writing.

Reads the host zcode DB and the opencode container DB, maps sessions to
issues, attributes design/IMPL phases, aggregates tokens and active time,
and writes atomic snapshots under data/. Aggregation/snapshots are filled
in by later tasks of #26; this file currently provides:

* `read_host(db_path)`       — sqlite3, read-only URI + PRAGMA busy_timeout=5000;
* `read_container(c, path)`  — `docker exec <c> sqlite3 -readonly -json <db>
  .timeout 5000 <SQL>`, argv list only.

Both return the FULL session set (every directory — filtering is the
mapping stage's job) plus, for the host, all turn_usage/model_usage rows.
Both are fail-open per source: any open/read failure yields a warning
line on stderr and None — the caller skips that source and the pipeline
exit code stays 0.

Mapping layer (spec §Session → issue mapping, §Phase attribution):

* `attribute_project(directory, config)` — ordered directory-prefix match;
* `is_root` / `group_by_root(sessions)` — root = `parent_id IS NULL` per
  source DB, descendants fold into their root (children inherit the root's
  issue);
* `extract_issue(title)` — the spec's ordered pattern set, first match wins;
* `load_overrides(data_dir)` / `save_overrides(data_dir, overrides)` —
  manual bindings in `data/overrides.json`, atomic save, injectable path;
* `phase_for_root(root, mode, source, override)` — split vs title mode,
  override forces either;
* `build_unmatched(host, container, config, overrides)` — rows for roots
  matching no issue (any directory), sorted by tokens desc.

Safety invariants (grep-checked by tests/test_readers.py):
* subprocess calls are argv lists only — never through a shell;
* all SQL is static constants with parameter placeholders where values
  exist — no f-string/format-built SQL anywhere.
"""

import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.parse

DOCKER_TIMEOUT_S = 30           # a wedged docker exec must not hang a collect run

PHASES = ("design", "impl")     # spec §Phase attribution
SOURCES = ("host", "container")
UNATTRIBUTED = "—"              # project shown for directories matching no project
OVERRIDES_FILENAME = "overrides.json"

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


# --- Mapping: project attribution (spec §Session → issue mapping) ----------

def attribute_project(directory, config):
    """Session directory → project name via ordered prefix match.

    Projects are tried in config order and each project's directories in
    their listed order; the first prefix that matches on a path boundary
    (exact directory or a parent of it) wins. Unknown directory → None
    (rendered as «—» in the unmatched table).
    """
    if not directory:
        return None
    for name, spec in config.get("projects", {}).items():
        for prefix in spec.get("directories", []):
            stripped = prefix.rstrip("/")
            if not stripped:
                continue  # "" or "/" would match every path — skip, not wildcard
            if directory == stripped or directory.startswith(stripped + "/"):
                return name
    return None


# --- Mapping: root detection (spec §Session → issue mapping) ---------------

def is_root(session) -> bool:
    """A root session: `parent_id IS NULL` in its own source DB."""
    return session.get("parent_id") is None


def _root_id_of(session, by_id):
    """Walk the parent chain up to the topmost session present in the source.

    Cycle- and dangling-parent-safe: a chain that loops or references a
    missing id stops at the deepest real ancestor.
    """
    current = session
    seen = set()
    while current["id"] not in seen:
        seen.add(current["id"])
        parent_id = current.get("parent_id")
        if parent_id is None or parent_id not in by_id:
            break
        current = by_id[parent_id]
    return current["id"]


def group_by_root(sessions):
    """{root_id: [sessions in that subtree]} for one source's session list.

    Children and grandchildren (any depth) fold into their root — they
    inherit the root's issue (panels and T-tasks do not repeat the number).
    """
    by_id = {s["id"]: s for s in sessions}
    groups = {}
    for session in sessions:
        groups.setdefault(_root_id_of(session, by_id), []).append(session)
    return groups


# --- Mapping: issue number from the root title ------------------------------

# Ordered pattern set, first match wins (leftmost–strongest): `#N` anywhere,
# then a leading bare number (memo habit), then keyword forms (Russian ones
# like «дизайн 26 тикета»). Verbatim from spec §Session → issue mapping.
ISSUE_PATTERNS = (
    re.compile(r"#(\d{1,4})"),
    re.compile(r"^(\d{1,4})\b"),
    re.compile(r"(?:issue|тикет|задач[аи]|дизайн)\s+(\d{1,4})\b"),
)


def extract_issue(title):
    """Root title → issue number (int) or None when nothing matches.

    Patterns are tried in order over the whole title; within a pattern the
    leftmost match wins. No match → the root flows into the unmatched table.
    """
    if not title:
        return None
    for pattern in ISSUE_PATTERNS:
        match = pattern.search(title)
        if match:
            return int(match.group(1))
    return None


# --- Mapping: manual overrides (spec §Session → issue mapping) --------------

def _coerce_issue(value):
    """Any override issue value → positive int or None — never a silent binding.

    Accepts ints and digit-only strings (surrounding whitespace tolerated —
    the file is hand-edited). Rejects everything else: bools (bool IS int
    in Python, guard first), floats (32.5 must not bind issue 32), junk
    strings («№327»), zero/negatives, containers. A None result keeps the
    root visible in the unmatched table instead of binding it silently.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdecimal():
            number = int(text)
            return number if number > 0 else None
    return None


def _normalize_override_entry(entry):
    """{project, issue, phase} with a liberal hand-editable value coercion."""
    return {
        "project": entry.get("project"),
        "issue": _coerce_issue(entry.get("issue")),
        "phase": entry.get("phase"),
    }


def load_overrides(data_dir):
    """Read `data/overrides.json` → {session_id: {project, issue, phase}}.

    Missing file → {}. Unparseable/non-dict content → warning + {} (a
    hand-editing mistake must not kill a collect run). A hand-removed line
    simply takes effect on the next run (full rebuild).
    """
    path = os.path.join(os.fspath(data_dir), OVERRIDES_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        _warn("load_overrides " + path + ": " + str(exc))
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        _warn("load_overrides " + path + ": cannot parse, ignoring overrides")
        return {}
    if not isinstance(data, dict):
        _warn("load_overrides " + path + ": expected an object, ignoring overrides")
        return {}
    overrides = {}
    for session_id, entry in data.items():
        if not isinstance(entry, dict):
            _warn("load_overrides " + path + ": entry " + repr(session_id)
                  + " is not an object, skipping")
            continue
        overrides[session_id] = _normalize_override_entry(entry)
    return overrides


def save_overrides(data_dir, overrides) -> None:
    """Write overrides.json atomically (tmp file + os.replace, spec §Snapshots).

    Sorted keys, UTF-8, indented — hand-editable; all snapshot writers are
    serialized by data/.lock so a fixed tmp name is safe.
    """
    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, OVERRIDES_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(overrides, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


# --- Phase attribution (spec §Phase attribution) -----------------------------

def phase_for_root(root, mode, source, override=None):
    """Phase ("design"/"impl") for a ROOT session under a project's mode.

    * `split`: the source decides — host sessions are design, container
      sessions are IMPL (clean split, title ignored);
    * `title`: the root title starting with IMPL (case-insensitive) → impl,
      otherwise design — source irrelevant.

    An override phase ("design"/"impl") forces either in both modes; any
    other override value falls through to the heuristic. Unknown mode is a
    config error and is loud.
    """
    if override in PHASES:
        return override
    if mode == "split":
        return "design" if source == "host" else "impl"
    if mode == "title":
        title = root.get("title") or ""
        return "impl" if title.upper().startswith("IMPL") else "design"
    raise ValueError("unknown phase_mode: " + repr(mode))


# --- Unmatched rows (spec §Session → issue mapping, step 5) -------------------

def _utc_date(epoch_ms) -> str:
    """Epoch milliseconds → UTC ISO date (deterministic, no local timezone)."""
    moment = datetime.datetime.fromtimestamp(epoch_ms / 1000,
                                             tz=datetime.timezone.utc)
    return moment.date().isoformat()


def _token_total(row) -> int:
    """Plain raw sum of a row's 5 canonical token components.

    Host turn_usage rows and container session rows carry the same five
    token_* column names, so one sum serves both sources.
    """
    return (row["tokens_input"] + row["tokens_output"] + row["tokens_reasoning"]
            + row["tokens_cache_read"] + row["tokens_cache_write"])


def build_unmatched(host, container, config, overrides=None):
    """Rows for roots matching no issue (any directory), tokens desc.

    `host`/`container` are reader payloads (or None for a failed source):
    an override with a well-formed issue (positive int, or a string that
    coerces to one — see `_coerce_issue`) binds its root regardless of
    title or directory (overrides beat every heuristic and carry the
    project for unattributed directories, so such roots leave this
    table); a malformed override issue coerces to None and the root stays
    visible here. Each row: {project (derived else «—»), date, directory,
    title, tokens, session_id} with tokens summed over the root's whole
    subtree.
    """
    overrides = overrides or {}
    rows = []
    for source, payload in ((SOURCES[0], host), (SOURCES[1], container)):
        if not payload:
            continue
        sessions = payload["sessions"]
        by_id = {s["id"]: s for s in sessions}
        groups = group_by_root(sessions)
        if source == "host":
            per_session = {}
            for turn in payload["turns"]:
                per_session[turn["session_id"]] = (
                    per_session.get(turn["session_id"], 0) + _token_total(turn))
        else:
            per_session = {s["id"]: _token_total(s) for s in sessions}
        for root_id, members in groups.items():
            root = by_id[root_id]
            override = overrides.get(root_id) or {}
            # coerce at point of use too: overrides may arrive as raw dicts
            # that never passed through load_overrides normalization
            issue = _coerce_issue(override.get("issue"))
            if issue is None:
                issue = extract_issue(root.get("title"))
            if issue is not None:
                continue  # bound (override or title) — not unmatched
            project = override.get("project") or attribute_project(
                root.get("directory"), config) or UNATTRIBUTED
            tokens = sum(per_session.get(m["id"], 0) for m in members)
            rows.append({
                "project": project,
                "date": _utc_date(root["time_created"]),
                "directory": root["directory"],
                "title": root["title"],
                "tokens": tokens,
                "session_id": root_id,
            })
    rows.sort(key=lambda row: -row["tokens"])
    return rows


def run_collect(config: dict) -> None:
    """Stub: one collection pass; filled in by later tasks of #26."""
