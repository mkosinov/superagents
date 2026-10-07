"""Tests for board write-back + the `fields` subcommand (#26 Task 8).

DoD coverage (spec §Board write-back, §Config file; user scenario 6):
- E2E scenario 6 (stubbed gh on PATH): a full `collect` pushes snapshot
  values to the board — diff-gate writes only changed fields; a gh
  failure warns and the run still exits 0; disabled project and empty
  fields make no gh calls at all; an issue not on the board is skipped
  with a note; WIP/closed alike (no status filtering anywhere);
- dot-path resolver: all 6 canonical paths resolve; an unknown path
  fails loudly (the MISSING sentinel, never a silent None);
- pagination: item-list/field-list drain a stub board past 30 items
  with an explicit --limit on every call (#24 canon);
- `fields`: missing canonical names are created (NUMBER), rerun creates
  nothing, an existing non-NUMBER name stops loudly with zero mutations;
- write-back: unknown field name → warning + that field skipped only;
  cached item id dropped on write failure, re-resolved next run;
  values written verbatim from board-ready snapshot fields («48.2»).

The fake gh mirrors the recon-verified shapes of gh 2.100.0:
- `project item-list <n> --owner O --format json --limit N` →
  {"items": [...first N...], "totalCount": T}  (each call returns a
  full stable prefix; gh pages internally, so draining = growing the
  explicit limit until totalCount is covered);
- `project field-list ...` → {"fields": [{"id","name","type"[,"options"]}],
  "totalCount": T} with type = GraphQL typename (ProjectV2Field covers
  NUMBER/TEXT/DATE; single-select/iteration are the stop-worthy kinds);
- `project item-edit --id --field-id --project-id --number`;
- `project field-create <n> --owner O --name X --data-type NUMBER`.
"""

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect  # noqa: E402
import writeback  # noqa: E402
try:
    from . import fixtures  # tests discovered as a package
except ImportError:
    import fixtures  # noqa: E402

# --- fake gh (PATH-injected, same trick as the fake docker) -------------------

FAKE_GH = """#!/usr/bin/env python3
import json, os, sys

argv = sys.argv[1:]
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")

def out(payload):
    print(json.dumps(payload))

def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None

if argv[:2] == ["issue", "list"]:
    out([])
elif argv[0] == "project" and argv[1] in ("item-list", "field-list"):
    if os.environ.get("GH_LIST_FAIL"):
        print("gh: network down", file=sys.stderr)
        sys.exit(1)
    is_items = argv[1] == "item-list"
    rows = json.load(open(os.environ["GH_ITEMS" if is_items else "GH_FIELDS"]))
    key = "items" if is_items else "fields"
    page = rows[: int(flag("--limit"))]
    mode = os.environ.get("GH_TOTAL_MODE", "")
    if mode == "omit":       # pathological: no totalCount at all
        out({key: page})
    elif mode == "lie-low":  # pathological: totalCount understates rows
        out({key: page, "totalCount": 3})
    else:
        out({key: page, "totalCount": len(rows)})
elif argv[:2] == ["project", "item-edit"]:
    item = flag("--id")
    if item in json.load(open(os.environ["GH_EDIT_FAIL"])):
        print("gh: mutation failed for " + str(item), file=sys.stderr)
        sys.exit(1)
    out({"item": {"id": item}})
elif argv[:2] == ["project", "field-create"]:
    with open(os.environ["GH_CREATED"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\\n")
    if os.environ.get("GH_CREATE_FAIL"):
        print("gh: create failed", file=sys.stderr)
        sys.exit(1)
    out({"field": {"id": "PVTF_created_" + flag("--name").replace(" ", "_")}})
else:
    print("gh: unsupported command " + " ".join(argv[:3]), file=sys.stderr)
    sys.exit(64)
"""

CANONICAL_FIELDS = {
    "Tokens total": "tokens.total_m",
    "Tokens design": "phases.design.tokens.total_m",
    "Tokens IMPL": "phases.impl.tokens.total_m",
    "Hours total": "active.hours",
    "Hours design": "phases.design.active.hours",
    "Hours impl": "phases.impl.active.hours",
}

NUMBER_FIELD_TYPE = "ProjectV2Field"  # gh's JSON typename for NUMBER fields


def _canonical_board_fields():
    """The 6 canonical fields as gh field-list rows (id = PVTNF_<n>)."""
    return [{"id": "PVTNF_" + name.replace(" ", "_"), "name": name,
             "type": NUMBER_FIELD_TYPE}
            for name in CANONICAL_FIELDS]


def _board_item(issue, item_id=None):
    """A gh item-list row for one issue (content.number is the key)."""
    return {"id": item_id or ("I" + str(issue)),
            "content": {"number": issue, "type": "Issue"},
            "title": "issue #" + str(issue)}


