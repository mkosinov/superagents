#!/usr/bin/env python3
"""board_bootstrap.py — roll out (init) or adopt a GH ProjectV2 board.

Reads the declarative board definition (etalon) from docs/board/board-etalon.md
and creates the project, its fields, links the repo, seeds open issues, writes
docs/board/board_config.json. `adopt` compares an existing project with the
etalon and writes the config without mutating the board.

Task 5: the live `init` chain, wired to the verified mutation sequence (gh
2.100.0): create → per-field create-or-sync (the built-in Status CANNOT be
deleted — the API refuses built-ins with "Only custom fields can be
deleted" — so its option list is rewritten IN PLACE on the existing field
id via updateProjectV2Field; verified against the live schema 2026-10-03)
→ link → seed open issues with Status=Backlog → verification read after
every mutation → config write. Mid-run failure prints the partial report
(what exists, per-resource cleanup, adopt recovery).

Usage:
  python3 .zcode/scripts/board_bootstrap.py init --repo <owner/name> --title <t> \
      [--owner <login>] [--etalon <path>] [--out <path>] [--dry-run]
  python3 .zcode/scripts/board_bootstrap.py adopt <project-number> --repo <owner/name> \
      [--owner <login>] [--etalon <path>] [--out <path>] [--force] [--dry-run]

Identical copies ship in BOTH harness folders — .zcode/scripts/ (host)
and .opencode/scripts/ (container); when editing, change both (or edit
one and copy over). Same convention as gh_board.py.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Repo root anchored to the script's own path (both twins resolve the same
# root: .zcode/scripts/x.py and .opencode/scripts/x.py are two levels deep).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ETALON = REPO_ROOT / "docs" / "board" / "board-etalon.md"
DEFAULT_CONFIG = REPO_ROOT / "docs" / "board" / "board_config.json"

BLOCK_RE = re.compile(r"```board-etalon\n(.*?)\n```", re.S)

# Single-select type names compare_fields accepts: the gh CLI reports
# "ProjectV2SingleSelectField" (live, pinned 2026-09-26); "SINGLE_SELECT" is
# the historical fixture spelling. Built-in metadata columns (Title/Labels/
# Assignees report "ProjectV2Field") are excluded by this set.
SELECT_TYPES = {"SINGLE_SELECT", "ProjectV2SingleSelectField"}

# Explicit caps on every list read — no 30-row gh defaults.
PROJECT_LIST_LIMIT = 1000
FIELD_LIST_LIMIT = 200
ITEM_LIST_LIMIT = 1000
ISSUE_LIST_LIMIT = 10000

# The seed status written onto every newly added item (option id read at
# run time from field-list — rollout-log quirk: it is project-specific).
SEED_STATUS_OPTION = "Backlog"

INTROSPECTION_QUERY = 'query{__type(name:"ProjectV2"){fields{name}}}'


class EtalonError(Exception):
    """Broken etalon: carries the reason text only (path named by the caller)."""


@dataclass(frozen=True)
class Etalon:
    fields: list[dict]      # [{"name","type","options":[str,...]}] in etalon order
    host_budgets: dict[str, int]


def parse_etalon(text: str) -> Etalon:
    """Extract the fenced block (exactly one) and validate it.

    Raises EtalonError(reason) on: multiple or zero blocks, malformed JSON,
    wrong version, empty fields, non-single_select types, empty/duplicate
    option names, host_budgets values below 1.
    """
    blocks = BLOCK_RE.findall(text)
    if not blocks:
        raise EtalonError("no board-etalon block found in the etalon doc")
    if len(blocks) > 1:
        raise EtalonError(f"expected exactly one board-etalon block, found {len(blocks)}")
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as e:
        raise EtalonError(f"malformed JSON in board-etalon block: {e}") from e
    return validate_etalon(data)


def validate_etalon(data: dict) -> Etalon:
    """Validate the parsed block dict; EtalonError on any violation."""
    if not isinstance(data, dict):
        raise EtalonError(f"board-etalon block must be a JSON object, got {type(data).__name__}")
    if data.get("version") != 1:
        raise EtalonError(f"unsupported etalon version {data.get('version')!r} (expected 1)")
    fields = data.get("fields")
    if not isinstance(fields, list) or not fields:
        raise EtalonError("etalon has no fields (fields must be a non-empty list)")
    for f in fields:
        if not isinstance(f, dict) or "name" not in f:
            raise EtalonError(f"malformed field entry: {f!r}")
        name = f.get("name")
        ftype = f.get("type")
        if ftype != "single_select":
            raise EtalonError(
                f'field "{name}": unsupported type {ftype!r} '
                f"(only single_select fields are supported)")
        options = f.get("options")
        if not isinstance(options, list) or not options:
            raise EtalonError(f'field "{name}": empty options (need a non-empty list)')
        seen = set()
        for opt in options:
            if not isinstance(opt, str) or not opt:
                raise EtalonError(f'field "{name}": option names must be non-empty strings')
            if opt in seen:
                raise EtalonError(f'field "{name}": duplicate option "{opt}"')
            seen.add(opt)
    budgets = data.get("host_budgets")
    if not isinstance(budgets, dict):
        raise EtalonError("host_budgets must be an object")
    for host, budget in budgets.items():
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
            raise EtalonError(f'host_budgets["{host}"] = {budget!r}: budgets must be ints >= 1')
    return Etalon(fields=fields, host_budgets=budgets)


def load_etalon(path_arg: str | None) -> tuple[Etalon, Path]:
    """Resolve the etalon path (path_arg, else the repo-root default) and parse it.

    Missing file, no block, bad JSON -> EtalonError naming the path and cause.
    """
    path = Path(path_arg) if path_arg else DEFAULT_ETALON
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise EtalonError(f"etalon file not found or unreadable: {path} ({e.strerror or e})") from e
    try:
        etalon = parse_etalon(text)
    except EtalonError as e:
        raise EtalonError(f"{path}: {e}") from e
    return etalon, path


def effective_owner(args) -> str:
    """Project owner login: explicit --owner, else the --repo owner (never @me)."""
    return args.owner or args.repo.split("/")[0]


def effective_config_path(args) -> Path:
    """Where the config would be written: --out, else the repo-root canonical path."""
    return Path(args.out) if args.out else DEFAULT_CONFIG


def display_path(path: Path) -> Path:
    """Plan-line rendering: repo-relative inside the repo root, as given outside.

    The dry-run etalon/config lines are a stable CI-grep contract
    ("docs/board/board-etalon.md") — relative output survives different
    checkouts (CI runner vs local), absolute output does not. Explicit
    --etalon/--out targets outside the repo keep their given form.
    """
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def gh(argv: list[str]):
    """Thin gh runner (argv list, never shell=True) — mirrors gh_board.py."""
    return subprocess.run(["gh", *argv], capture_output=True, text=True)


def gh_json(argv: list[str]) -> dict:
    """gh ... --format json, stdout parsed; exit on failure (gh_board style)."""
    r = gh(argv)
    if r.returncode != 0:
        sys.exit(f"gh error ({' '.join(r.args[1:])}): {r.stderr.strip()}")
    return json.loads(r.stdout)


def gql(query: str) -> dict:
    """gh api graphql -f query=... (argv list) — the gh_board.py read pattern."""
    r = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gh api error: {r.stderr.strip()}")
    data = json.loads(r.stdout)
    if "errors" in data:
        sys.exit(f"graphql errors: {data['errors']}")
    return data["data"]


@dataclass(frozen=True)
class Guard:
    """One guard verdict: ok | warn | refuse | skipped, plus the report text."""
    status: str
    message: str
    project: dict | None = None  # payload for callers (adopt: the project row)


def guard_config_exists(path: Path, force: bool = False) -> Guard:
    """Local damage-prevention guard: refuse when the effective config exists.

    Refusal names the path and the exact damage prevented; --force (adopt
    only) flips it to a deliberate-overwrite ok.
    """
    if not path.exists():
        return Guard("ok", f"no config at {path}: safe to write")
    if force:
        return Guard("ok", f"config exists at {path}; --force: deliberate overwrite")
    return Guard(
        "refuse",
        f"config already exists at {path}: refusing — a second run creates a "
        f"duplicate project, re-seeds the issues as duplicate cards, and "
        f"overwrites the config; the previously rolled-out board loses its "
        f"config and goes unwatched. Use adopt, or --force to overwrite "
        f"deliberately (adopt only).")


def find_repo_connection(schema: dict) -> str | None:
    """Pick the ProjectV2 repository-connection field name from introspection.

    Prefers the documented `linkedRepositories`; accepts `repositories`
    (present in the live schema, pinned 2026-09-26). Neither → None (the
    documented downgrade: the init repo guard degrades to config + title
    checks).
    """
    def names(d):
        try:
            return {f["name"] for f in d["__type"]["fields"]}
        except (KeyError, TypeError):
            return set()
    found = names(schema)
    if "linkedRepositories" in found:
        return "linkedRepositories"
    if "repositories" in found:
        return "repositories"
    return None


def _repo_in_nodes(nodes: list, repo: str) -> bool:
    """owner/name match against repository-connection nodes."""
    owner, _, name = repo.partition("/")
    for n in nodes or []:
        try:
            if n["owner"]["login"] == owner and n["name"] == name:
                return True
        except (KeyError, TypeError):
            continue
    return False


_UNSET = object()  # sentinel: "connection= not passed — introspect inside"


def guard_repo_has_project(owner: str, repo: str, *, gh_json=gh_json, gql=gql,
                           limit: int = PROJECT_LIST_LIMIT,
                           projects: list | None = None,
                           connection=_UNSET) -> Guard:
    """init guard: refuse if ANY open project of the owner links the repo.

    Introspects once to find the repository connection, enumerates the owner's
    open projects (explicit --limit; pass `projects=` to reuse a list already
    read for another guard — cmd_init lists projects once; pass `connection=`
    to likewise reuse a schema read), reads each project's linked repos with
    one node query. No connection in the schema → documented downgrade
    (skipped, reported); the guard degrades to config + title checks.
    """
    if connection is _UNSET:
        connection = find_repo_connection(gql(INTROSPECTION_QUERY))
    if connection is None:
        return Guard("skipped",
                     "skipped: no repository connection in schema "
                     "(guard degraded to the config check + title-collision warning)")
    if projects is None:
        projects = gh_json(["project", "list", "--owner", owner,
                            "--format", "json", "--limit", str(limit)])["projects"]
    if len(projects) >= limit:
        return Guard("refuse",
                     f"owner {owner} has {len(projects)} projects (>= --limit "
                     f"{limit}): cannot verify {repo} is unlinked; raise the limit")
    for p in projects:
        if p.get("closed"):
            continue
        q = ('query{node(id:"%s"){...on ProjectV2{number title %s'
             '(first:100){nodes{owner{login} name}}}}}' % (p["id"], connection))
        nodes = gql(q)["node"][connection]["nodes"]
        if _repo_in_nodes(nodes, repo):
            return Guard(
                "refuse",
                f'refusing: repo {repo} is already linked to open project '
                f'#{p["number"]} "{p["title"]}" ({p["id"]}) — init would create '
                f"a duplicate project and re-seed the issues as duplicate cards; "
                f"adopt that project instead")
    return Guard("ok", f"no open project of {owner} links {repo}")


def verify_project_links_repo(project_number: int, owner: str, repo: str, *,
                              gh_json=gh_json, gql=gql, projects=None) -> Guard:
    """adopt guard (inverse contract, deliberately not shared with init's):

    refuse unless project #N — the one being adopted — is linked to --repo.
    Carries the project row (id, number, title) as payload for the config.
    """
    if projects is None:
        projects = gh_json(["project", "list", "--owner", owner,
                            "--format", "json", "--limit",
                            str(PROJECT_LIST_LIMIT)])["projects"]
    row = next((p for p in projects if p.get("number") == project_number), None)
    if row is None:
        return Guard("refuse",
                     f"project #{project_number} of {owner} not found among "
                     f"{len(projects)} listed projects")
    connection = find_repo_connection(gql(INTROSPECTION_QUERY))
    if connection is None:
        return Guard("refuse",
                     f"cannot verify project #{project_number} links {repo}: "
                     f"no repository connection in schema (introspection)")
    q = ('query{node(id:"%s"){...on ProjectV2{number title %s'
         '(first:100){nodes{owner{login} name}}}}}' % (row["id"], connection))
    nodes = gql(q)["node"][connection]["nodes"]
    if not _repo_in_nodes(nodes, repo):
        linked = ", ".join(f'{n["owner"]["login"]}/{n["name"]}' for n in nodes or []) \
                 or "nothing"
        return Guard(
            "refuse",
            f"project #{project_number} \"{row['title']}\" is not linked to {repo} "
            f"(linked: {linked}); adopt --repo must name a repo this project links")
    return Guard("ok", f"project #{project_number} \"{row['title']}\" links {repo}",
                 project=row)


def guard_title_collision(projects: list, title: str) -> Guard:
    """Equal title among the owner's open projects: warn only (GitHub permits
    duplicates), naming both the existing project and the requested title."""
    for p in projects:
        if not p.get("closed") and p.get("title") == title:
            return Guard(
                "warn",
                f'title collision: open project #{p["number"]} "{p["title"]}" '
                f'already has the title "{title}" (GitHub permits duplicates; '
                f"proceeding)")
    return Guard("ok", f'no open project already titled "{title}"')


def format_diff(diff: dict) -> str:
    """Human rendering of a compare_fields verdict (refusals and warnings)."""
    parts = []
    if diff["missing_fields"]:
        parts.append("missing fields: " + ", ".join(diff["missing_fields"]))
    if diff["missing_options"]:
        for name, opts in diff["missing_options"].items():
            parts.append(f"missing options in {name}: " + ", ".join(opts))
    if diff["extra_fields"]:
        parts.append("extra fields (warning): " + ", ".join(diff["extra_fields"]))
    if diff["extra_options"]:
        for name, opts in diff["extra_options"].items():
            parts.append(f"extra options in {name} (warning): " + ", ".join(opts))
    return "; ".join(parts)


def plan_guards(mode: str, args, etalon_path: Path) -> list[str]:
    """Dry-run guard verdicts as report-only plan lines.

    Zero network calls: local guards render real verdicts; network guards say
    "read at run time". A would-be refusal never changes the exit code.
    """
    out = effective_config_path(args)
    cfg = guard_config_exists(out, force=getattr(args, "force", False))
    if mode == "init":
        repo_guard = (f"guard: repo {args.repo} already linked to an open project: "
                      f"read at run time")
        title_guard = (f'guard: title collision with an open project of '
                       f"{effective_owner(args)}: read at run time")
        return [f"guard: {cfg.status}: {cfg.message} (report-only)", repo_guard,
                title_guard]
    return [f"guard: {cfg.status}: {cfg.message} (report-only)"]


def render_plan(mode: str, args, etalon: Etalon, etalon_path: Path,
                guard_verdicts: list[str]) -> str:
    """Offline text tree of what WOULD happen. Zero network calls.

    init: etalon → project create → per-field create-or-in-place-sync → repo
    link → seeding → config path. adopt: the planned comparison instead of
    the create/sync/link lines. Guard verdicts appended report-only, one
    line per guard.
    """
    lines = [f"etalon: {display_path(etalon_path)}"]
    if mode == "init":
        lines.append(f'project: create "{args.title}" (owner {effective_owner(args)})')
        lines.append("fields: created when absent; existing same-name fields get "
                     "their options synced in place (built-in fields cannot "
                     "be deleted)")
        for f in etalon.fields:
            lines.append(f'{f["name"]}: ' + " | ".join(f["options"]))
        lines.append(f"link: {args.repo}")
        lines.append("seed: open issues would be listed live (--dry-run: no network)")
    else:
        lines.append(f"compare: read fields of project #{args.project} "
                     f"and match by exact name")
        lines.append("refuse: missing field or option; "
                     "warn: extra field or option (drift contract)")
        lines.append(f"verify: project #{args.project} is linked to {args.repo}")
    lines.append(f"config: {display_path(effective_config_path(args))}")
    lines.extend(guard_verdicts)
    return "\n".join(lines)


def compare_fields(etalon: Etalon, live: list[dict]) -> dict:
    """Diff an existing board (gh project field-list JSON entries) against the etalon.

    live entries are filtered to single-select types first (SELECT_TYPES —
    "SINGLE_SELECT" historically, "ProjectV2SingleSelectField" live) — built-in
    metadata columns (Title/Labels/Assignees/...) are not single-selects and
    are ignored by that filter. Matching is by exact field/option name (no
    prefix tolerance: a rename like `In Design (G1a)` vs `In Design` counts
    as BOTH missing and extra). Returns {"missing_fields", "missing_options",
    "extra_fields", "extra_options"}; missing lists keep etalon order, extra
    lists live order.
    """
    etalon_names = {f["name"] for f in etalon.fields}
    live_selects = {e["name"]: e for e in live if e.get("type") in SELECT_TYPES}
    missing_fields = [f["name"] for f in etalon.fields
                      if f["name"] not in live_selects]
    extra_fields = [e["name"] for e in live
                    if e.get("type") in SELECT_TYPES and e["name"] not in etalon_names]
    missing_options: dict[str, list[str]] = {}
    extra_options: dict[str, list[str]] = {}
    for f in etalon.fields:
        entry = live_selects.get(f["name"])
        if entry is None:
            continue
        live_opts = [o["name"] for o in entry.get("options") or []]
        live_set = set(live_opts)
        etalon_set = set(f["options"])
        if missing := [o for o in f["options"] if o not in live_set]:
            missing_options[f["name"]] = missing
        if extra := [o for o in live_opts if o not in etalon_set]:
            extra_options[f["name"]] = extra
    return {"missing_fields": missing_fields, "missing_options": missing_options,
            "extra_fields": extra_fields, "extra_options": extra_options}


def ok_to_adopt(diff: dict) -> bool:
    """Drift contract verdict: missing field/option -> refuse; extra -> warn-ok."""
    return not diff["missing_fields"] and not diff["missing_options"]


def build_config(project_id: str, project_number: int, owner: str, repo: str,
                 field_ids: dict[str, str], host_budgets: dict[str, int]) -> dict:
    """Assemble board_config.json (format v1) as a plain dict.

    Option ids are deliberately absent: they are project-specific and must be
    read from field-list at run time (rollout-log quirk). host_budgets are
    copied from the etalon verbatim.
    """
    return {
        "version": 1,
        "project_id": project_id,
        "project_number": project_number,
        "owner": owner,
        "repo": repo,
        "fields": dict(field_ids),
        "host_budgets": dict(host_budgets),
    }


def write_config(path: Path, config: dict) -> None:
    """Write the config to the effective path (caller resolves --out/default), mkdir parents.

    Conventions mirror subagent-audit.py: utf-8, ensure_ascii=False, indent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def validate_repo(repo: str) -> None:
    """--repo must be owner/name; refuse pre-network on a malformed value."""
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        sys.exit(f"error: --repo must be owner/name, got {repo!r}")


