#!/usr/bin/env python3
"""
Stage 1c: Joint entry-quality sweep.

WHY THIS STAGE:
  Stage 1 grid (stage1_grid.csv) proved that of the 2D entry-pricing space,
  fib=0.50/offset=0.0 is the lone survivor on all 5 regime windows — but
  "surviving" a 3-year window is not the same as "best entry quality". Here we
  ask: can a VOLATILITY-ADAPTIVE fib (shallow calm, deep volatile) combined with
  an ADX trend-quality gate increase win-rate while keeping trade frequency
  healthy? Better entries mean fewer consecutive losers, less drawdown, and more
  headroom for the safety-sizing stage (Stage 2) to compound cleanly.

LEVERS (4 dimensions):
  entry_fib_level            calm-regime fib entry level
  entry_fib_level_volatile   fib in volatile regime (0.0 = disabled)
  fib_vol_ratio_threshold    ATR(14)/ATR(50) ratio that triggers volatile mode
  adx_min_entry              skip trend-weak setups with ADX below this (0=off)

  Both shallower (volatile < calm) and deeper (volatile > calm) pairs are swept.
  Shallower-in-volatile: enter early before fast markets reverse past your level.
  Deeper-in-volatile: wait for a bigger pullback that volatile markets often reach.
  When volatile=0.0 the threshold dimension is collapsed to one value (irrelevant).

SCORING:
  Primary: avg_win_rate across 5 windows.
  Guard:   cells with avg_trades < MIN_TRADES_PER_WINDOW (30) are penalized
           2 pct-points per missing trade — prevents over-filtering from
           starving the account.

  score = avg_win_rate - 2 * max(0, MIN_TRADES - avg_trades_per_window)

  Win-rate is the RIGHT objective here: we will optimise return (TP ladder,
  sizing) with later stages — what we need now are clean, high-probability
  entries that don't bleed the account during weak-trend periods.

CRASH-PROOF: each cell appends one row to stage1c_grid.csv on completion.
None-result windows (OOM/timeout) trigger IncompleteCell → cell NOT written
→ restart re-runs it. skip-if-done cache prevents double-work.
Parallel across cells (WORKERS_SHORT = 4).

Usage:
  uv run python -u backtest/src/stage1_entry_quality.py --phase grid
  uv run python -u backtest/src/stage1_entry_quality.py --phase validate
  uv run python -u backtest/src/stage1_entry_quality.py --phase all
"""
import argparse
import concurrent.futures
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE  = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh    = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR   = dh.DOE_DIR
GRID_CSV  = DOE_DIR / "stage1c_grid.csv"
TOP5_JSON = DOE_DIR / "stage1c_top5.json"
WORKERS   = dh.WORKERS_SHORT        # 4 — safe for short windows
WINDOWS   = dh.STAGE1_WINDOWS       # 5 short multi-regime slices

MIN_TRADES_PER_WINDOW = 30          # trade-frequency floor before penalty fires
PENALTY_PER_TRADE     = 2.0         # pct-pts deducted per missing trade below floor

# ── 4-D grid ─────────────────────────────────────────────────────────────────
GRID_FIB_CALM = [0.45, 0.50, 0.55, 0.60, 0.65]
# 0.0 = feature disabled (no vol-adaptation)
# Shallower-than-calm values (0.35–0.45): enter early in volatile swings —
#   fast-moving markets may reverse before reaching a deep pullback level
# Deeper-than-calm values (0.65–0.80): wait for bigger pullback in volatile —
#   volatile markets often overshoot; deeper entry = better R:R
# Both hypotheses are valid; the data decides which wins.
GRID_FIB_VOL  = [0.0, 0.35, 0.40, 0.45, 0.50, 0.65, 0.70, 0.75, 0.78, 0.80]
GRID_VOL_THR  = [1.05, 1.15, 1.25, 1.35]
GRID_ADX      = [0, 15, 20, 25]

