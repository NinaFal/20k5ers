# 5%ers Bot — Optimization Roadmap

The plan of record for building a funded-account bot that **maximizes net profit
with zero breaches** across out-of-sample, random starts, a 10-year run, and
stress tests. Each stage locks its winner into the next. Nothing is selected on
in-sample data alone.

## North-star objective (priority order — NEVER reorder)

1. **Never breach** — 5%ers hard walls: 5% daily DD (from day-start equity) /
   10% total DD (from initial balance), measured on mark-to-market **equity**.
   This is a HARD VETO, never a soft penalty. Account death = game over.
2. **Maximize net profit** — the real goal, unbounded. $20K/month is the FLOOR,
   "the more the better". You scale past the floor with **big runners**, not
   tighter scratch-wins.
3. **Robustness** — worst-window net (maximin) and survival across every test
   below. Prefer robust *plateaus* over fragile *peaks*.
4. **Win-rate / TP1-hit** — a DIAGNOSTIC that the entry is sound, not a maximize
   target. Win-rate is sensitive to the TP ladder and means little in isolation.

## Entry-quality metrics (why MFE/MAE, not win-rate)

- **MFE (Max Favorable Excursion, in R)** — how far price runs in our favor after
  entry. This is the **runner-potential** metric and it is **TP-ladder-independent**,
  so the best entry stays best regardless of the Stage 3 exit policy.
- **MAE (Max Adverse Excursion, in R)** — how far price goes against us before
  working out. Low MAE → survives to TP1 → drives win-rate.
- The ideal entry **maximizes MFE/MAE separation**, robust across all windows,
  zero breach. High runner potential AND high TP1-survival at once — the way to
  get high win-rate AND big runners instead of trading one for the other.
- Then Stage 3 sets SL just beyond the MAE distribution and TP/trail to capture
  the MFE distribution.

## Stages (each locks its winner into the next)

### Stage 1 — Entry quality (IN PROGRESS)
- **1c grid (692 cells):** entry_fib_level (calm 0.45–0.65) × entry_fib_level_volatile
  (0.0, 0.35–0.80) × fib_vol_ratio_threshold (1.05–1.35) × adx_min_entry (0,15,20,25).
  Scored on avg win-rate + no-breach across 5 windows. Output: `output/doe/stage1c_grid.csv`.
- **1d extension (18 cells):** calm fibs 0.35, 0.40 (winner sat at the 0.45 edge).
  `src/stage1d_lower_calm_fibs.py`.
- **Entry-quality report (NEW):** rerun top-N finalists with MAE/MFE instrumentation;
  rank by (TP1-hit%, MFE-p75, worst-window net), breach = hard veto.
  `src/stage1c_entry_quality_report.py`.
- **Findings so far:** ADX gate consistently HURTS (adx=0 best); thr=1.05 over-trades
  and breaches; best survivor c=0.45 v=0.40 thr=1.15 adx=0 (~48.9% avg WR, no breach).

### Stage 2 — Sizing, risk & breach control (Optuna, ~1000 trials)
- Per-symbol volatility-class multipliers (MAJOR / MID / HIGHVOL asset classes).
- Base risk-per-trade % sweep.
- 4-rung TDD system incl. a 4th "wall" rung (~9.2%) to prevent stalling near the
  10% limit while still de-risking on the way down.
- Progressive ADX/regime tightening (ADX as a regime CONTROLLER that adapts
  sizing/behavior, NOT as a binary skip-gate — that already proved to hurt).
- **This is the primary breach-avoidance machinery.**

### Stage 3 — TP ladder & runners (Optuna)
- Optimize TP1–TPn levels, close %, trailing activation/multiplier ON the locked
  Stage 1+2 config, using the measured MFE distribution to set realistic runner
  targets. **This is the profit-scaling machinery.**

### Stage 4 — Pareto joint optimization
- Joint refinement over the combined space; pick the Pareto-optimal config on
  (net profit, maximin, max worst-case DD) with zero breach.

## Validation gauntlet — the gate that proves "0 breach everywhere"

Applied to finalists BEFORE locking any stage. A config advances only if it
passes ALL of these with zero breach:

| Test | Purpose | Tool |
|------|---------|------|
| **Walk-forward / OOS** | Anti-overfit — THE #1 guard. Select on held-out data, never in-sample. | `src/walk_forward.py` — **promote to the selection gate at every stage** |
| **Gap / slippage stress** | Weekend/news gap jumps the stop. | `src/gap_stress.py` |
| **Worst-case intrabar TDD** | Bar-close equity can miss a wick piercing the wall. | `TDD_WORST_CASE=1` env flag |
| **5 start-date survival** | The literal 5%ers challenge condition. | 5 windows in harness |
| **10-year continuous run** | Compounding, scaling events, withdrawals. | NEEDS dedicated long-run harness |
| **Monte-Carlo trade-order shuffle** | Drawdown is PATH-DEPENDENT; same trades in a worse order can breach. | **NEEDS building** |
| **Parameter-perturbation robustness** | A robust optimum sits on a plateau, not a spike. | `src/robustness_tp.py` — extend to entry/risk |

## Premortem — failure modes we are actively guarding against

1. **Overfit to the 5 in-sample windows.** Guard: OOS/walk-forward as the
   selection gate; prefer plateaus; reject "just barely survives".
2. **Optimizing the wrong metric.** Guard: maximize net profit + MFE runner
   potential, never win-rate alone.
3. **Entry/exit coupling trap.** Guard: MFE is TP-ladder-independent, so the
   chosen entry survives Stage 3.
4. **Averages hide fragility.** Guard: select on worst-window (maximin), not mean.
5. **Path-dependent drawdown.** Guard: Monte-Carlo trade-order shuffle.
6. **Destabilizing a running optimization.** Guard: never edit the live engine
   while a sweep runs; develop on isolated worktrees; apply after completion.

## Honest caveat

No backtest process can GUARANTEE zero breaches on unseen future data — markets
produce events no history contains. This process delivers a config that has
never breached across OOS + gap + worst-case + Monte-Carlo + 10-year, which is as
robust as testing can prove. Keep worst-case drawdown well UNDER 10%, never at it.
