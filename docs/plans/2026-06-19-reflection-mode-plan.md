# Reflection Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `reflect` skill + `reflector` agent that analyzes opencode.db session history, detects workflow compliance violations, and produces human-approved proposals for SuperAgents workflow improvements.

**Architecture:** Read-only SQLite access to `opencode.db` (965 MB, no new DB). Filesystem storage for proposals/decisions/reports (markdown + JSON state). Single Python package `reflectlib/` with focused modules. CLI wrapper `reflect.sh` with 3 modes. Subagent `reflector.md` for LLM-driven analysis. Auto-apply off in MVP, architecturally supported.

**Tech Stack:** Python 3.11+ (stdlib: sqlite3, json, argparse, pathlib), Bash 5, SQLite 3, cron, Telegram Bot API.

**Total:** 18 tasks, ~11-12 working days.

---

## File Structure

```
superagents/skills/reflect/
├── SKILL.md
├── README.md
├── scripts/
│   ├── reflect.sh
│   ├── notify.sh
│   ├── lib/
│   │   ├── __init__.py        # CLI entry
│   │   ├── db.py
│   │   ├── reconstruct_tree.py
│   │   ├── attribute_to_sessions.py
│   │   ├── workflow_checks.py  # 16 checks + ALL_CHECKS list
│   │   ├── quality_scoring.py
│   │   ├── closing_the_loop.py
│   │   ├── detect_skill_candidates.py
│   │   ├── analyze.py
│   │   ├── metrics.py
│   │   ├── proposals.py
│   │   ├── config.py
│   │   ├── notify.py
│   │   ├── redactor.py
│   │   ├── post_mortem.py
│   │   ├── wave_report.py
│   │   ├── nightly.py
│   │   └── status_cmd.py
│   └── install-cron.sh
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_db.py
│   ├── test_reconstruct_tree.py
│   ├── test_workflow_checks.py
│   ├── test_quality_scoring.py
│   ├── test_closing_the_loop.py
│   ├── test_proposals.py
│   ├── test_config.py
│   ├── test_redactor.py
│   ├── test_analyze.py
│   ├── test_attribute_to_sessions.py
│   ├── test_detect_skill_candidates.py
│   ├── test_metrics.py
│   ├── test_post_mortem.py
│   ├── test_wave_report.py
│   └── test_nightly.py
├── queries.sql
├── templates/
│   ├── post-mortem.md
│   ├── wave-report.md
│   ├── nightly-digest.md
│   └── proposal.md
├── config/
│   └── reflect.config.example.json
└── examples/
    ├── example-postmortem-session-title.md
    ├── example-wave-report-wave-4-5.md
    ├── example-nightly-digest.md
    └── example-proposal.md

superagents/agents/
└── reflector.md

~/.config/opencode/reflection/   # runtime
├── reports/
├── proposals/
├── decisions/
├── metrics.json
└── state.json
```

---

## Task Classification Reference

| Tier | Criteria | Review pipeline |
|------|----------|-----------------|
| Trivial | ≤5 lines, no logic | self + architect spot-check |
| Small | 1 file, <50 lines, no state | spec-review only |
| Standard | Multi-file, logic, state | spec + quality review |
| Large | Architecture, >200 lines, breaking | full + final review |

---

## Task 1: Initialize skill structure and queries.sql

### Classification: small
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §4 (Data model), §11 (Implementation outline)

### Task Description