def cmd_adopt(args, etalon: Etalon, *, gh=gh, gh_json=gh_json, gql=gql) -> int:
    """Live adopt: verify link → read fields → compare → write config.

    Mandated order; adopt NEVER mutates the project (reads only). Refusals
    exit with the full reason; extras warn and proceed (drift contract).
    """
    validate_repo(args.repo)
    owner = effective_owner(args)
    out = effective_config_path(args)

    r = gh(["auth", "status"])
    if r.returncode != 0:
        sys.exit(f"error: gh auth status failed ({r.stderr.strip()}); "
                 f"authenticate first")

    link = verify_project_links_repo(args.project, owner, args.repo,
                                     gh_json=gh_json, gql=gql)
    if link.status != "ok" or not link.project:
        sys.exit(f"error: adopt #{args.project}: {link.message}")

    fields = read_fields(args.project, owner, gh_json=gh_json)

    diff = compare_fields(etalon, fields)
    if not ok_to_adopt(diff):
        sys.exit(f"error: project #{args.project} does not match the etalon "
                 f"(missing = refuse, extra = warn): {format_diff(diff)}")
    if diff["extra_fields"] or diff["extra_options"]:
        print(f"warning: drift vs etalon (extras allowed, etalon = intent, "
              f"web UI = fact): {format_diff(diff)}")

    cfg = guard_config_exists(out, force=args.force)
    if cfg.status == "refuse":
        sys.exit(f"error: {cfg.message}")

    field_ids = {f["name"]: f["id"] for f in fields
                 if f.get("type") in SELECT_TYPES and f["name"] in
                 {e["name"] for e in etalon.fields}}
    write_config(out, build_config(project_id=link.project["id"],
                                   project_number=args.project, owner=owner,
                                   repo=args.repo.split("/")[1],
                                   field_ids=field_ids,
                                   host_budgets=etalon.host_budgets))
    print(f"adopted #{args.project} \"{link.project['title']}\" -> {out}")
    return 0


