---
name: finishing-a-development-branch
description: Use when implementation is complete, all tests pass, and you need to finish the work - the default is auto push+PR+auto-merge after green CI, notifying the user before push and contacting them only on error
---

# Finishing a Development Branch

## Overview

Finish development work by **automatically** pushing, opening a PR, and auto-merging
after CI goes green. The user is **notified** before the push (fire-and-continue) and is
**contacted only when something goes wrong**.

**Core principle:** Verify tests → Detect environment → Notify → Push + PR + auto-merge on green CI → Clean up. Contact the user ONLY on error.

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before finishing, verify tests pass:**

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Detect Environment

**Determine workspace state before the auto-flow:**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
```

This determines the default flow and how cleanup works:

| State | Default flow | Cleanup |
|-------|--------------|---------|
| `GIT_DIR == GIT_COMMON` (normal repo) | Auto push + PR + auto-merge | No worktree to clean up |
| `GIT_DIR != GIT_COMMON`, named branch | Auto push + PR + auto-merge | Provenance-based |
| `GIT_DIR != GIT_COMMON`, detached HEAD | Auto push (as new branch) + PR + auto-merge | No cleanup |

### Step 3: Determine Base Branch

```bash
# Try common base branches
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 4: Notify (fire-and-continue)

**Do NOT present a menu and do NOT wait for a reply.** Print a SHORT notification and
proceed immediately to Step 5:

```
Финиш: пушу ветку <feature-branch> + создаю PR + авто-мерж после зелёного CI.
```

For detached HEAD, note the new branch name:

```
Финиш: детач-HEAD → пушу как новую ветку <feature-branch> + создаю PR + авто-мерж после зелёного CI.
```

**Don't add explanation** - keep the notification to one line, then continue.

### Step 5: Auto Push + PR + Auto-merge (DEFAULT)

This is the default success-path flow. Run it automatically after the notification.
**Contact the user ONLY on error** (push failure, PR creation error, red CI, merge error).

```bash
# Push branch (pre-push hook is disabled — CI runs on GitHub Actions)
if ! git push -u origin <feature-branch>; then
  echo "❌ Push failed for <feature-branch>."
  # STOP — report to user, preserve worktree for fixes. Do NOT continue.
  exit 1
fi

# Create PR
if ! gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Test Plan
- [x] CI checks pass (GitHub Actions)
EOF
)"; then
  echo "❌ PR creation failed."
  # STOP — report to user with the push state. Preserve worktree.
  exit 1
fi

# Get PR URL for reporting
PR_URL=$(gh pr view --json url -q .url)
echo "PR created: $PR_URL"
echo "Waiting for CI checks to complete (may take 5-15 min)..."

# Poll CI checks until completion
# gh pr checks --watch blocks until all checks conclude, then:
#   exit 0 = all passed, exit 1 = some failed
if gh pr checks --watch; then
  echo "✅ All CI checks passed. Auto-merging..."
  if ! gh pr merge --squash --delete-branch --subject "<title>" --body "Auto-merged: all CI checks passed."; then
    echo "❌ Merge command failed."
    echo "PR: $PR_URL — report to user. Preserve worktree."
    # STOP — do NOT clean up worktree.
    exit 1
  fi
  # Update local main
  git checkout <base-branch>
  git pull origin <base-branch>
  # NOTE: spec/plan doc commits are pushed to main at G1b/G2 approval time, so this pull is
  # normally a clean fast-forward. If it FAILS because local main has diverged (unpushed doc
  # commits from an older workflow), STOP and contact the user — do NOT `reset --hard` silently
  # (risks losing unpushed commits).
else
  echo "❌ CI checks failed (red). NOT auto-merging."
  echo "PR: $PR_URL — report to user. Preserve worktree for fixes."
  # STOP — do NOT clean up worktree.
  exit 1
fi
```

**On success (all CI green + merged):** cleanup worktree (Step 6), delete local branch.

**On ANY error — STOP and contact the user:**
- Push fails → report the failure, preserve worktree.
- PR creation errors → report the error, preserve worktree.
- CI is red / checks fail → report to user with PR URL. Do NOT auto-merge.
- Merge command errors → report to user with PR URL. Do NOT auto-merge.

In all error cases: preserve the worktree (user may need to push fixes) and let the user decide the next action.

### Step 5.1: Explicit User-Requested Fallbacks (NOT the default)

The default flow above always applies unless the **user explicitly asks** for one of these
alternatives. These are no longer offered as a menu — only run them on explicit request.

