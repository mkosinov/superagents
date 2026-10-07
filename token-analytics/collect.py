#!/usr/bin/env python3
"""collect.py — CLI entry for token-analytics (#26).

Subcommands:
  collect     run one collection pass (host + container sources -> data/)
  serve       static viewer + JSON API (server.py)
  writeback   board write-back via managed gh CLI (writeback.py)

`collect` (Task 5) wires the full pipeline via collector.run_collect:
readers -> mapping -> aggregation -> snapshots -> write-back hook, the
whole write phase under an exclusive flock on data/.lock — a second
run finding the lock held logs «skipped: previous run still active»
and exits 0. Warnings always go to stderr; under cron they land in
data/collect.log via the README's redirect. `serve` (Task 7) runs the
viewer + /data/*.json + POST /api/bind on 127.0.0.1:8765 via server.py;
`writeback` remains a stub until its task of #26.
"""
import argparse
import os
import sys

import collector

DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.json")


def cmd_collect(args: argparse.Namespace) -> int:
    """One collection pass: locked readers -> rebuild -> write-back hook."""
    try:
        config = collector.load_config(args.config)
    except (OSError, ValueError) as exc:
        print("collect: cannot load config " + str(args.config) + ": "
              + str(exc), file=sys.stderr)
        return 1  # a broken config is not fail-open, unlike source failures
    collector.run_collect(config, collector.data_dir_for(args.config))
    return 0  # lock-skip and fail-open source losses both stay 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Serve the static viewer + JSON API + POST /api/bind (server.py).

    Host/port come from the config `serve` block (default 127.0.0.1:8765);
    Ctrl-C is the normal way down.
    """
    try:
        config = collector.load_config(args.config)
    except (OSError, ValueError) as exc:
        print("serve: cannot load config " + str(args.config) + ": "
              + str(exc), file=sys.stderr)
        return 1
    import server
    server.run_serve(config, collector.data_dir_for(args.config))
    return 0


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
    p_collect.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="path to config.json (default: the config.json next to this script)",
    )
    p_collect.set_defaults(func=cmd_collect)

    p_serve = sub.add_parser(
        "serve", help="serve the static viewer + JSON API"
    )
    p_serve.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="path to config.json (default: the config.json next to this script)",
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
