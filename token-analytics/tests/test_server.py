"""Server tests for `collect serve` (#26 Task 7): static + /data + POST /api/bind.

E2E per spec §Testing: a REAL rebuild over fixture DBs into a tmp data
dir (the test_cli.py pipeline machinery — fixture config + fake docker
on PATH), then `server.make_server` on an ephemeral port (bind port 0,
read back the assigned port, serve in a thread, tearDown shuts down),
driven with stdlib urllib.request only.

DoD coverage:
- E2E scenarios 1–4 (index sorted + WIP row, issue snapshot full field
  set, design tree agent attribution, T-fold + standalone + grandchild
  folded into the parent's subtree total);
- E2E scenario 5 (bind on unmatched AND already-matched sessions →
  override written/replaced, snapshot includes the session, unmatched
  drops it; child session id resolves to its ROOT);
- guard units (wrong Host, cross-origin POST, wrong Content-Type,
  unknown session/issue, lock busy → 503 «сбор идёт, повтори»);
- static contract (viewer whitelist, /data/*.json, path traversal and
  symlink escape rejected, no directory listing);
- `collect.py serve` wiring (--config, serve block host/port).
"""

import fcntl
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect  # noqa: E402
import collector  # noqa: E402
import server  # noqa: E402
try:
    from . import fixtures  # discovered as a package (tests/__init__.py present)
except ImportError:  # discovered bare from inside tests/
    import fixtures  # noqa: E402

# Same fake-docker trick as test_cli.py / test_readers.py: records argv,
# then runs `exec <container> <cmd...>` locally so the real sqlite3 CLI
# validates the args against the fixture container DB.
FAKE_DOCKER = (
    "#!/bin/sh\n"
    'printf \'%s\\n\' "$@" > "$FAKE_DOCKER_ARGS_FILE"\n'
    '[ "$1" = "exec" ] || exit 64\n'
    "shift 2\n"
    'exec "$@"\n'
)

TITLES = {"327": "каскад удаления"}  # repo mkosinov/memo, via patched gh


def _fake_docker_on_path(tmpdir: Path) -> Path:
    bindir = tmpdir / "bin"
    bindir.mkdir(exist_ok=True)
    fake_docker = bindir / "docker"
    fake_docker.write_text(FAKE_DOCKER)
    os.chmod(fake_docker, 0o755)
    return bindir


def build_world(tmpdir: Path):
    """Fixture DBs + config + one full collect pass → (config_path,
    config_dict, data_dir). The data dir is the config's sibling."""
    host_db = tmpdir / "host.sqlite"
    fixtures.write_host_db(host_db, fixtures.host_scenario())
    ctr_db = tmpdir / "opencode.db"
    fixtures.write_container_db(ctr_db, fixtures.container_scenario())
    config = {
        "version": 1,
        "sources": {
            "zcode_host": {"db": str(host_db)},
            "opencode_container": {"container": "memo-box", "db": str(ctr_db)},
        },
        "projects": {
            "memo": {"repo": "mkosinov/memo", "phase_mode": "split",
                     "directories": ["/root/workspace/memo"]},
        },
        "serve": {"host": "127.0.0.1", "port": 8765},
    }
    config_path = tmpdir / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    bindir = _fake_docker_on_path(tmpdir)
    env = {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
           "FAKE_DOCKER_ARGS_FILE": str(tmpdir / "docker-args.txt")}
    with mock.patch.dict(os.environ, env), \
            mock.patch.object(collector, "fetch_issue_titles",
                              lambda repo: dict(TITLES)):
        rc = collect.main(["collect", "--config", str(config_path)])
    assert rc == 0
    return config_path, config, tmpdir / "data"


