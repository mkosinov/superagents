"""Unit tests for board_bootstrap.py — etalon parser (scenario 7) and dry-run plan.

Run from repo root:
    python3 -m unittest tests.test_board_bootstrap -v

stdlib unittest only (repo has no pytest). The module under test lives in
.zcode/scripts/ (the .opencode/scripts/ copy is a byte-identical twin).
"""
import argparse
import json
import subprocess
import sys
import tempfile
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
