# Implementation Roadmap - Prioritized Action Plan

## Overview

This document provides a step-by-step implementation plan to achieve:
- ✅ FTMO Compliance (<10% max DD, <5% daily loss)
- ✅ 60%+ Win Rate
- ✅ 100%+ Annual Return

---

## PHASE 1: CRITICAL - FTMO Compliance
**Timeline:** Week 1  
**Goal:** Reduce Max DD from 25.9% to <10%

### Task 1.1: Implement Daily Loss Circuit Breaker
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🔴 CRITICAL  
**Effort:** 4-6 hours  

**Changes:**
1. Add `FTMOComplianceTracker` dataclass (see FTMO_COMPLIANCE_IMPLEMENTATION.md)
2. Modify `run_full_period_backtest()` to track daily P&L
3. Skip trades when daily loss >= 4.2%
4. Terminate simulation if daily loss >= 5.0%

**Expected Impact:** DD reduction of 10-15%

### Task 1.2: Implement Total DD Circuit Breaker
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🔴 CRITICAL  
**Effort:** 2-3 hours  

**Changes:**
1. Track total drawdown from starting balance
2. Skip trades when total DD >= 8%
3. Terminate simulation if total DD >= 10%

**Expected Impact:** DD reduction of 3-5%

### Task 1.3: Implement Consecutive Loss Halt
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🟡 HIGH  
**Effort:** 1-2 hours  

**Changes:**
1. Track consecutive losses
2. Halt trading after 5 consecutive losses
3. Reset counter after winning trade

**Expected Impact:** DD reduction of 2-3%

### Task 1.4: Implement Dynamic Position Sizing
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🟡 HIGH  
**Effort:** 3-4 hours  

**Changes:**
1. Reduce position size after losses
2. Reduce when approaching daily/total DD limits
3. Use `calculate_dynamic_risk()` function

**Expected Impact:** DD reduction of 2-3%

### Phase 1 Verification:
```bash
# Run test backtest
python ftmo_challenge_analyzer.py --test-compliance

# Expected output:
# Max DD: <10% (was 25.9%)
# Daily loss breach: 0 (trades skipped before breach)
# Challenge status: PASSED
```

---

## PHASE 2: HIGH - Win Rate Improvement
**Timeline:** Week 2  
**Goal:** Increase Win Rate from 48% to 55-60%

### Task 2.1: Add TP R-Multiples to Optimization
**File:** `ftmo_challenge_analyzer.py` (objective function)  
**Priority:** 🟡 HIGH  
**Effort:** 2-3 hours  

**Add parameters:**
```python
'tp1_r_multiple': trial.suggest_float('tp1_r_multiple', 1.0, 2.0, step=0.25),
'tp2_r_multiple': trial.suggest_float('tp2_r_multiple', 2.0, 4.0, step=0.5),
'tp3_r_multiple': trial.suggest_float('tp3_r_multiple', 3.5, 6.0, step=0.5),
```

**Expected Impact:** Win Rate +3-5%

### Task 2.2: Add TP Close Percentages to Optimization
**File:** `ftmo_challenge_analyzer.py` (objective function)  
**Priority:** 🟡 HIGH  
**Effort:** 2-3 hours  

**Add parameters:**
```python
'tp1_close_pct': trial.suggest_float('tp1_close_pct', 0.10, 0.40, step=0.05),
'tp2_close_pct': trial.suggest_float('tp2_close_pct', 0.10, 0.25, step=0.05),
'tp3_close_pct': trial.suggest_float('tp3_close_pct', 0.10, 0.25, step=0.05),
```

**Expected Impact:** Win Rate +2-3%

### Task 2.3: Enable Filter Toggle Parameters
**File:** `ftmo_challenge_analyzer.py` (objective function)  
**Priority:** 🟡 HIGH  
**Effort:** 3-4 hours  

**Add parameters:**
```python
'use_htf_filter': trial.suggest_categorical('use_htf_filter', [True, False]),
'use_structure_filter': trial.suggest_categorical('use_structure_filter', [True, False]),
'use_confirmation_filter': trial.suggest_categorical('use_confirmation_filter', [True, False]),
```

**Expected Impact:** Win Rate +5-10%

### Task 2.4: Pass Filters to StrategyParams
**File:** `ftmo_challenge_analyzer.py` (run_full_period_backtest)  
**Priority:** 🟡 HIGH  
**Effort:** 1-2 hours  

**Changes:**
1. Add filter params to function signature
2. Pass to StrategyParams constructor
3. Verify filters are applied in simulate_trades()

**Expected Impact:** Required for Task 2.3

### Phase 2 Verification:
```bash
# Run optimization with new parameters
python ftmo_challenge_analyzer.py --trials 100

# Expected output:
# Win Rate: 55-60% (was 48%)
# Parameters: TP1=1.25R, TP2=2.5R, etc.
# Filters: use_htf_filter=True, etc.
```

---

## PHASE 3: MEDIUM - Profit Optimization
**Timeline:** Week 3  
**Goal:** Increase Annual Return to 80-100%+

### Task 3.1: Implement Volatility Parity Sizing
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🟢 MEDIUM  
**Effort:** 3-4 hours  

**Changes:**
1. Calculate reference ATR for each asset
2. Adjust position size inversely to current ATR
3. Higher risk in low-vol, lower risk in high-vol

**Expected Impact:** Return +10%

