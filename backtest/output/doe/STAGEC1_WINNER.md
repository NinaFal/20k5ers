# Stage C1 Winner — entry shape for the challenge objective

**Date:** 2026-07-20. Grid: 12 entry shapes x 16 TRAIN starts (full 2-step,
challenge_score.py rules), bank_fast ladder, risk 3.5%, t49 regime skeleton,
cap 3, CHF on.

## Ranking (score = 3*P(<=20d) + P(<=40d) - 10*breach - medTotal/100)

| config | score | p(<=20d) | p(<=40d) | breach | median total days |
|---|--:|--:|--:|--:|--:|
| **c=0.65 v=0.65 thr=1.15** | **93.5** | 0.12 | **0.56** | **0.00** | 29 |
| c=0.65 v=0.80 thr=1.15 | 87.2 | 0.12 | 0.50 | 0.00 | 28 |
| c=0.55 v=0.65 thr=1.15 | 74.8 | 0.12 | 0.38 | 0.00 | 25.5 |
| c=0.55 v=0.80 thr=1.05 (funded baseline) | 62.3 | 0.06 | 0.44 | 0.00 | 22 |
| c=0.45 v=0.65 thr=1.05 | -12.6 | 0.12 | 0.12 | **0.06** | 12.0 |
| c=0.45 v=0.80 thr=1.05 | -25.3 | 0.06 | 0.19 | **0.06** | 26.0 |

Full 12-row table: `output/doe/stageC1_entry_shape.json`.

## Findings

1. **The funded-phase entry (c=0.55/v=0.80/thr=1.05) is NOT the challenge
   winner** — it ranks 4th. Optimizing for "safe long-run profit" and
   "fast safe challenge pass" pull entry shape in different directions.
2. **c=0.45 (shallow calm fib) is unsafe for the challenge** — every c=0.45
   variant shows 6% breach, while every c>=0.55 variant shows 0%. Shallow
   entries take weaker setups, feeding into 3.5% risk badly.
3. **Winner: c=0.65 v=0.65 thr=1.15** — deep retracement on BOTH calm and
   volatile regimes, higher regime-switch threshold (mostly "calm" fib
   behavior). Best combination of safety (0 breach) and reliability (56% within
   40 days) of all zero-breach configs. It doesn't win outright on p20 (tied
   at 0.12 with several), but wins decisively on p40 and safety margin.

## Locked into C2

Entry params for all subsequent challenge stages:
```
entry_fib_level          = 0.65
entry_fib_level_volatile = 0.65
fib_vol_ratio_threshold  = 1.15
```
(all other PINNED_ENTRY fields unchanged from stage5c_oos_screen.py)
