# Main Live Bot Backtest - Complete Restructure

## 📁 Directory Structure

```
backtest/
├── src/                              # All Python code
│   ├── main_live_bot_backtest.py    # Exact copy of main_live_bot.py with CSV data
│   ├── csv_mt5_simulator.py         # MT5Client drop-in replacement using CSV M15 data
│   ├── csv_data_provider.py         # (archived)
│   └── m15_backtest_bot.py          # (archived compact version)
├── results/                          # Output files
│   ├── backtest_2023_2025.json      # Final results & statistics
│   └── backtest_2023_2025.log       # Execution log
├── run_backtest_2023_2025.sh        # Executable backtest script
└── monitor_progress.sh               # Progress monitoring script
```

## 🚀 Running the Backtest

### Full 2023-2025 Backtest (Recommended)
```bash
cd /workspaces/20k5ers
python backtest/src/main_live_bot_backtest.py \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --balance 20000 \
  --output backtest/results/backtest_2023_2025.json
```

### Using the Run Script (with nohup for background)
```bash
nohup bash /workspaces/20k5ers/backtest/run_backtest_2023_2025.sh \
  > backtest/results/backtest_2023_2025.log 2>&1 &
```

### Monitor Progress
```bash
tail -f backtest/results/backtest_2023_2025.log
bash backtest/monitor_progress.sh
```

---

## 🔧 Implementation Details

### main_live_bot_backtest.py
- **Source**: Exact copy of [main_live_bot.py](../main_live_bot.py) (4163 lines)
- **Modification**: Only changed import to use `CSVMT5Simulator` instead of `MT5Client`
- **Key Method**: `run_backtest()` - iterates through M15 candles, simulating 00:10 daily scans
- **Data Source**: `data/ohlcv/*.csv` (M15 candles for 35 symbols)
- **Logic**: 
  - ✅ Strategy signal generation (HTF: D1/W1/MN)
  - ✅ Entry queue system (0.3R proximity)
  - ✅ Lot sizing at FILL moment (dynamic risk calculation)
  - ✅ 3-TP partial closes (35%/30%/35%)
  - ✅ Progressive SL trailing at 0.8R → TP1 lock-in
  - ✅ DDD/TDD safety checks (5ers compliance)
  - ✅ Challenge Phase management (auto-start, progression)

### CSVMT5Simulator (csv_mt5_simulator.py)
- **Purpose**: Drop-in replacement for MT5Client
- **Interface**: All ~50 methods from MT5Client
- **Data**: Loads M15 OHLCV from CSV files on connect()
- **Key Methods**:
  - `get_tick(symbol, timeframe)` - returns simulated tick from M15 candles
  - `get_ohlcv(symbol, timeframe)` - returns list of OHLCV dicts
  - `place_market_order()` - executes immediately at ask/bid
  - `place_pending_order()` - queues order until price reached
  - `check_sl_tp_hits()` - simulates SL/TP execution within current candle
  - `partial_close()` - closes percentage of position at specified price
- **Performance**: ~26 seconds to load all M15 data (optimized with pandas set_index)

---

## 📊 Reference Performance (as of Jan 20, 2026)

From production validation (2023-01-01 → 2025-12-31):

| Metric | Value |
|--------|-------|
| Starting Balance | $20,000 |
| Final Balance | $310,183 |
| Gross Return | +1,451% (+$290,183) |
| Total Trades | 871 |
| Win Rate | 67.5% |
| Max Daily DD | 3.61% |
| Max Total DD | 4.94% |
| 5ers Compliance | ✅ PASS (within 10% TDD, 5% DDD) |

---

## ⚙️ Key Parameters

Loaded from [params/current_params.json](../params/current_params.json):
- **Strategy**: Confluence-based price action (min 5/7 confluence)
- **Risk per Trade**: 0.6% (base) → reduced to 0.4% if DD ≥ 3.0%
- **Position Management**: 
  - Max Daily Loss: 5% from day start
  - Max Total DD: 10% from initial balance
  - Daily Halt: If TDD > 3.5%, close all and stop trading
- **Entry Window**: 0.3R from signal (within entry queue)
- **TP Levels**:
  - TP1: 0.6R (close 35%)
  - TP2: 1.2R (close 30%)
  - TP3: 2.0R (close 35%)
- **Progressive Trailing**: SL moves to TP1 at 0.8R profit

---

## 🧪 Test Results

### 1-Week Validation (June 1-7, 2024)
- Trades: 31
- Win Rate: 67.7%
- Return: +3.9% ($324.85)
- Max DDD: 1.25%
- Max TDD: 0.63%
- ✅ All logic verified (0.8R progressive trailing confirmed)

### Full Backtest (Current - 2023-2025)
- **Status**: ⏳ IN PROGRESS
- **Expected Runtime**: ~2-3 hours
- **Expected Result**: ~871 trades, +$310K profit

---

## 🔍 Data Sources

### M15 Candle Data
- Location: `data/ohlcv/*.csv`
- Format: OANDA with underscores (EUR_USD, XAU_USD)
- Symbols: 33 forex pairs + 2 metals + 3 indices = 35 total
- Timeframe: January 1, 2023 → December 31, 2025
- Per Symbol: ~74,000 candles (~2.6M total records)

### Higher Timeframe Data (Signal Generation)
- Daily (D1), Weekly (W1), Monthly (MN)
- Used by strategy_core.py via compute_confluence()
- Already included in project data

---

## 🚨 Troubleshooting

### Import Errors
- Ensure sys.path includes project root from backtest/src/
- Fixed in lines 18-28 of main_live_bot_backtest.py

### Missing M15 Data
- Run: `python download_m15_data.py` to fetch latest
- Files saved to: `data/ohlcv/`

### Results Not Saving
- Check: `backtest/results/` directory exists
- Verify: write permissions on backtest/ folder
- Monitor: `backtest/results/backtest_2023_2025.log`

---

## 📈 Post-Backtest Analysis

After run completes:

1. **Load Results**
   ```python
   import json
   with open('backtest/results/backtest_2023_2025.json') as f:
       results = json.load(f)
   ```

2. **Key Metrics to Check**
   - Total trades vs reference (871)
   - Win rate vs reference (67.5%)
   - Final balance vs reference ($310,183)
   - Max DD within limits (TDD ≤ 4.94%, DDD ≤ 3.61%)

3. **Optional: Compare with Production Run**
   ```bash
   diff backtest/results/backtest_2023_2025.json \
        ftmo_analysis_output/SIMULATE_2023_2025_20K_JAN18/results.json
   ```

---

## ✅ Validation Checklist

- [x] Python files reorganized to backtest/src/
- [x] Import paths fixed for backtest/src/ location
- [x] Results directory created
- [x] CSVMT5Simulator fully functional
- [x] main_live_bot_backtest.py ready to run
- [x] 1-week test passed (June 2024)
- [ ] Full 2023-2025 backtest completed
- [ ] Results match reference performance
- [ ] 5ers compliance verified
- [ ] Documentation complete

---

**Last Updated**: January 22, 2026
**Status**: 🟢 Ready for Full Backtest
**Estimated Completion**: ~2-3 hours from start
