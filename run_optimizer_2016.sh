#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  run_optimizer_2016.sh
#  TP / Close% / SL Optimizer  –  Januari 2016 t/m Mei 2016
#
#  Lanceert de optimizer in een NIEUWE SESSIE via setsid zodat:
#    - Het proces blijft draaien als je de terminal sluit
#    - Geen timeout (loopt tot alle trials klaar zijn)
#    - Output gaat naar logfile ÉN naar de terminal
#
#  Gebruik:
#    bash run_optimizer_2016.sh [--trials N] [--parallel N] [--startup-trials N]
#
#  Monitor live:
#    tail -f backtest/optimization_results/2016_jan_may/optimizer.log
#
#  Stop de optimizer:
#    cat backtest/optimization_results/2016_jan_may/optimizer.pid | xargs kill
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Configuratie ──────────────────────────────────────────────────────────────
TRIALS="${TRIALS:-100}"          # aantal trials (overschrijf via env: TRIALS=200 bash run_optimizer_2016.sh)
PARALLEL="${PARALLEL:-1}"        # parallelle workers
STARTUP="${STARTUP:-15}"         # random verkenning voor TPE
UPDATE_INTERVAL="${UPDATE_INTERVAL:-5}"  # update elke N trials

LOG_DIR="backtest/optimization_results/2016_jan_may"
LOG_FILE="${LOG_DIR}/optimizer.log"
PID_FILE="${LOG_DIR}/optimizer.pid"

mkdir -p "$LOG_DIR"

# ── Verwerk CLI-argumenten ────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --trials)        TRIALS="$2";   shift 2 ;;
        --parallel|-j)   PARALLEL="$2"; shift 2 ;;
        --startup-trials) STARTUP="$2"; shift 2 ;;
        --update-interval) UPDATE_INTERVAL="$2"; shift 2 ;;
        *)               echo "Onbekende optie: $1"; exit 1 ;;
    esac
done

# ── Python detectie ───────────────────────────────────────────────────────────
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
    echo "ERROR: Python niet gevonden. Stel PYTHON in, bijv.: PYTHON=python3.10 bash run_optimizer_2016.sh"
    exit 1
fi

# ── Informatie ────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════════"
echo "  TP / CLOSE% / SL OPTIMIZER  –  JAN 2016 t/m MEI 2016"
echo "═══════════════════════════════════════════════════════════════════════"
echo "  Trials:           $TRIALS"
echo "  Parallel workers: $PARALLEL"
echo "  Startup trials:   $STARTUP"
echo "  Update interval:  elke $UPDATE_INTERVAL trials"
echo "  Log:              $LOG_FILE"
echo "  PID file:         $PID_FILE"
echo "  Timeout:          GEEN"
echo "═══════════════════════════════════════════════════════════════════════"

# ── Check: draait er al een optimizer? ───────────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(<"$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo ""
        echo "  WAARSCHUWING: Er draait al een optimizer (PID=$OLD_PID)."
        echo "  Stop hem eerst:  kill $OLD_PID"
        echo "  Of bekijk de log: tail -f $LOG_FILE"
        exit 1
    else
        echo "  Oud PID-bestand gevonden maar process is gestopt – verwijderd."
        rm -f "$PID_FILE"
    fi
fi

echo ""
echo "  Starten via setsid (nieuwe sessie, blijft draaien na afsluiten terminal)..."
echo ""

# ── Launch met setsid ─────────────────────────────────────────────────────────
# setsid: nieuwe sessie → los van de huidige terminal
# nohup:  negeer HUP-signaal voor extra zekerheid
# tee:    schrijft tegelijk naar logfile en stdout
setsid nohup "$PYTHON" backtest/optimize_2016_jan_may.py \
    --trials             "$TRIALS"          \
    --parallel           "$PARALLEL"        \
    --startup-trials     "$STARTUP"         \
    --update-interval    "$UPDATE_INTERVAL" \
    >> "$LOG_FILE" 2>&1 &

OPTIMIZER_PID=$!
echo "$OPTIMIZER_PID" > "$PID_FILE"

echo "  Optimizer gestart!"
echo "  PID:  $OPTIMIZER_PID"
echo ""
echo "  Monitor (live):   tail -f $LOG_FILE"
echo "  Stop:             kill $OPTIMIZER_PID  (of: cat $PID_FILE | xargs kill)"
echo ""
echo "  De optimizer blijft draaien ook als je deze terminal sluit."
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "  Live output:"
echo "─────────────────────────────────────────────────────────────────────"
echo ""

# Volg de log live in deze terminal (totdat de gebruiker Ctrl+C drukt)
# Ctrl+C stopt alleen de tail, NIET de optimizer
tail -f "$LOG_FILE" &
TAIL_PID=$!

# Wacht op optimizer (of Ctrl+C)
wait "$OPTIMIZER_PID" 2>/dev/null || true

# Optimizer klaar
kill "$TAIL_PID" 2>/dev/null || true
rm -f "$PID_FILE"

echo ""
echo "─────────────────────────────────────────────────────────────────────"
echo "  Optimizer klaar! Zie het volledige rapport in:"
echo "  $LOG_FILE"
echo "═══════════════════════════════════════════════════════════════════════"
