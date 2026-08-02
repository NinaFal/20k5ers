# Parameter inventory — what has been optimized, what hasn't

**Date:** 2026-07-29. Target for the next round: **0 breaches and both steps passed in under 50 days**, every stage scored on the same 100 canonical start dates (`output/doe/CANONICAL_100_STARTS.json`).

Three groups: **[OPT]** optimized at some point, **[FROZEN]** given a value early and never searched since, **[NEVER]** never searched at all.

---

## A. Entry / setup quality — 15 parameters

The largest unexplored block. Only three of these have ever been searched.

| parameter | current | status |
|---|---|---|
| `entry_fib_level` | 0.45 | **[OPT]** Stage 1, C1 |
| `entry_fib_level_volatile` | 0.80 | **[OPT]** Stage 1, C1 |
| `fib_vol_ratio_threshold` | 1.05 | **[OPT]** Stage 1, C1 |
| `min_confluence` | 6 | **[FROZEN]** |
| `trend_min_confluence` | 6–7 | **[FROZEN]** |
| `range_min_confluence` | 2–3 | **[FROZEN]** |
| `min_quality_factors` | 3–4 | **[FROZEN]** |
| `adx_trend_threshold` | 30.0 | **[NEVER]** |
| `adx_range_threshold` | 11.0 | **[NEVER]** |
| `adx_min_entry` | 0.0 (off) | **[NEVER]** |
| `atr_min_percentile` | 41.0 | **[FROZEN]** |
| `atr_vol_ratio_range` | 1.4 | **[FROZEN]** |
| `entry_limit_offset_atr` | 0.0 | **[NEVER]** |
| `december_atr_multiplier` | 1.8 | **[NEVER]** |
| `volatile_asset_boost` | 1.8 | **[NEVER]** |

### The six filter switches — all OFF, none ever tested

```
use_htf_filter           False
use_structure_filter     False
use_confirmation_filter  False
use_fib_filter           False
use_displacement_filter  False
use_candle_rejection     False
```

**[NEVER]** — an entire dimension untouched. These are selectivity filters, and selectivity is precisely what a 0-breach target needs: fewer, higher-quality setups mean a thinner book and less to go wrong. Worth testing early.

---

## B. Exit ladder — 14 parameters

| parameter | current | status |
|---|---|---|
| `tp1_r_multiple` … `tp5_r_multiple` | 0.5 / 1.0 / 1.5 / 2.5 / 3.5 | **[OPT]** Stage 3, C2 |
| `tp1_close_pct` … `tp5_close_pct` | 0.45 / 0.35 / 0.20 / 0 / 0 | **[OPT]** Stage 3, C2 |
| `sl_after_tp2_r` / `tp3_r` / `tp4_r` | 0.5 / 1.2 / 1.8 | **[OPT]** Stage 3, C2 |
| `sl_after_tp1_r` | 0.2 | **[NEVER]** — the earliest stop-trail, never searched |

Note the ladder currently closes 100% by TP3; TP4/TP5 are inert. Whether that is optimal under a 3% wall was decided in C2 under different assumptions.

---

## C. Risk sizing — 12 levers

| lever | current | status |
|---|---|---|
| `risk_per_trade_pct` | 1.1 | **[OPT]** Stage 2, C3, E3/E4 |
| `CFG_MAX_CUM_RISK` | 3.0 | **[OPT]** C3, D2/D3 |
| `RISK_CALM_MULT` | 1.45 | **[OPT]** Stage 2, 5d |
| `RISK_VOLATILE_MULT` | 0.64 | **[OPT]** Stage 2, 5d |
| `RISK_REGIME_3WAY` | off | **[NEVER]** — built, never searched |
| `RISK_NORMAL_MULT` | — | **[NEVER]** (needs 3WAY on) |
| `RISK_CALM_THR` / `RISK_VOL_THR` | — | **[NEVER]** — the ATR ratio cutoffs themselves |
| `VOL_SIZE_ENABLE` | 0 | **[NEVER]** — disabled throughout |
| `VOL_SIZE_LOOKBACK` / `MULT_HIGH` / `MULT_LOW` | — | **[NEVER]** |
| `compound_threshold_pct` | 13.5 | **[NEVER]** |

---

## D. Drawdown protection — 9 levers

