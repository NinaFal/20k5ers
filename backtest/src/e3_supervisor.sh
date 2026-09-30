#!/usr/bin/env bash
# Supervisor for the E3 fastest-safe search. The whole process group is reaped
# whenever the session goes idle, so an unsupervised run stalls at whatever
# trial it reached. The Optuna study is resumable, so just restart until the
# target trial count is reached.
cd /home/user/20k5ers || exit 1
TARGET=${1:-150}
HORIZON=${2:-60}
MAX_RESTARTS=${3:-60}
LOG=backtest/output/doe/e3_run.log

count_done() {
  uv run python3 -c "
import optuna
optuna.logging.set_verbosity(optuna.logging.CRITICAL)
try:
    s = optuna.load_study(study_name='stageE3',
                          storage='sqlite:///backtest/output/doe/stageE3.db')
    print(sum(1 for t in s.trials if t.state.name in ('COMPLETE', 'PRUNED')))
except Exception:
    print(0)
" 2>/dev/null | tail -1
}

for ((i = 0; i < MAX_RESTARTS; i++)); do
  while pgrep -f "e3_nightly_optimize.py" >/dev/null 2>&1; do sleep 30; done

  done_n=$(count_done)
  echo "[SUP] optimizer down; study has ${done_n}/${TARGET} trials" >>"$LOG"
  if [[ "$done_n" -ge "$TARGET" ]]; then
    echo "[SUP] target reached — supervisor exiting" >>"$LOG"
    exit 0
  fi

  echo "[SUP] restart #$((i + 1))" >>"$LOG"
  setsid nohup uv run python3 backtest/src/e3_nightly_optimize.py \
    --trials "$TARGET" --horizon "$HORIZON" >>"$LOG" 2>&1 </dev/null &
  sleep 20
done

echo "[SUP] hit MAX_RESTARTS — giving up" >>"$LOG"
