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

1. **G1 Brainstorming** → invoke `brainstorming` skill
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
│   └── systematic-debugging/
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
4. **Human Gates** — G1 (design), G2 (plan), G7 (finish) require user approval
5. **Circuit Breaker** — max 3 review loops per reviewer, then escalate
6. **Diff in Prompt** — reviewers receive git diff embedded, never read files
7. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
8. **No Temporary Tool Installation** — all tools in Dockerfile, never in worktree

## Workflow Diagram

See [`docs/workflow/README.md`](docs/workflow/README.md) for full flow.

```
G1 (Human) → G2 (Human) → G3 (Auto) → G4-G6 (Auto) → G7 (Human)
Brainstorm   Plan         Worktree    Development      Finish
```

## Token Economy

See [`docs/architecture/token-economy.md`](docs/architecture/token-economy.md) for cost model and optimization rationale.

## Decision Log

See [`docs/architecture/decision-log.md`](docs/architecture/decision-log.md) for architecture decisions.

## License

MIT / Proprietary — for internal use in AI-assisted development workflows.
