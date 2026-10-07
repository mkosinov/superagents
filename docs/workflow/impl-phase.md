# IMPL Phase — plan → merged PR (autonomous)

> **Audience:** humans — this is the human-readable reference for the IMPL phase.
>
> **Where it runs:** autonomously — the phase is environment-independent; an isolated container is the recommended environment for the long autonomous run. A **session manager** (entry point, gates, scratchpad, board) dispatches a **controller** (phase executor); the controller dispatches implementers and reviewers. Nothing in IMPL talks to the user except through the session manager. Current adapter: the OpenCode Docker container (see [Executors](#executors-adapters-1)).
>
> **Input:** an approved plan already on origin/main, card at `Ready to IMPL` (produced by the [DESIGN phase](design-phase.md)). **Output:** merged PR / In-main.
>
> **Version:** 3.11 · **Last aligned:** 2026-10-07

## Executors (adapters)

The theory below names roles and artifacts, never tools. The current opencode adapter implements the roles like this (other harnesses implement the same roles with their own mechanics — dispatch tools, agent/skill formats, scripts, paths, model assignments — and reference this canon without re-telling it):

| Theory role | opencode adapter (container) |
|---|---|
| Session manager | agent `manager` (@manager) |
| Controller (phase executor) | agent `architect` (@architect) |
| Implementers | agents `frontend-coder`, `backend-coder` |
| Compliance reviewer | agent `code-compliance-reviewer` |
| Quality reviewer | agent `code-quality-reviewer` |
| Investigator (root cause) | agent `debugger` |
| Test runner (cheap model) | agent `tester` |
| Scribe (docs) | agent `docser` |
| Deployer | agent `deployer` |
| Dispatch tool | `task()` |
| Board script | `gh_board.py` (shipped with each adapter) |
| Worktree / visual / audit scripts | `.opencode/scripts/*` |
| Dev-loop / worktree / finishing skills | `subagent-driven-development`, `using-git-worktrees`, `finishing-a-development-branch`, `fast-track-protocol` |

Seed source: this repo's [`.opencode/`](../../.opencode/).

## At a glance

| Step | Gate | Who decides | Executors |
|------|------|-------------|-----------|
| Entry: plan-only start | — | user says «start impl #NNN» | session manager |
| 0. Worktree + baseline | G3 | Auto (BLOCKED on red baseline) | controller |
| 4. Dev loop + reviews | G4–G6 | Auto | controller → implementers → reviewers |
| 4.5 Visual check (UI) | G4.5 | Auto, soft block | visual compliance tooling |
| 5. Docs on branch | — | Auto | scribe |
| 6. Finish | G7 | **Human** | finishing skill (adapter) |

Legend: **Human** = requires a user decision (pause); `auto` = passes automatically; `▶` = automatic transition; `→` = data/control flow.

## Entry (plan-only start)

The user tells the IMPL session manager «start impl #NNN». The session manager pre-flight, in order:

1. **Board:** issue #NNN must be at `Ready to IMPL`. Any other status → do NOT start IMPL; show the status to the user.
2. **Git:** `git fetch origin && git status -sb`. Behind → fast-forward. **Diverged → STOP + user** (never reset/merge on your own; no local-only commits on main while a DESIGN session is in flight).
3. **Plan file:** must exist on the fetched main. Missing → STOP + user.

Then: dispatch the controller with the **plan-only** template (no `## Worktree:` line — the controller creates the worktree as its first action) and flip the board to `In IMPL`. No brainstorming — the feature is approved through G2.

## Full flow

```
╔══════════════════════════════════════════════════════════════╗
║  STEP 0: WORKTREE + BASELINE  (Auto Gate G3)                  ║
║  The controller's FIRST action of IMPL (plan-only start)      ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Fetch/ff + plan-vs-main sanity check
         │ 2. Invoke the worktree skill (adapter)
         │ 3. Create the feature worktree (adapter script:
         │    create-worktree.sh <branch>)
         │ 4. cd .worktrees/<branch>; confirm .worktrees/ gitignored
         │ 5. Verify clean baseline (CI fact-check, or local suite)
         │
         ▼  [G3: BASELINE GREEN]  (red → BLOCKED)
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
    │ (via the dispatch    │
    │  tool)               │
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
         │ │ Trivial: self-review + controller       │
         ├─│   git diff spot-check (≤5 lines)        │
         │ └─────────────────────────────────────────┘
         │
          │ ┌─────────────────────────────────────────┐
          │ │ Small: compliance only (max 3 loops)  │
          ├─│                                          │
          │ │   git diff --stat BASE..HEAD (see scale) │
          │ │   git diff BASE..HEAD > /tmp/diff.patch  │
          │ │   Pass FILE PATH to reviewer prompt      │
          │ │   Dispatch compliance reviewer           │
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
          │ │   Stage 1: compliance reviewer           │
          │ │     Reads diff file independently        │
          │ │     If ❌ → implementer fixes → re-review │
          │ │     If ✅ → Stage 2                       │
          │ │                                          │
          │ │   Stage 2: quality reviewer              │
          │ │     Reads diff file + runs test suite    │
          │ │     UI diff → full visual tests         │
          │ │       (example Memo: `npm run test:all`) │
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
          │ 2. Run the visual compliance check (adapter
          │    script: visual-compliance-check.sh <url> <spec>)
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
         │ 2. Dispatch the scribe via the dispatch tool
         │ 3. Scribe updates PLAN.md + CHANGELOG.md
         │ 4. Commit INTO feature branch
         │
         ▼
╔══════════════════════════════════════════════════════════════╗
║  STEP 6: FINISHING  (Human Gate G7)                          ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Invoke the finishing skill (adapter)
         │ 2. Run final tests (project-specific;
         │    example Memo: `npm run test:all`)
         │ 3. Present 4 options:
         │
         ▼  [G7: USER CHOOSES]
         │
    ┌──────┴───────────────────────────────────────────────────┐
    │                                                           │
    ▼            ▼              ▼                   ▼           ▼
┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Option 1│ │ Option 2 │ │ Option 3 │ │ Option 4 │
│ Merge  │ │ Push + PR│ │ Keep     │ │ Discard  │
│ locally│ │ (default)│ │ branch   │ │ (confirm)│
└────────┘ └──────────┘ └──────────┘ └──────────┘
```

> **Diagram note:** Commands shown as *example (Memo)* illustrate one reference stack (Next.js + vitest/playwright). Your project uses its own test commands in its adapter copy of agents/skills — not defined in this framework repo.

**After merge / polish:** the fast-track protocol (adapter skill: `fast-track-protocol` — the session manager dispatches implementers directly, lighter path).

## Role architecture

Theory roles and their contracts:

- **Session manager** — single entry point; owns the conversation, gates, scratchpad, board. The only role that talks to the user.
- **Controller** — phase executor; plans and delegates, **never implements code, never talks to the user**.
- **Implementers** — write code per task prompt; TDD required.
- **Compliance reviewer** (read-only) — code matches the task/plan.
- **Quality reviewer** (read-only + tests) — code is well-built and tests pass.
- **Investigator** — root-cause analysis on BLOCKED/bugs.
- **Test runner** — env prep and test suite runs (cheap model).
- **Scribe** — meta documentation (PLAN.md, CHANGELOG) after all tasks.
- **Deployer** — production deployment, on user request.

The org chart as wired in the current opencode adapter:

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
│ (implementer)    │  │  (implementer)   │  │ (investigator)  │
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

**Unsure which agent to dispatch?** The controller may use the adapter's find-specialist skill (not a gate).

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
1. **Screenshot capture** — captures key page states (mobile 390x844 by default, desktop optional)
2. **Element presence checks** — verifies DOM elements from the spec exist and are visible
3. **Report generation** — markdown report with pass/fail status and screenshot paths

### When to run G4.5 vs skip

| Situation | Step 4.5 |
|-----------|----------|
| Phase changes **user-visible UI** (pages, components, styles users see) | **Run** after all tasks in that phase — once per phase, not per task |
| Design spec has **`## Visual Compliance Checks`** with real checklist items | **Run** — the check reads that section |
| Phase is **backend/API/CLI/data only** — no UI surface in scope | **Skip** — go Step 4 → Step 5; do not run the check |
| Spec explicitly says **Visual Compliance N/A** (e.g. infra skill, no UI) | **Skip** — document in spec why N/A |
| **Mixed phase** (API + UI) | **Run** if any UI shipped; checks cover UI portion of spec |

**Controller rule of thumb:** if the spec never needed a Visual Compliance section and no `.tsx`/user-facing CSS was in the plan, skip 4.5. If UI was in scope, the spec should have included checks; a missing section on a UI feature is a spec gap — add checks or ask the user before skipping.

**Per-task vs phase:** implementers may run narrower visual/unit tests **per task** when UI files change. **G4.5** is the **phase-level** gate with the visual compliance tooling and the design spec file — one run before documentation (Step 5).

**Spec integration (UI features):** design specs include a `## Visual Compliance Checks` section:

```markdown
## Visual Compliance Checks
- [ ] "Сегодня" tab is visible and clickable on main page
- [ ] "Завтра" tab switches view to tomorrow's schedule
- [ ] "Календарь" tab opens date picker overlay
- [ ] Filter pills are visible below the tabs
- [ ] Clicking a filter pill highlights it and filters the list
```

**Execution (adapter + example project — Memo, Next.js on :3000):**
```bash
<repo>/.opencode/scripts/visual-compliance-check.sh \
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
│ Session manager invokes fast-track         │
│ • Dispatches implementers directly         │
│   (no controller)                          │
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

Runtime: adapter skill `fast-track-protocol` + rules in the controller's agent definition.

## Board during IMPL

The board is the project's state visualizer, not a context carrier; the session manager's flips keep it truthful.

`In IMPL` (at dispatch) → `PR (G7)` (at finishing) → `In-main` (after merge; if the issue was Next up 1 → `shift`), then the board script's `merged` command (`gh_board.py merged <issue> <pr> "<short title>"`) appends the `## Recently merged` scratchpad line (v2) and the session manager removes its session section. Flips belong to the session manager. The board script ships with the adapters.

## Return path (spec/plan invalid → back to DESIGN)

A one-time bounce-back, not a live channel:

1. The controller reports BLOCKED because the spec or the plan itself is wrong (not an env or implementer issue) → the session manager presents it to the user.
2. **The user decides** to return the trajectory.
3. The session manager posts a GH issue comment describing the problem, then moves the card back to `In Design`: a broken spec restarts the design (Gate A); a broken plan additionally marks a pending plan decision on the card — the next DESIGN session resumes at Gate C.
4. Worktree/branch keep-vs-discard is the user's call.
5. Scratchpad (v2): the section is removed if the worktree/branch is discarded; if it was kept, the section stays while that worktree lives. The durable record of the return is the issue comment + board status.

The next DESIGN session picks the issue up from the board with the issue comment as input — see [design-phase.md](design-phase.md).

## Gates summary

```
G3 ─── Clean Baseline ────────── Auto ─── Baseline green: CI fact-check of latest merged PR, or local suite
G4 ─── TDD Compliance ────────── Auto ─── Implementer self-check
G4a ── Controller Spot-Check ─── Auto ─── Diff ≤5 lines (trivial only)
G4.5 ─ Visual Compliance ─────── Auto ─── UI phases only; skip if no UI
G5 ─── Code Compliance ───────── Auto ─── Code matches plan (compliance reviewer)
G6 ─── Code Quality + Tests ──── Auto ─── Clean code, tests pass
G6a ── Review Loop Limit ─────── Auto ─── Max 3 iterations → escalate
G6b ── Controller Never Implem.─ Auto ─── Controller did not edit code
G7 ─── Final Tests + Choice ──── Human ── Merge/PR/Keep/Discard
```

## Key principles (IMPL)

1. **Manager Owns Conversation** — the session manager is the single entry point; the controller never talks to the user
2. **Controller Never Implements** — the controller plans and delegates, never edits code
3. **Two-Stage Review** — code compliance → code quality, never one without the other
4. **Sequential Tasks** — one implementer at a time, no parallel dispatch
5. **Circuit Breaker** — max 3 review loops per reviewer, then escalate
6. **Hybrid Diff Review** — the controller reads `--stat` only, passes the file path to reviewers (saves ~30-40% tokens)
7. **TDD Required** — RED-GREEN-REFACTOR for every implementation task
8. **Env Work Delegated** — env prep and e2e/full-suite test runs go to the test runner (cheap model)
9. **No Temporary Tool Installation** — all tools in the runtime image, never in worktree
10. **Scratchpad v2** — DESIGN writes nothing; the session manager's section lives while the worktree exists; finishing = board flip + `merged` line (`## Recently merged`, max 5) + section removal; the adapter's sanitize command audits legacy files

> **opencode adapter note:** restart the container runtime after any change to its agent/skill files (`.opencode/agents/*.md`, `.opencode/skills/**/SKILL.md`).
