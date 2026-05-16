# Superpowers Integration Specification — Memo Project

> **Version:** 1.0  
> **Date:** 2026-05-14  
> **Project:** Memo (Colour Mountains art studio management system)  
> **Purpose:** Precise specification for merging Superpowers workflow with existing Memo agents. Any LLM reading this spec must be able to implement it identically without inferring context.

---

## 1. Goal

Replace the existing ad-hoc multi-agent workflow with a **unified Superpowers-driven workflow** while preserving domain-specific agent expertise (Next.js, FastAPI, design system).

**Outcomes:**
- Automatic workflow progression with quality gates
- Test-Driven Development (RED-GREEN-REFACTOR) for all code
- Two-stage review (spec compliance + code quality) after every task
- Git worktree isolation for every feature
- Documentation committed into feature branch before PR

---

## 2. Final Agent Architecture

| # | Agent | Mode | Model | Role | Source |
|---|-------|------|-------|------|--------|
| 1 | **@architect** | primary | opencode-go/kimi-k2.6 | Workflow controller. Entry point, planning, subagent dispatch, timeline | Merge of @manager + @architect |
| 2 | **@frontend-coder** | subagent | opencode-go/qwen3.6-plus | Implementer. Next.js 14 + TypeScript + Tailwind + TDD | Existing, enhanced |
| 3 | **@backend-coder** | subagent | opencode-go/qwen3.6-plus | Implementer. FastAPI + SQLite + TDD | Existing, enhanced |
| 4 | **@debugger** | subagent | opencode-go/qwen3.6-plus | Investigator. Root cause analysis only. Not a fixer. | Existing, enhanced |
| 5 | **@docser** | subagent | opencode/deepseek-v4-flash-free | Scribe. Docs, PLAN.md, CHANGELOG.md, GitHub Project | Existing, enhanced |
| 6 | **@deployer** | subagent | opencode/deepseek-v4-flash-free | DevOps. Production deploy, SSH, Docker, manual ops | Existing, unchanged |
| 7 | **@spec-reviewer** | subagent | opencode/deepseek-v4-flash-free | Read-only. Verifies "code matches plan" | **NEW** |
| 8 | **@code-quality-reviewer** | subagent | opencode/deepseek-v4-flash-free | Read-only. Verifies "code is well-built" | **NEW** |

**Removed:** @manager (merged into @architect), @tester (TDD absorbed into implementers).

---

## 3. Agent Specifications

### 3.1 @architect (Primary / Controller)

**File:** `.opencode/agents/architect.md`

**Frontmatter:**
```yaml
---
description: Workflow controller. Entry point, brainstorming, planning, subagent dispatch, quality gates, timeline.
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

**Prompt — Superpowers Skill Invocation Rule:**
- Before ANY creative work (planning, coding dispatch, bug triage), check if a Superpowers skill applies.
- If yes — invoke it via the `skill` tool FIRST, before any other action.
- If multiple skills apply — process skills first (brainstorming, debugging), then implementation skills (writing-plans).

**Prompt — Workflow Steps (Automatic Transitions):**

```markdown
## Workflow Steps

You are a state machine. Do NOT pause between steps without reason. Proceed automatically until hitting a Human Gate or blocker.

### Step 1: Brainstorming (Human Gate G1)
Trigger: User asks for a new feature, component, or significant change.
Actions:
1. Invoke skill `superpowers:brainstorming`
2. Follow skill exactly: explore context → ask clarifying questions (one at a time) → propose 2-3 approaches → present design sections → get user approval
3. Save approved design to `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md`
4. Commit: `git add docs/superpowers/specs/... && git commit -m "docs: add design for <feature>"`
5. [GATE G1] Wait for user approval of design. Do NOT proceed without it.

### Step 2: Writing Plans (Human Gate G2)
Trigger: Design approved.
Actions:
1. Invoke skill `superpowers:writing-plans`
2. Create bite-sized implementation plan: exact file paths, exact code blocks, exact commands, no placeholders
3. Save to `docs/superpowers/plans/YYYY-MM-DD-<feature>-plan.md`
4. Self-review: scan for TBD, TODO, "implement later", vague requirements. Fix inline.
5. [GATE G2] Present plan to user for approval.