def http(method: str, url: str, headers=None, body: bytes = b""):
    """One stdlib-urllib request → (status, headers, body bytes).

    HTTPError is unfolded too — guard tests need the 4xx/5xx bodies.
    """
    request = urllib.request.Request(url, data=body or None, method=method,
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, dict(exc.headers), exc.read()


class ServeTestCase(unittest.TestCase):
    """Fresh fixture world + ephemeral-port server per test (bind tests
    mutate data/ — no shared state between tests)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmpdir = Path(tmp.name)
        self.config_path, self.config, self.data_dir = build_world(self.tmpdir)
        # The bind rebuild (server thread) re-reads sources: keep the fake
        # docker on PATH and gh titles patched for the whole test.
        env = {"PATH": str(self.tmpdir / "bin") + os.pathsep
               + os.environ.get("PATH", ""),
               "FAKE_DOCKER_ARGS_FILE": str(self.tmpdir / "docker-args.txt")}
        env_patch = mock.patch.dict(os.environ, env)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        titles_patch = mock.patch.object(collector, "fetch_issue_titles",
                                         lambda repo: dict(TITLES))
        titles_patch.start()
        self.addCleanup(titles_patch.stop)
        self.httpd = server.make_server(self.config, str(self.data_dir),
                                        host="127.0.0.1", port=0)
        self.port = self.httpd.server_address[1]
        self.base = "http://127.0.0.1:" + str(self.port)
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        # LIFO cleanup: shutdown → join → server_close
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(self.httpd.shutdown)

    # -- small helpers ----------------------------------------------------

    def get(self, path, headers=None):
        return http("GET", self.base + path, headers=headers)

    def post_json(self, path, payload, headers=None):
        merged = {"Content-Type": "application/json"}
        merged.update(headers or {})
        status, resp_headers, body = http(
            "POST", self.base + path, headers=merged,
            body=json.dumps(payload).encode("utf-8"))
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
        return status, parsed

    def snapshot(self, name):
        return json.loads((self.data_dir / "issues" / name)
                          .read_text(encoding="utf-8"))


class E2eIndexTests(ServeTestCase):
    """Scenario 1: index JSON — sorted table, WIP row with accrued totals
    and a real date, project tabs, per-source availability."""

    def test_index_sorted_wip_row_real_date(self):
        status, headers, body = self.get("/data/index.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        index = json.loads(body.decode("utf-8"))
        # sorted by token total desc (ties → project, issue): known numbers
        self.assertEqual([row["issue"] for row in index["issues"]],
                         [327, 331, 335])
        top = index["issues"][0]
        self.assertEqual(top["project"], "memo")
        self.assertEqual(top["tokens"]["total"], 157_200)
        # every row carries a REAL last-activity date (fixture-derived)
        for row in index["issues"]:
            self.assertRegex(row["last_activity"], r"^\d{4}-\d{2}-\d{2}$")
        # the WIP row (latest real work, no invented completion state):
        # memo-335 = c-solo-1, updated BASE+7h40m → 2023-11-15 UTC
        wip = next(row for row in index["issues"] if row["issue"] == 335)
        self.assertEqual(wip["last_activity"], "2023-11-15")
        self.assertEqual(wip["tokens"]["total"], 6_550)  # accrued, not zeroed
        self.assertEqual(wip["phases"]["impl"]["active_ms"], 2_400_000)
        self.assertEqual(wip["phases"]["impl"]["tokens"]["total"], 6_550)
        self.assertNotIn("design", wip["phases"])  # absent phase, not zeroed
        # tabs + per-source availability
        self.assertEqual(index["projects"], ["memo"])
        self.assertEqual(index["sources"], {"host": True, "container": True})


class E2eIssueSnapshotTests(ServeTestCase):
    """Scenario 2: the issue snapshot exposes both phases with the full
    field set (components, active, calendar) and aggregates."""

    def test_issue_snapshot_full_field_set(self):
        status, headers, body = self.get("/data/issues/memo-327.json")
        self.assertEqual(status, 200)
        snap = json.loads(body.decode("utf-8"))
        self.assertEqual(snap["project"], "memo")
        self.assertEqual(snap["issue"], 327)
        self.assertEqual(snap["title"], "каскад удаления")  # via patched gh
        self.assertEqual(snap["title_source"], "gh")
        self.assertEqual(snap["tokens"]["total"], 157_200)
        self.assertEqual(set(snap["phases"]), {"design", "impl"})
        self.assertEqual(snap["phases"]["design"]["tokens"]["total"], 91_700)
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 65_500)
        for phase, block in snap["phases"].items():
            self.assertEqual(set(block["tokens"]),
                             {"input", "output", "reasoning",
                              "cache_read", "cache_write", "total", "total_m"})
            self.assertGreater(block["active_ms"], 0)
            self.assertEqual(set(block["active"]), {"hours"})
            self.assertEqual(set(block["calendar"]), {"ms", "days", "hours"})
            self.assertIsInstance(block["tree"], list)
            self.assertTrue(block["tree"])
            self.assertEqual({frozenset(bar) for bar in block["by_model"]},
                             {frozenset({"model", "tokens"})})
            self.assertEqual({frozenset(bar) for bar in block["by_agent"]},
                             {frozenset({"agent", "tokens"})})
        # issue-level aggregates
        self.assertEqual(snap["active"], {"hours": snap["active"]["hours"]})
        self.assertTrue(snap["by_model"])
        self.assertTrue(snap["by_agent"])


class E2eDesignTreeTests(ServeTestCase):
    """Scenario 3: design tree children present WITH agent attribution."""

    def test_design_tree_children_agent_attribution(self):
        snap = self.snapshot("memo-327.json")
        tree = snap["phases"]["design"]["tree"]
        tops = {node["session_id"]: node for node in tree}
        self.assertEqual(set(tops), {"h-design", "h-marathon"})
        design = tops["h-design"]
        self.assertEqual(design["tokens"]["total"], 45_850)  # whole subtree
        children = {child["title"]: child for child in design["children"]}
        self.assertEqual(set(children),
                         {"panel scout", "spec panel 2"})
        # agent attribution on every child node (dominant model_usage agent)
        self.assertEqual(children["panel scout"]["agent"], "zcode-Explore")
        self.assertEqual(children["spec panel 2"]["agent"],
                         "zcode-spec-panel-security")
        # grandchild nested under the last panel child, with its agent
        grandchild = children["spec panel 2"]["children"]
        self.assertEqual([node["session_id"] for node in grandchild],
                         ["h-design-p2-g1"])
        self.assertEqual(grandchild[0]["agent"], "zcode-plan-reviewer")
        # the grandchild's tokens are folded into the parent's subtree total
        self.assertEqual(children["spec panel 2"]["tokens"]["total"], 19_650)


class E2eImplTreeTests(ServeTestCase):
    """Scenario 4: T-folded node + standalone node; grandchild inside its
    parent's subtree total."""

    def test_impl_tree_t_fold_standalone_grandchild(self):
        snap = self.snapshot("memo-327.json")
        tree = snap["phases"]["impl"]["tree"]
        self.assertEqual([node["session_id"] for node in tree], ["c-marathon"])
        root = tree[0]
        self.assertEqual(root["tokens"]["total"], 65_500)
        by_title = {child["title"]: child for child in root["children"]}
        self.assertEqual(set(by_title), {"T1", "hotfix db"})  # folded + standalone
        t1 = by_title["T1"]
        self.assertIsNone(t1["session_id"])  # synthetic fold node
        # T1 aggregates BOTH T1-labeled children AND the grandchild under
        # the first one: (3+1+1) × 6_550 = 32_750
        self.assertEqual(t1["tokens"]["total"], 32_750)
        members = {node["session_id"] for node in t1["children"]}
        self.assertEqual(members, {"c-marathon-c1", "c-marathon-c2"})
        first = next(node for node in t1["children"]
                     if node["session_id"] == "c-marathon-c1")
        self.assertEqual([node["session_id"] for node in first["children"]],
                         ["c-marathon-c1-g1"])
        # standalone child stays unfolded, outside T1's total
        self.assertEqual(by_title["hotfix db"]["tokens"]["total"], 6_550)


class E2eBindTests(ServeTestCase):
    """Scenario 5: bind POST on unmatched AND already-matched sessions;
    child session id resolves to its ROOT; override written/replaced."""

    def _overrides(self):
        return json.loads((self.data_dir / "overrides.json")
                          .read_text(encoding="utf-8"))

    def _unmatched_ids(self):
        rows = json.loads((self.data_dir / "unmatched.json")
                          .read_text(encoding="utf-8"))
        return [row["session_id"] for row in rows]

    def test_bind_unmatched_replaced_rebind_child_resolution(self):
        self.assertEqual(self._unmatched_ids(), ["h-loose", "c-play"])

        # 1) unmatched root → memo/327/impl: moves into the issue
        status, payload = self.post_json("/api/bind", {
            "session_id": "h-loose", "project": "memo",
            "issue": 327, "phase": "impl"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["redirect"], "/#/memo/327")
        self.assertEqual(self._overrides(), {
            "h-loose": {"project": "memo", "issue": 327, "phase": "impl"}})
        snap = self.snapshot("memo-327.json")
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 72_050)
        impl_tops = {node["session_id"]
                     for node in snap["phases"]["impl"]["tree"]}
        self.assertIn("h-loose", impl_tops)  # session joined the issue
        self.assertEqual(self._unmatched_ids(), ["c-play"])  # row dropped

        # 2) rebind the SAME session → the override entry is REPLACED
        status, payload = self.post_json("/api/bind", {
            "session_id": "h-loose", "project": "memo",
            "issue": 331, "phase": "design"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["redirect"], "/#/memo/331")
        self.assertEqual(self._overrides(), {
            "h-loose": {"project": "memo", "issue": 331, "phase": "design"}})
        self.assertEqual(
            self.snapshot("memo-327.json")["phases"]["impl"]["tokens"]["total"],
            65_500)  # moved out again
        self.assertEqual(
            self.snapshot("memo-331.json")["phases"]["design"]["tokens"]["total"],
            13_100)  # solo 6_550 + h-loose 6_550

        # 3) already-matched root (auto-matched by title) → rebinding is
        #    the fix path; h-marathon leaves 327 for 331
        status, payload = self.post_json("/api/bind", {
            "session_id": "h-marathon", "project": "memo",
            "issue": 331, "phase": "design"})
        self.assertEqual(status, 200)
        snap327 = self.snapshot("memo-327.json")
        self.assertEqual(snap327["phases"]["design"]["tokens"]["total"], 45_850)
        self.assertEqual(
            self.snapshot("memo-331.json")["phases"]["design"]["tokens"]["total"],
            58_950)  # 13_100 + marathon subtree 45_850
        self.assertEqual(sorted(self._overrides()),
                         ["h-loose", "h-marathon"])

        # 4) a CHILD session id resolves to its ROOT before writing
        status, payload = self.post_json("/api/bind", {
            "session_id": "h-design-p2", "project": "memo",
            "issue": 331, "phase": "design"})
        self.assertEqual(status, 200)
        self.assertEqual(sorted(self._overrides()),
                         ["h-design", "h-loose", "h-marathon"])
        self.assertEqual(self._overrides()["h-design"],
                         {"project": "memo", "issue": 331, "phase": "design"})
        # the whole h-design family moved: 327 loses the design phase
        snap327 = self.snapshot("memo-327.json")
        self.assertEqual(set(snap327["phases"]), {"impl"})  # absent, not zero
        snap331 = self.snapshot("memo-331.json")
        self.assertEqual(snap331["phases"]["design"]["tokens"]["total"], 104_800)


class StaticFilesTests(ServeTestCase):
    """Static contract: viewer whitelist, /data/*.json, traversal and
    symlink rejection, no directory listing, method handling."""

    def test_root_serves_index_html(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b'src="app.js"', body)
        self.assertIn(b'lang="ru"', body)

    def test_viewer_assets_by_content_type(self):
        for name, fragment in (("app.js", "text/javascript"),
                               ("lib.js", "text/javascript"),
                               ("style.css", "text/css")):
            status, headers, body = self.get("/" + name)
            self.assertEqual(status, 200, name)
            self.assertIn(fragment, headers.get("Content-Type", ""), name)
            self.assertTrue(body)
        # /index.html is the same whitelist as /
        status, _, body = self.get("/index.html")
        self.assertEqual(status, 200)
        self.assertIn(b'src="lib.js"', body)

    def test_unknown_paths_404(self):
        for path in ("/favicon.ico", "/viewer/app.js", "/nope.js",
                     "/data/", "/data", "/api", "/api/other"):
            status, _, _ = self.get(path)
            self.assertEqual(status, 404, path)

    def test_data_json_files_served(self):
        status, headers, body = self.get("/data/unmatched.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        rows = json.loads(body.decode("utf-8"))
        self.assertEqual([row["session_id"] for row in rows],
                         ["h-loose", "c-play"])
        status, _, _ = self.get("/data/issues/memo-327.json")
        self.assertEqual(status, 200)
        # non-JSON data files stay unserved (no .lock, no overrides yet)
        status, _, _ = self.get("/data/.lock")
        self.assertEqual(status, 404)

    def test_path_traversal_rejected(self):
        for path in ("/data/../config.json",
                     "/data/%2e%2e/config.json",
                     "/data/..%2fconfig.json",
                     "/data//etc/passwd",
                     "/data/sub/../../server.py",
                     "/data/issues/../../../../etc/passwd"):
            status, _, _ = self.get(path)
            self.assertEqual(status, 404, path)

    def test_symlink_escape_rejected(self):
        outside = self.tmpdir / "outside.json"
        outside.write_text('{"pwned": true}', encoding="utf-8")
        os.symlink(outside, self.data_dir / "secret.json")
        status, _, _ = self.get("/data/secret.json")
        self.assertEqual(status, 404)

    def test_method_handling(self):
        status, _, _ = self.get("/api/bind")  # GET on the POST endpoint
        self.assertEqual(status, 405)
        status, _, _ = http("POST", self.base + "/data/index.json",
                            headers={"Content-Type": "application/json"},
                            body=b"{}")
        self.assertEqual(status, 404)


class GuardUnitTests(ServeTestCase):
    """Request guards and bind validation — the always-on clauses."""

    def _bind(self, payload, headers=None):
        return self.post_json("/api/bind", payload, headers=headers)

    def test_wrong_host_rejected(self):
        status, _, _ = self.get("/", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)
        # the guard is not port-spoofable and covers POST too
        status, _, _ = http(
            "POST", self.base + "/api/bind",
            headers={"Host": "127.0.0.1:9999",
                     "Content-Type": "application/json"},
            body=b'{"session_id": "h-loose", "project": "memo",'
                 b' "issue": 327, "phase": "impl"}')
        self.assertEqual(status, 403)

    def test_localhost_host_allowed(self):
        status, _, _ = self.get("/data/index.json",
                                headers={"Host": "localhost:" + str(self.port)})
        self.assertEqual(status, 200)

    def test_cross_origin_post_rejected(self):
        status, payload = self._bind(
            {"session_id": "h-loose", "project": "memo",
             "issue": 327, "phase": "impl"},
            headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertFalse((self.data_dir / "overrides.json").exists())
        # loopback origins pass the guard
        status, _ = self._bind(
            {"session_id": "h-loose", "project": "memo",
             "issue": 327, "phase": "impl"},
            headers={"Origin": "http://127.0.0.1:" + str(self.port)})
        self.assertEqual(status, 200)

    def test_wrong_content_type_415(self):
        status, _, body = http(
            "POST", self.base + "/api/bind",
            headers={"Content-Type": "text/plain"}, body=b"hello")
        self.assertEqual(status, 415)
        self.assertFalse((self.data_dir / "overrides.json").exists())
        # charset parameters on the right type are fine
        status, payload = self._bind(
            {"session_id": "h-loose", "project": "memo",
             "issue": 327, "phase": "impl"},
            headers={"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual(status, 200)

    def test_bad_json_and_shape_400(self):
        status, _, body = http("POST", self.base + "/api/bind",
                               headers={"Content-Type": "application/json"},
                               body=b"{not json")
        self.assertEqual(status, 400)
        status, payload = self._bind([1, 2, 3])  # not an object
        self.assertEqual(status, 400)
        base = {"project": "memo", "issue": 327, "phase": "design"}
        for patch in ({"session_id": None}, {"session_id": 42},
                      {"session_id": ""}, {"session_id": "h-loose",
                                           "issue": "abc"},
                      {"session_id": "h-loose", "issue": 0},
                      {"session_id": "h-loose", "issue": True}):
            status, payload = self._bind({**base, **patch})
            self.assertEqual(status, 400, patch)
            self.assertIn("error", payload)

    def test_unknown_session_400(self):
        status, payload = self._bind(
            {"session_id": "ghost-session", "project": "memo",
             "issue": 327, "phase": "design"})
        self.assertEqual(status, 400)
        self.assertIn("сесс", payload["error"])
        # validation order: session is checked BEFORE project/phase — a
        # payload wrong in both names the session
        status, payload = self._bind(
            {"session_id": "ghost-session", "project": "nope",
             "issue": 327, "phase": "design"})
        self.assertEqual(status, 400)
        self.assertIn("сесс", payload["error"])

    def test_unknown_project_and_phase_400(self):
        status, payload = self._bind(
            {"session_id": "h-loose", "project": "nope",
             "issue": 327, "phase": "design"})
        self.assertEqual(status, 400)
        self.assertIn("проект", payload["error"])
        status, payload = self._bind(
            {"session_id": "h-loose", "project": "memo",
             "issue": 327, "phase": "test"})
        self.assertEqual(status, 400)
        self.assertIn("фаз", payload["error"])

    def test_unknown_issue_400_no_phantom_snapshot(self):
        with mock.patch.object(server, "gh_issue_exists",
                               return_value=False) as gh:
            status, payload = self._bind(
                {"session_id": "h-loose", "project": "memo",
                 "issue": 9999, "phase": "design"})
        self.assertEqual(status, 400)
        gh.assert_called_once_with("mkosinov/memo", 9999)
        self.assertFalse((self.data_dir / "issues" / "memo-9999.json").exists())
        self.assertFalse((self.data_dir / "overrides.json").exists())

    def test_issue_verified_via_gh_creates_snapshot(self):
        with mock.patch.object(server, "gh_issue_exists",
                               return_value=True):
            status, payload = self._bind(
                {"session_id": "h-loose", "project": "memo",
                 "issue": 9999, "phase": "impl"})
        self.assertEqual(status, 200)
        snap = self.snapshot("memo-9999.json")
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 6_550)

    def test_lock_busy_503_nothing_written(self):
        lock_fd = os.open(os.path.join(self.data_dir, collector.LOCK_FILENAME),
                          os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)  # hold like a running collect
            with mock.patch.object(server, "LOCK_WAIT_S", 0.3):
                status, payload = self._bind(
                    {"session_id": "h-loose", "project": "memo",
                     "issue": 327, "phase": "impl"})
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "сбор идёт, повтори")
        self.assertFalse((self.data_dir / "overrides.json").exists())


class CliWiringTests(unittest.TestCase):
    """`collect.py serve`: --config plumbing + the config serve block."""

    def test_parser_accepts_config(self):
        args = collect.build_parser().parse_args(
            ["serve", "--config", "/x/config.json"])
        self.assertEqual(args.config, "/x/config.json")

    def test_serve_delegates_to_run_serve_with_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            host_db = tmpdir / "host.sqlite"
            fixtures.write_host_db(host_db, fixtures.host_scenario())
            config = {"version": 1,
                      "sources": {"zcode_host": {"db": str(host_db)}},
                      "projects": {}, "serve": {"host": "127.0.0.1",
                                                "port": 8765}}
            config_path = tmpdir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(server, "run_serve") as run_serve:
                rc = collect.main(["serve", "--config", str(config_path)])
            self.assertEqual(rc, 0)
            run_serve.assert_called_once_with(config, str(tmpdir / "data"))

    def test_run_serve_uses_serve_block_and_overrides(self):
        config = {"projects": {},
                  "serve": {"host": "127.0.0.1", "port": 8765}}
        with mock.patch.object(server, "make_server") as make_server:
            make_server.return_value.serve_forever = mock.Mock(
                side_effect=KeyboardInterrupt)
            server.run_serve(config, "/tmp/data-served")
            # config serve block honored...
            self.assertEqual(make_server.call_args.kwargs["host"], "127.0.0.1")
            self.assertEqual(make_server.call_args.kwargs["port"], 8765)
        # ...and explicit args win (the ephemeral-port injection path)
        with mock.patch.object(server, "make_server") as make_server:
            make_server.return_value.serve_forever = mock.Mock(
                side_effect=KeyboardInterrupt)
            server.run_serve(config, "/tmp/data-served",
                             host="127.0.0.1", port=0)
            self.assertEqual(make_server.call_args.kwargs["port"], 0)


if __name__ == "__main__":
    unittest.main()
