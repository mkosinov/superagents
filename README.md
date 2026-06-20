# SuperAgents

> A reusable agentic workflow framework for AI-driven software development.
>
> **System:** @architect (controller) + subagent implementers + two-stage review pipeline
> **Version:** 3.1
> **Date:** 2026-05-15

## What is SuperAgents?

SuperAgents is a workflow framework for orchestrating AI agents to develop software with:

- **Automatic workflow progression** through 7 quality gates
- **Test-Driven Development** (RED-GREEN-REFACTOR) for all code
- **Two-stage review** after every non-trivial task (spec compliance + code quality)
- **Git worktree isolation** for every feature
- **Documentation committed** into feature branch before PR
- **Workflow resumable** after session interruption via scratchpad

## Quick Start

### New Project Setup

See [`docs/setup/new-project-setup.md`](docs/setup/new-project-setup.md)

### Run Workflow

1. **G1a+b Brainstorming** → invoke `brainstorming` skill
2. **G2 Planning** → invoke `writing-plans` skill
3. **G3 Worktree** → invoke `using-git-worktrees` skill
4. **G4-G6 Development** → invoke `subagent-driven-development` skill
5. **G7 Finishing** → invoke `finishing-a-development-branch` skill

## Repository Structure

```
superagents/
├── agents/                  # Agent definitions (frontmatter + prompts)
│   ├── architect.md         # Primary controller
│   ├── frontend-coder.md    # Next.js implementer
│   ├── backend-coder.md     # FastAPI implementer
│   ├── spec-reviewer.md     # Spec compliance reviewer
│   ├── code-quality-reviewer.md  # Quality + tests reviewer
│   ├── debugger.md          # Root cause investigator
│   ├── docser.md            # Meta documentation
│   └── deployer.md          # DevOps / deploy
├── skills/                  # Reusable skills (invoked via skill tool)
│   ├── brainstorming/
│   ├── writing-plans/
│   ├── using-git-worktrees/
│   ├── test-driven-development/
│   ├── subagent-driven-development/
│   ├── finishing-a-development-branch/
│   ├── using-skills/
│   ├── systematic-debugging/
│   └── reflect/
├── templates/               # Reviewer prompt templates
│   └── reviewers/
│       ├── spec-reviewer.md
│       └── code-quality-reviewer.md
└── docs/
    ├── workflow/            # Workflow documentation
    ├── architecture/        # System design decisions
    └── setup/               # Project initialization guides
```

## Agents

| Agent | Role | Mode | When to Dispatch |
|-------|------|------|-----------------|
| **@architect** | Workflow controller, planning, delegation | Primary | Entry point for all requests |
| **@frontend-coder** | Next.js + TypeScript + Tailwind implementation | Subagent | UI/frontend tasks |
| **@backend-coder** | FastAPI + SQLite implementation | Subagent | API/backend tasks |
| **@spec-reviewer** | Verify "code matches plan" | Subagent | After small/standard/large tasks |
| **@code-quality-reviewer** | Verify "code is well-built AND tests pass" | Subagent | After spec-review passes |
| **@debugger** | Root cause analysis | Subagent | On BLOCKED/bugs |
| **@docser** | Meta documentation (PLAN.md, CHANGELOG) | Subagent | After all tasks complete |
| **@deployer** | Production deployment | Subagent | On user request |

## Key Principles

1. **Controller Never Implements** — @architect plans and delegates, never edits code
2. **Two-Stage Review** — spec compliance → code quality, never one without the other
3. **Sequential Tasks** — one implementer at a time, no parallel dispatch
4. **Human Gates** — G1a (design concept), G1b (written spec), G2 (plan), G7 (finish) require user approval
5. **Circuit Breaker** — max 3 review loops per reviewer, then escalate
6. **Diff in Prompt** — reviewers receive git diff embedded, never read files
7. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
8. **No Temporary Tool Installation** — all tools in Dockerfile, never in worktree

## Workflow Diagram

See [`docs/workflow/README.md`](docs/workflow/README.md) for full flow.

```
G1a(Human) → G1b(Human) → G2(Human) → G3(Auto) → G4-G6(Auto) → G7(Human)
Concept      Spec        Plan         Worktree    Development      Finish
```

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

This repo (`/root/workspace/superagents/`) is the **single source of truth** for the SuperAgents workflow framework.

**Project repos** (e.g., `/root/workspace/memo/.opencode/`) contain **local copies** of agents and skills adapted with project-specific context.

### Change Protocol

1. **Generic workflow changes** → edit in `superagents/` FIRST → commit → sync to project repos
2. **Project-specific changes** → edit in project `.opencode/` only → no sync needed
3. **@infra** verifies sync status when workflow files change in either repo

### Generic vs Project-Specific

| Generic (edit superagents/) | Project-specific (edit project .opencode/) |
|----------------------------|-------------------------------------------|
| Workflow steps, gates, rules | Project name, design system paths |
| Agent roles and responsibilities | Model assignments, temperature settings |
| Task classification, circuit breaker | Tech stack versions, mock data refs |
| Skill definitions | Permission lists in frontmatter |
| Review pipeline structure | Project-specific bash allow lists |

## License

MIT / Proprietary — for internal use in AI-assisted development workflows.
