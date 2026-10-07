"""Unit tests for token-analytics source readers and fixture generators (#26 Task 2).

DoD coverage:
- fixture DBs read back exact rows (counts + spot fields), grandparents included;
- fail-open: missing host path, garbage host file, unknown container →
  warning + None, and a process doing only fail-open reads exits 0;
- reader connections are read-only (a write attempt raises) with busy_timeout=5000;
- static safety: no `shell=True`/shell=, no non-parameterized SQL in collector.py;
- the exact `docker exec <c> sqlite3 -readonly -json <db> .timeout 5000 <SQL>`
  command surface (verified through a fake docker executable).
"""

import contextlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make collector importable

import collector  # noqa: E402
try:
    from . import fixtures  # discovered as a package (tests/__init__.py present)
except ImportError:  # discovered bare from inside tests/
    import fixtures  # noqa: E402

# Fake `docker`: records its argv (so tests can pin the exact command surface),
# then re-executes `exec <container> <cmd...>` as the local `<cmd...>` — the
# local sqlite3 CLI therefore validates the real -readonly/-json/.timeout args.
FAKE_DOCKER = (
    "#!/bin/sh\n"
    'printf \'%s\\n\' "$@" > "$FAKE_DOCKER_ARGS_FILE"\n'
    '[ "$1" = "exec" ] || exit 64\n'
    "shift 2\n"
    'exec "$@"\n'
)


def _by_id(sessions):
    return {s["id"]: s for s in sessions}


def _sort_turns(turns):
    return sorted(turns, key=lambda t: (t["session_id"], t["turn_id"]))


def _sort_models(models):
    return sorted(models, key=lambda m: (m["session_id"], m["turn_id"], m["model_id"]))


class HostReaderTests(unittest.TestCase):
    def test_read_host_round_trips_exact_rows_including_grandparents(self):
        rows = fixtures.host_scenario()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite"
            fixtures.write_host_db(db_path, rows)
            result = collector.read_host(db_path)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(result["sessions"], key=lambda s: s["id"]),
                         sorted(rows["sessions"], key=lambda s: s["id"]))
        self.assertEqual(_sort_turns(result["turns"]), _sort_turns(rows["turns"]))
        self.assertEqual(_sort_models(result["models"]), _sort_models(rows["models"]))

        # grandparents/roots and grandchild links survive the round trip
        by_id = _by_id(result["sessions"])
        self.assertIsNone(by_id["h-design"]["parent_id"])
        self.assertIsNone(by_id["h-marathon"]["parent_id"])
        self.assertEqual(by_id["h-design-p2-g1"]["parent_id"], "h-design-p2")
        self.assertEqual(by_id["h-marathon-c1-g1"]["parent_id"], "h-marathon-c1")

        # an errored turn came through with its status and error count
        errored = [t for t in result["turns"] if t["status"] == "error"]
        self.assertEqual(len(errored), 1)
        self.assertEqual(errored[0]["errors"], 1)

        # spot token/agent fields are untouched
        root_turn = next(t for t in result["turns"] if t["turn_id"] == "h-design/t1")
        self.assertEqual(root_turn["tokens_input"], 2_000)
        self.assertEqual(root_turn["tokens_cache_write"], 600)
        model = next(m for m in result["models"] if m["turn_id"] == "h-design/t1")
        self.assertEqual(model["agent"], "zcode-Explore")
        self.assertEqual(model["model_id"], "claude-sonnet-4-5")

    def test_read_host_returns_all_directories_unfiltered(self):
        rows = fixtures.host_scenario()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite"
            fixtures.write_host_db(db_path, rows)
            result = collector.read_host(db_path)
        self.assertIsNotNone(result)
        # ALL directories come back — filtering is mapping's job (spec §Mapping step 1)
        dirs = {s["directory"] for s in result["sessions"]}
        self.assertEqual(dirs, {"/root/workspace/memo", "/tmp/scratch"})
        by_id = _by_id(result["sessions"])
        self.assertIn("h-solo-1", by_id)      # childless root
        self.assertIn("h-loose", by_id)       # unattributed directory

    def test_host_scenario_counts_and_parameterization(self):
        full = fixtures.host_scenario()
        self.assertEqual(len(full["sessions"]), 11)
        self.assertEqual(len(full["turns"]), 13)
        self.assertEqual(len(full["models"]), 13)

        # parallel children genuinely overlap in time
        by_id = _by_id(full["sessions"])
        p1, p2 = by_id["h-design-p1"], by_id["h-design-p2"]
        self.assertLess(p1["time_created"], p2["time_created"])
        self.assertGreater(p1["time_updated"], p2["time_created"])

        # marathon root with T-labeled children (T1 twice) + standalone child
        child_titles = [s["title"] for s in full["sessions"]
                        if s["id"].startswith("h-marathon-c") and not s["id"].endswith("-g1")]
        self.assertEqual(child_titles, ["T1: scaffold", "T1: tests", "Fix crash"])

        slim = fixtures.host_scenario(with_grandchildren=False, parallel_children=1,
                                      marathon_children=("T1: only",), childless_roots=0,
                                      with_errored_turns=False)
        slim_ids = {s["id"] for s in slim["sessions"]}
        self.assertFalse(any(i.endswith("-g1") for i in slim_ids))
        self.assertNotIn("h-solo-1", slim_ids)
        self.assertNotIn("h-design-p2", slim_ids)
        self.assertTrue(all(t["status"] == "ok" for t in slim["turns"]))


