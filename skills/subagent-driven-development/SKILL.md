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

1. Read plan, extract all tasks with full text, note context, create TodoWrite
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