def find_status_field(fields: list[dict]) -> dict | None:
    """The project's single-select "Status" entry (None when absent).

    On a fresh project this is the built-in field every project ships with
    (options Todo / In Progress / Done); after init it is the etalon Status.
    Built-in metadata columns (Title/Labels/...) are excluded by the type
    filter.
    """
    return next((f for f in fields if f.get("name") == "Status"
                 and f.get("type") in SELECT_TYPES), None)


# Legal option colors, live enum order (ProjectV2SingleSelectFieldOptionColor,
# introspected 2026-10-03): cycled per option position, etalon order.
OPTION_COLORS = ["GRAY", "BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE"]


def sync_field_options(field: dict, options: list[str], *, gql=gql) -> dict:
    """Rewrite a single-select field's option list IN PLACE (live-verified
    schema, 2026-10-03):

      mutation{updateProjectV2Field(input:{fieldId, singleSelectOptions:
      [{name, color, description}, ...]}){clientMutationId}}

    - fieldId is the EXISTING field's id. Built-in fields cannot be deleted
      ("Only custom fields can be deleted") — including every fresh
      project's Status (Todo / In Progress / Done) — so init converges the
      built-in Status onto the etalon options right on that field.
    - singleSelectOptions is the FULL replacement list. An option whose id
      is omitted gets a fresh id; name+color+description are all required
      by ProjectV2SingleSelectFieldOptionInput (color from OPTION_COLORS).
    - The response projection is the payload scalar clientMutationId. The
      payload's other field, projectV2Field, is a UNION
      (ProjectV2FieldConfiguration) — direct subselections are invalid
      GraphQL ("Selections can't be made directly on unions"), which
      aborted the whole mutation in both earlier live attempts
      ({projectV2{id}} does not exist; {projectV2Field{id}} needs inline
      fragments). The return value is ignored either way: success is
      verified by the field-list read-back, as with every gh mutation.

    Card-value safety: the only value init ever stamps is Status=Backlog
    (SEED_STATUS_OPTION), and every etalon Status list contains Backlog, so
    a replacement never destroys a seeded value. Nothing else seeds values.
    """
    opt_inputs = ", ".join(
        f'{{name:"{o}", color:{OPTION_COLORS[i % len(OPTION_COLORS)]}, description:""}}'
        for i, o in enumerate(options))
    q = (f'mutation{{updateProjectV2Field(input:{{fieldId:"{field["id"]}",'
         f"singleSelectOptions:[{opt_inputs}]}}){{clientMutationId}}}}")
    return gql(q)