class ContainerReaderTests(unittest.TestCase):
    def test_read_container_round_trips_via_fake_docker(self):
        rows = fixtures.container_scenario()
        self.assertEqual(len(rows["sessions"]), 7)
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            db_path = tmpdir / "opencode.db"
            fixtures.write_container_db(db_path, rows)
            bindir = tmpdir / "bin"
            bindir.mkdir()
            fake_docker = bindir / "docker"
            fake_docker.write_text(FAKE_DOCKER)
            os.chmod(fake_docker, 0o755)
            args_file = tmpdir / "docker-args.txt"
            env = {
                "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                "FAKE_DOCKER_ARGS_FILE": str(args_file),
            }
            with mock.patch.dict(os.environ, env):
                result = collector.read_container("memo-box", str(db_path))
            argv_seen = args_file.read_text().splitlines()

        self.assertIsNotNone(result)
        # exact recon-verified command surface (spec §Reuse / §Sources and access)
        self.assertEqual(argv_seen, [
            "exec", "memo-box",
            "sqlite3", "-readonly", "-json", str(db_path),
            ".timeout 5000",
            collector.CONTAINER_SESSION_SQL,
        ])
        self.assertEqual(sorted(result["sessions"], key=lambda s: s["id"]),
                         sorted(rows["sessions"], key=lambda s: s["id"]))

        by_id = _by_id(result["sessions"])
        self.assertEqual(by_id["c-marathon"]["model"], json.dumps({"id": "claude-opus-4-6"}))
        self.assertEqual(by_id["c-marathon"]["agent"], "manager")
        self.assertEqual(by_id["c-marathon"]["tokens_input"], 4_000)  # wrapper tokens count
        self.assertEqual(by_id["c-marathon-c1"]["agent"], "backend-coder")
        self.assertEqual(by_id["c-marathon-c1-g1"]["parent_id"], "c-marathon-c1")
        self.assertIn("песочница", by_id["c-play"]["title"])  # UTF-8 survives the pipe
        self.assertEqual(by_id["c-solo-1"]["parent_id"], None)  # childless root


class FailOpenTests(unittest.TestCase):
    def test_read_host_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.sqlite"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = collector.read_host(missing)
        self.assertIsNone(result)
        self.assertIn("warning", stderr.getvalue())

    def test_read_host_garbage_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            garbage = Path(tmp) / "garbage.sqlite"
            garbage.write_bytes(b"this is not a database at all")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = collector.read_host(garbage)
        self.assertIsNone(result)
        self.assertIn("warning", stderr.getvalue())

    def test_read_container_unknown_container(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = collector.read_container(
                "token-analytics-no-such-container-xyz",
                "/root/.local/share/opencode/opencode.db")
        self.assertIsNone(result)
        self.assertIn("warning", stderr.getvalue())

    def test_fail_open_sources_keep_process_exit_zero(self):
        collector_dir = Path(collector.__file__).resolve().parent
        script = (
            "import sys; sys.path.insert(0, {path!r}); import collector; "
            "host = collector.read_host({missing!r}); "
            "ctr = collector.read_container('token-analytics-no-such-container-xyz',"
            " '/root/x/opencode.db'); "
            "assert host is None and ctr is None, (host, ctr)"
        ).format(path=str(collector_dir), missing="/nonexistent/host-db.sqlite")
        proc = subprocess.run([sys.executable, "-c", script],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("warning", proc.stderr)


class ReadOnlyTests(unittest.TestCase):
    def test_host_connection_is_readonly_with_busy_timeout(self):
        rows = fixtures.host_scenario()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite"
            fixtures.write_host_db(db_path, rows)
            conn = collector.open_host_readonly(db_path)
            try:
                self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute(
                        "INSERT INTO session"
                        " (id, parent_id, directory, title, time_created, time_updated)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        ("evil", None, "/etc", "mutation attempt", 1, 2))
            finally:
                conn.close()


class StaticSafetyTests(unittest.TestCase):
    def test_collector_uses_argv_lists_and_parameterized_sql_only(self):
        src = Path(collector.__file__).read_text()
        self.assertNotIn("shell=", src)  # argv lists only — never shell=True (nor False)
        self.assertNotIn(".format(", src)
        self.assertIsNone(re.search(r'execute\(\s*f["\']', src))
        self.assertIsNone(re.search(r'executemany\(\s*f["\']', src))
        # every SQL statement is a pure static constant — no interpolation markers
        for name in ("HOST_SESSION_SQL", "HOST_TURN_SQL", "HOST_MODEL_SQL",
                     "CONTAINER_SESSION_SQL"):
            sql = getattr(collector, name)
            for marker in ("{", "}", "%"):
                self.assertNotIn(marker, sql, name)

    def test_fixtures_use_parameterized_sql_only(self):
        src = Path(fixtures.__file__).read_text()
        self.assertNotIn("shell=", src)
        self.assertNotIn(".format(", src)
        self.assertIsNone(re.search(r'execute\(\s*f["\']', src))
        self.assertIsNone(re.search(r'executescript\(\s*f["\']', src))


if __name__ == "__main__":
    unittest.main()
