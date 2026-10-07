"""Unit tests for gh_board.py — config identity, priority pick, Next Up strip,
bookkeeping commands (status stamping matrix, gate, reconcile, merged).

Run from repo root:
    python3 -m unittest tests.test_gh_board -v

stdlib unittest only (repo has no pytest). The module under test lives in
.zcode/scripts/ (the .opencode/scripts/ copy is a byte-identical twin).

Zero-network harness: EVERY gh CLI call the script can make goes through
subprocess.run — the single transport seam. These tests install a
fixture-backed fake as subprocess.run; any call the fake cannot route
raises AssertionError, so a real network call fails the test instead of
happening. On top of the per-test fake, a session-wide guard (setUpModule)
replaces subprocess.run/Popen for the whole test-module session: a call
escaping every mock fails with the guard's AssertionError instead of
reaching the network — the zero-network claim is asserted, not accidental.
The guard is module-scoped, so it never touches the board-bootstrap tests,
which spawn real local subprocesses by design.
"""
import contextlib
import hashlib
import io
import json
import re
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".zcode" / "scripts" / "gh_board.py"
sys.path.insert(0, str(REPO / ".zcode" / "scripts"))

import gh_board as gb  # noqa: E402

# The unpatched canon path, captured before any test patches BOARD_CONFIG_PATH:
# the repo root must be parents[2] of the script itself (the twins convention).
ORIGINAL_CONFIG_PATH = gb.BOARD_CONFIG_PATH


# ---------------------------------------------------------------------------
# Session-wide zero-network guard (spec §CI: asserted, not accidental)


_REAL_SUBPROCESS_RUN = subprocess.run
_REAL_SUBPROCESS_POPEN = subprocess.Popen
"""The real primitives, captured at import (before the guard is installed).
subprocess.Popen is guarded alongside run because run shells out through it
and subprocess.call/check_call use Popen directly — every subprocess entry
point funnels through these two."""


def _zero_network_guard(*args, **kwargs):
    """Fails any code path that reaches a REAL subprocess call: on CI a `gh`
    invocation here would be a network call (and would fail token-less).
    Installed for the whole test-module session (setUpModule); each fixture
    test patches subprocess.run ON TOP of it, so mocked behavior is unchanged
    and only a call escaping every mock hits this guard."""
    raise AssertionError(
        "zero-network guard: subprocess escaped the fixture-backed mock "
        f"(args={args!r}, kwargs={kwargs!r}) — a real gh/date call would hit "
        "the network. Route the call through FakeGhBoard (GhBoardCase.setUp "
        "patches subprocess.run), or, for a deliberate LOCAL check like the "
        "bash -n test, restore _REAL_SUBPROCESS_RUN/_REAL_SUBPROCESS_POPEN "
        "explicitly for that one call.")


def setUpModule():
    subprocess.run = _zero_network_guard
    subprocess.Popen = _zero_network_guard


def tearDownModule():
    subprocess.run = _REAL_SUBPROCESS_RUN
    subprocess.Popen = _REAL_SUBPROCESS_POPEN


# ---------------------------------------------------------------------------
# Fixtures


def valid_config(**over) -> dict:
    """A board_config.json v1 body (field ids intentionally differ from the
    live field-list fixture below — proves field ids come from the config,
    while option ids come from the live read)."""
    cfg = {
        "version": 1,
        "project_id": "PVT_test_proj",
        "project_number": 4,
        "owner": "mkosinov",
        "repo": "superagents",
        "fields": {
            "Status": "PVTSSF_cfg_status",
            "Priority": "PVTSSF_cfg_priority",
            "host": "PVTSSF_cfg_host",
            "gate": "PVTSSF_cfg_gate",
        },
        "host_budgets": {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1},
    }
    cfg.update(over)
    return cfg


def opt(name: str) -> dict:
    return {"id": "OPT_" + re.sub(r"\W+", "_", name).lower(), "name": name}


def default_fields() -> dict:
    """Live single-select fields as the GraphQL field-list would return them."""
    return {
        "Status": {"id": "PVTSSF_live_status", "options": [
            opt("Hold"), opt("Backlog"), opt("In Design"), opt("Ready to IMPL"),
            opt("In IMPL"), opt("PR (G7)"), opt("In-main"), opt("Not planned")]},
        "Priority": {"id": "PVTSSF_live_priority", "options": [
            opt("Critical"), opt("High"), opt("Medium"), opt("Low")]},
        "host": {"id": "PVTSSF_live_host", "options": [
            opt("imac"), opt("macbook"), opt("hk"), opt("gcp")]},
        "gate": {"id": "PVTSSF_live_gate", "options": [
            opt("concept"), opt("spec"), opt("plan"), opt("blocked")]},
    }


def card(number: int, title: str | None = None, state: str = "OPEN",
         status: str | None = None, priority: str | None = None,
         host: str | None = None, gate: str | None = None) -> dict:
    """One ProjectV2 item in the shape items_with_fields() parses."""
    vals = [("Status", status), ("Priority", priority), ("host", host), ("gate", gate)]
    return {
        "id": f"PVTI_{number}",
        "content": {"number": number, "title": title or f"issue {number}", "state": state},
        "fieldValues": {"nodes": [
            {"name": v, "field": {"name": f}} for f, v in vals if v]},
    }


def log_comment(cid: int, login: str, body: str) -> dict:
    return {"id": cid, "user": {"login": login}, "body": body}


def completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def field_writes(board: "FakeGhBoard") -> list[tuple]:
    """(kind, field_id, option_id|None) for every board-field mutation the mock
    recorded — the update/clear GraphQL writes to Status/host/gate. Comment
    patches (tuples) and card auto-adds are excluded. Field ids come from the
    config fixture, option ids from the live field-list fixture — every
    assertion on this helper therefore also pins that pairing at write time."""
    out = []
    for m in board.mutations:
        if not isinstance(m, str):
            continue  # ("patch_comment", cid, body) from the REST seam
        if "updateProjectV2ItemFieldValue" in m:
            fid = re.search(r'fieldId: "([^"]+)"', m).group(1)
            om = re.search(r'singleSelectOptionId: "([^"]+)"', m)
            out.append(("update", fid, om.group(1) if om else None))
        elif "clearProjectV2ItemFieldValue" in m:
            fid = re.search(r'fieldId: "([^"]+)"', m).group(1)
            out.append(("clear", fid, None))
    return out