class FakeGh:
    """Writes the fake gh + its control files into a tmp dir.

    Control files are re-read on every invocation, so tests mutate the
    board between runs via `set_items`/`set_fields`/`set_edit_fail`.
    """

    def __init__(self, tmpdir):
        self.bindir = tmpdir / "bin"
        self.bindir.mkdir(exist_ok=True)
        fake = self.bindir / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        os.chmod(fake, 0o755)
        self.paths = {name: tmpdir / name for name in
                      ("gh-items.json", "gh-fields.json", "gh-edit-fail.json",
                       "gh-log.jsonl", "gh-created.jsonl")}
        self.reset(items=[], fields=[], edit_fail=[])
        for path in self.paths.values():
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def reset(self, items, fields, edit_fail=()):
        self.set_items(items)
        self.set_fields(fields)
        self.set_edit_fail(edit_fail)

    def set_items(self, items):
        self.paths["gh-items.json"].write_text(
            json.dumps(items), encoding="utf-8")

    def set_fields(self, fields):
        self.paths["gh-fields.json"].write_text(
            json.dumps(fields), encoding="utf-8")

    def set_edit_fail(self, item_ids):
        self.paths["gh-edit-fail.json"].write_text(
            json.dumps(list(item_ids)), encoding="utf-8")

    def env(self, **extra):
        env = {"PATH": str(self.bindir) + os.pathsep + os.environ.get("PATH", ""),
               "GH_LOG": str(self.paths["gh-log.jsonl"]),
               "GH_CREATED": str(self.paths["gh-created.jsonl"]),
               "GH_ITEMS": str(self.paths["gh-items.json"]),
               "GH_FIELDS": str(self.paths["gh-fields.json"]),
               "GH_EDIT_FAIL": str(self.paths["gh-edit-fail.json"])}
        env.update(extra)
        return env

    def log(self):
        text = self.paths["gh-log.jsonl"].read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line]

    def created(self):
        text = self.paths["gh-created.jsonl"].read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line]

    def calls(self, *prefix):
        return [argv for argv in self.log() if tuple(argv[:len(prefix)]) == tuple(prefix)]


def _flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def _write_config(tmpdir, projects, sources=None):
    config = {"version": 1,
              "sources": sources if sources is not None else {},
              "projects": projects}
    path = tmpdir / "config.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def _project_spec(*, enabled=True, fields=None, number=3, repo="mkosinov/memo",
                  phase_mode="split", directories=("/root/workspace/memo",)):
    return {
        "repo": repo, "phase_mode": phase_mode, "directories": list(directories),
        "board": {"owner": "t", "project_number": number, "project_id": "PVT_TEST"},
        "write_back": {"enabled": enabled,
                       "fields": dict(fields if fields is not None
                                      else CANONICAL_FIELDS)},
    }


def _snapshot(issue=5, project="memo", total_m=48.2, design_m=12.1, impl_m=36.1,
              hours=25.3, design_h=10.1, impl_h=15.2, with_impl=True,
              with_design=True):
    """A snapshot with the board-ready shape aggregate() produces."""
    phases = {}
    if with_design:
        phases["design"] = {"tokens": {"total": 0, "total_m": design_m},
                            "active": {"hours": design_h}}
    if with_impl:
        phases["impl"] = {"tokens": {"total": 0, "total_m": impl_m},
                          "active": {"hours": impl_h}}
    return {
        "project": project, "issue": issue, "title": "issue #" + str(issue),
        "title_source": "fallback", "last_activity": "2026-10-01",
        "collected_at": "2026-10-01T00:00:00Z",
        "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0,
                   "cache_write": 0, "total": 0, "total_m": total_m},
        "active_ms": 0, "active": {"hours": hours},
        "phases": phases, "by_model": [], "by_agent": [],
    }


def _write_snapshots(data_dir, snapshots):
    issues = data_dir / "issues"
    issues.mkdir(parents=True, exist_ok=True)
    for snap in snapshots:
        name = str(snap["project"]) + "-" + str(snap["issue"]) + ".json"
        (issues / name).write_text(json.dumps(snap, indent=2), encoding="utf-8")


def _state(data_dir):
    return json.loads((data_dir / "state.json").read_text(encoding="utf-8"))


# --- unit: dot-path resolver ---------------------------------------------------

