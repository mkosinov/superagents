# SuperAgents Workflow

> **System:** SuperAgents — @architect (controller) + subagents (implementers + reviewers)
> **Version:** 3.2

## Legend

| Symbol | Meaning |
|--------|---------|
| `G1`–`G7`, `G4.5` | Quality Gates |
| **Human** | Requires user decision (pause) |
| auto | Passes automatically |
| `▶` | Automatic transition to next step |
| `→` | Data/control flow |

## Full Workflow

```
┌──────────────────────────────────────────────────────────────────┐
│                    @architect (Controller)                        │
│  Role: Orchestrator — NEVER implements code                       │
└──────────────────────────────────────────────────────────────────┘
         │
         │ new feature request
         ▼
╔══════════════════════════════════════════════════════════════╗
║  STEP 1: BRAINSTORMING  (Human Gates G1a + G1b)           ║
╚══════════════════════════════════════════════════════════════╝
         │
         │ 1. Read scratchpad — resume or start fresh
         │ 2. Invoke skill `brainstorming`
         │ 3. Explore context → ask clarifying questions
         │ 4. Propose 2-3 approaches → present design sections
         │ 5. Get user approval on design concept
         │
         ▼  [G1a: USER APPROVES DESIGN CONCEPT]
         │
         │ 6. Save to docs/specs/YYYY-MM-DD-<feature>-design.md
         │ 7. Commit design doc
         │ 8. Spec self-review (placeholder, consistency, scope)
         │
         ▼  [G1b: USER APPROVES WRITTEN SPEC (HARD BLOCK)]
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 2: WRITING PLANS  (Human Gate G2)                     ║
╚══════════════════════════════════════════════════════════════╝
         │
         │ 1. Invoke skill `writing-plans`
         │ 2. Create implementation plan with classifications
         │    (trivial / small / standard / large)
         │ 3. Save to docs/plans/YYYY-MM-DD-<feature>-plan.md
         │ 4. Self-review for TBD/TODO/vague
         │
         ▼  [G2: USER APPROVES PLAN]
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 3: GIT WORKTREE  (Auto Gate G3)                       ║
╚══════════════════════════════════════════════════════════════╝
         │
         │ 1. Invoke skill `using-git-worktrees`
         │ 2. git worktree add .worktrees/feat-<name> -b feat-<name>
         │ 3. cd .worktrees/feat-<name>
         │ 4. cd frontend && npm install / cd backend && uv sync / pip install
         │ 5. Run tests → verify clean baseline
         │    npm run test:all  # vitest + playwright (browsers pre-installed in image)
         │
         ▼  [G3: TESTS PASS]  (if fail → ask user)
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 4: SUBAGENT-DRIVEN DEVELOPMENT  (Auto Gates G4-G6)    ║
║  Sequential tasks — never parallel                           ║
╚══════════════════════════════════════════════════════════════╝
         │
         │ For EACH task in plan (1..N):
         ▼
    ┌────────────┐
    │ 4a. Record │──→ Update scratchpad + GitHub Project board
    │ task start │
    └────────────┘
         │
         ▼
    ┌─────────────────────┐
    │ 4b. Dispatch         │
    │ Implementer          │
    │ (frontend-coder /    │
    │  backend-coder)      │
    │ via task() tool      │
    │                      │
    │ Prompt includes:     │
    │ • Task text (verbatim│
    │ • Classification     │
    │ • Scene-setting      │
    │ • Worktree path      │
    │ • TDD skill required │
    │ • Visual test rule:  │
    │   If diff touches UI │
    │   (.tsx, .css,       │
    │   tailwind.config)   │
    │   → run `test:all`   │
    └──────────┬──────────┘
         │
         ▼
    ┌──────────┐
    │ 4c.      │
    │ Handle   │──→ DONE → 4d
    │ Status   │──→ DONE_WITH_CONCERNS → read concerns → fix or proceed
    │          │──→ BLOCKED/NEEDS_CONTEXT → re-dispatch or escalate
    └──────────┘
         │
         ▼
    ┌──────────────────────────────────────────────┐
    │ 4d. Review Pipeline (depends on classification) │
    └──────────────────────────────────────────────┘
         │
         │ ┌─────────────────────────────────────────┐
         │ │ Trivial: self-review + architect        │
         ├─│   git diff spot-check (≤5 lines)        │
         │ └─────────────────────────────────────────┘
         │
          │ ┌─────────────────────────────────────────┐
          │ │ Small: spec-review only (max 3 loops)   │
          ├─│                                          │
          │ │   git diff --stat BASE..HEAD (see scale) │
          │ │   git diff BASE..HEAD > /tmp/diff.patch  │
          │ │   Pass FILE PATH to reviewer prompt      │
          │ │   Dispatch @spec-reviewer                 │
          │ │   If ❌ → re-dispatch implementer         │
          │ └─────────────────────────────────────────┘
          │
          │ ┌─────────────────────────────────────────┐
          │ │ Standard/Large: full two-stage review   │
          ├─│   (each max 3 loops)                     │
          │ │                                          │
          │ │   git diff --stat (see scale)            │
          │ │   git diff > /tmp/task-diff.patch        │
          │ │                                          │
          │ │   Stage 1: @spec-reviewer                 │
          │ │     Reads diff file independently        │
          │ │     If ❌ → implementer fixes → re-review │
          │ │     If ✅ → Stage 2                       │
          │ │                                          │
          │ │   Stage 2: @code-quality-reviewer         │
          │ │     Reads diff file + runs test suite    │
          │ │     UI diff → `npm run test:all`          │
          │ │     Else → `npm run test` (vitest only)   │
          │ │     If ❌ → implementer fixes → re-review │
          │ │     If ✅ → task complete                 │
          │ └─────────────────────────────────────────┘
         │
         ▼
    ┌──────────────────────┐
    │ 4e. Review Loop Limit│──→ Max 3 per reviewer
    │ (circuit breaker)    │──→ If exceeded → STOP → escalate
    └──────────────────────┘
         │
         ▼
    ┌──────────────────────┐
    │ 4f. Next Task        │──→ Auto. Do NOT ask "continue?"
    │ (auto)               │
    └──────────────────────┘
         │
          │ ALL TASKS DONE
          ▼
╔══════════════════════════════════════════════════════════════╗
║  STEP 4.5: VISUAL COMPLIANCE GATE  (Auto Gate G4.5)       ║
║  Run ONCE per phase — NOT per task                         ║
╚══════════════════════════════════════════════════════════════╝
          │
          │ 1. Start dev server (or use static build)
          │ 2. Run visual-compliance-check.sh <url> <spec>
          │    • Captures screenshots to /tmp/visual-compliance/
          │    • Verifies DOM elements from spec's Visual Compliance Checks
          │    • Generates markdown report
          │
          ▼  [G4.5: SOFT BLOCK]
          │
          │  ALL CHECKS PASSED? ──▶ proceed to Step 5
          │  ANY CHECK FAILED?  ──▶ report to user with screenshots
          │                         user decides: fix / override / abort
          │
          ▼ (after pass or user override)
╔══════════════════════════════════════════════════════════════╗
║  STEP 5: DOCUMENTATION COMMIT  (Auto)                        ║
╚══════════════════════════════════════════════════════════════╝
         │
         │ 1. Gather context (design doc, plan, tasks, tests)
         │ 2. Dispatch @docser via task() tool
         │ 3. @docser updates PLAN.md + CHANGELOG.md
         │ 4. Commit INTO feature branch
         │
         ▼
╔══════════════════════════════════════════════════════════════╗
║  STEP 6: FINISHING  (Human Gate G7)                          ║
╚══════════════════════════════════════════════════════════════╝
         │
         │ 1. Invoke skill `finishing-a-development-branch`
         │ 2. Run final tests
         │    npm run test:all  # vitest + playwright
         │ 3. Present 4 options:
         │
         ▼  [G7: USER CHOOSES]
         │
    ┌──────┴───────────────────────────────────────────────────┐
    │                                                           │
    ▼            ▼              ▼                   ▼           │
┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│Option 1│ │ Option 2 │ │ Option 3 │ │ Option 4 │             │
│ Merge  │ │ Push + PR│ │ Keep     │ │ Discard  │             │
│ locally│ │ (default)│ │ branch   │ │ (confirm)│             │
└────────┘ └──────────┘ └──────────┘ └──────────┘             │
```

