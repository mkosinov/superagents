"""collector.py — source readers, mapping, aggregation, snapshot writing.

Reads the host zcode DB and the opencode container DB, maps sessions to
issues, attributes design/IMPL phases, aggregates tokens and active time,
and writes atomic snapshots under data/. The one-collection-pass entry
point `run_collect` (Task 5) wires it all under data/.lock and calls the
write-back hook (a no-op stub in writeback.py until Task 8):

Source readers (spec §Sources and access):

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

Aggregation + snapshot writing (spec §Token accounting, §Active model time
and calendar span, §Drill-down tree, §By-model and by-agent aggregates,
§Snapshots and state):

* `aggregate(host, container, config, overrides, titles)` — the rebuild
  core: per-issue snapshot dicts (tokens 5 components + raw-sum total,
  active model time, calendar span per phase, recursive drill-down tree
  with T-folding on IMPL-root children and agent-labeled design children,
  by_model/by_agent bars, board-ready rounded values);
* `rebuild(host, container, config, data_dir)` — one full pass: refresh
  the gh title cache, aggregate, write `issues/*.json` + `index.json` +
  `unmatched.json` atomically, drop stale issue files, ensure
  `state.json` exists (write-back caches only);
* `fetch_issue_titles(repo)` / `refresh_titles(...)` — one bulk
  `gh issue list` argv call per repo per run; `data/titles.json` is the
  offline fallback cache (closed issues keep the last known title);
* `run_collect(config, data_dir)` — the CLI's one pass: exclusive
  flock on `data/.lock` for the whole write phase (a concurrent run
  logs «skipped: previous run still active» and returns "skipped" —
  the caller exits 0), then readers → rebuild → write-back hook;
  `load_config(path)` / `data_dir_for(config_path)` pin the config
  and its sibling data/ dir (spec §Directory layout, §Config file).

Determinism: every JSON write goes through `_atomic_write_json`
(tmp + `os.replace`, `sort_keys=True`, `ensure_ascii=False`) and no
wall-clock timestamp ever enters a snapshot — `collected_at` and
last-activity dates are derived from DB times — so identical input yields
byte-identical output.

Safety invariants (grep-checked by tests/test_readers.py):
* subprocess calls are argv lists only — never through a shell;
* all SQL is static constants with parameter placeholders where values
  exist — no f-string/format-built SQL anywhere.
"""

import datetime
import fcntl
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


