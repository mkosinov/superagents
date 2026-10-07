"""writeback.py — board write-back via the managed gh CLI (#26 Task 8).

Pushes each issue's board-ready snapshot values (tokens in millions,
hours, 1 decimal — «48.2», «25.3») onto that project's own GitHub
Projects board (spec §Board write-back). Runs after every rebuild
(`run_after_rebuild`, called by collector.run_collect and the serve
bind rebuild — both already hold data/.lock) and standalone via
`collect.py writeback` (a manual re-push from the snapshots already
in data/, same pipeline, own flock).

Managed CLI only — the recorded second-writer exception beside
gh_board.py, approved at G1a close:

* `gh project item-edit --id <item> --field-id <field>
  --project-id <project> --number <value>` — one item+field per call;
* `gh project field-list <number> --owner <owner> --format json
  --limit N` / `gh project item-list …` — reads, drained with an
  EXPLICIT limit and a loop until exhausted (the CLI's default 30
  silently truncates; #24 canon). gh pages internally up to --limit
  and each call returns a full stable prefix + totalCount, so the
  drain grows the explicit limit until totalCount is covered;
* `gh project field-create <number> --owner <owner> --name <name>
  --data-type NUMBER` — one-time field creation (`collect.py fields`).

NEVER raw GraphQL and NEVER field-definition mutations — the
2026-09-09 wipe ban stands untouched.

Field binding is by NAME (config `write_back.fields`: name → snapshot
dot-path); ids are resolved per run. Unknown name → warning + that
field skipped with a «run `collect.py fields`» hint. Values are
diff-gated against the last WRITTEN value cached in `data/state.json`
(so rounding noise never writes); the cache updates only after a
successful write, and a write failure drops the item's cached id (a
re-added card gets a new one — re-resolved next run). Everything is
fail-open: a gh/network failure warns on stderr, the run continues,
the exit code stays 0. No status filtering — WIP and closed issues
are written alike; an issue not on the board is skipped with a note.

`gh project field-list` JSON exposes the GraphQL typename per field;
`ProjectV2Field` covers NUMBER (and TEXT/DATE — indistinguishable via
the managed CLI; a TEXT field simply fails its writes fail-open),
while `ProjectV2SingleSelectField` / `ProjectV2IterationField` are
definitely non-NUMBER: `fields` stops loudly on those, changing
nothing (it never renames fields, never touches single-select
options).
"""

import json
import os
import subprocess
import sys

GH_TIMEOUT_S = 30             # a wedged gh must not hang a collect run
PAGE_SIZE = 100               # explicit per-call --limit (default 30 truncates)
LIMIT_CAP = 2000              # drain-loop guard for a pathological totalCount
NUMBER_FIELD_TYPE = "ProjectV2Field"  # gh JSON typename covering NUMBER fields
STATE_KEY = "writeback"       # state.json namespace owned by this module
FIELDS_HINT = "run `collect.py fields`"

# Sentinel for «path not present in this snapshot» — deliberately NOT
# None so a missing value can never be silently written anywhere.
MISSING = object()


def _warn(message: str) -> None:
    """One fail-open warning line on stderr (collector's convention)."""
    print("warning: " + message, file=sys.stderr)


def _note(message: str) -> None:
    """An informational line on stderr (notes land in collect.log)."""
    print(message, file=sys.stderr)


# --- dot-path resolution -------------------------------------------------------

def resolve_path(snapshot, path: str):
    """Resolve a config dot-path (`tokens.total_m`, …) inside a snapshot.

    Returns the value, or MISSING when any segment is absent (a
    phase-less issue, a config typo) — never a silent None.
    """
    current = snapshot
    for segment in str(path).split("."):
        if not isinstance(current, dict) or segment not in current:
            return MISSING
        current = current[segment]
    return MISSING if current is None else current


# --- gh plumbing: argv lists only, fail-open (gh_board.py's error pattern) ----

