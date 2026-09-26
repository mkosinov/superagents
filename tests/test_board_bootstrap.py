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
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
