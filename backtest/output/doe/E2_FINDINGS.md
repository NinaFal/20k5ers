# E2 — NIGHTLY_DERISK moves the speed/safety frontier

**Date:** 2026-07-25. Branch `claude/3pct-challenge-rd`.

## The lever

E0 showed 95.5% of breach-day loss comes from positions carried overnight. The
bot already had a good answer to that risk — a Tier-1 correlation-aware
selector that closes losers, halves young positions, holds winners, and caps
both per-correlation-group and total exposure — but it **only ran on Fridays**.

`NIGHTLY_DERISK` (env-gated, default off) runs that same selector every night
at `NIGHTLY_DERISK_HOUR`. Friday is left to the existing weekend path so the
two don't double-derisk.

### A bug worth recording

`select_positions_for_weekend_tier1` hard-gated on Friday 19:30+ *inside* the
function and returned HOLD-everything otherwise. The first wiring therefore ran
every night and did **nothing** — an A/B showed byte-identical results. Had that
gone unnoticed it would have produced a confident, completely false finding that
"overnight de-risking doesn't help". Fixed with an explicit
`enforce_friday_gate` parameter (default `True`, so Friday behavior is
unchanged); the nightly caller passes `False`.

**Lesson: always A/B a new lever against a case it is supposed to change before
searching over it.**

## Result — 16 TRAIN starts, full two-step, horizon 90d/step

Arms are paired: same skeleton, same risk, only the overnight control differs.

| risk | overnight | breach | completes | median | fastest | p30 | p40 | p60 |
|---|---|---|---|---|---|---|---|---|
| 1.0% | off | 25.0% | 25.0% | 165d | 109d | 0% | 0% | 0% |
| 1.0% | **on** | **6.2%** | **68.8%** | **76d** | **31d** | 0% | 6.2% | 25.0% |
| 1.6% | off | 43.8% | 12.5% | 94d | 49d | 0% | 0% | 6.2% |
| 1.6% | **on** | 25.0% | **75.0%** | **59d** | **18d** | **12.5%** | **31.2%** | **43.8%** |

At matched risk, **every axis improves at once** — breach down, completions up,
median down, fastest down. That is not movement along a frontier; it relocates
it. Overnight gap risk was costing safety *and* speed, because breaching ends
the attempt.

## What this overturns

`PHASE3_FINAL_ASSESSMENT.md` concluded speed and safety were "monotonically
opposed" and that the minimum breach rate among configs ever passing inside 30
days was **31.2%**. With the overnight control:

- p40 = 6.2% at **6.2%** breach (was: impossible below 31.2%)
- p40 = 31.2% and p30 = 12.5% at 25% breach
- fastest single window **18 days**

The old frontier was real *for the levers searched* — it was never a property of
the strategy. The generalization was the error.

## Against the previous champion

| | D2 t117 (old best) | nightly @ 1.0% |
|---|---|---|
| breach | 0% | 6.2% |
| windows completing | 1 / 16 | **11 / 16** |
| median | 68d | 76d |
| fastest | 68d | **31d** |

## Not done

The user's criterion is **zero** breach. 1.0%/on is at 6.2% (one window of 16).
All five overnight knobs — hour, max-per-group, max-total, the R threshold for
closing vs halving, and the reduce fraction — were at first-guess defaults for
every number above. None had been searched. That is `E3`.
