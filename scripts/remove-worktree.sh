#!/bin/bash
# remove-worktree.sh <branch-name>
# Removes a git worktree and optionally deletes the branch

set -e

BRANCH=$1

if [ -z "$BRANCH" ]; then
  echo "Usage: $0 <branch-name>"
  exit 1
fi

WORKTREE_DIR=".worktrees/$BRANCH"

# Check if worktree exists
if [ ! -d "$WORKTREE_DIR" ]; then
  echo "Error: worktree not found at $WORKTREE_DIR"
  exit 1
fi

# Check if we're inside the worktree
CURRENT_DIR=$(pwd)
WORKTREE_ABS=$(cd "$WORKTREE_DIR" && pwd)

if [[ "$CURRENT_DIR" == "$WORKTREE_ABS"* ]]; then
  echo "Error: Cannot remove worktree while inside it. cd to project root first."
  exit 1
fi

echo "Removing worktree at $WORKTREE_DIR..."
git worktree remove "$WORKTREE_DIR" --force

echo "Worktree removed."

# Ask about branch deletion
if git show-ref --verify --quiet "refs/heads/$BRANCH" 2>/dev/null; then
  echo ""
  echo "Branch '$BRANCH' still exists."
  echo "To delete it: git branch -d $BRANCH"
  echo "To force delete (unmerged changes): git branch -D $BRANCH"
fi
