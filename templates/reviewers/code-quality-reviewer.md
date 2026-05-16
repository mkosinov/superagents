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
- Frontend: `cd {WORKTREE_PATH}/frontend && npx vitest run`
  - If vitest hangs, try: `npx vitest run --pool forks`
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