#### Fallback: Merge Locally (only if user explicitly asks)

```bash
# Get main repo root for CWD safety
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"

# Merge first — verify success before removing anything
git checkout <base-branch>
git pull
git merge <feature-branch>

# Verify tests on merged result
<test command>

# Only after merge succeeds: cleanup worktree (Step 6), then delete branch
git branch -d <feature-branch>
```

#### Fallback: Keep As-Is (only if user explicitly asks)

Report: "Keeping branch <name>. Worktree preserved at <path>."

**Don't cleanup worktree.**

#### Fallback: Discard (only if user explicitly asks)

**Confirm first:**
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed:
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
```

Then: Cleanup worktree (Step 6), then force-delete branch:
```bash
git branch -D <feature-branch>
```

### Step 5.5: Suggest Post-Merge Reflection

After the PR is created (default flow) or the branch is merged locally (fallback), **suggest to user** running reflection analysis. This is not auto-run — human decides.

```bash
# Extract wave name from branch (e.g., "Wave 4.5" from "Wave 4.5 старт" or PR title)
WAVE_NAME=$(git log -1 --format='%s' | grep -oE 'Wave [0-9.]+' | head -1)
[ -z "$WAVE_NAME" ] && WAVE_NAME="<ask user>"

# Suggest to user:
echo "Wave complete. Recommended next step:"
echo "  reflect.sh wave --name=\"$WAVE_NAME\""
echo "Or run /reflect in the next session for in-session analysis."
```

**Why not auto-run:** Retrospection principle. Reflection after the fact is more useful than pre-block. User reviews proposals at their own pace.

**For the default PR flow:** Suggestion is forward-looking — when the PR is merged, run `/reflect` or `reflect.sh wave`. Don't run it now (wave isn't on main yet).

### Step 6: Cleanup Workspace

**Runs on the default success path (after auto-merge) and for the explicit "merge locally" / "discard" fallbacks.** The "keep as-is" fallback and any error path always preserve the worktree.

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
WORKTREE_PATH=$(git rev-parse --show-toplevel)
```

**If `GIT_DIR == GIT_COMMON`:** Normal repo, no worktree to clean up. Done.

**If worktree path is under `.worktrees/`, `worktrees/`, or `~/.config/worktrees/`:** We own cleanup.

```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git worktree remove "$WORKTREE_PATH"
git worktree prune  # Self-healing: clean up any stale registrations
```

**Otherwise:** The host environment (harness) owns this workspace. Do NOT remove it.

### Step 7: Report Board-Update Facts to @manager (mandatory)

After a successful merge, the architect does NOT touch the GH Project board — board updates are @manager's decision and responsibility. The architect's only duty: include this block in the DONE report so the manager has the facts:

```
## Board Update Needed
- Issue: #N (or "no issue — FasTP fix without issue")
- Next Up: was 1|2|3|not in queue
```


## Quick Reference

| Flow | Trigger | Merge | Push | Keep Worktree | Cleanup Branch |
|------|---------|-------|------|---------------|----------------|
| **Auto push + PR + auto-merge** (default) | success path | yes (after CI green) | yes | - (after merge) | yes |
| Merge locally (fallback) | user asks explicitly | yes | - | - | yes |
| Keep as-is (fallback) | user asks explicitly | - | - | yes | - |
| Discard (fallback) | user asks explicitly | - | - | - | yes (force) |
| Error (push/PR/CI/merge) | anything goes wrong | no | maybe | yes (preserved) | no |

## Red Flags

**Never:**
- Proceed with failing tests
- Merge on red / failing CI
- Merge without verifying tests on result
- Auto-merge when any error occurred — STOP and contact the user instead
- Clean up a worktree on any error path (user may need it for fixes)
- Delete work without confirmation
- Force-push without explicit request
- Remove a worktree before confirming merge success
- Clean up worktrees you didn't create (provenance check)
- Run `git worktree remove` from inside the worktree
- `reset --hard` local main on a divergent pull — unpushed DESIGN-phase doc commits should not
  exist (they are pushed at G1b/G2); if they do, stop and ask the user

**Always:**
- Verify tests before finishing
- Detect environment before the auto-flow
- Notify before push (one line, fire-and-continue — do NOT wait for a reply)
- Contact the user ONLY on error (push failure, PR error, red CI, merge error)
- Get typed confirmation before the discard fallback
- Clean up worktree only on the default merge success path and the explicit merge-locally / discard fallbacks
- `cd` to main repo root before worktree removal
- Run `git worktree prune` after removal