### Step 3: Git Worktree (Auto Gate G3)
Trigger: Plan approved.
Actions:
1. Invoke skill `superpowers:using-git-worktrees`
2. Create isolated worktree: `git worktree add .worktrees/feat-<name> -b feat-<name>`
3. Change to worktree: `cd .worktrees/feat-<name>`
4. Run project setup:
   - If `package.json` exists: `npm install`
   - If `requirements.txt` or `pyproject.toml` exists: install python deps
5. Run tests to verify clean baseline:
   - Frontend: `npm test` or `vitest run`
   - Backend: `pytest` or `python -m pytest`
6. [GATE G3] If tests FAIL → stop, report failures to user, ask whether to proceed. If PASS → proceed to Step 4 automatically.

### Step 4: Subagent-Driven Development Loop (Auto Gates G4-G6)
Trigger: Clean baseline verified.
Actions:
1. Invoke skill `superpowers:subagent-driven-development`
2. Read plan file once. Extract ALL tasks with full text and context. Store in memory.
3. Create TodoWrite with all tasks from plan.
4. **FOR each task:**

   **4a. Dispatch Implementer Subagent**
   - Determine agent type from plan (frontend task → `frontend-coder`, backend task → `backend-coder`)
   - Use `task` tool:
     ```
     subagent_type: "frontend-coder" | "backend-coder"
     prompt: |
       ## Task N: [name from plan]

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

   **4b. Handle Implementer Status**
   - `DONE` → proceed to 4c
   - `DONE_WITH_CONCERNS` → read concerns. If correctness/scope → address before review. If observations → note and proceed.
   - `NEEDS_CONTEXT` → provide missing context, re-dispatch SAME task to SAME subagent.
   - `BLOCKED` → assess: (1) context problem → re-dispatch, (2) needs more reasoning → re-dispatch with more capable model, (3) task too large → break into smaller tasks, (4) plan wrong → escalate to user.

   **4c. Dispatch Spec Reviewer (Auto, no human input)**
   - Get git SHAs: `BASE_SHA=$(git rev-parse HEAD~1)` (or before task), `HEAD_SHA=$(git rev-parse HEAD)`
   - Use `task` tool:
     ```
     subagent_type: "spec-reviewer"
     prompt: [load from .opencode/skills/reviewers/spec-reviewer.md template, fill placeholders]
     ```
   - Wait for report.
   - If ❌ issues found → return implementer subagent with SPECIFIC issues (file:line, what's missing/extra). Loop: fix → re-dispatch spec reviewer → until ✅.
   - If ✅ → proceed to 4d.

   **4d. Dispatch Code Quality Reviewer (Auto, no human input)**
   - Only after spec compliance is ✅.
   - Use `task` tool:
     ```
     subagent_type: "code-quality-reviewer"
     prompt: [load from .opencode/skills/reviewers/code-quality-reviewer.md template]
     ```
   - Wait for report.
   - If ❌ issues found → return implementer subagent. Loop: fix → re-dispatch quality reviewer → until ✅.
   - If ✅ → mark task complete in TodoWrite.

   **4e. Next Task**
   - Automatically proceed to next task. Do NOT ask user "continue?".
   - Exception: if BLOCKED and cannot resolve → stop and ask user.

### Step 5: Documentation Commit (Auto, before finishing)
Trigger: All tasks complete, all tests passing.
Actions:
1. Gather context from session:
   - Feature name, design doc path, plan path
   - List of completed tasks (from TodoWrite)
   - Test results (final run)
   - Changed files (`git diff --name-only base..HEAD`)
   - Acceptance criteria status
2. Dispatch @docser via `task` tool with structured handoff (see @docser spec below).
3. @docser commits documentation into the FEATURE BRANCH (not after merge).
4. Wait for commit SHA from @docser.

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
```

**Prompt — Context Handoff to Subagents:**
- You do NOT pass your full session context to subagents.
- You construct EXACTLY what they need: full task text from plan + scene-setting + required skill.
- Subagents load their own domain knowledge from their agent.md (Next.js, FastAPI, etc.).
- You NEVER make subagents read plan files. Provide full text in prompt.

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

### Report Format
When done, report to @architect:
- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- **Implemented:** what you built
- **Tested:** test command and results (e.g., "5/5 passing")
- **Files changed:** list with created/modified
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

**Frontmatter:** add `skill` permission as above.

