# Requests to SUPERAGENTS_SPEC.md author

> From: review of SUPERAGENTS_SPEC.md v1.0 against real OpenCode environment
> Date: 2026-05-15

---

## 1. Prompt caching reality — subagent spawn cost analysis (COST-CRITICAL)

### Evidence from superpowers source

**`subagent-driven-development` SKILL.md, line 10:**

> «They should never inherit your session's context or history — you construct exactly what they need. This also preserves your own context for coordination work.»

**Line 242 (Red Flags):**

> «Never: Dispatch multiple implementation subagents in parallel (conflicts)»

### What actually happens at the API level

Each `task()` call creates a **new LLM API request with zero context inheritance**. No shared conversation history, no shared cache between subagent sessions:

```
@architect session (PID A)
  │
  ├─ task("frontend-coder", prompt₁)
  │    └─ NEW API request
  │       ├─ system: frontend-coder.md (fixed, ~1K tokens)
  │       ├─ user:   prompt₁ (variable, ~500-2K)
  │       └─ tool calls: read files → results in session context (~5-20K)
  │
  ├─ task("spec-reviewer", prompt₂)
  │    └─ NEW API request (NO shared cache with frontend-coder)
  │       ├─ system: spec-reviewer.md (fixed, ~500 tokens)
  │       ├─ user:   prompt₂ (variable, ~500-1K)
  │       └─ tool calls: read SAME files again → (~5-20K)  ← DUPLICATE
  │
  └─ task("code-quality-reviewer", prompt₃)
       └─ NEW API request (NO shared cache with either)
          ├─ system: quality-reviewer.md (fixed, ~500 tokens)
          ├─ user:   prompt₃ (variable, ~500-1K)
          └─ tool calls: read SAME files again → (~5-20K)  ← TRIPLICATE
```

### What prompt caching actually saves

Prompt caching operates at the **provider level** (e.g., OpenRouter, opencode-go). It caches identical prefixes of consecutive API requests. In this workflow:

| Component | Cached? | Details |
|-----------|---------|---------|
| Implementer `agent.md` (system prompt) | ✅ from 2nd+ spawn | Same agent type, identical system prompt → provider may cache. Saves ~1K tokens on repeated dispatches. |
| Reviewer `agent.md` (system prompt) | ✅ from 2nd+ spawn | Same. Saves ~500 tokens per repeated review. |
| Task `prompt` (user message) | ❌ NEVER | Unique per task: different feature, different context, different diff. |
| File reads (`read`/`grep` results) | ❌ NEVER | Results flow into session-specific context. Each subagent has its own session → reads everything fresh. |
| Output tokens | ❌ NEVER | Unique response per agent. |
| Fix-loop: implementer re-spawn | ⚠️ Partial | agent.md cached, but new task prompt + re-read all files. |
| Fix-loop: reviewer re-spawn | ⚠️ Partial | agent.md cached, but re-read all files. |

### Detailed per-task cost model

Assume average feature task: 3 files changed, 200 lines of diff, ~10K tokens of code to review.

**Without fix-loop (ideal case):**

| Step | System prompt | Task prompt | File reads | Output | Subtotal |
|------|:---:|:---:|:---:|:---:|:---:|
| Implementer spawn | 1K (cached) | 1K | 10K | 2K | 14K |
| Spec-reviewer spawn | 500 (cached) | 500 | 10K | 1K | 12K |
| Code-quality spawn | 500 (cached) | 500 | 10K | 1K | 12K |
| **Total 1 task** | | | | | **~38K tokens** |

**With 1 fix-loop (typical — spec or quality issues found, implementer fixes, re-review):**

| Step | System prompt | Task prompt | File reads | Output | Subtotal |
|------|:---:|:---:|:---:|:---:|:---:|
| ... (initial 3 agents) | | | | | 38K |
| Implementer fix + re-spawn | 1K (cached) | 500 | 8K | 1.5K | 11K |
| Reviewer re-spawn | 500 (cached) | 300 | 8K | 500 | 9.3K |
| **Total 1 task + 1 fix** | | | | | **~58K tokens** |

