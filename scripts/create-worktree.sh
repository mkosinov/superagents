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

# node_modules setup
#
# Strategy: all-or-nothing.
#   - If EVERY source node_modules is valid (real dir or valid symlink to dir),
#     symlink them into the worktree. Fast (no install).
#   - If ANY source is missing or a broken symlink, do a fresh `pnpm install`
#     in the worktree. Slower (20-30s) but guaranteed-correct.
#
# Why all-or-nothing: a partial symlink set + pnpm install would either
# (a) cause pnpm to misinterpret the symlinked dirs and rewrite them, or
# (b) leave the worktree in a hybrid state that's hard to debug. Better
# to pick one path and commit.
#
# Why this matters: a broken self-referential symlink (e.g.
#   /root/workspace/<project>/node_modules -> /root/workspace/<project>/node_modules)
# would cause pnpm to ELOOP on any operation in the worktree if propagated.
# Instead, the script detects the broken state and self-heals via pnpm install.

# Check whether every source node_modules is usable.
# [ -d ] follows symlinks: TRUE for real dir, TRUE for valid symlink→dir,
# FALSE for broken symlink (target missing) and missing path.
SOURCE_NEEDS_INSTALL=false
if [ ! -d "node_modules" ]; then
  echo "⚠ Root node_modules missing or broken in source"
  SOURCE_NEEDS_INSTALL=true
fi
while IFS= read -r pkg_dir; do
  if [ ! -d "$pkg_dir/node_modules" ]; then
    pkg_name="$(basename "$pkg_dir")"
    echo "⚠ $pkg_name/node_modules missing or broken in source"
    SOURCE_NEEDS_INSTALL=true
  fi
done < <(find . -name "package.json" \
            -not -path "./node_modules/*" \
            -not -path "*/node_modules/*" \
            -not -path "*/.next/*" \
            -not -path "*/.worktrees/*" \
            -exec dirname {} \;)

if [ "$SOURCE_NEEDS_INSTALL" = true ]; then
  # Self-heal: run pnpm install inside the worktree (don't touch source —
  # other worktrees may be using it).
  echo ""
  echo "→ Source node_modules incomplete; running 'pnpm install' in worktree to self-heal..."
  if ! (cd "$WORKTREE_DIR" && pnpm install --prefer-offline); then
    echo "❌ pnpm install failed in worktree. Worktree is in a partial state."
    echo "   Manual fix:  cd $WORKTREE_DIR && pnpm install"
    exit 1
  fi
  echo "✓ pnpm install succeeded — worktree node_modules repaired"
else
  # All sources are valid — symlink everything (fast path).
  ln -s "$(pwd)/node_modules" "$WORKTREE_DIR/node_modules"
  echo "Symlinked root node_modules"
  while IFS= read -r pkg_dir; do
    # pnpm 11 checks per-workspace deps status; missing workspace node_modules
    # causes runDepsStatusCheck to prompt for TTY confirmation, which fails
    # in non-interactive environments (CI, dev.sh background).
    src_nm="$pkg_dir/node_modules"
    dest_dir="$WORKTREE_DIR/$pkg_dir"
    mkdir -p "$dest_dir"
    ln -s "$(pwd)/$src_nm" "$dest_dir/node_modules"
  done < <(find . -name "package.json" \
              -not -path "./node_modules/*" \
              -not -path "*/node_modules/*" \
              -not -path "*/.next/*" \
              -not -path "*/.worktrees/*" \
              -exec dirname {} \;)
fi

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