def seed_status_ids(fields: list[dict],
                    option: str = SEED_STATUS_OPTION) -> tuple[str, str]:
    """(field_id, option_id) for the seed status, from a field-list payload.

    Rollout-log quirk: ids are project-specific and must never be hardcoded —
    this is the run-time read.
    """
    status = find_status_field(fields)
    if status is None:
        sys.exit('error: created project has no single-select field "Status"')
    for o in status.get("options") or []:
        if o.get("name") == option:
            return status["id"], o["id"]
    sys.exit(f'error: Status field has no option "{option}" to seed items with')


def read_fields(project_number: int, owner: str, *, gh_json=gh_json) -> list[dict]:
    """field-list with the explicit cap; refuses when the cap is hit."""
    listed = gh_json(["project", "field-list", str(project_number),
                      "--owner", owner, "--format", "json",
                      "--limit", str(FIELD_LIST_LIMIT)])
    fields = listed["fields"]
    if len(fields) >= FIELD_LIST_LIMIT:
        sys.exit(f"error: project #{project_number} has {len(fields)} fields "
                 f"(>= --limit {FIELD_LIST_LIMIT}): cannot safely verify; "
                 f"raise the cap in FIELD_LIST_LIMIT")
    return fields


# Settle retries for item read-backs: the Projects API is eventually
# consistent — an immediate item-list after item-add / item-edit can serve
# a stale snapshot missing the fresh change (live-verified 2026-10-03: a
# just-added item was absent from the first read and present ~2s later).
ITEM_SETTLE_ATTEMPTS = 6
ITEM_SETTLE_DELAY = 1.0  # seconds between reads


