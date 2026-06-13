#!/bin/bash
# SessionStart hook: pull latest state and relaunch Stage 4 Pareto watchdog if needed.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd /home/user/20k5ers
git pull origin claude/awesome-maxwell-50dMF --quiet 2>/dev/null || true

LOG="backtest/output/doe/stage4_pareto_run.log"

# Check if Pareto is already done
if grep -q "STAGE4_PARETO_DONE_MARKER" "$LOG" 2>/dev/null; then
  echo "[session-start] Stage 4 Pareto COMPLETE — no watchdog needed"
  exit 0
fi

# Check if watchdog is already running (pgrep avoids false match on grep itself)
if pgrep -f "watchdog_stage4_pareto.sh" > /dev/null 2>&1; then
  echo "[session-start] Stage 4 Pareto watchdog already running"
  exit 0
fi

# Relaunch watchdog
mkdir -p backtest/output/doe
setsid nohup bash backtest/src/watchdog_stage4_pareto.sh \
  >> backtest/output/doe/watchdog_stage4_pareto.log 2>&1 &
echo "[session-start] Stage 4 Pareto watchdog relaunched (pid=$!)"
