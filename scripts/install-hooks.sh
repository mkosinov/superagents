#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null || echo "")"

if [ -z "$GIT_DIR" ]; then
  echo "Not a git repository. Skipping hook installation." >&2
  exit 0
fi

HOOKS_DIR="$GIT_DIR/hooks"
SOURCE_HOOK="$SCRIPT_DIR/git-hooks/pre-commit"
DEST_HOOK="$HOOKS_DIR/pre-commit"

if [ -f "$DEST_HOOK" ] && [ ! -L "$DEST_HOOK" ]; then
  echo "pre-commit hook already installed (not a symlink). Skipping." >&2
  exit 0
fi

[ -L "$DEST_HOOK" ] && rm "$DEST_HOOK"

cp "$SOURCE_HOOK" "$DEST_HOOK"
chmod +x "$DEST_HOOK"
echo "Installed pre-commit hook → $DEST_HOOK"