class FakeGhBoard:
    """Fixture-backed stand-in for every gh CLI call gh_board.py can make.

    Installed as subprocess.run. Routes on argv shape; unmocked calls raise
    AssertionError — the zero-network claim is asserted, not accidental.
    """

    def __init__(self, *, fields=None, items=None, issue_bodies=None,
                 issue_states=None, log_comments=None, merged_prs=None):
        self.calls: list[list] = []
        self.mutations: list = []
        self.fields = fields if fields is not None else default_fields()
        self.fields_overflow = False  # simulate >30 project fields
        self.items = items if items is not None else []
        self.issue_bodies = issue_bodies or {}
        self.issue_states = issue_states or {}  # dep lookups; default CLOSED
        self.state_reasons = {}  # issue number → stateReason (reconcile; default COMPLETED)
        self.issue_details = {}  # issue number → cmd_issue's --json document
        self.log_comments = {n: list(c) for n, c in (log_comments or {}).items()}
        self.merged_prs = merged_prs or []
        self._next_comment_id = 9001

    # -- subprocess.run seam --
    def run(self, argv, capture_output=True, text=True, **kw):
        argv = list(argv)
        self.calls.append(argv)
        return completed(self.route(argv))

    def route(self, argv):
        if argv[:3] == ["gh", "api", "graphql"]:
            return self.graphql(argv[4][len("query="):])
        if argv[:2] == ["gh", "api"] and "-X" in argv:
            return self.patch_comment(argv)
        if argv[:2] == ["gh", "api"]:
            return self.rest_get(argv[2])
        if argv[:3] == ["gh", "issue", "view"]:
            return self.issue_view_json(argv)
        if argv[:3] == ["gh", "issue", "comment"]:
            return self.create_comment(argv)
        if argv[:3] == ["gh", "pr", "list"]:
            return json.dumps(self.merged_prs)
        if argv[:1] == ["date"]:
            return "2026-10-07\n"
        raise AssertionError(f"unexpected subprocess call (unmocked gh/date?): {argv}")

    # -- GraphQL --
    def graphql(self, query: str):
        if "addProjectV2ItemById" in query:
            self.mutations.append(query)
            return json.dumps({"data": {"addProjectV2ItemById": {"item": {"id": "PVTI_new"}}}})
        if "updateProjectV2ItemFieldValue" in query or "clearProjectV2ItemFieldValue" in query:
            self.mutations.append(query)
            return json.dumps({"data": {"projectV2Item": {"id": "PVTI_x"}}})
        if "items(first: 50" in query:
            page = {"pageInfo": {"hasNextPage": False, "endCursor": ""}, "nodes": self.items}
            return json.dumps({"data": {"node": {"items": page}}})
        if "fields(first: 30)" in query:
            nodes = [{"__typename": "ProjectV2SingleSelectField", "id": v["id"],
                      "name": k, "options": v["options"]} for k, v in self.fields.items()]
            page = {"pageInfo": {"hasNextPage": self.fields_overflow}, "nodes": nodes}
            return json.dumps({"data": {"node": {"fields": page}}})
        m = re.search(r"issue\(number: (\d+)\)", query)
        if m and "repository(" in query:
            n = int(m.group(1))
            return json.dumps({"data": {"repository": {"issue": {
                "id": f"ISSUE_{n}", "title": f"issue {n}",
                "state": self.issue_states.get(n, "CLOSED")}}}})
        raise AssertionError(f"unrouted graphql query: {query[:140]}")

    # -- REST --
    def rest_get(self, path: str):
        m = re.fullmatch(r"repos/[^/]+/[^/]+/issues/(\d+)/comments", path)
        if m:
            return json.dumps(self.log_comments.get(int(m.group(1)), []))
        raise AssertionError(f"unrouted REST GET: {path}")

    def patch_comment(self, argv):
        path = argv[argv.index("PATCH") + 1]
        m = re.fullmatch(r"repos/[^/]+/[^/]+/issues/comments/(\d+)", path)
        if not m:
            raise AssertionError(f"unrouted REST PATCH: {path}")
        cid = int(m.group(1))
        body = argv[argv.index("-f") + 1][len("body="):]
        for comments in self.log_comments.values():
            for c in comments:
                if c["id"] == cid:
                    c["body"] = body
        self.mutations.append(("patch_comment", cid, body))
        return json.dumps({"id": cid})

    def create_comment(self, argv):
        n = int(argv[3])
        body = argv[argv.index("--body") + 1]
        cid = self._next_comment_id
        self._next_comment_id += 1
        self.log_comments.setdefault(n, []).append(
            {"id": cid, "user": {"login": gb.OWNER}, "body": body})
        return f"https://github.com/{gb.OWNER}/{gb.REPO}/issues/{n}#issuecomment-{cid}\n"

    def issue_view_json(self, argv):
        n = int(argv[3])
        which = argv[argv.index("--json") + 1]
        if which == "body":
            return json.dumps({"body": self.issue_bodies.get(n, "")})
        if which == "stateReason":
            return json.dumps({"stateReason": self.state_reasons.get(n, "COMPLETED")})
        if which == "number,title,state,labels,body,url":
            d = self.issue_details.get(n) or {
                "number": n, "title": f"issue {n}", "state": "OPEN",
                "labels": [], "body": "",
                "url": f"https://github.com/{gb.OWNER}/{gb.REPO}/issues/{n}"}
            return json.dumps(d)
        raise AssertionError(f"unrouted gh issue view --json {which!r}")


class FrozenDatetime(datetime):
    """gb.datetime stand-in with a fixed now() for TTL-boundary tests.
    fromisoformat stays real (inherited), so log entries parse normally."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


FROZEN_EPOCH_S = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc).timestamp()
"""The epoch second of FrozenDatetime.now() — for session-store rows whose
exact age against SESSION_IDLE_LIMIT_S must be deterministic."""


# ---------------------------------------------------------------------------
# Base case


def reset_gb_state():
    """Clean the module under test between scenarios (tests reload the config
    fixture through the patched BOARD_CONFIG_PATH)."""
    gb._CONFIG = None
    gb._LOG_PIN = {}
    gb.PROJECT_ID = gb.OWNER = gb.REPO = None
    gb.PROJECT_NUM = None
    gb.HOST_BUDGETS = {}
    gb._status_field_id = gb._status_opts = None
    gb._host_field_id = gb._host_field_opts = None
    gb._gate_field_id = gb._gate_field_opts = None


class GhBoardCase(unittest.TestCase):
    """Temp repo-root config + mocked transport + clean module state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg_path = Path(self.tmp.name) / "docs" / "board" / "board_config.json"
        self.board = FakeGhBoard()
        p1 = mock.patch.object(gb, "BOARD_CONFIG_PATH", self.cfg_path)
        p1.start()
        self.addCleanup(p1.stop)
        p2 = mock.patch("subprocess.run", self.board.run)
        p2.start()
        self.addCleanup(p2.stop)
        reset_gb_state()
        self.write_config(valid_config())
        gb.load_config()

    def write_config(self, cfg: dict):
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def run_cmd(self, fn, *args) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fn(*args)
        return out.getvalue(), err.getvalue()

    def assert_exit(self, fn, *args, needles=()) -> str:
        with self.assertRaises(SystemExit) as cm:
            fn(*args)
        msg = str(cm.exception)
        for needle in needles:
            self.assertIn(needle, msg)
        return msg


# ---------------------------------------------------------------------------
# Scenario 6: config-driven identity