class ResolvePathTests(unittest.TestCase):
    def test_all_six_canonical_paths_resolve(self):
        snap = _snapshot()
        expected = {
            "tokens.total_m": 48.2,
            "phases.design.tokens.total_m": 12.1,
            "phases.impl.tokens.total_m": 36.1,
            "active.hours": 25.3,
            "phases.design.active.hours": 10.1,
            "phases.impl.active.hours": 15.2,
        }
        for path, value in expected.items():
            self.assertEqual(writeback.resolve_path(snap, path), value,
                             msg=path)

    def test_unknown_path_is_missing_not_none(self):
        snap = _snapshot()
        for bad in ("tokens.total_M", "bogus.path", "phases.impl.tokens.total_m",
                    "active.hours.deep"):
            resolved = writeback.resolve_path(snap if "impl" not in bad
                                              else _snapshot(with_impl=False), bad)
            self.assertIs(resolved, writeback.MISSING, msg=bad)
            self.assertIsNotNone(resolved, msg=bad)  # no silent None


# --- unit: state cache normalization (fail-open against corrupt state) -------

class ProjectCacheTests(unittest.TestCase):
    def test_corrupt_written_entry_reset_to_empty_dict(self):
        # regression: "written": {"5": 48.2} (number, not {field: value})
        # used to AttributeError through run_collect and kill the cron
        # collect — it must normalize one level deeper, fail-open
        state = {"writeback": {"memo": {
            "items": {"5": "I5"},
            "written": {"5": 48.2, "7": {"Hours total": 1.0}}}}}
        cache = writeback._project_cache(state, "memo")
        self.assertEqual(cache["written"]["5"], {})  # reset, not crash
        self.assertEqual(cache["written"]["7"], {"Hours total": 1.0})
        self.assertEqual(cache["items"], {"5": "I5"})  # sibling intact

    def test_non_dict_levels_replaced_in_place(self):
        state = {"writeback": "junk"}
        cache = writeback._project_cache(state, "memo")
        self.assertEqual(cache, {"items": {}, "written": {}})
        root = state["writeback"]
        self.assertIsInstance(root, dict)
        self.assertIs(root["memo"], cache)  # saved back


# --- unit: pagination drain (#24 canon) ----------------------------------------

class PaginationTests(unittest.TestCase):
    def _fake(self, tmpdir):
        return FakeGh(tmpdir)

    def test_item_list_drains_stub_board_past_100_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            gh = self._fake(Path(tmp))
            items = [_board_item(n) for n in range(1, 131)]  # 130 > 30, > 100
            gh.set_items(items)
            with mock.patch.dict(os.environ, gh.env()):
                resolved = writeback.gh_item_list("t", 3)
            self.assertIsInstance(resolved, list)
            assert resolved is not None  # narrows for the type checker
            self.assertEqual(len(resolved), 130)
            numbers = {item["content"]["number"] for item in resolved}
            self.assertEqual(numbers, set(range(1, 131)))
            calls = gh.calls("project", "item-list")
            self.assertGreaterEqual(len(calls), 2)  # the loop ran >1 page
            for argv in calls:
                self.assertIn("--limit", argv)      # explicit, never default 30
                self.assertGreaterEqual(int(_flag(argv, "--limit")), 100)
            self.assertEqual(int(_flag(calls[0], "--limit")), 100)

    def test_field_list_drains_stub_board_past_100_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            gh = self._fake(Path(tmp))
            filler = [{"id": "PVTF_f" + str(i), "name": "f" + str(i),
                       "type": NUMBER_FIELD_TYPE} for i in range(120)]
            gh.set_fields(filler + _canonical_board_fields())
            with mock.patch.dict(os.environ, gh.env()):
                fields = writeback.gh_field_list("t", 3)
            self.assertIsInstance(fields, list)
            assert fields is not None  # narrows for the type checker
            self.assertEqual(len(fields), 126)
            names = {field["name"] for field in fields}
            self.assertIn("Hours impl", names)  # canonical names live past 100

    def test_totalcount_missing_returns_page_without_looping(self):
        # pathological shape: gh omits totalCount — nothing to drain
        # against, so the loop stops at the explicit page (bounded,
        # never infinite) instead of crashing or guessing
        with tempfile.TemporaryDirectory() as tmp:
            gh = self._fake(Path(tmp))
            gh.set_items([_board_item(n) for n in range(1, 131)])
            with mock.patch.dict(os.environ, gh.env(GH_TOTAL_MODE="omit")):
                resolved = writeback.gh_item_list("t", 3)
            self.assertIsInstance(resolved, list)
            assert resolved is not None
            self.assertEqual(len(resolved), 100)  # first explicit page only
            self.assertEqual(len(gh.calls("project", "item-list")), 1)

    def test_totalcount_lying_low_stops_immediately(self):
        # pathological shape: totalCount (3) understates the rows the
        # call actually returned — «covered», stop, no grow-loop
        with tempfile.TemporaryDirectory() as tmp:
            gh = self._fake(Path(tmp))
            gh.set_items([_board_item(n) for n in range(1, 131)])
            with mock.patch.dict(os.environ, gh.env(GH_TOTAL_MODE="lie-low")):
                resolved = writeback.gh_item_list("t", 3)
            self.assertIsInstance(resolved, list)
            assert resolved is not None
            self.assertEqual(len(resolved), 100)  # the full returned page
            self.assertEqual(len(gh.calls("project", "item-list")), 1)

    def test_board_over_limit_cap_warns_and_drains_partially(self):
        # pathological shape: totalCount beyond LIMIT_CAP — the drain
        # warns and returns the capped prefix, limit never exceeds the cap
        with tempfile.TemporaryDirectory() as tmp:
            gh = self._fake(Path(tmp))
            gh.set_items([_board_item(n)
                          for n in range(1, writeback.LIMIT_CAP + 2)])
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, gh.env()), \
                    contextlib.redirect_stderr(stderr):
                resolved = writeback.gh_item_list("t", 3)
            self.assertIsInstance(resolved, list)
            assert resolved is not None
            self.assertEqual(len(resolved), writeback.LIMIT_CAP)
            self.assertIn("drained partially", stderr.getvalue())
            calls = gh.calls("project", "item-list")
            limits = [int(_flag(argv, "--limit")) for argv in calls]
            self.assertEqual(limits, [writeback.PAGE_SIZE,
                                      writeback.LIMIT_CAP])
            for limit in limits:
                self.assertLessEqual(limit, writeback.LIMIT_CAP)


