#!/usr/bin/env python3
"""
Stage 1b: 2D GRID sweep over the only two live entry levers.

WHY A GRID (not Optuna):
  The OAT screen (stage1_oat.csv) proved that of the 9 entry/fib variables,
  only TWO actually change backtest outcomes:
      entry_fib_level        (where the limit order sits on the swing leg)
      entry_limit_offset_atr (extra ATR push for a better fill)
  The other 7 (trend/range confluence, quality factors 2-4, atr filters,
  use_fib_filter, fib_zone_type) are INERT — the confluence gate is saturated,
  so they never flip a trade active/inactive. min_quality only bit at 5 (worse
  on every axis), so it is pinned at 3.

  With the search collapsed to 2 dimensions, an exhaustive grid is the correct
  tool: interpretable response surface, zero overfit risk, fully parallel.

SCORING: maximin across 5 SHORT multi-regime windows (worst-window net P&L).
Entry pricing is judged on per-regime efficiency, NOT full-path survival — the
ratcheting-floor compounding breach is Stage 2's job (it needs the safety levers
we hold fixed here). Short windows are also memory-light → 4 workers, no OOM.

CRASH-PROOF: each grid cell appends one row to stage1_grid.csv on completion.
A window that returns None (OOM/timeout) is retried inside run_single; if it
still fails the whole cell is skipped (not written) so a restart re-runs it.
Restart skips done cells. Parallel across cells (WORKERS_SHORT=4).

Usage:
  uv run python -u backtest/src/stage1_grid.py --phase grid
  uv run python -u backtest/src/stage1_grid.py --phase validate
"""
import argparse
import concurrent.futures
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR    = dh.DOE_DIR
GRID_CSV   = DOE_DIR / "stage1_grid.csv"
TOP5_JSON  = DOE_DIR / "stage1_grid_top5.json"
WORKERS    = dh.WORKERS_SHORT        # 4 — safe for short windows (~1.5GB each)
WINDOWS    = dh.STAGE1_WINDOWS       # 5 short multi-regime (start, end) slices

# ── The 2D grid (the only live levers) ───────────────────────────────────────
GRID_FIB    = [0.500, 0.550, 0.600, 0.650, 0.700, 0.750, 0.800]
GRID_OFFSET = [0.00, 0.10, 0.20, 0.30, 0.40]

# Dead levers pinned at safe/default values (proven inert in OAT)
PINNED = {
    "trend_min_confluence":   6,
    "range_min_confluence":   3,
    "min_quality_factors":    3,    # 2-4 identical; 3 = middle
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
}

CSV_HEADER = ["entry_fib_level", "entry_limit_offset_atr", "maximin",
              "worst_window", "n_survived", "breached", "min_wr",
              "avg_net", "max_tdd", "max_ddd",
              "net_w0", "net_w1", "net_w2", "net_w3", "net_w4",
              "elapsed_s"]


def _load_done() -> set:
    done = set()
    if not GRID_CSV.exists():
        return done
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            done.add((row["entry_fib_level"], row["entry_limit_offset_atr"]))
    return done


class IncompleteCell(Exception):
    """Raised when a window run returns None even after retries (infra failure)."""


def _run_cell(args: tuple) -> dict:
    """
    Run one grid cell across all 5 short windows.

    A None run (OOM/timeout after retries) raises IncompleteCell → the cell is
    NOT written, so a restart re-runs it. We do NOT early-exit on breach here:
    these are short survivable windows, and we want the full per-window net
    vector to rank entry pricing by worst-window (maximin) profit.
    """
    fib, offset = args
    t0 = time.time()
    tp = dict(PINNED)
    tp["entry_fib_level"] = fib
    tp["entry_limit_offset_atr"] = offset

    nets, wrs, tdds, ddds = [], [], [], []
    breached = False
    worst_window = ""

    for i, (start, end) in enumerate(WINDOWS):
        r = dh.run_single({}, tp, start, end)
        if r is None:
            raise IncompleteCell(f"window {start}->{end} returned None")
        a = dh.extract_attrs(r)
        nets.append(a["net"])
        wrs.append(a["win_rate"]); tdds.append(a["max_tdd"]); ddds.append(a["max_ddd"])
        if a["failed"]:
            breached = True
            if not worst_window:
                worst_window = start

    elapsed = round(time.time() - t0)
    n_survived = sum(1 for t in tdds if t < 9.99) if not breached else \
                 len(WINDOWS) - sum(1 for a in [breached] if a)  # informational
    n_survived = len(WINDOWS) - (1 if breached else 0)
    # maximin = worst window net; breached cells get a hard penalty floor
    maximin = (min(nets) if not breached
               else -1_000_000 + int(min(nets)))

    return {
        "entry_fib_level": fib, "entry_limit_offset_atr": offset,
        "maximin": maximin, "worst_window": worst_window,
        "n_survived": n_survived, "breached": breached,
        "min_wr": round(min(wrs), 1) if wrs else 0,
        "avg_net": round(sum(nets) / len(nets)) if nets else 0,
        "max_tdd": round(max(tdds), 2) if tdds else 0,
        "max_ddd": round(max(ddds), 2) if ddds else 0,
        "net_w0": nets[0] if len(nets) > 0 else "",
        "net_w1": nets[1] if len(nets) > 1 else "",
        "net_w2": nets[2] if len(nets) > 2 else "",
        "net_w3": nets[3] if len(nets) > 3 else "",
        "net_w4": nets[4] if len(nets) > 4 else "",
        "elapsed_s": elapsed,
    }


