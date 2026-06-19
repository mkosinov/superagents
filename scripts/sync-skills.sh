#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <project-path>" >&2
  echo "Example: $0 /root/workspace/memo" >&2
  exit 2
fi

PROJECT="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRAMEWORK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$FRAMEWORK_ROOT/skills"
TARGET_DIR="$PROJECT/.opencode/skills"

if [ ! -d "$PROJECT" ]; then
  echo "Error: project path does not exist: $PROJECT" >&2
  exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: framework skills dir does not exist: $SOURCE_DIR" >&2
  exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
  echo "Creating $TARGET_DIR"
  mkdir -p "$TARGET_DIR"
fi

ADDED=0
UPDATED=0
SKIPPED=0

for skill_dir in "$SOURCE_DIR"/*/; do
  [ -d "$skill_dir" ] || continue
  skill_name="$(basename "$skill_dir")"
  source_file="$skill_dir/SKILL.md"
  target_skill_dir="$TARGET_DIR/$skill_name"
  target_file="$target_skill_dir/SKILL.md"

  if [ ! -f "$source_file" ]; then
    continue
  fi

  if [ ! -d "$target_skill_dir" ]; then
    mkdir -p "$target_skill_dir"
    cp "$source_file" "$target_file"
    echo "  + added $skill_name"
    ADDED=$((ADDED + 1))
  elif diff -q "$source_file" "$target_file" > /dev/null 2>&1; then
    SKIPPED=$((SKIPPED + 1))
  else
    cp "$source_file" "$target_file"
    echo "  ~ updated $skill_name"
    UPDATED=$((UPDATED + 1))
  fi
done

# Report project-specific skills (not in framework)
PROJECT_SPECIFIC=0
for target_skill_dir in "$TARGET_DIR"/*/; do
  [ -d "$target_skill_dir" ] || continue
  skill_name="$(basename "$target_skill_dir")"
  if [ ! -d "$SOURCE_DIR/$skill_name" ]; then
    PROJECT_SPECIFIC=$((PROJECT_SPECIFIC + 1))
  fi
done

echo ""
echo "Sync complete: $ADDED added, $UPDATED updated, $SKIPPED unchanged, $PROJECT_SPECIFIC project-specific preserved"