## Quality Gates Summary

```
G1a ─── Design Concept Approval ─── Human ── Concept approved
G1b ─── Written Spec Approval ───── Human ── Spec file reviewed & approved
G2 ─── Plan Approval ─────────── Human ── Plan written
G3 ─── Clean Baseline ────────── Auto ─── Tests pass on empty worktree
G4 ─── TDD Compliance ────────── Auto ─── Implementer self-check
G4a ── Architect Spot-Check ──── Auto ─── Diff ≤5 lines (trivial only)
G4.5 ─ Visual Compliance ─────── Auto ─── Screenshots + DOM checks match design spec
G5 ─── Spec Compliance ───────── Auto ─── Code matches plan (reviewer)
G6 ─── Code Quality + Tests ──── Auto ─── Clean code, tests pass
G6a ── Review Loop Limit ─────── Auto ─── Max 3 iterations → escalate
G6b ── Controller Never Implem.─ Auto ─── Architect did not edit code
G7 ─── Final Tests + Choice ──── Human ── Merge/PR/Keep/Discard
```

## Agent Architecture

```
                       ┌─────────────────────┐
                       │    @architect        │
                       │  (primary/controller)│
                       │  NEVER implements    │
                       └──────────┬──────────┘
                                  │ dispatches via task()
          ┌───────────────────────┼──────────────────────────┐
          │                       │                          │
          ▼                       ▼                          ▼
┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ @frontend-coder  │  │  @backend-coder      │  │  @debugger           │
│ (implementer)    │  │  (implementer)       │  │  (investigator)      │
│ Next.js + TDD    │  │  FastAPI + TDD       │  │  root cause analysis │
└──────────────────┘  └──────────────────────┘  └──────────────────────┘

          ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐
│ @spec-reviewer       │  │ @code-quality-reviewer│
│ (read-only)          │  │ (read-only + tests)   │
│ checks: code matches │  │ checks: quality+tests │
│ plan spec            │  │ runs full test suite  │
└──────────────────────┘  └──────────────────────┘

          ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐
│ @docser              │  │ @deployer            │
│ (scribe, meta docs)  │  │ (devops, manual)     │
│ PLAN.md, CHANGELOG   │  │ production deploy    │
└──────────────────────┘  └──────────────────────┘
```