# Levers pinned at best known values (OAT + Stage 1 grid proof)
PINNED = {
    "trend_min_confluence":   6,
    "range_min_confluence":   3,
    "min_quality_factors":    3,
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
    "entry_limit_offset_atr": 0.0,   # Stage 1 grid winner
}

CSV_HEADER = [
    "entry_fib_level", "entry_fib_level_volatile", "fib_vol_ratio_threshold",
    "adx_min_entry",
    "avg_wr", "min_wr", "avg_trades", "min_trades",
    "avg_net", "maximin", "breached", "n_survived",
    "wr_w0",     "wr_w1",     "wr_w2",     "wr_w3",     "wr_w4",
    "net_w0",    "net_w1",    "net_w2",    "net_w3",    "net_w4",
    "trades_w0", "trades_w1", "trades_w2", "trades_w3", "trades_w4",
    "score", "elapsed_s",
]


def _build_cells() -> list:
    """
    Build the list of (calm, volatile, threshold, adx) tuples to sweep.

    Rules:
    - volatile != calm when volatile != 0.0  (skip identical — redundant with single-fib)
    - when volatile == 0.0, only test one threshold value (feature is off, so
      threshold has no effect — avoid running 4× the same experiment)
    Both shallower (volatile < calm) and deeper (volatile > calm) pairs are tested;
    the data decides which direction helps win-rate.
    """
    cells = []
    for fib_c in GRID_FIB_CALM:
        for fib_v in GRID_FIB_VOL:
            if fib_v != 0.0 and fib_v == fib_c:
                continue  # skip identical — same as no vol-adaptation
            thresholds = GRID_VOL_THR if fib_v != 0.0 else [GRID_VOL_THR[0]]
            for thr in thresholds:
                for adx in GRID_ADX:
                    cells.append((fib_c, fib_v, thr, adx))
    return cells


def _load_done() -> set:
    done = set()
    if not GRID_CSV.exists():
        return done
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            done.add((row["entry_fib_level"], row["entry_fib_level_volatile"],
                      row["fib_vol_ratio_threshold"], row["adx_min_entry"]))
    return done


def _cell_key(fib_c, fib_v, thr, adx) -> tuple:
    return (str(fib_c), str(fib_v), str(thr), str(adx))


class IncompleteCell(Exception):
    """Raised when a window returns None after retries (infra failure)."""


def _run_cell(args: tuple) -> dict:
    """
    Run one cell across all 5 short windows.
    None result from any window raises IncompleteCell → NOT written to CSV
    so a restart re-runs this cell automatically.
    """
    fib_c, fib_v, thr, adx = args
    t0 = time.time()

    tp = dict(PINNED)
    tp["entry_fib_level"]           = fib_c
    tp["entry_fib_level_volatile"]  = fib_v
    tp["fib_vol_ratio_threshold"]   = thr
    tp["use_trend_quality_gate"]    = adx > 0
    tp["adx_min_entry"]             = float(adx)

    nets, wrs, trades_list, failed_list = [], [], [], []

    for start, end in WINDOWS:
        r = dh.run_single({}, tp, start, end)
        if r is None:
            raise IncompleteCell(f"window {start}->{end} returned None")
        a = dh.extract_attrs(r)
        nets.append(a["net"])
        wrs.append(a["win_rate"])
        trades_list.append(a["trades"])
        failed_list.append(a["failed"])

    elapsed    = round(time.time() - t0)
    breached   = any(failed_list)
    n_survived = sum(1 for f in failed_list if not f)

    avg_wr     = round(sum(wrs) / len(wrs), 2)           if wrs else 0.0
    min_wr     = round(min(wrs), 2)                       if wrs else 0.0
    avg_trades = round(sum(trades_list) / len(trades_list)) if trades_list else 0
    min_trades = min(trades_list)                          if trades_list else 0
    avg_net    = round(sum(nets) / len(nets))             if nets else 0
    maximin_v  = (min(nets) if not breached
                  else -1_000_000 + int(min(nets)))

    # Score: avg win-rate with a hard penalty for low trade frequency
    trade_penalty = PENALTY_PER_TRADE * max(0.0, MIN_TRADES_PER_WINDOW - avg_trades)
    score = round(avg_wr - trade_penalty, 3)

    return {
        "entry_fib_level":           fib_c,
        "entry_fib_level_volatile":  fib_v,
        "fib_vol_ratio_threshold":   thr,
        "adx_min_entry":             adx,
        "avg_wr":                    avg_wr,
        "min_wr":                    min_wr,
        "avg_trades":                avg_trades,
        "min_trades":                min_trades,
        "avg_net":                   avg_net,
        "maximin":                   maximin_v,
        "breached":                  breached,
        "n_survived":                n_survived,
        "wr_w0": wrs[0], "wr_w1": wrs[1], "wr_w2": wrs[2],
        "wr_w3": wrs[3], "wr_w4": wrs[4],
        "net_w0": nets[0], "net_w1": nets[1], "net_w2": nets[2],
        "net_w3": nets[3], "net_w4": nets[4],
        "trades_w0": trades_list[0], "trades_w1": trades_list[1],
        "trades_w2": trades_list[2], "trades_w3": trades_list[3],
        "trades_w4": trades_list[4],
        "score":     score,
        "elapsed_s": elapsed,
    }


