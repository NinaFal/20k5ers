# BASELINE CONFIG — t65 + TDD tiers (FROZEN)

This is the confirmed baseline. Frozen copy:
`backtest/output/doe/wall5/BASELINE_t65_tdd_FROZEN.json`, which is immutable —
future optimisation rounds write to `current_best.json` and must never touch it.

Identity: **nightly-stage trial 65**, plus the TDD-tier tightening from the 2025
rescue (variant `halt2.50+tdd`). Account: 5ers **classic**, Step 1 8%, Step 2 5%,
**5% daily wall**, **10% total wall**, 3 profitable days at 0.5% of balance.

---

## 1. Settings

### Environment

| Variable | Value |
|---|---|
| `RISK_VOLATILE_MULT` | `1.0` |
| `CFG_MAX_CUM_RISK` | `7.0` |
| `CORR_GROUP_CAP` | `6` |
| `MAX_TOTAL_POSITIONS` | `20` |
| `NIGHTLY_DERISK` | `1`  ← master gate; whole nightly block is dead without it |
| `NIGHTLY_DERISK_HOUR` | `22` |
| `NIGHTLY_MAX_PER_GROUP` | `0` |
| `NIGHTLY_MAX_TOTAL` | `0` |
| `NIGHTLY_R_CLOSE_LOSING` | `0.25` |
| `NIGHTLY_R_NEW` | `0.5` |
| `NIGHTLY_REDUCE_PCT` | `0.75` |
| `CFG_DAILY_HALT_PCT` | `2.50` |
| `TDD_WALL_SAFETY` | `5.5` |
| `CFG_TDD_CAUTION_PCT` | `1.5` |
| `CFG_RISK_CAUTIOUS` | `0.4` |
| `CFG_TDD_WARNING_PCT` | `2.5` |
| `CFG_RISK_CONSERVATIVE` | `0.25` |
| `CFG_DAILY_WALL_PCT` | `5.0` |
| `FIVEERS_MAX_SCALE` | `500000` |
| `DDD_CLOSE_AT_TRIGGER` | `1` |
| `TDD_WORST_CASE` | `1` (measurement only — no live equivalent) |
| `EXCLUDE_SYMBOLS` | `AUD_NZD,EUR_NZD,AUD_JPY` |
| `BROKER_TYPE` | `fiveers_live` |

### Trade parameters

| Parameter | Value |
|---|---|
| `risk_per_trade_pct` | **2.7** |
| `tp1_r_multiple` / `tp1_close_pct` | 0.65 / 0.25 |
| `tp2_r_multiple` / `tp2_close_pct` | 1.85 / 0.60 |
| `tp3_r_multiple` / `tp3_close_pct` | 2.75 / 0.15 |
| `sl_after_tp1_r` | −0.10 |
| `sl_after_tp2_r` | 0.90 |
| `sl_after_tp3_r` | 1.70 |
| all six entry filters | disabled |

---

## 2. What it does — measured

**Challenge, 100 fresh random starts 2015-2025 (out of sample):**

| outcome | count |
|---|---|
| passed both steps | **86** |
| breached — account lost | **7** |
| stalled — fee lost, account intact | 7 |

Median **16 days**, fastest 5, slowest 115. Within 20d 58, **within 30d 69**,
within 40d 74, within 50d 76.

**Funded account, continuous, level carried forward** (both survived, zero
breaches, under strict intrabar marking):

| start | years | trading profit | fixed payouts | worst daily | worst total |
|---|---|---|---|---|---|
| $100k, 2016-2025 | 10 | $3,400,723 | not computed | 4.73% | 4.27% |
| $50k, 2015-2025 | 11 | $3,622,756 | $672,000 | 4.09% | 6.33% |

Once both reach the $500k cap they are **bit-for-bit identical**; starting at
$50k costs one extra year of climbing and nothing else.

**Scaling cap:** keep it at **$500k**. $350k survives with an identical 4.73%
worst day but earns ~$1M less; $150k and $250k both die in 2016.

---

## 3. Position sizing and the 50-lot cap

**5ers broker hard cap is 50 lots per position** (`main_live_bot.py:4361`). It is
not published on the5ers' High Stakes page, which states only leverage 1:100 —
reconfirm with support.

Realised sizes under this config are far below it:

| account | trades | max lot | mean lot |
|---|---|---|---|
| $100k climbing | 985 | 19.45 | 2.36 |
| $500k at cap | 891 | 28.07 | 2.92 |

So the cap never binds in normal operation.

**Known defect, no impact on these results.** The backtest reads
`symbol_info.get('max_lot', 100.0)` (`main_live_bot_backtest.py:3454`) but
`get_symbol_info()` returns `volume_max`, not `max_lot`. The lookup always misses
and falls back to **100 lots**, double the real limit, and the symbol table's
`volume_max: 50.0` is never read. The live bot gets this right. It only bites
above 50 lots, which happens nowhere in the scaled or challenge results.

**Unexplained observation:** mean lot rose only 1.24× (2.36 → 2.92) for a 5×
larger account. Suspected cause is the TDD tiers throttling risk near the funded
floor, but unverified — and if true, some of the lower drawdown at the cap that
was attributed to the absence of rung crossings may belong to risk throttling
instead. Separating them needs a run with the TDD tiers disabled.

---

## 4. Before this can be traded

Unchanged from `W5_FINAL_SETTINGS.md` §4 — none of the tuned environment
variables are read by any live-bot file, the nightly de-risk pass has no live
implementation, and `ftmo_config.py` defaults differ sharply (`risk_per_trade_pct`
0.6 against the validated 2.7). Read that section before going live.
