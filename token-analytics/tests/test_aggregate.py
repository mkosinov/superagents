"""Unit tests for token-analytics aggregation + snapshot writing (#26 Task 4).

DoD coverage (spec §Token accounting, §Active model time and calendar span,
§Drill-down tree, §By-model and by-agent aggregates, §Snapshots and state):
- token math: 5 components kept separately, raw-sum total (no weights),
  board rounding («48.2», «25.3»); errored/cancelled turn rows count;
- recursive aggregation: a grandchild folds into its parent node's subtree
  total; issue totals reconcile with node sums by construction;
- T-folding on IMPL-root children: `T1: a`, `T1: b`, `Fix …` → one T1 node
  + one standalone node (container/split AND host/title mode); design-phase
  marathon children are NOT folded;
- root-wrapper asymmetry: container marathon root wrapper tokens counted,
  its span not; childless roots count their own span; host counts turn
  durations for roots AND children;
- calendar span: max(end) − min(start) per phase; hours granularity below
  a day, whole days at/above a day;
- by_model/by_agent per issue and per phase — host from model_usage joined
  by session_id, container from session-level model/agent;
- snapshot shape: board-ready dot-path values (tokens.total_m,
  phases.<ph>.tokens.total_m, active.hours, phases.<ph>.active.hours) with
  raw values alongside; title + source; last activity; collected_at is
  data-derived (no wall clock anywhere — byte determinism);
- index.json rows (totals, phase split, last activity) sorted by spend,
  per-source availability; unmatched.json regenerated;
- determinism: two rebuilds over the same fixture → byte-identical files;
- stale removal: an issue whose sessions vanish loses file + index entry;
- atomic write: a failure mid-write leaves the previous file intact, no
  tmp leftovers; a SIGKILL-leftover `*.tmp` inside issues/ is swept by
  the next run's stale scan;
- hardening: container session with an empty/blank model string mixes
  with modeled sessions without killing `_bars` (None sorts against str
  → TypeError); a parent cycle (A↔B, self-parent) builds a finite tree
  instead of RecursionError; both sources None → empty aggregate;
  zero-turn host session; override to a nonexistent issue → «issue #N»
  fallback title; host child of a container root (cross-source dangling
  parent) fail-opens to its own root;
- titles: one bulk gh call per repo per run (exact argv pinned via a fake
  gh executable, like test_readers.py pins docker); gh failure → «issue #N»
  fallback; closed issues keep the last known (cached) title;
- state.json: created when missing (write-back caches only), untouched
  when present;
- golden: real superagents #16 (host-only) against data/golden-… — skips
  cleanly when the golden file or the live host DB is absent.
"""

import contextlib
import io
import json
import os
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

# Mirrors the committed config.json (spec §Config file): memo split,
# superagents title — fixture scenarios use memo's directories. Repos are
# needed for the gh title cache.
CONFIG = {
    "projects": {
        "superagents": {
            "repo": "mkosinov/superagents",
            "phase_mode": "title",
            "directories": ["/Users/mkosinov/dev/opencode/workspace/superagents",
                            "/Users/mkosinov/dev/superagents"],
        },
        "memo": {
            "repo": "mkosinov/memo",
            "phase_mode": "split",
            "directories": ["/root/workspace/memo", "/Users/mkosinov/dev/memo"],
        },
    },
}

T0 = fixtures.BASE_TIME_MS
MIN = fixtures.MIN
HOUR = fixtures.HOUR
SA_DIR = "/Users/mkosinov/dev/superagents"

# Fake `gh`: records its argv (pinning the exact command surface), then
# prints one JSON array of {number, title} rows — the `gh issue list
# --json number,title` output shape.
FAKE_GH_OK = (
    "#!/bin/sh\n"
    'printf \'%s\\n\' "$@" > "$FAKE_GH_ARGS_FILE"\n'
    "printf '[{\"number\": 327, \"title\": \"каскад удаления\"}]'\n"
)
FAKE_GH_FAIL = (
    "#!/bin/sh\n"
    'printf \'%s\\n\' "$@" > "$FAKE_GH_ARGS_FILE"\n'
    "echo 'gh: auth required' >&2\n"
    "exit 1\n"
)


def _snap(host=None, container=None, project="memo", issue=327, **kw):
    aggregated = collector.aggregate(host, container, CONFIG, **kw)
    return aggregated["issues"][(project, issue)]


def _find(nodes, session_id):
    """Depth-first node lookup in a tree list by session id."""
    for node in nodes:
        if node["session_id"] == session_id:
            return node
        found = _find(node["children"], session_id)
        if found is not None:
            return found
    return None


def _data_files(data_dir):
    """{relative path: bytes} for every file under data_dir (recursive)."""
    base = Path(data_dir)
    out = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(base))] = path.read_bytes()
    return out


