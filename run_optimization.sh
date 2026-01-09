#!/bin/bash
# FTMO Optimization Runner
# Automatically logs all output to ftmo_analysis_output/{MODE}/run.log
# Usage:
#   ./run_optimization.sh --single --trials 20
#   ./run_optimization.sh --multi --trials 50
#   ./run_optimization.sh --status

# Determine mode from arguments (default to TPE)
MODE="TPE"
if [[ "$*" == *"--multi"* ]]; then
    MODE="NSGA"
fi

# Create output directory
mkdir -p "ftmo_analysis_output/${MODE}"

# Run with nohup and log to mode-specific directory
LOG_FILE="ftmo_analysis_output/${MODE}/run.log"

echo "Starting FTMO optimization in ${MODE} mode..."
echo "Output logged to: ${LOG_FILE}"
echo "Monitor with: tail -f ${LOG_FILE}"

nohup python ftmo_challenge_analyzer.py "$@" > "${LOG_FILE}" 2>&1 &
PID=$!

echo "Process started with PID: ${PID}"
echo ""
echo "Commands:"
echo "  tail -f ${LOG_FILE}              # Watch live output"
echo "  ps aux | grep ${PID}             # Check if running"
echo "  kill ${PID}                      # Stop optimization"
echo ""