**Prompt — Required Additions:**
Same TDD skill invocation rule and report format as @frontend-coder.

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
4. Update README.md if quick-start instructions changed
5. Scan `docs/`, `.opencode/agents/`, `.opencode/skills/` for new files. Update your internal document list if needed.
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

## Rules
- You do NOT fix code. You only read and report.
- You do NOT trust the implementer's report. Read the actual code.
- Compare actual implementation to requirements line by line.
- Check for missing pieces and extra features.

## Report Format
- ✅ Spec compliant — if everything matches after code inspection
- ❌ Issues found — list specifically:
  - Missing: [requirement] not implemented, expected at [file:line]
  - Extra: [feature] not requested, found at [file:line]
  - Misunderstood: [requirement] implemented differently than specified
```

---

### 3.8 @code-quality-reviewer (NEW)

**File:** `.opencode/agents/code-quality-reviewer.md`

**Frontmatter:**
```yaml
---
description: Code quality reviewer. Verifies that implementation is well-built, clean, tested, and maintainable.
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
You are a Code Quality Reviewer.

Your ONLY job: verify implementation quality.

## Rules
- You do NOT fix code. You only read and report.
- Check: single responsibility per file, clear interfaces, test quality, naming, duplication.
- Do NOT flag pre-existing issues — only what THIS change contributed.

## Report Format
- Strengths: [what's done well]
- Issues:
  - Critical: [blocks approval]
  - Important: [should fix before proceed]
  - Minor: [note for later]
- Assessment: Approved / Needs work
```

---

## 4. Reviewer Prompt Templates (Project Skills)

**Location:** `.opencode/skills/reviewers/`

### 4.1 Spec Reviewer Template
**File:** `.opencode/skills/reviewers/spec-reviewer.md`

```markdown
---
name: spec-reviewer-template
description: Use when dispatching spec compliance reviewer subagent
---

## Review Task

Review whether the implementation matches its specification.

## What Was Requested

{PLAN_TASK_FULL_TEXT}

## What Implementer Claims They Built

{IMPLEMENTER_REPORT}

## CRITICAL: Do Not Trust the Report

The implementer may be incomplete or optimistic. You MUST verify independently by reading actual code.

## Your Job

Read the implementation and verify:
1. Missing requirements
2. Extra/unneeded work
3. Misunderstandings

Report:
- ✅ Spec compliant
- ❌ Issues found: [specific list with file:line references]
```

### 4.2 Code Quality Reviewer Template
**File:** `.opencode/skills/reviewers/code-quality-reviewer.md`

```markdown
---
name: code-quality-reviewer-template
description: Use when dispatching code quality reviewer subagent
---

## Review Task

Review code quality for Task {TASK_NUMBER}.

## Description
{IMPLEMENTER_DESCRIPTION}

## Plan
{PLAN_TASK_REFERENCE}

## Commits
Base: {BASE_SHA}
Head: {HEAD_SHA}

## Additional Checks
- Does each file have one clear responsibility?
- Are units decomposed for independent understanding/testing?
- Did this change create large new files or grow existing files beyond reasonable size?

Report:
- Strengths
- Issues (Critical / Important / Minor)
- Assessment: Approved / Needs work
```

---

## 5. Git Workflow Specification

### 5.1 Worktree Creation

**Directory:** `.worktrees/` at project root.
**Verify ignored:** Before first use, ensure `.worktrees/` is in `.gitignore`.
**Command:**
```bash
# From project root
FEATURE="feat-$(echo $FEATURE_NAME | tr ' ' '-' | tr '[:upper:]' '[:lower:]')"
git worktree add ".worktrees/$FEATURE" -b "$FEATURE"
cd ".worktrees/$FEATURE"
```

### 5.2 Project Setup in Worktree

Auto-detect and run:
```bash
# Node.js frontend
if [ -f package.json ]; then npm install; fi

# Python backend
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ]; then uv sync || poetry install || true; fi
```

### 5.3 Clean Baseline Verification

Run tests BEFORE any implementation:
```bash
# Frontend
if [ -f package.json ]; then npm test || npx vitest run; fi

