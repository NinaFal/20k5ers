# 5ers Compliance Guide

**Last Updated**: February 3, 2026  
**Account**: 5ers 20K High Stakes Challenge  
**Risk Per Trade**: 1.0% = $200/R

---

## 5ers Challenge Rules

### Total Drawdown (TDD) - STATIC
- **Stop-out level**: 10% below STARTING balance ($18,000 for 20K account)
- **NOT trailing**: If you grow to $300K and drop to $290K, still SAFE (above $18K)
- Maximum loss = $2,000 from starting balance

> ⚠️ **Key Difference from FTMO**: 5ers TDD is STATIC, not trailing!

### Daily Drawdown (DDD)
- **Limit**: 5% from day start
- **Baseline**: MAX(closing equity, closing balance) at 00:00 server time
- **Reset**: Daily at 00:00 broker time

### Profit Targets
| Step | Target | Amount |
|------|--------|--------|
| Step 1 | 8% | $1,600 |
| Step 2 | 5% | $1,000 |

---

## Bot Compliance Implementation

### DDD Safety System (3-Tier)

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning only |
| Reduce | ≥3.0% | Reduce risk |
| Halt | ≥3.2% | Close all, stop trading |

**Margin to 5ers limit**: 5.0% - 3.2% = **1.8% safety buffer**

### TDD Implementation
```python
# Stop-out level = starting_balance * 0.90 (STATIC)
stop_out_level = 20000 * 0.90  # = $18,000

# Trade is stopped if:
is_stopped_out = current_balance < stop_out_level
```

---

## Safety Features (February 3, 2026)

### Metal Pip Value Fix
- XAU: $100/pip (from fiveers_specs)
- XAG: $5/pip (from fiveers_specs)
- **Reason**: MT5 tick_value was unreliable for metals

### 2x Risk Rejection
```python
# Reject trades where actual risk exceeds 2x intended
if actual_risk_pct > risk_pct * 2:
    return 0.0  # NO TRADE
```

### Friday Protection
- No new orders after 16:00 UTC Friday
- Weekend gap management (correlation-aware)
- Crypto positions held (24/7 markets)

---

## Configuration (ftmo_config.py)

```python
FIVEERS_CONFIG = {
    "daily_loss_warning_pct": 2.0,
    "daily_loss_reduce_pct": 3.0,
    "daily_loss_halt_pct": 3.2,
    "total_dd_emergency_pct": 7.0,
    "friday_close_hour_utc": 16,
}
```

---

**Last Updated**: February 3, 2026
