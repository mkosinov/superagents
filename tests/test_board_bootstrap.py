"""Unit tests for board_bootstrap.py — etalon parser (scenario 7) and dry-run plan.

Run from repo root:
    python3 -m unittest tests.test_board_bootstrap -v

stdlib unittest only (repo has no pytest). The module under test lives in
.zcode/scripts/ (the .opencode/scripts/ copy is a byte-identical twin).
"""
import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".zcode" / "scripts"))

import board_bootstrap as bb


def doc(block_body: str) -> str:
    """A minimal etalon doc: prose + exactly one fenced board-etalon block."""
    return f"# Board etalon\n\nprose describing fields\n\n```board-etalon\n{block_body}\n```\n"


def valid_block() -> dict:
    return {
        "version": 1,
        "fields": [
            {"name": "Status", "type": "single_select",
             "options": ["Hold", "Backlog", "In IMPL"]},
            {"name": "Priority", "type": "single_select",
             "options": ["Critical", "High", "Medium", "Low"]},
            {"name": "host", "type": "single_select",
             "options": ["imac", "macbook", "hk", "gcp"]},
        ],
        "host_budgets": {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1},
    }


class TestParseEtalon(unittest.TestCase):
    """Scenario 7: broken etalon -> EtalonError with a reason, before any network."""

    def test_valid_block(self):
        et = bb.parse_etalon(doc(json.dumps(valid_block(), indent=2)))
        self.assertEqual([f["name"] for f in et.fields],
                         ["Status", "Priority", "host"])
        self.assertEqual(et.fields[0]["type"], "single_select")
        self.assertEqual(et.fields[0]["options"], ["Hold", "Backlog", "In IMPL"])
        self.assertEqual(et.host_budgets, {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1})

    def test_missing_block(self):
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon("# Doc\n\nno machine block here\n")
        self.assertIn("no board-etalon block", str(ctx.exception))

    def test_two_blocks(self):
        body = json.dumps(valid_block())
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(body) + "\n```board-etalon\n" + body + "\n```\n")
        self.assertIn("exactly one", str(ctx.exception))

    def test_malformed_json(self):
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc("{ not json at all"))
        self.assertIn("malformed JSON", str(ctx.exception))

    def test_unknown_field_type(self):
        bad = valid_block()
        bad["fields"][0]["type"] = "text"
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(json.dumps(bad)))
        msg = str(ctx.exception)
        self.assertIn("Status", msg)
        self.assertIn("text", msg)
        self.assertIn("single_select", msg)

    def test_duplicate_option(self):
        bad = valid_block()
        bad["fields"][1]["options"] = ["High", "High", "Low"]
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(json.dumps(bad)))
        self.assertIn('duplicate option "High"', str(ctx.exception))

    def test_empty_options(self):
        bad = valid_block()
        bad["fields"][2]["options"] = []
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(json.dumps(bad)))
        msg = str(ctx.exception)
        self.assertIn("host", msg)
        self.assertIn("empty options", msg)

    def test_budget_zero(self):
        bad = valid_block()
        bad["host_budgets"]["imac"] = 0
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(json.dumps(bad)))
        msg = str(ctx.exception)
        self.assertIn("imac", msg)
        self.assertIn(">= 1", msg)

    def test_bad_version(self):
        bad = valid_block()
        bad["version"] = 2
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(json.dumps(bad)))
        self.assertIn("version", str(ctx.exception))

    def test_no_fields(self):
        bad = valid_block()
        bad["fields"] = []
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.parse_etalon(doc(json.dumps(bad)))
        self.assertIn("fields", str(ctx.exception))


