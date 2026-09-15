#!/usr/bin/env bash
# Supervisor for the E4 grid — the process group is reaped when the session
# idles. The grid caches every completed cell to e4_grid_<split>.json and skips
# them on restart, so relaunching simply resumes.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/e4_run.log
for ((i = 0; i < 60; i++)); do
  while pgrep -f "e4_fastest_safe_grid.py" >/dev/null 2>&1; do sleep 30; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] grid complete" >>"$LOG"; exit 0
  fi
  echo "[SUP] restart #$((i + 1))" >>"$LOG"
  setsid nohup uv run python3 backtest/src/e4_fastest_safe_grid.py --horizon 60 >>"$LOG" 2>&1 </dev/null &
  sleep 20
done
