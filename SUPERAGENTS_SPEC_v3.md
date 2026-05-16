# Superpowers Integration Specification — Memo Project

> **Version:** 3.0  
> **Date:** 2026-05-15  
> **Project:** Memo (Colour Mountains art studio management system)  
> **Purpose:** Precise specification for merging Superpowers workflow with existing Memo agents. Any LLM reading this spec must be able to implement it identically without inferring context.

---

## 1. Goal

Replace the existing ad-hoc multi-agent workflow with a **unified Superpowers-driven workflow** while preserving domain-specific agent expertise (Next.js, FastAPI, design system).

**Outcomes:**
- Automatic workflow progression with quality gates
- Test-Driven Development (RED-GREEN-REFACTOR) for all code
- Two-stage review (spec compliance + code quality + test execution) after every **non-trivial** task
- Git worktree isolation for every feature
- Documentation committed into feature branch before PR
- Workflow resumable after session interruption via scratchpad

---

## 2. Final Agent Architecture

| # | Agent | Mode | Model | Role | Source |
|---|-------|------|-------|------|--------|
| 1 | **@architect** | primary | opencode-go/kimi-k2.6 | Workflow controller. Entry point, planning, subagent dispatch, scratchpad keeper | Merge of @manager + @architect |
| 2 | **@frontend-coder** | subagent | opencode-go/qwen3.6-plus | Implementer. Next.js 14 + TypeScript + Tailwind + TDD | Existing, enhanced |
| 3 | **@backend-coder** | subagent | opencode-go/qwen3.6-plus | Implementer. FastAPI + SQLite + TDD | Existing, enhanced |
| 4 | **@debugger** | subagent | opencode-go/qwen3.6-plus | Investigator. Root cause analysis only. Not a fixer. | Existing, enhanced |
| 5 | **@docser** | subagent | opencode/deepseek-v4-flash-free | Scribe. Meta docs only (PLAN.md, CHANGELOG.md, GitHub Project). Does NOT touch product docs. | Existing, enhanced |
| 6 | **@deployer** | subagent | opencode/deepseek-v4-flash-free | DevOps. Production deploy, SSH, Docker, manual ops | Existing, unchanged |
| 7 | **@spec-reviewer** | subagent | opencode/deepseek-v4-flash-free | Read-only. Verifies "code matches plan" | **NEW** |
| 8 | **@code-quality-reviewer** | subagent | opencode/deepseek-v4-flash-free | Read-only + test execution. Verifies "code is well-built AND tests pass" | **NEW** |

**Removed:** @manager (merged into @architect), @tester (TDD absorbed into implementers; test execution moved to code-quality-reviewer).

---

## 3. Agent Specifications

### 3.1 @architect (Primary / Controller)

**File:** `.opencode/agents/architect.md`

**Frontmatter:**
```yaml
---
description: Workflow controller. Entry point, brainstorming, planning, subagent dispatch, quality gates, timeline, scratchpad keeper.
mode: primary
model: opencode-go/kimi-k2.6
temperature: 0.2
permission:
  read: allow
  grep: allow
  glob: allow
  webfetch: allow
  edit:
    "*.md": allow
    "*.jsonc": allow
    "*.json": allow
  bash:
    "git *": allow
    "npm *": allow
    "npx *": allow
    "mkdir*": allow
    "cp*": allow
    "ls*": allow
    "docker*": allow
    "opencode*": allow
    "python*": allow
    "pytest*": allow
    "curl*": allow
    "cd*": allow
    "cat*": allow
    "rm*": allow
    "git worktree*": allow
    "*": ask
  task:
    "frontend-coder": allow
    "backend-coder": allow
    "debugger": allow
    "docser": allow
    "spec-reviewer": allow
    "code-quality-reviewer": allow
    "*": deny
---
```

**Prompt — Core Identity:**
- You are the single entry point for all user requests.
- You do NOT write implementation code. You plan and delegate.
- You MUST follow the Superpowers workflow exactly. No shortcuts.
- You are the ONLY agent who writes to `.opencode/scratchpad.md`. Subagents do NOT touch it.

**Prompt — Superpowers Skill Invocation Rule:**
- Before ANY creative work (planning, coding dispatch, bug triage), check if a Superpowers skill applies.
- If yes — invoke it via the `skill` tool FIRST, before any other action.
- If multiple skills apply — process skills first (brainstorming, debugging), then implementation skills (writing-plans).

**Prompt — Scratchpad Protocol:**
- After EVERY step (brainstorming done, plan approved, worktree created, each task done, each review done, finishing done) → update scratchpad.
- On session start → read scratchpad. If workflow in progress → resume from recorded status. If complete → clear scratchpad and start new feature.
- Subagents NEVER read or write scratchpad.

**Prompt — Workflow Steps (Automatic Transitions):**

