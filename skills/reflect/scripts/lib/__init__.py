"""reflect package CLI entry point."""
import argparse
import sys
from pathlib import Path

REFLECT_HOME = Path.home() / ".config" / "opencode" / "reflection"


def main() -> int:
    """CLI entry point for reflect skill."""
    parser = argparse.ArgumentParser(prog="reflect")
    sub = parser.add_subparsers(dest="mode", required=True)

    # post-mortem
    pm = sub.add_parser("post-mortem", help="Bug-driven post-mortem")
    pm.add_argument("--target", required=True, help="File path that has the bug")
    pm.add_argument("--repo", help="Repo path (default: cwd)")

    # wave
    wv = sub.add_parser("wave", help="Wave-driven report")
    wv.add_argument("--name", required=True, help='Wave name, e.g. "Wave 4.5"')

    # nightly
    nt = sub.add_parser("nightly", help="Time-driven nightly digest")
    nt.add_argument("--days", type=int, default=7)
    nt.add_argument("--auto-apply", action="store_true")

    # status
    sub.add_parser("status", help="Show reflection health + counts")

    args = parser.parse_args()
    if args.mode == "post-mortem":
        from .post_mortem import run_post_mortem
        return run_post_mortem(args)
    elif args.mode == "wave":
        from .wave_report import run_wave_report
        return run_wave_report(args)
    elif args.mode == "nightly":
        from .nightly import run_nightly
        return run_nightly(args)
    elif args.mode == "status":
        from .status_cmd import run_status
        return run_status(args)
    return 1
