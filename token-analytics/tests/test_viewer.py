"""Viewer tests: pure helpers in viewer/lib.js + static contracts.

The formatting/navigation helpers are plain JS without DOM access, in a
dedicated `viewer/lib.js` that ends with a CommonJS export guard
(`if (typeof module !== "undefined") module.exports = {...}`) — a no-op
in the browser. That lets these tests execute the REAL helper code under
`node` (stdlib subprocess only) and skip cleanly where node is absent;
the rendering itself is covered by the server E2E suite and the manual
browser checklist in README, not here. Static contract checks (files,
zero external references, verbatim RU label strings, purity) always run.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

VIEWER_DIR = Path(__file__).resolve().parent.parent / "viewer"
LIB_JS = VIEWER_DIR / "lib.js"
INDEX_HTML = VIEWER_DIR / "index.html"
APP_JS = VIEWER_DIR / "app.js"
STYLE_CSS = VIEWER_DIR / "style.css"

NODE = shutil.which("node")

# Verbatim RU label strings from spec §Viewer — part of the contract.
LABEL_UNMATCHED = "Несопоставленные"
LABEL_CALENDAR = "календарно: "
LABEL_APPROX = "≈ сумма по параллельным дочерним сессиям"
LABEL_BIND = "Привязать"


def _js(expr: str):
    """Evaluate a JS expression against lib.js under node → Python value."""
    harness = (
        "const lib = require(" + json.dumps(str(LIB_JS)) + ");\n"
        "console.log(JSON.stringify(" + expr + "));"
    )
    proc = subprocess.run(["node", "-e", harness], capture_output=True,
                          text=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError("node harness failed:\n" + proc.stderr.strip())
    return json.loads(proc.stdout)


def _arg(value) -> str:
    """Python literal → embedded JS literal."""
    return json.dumps(value)


class ViewerStaticContract(unittest.TestCase):
    """Files, zero external references, script wiring, label strings."""

    def test_files_exist(self):
        for path in (INDEX_HTML, APP_JS, STYLE_CSS, LIB_JS):
            self.assertTrue(path.is_file(), "missing " + str(path))

    def test_zero_external_references(self):
        """Spec §Viewer: no build, no external libs — grep-asserted."""
        offenders = []
        for path in sorted(VIEWER_DIR.rglob("*")):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if re.search(r"https?://|cdn", text):
                    offenders.append(path.name)
        self.assertEqual(offenders, [], "external references found")

    def test_index_html_wires_assets(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('href="style.css"', html)
        self.assertIn('src="lib.js"', html)
        self.assertIn('src="app.js"', html)
        self.assertIn('lang="ru"', html)

    def test_app_js_fetches_data_and_posts_bind(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("/data/index.json", js)
        self.assertIn("/data/unmatched.json", js)
        self.assertIn("/data/issues/", js)
        self.assertIn("/api/bind", js)
        self.assertIn(LABEL_BIND, js)

    def test_lib_js_pure_and_exported(self):
        """Helpers must be DOM-free (browser- and node-loadable) and exported."""
        js = LIB_JS.read_text(encoding="utf-8")
        self.assertNotRegex(js, r"\b(document|window)\b")
        self.assertNotIn("fetch(", js)
        self.assertIn("module.exports", js)

    def test_label_strings_verbatim(self):
        """RU label strings from the spec live in the shipped JS."""
        lib = LIB_JS.read_text(encoding="utf-8")
        self.assertIn(LABEL_UNMATCHED, lib)
        self.assertIn(LABEL_CALENDAR, lib)
        self.assertIn(LABEL_APPROX, lib)

    def test_app_js_ids_exist_in_index_html(self):
        """Every element id app.js looks up is present in index.html."""
        js = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        used = set(re.findall(r'byId\("([A-Za-z0-9_-]+)"\)', js))
        self.assertTrue(used)
        missing = sorted(i for i in used
                         if ('id="%s"' % i) not in html)
        self.assertEqual(missing, [])

    def test_app_js_helper_references_exported_by_lib(self):
        """Every L.<name> app.js uses must exist in lib.js exports."""
        js = APP_JS.read_text(encoding="utf-8")
        lib = LIB_JS.read_text(encoding="utf-8")
        used = set(re.findall(r'\bL\.([A-Za-z0-9_]+)', js))
        self.assertTrue(used)
        missing = sorted(name for name in used
                         if (name + ":") not in lib)
        self.assertEqual(missing, [])


@unittest.skipUnless(NODE, "node not available — helper behavior untested here")
class FmtTokensTest(unittest.TestCase):
    CASES = [
        (0, "0"),
        (999, "999"),
        (1000, "1K"),
        (830_000, "830K"),
        (830_400, "830.4K"),
        (1_000_000, "1M"),
        (1_234_567, "1.2M"),
        (12_400_000, "12.4M"),
        (48_240_000, "48.2M"),
    ]

    def test_table(self):
        for value, expected in self.CASES:
            self.assertEqual(_js("lib.fmtTokens(%d)" % value), expected,
                             "fmtTokens(%d)" % value)

    def test_none_and_negative_guard(self):
        self.assertEqual(_js("lib.fmtTokens(null)"), "0")
        self.assertEqual(_js("lib.fmtTokens(undefined)"), "0")


@unittest.skipUnless(NODE, "node not available")
class FmtDurationTest(unittest.TestCase):
    CASES = [
        (0, "0с"),
        (30_000, "30с"),
        (2_700_000, "45м"),
        (3_723_000, "1ч 02м"),
        (5_040_000, "1ч 24м"),       # the spec's example
        (7_200_000, "2ч"),
        (91_080_000, "25ч 18м"),
    ]

    def test_table(self):
        for value, expected in self.CASES:
            self.assertEqual(_js("lib.fmtDuration(%d)" % value), expected,
                             "fmtDuration(%d)" % value)

    def test_none_guard(self):
        self.assertEqual(_js("lib.fmtDuration(null)"), "0с")


@unittest.skipUnless(NODE, "node not available")
class FmtDateAndIntTest(unittest.TestCase):
    def test_fmt_date_local_order(self):
        self.assertEqual(_js("lib.fmtDate(%s)" % _arg("2026-09-26")),
                         "26.09.2026")

    def test_fmt_date_none(self):
        self.assertEqual(_js("lib.fmtDate(null)"), "—")
        self.assertEqual(_js("lib.fmtDate('')"), "—")

    def test_fmt_date_invalid_falls_back(self):
        self.assertEqual(_js("lib.fmtDate('garbage')"), "—")

    def test_fmt_int_grouped(self):
        for value, expected in [(0, "0"), (1010, "1 010"),
                                (6_700, "6 700"),
                                (48_240_000, "48 240 000")]:
            self.assertEqual(_js("lib.fmtInt(%d)" % value), expected)


@unittest.skipUnless(NODE, "node not available")
class CalendarLineTest(unittest.TestCase):
    CASES = [
        ({"ms": 259_200_000, "days": 3, "hours": None}, "календарно: 3 дня"),
        ({"ms": 86_400_000, "days": 1, "hours": None}, "календарно: 1 день"),
        ({"ms": 172_800_000, "days": 2, "hours": None}, "календарно: 2 дня"),
        ({"ms": 432_000_000, "days": 5, "hours": None}, "календарно: 5 дней"),
        ({"ms": 1_814_400_000, "days": 21, "hours": None},
         "календарно: 21 день"),
        ({"ms": 950_400_000, "days": 11, "hours": None},
         "календарно: 11 дней"),
        ({"ms": 32_400_000, "days": None, "hours": 9}, "календарно: 9 ч"),
        ({"ms": 5_400_000, "days": None, "hours": 1.5},
         "календарно: 1.5 ч"),
    ]

    def test_table(self):
        for cal, expected in self.CASES:
            self.assertEqual(
                _js("lib.calendarLine(%s)" % json.dumps(cal, ensure_ascii=False)),
                expected, "calendarLine(%r)" % (cal,))


@unittest.skipUnless(NODE, "node not available")
class SortAndTabsTest(unittest.TestCase):
    ROWS = [
        {"project": "memo", "issue": 335, "tokens": {"total": 100}},
        {"project": "superagents", "issue": 26, "tokens": {"total": 900}},
        {"project": "memo", "issue": 327, "tokens": {"total": 900}},
        {"project": "superagents", "issue": 16, "tokens": {"total": 500}},
    ]

    def test_sort_by_tokens_desc_then_project_issue_asc(self):
        got = _js("lib.sortIssues(%s)" % json.dumps(self.ROWS))
        self.assertEqual([(r["project"], r["issue"]) for r in got],
                         [("memo", 327), ("superagents", 26),
                          ("superagents", 16), ("memo", 335)])

    def test_project_tabs_spend_order_then_unmatched_last(self):
        got = _js("lib.projectTabs(%s)" % json.dumps(self.ROWS))
        self.assertEqual([t["id"] for t in got],
                         ["memo", "superagents", "__unmatched__"])
        self.assertEqual(got[-1]["label"], LABEL_UNMATCHED)
        self.assertTrue(got[-1]["unmatched"])

    def test_project_tabs_empty_index(self):
        got = _js("lib.projectTabs([])")
        self.assertEqual([t["id"] for t in got], ["__unmatched__"])

    def test_project_tabs_configured_empty_project_kept(self):
        """index.projects: a zero-issue project still gets a tab (empty state)."""
        got = _js("lib.projectTabs(%s, %s)"
                  % (json.dumps(self.ROWS), _arg(["superagents", "zzz"])))
        self.assertEqual([t["id"] for t in got],
                         ["memo", "superagents", "zzz", "__unmatched__"])

    def test_issue_data_url(self):
        self.assertEqual(_js("lib.issueDataUrl(%s, %s)" % (_arg("memo"), _arg(327))),
                         "/data/issues/memo-327.json")


@unittest.skipUnless(NODE, "node not available")
class TreeDrilldownTest(unittest.TestCase):
    """flatten/expand logic for the recursive drill-down (any depth)."""

    TREE = [{
        "session_id": "a1", "title": "root A", "agent": None,
        "tokens": {"total": 100}, "active_ms": 1000,
        "children": [
            {"session_id": "b1", "title": "child B", "agent": None,
             "tokens": {"total": 60}, "active_ms": 600,
             "children": [
                 {"session_id": "g1", "title": "grand G", "agent": None,
                  "tokens": {"total": 20}, "active_ms": 200, "children": []},
             ]},
            {"session_id": "c1", "title": "child C", "agent": None,
             "tokens": {"total": 40}, "active_ms": 400, "children": []},
        ],
    }]

    def _visible(self, expanded):
        return _js("lib.visibleNodes(%s, %s)"
                   % (json.dumps(self.TREE), json.dumps(expanded)))

    def test_collapsed_shows_roots_only(self):
        rows = self._visible([])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["node"]["session_id"], "a1")
        self.assertEqual(rows[0]["depth"], 0)
        self.assertTrue(rows[0]["expandable"])
        self.assertEqual(rows[0]["key"], "0")

    def test_expand_one_level(self):
        rows = self._visible(["0"])
        self.assertEqual([r["node"]["session_id"] for r in rows],
                         ["a1", "b1", "c1"])
        self.assertEqual([r["depth"] for r in rows], [0, 1, 1])
        self.assertEqual(rows[1]["key"], "0/0")
        self.assertFalse(rows[2]["expandable"])

    def test_grandchild_needs_both_levels(self):
        self.assertEqual(len(self._visible(["0/0"])), 1)
        rows = self._visible(["0", "0/0"])
        ids = [r["node"]["session_id"] for r in rows]
        self.assertEqual(ids, ["a1", "b1", "g1", "c1"])
        self.assertEqual(rows[2]["depth"], 2)

    def test_toggle_key(self):
        self.assertEqual(_js("lib.toggleKey([], '0')"), ["0"])
        self.assertEqual(_js("lib.toggleKey(['0'], '0')"), [])
        self.assertEqual(_js("lib.toggleKey(['0'], '0/1')"), ["0", "0/1"])


@unittest.skipUnless(NODE, "node not available")
class BarsTest(unittest.TestCase):
    def test_widths_normalized_to_max(self):
        rows = [{"model": "glm", "tokens": 100},
                {"model": "mini", "tokens": 50},
                {"model": "none", "tokens": 0}]
        got = _js("lib.barsWidths(%s, 'model')" % json.dumps(rows))
        self.assertEqual([r["pct"] for r in got], [100, 50, 0])
        self.assertEqual([r["label"] for r in got], ["glm", "mini", "none"])

    def test_all_zero_guard(self):
        rows = [{"agent": "x", "tokens": 0}, {"agent": "y", "tokens": 0}]
        got = _js("lib.barsWidths(%s, 'agent')" % json.dumps(rows))
        self.assertEqual([r["pct"] for r in got], [0, 0])

    def test_empty(self):
        self.assertEqual(_js("lib.barsWidths([], 'model')"), [])

    def test_missing_name_renders_dash(self):
        got = _js("lib.barsWidths([{model: null, tokens: 5}], 'model')")
        self.assertEqual(got[0]["label"], "—")


@unittest.skipUnless(NODE, "node not available")
class ScrollHintTest(unittest.TestCase):
    """Table scroll affordance: the fade hint appears only when the
    .table-wrap actually scrolls (wide table inside a narrow viewport)."""

    def test_wider_content_needs_hint(self):
        self.assertTrue(_js("lib.needsScrollHint(864, 340)"))

    def test_fitting_content_has_no_hint(self):
        self.assertFalse(_js("lib.needsScrollHint(340, 340)"))
        self.assertFalse(_js("lib.needsScrollHint(300, 340)"))

    def test_subpixel_tolerance(self):
        self.assertFalse(_js("lib.needsScrollHint(341, 340)"))
        self.assertTrue(_js("lib.needsScrollHint(342.5, 340)"))

    def test_guards(self):
        self.assertFalse(_js("lib.needsScrollHint(null, 340)"))
        self.assertFalse(_js("lib.needsScrollHint(864, null)"))


@unittest.skipUnless(NODE, "node not available")
class DialogHelpersTest(unittest.TestCase):
    def test_parse_issue_number(self):
        cases = [("16", 16), (" 327 ", 327), ("0", None), ("-5", None),
                 ("abc", None), ("", None), ("1.5", None), (None, None)]
        for value, expected in cases:
            self.assertEqual(
                _js("lib.parseIssueNumber(%s)" % _arg(value)), expected,
                "parseIssueNumber(%r)" % (value,))

    def test_prefill_project_attributable_wins(self):
        got = _js("lib.prefillProject(%s, %s)"
                  % (_arg("memo"), _arg(["memo", "superagents"])))
        self.assertEqual(got, "memo")

    def test_prefill_project_unattributable_falls_back(self):
        got = _js("lib.prefillProject(%s, %s)"
                  % (_arg("—"), _arg(["memo", "superagents"])))
        self.assertEqual(got, "memo")
        self.assertEqual(_js("lib.prefillProject('x', [])"), "")

    def test_node_title_fallback(self):
        self.assertEqual(_js("lib.nodeTitle({title: 'T1: a'})"), "T1: a")
        self.assertEqual(_js("lib.nodeTitle({title: null})"),
                         "(без названия)")
        self.assertEqual(_js("lib.nodeTitle({})"), "(без названия)")

    def test_phase_rows_absent_hidden_not_zero_filled(self):
        both = _js("lib.phaseRows({design: {tokens: {}}, impl: {tokens: {}}})")
        self.assertEqual([p["key"] for p in both], ["design", "impl"])
        impl_only = _js("lib.phaseRows({impl: {tokens: {}}})")
        self.assertEqual([p["key"] for p in impl_only], ["impl"])

    def test_constants(self):
        self.assertEqual(_js("lib.UNMATCHED_TAB"), "__unmatched__")
        self.assertEqual(_js("lib.APPROX_LABEL"), LABEL_APPROX)


if __name__ == "__main__":
    unittest.main()
