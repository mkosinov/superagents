---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

# Subagent-Driven Development

Execute plan by dispatching fresh subagent per task, with two-stage review after each: spec compliance review first, then code quality review.

**Why subagents:** You delegate tasks to specialized agents with isolated context. By precisely crafting their instructions and context, you ensure they stay focused and succeed at their task. They should never inherit your session's context or history — you construct exactly what they need. This also preserves your own context for coordination work.

**Core principle:** Fresh subagent per task + two-stage review (spec then quality) = high quality, fast iteration

**Continuous execution:** Do not pause to check in with your human partner between tasks. Execute all tasks from the plan without stopping. The only reasons to stop are: BLOCKED status you cannot resolve, ambiguity that genuinely prevents progress, or all tasks complete. "Should I continue?" prompts and progress summaries waste their time — they asked you to execute the plan, so execute it.

## When to Use

Use when you have a written implementation plan with independent tasks, and you are staying in this session (not parallel session).

**vs. Executing Plans (parallel session):**
- Same session (no context switch)
- Fresh subagent per task (no context pollution)
- Two-stage review after each task: spec compliance first, then code quality
- Faster iteration (no human-in-loop between tasks)

## The Process

1. Read the plan ONCE and extract all tasks with full text + classification into session notes;
   create TodoWrite as the live tracker. Never re-read the plan file during the phase — a plan is
   20K+ tokens; per-task text stays in your notes, TodoWrite tracks progress (Doc Working
   Discipline).
2. For each task:
   a. **Dispatch implementer subagent** with full task text + context
   b. Implementer implements, tests, commits, self-reviews
   c. **Dispatch spec reviewer subagent** — MUST include `## Working Directory` in prompt
   d. If ❌ → implementer fixes → re-dispatch spec reviewer (max 3 loops)
   e. Only if spec ✅ → **dispatch code quality reviewer subagent** — MUST include `## Working Directory` in prompt
   f. If ❌ → implementer fixes → re-dispatch quality reviewer (max 3 loops)
    g. If ✅ → mark task complete in TodoWrite

## Bug Fix Two-Gate Protocol

When dispatching a **bug fix** (not a feature/plan task), use a TWO-GATE sub-process:

### Gate 1: RED Test (reproduce the bug)
1. Dispatch implementer with ONLY the task to write a failing test that reproduces the bug
2. The test must be `test.skip` or clearly marked as reproducing the exact bug scenario
3. **Review Gate:** You (architect) review the test BEFORE accepting it:
   - Does it match the bug description?
   - Does it represent real data conditions?
   - Does it fail with the expected error/message?
   - Could it pass for the wrong reasons?
4. Only when the test accurately reproduces the bug → mark Gate 1 ✅

### Gate 2: GREEN (fix the code)
1. Dispatch implementer again with the task to make the RED test GREEN
2. Implementer fixes production code — test must pass
3. Implementer also ensures all existing tests still pass
4. **Review Gate:** Standard review applies (spec + quality for standard/large tasks)

### Rules
- Do NOT skip Gate 1 — no "I know what the fix is, let me just do it"
- Do NOT let implementer write fix + test in one dispatch
- Architect reviews the test file only (read it), does NOT run it
- Test must be new and specific to the bug, not an existing test
- If the bug is complex, split into sub-bugs and repeat the protocol

**Visual Regression Testing:**
- If task touches UI (.tsx, .css, tailwind.config.ts, next.config.mjs):
  - Implementer runs `cd frontend && npm run test:all` before marking DONE
  - Code-quality reviewer runs `cd frontend && npm run test:all` and reports visual diff results
- If task is logic-only (hooks, utils, types):
  - Implementer runs `cd frontend && npm run test` (vitest only)
  - Code-quality reviewer runs `cd frontend && npm run test`

**Env-dependent test runs (e2e, full-suite, visual) → @tester:**
- Any test run that needs the running environment (servers up, ports free, DB seeded) is delegated to the `tester` agent (cheap model). It prepares the env once per phase (leaves it running), runs the suite, and returns a compact `## Test Results` report.
- Implementers and reviewers dispatch `tester` for such runs instead of doing env forensics themselves (port checks, health loops, stale-PID hunts, sleeps) — that work burns expensive context and was the #1 token waster in e2e tasks.

3. After all tasks: dispatch final code reviewer for entire implementation

4. **Visual Compliance Gate (ONCE per phase, NOT per task)**
   - Trigger: All tasks in this phase complete, all reviews passed
   - Run `/root/workspace/superagents/scripts/visual-compliance-check.sh <dev-url> <spec-file>`
   - If FAILS → soft block: report to user with screenshots, wait for decision (fix/override/abort)
   - Only proceed to Step 5 (documentation) after pass or explicit user override

5. Use finishing-a-development-branch skill to complete

## Critical: Working Directory

**ALWAYS substitute the real worktree path.** The template placeholder `feat-<name>` must be replaced with the actual branch name (e.g., `feat-admin-polish`). If you send the placeholder, the subagent will write to `main/` instead of the branch.

**Architect MUST verify before dispatch:**
```bash
# Check that worktree exists and path is correct
ls /root/workspace/memo/.worktrees/<actual-branch-name>/
```

**Always pass `## Working Directory` to ALL subagents** (implementer AND reviewers):

```
## Working Directory
{ABSOLUTE_PATH_TO_WORKTREE}
```

