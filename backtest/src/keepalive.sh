#!/usr/bin/env bash
# Keeps grid_watchdog.sh alive. Run once with nohup.
cd /home/user/20k5ers || exit 1
while true; do
  if ! pgrep -f grid_watchdog.sh > /dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] keepalive: watchdog dead, respawning" >> backtest/output/doe/grid_watchdog.log
    bash backtest/src/grid_watchdog.sh >> backtest/output/doe/grid_watchdog.log 2>&1 &
  fi
  sleep 60
done