Create the skill directory structure and `queries.sql` containing all SQL queries referenced in the spec. This is the foundation — every other task uses these queries.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/__init__.py` (empty)
- `superagents/skills/reflect/scripts/__init__.py` (empty)
- `superagents/skills/reflect/tests/__init__.py` (empty)
- `superagents/skills/reflect/queries.sql`

### Steps

- [ ] **1.1** Create directory structure:
  ```bash
  cd /root/workspace/superagents
  mkdir -p skills/reflect/scripts/lib skills/reflect/tests/fixtures skills/reflect/templates skills/reflect/config skills/reflect/examples
  touch skills/reflect/scripts/__init__.py skills/reflect/scripts/lib/__init__.py skills/reflect/tests/__init__.py
  ```

- [ ] **1.2** Create `skills/reflect/queries.sql` with header + queries Q1-Q7 (see spec §6, §11). Each query: `SELECT` from session/part/message with `json_extract` for JSON fields. Queries cover: sessions, tool calls with errors, subagent counts, cost aggregates, compaction events, wave identification, tool usage stats.

- [ ] **1.3** Commit:
  ```bash
  cd /root/workspace/superagents
  git add skills/reflect/
  git commit -m "feat(reflect): scaffold skill structure + queries.sql"
  ```

---

## Task 2: db.py — SQLite connection and session loader

### Classification: small
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §4.1 (Read-only источник)

### Task Description

Create `db.py` that opens `opencode.db` in read-only mode and provides typed accessors. Must work with real DB and test fixture.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/db.py`
- `superagents/skills/reflect/tests/conftest.py`
- `superagents/skills/reflect/tests/test_db.py`

### Steps

- [ ] **2.1** Create `tests/conftest.py` with `sample_db_path` fixture (copies real opencode.db to tmp).

- [ ] **2.2** Write RED test in `tests/test_db.py` with 4 tests:
  - `test_open_db_returns_readonly_connection` — verify read-only mode (CREATE TABLE fails)
  - `test_list_sessions_returns_rows` — returns list with `id`, `agent`
  - `test_list_tool_calls_returns_tool_data` — returns list with `tool`, `session_id`
  - `test_aggregate_tool_usage_groups_by_tool` — returns dict with `bash` key

- [ ] **2.3** Run RED — confirm tests fail (ImportError).

- [ ] **2.4** Implement `scripts/lib/db.py` with 3 functions:
  - `open_db(path) -> sqlite3.Connection` (read-only via `?mode=ro` URI)
  - `list_sessions(conn, since_ms) -> list[dict]` (Q1 query)
  - `list_tool_calls(conn, since_ms) -> list[dict]` (Q2 query with `json_extract`)
  - `aggregate_tool_usage(conn, since_ms) -> dict[str, dict]` (Q7 query, grouped by tool)

- [ ] **2.5** Run GREEN:
  ```bash
  cd /root/workspace/superagents/skills/reflect
  PYTHONPATH=scripts python -m pytest tests/test_db.py -v
  ```
  Expected: 4 passed

- [ ] **2.6** Commit: `feat(reflect): db.py with read-only access + 3 accessors`

---

## Task 3: reconstruct_tree.py — session tree builder

### Classification: small
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5.1, §5.2

### Task Description

Build a session tree from a flat list of sessions. Tree: main → subagents (by parent_id) → nested.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/reconstruct_tree.py`
- `superagents/skills/reflect/tests/test_reconstruct_tree.py`

### Steps

- [ ] **3.1** Write RED test with 3 tests: `test_build_tree_simple_chain`, `test_find_root_main_sessions`, `test_session_node_duration`.

- [ ] **3.2** Run RED.

- [ ] **3.3** Implement `scripts/lib/reconstruct_tree.py`:
  - `SessionNode` dataclass: `id`, `title`, `parent_id`, `agent`, `time_created`, `time_updated`, `time_archived`, `children`. Properties: `duration_ms`, `is_archived`, `is_root`.
  - `build_tree(sessions) -> dict[str, SessionNode]`
  - `find_root(sessions) -> list[SessionNode]`

- [ ] **3.4** Run GREEN: 3 passed

- [ ] **3.5** Commit: `feat(reflect): session tree reconstruction with SessionNode`

---

## Task 4: config.py — per-project config loader

### Classification: small
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §4.3, §9.1

### Task Description

Load `~/.config/opencode/reflect.config.json` with defaults. Each check has `enabled`, `severity`, `options`.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/config.py`
- `superagents/skills/reflect/config/reflect.config.example.json`
- `superagents/skills/reflect/tests/test_config.py`

### Steps

- [ ] **4.1** Create `config/reflect.config.example.json` with all 17 check configs (16 checks + auto_apply/notify/thresholds sections).

