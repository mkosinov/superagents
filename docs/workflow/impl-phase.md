# IMPL Phase — runs in the opencode container

> **Audience:** humans — this is the human-readable reference for the IMPL phase.
>
> **Where it runs:** autonomously in the **opencode container**: @manager (entry point, gates, scratchpad, board) dispatches @architect (phase executor); @architect dispatches implementers and reviewers. Nothing in IMPL talks to the user except through @manager.
>
> **Input:** an approved plan already on origin/main, card at `Ready to IMPL (G2)` (produced by the [DESIGN phase](design-phase.md) on the host). **Output:** merged PR / In-main.
>
> **Version:** 3.5 · **Last aligned:** 2026-09-06

Executors: the project's `.opencode/` — agents `manager`, `architect`, `frontend-coder`/`backend-coder`, reviewers, `tester`, `docser`; skills `using-git-worktrees`, `subagent-driven-development`, `finishing-a-development-branch`; scripts under `.opencode/scripts/`. Seed source: this repo's [`.opencode/`](../../.opencode/).

## At a glance

| Step | Gate | Who decides | Executors |
|------|------|-------------|-----------|
| Entry: plan-only start | — | user says «продолжаем траекторию #NNN» | @manager |
| 0. Worktree + baseline | G3 | Auto (ask if tests fail) | @architect |
| 4. Dev loop + reviews | G4–G6 | Auto | @architect → coders → reviewers |
| 4.5 Visual check (UI) | G4.5 | Auto, soft block | `visual-compliance-check.sh` |
| 5. Docs on branch | — | Auto | @docser |
| 6. Finish | G7 | **Human** | `finishing-a-development-branch` |

Legend: **Human** = requires a user decision (pause); `auto` = passes automatically; `▶` = automatic transition; `→` = data/control flow.

## Entry (plan-only start)

The user tells the container manager «продолжаем траекторию #NNN». @manager pre-flight, in order:

1. **Board:** issue #NNN must be at `Ready to IMPL (G2)`. Any other status → do NOT start IMPL; show the status to the user.
2. **Git:** `git fetch origin && git status -sb`. Behind → fast-forward. **Diverged → STOP + user** (never reset/merge on your own; no local-only commits on main while a host DESIGN session is in flight).
3. **Plan file:** must exist on the fetched main. Missing → STOP + user.

Then: dispatch @architect with the **plan-only** template (no `## Worktree:` line — the architect creates the worktree as its first action) and flip the board to `In IMPL`. No brainstorming — the feature is approved through G2.

## Full flow

```
╔══════════════════════════════════════════════════════════════╗
║  STEP 0: WORKTREE + BASELINE  (Auto Gate G3)                  ║
║  The architect's FIRST action of IMPL (plan-only start)       ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Fetch/ff + plan-vs-main sanity check
         │ 2. Invoke skill `using-git-worktrees`
         │ 3. Run .opencode/scripts/create-worktree.sh <branch>
         │ 4. cd .worktrees/<branch>; confirm .worktrees/ gitignored
         │ 5. Run project test suite → clean baseline
         │
         ▼  [G3: TESTS PASS]  (if fail → ask user)
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 4: SUBAGENT-DRIVEN DEVELOPMENT  (Auto Gates G4-G6)     ║
║  Sequential tasks — never parallel                            ║
╚══════════════════════════════════════════════════════════════╝
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
         │ │ Trivial: self-review + @architect       │
         ├─│   git diff spot-check (≤5 lines)        │
         │ └─────────────────────────────────────────┘
         │
          │ ┌─────────────────────────────────────────┐
          │ │ Small: compliance only (max 3 loops)  │
          ├─│                                          │
          │ │   git diff --stat BASE..HEAD (see scale) │
          │ │   git diff BASE..HEAD > /tmp/diff.patch  │
          │ │   Pass FILE PATH to reviewer prompt      │
          │ │   Dispatch @code-compliance-reviewer     │
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
          │ │   Stage 1: @code-compliance-reviewer     │
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
         │ 1. Gather context (design doc, plan, tasks, tests)
         │ 2. Dispatch @docser via task() tool
         │ 3. @docser updates PLAN.md + CHANGELOG.md
         │ 4. Commit INTO feature branch
         │
         ▼
╔══════════════════════════════════════════════════════════════╗
║  STEP 6: FINISHING  (Human Gate G7)                          ║
╚══════════════════════════════════════════════════════════════╝
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

**After merge / polish:** [`fast-track-protocol`](../../.opencode/skills/fast-track-protocol/SKILL.md) (lighter path, @manager dispatches coders directly).

## Agent architecture (container)

```
               ┌──────────────────────────┐
               │       @manager            │
               │  (primary entry point)    │
               │  gates, brainstorming,    │
               │  scratchpad, board        │
               └────────────┬─────────────┘
                            │ dispatches via task()
                            │ (DESIGN or IMPL phase)
                            ▼
               ┌──────────────────────────┐
               │      @architect           │
               │  (phase executor)         │
               │  NEVER implements code    │
               │  NEVER talks to user      │
               └────────────┬─────────────┘
                            │ dispatches via task()
          ┌─────────────────┼─────────────────────────┐
          │                 │                         │
          ▼                 ▼                         ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ @frontend-coder  │  │  @backend-coder  │  │  @debugger       │
