#!/usr/bin/env bash
# Stage 1b grid supervisor — crash-proof, resumable (skip-if-done CSV).
cd "$(dirname "$0")/../.." || exit 1
MAX_RETRIES=8
LOGFILE="backtest/output/doe/stage1_grid_live.log"
mkdir -p backtest/output/doe
exec >> "$LOGFILE" 2>&1
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

run_with_retry() {
    local label="$1"; shift
    local attempt=0
    while [ $attempt -lt $MAX_RETRIES ]; do
        log "START $label (attempt $((attempt+1))/$MAX_RETRIES)"
        "$@" && { log "DONE $label"; return 0; }
        attempt=$((attempt+1)); log "CRASH $label retry in 5s"; sleep 5
    done
    log "FAILED $label"; return 1
}

run_with_retry "grid"     uv run python -u backtest/src/stage1_grid.py --phase grid
run_with_retry "validate" uv run python -u backtest/src/stage1_grid.py --phase validate
log "=== Stage 1b complete ==="
