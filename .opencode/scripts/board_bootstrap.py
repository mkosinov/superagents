#!/usr/bin/env python3
"""board_bootstrap.py — roll out (init) or adopt a GH ProjectV2 board.

Reads the declarative board definition (etalon) from docs/board/board-etalon.md
and creates the project, its fields, links the repo, seeds open issues, writes
docs/board/board_config.json. `adopt` compares an existing project with the
etalon and writes the config without mutating the board.

This file is the pure, network-free foundation (Task 2 of the build):
etalon parsing, plan rendering, CLI wiring. The gh runner lands later; --dry-run
works end-to-end today with zero network calls.

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
import sys
from dataclasses import dataclass
from pathlib import Path

# Repo root anchored to the script's own path (both twins resolve the same
# root: .zcode/scripts/x.py and .opencode/scripts/x.py are two levels deep).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ETALON = REPO_ROOT / "docs" / "board" / "board-etalon.md"
DEFAULT_CONFIG = REPO_ROOT / "docs" / "board" / "board_config.json"

BLOCK_RE = re.compile(r"```board-etalon\n(.*?)\n```", re.S)


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


def plan_guards(mode: str, args, etalon_path: Path) -> list[str]:
    """Guard planner — REPORT-ONLY placeholder (real verdicts land with the guards task).

    One line per future guard; in dry-run these become plan lines and a
    would-be refusal never changes the exit code (keeps CI green once the
    real config is committed).
    """
    out = effective_config_path(args)
    if mode == "init":
        return [
            f"guard: config exists at {out}: not-checked-yet (planned)",
            f"guard: repo {args.repo} already linked to an open project: "
            f"not-checked-yet (planned)",
            f"guard: title collision with an open project of the owner: "
            f"not-checked-yet (planned)",
        ]
    return [
        f"guard: config exists at {out} (--force overwrites): not-checked-yet (planned)",
    ]


def render_plan(mode: str, args, etalon: Etalon, etalon_path: Path,
                guard_verdicts: list[str]) -> str:
    """Offline text tree of what WOULD happen. Zero network calls.

    init: etalon → project create → built-in Status removal → one line per
    etalon field → repo link → seeding → config path. adopt: the planned
    comparison instead of the create/link lines. Guard verdicts appended
    report-only, one line per guard.
    """
    lines = [f"etalon: {etalon_path}"]
    if mode == "init":
        lines.append(f'project: create "{args.title}" (owner {effective_owner(args)})')
        lines.append("remove built-in field Status (Todo / In Progress / Done)")
        for f in etalon.fields:
            lines.append(f'create {f["name"]}: ' + " | ".join(f["options"]))
        lines.append(f"link: {args.repo}")
        lines.append("seed: open issues would be listed live (--dry-run: no network)")
    else:
        lines.append(f"compare: read fields of project #{args.project} "
                     f"and match by exact name")
        lines.append("refuse: missing field or option; "
                     "warn: extra field or option (drift contract)")
        lines.append(f"verify: project #{args.project} is linked to {args.repo}")
    lines.append(f"config: {effective_config_path(args)}")
    lines.extend(guard_verdicts)
    return "\n".join(lines)


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
    if args.dry_run:
        guards = plan_guards(args.mode, args, etalon_path)
        print(render_plan(args.mode, args, etalon, etalon_path, guards))
        return
    sys.exit(f"error: live '{args.mode}' is not implemented yet (use --dry-run)")


if __name__ == "__main__":
    main()
