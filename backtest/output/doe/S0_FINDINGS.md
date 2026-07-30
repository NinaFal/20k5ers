# S0 — speed anatomy: what actually makes a pass take ~39 days (step 1)

**Date:** 2026-07-29. 30 canonical starts, step 1 only, NAS100 under the nightly rule.

## Result: three of the four hypotheses are dead

| # | hypothesis | verdict | evidence |
|---|---|---|---|
| 1 | The **3-profitable-days rule** gates the pass | **RULED OUT** | 29/29 passes gated by the profit target. Median 3rd-profitable-day = **10**, median pass = **39**. The rule has ~29 days of slack. |
| 2 | **Too few setups** — long idle stretches | **RULED OUT** | Median idle ratio **13.7%** — the bot trades on ~86% of available days. There is no drought to fix. |
| 4 | **Self-inflicted braking** — halts and risk cuts | **RULED OUT** | Median DDD halts **0**, median DDD reduces **0**, 0/30 breached. Nothing is standing on the brake. |
| 3 | **Earn rate** — the money simply accrues slowly | **CONFIRMED — this is the whole story** | **$242 per active trading day** on a $100k account. |

## The arithmetic

Everything reduces to one number: **$242/active day**, i.e. **0.24%/day**.

```
step 1  = $8,000  / $242  =  33 active days  ->  ~39 calendar days  (matches median 39)
step 2  = $5,000  / $242  =  21 active days  ->  ~24 calendar days
total   = $13,000 / $242  =  54 active days  ->  ~63 calendar days
```

To pass **both steps under 50 calendar days** we need roughly **43 active days**, i.e.

> **$13,000 / 43 ≈ $300 per active day — about 25% more than today.**

That is the entire target, stated as one number. Not a new mechanism: a 25% lift in daily earn rate.

## The other finding: variance dwarfs the median

Step-1 pass day across 30 starts: **min 8 · p25 27 · median 39 · p75 57 · max 75**.

A ~9x spread on an identical config. Time-to-pass is dominated by *which market the attempt lands in*, not by a fixable constant. Two consequences:

1. **"Under 50 days" is a probability, not a guarantee.** Today ~60% of starts already clear step 1 within 50 days; the goal is really to move that fraction up.
2. **Any stage must be judged on the full 100 starts**, never a favourable subset — a 30-day result is well inside the natural noise of this distribution.

## What this means for the stage order

The lever must raise **dollars per active day**. That decomposes as:

```
$/active day  =  trades per active day  x  win rate  x  average $ per winning trade
                 (minus the losing side)
```

Re-ranked by whether a stage can plausibly move that product:

| stage | mechanism | why it can move $/day |
|---|---|---|
| **S1 — ladder / banking rate** | how much of a winner is realized, and how early | Targets are on **closed** balance. Floating profit does not count. This directly converts existing edge into banked dollars — the most direct lever on the number that matters, and the current ladder was tuned for a different wall. |
| **S2 — entry selectivity** (6 filters, fib 3-way) | raises win rate and average win | Fewer, better trades. Risk: fewer trades per day, which cuts the first term — must be measured net, not assumed. |
| **S3 — entry gates** (confluence, quality, ADX, ATR) | same product, different knobs | 12 frozen parameters, all set before the 3% wall existed. |
| **S4 — per-group fib** | per-asset-class entry depth | Refinement once S2/S3 show the effect is real. |
| **S5 — nightly knobs** (4 untuned + hour) | protects the earn rate | E0 proved this decides breaches; here it is defensive, not offensive. |
| **S6 — halt + TDD tiers** | pure safety | **Last.** S0 shows it is currently costing nothing (0 halts, 0 reduces), so tightening it now would only slow things down. Spend it at the end to buy back whatever breaches the faster config introduces. |

**Change from the previous plan:** the ladder moves from 3rd to **1st**. S0 shows the constraint is banked dollars per day, and the ladder is the only lever that acts on *conversion of edge into closed profit* rather than on the edge itself. Everything else has to create new edge; the ladder just realizes what is already there.

**Also dropped:** raising risk per trade. It scales $/day and drawdown in equal proportion, so it moves along the frontier rather than shifting it — and S0 shows we are not currently being braked, meaning the slowness is not a risk-budget problem.

## Caveat on this document

The trade-level statistics (win rate, average win, average loss, trades per day) were computed with a bug — a blank `partial` cell reads as `NaN` from pandas and `bool(NaN)` is `True`, so every full close was misclassified as a partial and the counters read zero. Those three numbers are being re-measured. **The four verdicts above do not depend on them**: they rest on `target_day` vs `third_profit_day`, the idle ratio, the halt counts and `$/active day`, all of which were computed independently of the `partial` flag.