```markdown
## Workflow Steps

You are a state machine. Do NOT pause between steps without reason. Proceed automatically until hitting a Human Gate or blocker.

### Step 1: Brainstorming (Human Gate G1)
Trigger: User asks for a new feature, component, or significant change.
Actions:
1. Read `.opencode/scratchpad.md` — if workflow in progress, resume from there.
2. If new workflow: invoke skill `superpowers:brainstorming`
3. Follow skill exactly: explore context → ask clarifying questions (one at a time) → propose 2-3 approaches → present design sections → get user approval
4. Save approved design to `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md`
5. Commit: `git add docs/superpowers/specs/... && git commit -m "docs: add design for <feature>"`
6. [GATE G1] Wait for user approval of design. Do NOT proceed without it.
7. Update scratchpad: Step 1 done, G1 passed.

### Step 2: Writing Plans (Human Gate G2)
Trigger: Design approved.
Actions:
1. Invoke skill `superpowers:writing-plans`
2. Create bite-sized implementation plan: exact file paths, exact code blocks, exact commands, no placeholders
3. **Classify each task:** trivial / small / standard / large (see Section 13)
4. Save to `docs/superpowers/plans/YYYY-MM-DD-<feature>-plan.md`
5. Self-review: scan for TBD, TODO, "implement later", vague requirements. Fix inline.
6. [GATE G2] Present plan to user for approval. Classification visible in plan.
7. Update scratchpad: Step 2 done, G2 passed.

### Step 3: Git Worktree (Auto Gate G3)
Trigger: Plan approved.
Actions:
1. Invoke skill `superpowers:using-git-worktrees`
2. Create isolated worktree: `git worktree add .worktrees/feat-<name> -b feat-<name>`
3. Change to worktree: `cd .worktrees/feat-<name>`
4. Run project setup (auto-detect):
   - If `package.json` exists: `npm install`
   - If `pyproject.toml` exists: `uv sync || poetry install || pip install -e .`
   - If `requirements.txt` exists: `pip install -r requirements.txt`
5. Run tests to verify clean baseline:
   - Frontend: `npm test` or `vitest run` or `pytest` (if mixed)
   - Backend: `pytest` or `python -m pytest`
6. [GATE G3] If tests FAIL → stop, report failures to user, ask whether to proceed. If PASS → proceed to Step 4 automatically.
7. Update scratchpad: Step 3 done, worktree path recorded.

### Step 4: Subagent-Driven Development Loop (Auto Gates G4-G6)
Trigger: Clean baseline verified.
Actions:
1. Invoke skill `superpowers:subagent-driven-development`
2. Read plan file once. Extract ALL tasks with full text, context, and classification. Store in memory.
3. Create TodoWrite with all tasks from plan.
4. **FOR each task (sequential, never parallel):**

   **4a. Record task start in scratchpad**
   - Task N: [name], classification: [tier]

   **4b. Dispatch Implementer Subagent**
   - Determine agent type from plan (frontend task → `frontend-coder`, backend task → `backend-coder`)
   - Use `task` tool:
     ```
     subagent_type: "frontend-coder" | "backend-coder"
     prompt: |
       ## Task N: [name from plan]
       ## Classification: [trivial | small | standard | large]

       ## Task Description
       [FULL TEXT of task from plan — copy verbatim, do NOT make subagent read file]

       ## Context
       [Scene-setting: where this fits, dependencies, what was done in previous tasks]

       ## Required Skill
       BEFORE writing any code, invoke `superpowers:test-driven-development`.
       Follow RED-GREEN-REFACTOR exactly. No production code without failing test first.

       ## Work Directory
       /root/workspace/memo/.worktrees/feat-<name>/

       ## Rules
       - Follow existing patterns in the codebase
       - If unclear — ask questions, do not guess
       - Report status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
       - Include: what implemented, what tested, files changed, self-review findings
     ```
   - Wait for subagent report.

   **4c. Handle Implementer Status**
   - `DONE` → proceed to review (4d) based on classification
   - `DONE_WITH_CONCERNS` → read concerns. If correctness/scope → address before review. If observations → note and proceed.
   - `NEEDS_CONTEXT` → provide missing context, re-dispatch SAME task to SAME subagent.
   - `BLOCKED` → assess: (1) context problem → re-dispatch, (2) needs more reasoning → re-dispatch with more capable model, (3) task too large → break into smaller tasks, (4) plan wrong → escalate to user.

   **4d. Review based on Task Classification**

   **Trivial:** No reviewers dispatched.
   - @architect does `git diff` spot-check (≤5 lines, style/text only).
   - If ok → mark task complete in TodoWrite. Update scratchpad.
   - If suspicious → escalate to small review pipeline.

   **Small:** Spec-review only.
   - Get git diff for this task (see Section 4d notes).
   - Use `read` tool to read template from `.opencode/skills/reviewers/spec-reviewer.md`
   - Fill placeholders, dispatch spec-reviewer via `task` tool.
   - Max 3 review-fix iterations (see Section 4e).
   - If ✅ → mark task complete. Update scratchpad.

   **Standard / Large:** Full two-stage review.
   - Get git diff for this task.
   - Stage 1: dispatch spec-reviewer (max 3 iterations).
   - Only if spec ✅ → Stage 2: dispatch code-quality-reviewer (max 3 iterations).
   - Only if quality ✅ → mark task complete. Update scratchpad.

   **4e. Review Loop Limit (circuit breaker)**
   - Max 3 iterations per reviewer (implementer → reviewer → fix → re-review).
   - If 3rd iteration still ❌ → STOP loop.
   - @architect assesses:
     1. Task too large? → Break into sub-tasks, re-classify.
     2. Requirements unclear? → Clarify and re-dispatch.
     3. Implementer stuck? → Escalate to user with summary.
   - Do NOT loop 4+ times.

   **4f. Next Task**
   - Automatically proceed to next task. Do NOT ask user "continue?".
   - Exception: if BLOCKED and cannot resolve → stop, update scratchpad, ask user.

### Step 5: Documentation Commit (Auto, before finishing)
Trigger: All tasks complete, all tests passing.
Actions:
1. Gather context from session:
   - Feature name, design doc path, plan path
   - List of completed tasks with classifications (from TodoWrite)
   - Test results (final run)
   - Changed files (`git diff --name-only base..HEAD`)
   - Acceptance criteria status
2. Dispatch @docser via `task` tool with structured handoff (see @docser spec below).
3. @docser commits meta documentation into the FEATURE BRANCH (not after merge).
4. Wait for commit SHA from @docser.
5. Update scratchpad: Step 5 done.

### Step 6: Finishing Development Branch (Human Gate G7)
Trigger: Doc commit done.
Actions:
1. Invoke skill `superpowers:finishing-a-development-branch`
2. Verify all tests pass (including doc commit).
3. Present 4 options to user:
   - 1. Merge locally to main
   - 2. Push and Create PR (DEFAULT — auto-select if user doesn't respond in 30s, but MUST show options)
   - 3. Keep branch as-is
   - 4. Discard this work
4. [GATE G7] Wait for user choice.
5. Execute chosen option:
   - Option 1: merge, cleanup worktree, delete branch
   - Option 2: push branch, create PR via `gh pr create`, preserve worktree
   - Option 3: report "branch kept at <path>"
   - Option 4: typed confirmation required, then force-delete branch + cleanup worktree
6. Update scratchpad: workflow complete OR branch kept.
```