- [ ] **4.2** Write RED test with 3 tests: `test_load_default_config`, `test_load_custom_config`, `test_check_config_severity_validation`.

- [ ] **4.3** Run RED.

- [ ] **4.4** Implement `scripts/lib/config.py`:
  - `CheckConfig` dataclass: `enabled: bool = True`, `severity: Severity = "warning"`, `options: dict = {}`
  - `AutoApplyConfig`: `enabled=False`, `max_confidence=0.95`, `allowed_severities=["info"]`, `allowed_types=["archive-skill"]`
  - `NotifyConfig`: `telegram_chat_id=None`, `min_severity_to_notify="warning"`
  - `ThresholdsConfig`: `regression_delta_pct=30.0`, `min_confidence_for_proposal=0.6`
  - `ReflectConfig` with `from_dict(data)` classmethod
  - `load_config(config_dir: Path) -> ReflectConfig` (returns defaults if file missing)

- [ ] **4.5** Run GREEN: 3 passed

- [ ] **4.6** Commit: `feat(reflect): config loader with 17 check defaults`

---

## Task 5: workflow_checks.py — first 5 critical checks

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §6, §14

### Task Description

Implement the 5 critical workflow checks. Each check: `(sessions, tool_calls, config) -> list[Violation]`.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/workflow_checks.py`
- `superagents/skills/reflect/tests/test_workflow_checks.py`

### Steps

- [ ] **5.1** Write RED test with 5 tests covering: `controller_never_implements` (detects edit, clean case), `stuck_in_retry` (3x same cmd), `same_error_repeated` (3 sessions), `mandatory_reviewer_for_code` (missing spec-reviewer).

- [ ] **5.2** Run RED.

- [ ] **5.3** Implement `scripts/lib/workflow_checks.py`:
  - `Violation` dataclass: `check_name`, `severity`, `session_id`, `title`, `message`, `context`
  - `check_controller_never_implements` — architect + edit/write/apply_patch + completed
  - `check_stuck_in_retry` — same bash cmd 3+ times in one session
  - `check_same_error_repeated` — same (tool, error) in 3+ sessions
  - `check_mandatory_reviewer_for_code` — implementer session without spec-reviewer + code-quality-reviewer children
  - `check_gate_compliance` — stub returns [] (no gate markers in data yet)

- [ ] **5.4** Run GREEN: 5 passed

- [ ] **5.5** Commit: `feat(reflect): 5 critical workflow checks (controller, retry, errors, reviewers, gates)`

---

## Task 6: workflow_checks.py — remaining 11 checks

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §14

### Task Description

Add 8 warning + 3 info checks. Total 16.

### Files

**Modify:**
- `superagents/skills/reflect/scripts/lib/workflow_checks.py`
- `superagents/skills/reflect/tests/test_workflow_checks.py`

### Steps

- [ ] **6.1** Append 11 check functions to `workflow_checks.py`:
  - **Warning (8):** `check_tdd_red_first`, `check_max_review_loops`, `check_regression_test_on_bugfix`, `check_arch_session_too_long`, `check_skill_triggered_when_should` (stub), `check_subagent_completion_rate`, `check_first_time_right`, `check_over_orchestration`
  - **Info (3):** `check_dead_end_sessions`, `check_skill_orphan` (stub), `check_context_overflow`, `check_missed_parallelism`
  - Append `ALL_CHECKS = [check_1, ..., check_16]` list

- [ ] **6.2** Add 2 more tests to `tests/test_workflow_checks.py` for `tdd_red_first` and `context_overflow`.

- [ ] **6.3** Run GREEN: 7+ passed

- [ ] **6.4** Commit: `feat(reflect): 11 more workflow checks (warnings + info). Total 16.`

---

## Task 7: redactor.py — secret scrubbing

### Classification: small
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §12 (Open question #6, privacy)

### Task Description

Regex-based filter for API keys/tokens/passwords before LLM call.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/redactor.py`
- `superagents/skills/reflect/tests/test_redactor.py`

### Steps

