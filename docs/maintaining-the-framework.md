# Maintaining the Framework

> For changes to the framework itself (this repo). For using the workflow, see the [README](../README.md) and [docs/workflow/](workflow/).

## Golden Source Rule

This repo is the **single source of truth** for the SuperAgents workflow framework.

**Project repos** contain **local copies** of agents and skills with project-specific context (test commands, paths, models).

## Change Protocol

1. **Generic workflow changes** → edit in `superagents/` FIRST → commit → sync to project repos
2. **Project-specific changes** → edit in project `.opencode/`/`.zcode/` only → no sync needed
3. Update **[docs/workflow/design-phase.md](workflow/design-phase.md)** / **[docs/workflow/impl-phase.md](workflow/impl-phase.md)** when gates or steps change — using the workflow change checklist below
4. **@infra** verifies sync status when workflow files change in either repo

**Language convention:** skill and agent bodies (`.opencode/`, `.zcode/`) are written in English. Literal user-side strings stay in the user's language: trigger phrases («design #NNN», «start impl #NNN», «коммитим»), sample user-facing messages, UI literals and domain data in examples (Алиса, «Картина маслом») — translating those would break real triggers and make examples diverge from the actual product.

## Workflow change checklist

When behavior of a step or gate changes, update in order:

1. **`.opencode/agents/manager.md`** — routing, gate handling, phase dispatch (if change affects manager behavior)
2. **`.opencode/agents/architect.md`** — steps, triggers, gate rules
3. **Affected `.opencode/skills/*/SKILL.md`** — procedure invoked at that step
4. **`.opencode/scripts/`** — if automation changes
5. **`docs/workflow/design-phase.md` / `docs/workflow/impl-phase.md`** — human diagrams and gates
6. **The README** — if gates, skills list, or onboarding summary changes
7. **Project repos** — sync generic changes into `.opencode/`/`.zcode/`; restart agent runtime if required

## Documentation map (keep in sync)

| What | Theory (canon, human-readable) | Adapter (runtime, agents execute) |
|------|----------------|---------------------------|
| DESIGN phase flow & gates | [docs/workflow/design-phase.md](workflow/design-phase.md) | project `.zcode/skills/design-phase/SKILL.md` |
| IMPL phase flow & gates | [docs/workflow/impl-phase.md](workflow/impl-phase.md) | — |
| Overview & onboarding | [README](../README.md) | — |
| Entry point + routing (IMPL) | — | [.opencode/agents/manager.md](../.opencode/agents/manager.md) |
| Scratchpad discipline (v2) | — | [.opencode/agents/manager.md](../.opencode/agents/manager.md), [.opencode/scripts/scratchpad_audit.py](../.opencode/scripts/scratchpad_audit.py), [.opencode/command/sanitize-scratchpad.md](../.opencode/command/sanitize-scratchpad.md) |
| Orchestration steps (IMPL) | — | [.opencode/agents/architect.md](../.opencode/agents/architect.md) |
| Worktree create/remove | — | [.opencode/skills/using-git-worktrees/SKILL.md](../.opencode/skills/using-git-worktrees/SKILL.md), [.opencode/scripts/create-worktree.sh](../.opencode/scripts/create-worktree.sh), [.opencode/scripts/remove-worktree.sh](../.opencode/scripts/remove-worktree.sh) |
| Dev loop & reviews | — | [.opencode/skills/subagent-driven-development/SKILL.md](../.opencode/skills/subagent-driven-development/SKILL.md) |
| Visual gate | impl-phase.md, Step 4.5 | [.opencode/scripts/visual-compliance-check.sh](../.opencode/scripts/visual-compliance-check.sh) |
| Reviewer behavior | impl-phase.md, role architecture | [.opencode/agents/plan-reviewer.md](../.opencode/agents/plan-reviewer.md), [.opencode/agents/code-compliance-reviewer.md](../.opencode/agents/code-compliance-reviewer.md), [.opencode/agents/code-quality-reviewer.md](../.opencode/agents/code-quality-reviewer.md) |

Test commands and app paths in diagrams may show *example (Memo)*; each project configures its own commands in its `.opencode/`/`.zcode/` copies.

## Generic vs Project-Specific

| Generic (edit superagents/) | Project-specific (edit project .opencode/ or .zcode/) |
|----------------------------|-------------------------------------------|
| Workflow steps, gates, rules | Project name, design system paths |
| Agent roles and responsibilities | Model assignments, temperature settings |
| Task classification, circuit breaker | Tech stack versions, mock data refs |
| Skill definitions | Permission lists in frontmatter |
| Review pipeline structure | Project-specific bash allow lists, test commands |