# --- unit: `fields` subcommand --------------------------------------------------

class FieldsCommandTests(unittest.TestCase):
    def _run(self, gh, config_path, env_extra=None):
        env = gh.env(**(env_extra or {}))
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, env), \
                contextlib.redirect_stderr(stderr):
            rc = collect.main(["fields", "--config", str(config_path)])
        return rc, stderr.getvalue()

    def test_missing_canonical_fields_created_then_rerun_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh = FakeGh(tmpdir)
            existing = [f for f in _canonical_board_fields()
                        if f["name"] in ("Tokens total", "Hours total")]
            gh.set_fields(existing)
            config = _write_config(tmpdir, {"memo": _project_spec()})
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            created = gh.created()
            self.assertEqual(len(created), 4)  # the 4 missing canonical names
            for argv in created:
                self.assertEqual(argv[:2], ["project", "field-create"])
                self.assertEqual(argv[2], "3")
                self.assertEqual(_flag(argv, "--owner"), "t")
                self.assertEqual(_flag(argv, "--data-type"), "NUMBER")
                self.assertIn(_flag(argv, "--name"), CANONICAL_FIELDS)
            self.assertEqual({_flag(argv, "--name") for argv in created},
                             set(CANONICAL_FIELDS) - {"Tokens total", "Hours total"})
            # rerun: everything present now — zero mutations
            gh.set_fields(_canonical_board_fields())
            rc, _ = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertEqual(len(gh.created()), 4)  # unchanged

    def test_existing_non_number_field_stops_loudly_zero_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh = FakeGh(tmpdir)
            clash = [{"id": "PVTSSF_x", "name": "Tokens total",
                      "type": "ProjectV2SingleSelectField",
                      "options": [{"id": "o1", "name": "one"}]}]
            gh.set_fields(clash + _canonical_board_fields()[1:])
            config = _write_config(tmpdir, {"memo": _project_spec()})
            rc, stderr = self._run(gh, config)
            self.assertNotEqual(rc, 0)               # loud stop, not fail-open
            self.assertIn("Tokens total", stderr)    # names the field
            self.assertIn("SingleSelectField", stderr)  # names the actual type
            self.assertEqual(gh.created(), [])       # zero mutations

    def test_gh_failure_warns_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh = FakeGh(tmpdir)
            gh.set_fields(_canonical_board_fields())
            config = _write_config(tmpdir, {"memo": _project_spec()})
            rc, stderr = self._run(gh, config, {"GH_LIST_FAIL": "1"})
            self.assertEqual(rc, 0)                  # fail-open
            self.assertIn("warning", stderr)

    def test_disabled_project_makes_no_gh_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh = FakeGh(tmpdir)
            gh.set_fields(_canonical_board_fields())
            config = _write_config(tmpdir, {
                "memo": _project_spec(number=3),
                "off": _project_spec(enabled=False, number=7, repo="mkosinov/off",
                                     directories=("/root/workspace/off",)),
            })
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            calls = gh.calls("project", "field-list")
            self.assertEqual(len(calls), 1)              # only memo was touched
            self.assertEqual(calls[0][2], "3")           # memo's board number
            self.assertNotIn("7", calls[0])              # never the disabled board


# --- unit/CLI: standalone `writeback` re-push -----------------------------------