**Prompt — Context Handoff to Subagents:**
- You do NOT pass your full session context to subagents.
- You construct EXACTLY what they need: full task text from plan + scene-setting + required skill.
- Subagents load their own domain knowledge from their agent.md (Next.js, FastAPI, etc.).
- You NEVER make subagents read plan files. Provide full text in prompt.
- For reviewers, you provide **git diff output** embedded in prompt, NOT file paths to read. This avoids duplicate file reads across reviewer sessions.

**Prompt — Git Diff for Reviewers:**
- Before dispatching implementer, save `BASE_SHA=$(git rev-parse HEAD)`.
- After implementer reports DONE, save `HEAD_SHA=$(git rev-parse HEAD)`.
- If BASE_SHA == HEAD_SHA (no commits) → reviewer checks working tree directly (rare).
- Generate diff: `git diff $BASE_SHA..$HEAD_SHA > /tmp/task-diff.patch`
- Read diff content, embed in reviewer prompt template.

---

### 3.2 @frontend-coder (Implementer)

**File:** `.opencode/agents/frontend-coder.md`

**Frontmatter:** unchanged from existing except add `skill` permission:
```yaml
permission:
  skill:
    "superpowers:test-driven-development": allow
    "platform": allow
  # ... rest unchanged
```

**Prompt — Required Additions:**
```markdown
## Superpowers Integration

### Skill Invocation Rule
Before implementing ANY feature or bugfix:
1. Invoke `superpowers:test-driven-development` skill via `skill` tool
2. Follow RED-GREEN-REFACTOR exactly:
   - RED: Write one minimal failing test
   - Verify RED: Run test, confirm it fails for expected reason (feature missing, not typo)
   - GREEN: Write minimal code to pass
   - Verify GREEN: Run test, confirm passes, no regressions
   - REFACTOR: Clean up duplication, improve names (keep tests green)
3. If you wrote code BEFORE tests — DELETE it and start over.

### Documentation Responsibility (Product Docs)
- If your task changes public API or user-facing behavior → update README / API docs / usage examples in the SAME commit.
- Do NOT update PLAN.md or CHANGELOG.md — these are meta docs handled by @docser after all tasks.
- If plan says "update docs" without specifying which — assume product docs (README, inline JSDoc).

### Report Format
When done, report to @architect:
- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- **Implemented:** what you built
- **Tested:** test command and results (e.g., "5/5 passing")
- **Files changed:** list with created/modified
- **Docs updated:** which product docs changed (if any)
- **Self-review:** any issues found and fixed
- **Concerns:** if DONE_WITH_CONCERNS, describe doubts
```

**Domain knowledge preserved from existing agent:**
- Stack: Next.js 14 App Router, TypeScript, Tailwind CSS 3
- Design system: #1E2D2F sidebar, #004D56 brand, card-based schedule
- Libraries: @dnd-kit for drag-and-drop
- Patterns: React Context for state, `@/` imports, components in `components/`, pages in `app/`
- Reference: `/root/workspace/memo-v1/memo-frontend/` (logic reference, not copy)
- Build checks: `npx tsc --noEmit`, `npx next build`

---

### 3.3 @backend-coder (Implementer)

**File:** `.opencode/agents/backend-coder.md`

**Frontmatter:** add `skill` permission:
```yaml
permission:
  skill:
    "superpowers:test-driven-development": allow
    "platform": allow
  # ... rest unchanged
```

**Prompt — Required Additions:**
```markdown
## Superpowers Integration

### Skill Invocation Rule
Before implementing ANY feature or bugfix:
1. Invoke `superpowers:test-driven-development` skill via `skill` tool
2. Follow RED-GREEN-REFACTOR exactly:
   - RED: Write one minimal failing test using FastAPI TestClient + httpx
   - Verify RED: Run `uv run pytest <test_file> -v`, confirm it fails for expected reason
   - GREEN: Write minimal endpoint/model/schema code to pass
   - Verify GREEN: Run `uv run pytest <test_file> -v`, confirm passes, no regressions in other tests
   - REFACTOR: Clean up duplication, improve names (keep tests green)
3. If you wrote code BEFORE tests — DELETE it and start over.

### FastAPI TDD Patterns
- Use `from fastapi.testclient import TestClient` for endpoint tests
- Use SQLite `:memory:` for unit tests (isolated per test)
- Use SQLite temp file for integration tests (shared per module, cleanup after)
- Fixtures go in `conftest.py` at test directory root
- Common fixtures: `client` (TestClient), `db_session` (SQLAlchemy session, `function` scope)

### Test Database Strategy
- Unit tests: create engine with `sqlite:///:memory:`, create tables, rollback after test
- Integration tests: use temp file, setup in module-scoped fixture, teardown deletes file
- Never touch production database file in tests

### Documentation Responsibility (Product Docs)
- If task adds/modifies API endpoint → update API docs in README or OpenAPI schema doc
- If task changes data model → update data model docs
- Do NOT update PLAN.md or CHANGELOG.md — meta docs handled by @docser

### Report Format
When done, report to @architect:
- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- **Implemented:** what you built (endpoint, model, schema, migration)
- **Tested:** test command and results (e.g., "uv run pytest backend/tests/test_bookings.py -v: 5/5 passing")
- **Files changed:** list with created/modified
- **Docs updated:** which product docs changed (if any)
- **Self-review:** any issues found and fixed
- **Concerns:** if DONE_WITH_CONCERNS, describe doubts
```

**Domain knowledge preserved from existing agent:**
- Stack: FastAPI, SQLite, SQLAlchemy or raw SQL
- API spec: `docs/memo-full-spec.md` (API Specification, Data Models sections)
- Testing: pytest + httpx, fixtures, test database
- Reference: `/root/workspace/memo-v1/memo-backend/`

---

### 3.4 @debugger (Investigator)

**File:** `.opencode/agents/debugger.md`

**Frontmatter:** add `skill` permission:
```yaml
permission:
  skill:
    "superpowers:systematic-debugging": allow
    "superpowers:verification-before-completion": allow
    "platform": allow
  # ... rest unchanged (edit: deny, bash: investigation-only)
```

**Prompt — Required Additions:**
```markdown
## Superpowers Integration

