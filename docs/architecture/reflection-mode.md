# Reflection Mode — Architecture Overview

> **Design doc:** [`docs/specs/2026-06-19-reflection-mode-design.md`](../specs/2026-06-19-reflection-mode-design.md) (1092 lines, full specification)
> **Skill location:** [`skills/reflect/`](../../skills/reflect/)

## Design Philosophy

Reflection Mode is a **self-analysis sidecar** for the SuperAgents workflow. It runs parallel to the main development flow (not as a sequential gate) and audits historical session data against the 8 Key Principles. It is:

- **Read-only** — queries `opencode.db` without modifying it
- **Filesystem output** — proposals, reports, and decisions are markdown files, not a new database
- **Human-in-the-loop** — proposals require user approval by default; auto-apply is opt-in for low-risk changes
- **Reusable** — one skill + one agent definition, per-project config via `reflect.config.json`

## 17 Workflow Compliance Checks

Mapped to Key Principles and emergent anti-patterns. All checks are functions in `workflow_checks.py`, configurable per project (`enabled`, `severity`, `thresholds`).

| Severity | Checks | What they enforce |
|----------|--------|------------------|
| **critical** (5) | `controller_never_implements`, `mandatory_reviewer_for_code`, `stuck_in_retry`, `same_error_repeated`, `gate_compliance` | Hard rules: architect doesn't edit, reviews mandatory, gates passed, no infinite retry loops |
| **warning** (8) | `tdd_red_first`, `max_review_loops`, `regression_test_on_bugfix`, `arch_session_too_long`, `skill_triggered_when_should`, `subagent_completion_rate`, `first_time_right`, `over_orchestration` | Workflow quality: TDD, review cycles, regression tests, completion rates |
| **info** (4) | `dead_end_sessions`, `skill_orphan`, `context_overflow`, `missed_parallelism` | Hygiene: dead sessions, unused skills, compaction events, parallelization opportunities |

## Three Trigger Modes

| Mode | Entry point | When | Output |
|------|------------|------|--------|
| **Bug-driven** | `reflect.sh post-mortem --target=<path>` | Before fixing a bug | `post-mortem.md` + proposals for workflow gaps that caused the bug |
| **Wave-driven** | `reflect.sh wave --name="Wave N"` | End of a development wave | `wave-report.md` + proposals for the wave's violations |
| **Time-driven** | `reflect.sh nightly [--days=7]` | Nightly cron (`install-cron.sh` installs `0 3 * * *`) | `nightly-digest.md` with aggregated trends |

## Closing-the-Loop

Every proposal, when approved, records its effect:

1. **Proposal created** → stored under `~/.config/opencode/reflection/proposals/`
2. **User action** → approve (apply diff) or reject (with reason) → logged in `decisions/`
3. **Subsequent runs** → `closing_the_loop.py` checks if violations addressed by past proposals still reoccur
4. **Evidence tracked** → if a proposal's target pattern disappears post-application, the loop is considered closed

## Quality Scoring

Two-layer scoring for skills and agents:

- **Heuristic layer** — completion rate, review iterations, cost per session, tool error rates
- **LLM layer** — triggered on low-confidence cases; evaluates whether skill/agent contributed to successful outcomes

## Auto Skill Generation

`detect_skill_candidates.py` identifies recurring patterns that suggest new skills (e.g., same error → recovery sequence repeated 3+ times, repeated user warnings). Proposals include a draft `SKILL.md` diff.

## Reflection Metrics

Meta-metrics about the reflection process itself: number of runs, violations per run, proposal acceptance rate, time-to-close for loops, and trend data for compliance over time.

## Runtime State

All runtime data lives under `~/.config/opencode/reflection/`:
- `reports/` — generated reports (post-mortems, wave reports, nightly digests)
- `proposals/` — pending proposals awaiting user action
- `decisions/` — audit log of approved/rejected proposals
- `state.json` — last-run state for idempotency and trend calculation