class WritebackStandaloneTests(unittest.TestCase):
    def _run(self, gh, config_path, env_extra=None):
        env = gh.env(**(env_extra or {}))
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, env), \
                contextlib.redirect_stderr(stderr):
            rc = collect.main(["writeback", "--config", str(config_path)])
        return rc, stderr.getvalue()

    def _setup(self, tmpdir, snapshots, items=None, fields=None):
        gh = FakeGh(tmpdir)
        gh.set_items(items if items is not None else [_board_item(5)])
        gh.set_fields(fields if fields is not None
                      else _canonical_board_fields())
        config = _write_config(tmpdir, {"memo": _project_spec()})
        _write_snapshots(tmpdir / "data", snapshots)
        return gh, config

    def _edits(self, gh):
        return gh.calls("project", "item-edit")

    def test_diff_gate_first_run_all_then_nothing_then_only_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh, config = self._setup(tmpdir, [_snapshot()])
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            edits = self._edits(gh)
            self.assertEqual(len(edits), 6)
            self.assertEqual({_flag(argv, "--number") for argv in edits},
                             {"48.2", "12.1", "36.1", "25.3", "10.1", "15.2"})
            for argv in edits:
                self.assertEqual(_flag(argv, "--id"), "I5")
                self.assertEqual(_flag(argv, "--project-id"), "PVT_TEST")
                self.assertTrue(_flag(argv, "--field-id"))
            # rerun: nothing changed — zero writes (rounding noise never writes)
            rc, _ = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertEqual(len(self._edits(gh)), 6)
            # one field changes — exactly that field is rewritten
            snap_path = tmpdir / "data" / "issues" / "memo-5.json"
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            snap["tokens"]["total_m"] = 50.0
            snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            rc, _ = self._run(gh, config)
            self.assertEqual(rc, 0)
            new_edits = self._edits(gh)[6:]
            self.assertEqual(len(new_edits), 1)
            self.assertEqual(_flag(new_edits[0], "--number"), "50.0")
            self.assertEqual(
                _flag(new_edits[0], "--field-id"), "PVTNF_Tokens_total")
            # cache holds the last WRITTEN values
            state = _state(tmpdir / "data")
            written = state["writeback"]["memo"]["written"]["5"]
            self.assertEqual(written["Tokens total"], 50.0)
            self.assertEqual(written["Hours design"], 10.1)

    def test_unknown_field_name_warned_and_skipped_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            fields = [f for f in _canonical_board_fields()
                      if f["name"] != "Hours impl"]
            gh, config = self._setup(tmpdir, [_snapshot()], fields=fields)
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertIn("Hours impl", stderr)      # warning names the field
            self.assertIn("memo", stderr)            # …and the project
            self.assertIn("fields", stderr)          # «run `fields`» hint
            self.assertEqual(len(self._edits(gh)), 5)  # the other 5 written
            written = _state(tmpdir / "data")["writeback"]["memo"]["written"]["5"]
            self.assertNotIn("Hours impl", written)

    def test_missing_phase_path_warned_never_writes_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            snap = _snapshot(with_impl=False)  # design-only issue
            gh, config = self._setup(tmpdir, [snap])
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertEqual(stderr.count("phases.impl"), 2)  # tokens + hours
            self.assertIn("tokens.total_m", stderr)  # loud: names the path
            edits = self._edits(gh)
            self.assertEqual(len(edits), 4)
            for argv in edits:  # never a silent None/missing written
                self.assertNotIn(_flag(argv, "--number"), (None, "None", "null"))

    def test_issue_not_on_board_skipped_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh, config = self._setup(tmpdir, [_snapshot()], items=[])
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertIn("not on board", stderr)
            self.assertEqual(self._edits(gh), [])

    def test_cached_item_id_dropped_on_failure_re_resolved_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh, config = self._setup(tmpdir, [_snapshot()])
            self._run(gh, config)
            self.assertEqual(_state(tmpdir / "data")
                             ["writeback"]["memo"]["items"]["5"], "I5")
            # the write fails: warning, exit 0, cached id dropped, cache intact
            gh.set_edit_fail(["I5"])
            snap_path = tmpdir / "data" / "issues" / "memo-5.json"
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            snap["tokens"]["total_m"] = 60.0
            snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertIn("warning", stderr)
            self.assertIn("memo#5", stderr)  # failure names project + issue
            state = _state(tmpdir / "data")["writeback"]["memo"]
            self.assertNotIn("5", state["items"])          # id dropped
            self.assertEqual(state["written"]["5"]["Tokens total"], 48.2)
            # the card was re-added with a NEW id: next run re-resolves + writes
            gh.set_edit_fail([])
            gh.set_items([_board_item(5, item_id="I5NEW")])
            failed_count = len(self._edits(gh))  # 6 ok + 1 failed attempt
            rc, _ = self._run(gh, config)
            self.assertEqual(rc, 0)
            new_edits = self._edits(gh)[failed_count:]
            self.assertEqual(len(new_edits), 1)
            self.assertEqual(_flag(new_edits[0], "--id"), "I5NEW")
            self.assertEqual(_flag(new_edits[0], "--number"), "60.0")
            state = _state(tmpdir / "data")["writeback"]["memo"]
            self.assertEqual(state["items"]["5"], "I5NEW")
            self.assertEqual(state["written"]["5"]["Tokens total"], 60.0)

    def test_mixed_type_issue_values_sort_without_typeerror(self):
        # one snapshot file carries a STRING issue (hand-edit, older
        # writer): sorting int vs str must not TypeError; the string
        # issue is skipped like every other non-int issue, the int one
        # is written normally
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            snap9 = _snapshot(issue=9)
            snap9["issue"] = "9"  # hand-corrupted to a string
            gh, config = self._setup(
                tmpdir, [_snapshot(issue=5), snap9],
                items=[_board_item(5), _board_item(9)])
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            edits = self._edits(gh)
            self.assertEqual({_flag(argv, "--id") for argv in edits}, {"I5"})

    def test_written_cache_pruned_for_dropped_issue_snapshots(self):
        # entries for issues whose snapshot files no longer exist (the
        # rebuild stale-swept them) must not accumulate forever
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh, config = self._setup(
                tmpdir, [_snapshot(issue=5), _snapshot(issue=9)],
                items=[_board_item(5), _board_item(9)])
            self._run(gh, config)
            written = _state(tmpdir / "data")["writeback"]["memo"]["written"]
            self.assertEqual(set(written), {"5", "9"})
            # issue 9's snapshot disappears; its board card stays
            (tmpdir / "data" / "issues" / "memo-9.json").unlink()
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            written = _state(tmpdir / "data")["writeback"]["memo"]["written"]
            self.assertEqual(set(written), {"5"})  # pruned — no growth
            self.assertIn("pruned", stderr)        # note lands in collect.log
            # the survivor's cache is untouched: no re-write for issue 5
            self.assertEqual(len(self._edits(gh)), 12)

    def test_empty_fields_noop_disabled_project_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            gh = FakeGh(tmpdir)
            gh.set_items([_board_item(5)])
            gh.set_fields(_canonical_board_fields())
            config = _write_config(tmpdir, {
                "memo": _project_spec(fields={}),           # enabled, no fields
                "off": _project_spec(enabled=False, number=7,
                                     repo="mkosinov/off",
                                     directories=("/root/workspace/off",)),
            })
            _write_snapshots(tmpdir / "data", [_snapshot()])
            rc, stderr = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertIn("no fields", stderr.lower())      # the log note
            self.assertEqual(gh.calls("project"), [])       # zero gh project calls

    def test_field_resolution_served_by_paginated_field_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            filler = [{"id": "PVTF_f" + str(i), "name": "f" + str(i),
                       "type": NUMBER_FIELD_TYPE} for i in range(120)]
            gh, config = self._setup(
                tmpdir, [_snapshot()],
                fields=filler + _canonical_board_fields())  # canonicals > 100th
            rc, _ = self._run(gh, config)
            self.assertEqual(rc, 0)
            self.assertEqual(len(self._edits(gh)), 6)  # all resolved past page 1
            list_calls = gh.calls("project", "field-list")
            self.assertGreaterEqual(len(list_calls), 2)
            for argv in list_calls:
                self.assertIn("--limit", argv)