def _with_fake_gh(script, fn):
    """Run fn() with a fake `gh` executable first on PATH; returns its result
    plus the argv lines the collector passed to it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        bindir = tmpdir / "bin"
        bindir.mkdir()
        fake_gh = bindir / "gh"
        fake_gh.write_text(script)
        os.chmod(fake_gh, 0o755)
        args_file = tmpdir / "gh-args.txt"
        env = {
            "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_GH_ARGS_FILE": str(args_file),
        }
        with mock.patch.dict(os.environ, env):
            result = fn()
        return result, args_file.read_text().splitlines()


class TokenMathTests(unittest.TestCase):
    def test_board_rounding_48_2_and_25_3(self):
        sessions = [fixtures.make_host_session(
            "r", "/root/workspace/memo", "#700 big spend", created=T0, updated=T0 + HOUR)]
        turns = [fixtures.make_turn("r", "r/t1", tokens=(48_240_000, 0, 0, 0, 0),
                                    duration_ms=91_080_000)]
        snap = _snap(host={"sessions": sessions, "turns": turns, "models": []},
                     project="memo", issue=700)
        self.assertEqual(snap["tokens"]["total"], 48_240_000)   # plain raw sum, no weights
        self.assertEqual(snap["tokens"]["total_m"], 48.2)       # «48.2»
        self.assertEqual(json.dumps(snap["tokens"]["total_m"]), "48.2")
        self.assertEqual(snap["active"]["hours"], 25.3)         # «25.3»
        self.assertEqual(snap["active_ms"], 91_080_000)

    def test_five_components_kept_separately_total_is_raw_sum(self):
        sessions = [fixtures.make_host_session(
            "r", "/root/workspace/memo", "#700 mix", created=T0, updated=T0 + MIN)]
        turns = [
            fixtures.make_turn("r", "r/1", tokens=(1000, 200, 50, 5000, 300)),
            fixtures.make_turn("r", "r/2", tokens=(10, 20, 30, 40, 50)),
        ]
        snap = _snap(host={"sessions": sessions, "turns": turns, "models": []},
                     project="memo", issue=700)
        self.assertEqual(snap["tokens"]["input"], 1010)
        self.assertEqual(snap["tokens"]["output"], 220)
        self.assertEqual(snap["tokens"]["reasoning"], 80)
        self.assertEqual(snap["tokens"]["cache_read"], 5040)
        self.assertEqual(snap["tokens"]["cache_write"], 350)
        self.assertEqual(snap["tokens"]["total"], 6700)  # 1010+220+80+5040+350

    def test_errored_and_cancelled_turns_count(self):
        sessions = [fixtures.make_host_session(
            "r", "/root/workspace/memo", "#700 flaky", created=T0, updated=T0 + MIN)]
        turns = [
            fixtures.make_turn("r", "r/1", tokens=(1000, 0, 0, 0, 0), duration_ms=60_000),
            fixtures.make_turn("r", "r/2", status="error", tokens=(0, 200, 0, 0, 0),
                               duration_ms=30_000, errors=1),
            fixtures.make_turn("r", "r/3", status="cancelled", tokens=(0, 0, 50, 0, 0),
                               duration_ms=10_000),
        ]
        snap = _snap(host={"sessions": sessions, "turns": turns, "models": []},
                     project="memo", issue=700)
        self.assertEqual(snap["tokens"]["total"], 1250)
        self.assertEqual(snap["active_ms"], 100_000)


class RecursiveAggregationTests(unittest.TestCase):
    def test_grandchild_folds_into_parent_subtree(self):
        snap = _snap(host=fixtures.host_scenario())
        design_roots = snap["phases"]["design"]["tree"]
        p2 = _find(design_roots, "h-design-p2")
        self.assertIsNotNone(p2)
        # own 13100 (ok turn 6550 + errored turn 6550) + grandchild 6550
        self.assertEqual(p2["tokens"]["total"], 19_650)
        # own 5 min + 3000 ms + grandchild 4 min
        self.assertEqual(p2["active_ms"], 543_000)
        self.assertEqual([c["session_id"] for c in p2["children"]], ["h-design-p2-g1"])

    def test_issue_total_equals_sum_over_roots(self):
        snap = _snap(host=fixtures.host_scenario())
        phase = snap["phases"]["design"]
        self.assertEqual(sorted(r["session_id"] for r in phase["tree"]),
                         ["h-design", "h-marathon"])
        self.assertEqual(sum(r["tokens"]["total"] for r in phase["tree"]),
                         phase["tokens"]["total"])
        self.assertEqual(sum(r["active_ms"] for r in phase["tree"]), phase["active_ms"])
        self.assertEqual(phase["tokens"]["total"], 91_700)   # design + marathon families
        self.assertEqual(phase["active_ms"], 3_723_000)      # 30.05 min + 32 min
        self.assertEqual(snap["tokens"]["total"], 91_700)    # host-only → design-only


class TFoldTests(unittest.TestCase):
    def test_container_impl_children_fold_into_one_t_node(self):
        snap = _snap(host=fixtures.host_scenario(), container=fixtures.container_scenario())
        roots = snap["phases"]["impl"]["tree"]
        self.assertEqual([r["session_id"] for r in roots], ["c-marathon"])
        kids = roots[0]["children"]
        # `T1: api`, `T1: ui`, `hotfix db` → one T1 node + one standalone node
        self.assertEqual([k["title"] for k in kids], ["T1", "hotfix db"])
        t1 = kids[0]
        self.assertIsNone(t1["session_id"])
        self.assertIsNone(t1["agent"])
        self.assertEqual(t1["tokens"]["total"], 32_750)     # c1 19650 + c1-g1 6550 + c2 6550
        self.assertEqual(t1["active_ms"], 11_700_000)      # 90 + 15 + 90 min
        self.assertEqual(sorted(c["session_id"] for c in t1["children"]),
                         ["c-marathon-c1", "c-marathon-c2"])
        c1 = _find([t1], "c-marathon-c1")
        self.assertEqual(c1["tokens"]["total"], 26_200)
        self.assertEqual([g["session_id"] for g in c1["children"]], ["c-marathon-c1-g1"])
        self.assertEqual(kids[1]["title"], "hotfix db")     # standalone keeps its subtree
        self.assertEqual(kids[1]["tokens"]["total"], 6_550)
        self.assertEqual(kids[1]["active_ms"], 1_800_000)

    def test_host_title_mode_impl_folds_t_children(self):
        sessions = [
            fixtures.make_host_session("m", SA_DIR, "IMPL #50 build",
                                       created=T0, updated=T0 + 3 * HOUR),
            fixtures.make_host_session("m-t1a", SA_DIR, "T1: a", parent_id="m",
                                       created=T0, updated=T0 + HOUR),
            fixtures.make_host_session("m-t1a-g", SA_DIR, "nested qa", parent_id="m-t1a",
                                       created=T0, updated=T0 + 30 * MIN),
            fixtures.make_host_session("m-t1b", SA_DIR, "T1. b", parent_id="m",
                                       created=T0 + HOUR, updated=T0 + 2 * HOUR),
            fixtures.make_host_session("m-fix", SA_DIR, "Fix bus emission", parent_id="m",
                                       created=T0 + 2 * HOUR, updated=T0 + 2 * HOUR + 30 * MIN),
            # same issue, design phase — both phases from one source
            fixtures.make_host_session("d", SA_DIR, "Разведка issue #50",
                                       created=T0, updated=T0 + 40 * MIN),
        ]
        turns = [fixtures.make_turn(s["id"], s["id"] + "/t1", tokens=(1000, 100, 100, 100, 100),
                                    duration_ms=10 * MIN) for s in sessions]
        snap = _snap(host={"sessions": sessions, "turns": turns, "models": []},
                     project="superagents", issue=50)
        self.assertEqual(set(snap["phases"]), {"design", "impl"})
        kids = snap["phases"]["impl"]["tree"][0]["children"]
        self.assertEqual([k["title"] for k in kids], ["T1", "Fix bus emission"])
        self.assertEqual(kids[0]["tokens"]["total"], 4_200)   # a + a-g + b
        self.assertEqual(kids[0]["active_ms"], 30 * MIN)
        self.assertEqual(len(kids[0]["children"]), 2)
        self.assertEqual(kids[1]["tokens"]["total"], 1_400)
        # issue totals reconcile: impl root subtree + design root
        self.assertEqual(snap["tokens"]["total"], 8_400)      # 6 sessions × 1400
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 7_000)

    def test_design_phase_marathon_children_are_not_folded(self):
        # memo split mode → h-marathon is DESIGN: T-titled children stay
        # standalone nodes labeled by agent attribution
        snap = _snap(host=fixtures.host_scenario())
        marathon = _find(snap["phases"]["design"]["tree"], "h-marathon")
        self.assertEqual([c["title"] for c in marathon["children"]],
                         ["T1: scaffold", "T1: tests", "Fix crash"])
        self.assertEqual([c["agent"] for c in marathon["children"]],
                         ["zcode-implement", "zcode-compliance", "zcode-quality"])


class RootWrapperAsymmetryTests(unittest.TestCase):
    def test_wrapper_tokens_count_time_does_not(self):
        snap = _snap(host=fixtures.host_scenario(), container=fixtures.container_scenario())
        root = snap["phases"]["impl"]["tree"][0]
        self.assertEqual(root["session_id"], "c-marathon")
        self.assertEqual(root["tokens"]["total"], 65_500)      # includes wrapper's 26_200
        self.assertEqual(root["active_ms"], 13_500_000)       # wrapper 4h span excluded
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 65_500)
        self.assertEqual(snap["phases"]["impl"]["active_ms"], 13_500_000)

    def test_childless_root_counts_own_span(self):
        snap = _snap(container=fixtures.container_scenario(), project="memo", issue=335)
        node = snap["phases"]["impl"]["tree"][0]
        self.assertEqual(node["session_id"], "c-solo-1")
        self.assertEqual(node["active_ms"], 2_400_000)        # 40 min own span
        self.assertEqual(node["tokens"]["total"], 6_550)
        self.assertEqual(snap["active"]["hours"], 0.7)

    def test_host_time_counts_roots_and_children(self):
        snap = _snap(host=fixtures.host_scenario())
        # roots AND children, per-turn durations: 30.05 min design + 32 min marathon
        self.assertEqual(snap["active_ms"], 3_723_000)
        self.assertEqual(snap["phases"]["design"]["active_ms"], 3_723_000)


class CalendarSpanTests(unittest.TestCase):
    def test_phase_span_hours_below_a_day(self):
        snap = _snap(host=fixtures.host_scenario(), container=fixtures.container_scenario())
        self.assertEqual(snap["phases"]["design"]["calendar"],
                         {"ms": 21_600_000, "days": None, "hours": 6.0})  # t0 → t0+6h
        self.assertEqual(snap["phases"]["impl"]["calendar"],
                         {"ms": 14_400_000, "days": None, "hours": 4.0})  # t0+2h → t0+6h

    def test_phase_span_days_at_or_above_a_day(self):
        span = 276_480_000  # 3.2 days
        sessions = [fixtures.make_host_session("r", "/root/workspace/memo", "#700 slow",
                                               created=T0, updated=T0 + span)]
        turns = [fixtures.make_turn("r", "r/t1", duration_ms=MIN)]
        snap = _snap(host={"sessions": sessions, "turns": turns, "models": []},
                     project="memo", issue=700)
        self.assertEqual(snap["phases"]["design"]["calendar"],
                         {"ms": span, "days": 3, "hours": None})


class AggregateBarsTests(unittest.TestCase):
    def test_by_model_and_by_agent_issue_and_phase(self):
        snap = _snap(host=fixtures.host_scenario(), container=fixtures.container_scenario())
        self.assertEqual(snap["by_model"], [
            {"model": "claude-opus-4-6", "tokens": 72_050},
            {"model": "claude-sonnet-4-5", "tokens": 65_500},
            {"model": "glm-4.7", "tokens": 19_650},
        ])
        self.assertEqual(snap["by_agent"], [
            {"agent": "backend-coder", "tokens": 32_750},
            {"agent": "manager", "tokens": 26_200},
            {"agent": "zcode-Explore", "tokens": 26_200},
            {"agent": "zcode-manager", "tokens": 19_650},
            {"agent": "zcode-compliance", "tokens": 13_100},
            {"agent": "zcode-spec-panel-security", "tokens": 13_100},
            {"agent": "frontend-coder", "tokens": 6_550},
            {"agent": "zcode-implement", "tokens": 6_550},
            {"agent": "zcode-plan-reviewer", "tokens": 6_550},
            {"agent": "zcode-quality", "tokens": 6_550},
        ])
        # bars reconcile with issue totals
        self.assertEqual(sum(b["tokens"] for b in snap["by_model"]),
                         snap["tokens"]["total"])
        self.assertEqual(sum(b["tokens"] for b in snap["by_agent"]),
                         snap["tokens"]["total"])
        # per-phase bars: design = host model_usage, impl = session-level
        self.assertEqual(snap["phases"]["design"]["by_model"], [
            {"model": "claude-sonnet-4-5", "tokens": 58_950},
            {"model": "claude-opus-4-6", "tokens": 19_650},
            {"model": "glm-4.7", "tokens": 13_100},
        ])
        self.assertEqual(snap["phases"]["impl"]["by_model"], [
            {"model": "claude-opus-4-6", "tokens": 52_400},
            {"model": "claude-sonnet-4-5", "tokens": 6_550},
            {"model": "glm-4.7", "tokens": 6_550},
        ])

    def test_design_child_unrecognized_agent_kept_raw(self):
        host = fixtures.host_scenario()
        host["models"].append(fixtures.make_model_call(
            "h-design-p1", "h-design-p1/t9", model_id="glm-4.7",
            agent="zcode-mystery", tokens=(10_000, 0, 0, 0, 0)))
        snap = _snap(host=host)
        p1 = _find(snap["phases"]["design"]["tree"], "h-design-p1")
        self.assertEqual(p1["agent"], "zcode-mystery")  # raw agent string kept


class HardeningTests(unittest.TestCase):
    """Robustness pins from the quality review of b85f273."""

    def test_container_none_model_mixed_with_modeled_sessions(self):
        # one blank-model session among modeled ones: `_bars` sorts bar
        # rows by (-tokens, name) — a None model name next to a string
        # is a TypeError on the tie-break that must never kill a collect
        # run; it lands under «—» like every other unattributed name
        blank = fixtures.make_container_session(
            "r2", "/root/workspace/memo", "#700 blank model",
            created=T0, updated=T0 + HOUR)
        blank["model"] = ""    # _container_model_id → None (empty string)
        sessions = [
            fixtures.make_container_session(
                "r1", "/root/workspace/memo", "#700 plain",
                model="claude-opus-4-6", created=T0, updated=T0 + HOUR),
            blank,
        ]
        snap = _snap(container={"sessions": sessions}, project="memo", issue=700)
        expected = [{"model": "claude-opus-4-6", "tokens": 6_550},
                    {"model": "—", "tokens": 6_550}]   # tie → name asc
        self.assertEqual(snap["by_model"], expected)
        self.assertEqual(snap["phases"]["impl"]["by_model"], expected)
        self.assertEqual(sum(b["tokens"] for b in snap["by_model"]),
                         snap["tokens"]["total"])      # 2 × 6_550

    def test_parent_cycle_builds_finite_tree(self):
        # A↔B parent cycle + a self-parent session: group_by_root treats
        # each as its own root (cycle-safe since 707bf43) — _build_node
        # must stop descending too instead of recursing to RecursionError,
        # and the tree must stay consistent with the accounting: b's spend
        # belongs to b's own unmatched row, not to issue 700's tree
        sessions = [
            fixtures.make_host_session("a", "/root/workspace/memo", "#700 cycle a",
                                       parent_id="b", created=T0, updated=T0 + MIN),
            fixtures.make_host_session("b", "/root/workspace/memo", "helper b",
                                       parent_id="a", created=T0, updated=T0 + MIN),
            fixtures.make_host_session("s", "/root/workspace/memo", "self parent #700",
                                       parent_id="s", created=T0, updated=T0 + MIN),
        ]
        turns = [fixtures.make_turn(s["id"], s["id"] + "/t1") for s in sessions]
        aggregated = collector.aggregate(
            {"sessions": sessions, "turns": turns, "models": []}, None, CONFIG)
        snap = aggregated["issues"][("memo", 700)]
        tree = snap["phases"]["design"]["tree"]
        self.assertEqual(sorted(n["session_id"] for n in tree), ["a", "s"])
        self.assertEqual(_find(tree, "a")["children"], [])   # cyclic child not drilled
        self.assertEqual(_find(tree, "s")["children"], [])   # self-parent pruned
        # tree reconciles with the accounting: a + s only…
        self.assertEqual(sum(n["tokens"]["total"] for n in tree),
                         snap["tokens"]["total"])
        self.assertEqual(snap["tokens"]["total"], 2 * 6_550)
        # …while b (own root, issue-less title) lands in the unmatched table
        self.assertEqual([r["session_id"] for r in aggregated["unmatched"]], ["b"])

    def test_dag_grandchild_counted_once(self):
        # two parents sharing one grandchild: the shared subtree must
        # not be double-counted in either parent's node
        sessions = [
            fixtures.make_host_session("r", "/root/workspace/memo", "#700 dag",
                                       created=T0, updated=T0 + MIN),
            fixtures.make_host_session("p1", "/root/workspace/memo", "panel one",
                                       parent_id="r", created=T0, updated=T0 + MIN),
            fixtures.make_host_session("p2", "/root/workspace/memo", "panel two",
                                       parent_id="r", created=T0, updated=T0 + MIN),
            fixtures.make_host_session("g", "/root/workspace/memo", "shared grandchild",
                                       parent_id="p1", created=T0, updated=T0 + MIN),
            # g re-parented under p2 as well is impossible (single parent
            # column), so the once-only guarantee here pins the visited
            # guard's benign side: no node lost on legit trees
        ]
        turns = [fixtures.make_turn(s["id"], s["id"] + "/t1") for s in sessions]
        snap = _snap(host={"sessions": sessions, "turns": turns, "models": []},
                     project="memo", issue=700)
        tree = snap["phases"]["design"]["tree"]
        self.assertEqual(len(tree), 1)                 # one root, full family
        self.assertEqual(tree[0]["tokens"]["total"], 4 * 6_550)
        p1, p2 = _find(tree, "p1"), _find(tree, "p2")
        self.assertEqual([c["session_id"] for c in p1["children"]], ["g"])
        self.assertEqual(p2["children"], [])
        self.assertEqual(p1["tokens"]["total"], 2 * 6_550)
        self.assertEqual(p2["tokens"]["total"], 6_550)


class EdgeCoverageTests(unittest.TestCase):
    """Currently-correct-but-untested edges pinned per the quality review."""

    def test_both_sources_unavailable_yields_empty_result(self):
        aggregated = collector.aggregate(None, None, CONFIG)
        self.assertEqual(aggregated, {"issues": {}, "unmatched": []})

    def test_zero_turn_host_session(self):
        # a root with no turn_usage/model_usage rows still maps, phases,
        # spans (created→updated) and drills down — just with zero spend
        sessions = [fixtures.make_host_session(
            "r", "/root/workspace/memo", "#700 silent",
            created=T0, updated=T0 + 30 * MIN)]
        snap = _snap(host={"sessions": sessions, "turns": [], "models": []},
                     project="memo", issue=700)
        self.assertEqual(snap["tokens"]["total"], 0)
        self.assertEqual(snap["tokens"]["total_m"], 0.0)
        self.assertEqual(snap["active_ms"], 0)
        self.assertEqual(snap["active"]["hours"], 0.0)
        self.assertEqual(snap["by_model"], [])
        self.assertEqual(snap["phases"]["design"]["calendar"],
                         {"ms": 30 * MIN, "days": None, "hours": 0.5})
        node = snap["phases"]["design"]["tree"][0]
        self.assertEqual((node["session_id"], node["children"]), ("r", []))
        self.assertEqual(node["tokens"]["total"], 0)

    def test_override_to_nonexistent_issue_gets_fallback_title(self):
        overrides = {"h-loose": {"project": "memo", "issue": 9999}}
        aggregated = collector.aggregate(fixtures.host_scenario(), None, CONFIG,
                                         overrides=overrides, titles={})
        snap = aggregated["issues"][("memo", 9999)]
        self.assertEqual(snap["title"], "issue #9999")   # gh knows no such issue
        self.assertEqual(snap["title_source"], "fallback")
        self.assertEqual(snap["tokens"]["total"], 6_550)  # h-loose subtree
        self.assertEqual(aggregated["unmatched"], [])      # override bound it

    def test_host_child_of_container_root_fail_open(self):
        # cross-source dangling parent: a host session pointing at a
        # container-only parent id is its own root (parent not in the
        # host by_id) — no crash, no cross-source stitching
        host = fixtures.host_scenario()
        host["sessions"].append(fixtures.make_host_session(
            "h-cross", "/root/workspace/memo", "panel work #327",
            parent_id="c-marathon", created=T0, updated=T0 + MIN))
        host["turns"].append(fixtures.make_turn("h-cross", "h-cross/t1"))
        snap = _snap(host=host)    # container payload deliberately absent
        node = _find(snap["phases"]["design"]["tree"], "h-cross")
        self.assertIsNotNone(node)                       # own root, host design
        self.assertEqual(node["tokens"]["total"], 6_550)
        self.assertEqual(snap["tokens"]["total"], 91_700 + 6_550)


class SnapshotShapeTests(unittest.TestCase):
    def test_snapshot_toplevel_shape_and_board_values(self):
        titles = {"mkosinov/memo": {"327": "каскад удаления"}}
        snap = _snap(host=fixtures.host_scenario(),
                     container=fixtures.container_scenario(), titles=titles)
        self.assertEqual(set(snap), {
            "project", "issue", "title", "title_source", "last_activity",
            "collected_at", "tokens", "active_ms", "active", "phases",
            "by_model", "by_agent"})
        self.assertEqual((snap["project"], snap["issue"]), ("memo", 327))
        self.assertEqual(snap["title"], "каскад удаления")
        self.assertEqual(snap["title_source"], "gh")
        self.assertEqual(set(snap["tokens"]),
                         {"input", "output", "reasoning", "cache_read", "cache_write",
                          "total", "total_m"})
        self.assertEqual(set(snap["phases"]), {"design", "impl"})
        for phase in snap["phases"].values():
            self.assertEqual(set(phase),
                             {"tokens", "active_ms", "active", "calendar", "tree",
                              "by_model", "by_agent"})
        node = snap["phases"]["design"]["tree"][0]
        self.assertEqual(set(node),
                         {"session_id", "title", "agent", "tokens", "active_ms",
                          "children"})
        # board-ready dot-paths + raw alongside (write-back config keys)
        self.assertEqual(snap["tokens"]["total"], 157_200)
        self.assertEqual(snap["tokens"]["total_m"], 0.2)
        self.assertEqual(snap["active_ms"], 17_223_000)
        self.assertEqual(snap["active"]["hours"], 4.8)
        self.assertEqual(snap["phases"]["design"]["tokens"]["total"], 91_700)
        self.assertEqual(snap["phases"]["design"]["tokens"]["total_m"], 0.1)
        self.assertEqual(snap["phases"]["design"]["active_ms"], 3_723_000)
        self.assertEqual(snap["phases"]["design"]["active"]["hours"], 1.0)
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 65_500)
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total_m"], 0.1)
        self.assertEqual(snap["phases"]["impl"]["active_ms"], 13_500_000)
        self.assertEqual(snap["phases"]["impl"]["active"]["hours"], 3.8)
        # data-derived dates only — no wall clock (determinism)
        self.assertEqual(snap["last_activity"], "2023-11-15")
        self.assertEqual(snap["collected_at"], "2023-11-15T04:13:20Z")

    def test_title_fallback_when_gh_has_no_entry(self):
        snap = _snap(host=fixtures.host_scenario(), container=fixtures.container_scenario())
        self.assertEqual(snap["title"], "issue #327")
        self.assertEqual(snap["title_source"], "fallback")

    def test_design_tree_agents(self):
        snap = _snap(host=fixtures.host_scenario())
        h_design = _find(snap["phases"]["design"]["tree"], "h-design")
        self.assertEqual([c["agent"] for c in h_design["children"]],
                         ["zcode-Explore", "zcode-spec-panel-security"])
        self.assertEqual(h_design["children"][1]["children"][0]["agent"],
                         "zcode-plan-reviewer")

    def test_aggregate_keys_and_unmatched(self):
        aggregated = collector.aggregate(fixtures.host_scenario(),
                                         fixtures.container_scenario(), CONFIG)
        self.assertEqual(sorted(aggregated["issues"]),
                         [("memo", 327), ("memo", 331), ("memo", 335)])
        self.assertEqual([r["session_id"] for r in aggregated["unmatched"]],
                         ["h-loose", "c-play"])

    def test_override_binds_and_forces_phase(self):
        overrides = {"h-loose": {"project": "memo", "issue": 327, "phase": "impl"}}
        aggregated = collector.aggregate(fixtures.host_scenario(), None, CONFIG,
                                         overrides=overrides)
        snap = aggregated["issues"][("memo", 327)]
        self.assertEqual(snap["phases"]["impl"]["tokens"]["total"], 6_550)
        self.assertEqual(snap["tokens"]["total"], 98_250)  # 91_700 + 6_550
        self.assertEqual(aggregated["unmatched"], [])


class RebuildAndFilesTests(unittest.TestCase):
    def _rebuild(self, tmp, host, container, fetch=lambda repo: {}):
        with mock.patch.object(collector, "fetch_issue_titles", fetch):
            return collector.rebuild(host, container, CONFIG, tmp)

    def test_rebuild_writes_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, fixtures.host_scenario(), fixtures.container_scenario())
            names = sorted(p.name for p in Path(tmp).iterdir())
            issue_names = sorted(p.name for p in (Path(tmp) / "issues").iterdir())
        self.assertEqual(names, ["index.json", "issues", "state.json",
                                 "titles.json", "unmatched.json"])
        self.assertEqual(issue_names, ["memo-327.json", "memo-331.json",
                                       "memo-335.json"])

    def test_index_shape_sorted_with_phase_split_and_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, fixtures.host_scenario(), fixtures.container_scenario())
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(index), {"issues", "sources"})
        self.assertEqual(index["sources"], {"host": True, "container": True})
        self.assertEqual([r["issue"] for r in index["issues"]], [327, 331, 335])
        row = index["issues"][0]
        self.assertEqual(set(row), {"project", "issue", "title", "title_source",
                                    "tokens", "active_ms", "phases", "last_activity"})
        self.assertEqual(row["tokens"], {"total": 157_200, "total_m": 0.2})
        self.assertEqual(set(row["phases"]), {"design", "impl"})
        self.assertEqual(row["phases"]["design"]["tokens"]["total"], 91_700)

    def test_index_marks_failed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, fixtures.host_scenario(), None)
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["sources"], {"host": True, "container": False})

    def test_unmatched_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, fixtures.host_scenario(), fixtures.container_scenario())
            rows = json.loads((Path(tmp) / "unmatched.json").read_text(encoding="utf-8"))
        self.assertEqual([r["session_id"] for r in rows], ["h-loose", "c-play"])

    def test_determinism_two_rebuilds_byte_identical(self):
        host, container = fixtures.host_scenario(), fixtures.container_scenario()
        fetch = lambda repo: {"327": "каскад удаления"}  # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, host, container, fetch)
            first = _data_files(tmp)
            self.assertIn("issues/memo-327.json", first)
            self.assertIn("index.json", first)
            self.assertIn("unmatched.json", first)
            self.assertIn("titles.json", first)
            self._rebuild(tmp, host, container, fetch)
            second = _data_files(tmp)
        self.assertEqual(set(first), set(second))
        for name in first:
            self.assertEqual(first[name], second[name], name)

    def test_stale_issue_file_and_index_entry_removed(self):
        host = fixtures.host_scenario()
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, host, fixtures.container_scenario())
            self.assertTrue((Path(tmp) / "issues" / "memo-335.json").exists())
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            self.assertIn(335, [r["issue"] for r in index["issues"]])
            # issue 335's sessions vanish → snapshot file and index entry go
            self._rebuild(tmp, host, fixtures.container_scenario(childless_roots=0))
            issues_dir = Path(tmp) / "issues"
            self.assertEqual(sorted(p.name for p in issues_dir.iterdir()),
                             ["memo-327.json", "memo-331.json"])
            index2 = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual([r["issue"] for r in index2["issues"]], [327, 331])

    def test_stale_tmp_files_in_issues_dir_swept(self):
        # a SIGKILL between tmp creation and os.replace leaves issues/*.tmp
        # behind; the stale sweep runs after all current writes (whose tmps
        # are renamed or deleted by then), so every *.tmp it sees is stale
        host = fixtures.host_scenario()
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, host, fixtures.container_scenario())
            orphan = Path(tmp) / "issues" / "memo-999.json.tmp"
            orphan.write_text('{"partial": ', encoding="utf-8")
            self._rebuild(tmp, host, fixtures.container_scenario())
            names = sorted(p.name for p in (Path(tmp) / "issues").iterdir())
        self.assertEqual(names, ["memo-327.json", "memo-331.json",
                                 "memo-335.json"])  # orphan .tmp gone, rest intact

    def test_failed_mid_write_leaves_previous_file_intact(self):
        host, container = fixtures.host_scenario(), fixtures.container_scenario()
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, host, container)
            target = Path(tmp) / "issues" / "memo-327.json"
            before = target.read_bytes()
            real_dump = json.dump

            def exploding_dump(obj, fh, **kwargs):
                if isinstance(obj, dict) and "phases" in obj:  # issue snapshots only
                    fh.write('{"partial":')
                    raise RuntimeError("simulated crash mid-write")
                return real_dump(obj, fh, **kwargs)

            with mock.patch.object(collector, "fetch_issue_titles", lambda repo: {}), \
                    mock.patch("json.dump", exploding_dump):
                with self.assertRaises(RuntimeError):
                    collector.rebuild(host, container, CONFIG, tmp)
            self.assertEqual(target.read_bytes(), before)
            leftovers = [p.name for p in (Path(tmp) / "issues").iterdir()
                         if p.name.endswith(".tmp")]
            self.assertEqual(leftovers, [])

    def test_atomic_write_helper_cleans_tmp_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text('{"old": true}', encoding="utf-8")
            with mock.patch("json.dump", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    collector._atomic_write_json(path, {"new": 1})
            self.assertEqual(path.read_text(), '{"old": true}')
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_state_json_created_when_missing_untouched_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rebuild(tmp, fixtures.host_scenario(), None)
            state = Path(tmp) / "state.json"
            self.assertEqual(json.loads(state.read_text(encoding="utf-8")), {})
            state.write_text('{"item_ids": {"memo-327": "PVTI_x"}}', encoding="utf-8")
            before = state.read_bytes()
            self._rebuild(tmp, fixtures.host_scenario(), None)
            self.assertEqual(state.read_bytes(), before)  # write-back caches only


class TitlesTests(unittest.TestCase):
    def test_fetch_issue_titles_argv_and_parse(self):
        result, argv_seen = _with_fake_gh(
            FAKE_GH_OK, lambda: collector.fetch_issue_titles("mkosinov/memo"))
        self.assertEqual(result, {327: "каскад удаления"})
        self.assertEqual(argv_seen, [
            "issue", "list",
            "--repo", "mkosinov/memo",
            "--state", "all",
            "--limit", "1000",
            "--json", "number,title",
        ])

    def test_fetch_issue_titles_failure_warns_and_returns_none(self):
        stderr = io.StringIO()
        def fetch():
            with contextlib.redirect_stderr(stderr):
                return collector.fetch_issue_titles("mkosinov/memo")
        result, _ = _with_fake_gh(FAKE_GH_FAIL, fetch)
        self.assertIsNone(result)
        self.assertIn("warning", stderr.getvalue())

    def test_rebuild_resolves_titles_and_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "fetch_issue_titles",
                                   lambda repo: {"327": "каскад удаления"}):
                collector.rebuild(fixtures.host_scenario(),
                                  fixtures.container_scenario(), CONFIG, tmp)
            snap327 = json.loads((Path(tmp) / "issues" / "memo-327.json")
                                 .read_text(encoding="utf-8"))
            snap331 = json.loads((Path(tmp) / "issues" / "memo-331.json")
                                 .read_text(encoding="utf-8"))
            titles = json.loads((Path(tmp) / "titles.json").read_text(encoding="utf-8"))
        self.assertEqual(snap327["title"], "каскад удаления")
        self.assertEqual(snap327["title_source"], "gh")
        self.assertEqual(snap331["title"], "issue #331")     # gh failure → fallback
        self.assertEqual(snap331["title_source"], "fallback")
        self.assertEqual(titles["mkosinov/memo"], {"327": "каскад удаления"})

    def test_gh_failure_keeps_cached_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "titles.json").write_text(json.dumps(
                {"mkosinov/memo": {"327": "старое название", "400": "closed thing"}}),
                encoding="utf-8")
            stderr = io.StringIO()
            with mock.patch.object(collector, "fetch_issue_titles",
                                   lambda repo: None), \
                    contextlib.redirect_stderr(stderr):
                collector.rebuild(fixtures.host_scenario(), None, CONFIG, tmp)
            snap327 = json.loads((Path(tmp) / "issues" / "memo-327.json")
                                 .read_text(encoding="utf-8"))
            titles = json.loads((Path(tmp) / "titles.json").read_text(encoding="utf-8"))
        self.assertEqual(snap327["title"], "старое название")  # cache survives gh down
        self.assertEqual(snap327["title_source"], "gh")
        self.assertEqual(titles["mkosinov/memo"]["400"], "closed thing")
        self.assertIn("warning", stderr.getvalue())

    def test_closed_issue_keeps_last_known_title(self):
        # fresh fetch no longer returns #400 (closed), the cache keeps it
        sessions = [fixtures.make_host_session("r", "/root/workspace/memo", "#400 old",
                                               created=T0, updated=T0 + MIN)]
        turns = [fixtures.make_turn("r", "r/t1")]
        host = {"sessions": sessions, "turns": turns, "models": []}
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "titles.json").write_text(json.dumps(
                {"mkosinov/memo": {"400": "закрытый тикет"}}), encoding="utf-8")
            with mock.patch.object(collector, "fetch_issue_titles",
                                   lambda repo: {"327": "каскад удаления"}):
                collector.rebuild(host, None, CONFIG, tmp)
            snap = json.loads((Path(tmp) / "issues" / "memo-400.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(snap["title"], "закрытый тикет")
        self.assertEqual(snap["title_source"], "gh")


class GoldenTests(unittest.TestCase):
    """Golden check against the REAL host DB (spec §Testing).

    Fixture of record: superagents #16 (host-only, the panel-security
    design). The golden snapshot lives in data/ (gitignored — personal
    numbers stay out of git); the test skips cleanly when it is absent.

    Regenerate on demand (from token-analytics/, against the live host DB):

      python3 -c "import os, json, collector; cfg = json.load(open('config.json')); host = collector.read_host(os.path.expanduser(cfg['sources']['zcode_host']['db'])); snap = collector.aggregate(host, None, cfg)['issues'][('superagents', 16)]; json.dump(snap, open('data/golden-superagents-16.json', 'w'), sort_keys=True, ensure_ascii=False, indent=2)"
    """

    GOLDEN = Path(collector.__file__).resolve().parent / "data" / "golden-superagents-16.json"

    def test_real_superagents_16_matches_golden(self):
        if not self.GOLDEN.exists():
            self.skipTest("golden file absent — regenerate locally (see docstring)")
        config_path = Path(collector.__file__).resolve().parent / "config.json"
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        host = collector.read_host(os.path.expanduser(cfg["sources"]["zcode_host"]["db"]))
        if host is None:
            self.skipTest("live host DB unavailable")
        aggregated = collector.aggregate(host, None, cfg)
        snapshot = aggregated["issues"].get(("superagents", 16))
        if snapshot is None:
            self.skipTest("issue #16 not present in the live host DB")
        golden = json.loads(self.GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(snapshot, golden)


if __name__ == "__main__":
    unittest.main()
