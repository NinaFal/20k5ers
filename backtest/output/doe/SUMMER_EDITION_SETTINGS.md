# Summer Edition (3% daily wall) — full settings breakdown

**Config under test:** E4 grid winner — overnight book 1/2 @ 21:00, risk 1.1%.
**Status:** validated on TRAIN, **failed HOLDOUT** (see caveats at the bottom).
Read the caveats before using any of this live.

---

## 1. The overnight safety (`NIGHTLY_DERISK`) — the new mechanism

This is the lever that changed the picture. Everything else here already existed.

**Why it exists.** The E0 diagnostic dissected every breach day and found
**95.5% of the loss came from positions held overnight** — 5 of 6 breaches were
100% overnight, none was primarily intraday. Position-count caps bound *how many*
trades are open; they do not bound how much gap risk rides unattended overnight.

**What it does.** Every night at 21:00 UTC it runs the bot's existing Tier-1
correlation-aware selector — previously used only on Fridays — over the open book:

| rule | action |
|---|---|
| position at or above SL-breakeven (TP1 hit) | **hold**, exempt from all rules |
| crypto | **hold** (trades 24/7, no gap) |
| R < `NIGHTLY_R_CLOSE_LOSING` | **close** |
| R between close-threshold and `NIGHTLY_R_NEW` | **reduce** by `NIGHTLY_REDUCE_PCT` |
| R ≥ `NIGHTLY_R_NEW` | candidate to hold — winners run |
| more than `NIGHTLY_MAX_PER_GROUP` in a correlation group | trim to the cap |
| more than `NIGHTLY_MAX_TOTAL` non-crypto total | trim to the cap |

Friday is skipped — the existing weekend logic already handles it, and running
both would double-derisk.

```
NIGHTLY_DERISK          = 1        enable
NIGHTLY_DERISK_HOUR     = 21       UTC hour, once per calendar day
NIGHTLY_MAX_PER_GROUP   = 1        max overnight positions per correlation group
NIGHTLY_MAX_TOTAL       = 2        max overnight non-crypto positions
NIGHTLY_R_CLOSE_LOSING  = 0.0      close anything below breakeven
NIGHTLY_R_NEW           = 0.5      below 0.5R -> reduce
NIGHTLY_REDUCE_PCT      = 0.5      reduce those by half
```

The book size matters more than the risk setting. At the *same* 1.1% risk, an
overnight book of 1-per-group/3-total **breaches (8.3%)** where 1/2 does not —
direct confirmation that overnight exposure is the active mechanism.

---

## 2. Account walls

```
CFG_DAILY_WALL_PCT      = 3.0      Summer Edition daily wall
                                   (3% of EOD max(equity, balance))
                                   total wall is 10%, engine-enforced
BROKER_TYPE             = fiveers_live
FIVEERS_MAX_SCALE       = 175000   account stops scaling at $175k
```

## 3. Risk sizing

```
risk_per_trade_pct      = 1.1
CFG_MAX_CUM_RISK        = 3.0      max cumulative open risk
CFG_DAILY_HALT_PCT      = 2.0      halt trading for the day at 2% down
RISK_REGIME_ENABLE      = 1
RISK_CALM_MULT          = 1.45     size up in calm regimes (ATR14/ATR50)
RISK_VOLATILE_MULT      = 0.64     size down in volatile regimes
VOL_SIZE_ENABLE         = 0
VOL_REGIME_DD_MULT      = 1.0
VOL_REGIME_DD_OFF       = 5.0
```

## 4. Drawdown ladder (progressive de-risking toward the total wall)

```
CFG_TDD_CAUTION_PCT     = 2.0  -> CFG_RISK_CAUTIOUS      = 0.5
CFG_TDD_WARNING_PCT     = 3.0  -> CFG_RISK_CONSERVATIVE  = 0.3
CFG_TDD_EMERGENCY_PCT   = 5.5  -> CFG_RISK_ULTRASAFE     = 0.15
TDD_WALL_SAFETY         = 4.0
```

## 5. Position caps (intraday)

```
CORR_GROUP_CAP          = 3        max concurrent per correlation group
MAX_TOTAL_POSITIONS     = 15       max concurrent total
```

## 6. Entry

```
entry_fib_level           = 0.45   normal regime
entry_fib_level_volatile  = 0.80   volatile regime
fib_vol_ratio_threshold   = 1.05   regime switch
```

## 7. Take-profit ladder

| level | R multiple | close % |
|---|---|---|
| TP1 | 0.5 | 45% |
| TP2 | 1.0 | 35% |
| TP3 | 1.5 | 20% |
| TP4 | 2.5 | 0% |
| TP5 | 3.5 | 0% |

100% is closed by TP3 — front-loaded banking, which is what keeps realized
balance climbing (the challenge targets are on *closed* balance, not equity).

```
sl_after_tp2_r = 0.5    trail stop to +0.5R after TP2
sl_after_tp3_r = 1.2
sl_after_tp4_r = 1.8
```

## 8. Universe

```
EXCLUDE_SYMBOLS = AUD_NZD, EUR_NZD, AUD_JPY     (D1 screen: net-negative)
```
Everything else on the `fiveers_live` profile, **including metals and NAS100** —
two pipeline bugs had silently excluded 10 symbols from every backtest before
this branch (wrong broker profile disabled metals; a tz-naive/aware file mix
dropped NAS100).

---

## Caveats — read before risking money

1. **HOLDOUT failed.** On 16 windows the search never saw, this config breaches
   **6.2%** of the time (TRAIN: 0%) and passes-within-40-days drops from 18.8%
   to **0%**. The fast zero-breach result was fitted to the tuned windows. It is
   **not** validated as a challenge config.
2. **Daily margin is thin.** Best years show max daily DD of 2.88-2.90% against
   a 3.0% wall — roughly $100 of headroom on a $175k account, on backtest fills.
   Real slippage eats that.
3. **A true gap event still kills it.** Starting 2015-01-01, the account dies on
   day 13 on the CHF unpeg — via the **total** wall, at 13.67%. Daily DD that day
   was only 2.51%. The overnight de-risk controls daily risk; nothing here
   protects against a single-bar move larger than the whole total-loss budget.
4. **Sample size.** 16 windows means one breach *is* 6.25%. Treat "0%" as "none
   in 16", never as a guarantee.
