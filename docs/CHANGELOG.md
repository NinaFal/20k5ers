# Changelog

## [February 3, 2026]

### Critical Fixes
- **Metal Pip Value Fix**: XAU and XAG now use `fiveers_specs` directly for pip_value
  - XAU: $100/pip (was incorrectly getting $1/pip from MT5 tick_value)
  - XAG: $5/pip
  - This fix prevents 59x oversizing on metal trades

### Safety Additions
- **2x Risk Rejection**: Trades are now rejected if actual_risk exceeds 2x intended risk
  - Catches cases where min_lot forces excessive risk
  - Applies to ALL assets (forex, metals, indices, crypto)

### Documentation Updates
- Updated all documentation to reflect 5-TP system (from old 3-TP references)
- Updated risk per trade to 1.0% (from old 0.6% references)
- Removed outdated files:
  - `AI_ASSISTANT_GUIDE.md` (replaced by `.github/copilot-instructions.md`)
  - `backtest/ISSUE_LOT_SIZING_ACCUMULATION.md` (resolved)
  - `backtest/FIXES_AND_UPDATES.md` (outdated)
  - Old analysis report txt files

### Files Modified
- `main_live_bot.py` - Metal pip_value fix, 2x risk rejection, updated docstring
- `backtest/src/main_live_bot_backtest.py` - Same fixes as live bot
- `.github/copilot-instructions.md` - Full update
- `README.md` - Updated to 5-TP system
- `docs/EXIT_STRATEGY.md` - Updated to 5-TP system
- `docs/5ERS_COMPLIANCE.md` - Updated with safety features
- `docs/ARCHITECTURE.md` - Updated architecture diagram

---

## [January 2026]

### Strategy Configuration
- Migrated from 3-TP to 5-TP exit system
- Parameters now loaded from `params/current_params.json`
- Risk per trade: 1.0%

### Entry System
- Entry queue with 168h (7 day) expiry
- 0.3R proximity for limit orders
- 0.05R for immediate market orders

### Safety Systems
- DDD 3-tier: 2% warn, 3% reduce, 3.2% halt
- TDD static from initial balance (10% = $18K stop-out)
- Friday closing at 16:00 UTC
- Weekend gap management

---

**Last Updated**: February 3, 2026