**With 2 fix-loops (spec rejected → fix → quality rejected → fix):** ~78K tokens.

### What prompt caching does NOT solve

**The architectural waste: duplicate file reads.**

Spec-reviewer and code-quality-reviewer read the SAME files in separate sessions. Prompt caching cannot help because:
- `read` tool results are injected into the session's message history (unique per subagent)
- Provider caching works on API request prefixes, not on tool call results across different sessions
- Each reviewer session has a different system prompt → different cache keys

This means **10K of code is read 3 times** (implementer + spec-reviewer + quality-reviewer) = 30K tokens just for file access. This is the single biggest cost driver in the workflow.

### Impact of the "no parallel implementers" rule

Superpowers forbids parallel implementer dispatch: *«Never: Dispatch multiple implementation subagents in parallel (conflicts)»*. This is correct for a single working copy. However, with git worktrees (separate working copies), parallel dispatch IS safe — see Section 4 below.

### Cost projections for a feature

A medium feature (5 tasks, 1 fix-loop average):

- **Per task:** ~58K tokens
- **5 tasks:** ~290K tokens
- **+ docser:** ~10K tokens
- **+ finishing:** ~5K tokens
- **Total feature input tokens:** **~305K**

At typical model pricing (~$1-3/M input, ~$5-15/M output for capable models), a single feature costs **~$1.50-$6.00 in API costs** for subagents alone, plus @architect's own session.

### Requests

Add a **Cost Model** appendix to the spec that:
1. States clearly: each subagent spawn = fresh API call, no context inheritance
2. Estimates token cost per task (implementer + 2 reviewers + fix-loops) — use tables above
3. Provides guidance on when to use cheap models for reviewers vs. when to upgrade
4. Recommends consolidating spec-reviewer and code-quality-reviewer into ONE agent when using cheap models for both (saves ~30-40% on duplicate file reads)
5. Adds model selection guidance: cheap models for small diffs (< 200 lines), standard for medium, capable for architectural changes
6. **Recommends setting token budgets**: e.g., "if task accumulates > 100K tokens in fix-loops → escalate to human"

---

## 2. @tester removal — gap in quality verification

### Problem

The spec removes @tester with rationale «TDD absorbed into implementers». However:

1. **Self-review bias:** Implementer writes tests for their own mental model of the code, not for actual behavior. Edge cases, boundary conditions, and integration regressions are systematically missed.

2. **No independent test execution:** Spec-reviewer and code-quality-reviewer (both `edit: deny`) **never run the test suite**. They only read code. A passing test that tests the wrong thing passes both reviews unnoticed.

3. **The gap:**

```
Current:     implementer → @tester (runs tests, writes edge cases) → verified
Spec:        implementer → spec-reviewer (reads code) → quality-reviewer (reads code) → ??? (no test run)
```

Nobody verifies: test correctness, test coverage of acceptance criteria, regression in unrelated modules.

### Concrete example

Implementer builds ActivityCard. TDD: writes a render test. Green. Reports DONE. Reviewers see code exists, plan says "card component" — ✅. But nobody noticed: card doesn't compress below 90px, artist color is hardcoded, private corner-cut missing. Tests don't cover these because implementer never thought of them.

### Proposed solutions (ranked)

**Option A — Keep @tester after reviewers (highest quality):**
```
implementer → spec-reviewer → code-quality-reviewer → @tester → docser
```
@tester receives diff + acceptance criteria, writes independent tests, runs full suite, reports pass/fail with specifics.

**Option B — Expand code-quality-reviewer (cheapest):**
Give code-quality-reviewer `bash: "vitest*" | "pytest*"`. Require test execution as part of quality gate:
```markdown
## Required: Test Execution
- Run full test suite: `npx vitest run` / `pytest`
- Report total/passed/failed with failure details
- Verify acceptance criteria have test coverage
- Failures → Critical issue, do NOT approve
```

