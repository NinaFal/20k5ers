## ⚠️ Backtest Issue Report - Lot Sizing Accumulation

### Problem
Backtest produced incorrect results:
- Final Balance: **-$1,577,772** (should be +$310,183)
- Return: **-7,988.86%** (should be +1,451%)
- Total Trades: 43 (should be ~871)
- Max TDD: 7,988.86% (should be ~4.94%)

### Root Cause
The position reopening logic in main_live_bot_backtest.py is causing:
1. Initial order fills with 0.01 lots (placeholder)
2. Code detects mismatch: "should be 0.12 lots"
3. Closes 0.01 position and reopens with 0.12 lots
4. **BUG**: Lot sizes are accumulating or positions not properly closed/reopened

Evidence from trades.csv:
- Ticket 1000025: EUR_USD, 0.14 lots (cumulative of multiple reopenings)
- Ticket 1000006: EUR_JPY, 0.03 lots (partial reopening)
- Multiple trades showing fractional lots instead of consistent sizing

### Impact on Results
- Positions are overleveraged
- Losses accumulate faster than expected
- Total equity goes deeply negative
- Account gets liquidated early

### Solution Approach

**Option 1: Fix the Reopening Logic** (RECOMMENDED)
- Instead of close + reopen, modify the open position's lot size directly
- In CSVMT5Simulator.place_market_order():
  ```python
  # Don't close and reopen, just update the existing position
  if position_exists:
      position.volume = correct_lot_size  # Update, don't create new
  ```

**Option 2: Remove Reopening Entirely**
- Accept the initial 0.01 lot placeholder
- Update TP levels based on actual lot size
- Simpler but less accurate for large accounts

**Option 3: Pre-Calculate Lot Size**
- Calculate lot size BEFORE placing order
- Pass correct volume to place_market_order() initially
- Requires refactoring entry queue logic

### Next Steps
1. ✅ Identify the bug (lot size accumulation in reopening)
2. ⏳ Choose fix approach
3. ⏳ Modify CSVMT5Simulator.py or main_live_bot_backtest.py
4. ⏳ Re-run 1-week test first (June 2024)
5. ⏳ If successful, re-run full 2023-2025 backtest

### Files to Modify
- `backtest/src/csv_mt5_simulator.py` - place_market_order() method (line ~450-550)
- `backtest/src/main_live_bot_backtest.py` - close_and_reopen logic (line ~2500-2600)

---

**Status**: 🔴 FAILED - Lot sizing bug detected
**Severity**: CRITICAL - Results completely invalid
**Workaround**: Disable lot size correction for now (use 0.01 placeholder lots)
**ETA to Fix**: 30 minutes with proper debugging

