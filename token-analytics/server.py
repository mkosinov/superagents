"""server.py — `collect serve`: static viewer + JSON + POST /api/bind.

`ThreadingHTTPServer` (spec §Viewer): browsers pre-open sockets and a
bind-triggered rebuild must not stall serving, so requests are handled
on worker threads. Serves the static `viewer/` directory (a fixed file
whitelist — no directory listing), `data/*.json` snapshots (read-only,
traversal- and symlink-proofed), and exactly one POST endpoint:

  POST /api/bind {session_id, project, issue, phase}

The bind accepts ANY session id known to the last snapshot set — root
or child, matched or unmatched (rebinding a wrongly auto-matched
session is the normal fix path) — and resolves it to its ROOT before
writing the override, because overrides are keyed by root session id
(the same key `group_by_root` aggregates under). It then runs the same
full in-process rebuild as `collect`, under the same exclusive flock
on `data/.lock`: a bounded ~10 s retry, then 503 «сбор идёт, повтори».

Request guards (spec §Safety & privacy — always on, every request):
Host must be the bound loopback host:port (DNS-rebinding), a POST
bearing a non-loopback non-null Origin is rejected (CSRF), and POST
accepts only Content-Type: application/json. No path parameters
anywhere; the endpoint's own write surface is exactly one file,
`overrides.json`, via the atomic helper.
"""

import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import collector
import writeback

DEFAULT_VIEWER_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "viewer")

# Static viewer whitelist: URL path → file under viewer/ (spec §Viewer:
# index.html + app.js + lib.js + style.css, no build step, nothing else).
VIEWER_ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/lib.js": "lib.js",
    "/style.css": "style.css",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

LOCK_WAIT_S = 10.0          # bind rebuild waits for a running collect…
LOCK_RETRY_S = 0.2          # …polling the flock at this cadence
BUSY_MESSAGE = "сбор идёт, повтори"  # 503 body, verbatim per spec
MAX_BODY_BYTES = 1 << 20    # a bind payload is a few hundred bytes

LOOPBACK_NAMES = ("127.0.0.1", "localhost")


def _warn(message: str) -> None:
    """Warnings to stderr, the collector convention (README cron note)."""
    print("warning: " + message, file=sys.stderr)