│ (implementer)    │  │  (implementer)   │  │  (investigator)  │
│ Next.js + TDD    │  │  FastAPI + TDD   │  │  root cause      │
└──────────────────┘  └──────────────────┘  └──────────────────┘

          ▼                 ▼
┌────────────────────────┐  ┌──────────────────┐
│ @code-compliance-      │  │@code-quality-    │
│  reviewer (read-only)  │  │  reviewer        │
│ checks: code matches   │  │ (read-only +     │
│ plan                   │  │  tests)          │
└────────────────────────┘  └──────────────────┘

          ▼                 ▼
┌──────────────────┐  ┌──────────────────┐
│ @docser          │  │ @deployer        │
│ (scribe, docs)   │  │ (devops, manual) │
│ PLAN.md,         │  │ production       │
│ CHANGELOG        │  │ deploy           │
└──────────────────┘  └──────────────────┘

                    ▼
          ┌──────────────────┐
          │ @tester           │
          │ (env prep + runs) │
          │ cheap model       │
          └──────────────────┘
```

**Unsure which agent to dispatch?** @architect may use [`.opencode/skills/find-specialist`](../../.opencode/skills/find-specialist/SKILL.md) (not a gate).

## Task classification & review budget

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

**Why:** prevents UI mismatch (wrong tabs, missing controls). Catches what unit tests often miss — layout and visible DOM.

**What it does:**
1. **Screenshot capture** — Playwright captures key page states (mobile 390x844 by default, desktop optional)
2. **Element presence checks** — verifies DOM elements from the spec exist and are visible
3. **Report generation** — markdown report with pass/fail status and screenshot paths

### When to run G4.5 vs skip

| Situation | Step 4.5 |
|-----------|----------|
| Phase changes **user-visible UI** (pages, components, styles users see) | **Run** after all tasks in that phase — once per phase, not per task |
| Design spec has **`## Visual Compliance Checks`** with real checklist items | **Run** — script reads that section |
| Phase is **backend/API/CLI/data only** — no UI surface in scope | **Skip** — go Step 4 → Step 5; do not run the script |
| Spec explicitly says **Visual Compliance N/A** (e.g. infra skill, no UI) | **Skip** — document in spec why N/A |
| **Mixed phase** (API + UI) | **Run** if any UI shipped; checks cover UI portion of spec |

**Architect rule of thumb:** if the spec never needed a Visual Compliance section and no `.tsx`/user-facing CSS was in the plan, skip 4.5. If UI was in scope, the spec should have included checks; a missing section on a UI feature is a spec gap — add checks or ask the user before skipping.

**Per-task vs phase:** implementers may run narrower visual/unit tests **per task** when UI files change. **G4.5** is the **phase-level** gate with `visual-compliance-check.sh` and the design spec file — one run before documentation (Step 5).

