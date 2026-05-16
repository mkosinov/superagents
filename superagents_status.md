# Superagents v3.0 — Status

> **Last updated:** 2026-05-15  
> **Spec:** `SUPERAGENTS_SPEC_v3.md`  
> **Project:** Memo (Colour Mountains art studio management system)

---

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Localize Superpowers Skills (8 skills in `.opencode/skills/superpowers/`) | ✅ Done |
| **Phase 2** | New Agent Files: `spec-reviewer.md`, `code-quality-reviewer.md` | ✅ Done |
| **Phase 3** | Reviewer Templates: `.opencode/skills/reviewers/` (2 templates) | ✅ Done |
| **Phase 4** | Existing Agent Updates (architect, frontend-coder, backend-coder, debugger, docser) | ✅ Done |
| **Phase 5** | Infrastructure: .gitignore, docs/, archive legacy, scratchpad | ✅ Done |
| **Phase 6** | Proof-of-Concept: End-to-end workflow run | ⏳ Pending |

---

## Agent Architecture

| # | Agent | Mode | Model | Status | Source |
|---|-------|------|-------|--------|--------|
| 1 | **@architect** | primary | opencode-go/kimi-k2.6 | ✅ Updated | @manager merged into @architect |
| 2 | **@frontend-coder** | subagent | opencode-go/qwen3.6-plus | ✅ Updated | + TDD, report format, skill perm |
| 3 | **@backend-coder** | subagent | opencode-go/qwen3.6-plus | ✅ Updated | + FastAPI TDD, report format, skill perm |
| 4 | **@debugger** | subagent | opencode-go/qwen3.6-plus | ✅ Updated | + systematic-debugging skill |
| 5 | **@docser** | subagent | opencode/deepseek-v4-flash-free | ✅ Updated | + Meta Docs Only, feature branch commit |
| 6 | **@deployer** | subagent | opencode/deepseek-v4-flash-free | ✅ Unchanged | Outside Superpowers workflow |
| 7 | **@spec-reviewer** | subagent | opencode/deepseek-v4-flash-free | ✅ **NEW** | Spec compliance, read-only |
| 8 | **@code-quality-reviewer** | subagent | opencode/deepseek-v4-flash-free | ✅ **NEW** | Code quality + test execution |

### Removed / Archived
| File | Action | Reason |
|------|--------|--------|
| `manager.md` → `manager.md.ARCHIVED` | Archived | Merged into @architect |
| `tester.md` → `tester.md.ARCHIVED` | Archived | TDD absorbed into implementers; test execution → code-quality-reviewer |
| `git-flow.md` → `git-flow.md.ARCHIVED` | Archived | Replaced by Superpowers skills (using-git-worktrees) |
| `superpowers-local/` | Deleted | Full 8-skill set exists in `superpowers/` |

---

## Skills (`.opencode/skills/superpowers/`)

| Skill | Name | Status |
|-------|------|--------|
| `using-superpowers` | Skill invocation rules | ✅ Existing |
| `brainstorming` | Design brainstorming (G1) | ✅ Existing |
| `writing-plans` | Implementation plans (G2) | ✅ Existing |
| `using-git-worktrees` | Worktree creation (G3) | ✅ Existing |
| `subagent-driven-development` | Subagent dispatch loop (G4-G6) | ✅ Existing |
| `test-driven-development` | RED-GREEN-REFACTOR (G4) | ✅ Existing |
| `finishing-a-development-branch` | Merge/PR/Keep/Discard (G7) | ✅ Existing |
| `systematic-debugging` | 4-phase bug investigation | ✅ Existing |

## Reviewer Templates (`.opencode/skills/reviewers/`)

| Template | Purpose | Status |
|----------|---------|--------|
| `spec-reviewer.md` | Placeholder template for spec compliance review | ✅ Created |
| `code-quality-reviewer.md` | Placeholder template for quality review + test run | ✅ Created |

---

## Infrastructure

| Item | Status |
|------|--------|
| `.worktrees/` in `.gitignore` | ✅ Added |
| `docs/superpowers/specs/` | ✅ Created |
| `docs/superpowers/plans/` | ✅ Created |
| `.opencode/scratchpad.md` | ✅ Replaced (Section 9 format) |
| `~/.config/opencode/update-infrastructure.sh` | ✅ Run |
| `.opencode/opencode.jsonc` | ❌ Not needed (no plugin required) |

---

## Workflow Gates

| Gate | Name | Applies to | Implemented in |
|------|------|------------|----------------|
| G1 | Design Approval | All | @architect → Step 1 |
| G2 | Plan Approval | All | @architect → Step 2 |
| G3 | Clean Baseline | All | @architect → Step 3 |
| G4 | TDD Compliance | All | @frontend-coder / @backend-coder agent prompts |
| G4a | Architect Spot-Check | Trivial only | @architect → Step 4d |
| G5 | Spec Compliance | Small, Standard, Large | @spec-reviewer agent |
| G6 | Code Quality + Tests | Standard, Large | @code-quality-reviewer agent |
| G6a | Review Loop Limit (max 3) | Small, Standard, Large | @architect → Step 4e |
| G7 | Final Tests + Merge Choice | All | @architect → Step 6 |

---

## Decisions Applied

Per user clarification during implementation:
1. ✅ `superpowers-local/` deleted (8 skills in `superpowers/` sufficient)
2. ✅ `manager.md` / `tester.md` archived (`.ARCHIVED`), not deleted
3. ✅ `scratchpad.md` replaced entirely with new format
4. ✅ `verification-before-completion` omitted from debugger prompt
5. ✅ `opencode.jsonc` not created (no plugin needed)
6. ✅ `git-flow.md` archived (replaced by Superpowers skills)

---

## Next: Phase 6 — Proof-of-Concept

Run full Superpowers workflow end-to-end with a small feature:
1. Brainstorming → design doc
2. Writing-plans → plan file with classification
3. Git worktree → isolated workspace
4. Subagent-driven-development → tasks with TDD + tier-specific review
5. Doc commit into branch
6. Finishing → create PR
