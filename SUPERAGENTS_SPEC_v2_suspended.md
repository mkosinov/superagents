# Superpowers Integration — Suspended Proposals

> **Version:** 2.0  
> **Date:** 2026-05-15  
> **Status:** Postponed or rejected proposals from `SUPERAGENTS_SPEC_v2.md` review.  
> **Purpose:** Archive for future reconsideration when project scales beyond MVP.

---

## Proposal 3: Consolidate spec-reviewer + code-quality-reviewer into one @reviewer agent

**Source:** `request_to_superagents_spec.md`, Section 3  
**Status:** **REJECTED**  
**Decision date:** 2026-05-15

### Original Proposal

Replace spec-reviewer + code-quality-reviewer with one combined agent:

```yaml
---
description: Code reviewer. Verifies spec compliance AND code quality in one pass.
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
    "vitest*": allow
    "pytest*": allow
    "*": deny
  task:
    "*": deny
---
```

**Claimed savings:** 30–40% token reduction (2 agent spawns → 1, 2 file reads → 1).

### Why Rejected

1. **Two-stage review = core Superpowers principle.**  
   `subagent-driven-development` SKILL.md:  
   > "Two-stage review (spec then quality) = high quality, fast iteration"  
   > "Never: Start code quality review before spec compliance is ✅"  
   
   Spec reviewer answers: **"Built the right thing?"**  
   Quality reviewer answers: **"Built it right?"**  
   These are orthogonal questions. A combined reviewer may answer "well-built" and miss "wrong thing built."

2. **Cost problem already solved.**  
   In v2.0, reviewers receive `git diff` embedded in prompt (not file paths). Duplicate file reads eliminated. Savings from consolidation would be marginal (~2K tokens for second system prompt) compared to lost quality gate.

3. **Gate ordering is sequential by design.**  
   If spec fails → no point in quality review. Separate agents enforce this ordering architecturally. Combined agent might produce a mixed report that obscures the "stop here" signal.

### When to Reconsider

- If project upgrades to **different models** for each reviewer (e.g., spec-reviewer on cheap model, quality-reviewer on capable model). Then separation provides model-selection flexibility that consolidation loses.
- If token costs become prohibitive AND quality metrics prove single reviewer is sufficient (data-driven decision).

---

## Proposal 4: Wave-based Parallel Dispatch Using Worktrees

**Source:** `request_to_superagents_spec.md`, Section 4  
**Status:** **POSTPONED**  
**Decision date:** 2026-05-15  
**Revisit condition:** Project grows to 30+ independent components OR CI/CD pipeline matures.

### Original Proposal

Instead of sequential `FOR each task`, analyze dependencies and dispatch independent tasks in parallel waves:

```markdown
4.1. Dependency Analysis
   - Build dependency graph from plan tasks
   - Wave 1: tasks with zero dependencies on other tasks
   - Wave 2: tasks depending only on Wave 1 results
   - Wave N: tasks depending on previous waves

4.2. Parallel Wave Dispatch
   For each task in the current wave IN PARALLEL:
   a. Create worktree: `git worktree add .worktrees/task-<N>-<name> -b feat/task-<N>`
   b. Run setup
   c. Verify baseline tests
   d. Dispatch implementer subagent → worktree path

4.3. Wait for ALL implementers in wave to complete

4.4. Parallel Review per task
   For each completed task:
   - Dispatch reviewer

4.5. Wave Merge
   - Merge all task branches into wave-integration branch
   - Run full test suite
   - Resolve conflicts
   - Merge to feature branch

4.6. Next Wave
```

### Why Postponed

1. **Violates `subagent-driven-development` skill.**  
   SKILL.md, Red Flags:  
   > "Never: Dispatch multiple implementation subagents in parallel (conflicts)"  
   
   This rule exists for single-working-copy scenarios. Worktrees provide isolation, but the skill was designed assuming shared state. Parallel dispatch is safe technically but breaks the methodology's tested assumptions.

2. **Over-engineering for MVP scope.**  
   Current Memo project (deadline 2026-05-20):  
   - ~8 total tasks across all features  
   - Tasks are sequential by nature (foundation → layout → components → features)  
   - No natural "waves" of independent tasks exist yet  
   
   Parallelism adds complexity (dependency graph, sync points, merge conflict resolution) with zero benefit at current scale.

3. **Complexity exceeds @architect capability.**  
   Wave dispatch requires:  
   - Static dependency analysis (which tasks touch which files)  
   - Conflict detection and resolution  
   - Integration test after wave merge  
   
   These are CI/CD pipeline responsibilities, not LLM controller responsibilities. Offload to GitHub Actions, not @architect.

4. **Token cost doesn't justify speed gain.**  
   At current scale, sequential execution completes in ~2–3 hours per feature. Parallel would save ~30 minutes but add significant complexity and risk.

### When to Reconsider

**Trigger conditions (ALL must be true):**
1. Project has 30+ tasks that are demonstrably independent (different subsystems, no shared files)
2. CI/CD pipeline handles merge and integration testing automatically
3. Cost of sequential execution exceeds $10/feature OR timeline pressure demands 3x speedup
4. Superpowers skill itself is updated to officially support parallel dispatch

**Implementation path if triggered:**
- Build dependency graph automatically from plan file analysis
- Use GitHub Actions matrix builds for parallel task execution (not @architect)
- @architect dispatches waves to CI, not to individual subagents
- Review happens after wave merge, not per-task

---

## Summary

| # | Proposal | Status | Rationale | Revisit When |
|---|----------|--------|-----------|--------------|
| 3 | Consolidate reviewers | REJECTED | Two-stage review is core principle; cost already solved by git diff | Token costs prohibitive + data proves sufficiency |
| 4 | Wave parallelism | POSTPONED | Violates skill, overkill for 8 tasks, belongs in CI/CD | 30+ independent tasks + CI/CD mature + cost/time pressure |

---

## Archive Policy

- Review suspended proposals monthly or when project scope significantly expands.
- If reconsidering, create new proposal document referencing this archive.
- Do NOT modify this file — append new decisions at the bottom with date and rationale.
