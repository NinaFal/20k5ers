# 5ers Compliance Guide

**Last Updated**: January 20, 2026  
**Account**: 5ers 20K High Stakes Challenge  
**Strategy Risk**: 0.6% per trade = $120/R

---

## 5ers Challenge Rules

### Total Drawdown (TDD) - STATIC
- **Stop-out level**: 10% below STARTING balance ($18,000 for 20K account)
- **NOT trailing**: If you grow to $300K and drop to $290K, still SAFE (above $18K)
- Maximum loss = $2,000 from starting balance

> ⚠️ **Key Difference from FTMO**: 5ers TDD is STATIC, not trailing!

### Daily Drawdown (DDD)
**5ers DOES track daily drawdown!**
- **Limit**: 5% from day start
- **Baseline**: MAX(closing equity, closing balance) at 00:00 server time
- **Reset**: Daily at 00:00 broker time
- As balance grows, daily loss allowance grows too

**Example**: If your account has equity $22,000 and balance $21,500 at 23:59:
- At 00:00 rollover → day_start = MAX($22,000, $21,500) = **$22,000**
- Daily loss limit: 5% × $22,000 = **$1,100**
- Stop-out at: $22,000 - $1,100 = **$20,900** for that day

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
| Warning | ≥2.0% | Log warning |
| Reduce | ≥3.0% | Reduce risk 0.6%→0.4% |
| Halt | ≥3.5% | Close all, stop trading |

**Margin to 5ers limit**: 5.0% - 3.5% = **1.5% safety buffer**

### TDD Implementation
```python
# Stop-out level = starting_balance * 0.90 (STATIC)
stop_out_level = 20000 * 0.90  # = $18,000

# Trade is stopped if:
is_stopped_out = current_balance < stop_out_level
```

---

## Validated Compliance (January 18, 2026)

### Simulation Results (2023-2025)
```
Starting Balance:     $20,000
Final Balance:        $310,183
Return:               +1,451%
Max TDD:              4.94%  (limit 10%) ✅
Max DDD:              3.61%  (limit 5%)  ✅
DDD Halt Events:      1 (safety working)
```

### Margin Analysis
| Metric | Limit | Achieved | Margin |
|--------|-------|----------|--------|
| TDD | 10.0% | 4.94% | 5.06% |
| DDD | 5.0% | 3.61% | 1.39% |

---

**Last Updated**: January 20, 2026