# Backend
if [ -f pytest.ini ] || [ -f pyproject.toml ]; then pytest; fi
```

**If tests fail:** Stop. Report failures to user. Do NOT proceed.

### 5.4 Documentation Commit (in feature branch)

**When:** After all tasks complete, before finishing branch.
**Commit message:** `docs: update status for feat-<name>`
**Content:** PLAN.md + CHANGELOG.md updates.

### 5.5 Finishing Branch

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

## 6. Quality Gates Summary

| Gate | Name | Checks | Blocker? | Who decides |
|------|------|--------|----------|-------------|
| G1 | Design Approval | User reviewed design doc | YES | User |
| G2 | Plan Approval | User reviewed plan (no placeholders) | YES | User |
| G3 | Clean Baseline | Tests pass on new worktree | YES | Auto — if fail, ask user |
| G4 | TDD Compliance | RED-GREEN-REFACTOR, test before code | YES | Implementer self-check |
| G5 | Spec Compliance | Code matches plan exactly | YES | Spec reviewer |
| G6 | Code Quality | Clean, maintainable, tested | YES | Quality reviewer |
| G7 | Final Tests | All tests pass after all tasks | YES | Auto — if fail, fix before options |
| G7b | Merge/PR/Keep/Discard | User choice | YES | User |

---

## 7. Directory Structure

```
/root/workspace/memo/
├── .opencode/
│   ├── agents/
│   │   ├── architect.md          # primary controller (manager + architect)
│   │   ├── frontend-coder.md     # implementer + TDD
│   │   ├── backend-coder.md      # implementer + TDD
│   │   ├── debugger.md           # investigator + systematic-debugging
│   │   ├── docser.md             # scribe, docs commit into branch
│   │   ├── deployer.md           # unchanged, manual ops
│   │   ├── spec-reviewer.md      # NEW, read-only
│   │   └── code-quality-reviewer.md # NEW, read-only
│   ├── skills/
│   │   └── reviewers/
│   │       ├── spec-reviewer.md  # prompt template
│   │       └── code-quality-reviewer.md # prompt template
│   ├── opencode.jsonc            # project-level plugin config
│   └── scratchpad.md             # current mission context
├── docs/
│   └── superpowers/
│       ├── specs/                # design docs from brainstorming
│       └── plans/                # implementation plans from writing-plans
├── .worktrees/                   # git worktrees (gitignored)
├── frontend/                     # Next.js 14 project
├── backend/                      # FastAPI project
└── SUPERAGENTS_SPEC.md           # THIS FILE
```

---

## 8. Implementation Order

Execute in this exact order. Do NOT skip steps.

### Phase 1: Plugin Installation
1. Add `superpowers@git+https://github.com/obra/superpowers.git` to global `opencode.jsonc` plugin array.
2. Create project-level `.opencode/opencode.jsonc` with same plugin.
3. Restart OpenCode container to load plugin.
4. Verify: `opencode run --print-logs "Tell me about your superpowers"` contains `superpowers`.
5. Verify: use `skill` tool to list skills, see `superpowers/brainstorming`, `superpowers/writing-plans`, etc.

### Phase 2: New Agent Files
6. Create `.opencode/agents/spec-reviewer.md` (Section 3.7).
7. Create `.opencode/agents/code-quality-reviewer.md` (Section 3.8).

### Phase 3: Reviewer Templates
8. Create `.opencode/skills/reviewers/` directory.
9. Create `.opencode/skills/reviewers/spec-reviewer.md` (Section 4.1).
10. Create `.opencode/skills/reviewers/code-quality-reviewer.md` (Section 4.2).

### Phase 4: Existing Agent Updates
11. Update `.opencode/agents/architect.md`:
    - Merge @manager content (entry point, delegation, project context references).
    - Add Superpowers workflow steps (Section 3.1).
    - Update permissions: add `task` entries for spec-reviewer, code-quality-reviewer.
    - Add `skill` permission.
12. Update `.opencode/agents/frontend-coder.md`:
    - Add TDD skill invocation rule (Section 3.2).
    - Add report format (DONE, DONE_WITH_CONCERNS, etc.).
    - Add `skill` permission.
13. Update `.opencode/agents/backend-coder.md`:
    - Same as frontend-coder (Section 3.3).
14. Update `.opencode/agents/debugger.md`:
    - Add systematic-debugging skill invocation (Section 3.4).
    - Add `skill` permission.
15. Update `.opencode/agents/docser.md`:
    - Add "commit into feature branch" workflow (Section 3.5).