### Task 3.2: Implement Confluence-Based Scaling
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🟢 MEDIUM  
**Effort:** 2-3 hours  

**Changes:**
1. Higher confluence = larger position
2. Scale: 1.0x at 4/7, 1.5x at 7/7
3. Use `confluence_scale_per_point` parameter

**Expected Impact:** Return +5%

### Task 3.3: Add Seasonality Optimization
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🟢 MEDIUM  
**Effort:** 2-3 hours  

**Add parameters:**
```python
'summer_risk_multiplier': trial.suggest_float('summer_risk_multiplier', 0.4, 1.0, step=0.2),
'december_boost': trial.suggest_float('december_boost', 1.0, 1.5, step=0.1),
```

**Expected Impact:** Return +3%

### Task 3.4: Optimize Breakeven Strategy
**File:** `ftmo_challenge_analyzer.py`  
**Priority:** 🟢 MEDIUM  
**Effort:** 1-2 hours  

**Add parameters:**
```python
'breakeven_trigger_r': trial.suggest_float('breakeven_trigger_r', 0.5, 1.5, step=0.25),
'breakeven_buffer_pips': trial.suggest_float('breakeven_buffer_pips', 2.0, 10.0, step=2.0),
```

**Expected Impact:** DD -2%, WR +1%

### Phase 3 Verification:
```bash
# Run full optimization
python ftmo_challenge_analyzer.py --trials 200

# Expected output:
# Annual Return: 80-100%
# Max DD: <10%
# Win Rate: 60%+
```

---

## PHASE 4: LOW - Fine-Tuning
**Timeline:** Week 4+  
**Goal:** Polish and optimize edge cases

### Task 4.1: Add Cooldown Parameter
**Priority:** 🔵 LOW  
**Effort:** 1 hour  

```python
'cooldown_bars': trial.suggest_int('cooldown_bars', 0, 5),
```

### Task 4.2: Add Z-Score/Momentum Filters
**Priority:** 🔵 LOW  
**Effort:** 2-3 hours  

```python
'use_zscore_filter': trial.suggest_categorical('use_zscore_filter', [True, False]),
'zscore_threshold': trial.suggest_float('zscore_threshold', 1.0, 2.5, step=0.25),
```

### Task 4.3: Symbol-Specific Parameters (ADVANCED)
**Priority:** 🔵 LOW  
**Effort:** 8-12 hours  

Optimize different parameters for different asset classes:
- Forex majors vs. crosses
- Metals vs. currencies
- High vol vs. low vol

### Task 4.4: Multi-Timeframe Entry (ADVANCED)
**Priority:** 🔵 LOW  
**Effort:** 8-12 hours  

Use H4 for entry timing instead of D1 only.

---

## Quick Start Commands

### After Phase 1 Implementation:
```bash
# Test compliance tracking
python -c "
from ftmo_challenge_analyzer import run_full_period_backtest
from datetime import datetime

trades, report = run_full_period_backtest(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 6, 30),
    enable_compliance_tracking=True,
)

print(f'Trades: {len(trades)}')
print(f'Max DD: {report[\"max_dd_pct\"]:.1f}%')
print(f'Skipped: {report[\"total_skipped\"]}')
print(f'Passed: {report[\"challenge_passed\"]}')
"
```

### After Phase 2 Implementation:
```bash
# Run optimization with new parameters
python ftmo_challenge_analyzer.py --single --trials 100
```

### Full Production Run:
```bash
# Background optimization
./run_optimization.sh --single --trials 500
tail -f ftmo_analysis_output/TPE/run.log
```

---

## Success Criteria

| Phase | Metric | Target | Verification |
|-------|--------|--------|--------------|
| 1 | Max Drawdown | <10% | `compliance_report['max_dd_pct']` |
| 1 | Challenge Pass | Yes | `compliance_report['challenge_passed']` |
| 2 | Win Rate | 55-60% | `overall_stats['win_rate']` |
| 2 | Profit Factor | >1.5 | `overall_stats['profit_factor']` |
| 3 | Annual Return | 80-100% | `overall_stats['annual_return']` |
| 3 | Sharpe Ratio | >1.5 | `overall_stats['sharpe']` |

---

## Risk Mitigation

### If DD is still too high after Phase 1:
1. Lower `daily_loss_halt_pct` to 3.5%
2. Lower `consecutive_loss_halt` to 3
3. Increase position size reduction rate

### If Win Rate is too low after Phase 2:
1. Enable more filters (Bundle B, C)
2. Increase `min_confluence_score` range
3. Tighten Fib zone ranges

### If Trade Count is too low:
1. Disable some filters
2. Lower confluence requirements
3. Expand asset universe

---

## Files Changed Summary

| Phase | File | Lines | Changes |
|-------|------|-------|---------|
| 1 | ftmo_challenge_analyzer.py | 350-400 | Add FTMOComplianceTracker |
| 1 | ftmo_challenge_analyzer.py | 596-750 | Modify run_full_period_backtest |
| 2 | ftmo_challenge_analyzer.py | 1056-1090 | Add TP + filter params |
| 2 | ftmo_challenge_analyzer.py | 693-720 | Pass params to StrategyParams |
| 3 | ftmo_challenge_analyzer.py | 596-650 | Add dynamic sizing |
| 4 | ftmo_challenge_analyzer.py | 1056-1090 | Add fine-tuning params |

---

*Roadmap created December 28, 2025*
