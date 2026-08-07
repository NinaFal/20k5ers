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
| `risk_per_trade_pct` | **2.7** (base — see §2b for what is actually risked) |
| `tp1_r_multiple` / `tp1_close_pct` | 0.65 / 0.25 |
| `tp2_r_multiple` / `tp2_close_pct` | 1.85 / 0.60 |
| `tp3_r_multiple` / `tp3_close_pct` | 2.75 / 0.15 |
| `sl_after_tp1_r` | −0.10 |
| `sl_after_tp2_r` | 0.90 |
| `sl_after_tp3_r` | 1.70 |
| all six entry filters | disabled |

---

## 2b. ACTUAL risk per trade — not 2.7%

`risk_per_trade_pct = 2.7` is a base that two mechanisms then modify.

**A hard cap by funded level** (`main_live_bot_backtest.py:3331`):

```python
if   funded_level >= 2_000_000: base_risk = min(base_risk, 0.25)
elif funded_level >= 1_000_000: base_risk = min(base_risk, 0.40)
elif funded_level >=   300_000: base_risk = min(base_risk, 0.60)
```

**A regime multiplier** (`:3385`, `risk_pct = risk_pct * _rm`): ×1.45 when
ATR(14)/ATR(50) is below `fib_vol_ratio_threshold` (**1.05** in this config),
×1.0 otherwise. Collapses to ×1.0 past 5% drawdown.

| funded level | volatile | calm (×1.45) |
|---|---|---|
| below $300k — challenge and early climb | 2.70% | **3.92%** |
| $300k–$1M — includes the $500k cap | 0.60% | **0.87%** |
| $1M+ | 0.40% | 0.58% |
| $2M+ | 0.25% | 0.36% |

**At the $500k cap the account risks 0.6–0.87% per trade, roughly 4.5x less than
during the challenge.** This is very likely the dominant reason capped years run
1.78-3.42% worst daily drawdown against 4.73% while climbing.

An earlier draft attributed that gap mainly to scaling-rung crossings — balance
jumping to the next funded level mid-day while `day_start_equity`, the daily
drawdown denominator, stayed anchored to the pre-jump figure. That effect is
real and was measured at ~1.8 points across three paired years, but **this cap
is the larger cause and was missed.** It also explains the margin profile: 69%
usage climbing at 3.9% risk, 12.6% at the cap at 0.87%.

Practical consequence: the challenge is where the real risk sits. Once funded
and scaled the bot becomes dramatically more conservative without being told to.

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

**There is no per-trade risk limit at 5ers.** Confirmed by the account holder
and consistent with the5ers' published rules, which state the 5% daily wall, the
10% total wall and 1:100 leverage, and say nothing about risk per trade. The
`ftmo_config.py` guard that rejected anything above 2.5% was self-imposed and
had no basis; it is raised to 5.0 so it cannot reject the validated 2.7%
configuration. Changing an assertion is safe while the backtest runs — it either
raises or does not — unlike the behavioural fields in that file, which the
backtest imports and which must never be edited.

**The real constraint on size is margin.** At 1:100 each standard lot ties up
$1,000, so a $500k account supports at most 500 lots if it spends every cent of
margin. Measured peak concurrent exposure:

| account | peak concurrent lots | margin at 1:100 | % of equity |
|---|---|---|---|
| $100k climbing | 69.37 | $69,370 | **69.4%** |
| $500k at cap | 62.80 | $62,800 | 12.6% |

Peak exposure is essentially flat in absolute terms while equity grows 5x, so
margin pressure is concentrated entirely in the climb — the same phase that
produces every breach.

Two caveats on that 69.4%. It assumes 1:100 on **every** instrument, which is the
headline FX number; metals, indices and crypto are normally leveraged lower, and
this config trades XAU, XAG and NAS100. And the simulator models no margin at
all — `csv_mt5_simulator.py:557-559` hardcodes `margin: 0.0` and
`margin_free: equity` — so the backtest will happily open positions a broker
would reject. **Get the per-asset-class leverage from 5ers**; if indices are
1:20, NAS100 positions consume five times what is credited above and the
climbing phase may be at the margin ceiling rather than at 69% of it.

**Per-position cap: 50 lots** (`main_live_bot.py:4361`). Not published on the
High Stakes page either — reconfirm with support.

Realised sizes under this config are far below it:

| account | trades | max lot | mean lot |
|---|---|---|---|
| $100k climbing | 985 | 19.45 | 2.36 |
| $500k at cap | 891 | 28.07 | 2.92 |

So the cap never binds in normal operation.

**Open question for 5ers support — this one could actually change results.** The
50-lot limit is *per position*. Whether 5ers also caps **aggregate** exposure
across all open positions is not published on any page found. This config runs
up to 20 concurrent positions (`MAX_TOTAL_POSITIONS=20`), so at $500k it can
hold roughly 200-500 lots open at once. A total-exposure ceiling would bind
where the per-position cap does not, and unlike the backtest's max_lot defect it
would materially change these numbers. Ask alongside the fixed-payout question.

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