def settle_item_row(project_number: int, owner: str, item_id: str, *,
                    want_status: str | None = None, gh_json=gh_json,
                    attempts: int | None = None,
                    delay: float | None = None) -> tuple[list, dict | None]:
    """Read item-list until item_id appears (with status want_status, when
    given) or the attempts run out — the settle-retry for eventual
    consistency. Returns (final_items, row-or-None); row None after the
    last attempt is the settled mismatch verdict. Raises SystemExit when a
    read hits the item cap (same refusal as elsewhere)."""
    attempts = ITEM_SETTLE_ATTEMPTS if attempts is None else attempts
    delay = ITEM_SETTLE_DELAY if delay is None else delay
    def one_read() -> list:
        items = gh_json(["project", "item-list", str(project_number),
                         "--owner", owner, "--format", "json", "--limit",
                         str(ITEM_LIST_LIMIT)])["items"]
        if len(items) >= ITEM_LIST_LIMIT:
            raise SystemExit(f"error: project #{project_number} already has "
                             f"{len(items)} items (>= --limit "
                             f"{ITEM_LIST_LIMIT}): cannot verify seeding; "
                             f"raise the cap in ITEM_LIST_LIMIT")
        return items

    def verdict(items: list) -> dict | None:
        row = next((i for i in items if i.get("id") == item_id), None)
        if row is None:
            return None
        if want_status is not None and row.get("status") != want_status:
            return None
        return row

    items = one_read()
    for _ in range(attempts - 1):
        if verdict(items) is not None:
            return items, verdict(items)
        time.sleep(delay)
        items = one_read()
    return items, verdict(items)


