# SuperAgents Workflow

> **Audience:** humans — product owners, tech leads, and anyone reviewing how SuperAgents runs a feature from idea to merge.
>
> **System:** @architect (controller) + subagent implementers + two-stage review
>
> **Version:** 3.2 · **Last aligned with skills/scripts:** 2026-07-21

**Start here from the repo root:** [README.md](../../README.md) (overview, agents, principles).

Agents **execute** [`agents/architect.md`](../../agents/architect.md) and **skills** under `skills/` — not this file. When the workflow changes, update architect, the affected skills, this document, and the root README together.

## At a glance

| Phase | Gate | Who decides | Skill (architect invokes) |
|-------|------|-------------|---------------------------|
| 1. Design & spec | G1a, G1b | **Human** | `brainstorming` |
| 2. Plan | G2 | **Human** | `writing-plans` |
| 3. Isolated workspace | G3 | Auto (ask if tests fail) | `using-git-worktrees` → **`scripts/create-worktree.sh`** |
| 4. Implementation loop | G4–G6 | Auto | `subagent-driven-development` |
| 4.5 Visual check (UI features) | G4.5 | Auto, soft block on fail | `scripts/visual-compliance-check.sh` |
| 5. Docs on branch | — | Auto | dispatch `@docser` |
| 6. Finish | G7 | **Human** | `finishing-a-development-branch` |

**After merge / polish:** [`fast-track-protocol`](../../skills/fast-track-protocol/SKILL.md) (lighter path, architect still delegates).

**Unsure which agent to dispatch?** Architect may use [`find-specialist`](../../skills/find-specialist/SKILL.md) (not a gate).

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
         │ 1. Invoke skill `using-git-worktrees` (or follow it if already loaded)
         │ 2. From repository root — run script (do not hand-roll worktree/deps):
         │      ./scripts/create-worktree.sh <branch-name>
         │    → creates .worktrees/<branch>, copies env files, sets up deps
         │ 3. cd .worktrees/<branch-name>
         │ 4. Confirm .worktrees/ is gitignored (skill Step 2)
         │ 5. Run project test suite → clean baseline
         │    (commands are project-specific: pnpm test, pytest, cargo test, …)
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
    │   → full visual test │
    │   suite (example:    │
    │   Memo: `test:all`)  │
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
          │ │     UI diff → full visual tests         │
          │ │       (example Memo: `npm run test:all`)  │
          │ │     Else → unit tests only              │
          │ │       (example Memo: `npm run test`)    │
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
         │ 2. Run final tests (project-specific;
         │    example Memo: `npm run test:all`)
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

> **Diagram note:** Commands shown as *example (Memo)* illustrate one reference stack (Next.js + vitest/playwright). Your project uses its own test commands in the `.opencode/` copy of agents/skills — not defined in this framework repo.

## Alternate path: Fast Track Protocol (FasTP)

**Not a gate.** Used after merge or when the user sends a stream of small fixes/polish in chat — **not** for new features (those use Steps 1–7 above).

```
User: post-merge fixes / UI polish / wiring tweaks
         │
         ▼
┌────────────────────────────────────────┐
│ @architect invokes `fast-track-protocol`│
│ • Skip G1–G2 (no new spec/plan)         │
│ • Still dispatches coders (no self-code)│
│ • UI changes → visual verification still│
│   mandatory (per skill)                 │
│ • Local WIP commits until user signals  │
│   Phase 2 wrap-up ("коммитим", ship…)   │
└────────────────────────────────────────┘
         │
         │ grows into real feature?
         ▼
    STOP FasTP → back to Step 1 (brainstorming)
```

Runtime: [`skills/fast-track-protocol/SKILL.md`](../../skills/fast-track-protocol/SKILL.md) + rules in [`agents/architect.md`](../../agents/architect.md) (Fast Track Protocol Skill).

## Quality Gates Summary

