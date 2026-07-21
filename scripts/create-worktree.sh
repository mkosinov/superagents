#!/bin/bash
# create-worktree.sh <branch-name>
# Creates a git worktree with environment setup

set -e

list_pnpm_package_dirs() {
  find . -name "package.json" \
    -not -path "./node_modules/*" \
    -not -path "*/node_modules/*" \
    -not -path "*/.next/*" \
    -not -path "*/.worktrees/*" \
    -exec dirname {} \;
}

BRANCH=$1

if [ -z "$BRANCH" ]; then
  echo "Usage: $0 <branch-name>"
  exit 1
fi

if [[ ! "$BRANCH" =~ ^[a-zA-Z0-9/_-]+$ ]]; then
  echo "Error: Invalid branch name. Use only letters, numbers, /, _, -"
  exit 1
fi

WORKTREE_DIR=".worktrees/$BRANCH"

# --- Git worktree -----------------------------------------------------------

if [ -d "$WORKTREE_DIR" ]; then
  echo "Error: worktree already exists at $WORKTREE_DIR"
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/$BRANCH" 2>/dev/null; then
  echo "Branch '$BRANCH' already exists. Creating worktree from existing branch..."
  git worktree add "$WORKTREE_DIR" "$BRANCH"
else
  echo "Creating new branch '$BRANCH'..."
  git worktree add "$WORKTREE_DIR" -b "$BRANCH"
fi

echo "Worktree created at $WORKTREE_DIR"

# --- Environment files ------------------------------------------------------

for env_file in .env .env.dev .env.local; do
  if [ -f "$env_file" ]; then
    cp "$env_file" "$WORKTREE_DIR/"
    echo "Copied $env_file"
  fi
done

# --- Node modules -----------------------------------------------------------
# All-or-nothing: symlink every package node_modules from source, or run
# pnpm install only in the worktree (no mixed symlinks + install).

SOURCE_NEEDS_INSTALL=false
while IFS= read -r pkg_dir; do
  # [ -d ] follows symlinks; false for missing or broken targets.
  if [ ! -d "$pkg_dir/node_modules" ]; then
    if [ "$pkg_dir" = "." ]; then
      echo "⚠ Root node_modules missing or broken in source"
    else
      echo "⚠ $(basename "$pkg_dir")/node_modules missing or broken in source"
    fi
    SOURCE_NEEDS_INSTALL=true
  fi
done < <(list_pnpm_package_dirs)

if [ "$SOURCE_NEEDS_INSTALL" = true ]; then
  echo ""
  echo "→ Source node_modules incomplete; running 'pnpm install' in worktree to self-heal..."
  if ! (cd "$WORKTREE_DIR" && pnpm install --prefer-offline); then
    echo "❌ pnpm install failed in worktree. Worktree is in a partial state."
    echo "   Manual fix:  cd $WORKTREE_DIR && pnpm install"
    exit 1
  fi
  echo "✓ pnpm install succeeded — worktree node_modules repaired"
else
  while IFS= read -r pkg_dir; do
    # pnpm 11: each workspace needs node_modules or non-interactive runs hang on TTY prompt.
    if [ "$pkg_dir" = "." ]; then
      ln -s "$(pwd)/node_modules" "$WORKTREE_DIR/node_modules"
      echo "Symlinked root node_modules"
    else
      mkdir -p "$WORKTREE_DIR/$pkg_dir"
      ln -s "$(pwd)/$pkg_dir/node_modules" "$WORKTREE_DIR/$pkg_dir/node_modules"
    fi
  done < <(list_pnpm_package_dirs)
fi

# --- Python -----------------------------------------------------------------

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