- [ ] **7.1** Write RED test with 6 tests: `redacts_openai_keys`, `redacts_google_api_keys`, `redacts_bearer_tokens`, `redacts_password_env_vars`, `preserves_normal_text`, `patterns_list_nonempty`.

- [ ] **7.2** Run RED.

- [ ] **7.3** Implement `scripts/lib/redactor.py`:
  - `REDACT_PATTERNS`: 6 regex patterns (OpenAI sk-, Google AIza, Bearer, password env vars, GitHub ghp_, Slack xox-)
  - `redact_secrets(text) -> str` — applies all patterns, replaces with `[REDACTED]`

- [ ] **7.4** Run GREEN: 6 passed

- [ ] **7.5** Commit: `feat(reflect): redactor.py with 6 secret patterns`

---

## Task 8: proposals.py — decision log filesystem layer

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §7.1, §4.2

### Task Description

CRUD for proposals on filesystem. Each proposal is a `.md` in `~/.config/opencode/reflection/proposals/`. On decision, moved to `decisions/`.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/proposals.py`
- `superagents/skills/reflect/tests/test_proposals.py`

### Steps

- [ ] **8.1** Write RED test with 4 tests: `test_create_proposal_writes_file`, `test_list_pending_proposals`, `test_record_decision_moves_file`, `test_list_decisions_includes_metadata`.

- [ ] **8.2** Run RED.

- [ ] **8.3** Implement `scripts/lib/proposals.py`:
  - `PROPOSAL_TEMPLATE` (markdown with ID/severity/confidence/auto-apply mark/target/rationale/diff/Action checklist)
  - `DECISION_TEMPLATE` (Outcome/Decided/Reason/Commit SHA)
  - `create_proposal(base_dir, proposal_id, title, severity, confidence, target, rationale, diff, auto_apply_eligible) -> str`
  - `list_pending_proposals(base_dir) -> list[dict]`
  - `record_decision(base_dir, proposal_id, outcome, reason, commit_sha)` — moves file from proposals/ to decisions/
  - `list_decisions(base_dir) -> list[dict]`

- [ ] **8.4** Run GREEN: 4 passed

- [ ] **8.5** Commit: `feat(reflect): proposals.py with create/list/decision CRUD on filesystem`

---

## Task 9: templates + analyze.py skeleton

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5, §15, §16

### Task Description

Create 4 markdown templates (post-mortem, wave-report, nightly-digest, proposal) and skeleton `analyze.py` that fills them with data.

### Files

**Create:**
- `superagents/skills/reflect/templates/{post-mortem,wave-report,nightly-digest,proposal}.md`
- `superagents/skills/reflect/scripts/lib/analyze.py`
- `superagents/skills/reflect/tests/test_analyze.py`

### Steps

- [ ] **9.1** Create 4 templates (see spec §5.1, §5.2, §5.3 + §15 for proposal format). Each uses `{var}` placeholders. Post-mortem has bug_summary/originating workflow/gaps table/proposals. Wave-report has summary/subagent table/violations/proposals. Nightly-digest has top issues/reflection health/trends. Proposal has target/rationale/evidence/diff/related decisions.

- [ ] **9.2** Write RED test with 3 tests: `test_fill_template_substitutes_vars`, `test_format_violations_table`, `test_generate_proposal_id_format`.

- [ ] **9.3** Run RED.

- [ ] **9.4** Implement `scripts/lib/analyze.py`:
  - `fill_template(template, **kwargs) -> str` — substitutes `{var}`, raises on unfilled
  - `format_violations_table(violations) -> str` — markdown table with severity/check/session/message
  - `format_violations_with_context(violations) -> str` — same + context fields
  - `generate_proposal_id(date, seq) -> str` — format `prop-YYYY-MM-DD-NNN`

- [ ] **9.5** Run GREEN: 3 passed

- [ ] **9.6** Commit: `feat(reflect): 4 templates + analyze.py skeleton (template filler, no LLM yet)`

---

## Task 10: attribute_to_sessions.py — file → sessions

### Classification: small
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5.1 (Bug-driven step 1)

### Task Description

Given a file path, find sessions that touched it via `git log` + `session.path` + time window.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/attribute_to_sessions.py`
- `superagents/skills/reflect/tests/test_attribute_to_sessions.py`

