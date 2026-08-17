---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** If working in an isolated worktree, it should have been created via the `using-git-worktrees` skill at execution time.

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`
- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Behavioral Delta (REQUIRED section in every plan)

Every plan MUST include a `## Behavioral Delta` subsection, placed right after the header (before the task list). This is a **plain-language** description of how the feature will behave for the end user — no code, no file names — mapped to the spec's acceptance criteria.

This section is what the architect presents at the **asymmetric G2 gate**: for frontend features the user approves the feature by BEHAVIOR (relying on spec-reviewer's Plan Review for engineering correctness), not by reading plan code.

**Format:**

```markdown
## Behavioral Delta

How this feature behaves for the user, mapped to spec acceptance criteria:

- **[Acceptance criterion from spec]** → [what the user will see/do, in plain language]
- **[Acceptance criterion from spec]** → [observable behavior]
```

Keep it concise: one line per acceptance criterion. It must be understandable by someone who has NOT read the implementation.

## Task Structure

Each task must include:
- **Files:** exact paths (create/modify/test)
- **Required Docs:** list of docs the implementer must read before starting
- **Steps:** checkbox format with exact code/commands
- **No placeholders** — no "TBD", "TODO", "implement later"
- **Exact commands with expected output**

### Task Header Format — grep-able anchors

Every task MUST start with a stable, unique header that can be located by grep without reading
the file (architects read plans section-wise — this format is what makes that cheap):

```markdown
## Task N: <short unique name>
### Classification: trivial | small | standard | large
```

- Use exactly `## Task N:` (level-2 heading), `### Classification:` immediately after.
- Keep the name short and unique — it is the anchor for section-scoped reads.
- Do NOT duplicate a task's full text anywhere else in the plan. Each task text appears exactly
  once, so a section read by header is guaranteed complete.
- Cross-reference other tasks by `Task N`, never by pasting their content.
- After the plan is committed these headers are stable — do not renumber or rename them during
  review-fix loops (breaks anchors, TodoWrite tracking, and resume handoffs).

### Required Docs Section

Every task MUST have a `### Required Docs` section listing which docs the implementer needs to read. This is the **primary mechanism** for context transfer from architect to implementer.

**Example:**

```markdown
## Task 1: Add Master color validation
### Classification: small
### Required Docs
- `docs/domain-rules/masters.md` — entity fields, validation rules
- `docs/design-system.md` — color format conventions

### Task Description
[full task text]
```

**Rules for Required Docs:**
- If task touches an entity → include `docs/domain-rules/{entity}.md`
- If task touches UI → include `docs/design-system.md`
- If task touches naming → include `docs/domain-rules/_overview.md` (Naming Conventions)
- If task touches testing → include relevant skill (pytest-patterns, vitest-playwright-patterns)
- **If task implements a User Scenario** → the DoD must include "E2E test for scenario N passes" — written as a RED-GREEN-REFACTOR cycle. See testing-strategy-v2.
- Be specific: add comment explaining what to look for in each doc

## E2E Coverage in DoD

**When a task implements a User Scenario** (from the spec's `## User Scenarios` section), the task's DoD (Definition of Done) **MUST** include a line like:

> "E2E test for scenario N passes (RED-GREEN-REFACTOR)"

**Why:** The whole point of User Scenarios in the spec is to give E2E tests an anchor. If a task implements a scenario but its DoD doesn't mention an E2E, there's no guarantee the E2E exists or passes.

**Pattern in the task's Steps section:**
1. Write RED E2E for scenario N (test fails because feature is missing or buggy)
2. Implement minimal code to make E2E pass (GREEN)
3. Refactor if needed
4. Verify E2E still passes
5. Commit

See testing-strategy-v2 for full context.

## Backend Tasks with Schema Changes

**When:** Task involves adding/modifying SQLAlchemy model fields.

**Rule:** Architect MUST explicitly specify database migration in task description.

**Task template:**
```markdown
## Task N: Add [field] to [model]

**Schema change:**
- Model: `backend/src/models/[model].py`
- Field: `[field_name]: Mapped[type] = mapped_column(...)`
- SQLite: `ALTER TABLE [table] ADD COLUMN [field] [TYPE] [constraints]`
- Seed: Update `backend/src/seed/seed.py` to include new field

**Implementation steps:**
1. Update SQLite schema: `sqlite3 backend/memo.db "ALTER TABLE ..."`
2. Verify: `sqlite3 backend/memo.db ".schema [table]"`
3. Update model: add field to SQLAlchemy class
4. Update seed.py: add field to seed data
5. Write RED test
6. Implement GREEN
7. Refactor

**Why:** Schema must exist BEFORE tests run. Architect decides schema changes, implementer executes.
```

**Example:**
```markdown
## Task 3: Add sort_order to Master and Location models

**Schema change:**
- Models: `backend/src/models/master.py`, `backend/src/models/location.py`
- Field: `sort_order: Mapped[int] = mapped_column(Integer, default=0)`
- SQLite: 
  - `ALTER TABLE masters ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0`
  - `ALTER TABLE locations ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0`
- Seed: Update seed data to include sort_order values

**Implementation steps:**
1. Update SQLite: run both ALTER TABLE commands
2. Verify schemas: `.schema masters` and `.schema locations`
3. Update models: add sort_order field
4. Update seed.py: add sort_order to master/location data
5. Write RED test for sort_order functionality
6. Implement GREEN
7. Refactor
```

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures**:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code)
- Steps that describe what to do without showing how

## Self-Review

After writing the complete plan:

1. **Spec coverage:** Can you point to a task for each requirement? List gaps.
2. **Placeholder scan:** Fix any red flags.
3. **Type consistency:** Functions/types match across tasks?
4. **Required Docs check:** Every task has `### Required Docs` section? Missing docs?

If issues found, fix inline.

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/plans/<filename>.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use subagent-driven-development
- Fresh subagent per task + two-stage review