def _gh_json(argv: list, what: str):
    """Run gh and parse its JSON stdout; warning + None on any failure."""
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=GH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn("writeback " + what + ": " + str(exc))
        return None
    if proc.returncode != 0:
        stderr_lines = proc.stderr.decode("utf-8", errors="replace") \
            .strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else "no stderr"
        _warn("writeback " + what + ": exit " + str(proc.returncode)
              + ": " + detail)
        return None
    try:
        return json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _warn("writeback " + what + ": cannot parse gh output")
        return None


def _drain(subcommand: str, owner: str, number, rows_key: str):
    """Page `gh project item-list|field-list` until exhausted (#24 canon).

    Every call carries an explicit `--limit` (never gh's default 30);
    because gh pages internally and returns a full stable prefix plus
    `totalCount` per call, draining = growing the limit until the
    prefix covers totalCount. Returns the drained rows, or None on any
    gh failure (fail-open: the caller warns/falls back to caches).
    """
    what = subcommand + " " + str(number)
    argv = ["gh", "project", subcommand, str(number),
            "--owner", str(owner), "--format", "json"]
    limit = PAGE_SIZE
    while True:
        data = _gh_json(argv + ["--limit", str(limit)], what)
        if not isinstance(data, dict):
            return None
        rows = data.get(rows_key)
        total = data.get("totalCount")
        if not isinstance(rows, list):
            _warn("writeback " + what + ": unexpected gh output shape")
            return None
        if not isinstance(total, int) or len(rows) >= total \
                or len(rows) < limit:
            return rows  # exhausted (totalCount reached or partial page)
        if limit >= LIMIT_CAP:
            _warn("writeback " + what + ": board exceeds " + str(LIMIT_CAP)
                  + " rows — drained partially")
            return rows
        limit = min(total, LIMIT_CAP)  # re-fetch the full prefix, bigger


def gh_item_list(owner: str, number):
    """All board items (drained): raw gh item-list rows, or None."""
    return _drain("item-list", owner, number, "items")


def gh_field_list(owner: str, number):
    """All board fields (drained): raw gh field-list rows, or None."""
    return _drain("field-list", owner, number, "fields")


def resolve_board_items(owner: str, number):
    """item-list rows → {issue number (int): item id}; None on failure.

    Draft items (no content) are skipped; when a PR and an issue share
    a number on the board, the issue wins.
    """
    rows = gh_item_list(owner, number)
    if rows is None:
        return None
    items = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        content = row.get("content")
        if not isinstance(content, dict):
            continue
        issue, item_id = content.get("number"), row.get("id")
        if not isinstance(issue, int) or isinstance(issue, bool) \
                or not isinstance(item_id, str):
            continue
        is_issue = str(content.get("type") or "").lower() == "issue"
        if issue not in items or (is_issue and not items[issue][1]):
            items[issue] = (item_id, is_issue)
    return {issue: pair[0] for issue, pair in items.items()}


def resolve_field_ids(owner: str, number, names) -> dict | None:
    """Configured field names → {name: field id} via field-list.

    Unknown names warn (with the `fields` hint) and stay absent from
    the result — only that field is skipped. None on gh failure.
    """
    rows = gh_field_list(owner, number)
    if rows is None:
        return None
    by_name = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str) \
                and isinstance(row.get("id"), str):
            by_name[row["name"]] = row["id"]
    resolved = {}
    for name in names:
        if name in by_name:
            resolved[name] = by_name[name]
        else:
            _warn("writeback: field " + repr(name) + " not on board "
                  + str(number) + " — skipped (" + FIELDS_HINT + ")")
    return resolved


# --- state.json: the write-back cache ------------------------------------------