def phase_grid():
    cells = _build_cells()
    done  = _load_done()
    todo  = [c for c in cells if _cell_key(*c) not in done]

    print(f"\n{'='*78}")
    print(f"  Stage 1c — Entry Quality: vol-adaptive fib × ADX gate")
    print(f"  {len(cells)} cells total  |  {len(done)} cached  |  {len(todo)} to run")
    print(f"  Scoring: avg_win_rate − penalty(trades<{MIN_TRADES_PER_WINDOW})")
    print(f"  {WORKERS} workers  |  {len(WINDOWS)} windows per cell")
    print(f"{'='*78}\n")
    sys.stdout.flush()

    write_header = not GRID_CSV.exists() or GRID_CSV.stat().st_size == 0
    with open(GRID_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if write_header:
            writer.writeheader(); f.flush()

        with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(_run_cell, c): c for c in todo}
            for fut in concurrent.futures.as_completed(futures):
                cell = futures[fut]
                try:
                    row = fut.result()
                except Exception as e:
                    print(f"  SKIP  calm={cell[0]} vol={cell[1]} thr={cell[2]}"
                          f" adx={cell[3]}  — {type(e).__name__}: {e}")
                    sys.stdout.flush(); continue

                writer.writerow(row); f.flush()
                breach_tag = "BREACH" if row["breached"] else "ok"
                print(f"  c={row['entry_fib_level']:.2f} v={row['entry_fib_level_volatile']:.2f}"
                      f" thr={row['fib_vol_ratio_threshold']:.2f} adx={row['adx_min_entry']:>2}"
                      f"  [{breach_tag}]"
                      f"  wr={row['avg_wr']:>5.1f}% (min {row['min_wr']:>5.1f}%)"
                      f"  trades={row['avg_trades']:>3} (min {row['min_trades']:>3})"
                      f"  avg_net={row['avg_net']:>9,}  score={row['score']:>6.2f}"
                      f"  {row['elapsed_s']}s")
                sys.stdout.flush()

    print(f"\n  Grid complete → {GRID_CSV}")
    _print_summary()