| lever | current | status |
|---|---|---|
| `CFG_DAILY_HALT_PCT` | 2.0 | **[OPT]** C3 — **E8 sweep built, never run** |
| `CFG_TDD_CAUTION_PCT` → `CFG_RISK_CAUTIOUS` | 2.0 → 0.5 | **[FROZEN]** |
| `CFG_TDD_WARNING_PCT` → `CFG_RISK_CONSERVATIVE` | 3.0 → 0.3 | **[FROZEN]** |
| `CFG_TDD_EMERGENCY_PCT` → `CFG_RISK_ULTRASAFE` | 5.5 → 0.15 | **[FROZEN]** |
| `TDD_WALL_SAFETY` | 4.0 | **[FROZEN]** |
| `DDD_CLOSE_AT_TRIGGER` | 1 | **[FROZEN]** |

The halt threshold is the single highest-value item here: 2019 and 2020 died at **3.29%** and **3.17%** against a 3.0% wall, i.e. narrowly, with the halt set 1.0 point away.

---

## E. Position / exposure caps — 4 levers

| lever | current | status |
|---|---|---|
| `CORR_GROUP_CAP` | 3 | **[OPT]** Stage 5d, C3 |
| `MAX_TOTAL_POSITIONS` | 15 | **[OPT]** C3 |
| `MAX_HOLD_DAYS` | off | **[NEVER]** — added this session, unvalidated |
| `MAX_HOLD_HOUR` | 21 | **[NEVER]** |

---

## F. Overnight de-risk — 7 levers

| lever | current | status |
|---|---|---|
| `NIGHTLY_MAX_PER_GROUP` | 1 | **[OPT]** E4 |
| `NIGHTLY_MAX_TOTAL` | 2 | **[OPT]** E4 |
| `NIGHTLY_DERISK_HOUR` | 21 | **[NEVER]** — fixed throughout |
| `NIGHTLY_R_CLOSE_LOSING` | 0.0 | **[NEVER]** |
| `NIGHTLY_R_NEW` | 0.5 | **[NEVER]** |
| `NIGHTLY_REDUCE_PCT` | 0.5 | **[NEVER]** |
| Friday equivalents (`friday_safety_*`, 5 params) | various | **[NEVER]** |

E4 searched only the two book-size caps. The four behavioural knobs — when to run, what counts as a loser, what counts as young, how much to cut — were left at first guesses, and E0 showed this is the mechanism that decides breaches.

---

## G. Universe

| lever | current | status |
|---|---|---|
| `EXCLUDE_SYMBOLS` | AUD_NZD, EUR_NZD, AUD_JPY | **[OPT]** D1 screen |
| per-symbol inclusion | 27 symbols | **[FROZEN]** — screened once, as a block |

---

## H. Not tunable (infrastructure / account rules)

`CFG_DAILY_WALL_PCT` (3.0 — the account's rule), `FIVEERS_MAX_SCALE` (175000 — your terms), `BROKER_TYPE`, `TERMINAL_ON_BREACH`, `GAP_FILLS`, `SLIPPAGE_PIPS`, `RECORD_TDD`, `TDD_WORST_CASE`, `DDD_DEBUG`, `NIGHTLY_DEBUG`.

---

## Totals

| | count |
|---|---|
| **[OPT]** genuinely searched | **17** |
| **[FROZEN]** set once, never revisited | **13** |
| **[NEVER]** never searched | **29** |
| Infrastructure | 10 |

**Roughly 70% of the tunable surface has never been searched, or was frozen before the 3% wall was even known about.**

---

## Suggested stage order for the new round

Ranked by expected value against *0 breaches, under 50 days*.

| stage | what | why first |
|---|---|---|
| **S1** | `CFG_DAILY_HALT_PCT` + TDD ladder tiers | The two 2019/2020 deaths missed by 0.29 and 0.17 points. Cheapest possible fix. |
| **S2** | The 4 untuned nightly knobs + hour | E0 proved overnight exposure decides breaches; only 2 of 7 knobs were ever searched. |
| **S3** | The 6 filter switches | Whole untested dimension. Selectivity directly serves a 0-breach target. |
| **S4** | Entry gates (confluence, quality, ADX, ATR) | 12 frozen parameters, all set before the 3% wall existed. |
| **S5** | Ladder re-tune, incl. `sl_after_tp1_r` | Current ladder was optimized for a different wall. |
| **S6** | `MAX_HOLD_DAYS` + risk-regime 3-way | Both built, neither validated. |
| **S7** | Joint re-tune of the survivors | Interactions, once the individual effects are known. |

**Method for every stage:** the same 100 canonical starts, breach as a hard reject (no amount of speed buys it back), then rank by passes-under-50-days. Hold out a slice for final validation — the 30-day "winner" that failed holdout is what happens otherwise.