class TestLoadEtalon(unittest.TestCase):
    """load_etalon names the path and the cause; default resolution hits the repo doc."""

    def test_missing_file(self):
        with self.assertRaises(bb.EtalonError) as ctx:
            bb.load_etalon("/no/such/board-etalon.md")
        msg = str(ctx.exception)
        self.assertIn("/no/such/board-etalon.md", msg)
        self.assertIn("not found", msg)

    def test_parse_error_names_path(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "etalon.md"
            p.write_text(doc("{ broken"), encoding="utf-8")
            with self.assertRaises(bb.EtalonError) as ctx:
                bb.load_etalon(str(p))
            msg = str(ctx.exception)
            self.assertIn(str(p), msg)
            self.assertIn("malformed JSON", msg)

    def test_no_block_names_path(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "etalon.md"
            p.write_text("# no block\n", encoding="utf-8")
            with self.assertRaises(bb.EtalonError) as ctx:
                bb.load_etalon(str(p))
            msg = str(ctx.exception)
            self.assertIn(str(p), msg)
            self.assertIn("no board-etalon block", msg)

    def test_custom_path_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "etalon.md"
            p.write_text(doc(json.dumps(valid_block())), encoding="utf-8")
            et, path = bb.load_etalon(str(p))
            self.assertEqual(path, p)
            self.assertEqual([f["name"] for f in et.fields],
                             ["Status", "Priority", "host"])

    def test_default_is_the_repo_etalon_doc(self):
        """Task 1's committed file parses cleanly via the default resolution."""
        et, path = bb.load_etalon(None)
        self.assertEqual(path, REPO / "docs" / "board" / "board-etalon.md")
        self.assertEqual([f["name"] for f in et.fields],
                         ["Status", "Priority", "host", "gate"])
        self.assertEqual(
            et.fields[0]["options"],
            ["Hold", "Backlog", "In Design", "Ready to IMPL", "In IMPL",
             "PR (G7)", "In-main", "deployed", "Not planned"])
        self.assertEqual(et.host_budgets, {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1})


class TestRenderPlan(unittest.TestCase):
    """Scenario 5: the dry-run plan tree — etalon path, create/remove/link lines."""

    def setUp(self):
        self.etalon = bb.Etalon(
            fields=[
                {"name": "Status", "type": "single_select",
                 "options": ["Hold", "Backlog", "In IMPL"]},
                {"name": "Priority", "type": "single_select",
                 "options": ["Critical", "High"]},
            ],
            host_budgets={"imac": 2},
        )
        self.etalon_path = Path("/tmp/some/board-etalon.md")
        self.guards = ["guard: config exists at /tmp/out/board_config.json: not-checked-yet (planned)"]
        self.args = argparse.Namespace(
            mode="init", repo="mkosinov/superagents", title="Superagents",
            owner=None, etalon=None, out=None, force=False, dry_run=True)

    def args_with(self, **kw):
        ns = vars(self.args).copy()
        ns.update(kw)
        return argparse.Namespace(**ns)

    def lines(self, mode, args=None):
        return bb.render_plan(mode, args or self.args, self.etalon,
                              self.etalon_path, self.guards).splitlines()

    def test_init_plan_lines_in_order(self):
        lines = self.lines("init")
        self.assertEqual(lines[0], "etalon: /tmp/some/board-etalon.md")
        self.assertEqual(lines[1], 'project: create "Superagents" (owner mkosinov)')
        self.assertEqual(lines[2], "remove built-in field Status (Todo / In Progress / Done)")
        self.assertEqual(lines[3], "create Status: Hold | Backlog | In IMPL")
        self.assertEqual(lines[4], "create Priority: Critical | High")
        self.assertIn("link: mkosinov/superagents", lines)
        self.assertIn("seed: open issues would be listed live (--dry-run: no network)", lines)
        self.assertIn("config: " + str(REPO / "docs" / "board" / "board_config.json"), lines)
        # one guard line per guard verdict, after the plan body
        self.assertEqual(lines[-1], "guard: config exists at /tmp/out/board_config.json: not-checked-yet (planned)")
        self.assertEqual(sum(1 for l in lines if l.startswith("guard: ")), 1)

    def test_owner_defaults_to_repo_owner(self):
        lines = self.lines("init", self.args_with(owner=None))
        self.assertEqual(lines[1], 'project: create "Superagents" (owner mkosinov)')

    def test_explicit_owner(self):
        lines = self.lines("init", self.args_with(owner="someone"))
        self.assertEqual(lines[1], 'project: create "Superagents" (owner someone)')

    def test_out_override(self):
        lines = self.lines("init", self.args_with(out="/tmp/out/board_config.json"))
        self.assertIn("config: /tmp/out/board_config.json", lines)

    def test_adopt_prints_comparison_instead_of_create_link(self):
        lines = self.lines("adopt", self.args_with(mode="adopt", project=4))
        self.assertEqual(lines[0], "etalon: /tmp/some/board-etalon.md")
        self.assertIn("compare: read fields of project #4 and match by exact name", lines)
        self.assertIn("refuse: missing field or option; warn: extra field or option (drift contract)", lines)
        create_lines = [l for l in lines if l.startswith("create ") or l.startswith("link: ")]
        self.assertEqual(create_lines, [])
        self.assertIn("config: " + str(REPO / "docs" / "board" / "board_config.json"), lines)
        self.assertEqual(lines[-1].startswith("guard: "), True)


def compare_etalon() -> bb.Etalon:
    """Small etalon fixture for comparison tests (Status + Priority)."""
    return bb.Etalon(
        fields=[
            {"name": "Status", "type": "single_select",
             "options": ["Hold", "Backlog", "In Design", "Ready to IMPL", "In IMPL"]},
            {"name": "Priority", "type": "single_select",
             "options": ["Critical", "High", "Medium", "Low"]},
        ],
        host_budgets={"imac": 2, "macbook": 1},
    )


def live_field(name: str, options: list[str], type_: str = "SINGLE_SELECT") -> dict:
    """One gh `project field-list --format json` entry (option ids included)."""
    return {
        "id": f"PVTSSF_{name}",
        "name": name,
        "type": type_,
        "options": [{"id": f"PVTSSO_{name}_{o}", "name": o} for o in options],
    }


def matching_live() -> list[dict]:
    """Live field list matching compare_etalon() exactly, plus metadata columns."""
    return [
        {"id": "PVTSSF_title", "name": "Title", "type": "TITLE", "options": None},
        live_field("Status", ["Hold", "Backlog", "In Design", "Ready to IMPL", "In IMPL"]),
        {"id": "PVTSSF_labels", "name": "Labels", "type": "LABELS", "options": None},
        live_field("Priority", ["Critical", "High", "Medium", "Low"]),
        {"id": "PVTSSF_assignees", "name": "Assignees", "type": "ASSIGNEES", "options": None},
    ]


class TestCompareFields(unittest.TestCase):
    """Adopt comparison matrix on fixtures: missing -> refuse, extra -> warn-ok."""

    def test_exact_match_is_ok_to_adopt(self):
        diff = bb.compare_fields(compare_etalon(), matching_live())
        self.assertEqual(diff, {"missing_fields": [], "missing_options": {},
                                "extra_fields": [], "extra_options": {}})
        self.assertTrue(bb.ok_to_adopt(diff))

    def test_metadata_columns_ignored(self):
        """Non-single-select entries (Title/Labels/Assignees/Milestones) are not extras."""
        live = matching_live() + [
            {"id": "PVTSSF_milestones", "name": "Milestones", "type": "MILESTONE",
             "options": None}]
        diff = bb.compare_fields(compare_etalon(), live)
        self.assertEqual(diff["extra_fields"], [])
        self.assertTrue(bb.ok_to_adopt(diff))

    def test_missing_field_refuses(self):
        live = [e for e in matching_live() if e["name"] != "Priority"]
        diff = bb.compare_fields(compare_etalon(), live)
        self.assertEqual(diff["missing_fields"], ["Priority"])
        self.assertEqual(diff["missing_options"], {})
        self.assertFalse(bb.ok_to_adopt(diff))

    def test_missing_option_refuses(self):
        live = matching_live()
        live[1]["options"] = [o for o in live[1]["options"] if o["name"] != "In IMPL"]
        diff = bb.compare_fields(compare_etalon(), live)
        self.assertEqual(diff["missing_options"], {"Status": ["In IMPL"]})
        self.assertEqual(diff["missing_fields"], [])
        self.assertFalse(bb.ok_to_adopt(diff))

    def test_extra_field_warns_ok(self):
        live = matching_live() + [live_field("Reviewer", ["me", "you"])]
        diff = bb.compare_fields(compare_etalon(), live)
        self.assertEqual(diff["extra_fields"], ["Reviewer"])
        self.assertEqual(diff["missing_fields"], [])
        self.assertTrue(bb.ok_to_adopt(diff))

    def test_extra_option_warns_ok(self):
        live = matching_live()
        live[1]["options"].append({"id": "PVTSSO_extra", "name": "Whatever"})
        diff = bb.compare_fields(compare_etalon(), live)
        self.assertEqual(diff["extra_options"], {"Status": ["Whatever"]})
        self.assertTrue(bb.ok_to_adopt(diff))

    def test_renamed_option_is_missing_and_extra(self):
        """Exact match only: `In Design (G1a)` vs `In Design` counts BOTH ways."""
        live = matching_live()
        live[1]["options"] = [
            {"id": "PVTSSO_Status_Hold", "name": "Hold"},
            {"id": "PVTSSO_Status_Backlog", "name": "Backlog"},
            {"id": "PVTSSO_Status_r", "name": "In Design (G1a)"},
            {"id": "PVTSSO_Status_RTI", "name": "Ready to IMPL"},
            {"id": "PVTSSO_Status_II", "name": "In IMPL"},
        ]
        diff = bb.compare_fields(compare_etalon(), live)
        self.assertEqual(diff["missing_options"], {"Status": ["In Design"]})
        self.assertEqual(diff["extra_options"], {"Status": ["In Design (G1a)"]})
        self.assertFalse(bb.ok_to_adopt(diff))


class TestBuildConfig(unittest.TestCase):
    """board_config.json format v1: exact keys, no option ids, budgets verbatim."""

    FIELD_IDS = {"Status": "PVTSSF_1", "Priority": "PVTSSF_2",
                 "host": "PVTSSF_3", "gate": "PVTSSF_4"}
    BUDGETS = {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1}

    def build(self, **kw):
        params = dict(project_id="PVT_1", project_number=4, owner="mkosinov",
                      repo="superagents", field_ids=self.FIELD_IDS,
                      host_budgets=self.BUDGETS)
        params.update(kw)
        return bb.build_config(**params)

    def test_exact_key_set(self):
        self.assertEqual(sorted(self.build()),
                         ["fields", "host_budgets", "owner", "project_id",
                          "project_number", "repo", "version"])

    def test_version_and_scalars(self):
        config = self.build()
        self.assertEqual(config["version"], 1)
        self.assertEqual(config["project_id"], "PVT_1")
        self.assertEqual(config["project_number"], 4)
        self.assertEqual(config["owner"], "mkosinov")
        self.assertEqual(config["repo"], "superagents")

    def test_fields_map_name_to_field_id_no_option_ids(self):
        config = self.build()
        self.assertEqual(config["fields"], self.FIELD_IDS)
        self.assertTrue(all(isinstance(v, str) for v in config["fields"].values()))
        dumped = json.dumps(config)
        self.assertNotIn("options", dumped)
        self.assertNotIn("PVTSSO", dumped)  # option ids never leak anywhere

    def test_host_budgets_copied_verbatim(self):
        budgets = {"imac": 2, "macbook": 1}
        config = self.build(field_ids={"Status": "PVTSSF_x"}, host_budgets=budgets)
        self.assertEqual(config["host_budgets"], budgets)


class TestWriteConfig(unittest.TestCase):
    """write_config: mkdir parents, indent=2 JSON, round-trips."""

    def test_creates_parents_writes_indented_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "docs" / "board" / "board_config.json"
            config = bb.build_config("PVT_1", 4, "mkosinov", "superagents",
                                     {"Status": "PVTSSF_1"}, {"imac": 2})
            bb.write_config(path, config)
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn('  "version": 1,', text)  # top-level keys at indent=2
            self.assertEqual(json.loads(text), config)


# ---------------------------------------------------------------------------
# Task 4 fixtures: guards, adopt wiring. NEVER a real gh call — FakeGh only.

def introspection(*connection_names: str) -> dict:
    """Schema-introspection fixture: __type.fields[].name list."""
    names = ("id", "number", "title", *connection_names)
    return {"__type": {"fields": [{"name": n} for n in names]}}


PROJECTS = [
    {"number": 4, "id": "PVT_4", "title": "Superagents", "closed": False},
    {"number": 3, "id": "PVT_3", "title": "Memo Project", "closed": False},
]
NODES_SUPERAGENTS = [{"owner": {"login": "mkosinov"}, "name": "superagents"}]
NODES_MEMO = [{"owner": {"login": "mkosinov"}, "name": "memo"}]


class FakeGh:
    """Fixture-backed stand-in for the thin gh wrappers; records every argv.

    gql answers introspection queries from `introspection` and node queries by
    the PVT id embedded in the query, keyed by the connection name the query
    asked for — mirroring the documented query shapes, nothing else.
    """

    def __init__(self, *, introspect=None, projects=None, nodes_by_id=None,
                 fields=None):
        self.introspect = introspect if introspect is not None else introspection("repositories")
        self.projects = projects if projects is not None else PROJECTS
        self.nodes_by_id = nodes_by_id if nodes_by_id is not None else {
            "PVT_4": NODES_SUPERAGENTS, "PVT_3": NODES_MEMO}
        self.fields = fields if fields is not None else []
        self.auth_rc = 0
        self.auth_stderr = ""
        self.calls = []

    def gh(self, argv):
        self.calls.append(("gh", *argv))
        return types.SimpleNamespace(returncode=self.auth_rc, stderr=self.auth_stderr)

    def gh_json(self, argv):
        self.calls.append(("gh", *argv))
        if argv[:2] == ["project", "list"]:
            return {"projects": self.projects}
        if argv[:2] == ["project", "field-list"]:
            return {"fields": self.fields}
        raise AssertionError(f"unexpected gh json call: {argv}")

    def gql(self, query):
        self.calls.append(("gql", query))
        if "__type" in query:
            return self.introspect
        pid = next(pid for pid in self.nodes_by_id if f'"{pid}"' in query)
        conn = "linkedRepositories" if "linkedRepositories" in query else "repositories"
        meta = {k: v for k, v in self.nodes_by_id_meta(pid).items() if k != "id"}
        return {"node": {**meta, conn: {"nodes": self.nodes_by_id[pid]}}}

    def nodes_by_id_meta(self, pid):
        return next(p for p in self.projects if p["id"] == pid)


def init_args(**kw):
    ns = dict(mode="init", repo="mkosinov/superagents", title="New Board",
              owner=None, etalon=None, out=None, force=False, dry_run=False)
    ns.update(kw)
    return argparse.Namespace(**ns)


def adopt_args(**kw):
    ns = dict(mode="adopt", project=4, repo="mkosinov/superagents",
              owner=None, etalon=None, out=None, force=False, dry_run=False)
    ns.update(kw)
    return argparse.Namespace(**ns)


def gh_field(name: str, options: list[str], type_: str = "ProjectV2SingleSelectField") -> dict:
    """One live gh field-list entry (real gh type names, real id shapes)."""
    return {
        "id": f"PVTSSF_{name}",
        "name": name,
        "type": type_,
        "options": [{"id": f"PVTSSO_{name}_{o}", "name": o} for o in options],
    }


def gh_matching_live() -> list[dict]:
    """Live-typed field list matching compare_etalon() (Status + Priority)."""
    return [
        {"id": "PVTF_Title", "name": "Title", "type": "ProjectV2Field", "options": None},
        gh_field("Status", ["Hold", "Backlog", "In Design", "Ready to IMPL", "In IMPL"]),
        {"id": "PVTF_Labels", "name": "Labels", "type": "ProjectV2Field", "options": None},
        gh_field("Priority", ["Critical", "High", "Medium", "Low"]),
    ]


class TestGuardConfigExists(unittest.TestCase):
    """Local damage-prevention guard: the config path is checked offline."""

    def test_ok_when_config_absent(self):
        v = bb.guard_config_exists(Path("/no/such/board_config.json"))
        self.assertEqual(v.status, "ok")

    def test_refusal_names_path_and_damage(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            v = bb.guard_config_exists(out)
            self.assertEqual(v.status, "refuse")
            self.assertIn(str(out), v.message)
            # mandated damage sentence, verbatim
            self.assertIn("a second run creates a duplicate project, re-seeds "
                          "the issues as duplicate cards, and overwrites the config",
                          v.message)
            self.assertIn("--force", v.message)  # the adopt escape hatch is named

    def test_force_allows_deliberate_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            v = bb.guard_config_exists(out, force=True)
            self.assertEqual(v.status, "ok")
            self.assertIn("deliberate", v.message)


class TestFindRepoConnection(unittest.TestCase):
    """Schema introspection: which ProjectV2 connection links repositories."""

    def test_prefers_linked_repositories(self):
        schema = introspection("linkedRepositories", "repositories")
        self.assertEqual(bb.find_repo_connection(schema), "linkedRepositories")

    def test_falls_back_to_repositories(self):
        self.assertEqual(bb.find_repo_connection(introspection("repositories")),
                         "repositories")

    def test_none_when_schema_has_no_connection(self):
        self.assertIsNone(bb.find_repo_connection(introspection()))
        self.assertIsNone(bb.find_repo_connection({}))

    def test_live_shape_from_the_real_schema(self):
        """The actual introspection payload (pinned 2026-09-26): repositories."""
        schema = {"__type": {"fields": [
            {"name": n} for n in ("id", "number", "title", "fields", "items",
                                  "repositories", "closed", "owner")]}}
        self.assertEqual(bb.find_repo_connection(schema), "repositories")


class TestGuardRepoHasProject(unittest.TestCase):
    """init guard: refuse if ANY open project of the owner links the repo."""

    def test_refuses_when_a_project_links_the_repo(self):
        fake = FakeGh()
        v = bb.guard_repo_has_project("mkosinov", "mkosinov/superagents",
                                      gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "refuse")
        self.assertIn("#4", v.message)
        self.assertIn("Superagents", v.message)
        self.assertIn("mkosinov/superagents", v.message)

    def test_ok_when_no_project_links_the_repo(self):
        fake = FakeGh(nodes_by_id={"PVT_4": NODES_MEMO, "PVT_3": []})
        v = bb.guard_repo_has_project("mkosinov", "mkosinov/superagents",
                                      gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "ok")

    def test_downgrades_when_schema_has_no_connection(self):
        fake = FakeGh(introspect=introspection())
        v = bb.guard_repo_has_project("mkosinov", "mkosinov/superagents",
                                      gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "skipped")
        self.assertIn("skipped: no repository connection in schema", v.message)
        # degradation happens before enumeration: no project list read
        self.assertFalse(any(c[1:3] == ("project", "list") for c in fake.calls))

    def test_refuses_when_list_hits_the_cap(self):
        fake = FakeGh()
        v = bb.guard_repo_has_project("mkosinov", "mkosinov/superagents",
                                      gh_json=fake.gh_json, gql=fake.gql, limit=2)
        self.assertEqual(v.status, "refuse")
        self.assertIn("--limit 2", v.message)

    def test_works_with_linked_repositories_connection(self):
        fake = FakeGh(introspect=introspection("linkedRepositories"))
        v = bb.guard_repo_has_project("mkosinov", "mkosinov/superagents",
                                       gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "refuse")  # PVT_4 fixture links the repo

    def test_preloaded_projects_skip_the_list_read(self):
        """Carry-over A: cmd_init lists projects once, guards reuse the rows."""
        fake = FakeGh(nodes_by_id={"PVT_4": NODES_MEMO, "PVT_3": []})
        v = bb.guard_repo_has_project("mkosinov", "mkosinov/superagents",
                                      projects=PROJECTS,
                                      gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "ok")
        self.assertFalse(any(c[1:3] == ("project", "list") for c in fake.calls))


class TestVerifyProjectLinksRepo(unittest.TestCase):
    """adopt guard (inverse contract): refuse unless THE project links --repo."""

    def test_ok_when_linked_and_carries_project_payload(self):
        fake = FakeGh()
        v = bb.verify_project_links_repo(4, "mkosinov", "mkosinov/superagents",
                                         projects=PROJECTS, gql=fake.gql)
        self.assertEqual(v.status, "ok")
        self.assertEqual(v.project, PROJECTS[0])  # id feeds build_config

    def test_default_path_lists_with_explicit_limit(self):
        fake = FakeGh()
        v = bb.verify_project_links_repo(4, "mkosinov", "mkosinov/superagents",
                                         gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "ok")
        self.assertIn(("gh", "project", "list", "--owner", "mkosinov",
                       "--format", "json", "--limit", "1000"), fake.calls)

    def test_refuses_when_project_not_linked(self):
        fake = FakeGh(nodes_by_id={"PVT_4": NODES_MEMO})
        v = bb.verify_project_links_repo(4, "mkosinov", "mkosinov/superagents",
                                         projects=PROJECTS, gql=fake.gql)
        self.assertEqual(v.status, "refuse")
        self.assertIn("not linked", v.message)
        self.assertIn("mkosinov/memo", v.message)  # names what IS linked

    def test_refuses_when_project_number_unknown(self):
        fake = FakeGh()
        v = bb.verify_project_links_repo(99, "mkosinov", "mkosinov/superagents",
                                         gh_json=fake.gh_json, gql=fake.gql)
        self.assertEqual(v.status, "refuse")
        self.assertIn("#99", v.message)
        self.assertIn("not found", v.message)

    def test_refuses_when_connection_missing(self):
        fake = FakeGh(introspect=introspection())
        v = bb.verify_project_links_repo(4, "mkosinov", "mkosinov/superagents",
                                         projects=PROJECTS, gql=fake.gql)
        self.assertEqual(v.status, "refuse")
        self.assertIn("no repository connection in schema", v.message)


class TestGuardTitleCollision(unittest.TestCase):
    """Equal title among the owner's open projects: warn only, naming both."""

    def test_warns_naming_existing_and_requested_title(self):
        v = bb.guard_title_collision(PROJECTS, "Superagents")
        self.assertEqual(v.status, "warn")
        self.assertIn("#4", v.message)
        self.assertIn("Superagents", v.message)

    def test_ok_when_no_collision(self):
        v = bb.guard_title_collision(PROJECTS, "A Fresh Title")
        self.assertEqual(v.status, "ok")


class TestCompareFieldsGhTypes(unittest.TestCase):
    """compare_fields accepts the real gh type names, not just the fixture one."""

    def test_live_select_type_recognized(self):
        diff = bb.compare_fields(compare_etalon(), gh_matching_live())
        self.assertEqual(diff["missing_fields"], [])
        self.assertTrue(bb.ok_to_adopt(diff))

    def test_live_metadata_columns_are_not_extras(self):
        diff = bb.compare_fields(compare_etalon(), gh_matching_live() + [
            {"id": "PVTF_Milestone", "name": "Milestone",
             "type": "ProjectV2Field", "options": None}])
        self.assertEqual(diff["extra_fields"], [])
        self.assertTrue(bb.ok_to_adopt(diff))


class TestPlanGuards(unittest.TestCase):
    """Dry-run guard verdicts: local ones real, network ones deferred; strings."""

    def test_init_local_verdict_plus_two_deferred(self):
        out = Path("/tmp/nowhere/board_config.json")
        lines = bb.plan_guards("init", init_args(out=str(out)), Path("/tmp/e.md"))
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("guard: ok:"))
        self.assertIn(str(out), lines[0])
        self.assertIn("read at run time", lines[1])
        self.assertIn("mkosinov/superagents", lines[1])
        self.assertIn("read at run time", lines[2])

    def test_init_existing_config_renders_report_only_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            lines = bb.plan_guards("init", init_args(out=str(out)), Path("/tmp/e.md"))
            self.assertIn("guard: refuse:", lines[0])
            self.assertIn("duplicate project", lines[0])
            self.assertIn("report-only", lines[0])

    def test_adopt_existing_config_names_force(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            lines = bb.plan_guards("adopt", adopt_args(out=str(out)), Path("/tmp/e.md"))
            self.assertEqual(len(lines), 1)
            self.assertIn("guard: refuse:", lines[0])
            self.assertIn("--force", lines[0])

    def test_adopt_force_renders_deliberate_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            lines = bb.plan_guards("adopt", adopt_args(out=str(out), force=True),
                                   Path("/tmp/e.md"))
            self.assertTrue(lines[0].startswith("guard: ok:"))
            self.assertIn("deliberate overwrite", lines[0])


class TestCliDryRunGuards(unittest.TestCase):
    """Dry-run stays report-only: guard refusals never change the exit code."""

    SCRIPT = REPO / ".zcode" / "scripts" / "board_bootstrap.py"

    def run_cli(self, *cli_args):
        return subprocess.run([sys.executable, str(self.SCRIPT), *cli_args],
                              capture_output=True, text=True)

    def etalon_in(self, td):
        etalon = Path(td) / "etalon.md"
        etalon.write_text(doc(json.dumps(valid_block())), encoding="utf-8")
        return etalon

    def test_init_existing_config_exit_zero_with_damage_line(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = self.etalon_in(td)
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            r = self.run_cli("init", "--dry-run", "--repo", "mkosinov/superagents",
                             "--title", "T", "--etalon", str(etalon), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("duplicate project", r.stdout)
            self.assertIn("report-only", r.stdout)
            self.assertEqual(out.read_text(encoding="utf-8"), "{}")  # untouched

    def test_adopt_existing_config_exit_zero(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = self.etalon_in(td)
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            r = self.run_cli("adopt", "4", "--dry-run", "--repo", "mkosinov/superagents",
                             "--etalon", str(etalon), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--force", r.stdout)

    def test_malformed_repo_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = self.etalon_in(td)
            r = self.run_cli("init", "--dry-run", "--repo", "noslash",
                             "--title", "T", "--etalon", str(etalon))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("owner/name", r.stderr)


class TestCmdAdopt(unittest.TestCase):
    """Live adopt wiring on fixtures: mandated order, refusals, config write."""

    def run_adopt(self, fake, args, etalon=None):
        """Adopt prints its success line; silence it unless asserted."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = bb.cmd_adopt(args, etalon or compare_etalon(),
                              gh=fake.gh, gh_json=fake.gh_json, gql=fake.gql)
        return rc, buf.getvalue()

    def test_happy_path_order_config_written_no_mutations(self):
        fake = FakeGh(fields=gh_matching_live())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            self.run_adopt(fake, adopt_args(out=str(out)))            # mandated step order: auth → project list → introspection → node
            # link query → field-list. Nothing else — adopt never mutates.
            self.assertEqual(fake.calls[0], ("gh", "auth", "status"))
            self.assertEqual(fake.calls[1], ("gh", "project", "list", "--owner",
                                             "mkosinov", "--format", "json",
                                             "--limit", "1000"))
            self.assertEqual(fake.calls[2][0], "gql")
            self.assertIn("__type", fake.calls[2][1])
            self.assertEqual(fake.calls[3][0], "gql")
            self.assertIn('"PVT_4"', fake.calls[3][1])
            self.assertEqual(fake.calls[4], ("gh", "project", "field-list", "4",
                                             "--owner", "mkosinov", "--format",
                                             "json", "--limit", "200"))
            self.assertEqual(len(fake.calls), 5)
            config = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(config["project_id"], "PVT_4")
            self.assertEqual(config["project_number"], 4)
            self.assertEqual(config["owner"], "mkosinov")
            self.assertEqual(config["repo"], "superagents")
            self.assertEqual(config["fields"],
                             {"Status": "PVTSSF_Status", "Priority": "PVTSSF_Priority"})
            self.assertEqual(config["host_budgets"], {"imac": 2, "macbook": 1})

    def test_auth_failure_refuses(self):
        fake = FakeGh(fields=gh_matching_live())
        fake.auth_rc, fake.auth_stderr = 1, "not logged in"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit) as ctx:
                self.run_adopt(fake, adopt_args(out=str(Path(td) / "c.json")))
            self.assertIn("auth status", str(ctx.exception))

    def test_unlinked_project_refuses_before_field_list(self):
        fake = FakeGh(fields=gh_matching_live(), nodes_by_id={"PVT_4": NODES_MEMO})
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            with self.assertRaises(SystemExit) as ctx:
                self.run_adopt(fake, adopt_args(out=str(out)))
            self.assertIn("not linked", str(ctx.exception))
            self.assertFalse(out.exists())
            self.assertFalse(any(c[1:3] == ("project", "field-list") for c in fake.calls))

    def test_unknown_project_number_refuses(self):
        fake = FakeGh(fields=gh_matching_live())
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit) as ctx:
                self.run_adopt(fake, adopt_args(project=99, out=str(Path(td) / "c.json")))
            self.assertIn("not found", str(ctx.exception))

    def test_field_list_cap_refuses(self):
        fields = [gh_field(f"F{i:03d}", ["x"]) for i in range(200)]
        fake = FakeGh(fields=fields)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            with self.assertRaises(SystemExit) as ctx:
                self.run_adopt(fake, adopt_args(out=str(out)))
            self.assertIn("--limit 200", str(ctx.exception))
            self.assertFalse(out.exists())

    def test_missing_refuses_with_full_difference_list(self):
        fields = gh_matching_live()
        fields = [e for e in fields if e["name"] != "Priority"]  # field missing
        fields[1]["options"] = [o for o in fields[1]["options"]
                                if o["name"] != "In IMPL"]        # option missing
        fake = FakeGh(fields=fields)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            with self.assertRaises(SystemExit) as ctx:
                self.run_adopt(fake, adopt_args(out=str(out)))
            msg = str(ctx.exception)
            self.assertIn("Priority", msg)   # full list: the missing field
            self.assertIn("In IMPL", msg)    # …and the missing option
            self.assertFalse(out.exists())

    def test_extra_warns_and_proceeds(self):
        fields = gh_matching_live() + [gh_field("Reviewer", ["me", "you"])]
        fake = FakeGh(fields=fields)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            _, stdout = self.run_adopt(fake, adopt_args(out=str(out)))
            self.assertIn("Reviewer", stdout)
            self.assertIn("warning", stdout)
            self.assertTrue(out.exists())  # drift contract: extras proceed

    def test_existing_config_refuses_naming_force(self):
        fake = FakeGh(fields=gh_matching_live())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text('{"old": true}', encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                self.run_adopt(fake, adopt_args(out=str(out)))
            self.assertIn("--force", str(ctx.exception))
            self.assertIn(out.read_text(encoding="utf-8"), '{"old": true}')

    def test_force_overwrites_config(self):
        fake = FakeGh(fields=gh_matching_live())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text('{"old": true}', encoding="utf-8")
            rc, _ = self.run_adopt(fake, adopt_args(out=str(out), force=True))
            self.assertEqual(rc, 0)
            config = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(config["project_id"], "PVT_4")


class TestCliDryRun(unittest.TestCase):
    """CLI wiring: --dry-run paths honor --etalon and --out, exit 0, no network."""

    SCRIPT = REPO / ".zcode" / "scripts" / "board_bootstrap.py"

    def run_cli(self, *cli_args):
        return subprocess.run(
            [sys.executable, str(self.SCRIPT), *cli_args],
            capture_output=True, text=True)

    def test_init_dry_run_prints_etalon_path_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = Path(td) / "etalon.md"
            etalon.write_text(doc(json.dumps(valid_block())), encoding="utf-8")
            r = self.run_cli("init", "--dry-run", "--repo", "mkosinov/superagents",
                             "--title", "Superagents", "--etalon", str(etalon))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"etalon: {etalon}", r.stdout)

    def test_init_dry_run_out_override(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = Path(td) / "etalon.md"
            out = Path(td) / "custom" / "board_config.json"
            etalon.write_text(doc(json.dumps(valid_block())), encoding="utf-8")
            r = self.run_cli("init", "--dry-run", "--repo", "mkosinov/superagents",
                             "--title", "Superagents", "--etalon", str(etalon),
                             "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"config: {out}", r.stdout)
            self.assertFalse(out.exists())  # dry-run writes nothing

    def test_adopt_dry_run_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = Path(td) / "etalon.md"
            etalon.write_text(doc(json.dumps(valid_block())), encoding="utf-8")
            r = self.run_cli("adopt", "4", "--dry-run", "--repo", "mkosinov/superagents",
                             "--etalon", str(etalon))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"etalon: {etalon}", r.stdout)
            self.assertIn("compare:", r.stdout)

    def test_broken_etalon_exits_nonzero_before_network(self):
        with tempfile.TemporaryDirectory() as td:
            etalon = Path(td) / "etalon.md"
            etalon.write_text("# no block\n", encoding="utf-8")
            r = self.run_cli("init", "--dry-run", "--repo", "mkosinov/superagents",
                             "--title", "T", "--etalon", str(etalon))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(str(etalon), r.stderr)
            self.assertIn("no board-etalon block", r.stderr)


# ---------------------------------------------------------------------------
# Task 5 fixtures: init wiring. NEVER a real gh call — FakeGh only.

INIT_ETALON = bb.Etalon(
    fields=[
        {"name": "Status", "type": "single_select",
         "options": ["Hold", "Backlog", "In IMPL"]},
        {"name": "Priority", "type": "single_select",
         "options": ["Critical", "High", "Medium", "Low"]},
    ],
    host_budgets={"imac": 2, "macbook": 1},
)


def builtin_field() -> dict:
    """The built-in Status single-select every new project ships with."""
    return gh_field("Status", ["Todo", "In Progress", "Done"])


class InitGh:
    """FakeGh extension answering the full init sequence.

    Emulates gh semantics faithfully (gh 2.100.0 --help + the rollout log):
    mutations mutate internal state and stay silent on success; failures
    raise SystemExit exactly like the real gh_json wrapper; field-list /
    item-list reflect current state; ids are minted per resource at run time.
    """

    def __init__(self, *, projects=None, linked_pids=None, issues=None,
                 fail_verb=None, fail_object=None, auth_rc=0):
        self.projects = projects if projects is not None else []
        self.linked_pids = linked_pids if linked_pids is not None else set()
        self.issues = issues if issues is not None else [
            {"number": 1, "url": "https://github.com/mkosinov/superagents/issues/1"},
            {"number": 2, "url": "https://github.com/mkosinov/superagents/issues/2"},
        ]
        self.fail_verb = fail_verb      # e.g. "link" — its FIRST call fails
        self.fail_object = fail_object  # e.g. {"field-create": "Priority"} —
        self._failed_verbs = set()      #   the named object always fails
        self.auth_rc = auth_rc
        self.auth_stderr = "" if auth_rc == 0 else "not logged in"
        self.calls = []
        # state of the project created by this run
        self.created = None       # {"id", "number", "title"}
        self.fields = [builtin_field()]  # fresh projects ship the built-in
        self.items = []           # live item entries
        self._ids = iter(range(1000, 2000))
        self.linked = False

    def _nid(self, prefix: str) -> str:
        return f"{prefix}_{next(self._ids)}"

    def _boom(self, argv: str) -> SystemExit:
        return SystemExit(f"gh error ({argv}): simulated failure")

    def _should_fail(self, verb: str, obj: str | None) -> bool:
        if self.fail_object and verb in self.fail_object \
                and self.fail_object[verb] == obj:
            return True
        if self.fail_verb and verb == self.fail_verb and verb not in self._failed_verbs:
            self._failed_verbs.add(verb)
            return True
        return False

    def gh(self, argv):
        self.calls.append(("gh", *argv))
        if len(argv) > 1 and argv[1] == "field-delete":
            # mutations are silent: exit status only (verified by read-back)
            fid = argv[argv.index("--id") + 1]
            if self._should_fail("field-delete", fid):
                return types.SimpleNamespace(
                    returncode=1, stderr="gh: cannot delete built-in field")
            self.fields = [f for f in self.fields if f["id"] != fid]
            return types.SimpleNamespace(returncode=0, stderr="")
        return types.SimpleNamespace(returncode=self.auth_rc,
                                     stderr=self.auth_stderr)

    def gh_json(self, argv):
        self.calls.append(("gh", *argv))
        verb = argv[1] if len(argv) > 1 else ""
        if argv[0] == "issue" and verb == "list":
            if self._should_fail("issue-list", None):
                raise self._boom("gh issue list")
            return list(self.issues)
        if argv[0] == "project" and verb == "list":
            return {"projects": list(self.projects)}
        if verb == "create":
            if self._should_fail("create", None):
                raise self._boom("gh project create")
            self.created = {"id": "PVT_1010", "number": 7,
                            "title": argv[argv.index("--title") + 1]}
            return dict(self.created)
        if verb == "field-list":
            return {"fields": [dict(f, options=list(f["options"]))
                               for f in self.fields]}
        if verb == "field-create":
            name = argv[argv.index("--name") + 1]
            if self._should_fail("field-create", name):
                raise self._boom(f"gh project field-create --name {name}")
            opts = argv[argv.index("--single-select-options") + 1].split(",")
            self.fields.append(gh_field(name, opts, "ProjectV2SingleSelectField"))
            return {}
        if verb == "link":
            if self._should_fail("link", None):
                raise self._boom("gh project link")
            self.linked = True
            return {}
        if verb == "item-list":
            return {"items": [dict(i) for i in self.items]}
        if verb == "item-add":
            url = argv[argv.index("--url") + 1]
            if self._should_fail("item-add", url):
                raise self._boom(f"gh project item-add --url {url}")
            number = int(url.rsplit("/", 1)[1])
            self.items.append({"id": f"PVTI_{number}", "number": number,
                               "url": url, "status": None})
            return {"id": f"PVTI_{number}"}
        if verb == "item-edit":
            iid = argv[argv.index("--id") + 1]
            if self._should_fail("item-edit", iid):
                raise self._boom(f"gh project item-edit --id {iid}")
            fid = argv[argv.index("--field-id") + 1]
            oid = argv[argv.index("--single-select-option-id") + 1]
            field = next(f for f in self.fields if f["id"] == fid)
            opt = next(o for o in field["options"] if o["id"] == oid)
            for it in self.items:
                if it["id"] == iid:
                    it["status"] = opt["name"]
            return {}
        raise AssertionError(f"unexpected gh json call: {argv}")

    def gql(self, query):
        self.calls.append(("gql", query))
        if "__type" in query:
            return introspection("repositories")
        if "updateProjectV2Field" in query:
            names = re.findall(r'\{name:"([^"]*)"', query)
            for f in self.fields:
                if f["name"] == "Status":
                    f["options"] = [{"id": self._nid("PVTSSO"), "name": n}
                                    for n in names]
            return {"updateProjectV2Field": {"projectV2": {"id": "PVT_1010"}}}
        pids = [p["id"] for p in self.projects]
        if self.created:
            pids.append(self.created["id"])
        pid = next(pid for pid in pids if f'"{pid}"' in query)
        row = next(p for p in self.projects + ([self.created] if self.created else [])
                   if p["id"] == pid)
        nodes = ([{"owner": {"login": "mkosinov"}, "name": "superagents"}]
                 if (pid in self.linked_pids or (self.created and pid == self.created["id"]
                                                 and self.linked)) else [])
        return {"node": {"id": pid, "number": row["number"], "title": row["title"],
                         "repositories": {"nodes": nodes}}}


class TestFormatPartialFailure(unittest.TestCase):
    """The partial-failure report: what exists, per-resource cleanup, adopt."""

    def test_full_report_after_field_and_seed_stages(self):
        created = {
            "project": {"id": "PVT_kwDOABVmAs4A", "number": 7, "title": "B"},
            "owner": "mkosinov", "repo": "mkosinov/superagents",
            "fields": [("Status", "PVTSSF_1"), ("Priority", "PVTSSF_2")],
            "items": [(1, "https://github.com/mkosinov/superagents/issues/1", "PVTI_1"),
                      (2, "https://github.com/mkosinov/superagents/issues/2", "PVTI_2")],
        }
        text = bb.format_partial_failure(created, "boom at item-edit")
        self.assertIn("PVT_kwDOABVmAs4A", text)
        self.assertIn("#7", text)
        self.assertIn("Status", text)
        self.assertIn("PVTSSF_1", text)
        self.assertIn("PVTI_2", text)
        self.assertIn("boom at item-edit", text)
        # per-resource cleanup route (web board page), not just project-level
        self.assertIn("web", text.lower())
        # adopt recovery route with the runnable command shape
        self.assertIn("adopt 7", text)
        self.assertIn("--repo mkosinov/superagents", text)

    def test_minimal_report_after_create_only(self):
        created = {"project": {"id": "PVT_x", "number": 3, "title": "T"},
                   "owner": "mkosinov", "repo": "mkosinov/superagents",
                   "fields": [], "items": []}
        text = bb.format_partial_failure(created, "gh: field-delete failed")
        self.assertIn("PVT_x", text)
        self.assertIn("#3", text)
        self.assertIn("field-delete", text)
        self.assertIn("adopt 3", text)
        # nothing created besides the project: no empty field/item bullets
        self.assertNotIn("fields created", text)
        self.assertNotIn("items added", text)

    def test_report_when_nothing_was_created(self):
        created = {"project": None, "owner": "mkosinov",
                   "repo": "mkosinov/superagents", "fields": [], "items": []}
        text = bb.format_partial_failure(created, "gh error (create): boom")
        self.assertIn("nothing", text.lower())
        self.assertIn("boom", text)
        self.assertNotIn("adopt ", text)  # no number exists to adopt


class TestCmdInit(unittest.TestCase):
    """init wiring on fixtures: exact argv sequence, refusals, recovery."""

    def run_init(self, fake, args, etalon=None):
        """Capture stdout/stderr; cmd_init signals via return code / SystemExit."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = bb.cmd_init(args, etalon or INIT_ETALON,
                             gh=fake.gh, gh_json=fake.gh_json, gql=fake.gql)
        return rc, out.getvalue(), err.getvalue()

    AUTH = ("gh", "auth", "status")

    def LIST(self, owner="mkosinov"):
        return ("gh", "project", "list", "--owner", owner,
                "--format", "json", "--limit", "1000")

    def FIELD_LIST(self):
        return ("gh", "project", "field-list", "7", "--owner", "mkosinov",
                 "--format", "json", "--limit", "200")

    def ITEM_LIST(self):
        return ("gh", "project", "item-list", "7", "--owner", "mkosinov",
                 "--format", "json", "--limit", "1000")

    def test_happy_path_argv_sequence(self):
        """The verified mutation sequence, --limit on every list read."""
        fake = InitGh()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            rc, stdout, _ = self.run_init(
                fake, init_args(title="New Board", out=str(out)))
            self.assertEqual(rc, 0, stdout)
            # 1. auth pre-flight; 2. ONE project list read feeding both guards
            self.assertEqual(fake.calls[0], self.AUTH)
            self.assertEqual(fake.calls[1], self.LIST())
            self.assertEqual(fake.calls[2][0], "gql")  # guard introspection
            self.assertIn("__type", fake.calls[2][1])
            self.assertEqual(sum(1 for c in fake.calls
                                 if c[1:3] == ("project", "list")), 1)
            # 3. create (explicit owner, never @me)
            self.assertEqual(
                fake.calls[3],
                ("gh", "project", "create", "--owner", "mkosinov",
                 "--title", "New Board", "--format", "json"))
            # 4. field-list (builtin lookup) → field-delete → verify read-back
            self.assertEqual(fake.calls[4], self.FIELD_LIST())
            self.assertEqual(
                fake.calls[5],
                ("gh", "project", "field-delete", "--id", "PVTSSF_Status"))
            self.assertEqual(fake.calls[6], self.FIELD_LIST())
            self.assertNotIn("Todo", json.dumps(fake.fields))  # builtin gone
            # 5. one field-create per etalon field (etalon order) + verify read
            creates = [c for c in fake.calls if c[1:3] == ("project", "field-create")]
            self.assertEqual(
                creates[0],
                ("gh", "project", "field-create", "7", "--owner", "mkosinov",
                 "--name", "Status", "--data-type", "SINGLE_SELECT",
                 "--single-select-options", "Hold,Backlog,In IMPL",
                 "--format", "json"))
            self.assertEqual(creates[1][creates[1].index("--name") + 1], "Priority")
            self.assertEqual(creates[1][creates[1].index("--single-select-options") + 1],
                             "Critical,High,Medium,Low")
            field_lists = [c for c in fake.calls if c[1:3] == ("project", "field-list")]
            self.assertEqual(len(field_lists), 4)  # lookup + 3 verify reads
            # 6. link
            self.assertIn(("gh", "project", "link", "7", "--owner", "mkosinov",
                           "--repo", "mkosinov/superagents"), fake.calls)
            link_i = fake.calls.index(("gh", "project", "link", "7", "--owner",
                                       "mkosinov", "--repo", "mkosinov/superagents"))
            # …verified by a node read (repos connection), not assumed
            self.assertEqual(fake.calls[link_i + 1][0], "gql")
            self.assertIn('"PVT_1010"', fake.calls[link_i + 1][1])
            self.assertIn("repositories", fake.calls[link_i + 1][1])
            # 7. seed: ONE issue list call, explicit --limit 10000, json fields
            lists = [c for c in fake.calls if c[1:3] == ("issue", "list")]
            self.assertEqual(len(lists), 1)
            self.assertEqual(
                lists[0],
                ("gh", "issue", "list", "--repo", "mkosinov/superagents",
                 "--state", "open", "--limit", "10000", "--json", "number,url"))
            adds = [c for c in fake.calls if c[1:3] == ("project", "item-add")]
            self.assertEqual(len(adds), 2)
            for i, c in enumerate(adds, start=1):
                self.assertEqual(
                    c,
                    ("gh", "project", "item-add", "7", "--owner", "mkosinov",
                     "--url", f"https://github.com/mkosinov/superagents/issues/{i}",
                     "--format", "json"))
            # item-edit: ids read at run time (project id from create json,
            # field id from field-list, option id from field-list)
            edits = [c for c in fake.calls if c[1:3] == ("project", "item-edit")]
            self.assertEqual(len(edits), 2)
            opt_id = next(o["id"] for f in fake.fields if f["name"] == "Status"
                          for o in f["options"] if o["name"] == "Backlog")
            for c in edits:
                self.assertEqual(
                    c,
                    ("gh", "project", "item-edit", "--project-id", "PVT_1010",
                     "--id", c[c.index("--id") + 1], "--field-id", "PVTSSF_Status",
                     "--single-select-option-id", opt_id))
            self.assertEqual(
                edits[0][edits[0].index("--id") + 1], "PVTI_1")
            self.assertEqual(
                edits[1][edits[1].index("--id") + 1], "PVTI_2")
            # 8. verification read after EVERY item mutation (add and edit)
            item_lists = [c for c in fake.calls if c[1:3] == ("project", "item-list")]
            self.assertEqual(len(item_lists), 4)
            self.assertTrue(all(c == self.ITEM_LIST() for c in item_lists))
            # 9. config written with live ids
            config = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(config["project_id"], "PVT_1010")
            self.assertEqual(config["project_number"], 7)
            self.assertEqual(config["fields"],
                             {"Status": "PVTSSF_Status", "Priority": "PVTSSF_Priority"})
            self.assertEqual(config["host_budgets"], {"imac": 2, "macbook": 1})
            self.assertIn("init #7", stdout)

    def test_owner_flag_overrides_repo_owner(self):
        fake = InitGh()
        with tempfile.TemporaryDirectory() as td:
            rc, _, _ = self.run_init(
                fake, init_args(title="New Board", owner="someone",
                                out=str(Path(td) / "c.json")))
            self.assertEqual(rc, 0)
            self.assertEqual(
                fake.calls[3],
                ("gh", "project", "create", "--owner", "someone",
                 "--title", "New Board", "--format", "json"))

    def test_issue_list_cap_refuses_with_report(self):
        """Returned length hits the cap → refuse naming it, no seeding."""
        fake = InitGh(issues=[{"number": i, "url": f"u/{i}"} for i in range(3)])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.json"
            with mock.patch.object(bb, "ISSUE_LIST_LIMIT", 2):
                rc, stdout, _ = self.run_init(fake, init_args(out=str(out)))
            self.assertEqual(rc, 1)
            self.assertIn("--limit 2", stdout)
            self.assertIn("raise", stdout)
            self.assertIn("adopt 7", stdout)  # recovery route still printed
            self.assertFalse(out.exists())
            self.assertFalse(any(c[1:3] == ("project", "item-add")
                                 for c in fake.calls))

    def test_verification_mismatch_stops_and_reports(self):
        """item-list read-back disagrees with what was added → stop, report."""
        fake = InitGh()
        original = fake.gh_json

        def gh_json(argv):
            r = original(argv)
            if argv[1] == "item-list":
                r = {"items": r["items"][:-1]}  # read-back hides the last item
            return r
        fake.gh_json = gh_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.json"
            rc, stdout, _ = self.run_init(fake, init_args(out=str(out)))
            self.assertEqual(rc, 1)
            self.assertIn("mismatch", stdout.lower())
            self.assertIn("adopt 7", stdout)
            self.assertFalse(out.exists())

    def test_auth_failure_refuses_naming_it(self):
        fake = InitGh(auth_rc=1)
        with tempfile.TemporaryDirectory() as td:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as ctx:
                    bb.cmd_init(init_args(out=str(Path(td) / "c.json")),
                                INIT_ETALON, gh=fake.gh, gh_json=fake.gh_json,
                                gql=fake.gql)
            self.assertIn("auth status", str(ctx.exception) + err.getvalue())
            self.assertIn("authenticate", str(ctx.exception) + err.getvalue())
            self.assertEqual(fake.calls, [self.AUTH])  # nothing after

    def test_existing_config_refuses_before_any_mutation(self):
        fake = InitGh()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "board_config.json"
            out.write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                bb.cmd_init(init_args(out=str(out)), INIT_ETALON,
                            gh=fake.gh, gh_json=fake.gh_json, gql=fake.gql)
            self.assertIn("duplicate project", str(ctx.exception))
            # etalon → auth → guards: only the auth call happened, no mutations
            self.assertEqual(fake.calls, [self.AUTH])
            self.assertEqual(out.read_text(encoding="utf-8"), "{}")

    def test_repo_already_linked_refuses_before_create(self):
        fake = InitGh(projects=[{"number": 4, "id": "PVT_4", "title": "Old",
                                 "closed": False}],
                      linked_pids={"PVT_4"})
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit) as ctx:
                bb.cmd_init(init_args(out=str(Path(td) / "c.json")), INIT_ETALON,
                            gh=fake.gh, gh_json=fake.gh_json, gql=fake.gql)
            self.assertIn("already linked", str(ctx.exception))
            created = [c for c in fake.calls if c[1:3] == ("project", "create")]
            self.assertEqual(created, [])  # no mutation after refusal

    def test_title_collision_warns_and_proceeds(self):
        fake = InitGh(projects=[{"number": 4, "id": "PVT_4", "title": "New Board",
                                 "closed": False}])
        with tempfile.TemporaryDirectory() as td:
            rc, stdout, _ = self.run_init(
                fake, init_args(title="New Board", out=str(Path(td) / "c.json")))
            self.assertEqual(rc, 0)
            self.assertIn("title collision", stdout.lower())

    def test_midrun_failure_reports_created_and_recovery(self):
        """field-create for Priority fails → report + NO further mutations."""
        fake = InitGh(fail_object={"field-create": "Priority"})
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.json"
            rc, stdout, _ = self.run_init(fake, init_args(out=str(out)))
            self.assertEqual(rc, 1)
            self.assertIn("partial init", stdout.lower())
            self.assertIn("PVT_1010", stdout)
            self.assertIn("#7", stdout)
            self.assertIn("Status", stdout)       # the created field is named
            self.assertIn("adopt 7", stdout)
            self.assertIn("web", stdout.lower())  # per-resource cleanup route
            self.assertFalse(out.exists())
            after = [c for c in fake.calls
                     if c[1:3] in (("project", "link"), ("issue", "list"),
                                   ("project", "item-add"))]
            self.assertEqual(after, [])  # stopped at the failure point

    def test_midrun_failure_at_link(self):
        fake = InitGh(fail_verb="link")
        with tempfile.TemporaryDirectory() as td:
            rc, stdout, _ = self.run_init(fake, init_args(out=str(Path(td) / "c.json")))
            self.assertEqual(rc, 1)
            self.assertIn("partial init", stdout.lower())
            self.assertIn("adopt 7", stdout)
            seeded = [c for c in fake.calls if c[1:3] == ("issue", "list")]
            self.assertEqual(seeded, [])

    def test_midrun_failure_at_item_add(self):
        fake = InitGh(fail_object={
            "item-add": "https://github.com/mkosinov/superagents/issues/2"})
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.json"
            rc, stdout, _ = self.run_init(fake, init_args(out=str(out)))
            self.assertEqual(rc, 1)
            self.assertIn("adopt 7", stdout)
            self.assertIn("issues/1", stdout)  # the one added item is named
            self.assertFalse(out.exists())

    def test_midrun_failure_at_create_reports_nothing_created(self):
        fake = InitGh(fail_verb="create")
        with tempfile.TemporaryDirectory() as td:
            rc, stdout, _ = self.run_init(fake, init_args(out=str(Path(td) / "c.json")))
            self.assertEqual(rc, 1)
            self.assertIn("partial init", stdout.lower())
            self.assertIn("project create", stdout)
            # nothing was created: no bogus resources, no adopt route
            self.assertIn("nothing", stdout.lower())
            self.assertNotIn("adopt ", stdout)

    def test_field_delete_failure_uses_graphql_fallback(self):
        """Built-in Status undeletable → documented GraphQL option-list
        rewrite on the still-empty project; the sequence continues."""
        fake = InitGh(fail_object={"field-delete": "PVTSSF_Status"})
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.json"
            rc, stdout, _ = self.run_init(fake, init_args(out=str(out)))
            self.assertEqual(rc, 0, stdout)
            self.assertIn("fallback", stdout.lower())
            mutations = [c for c in fake.calls if c[0] == "gql"
                         and "updateProjectV2Field" in c[1]]
            self.assertEqual(len(mutations), 1)
            self.assertIn('"PVTSSF_Status"', mutations[0][1])
            self.assertIn('name:"Hold"', mutations[0][1])
            # Status is NOT re-created (the rewrite made it the etalon field)
            created_names = [c[c.index("--name") + 1] for c in fake.calls
                             if c[1:3] == ("project", "field-create")]
            self.assertEqual(created_names, ["Priority"])
            config = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(config["project_id"], "PVT_1010")
            self.assertEqual(config["fields"]["Status"], "PVTSSF_Status")

    def test_fallback_failure_stops_with_partial_report(self):
        """GraphQL fallback also fails → stop with the partial report."""
        fake = InitGh(fail_object={"field-delete": "PVTSSF_Status"})
        original = fake.gql

        def gql(query):
            if "updateProjectV2Field" in query:
                raise SystemExit("gh api error: graphql refused the mutation")
            return original(query)
        fake.gql = gql
        with tempfile.TemporaryDirectory() as td:
            rc, stdout, _ = self.run_init(fake, init_args(out=str(Path(td) / "c.json")))
            self.assertEqual(rc, 1)
            self.assertIn("partial init", stdout.lower())
            self.assertIn("adopt 7", stdout)


if __name__ == "__main__":
    unittest.main()