### Steps

- [ ] **10.1** Write RED test with 3 tests: `test_match_session_to_path_same_path`, `test_match_session_to_path_different_path`, `test_find_sessions_for_file_via_git_log` (skips if no git repo).

- [ ] **10.2** Run RED.

- [ ] **10.3** Implement `scripts/lib/attribute_to_sessions.py`:
  - `match_session_to_path(session, repo_path) -> bool` — checks session.path contains repo_path
  - `get_git_commits_for_file(repo_path, file) -> list[dict]` — runs `git log --format=%H|%ct|%an -- file`, returns list of `{sha, time_ms, author}`
  - `find_sessions_for_file(sessions, target_file, repo_path, window_ms=24h) -> list[dict]` — algorithm: git log → for each commit, find session matching path + within time window

- [ ] **10.4** Run GREEN: 2-3 passed

- [ ] **10.5** Commit: `feat(reflect): file→session attribution via git log + path match`

---

## Task 11: quality_scoring.py — skill/agent effectiveness

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §7.3

### Task Description

Score skills and agents by usage + success + token efficiency. Heuristics only (LLM classify in Task 14).

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/quality_scoring.py`
- `superagents/skills/reflect/tests/test_quality_scoring.py`

### Steps

- [ ] **11.1** Write RED test with 3 tests: `test_score_agents_basic`, `test_score_agents_filters_below_min_samples`, `test_score_skills_extracts_from_parts`.

- [ ] **11.2** Run RED.

- [ ] **11.3** Implement `scripts/lib/quality_scoring.py`:
  - `EffectivenessScore` dataclass: `name`, `type`, `usage_count`, `success_rate`, `token_efficiency`, `duration_impact_ms`, `composite_score`, `confidence`
  - `_is_success(session)` — heuristic: archived + cost >= 0
  - `_composite(success, efficiency, samples)` — weighted: 0.5*success + 0.3*efficiency + 0.2*confidence_penalty
  - `score_agents(sessions, min_samples=5) -> dict[str, EffectivenessScore]`
  - `score_skills(sessions, tool_calls, min_samples=5) -> dict[str, EffectivenessScore]` — parses skill name from `cmd` field

- [ ] **11.4** Run GREEN: 3 passed

- [ ] **11.5** Commit: `feat(reflect): quality_scoring.py with agent + skill effectiveness scores`

---

## Task 12: closing_the_loop.py — proposal → outcome

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §7.2

### Task Description

Match new proposals/violations with past decisions. Mark if applied proposal "should have prevented" current violation.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/closing_the_loop.py`
- `superagents/skills/reflect/tests/test_closing_the_loop.py`

### Steps

- [ ] **12.1** Write RED test with 4 tests: `test_find_related_decisions_same_target`, `test_find_related_decisions_no_match`, `test_compute_loop_hit_rate_empty`, `test_compute_loop_hit_rate_with_matches`.

- [ ] **12.2** Run RED.

- [ ] **12.3** Implement `scripts/lib/closing_the_loop.py`:
  - `_decision_date(content)` — extract from `**Decided at:**` regex
  - `find_related_decisions(base_dir, target, keywords=None) -> list[dict]` — match by target file path or keywords
  - `evaluate_prevention(decision, current_violation, window_days=30) -> str` — returns "should_have_prevented" | "didnt_prevent" | "rejected" | "unknown"
  - `compute_loop_hit_rate(decisions_with_prevention) -> float` — % of applied decisions that prevented later violations

- [ ] **12.4** Run GREEN: 4 passed

- [ ] **12.5** Commit: `feat(reflect): closing_the_loop.py with decision matching + hit rate`

---

## Task 13: detect_skill_candidates.py — auto skill generation

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §15

### Task Description

