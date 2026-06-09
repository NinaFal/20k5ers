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

### Stage 1 — Entry quality (✅ COMPLETE 2026-06-09)

**Result:** 710 cells swept (692 1c + 18 1d), MFE/MAE report run on top-16
survivors. TP1-hit% near-flat (76–81%) → real discriminators are net, maximin,
MFE-p75. Deep-volatile entries (v=0.75–0.80) won on runner potential (1.65–1.74R);
the 50%-WR config had the weakest runners (1.49R, rejected). **Two finalists
carried into Stage 2:** A = c=0.55 v=0.80 thr=1.05 (MFE 1.74R, maximin $28.7K);
B = c=0.45 v=0.80 thr=1.15 (net $70K, MFE 1.65R). Report:
`output/doe/stage1c_entry_quality_report.csv`. Full detail in SESSION_HANDOFF §0.

<details><summary>Original Stage 1 plan (for reference)</summary>

- **1c grid (692 cells):** entry_fib_level (calm 0.45–0.65) × entry_fib_level_volatile
  (0.0, 0.35–0.80) × fib_vol_ratio_threshold (1.05–1.35) × adx_min_entry (0,15,20,25).
  Scored on avg win-rate + no-breach across 5 windows × 3yr each. Output:
  `output/doe/stage1c_grid.csv`. Skip-if-done on restart. Watchdog auto-commits
  every 20 min. **Best so far: `c=0.45 v=0.40 thr=1.15 adx=0` — score 48.92,
  avg $57K net/3yr window on $50K account (~34% annual ROI).**
- **1d extension (18 cells):** calm fibs 0.35, 0.40 — because the 1c winner
  sits at the floor (0.45), shallower calm fibs may score even higher.
  `src/stage1d_lower_calm_fibs.py`. Writes to the SAME `stage1c_grid.csv`.
  Auto-chained by `grid_watchdog.sh` when 1c hits 692.
- **Entry-quality report:** rerun top-N finalists with MAE/MFE instrumentation;
  rank by (TP1-hit%, MFE-p75, worst-window net), breach = hard veto.
  `src/stage1c_entry_quality_report.py`. MFE tools on worktree branch
  `worktree-agent-a0059c8061087a5b1` — cherry-pick 3 files after grid completes.
- **Key findings:**
  - ADX gate consistently HURTS — adx=0 best everywhere; adx≥15 breaches or
    underperforms. Revisit ADX ONLY as a regime controller in Stage 2.
  - thr=1.05 over-trades and breaches (370+ trades/window → exposure → wall).
    Winner zone: thr=1.15–1.35.
  - Calm fib floor dominates: c=0.45 holds all top-5 slots → Stage 1d needed.
  - Volatile fib v=0.40–0.75 all survive with c=0.45; MFE will rank them.
  - Pass rate ≈ 11% (43/456 clean survivors).
- **Net profit context:** Stage 1 with default TPs yields ~$17K/yr on $50K.
  Stages 2+3 (risk sizing, TP ladder) are the profit multipliers. The
  $20K+/month goal is reached via 5%ers account scaling + Stage 2–3 gains.

</details>

### Stage 2 — Sizing, risk & breach control (Optuna) — IN PROGRESS
Run for BOTH locked entries (A: c=0.55 v=0.80 thr=1.05; B: c=0.45 v=0.80 thr=1.15);
decide the entry winner on post-sizing net + zero-breach. Driver:
`src/stage2_sizing_risk.py` (resumable sqlite Optuna study per entry, keepalive-wrapped).

**Levers WIRED today (Stage 2a — optimize these now):**
- Base risk-per-trade % (`risk_per_trade_pct` via OPT_PARAMS; engine line ~3171).
- Vol-scaled sizing mults `VOL_SIZE_MULT_LOW` / `_HIGH`.
- Regime gate `VOL_REGIME_DD_OFF` (size-up only while healthy — the proven win).
- Cumulative open-risk cap `CFG_MAX_CUM_RISK`; daily halt `CFG_DAILY_HALT_PCT`.
- 3-rung TDD: `CFG_TDD_CAUTION/WARNING/EMERGENCY_PCT` + matching `CFG_RISK_*`.

**Levers NOT wired yet (Stage 2b — require engine work first):**
- Per-symbol volatility-class multipliers (MAJOR / MID / HIGHVOL) — no lever exists.
- 4th "wall" TDD rung (~9.2%) — only 3 rungs wired today.
- ADX as a regime CONTROLLER (adaptive sizing, NOT a binary skip-gate — the gate
  already proved to hurt in Stage 1).

- **This is the primary breach-avoidance machinery.** Objective: maximin net
  across multi-year starts, hard breach veto, DD-margin penalty (keep worst-case
  TDD well under 10%). Reuses the proven `optimize_multistart.py` scoring.

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
