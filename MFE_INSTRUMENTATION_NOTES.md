# MAE/MFE Entry-Quality Instrumentation — Change Notes

Worktree branch: `worktree-agent-a0059c8061087a5b1` (isolated; does NOT touch the
running sweep in the main working dir).

Goal: add per-trade MAE/MFE (in R-multiples) + a multi-objective "entry quality"
report so fib entry setups can be ranked by runner-potential and TP1-survival, not
just net win-rate. All engine changes are **purely additive instrumentation** —
win_rate, net_pnl, trade count, and breach behavior are bit-identical to before.

---

## Files changed

### 1. `backtest/src/main_live_bot_backtest.py`

| Lines (approx) | What |
|---|---|
| 5393–5448 | New method `_mark_mfe_mae(self, current_time)` — marks each open position to its M15 bar high/low and records the peak favorable / adverse extreme in `self._mfe_mae[ticket]`. Locks initial entry→SL risk on first sighting. Fully wrapped in try/except; writes ONLY to `self._mfe_mae`. |
| ~5500–5506 | Initialize `self._mfe_mae = {}` alongside the other `run_backtest` tracking vars. |
| ~5598–5602 | Call `self._mark_mfe_mae(current_time)` once per bar, right after `self.mt5.set_current_time(...)` and BEFORE any SL/TP processing, so the full bar excursion is captured even on the closing bar. |
| ~5989–6058 | Results aggregation: join `self._mfe_mae` onto each FULL closed trade, attach `mfe_r` / `mae_r` (R-multiples, floored at 0), compute `mfe_r_median`, `mfe_r_p75`, `mae_r_median`, and `tp1_hits` (full trades that spawned ≥1 partial close). Local `_median` / `_percentile` helpers. |
| ~6135–6143 | Add `mfe_r_median`, `mfe_r_p75`, `mae_r_median`, `tp1_hits`, `tp1_hit_rate` to the returned `results` dict (next to `win_rate`). |

### 2. `backtest/src/doe_harness.py`

| Lines (approx) | What |
|---|---|
| ~171–200 | `extract_attrs`: surface `mfe_r_median`, `mfe_r_p75`, `mae_r_median`, `tp1_hits`, `tp1_hit_rate` with safe `0` defaults in BOTH the `r is None` branch and the normal branch (so an older `results.json` that never emitted them yields well-formed scalars, never a `KeyError`). |

### 3. `backtest/src/stage1c_entry_quality_report.py` (NEW)

Standalone analysis script mirroring `stage1d_lower_calm_fibs.py`:
importlib import of `doe_harness`, the `PINNED` lever dict, `stage1c_grid.csv`
reading, and `ProcessPoolExecutor` usage. Reads the top-N grid finalists (by
`score`), re-runs each across the 5 `STAGE1_WINDOWS` via `dh.run_single`, and prints
a multi-objective table per finalist: trades, TP1-hit%, SL-out%, MFE_R median & p75,
MAE_R median, per-window net, maximin (worst-window net), breach status. Ranked
Pareto-style over `(tp1_hit_rate, mfe_r_p75, maximin)` with breach as a hard veto.
Has a `--top N` flag (default 8). **Not run** (grid still executing).

---

## Definitions

- **MFE_R** = furthest favorable excursion (bar high for longs, bar low for shorts)
  minus entry, divided by the **original** entry→SL risk. Floored at 0.
- **MAE_R** = furthest adverse excursion before close, same R basis. Floored at 0.
- **Initial risk** is captured on the FIRST bar a ticket is seen. Because marking
  runs at the top of the bar loop (before partial-exit SL trailing), `pos.sl` is
  still the ORIGINAL stop at that moment, so R is always measured against the true
  entry→SL distance even after the SL is trailed to breakeven post-TP1.
- **TP1-hit** = a full trade whose base ticket spawned ≥1 partial close (the first
  partial-ladder rung is TP1, where `setup.tp1_hit` is set). `tp1_hit_rate` =
  `tp1_hits / total_trades * 100`.
- **SL-out%** (in the report) = `100 − tp1_hit_rate` (entries stopped before TP1).

---

## Why it is behavior-neutral (additive only)

- `_mfe_mae` is a **side dict**. Nothing in any decision path (entry, exit, SL/TP,
  sizing, DDD/TDD wall checks, breach registration, PnL) ever reads from it. It is
  read exactly once, at results-compile time, to annotate the trade records and
  produce summary scalars.
- `_mark_mfe_mae` is read-only against simulator state (`get_my_positions`,
  `get_m15_bar`) and is fully wrapped in try/except so it can never raise into the
  loop. It returns nothing the caller uses.
- The results-time loop adds NEW keys (`mfe_r`, `mae_r`) to trade dicts and computes
  NEW result keys. It runs BEFORE `total_trades` / `winners` / `win_rate` are
  derived and never touches `pnl` / `partial` / existing keys, so all legacy metrics
  are unchanged.
- `extract_attrs` only ADDS keys with `0` defaults; existing keys/return shape are
  unchanged.

### Residual notes / risks (could not fully rule out by static review alone)
- **Side output:** `trades.csv` will gain two extra columns (`mfe_r`, `mae_r`).
  This is an output artifact only; it does not affect any computed metric.
- **Entry-bar excursion:** excursion is measured from the bar AFTER the fill bar
  (positions fill at the end of a bar's loop; marking happens at the top of the next
  bar). The fill-bar's own post-entry excursion is not counted. This is a consistent,
  standard convention and identical across all configs, so it does not bias ranking.
- **Verification gap:** the dataset/cache needed for a real run is not present in this
  worktree, so bit-identity of `win_rate`/`net_pnl` was confirmed by static diff
  review (additive-only argument above), not by an actual A/B execution. `py_compile`
  passes on all three files.

---

## One command to run the report (AFTER the grid completes)

```bash
python -u backtest/src/stage1c_entry_quality_report.py
# or pick how many top-by-score finalists to re-run:
python -u backtest/src/stage1c_entry_quality_report.py --top 12
```