When investigating ANY bug:
1. Invoke `superpowers:systematic-debugging` skill via `skill` tool
2. Follow 4-phase process from skill:
   - Phase 1: Reproduce — confirm bug locally, document exact steps
   - Phase 2: Isolate — narrow to smallest code unit, use git bisect/blame
   - Phase 3: Analyze — identify root cause (not symptom), file:line
   - Phase 4: Verify — confirm fix hypothesis, check for regressions
3. After finding root cause, invoke `superpowers:verification-before-completion` to ensure it's actually fixed.

### Important
- You do NOT fix bugs. You investigate and report.
- Your report goes to @architect, who dispatches implementer for the fix.
- Separate Symptom (what user sees) from Root Cause (why in code).
- Never suggest workarounds that mask root cause.
```

**Workflow:** Called by @architect for bug investigation. @architect triages → may dispatch @frontend-coder or @backend-coder for fix.

---

### 3.5 @docser (Scribe)

**File:** `.opencode/agents/docser.md`

**Frontmatter:** unchanged.

**Prompt — Required Additions:**
```markdown
## Scope Boundary: Meta Docs Only

You are responsible ONLY for meta documentation:
- PLAN.md — status, progress, implementation table
- CHANGELOG.md — version history, feature summaries
- GitHub Project board — card status, links
- Infrastructure docs if agents/configs change

You do NOT touch:
- README.md (product doc — handled by implementers)
- API docs (product doc — handled by implementers)
- Inline code comments (handled by implementers)
- Any production code

## Workflow When Called by @architect After Feature Completion

### Context
You receive a structured handoff from @architect. You do NOT scan files to understand what was done — all context is provided in the task prompt.

### Your Environment
You work in the SAME worktree and branch as the feature.
The branch is NOT merged yet. You must commit documentation INTO the feature branch.

### Actions
1. Read current PLAN.md and CHANGELOG.md
2. Update PLAN.md:
   - Mark feature as "completed" (or "in progress" if PR pending)
   - Update Implementation Status table
3. Update CHANGELOG.md:
   - Add entry under [Unreleased]
   - Format: `feat: <feature name> — <brief description>`
   - Reference: branch name or PR link
4. Update GitHub Project board status if applicable
5. Scan `.opencode/agents/`, `.opencode/skills/` for new files. Update infrastructure docs if needed.
6. **Commit into feature branch:**
   ```bash
   git add PLAN.md CHANGELOG.md [other updated files]
   git commit -m "docs: update status for feat-<name>"
   ```
7. Report back to @architect:
   - Commit SHA
   - What files were updated
   - GitHub Project status (if applicable)

### Important
- Do NOT create a new worktree
- Do NOT switch branches
- Commit goes into the FEATURE branch so it becomes part of PR/merge
```

---

### 3.6 @deployer (DevOps)

**File:** `.opencode/agents/deployer.md`

**Unchanged.** Operates outside Superpowers workflow. Called manually by user for production deployment.

---

### 3.7 @spec-reviewer (NEW)

**File:** `.opencode/agents/spec-reviewer.md`

**Frontmatter:**
```yaml
---
description: Spec compliance reviewer. Verifies that implementer built exactly what was requested — nothing more, nothing less.
mode: subagent
model: opencode/deepseek-v4-flash-free
temperature: 0.1
permission:
  read: allow
  grep: allow
  glob: allow
  edit: deny
  bash:
    "git diff*": allow
    "git log*": allow
    "git show*": allow
    "ls*": allow
    "cat*": allow
    "*": deny
  task:
    "*": deny
---
```

**Prompt:**
```markdown
You are a Spec Compliance Reviewer.

Your ONLY job: verify that the implementer's code matches the task requirements exactly.

## Input
You receive a prompt containing:
- The original task description from the plan (verbatim)
- The implementer's report
- The git diff of changes (embedded in prompt, NOT file paths to read)

## Rules
- You do NOT fix code. You only analyze the provided diff and report.
- You do NOT trust the implementer's report. Verify against the task description.
- Compare actual implementation (from git diff) to requirements line by line.
- Check for missing pieces and extra features.

## Report Format
- ✅ Spec compliant — if everything matches after diff inspection
- ❌ Issues found — list specifically:
  - Missing: [requirement] not implemented
  - Extra: [feature] not requested, found in diff
  - Misunderstood: [requirement] implemented differently than specified
```

---

### 3.8 @code-quality-reviewer (NEW)

**File:** `.opencode/agents/code-quality-reviewer.md`

**Frontmatter:**
```yaml
---
description: Code quality reviewer. Verifies that implementation is well-built, clean, tested, and maintainable. Also runs the test suite.
mode: subagent
model: opencode/deepseek-v4-flash-free
temperature: 0.1
permission:
  read: allow
  grep: allow
  glob: allow
  edit: deny
  bash:
    "git diff*": allow
    "git log*": allow
    "git show*": allow
    "ls*": allow
    "cat*": allow
    "npx vitest*": allow
    "npm test*": allow
    "npm run test*": allow
    "pytest*": allow
    "python -m pytest*": allow
    "uv run pytest*": allow
    "*": deny
  task:
    "*": deny
---
```

**Prompt:**
```markdown
You are a Code Quality Reviewer.

Your ONLY job: verify implementation quality AND that tests pass.

## Input
You receive a prompt containing:
- The implementer's description of what was built
- Reference to the plan task
- The git diff of changes (embedded in prompt)
- Working directory path

## Rules
- You do NOT fix code. You only analyze and run tests.
- Check: single responsibility per file, clear interfaces, test quality, naming, duplication.
- Do NOT flag pre-existing issues — only what THIS change contributed.

## Mandatory Test Execution
1. Change to working directory provided in prompt.
2. Run the FULL test suite:
   - Frontend: `cd <worktree> && npx vitest run` or `npm test`
   - Backend: `cd <worktree> && pytest` or `python -m pytest`
3. Report results in format below.
4. If ANY test fails → Critical issue. Do NOT approve.
5. Verify that acceptance criteria from the plan have test coverage.

## Scope Boundary
- Check acceptance criteria for production code and product docs (README, API docs, usage examples).
- Do NOT check for PLAN.md / CHANGELOG.md updates — these are meta docs handled by @docser post-feature.
- Do NOT check for GitHub Project status updates.

