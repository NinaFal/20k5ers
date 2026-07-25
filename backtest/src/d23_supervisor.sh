#!/usr/bin/env bash
# Supervisor for the D23 combined search: the optimizer has twice been reaped
# silently mid-run. The Optuna study is resumable, so just restart it until the
# target trial count is reached (or we give up after too many restarts).
cd /home/user/20k5ers || exit 1
TARGET=${1:-120}
MAX_RESTARTS=${2:-40}
LOG=backtest/output/doe/stageD23_run.log

count_done() {
  uv run python3 -c "
import optuna, sys
optuna.logging.set_verbosity(optuna.logging.CRITICAL)
try:
    s = optuna.load_study(study_name='stageD23',
                          storage='sqlite:///backtest/output/doe/stageD23.db')
    print(sum(1 for t in s.trials if t.state.name in ('COMPLETE', 'PRUNED')))
except Exception:
    print(0)
" 2>/dev/null | tail -1
}

for ((i = 0; i < MAX_RESTARTS; i++)); do
  # wait out whatever optimizer is currently alive
  while pgrep -f "stageD23_combined_optimize.py" >/dev/null 2>&1; do sleep 30; done

  done_n=$(count_done)
  echo "[SUP] optimizer not running; study has ${done_n}/${TARGET} trials" >>"$LOG"
  if [[ "$done_n" -ge "$TARGET" ]]; then
    echo "[SUP] target reached — supervisor exiting" >>"$LOG"
    exit 0
  fi

  echo "[SUP] restart #$((i + 1))" >>"$LOG"
  setsid nohup uv run python3 backtest/src/stageD23_combined_optimize.py \
    --trials "$TARGET" >>"$LOG" 2>&1 </dev/null &
  sleep 20
done

echo "[SUP] hit MAX_RESTARTS — giving up" >>"$LOG"