```
G1a ─── Design Concept Approval ─── Human ── Concept approved
G1b ─── Written Spec Approval ───── Human ── Spec file reviewed & approved
G2 ─── Plan Approval ─────────── Human ── Plan written
G3 ─── Clean Baseline ────────── Auto ─── Tests pass on empty worktree
G4 ─── TDD Compliance ────────── Auto ─── Implementer self-check
G4a ── Architect Spot-Check ──── Auto ─── Diff ≤5 lines (trivial only)
G4.5 ─ Visual Compliance ─────── Auto ─── UI phases only; skip if no UI (see below)
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

**Why:** Prevents UI mismatch (wrong tabs, missing controls). Catches what unit tests often miss — layout and visible DOM.

**What it does:**
1. **Screenshot capture** — Playwright captures key page states (mobile 390x844 by default, desktop optional)
2. **Element presence checks** — Verifies DOM elements from the spec exist and are visible
3. **Report generation** — Markdown report with pass/fail status and screenshot paths

### When to run G4.5 vs skip

| Situation | Step 4.5 |
|-----------|----------|
| Phase changes **user-visible UI** (pages, components, styles users see) | **Run** after all tasks in that phase — once per phase, not per task |
| Design spec has **`## Visual Compliance Checks`** with real checklist items | **Run** — script reads that section |
| Phase is **backend/API/CLI/data only** — no UI surface in scope | **Skip** — go Step 4 → Step 5; do not run the script |
| Spec explicitly says **Visual Compliance N/A** (e.g. infra skill, no UI) | **Skip** — document in spec why N/A |
| **Mixed phase** (API + UI) | **Run** if any UI shipped; checks cover UI portion of spec |

**Architect rule of thumb:** If Step 1 spec never needed a Visual Compliance section and no `.tsx`/user-facing CSS was in the plan, skip 4.5. If UI was in scope, G1 spec should have included checks; missing section on a UI feature is a spec gap — add checks or ask the user before skipping.

**Per-task vs phase:** Implementers may run narrower visual/unit tests **per task** when UI files change (see Step 4 diagram). **G4.5** is the **phase-level** gate with `visual-compliance-check.sh` and the design spec file — one run before documentation (Step 5).

**Spec integration (UI features):** Design specs should include a `## Visual Compliance Checks` section:

```markdown
## Visual Compliance Checks
- [ ] "Сегодня" tab is visible and clickable on main page
- [ ] "Завтра" tab switches view to tomorrow's schedule
- [ ] "Календарь" tab opens date picker overlay
- [ ] Filter pills are visible below the tabs
- [ ] Clicking a filter pill highlights it and filters the list
```

**Execution (example — Memo, Next.js on :3000):**
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

## Workflow change checklist

When behavior of a step or gate changes, update in order:

1. **`agents/architect.md`** — steps, triggers, gate rules (architect follows this through the flow)
2. **Affected `skills/*/SKILL.md`** — procedure invoked at that step
3. **`scripts/`** — if automation changes
4. **`docs/workflow/README.md`** — human diagram and gates (this file)
5. **[README.md](../../README.md)** — if gates, skills list, or onboarding summary changes
6. **Project repos** — sync generic changes into `.opencode/`; restart agent runtime if required

## Documentation map (keep in sync)

| What | Human-readable | Runtime (agents execute) |
|------|----------------|---------------------------|
| Full flow & gates | **This file** | — |
| Overview & onboarding | [README.md](../../README.md) | — |
| Orchestration steps | — | [agents/architect.md](../../agents/architect.md) |
| Worktree create/remove | — | [skills/using-git-worktrees/SKILL.md](../../skills/using-git-worktrees/SKILL.md), [scripts/create-worktree.sh](../../scripts/create-worktree.sh), [scripts/remove-worktree.sh](../../scripts/remove-worktree.sh) |
| Dev loop & reviews | — | [skills/subagent-driven-development/SKILL.md](../../skills/subagent-driven-development/SKILL.md) |
| Visual gate | Step 4.5 above | [scripts/visual-compliance-check.sh](../../scripts/visual-compliance-check.sh) |
| Reviewer behavior | Agent table above | [agents/spec-reviewer.md](../../agents/spec-reviewer.md), [agents/code-quality-reviewer.md](../../agents/code-quality-reviewer.md) |

Test commands and app paths in diagrams may show *example (Memo)*; each project configures its own commands in its `.opencode/` agent/skill copies.

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
