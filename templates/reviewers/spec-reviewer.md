# Spec Compliance Review

## Review Task
Review whether the implementation matches its specification.

## Working Directory
{WORKTREE_PATH}

## What Was Requested
{PLAN_TASK_FULL_TEXT}

## What Implementer Claims They Built
{IMPLEMENTER_REPORT}

## Git Diff
```diff
{GIT_DIFF_OUTPUT}
```

## CRITICAL: Do Not Trust the Report
The implementer may be incomplete or optimistic. You MUST verify independently:
1. **Analyze the git diff above** — check every change for spec alignment
2. **Read files from disk** — use the Read tool with paths rooted at the Working Directory to confirm actual file contents
3. **Run `git log --oneline`** to verify commit history in the Working Directory

## Your Job
1. Missing requirements
2. Extra/unneeded work
3. Misunderstandings

Report:
- ✅ Spec compliant / ❌ Issues found [file:line references]