### Phase 5: Infrastructure
16. Run `~/.config/opencode/update-infrastructure.sh`.
17. Create `docs/superpowers/specs/` and `docs/superpowers/plans/` directories.
18. Verify `.worktrees/` is in `.gitignore`.

### Phase 6: Proof-of-Concept
19. Ask user for a small feature (e.g., "Initialize Next.js 14 project").
20. Run full workflow end-to-end:
    - Brainstorming → design doc
    - Writing-plans → plan file
    - Git worktree → isolated workspace
    - Subagent-driven-development → tasks with TDD + two-stage review
    - Doc commit into branch
    - Finishing → create PR
21. Verify all gates passed.

---

## 9. Token Economy Rationale

To minimize token usage while preserving quality:

- **@architect** loads Superpowers workflow skills (generic, reusable).
- **@frontend-coder** / **@backend-coder** load their own agent.md (domain-specific) ONCE per subagent dispatch.
- **Project context** lives in agent.md files, NOT in task prompts. @architect sends only task-specific text + scene-setting.
- **Reviewers** use cheap models (`deepseek-v4-flash-free`) because they only read code and report, no generation.
- **No project skill** — avoids loading full project context into @architect session repeatedly.

---

## 10. Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | @manager merged into @architect | Single entry point, single controller for workflow |
| 2 | @tester removed | TDD absorbed into implementers; review is two-stage automatic |
| 3 | Separate spec-reviewer and code-quality-reviewer agents | Dedicated roles, read-only permissions, cheap models |
| 4 | Reviewer prompts stored as project skills | Version control, easy to modify without touching agent.md |
| 5 | No project skill for context | Token economy — domain knowledge lives in agent.md |
| 6 | Auto-create PR as default (Option 2) | Standard for feature work, user can still choose others |
| 7 | Docser commits into feature branch before finishing | PR includes documentation, reviewer sees full picture |
| 8 | Superpowers spec.md in root | Easy to find, not buried in docs/ |
| 9 | No project skill, agents read docs on-demand | Surgical context — controller minimal, agents responsible for their domain |

---

## 11. Context Management Strategy

### Principle: Surgical by Design, Not by Controller

This project uses a **HYBRID approach** distinct from pure Superpowers:

- **Controller (@architect)** provides **MINIMAL task context**:
  - Task description (verbatim from plan)
  - Scene-setting (where this fits in the architecture)
  - Reference to relevant docs (file paths, NOT content)

- **Implementer subagents** are **RESPONSIBLE for their own domain context**:
  - @frontend-coder knows to read `docs/v4-design-system.md`, `docs/schedule-ui.md`
  - @backend-coder knows to read `docs/memo-full-spec.md` (API Specification, Data Models)
  - Both know their stack conventions from their own `agent.md`

### Why This Differs from Pure Superpowers

In pure Superpowers, the controller holds ALL project context and surgically passes slices to subagents. In our architecture:

- The controller does NOT preload full project context
- The controller does NOT decide what the subagent needs to know
- The subagent's `agent.md` instructions define what docs to read
- The subagent reads relevant docs ON-DEMAND via `read` tool

### Rationale

1. **Token efficiency**: Controller doesn't carry 1000+ tokens of project context in every prompt
2. **Reliability**: No single point of failure (controller forgetting to include design colors or API convention)
3. **Specialization**: Domain experts (@frontend-coder, @backend-coder) know what they need better than the controller
4. **Auditability**: If context is wrong, it's in `agent.md` (reviewable file), not in ephemeral task prompts
5. **Scalability**: Adding a new tech stack means updating one agent.md, not bloating the controller

### Implementation Rule

**Controller prompt to subagent MUST NOT include:**
- Full design system content (colors, typography, spacing)
- Full API specification (endpoints, schemas, auth)
- Full mock data structures
- Full project history or previous implementation details

**Controller prompt MUST include:**
- Exact task description from plan (verbatim)
- File paths to relevant docs (for subagent to read if needed)
- Working directory
- Required skill invocation (TDD, etc.)
- Scene-setting: architectural position of this task

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
Design reference: docs/v4-design-system.md
API reference: docs/memo-full-spec.md (Schedule section)
Previous impl reference: /root/workspace/memo-v1/memo-frontend/
Required skill: superpowers:test-driven-development
```