def _print_summary():
    if not GRID_CSV.exists():
        return
    rows = []
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            rows.append(row)

    survivors = [r for r in rows if r["breached"] == "False"]
    survivors.sort(key=lambda r: float(r["score"]), reverse=True)
    all_sorted = sorted(rows, key=lambda r: float(r["score"]), reverse=True)

    print(f"\n{'─'*78}")
    print(f"  STAGE 1c SUMMARY — {len(survivors)}/{len(rows)} cells survived all windows")
    print(f"{'─'*78}")
    print(f"  Top-15 by score (avg_wr − freq_penalty) — survivors only:")
    hdr = f"  {'calm':<6}{'vol':<6}{'thr':<6}{'adx':>4}  {'avg_wr':>7}  {'min_wr':>7}  {'avg_tr':>7}  {'avg_net':>10}  {'score':>7}"
    print(hdr)
    shown = 0
    for r in all_sorted[:30]:
        if r["breached"] == "True" and shown >= 15:
            continue
        mark = "" if r["breached"] == "False" else " BREACH"
        print(f"  {r['entry_fib_level']:<6}{r['entry_fib_level_volatile']:<6}"
              f"{r['fib_vol_ratio_threshold']:<6}{r['adx_min_entry']:>4}"
              f"  {float(r['avg_wr']):>7.1f}%  {float(r['min_wr']):>7.1f}%"
              f"  {r['avg_trades']:>7}  {int(r['avg_net']):>10,}"
              f"  {float(r['score']):>7.2f}{mark}")
        shown += 1
        if shown >= 15:
            break

    # WR improvement over baseline (Stage 1 grid winner: fib=0.50 no gate)
    baseline = next((r for r in rows
                     if r["entry_fib_level"] == "0.5"
                     and r["entry_fib_level_volatile"] == "0.0"
                     and r["adx_min_entry"] == "0"), None)
    if baseline:
        base_wr = float(baseline["avg_wr"])
        print(f"\n  Baseline (fib=0.50, no vol-adapt, no gate): avg_wr={base_wr:.1f}%")
        best = survivors[0] if survivors else None
        if best:
            best_wr = float(best["avg_wr"])
            print(f"  Best survivor:                              avg_wr={best_wr:.1f}%"
                  f"  (Δ={best_wr-base_wr:+.1f} pct-pts)")
    print()
    sys.stdout.flush()


def phase_validate(n_top: int = 5):
    if not GRID_CSV.exists():
        print("  No grid CSV — run phase grid first."); return

    rows = []
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            if row["breached"] == "False":
                rows.append(row)

    if not rows:
        print("  No surviving cells — relaxing to breach-allowed top-5 by score.")
        with open(GRID_CSV) as f:
            rows = list(csv.DictReader(f))

    rows.sort(key=lambda r: float(r["score"]), reverse=True)

    configs = []
    for i, r in enumerate(rows[:n_top]):
        tp = dict(PINNED)
        tp["entry_fib_level"]           = float(r["entry_fib_level"])
        tp["entry_fib_level_volatile"]  = float(r["entry_fib_level_volatile"])
        tp["fib_vol_ratio_threshold"]   = float(r["fib_vol_ratio_threshold"])
        adx = float(r["adx_min_entry"])
        tp["use_trend_quality_gate"]    = adx > 0
        tp["adx_min_entry"]             = adx
        configs.append({
            "label": (f"1c_top{i+1}"
                      f"_c{r['entry_fib_level']}"
                      f"_v{r['entry_fib_level_volatile']}"
                      f"_thr{r['fib_vol_ratio_threshold']}"
                      f"_adx{r['adx_min_entry']}"),
            "env": {},
            "tp":  tp,
            "train_score": float(r["score"]),
            "train_avg_wr": float(r["avg_wr"]),
        })

    print(f"\n{'='*78}")
    print(f"  Stage 1c — Validating top {n_top} cells on TEST_STARTS + full 10yr")
    print(f"{'='*78}\n")
    validated = dh.validate_configs(configs, tag="stage1c_top5")
    TOP5_JSON.write_text(json.dumps(validated, indent=2, default=str))
    print(f"\n  Saved → {TOP5_JSON}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["grid", "validate", "all"], default="all")
    args = p.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    if args.phase in ("grid", "all"):
        phase_grid()
    if args.phase in ("validate", "all"):
        phase_validate()


if __name__ == "__main__":
    main()