def cmd_init(args, etalon: Etalon, *, gh=gh, gh_json=gh_json, gql=gql) -> int:
    """Live init: the verified mutation sequence with read-back verification.

    Etalon was parsed strictly first (main). Order: auth pre-flight → guards
    (config / repo-linked / title-collision warn) → create → per etalon field
    create-or-sync (absent fields are created; an existing same-name field —
    the built-in Status, or a prior partial run's — gets its option list
    synced in place, since built-ins cannot be deleted) → link → seed open
    issues with Status=Backlog → write config. EVERY mutation is followed by
    a verification read; mismatch → stop and report (gh is silent on success —
    rollout-log quirk). Any failure prints the partial report with the manual
    cleanup + adopt recovery routes; nothing is auto-deleted.
    """
    owner = effective_owner(args)
    validate_repo(args.repo)
    repo = args.repo
    out = effective_config_path(args)
    state = CreatedState()

    def fail(cause: str) -> int:
        print(format_partial_failure(state.as_dict(owner, repo), cause))
        return 1

    # 1. auth pre-flight (etalon already parsed, before any network use).
    r = gh(["auth", "status"])
    if r.returncode != 0:
        sys.exit(f"error: gh auth status failed ({r.stderr.strip()}); "
                 f"authenticate first")

    # 2. guards — one project-list read feeds the repo + title guards alike.
    cfg = guard_config_exists(out)
    if cfg.status == "refuse":
        sys.exit(f"error: {cfg.message}")
    projects = gh_json(["project", "list", "--owner", owner, "--format", "json",
                        "--limit", str(PROJECT_LIST_LIMIT)])["projects"]
    if len(projects) >= PROJECT_LIST_LIMIT:
        sys.exit(f"error: owner {owner} has {len(projects)} projects "
                 f"(>= --limit {PROJECT_LIST_LIMIT}): cannot verify {repo} "
                 f"is unlinked; raise the cap in PROJECT_LIST_LIMIT")
    connection = find_repo_connection(gql(INTROSPECTION_QUERY))
    repo_guard = guard_repo_has_project(owner, repo, gh_json=gh_json, gql=gql,
                                        projects=projects,
                                        connection=connection)
    if repo_guard.status == "refuse":
        sys.exit(f"error: {repo_guard.message}")
    if repo_guard.status == "skipped":
        print(f"warning: {repo_guard.message}")
    title_guard = guard_title_collision(projects, args.title)
    if title_guard.status == "warn":
        print(f"warning: {title_guard.message}")

    # 3. create the project (explicit login, never @me).
    try:
        state.project = gh_json(["project", "create", "--owner", owner,
                                 "--title", args.title, "--format", "json"])
    except SystemExit as e:
        return fail(str(e))
    number = state.project["number"]

    try:
        # 4+5. per etalon field, in etalon order: create when absent; when a
        #      same-name single-select already exists (a fresh project's
        #      built-in Status, or a prior partial run's field), converge its
        #      option list IN PLACE — built-in fields cannot be deleted
        #      ("Only custom fields can be deleted"), and an idempotent
        #      re-run must not touch a field that already matches. Every
        #      mutation is verified by a read-back.
        fields = read_fields(number, owner, gh_json=gh_json)
        if find_status_field(fields) is not None and \
                not any(f["name"] == "Status" for f in etalon.fields):
            print("warning: the project's built-in Status field cannot be "
                  "deleted (the API refuses built-in fields) and the etalon "
                  "defines no Status field; it remains as an extra field")
        for fdef in etalon.fields:
            entry = next((f for f in fields if f["name"] == fdef["name"]
                          and f.get("type") in SELECT_TYPES), None)
            if entry is None:
                gh_json(["project", "field-create", str(number), "--owner", owner,
                         "--name", fdef["name"], "--data-type", "SINGLE_SELECT",
                         "--single-select-options", ",".join(fdef["options"]),
                         "--format", "json"])
                fields = read_fields(number, owner, gh_json=gh_json)
                entry = next((f for f in fields if f["name"] == fdef["name"]
                              and f.get("type") in SELECT_TYPES), None)
                if entry is None:
                    return fail(f'field-create of "{fdef["name"]}" reported '
                                f"success but the field is missing from the "
                                f"read-back (verification mismatch)")
            elif [o["name"] for o in entry.get("options") or []] != fdef["options"]:
                sync_field_options(entry, fdef["options"], gql=gql)
                fields = read_fields(number, owner, gh_json=gh_json)
                entry = next((f for f in fields if f["name"] == fdef["name"]
                              and f.get("type") in SELECT_TYPES), None)
                if entry is None:
                    return fail(f'option sync of "{fdef["name"]}" reported '
                                f"success but the field is missing from the "
                                f"read-back (verification mismatch)")
            diff = compare_fields(
                Etalon(fields=[fdef], host_budgets={}), fields)
            if diff["missing_options"].get(fdef["name"]):
                return fail(f'field "{fdef["name"]}" is missing options after '
                            f"sync: {diff['missing_options'][fdef['name']]} "
                            f"(verification mismatch)")
            state.fields.append((fdef["name"], entry["id"]))
        final_check = compare_fields(etalon, fields)
        if not ok_to_adopt(final_check):
            return fail("created field set does not match the etalon after "
                        f"creation (verification mismatch): {format_diff(final_check)}")

        # 6. link the repo; `project link` is a silent-success mutation (rc
        #    only, no stdout — its help lists no --format flag), so it is a
        #    plain rc-checked gh call, verified by the node read below
        #    (connection introspected once, before the guards — reused).
        r = gh(["project", "link", str(number), "--owner", owner,
                "--repo", repo])
        if r.returncode != 0:
            return fail(f"gh project link failed: "
                        f"{r.stderr.strip() or 'no stderr'}")
        if connection:
            q = ('query{node(id:"%s"){...on ProjectV2{number title %s'
                 '(first:100){nodes{owner{login} name}}}}}'
                 % (state.project["id"], connection))
            nodes = gql(q)["node"][connection]["nodes"]
            if not _repo_in_nodes(nodes, repo):
                return fail(f"project link reported success but the read-back "
                            f"does not show {repo} among the linked "
                            f"repositories (verification mismatch)")
        else:
            print("warning: cannot verify the repo link: no repository "
                  "connection in schema (introspection) — documented "
                  "downgrade, gh's exit code is all we have")

        # 7. seed open issues: ONE capped list read, then add + edit + verify
        #    per issue (all ids read at run time — never hardcoded). The
        #    read-backs settle-retry: the Projects API is eventually
        #    consistent and a fresh add/edit can be missing from an
        #    immediate item-list (live-verified 2026-10-03).
        issues = gh_json(["issue", "list", "--repo", repo, "--state", "open",
                          "--limit", str(ISSUE_LIST_LIMIT), "--json", "number,url"])
        if len(issues) >= ISSUE_LIST_LIMIT:
            return fail(f"repo {repo} has {len(issues)} open issues "
                        f"(>= --limit {ISSUE_LIST_LIMIT}): refusing to seed a "
                        f"truncated board; raise the cap in ISSUE_LIST_LIMIT "
                        f"and re-run (after manual cleanup or adopt recovery)")
        status_field_id, backlog_id = seed_status_ids(fields)
        for issue in issues:
            added = gh_json(["project", "item-add", str(number), "--owner", owner,
                             "--url", issue["url"], "--format", "json"])
            item_id = added["id"]
            _, row = settle_item_row(number, owner, item_id, gh_json=gh_json)
            if row is None:
                return fail(f'item-add of {issue["url"]} reported success but '
                            f"the item never appeared in the read-back "
                            f"(settled after {ITEM_SETTLE_ATTEMPTS} reads "
                            f"{ITEM_SETTLE_DELAY:.0f}s apart — verification "
                            f"mismatch)")
            # `project item-edit` is another silent-success mutation (rc
            # only, no stdout — its help lists no --format flag): plain
            # rc-checked gh call, verified by the settled read below.
            r = gh(["project", "item-edit", "--project-id", state.project["id"],
                    "--id", item_id, "--field-id", status_field_id,
                    "--single-select-option-id", backlog_id])
            if r.returncode != 0:
                return fail(f"gh project item-edit of {issue['url']} failed: "
                            f"{r.stderr.strip() or 'no stderr'}")
            _, row = settle_item_row(number, owner, item_id,
                                     want_status=SEED_STATUS_OPTION,
                                     gh_json=gh_json)
            if row is None:
                return fail(f'Status edit of item {item_id} ({issue["url"]}) '
                            f"did not settle to {SEED_STATUS_OPTION} "
                            f"(after {ITEM_SETTLE_ATTEMPTS} reads "
                            f"{ITEM_SETTLE_DELAY:.0f}s apart — verification "
                            f"mismatch)")
            state.items.append((issue["number"], issue["url"], item_id))
    except SystemExit as e:
        return fail(str(e))

    # 8. write the config (ids read back live; budgets verbatim from etalon).
    field_ids = {name: fid for name, fid in state.fields}
    write_config(out, build_config(project_id=state.project["id"],
                                   project_number=number, owner=owner,
                                   repo=repo.split("/")[1], field_ids=field_ids,
                                   host_budgets=etalon.host_budgets))
    print(f'init #{number} "{args.title}" ({state.project["id"]}) '
          f"-> {out}")
    return 0