class TestConfigLoading(GhBoardCase):
    def test_valid_config_loads_identity_without_network(self):
        self.assertEqual(gb.PROJECT_ID, "PVT_test_proj")
        self.assertEqual(gb.OWNER, "mkosinov")
        self.assertEqual(gb.REPO, "superagents")
        self.assertEqual(gb.PROJECT_NUM, 4)
        self.assertEqual(gb.HOST_BUDGETS, {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1})
        self.assertEqual(self.board.calls, [], "config load must make no network calls")

    def test_repo_root_is_parents2_of_the_script(self):
        expected = Path(gb.__file__).resolve().parents[2] / "docs" / "board" / "board_config.json"
        self.assertEqual(ORIGINAL_CONFIG_PATH, expected)

    def test_missing_file_exits_with_exact_adopt_hint(self):
        self.cfg_path.unlink()
        reset_gb_state()
        msg = self.assert_exit(gb.load_config)
        self.assertEqual(
            msg,
            f"board config not found: {self.cfg_path}\n"
            "run: board_bootstrap.py adopt <project-number> — it generates the config (issue #24)")

    def test_wrong_version_exits_naming_expected_version(self):
        for bad in (2, "1", True):
            with self.subTest(version=bad):
                self.write_config(valid_config(version=bad))
                reset_gb_state()
                self.assert_exit(gb.load_config, needles=("unsupported version", "expected 1"))

    def test_garbage_json_exits_with_parse_error(self):
        for garbage in ("{not json", "[]"):
            with self.subTest(garbage=garbage):
                self.cfg_path.write_text(garbage, encoding="utf-8")
                reset_gb_state()
                self.assert_exit(gb.load_config, needles=("invalid JSON",))

    def test_each_missing_required_key_is_named(self):
        for key in ("version", "project_id", "project_number", "owner", "repo", "fields", "host_budgets"):
            with self.subTest(key=key):
                cfg = valid_config()
                del cfg[key]
                self.write_config(cfg)
                reset_gb_state()
                self.assert_exit(gb.load_config, needles=(f"missing required key '{key}'",))

    def test_value_format_checks(self):
        cases = [
            ({"owner": "mkosinov!"}, "invalid owner"),
            ({"owner": "-bad"}, "invalid owner"),
            ({"repo": "bad repo"}, "invalid repo"),
            ({"project_id": "proj_123"}, "invalid project_id"),
            ({"project_id": "PVTSSF_looks_like_field"}, "invalid project_id"),
            ({"fields": {"Status": "PVT_wrong_prefix"}}, "'fields' must map"),
            ({"host_budgets": {"imac": "two"}}, "'host_budgets' must map"),
        ]
        for over, needle in cases:
            with self.subTest(over=over):
                self.write_config(valid_config(**over))
                reset_gb_state()
                self.assert_exit(gb.load_config, needles=("board config", needle))

    def test_field_ids_come_from_config_option_ids_from_live_read(self):
        gb.load_status_field()
        self.assertEqual(gb._status_field_id, "PVTSSF_cfg_status")
        self.assertEqual(gb._host_field_id, "PVTSSF_cfg_host")
        self.assertEqual(gb._gate_field_id, "PVTSSF_cfg_gate")
        self.assertEqual(gb._status_opts["Backlog"], "OPT_backlog")
        self.assertEqual(gb._host_field_opts["imac"], "OPT_imac")
        self.assertEqual(gb._gate_field_opts["blocked"], "OPT_blocked")

    def test_field_list_overflow_exits_loudly(self):
        self.board.fields_overflow = True
        self.assert_exit(gb.load_status_field, needles=("more than 30 fields",))

    def test_config_budgets_drive_the_budget_gate(self):
        self.board.items = [
            card(13, status="In IMPL", host="imac"),
            card(11, status="Ready to IMPL", priority="Critical"),
        ]
        self.write_config(valid_config(host_budgets={"imac": 1}))
        gb.load_config(force=True)
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "NONE")
        self.write_config(valid_config(host_budgets={"imac": 2}))
        gb.load_config(force=True)
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "11")


# ---------------------------------------------------------------------------
# Scenario 1: pick-next — priority order + budget pressure


