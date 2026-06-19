#!/usr/bin/env bash
set -uo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <project-path>" >&2
  exit 2
fi

PROJECT="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRAMEWORK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$FRAMEWORK_ROOT/skills"
TARGET_DIR="$PROJECT/.opencode/skills"

if [ ! -d "$PROJECT" ]; then
  echo "MISSING: project path does not exist: $PROJECT" >&2
  exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
  echo "ERROR: framework skills dir does not exist: $SOURCE_DIR" >&2
  exit 1
fi

ISSUES=0

for skill_dir in "$SOURCE_DIR"/*/; do
  [ -d "$skill_dir" ] || continue
  skill_name="$(basename "$skill_dir")"
  source_file="$skill_dir/SKILL.md"
  target_file="$TARGET_DIR/$skill_name/SKILL.md"

  if [ ! -f "$source_file" ]; then
    continue
  fi

  if [ ! -f "$target_file" ]; then
    echo "  [MISSING] $skill_name — skill not in $TARGET_DIR"
    ISSUES=$((ISSUES + 1))
  elif ! diff -q "$source_file" "$target_file" > /dev/null 2>&1; then
    echo "  [DRIFT]   $skill_name — content differs"
    ISSUES=$((ISSUES + 1))
  fi
done

if [ "$ISSUES" -gt 0 ]; then
  echo ""
  echo "❌ $ISSUES skill(s) out of sync in $PROJECT"
  echo "   Fix with: bash $FRAMEWORK_ROOT/scripts/sync-skills.sh $PROJECT"
  exit 1
fi

exit 0
