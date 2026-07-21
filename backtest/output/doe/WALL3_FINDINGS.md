# The 3% daily wall — comprehensive finding (C1 restart + C3 at scale)

**Date:** 2026-07-21. After two full staged searches under the corrected 3%
5%ers "Summer Edition" wall (C3: 129 Optuna trials tuning risk/regime on the
OLD entry+ladder; C1 restart: 24 entry shapes × 2 risk levels × 16 starts =
384 cells, ~900 backtests total), the conclusion is consistent and decisive.

## Bottom line

**Under the true 3% daily wall, this strategy (selective HTF-confluence entry,
~1 trade/day) does not have a reliably fast, safe path to +8%.** Across all 24
entry-shape/risk combinations tested:

- **p(pass ≤20 days) = 0.00 for EVERY config.** Not one combination passes
  Step 1 within 20 days on any meaningful share of starts.
- The safest config (`c=0.45 v=0.80 thr=1.05`, risk 1.0%) has **0% breach**
  but only **1 of 16 starts completes at all** (52 days, on a strongly
  trending window) — everything else never reaches +8% within the 40-day cap.
- Pushing risk to 1.5% roughly **doubles breach rate** (19→44% across
  matched configs) for only a marginal gain in pass rate (best p40 = 0.12,
  i.e. 2/16 starts, at 38% breach).

There is no config in the tested space that is both meaningfully fast AND
safe. The tradeoff is stark: **safe = usually frozen; faster = 20-44% breach.**

## Why (root cause, confirmed across three investigations)

1. Entry gates are non-binding (confluence/quality/ATR thresholds don't limit
   trade count — CHALLENGE_20DAY_FINDINGS.md).
2. The strategy is inherently low-frequency (~1 trade/day) — this doesn't
   change with entry shape, only which trades are taken.
3. A 3% daily wall + a real total-position cap (needed — see
   diag_wall3_anomaly.py) bounds concurrent risk hard enough that reaching
   $8,000 of REALIZED profit takes many weeks in most market regimes, and the
   regimes with enough velocity to go faster also carry a meaningfully higher
   chance of a bad day breaching 3%.

## Options going forward

1. **Accept a long timeline on THIS account.** Use the safest config
   (c=0.45/v=0.80/thr=1.05, risk ~1.0%, MAX_TOTAL_POSITIONS~15) and expect the
   challenge to take considerably longer than 20-40 days in most windows —
   possibly much longer, since most TRAIN starts never reached target within
   40 days at all. This is genuinely uncertain; we have not measured the
   REAL median time at a 90+ day horizon.
2. **Accept a moderate breach-risk tradeoff for speed** — e.g. risk 1.5%,
   ~25-40% chance any given attempt breaches, but when it doesn't, ~40 days
   to pass. Means budgeting for possibly multiple challenge attempts.
3. **Use a classic 5% daily wall account instead**, if available. The FIRST
   C1→C2 pipeline (before the wall correction) found a genuinely strong
   config for that wall: 37.5% pass ≤20 days, 0% breach, score 174.8 — saved
   in STAGEC2_TRIAL4_BACKUP.md. This is a real, already-proven-fast option,
   just not for the Summer Edition (3%) account.
4. **A higher-frequency entry model.** The fundamental limiter is trade
   velocity. A different (lower-timeframe or less selective) entry system
   could bank $8k faster, but this is new strategy R&D, not a parameter tune
   of the existing HTF system — a much larger undertaking.

## What was NOT yet tried (possible next steps if continuing on this path)

- A longer horizon test (90-180 days) to get the REAL median time-to-pass
  distribution for the safest config, rather than treating "no pass in 40
  days" as a hard failure — most of the "frozen" starts may pass eventually.
- A finer risk sweep between 1.0 and 1.5% (e.g. 1.1, 1.2, 1.3) to look for a
  sweet spot the 2-point grid may have stepped over.
- Testing whether a SMALLER `MAX_TOTAL_POSITIONS` (e.g. 8-10) combined with
  HIGHER per-trade risk changes the tradeoff shape (C3's data was suggestive
  but not conclusive on this interaction).

Reproduce: `uv run python3 backtest/src/stageC1_entry_shape.py`
Raw data: `output/doe/stageC1_wall3.json` (384 cells),
`output/doe/stageC3_wall3.csv` (129 Optuna trials).