class TestPickNext(GhBoardCase):
    def setUp(self):
        super().setUp()
        # GH_BOARD_HOST must not leak in from the caller's environment.
        p = mock.patch.dict("os.environ", {"GH_BOARD_HOST": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_priority_order_critical_first_tiebreak_by_number(self):
        self.board.items = [
            card(12, status="Ready to IMPL", priority="Medium"),
            card(11, status="Ready to IMPL", priority="Critical"),
            card(13, status="Ready to IMPL"),  # unset
            card(14, status="Ready to IMPL", priority="High"),
            card(15, status="Backlog", priority="Critical"),  # not eligible here
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "11")

    def test_unset_priority_sorts_after_low(self):
        self.board.items = [
            card(11, status="Ready to IMPL"),  # unset → rank 4
            card(12, status="Ready to IMPL", priority="Low"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "12")

    def test_budget_pressure_returns_none(self):
        self.board.items = [
            card(13, status="In IMPL", host="imac"),
            card(30, status="In IMPL", host="imac"),  # budget imac=2 exhausted
            card(11, status="Ready to IMPL", priority="Critical"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "NONE")

    def test_in_design_cards_do_not_count_against_budget(self):
        self.board.items = [
            card(13, status="In Design", host="imac"),
            card(14, status="In Design", host="imac"),
            card(11, status="Ready to IMPL", priority="High"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "11")

    def test_unknown_host_gets_default_budget_one(self):
        self.board.items = [
            card(13, status="In IMPL", host="pixel"),  # not in host_budgets
            card(11, status="Ready to IMPL", priority="High"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next, "pixel")
        self.assertEqual(out.strip(), "NONE")

    def test_orphan_in_impl_warns_but_does_not_block(self):
        self.board.items = [
            card(13, status="In IMPL"),  # no host: blocks no one
            card(11, status="Ready to IMPL", priority="High"),
        ]
        out, err = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "11")
        self.assertIn("warn: In IMPL cards without host", err)
        self.assertIn("#13", err)

    def test_none_on_empty_board(self):
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "NONE")

    def test_requires_a_host(self):
        self.assert_exit(gb.cmd_pick_next, needles=("pick-next needs a host",))

    def test_open_dep_is_skipped(self):
        self.board.items = [
            card(11, status="Ready to IMPL", priority="Critical"),
            card(12, status="Ready to IMPL", priority="High"),
        ]
        self.board.issue_bodies = {11: "depends-on: #20\n"}
        self.board.issue_states = {20: "OPEN"}
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "12")


# ---------------------------------------------------------------------------
# Claim freshness (TTL boundary) + canonical log pinning


class TestClaimFreshness(GhBoardCase):
    def log(self, last_entry: str):
        self.board.log_comments[11] = [
            log_comment(101, gb.OWNER, f"auto-impl log:\n- {last_entry}")]

    def pick_with_frozen_now(self) -> str:
        with mock.patch.object(gb, "datetime", FrozenDatetime):
            out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        return out.strip()

    def test_fresh_claim_at_exact_ttl_boundary_is_skipped(self):
        self.board.items = [card(11, status="Ready to IMPL", priority="Critical")]
        self.log("2026-10-07T11:00:00Z CLAIM watcher")  # exactly CLAIM_TTL_HOURS old
        self.assertEqual(self.pick_with_frozen_now(), "NONE")

    def test_claim_one_second_past_ttl_is_stale_and_picked(self):
        self.board.items = [card(11, status="Ready to IMPL", priority="Critical")]
        self.log("2026-10-07T10:59:59Z CLAIM watcher")
        self.assertEqual(self.pick_with_frozen_now(), "11")

    def test_fresh_blocked_entry_is_skipped(self):
        self.board.items = [card(11, status="Ready to IMPL", priority="Critical")]
        self.log("2026-10-07T11:30:00Z BLOCKED waiting for user")
        self.assertEqual(self.pick_with_frozen_now(), "NONE")

    def test_other_last_entry_does_not_skip(self):
        self.board.items = [card(11, status="Ready to IMPL", priority="Critical")]
        self.log("2026-10-07T11:30:00Z note just talking")
        self.assertEqual(self.pick_with_frozen_now(), "11")


class TestCanonicalLogPinning(GhBoardCase):
    def test_cold_scan_takes_oldest_owner_log_and_pins_it(self):
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER, "auto-impl log:\n- 2026-10-07T10:00:00Z CLAIM a"),
            log_comment(200, "spoof", "auto-impl log:\n- 2026-10-07T11:00:00Z CLAIM fake"),
        ]
        cid, body = gb._auto_impl_log(11)
        self.assertEqual(cid, 100)
        self.assertIn("CLAIM a", body)
        self.assertEqual(gb._LOG_PIN[11], 100)

    def test_later_prefix_match_from_another_author_is_ignored(self):
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER, "auto-impl log:\n- real"),
            log_comment(200, "spoof", "auto-impl log:\n- forged"),
        ]
        cid, body = gb._auto_impl_log(11)
        self.assertEqual((cid, gb._LOG_PIN[11]), (100, 100))
        self.assertIn("real", body)
        self.assertNotIn("forged", body)

    def test_spoof_log_posted_before_the_real_one_is_ignored(self):
        self.board.log_comments[11] = [
            log_comment(100, "spoof", "auto-impl log:\n- forged"),
            log_comment(200, gb.OWNER, "auto-impl log:\n- real"),
        ]
        cid, body = gb._auto_impl_log(11)
        self.assertEqual(cid, 200)
        self.assertIn("real", body)

    def test_all_spoofed_prefix_matches_yield_no_log(self):
        self.board.log_comments[11] = [log_comment(100, "spoof", "auto-impl log:\n- forged")]
        self.assertEqual(gb._auto_impl_log(11), (None, None))

    def test_pinned_id_wins_over_other_prefix_matches(self):
        gb._LOG_PIN[11] = 200
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER, "auto-impl log:\n- older owner log"),
            log_comment(200, gb.OWNER, "auto-impl log:\n- pinned canonical"),
        ]
        cid, body = gb._auto_impl_log(11)
        self.assertEqual(cid, 200)
        self.assertIn("pinned canonical", body)

    def test_stale_pin_falls_back_to_scan(self):
        gb._LOG_PIN[11] = 999  # deleted comment
        self.board.log_comments[11] = [log_comment(100, gb.OWNER, "auto-impl log:\n- real")]
        cid, _ = gb._auto_impl_log(11)
        self.assertEqual(cid, 100)

    def test_auto_log_create_pins_the_new_comment_id(self):
        out, _ = self.run_cmd(gb.cmd_auto_log, 11, "CLAIM test entry")
        self.assertEqual(out.strip(), "log created")
        self.assertEqual(gb._LOG_PIN[11], 9001)
        cid, body = gb._auto_impl_log(11)
        self.assertEqual(cid, 9001)
        self.assertIn("CLAIM test entry", body)
        self.assertEqual(self.board.log_comments[11][0]["user"]["login"], gb.OWNER)

    def test_auto_log_append_patches_the_pinned_comment(self):
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER, "auto-impl log:\n- 2026-10-07T10:00:00Z CLAIM first")]
        out, _ = self.run_cmd(gb.cmd_auto_log, 11, "BLOCKED second entry")
        self.assertEqual(out.strip(), "log appended")
        patches = [m for m in self.board.mutations if isinstance(m, tuple) and m[0] == "patch_comment"]
        self.assertEqual([p[1] for p in patches], [100])
        body = self.board.log_comments[11][0]["body"]
        self.assertIn("CLAIM first", body)
        self.assertIn("BLOCKED second entry", body)


# ---------------------------------------------------------------------------
# Scenario 2: pick-next-design — slot invariant + priority order