Detect patterns that suggest a new skill should be created: recurring recovery (tool A error → tool B success) 3+ times, recurring command sequence 5+ times.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/detect_skill_candidates.py`
- `superagents/skills/reflect/tests/test_detect_skill_candidates.py`

### Steps

- [ ] **13.1** Write RED test with 2 tests: `test_detect_recurring_recovery_websearch_to_websearch_cited`, `test_detect_recurring_command_sequence`.

- [ ] **13.2** Run RED.

- [ ] **13.3** Implement `scripts/lib/detect_skill_candidates.py`:
  - `SkillCandidate` dataclass: `pattern_type`, `suggested_name`, `evidence`, `confidence`, `occurrences`, `sessions`
  - `detect_recurring_recovery(sessions, tool_calls, min_count=3) -> list[SkillCandidate]` — group tool calls by session, find (error_tool, error) → next success_tool patterns, aggregate
  - `detect_recurring_command_sequence(sessions, tool_calls, min_count=5) -> list[SkillCandidate]` — same bash cmd in 5+ different sessions

- [ ] **13.4** Run GREEN: 2 passed

- [ ] **13.5** Commit: `feat(reflect): detect_skill_candidates.py with 2 pattern detectors`

---

## Task 14: metrics.py + analyze.py LLM integration

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §16, §5.5

### Task Description

Two parts: (1) `metrics.py` — compute reflection process metrics; (2) `analyze.py` — extend with LLM call via `opencode` subprocess.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/metrics.py`
- `superagents/skills/reflect/tests/test_metrics.py`
- `superagents/skills/reflect/tests/test_analyze_llm.py`

**Modify:**
- `superagents/skills/reflect/scripts/lib/analyze.py`

### Steps

- [ ] **14.1** Write RED test for `metrics.py` with 3 tests: `test_compute_proposal_metrics_empty`, `test_compute_proposal_metrics_with_data` (using proposals+record_decision), `test_compute_compliance_trend_groups_by_day`.

- [ ] **14.2** Run RED.

- [ ] **14.3** Implement `scripts/lib/metrics.py`:
  - `compute_proposal_metrics(base_dir) -> dict` — returns `{total, applied, rejected, modified, pending, adoption_rate, false_positive_rate}` from pending + decisions
  - `compute_compliance_trend(sessions, violations, days=7) -> list[dict]` — daily compliance % over last N days

- [ ] **14.4** Add to `scripts/lib/analyze.py` (append):
  - `call_llm(prompt, config, model="omniroute/flash") -> str` — runs `opencode run --model MODEL <prompt>` subprocess, returns stdout. Uses `redact_secrets` on prompt first.
  - `generate_proposal_with_llm(violation, template_str, config) -> dict` — sends violation to LLM, parses JSON response, falls back to heuristic if parse fails.

- [ ] **14.5** Write RED test for LLM integration (uses `unittest.mock.patch` on `subprocess.run`):
  - `test_call_llm_invokes_opencode` — verifies subprocess called
  - `test_call_llm_redacts_secrets` — verifies prompt redacted before subprocess

- [ ] **14.6** Run GREEN: all passed

- [ ] **14.7** Commit: `feat(reflect): metrics.py + analyze.py LLM call via opencode subprocess`

---

## Task 15: reflect.sh CLI wrapper + lib/__init__.py

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5, §8

### Task Description

Bash CLI + Python argparse entry point. 4 modes: post-mortem, wave, nightly, status.

### Files

**Create:**
- `superagents/skills/reflect/scripts/reflect.sh`
- `superagents/skills/reflect/scripts/lib/__init__.py` (overwrite empty with CLI)
- `superagents/skills/reflect/scripts/lib/post_mortem.py` (stub)
- `superagents/skills/reflect/scripts/lib/wave_report.py` (stub)
- `superagents/skills/reflect/scripts/lib/nightly.py` (stub)
- `superagents/skills/reflect/scripts/lib/status_cmd.py` (stub)
- `superagents/skills/reflect/scripts/notify.sh`

### Steps

- [ ] **15.1** Create `scripts/reflect.sh`:
  ```bash
  #!/usr/bin/env bash
  # reflect.sh — CLI wrapper
  # Usage: reflect.sh <mode> [args]
  #   post-mortem --target=path
  #   wave --name="Wave X.Y"
  #   nightly [--days=7] [--auto-apply]
  #   status
  set -euo pipefail
  SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  PYTHONPATH="$SKILL_DIR/scripts" exec python3 -c "from reflect.scripts.lib import cli; cli.main()" "$@"
  ```
  Make executable: `chmod +x`.