**Spec integration (UI features):** design specs include a `## Visual Compliance Checks` section:

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
/root/workspace/superagents/.opencode/scripts/visual-compliance-check.sh \
  http://localhost:3000 \
  docs/specs/YYYY-MM-DD-<feature>-design.md \
  /tmp/visual-compliance \
  mobile
```

**Gate behavior:** **PASS** → auto-proceed to Step 5; **FAIL** → soft block (user can override): fix/re-run, override, or abort.

## Alternate path: Fast Track Protocol (FasTP)

**Not a gate.** Used after merge or when the user sends a stream of small fixes/polish in chat — **not** for new features (those use DESIGN → IMPL).

```
User: post-merge fixes / UI polish / wiring tweaks
         │
         ▼
┌────────────────────────────────────────────┐
│ @manager invokes `fast-track-protocol`     │
│ • Dispatches coders directly (no architect)│
│ • Skip G1–G2 (no new spec/plan)            │
│ • UI changes → visual verification still   │
│   mandatory (per skill)                    │
│ • Local WIP commits until user signals     │
│   Phase 2 wrap-up ("коммитим", ship…)      │
└────────────────────────────────────────────┘
         │
         │ grows into real feature?
         ▼
    STOP FasTP → back to Phase 0 (brainstorming)
```

Runtime: [`fast-track-protocol`](../../.opencode/skills/fast-track-protocol/SKILL.md) + rules in [`.opencode/agents/architect.md`](../../.opencode/agents/architect.md).

## Board during IMPL

`In IMPL` (at dispatch) → `PR (G7)` (at finishing) → `In-main` (after merge; if the issue was Next Up 1 → `shift`). Flips belong to @manager. The board script lives in the project repo: `.opencode/scripts/gh_board.py`.

## Return path (spec/plan invalid → back to DESIGN)

A one-time bounce-back, not a live channel:

1. @architect reports BLOCKED because the spec or the plan itself is wrong (not an env or implementer issue) → @manager presents it to the user.
2. **The user decides** to return the trajectory.
3. @manager posts a GH issue comment describing the problem, then moves the card back: spec invalid → `In Design (G1a)`; spec intact, plan broken → `Spec OK (G1b)`.
4. Worktree/branch keep-vs-discard is the user's call.
5. The trajectory's scratchpad section closes with an Idle line: reason, new status, comment URL.

The next host DESIGN session picks the issue up from the board with the issue comment as input — see [design-phase.md](design-phase.md).

## Gates summary

```
G3 ─── Clean Baseline ────────── Auto ─── Tests pass on empty worktree
G4 ─── TDD Compliance ────────── Auto ─── Implementer self-check
G4a ── Architect Spot-Check ──── Auto ─── Diff ≤5 lines (trivial only)
G4.5 ─ Visual Compliance ─────── Auto ─── UI phases only; skip if no UI
G5 ─── Code Compliance ───────── Auto ─── Code matches plan (code-compliance-reviewer)
G6 ─── Code Quality + Tests ──── Auto ─── Clean code, tests pass
G6a ── Review Loop Limit ─────── Auto ─── Max 3 iterations → escalate
G6b ── Controller Never Implem.─ Auto ─── Architect did not edit code
G7 ─── Final Tests + Choice ──── Human ── Merge/PR/Keep/Discard
```

## Key principles (IMPL)

1. **Manager Owns Conversation** — @manager is the single entry point; @architect never talks to the user
2. **Controller Never Implements** — @architect plans and delegates, never edits code
3. **Two-Stage Review** — code compliance → code quality, never one without the other
4. **Sequential Tasks** — one implementer at a time, no parallel dispatch
5. **Circuit Breaker** — max 3 review loops per reviewer, then escalate
6. **Hybrid Diff Review** — @architect reads `--stat` only, passes the file path to reviewers (saves ~30-40% tokens)
7. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
8. **Env Work Delegated** — env prep and e2e/full-suite test runs go to @tester (cheap model)
9. **No Temporary Tool Installation** — all tools in Dockerfile, never in worktree

**Container restart required** after any `.opencode/agents/*.md` or `.opencode/skills/**/SKILL.md` changes.