class TestPickNextDesign(GhBoardCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict("os.environ", {"GH_BOARD_HOST": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_design_slot_busy(self):
        self.board.items = [
            card(13, status="In Design", host="imac"),
            card(21, status="Backlog", priority="Critical"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "NONE (design slot busy: #13)")

    def test_all_busy_cards_are_listed(self):
        self.board.items = [
            card(13, status="In Design"),
            card(14, status="In Design"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "NONE (design slot busy: #13, #14)")

    def test_backlog_candidates_priority_ordered(self):
        self.board.items = [
            card(24, status="Backlog", priority="Low"),
            card(21, status="Backlog", priority="High"),
            card(23, status="Backlog"),  # unset → last
            card(22, status="Backlog", priority="Critical"),
            card(25, status="Ready to IMPL", priority="Critical"),  # not eligible
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "22")

    def test_no_backlog_cards(self):
        self.board.items = [card(25, status="Ready to IMPL")]
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "NONE (no Backlog cards)")

    def test_all_backlog_blocked_by_deps(self):
        self.board.items = [card(21, status="Backlog", priority="Critical")]
        self.board.issue_bodies = {21: "depends-on: #20\n"}
        self.board.issue_states = {20: "OPEN"}
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "NONE (all Backlog cards blocked by depends-on)")

    def test_design_pick_needs_no_host(self):
        self.board.items = [card(22, status="Backlog", priority="Critical")]
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "22")


# ---------------------------------------------------------------------------
# Priority never overrides status eligibility (spec §Concepts)


class TestPriorityEligibility(GhBoardCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict("os.environ", {"GH_BOARD_HOST": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_backlog_critical_is_invisible_to_pick_next(self):
        self.board.items = [
            card(40, status="Backlog", priority="Critical"),
            card(41, status="Ready to IMPL", priority="Low"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next, "imac")
        self.assertEqual(out.strip(), "41")

    def test_ready_critical_is_invisible_to_pick_next_design(self):
        self.board.items = [
            card(40, status="Backlog", priority="Low"),
            card(41, status="Ready to IMPL", priority="Critical"),
        ]
        out, _ = self.run_cmd(gb.cmd_pick_next_design)
        self.assertEqual(out.strip(), "40")


# ---------------------------------------------------------------------------
# Next Up stripped everywhere (spec Goal 1)


class TestNextUpStripped(GhBoardCase):
    def test_source_has_no_next_up_tokens(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for token in ("next-up", "next_up", "Next Up", "NEXT_UP", "cmd_shift", "cmd_next_up"):
            self.assertNotIn(token, src)

    def test_removed_commands_fall_through_to_usage(self):
        for argv in (["next-up"], ["set-next-up", "5", "1"], ["shift"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with mock.patch("sys.argv", ["gh_board.py", *argv]), \
                        contextlib.redirect_stdout(out), \
                        self.assertRaises(SystemExit) as cm:
                    runpy.run_path(str(SCRIPT), run_name="__main__")
                self.assertEqual(cm.exception.code, 1)
                self.assertIn("Usage (from repo root):", out.getvalue())

    def test_show_all_has_no_next_up_column(self):
        self.board.items = [card(11, status="Ready to IMPL", priority="High", host="imac")]
        out, _ = self.run_cmd(gb.cmd_show, "all")
        self.assertNotIn("NextUp", out)
        self.assertNotIn("Next Up", out)
        self.assertIn("Status", out)
        self.assertIn("Host", out)

    def test_show_card_has_no_next_up_line(self):
        self.board.items = [card(11, status="Ready to IMPL", host="imac")]
        out, _ = self.run_cmd(gb.cmd_show, "11")
        self.assertNotIn("Next Up", out)
        self.assertIn("Status: Ready to IMPL", out)
        self.assertIn("Host: imac", out)

    def test_show_not_on_board_hint_names_status_call_only(self):
        self.assert_exit(gb.cmd_show, "99", needles=("not on the board", "first status call"))


# ---------------------------------------------------------------------------
# Scenario 3: gate — set/clear round-trip against the mocked transport


class TestGate(GhBoardCase):
    def test_set_then_none_roundtrip(self):
        self.board.items = [card(23, status="In Design")]
        out, _ = self.run_cmd(gb.cmd_gate, 23, "concept")
        self.assertEqual(out.strip(), "#23: gate → concept")
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_gate", "OPT_concept")])
        out, _ = self.run_cmd(gb.cmd_gate, 23, "none")
        self.assertEqual(out.strip(), "#23: gate cleared")
        self.assertEqual(field_writes(self.board)[-1],
                         ("clear", "PVTSSF_cfg_gate", None))

    def test_each_valid_value_sets_the_gate_field(self):
        self.board.items = [card(23, status="In Design")]
        for value in ("concept", "spec", "plan", "blocked"):
            with self.subTest(value=value):
                out, _ = self.run_cmd(gb.cmd_gate, 23, value)
                self.assertEqual(out.strip(), f"#23: gate → {value}")
        self.assertEqual([w[2] for w in field_writes(self.board)],
                         ["OPT_concept", "OPT_spec", "OPT_plan", "OPT_blocked"])
        self.assertTrue(all(w[1] == "PVTSSF_cfg_gate"
                            for w in field_writes(self.board)))

    def test_none_clears_via_the_clear_mutation_even_when_unset(self):
        self.board.items = [card(23, status="In Design")]  # gate already empty
        out, _ = self.run_cmd(gb.cmd_gate, 23, "none")
        self.assertEqual(out.strip(), "#23: gate cleared")
        self.assertEqual(field_writes(self.board),
                         [("clear", "PVTSSF_cfg_gate", None)])

    def test_invalid_value_rejected_cleanly_without_writes(self):
        self.board.items = [card(23, status="In Design")]
        self.assert_exit(gb.cmd_gate, 23, "gadget",
                         needles=("Unknown gate 'gadget'",
                                  "Available: concept, spec, plan, blocked, none"))
        self.assertEqual(field_writes(self.board), [])

    def test_values_come_from_the_live_field_options(self):
        fields = default_fields()
        fields["gate"]["options"].append(opt("surprise"))
        self.board.fields = fields
        self.board.items = [card(23, status="In Design")]
        out, _ = self.run_cmd(gb.cmd_gate, 23, "surprise")
        self.assertIn("#23: gate → surprise", out)
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_gate", "OPT_surprise")])

    def test_value_missing_from_live_options_is_rejected(self):
        fields = default_fields()
        fields["gate"]["options"] = [o for o in fields["gate"]["options"]
                                     if o["name"] != "plan"]
        self.board.fields = fields
        self.board.items = [card(23, status="In Design")]
        self.assert_exit(gb.cmd_gate, 23, "plan", needles=("Unknown gate 'plan'",))
        self.assertEqual(field_writes(self.board), [])

    def test_gate_on_unboarded_card_auto_adds_it_first(self):
        self.board.items = []
        out, _ = self.run_cmd(gb.cmd_gate, 77, "spec")
        self.assertIn("#77: gate → spec", out)
        self.assertTrue(any(isinstance(m, str) and "addProjectV2ItemById" in m
                            for m in self.board.mutations))
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_gate", "OPT_spec")])


# ---------------------------------------------------------------------------
# Scenario 4: status — the full host/gate stamping matrix


class TestStatusStamping(GhBoardCase):
    """Spec §Concepts: entering In Design / In IMPL stamps host (arg >
    GH_BOARD_HOST > container label file; unresolved → warning); leaving those
    statuses clears host AND gate; entering PR (G7) clears gate but KEEPS host
    (the card stays owned by its machine on CI and occupies no IMPL slot)."""

    def setUp(self):
        super().setUp()
        # The ambient GH_BOARD_HOST must not leak in; the label file does not
        # exist on a host run, so the host comes from the arg or the env here.
        p = mock.patch.dict("os.environ", {"GH_BOARD_HOST": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_enter_in_design_stamps_host_from_third_arg(self):
        self.board.items = [card(31)]
        out, _ = self.run_cmd(gb.cmd_status, 31, "In Design", "macbook")
        self.assertEqual(field_writes(self.board), [
            ("update", "PVTSSF_cfg_status", "OPT_in_design"),
            ("update", "PVTSSF_cfg_host", "OPT_macbook"),
        ])
        self.assertIn("#31: Status → In Design", out)
        self.assertIn("#31: host → macbook", out)

    def test_enter_in_impl_stamps_host_from_env(self):
        self.board.items = [card(32)]
        with mock.patch.dict("os.environ", {"GH_BOARD_HOST": "imac"}):
            out, _ = self.run_cmd(gb.cmd_status, 32, "In IMPL")
        self.assertEqual(field_writes(self.board), [
            ("update", "PVTSSF_cfg_status", "OPT_in_impl"),
            ("update", "PVTSSF_cfg_host", "OPT_imac"),
        ])

    def test_enter_with_unresolved_host_warns_and_leaves_the_field(self):
        self.board.items = [card(33)]
        out, err = self.run_cmd(gb.cmd_status, 33, "In Design")
        self.assertIn("warn: host not resolved", err)
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_status", "OPT_in_design")])

    def test_enter_with_unknown_host_exits_cleanly(self):
        self.board.items = [card(34)]
        # the status write has already happened when host validation fires —
        # swallow its stdout so the unittest report stays clean
        with contextlib.redirect_stdout(io.StringIO()):
            self.assert_exit(gb.cmd_status, 34, "In Design", "pixel",
                             needles=("Unknown host 'pixel'",
                                      "Field options: imac, macbook, hk, gcp"))

    def test_leaving_in_impl_clears_host_and_gate(self):
        self.board.items = [card(35, status="In IMPL", host="imac", gate="blocked")]
        out, _ = self.run_cmd(gb.cmd_status, 35, "Ready to IMPL")
        self.assertEqual(field_writes(self.board), [
            ("update", "PVTSSF_cfg_status", "OPT_ready_to_impl"),
            ("clear", "PVTSSF_cfg_host", None),
            ("clear", "PVTSSF_cfg_gate", None),
        ])
        self.assertIn("#35: host cleared", out)
        self.assertIn("#35: gate cleared", out)

    def test_leaving_clears_only_what_is_set(self):
        self.board.items = [card(36, status="In Design")]  # no host, no gate
        out, _ = self.run_cmd(gb.cmd_status, 36, "Backlog")
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_status", "OPT_backlog")])
        self.assertNotIn("cleared", out)

    def test_entering_pr_g7_clears_gate_but_keeps_host(self):
        self.board.items = [card(37, status="In IMPL", host="imac", gate="concept")]
        out, _ = self.run_cmd(gb.cmd_status, 37, "PR (G7)")
        self.assertEqual(field_writes(self.board), [
            ("update", "PVTSSF_cfg_status", "OPT_pr_g7_"),
            ("clear", "PVTSSF_cfg_gate", None),
        ])
        self.assertIn("#37: gate cleared", out)
        self.assertNotIn("host cleared", out)
        self.assertNotIn("host →", out)  # kept: no host field write at all

    def test_entering_pr_g7_without_gate_writes_status_only(self):
        self.board.items = [card(38, status="In IMPL", host="imac")]
        out, _ = self.run_cmd(gb.cmd_status, 38, "PR (G7)")
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_status", "OPT_pr_g7_")])

    def test_leaving_pr_g7_clears_the_host(self):
        self.board.items = [card(39, status="PR (G7)", host="imac")]
        out, _ = self.run_cmd(gb.cmd_status, 39, "In-main")
        self.assertEqual(field_writes(self.board), [
            ("update", "PVTSSF_cfg_status", "OPT_in_main"),
            ("clear", "PVTSSF_cfg_host", None),
        ])
        self.assertIn("#39: host cleared", out)

    def test_unknown_status_rejected_before_any_write(self):
        self.board.items = [card(40)]
        self.assert_exit(gb.cmd_status, 40, "In Design (G1a)",
                         needles=("Unknown status 'In Design (G1a)'", "Available:"))
        self.assertEqual(field_writes(self.board), [])


# ---------------------------------------------------------------------------
# Scenario 5: reconcile — dry-run prints the plan, records zero mutations


class TestReconcile(GhBoardCase):
    """The watcher-side sweep. --dry-run must print the "would:" plan and
    issue no mutation at all; the stuck-dispatch repair triggers only past
    SESSION_IDLE_LIMIT_S of session-store silence."""

    def setUp(self):
        super().setUp()
        p = mock.patch.dict("os.environ", {"GH_BOARD_HOST": ""})
        p.start()
        self.addCleanup(p.stop)

    def make_session_db(self, rows):
        """A stand-in opencode.db with the `session` columns
        _run_session_fresh reads; time_updated is epoch milliseconds."""
        db = Path(self.tmp.name) / "opencode.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, "
                    "parent_id TEXT, time_updated INTEGER)")
        con.executemany("INSERT INTO session VALUES (?, ?, ?, ?)", rows)
        con.commit()
        con.close()
        p = mock.patch.object(gb, "SESSION_DB", db)
        p.start()
        self.addCleanup(p.stop)

    def assert_no_mutations(self):
        self.assertEqual(field_writes(self.board), [])
        self.assertEqual([m for m in self.board.mutations if isinstance(m, tuple)], [])
        self.assertFalse(any(isinstance(m, str) and "addProjectV2ItemById" in m
                             for m in self.board.mutations))

    def test_closed_issue_in_in_impl_dry_run_prints_plan_without_mutations(self):
        self.board.items = [card(13, state="CLOSED", status="In IMPL", host="imac")]
        self.board.merged_prs = [{"number": 55, "title": "Fix the thing",
                                  "body": "Closes #13"}]
        out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertIn("would: #13: closed issue in In IMPL → In-main (PR #55)", out)
        self.assert_no_mutations()

    def test_closed_issue_target_not_planned_in_dry_run(self):
        self.board.items = [card(13, state="CLOSED", status="In IMPL")]
        self.board.state_reasons[13] = "NOT_PLANNED"
        out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertIn("would: #13: closed issue in In IMPL → Not planned "
                      "(closing PR not found)", out)
        self.assert_no_mutations()

    def test_closed_issue_in_pr_g7_swept_in_dry_run(self):
        self.board.items = [card(14, state="CLOSED", status="PR (G7)")]
        out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertIn("would: #14: closed issue in PR (G7) → In-main", out)
        self.assert_no_mutations()

    def test_open_pr_g7_card_is_untouched(self):
        self.board.items = [card(15, status="PR (G7)")]  # legitimately on CI
        out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertEqual(out, "")
        self.assertFalse(any("stateReason" in argv for argv in self.board.calls))
        self.assert_no_mutations()

    def test_unowned_in_impl_past_idle_limit_prints_plan_without_mutations(self):
        self.board.items = [card(16, status="In IMPL")]
        stale_ms = int((datetime.now(timezone.utc).timestamp() - 2 * 3600) * 1000)
        self.make_session_db([("s1", "#16 IMPL.task", None, stale_ms)])
        out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertIn("would: #16: In IMPL with sessions silent >60min"
                      " → BLOCKED auto-log entry + Ready to IMPL", out)
        self.assert_no_mutations()

    def test_idle_threshold_respected_at_the_boundary(self):
        # exactly SESSION_IDLE_LIMIT_S silent = still fresh; one second past = stuck
        self.board.items = [card(13, status="In IMPL"), card(14, status="In IMPL")]
        self.make_session_db([
            ("s1", "#13 IMPL.task", None,
             int((FROZEN_EPOCH_S - gb.SESSION_IDLE_LIMIT_S) * 1000)),
            ("s2", "#14 IMPL.task", None,
             int((FROZEN_EPOCH_S - gb.SESSION_IDLE_LIMIT_S - 1) * 1000)),
        ])
        with mock.patch.object(gb, "datetime", FrozenDatetime):
            out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertNotIn("#13", out)
        self.assertIn("would: #14: In IMPL with sessions silent >60min", out)
        self.assert_no_mutations()

    def test_fresh_session_keeps_the_card(self):
        self.board.items = [card(17, status="In IMPL")]
        fresh_ms = int((datetime.now(timezone.utc).timestamp() - 60) * 1000)
        self.make_session_db([("s1", "#17 IMPL.task", None, fresh_ms)])
        out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertEqual(out, "")
        self.assert_no_mutations()

    def test_other_hosts_card_is_not_swept(self):
        self.board.items = [card(18, status="In IMPL", host="macbook")]
        out, _ = self.run_cmd(gb.cmd_reconcile, "imac", True)
        self.assertEqual(out, "")
        self.assertFalse(any("stateReason" in argv for argv in self.board.calls))

    def test_orphaned_claim_without_session_rows_is_swept(self):
        # claimed, but no session ever wrote: the /proc fallback decides —
        # a dead fallback (no run process) means the dispatch died before start
        self.board.items = [card(19, status="In IMPL")]
        self.make_session_db([])
        with mock.patch.object(gb, "_impl_run_alive", return_value=False):
            out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertIn("would: #19: In IMPL with sessions silent >60min", out)
        self.assert_no_mutations()

    def test_live_run_process_without_session_rows_is_fresh(self):
        self.board.items = [card(20, status="In IMPL")]
        self.make_session_db([])
        with mock.patch.object(gb, "_impl_run_alive", return_value=True):
            out, _ = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertEqual(out, "")

    def test_missing_session_store_skips_the_stuck_check(self):
        self.board.items = [card(21, status="In IMPL")]
        p = mock.patch.object(gb, "SESSION_DB", Path(self.tmp.name) / "absent.db")
        p.start()
        self.addCleanup(p.stop)
        out, err = self.run_cmd(gb.cmd_reconcile, None, True)
        self.assertIn("session store not found", err)
        self.assertEqual(out, "")
        self.assert_no_mutations()

    def test_non_dry_run_closed_issue_flips_and_records_merged(self):
        self.board.items = [card(13, state="CLOSED", status="In IMPL", host="imac")]
        self.board.merged_prs = [{"number": 55, "title": "Fix the thing",
                                  "body": "Closes #13"}]
        sp = Path(self.tmp.name) / "scratchpad.md"
        sp.write_text("# Scratchpad\n", encoding="utf-8")
        p = mock.patch.object(gb, "SCRATCHPAD", sp)
        p.start()
        self.addCleanup(p.stop)
        out, _ = self.run_cmd(gb.cmd_reconcile, None, False)
        self.assertIn("#13: closed issue in In IMPL → In-main (PR #55)", out)
        self.assertNotIn("would:", out)
        self.assertEqual(field_writes(self.board), [
            ("update", "PVTSSF_cfg_status", "OPT_in_main"),
            ("clear", "PVTSSF_cfg_host", None),
        ])
        self.assertIn("- 2026-10-07 #13 Fix the thing → PR #55",
                      sp.read_text(encoding="utf-8"))

    def test_non_dry_run_stuck_card_blocks_and_flips(self):
        self.board.items = [card(22, status="In IMPL")]
        stale_ms = int((datetime.now(timezone.utc).timestamp() - 2 * 3600) * 1000)
        self.make_session_db([("s1", "#22 IMPL.task", None, stale_ms)])
        out, _ = self.run_cmd(gb.cmd_reconcile, None, False)
        self.assertIn("#22: In IMPL with sessions silent >60min"
                      " → BLOCKED auto-log entry + Ready to IMPL", out)
        self.assertNotIn("would:", out)
        self.assertEqual(field_writes(self.board),
                         [("update", "PVTSSF_cfg_status", "OPT_ready_to_impl")])
        body = self.board.log_comments[22][0]["body"]
        self.assertIn("BLOCKED reconciler", body)


# ---------------------------------------------------------------------------
# auto-log read-merge-append — non-overlapping cycles keep each other's lines


class TestAutoLogMerge(GhBoardCase):
    def test_non_overlapping_cycles_keep_each_others_lines(self):
        # Cycle 1 completes fully (read → merge → patch) before cycle 2 reads:
        # the documented non-overlapping case must lose nothing.
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER,
                        "auto-impl log:\n- 2026-10-07T10:00:00Z CLAIM first")]
        self.run_cmd(gb.cmd_auto_log, 11, "CLAIM second")
        self.run_cmd(gb.cmd_auto_log, 11, "CLAIM third")
        body = self.board.log_comments[11][0]["body"]
        for fragment in ("CLAIM first", "CLAIM second", "CLAIM third"):
            self.assertIn(fragment, body)
        self.assertLess(body.index("CLAIM second"), body.index("CLAIM third"))

    def test_appended_entry_line_format(self):
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER,
                        "auto-impl log:\n- 2026-10-07T10:00:00Z CLAIM first")]
        self.run_cmd(gb.cmd_auto_log, 11, "BLOCKED net down")
        last = self.board.log_comments[11][0]["body"].splitlines()[-1]
        self.assertRegex(last, r"^- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z BLOCKED net down$")


# ---------------------------------------------------------------------------
# merged — scratchpad append, MERGED_MAX=5, idempotent


class TestMerged(GhBoardCase):
    def setUp(self):
        super().setUp()
        self.sp = Path(self.tmp.name) / "scratchpad.md"
        p = mock.patch.object(gb, "SCRATCHPAD", self.sp)
        p.start()
        self.addCleanup(p.stop)

    def write_sp(self, text: str):
        self.sp.write_text(text, encoding="utf-8")

    def test_merged_max_contract(self):
        self.assertEqual(gb.MERGED_MAX, 5)

    def test_creates_block_right_under_the_file_title(self):
        self.write_sp("# Scratchpad\n\n## Session\n- doing things\n")
        out, _ = self.run_cmd(gb.cmd_merged, 11, 55, "Fix the thing")
        self.assertEqual(
            self.sp.read_text(encoding="utf-8"),
            "# Scratchpad\n\n## Recently merged\n"
            "- 2026-10-07 #11 Fix the thing → PR #55\n\n## Session\n- doing things\n")
        self.assertIn("Recently merged: - 2026-10-07 #11 Fix the thing → PR #55", out)
        self.assertIn("block now holds 1/5 entries", out)

    def test_newest_first_and_trimmed_to_five(self):
        old = [f"- 2026-09-0{i} #{i} old → PR #{i}" for i in range(1, 6)]
        self.write_sp("# Scratchpad\n\n## Recently merged\n" + "\n".join(old) + "\n")
        out, _ = self.run_cmd(gb.cmd_merged, 12, 60, "Newest")
        content = self.sp.read_text(encoding="utf-8")
        self.assertIn("- 2026-10-07 #12 Newest → PR #60", content)
        self.assertLess(content.index("#12 Newest"), content.index("#1 old"))
        self.assertIn("block now holds 5/5 entries", out)
        self.assertNotIn("#5 old", content)  # the oldest entry was trimmed off

    def test_idempotent_replay_is_a_no_op(self):
        before = ("# Scratchpad\n\n## Recently merged\n"
                  "- 2026-10-07 #11 Fix the thing → PR #55\n")
        self.write_sp(before)
        out, _ = self.run_cmd(gb.cmd_merged, 11, 55, "Fix the thing")
        self.assertIn("Already recorded: #11 → PR #55", out)
        self.assertEqual(self.sp.read_text(encoding="utf-8"), before)

    def test_line_format_without_title(self):
        self.write_sp("# Scratchpad\n")
        out, _ = self.run_cmd(gb.cmd_merged, 11, 55)
        self.assertIn("Recently merged: - 2026-10-07 #11 → PR #55", out)
        self.assertIn("block now holds 1/5 entries", out)

    def test_block_does_not_swallow_the_next_section(self):
        self.write_sp("# Scratchpad\n\n## Recently merged\n"
                      "- 2026-09-30 #9 old → PR #9\n\n## Notes\n- keep me\n")
        self.run_cmd(gb.cmd_merged, 12, 60, "Newest")
        content = self.sp.read_text(encoding="utf-8")
        self.assertIn("## Notes", content)
        self.assertIn("- keep me", content)
        self.assertLess(content.index("→ PR #60"), content.index("→ PR #9"))

    def test_missing_scratchpad_exits_with_the_path(self):
        self.assert_exit(gb.cmd_merged, 11, 55,
                         needles=("scratchpad not found at", str(self.sp)))


# ---------------------------------------------------------------------------
# host / auto-state / issue / show — token and view helpers


class TestHostToken(GhBoardCase):
    def test_prints_the_host_field_value(self):
        self.board.items = [card(11, status="In IMPL", host="imac")]
        out, _ = self.run_cmd(gb.cmd_host, 11)
        self.assertEqual(out, "imac\n")

    def test_silent_when_the_card_has_no_host(self):
        self.board.items = [card(12, status="In Design")]
        out, _ = self.run_cmd(gb.cmd_host, 12)
        self.assertEqual(out, "")

    def test_exits_when_the_card_is_not_on_the_board(self):
        self.assert_exit(gb.cmd_host, 99, needles=("not on the board",))


class TestAutoState(GhBoardCase):
    def test_prints_the_last_log_entry(self):
        self.board.log_comments[11] = [
            log_comment(100, gb.OWNER,
                        "auto-impl log:\n- 2026-10-07T10:00:00Z CLAIM first"
                        "\n- 2026-10-07T11:00:00Z BLOCKED second")]
        out, _ = self.run_cmd(gb.cmd_auto_state, 11)
        self.assertEqual(out, "2026-10-07T11:00:00Z BLOCKED second\n")

    def test_silent_without_a_log_comment(self):
        out, _ = self.run_cmd(gb.cmd_auto_state, 11)
        self.assertEqual(out, "")

    def test_silent_when_the_log_has_no_entry_lines(self):
        self.board.log_comments[11] = [log_comment(100, gb.OWNER, "auto-impl log:\n")]
        out, _ = self.run_cmd(gb.cmd_auto_state, 11)
        self.assertEqual(out, "")


class TestIssueView(GhBoardCase):
    def seed(self, n=11, **over):
        d = {"number": n, "title": "Do the thing", "state": "OPEN",
             "labels": [{"name": "bug"}, {"name": "board"}],
             "body": "line 1\nline 2",
             "url": f"https://github.com/{gb.OWNER}/{gb.REPO}/issues/{n}"}
        d.update(over)
        self.board.issue_details[n] = d

    def test_renders_header_labels_url_and_body(self):
        self.seed()
        out, _ = self.run_cmd(gb.cmd_issue, 11)
        self.assertIn("#11 [OPEN] Do the thing", out)
        self.assertIn("  Labels: bug, board", out)
        self.assertIn(f"https://github.com/{gb.OWNER}/{gb.REPO}/issues/11", out)
        self.assertIn("line 1\nline 2", out)

    def test_no_labels_line_when_unlabeled(self):
        self.seed(labels=[])
        out, _ = self.run_cmd(gb.cmd_issue, 11)
        self.assertNotIn("Labels:", out)

    def test_body_capped_at_120_lines(self):
        self.seed(body="\n".join(f"line {i}" for i in range(1, 131)))
        out, _ = self.run_cmd(gb.cmd_issue, 11)
        self.assertIn("line 120", out)
        self.assertNotIn("line 121", out)
        self.assertIn("... [body truncated, 10 more lines]", out)


class TestShowBookkeeping(GhBoardCase):
    def test_show_all_lists_gate_and_host_columns(self):
        self.board.items = [card(11, status="In Design", host="imac", gate="concept")]
        out, _ = self.run_cmd(gb.cmd_show, "all")
        self.assertIn("Gate", out)
        self.assertIn("concept", out)
        self.assertIn("imac", out)

    def test_show_card_prints_gate_line(self):
        self.board.items = [card(11, status="In Design", gate="spec")]
        out, _ = self.run_cmd(gb.cmd_show, "11")
        self.assertIn("  Gate: spec", out)

    def test_show_rejects_other_arguments(self):
        self.assert_exit(gb.cmd_show, "gadget",
                         needles=("argument must be an issue number or 'all'",))


# ---------------------------------------------------------------------------
# Byte-identical twins (spec Goal 2)


class TestTwinsByteIdentical(unittest.TestCase):
    """Spec Goal 2: byte-identical twins within the repo, mechanically
    guarded by sha256 comparison."""

    def test_script_twins_are_byte_identical(self):
        a = (REPO / ".zcode" / "scripts" / "gh_board.py").read_bytes()
        b = (REPO / ".opencode" / "scripts" / "gh_board.py").read_bytes()
        self.assertEqual(
            hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())

    def test_github_board_skill_twins_are_byte_identical(self):
        a = (REPO / ".zcode" / "skills" / "github-board" / "SKILL.md").read_bytes()
        b = (REPO / ".opencode" / "skills" / "github-board" / "SKILL.md").read_bytes()
        self.assertTrue(a and b, "both skill twins must exist and be non-empty")
        self.assertEqual(
            hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())


# ---------------------------------------------------------------------------
# Watcher syntax — bash -n over the container template (spec CI: the loop
# logic itself stays live-observation-only)


class TestWatcherScriptSyntax(unittest.TestCase):
    def test_auto_impl_watch_sh_parses(self):
        script = REPO / ".opencode" / "scripts" / "auto_impl_watch.sh"
        self.assertTrue(script.is_file(), f"watcher template missing: {script}")
        # The session-wide zero-network guard blocks every subprocess for the
        # whole module; lift it for this one deliberately LOCAL, non-network
        # syntax check. Both primitives are restored because subprocess.run
        # shells out through Popen.
        with mock.patch.object(subprocess, "run", _REAL_SUBPROCESS_RUN), \
                mock.patch.object(subprocess, "Popen", _REAL_SUBPROCESS_POPEN):
            r = subprocess.run(["bash", "-n", str(script)],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, f"bash -n rejected {script.name}:\n{r.stderr}")
        self.assertEqual(r.stdout, "")


# ---------------------------------------------------------------------------
# Live-options read — loud-overflow-exit variant of the #24 pagination rule


class TestLiveOptionsLoudOverflow(GhBoardCase):
    """load_status_field (one query serves the Status/host/gate option lists)
    reads a single UNPAGINATED fields(first: 30) page and exits loudly on
    hasNextPage — a truncated list must never be silently trusted, and the
    failure must precede any field write."""

    def fields_queries(self) -> list[str]:
        return [argv[4][len("query="):] for argv in self.board.calls
                if argv[:3] == ["gh", "api", "graphql"]
                and "fields(first: 30)" in argv[4]]

    def test_single_non_paginated_fields_query(self):
        gb.load_status_field()
        self.assertEqual(len(self.board.calls), 1,
                         "the live-options read is exactly one gql call")
        queries = self.fields_queries()
        self.assertEqual(len(queries), 1)
        self.assertNotIn("after:", queries[0],
                         "no cursor pagination — the loud exit replaces it")
        self.assertIn("pageInfo { hasNextPage }", queries[0])
        self.assertEqual(self.board.mutations, [])

    def test_overflow_exits_loudly_refusing_to_guess(self):
        self.board.fields_overflow = True
        self.assert_exit(gb.load_status_field, needles=(
            f"project {gb.PROJECT_NUM} has more than 30 fields",
            "refusing to guess option ids"))
        self.assertEqual(self.board.mutations, [],
                         "a truncated read must precede no field write")


if __name__ == "__main__":
    unittest.main()
