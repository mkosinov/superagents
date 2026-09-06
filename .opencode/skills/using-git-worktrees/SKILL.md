---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans — detect existing isolation, then create or remove worktrees only via scripts/create-worktree.sh and scripts/remove-worktree.sh
---

# Using Git Worktrees

## Overview

Work happens in an isolated workspace. **Do not hand-roll** `git worktree add`, env copies, or dependency wiring — **run the scripts** from the repository root.

**Core principle:** Detect existing isolation first. **Always use the scripts.** Never fight the harness.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an isolated workspace."

## Step 0: Detect Existing Isolation

**Before creating anything, check if you are already in an isolated workspace.**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

**Submodule guard:** `GIT_DIR != GIT_COMMON` is also true inside git submodules. Before concluding "already in a worktree," verify you are not in a submodule:

```bash
git rev-parse --show-superproject-working-tree 2>/dev/null
```

**If `GIT_DIR != GIT_COMMON` (and not a submodule):** You are already in a linked worktree. Skip to Step 3. Do NOT run `create-worktree.sh`.

Report with branch state:
- On a branch: "Already in isolated workspace at `<path>` on branch `<name>`."
- Detached HEAD: "Already in isolated workspace at `<path>` (detached HEAD, externally managed). Branch creation needed at finish time."

**If `GIT_DIR == GIT_COMMON` (or in a submodule):** You are in a normal repo checkout. Proceed to Step 1.

## Step 1: Create Worktree (script required)

From the **repository root** (not inside an existing `.worktrees/...` checkout unless Step 0 said otherwise):

```bash
./scripts/create-worktree.sh <branch-name>
```

**You must run this script** — it creates `.worktrees/<branch-name>` and performs post-create setup (env, JS/Python deps). Do not duplicate that setup by hand.

- **Success:** follow the script’s final `cd` hint (typically `cd .worktrees/<branch-name>`).
- **Failure:** stop; report stderr/stdout. Fix only as the script suggests (e.g. retry `pnpm install` inside the worktree path it printed).

Implementation details live in `scripts/create-worktree.sh` — read there only if debugging.

## Step 2: Verify .gitignore

**Ensure `.worktrees/` is in `.gitignore`:**

```bash
git check-ignore -q .worktrees 2>/dev/null
```

If NOT ignored, add it and commit:

```bash
echo ".worktrees/" >> .gitignore
git add .gitignore
git commit -m "chore: add .worktrees to gitignore"
```

## Step 3: Verify Clean Baseline

From the isolated workspace path, run tests to ensure a clean start:

```bash
# Use project-appropriate command
pnpm test / npm run test:all / cargo test / pytest / go test ./...
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

## Removing a Worktree (script required)

From the **repository root** (never from inside the worktree being removed):

```bash
./scripts/remove-worktree.sh <branch-name>
```

**You must run this script** — do not only `rm -rf .worktrees/...` or `git worktree remove` without the script’s guards.

Branch deletion is separate; the script only reminds you if the branch still exists.

## Red Flags

**Never:**
- Create a worktree when Step 0 detects existing isolation
- Run `git worktree add` or copy env / link `node_modules` manually instead of `create-worktree.sh`
- Create worktree without verifying `.worktrees/` is in `.gitignore`
- Skip baseline test verification
- Proceed with failing tests without asking
- Remove a worktree while inside it (use `remove-worktree.sh` from project root)