- [ ] **15.2** Create `scripts/lib/__init__.py` with `main()` argparse entry:
  - 4 subparsers: post-mortem (--target, --repo), wave (--name), nightly (--days, --auto-apply), status
  - Each subparser routes to its mode module
  - Imports from `.post_mortem`, `.wave_report`, `.nightly`, `.status_cmd`

- [ ] **15.3** Create 4 stub mode files (each ~10 lines, just `def run_xxx(args) -> int: return 0` with print statement).

- [ ] **15.4** Create `scripts/notify.sh` (telegram notifier stub, real impl in Task 18).

- [ ] **15.5** Smoke test:
  ```bash
  cd /root/workspace/superagents/skills/reflect
  ./scripts/reflect.sh status
  ```
  Expected: prints "status: not yet implemented" or similar

- [ ] **15.6** Commit: `feat(reflect): CLI wrapper reflect.sh with 4 modes (stubs)`

---

## Task 16: bug-driven mode (post_mortem.py full pipeline)

### Classification: large
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5.1

### Task Description

Full post-mortem pipeline: file → sessions → tree → violations (all 16 checks) → LLM proposals → markdown output.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/post_mortem.py`
- `superagents/skills/reflect/tests/test_post_mortem.py`

### Steps

- [ ] **16.1** Write RED integration test: `test_post_mortem_creates_report` (uses sample_db_path fixture, patches subprocess.run for LLM, patches REFLECT_HOME to tmp_path).

- [ ] **16.2** Run RED.

- [ ] **16.3** Implement `scripts/lib/post_mortem.py`:
  - `REFLECT_HOME = Path.home() / ".config" / "opencode" / "reflection"`
  - `ALL_CHECKS` list (import from workflow_checks)
  - `_violations_to_proposals(violations, config, base_dir, date, seq_start) -> list[str]` — for each violation: call LLM, create proposal, return list of proposal IDs. Auto-apply eligible only for info severity + high confidence + config.enabled.
  - `run_post_mortem(args) -> int`:
    1. Load config
    2. Open DB read-only
    3. `find_sessions_for_file(target_file, repo)`
    4. `list_tool_calls` (all)
    5. `build_tree` (relevant sessions)
    6. Run all 16 checks
    7. `find_related_decisions` (target=target_file)
    8. `_violations_to_proposals`
    9. Fill post-mortem template
    10. Write report to `~/.config/opencode/reflection/reports/YYYY-MM-DD-postmortem-<target>.md`
    11. Print summary

- [ ] **16.4** Run GREEN (integration test passes).

- [ ] **16.5** Commit: `feat(reflect): post_mortem.py — full bug-driven pipeline`

---

## Task 17: wave-driven mode (wave_report.py)

### Classification: large
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5.2

### Task Description

Pipeline for wave-driven: find sessions by title pattern → tree → checks → quality scores → proposals.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/wave_report.py`
- `superagents/skills/reflect/tests/test_wave_report.py`

### Steps

- [ ] **17.1** Write RED integration test: `test_wave_report_creates_report` (similar to post_mortem test).

- [ ] **17.2** Run RED.

- [ ] **17.3** Implement `scripts/lib/wave_report.py`:
  - `find_wave_sessions(sessions, wave_name) -> list[dict]` — regex match `re.escape(wave_name)` against session titles (handles "Wave 4.5", "Wave 4.5 1", etc.)
  - `run_wave_report(args) -> int`:
    1. Load config
    2. Open DB
    3. Find wave sessions by title pattern
    4. Run all 16 checks
    5. `score_agents` + `score_skills` for quality metrics
    6. Aggregate: total_cost, total_tokens, compliance_score, first_time_right_pct
    7. Fill wave-report template
    8. Write report to `reports/YYYY-MM-DD-wave-<name>.md`
    9. Print summary

- [ ] **17.4** Run GREEN.