def phase_grid():
    print(f"\n{'='*72}")
    print(f"  Stage 1b — 2D GRID: entry_fib_level × entry_limit_offset_atr")
    print(f"  {len(GRID_FIB)}×{len(GRID_OFFSET)} = {len(GRID_FIB)*len(GRID_OFFSET)} cells"
          f"  |  maximin over {len(WINDOWS)} short windows  |  {WORKERS} workers")
    print(f"{'='*72}\n")
    sys.stdout.flush()

    done = _load_done()
    cells = [(f, o) for f in GRID_FIB for o in GRID_OFFSET
             if (str(f), str(o)) not in done]
    print(f"  {len(cells)} cells to run ({len(done)} cached)\n")
    sys.stdout.flush()

    write_header = not GRID_CSV.exists() or GRID_CSV.stat().st_size == 0
    with open(GRID_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if write_header:
            writer.writeheader(); f.flush()

        with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(_run_cell, c): c for c in cells}
            for fut in concurrent.futures.as_completed(futures):
                cell = futures[fut]
                try:
                    row = fut.result()
                except Exception as e:
                    # IncompleteCell or any transient worker error → don't write,
                    # so the skip-if-done restart re-runs this cell next pass.
                    print(f"  SKIP  fib={cell[0]} off={cell[1]} — {type(e).__name__}: {e}")
                    sys.stdout.flush(); continue
                writer.writerow(row); f.flush()
                tag = (f"BREACH@{row['worst_window'][:7]}" if row["breached"]
                       else f"maximin={row['maximin']:>9,}")
                print(f"  fib={row['entry_fib_level']:.3f} off={row['entry_limit_offset_atr']:.2f}  "
                      f"{tag:<22}  wr={row['min_wr']:>5}%  avg_net={row['avg_net']:>9,}  "
                      f"tdd={row['max_tdd']:>5}%  {row['elapsed_s']}s")
                sys.stdout.flush()

    print(f"\n  Grid complete → {GRID_CSV}")
    _print_grid_summary()


def _print_grid_summary():
    if not GRID_CSV.exists():
        return
    rows = []
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    survivors = [r for r in rows if r["breached"] == "False"]
    survivors.sort(key=lambda r: int(r["maximin"]), reverse=True)

    print(f"\n{'─'*72}")
    print(f"  GRID SUMMARY — {len(survivors)}/{len(rows)} cells survived all 5 windows")
    print(f"{'─'*72}")
    print(f"  Top-10 by maximin (worst-window net P&L):")
    print(f"  {'fib':<7}{'offset':<8}{'maximin':>11}{'avg_net':>11}  {'minWR':>6}  {'maxTDD':>7}")
    for r in survivors[:10]:
        print(f"  {r['entry_fib_level']:<7}{r['entry_limit_offset_atr']:<8}"
              f"{int(r['maximin']):>11,}{int(r['avg_net']):>11,}  "
              f"{r['min_wr']:>5}%  {r['max_tdd']:>6}%")

    # ASCII heatmap of maximin
    print(f"\n  Maximin heatmap (rows=fib, cols=offset; X=breach):")
    by = {(r["entry_fib_level"], r["entry_limit_offset_atr"]): r for r in rows}
    offs = sorted({r["entry_limit_offset_atr"] for r in rows}, key=float)
    fibs = sorted({r["entry_fib_level"] for r in rows}, key=float)
    print("        " + "".join(f"{o:>9}" for o in offs))
    for fib in fibs:
        cells = []
        for o in offs:
            r = by.get((fib, o))
            if not r:
                cells.append(f"{'·':>9}")
            elif r["breached"] == "True":
                cells.append(f"{'X':>9}")
            else:
                cells.append(f"{int(r['maximin'])//1000:>8}k")
        print(f"  {fib:<6}" + "".join(cells))
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
        print("  No surviving cells to validate."); return
    rows.sort(key=lambda r: int(r["maximin"]), reverse=True)

    configs = []
    for i, r in enumerate(rows[:n_top]):
        tp = dict(PINNED)
        tp["entry_fib_level"] = float(r["entry_fib_level"])
        tp["entry_limit_offset_atr"] = float(r["entry_limit_offset_atr"])
        configs.append({
            "label": f"grid_top{i+1}_fib{r['entry_fib_level']}_off{r['entry_limit_offset_atr']}",
            "env": {}, "tp": tp,
            "train_maximin": int(r["maximin"]),
        })

    print(f"\n{'='*72}")
    print(f"  Stage 1b — Validating top {n_top} grid cells on TEST_STARTS + full 10yr")
    print(f"{'='*72}\n")
    validated = dh.validate_configs(configs, tag="stage1_grid_top5")
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
