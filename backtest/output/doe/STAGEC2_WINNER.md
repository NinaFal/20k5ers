# Stage C2 Winner — fast-banking TP ladder for the challenge objective

**Date:** 2026-07-21. Optuna search (150 trials, resumable through 1 container
restart) over tp1-3 R-multiples + close%s + sl-trail-after levels. Entry locked
to C1 winner (c=0.65 v=0.65 thr=1.15), risk fixed at 3.5%, scored on the 16
TRAIN starts via `challenge_score.py`.

## Top result — a peak, not a plateau (flagged per roadmap premortem #4)

| rank | trial | score | p20 | p40 | breach | medTot | tp1/2/3 R | c1/c2 |
|---|---|--:|--:|--:|--:|--:|---|---|
| 1 | **t4** | **174.8** | 0.375 | 0.625 | 0.0 | 20 | 0.40/0.75/1.35 | 0.50/0.35 |
| 2 | t9 | 156.0 | 0.312 | 0.625 | 0.0 | 24 | 0.40/1.45/2.25 | 0.70/0.60 |
| 3-8 | t49,59,61,72,81,87 | **149.8 (all six)** | 0.312 | 0.562 | 0.0 | 19 | ~0.50/1.35/2.25 | ~0.58/0.55 |

**t4 sits alone** — a tight, fast-banking ladder (TP1 at 0.4R!, 50% closed
immediately) that scores well above everything else, with no nearby trials
replicating it. **Six separate trials independently converged on a materially
different, wider ladder** (~0.5/1.35/2.25R) at 149.8 — that repetition is the
signature of a genuine plateau. t4 might be the better answer, or might be an
artifact of fitting the 16 TRAIN starts (the concern the whole train/holdout
split exists to catch).

## Decision: lock t4 for C3, but carry the plateau rep as a challenger

Locking the top score (t4) into Stage C3 to keep the roadmap moving — but
**both t4 and the plateau representative (t61: score 149.8, tp
0.55/1.40/2.40R, c1=0.60/c2=0.60) must be carried through C4 and validated
head-to-head on the HOLDOUT starts in C5.** If t4 doesn't hold up out-of-sample
and the plateau rep does, the plateau rep becomes the pick — this is exactly
what the anti-overfit protocol in CHALLENGE_ROADMAP.md is for.

## Locked ladder for C3 (primary candidate)

```
tp1_r_multiple = 0.40   tp1_close_pct = 0.50
tp2_r_multiple = 0.75   tp2_close_pct = 0.35
tp3_r_multiple = 1.35   tp3_close_pct = 0.15   (100% closed by TP3)
tp4/5_r_multiple = tp3+1.0 / tp3+2.0, close 0% (unreachable, challenge-phase only)
sl_after_tp2_r = 0.25
sl_after_tp3_r = 0.60
risk_per_trade_pct = 3.5  (C3 will retune jointly with regime mults)
```

## Challenger (plateau rep, for C4/C5 comparison)

```
tp1_r_multiple = 0.55   tp1_close_pct = 0.60
tp2_r_multiple = 1.40   tp2_close_pct = 0.60   -> engine closes 100% here
tp3_r_multiple = 2.40   tp3_close_pct = 0.00   -- position never reaches TP3
sl_after_tp2_r = 0.30
sl_after_tp3_r = 1.30
```
**Note on c1+c2 > 1.0:** several plateau rows (e.g. t61: c1=0.60+c2=0.60=1.20)
have `_suggest()`'s clip `c3 = max(0.0, 1.0-c1-c2)` = 0. Verified this is
CORRECT, not a bug: the engine clamps `close_volume = min(requested,
current_volume)` (main_live_bot_backtest.py:4745/4784), so when tp1+tp2 close
requests exceed 100%, the position is simply fully closed by TP2 — a real,
independently-discovered **2-effective-TP ladder** shape (6 different trials
converged on it), not an artifact. TP3 in these configs is unreachable.

Full 150-trial log: `output/doe/stageC2.csv`.
