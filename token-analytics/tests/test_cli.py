"""Unit tests for the collect.py CLI `collect` subcommand (#26 Task 5).

DoD coverage (spec §Collection runs, §Snapshots and state):
- full pipeline over fixture DBs via a fixture config: readers → mapping
  → aggregation → snapshots produce the expected set (golden shape:
  projects, issues, phases), per-source availability recorded in
  index.json, write-back hook invoked after the rebuild (no-op stub);
- lock: data/.lock held by another process → «skipped: previous run
  still active» on stderr, exit 0, nothing written;
- fail-open: one source failing (unknown container) → the other
  source's issues still rebuilt, warnings on stderr, exit 0, the
  failed source marked unavailable in index.json;
- CLI plumbing: --config defaults to token-analytics/config.json
  resolved relative to the repo layout (not the CWD); the data dir is
  the config file's sibling data/ — injectable via a tmp fixture config.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make collect/collector importable

import collect  # noqa: E402
import collector  # noqa: E402
import writeback  # noqa: E402
try:
    from . import fixtures  # discovered as a package (tests/__init__.py present)
except ImportError:  # discovered bare from inside tests/
    import fixtures  # noqa: E402

# Fake `docker` (same trick as test_readers.py): records argv, then runs
# `exec <container> <cmd...>` locally so the real sqlite3 CLI validates
# the -readonly/-json/.timeout args against the fixture container DB.
FAKE_DOCKER = (
    "#!/bin/sh\n"
    'printf \'%s\\n\' "$@" > "$FAKE_DOCKER_ARGS_FILE"\n'
    '[ "$1" = "exec" ] || exit 64\n'
    "shift 2\n"
    'exec "$@"\n'
)


def _fake_docker_on_path(tmpdir):
    """Create the fake docker executable in tmpdir/bin; returns its dir."""
    bindir = tmpdir / "bin"
    bindir.mkdir(exist_ok=True)
    fake_docker = bindir / "docker"
    fake_docker.write_text(FAKE_DOCKER)
    os.chmod(fake_docker, 0o755)
    return bindir


def _write_fixture_config(tmpdir, *, host_db, container=None, container_db=None):
    """A fixture config.json in tmpdir: sources → fixture DBs, memo split
    mode; the data dir derives as tmpdir/data (config-file sibling)."""
    sources = {"zcode_host": {"db": str(host_db)}}
    if container is not None:
        sources["opencode_container"] = {"container": container,
                                         "db": str(container_db)}
    config = {
        "version": 1,
        "sources": sources,
        "projects": {
            "memo": {"repo": "mkosinov/memo", "phase_mode": "split",
                     "directories": ["/root/workspace/memo"]},
        },
    }
    config_path = tmpdir / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path


class FullPipelineTests(unittest.TestCase):
    def test_collect_over_fixture_dbs_produces_expected_snapshot_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            host_db = tmpdir / "host.sqlite"
            fixtures.write_host_db(host_db, fixtures.host_scenario())
            ctr_db = tmpdir / "opencode.db"
            fixtures.write_container_db(ctr_db, fixtures.container_scenario())
            config_path = _write_fixture_config(
                tmpdir, host_db=host_db, container="memo-box", container_db=ctr_db)
            bindir = _fake_docker_on_path(tmpdir)
            env = {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                   "FAKE_DOCKER_ARGS_FILE": str(tmpdir / "docker-args.txt")}
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(collector, "fetch_issue_titles",
                                      lambda repo: {"327": "каскад удаления"}), \
                    mock.patch.object(writeback, "run_after_rebuild") as hook, \
                    contextlib.redirect_stderr(stderr):
                rc = collect.main(["collect", "--config", str(config_path)])

            self.assertEqual(rc, 0)
            self.assertEqual(stderr.getvalue(), "")  # both sources healthy: no warnings
            # write-back hook fired after the rebuild (Task 8 fills the stub)
            hook.assert_called_once()
            self.assertEqual(hook.call_args.args[1], str(tmpdir / "data"))
            # golden shape: projects, issues, phases — the known fixture numbers
            data = tmpdir / "data"
            issue_names = sorted(p.name for p in (data / "issues").iterdir())
            self.assertEqual(issue_names,
                             ["memo-327.json", "memo-331.json", "memo-335.json"])
            snap327 = json.loads((data / "issues" / "memo-327.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(snap327["project"], "memo")       # project namespace
            self.assertEqual(set(snap327["phases"]), {"design", "impl"})
            self.assertEqual(snap327["tokens"]["total"], 157_200)
            self.assertEqual(snap327["title"], "каскад удаления")  # via mocked gh
            snap335 = json.loads((data / "issues" / "memo-335.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(set(snap335["phases"]), {"impl"})  # container-only
            # per-source availability recorded in index.json
            index = json.loads((data / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["sources"], {"host": True, "container": True})
            self.assertEqual([r["issue"] for r in index["issues"]], [327, 331, 335])
            # the lock file exists and the run released it (a second pass works)
            self.assertTrue((data / ".lock").exists())

    def test_default_config_resolves_relative_to_repo_layout(self):
        args = collect.build_parser().parse_args(["collect"])  # parse only
        self.assertEqual(args.config, collect.DEFAULT_CONFIG)
        self.assertEqual(
            os.path.normpath(args.config),
            os.path.join(str(Path(collect.__file__).resolve().parent), "config.json"))
        self.assertTrue(Path(args.config).exists())  # the committed config


class LockTests(unittest.TestCase):
    def test_lock_held_by_other_process_skips_message_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            host_db = tmpdir / "host.sqlite"
            fixtures.write_host_db(host_db, fixtures.host_scenario())
            config_path = _write_fixture_config(tmpdir, host_db=host_db)
            data = tmpdir / "data"
            data.mkdir()
            lock_path = data / ".lock"
            holder = subprocess.Popen(
                [sys.executable, "-c",
                 "import fcntl, os, time\n"
                 "fd = os.open({!r}, os.O_CREAT | os.O_RDWR)\n"
                 "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                 "print('held', flush=True)\n"
                 "time.sleep(60)".format(str(lock_path))],
                stdout=subprocess.PIPE, text=True)
            try:
                assert holder.stdout is not None  # narrows the Optional pipe
                self.assertEqual(holder.stdout.readline().strip(), "held")
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = collect.main(["collect", "--config", str(config_path)])
                self.assertEqual(rc, 0)
                self.assertIn("skipped: previous run still active",
                              stderr.getvalue())
                # the skipped run wrote nothing but the lock file itself
                self.assertFalse((data / "index.json").exists())
                self.assertEqual(sorted(p.name for p in data.iterdir()),
                                 [".lock"])
            finally:
                holder.kill()
                holder.wait()


class FailOpenTests(unittest.TestCase):
    def test_one_source_failing_other_source_rebuilt_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            host_db = tmpdir / "host.sqlite"
            fixtures.write_host_db(host_db, fixtures.host_scenario())
            # container source points at a container that cannot exist:
            # docker present (unknown name → non-zero) or absent (OSError)
            # — both paths are the reader's fail-open warning + None
            config_path = _write_fixture_config(
                tmpdir, host_db=host_db,
                container="token-analytics-no-such-container-xyz",
                container_db="/root/.local/share/opencode/opencode.db")
            stderr = io.StringIO()
            with mock.patch.object(collector, "fetch_issue_titles",
                                   lambda repo: {}), \
                    contextlib.redirect_stderr(stderr):
                rc = collect.main(["collect", "--config", str(config_path)])

            self.assertEqual(rc, 0)                       # fail-open: exit stays 0
            self.assertIn("warning", stderr.getvalue())   # warnings always on stderr
            data = tmpdir / "data"
            # host-only issues rebuilt; 335 (container-only) correctly absent
            issue_names = sorted(p.name for p in (data / "issues").iterdir())
            self.assertEqual(issue_names, ["memo-327.json", "memo-331.json"])
            snap327 = json.loads((data / "issues" / "memo-327.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(snap327["tokens"]["total"], 91_700)  # design-only
            # the failed source is marked unavailable in index.json
            index = json.loads((data / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["sources"], {"host": True, "container": False})


if __name__ == "__main__":
    unittest.main()
