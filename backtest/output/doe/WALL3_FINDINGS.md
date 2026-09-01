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

## UPDATE 2026-07-21 — relaxed target (20d ideal / 30d = pass), widened horizon

User relaxed the target: ~20 days ideal, but passing both steps within a
MONTH (30 days total) also counts as a good outcome. Re-ran with STEP_HORIZON
widened 40→60 days per step (so genuinely slow-but-real completions are
measured, not truncated into a false "fail") and a `p30` metric added.
Follow-up grid: 16 configs (shallower calm fibs 0.35-0.50 × finer risk steps
0.8/1.0/1.2/1.5%, holding v=0.80/thr=1.05 fixed — the safest combo from the
first restart) × 16 TRAIN starts = 256 cells.

**Result: `p30 = 0.00` for EVERY one of the 16 configs.** Not a single start,
at any tested entry shape or risk level, completes both steps within 30 days.
The best configs (c=0.35/0.45, risk 1.0%) are 0% breach with median completion
**~52 days** when they do finish — but that's only 1 of 16 starts even within
a full 60-day window; most remain frozen well past that.

**This is now conclusive, not merely suggestive: the ~20-30 day target is not
achievable with this strategy under the 3% wall**, at any combination of
entry shape and risk tested across two full restart cycles (640 cells / ~1500
backtests total for Phase 3). Real timescale for the safest configs is
2-4+ months in typical conditions, with most windows not completing within
even that.

## Options going forward — high-frequency trading explicitly RULED OUT

Per explicit instruction: **a higher-frequency entry model is NOT to be
pursued** for this account. That removes the one lever that could
structurally fix the root cause (trade velocity). Remaining options:

1. **Accept the long timeline on THIS account.** Use the safest found config
   (c=0.35-0.45 / v=0.80 / thr=1.05, risk ~1.0%, MAX_TOTAL_POSITIONS~15,
   bank_fast-style ladder) and expect the challenge to take on the order of
   months, not weeks, in most market conditions — with 0% breach in the
   tested windows. This is the only genuinely safe option within scope.
2. **Accept a moderate breach-risk tradeoff for whatever modest speed exists**
   — e.g. risk 1.5%, ~25-40% chance any given attempt breaches. Means
   budgeting for possibly multiple challenge attempts. Still doesn't reach
   30 days reliably even accepting the breach risk.
3. **Use a classic 5% daily wall account instead**, if available. The FIRST
   C1→C2 pipeline (before the wall correction) found a genuinely strong,
   FAST config for that wall: 37.5% pass ≤20 days, 0% breach, score 174.8 —
   saved in STAGEC2_TRIAL4_BACKUP.md. This is the only path that actually
   meets the original ~20-30 day goal, but requires a different account type.

## Status: Phase 3 (3% wall) R&D — continuing on a separate branch

This work continues as ongoing R&D on `claude/3pct-challenge-rd` (forked from
this branch). Phase 1 (funded account) and Phase 2 (classic 5% challenge) are
locked/stable findings; Phase 3 remains open — see MASTER_FINDINGS.md for the
full three-phase summary and current status of each.

Reproduce: `uv run python3 backtest/src/stageC1_entry_shape.py`
Raw data: `output/doe/stageC1_wall3.json` (384 cells, first restart),
`output/doe/stageC1_wall3_month.json` (256 cells, relaxed-target follow-up),
`output/doe/stageC3_wall3.csv` (129 Optuna trials).
