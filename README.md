# SuperAgents

> A reusable agentic workflow framework for AI-driven software development.
>
> **System:** @manager (entry point) → @architect (phase executor) + subagent implementers + two-stage review pipeline
> **Version:** 3.2
>
> **New project?** [New Project Setup](docs/setup/new-project-setup.md)

## What is SuperAgents?

SuperAgents orchestrates AI agents through a fixed **feature lifecycle** split into two phases:
- **DESIGN** — spec writing → spec review panel → plan → plan review → worktree + baseline tests
- **IMPL** — sequential task loop with reviews → visual compliance → docs → merge or PR

Humans approve at key gates (G1a/b, G2, G7); everything between gates runs automatically.

Capabilities:

- **7+ quality gates** (G1a/b, G2, G3, G4–G6, G4.5 visual, G7) — see [Workflow guide](docs/workflow/README.md)
- **Test-Driven Development** (RED-GREEN-REFACTOR) for implementation work
- **Two-stage review** after non-trivial tasks (spec compliance, then code quality + tests)
- **Git worktree isolation** per feature via `scripts/create-worktree.sh`
- **Documentation on the feature branch** before finish
- **Resumable sessions** via `.opencode/scratchpad.md`
- **Fast Track Protocol** for post-merge polish without full G1–G2
- **Spec review panel** — 5 parallel free-model perspectives review every spec before user approval
- **Reflection mode** for workflow self-analysis (`/reflect`, `skills/reflect/`)

## Workflow guide (detailed)

**For people:** step-by-step flow, gate diagram, agent roles, visual compliance, and which files agents actually run.

**[→ SuperAgents Workflow (`docs/workflow/README.md`)](docs/workflow/README.md)**

One-line map:

```
Phase 0: Brainstorming (G1a) → Phase DESIGN: Spec (G1b) → Plan (G2) → Worktree (G3)
                                                              ↓
Phase IMPL: Dev loop (G4–G6) → Visual gate (G4.5) → Docs → Finish (G7)
```

In the IDE, start **@manager** (or it starts automatically). It brainstorms with you, then dispatches **@architect** for each phase.

## Quick Start

### New Project Setup

[New Project Setup](docs/setup/new-project-setup.md) — copy agents, skills, and templates into your repo and adjust project-specific paths and test commands.

### Run Workflow (manager → architect)

| Phase | Step | Gate | Who | Skill |
|-------|------|------|-----|-------|
| **Phase 0** | Brainstorming | G1a (concept) | **@manager** + user | `brainstorming` |
| **DESIGN** | 1. Design spec | G1b (spec) | **@architect** | `brainstorming` (spec part) + `panel-spec-review` |
| | 2. Plan + review | G2 (plan) | **@architect** | `writing-plans` |
| | 3. Worktree + baseline | G3 | **@architect** | `using-git-worktrees` |
| **IMPL** | 4. Dev loop + reviews | G4–G6 | **@architect** | `subagent-driven-development` |
| | 4.5 Visual check (UI) | G4.5 | **@architect** | `visual-compliance-check.sh` |
| | 5. Docs | — | **@architect** | dispatch `@docser` |
| | 6. Finish | G7 (merge) | **@architect** | `finishing-a-development-branch` |

Details, review tiers, and diagrams: **[Workflow guide](docs/workflow/README.md)**.

## Repository Structure

```
superagents/
├── agents/                  # Agent definitions (frontmatter + prompts)
│   ├── manager.md           # Primary entry point — gates, brainstorming, phase dispatch
│   ├── architect.md         # Phase executor — DESIGN or IMPL (never talks to user)
│   ├── frontend-coder.md    # Next.js implementer
│   ├── backend-coder.md     # FastAPI implementer
│   ├── spec-reviewer.md     # Spec compliance reviewer
│   ├── code-quality-reviewer.md  # Quality + tests reviewer
│   ├── tester.md            # Test env prep + test suite runs (cheap model)
│   ├── debugger.md          # Root cause investigator
│   ├── docser.md            # Meta documentation
│   └── deployer.md          # DevOps / deploy
├── scripts/                 # Shared automation (worktree, visual gate)
│   ├── create-worktree.sh
│   ├── remove-worktree.sh
│   └── visual-compliance-check.sh
├── skills/                  # Reusable skills (invoked via skill tool)
│   ├── brainstorming/
│   ├── writing-plans/
│   ├── using-git-worktrees/
│   ├── find-specialist/     # Pick agent when dispatch is unclear (architect)
│   ├── test-driven-development/
│   ├── subagent-driven-development/
│   ├── finishing-a-development-branch/
│   ├── systematic-debugging/
│   ├── fast-track-protocol/
│   └── reflect/
├── templates/               # Reviewer prompt templates
│   └── reviewers/
└── docs/
    ├── workflow/            # Human workflow reference (start here for flow)
    ├── architecture/
    └── setup/
```

## Agents

| Agent | Role | Mode | When to Dispatch |
|-------|------|------|-----------------|
| **@manager** | Entry point, brainstorming, gates, scratchpad, phase dispatch | Primary | Auto — starts on user request |
| **@architect** | Phase executor — runs DESIGN or IMPL, never talks to user | All | Dispatched by @manager |
| **@frontend-coder** | Next.js + TypeScript + Tailwind implementation | Subagent | UI/frontend tasks |
| **@backend-coder** | FastAPI + SQLite implementation | Subagent | API/backend tasks |
| **@spec-reviewer** | Verify "code matches plan" | Subagent | After small/standard/large tasks |
| **@code-quality-reviewer** | Verify "code is well-built AND tests pass" | Subagent | After spec-review passes |
| **@tester** | Test env prep + test suite runs, compact reports | Subagent | Env-dependent test runs (e2e/full-suite), env pre-flight |
| **@debugger** | Root cause analysis | Subagent | On BLOCKED/bugs |
| **@docser** | Meta documentation (PLAN.md, CHANGELOG) | Subagent | After all tasks complete |
| **@deployer** | Production deployment | Subagent | On user request |

