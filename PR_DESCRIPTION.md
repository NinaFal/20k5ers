# CRITICAL: Lower max daily loss to 3.5% + JSON sync + transparency improvements

## Summary

This PR implements critical safety improvements and transparency enhancements for the trading bot:

1. **Lower emergency close threshold from 4.5% to 3.5% daily loss**
2. **Lock initial_balance to $20,000 with triple-layer protection**
3. **Sync JSON state files with 5ers dashboard**
4. **Add DDD/TDD metrics to JSON and detailed logging**

## Changes

### 1. CRITICAL: Lower Max Daily Loss Limit to 3.5%

**Risk Management Flow:**
- 2.0% daily loss: WARNING mode
- 3.0% daily loss: CONSERVATIVE mode + halt new trades
- **3.5% daily loss: EMERGENCY mode - CLOSE ALL POSITIONS** ⚠️
- 5.0% daily loss: Hard challenge limit (5ers rule)

**Files Changed:**
- `ftmo_config.py:40` - `daily_loss_emergency_pct`: 4.5% → **3.5%**
- `ftmo_config.py:39` - `daily_loss_halt_pct`: 3.5% → **3.0%**
- `challenge_risk_manager.py:265-268` - Emergency logic updated

**Impact:** Provides 1.5% extra buffer before 5% hard limit.

### 2. PROTECT: Lock initial_balance to $20,000

**Triple-Layer Protection:**

1. **Hardcoded Fallback:** `PROTECTED_INITIAL_BALANCE = 20000.0`
2. **Sanity Check:** Resets to $20k if value > $25k or < $15k
3. **Explicit Fallback Paths:**
   - JSON missing → $20k
   - Load fails → $20k
   - Key missing → $20k

**Files Changed:**
- `challenge_risk_manager.py:159-194` - Protected load_state()

**Impact:** TDD limit always calculated correctly: $20,000 × 0.90 = **$18,000** ✓

### 3. SYNC: Reset JSON State Files

**Corrected balances and risk limits:**
- Initial balance: **$20,000.00** (challenge start)
- Day start balance: **$20,193.68** → DDD limit = **$19,184.00** ✓
- Peak equity: **$20,204.05**
- Profitable days: **2**
- Cleared all pending setups and open positions

**Files Changed:**
- `challenge_state.json` - Reset to match 5ers
- `challenge_risk_state.json` - Updated with correct day start
- `awaiting_entry.json` - Cleared
- `pending_setups.json` - Cleared

**Impact:** Bot now correctly tracks challenge limits in sync with 5ers.

### 4. TRANSPARENCY: Add DDD/TDD Metrics

**JSON State Now Includes:**
```json
{
  "current_equity": 19961.67,
  "daily_pnl": -232.01,
  "daily_loss_pct": 1.15,
  "ddd_limit": 19184.0,
  "total_dd_pct": 1.2,
  "tdd_limit": 18000.0
}
```

**Enhanced Logging:**
```
📊 RISK METRICS (Compare with 5ers Dashboard)
  Initial Balance: $20,000.00
  Day Start Equity: $20,193.68
  Current Equity: $19,961.67
  Peak Equity: $20,204.05
  ---
  Daily P&L: -$232.01
  DDD: 1.15% (Limit: $19,184.00)
  TDD: 1.20% (Limit: $18,000.00)
```

**Files Changed:**
- `challenge_risk_manager.py:196-220` - Add metrics to _save_state()
- `challenge_risk_manager.py:245-283` - Enhanced sync_with_mt5() logging

**Impact:** Easy verification that bot calculations match 5ers exactly.

## Commits

- `e3937c9` - CRITICAL: Lower max daily loss limit to 3.5% (close all trades)
- `e2cbb74` - SYNC: Reset JSON state files to match 5ers dashboard
- `b37cc7e` - PROTECT: Lock initial_balance to $20,000 with triple-layer protection
- `62b0dae` - TRANSPARENCY: Add DDD/TDD metrics to JSON and detailed logging

## Testing

- [x] JSON state files manually verified
- [x] DDD calculation: $20,193.68 × 0.95 = $19,184.00 ✓ (matches 5ers)
- [x] TDD calculation: $20,000.00 × 0.90 = $18,000.00 ✓
- [x] Emergency threshold: 3.5% ✓
- [x] Protected initial_balance: $20,000 (locked) ✓

## Risk Assessment

**Low Risk:**
- All changes are safety improvements
- Tighter risk limits (3.5% vs 4.5%)
- Better transparency for monitoring
- Protected against incorrect initial_balance

**Benefits:**
- ✅ Extra 1.5% buffer before 5% breach
- ✅ Initial balance can never drift
- ✅ Easy comparison with 5ers dashboard
- ✅ Better logging for debugging

## Deployment Notes

1. Bot will read updated JSON files on startup
2. All trades were manually closed before sync
3. New DDD/TDD logs will appear in console
4. Initial balance permanently locked to $20,000

---

**Ready to merge!** All changes tested and verified against 5ers dashboard.
