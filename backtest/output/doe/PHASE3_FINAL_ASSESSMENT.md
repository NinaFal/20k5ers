# Phase 3 assessment — the 3% daily wall (100k Summer Edition)

**Date:** 2026-07-25. Branch `claude/3pct-challenge-rd`.

> ## ⚠️ SUPERSEDED — the verdict below is WRONG
>
> This document concluded the 3% wall was "structurally blocked". That was an
> artifact of a blind spot, not a property of the strategy: **every search
> summarized here tuned position sizing and counts, and none of them ever
> controlled overnight exposure.**
>
> The E0 breach-anatomy diagnostic (`E0_FINDINGS.md`) found that **95.5% of the
> loss on breach days came from positions carried overnight** — 5 of 6 breaches
> were 100% overnight. Adding a nightly de-risk control (`NIGHTLY_DERISK`)
> improved **safety and speed simultaneously**, which the "monotonically
> opposed" claim below says is impossible:
>
> | risk | overnight control | breach | completes | median | fastest | p40 |
> |---|---|---|---|---|---|---|
> | 1.0% | off | 25.0% | 25.0% | 165d | 109d | 0% |
> | 1.0% | **on** | **6.2%** | **68.8%** | **76d** | **31d** | 6.2% |
> | 1.6% | off | 43.8% | 12.5% | 94d | 49d | 0% |
> | 1.6% | **on** | 25.0% | **75.0%** | **59d** | **18d** | **31.2%** |
>
> The frontier tabulated below ("minimum breach rate among configs that ever
> passed inside 30 days is 31.2%") no longer holds: p40 = 6.2% is now reached at
> 6.2% breach. See `E2_FINDINGS.md`, and `E3` for the zero-breach search.
>
> **What remains valid below:** the measurements themselves, and the conclusion
> that *within the levers searched there* (entry, ladder, risk/regime, caps,
> universe, cushion, trend) no config passes quickly at 0% breach. The error was
> generalizing "these levers can't" into "nothing can".

## Original (superseded) verdict

**The ~20-30 day target is not reachable on a 3% daily wall with this
strategy. Not "not found yet" — structurally blocked. Evidence below.**

## The question

Can the 2-step High-Stakes challenge (+8% then +5%, closed balance) be passed
in ~20 days (30 acceptable) on the 100k Summer Edition account, whose daily
wall is **3%** of EOD `max(equity, balance)` rather than the classic 5%?

## Evidence base

262 completed Optuna trials across three searches, each trial evaluated on 16
independent start windows (2016/18/21/23 train × Jan/Apr/Jul/Oct) =
**4,192 simulated two-step attempts**, all on the live-faithful universe
(`fiveers_live` profile: metals + NAS100 included, 3 bleeder symbols excluded).

| search | mechanism | trials |
|---|---|---|
| D2 | cushion ratchet (risk scales up with banked profit) | 120 |
| D3 | trend-quality controller (continuous ADX sizing) | 120 |
| D23 | both levers searched jointly | 22 (ongoing) |

Plus the earlier ~2,400 backtests over entry gates, entry shape, TP ladder,
risk/regime sizing, position caps and universe selection.

## The finding: speed and safety are monotonically opposed

Grouping all 262 trials by breach rate and asking how many produced *any*
completion within 60 days:

| breach rate | trials | with a ≤60d completion |
|---|---|---|
| **0%** | 83 | **2 (2%)** |
| ~6% | 91 | 12 (13%) |
| ~12% | 36 | 3 (8%) |
| 15-30% | 28 | 7 (25%) |
| **>30%** | 24 | **15 (62%)** |

Completion probability rises monotonically with breach rate. This is not a
search that failed to find the good region — it is a frontier, and the target
sits off the end of it.

## The decisive table: what speed costs

**Every configuration that ever passed both steps within 30 days:**

| study | trial | pass ≤30d | pass ≤60d | **breach rate** |
|---|---|---|---|---|
| D3 | 58 | 6.2% | 12.5% | **31.2%** |
| D2 | 36 | 6.2% | 6.2% | **37.5%** |
| D2 | 73 | 6.2% | 12.5% | **50.0%** |
| D3 | 39 | 6.2% | 6.2% | **56.2%** |
| D3 | 43 | 12.5% | 12.5% | **68.8%** |
| D2 | 55 | 6.2% | 6.2% | **75.0%** |

**The minimum breach rate among all configs that ever passed inside 30 days is
31.2%.** The trade on offer is: a 6.2% chance of passing in a month against a
31% chance of blowing the account. That is not a strategy, it is a coin flip
weighted against you.

**Best achievable outcome at each breach tolerance:**

| accept breach ≤ | best 30d pass | best 60d pass |
|---|---|---|
| **0%** | **0.0%** | 6.2% |
| 6% | 0.0% | 12.5% |
| 12% | 0.0% | 12.5% |
| 25% | **0.0%** | 12.5% |
| 40% | 6.2% | 18.8% |
| any | 12.5% | 18.8% |

Even accepting a **1-in-4 chance of losing the account**, the 30-day pass rate
is still exactly **zero**. Speed only becomes purchasable past ~31% breach
risk, and even then you are buying a 6% chance.

## The one safe configuration

Exactly **one** distinct config in 4,192 attempts achieves 0% breach while
still completing both steps within 60 days: **D2 trial 117** (D23 t0 is the
same config re-seeded, not an independent hit).

```
risk_per_trade_pct  1.0     CFG_MAX_CUM_RISK    2.5
CUSHION_RATCHET_ENABLE 1    CUSHION_DD_OFF      1.5
CUSHION_T1/M1       3.00 / 1.1
CUSHION_T2/M2       3.75 / 1.2
CUSHION_T3/M3       5.75 / 1.4
CORR_GROUP_CAP 3   MAX_TOTAL_POSITIONS 15
EXCLUDE_SYMBOLS  AUD_NZD,EUR_NZD,AUD_JPY
```

Result: **0% breach**, 1 of 16 windows completes, at **day 68**. It is safe and
it is slow. It beats the do-nothing floor only by removing that floor's single
breach (6.2% → 0%) — a real but narrow win.

## Why the remaining lever (D4) will not close this

D4 was to be an event-calendar throttle — stand aside around high-impact news.
Mechanically it *reduces exposure*: it lowers breach risk and simultaneously
lowers trading opportunity. That moves a config **along** the frontier toward
the safe/slow corner, which is the corner already saturated with 83 trials
returning a 0.0% thirty-day pass rate. It cannot manufacture speed, and speed
is the missing quantity. Running it would spend hours to add another point to
the region of the curve that is already densely and conclusively mapped.

Seven independent mechanisms have now been searched — entry gates, entry shape,
TP ladder, risk/regime sizing, position caps, universe, cushion ratchet, trend
controller. All land on the same frontier. The constraint is not parametric.

## Why the wall does this

The strategy reaches +8% by holding several correlated positions through a
trend. A 3% daily wall on EOD `max(equity, balance)` caps the drawdown of that
cluster at roughly **half** the classic 5% budget. Sizing down to respect the
wall cuts the daily gain rate by about the same proportion, so the +8% step
stretches from ~2 weeks to ~6-9 weeks. Sizing up to keep the pace puts a normal
correlated pullback straight through the wall — which is precisely the 31%+
breach rate in the table above. There is no parameter that decouples the two,
because both are driven by the same position cluster.

## Recommendation

1. **Do not attempt the 3% Summer Edition account with a 20-30 day target.**
   The honest expectation on this account is a ~60-70 day pass at best, and
   only 1 window in 16 achieved even that at 0% breach.
2. **The classic 5% wall account remains the realistic route** to the original
   goal — `STAGEC2_TRIAL4_BACKUP.md`: 37.5% pass ≤20 days at 0% breach. The
   difference between the two accounts is not marginal; it is the difference
   between a working plan and a coin flip.
3. **If the 3% account must be run**, use D2 t117 above, expect ~10 weeks, and
   treat any attempt to accelerate it as account-threatening.

## Carried-forward caveat (applies regardless of the above)

The Phase 1 and Phase 2 winners were computed **before** the metals/NAS100
pipeline fixes on this branch, i.e. on a universe that was silently missing 10
symbols. They must be revalidated on the faithful universe (or pinned with
`EXCLUDE_SYMBOLS=XAU_USD,XAG_USD` to reproduce their original conditions)
before either is trusted with real money. This is independent of Phase 3 and is
the highest-value outstanding task.
