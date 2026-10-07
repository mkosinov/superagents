#!/usr/bin/env python3
"""collect.py — CLI entry for token-analytics (#26).

Subcommands:
  collect     run one collection pass (host + container sources -> data/)
  serve       static viewer + JSON API (server.py)
  writeback   board write-back re-push from existing data/ snapshots
  fields      one-time NUMBER field creation on each enabled board

`collect` (Task 5) wires the full pipeline via collector.run_collect:
readers -> mapping -> aggregation -> snapshots -> write-back hook, the
whole write phase under an exclusive flock on data/.lock — a second
run finding the lock held logs «skipped: previous run still active»
and exits 0. Warnings always go to stderr; under cron they land in
data/collect.log via the README's redirect. `serve` (Task 7) runs the
viewer + /data/*.json + POST /api/bind on 127.0.0.1:8765 via server.py.
`writeback` (Task 8) re-runs the same write-back pipeline the collect
pass ended with, over the snapshots already in data/ (same flock, same
fail-open rules); `fields` (Task 8) creates the configured NUMBER
fields on each enabled project's board — run it once per project after
flipping write_back.enabled on.
"""
import argparse
import errno
import fcntl
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
    Ctrl-C is the normal way down. A bind failure (port already taken by
    a second serve) is a clean one-line error, not a raw traceback.
    """
    try:
        config = collector.load_config(args.config)
    except (OSError, ValueError) as exc:
        print("serve: cannot load config " + str(args.config) + ": "
              + str(exc), file=sys.stderr)
        return 1
    import server
    try:
        server.run_serve(config, collector.data_dir_for(args.config))
    except OSError as exc:
        _, port = server.serve_address(config)
        if exc.errno == errno.EADDRINUSE:
            print("serve: порт " + str(port)
                  + " занят — сервер уже запущен?", file=sys.stderr)
        else:
            print("serve: " + str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_writeback(args: argparse.Namespace) -> int:
    """Re-push snapshot metrics to the boards from existing data/ snapshots.

    The same pipeline `collect` runs post-rebuild (writeback.py), over
    the issue files already in data/ — a manual re-push after a gh
    outage or a board fix. Serialized against a running collect by the
    same exclusive flock (a busy lock skips fail-open, exit 0); gh
    failures warn and the run still exits 0.
    """
    try:
        config = collector.load_config(args.config)
    except (OSError, ValueError) as exc:
        print("writeback: cannot load config " + str(args.config) + ": "
              + str(exc), file=sys.stderr)
        return 1
    import writeback
    directory = collector.data_dir_for(args.config)
    os.makedirs(directory, exist_ok=True)
    lock_fd = os.open(os.path.join(directory, collector.LOCK_FILENAME),
                      os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(collector.SKIP_MESSAGE, file=sys.stderr)
            return 0
        writeback.run_writeback(config, directory)
        return 0
    finally:
        os.close(lock_fd)  # releases the flock (never held on "skipped")


def cmd_fields(args: argparse.Namespace) -> int:
    """Create the configured NUMBER fields on each enabled board (once).

    One `gh project field-create --data-type NUMBER` per missing
    canonical name, idempotent; an existing non-NUMBER name with a
    configured binding stops loudly (exit 1, zero mutations). gh
    failures stay fail-open (warning, exit 0).
    """
    try:
        config = collector.load_config(args.config)
    except (OSError, ValueError) as exc:
        print("fields: cannot load config " + str(args.config) + ": "
              + str(exc), file=sys.stderr)
        return 1
    import writeback
    return writeback.run_fields(config)


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
        "writeback",
        help="re-push snapshot metrics to the GH boards from existing data/"
    )
    p_writeback.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="path to config.json (default: the config.json next to this script)",
    )
    p_writeback.set_defaults(func=cmd_writeback)

    p_fields = sub.add_parser(
        "fields",
        help="create the configured NUMBER fields on each enabled board (once)"
    )
    p_fields.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="path to config.json (default: the config.json next to this script)",
    )
    p_fields.set_defaults(func=cmd_fields)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
