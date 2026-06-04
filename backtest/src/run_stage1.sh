#!/usr/bin/env bash
# =============================================================================
# Stage 1 supervisor — crash-proof, parallel, background-safe
#
# Runs Phase 1a (OAT, 4-parallel) then Phase 1b (2 parallel Optuna workers)
# then Phase 1c (top-5 validation).
#
# Crash-proof guarantees:
#   - Each phase is retried up to MAX_RETRIES times on non-zero exit
#   - OAT: skip-if-done CSV — restart picks up where it left off
#   - Optuna: SQLite study — all trials survive a crash
#   - All output to stable log file in backtest/output/doe/
#
# Usage:
#   bash backtest/src/run_stage1.sh           # run all phases
#   bash backtest/src/run_stage1.sh optuna    # only Optuna phase
# =============================================================================

cd "$(dirname "$0")/../.." || exit 1          # repo root

PHASE="${1:-all}"
TRIALS="${2:-80}"                              # total Optuna trials (split across 2 workers)
MAX_RETRIES=8
LOGDIR="backtest/output/doe"
LOGFILE="$LOGDIR/stage1_live.log"
SUPLOG="$LOGDIR/stage1_supervisor.log"

mkdir -p "$LOGDIR"
exec >> "$LOGFILE" 2>&1                        # all stdout+stderr → stable log

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

run_with_retry() {
    local label="$1"; shift
    local attempt=0
    while [ $attempt -lt $MAX_RETRIES ]; do
        log "START  $label  (attempt $((attempt+1))/$MAX_RETRIES)"
        "$@"
        local rc=$?
        if [ $rc -eq 0 ]; then
            log "DONE   $label"
            return 0
        fi
        attempt=$((attempt + 1))
        log "CRASH  $label  exit=$rc  retrying in 5s..."
        sleep 5
    done
    log "FAILED $label after $MAX_RETRIES attempts"
    return 1
}

# ── Phase 1a: OAT (4-parallel, skip-if-done) ─────────────────────────────────
if [[ "$PHASE" == "all" || "$PHASE" == "oat" ]]; then
    run_with_retry "OAT" uv run python -u backtest/src/stage1_fib_sweep.py --phase oat
fi

# ── Phase 1b: Optuna (2 parallel workers, same SQLite DB) ────────────────────
if [[ "$PHASE" == "all" || "$PHASE" == "optuna" ]]; then
    HALF=$(( TRIALS / 2 ))
    log "START  Optuna — 2 workers × $HALF trials each (total $TRIALS)"

    # Worker 1
    run_with_retry "Optuna-worker1" \
        uv run python -u backtest/src/stage1_fib_sweep.py --phase optuna --trials "$HALF" &
    W1=$!

    # Worker 2 (slight stagger so they pick different initial trials)
    sleep 8
    run_with_retry "Optuna-worker2" \
        uv run python -u backtest/src/stage1_fib_sweep.py --phase optuna --trials "$HALF" &
    W2=$!

    wait $W1 $W2
    log "DONE   Optuna — both workers finished"
fi

# ── Phase 1c: validate top-5 ─────────────────────────────────────────────────
if [[ "$PHASE" == "all" || "$PHASE" == "validate" ]]; then
    run_with_retry "Validate-top5" \
        uv run python -u backtest/src/stage1_fib_sweep.py --phase validate
fi

log "=== Stage 1 complete ==="
