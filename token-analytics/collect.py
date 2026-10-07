#!/usr/bin/env python3
"""collect.py — CLI entry for token-analytics (#26).

Subcommands:
  collect     run one collection pass (host + container sources -> snapshot)
  serve       static viewer + JSON API (server.py)
  writeback   board write-back via managed gh CLI (writeback.py)

Skeleton only: the handlers print «not implemented» and exit; the real
logic lands with tasks 2-8 of #26.
"""
import argparse
import sys


def cmd_collect(args: argparse.Namespace) -> int:
    """Stub: one collection pass -> data/ snapshot (later tasks of #26)."""
    print("collect: not implemented", file=sys.stderr)
    return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """Stub: serve the static viewer + JSON API (later tasks of #26)."""
    print("serve: not implemented", file=sys.stderr)
    return 1


def cmd_writeback(args: argparse.Namespace) -> int:
    """Stub: write snapshot metrics to the GH board (later tasks of #26)."""
    print("writeback: not implemented", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collect.py",
        description="token-analytics: per-issue token & duration analytics (#26)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser(
        "collect", help="run one collection pass (sources -> snapshot in data/)"
    )
    p_collect.set_defaults(func=cmd_collect)

    p_serve = sub.add_parser(
        "serve", help="serve the static viewer + JSON API"
    )
    p_serve.set_defaults(func=cmd_serve)

    p_writeback = sub.add_parser(
        "writeback", help="write snapshot metrics to the GH board"
    )
    p_writeback.set_defaults(func=cmd_writeback)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
