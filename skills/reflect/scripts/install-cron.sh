#!/usr/bin/env bash
# Install nightly reflection cron job
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRON_LINE="0 3 * * * PYTHONPATH=$SKILL_DIR $SKILL_DIR/scripts/reflect.sh nightly --days=7 2>&1 | logger -t reflect-nightly"
(crontab -l 2>/dev/null | grep -v "reflect.sh nightly" || true; echo "$CRON_LINE") | crontab -
echo "Installed nightly cron: $CRON_LINE"