def load_state(data_dir) -> dict:
    """data/state.json → dict ({} when missing/corrupt — warning then)."""
    path = os.path.join(os.fspath(data_dir), "state.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        _warn("load_state " + path + ": " + str(exc) + " — starting empty")
        return {}
    return data if isinstance(data, dict) else {}


def save_state(data_dir, state: dict) -> None:
    """Write state.json atomically (tmp + os.replace, spec §Snapshots)."""
    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "state.json")
    tmp = path + ".tmp." + str(os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _project_cache(state: dict, project: str) -> dict:
    """The project's {"items": {…}, "written": {…}} cache, normalized."""
    root = state.get(STATE_KEY)
    if not isinstance(root, dict):
        root = {}
        state[STATE_KEY] = root
    cache = root.get(project)
    if not isinstance(cache, dict):
        cache = {}
        root[project] = cache
    for key in ("items", "written"):
        if not isinstance(cache.get(key), dict):
            cache[key] = {}
    return cache


# --- the write-back stage -------------------------------------------------------

def _item_edit(project_id: str, item_id: str, field_id: str, value) -> bool:
    """One `gh project item-edit` call (one item+field); True on success."""
    argv = ["gh", "project", "item-edit",
            "--id", item_id, "--field-id", field_id,
            "--project-id", project_id, "--number", str(value)]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=GH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn("writeback item-edit: " + str(exc))
        return False
    if proc.returncode != 0:
        stderr_lines = proc.stderr.decode("utf-8", errors="replace") \
            .strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else "no stderr"
        _warn("writeback item-edit " + item_id + " " + field_id
              + ": exit " + str(proc.returncode) + ": " + detail)
        return False
    return True


def _writeback_project(project, spec, snapshots, state) -> None:
    """One project's write-back pass (spec §Board write-back)."""
    write_back = spec.get("write_back") or {}
    if not write_back.get("enabled"):
        return  # kill switch: the whole stage is skipped
    fields = write_back.get("fields") or {}
    if not fields:
        _note("writeback: " + project + ": no fields configured — "
              "nothing to write")
        return
    board = spec.get("board") or {}
    owner = board.get("owner")
    number = board.get("project_number")
    project_id = board.get("project_id")
    if not owner or not number or not project_id:
        _warn("writeback: project " + repr(project)
              + ": incomplete board block — skipped")
        return
    own = [snap for snap in snapshots
           if isinstance(snap, dict) and snap.get("project") == project]
    if not own:
        return  # nothing mapped to this project — no gh calls at all

    field_ids = resolve_field_ids(owner, number, fields.keys())
    if field_ids is None:
        _warn("writeback: " + project
              + ": field-list failed — board write skipped this run")
        return
    fresh = resolve_board_items(owner, number)
    cache = _project_cache(state, project)
    if fresh is None:
        _warn("writeback: " + project
              + ": item-list failed — using cached item ids")
    else:
        cache["items"] = {str(issue): item_id
                          for issue, item_id in fresh.items()}

    for snap in sorted(own, key=lambda s: s.get("issue") or 0):
        issue = snap.get("issue")
        if not isinstance(issue, int) or isinstance(issue, bool):
            continue
        if fresh is not None:
            item_id = fresh.get(issue)
        else:
            item_id = cache["items"].get(str(issue))
        if item_id is None:
            _note("writeback: " + project + "#" + str(issue)
                  + " not on board — skipped")
            continue
        written = cache["written"].setdefault(str(issue), {})
        for name in sorted(fields):
            if name not in field_ids:
                continue  # unknown name — already warned + skipped
            value = resolve_path(snap, fields[name])
            if value is MISSING:
                _warn("writeback: " + project + "#" + str(issue) + ": field "
                      + repr(name) + ": path " + repr(fields[name])
                      + " not in snapshot — skipped")
                continue
            if written.get(name) == value:
                continue  # diff-gate: the written (rounded) value is unchanged
            if _item_edit(project_id, item_id, field_ids[name], value):
                written[name] = value  # cache updates only after success
            else:
                # A failed write invalidates the cached item id — a
                # re-added card gets a new one, re-resolved next run.
                cache["items"].pop(str(issue), None)


def load_snapshots(data_dir) -> list:
    """Read data/issues/*.json → snapshot dicts (bad files warn, skipped)."""
    issues_dir = os.path.join(os.fspath(data_dir), "issues")
    try:
        names = sorted(os.listdir(issues_dir))
    except OSError:
        return []
    snapshots = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(issues_dir, name), "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            _warn("load_snapshots " + name + ": " + str(exc) + " — skipped")
            continue
        if isinstance(snapshot, dict):
            snapshots.append(snapshot)
    return snapshots


def run_writeback(config: dict, data_dir, snapshots=None) -> None:
    """Write every enabled project's snapshot values to its board.

    `snapshots` defaults to the issue files already in data/ (the
    standalone `collect.py writeback` re-push path). The caller is
    expected to hold data/.lock (run_collect and cmd_writeback do).
    Fail-open throughout: warnings, never exceptions, exit code 0.
    """
    if snapshots is None:
        snapshots = load_snapshots(data_dir)
    state = load_state(data_dir)
    projects = config.get("projects") or {}
    for project in sorted(projects):
        spec = projects.get(project)
        if isinstance(spec, dict):
            _writeback_project(project, spec, snapshots, state)
    save_state(data_dir, state)


def run_after_rebuild(config: dict, data_dir, snapshots=None) -> None:
    """Post-rebuild write-back hook (spec §Collection runs, §Board write-back).

    Called by collector.run_collect and the serve bind rebuild, both
    under data/.lock — the same pipeline as the standalone re-push.
    """
    run_writeback(config, data_dir, snapshots)


# --- `collect.py fields`: one-time board field creation -------------------------

def _field_create(owner: str, number, name: str) -> bool:
    """One `gh project field-create … --data-type NUMBER` call."""
    argv = ["gh", "project", "field-create", str(number),
            "--owner", str(owner), "--name", name,
            "--data-type", "NUMBER"]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=GH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn("fields field-create: " + str(exc))
        return False
    if proc.returncode != 0:
        stderr_lines = proc.stderr.decode("utf-8", errors="replace") \
            .strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else "no stderr"
        _warn("fields field-create " + repr(name) + ": exit "
              + str(proc.returncode) + ": " + detail)
        return False
    return True


def run_fields(config: dict) -> int:
    """Create the configured (missing) NUMBER fields on each enabled
    project's board. Idempotent; never renames or modifies existing
    fields, never touches single-select options. An existing name with
    a definitely non-NUMBER type stops loudly (exit 1, zero mutations);
    gh/network failures stay fail-open (warning, exit 0).
    """
    projects = config.get("projects") or {}
    for project in sorted(projects):
        spec = projects.get(project)
        if not isinstance(spec, dict):
            continue
        write_back = spec.get("write_back") or {}
        if not write_back.get("enabled"):
            continue
        names = [name for name in (write_back.get("fields") or {})
                 if isinstance(name, str)]
        if not names:
            _note("fields: " + project + ": no fields configured — "
                  "nothing to create")
            continue
        board = spec.get("board") or {}
        owner, number = board.get("owner"), board.get("project_number")
        if not owner or not number:
            _warn("fields: project " + repr(project)
                  + ": incomplete board block — skipped")
            continue
        rows = gh_field_list(owner, number)
        if rows is None:
            continue  # already warned — fail-open, next project
        existing = {}
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                existing[row["name"]] = row.get("type")
        # Validate FIRST — zero mutations before the all-clear.
        for name in names:
            if name in existing and existing[name] != NUMBER_FIELD_TYPE:
                print("error: fields: project " + repr(project) + ": field "
                      + repr(name) + " already exists with type "
                      + repr(existing[name]) + ", not a NUMBER field — "
                      "refusing to touch the board; rename the board field "
                      "or fix config.json", file=sys.stderr)
                return 1
        missing = [name for name in names if name not in existing]
        if not missing:
            _note("fields: " + project + ": all fields present — "
                  "nothing to create")
            continue
        for name in missing:
            if _field_create(owner, number, name):
                _note("fields: " + project + ": created NUMBER field "
                      + repr(name))
    return 0