def format_partial_failure(created: dict, cause: str) -> str:
    """Render the mid-run failure report for a partial init.

    `created` is a CreatedState.as_dict(): {"project": row|None, "owner",
    "repo", "fields": [(name, id)], "items": [(number, url, item_id)]}.
    The report names every resource that exists, the per-resource cleanup
    route (items and fields from the project's web board page; the project
    itself from its web Settings — no automatic deletion), and the adopt
    recovery route (`adopt <number> --repo ...` refuses with the difference
    list until the board matches the etalon, then writes the config).
    """
    lines = ["partial init FAILED — no automatic deletion (the API has no "
             "transactions; auto-deleting risks destroying pre-existing "
             "resources). What was created:"]
    p = created.get("project")
    if p:
        lines.append(f'- project #{p["number"]} "{p["title"]}" ({p["id"]})')
    else:
        lines.append("- nothing (the failure happened before the project "
                     "was created)")
    if created.get("fields"):
        names = ", ".join(f'{n} ({fid})' for n, fid in created["fields"])
        lines.append(f"- fields created: {names}")
    if created.get("items"):
        items = ", ".join(f'#{num} {url} ({iid})' for num, url, iid
                          in created["items"])
        lines.append(f"- items added: {items}")
    lines.append(f"failure: {cause}")
    if p:
        lines.append(
            "manual cleanup (web): remove the items and the fields from the "
            "project's board page; delete the project from its Settings page "
            f'(or `gh project delete {p["number"]} --owner {created["owner"]}` '
            "where the local gh has it — gh 2.100 does, older releases do "
            "not). This script never deletes anything automatically")
        lines.append(
            f'or recover: board_bootstrap.py adopt {p["number"]} '
            f'--repo {created["owner"]}/{created["repo"].split("/")[-1]} '
            f'--owner {created["owner"]} — adopt refuses with the difference '
            "list until the board matches the etalon, then writes the config "
            "and the rollout continues by hand")
    return "\n".join(lines)


