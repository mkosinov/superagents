"""Unit tests for token-analytics mapping + phase attribution (#26 Task 3).

DoD coverage (spec §Session → issue mapping, §Phase attribution):
- extract_issue: each ordered pattern hits its class of titles; leftmost
  wins within a pattern; earlier pattern wins across patterns; no match →
  None (session flows into unmatched);
- attribute_project: ordered directory-prefix match, None for unknown
  directories (rendered «—» in unmatched rows);
- root detection: parent_id IS NULL per source; children fold into their
  root's group; dangling parents become their own roots;
- phase_for_root: `split` mode (host→design, container→impl, title ignored)
  vs `title` mode (root title starts with IMPL case-insensitively); a phase
  override forces either in both modes;
- overrides load/save: injectable data dir, atomic save, fail-open load;
- override with explicit project binds a session from an unattributed
  directory (removes it from unmatched);
- build_unmatched: roots matching no issue from ANY directory, project
  derived else «—», exact row shape, subtree token totals, sorted desc.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make collector importable

import collector  # noqa: E402
try:
    from . import fixtures  # discovered as a package (tests/__init__.py present)
except ImportError:  # discovered bare from inside tests/
    import fixtures  # noqa: E402

# Mirrors the committed config.json shape (spec §Config file): memo split,
# superagents title — the fixture scenarios use memo's directories.
CONFIG = {
    "projects": {
        "superagents": {
            "phase_mode": "title",
            "directories": ["/Users/mkosinov/dev/opencode/workspace/superagents",
                            "/Users/mkosinov/dev/superagents"],
        },
        "memo": {
            "phase_mode": "split",
            "directories": ["/root/workspace/memo", "/Users/mkosinov/dev/memo"],
        },
    },
}

T0 = fixtures.BASE_TIME_MS


def _host_payload(sessions, turns):
    return {"sessions": sessions, "turns": turns, "models": []}


class ExtractIssueTests(unittest.TestCase):
    def test_each_pattern_hits_its_class_of_titles(self):
        # pattern 1: #(\d{1,4}) anywhere
        self.assertEqual(collector.extract_issue("Разведка issue #327"), 327)
        self.assertEqual(collector.extract_issue("IMPL #324 delete family"), 324)
        # pattern 2: ^(\d{1,4})\b leading bare number (memo habit)
        self.assertEqual(collector.extract_issue("327 каскад удаления"), 327)
        # pattern 3: Russian/latin keyword forms
        self.assertEqual(collector.extract_issue("дизайн 26 тикета"), 26)
        self.assertEqual(collector.extract_issue("тикет 41 упал"), 41)
        self.assertEqual(collector.extract_issue("задача 7 срочная"), 7)
        self.assertEqual(collector.extract_issue("задачи 15 и ещё"), 15)
        self.assertEqual(collector.extract_issue("issue 99 plain"), 99)

    def test_leftmost_wins_within_a_pattern(self):
        self.assertEqual(collector.extract_issue("fix #10 then #20 later"), 10)
        self.assertEqual(collector.extract_issue("дизайн 26 и тикет 41"), 26)

    def test_earlier_pattern_wins_across_patterns(self):
        # «#400» is farther left? no — «327» is leftmost, but pattern 1 is
        # stronger and is tried over the whole title first (ordered set,
        # first match wins — spec §Mapping step 3).
        self.assertEqual(collector.extract_issue("327 marathon but #400 wins"), 400)

    def test_no_match_returns_none(self):
        for title in ("random experiment", "песочница эксперимент",
                      "solo quick check", "T1: scaffold", "Fix crash", "",
                      "Задача про память без номера",
                      "compare 40 vs 30 rows"):  # mid-title bare numbers need # or keyword
            self.assertIsNone(collector.extract_issue(title), repr(title))


class AttributeProjectTests(unittest.TestCase):
    def test_ordered_prefix_match(self):
        self.assertEqual(collector.attribute_project("/root/workspace/memo", CONFIG), "memo")
        self.assertEqual(collector.attribute_project("/root/workspace/memo/sub/dir", CONFIG), "memo")
        self.assertEqual(collector.attribute_project("/Users/mkosinov/dev/memo", CONFIG), "memo")
        self.assertEqual(collector.attribute_project(
            "/Users/mkosinov/dev/opencode/workspace/superagents", CONFIG), "superagents")
        self.assertEqual(collector.attribute_project("/Users/mkosinov/dev/superagents", CONFIG),
                         "superagents")

    def test_unknown_directory_is_none(self):
        self.assertIsNone(collector.attribute_project("/tmp/scratch", CONFIG))
        self.assertIsNone(collector.attribute_project("/opt/playground", CONFIG))

    def test_prefix_respects_path_boundary(self):
        # a longer directory sharing the prefix text is NOT a match
        self.assertIsNone(collector.attribute_project("/root/workspace/memo-other", CONFIG))
        self.assertIsNone(collector.attribute_project("/root/workspace/memoranda/x", CONFIG))

    def test_config_order_breaks_prefix_overlap(self):
        overlap = {
            "projects": {
                "broad": {"directories": ["/root/work"]},
                "narrow": {"directories": ["/root/work/special"]},
            }
        }
        self.assertEqual(collector.attribute_project("/root/work/special/x", overlap), "broad")

    def test_empty_prefix_is_skipped_not_wildcard(self):
        # a prefix that rstrip("/") reduces to "" would match EVERYTHING —
        # it must be skipped instead
        wildcard = {"projects": {"wild": {"directories": ["/"]},
                                 "emptier": {"directories": [""]}}}
        self.assertIsNone(collector.attribute_project("/root/workspace/memo", wildcard))
        self.assertIsNone(collector.attribute_project("/opt/playground", wildcard))
        self.assertIsNone(collector.attribute_project("/", wildcard))
        self.assertIsNone(collector.attribute_project("relative/path", wildcard))


class RootDetectionTests(unittest.TestCase):
    def test_is_root_is_parent_null(self):
        rows = fixtures.host_scenario()
        by_id = {s["id"]: s for s in rows["sessions"]}
        self.assertTrue(collector.is_root(by_id["h-design"]))
        self.assertTrue(collector.is_root(by_id["h-solo-1"]))
        self.assertFalse(collector.is_root(by_id["h-design-p1"]))
        self.assertFalse(collector.is_root(by_id["h-design-p2-g1"]))

    def test_group_by_root_folds_descendants_any_depth(self):
        rows = fixtures.host_scenario()
        groups = collector.group_by_root(rows["sessions"])
        self.assertEqual(set(groups), {"h-design", "h-marathon", "h-solo-1", "h-loose"})
        self.assertEqual(set(s["id"] for s in groups["h-design"]),
                         {"h-design", "h-design-p1", "h-design-p2", "h-design-p2-g1"})
        self.assertEqual(set(s["id"] for s in groups["h-marathon"]),
                         {"h-marathon", "h-marathon-c1", "h-marathon-c1-g1",
                          "h-marathon-c2", "h-marathon-c3"})
        self.assertEqual([s["id"] for s in groups["h-solo-1"]], ["h-solo-1"])
        self.assertEqual([s["id"] for s in groups["h-loose"]], ["h-loose"])

    def test_dangling_parent_becomes_its_own_root(self):
        sessions = [
            fixtures.make_host_session("ghost-child", "/root/workspace/memo", "orphan",
                                       parent_id="no-such-parent", created=T0, updated=T0),
        ]
        groups = collector.group_by_root(sessions)
        self.assertEqual(set(groups), {"ghost-child"})

    def test_parent_cycle_terminates_each_becomes_own_root(self):
        # A↔B parent cycle must not hang the walk; each member becomes its
        # own root (deepest real ancestor of a looped chain is undefined, so
        # no folding happens)
        sessions = [
            fixtures.make_host_session("a", "/tmp/scratch", "cycle member a",
                                       parent_id="b", created=T0, updated=T0),
            fixtures.make_host_session("b", "/tmp/scratch", "cycle member b",
                                       parent_id="a", created=T0, updated=T0),
        ]
        groups = collector.group_by_root(sessions)
        self.assertEqual(set(groups), {"a", "b"})
        self.assertEqual([s["id"] for s in groups["a"]], ["a"])
        self.assertEqual([s["id"] for s in groups["b"]], ["b"])


class PhaseTests(unittest.TestCase):
    def test_split_mode_source_decides_title_ignored(self):
        host_impl = {"id": "x", "title": "IMPL #324 delete family", "parent_id": None}
        host_design = {"id": "x", "title": "Разведка issue #327", "parent_id": None}
        ctr_impl = {"id": "x", "title": "#327 IMPL marathon", "parent_id": None}
        ctr_design = {"id": "x", "title": "Разведка issue #327", "parent_id": None}
        self.assertEqual(collector.phase_for_root(host_design, "split", "host"), "design")
        self.assertEqual(collector.phase_for_root(host_impl, "split", "host"), "design")
        self.assertEqual(collector.phase_for_root(ctr_design, "split", "container"), "impl")
        self.assertEqual(collector.phase_for_root(ctr_impl, "split", "container"), "impl")

    def test_title_mode_impl_prefix_case_insensitive(self):
        impl_root = {"id": "x", "title": "IMPL #324 delete family", "parent_id": None}
        lower_root = {"id": "x", "title": "impl: lowercase variant", "parent_id": None}
        design_root = {"id": "x", "title": "Разведка issue #327", "parent_id": None}
        self.assertEqual(collector.phase_for_root(impl_root, "title", "host"), "impl")
        self.assertEqual(collector.phase_for_root(lower_root, "title", "host"), "impl")
        self.assertEqual(collector.phase_for_root(design_root, "title", "host"), "design")
        # source is irrelevant in title mode
        self.assertEqual(collector.phase_for_root(design_root, "title", "container"), "design")
        self.assertEqual(collector.phase_for_root(impl_root, "title", "container"), "impl")

    def test_phase_override_forces_either_in_both_modes(self):
        host_design_root = {"id": "x", "title": "Разведка issue #327", "parent_id": None}
        impl_root = {"id": "x", "title": "IMPL #324 delete family", "parent_id": None}
        # split mode: heuristics say host→design / container→impl, override flips both
        self.assertEqual(
            collector.phase_for_root(host_design_root, "split", "host", override="impl"), "impl")
        self.assertEqual(
            collector.phase_for_root(impl_root, "split", "container", override="design"), "design")
        # title mode: heuristic title says design/impl, override flips both
        self.assertEqual(
            collector.phase_for_root(host_design_root, "title", "host", override="impl"), "impl")
        self.assertEqual(
            collector.phase_for_root(impl_root, "title", "host", override="design"), "design")

    def test_unknown_mode_is_loud(self):
        root = {"id": "x", "title": "whatever", "parent_id": None}
        with self.assertRaises(ValueError):
            collector.phase_for_root(root, "sideways", "host")


class OverrideIOTests(unittest.TestCase):
    def test_save_then_load_roundtrip(self):
        overrides = {
            "h-loose": {"project": "memo", "issue": 327, "phase": "design"},
            "c-play": {"project": "superagents", "issue": 16, "phase": "impl"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            collector.save_overrides(tmp, overrides)
            path = Path(tmp) / "overrides.json"
            self.assertTrue(path.exists())
            self.assertEqual(collector.load_overrides(tmp), overrides)

    def test_load_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collector.load_overrides(tmp), {})

    def test_load_corrupt_file_warns_and_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text("{not json at all", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                loaded = collector.load_overrides(tmp)
        self.assertEqual(loaded, {})
        self.assertIn("warning", stderr.getvalue())

    def test_load_string_issue_normalized_to_int(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text(json.dumps(
                {"s1": {"project": "memo", "issue": "327", "phase": "impl"}}),
                encoding="utf-8")
            loaded = collector.load_overrides(tmp)
        self.assertEqual(loaded["s1"]["issue"], 327)
        self.assertIsInstance(loaded["s1"]["issue"], int)

    def test_save_overwrites_atomically_no_tmp_leftovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "data"
            collector.save_overrides(nested, {"s1": {"project": "memo", "issue": 1,
                                                     "phase": "design"}})
            collector.save_overrides(nested, {"s2": {"project": "memo", "issue": 2,
                                                     "phase": "impl"}})
            leftovers = [p.name for p in nested.iterdir() if p.name != "overrides.json"]
            self.assertEqual(leftovers, [])
            self.assertEqual(collector.load_overrides(nested)["s2"]["issue"], 2)
            self.assertNotIn("s1", collector.load_overrides(nested))


class OverrideCoercionTests(unittest.TestCase):
    """A malformed override issue must coerce to None — never bind silently."""

    def _load_entry(self, issue):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text(json.dumps(
                {"s1": {"project": "memo", "issue": issue, "phase": "design"}}),
                encoding="utf-8")
            return collector.load_overrides(tmp)["s1"]

    def test_malformed_issue_values_coerce_to_none(self):
        # hand-edit typos: junk strings, bools (bool IS int in Python),
        # floats (32.5 must not bind 32), non-positives, containers, None
        for bad in ("№327", "327abc", "issue 327", True, False, 32.5, -5, 0,
                    [327], {"n": 327}, None):
            self.assertIsNone(self._load_entry(bad)["issue"], repr(bad))

    def test_coercible_string_issue_normalized_to_positive_int(self):
        self.assertEqual(self._load_entry("327")["issue"], 327)
        self.assertEqual(self._load_entry("327 ")["issue"], 327)  # stray space tolerated
        entry = self._load_entry("327 ")
        self.assertIsInstance(entry["issue"], int)

    def test_malformed_override_keeps_root_in_unmatched(self):
        # even when overrides reach build_unmatched un-normalized (raw
        # dicts), a junk issue must NOT count as a binding: the root stays
        # visible in the unmatched table instead of vanishing silently
        host = fixtures.host_scenario()
        container = fixtures.container_scenario()
        for bad in ("№327", True, 32.5):
            overrides = {"h-loose": {"project": "memo", "issue": bad, "phase": "design"}}
            rows = collector.build_unmatched(host, container, CONFIG, overrides)
            self.assertEqual([r["session_id"] for r in rows], ["h-loose", "c-play"],
                             repr(bad))


class OverrideBindsUnattributedTests(unittest.TestCase):
    def test_override_with_project_binds_unattributed_directory_session(self):
        host = fixtures.host_scenario()
        container = fixtures.container_scenario()
        overrides = {"h-loose": {"project": "memo", "issue": 327, "phase": "design"}}
        rows = collector.build_unmatched(host, container, CONFIG, overrides)
        self.assertEqual([r["session_id"] for r in rows], ["c-play"])  # h-loose is bound now

    def test_override_on_container_side_binds_too(self):
        host = fixtures.host_scenario()
        container = fixtures.container_scenario()
        overrides = {"c-play": {"project": "memo", "issue": 335, "phase": "impl"}}
        rows = collector.build_unmatched(host, container, CONFIG, overrides)
        self.assertEqual([r["session_id"] for r in rows], ["h-loose"])


class BuildUnmatchedTests(unittest.TestCase):
    def test_fixture_scenarios_only_loose_roots_unmatched(self):
        host = fixtures.host_scenario()
        container = fixtures.container_scenario()
        rows = collector.build_unmatched(host, container, CONFIG)
        self.assertEqual([r["session_id"] for r in rows], ["h-loose", "c-play"])  # token tie, host first
        for row in rows:
            self.assertEqual(set(row), {"project", "date", "directory", "title",
                                        "tokens", "session_id"})
            self.assertEqual(row["project"], "—")  # unknown directories
        loose, play = rows
        self.assertEqual((loose["directory"], loose["title"]), ("/tmp/scratch", "random experiment"))
        self.assertEqual((play["directory"], play["title"]), ("/opt/playground", "песочница эксперимент"))
        # BASE + 9h = 2023-11-15 UTC; single-session subtree totals = DEFAULT_TOKENS sum
        self.assertEqual(loose["date"], "2023-11-15")
        self.assertEqual(play["date"], "2023-11-15")
        self.assertEqual(loose["tokens"], 6550)
        self.assertEqual(play["tokens"], 6550)

    def test_sorted_by_tokens_desc_and_subtree_totals(self):
        sessions = [
            fixtures.make_host_session("big", "/tmp/scratch", "random experiment",
                                       created=T0, updated=T0 + 60_000),
            fixtures.make_host_session("mid", "/root/workspace/memo", "misc chatter",
                                       created=T0, updated=T0 + 60_000),
            fixtures.make_host_session("small", "/tmp/scratch", "another loose",
                                       created=T0, updated=T0 + 60_000),
            fixtures.make_host_session("small-c", "/tmp/scratch", "child of loose",
                                       parent_id="small", created=T0, updated=T0 + 60_000),
        ]
        turns = [
            fixtures.make_turn("big", "big/t1", tokens=(1000, 0, 0, 0, 0)),
            fixtures.make_turn("mid", "mid/t1", tokens=(700, 0, 0, 0, 0)),
            fixtures.make_turn("small", "small/t1", tokens=(300, 0, 0, 0, 0)),
            fixtures.make_turn("small-c", "small-c/t1", tokens=(200, 0, 0, 0, 0)),
        ]
        rows = collector.build_unmatched(_host_payload(sessions, turns), None, CONFIG)
        self.assertEqual([r["session_id"] for r in rows], ["big", "mid", "small"])
        self.assertEqual([r["tokens"] for r in rows], [1000, 700, 500])  # small = subtree 300+200
        self.assertEqual([r["project"] for r in rows], ["—", "memo", "—"])
        tokens = [r["tokens"] for r in rows]
        self.assertEqual(tokens, sorted(tokens, reverse=True))

    def test_titled_roots_from_any_directory_never_unmatched(self):
        sessions = [
            fixtures.make_host_session("known", "/root/workspace/memo", "Разведка issue #327",
                                       created=T0, updated=T0 + 60_000),
            fixtures.make_host_session("known2", "/tmp/scratch", "327 каскад удаления",
                                       created=T0, updated=T0 + 60_000),
            fixtures.make_host_session("loose", "/tmp/scratch", "no number here",
                                       created=T0, updated=T0 + 60_000),
        ]
        turns = [fixtures.make_turn(s["id"], s["id"] + "/t1") for s in sessions]
        rows = collector.build_unmatched(_host_payload(sessions, turns), None, CONFIG)
        self.assertEqual([r["session_id"] for r in rows], ["loose"])
        self.assertEqual(rows[0]["project"], "—")


if __name__ == "__main__":
    unittest.main()