## Key Principles

1. **Manager Owns Conversation** — @manager is the single entry point; @architect never talks to the user
2. **Controller Never Implements** — @architect plans and delegates, never edits code
3. **Two-Stage Review** — spec compliance → code quality, never one without the other
4. **Sequential Tasks** — one implementer at a time, no parallel dispatch
5. **Human Gates** — G1a (design concept), G1b (written spec), G2 (plan), G7 (finish) require user approval
6. **Circuit Breaker** — max 3 review loops per reviewer, then escalate
7. **Diff for reviewers (hybrid)** — architect reads `git diff --stat` only; full diff goes to a file; reviewers read the file (saves architect tokens). Not "paste entire diff into architect chat."
8. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
9. **Env Work Delegated** — env prep and e2e/full-suite test runs go to @tester (cheap model); coders keep their contexts clean of env forensics
10. **No Temporary Tool Installation** — all tools in Dockerfile, never in worktree

Full gate list and behavior: **[Workflow guide](docs/workflow/README.md)**.

## Reflection Mode

Self-analysis tool for the SuperAgents workflow. Reads `opencode.db` (read-only), runs 16 compliance checks (mapped to the 8 Key Principles), and produces human-approved improvement proposals as markdown files.

### How to run

**Slash command (easiest)** — type in opencode:
```
/reflect
/reflect websearch was failing all day
```
Optional text after `/reflect` = "what user noticed as wrong/strange", passed to the analysis as context.

**CLI** — `skills/reflect/scripts/reflect.sh`:

| Mode | Command | Use when |
|------|---------|----------|
| `post-mortem` | `reflect.sh post-mortem --target=path/to/file` | Before fixing a bug — investigate the workflow that produced it |
| `wave` | `reflect.sh wave --name="Wave 4.5"` | After a wave — compliance + quality report |
| `in_session` | `reflect.sh in_session --session=ses_xxx` | Analyze current session + all subagents |
| `nightly` | `reflect.sh nightly --days=7` | Last N days digest (run from cron) |
| `status` | `reflect.sh status` | Health summary (proposal counts, adoption rate) |

**Auto-triggers:**
- **Nightly cron** (host): `0 3 * * *` → `reflect.sh nightly --days=7` → telegram on critical. Install with `bash ~/.config/opencode/scripts/install-host-cron.sh`.
- **Post-wave** (in `finishing-a-development-branch` skill): suggests running `reflect.sh wave` after merge or PR.

### Where the output lives

```
~/.config/opencode/reflection/
├── reports/      # Human-readable analysis (markdown)
├── proposals/    # Pending improvement proposals
├── decisions/    # Applied/rejected history (audit trail)
└── state.json    # Last-run cursors
```

**Apply a proposal** → read the `.md` in `proposals/`, decide. On decision (apply/reject), the file moves to `decisions/`.

### LLM

Uses `opencode-go/deepseek-v4-flash` (1M context, MIT license, $0.09/M input). No additional config needed.

### More info

- Spec: [`docs/specs/2026-06-19-reflection-mode-design.md`](docs/specs/2026-06-19-reflection-mode-design.md)
- Architecture: [`docs/architecture/reflection-mode.md`](docs/architecture/reflection-mode.md)

## Token Economy

See [`docs/architecture/token-economy.md`](docs/architecture/token-economy.md) for cost model and optimization rationale.

## Decision Log

See [`docs/architecture/decision-log.md`](docs/architecture/decision-log.md) for architecture decisions.

## Maintaining the Framework

### Golden Source Rule

This repo is the **single source of truth** for the SuperAgents workflow framework.

**Project repos** contain **local copies** of agents and skills with project-specific context (test commands, paths, models).

### Change Protocol

1. **Generic workflow changes** → edit in `superagents/` FIRST → commit → sync to project repos
2. **Project-specific changes** → edit in project `.opencode/` only → no sync needed
3. Update **[docs/workflow/README.md](docs/workflow/README.md)** and this README when gates or steps change — use the [workflow change checklist](docs/workflow/README.md#workflow-change-checklist) in that doc
4. **@infra** verifies sync status when workflow files change in either repo

### Generic vs Project-Specific

| Generic (edit superagents/) | Project-specific (edit project .opencode/) |
|----------------------------|-------------------------------------------|
| Workflow steps, gates, rules | Project name, design system paths |
| Agent roles and responsibilities | Model assignments, temperature settings |
| Task classification, circuit breaker | Tech stack versions, mock data refs |
| Skill definitions | Permission lists in frontmatter |
| Review pipeline structure | Project-specific bash allow lists, test commands |

## Changelog

- **3.2** — asymmetric G2: spec-reviewer validates plans before implementation; user approves by behavior, not code. Manager/Architect split: @manager owns conversation + gates, @architect is phase executor. Spec review panel (5 free-model perspectives). Reflection mode. Context HANDOFF protocol.

## License

MIT / Proprietary — for internal use in AI-assisted development workflows.