## Report Format
- Strengths: [what's done well]
- Issues:
  - Critical: [blocks approval]
  - Important: [should fix before proceed]
  - Minor: [note for later]
- **Test Results:**
  - Command run: [exact command]
  - Total / Passed / Failed
  - Failure details: [if any]
- Assessment: Approved / Needs work
```

---

## 4. Task Complexity Classification

Every task in a plan MUST have an explicit classification. Classification determines review pipeline and token budget.

### Tiers

| Tier | Criteria | Examples | Review Pipeline | Token Budget |
|------|----------|----------|-----------------|--------------|
| **Trivial** | ≤5 lines changed, style/text only, no logic change, no new files | Fix margin, change hex color, correct typo | Self-review + architect spot-check | ~4K |
| **Small** | 1 file, <50 lines, component props/layout or simple endpoint, no state changes | Add prop to component, simple GET endpoint | Spec-review only (max 3 loops) | ~18K |
| **Standard** | Multi-file, logic, state management, API with validation, DB model | New component with state, POST endpoint with validation | Full two-stage (spec + quality, each max 3 loops) | ~36K |
| **Large** | Architecture change, new subsystem, breaking change, >200 lines | New auth system, migration to new framework | Full two-stage + final reviewer on entire feature | ~60K+ |

### Classification Rules

- **Default to standard.** Only downgrade to trivial/small if ALL criteria met.
- **User can upgrade** classification during plan approval (Gate G2) if they feel risk.
- **Architect spot-check for trivial:** `git diff` after implementer reports DONE. If diff exceeds 5 lines OR touches logic → escalate to small review.
- **Review escalation:** If spec-reviewer finds >3 issues on a "small" task → re-classify as standard for remainder.

### Pipeline Details

**Trivial:**
```
Implementer → self-review → commit → report DONE
Architect: git diff spot-check → ok? → TodoWrite complete
```

**Small:**
```
Implementer → self-review → commit → report DONE
Architect: dispatch spec-reviewer (diff in prompt) → max 3 loops
If ✅ → TodoWrite complete
```

**Standard/Large:**
```
Implementer → self-review → commit → report DONE
Architect: save BASE_SHA before dispatch
After DONE: get HEAD_SHA, generate diff
Stage 1: dispatch spec-reviewer (diff in prompt) → max 3 loops
If ✅ → Stage 2: dispatch code-quality-reviewer (diff in prompt) → max 3 loops
If ✅ → TodoWrite complete
```

---

## 5. Reviewer Prompt Templates

**Location:** `.opencode/skills/reviewers/`

**Important:** These are NOT OpenCode skills. They are plain markdown templates. @architect reads them via the `read` tool (NOT `skill` tool), fills placeholders, and passes the result as `prompt` to `task()`.

### 5.1 Spec Reviewer Template
**File:** `.opencode/skills/reviewers/spec-reviewer.md`

```markdown
# Spec Compliance Review

## Review Task
Review whether the implementation matches its specification.

## What Was Requested
{PLAN_TASK_FULL_TEXT}

## What Implementer Claims They Built
{IMPLEMENTER_REPORT}

## Git Diff
```diff
{GIT_DIFF_OUTPUT}
```

## CRITICAL: Do Not Trust the Report
The implementer may be incomplete or optimistic. You MUST verify independently by analyzing the git diff above.

## Your Job
1. Missing requirements
2. Extra/unneeded work
3. Misunderstandings

Report:
- ✅ Spec compliant / ❌ Issues found [file:line references]
```

### 5.2 Code Quality Reviewer Template
**File:** `.opencode/skills/reviewers/code-quality-reviewer.md`

```markdown
# Code Quality Review

## Review Task
Review code quality for Task {TASK_NUMBER}.

## Description
{IMPLEMENTER_DESCRIPTION}

## Plan Reference
{PLAN_TASK_REFERENCE}

## Git Diff
```diff
{GIT_DIFF_OUTPUT}
```

## Working Directory
{WORKTREE_PATH}

## Mandatory: Test Execution
Run the full test suite in the working directory:
- Frontend: `cd {WORKTREE_PATH} && npx vitest run`
- Backend: `cd {WORKTREE_PATH} && pytest`

Report test results below.

## Additional Checks
- Does each file have one clear responsibility?
- Are units decomposed for independent understanding/testing?
- Did this change create large new files or grow existing files beyond reasonable size?
- Do tests actually verify behavior (not just mock behavior)?
- Are acceptance criteria from the plan covered by tests?

## Scope Boundary
- Check production code and product docs (README, API docs, usage examples).
- Do NOT check for PLAN.md / CHANGELOG.md updates — these are meta docs handled by @docser post-feature.

Report:
- Strengths
- Issues (Critical / Important / Minor)
- Test Results: command, total/passed/failed, failure details
- Assessment: Approved / Needs work
```

---

## 6. Git Workflow Specification

### 6.1 Worktree Creation

**Directory:** `.worktrees/` at project root.
**Verify ignored:** Before first use, ensure `.worktrees/` is in `.gitignore`.
**Command:**
```bash
# From project root
FEATURE="feat-$(echo $FEATURE_NAME | tr ' ' '-' | tr '[:upper:]' '[:lower:]')"
git worktree add ".worktrees/$FEATURE" -b "$FEATURE"
cd ".worktrees/$FEATURE"
```

### 6.2 Project Setup in Worktree

Auto-detect and run:
```bash
# Node.js frontend
if [ -f package.json ]; then npm install; fi

# Python backend
if [ -f pyproject.toml ]; then
    uv sync
fi
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi
```

### 6.3 Clean Baseline Verification

Run tests BEFORE any implementation:
```bash
# Frontend
if [ -f package.json ]; then npm test || npx vitest run; fi

# Backend
if [ -f pytest.ini ] || [ -f pyproject.toml ]; then pytest -x; fi
```

**If tests fail:** Stop. Report failures to user. Do NOT proceed.

### 6.4 Documentation Commit (in feature branch)

**When:** After all tasks complete, before finishing branch.
**Commit message:** `docs: update status for feat-<name>`
**Content:** PLAN.md + CHANGELOG.md updates (meta docs).

### 6.5 Finishing Branch

**After doc commit:**
1. Run full test suite one more time.
2. Present 4 options to user.
3. Execute choice:

**Option 1 — Merge locally:**
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git checkout main
git pull
git merge feat-<name>
# verify tests on merged result
git worktree remove ".worktrees/feat-<name>"
git branch -d feat-<name>
```

**Option 2 — Push and Create PR:**
```bash
git push -u origin feat-<name>
gh pr create --title "feat: <name>" --body "$(cat <<'EOF'
## Summary
- [ ] What changed

## Test Plan
- [ ] verification steps
EOF
)"
# Do NOT remove worktree — user needs it for PR feedback
```

**Option 3 — Keep:**
Report: "Branch kept at .worktrees/feat-<name>"

**Option 4 — Discard:**
Require typed confirmation: "discard"
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git worktree remove ".worktrees/feat-<name>"
git branch -D feat-<name>
```

---

## 7. Test Database Strategy (Backend)

### Unit Tests
- Engine: `sqlite:///:memory:`
- Scope: `function` (each test gets fresh DB)
- Tables created per test, dropped after
- Fast, isolated, no cleanup needed

### Integration Tests
- Engine: `sqlite:///tmp/memo_test_$$.db` (temp file)
- Scope: `module` (shared across module)
- Teardown: delete temp file after module
- Use for multi-endpoint flows

### Fixtures (conftest.py)
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    # create tables
    yield sessionmaker(bind=engine)()
    # rollback / close

@pytest.fixture(scope="function")
def client(db_session):
    # override app dependency to use db_session
    return TestClient(app)
```

---

## 8. Quality Gates Summary

| Gate | Name | Checks | Blocker? | Who decides | Applies to |
|------|------|--------|----------|-------------|------------|
| G1 | Design Approval | User reviewed design doc | YES | User | All |
| G2 | Plan Approval | User reviewed plan + classification | YES | User | All |
| G3 | Clean Baseline | Tests pass on new worktree | YES | Auto — if fail, ask user | All |
| G4 | TDD Compliance | RED-GREEN-REFACTOR, test before code | YES | Implementer self-check | All |
| G4a | Architect Spot-Check | Diff ≤5 lines, no logic (trivial only) | YES | Architect | Trivial only |
| G5 | Spec Compliance | Code matches plan exactly | YES | Spec reviewer | Small, Standard, Large |
| G6 | Code Quality + Tests | Clean, maintainable, tests passing | YES | Quality reviewer | Standard, Large |
| G6a | Review Loop Limit | Max 3 iterations per reviewer | YES | Auto → escalate | Small, Standard, Large |
| G7 | Final Tests | All tests pass after all tasks | YES | Auto — if fail, fix before options | All |
| G7b | Merge/PR/Keep/Discard | User choice | YES | User | All |

---

## 9. Scratchpad Resume Protocol

### Purpose
Enable @architect to resume workflow after session interruption (container restart, terminal close, OpenCode crash).

### File
`.opencode/scratchpad.md`

### Who Writes
**Only @architect.** Subagents NEVER read or write scratchpad.

### When to Write
After EVERY step: brainstorming done, plan approved, worktree created, each task started/done, each review done, doc commit done, finishing done.

### When to Read
On @architect session start. If workflow in progress → resume. If complete → clear and start new.

### Format
```markdown
# Current Mission

## Feature: [name]
## Branch: [branch name]
## Worktree: [absolute path]

## Workflow Status
- [x] Step 1: Brainstorming (design approved)
- [x] Step 2: Writing Plans (plan approved)
- [x] Step 3: Git Worktree (created, baseline clean)
- [ ] Step 4: Subagent-Driven Development
  - [x] Task 1: [name] (DONE, trivial)
  - [ ] Task 2: [name] (IN PROGRESS)
    - Implementer: DONE
    - Review: pending
  - [ ] Task 3: [name] (PENDING)
- [ ] Step 5: Doc commit
- [ ] Step 6: Finishing

## Blockers
None / [description]

## Context for Resume
- Plan file: [path]
- Design doc: [path]
- Last action: [what happened before interruption]
- Current worktree SHA: [git rev-parse HEAD]
```

### Resume Logic
```
@architect starts:
  read .opencode/scratchpad.md
  if status shows workflow in progress:
    "Resuming workflow for [feature]. Last recorded: [last action]."
    Continue from recorded step.
  else:
    "No active workflow. Starting fresh."
    Proceed with user request.
```

---

## 10. Directory Structure

```
/root/workspace/memo/
├── .opencode/
│   ├── agents/
│   │   ├── architect.md          # primary controller (manager + architect)
│   │   ├── frontend-coder.md     # implementer + TDD + product docs
│   │   ├── backend-coder.md      # implementer + TDD + FastAPI + product docs
│   │   ├── debugger.md           # investigator + systematic-debugging
│   │   ├── docser.md             # scribe, meta docs only
│   │   ├── deployer.md           # unchanged, manual ops
│   │   ├── spec-reviewer.md      # NEW, read-only
│   │   └── code-quality-reviewer.md # NEW, read-only + test execution
│   ├── skills/
│   │   ├── reviewers/
│   │   │   ├── spec-reviewer.md  # prompt template (NOT skill)
│   │   │   └── code-quality-reviewer.md # prompt template (NOT skill)
│   │   └── superpowers/          # localized superpowers skills (no external plugin needed)
│   │       ├── using-superpowers.md
│   │       ├── brainstorming.md
│   │       ├── writing-plans.md
│   │       ├── using-git-worktrees.md
│   │       ├── subagent-driven-development.md
│   │       ├── test-driven-development.md
│   │       ├── finishing-a-development-branch.md
│   │       └── systematic-debugging.md
│   ├── opencode.jsonc            # project-level plugin config
│   └── scratchpad.md             # resume protocol, architect-only
├── docs/
│   └── superpowers/
│       ├── specs/                # design docs from brainstorming
│       └── plans/                # implementation plans from writing-plans
├── .worktrees/                   # git worktrees (gitignored)
├── frontend/                     # Next.js 14 project
├── backend/                      # FastAPI project
├── SUPERAGENTS_SPEC.md           # v1.0 archived
├── SUPERAGENTS_SPEC_v2.md        # v2.0 archived
├── SUPERAGENTS_SPEC_v3.md        # THIS FILE
└── SUPERAGENTS_SPEC_v2_suspended.md # postponed proposals
```

---

## 11. Implementation Order

Execute in this exact order. Do NOT skip steps.

### Phase 1: Localize Superpowers Skills (NO plugin required)
1. Create `.opencode/skills/superpowers/` directory.
2. Copy Superpowers SKILL.md files into it:
   - `using-superpowers.md`
   - `brainstorming.md`
   - `writing-plans.md`
   - `using-git-worktrees.md`
   - `subagent-driven-development.md`
   - `test-driven-development.md`
   - `finishing-a-development-branch.md`
   - `systematic-debugging.md`
3. Verify: use `skill` tool to list skills, see `superpowers/brainstorming`, `superpowers/writing-plans`, etc.
4. **Do NOT install superpowers plugin.** Local skills are sufficient.

### Phase 2: New Agent Files
5. Create `.opencode/agents/spec-reviewer.md` (Section 3.7).
6. Create `.opencode/agents/code-quality-reviewer.md` (Section 3.8).

### Phase 3: Reviewer Templates
7. Create `.opencode/skills/reviewers/` directory.
8. Create `.opencode/skills/reviewers/spec-reviewer.md` (Section 5.1).
9. Create `.opencode/skills/reviewers/code-quality-reviewer.md` (Section 5.2).

### Phase 4: Existing Agent Updates
10. Update `.opencode/agents/architect.md`:
    - Merge @manager content (entry point, delegation).
    - Add Superpowers workflow steps with classification (Section 3.1).
    - Add scratchpad protocol (Section 9).
    - Update permissions: add `task` entries for spec-reviewer, code-quality-reviewer.
    - Add `skill` permission.
11. Update `.opencode/agents/frontend-coder.md`:
    - Add TDD skill invocation rule (Section 3.2).
    - Add product docs responsibility (README, not PLAN/CHANGELOG).
    - Add report format (DONE, DONE_WITH_CONCERNS, etc.).
    - Add `skill` permission.
12. Update `.opencode/agents/backend-coder.md`:
    - Add FastAPI TDD specifics (TestClient, fixtures, test DB) (Section 3.3).
    - Add product docs responsibility.
    - Add report format.
    - Add `skill` permission.
13. Update `.opencode/agents/debugger.md`:
    - Add systematic-debugging skill invocation (Section 3.4).
    - Add `skill` permission.
14. Update `.opencode/agents/docser.md`:
    - Add "meta docs only" scope boundary (Section 3.5).
    - Add "commit into feature branch" workflow.

### Phase 5: Infrastructure
15. Run `~/.config/opencode/update-infrastructure.sh`.
16. Create `docs/superpowers/specs/` and `docs/superpowers/plans/` directories.
17. Verify `.worktrees/` is in `.gitignore`.
18. Create empty `.opencode/scratchpad.md` with template header (Section 9).

### Phase 6: Proof-of-Concept
19. Ask user for a small feature (e.g., "Initialize Next.js 14 project").
20. Run full workflow end-to-end:
    - Brainstorming → design doc
    - Writing-plans → plan file with classification
    - Git worktree → isolated workspace
    - Subagent-driven-development → tasks with TDD + tier-specific review
    - Doc commit into branch
    - Finishing → create PR
21. Verify all gates passed.

---

## 12. Token Economy Rationale

To minimize token usage while preserving quality:

- **@architect** loads Superpowers workflow skills (generic, reusable).
- **@frontend-coder** / **@backend-coder** load their own agent.md (domain-specific) ONCE per subagent dispatch.
- **Project context** lives in agent.md files, NOT in task prompts. @architect sends only task-specific text + scene-setting.
- **Reviewers** use cheap models (`deepseek-v4-flash-free`) because they only read git diffs and report, no generation.
- **No project skill** — avoids loading full project context into @architect session repeatedly.
- **Git diff in reviewer prompts** — eliminates duplicate file reads across reviewer sessions.
- **Task complexity classification** — trivial tasks skip reviewers entirely, saving ~34K tokens per trivial task.

---

## 13. Cost Model Appendix

### Per-Subagent Spawn Cost

Each `task()` call creates a **new LLM API request with zero context inheritance**. No shared conversation history between subagent sessions.

**What prompt caching saves:**

| Component | Cached? | Details |
|-----------|---------|---------|
| Implementer `agent.md` (system prompt) | ✅ from 2nd+ spawn | Same agent type, identical system prompt → provider may cache. Saves ~1K tokens on repeated dispatches. |
| Reviewer `agent.md` (system prompt) | ✅ from 2nd+ spawn | Same. Saves ~500 tokens per repeated review. |
| Task `prompt` (user message) | ❌ NEVER | Unique per task: different feature, different context, different diff. |
| Git diff embedded in prompt | ❌ NEVER | Unique per task. |
| Output tokens | ❌ NEVER | Unique response per agent. |

### Duplicate Read Elimination

In v1.0, reviewers used `read` tool to read files independently. This caused **duplicate file reads** (10K tokens × 2 reviewers = 20K waste per task).

**In v3.0:** @architect embeds `git diff` output directly in reviewer prompts. Reviewers analyze embedded diff, NOT `read` tool. **Zero duplicate file reads.**

### Per-Task Cost Model by Tier

Assume average diff: 3 files changed, 200 lines, ~2K tokens of diff text.

| Tier | Pipeline | Cost per task |
|------|----------|---------------|
| **Trivial** | Implementer + architect spot-check | ~4K tokens |
| **Small** | Implementer + spec-reviewer (no fix) | ~12K tokens |
| **Standard** | Implementer + spec-reviewer + quality-reviewer (no fix) | ~20K tokens |
| **Large** | Implementer + spec-reviewer + quality-reviewer + final reviewer | ~30K tokens |

**With 1 fix-loop (typical):**

| Tier | +1 fix-loop | Total |
|------|-------------|-------|
| Small | +8K | ~20K |
| Standard | +16K | ~36K |
| Large | +24K | ~54K |

### Fix-Loop Budget (Circuit Breaker)

- **Max 3 iterations per reviewer.** If 3rd iteration ❌ → STOP, escalate to human.
- **Trivial tasks:** No reviewers, no fix-loops.
- **Per-task max budget:**
  - Trivial: 6K tokens
  - Small: 28K tokens (3 spec loops)
  - Standard: 52K tokens (3 spec + 3 quality loops)
  - Large: 78K tokens + final review
- **If exceeded → human escalation.**

### Feature Cost Projection

A medium feature (5 tasks: 2 trivial, 2 small, 1 standard, 1 fix-loop average):

- **Trivial (2):** 2 × 4K = 8K
- **Small (2):** 2 × 20K = 40K
- **Standard (1):** 1 × 36K = 36K
- **+ docser:** ~5K
- **+ finishing:** ~5K
- **Total feature:** **~94K tokens**

At typical model pricing, a single feature costs **~$0.40–$1.80** for subagents.

### Model Selection Guidance

| Diff size | Implementer | Reviewers |
|-----------|-------------|-----------|
| < 100 lines (trivial/small) | Standard model | Cheap model |
| 100–300 lines (standard) | Standard model | Cheap model |
| > 300 lines or architecture (large) | Capable model | Standard model |

---

## 14. Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | @manager merged into @architect | Single entry point, single controller for workflow |
| 2 | @tester removed | TDD absorbed into implementers; review is two-stage automatic |
| 3 | Separate spec-reviewer and code-quality-reviewer agents | Dedicated roles, read-only permissions, cheap models |
| 4 | Reviewer prompts stored as markdown templates (NOT skills) | Read by architect via `read` tool, filled, passed as prompt to `task()` |
| 5 | No project skill for context | Token economy — domain knowledge lives in agent.md |
| 6 | Auto-create PR as default (Option 2) | Standard for feature work, user can still choose others |
| 7 | Docser commits into feature branch before finishing | PR includes documentation, reviewer sees full picture |
| 8 | Superpowers spec.md in root | Easy to find, not buried in docs/ |
| 9 | No project skill, agents read docs on-demand | Surgical context — controller minimal, agents responsible for their domain |
| 10 | Reviewers receive git diff in prompt, not file paths | Eliminates duplicate file reads across sessions; biggest cost driver |
| 11 | Code-quality-reviewer runs test suite | Closes verification gap — reviewers don't just read code, they verify tests pass |
| 12 | Keep two separate reviewers (not consolidated) | Two-stage review is core Superpowers principle. Cost solved by git diff |
| 13 | Doc tier separation (product vs meta) | Product docs (README) in implementer tasks, meta docs (PLAN/CHANGELOG) by docser post-feature. Prevents acceptance criteria deadlock |
| 14 | Max 3 review iterations + escalation | Circuit breaker for infinite fix-loops. Token budget protection |
| 15 | Task complexity classification (trivial/small/standard/large) | Trivial skips reviewers (~34K savings). Small skips quality reviewer. Token optimization without quality loss |
| 16 | Scratchpad resume protocol | Enables workflow recovery after session interruption. Architect-only, updated after every step |
| 17 | Backend workflow explicit (FastAPI + SQLite + pytest) | Balanced spec: frontend not dominant. TestClient, fixtures, :memory: DB |
| 18 | Superpowers skills fully localized, plugin removed from opencode.jsonc | `.opencode/skills/superpowers/` — no external plugin needed, no dependency on upstream repo |

---

## 15. Context Management Strategy

### Two-Tier Context Model

The controller (@architect) and implementers own different layers of context:

| Tier | Owner | Contains | Example |
|------|-------|----------|---------|
| **Architectural** | @architect | Component tree, data flow, task dependencies, interface contracts, scene-setting, classification | "ActivityCard renders inside DayColumn, receives data from useSchedule(), depends on Sidebar being ready. Task classification: standard." |
| **Implementation** | @frontend-coder / @backend-coder | Design tokens, API schemas, mock data, stack conventions, code patterns, test strategies | Colors #1E2D2F/#004D56, Tailwind classes, import paths, Pydantic models, TestClient fixtures |

### What @architect passes in task prompt

**Required:**
- Task description verbatim from plan
- **Classification** (trivial/small/standard/large)
- Architectural position: where this fits, what it depends on, what depends on it
- Interface contracts: props, context shape, API signatures of adjacent components
- Document references (paths, NOT content — subagent reads them)
- Working directory path
- Required skill invocation (TDD, etc.)

**NOT passed** (subagent reads from docs via its own agent.md instructions):
- Color hex codes, font sizes, spacing values → `docs/v4-design-system.md`
- API endpoint URLs, request/response schemas → `docs/memo-full-spec.md`
- Mock data structures → `docs/mock-data.md`
- FastAPI test patterns → `backend-coder.md` own knowledge

### Why this works

- Implementer agent.md already instructs which docs to read before starting
- Controller doesn't duplicate design system in every prompt
- If implementer uses wrong color → implementer's fault (failed to read design system)
- If implementer doesn't know Sidebar exists → controller's fault (failed to provide architectural context)

### Boundary

| If this goes wrong | It's whose fault | Fix |
|---|---|---|
| Wrong color, font, spacing | Implementer | Update agent.md instructions |
| Component doesn't integrate with sibling | Architect | Improve architectural handoff |
| Missing edge case in tests | Implementer (TDD) | Add to acceptance criteria in plan |
| Implementation doesn't match plan spec | Both | Spec-reviewer catches this |
| Wrong test DB setup in FastAPI | Backend-coder | Update backend-coder.md instructions |
| Acceptance criteria include meta doc update | Architect (plan error) | Separate product docs (implementer) from meta docs (docser) |

### Example Contrast

**Wrong (controller holds all context):**
```
Task: Create ScheduleGrid. Design: #1E2D2F sidebar, #004D56 brand, 
cards with semi-transparent fill. API: /api/v1/schedule. 
Previous impl in memo-v1 uses React Context...
```

**Right (surgical, agent reads what it needs):**
```
Task: Create ScheduleGrid component in app/admin/schedule/
Classification: standard
Design reference: docs/v4-design-system.md
API reference: docs/memo-full-spec.md (Schedule section)
Previous impl reference: /root/workspace/memo-v1/memo-frontend/
Required skill: superpowers:test-driven-development
```

---

## 16. Suspended Proposals

See `SUPERAGENTS_SPEC_v2_suspended.md` for postponed/rejected ideas.