## Task Classification & Token Budget

```
                    ┌──────────┐
                    │   TASK   │
                    └────┬─────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
           ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Trivial  │  │  Small   │  │Standard  │
    │ ≤5 lines │  │ 1 file   │  │Multi-file│
    │ no logic │  │ <50 lines│  │ has logic│
    │ text only│  │ no state │  │ state    │
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │             │             │
         ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────────┐
    │Self-     │  │Spec      │  │Spec + Quality│
    │review    │  │review    │  │review (two-  │
    │~4K tokens│  │~18K tok  │  │stage) ~36K   │
    └──────────┘  └──────────┘  └──────────────┘
                                           │
                                           ▼
                                    ┌──────────┐
                                    │  Large   │
                                    │ >200 str │
                                    │ arch chg │
                                    └────┬─────┘
                                         │
                                         ▼
                                    ┌──────────────┐
                                    │Full two-stage│
                                    │+ final review│
                                    │~60K+ tokens  │
                                    └──────────────┘
```

## Visual Compliance Gate (Step 4.5)

**Why:** Prevents UI mismatch incidents (e.g. "Календарь-линия" implemented instead of "Сегодня / Завтра / Календарь" tabs). Caught by user manually — now automated.

**What it does:**
1. **Screenshot capture** — Playwright captures key page states (mobile 390x844 by default, desktop optional)
2. **Element presence checks** — Verifies DOM elements from the spec exist and are visible
3. **Report generation** — Markdown report with pass/fail status and screenshot paths

**Spec integration:** Design specs should include a `## Visual Compliance Checks` section:

```markdown
## Visual Compliance Checks
- [ ] "Сегодня" tab is visible and clickable on main page
- [ ] "Завтра" tab switches view to tomorrow's schedule
- [ ] "Календарь" tab opens date picker overlay
- [ ] Filter pills are visible below the tabs
- [ ] Clicking a filter pill highlights it and filters the list
```

**Execution:**
```bash
/root/workspace/superagents/scripts/visual-compliance-check.sh \
  http://localhost:3000 \
  docs/specs/YYYY-MM-DD-<feature>-design.md \
  /tmp/visual-compliance \
  mobile
```

**Gate behavior:**
- **PASS** → auto-proceed to Step 5
- **FAIL** → soft block (user can override). User chooses: fix/re-run, override, or abort

## Implementation Points

**This document describes the workflow conceptually. The actual execution is embedded in agent and skill files. See the main SuperAgents repository for source files.**

| Workflow Element | File |
|-----------------|------|
| Step 3 (G3 baseline test) | `agents/architect.md` Step 3 |
| Step 4b (implementer prompt) | `agents/architect.md` Step 4b |
| Step 4d (review test run) | `agents/architect.md` Stage 2 review |
| Step 4.5 (visual compliance) | `scripts/visual-compliance-check.sh` |
| Quality reviewer tests | `agents/code-quality-reviewer.md` |
| Worktree baseline test | `skills/using-git-worktrees/SKILL.md` Step 4 |
| Review pipeline | `skills/subagent-driven-development/SKILL.md` |

**Rule:** When this workflow changes, ALL agent and skill files MUST be synchronized. The system executes agent files, not this document.

**Container restart required** after any `agents/*.md` or `skills/**/SKILL.md` changes.

## Key Principles

1. **Controller Never Implements** — @architect plans and delegates, never edits code
2. **Two-Stage Review** — spec compliance → code quality, never one without the other
3. **Sequential Tasks** — one implementer at a time, no parallel dispatch
4. **Human Gates** — G1a (design concept), G1b (written spec), G2 (plan), G7 (finish) require user approval
5. **Circuit Breaker** — max 3 review loops per reviewer, then escalate
6. **Hybrid Diff Review** — architect reads `--stat` only, passes file path to reviewers (saves ~30-40% tokens)
7. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
8. **No Temporary Tool Installation** — all tools in Dockerfile, never in worktree
