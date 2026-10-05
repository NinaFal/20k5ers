# BACKUP — Stage C2 "trial 4" config (KEEP for future use)

**Do not delete.** This was the Stage C2 winner (score 174.8) found BEFORE we
discovered the real 5%ers "Summer Edition" account uses a **3% daily wall**
(not the classic 5% we had assumed). Re-tested under the corrected 3% wall:

## ⚠️ Verified UNSAFE for the 3% wall account

Full 2-step challenge score, all 16 TRAIN starts, 3% daily wall (closed
balance, ≥3 profitable days, 100k account):

```
score=-825.13  p20=0.125  p40=0.125  breach_rate=0.875 (14/16)  median_total=13.5
```

**14 of 16 starts breach.** Only 2016-01-01 (11 days) and 2023-04-01 (16 days)
survive cleanly. This config was tuned at 3.5% risk with `CORR_GROUP_CAP=3` and
**no total-position cap** (`MAX_TOTAL_POSITIONS` didn't exist yet) — far too hot
for a 3% wall.

## ✅ Where this IS still valid: a classic 5% daily wall account

Under the (wrong-for-Summer-Edition, but real-for-classic-accounts) 5% daily
wall, this was the best config found in the C1→C2 pipeline: **score 174.8,
p20=37.5%, p40=62.5%, 0% breach** on the same 16 TRAIN starts. If you ever run
a 5%ers challenge on the CLASSIC (5% daily) account type, this is a strong
starting point — validate on holdout before using live.

## Full config

Entry (C1 winner):
```
entry_fib_level          = 0.65
entry_fib_level_volatile = 0.65
fib_vol_ratio_threshold  = 1.15
```
Ladder (C2 trial 4, 100% closed by TP3):
```
tp1_r_multiple = 0.40   tp1_close_pct = 0.50
tp2_r_multiple = 0.75   tp2_close_pct = 0.35
tp3_r_multiple = 1.35   tp3_close_pct = 0.15
sl_after_tp2_r = 0.25
sl_after_tp3_r = 0.60
risk_per_trade_pct = 3.5
```
Regime/risk skeleton:
```
RISK_REGIME_ENABLE=1  RISK_CALM_MULT=1.45  RISK_VOLATILE_MULT=0.64
VOL_REGIME_DD_OFF=5.0  CFG_MAX_CUM_RISK=5.0  CFG_DAILY_HALT_PCT=2.25
CFG_TDD_CAUTION_PCT=3.5  CFG_RISK_CAUTIOUS=0.65
CFG_TDD_WARNING_PCT=4.5  CFG_RISK_CONSERVATIVE=0.6
CFG_TDD_EMERGENCY_PCT=8.0  CFG_RISK_ULTRASAFE=0.4
TDD_WALL_SAFETY=4.0  CORR_GROUP_CAP=3
FIVEERS_MAX_SCALE=4000000
MAX_TOTAL_POSITIONS = (not set — this is exactly what made it unsafe at 3%)
CFG_DAILY_WALL_PCT = 5.0 for classic accounts / 3.0 for Summer Edition
```

Reproduce (classic 5% wall):
```bash
CFG_DAILY_WALL_PCT=5.0  # rest of env as above
```
Reproduce (Summer Edition 3% wall — will breach heavily, for reference only):
```bash
CFG_DAILY_WALL_PCT=3.0  # rest of env as above — DO NOT run live like this
```