def gh_issue_exists(repo: str, issue: int) -> bool:
    """`gh issue view -R <repo> <N>` (argv list, managed CLI only) — the
    bind's issue-existence check when no snapshot exists yet. Any
    invocation failure (no gh, no network, closed repo…) is simply
    «does not exist»: a typo must get a 400, never a phantom snapshot."""
    argv = ["gh", "issue", "view", "-R", repo, str(issue),
            "--json", "number"]
    try:
        proc = subprocess.run(argv, capture_output=True,
                              timeout=collector.GH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn("gh_issue_exists " + repo + " #" + str(issue) + ": " + str(exc))
        return False
    return proc.returncode == 0


def acquire_lock(data_dir, wait_s=None):
    """Exclusive flock on data/.lock with a bounded retry → (fd, True),
    or (None, False) after ~wait_s. `collect` skips on contention; the
    bind endpoint instead waits briefly, then reports 503."""
    if wait_s is None:
        wait_s = LOCK_WAIT_S  # read at call time — tests shrink it
    directory = os.fspath(data_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, collector.LOCK_FILENAME)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, True
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None, False
            time.sleep(LOCK_RETRY_S)


def _map_tree(node: dict, root_id, roots: dict) -> None:
    """Record every session id in a snapshot tree node's subtree as
    belonging to `root_id` (the tree's top session — overrides are keyed
    by root, the same key group_by_root aggregates under)."""
    session_id = node.get("session_id")
    if session_id is not None and root_id is not None \
            and session_id not in roots:
        roots[session_id] = root_id
    for child in node.get("children") or []:
        _map_tree(child, root_id, roots)


def _load_json(path: str):
    """Read a JSON file → parsed value, or None on any failure (a torn
    or hand-mangled data file must not kill the request thread)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


class ServeApp:
    """Everything the handlers need, independent of socket plumbing:
    the config, the data dir to serve JSON from, the viewer dir."""

    def __init__(self, config: dict, data_dir, viewer_dir=None):
        self.config = config
        self.data_dir = os.fspath(data_dir)
        self.viewer_dir = os.path.abspath(
            viewer_dir if viewer_dir is not None else DEFAULT_VIEWER_DIR)

    # --- the last snapshot set → {any known session id → root id} ----

    def session_roots(self) -> dict:
        """Session ids of the LAST snapshot set (matched trees walk for
        children and grandchildren; unmatched rows carry their root id)
        → the root id each belongs to. This is the bind's known-session
        universe and its child→root resolution."""
        roots: dict = {}
        issues_dir = os.path.join(self.data_dir, "issues")
        try:
            names = sorted(os.listdir(issues_dir))
        except OSError:
            names = []
        for name in names:
            if not name.endswith(".json"):
                continue
            snapshot = _load_json(os.path.join(issues_dir, name))
            if not isinstance(snapshot, dict):
                continue
            for block in (snapshot.get("phases") or {}).values():
                if not isinstance(block, dict):
                    continue
                for top in block.get("tree") or []:
                    if isinstance(top, dict):
                        _map_tree(top, top.get("session_id"), roots)
        rows = _load_json(
            os.path.join(self.data_dir, collector.UNMATCHED_FILENAME))
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("session_id") \
                        and row["session_id"] not in roots:
                    roots[row["session_id"]] = row["session_id"]
        return roots

    def snapshot_path(self, project: str, issue: int) -> str:
        return os.path.join(self.data_dir, collector.ISSUES_DIRNAME,
                            str(project) + "-" + str(issue) + ".json")

    # --- the bind endpoint (validation order per the design contract) --

    def bind(self, payload) -> tuple[int, dict]:
        """Validate + apply one bind: guards are the handler's job; here
        JSON shape → session known (root-or-child resolution) → project
        enum → phase enum → issue exists (snapshot or gh) → write the
        override atomically → full rebuild under data/.lock → the issue
        page path."""
        if not isinstance(payload, dict):
            return 400, {"error": "тело запроса — JSON-объект"}
        session_id = payload.get("session_id")
        project = payload.get("project")
        phase = payload.get("phase")
        if not isinstance(session_id, str) or not session_id:
            return 400, {"error": "не указан id сессии (session_id)"}
        if not isinstance(project, str) or not project:
            return 400, {"error": "не указан проект (project)"}
        if not isinstance(phase, str) or not phase:
            return 400, {"error": "не указана фаза (phase)"}

        root_id = self.session_roots().get(session_id)
        if root_id is None:
            return 400, {"error": "неизвестная сессия: " + session_id}
        projects = self.config.get("projects") or {}
        if project not in projects:
            return 400, {"error": "неизвестный проект: " + project}
        if phase not in collector.PHASES:
            return 400, {"error": "фаза должна быть design или impl"}
        issue = collector._coerce_issue(payload.get("issue"))
        if issue is None:
            return 400, {"error": "номер задачи — целое число больше нуля"}
        repo = (projects.get(project) or {}).get("repo") or ""
        if not os.path.exists(self.snapshot_path(project, issue)) \
                and not gh_issue_exists(repo, issue):
            return 400, {"error": "задача #" + str(issue)
                         + " не найдена (нет снимка, gh не подтвердил)"}

        lock_fd, locked = acquire_lock(self.data_dir)
        if not locked:
            return 503, {"error": BUSY_MESSAGE}
        assert lock_fd is not None  # locked implies a held fd
        try:
            # The endpoint's single own write: overrides.json, atomically
            # (tmp + os.replace), keyed by ROOT session id — a rebind of
            # the same root replaces its entry in place.
            overrides = collector.load_overrides(self.data_dir)
            overrides[root_id] = {"project": project, "issue": issue,
                                  "phase": phase}
            collector.save_overrides(self.data_dir, overrides)
            # The same full rebuild a collect run performs, in-process,
            # under the same lock (readers → rebuild → write-back hook).
            host = collector._read_host_source(self.config)
            container = collector._read_container_source(self.config)
            collector.rebuild(host, container, self.config, self.data_dir)
            writeback.run_after_rebuild(self.config, self.data_dir)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        return 200, {
            "ok": True,
            "redirect": "/#/" + project + "/" + str(issue),
            "project": project,
            "issue": issue,
            "phase": phase,
            "root_session_id": root_id,
        }


class AnalyticsHandler(BaseHTTPRequestHandler):
    """HTTP plumbing only: guards, routing, byte sending. All analytics
    logic lives in ServeApp (and collector) — the handler stays thin."""

    server_version = "token-analytics-serve"
    protocol_version = "HTTP/1.1"   # keep-alive; every reply carries Length
    timeout = 30                    # a stalled client frees its worker thread
    _replied = False                # one response per request, even on errors

    @property
    def app(self) -> ServeApp:
        return self.server.app

    def log_message(self, format, *args) -> None:  # noqa: A002 — base API
        pass  # an interactive local tool, not a log sink; errors go via _warn

    # --- replies ------------------------------------------------------------

    def _send_json(self, status: int, payload) -> None:
        self._replied = True  # one response per request, even on errors
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if self.close_connection:
            # e.g. the 413 path: say the close out loud, not just do it
            self.send_header("Connection", "close")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, no_store: bool = False) -> None:
        self._replied = True
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            self._send_json(404, {"error": "не найдено"})
            return
        ctype = CONTENT_TYPES.get(os.path.splitext(path)[1],
                                  "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if no_store:
            # post-bind reloads must observe the fresh snapshots
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # --- guards (spec §Safety & privacy — one clause, always on) ------------

    def _host_allowed(self) -> bool:
        """Host must be exactly <bound-loopback-host>:<bound-port>. Loopback
        binding alone does not stop DNS rebinding — the attacker's name
        resolves here, but their Host header does not match."""
        header = self.headers.get("Host")
        if not header:
            return False
        bound_host, bound_port = self.server.server_address[:2]
        names = (LOOPBACK_NAMES if bound_host in LOOPBACK_NAMES
                 else (bound_host,))
        allowed = {name + ":" + str(bound_port) for name in names}
        return header.strip().lower() in allowed

    def _origin_allowed(self) -> bool:
        """POST Origin: absent or `null` passes (same-origin fetches and
        some privacy modes); anything non-loopback is a cross-site
        attempt — rejected (CSRF)."""
        origin = self.headers.get("Origin")
        if origin is None or origin.strip().lower() == "null":
            return True
        host = urllib.parse.urlsplit(origin.strip()).hostname
        return host in LOOPBACK_NAMES or host == "::1"

    # --- routing ------------------------------------------------------------

    def do_GET(self) -> None:
        self._safely(self._handle_get)

    def do_POST(self) -> None:
        self._safely(self._handle_post)

    def _safely(self, handler) -> None:
        self._replied = False
        try:
            handler()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser closed the socket — nothing to report
        except Exception as exc:  # a bug must not kill the server thread
            # the client gets a generic message (no exception text, no
            # paths); the operator gets the details server-side
            _warn("unhandled error on " + str(self.command) + " "
                  + str(self.path) + ": " + repr(exc))
            try:
                if not self._replied:  # never send a second response
                    self._send_json(500, {"error": "внутренняя ошибка сервера"})
            except OSError:
                pass

    def _request_path(self) -> str:
        path = urllib.parse.urlsplit(self.path).path
        return urllib.parse.unquote(path)

    def _handle_get(self) -> None:
        if not self._host_allowed():
            self._send_json(403, {"error": "запрос отклонён (Host)"})
            return
        path = self._request_path()
        if path == "/api/bind":
            self._send_json(405, {"error": "метод не поддерживается"})
            return
        if path.startswith("/data/"):
            self._serve_data(path[len("/data/"):])
            return
        name = VIEWER_ROUTES.get(path)
        if name is not None:
            self._send_file(os.path.join(self.app.viewer_dir, name))
            return
        self._send_json(404, {"error": "не найдено"})

    def _serve_data(self, rel: str) -> None:
        """`/data/<subpath>` → JSON files under the data dir only: no
        empty or dot-dot segments (before any filesystem call), `.json`
        files only, then a realpath containment check so symlinks cannot
        escape. No directory listing — directories 404."""
        if not rel or "\0" in rel:
            self._send_json(404, {"error": "не найдено"})
            return
        parts = rel.split("/")
        if any(part in ("", ".", "..") for part in parts) \
                or not parts[-1].endswith(".json"):
            self._send_json(404, {"error": "не найдено"})
            return
        candidate = os.path.join(self.app.data_dir, *parts)
        target = None
        try:
            base = os.path.realpath(self.app.data_dir)
            target = os.path.realpath(candidate)
            inside = os.path.commonpath([base, target]) == base
        except ValueError:
            inside = False
        if not inside or target is None or not os.path.isfile(target):
            self._send_json(404, {"error": "не найдено"})
            return
        self._send_file(target, no_store=True)

    def _handle_post(self) -> None:
        if not self._host_allowed():
            self._send_json(403, {"error": "запрос отклонён (Host)"})
            return
        if not self._origin_allowed():
            self._send_json(403, {"error": "запрос отклонён (Origin)"})
            return
        if self._request_path() != "/api/bind":
            self._send_json(404, {"error": "не найдено"})
            return
        media_type = (self.headers.get("Content-Type") or "") \
            .split(";")[0].strip().lower()
        if media_type != "application/json":
            self._send_json(415, {"error":
                                  "Content-Type должен быть application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            # The body stays unread, so keep-alive would desync on the
            # next request — and draining an arbitrary-size body is not
            # worth it. Close instead; _send_json adds Connection: close.
            self.close_connection = True
            self._send_json(413, {"error": "тело запроса слишком большое"})
            return
        body = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "некорректный JSON"})
            return
        status, reply = self.app.bind(payload)
        self._send_json(status, reply)


class AnalyticsServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying its ServeApp (spec §Viewer: threaded
    — a bind-triggered rebuild must not stall other requests)."""

    daemon_threads = True

    def __init__(self, address, app: ServeApp):
        super().__init__(address, AnalyticsHandler)
        self.app = app


def make_server(config: dict, data_dir, host: str = "127.0.0.1",
                port: int = 8765, viewer_dir=None) -> AnalyticsServer:
    """Bind a server (port 0 → ephemeral; guards read the real address
    back from the socket, which is what makes an ephemeral test port
    pass the Host check the production 8765 faces)."""
    app = ServeApp(config, data_dir, viewer_dir=viewer_dir)
    return AnalyticsServer((host, port), app)


def serve_address(config: dict, host: str = None,
                  port: int = None) -> tuple[str, int]:
    """Resolve the bind address: args win, else the config `serve` block,
    else 127.0.0.1:8765. `run_serve` binds these numbers, and collect's
    port-busy error message quotes the same ones."""
    block = (config.get("serve") or {}) if isinstance(config, dict) else {}
    bound_host = host or block.get("host") or "127.0.0.1"
    if port is not None:
        bound_port = int(port)
    else:
        bound_port = int(block.get("port") or 8765)
    return bound_host, bound_port


def run_serve(config: dict, data_dir, host: str = None,
              port: int = None) -> None:
    """`collect serve`: serve until Ctrl-C. Host/port from the config
    `serve` block (defaults 127.0.0.1:8765), overridable by args — the
    tests' ephemeral-port injection path."""
    bound_host, bound_port = serve_address(config, host, port)
    httpd = make_server(config, data_dir, host=bound_host, port=bound_port)
    shown = httpd.server_address if isinstance(httpd.server_address, tuple) \
        else (bound_host, bound_port)
    print("serve: http://" + shown[0] + ":" + str(shown[1])
          + " (viewer + /data/*.json + POST /api/bind)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass  # Ctrl-C is the normal way down
    finally:
        httpd.server_close()