# --- CLI plumbing: config errors + the shared lock ------------------------------

class WritebackCliPlumbingTests(unittest.TestCase):
    def _run(self, argv):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = collect.main(argv)
        return rc, stderr.getvalue()

    def test_writeback_bad_config_exits_one_with_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "config.json"
            bad.write_text("{not json", encoding="utf-8")
            rc, stderr = self._run(["writeback", "--config", str(bad)])
            self.assertEqual(rc, 1)  # a broken config is not fail-open
            self.assertIn("writeback: cannot load config", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_fields_bad_config_exits_one_with_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "config.json"
            bad.write_text("{not json", encoding="utf-8")
            rc, stderr = self._run(["fields", "--config", str(bad)])
            self.assertEqual(rc, 1)
            self.assertIn("fields: cannot load config", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_writeback_lock_held_skips_exit_zero(self):
        # the SAME flock collect takes (shared helper): a busy lock
        # skips fail-open, exit 0, no gh calls at all
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            config = _write_config(tmpdir, {"memo": _project_spec()})
            _write_snapshots(tmpdir / "data", [_snapshot()])
            lock_path = tmpdir / "data" / ".lock"
            holder = subprocess.Popen(
                [sys.executable, "-c",
                 "import fcntl, os, time\n"
                 "fd = os.open({!r}, os.O_CREAT | os.O_RDWR)\n"
                 "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                 "print('held', flush=True)\n"
                 "time.sleep(60)".format(str(lock_path))],
                stdout=subprocess.PIPE, text=True)
            try:
                assert holder.stdout is not None
                self.assertEqual(holder.stdout.readline().strip(), "held")
                rc, stderr = self._run(["writeback", "--config", str(config)])
                self.assertEqual(rc, 0)
                self.assertIn("skipped: previous run still active", stderr)
            finally:
                holder.kill()
                holder.wait()


# --- E2E: scenario 6 — collect drives the write-back ------------------------------

FAKE_DOCKER = (
    "#!/bin/sh\n"
    "[ \"$1\" = \"exec\" ] || exit 64\n"
    "shift 2\n"
    "exec \"$@\"\n"
)


class WritebackE2ETests(unittest.TestCase):
    def _run_collect(self, gh, config_path, env_extra=None):
        env = gh.env(**(env_extra or {}))
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, env), \
                contextlib.redirect_stderr(stderr):
            rc = collect.main(["collect", "--config", str(config_path)])
        return rc, stderr.getvalue()

    def test_collect_writes_board_diff_gated_fail_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # fixture sources (same shape as test_cli's full-pipeline test)
            host_db = tmpdir / "host.sqlite"
            fixtures.write_host_db(host_db, fixtures.host_scenario())
            ctr_db = tmpdir / "opencode.db"
            fixtures.write_container_db(ctr_db, fixtures.container_scenario())
            docker_bin = tmpdir / "dbin"
            docker_bin.mkdir()
            fake_docker = docker_bin / "docker"
            fake_docker.write_text(FAKE_DOCKER, encoding="utf-8")
            os.chmod(fake_docker, 0o755)

            gh = FakeGh(tmpdir)
            gh.set_items([_board_item(327), _board_item(331)])  # 335 NOT on board
            gh.set_fields(_canonical_board_fields())
            projects = {
                "memo": _project_spec(number=3),
                "off": _project_spec(enabled=False, number=7, repo="mkosinov/off",
                                     directories=("/root/workspace/off",)),
                "empty": _project_spec(fields={}, number=8,
                                       repo="mkosinov/empty",
                                       directories=("/root/workspace/empty",)),
            }
            config = _write_config(
                tmpdir, projects,
                sources={"zcode_host": {"db": str(host_db)},
                         "opencode_container": {"container": "memo-box",
                                                "db": str(ctr_db)}})
            gh_env = gh.env()
            gh_env["PATH"] = str(docker_bin) + os.pathsep + gh_env["PATH"]

            def run(extra=None):
                env = dict(gh_env)
                env.update(extra or {})
                stderr = io.StringIO()
                with mock.patch.dict(os.environ, env), \
                        contextlib.redirect_stderr(stderr):
                    rc = collect.main(["collect", "--config", str(config)])
                return rc, stderr.getvalue()

            # --- pass 1: fresh board, everything changed -----------------------
            rc, stderr = run()
            self.assertEqual(rc, 0)
            edits = gh.calls("project", "item-edit")
            snap327 = json.loads((tmpdir / "data" / "issues" / "memo-327.json")
                                 .read_text(encoding="utf-8"))
            snap331 = json.loads((tmpdir / "data" / "issues" / "memo-331.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(len(edits), 10)  # 327: 6 fields, 331: 4 (design-only)
            # values written verbatim from the board-ready snapshot fields
            written_pairs = {( _flag(a, "--id"), _flag(a, "--field-id"),
                               _flag(a, "--number")) for a in edits}
            for snap, item_id in ((snap327, "I327"), (snap331, "I331")):
                for name, path in CANONICAL_FIELDS.items():
                    value = writeback.resolve_path(snap, path)
                    if value is writeback.MISSING:
                        continue  # 331's impl side: warned + skipped below
                    self.assertIn(
                        (item_id, "PVTNF_" + name.replace(" ", "_"), str(value)),
                        written_pairs, msg=name)
            self.assertIn("not on board", stderr)          # 335 skipped with note
            self.assertIn("phases.impl.tokens.total_m", stderr)  # 331 impl absent
            # disabled + empty-fields projects: zero gh traffic for their boards
            for argv in gh.calls("project"):
                self.assertNotEqual(argv[2], "7")
                self.assertNotEqual(argv[2], "8")
            state = _state(tmpdir / "data")["writeback"]["memo"]
            self.assertEqual(state["items"]["327"], "I327")

            # --- pass 2: nothing changed — zero writes ------------------------
            base = len(gh.log())
            rc, _ = run()
            self.assertEqual(rc, 0)
            self.assertEqual(len(gh.calls("project", "item-edit")[len(edits):]), 0)
            self.assertGreater(len(gh.log()), base)  # reads still happen

            # --- pass 3: 327's design tokens grow; its writes FAIL fail-open --
            conn = sqlite3.connect(host_db)
            conn.execute(
                "INSERT INTO turn_usage (turn_id, session_id, status, duration_ms,"
                " tokens_input, tokens_output, tokens_reasoning,"
                " tokens_cache_read, tokens_cache_write,"
                " retries, tool_calls, errors)"
                " VALUES ('h-design/t3', 'h-design', 'ok', 0,"
                " 2000000, 0, 0, 0, 0, 0, 0, 0)")
            conn.commit()
            conn.close()
            gh.set_edit_fail(["I327"])
            rc, stderr = run()
            self.assertEqual(rc, 0)                       # fail-open
            self.assertIn("warning", stderr)
            self.assertIn("memo#327", stderr)  # failure names project + issue
            failed_edits = gh.calls("project", "item-edit")[len(edits):]
            snap327b = json.loads((tmpdir / "data" / "issues" / "memo-327.json")
                                  .read_text(encoding="utf-8"))
            # only the fields whose WRITTEN value changed were attempted
            self.assertEqual({_flag(a, "--field-id") for a in failed_edits},
                             {"PVTNF_Tokens_total", "PVTNF_Tokens_design"})
            state = _state(tmpdir / "data")["writeback"]["memo"]
            self.assertNotIn("327", state["items"])       # failed id dropped
            self.assertIn("331", state["items"])          # untouched
            # cache still holds the last WRITTEN (old) value for 327
            self.assertEqual(state["written"]["327"]["Tokens total"],
                             snap327["tokens"]["total_m"])
            self.assertEqual(snap327b["tokens"]["total_m"], 2.2)  # it did change

            # --- pass 4: card re-added with a new id — re-resolved, written ---
            gh.set_edit_fail([])
            gh.set_items([_board_item(327, item_id="I327B"), _board_item(331)])
            rc, _ = run()
            self.assertEqual(rc, 0)
            re_edits = [a for a in gh.calls("project", "item-edit")
                        if _flag(a, "--id") == "I327B"]
            self.assertEqual({_flag(a, "--field-id") for a in re_edits},
                             {"PVTNF_Tokens_total", "PVTNF_Tokens_design"})
            self.assertEqual(_flag(re_edits[0], "--number"), "2.1")
            state = _state(tmpdir / "data")["writeback"]["memo"]
            self.assertEqual(state["items"]["327"], "I327B")

    def test_corrupt_written_state_collect_still_exits_zero(self):
        # BLOCKER regression: a shape-valid but corrupt state.json
        # («written": {"327": 48.2} — number, not {field: value}) used
        # to AttributeError through run_after_rebuild and kill the
        # scheduled cron collect. It must warn, reset the entry and
        # still exit 0 (fail-open contract), re-writing the values.
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            host_db = tmpdir / "host.sqlite"
            fixtures.write_host_db(host_db, fixtures.host_scenario())
            ctr_db = tmpdir / "opencode.db"
            fixtures.write_container_db(ctr_db, fixtures.container_scenario())
            docker_bin = tmpdir / "dbin"
            docker_bin.mkdir()
            fake_docker = docker_bin / "docker"
            fake_docker.write_text(FAKE_DOCKER, encoding="utf-8")
            os.chmod(fake_docker, 0o755)
            gh = FakeGh(tmpdir)
            gh.set_items([_board_item(327), _board_item(331)])
            gh.set_fields(_canonical_board_fields())
            config = _write_config(
                tmpdir, {"memo": _project_spec(number=3)},
                sources={"zcode_host": {"db": str(host_db)},
                         "opencode_container": {"container": "memo-box",
                                                "db": str(ctr_db)}})
            data = tmpdir / "data"
            data.mkdir()
            (data / "state.json").write_text(
                json.dumps({"writeback": {"memo": {
                    "items": {}, "written": {"327": 48.2}}}}, indent=2),
                encoding="utf-8")
            env = gh.env()
            env["PATH"] = str(docker_bin) + os.pathsep + env["PATH"]
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, env), \
                    contextlib.redirect_stderr(stderr):
                rc = collect.main(["collect", "--config", str(config)])
            self.assertEqual(rc, 0)                # the cron collect survives
            self.assertIn("warning", stderr.getvalue())
            self.assertIn("327", stderr.getvalue())  # names the corrupt entry
            # the reset entry re-writes from the fresh snapshot
            # (327: 6 fields, 331: 4 — both caches start empty/reset)
            self.assertEqual(len(gh.calls("project", "item-edit")), 10)
            written = _state(data)["writeback"]["memo"]["written"]["327"]
            self.assertIsInstance(written, dict)
            self.assertIn("Tokens total", written)


if __name__ == "__main__":
    unittest.main()