@dataclass
class CreatedState:
    """What the current init run has created so far (the repair input)."""

    project: dict | None = None
    fields: list = field(default_factory=list)  # [(name, field_id)] creation order
    items: list = field(default_factory=list)   # [(number, url, item_id)] add order

    def as_dict(self, owner: str, repo: str) -> dict:
        return {"project": self.project, "owner": owner, "repo": repo,
                "fields": list(self.fields), "items": list(self.items)}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="board_bootstrap.py",
        description="Roll out (init) or adopt a GH ProjectV2 board from the etalon doc.")
    sub = ap.add_subparsers(dest="mode", required=True)

    p_init = sub.add_parser("init", help="create a new board from the etalon")
    p_init.add_argument("--repo", required=True, help="owner/name of the repo to link")
    p_init.add_argument("--title", required=True, help="project title")
    p_init.add_argument("--owner", help="project owner login (default: --repo owner; never @me)")
    p_init.add_argument("--etalon", help=f"etalon doc path (default: {DEFAULT_ETALON})")
    p_init.add_argument("--out", help=f"config output path (default: {DEFAULT_CONFIG})")
    p_init.add_argument("--dry-run", action="store_true",
                        help="print the plan tree; zero network calls")

    p_adopt = sub.add_parser("adopt", help="adopt an existing board; never mutates it")
    p_adopt.add_argument("project", type=int, help="project number to adopt")
    p_adopt.add_argument("--repo", required=True, help="owner/name the project must be linked to")
    p_adopt.add_argument("--owner", help="project owner login (default: --repo owner; never @me)")
    p_adopt.add_argument("--etalon", help=f"etalon doc path (default: {DEFAULT_ETALON})")
    p_adopt.add_argument("--out", help=f"config output path (default: {DEFAULT_CONFIG})")
    p_adopt.add_argument("--force", action="store_true",
                         help="overwrite an existing board_config.json deliberately")
    p_adopt.add_argument("--dry-run", action="store_true",
                         help="print the plan tree; zero network calls")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    # Etalon parse/validate strictly first — before any network call.
    try:
        etalon, etalon_path = load_etalon(args.etalon)
    except EtalonError as e:
        sys.exit(f"error: {e}")
    validate_repo(args.repo)  # argument validation (also in --dry-run)
    if args.dry_run:
        guards = plan_guards(args.mode, args, etalon_path)
        print(render_plan(args.mode, args, etalon, etalon_path, guards))
        return
    if args.mode == "adopt":
        sys.exit(cmd_adopt(args, etalon))
    sys.exit(cmd_init(args, etalon))


if __name__ == "__main__":
    main()
