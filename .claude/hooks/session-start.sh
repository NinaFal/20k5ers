#!/bin/bash
# SessionStart hook: pull latest state.
# Stage 4 robustness is COMPLETE — nothing to relaunch.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd /home/user/20k5ers
git pull origin claude/awesome-maxwell-50dMF --quiet 2>/dev/null || true
echo "[session-start] Stage 4 robustness COMPLETE — no watchdog needed"