def _atomic_write_json(path, payload) -> None:
    """Write JSON atomically: tmp file + os.replace (spec §Snapshots).

    Sorted keys, UTF-8, indented — hand-editable and byte-deterministic.
    Writers are serialized by the exclusive flock on data/.lock that
    `run_collect` holds for the whole write phase (Task 5) — that
    serialization is what makes a fixed tmp name safe. A failure
    anywhere between tmp creation and replace removes the tmp file and
    re-raises — the previous file stays intact.
    """
    tmp = os.fspath(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_overrides(data_dir, overrides) -> None:
    """Write overrides.json atomically (tmp file + os.replace, spec §Snapshots)."""
    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    _atomic_write_json(os.path.join(directory, OVERRIDES_FILENAME), overrides)


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


def _utc_iso(epoch_ms) -> str:
    """Epoch milliseconds → UTC ISO-8601 second timestamp (deterministic)."""
    moment = datetime.datetime.fromtimestamp(int(epoch_ms) // 1000,
                                             tz=datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Aggregation: the rebuild core (spec §Token accounting, §Active model
# --- time and calendar span, §Drill-down tree, §By-model/by-agent) ---------

# The 5 canonical components and their column names in both source DBs.
TOKEN_KINDS = ("input", "output", "reasoning", "cache_read", "cache_write")
TOKEN_KIND_COLUMNS = (
    ("input", "tokens_input"),
    ("output", "tokens_output"),
    ("reasoning", "tokens_reasoning"),
    ("cache_read", "tokens_cache_read"),
    ("cache_write", "tokens_cache_write"),
)

MS_PER_HOUR = 3_600_000
MS_PER_DAY = 86_400_000

# IMPL-phase marathon children folding: `T1: …` / `T1. …` / `T1 …` all fold
# into one `T1` node aggregating their subtrees (spec §Drill-down tree).
T_LABEL_RE = re.compile(r"^T(\d+)[:. ]")


def board_total_m(total: int) -> float:
    """Raw token total → board value in millions, 1 decimal («48.2»)."""
    return round(total / 1_000_000, 1)


def board_hours(active_ms: int) -> float:
    """Active milliseconds → board value in hours, 1 decimal («25.3»)."""
    return round(active_ms / MS_PER_HOUR, 1)


def _zero_tokens() -> dict:
    return {kind: 0 for kind in TOKEN_KINDS}


def _add_tokens(acc, row) -> None:
    """Add a source row's 5 token columns into a kind-keyed accumulator."""
    for kind, column in TOKEN_KIND_COLUMNS:
        acc[kind] += row.get(column) or 0


def _tokens_block(acc) -> dict:
    """Kind accumulator → snapshot block: 5 components + total + total_m."""
    block = dict(acc)
    block["total"] = sum(acc[kind] for kind in TOKEN_KINDS)
    block["total_m"] = board_total_m(block["total"])
    return block


def _calendar_block(span_ms: int) -> dict:
    """Calendar span: whole days at/above a day, hours (1 dp) below it."""
    if span_ms >= MS_PER_DAY:
        return {"ms": span_ms, "days": int(round(span_ms / MS_PER_DAY)), "hours": None}
    return {"ms": span_ms, "days": None, "hours": board_hours(span_ms)}


def _bars(counts: dict, key: str) -> list:
    """{name: tokens} → sorted bar-chart rows, tokens desc then name asc."""
    return [{key: name, "tokens": total}
            for name, total in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _children_map(sessions) -> dict:
    """{parent_id: [direct child sessions]} in session-list order."""
    children = {}
    for session in sessions:
        children.setdefault(session.get("parent_id"), []).append(session)
    return children


def _container_model_id(session):
    """Container session.model (JSON `{"id": …}`) → the model id string."""
    raw = session.get("model")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if isinstance(data, dict) and data.get("id"):
        return data["id"]
    return raw


def _host_session_metrics(payload: dict) -> dict:
    """Per host session: tokens (5 kinds, ALL turn_usage rows — errored and
    cancelled turns are real spend attempts), active_ms (per-turn durations
    summed — roots AND children count), and agent attribution from
    model_usage for tree labels."""
    metrics = {}

    def _rec(session_id):
        return metrics.setdefault(session_id, {
            "tokens": _zero_tokens(), "active_ms": 0, "agent": None,
            "agent_tokens": {},
        })

    for turn in payload.get("turns") or []:
        rec = _rec(turn["session_id"])
        _add_tokens(rec["tokens"], turn)
        rec["active_ms"] += turn.get("duration_ms") or 0
    for row in payload.get("models") or []:
        rec = _rec(row["session_id"])
        agent = row.get("agent")
        rec["agent_tokens"][agent] = rec["agent_tokens"].get(agent, 0) + _token_total(row)
    for rec in metrics.values():
        # label = the session's highest-token agent (ties → name asc);
        # unrecognized agents keep their raw string — no translation
        rec["agent"] = _dominant_agent(rec["agent_tokens"])
    return metrics


def _dominant_agent(agent_tokens: dict):
    if not agent_tokens:
        return None
    ranked = sorted(agent_tokens.items(), key=lambda kv: (-kv[1], kv[0] or ""))
    return ranked[0][0]


def _container_session_metrics(sessions: list) -> dict:
    """Per container session: tokens from the session row (root wrappers'
    tokens COUNT — real orchestration spend) and the active-time
    approximation `time_updated − time_created`, with marathon root
    wrappers excluded (their span ≈ the whole marathon calendar) while
    childless roots count their own span (single-step IMPL session)."""
    children = _children_map(sessions)
    metrics = {}
    for session in sessions:
        tokens = {kind: (session.get(column) or 0) for kind, column in TOKEN_KIND_COLUMNS}
        span = max(0, (session.get("time_updated") or 0) - (session.get("time_created") or 0))
        is_wrapper = session.get("parent_id") is None and bool(children.get(session["id"]))
        metrics[session["id"]] = {
            "tokens": tokens,
            "active_ms": 0 if is_wrapper else span,
            "agent": session.get("agent"),
            "model": _container_model_id(session),
        }
    return metrics


def _model_rows_by_session(models: list) -> dict:
    rows = {}
    for row in models or []:
        rows.setdefault(row["session_id"], []).append(row)
    return rows


def _fold_t_children(nodes: list) -> list:
    """Fold `T<N>`-titled root children into one aggregating node each.

    One task = several sub-sessions (implement/compliance/quality) — they
    aggregate under a single `T<N>` node, each keeping its own subtree as
    a child; unlabeled children («Fix …») stay standalone (spec
    §Drill-down tree). Fold nodes appear at their first member's position.
    """
    folded = []
    t_nodes = {}
    for node in nodes:
        match = T_LABEL_RE.match(node["title"] or "")
        if not match:
            folded.append(node)
            continue
        number = match.group(1)
        t_node = t_nodes.get(number)
        if t_node is None:
            t_node = {"session_id": None, "title": "T" + number, "agent": None,
                      "tokens": _zero_tokens(), "active_ms": 0, "children": [],
                      "approx": False}
            t_nodes[number] = t_node
            folded.append(t_node)
        for kind in TOKEN_KINDS:
            t_node["tokens"][kind] += node["tokens"][kind]
        t_node["active_ms"] += node["active_ms"]
        # fold nodes inherit the container-time approximation flag
        t_node["approx"] = t_node["approx"] or bool(node.get("approx"))
        t_node["children"].append(node)
    for t_node in t_nodes.values():
        t_node["tokens"] = _tokens_block(t_node["tokens"])
    return folded


def _build_node(session, children_map, metrics, fold_t=False, visited=None,
                allowed=None, approx=False) -> dict:
    """Session → tree node whose tokens/active are its WHOLE subtree's
    aggregate (own session + descendants, any nesting depth).

    Cycle-safe like `_root_id_of`: `visited` collects the ids already
    built on this descent, so a parent cycle (A↔B or a self-parent)
    stops descending at the repeat instead of recursing forever, and
    `allowed` (the root's group_by_root member ids, passed by
    aggregate) keeps the tree consistent with the accounting — a
    cyclic sibling that group_by_root made its own root is drilled
    into only under itself. Ids are unique per source, so on
    well-formed trees both guards prune nothing.

    `approx` marks container-built time (the `time_updated −
    time_created` span approximation; spec §Active model time) — the
    viewer renders it with the «≈ сумма по параллельным дочерним
    сессиям» label. Host nodes are exact per-turn sums: approx=False.
    """
    visited = visited if visited is not None else set()
    visited.add(session["id"])
    rec = metrics.get(session["id"]) or {}
    tokens = dict(rec.get("tokens") or _zero_tokens())
    active_ms = rec.get("active_ms") or 0
    children = [_build_node(child, children_map, metrics, visited=visited,
                            allowed=allowed, approx=approx)
                for child in children_map.get(session["id"], [])
                if child["id"] not in visited
                and (allowed is None or child["id"] in allowed)]
    if fold_t:  # T-folding applies to IMPL-root children only, not deeper
        children = _fold_t_children(children)
    for child in children:
        for kind in TOKEN_KINDS:
            tokens[kind] += child["tokens"][kind]
        active_ms += child["active_ms"]
    return {
        "session_id": session["id"],
        "title": session.get("title"),
        "agent": rec.get("agent"),
        "tokens": _tokens_block(tokens),
        "active_ms": active_ms,
        "children": children,
        "approx": approx,
    }


def _new_issue_acc() -> dict:
    return {"phases": {}, "max_updated": None}


def _new_phase_acc() -> dict:
    return {"tokens": _zero_tokens(), "active_ms": 0,
            "min_created": None, "max_updated": None,
            "by_model": {}, "by_agent": {}, "roots": []}


def aggregate(host, container, config, overrides=None, titles=None) -> dict:
    """Both source payloads → per-issue snapshot dicts (the rebuild core).

    `host`/`container` are reader payloads (None = source unavailable,
    skipped fail-open). Roots are mapped to (project, issue) by the
    mapping layer (overrides beat every heuristic) and phased per the
    project's mode; each root's whole subtree folds into its issue.
    Returns {"issues": {(project, issue): snapshot}, "unmatched": rows}.

    Snapshot shape (spec §Snapshots and state): title + source, project,
    last activity, issue-level raw totals (5 components + total +
    active_ms) AND board-ready values (`tokens.total_m`, `active.hours`,
    mirrored per phase), `phases.{design,impl}` each with tokens,
    active_ms/hours, calendar span, the recursive drill-down tree, and
    by_model/by_agent bars; `by_model`/`by_agent`/`collected_at` at the
    top. Every date is data-derived — no wall clock (byte determinism).
    """
    overrides = overrides or {}
    titles = titles or {}
    projects_cfg = config.get("projects", {})
    issues = {}

    for source, payload in ((SOURCES[0], host), (SOURCES[1], container)):
        if not payload:
            continue
        sessions = payload["sessions"]
        by_id = {s["id"]: s for s in sessions}
        children_map = _children_map(sessions)
        groups = group_by_root(sessions)
        if source == "host":
            metrics = _host_session_metrics(payload)
            model_rows = _model_rows_by_session(payload.get("models"))
        else:
            metrics = _container_session_metrics(sessions)
            model_rows = {}

        for root_id in sorted(groups):
            root = by_id[root_id]
            override = overrides.get(root_id) or {}
            project = override.get("project") or attribute_project(
                root.get("directory"), config)
            issue = _coerce_issue(override.get("issue"))
            if issue is None:
                issue = extract_issue(root.get("title"))
            if project is None or issue is None:
                continue  # unmapped — flows into the unmatched table
            spec = projects_cfg.get(project)
            if spec is None:
                _warn("aggregate: project " + repr(project)
                      + " not in config (override typo?); title phase mode assumed")
                mode = "title"
            else:
                mode = spec.get("phase_mode", "title")
            phase = phase_for_root(root, mode, source, override.get("phase"))

            issue_acc = issues.setdefault((project, issue), _new_issue_acc())
            phase_acc = issue_acc["phases"].setdefault(phase, _new_phase_acc())
            for member in groups[root_id]:
                rec = metrics.get(member["id"])
                if rec is not None:
                    _add_into(phase_acc["tokens"], rec["tokens"])
                    phase_acc["active_ms"] += rec["active_ms"]
                    if source == "container":
                        total = sum(rec["tokens"].values())
                        # a blank model string yields None — unattributed,
                        # like every other missing name (one bad row must
                        # not kill the collect run in _bars' sort)
                        model = rec["model"] or UNATTRIBUTED
                        phase_acc["by_model"][model] = (
                            phase_acc["by_model"].get(model, 0) + total)
                        agent = rec["agent"] or UNATTRIBUTED
                        phase_acc["by_agent"][agent] = (
                            phase_acc["by_agent"].get(agent, 0) + total)
                created = member.get("time_created")
                updated = member.get("time_updated")
                phase_acc["min_created"] = _min_nullable(phase_acc["min_created"], created)
                phase_acc["max_updated"] = _max_nullable(phase_acc["max_updated"], updated)
                issue_acc["max_updated"] = _max_nullable(issue_acc["max_updated"], updated)
                if source == "host":
                    for row in model_rows.get(member["id"], []):
                        total = _token_total(row)
                        model_id = row.get("model_id") or UNATTRIBUTED
                        phase_acc["by_model"][model_id] = (
                            phase_acc["by_model"].get(model_id, 0) + total)
                        agent = row.get("agent") or UNATTRIBUTED
                        phase_acc["by_agent"][agent] = (
                            phase_acc["by_agent"].get(agent, 0) + total)
            phase_acc["roots"].append(_build_node(
                root, children_map, metrics, fold_t=(phase == "impl"),
                allowed={member["id"] for member in groups[root_id]},
                approx=(source == "container")))

    snapshots = {key: _make_snapshot(key, acc, config, titles)
                 for key, acc in issues.items()}
    return {
        "issues": snapshots,
        "unmatched": build_unmatched(host, container, config, overrides),
    }


def _add_into(acc, tokens) -> None:
    for kind in TOKEN_KINDS:
        acc[kind] += tokens.get(kind) or 0


def _min_nullable(current, candidate):
    if candidate is None:
        return current
    return candidate if current is None else min(current, candidate)


def _max_nullable(current, candidate):
    if candidate is None:
        return current
    return candidate if current is None else max(current, candidate)


def _make_snapshot(key, issue_acc, config, titles) -> dict:
    """Issue accumulator → the final snapshot dict (shapes pinned by spec)."""
    project, issue = key
    repo = (config.get("projects", {}).get(project) or {}).get("repo")
    repo_titles = titles.get(repo) if repo else None
    number = str(issue)
    if repo_titles and number in repo_titles:
        title, title_source = repo_titles[number], "gh"
    else:
        title, title_source = "issue #" + number, "fallback"

    issue_tokens = _zero_tokens()
    issue_active_ms = 0
    issue_by_model, issue_by_agent = {}, {}
    phases = {}
    for phase in sorted(issue_acc["phases"]):
        acc = issue_acc["phases"][phase]
        _add_into(issue_tokens, acc["tokens"])
        issue_active_ms += acc["active_ms"]
        for name, total in acc["by_model"].items():
            issue_by_model[name] = issue_by_model.get(name, 0) + total
        for name, total in acc["by_agent"].items():
            issue_by_agent[name] = issue_by_agent.get(name, 0) + total
        span_ms = (acc["max_updated"] or 0) - (acc["min_created"] or 0)
        phases[phase] = {
            "tokens": _tokens_block(acc["tokens"]),
            "active_ms": acc["active_ms"],
            "active": {"hours": board_hours(acc["active_ms"])},
            "calendar": _calendar_block(span_ms),
            "tree": sorted(acc["roots"],
                           key=lambda node: (-node["tokens"]["total"],
                                             node["session_id"])),
            "by_model": _bars(acc["by_model"], "model"),
            "by_agent": _bars(acc["by_agent"], "agent"),
        }
    max_updated = issue_acc["max_updated"]
    return {
        "project": project,
        "issue": issue,
        "title": title,
        "title_source": title_source,
        "last_activity": _utc_date(max_updated) if max_updated is not None else None,
        # data-derived (DB times) — never a wall clock, for byte determinism
        "collected_at": _utc_iso(max_updated) if max_updated is not None else None,
        "tokens": _tokens_block(issue_tokens),
        "active_ms": issue_active_ms,
        "active": {"hours": board_hours(issue_active_ms)},
        "phases": phases,
        "by_model": _bars(issue_by_model, "model"),
        "by_agent": _bars(issue_by_agent, "agent"),
    }


# --- Issue titles: one bulk gh call per repo per run (spec §Snapshots) -------

GH_TIMEOUT_S = 30               # a wedged gh must not hang a collect run
GH_LIST_LIMIT = "1000"          # no 30-row defaults — loop/exhaust equivalents
TITLES_FILENAME = "titles.json"
STATE_FILENAME = "state.json"
INDEX_FILENAME = "index.json"
UNMATCHED_FILENAME = "unmatched.json"
ISSUES_DIRNAME = "issues"


def fetch_issue_titles(repo: str) -> dict | None:
    """One bulk `gh issue list` per repo → {issue_number: title}, or None.

    `--state all` so closed issues refresh too; the titles.json cache is
    the offline fallback either way (closed issues keep the last known
    title). Any invocation/parse failure → warning + None (fail-open).
    """
    argv = ["gh", "issue", "list",
            "--repo", repo,
            "--state", "all",
            "--limit", GH_LIST_LIMIT,
            "--json", "number,title"]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=GH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn("fetch_issue_titles " + repo + ": " + str(exc))
        return None
    if proc.returncode != 0:
        stderr_lines = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else "no stderr"
        _warn("fetch_issue_titles " + repo + ": exit " + str(proc.returncode)
              + ": " + detail)
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _warn("fetch_issue_titles " + repo + ": cannot parse gh output")
        return None
    titles = {}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and isinstance(row.get("number"), int) \
                    and isinstance(row.get("title"), str):
                titles[row["number"]] = row["title"]
    return titles


def load_titles(data_dir) -> dict:
    """Read data/titles.json → {repo: {issue-number-string: title}}.

    Missing file → {}. Corrupt/non-dict content → warning + {} (the cache
    must not kill a collect run).
    """
    path = os.path.join(os.fspath(data_dir), TITLES_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        _warn("load_titles " + path + ": " + str(exc))
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        _warn("load_titles " + path + ": cannot parse, ignoring cache")
        return {}
    if not isinstance(data, dict):
        _warn("load_titles " + path + ": expected an object, ignoring cache")
        return {}
    titles = {}
    for repo, entries in data.items():
        if isinstance(entries, dict):
            titles[repo] = {str(number): title for number, title in entries.items()
                            if isinstance(title, str)}
    return titles


def refresh_titles(data_dir, config, fetch=None) -> dict:
    """Refresh the gh title cache: one bulk call per configured repo, merged
    over the existing cache (fresh wins per issue; cached issues gh no
    longer returns — e.g. filtered-out closed ones — keep their last known
    title). Saves and returns the merged mapping.
    """
    fetch = fetch or fetch_issue_titles
    cache = load_titles(data_dir)
    merged = {repo: dict(entries) for repo, entries in cache.items()}
    repos = set()
    for spec in config.get("projects", {}).values():
        repo = (spec or {}).get("repo")
        if repo:
            repos.add(repo)
    for repo in sorted(repos):
        fresh = fetch(repo)
        if fresh is None:
            _warn("titles " + repo + ": gh failed, keeping cached titles")
            continue
        entries = merged.setdefault(repo, {})
        for number, title in fresh.items():
            entries[str(number)] = title
    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    _atomic_write_json(os.path.join(directory, TITLES_FILENAME), merged)
    return merged


def write_snapshots(data_dir, aggregated, sources=None, projects=None) -> None:
    """Persist an aggregate() result under data/ — all writes atomic.

    Writes `issues/<project>-<N>.json`, `index.json` (issue rows with
    totals/phase split/last activity, sorted by spend desc, plus
    per-source availability and — when `projects` (the configured
    project keys) is given — the `projects` list the viewer builds its
    tabs from, so a project with zero mapped issues still gets a tab
    with an explicit empty state), `unmatched.json`; removes snapshot
    files of issues that no longer have mapped sessions (their index
    entries are gone with the rewrite) and sweeps stale `*.tmp`
    leftovers a killed run may have left in issues/ (the sweep runs
    after every current write — `_atomic_write_json` renames or
    deletes each tmp — so any `*.tmp` still present is by definition
    orphaned); creates `state.json` when missing (write-back caches
    only — nothing else ever goes in it here).
    """
    directory = os.fspath(data_dir)
    issues_dir = os.path.join(directory, ISSUES_DIRNAME)
    os.makedirs(issues_dir, exist_ok=True)
    current = set()
    index_rows = []
    for (project, issue), snapshot in sorted(aggregated.get("issues", {}).items()):
        name = str(project) + "-" + str(issue) + ".json"
        _atomic_write_json(os.path.join(issues_dir, name), snapshot)
        current.add(name)
        index_rows.append({
            "project": snapshot["project"],
            "issue": snapshot["issue"],
            "title": snapshot["title"],
            "title_source": snapshot["title_source"],
            "tokens": {"total": snapshot["tokens"]["total"],
                       "total_m": snapshot["tokens"]["total_m"]},
            "active_ms": snapshot["active_ms"],
            "phases": {phase: {"tokens": {"total": block["tokens"]["total"],
                                          "total_m": block["tokens"]["total_m"]},
                                "active_ms": block["active_ms"]}
                        for phase, block in snapshot["phases"].items()},
            "last_activity": snapshot["last_activity"],
        })
    index_rows.sort(key=lambda row: (-row["tokens"]["total"], row["project"],
                                     row["issue"]))
    index_payload = {"issues": index_rows, "sources": dict(sources or {})}
    if projects is not None:
        index_payload["projects"] = sorted(projects)
    _atomic_write_json(os.path.join(directory, INDEX_FILENAME), index_payload)
    _atomic_write_json(os.path.join(directory, UNMATCHED_FILENAME),
                       aggregated.get("unmatched", []))
    # Stale sweep, post-write: vanished issues lose their .json; any
    # *.tmp left is a SIGKILL leftover from an earlier run (this run's
    # tmps are all renamed or deleted by _atomic_write_json by now).
    with os.scandir(issues_dir) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            if entry.name.endswith(".json") and entry.name not in current:
                os.unlink(entry.path)
            elif entry.name.endswith(".tmp"):
                os.unlink(entry.path)
    state_path = os.path.join(directory, STATE_FILENAME)
    if not os.path.exists(state_path):
        _atomic_write_json(state_path, {})


def rebuild(host, container, config, data_dir, overrides=None, fetch_titles=None) -> dict:
    """One full rebuild over both sources into data/ (spec §Collection runs).

    Loads overrides from data_dir unless given, refreshes the gh title
    cache (injectable fetcher), aggregates, writes every snapshot file
    atomically and returns the aggregate() result. First run and every
    later run are the same code path.
    """
    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    if overrides is None:
        overrides = load_overrides(directory)
    titles = refresh_titles(directory, config, fetch_titles)
    aggregated = aggregate(host, container, config, overrides=overrides,
                           titles=titles)
    write_snapshots(directory, aggregated,
                    sources={"host": host is not None,
                             "container": container is not None},
                    projects=config.get("projects", {}).keys())
    return aggregated


# --- Collection pass: config plumbing + the locked pipeline entry ------------
# (spec §Collection runs, §Config file, §Snapshots and state)

LOCK_FILENAME = ".lock"
SKIP_MESSAGE = "skipped: previous run still active"


def load_config(path) -> dict:
    """Read config.json (committed, no secrets — spec §Config file).

    A config that cannot be read or parsed is a loud error raised to
    the caller — unlike source failures this is NOT fail-open: without
    a valid config there is nothing sensible to collect.
    """
    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    return config


def data_dir_for(config_path) -> str:
    """The data dir for a config path: the `data/` sibling of the config
    file (spec §Directory layout — data/ belongs to the token-analytics/
    layout the config lives in; a tmp fixture config yields a tmp data
    dir, which is what keeps test paths injectable)."""
    parent = os.path.dirname(os.path.abspath(os.fspath(config_path)))
    return os.path.join(parent, "data")


def _read_host_source(config):
    """Config's zcode_host entry → reader payload (None when unconfigured
    or unavailable — the reader itself warns fail-open)."""
    spec = (config.get("sources") or {}).get("zcode_host") or {}
    db = spec.get("db")
    if not db:
        return None
    return read_host(os.path.expanduser(db))


def _read_container_source(config):
    """Config's opencode_container entry → reader payload (None when
    unconfigured or unavailable — fail-open per source)."""
    spec = (config.get("sources") or {}).get("opencode_container") or {}
    container = spec.get("container")
    db = spec.get("db")
    if not container or not db:
        return None
    return read_container(container, os.path.expanduser(db))


def run_collect(config: dict, data_dir) -> str:
    """One full collection pass under data/.lock (spec §Collection runs).

    Acquires an exclusive flock on `data/.lock` for the whole write
    phase; a second run finding the lock held logs «skipped: previous
    run still active» on stderr (cron redirects it into
    data/collect.log) and returns "skipped" — the caller exits 0 either
    way. With the lock: readers → rebuild (mapping + aggregation +
    snapshots, per-source availability into index.json) → the write-back
    hook `writeback.run_after_rebuild` (a no-op stub until Task 8).
    Source failures stay fail-open: readers warn + return None, the
    other source still rebuilds, the run returns "ok".
    """
    # Imported here rather than at module top: keeps collector importable
    # standalone whatever writeback grows to import (Task 8).
    import writeback

    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    lock_fd = os.open(os.path.join(directory, LOCK_FILENAME),
                      os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(SKIP_MESSAGE, file=sys.stderr)
            return "skipped"
        host = _read_host_source(config)
        container = _read_container_source(config)
        rebuild(host, container, config, directory)
        writeback.run_after_rebuild(config, directory)
        return "ok"
    finally:
        os.close(lock_fd)  # releases the flock (never held on "skipped")
