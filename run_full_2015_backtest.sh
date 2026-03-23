#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# FULL 2015-2025 BACKTEST — wacht op alle M5 data, dan start automatisch
# ═══════════════════════════════════════════════════════════════════════════════

cd /home/user/20k5ers

REQUIRED=33
DATA_DIR="data/ohlcv"
OUTPUT_DIR="backtest/results"
mkdir -p "$OUTPUT_DIR"

echo "════════════════════════════════════════════════════════"
echo "  Wacht op M5 data... ($REQUIRED bestanden nodig)"
echo "════════════════════════════════════════════════════════"

while true; do
    COUNT=$(ls "$DATA_DIR"/*_M5_*.csv 2>/dev/null | wc -l)
    echo "  [$(date '+%H:%M:%S')] M5 bestanden: $COUNT / $REQUIRED"
    if [ "$COUNT" -ge "$REQUIRED" ]; then
        break
    fi
    sleep 60
done

echo ""
echo "✓ Alle $REQUIRED M5 bestanden aanwezig!"
echo ""
echo "════════════════════════════════════════════════════════"
echo "  START: Backtest 2015-01-01 → 2025-12-31"
echo "  Balance: \$20,000  |  Data: M5 + M15 fallback"
echo "════════════════════════════════════════════════════════"
echo ""

source .venv/bin/activate 2>/dev/null || true

python backtest/src/main_live_bot_backtest.py \
    --start 2015-01-01 \
    --end   2025-12-31 \
    --balance 20000 \
    --output "$OUTPUT_DIR/backtest_2015_2025_M5" \
    2>&1 | tee "$OUTPUT_DIR/backtest_2015_2025_M5.log"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  KLAAR — resultaten in: $OUTPUT_DIR/backtest_2015_2025_M5/"
echo "════════════════════════════════════════════════════════"