**Option C — Structured implementer self-report (lightest):**
Add mandatory fields to implementer report:
```markdown
- **Test output**: paste actual terminal output (not just "5/5 passed")
- **Coverage map**: which acceptance criteria → which test
- **Edge cases**: explicitly list what was tested beyond happy path
- **Self-review**: what would a reviewer flag
```

### Recommendation

**Option B** — minimal spec change, closes the verification gap without a new agent.

---

## 3. Consolidate reviewers into single @reviewer agent

### Rationale

When both reviewers use the same cheap model (`deepseek-v4-flash-free`), having two separate agents creates waste:

1. **Duplicate file reads:** Both read the same diff/files in separate sessions. Not cacheable (see Section 1).
2. **Token overhead:** Two system prompts, two task prompts, two rounds of output.
3. **No quality benefit:** If they use the same model, two sequential passes don't add more insight than one combined pass.

### Proposal

Replace spec-reviewer + code-quality-reviewer with **one @reviewer** agent:

```yaml
---
description: Code reviewer. Verifies spec compliance AND code quality in one pass.
mode: subagent
model: opencode/deepseek-v4-flash-free  # or upgrade for critical tasks
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
    "vitest*": allow     # ← also runs tests!
    "pytest*": allow
    "*": deny
  task:
    "*": deny
---
```

**Report format:**

```markdown
## Spec Compliance
✅ / ❌ [specific issues with file:line]

## Code Quality
- Strengths: ...
- Issues: Critical / Important / Minor
- Assessment: Approved / Needs work

## Test Results
- Command: `npx vitest run`
- N/N passing
- Failures: [details if any]
```

### Cost savings

- 2 agent spawns → 1 agent spawn (~40% reduction)
- 2 file reads → 1 file read (~50% reduction on the biggest cost driver)
- Plus: test execution integrated (no separate @tester needed)

### When to keep separate reviewers

If the project upgrades code-quality-reviewer to a more capable model while keeping spec-reviewer cheap — then separation makes sense (different models, different roles). But with both on `deepseek-v4-flash-free` — consolidate.

---

## 4. Worktree parallelism (currently missing from spec)

### Current state

Spec Step 4: *«FOR each task»* — strictly sequential. Worktrees provide isolation but not parallelism.

### Opportunity

Superpowers already has `dispatching-parallel-agents` SKILL (for debugging independent test failures). Same pattern applies to implementation — if tasks operate on disjoint file sets, they can run in parallel:

**Wave-based parallel dispatch:**

```markdown
4.1. Dependency Analysis
   - Build dependency graph from plan tasks
   - Wave 1: tasks with zero dependencies on other tasks
   - Wave 2: tasks depending only on Wave 1 results
   - Wave N: tasks depending on previous waves

4.2. Parallel Wave Dispatch
   For each task in the current wave IN PARALLEL:
   a. Create worktree: `git worktree add .worktrees/task-<N>-<name> -b feat/task-<N>`
   b. Run setup (npm install / pip install)
   c. Verify baseline tests
   d. Dispatch implementer subagent → worktree path

4.3. Wait for ALL implementers in wave to complete

4.4. Parallel Review per task
   For each completed task:
   - Dispatch reviewer (reviews can be parallel since different worktrees)

4.5. Wave Merge
   - Merge all task branches into wave-integration branch
   - Run full test suite
   - Resolve conflicts (if two tasks touch same file)
   - Merge to feature branch

4.6. Next Wave
```

### Constraints

- **Same-file conflict detection:** Before dispatching a wave, verify no two tasks modify the same file. If they do → sequentialize.
- **Integration testing:** Wave merge step catches cross-task regressions.
- **Superpowers says NEVER parallel implementers?** That rule is for single-session, single-repo scenarios. With worktrees (separate working copies), parallel is safe.

### Applicability to Memo

| Phase | Parallelizable? |
|-------|----------------|
| Foundation (layout, design-system) | ❌ Everything depends on everything |
| P1 components (WeekView, ActivityCard, Toolbar) | ✅ Parallel after foundation exists |
| P1 features (DnD, stamp, modal) | ✅ Parallel — independent concerns |

---

## 5. Context Management rewording (Section 11)

### Problem

