# SuperAgents

> A reusable agentic workflow framework for AI-driven software development.
>
> **System:** @architect (controller) + subagent implementers + two-stage review pipeline
> **Version:** 3.2
>
> **New project?** [New Project Setup](docs/setup/new-project-setup.md)

## What is SuperAgents?

SuperAgents orchestrates AI agents through a fixed **feature lifecycle**: design and written spec → implementation plan → isolated git worktree → sequential tasks with reviews → docs on the branch → merge or PR. Humans approve at key gates; everything between gates runs automatically.

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
G1a/G1b (Human) → G2 (Human) → G3 worktree (Auto) → G4–G6 dev+review (Auto) → G4.5 visual if UI (Auto) → docs → G7 (Human)
```

In the IDE, start **@architect** and ask for a new feature; it invokes skills (`brainstorming`, `writing-plans`, `using-git-worktrees`, …) in order.

## Quick Start

### New Project Setup

[New Project Setup](docs/setup/new-project-setup.md) — copy agents, skills, and templates into your repo and adjust project-specific paths and test commands.

### Run Workflow (architect)

| Step | Gate | Skill |
|------|------|--------|
| Brainstorming + spec | G1a, G1b | `brainstorming` |
| Implementation plan | G2 | `writing-plans` |
| Worktree + baseline tests | G3 | `using-git-worktrees` (+ `scripts/create-worktree.sh`) |
| Tasks + reviews | G4–G6 | `subagent-driven-development` |
| Finish (merge / PR / …) | G7 | `finishing-a-development-branch` |

Details, review tiers, and diagrams: **[Workflow guide](docs/workflow/README.md)**.

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
│   ├── using-skills/
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
6. **Diff for reviewers (hybrid)** — architect reads `git diff --stat` only; full diff goes to a file; reviewers read the file (saves architect tokens). Not “paste entire diff into architect chat.”
7. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
8. **No Temporary Tool Installation** — all tools in Dockerfile, never in worktree

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

- **3.2** — asymmetric G2: spec-reviewer validates plans before implementation; user approves by behavior, not code.

## License

MIT / Proprietary — for internal use in AI-assisted development workflows.
