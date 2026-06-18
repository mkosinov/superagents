#!/bin/bash
# create-worktree.sh <branch-name>
# Creates a git worktree with environment setup

set -e

BRANCH=$1

if [ -z "$BRANCH" ]; then
  echo "Usage: $0 <branch-name>"
  exit 1
fi

# Validate branch name (git ref rules)
if [[ ! "$BRANCH" =~ ^[a-zA-Z0-9/_-]+$ ]]; then
  echo "Error: Invalid branch name. Use only letters, numbers, /, _, -"
  exit 1
fi

WORKTREE_DIR=".worktrees/$BRANCH"

# Check if worktree already exists
if [ -d "$WORKTREE_DIR" ]; then
  echo "Error: worktree already exists at $WORKTREE_DIR"
  exit 1
fi

# Check if branch already exists
if git show-ref --verify --quiet "refs/heads/$BRANCH" 2>/dev/null; then
  echo "Branch '$BRANCH' already exists. Creating worktree from existing branch..."
  git worktree add "$WORKTREE_DIR" "$BRANCH"
else
  echo "Creating new branch '$BRANCH'..."
  git worktree add "$WORKTREE_DIR" -b "$BRANCH"
fi

echo "Worktree created at $WORKTREE_DIR"

# Copy environment files
if [ -f ".env" ]; then
  cp .env "$WORKTREE_DIR/"
  echo "Copied .env"
fi

if [ -f ".env.dev" ]; then
  cp .env.dev "$WORKTREE_DIR/"
  echo "Copied .env.dev"
fi

if [ -f ".env.local" ]; then
  cp .env.local "$WORKTREE_DIR/"
  echo "Copied .env.local"
fi

# Symlink root node_modules if exists
if [ -d "node_modules" ]; then
  ln -s "$(pwd)/node_modules" "$WORKTREE_DIR/node_modules"
fi

# Symlink every workspace's node_modules (not just root).
# pnpm 11 checks per-workspace deps status; missing workspace node_modules
# causes runDepsStatusCheck to prompt for TTY confirmation, which fails
# in non-interactive environments (CI, dev.sh background).
while IFS= read -r pkg_dir; do
  # pkg_dir is relative to source repo root
  if [ -d "$pkg_dir/node_modules" ]; then
    # Compute path relative to source root, replicate in worktree
    src_nm="$pkg_dir/node_modules"
    dest_dir="$WORKTREE_DIR/$pkg_dir"
    mkdir -p "$dest_dir"
    ln -s "$(pwd)/$src_nm" "$dest_dir/node_modules"
  fi
done < <(find . -name "package.json" \
            -not -path "./node_modules/*" \
            -not -path "*/node_modules/*" \
            -not -path "*/.next/*" \
            -not -path "*/.worktrees/*" \
            -exec dirname {} \;)

# Create venv and install Python deps if Python project detected
cd "$WORKTREE_DIR"

if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  echo "Python project detected, creating venv..."
  python3 -m venv .venv
  source .venv/bin/activate

  if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt --quiet
    echo "Installed requirements.txt"
  elif [ -f "pyproject.toml" ]; then
    pip install -e . --quiet 2>/dev/null || poetry install --quiet 2>/dev/null
    echo "Installed pyproject.toml dependencies"
  elif [ -f "setup.py" ]; then
    pip install -e . --quiet
    echo "Installed setup.py dependencies"
  fi

  deactivate
fi

echo ""
echo "✓ Worktree ready at $WORKTREE_DIR"
echo "  cd $WORKTREE_DIR to start working"
