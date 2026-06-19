#!/usr/bin/env bash
# reflect.sh — CLI wrapper for reflection-mode
# Usage:
#   reflect.sh post-mortem --target=path/to/file
#   reflect.sh wave --name="Wave 4.5"
#   reflect.sh nightly [--days=7] [--auto-apply]
#   reflect.sh status
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHONPATH="$SKILL_DIR" exec python3 -c "from reflect.scripts.lib import main; main()" "$@"
