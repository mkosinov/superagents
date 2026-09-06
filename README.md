# SuperAgents

> A reusable agentic workflow framework for AI-driven software development.
>
> **Version:** 3.5
>
> **New project?** [New Project Setup](docs/setup/new-project-setup.md)

## What is SuperAgents? (read this first)

Every feature goes through **two phases**, and by design each phase runs in its own tool:

| Phase | What happens | Where it runs | Full reference |
|-------|--------------|---------------|----------------|
| **DESIGN** | brainstorm concept → spec + 5-perspective review panel → plan + plan review. Human gates G1a/G1b/G2. Output: approved spec + plan **pushed to main**. | **ZCode on the host** — an interactive session with you; review agents dispatched in parallel | [docs/workflow/design-phase.md](docs/workflow/design-phase.md) |
| **IMPL** | worktree + baseline → sequential task loop with two-stage reviews → visual gate → docs → merge/PR. Human gate G7. Input: the approved plan from DESIGN. | **OpenCode in the container** — @manager + @architect run it autonomously | [docs/workflow/impl-phase.md](docs/workflow/impl-phase.md) |

Why two tools: DESIGN is a conversation with a human at gates — it needs an interactive session and only one level of subagent dispatch, which the host (ZCode) provides. IMPL is a long autonomous pipeline with nested dispatch (manager → architect → coders/reviewers), which the container (OpenCode) provides. The only things that cross between them are **git** (pushed spec/plan) and the **GitHub Project board** (the card's status shows which gate was passed last). The handoff is one sentence: the user tells the container manager «продолжаем траекторию #NNN».

If IMPL discovers the spec or plan itself is wrong, the card bounces back to a DESIGN gate with an issue comment — see the return path in [impl-phase.md](docs/workflow/impl-phase.md).

Each project repo gets its own copies of the harness: `.zcode/` (DESIGN executors) and `.opencode/` (the full pipeline, container side), seeded from this repo's [`.zcode/`](.zcode/) and [`.opencode/`](.opencode/).

Capabilities:

- **7+ quality gates** (G1a/b, G2, G3, G4–G6, G4.5 visual, G7)
- **Test-Driven Development** (RED-GREEN-REFACTOR) for implementation work
- **Two-stage review** after non-trivial tasks (code compliance, then code quality + tests)
- **Git worktree isolation** per feature via `.opencode/scripts/create-worktree.sh`
- **Documentation on the feature branch** before finish
- **Resumable sessions** via `.opencode/scratchpad.md`
- **Fast Track Protocol** for post-merge polish without full G1–G2
- **Spec review panel** — 5 parallel free-model perspectives review every spec before user approval
- **Reflection mode** for workflow self-analysis (`/reflect`, `.opencode/skills/reflect/`)

## Workflow guides (detailed)

- **[DESIGN phase — host, ZCode](docs/workflow/design-phase.md)** — brainstorm G1a, spec + panel G1b, plan G2, board flips, the push-to-main seam contract
- **[IMPL phase — container, OpenCode](docs/workflow/impl-phase.md)** — plan-only entry, worktree G3, dev loop G4–G6, visual gate, finish G7, FasTP, agent architecture

One-line map:

```
DESIGN (host, ZCode):  Brainstorm (G1a) → Spec + panel (G1b) → Plan (G2) → push to main
                                                              ↓  «продолжаем траекторию #NNN»
IMPL (container, opencode):  Worktree + baseline (G3) → Dev loop (G4–G6) → Visual (G4.5) → Docs → Finish (G7)
```

## Quick Start

### New Project Setup

[New Project Setup](docs/setup/new-project-setup.md) — copy the `.zcode/` and `.opencode/` folders into your repo and adjust project-specific paths and test commands.

### Run Workflow (two phases, two tools)

| Phase | Step | Gate | Executor | Skill |
|-------|------|------|----------|-------|
| **DESIGN** (host, ZCode) | 0. Brainstorming | G1a (concept) | host session + user | `design-phase` |
| | 1. Spec + panel review | G1b (spec) | host session + `spec-panel-*` ×5 | `design-phase` (panel protocol ported from `panel-spec-review`) |
| | 2. Plan + review | G2 (plan) | host session + `plan-reviewer` | `design-phase` (conventions from `writing-plans`) |
| **IMPL** (container, OpenCode) | 0. Worktree + baseline | G3 | @architect (first IMPL action) | `using-git-worktrees` |
| | 4. Dev loop + reviews | G4–G6 | @architect → coders → reviewers | `subagent-driven-development` |
| | 4.5 Visual check (UI) | G4.5 | @architect | `visual-compliance-check.sh` |
| | 5. Docs | — | @docser | dispatch |
| | 6. Finish | G7 (merge) | @manager + user | `finishing-a-development-branch` |

Details, review tiers, and diagrams: [design-phase.md](docs/workflow/design-phase.md) · [impl-phase.md](docs/workflow/impl-phase.md).

## Repository Structure

```
superagents/
├── .opencode/               # IMPL pipeline (full container workflow) — seed for project .opencode/
│   ├── agents/              # Agent definitions (frontmatter + prompts)
│   │   ├── manager.md       # Primary entry point — gates, brainstorming, phase dispatch
│   │   ├── architect.md     # Phase executor — DESIGN or IMPL (never talks to user)
│   │   ├── frontend-coder.md# Next.js implementer
│   │   ├── backend-coder.md # FastAPI implementer
│   │   ├── plan-reviewer.md # Plan reviewer — plan vs spec (G2, DESIGN)
│   │   ├── code-compliance-reviewer.md  # Code compliance reviewer — code vs task (G5)
│   │   ├── code-quality-reviewer.md     # Quality + tests reviewer
│   │   ├── tester.md        # Test env prep + test suite runs (cheap model)
│   │   ├── debugger.md      # Root cause investigator
│   │   ├── docser.md        # Meta documentation
│   │   ├── deployer.md      # DevOps / deploy
│   │   └── spec-panel-*.md  # Spec review panel (5 perspectives, G1b)
│   ├── scripts/             # Shared automation (worktree, visual gate, subagent audit)
│   │   ├── create-worktree.sh
│   │   ├── remove-worktree.sh
│   │   ├── visual-compliance-check.sh
│   │   └── subagent-audit.py
│   ├── skills/              # Reusable skills (invoked via skill tool)
│   │   ├── brainstorming/
│   │   ├── writing-plans/
│   │   ├── using-git-worktrees/
│   │   ├── find-specialist/ # Pick agent when dispatch is unclear (architect)
│   │   ├── test-driven-development/
│   │   ├── subagent-driven-development/
│   │   ├── finishing-a-development-branch/
│   │   ├── systematic-debugging/
│   │   ├── fast-track-protocol/
│   │   ├── github-board/    # Board doc (script ships in both harness folders)
│   │   ├── panel-spec-review/     # Panel protocol (canon body for the host design-phase skill)
│   │   ├── pytest-patterns/       # Backend test patterns (generic, Memo examples)
│   │   ├── vitest-playwright-patterns/  # Frontend test patterns (generic, Memo examples)
│   │   └── reflect/
│   └── agents/AGENTS.md     # Shared-rules variant WITH the opencode session-id rule
├── .zcode/                  # DESIGN pipeline (host) — seed for project .zcode/
│   ├── AGENTS.seed.md       # Shared-rules variant WITHOUT session-id (zcode-only setups)
│   ├── agents/              # spec-panel-* ×5, plan-reviewer (+ smoke spikes)
│   ├── skills/design-phase/ # DESIGN phase skill (gates G1a/G1b/G2)
│   └── scripts/gh_board.py  # GitHub Project board script
└── docs/
    ├── workflow/            # design-phase.md + impl-phase.md (human reference)
    ├── architecture/        # token-economy, context-management, decision-log, reflection-mode
    ├── specs/ + plans/      # dated design artifacts (historical)
    └── setup/               # new-project-setup.md
```

## Agents

| Agent | Role | Mode | When to Dispatch |
|-------|------|------|-----------------|
| **@manager** | Entry point, brainstorming, gates, scratchpad, phase dispatch | Primary | Auto — starts on user request |
| **@architect** | Phase executor — runs DESIGN or IMPL, never talks to user | All | Dispatched by @manager |
| **@frontend-coder** | Next.js + TypeScript + Tailwind implementation | Subagent | UI/frontend tasks |
| **@backend-coder** | FastAPI + SQLite implementation | Subagent | API/backend tasks |
| **@plan-reviewer** | Verify "plan faithfully expands spec" (G2, DESIGN) | Subagent | Plan review before G2 approval |
| **@code-compliance-reviewer** | Verify "code matches plan" | Subagent | After small/standard/large tasks |
| **@code-quality-reviewer** | Verify "code is well-built AND tests pass" | Subagent | After compliance review passes |
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

Full gate list and behavior: [design-phase.md](docs/workflow/design-phase.md) · [impl-phase.md](docs/workflow/impl-phase.md).

## Reflection Mode

Self-analysis tool for the SuperAgents workflow. Reads `opencode.db` (read-only), runs 17 compliance checks (5 critical / 8 warning / 4 info, mapped to the Key Principles), and produces human-approved improvement proposals as markdown files.

### How to run

**Slash command (easiest)** — type in opencode:
```
/reflect
/reflect websearch was failing all day
```
Optional text after `/reflect` = "what user noticed as wrong/strange", passed to the analysis as context.

**CLI** — `.opencode/skills/reflect/scripts/reflect.sh`:

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
2. **Project-specific changes** → edit in project `.opencode/`/`.zcode/` only → no sync needed
3. Update **[docs/workflow/design-phase.md](docs/workflow/design-phase.md)** / **[docs/workflow/impl-phase.md](docs/workflow/impl-phase.md)** and this README when gates or steps change — using the workflow change checklist below
4. **@infra** verifies sync status when workflow files change in either repo

### Workflow change checklist

When behavior of a step or gate changes, update in order:

1. **`.opencode/agents/manager.md`** — routing, gate handling, phase dispatch (if change affects manager behavior)
2. **`.opencode/agents/architect.md`** — steps, triggers, gate rules
3. **Affected `.opencode/skills/*/SKILL.md`** — procedure invoked at that step
4. **`.opencode/scripts/`** — if automation changes
5. **`docs/workflow/design-phase.md` / `docs/workflow/impl-phase.md`** — human diagrams and gates
6. **This README** — if gates, skills list, or onboarding summary changes
7. **Project repos** — sync generic changes into `.opencode/`/`.zcode/`; restart agent runtime if required

### Documentation map (keep in sync)

| What | Human-readable | Runtime (agents execute) |
|------|----------------|---------------------------|
| DESIGN phase flow & gates | [docs/workflow/design-phase.md](docs/workflow/design-phase.md) | project `.zcode/skills/design-phase/SKILL.md` |
| IMPL phase flow & gates | [docs/workflow/impl-phase.md](docs/workflow/impl-phase.md) | — |
| Overview & onboarding | this README | — |
| Entry point + routing (IMPL) | — | [.opencode/agents/manager.md](.opencode/agents/manager.md) |
| Orchestration steps (IMPL) | — | [.opencode/agents/architect.md](.opencode/agents/architect.md) |
| Worktree create/remove | — | [.opencode/skills/using-git-worktrees/SKILL.md](.opencode/skills/using-git-worktrees/SKILL.md), [.opencode/scripts/create-worktree.sh](.opencode/scripts/create-worktree.sh), [.opencode/scripts/remove-worktree.sh](.opencode/scripts/remove-worktree.sh) |
| Dev loop & reviews | — | [.opencode/skills/subagent-driven-development/SKILL.md](.opencode/skills/subagent-driven-development/SKILL.md) |
| Visual gate | impl-phase.md, Step 4.5 | [.opencode/scripts/visual-compliance-check.sh](.opencode/scripts/visual-compliance-check.sh) |
| Reviewer behavior | impl-phase.md, agent architecture | [.opencode/agents/plan-reviewer.md](.opencode/agents/plan-reviewer.md), [.opencode/agents/code-compliance-reviewer.md](.opencode/agents/code-compliance-reviewer.md), [.opencode/agents/code-quality-reviewer.md](.opencode/agents/code-quality-reviewer.md) |

Test commands and app paths in diagrams may show *example (Memo)*; each project configures its own commands in its `.opencode/`/`.zcode/` copies.

### Generic vs Project-Specific

| Generic (edit superagents/) | Project-specific (edit project .opencode/ or .zcode/) |
|----------------------------|-------------------------------------------|
| Workflow steps, gates, rules | Project name, design system paths |
| Agent roles and responsibilities | Model assignments, temperature settings |
| Task classification, circuit breaker | Tech stack versions, mock data refs |
| Skill definitions | Permission lists in frontmatter |
| Review pipeline structure | Project-specific bash allow lists, test commands |

## Changelog

- **3.5** — workflow docs split by phase: `docs/workflow/README.md` → `design-phase.md` (host, ZCode, gates G1a–G2) + `impl-phase.md` (container, OpenCode, G3–G7); root README re-written as the two-phase entry point for newcomers. Canon restructured: flat `agents/`+`skills/`+`scripts/` moved into `.opencode/` (full pipeline) and `.zcode/` (DESIGN-only host seed); project seeding = copy the two folders + AGENTS.md to the project root.
- **3.4** — agent registry rename (names state the reviewed document): `spec-review-*` panel → `spec-panel-*`; `spec-reviewer` split into `plan-reviewer` (G2: plan vs spec, DESIGN) + `code-compliance-reviewer` (G5: code vs task, symmetry with code-quality-reviewer at G6); gate G5 label "Spec Compliance" → "Code Compliance". Container `.opencode` copies re-sync manually after in-flight IMPL waves.
- **3.3** — host/container phase split: DESIGN (G1a–G2) can run in a host session, IMPL stays in-container; plan-only IMPL entry (architect creates worktree + baseline as its first IMPL action, IMPL Step 0); git+board seam contract with diverged-main STOP and a one-time return path (BLOCKED → issue comment → card back).
- **3.2** — asymmetric G2: spec-reviewer validates plans before implementation; user approves by behavior, not code. Manager/Architect split: @manager owns conversation + gates, @architect is phase executor. Spec review panel (5 free-model perspectives). Reflection mode. Context HANDOFF protocol.

## License

MIT / Proprietary — for internal use in AI-assisted development workflows.