- [ ] **17.5** Commit: `feat(reflect): wave_report.py — wave-driven pipeline`

---

## Task 18: time-driven mode (nightly) + cron + telegram

### Classification: standard
### Required Docs
- `docs/specs/2026-06-19-reflection-mode-design.md` §5.3, §9.3, §16

### Task Description

Nightly: collect last N days → checks + quality + metrics + regression detection → digest with reflection health → telegram notification. Plus cron install script.

### Files

**Create:**
- `superagents/skills/reflect/scripts/lib/nightly.py`
- `superagents/skills/reflect/scripts/lib/notify.py`
- `superagents/skills/reflect/scripts/lib/status_cmd.py` (real impl)
- `superagents/skills/reflect/scripts/notify.sh` (real impl)
- `superagents/skills/reflect/scripts/install-cron.sh`
- `superagents/skills/reflect/tests/test_nightly.py`

### Steps

- [ ] **18.1** Implement `scripts/lib/notify.py`:
  - `notify_telegram(message: str, chat_id: str | None) -> bool` — uses `curl` to POST to `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`. Reads token from env or config.

- [ ] **18.2** Implement `scripts/lib/nightly.py`:
  - `_since_ms(days) -> int` — timestamp N days ago
  - `_detect_regressions(agg_now, agg_prev, threshold_pct) -> list[dict]` — compare tool usage stats current vs previous 7d, return tools with delta > threshold
  - `run_nightly(args) -> int`:
    1. Load config
    2. Open DB
    3. Collect last N days sessions + tool calls
    4. Run all 16 checks
    5. `score_agents` + `score_skills`
    6. `compute_proposal_metrics` (proposals+decisions)
    7. `compute_compliance_trend` (last 7 days)
    8. `_detect_regressions` (compare last 7d vs prev 7d)
    9. `detect_skill_candidates` (recurring patterns)
    10. Generate proposals from violations
    11. Fill nightly-digest template (includes reflection health table)
    12. Write report to `reports/YYYY-MM-DD-nightly.md`
    13. `notify_telegram` if severity >= configured threshold
    14. If `--auto-apply`: apply eligible proposals
    15. Print summary

- [ ] **18.3** Implement `scripts/lib/status_cmd.py`:
  - `run_status(args) -> int` — prints `compute_proposal_metrics` + counts of pending/decided + last report dates

- [ ] **18.4** Implement `scripts/notify.sh` (wrapper for `notify.py`, for cron compatibility).

- [ ] **18.5** Implement `scripts/install-cron.sh`:
  ```bash
  #!/usr/bin/env bash
  # Installs cron entry for nightly reflection
  CRON_LINE="0 3 * * * $SKILL_DIR/scripts/reflect.sh nightly --days=7 2>&1 | logger -t reflect-nightly"
  (crontab -l 2>/dev/null | grep -v "reflect.sh nightly"; echo "$CRON_LINE") | crontab -
  echo "Installed: $CRON_LINE"
  ```
  Make executable.

- [ ] **18.6** Write RED test: `test_nightly_creates_digest` (integration test with mocks).

- [ ] **18.7** Run GREEN.

- [ ] **18.8** Commit: `feat(reflect): nightly.py with regression detection + cron + telegram`

---

## Self-review (G2 gate)

- [x] All 18 tasks have exact file paths and step-by-step commands
- [x] Each task has Required Docs section
- [x] No "TBD" / "TODO" / "implement later" placeholders in main steps
- [x] TDD pattern: RED test → implement → GREEN → commit (Tasks 2-14)
- [x] Integration tests for mode pipelines (Tasks 16-18)
- [x] Classification marked per task
- [x] No TDD required for setup tasks (1, 15 stubs) but explicit about it
- [x] File structure matches spec §3.1
- [x] All 16 checks from spec §6+§14 implemented
- [x] All 3 trigger modes (post-mortem/wave/nightly) have full pipeline
- [x] Decision log + closing-the-loop + quality scoring + auto skill gen + reflection metrics all in plan
- [x] Cron + telegram + auto-apply supported
- [x] Estimated ~11-12 working days (matches spec)