Current wording: «controller does NOT preload full project context» contradicts «provide scene-setting, dependencies, what was done in previous tasks».

### Proposed replacement

```markdown
## 11. Context Management Strategy

### Two-Tier Context Model

The controller (@architect) and implementers own different layers of context:

| Tier | Owner | Contains | Example |
|------|-------|----------|---------|
| **Architectural** | @architect | Component tree, data flow, task dependencies, interface contracts, scene-setting | "ActivityCard renders inside DayColumn, receives data from useSchedule(), depends on Sidebar being ready" |
| **Implementation** | @frontend-coder / @backend-coder | Design tokens, API schemas, mock data, stack conventions, code patterns | Colors #1E2D2F/#004D56, Tailwind classes, import paths, Pydantic models |

### What @architect passes in task prompt

**Required:**
- Task description verbatim from plan
- Architectural position: where this fits, what it depends on, what depends on it
- Interface contracts: props, context shape, API signatures of adjacent components
- Document references (paths, NOT content — subagent reads them)
- Working directory path
- Required skill invocation (TDD, etc.)

**NOT passed** (subagent reads from docs via its own agent.md instructions):
- Color hex codes, font sizes, spacing values → `docs/v4-design-system.md`
- API endpoint URLs, request/response schemas → `docs/memo-full-spec.md`
- Mock data structures → `docs/mock-data.md`

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
```

---

## 6. Reviewer template mechanism clarification (Section 4)

### Problem

Spec calls reviewer prompt templates «Project Skills» with YAML frontmatter (`name:`, `description:`). This creates confusion:

- In OpenCode, `skill` tool loads skill into **caller's** context, not subagent's
- If @architect calls `skill("spec-reviewer-template")` → template loads into @architect's session (useless)
- Reviewer needs the template in ITS context, not architect's

### How it actually works (correct mechanism)

1. @architect uses `read` tool (NOT `skill` tool) to read `.opencode/skills/reviewers/spec-reviewer.md`
2. @architect replaces `{PLACEHOLDERS}` with actual values
3. @architect passes filled result as `prompt` to `task(subagent_type="spec-reviewer", prompt=...)`

### Proposed fix

Rename Section 4 from «Reviewer Prompt Templates (Project Skills)» → «Reviewer Prompt Templates». Remove `name:` and `description:` from template frontmatter (or add explicit instruction: «@architect reads via `read` tool, NOT `skill` tool»).

Updated template format:

```markdown
# Spec Compliance Review

## Review Task
Review whether the implementation matches its specification.

## What Was Requested
{PLAN_TASK_FULL_TEXT}

## What Implementer Claims They Built
{IMPLEMENTER_REPORT}

## CRITICAL: Do Not Trust the Report
The implementer may be incomplete or optimistic. Verify independently by reading actual code.

## Your Job
1. Missing requirements
2. Extra/unneeded work
3. Misunderstandings

Report: ✅ Spec compliant / ❌ Issues found [file:line references]
```

---

## Summary of requests

| # | Request | Priority | Impact |
|---|---------|----------|--------|
| 1 | Add Cost Model appendix — subagent spawn cost analysis, caching boundaries, feature cost projections | 🔴 CRITICAL | Prevents budget surprises; reveals duplicate file reads as #1 cost driver |
| 2 | @tester: add Option B — expand quality reviewer with mandatory test execution | 🔴 HIGH | Closes verification gap (reviewers don't run tests) |
| 3 | Consolidate 2 reviewers into 1 @reviewer agent with integrated test execution | 🟡 MEDIUM | 30-40% token cost reduction; eliminates duplicate file reads |
| 4 | Add wave-based parallel dispatch using worktrees | 🟡 MEDIUM | 3-5x speedup for independent tasks; uses worktree isolation correctly |
| 5 | Reword Section 11 — two-tier context model (architectural vs. implementation) | 🟢 LOW | Removes contradiction; clarifies accountability |
| 6 | Fix Section 4 — templates use `read` not `skill`; remove misleading "Project Skills" label | 🟢 LOW | Prevents implementation confusion |
