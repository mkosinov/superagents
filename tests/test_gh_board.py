"""Unit tests for gh_board.py — config identity, priority pick, Next Up strip.

Run from repo root:
    python3 -m unittest tests.test_gh_board -v

stdlib unittest only (repo has no pytest). The module under test lives in
.zcode/scripts/ (the .opencode/scripts/ copy is a byte-identical twin).

Zero-network harness: EVERY gh CLI call the script can make goes through
subprocess.run — the single transport seam. These tests install a
fixture-backed fake as subprocess.run; any call the fake cannot route
raises AssertionError, so a real network call fails the test instead of
happening (Task 3 adds the session-wide guard fixture on top).
"""
import contextlib
import hashlib
import io
import json
import re
import runpy
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
        if argv[:2] == ["gh", "pr", "list"]:
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
            return json.dumps({"data": {"repository": {"issue": {"state": self.issue_states.get(n, "CLOSED")}}}})
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
            return json.dumps({"stateReason": "COMPLETED"})
        raise AssertionError(f"unrouted gh issue view --json {which!r}")


class FrozenDatetime(datetime):
    """gb.datetime stand-in with a fixed now() for TTL-boundary tests.
    fromisoformat stays real (inherited), so log entries parse normally."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


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
# Byte-identical twins (spec Goal 2)


class TestTwinsByteIdentical(unittest.TestCase):
    def test_script_twins_are_byte_identical(self):
        a = (REPO / ".zcode" / "scripts" / "gh_board.py").read_bytes()
        b = (REPO / ".opencode" / "scripts" / "gh_board.py").read_bytes()
        self.assertEqual(
            hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    unittest.main()