Reviewers need this to:
- Read files from disk with the Read tool (not just the git diff)
- Run tests: `cd frontend && npx vitest run` (they'll use `workdir=` parameter in bash)

## Critical: Vitest Pool Compatibility

If vitest hangs in subagent environments (worker_threads timeout), ensure `vitest.config.ts` uses fork pool:

```ts
test: {
  pool: 'forks',
  // ...
}
```

This must be set BEFORE dispatching subagents that run tests. Vitest 4.x defaults to `worker_threads` which may not initialize in sandboxed subagent environments.

## Model Selection

Use the least powerful model that can handle each role to conserve cost and increase speed.

- Mechanical implementation tasks (isolated functions, clear specs, 1-2 files): fast, cheap model
- Integration and judgment tasks (multi-file coordination, pattern matching, debugging): standard model
- Architecture, design, and review tasks: most capable available model

## Handling Implementer Status

**DONE:** Proceed to spec compliance review.

**DONE_WITH_CONCERNS:** Read concerns. If correctness/scope → address before review. If observations → note and proceed.

**NEEDS_CONTEXT:** Provide missing context and re-dispatch.

**BLOCKED:** Assess:
1. Context problem → re-dispatch with same model
2. Needs more reasoning → re-dispatch with more capable model
3. Task too large → break into smaller pieces
4. Plan wrong → escalate to human

**Never** ignore an escalation or force the same model to retry without changes.

## Dead-Subagent Recovery

When a dispatched subagent **dies without returning a usable report** (crash, context exhausted,
an EMPTY task_result, or an unusable/no-op response) AND its task_id is known, follow this
ordered recovery. Do NOT immediately re-dispatch a fresh task — you may discard a thousand lines
of correct work that the dead subagent already produced.

### Step 0: Empty/no-op result → DB audit first (zero token cost)

An empty task_result does NOT mean "no work". Subagents often complete real work (reads, edits,
commits, test runs) yet the final report text never materializes. Before re-dispatching or even
resuming, read the session's actual state from the DB — this costs 0 tokens:

    python3 .opencode/scripts/subagent-audit.py <session_id>

(script: `superagents/scripts/subagent-audit.py`, canonical; synced to each project's
`.opencode/scripts/`. Opens `~/.local/share/opencode/opencode.db` read-only — safe while opencode
is running.) The digest tells you which branch to take:

- **final assistant text present** (delivery/transport bug only) → use that text as the report and
  proceed to the normal review. 0 extra tokens.
- **git commits / test results in DB, no final text** → work was done: resume (Step 1, cheap) or
  audit-verify-commit (Step 3). Never a fresh redo of committed work.
- **worked but no final report** (tool calls ran, no final text) → resume the same session to
  finish and report (Step 1) — resuming is ~1 cheap turn.
- **no work at all** (no tool calls, only the prompt) → fresh re-dispatch is fine.

Applies to ALL roles — coders, reviewers, testers, explore, docser, panelists. The recoverable
artifact differs by role (coder → commits/tests; reviewer → final text; tester → pty/test
verdict), but the ladder is the same.

### Step 1: Resume the dead session (cheapest — try this FIRST)

Resume the known `task_id` and ask it to report status and finish the task. A resume is far
cheaper than a redo, and often the subagent already did the work — it just couldn't deliver the
report. Pass a brief reminder of the original task and "report your status and finish."

If the resume returns a usable report → proceed to the normal two-stage review (spec, then
quality). Done.

### Step 2: If resume fails — audit the worktree for partial work

If the resume is unusable (context exhausted, inadequate response, session cannot continue),
DO NOT re-dispatch a full redo yet. First inspect the worktree for partial changes left behind
by the dead subagent:

```bash
cd <worktree>
git status
git diff                      # uncommitted changes
git log origin/<base>..HEAD   # committed but unpushed work
```

### Step 3: Salvage or redo

- **Partial changes look sound** (compile/test or a quick read shows a correct direction) →
  dispatch a **fresh audit-verify-commit** task (NOT a full re-implementation): have a new
  subagent review the existing diff, verify correctness (run tests), fix any gaps, and commit.
  This salvages the dead subagent's work instead of redoing it.
- **No useful work, or changes are broken** → re-dispatch the task fresh (full re-implementation).

### Motivation

Real incident (GH #185): a dead backend-coder had already produced ~1000 lines of correct
edits. A `git status` / `git diff` audit revealed the work was sound, and a fresh
audit-verify-commit task salvaged it — saving a full rework. But a **resume attempt would have
been even cheaper** and was skipped; that is why resume is Step 1, not the audit.

## Red Flags

**Never:**
- Start implementation on main/master branch without explicit user consent
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed issues
- Dispatch multiple implementation subagents in parallel (conflicts)
- Make subagent read plan file (provide full text instead)
- Skip scene-setting context
- Ignore subagent questions
- Accept "close enough" on spec compliance
- Skip review loops
- Let implementer self-review replace actual review
- **Start code quality review before spec compliance is ✅** (wrong order)
- Move to next task while either review has open issues

## Integration

**Required workflow skills:**
- **using-git-worktrees** - Ensures isolated workspace
- **writing-plans** - Creates the plan this skill executes
- **finishing-a-development-branch** - Complete development after all tasks

**Subagents should use:**
- **test-driven-development** - Subagents follow TDD for each task
