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

SCORING: maximin across the 5 TRAIN_STARTS (worst-start net P&L), hard breach
floor. Early-exit: a cell that breaches on a worst-first start stops there.

CRASH-PROOF: each grid cell appends one row to stage1_grid.csv on completion.
Restart skips done cells. Parallel across cells (4 workers).

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
WORKERS    = 4

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
              "worst_start", "n_survived", "breached", "min_wr",
              "max_tdd", "max_ddd",
              "net_2016", "net_2017", "net_2020", "net_2022", "net_2019",
              "elapsed_s"]


def _load_done() -> set:
    done = set()
    if not GRID_CSV.exists():
        return done
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            done.add((row["entry_fib_level"], row["entry_limit_offset_atr"]))
    return done


def _run_cell(args: tuple) -> dict:
    """
    Run one grid cell: all 5 train starts, worst-first, early-exit on breach.
    Returns a result dict (one CSV row).
    """
    fib, offset = args
    t0 = time.time()
    tp = dict(PINNED)
    tp["entry_fib_level"] = fib
    tp["entry_limit_offset_atr"] = offset

    nets, wrs, tdds, ddds = {}, [], [], []
    breached = False
    worst_start = ""
    n_survived = 0

    for start in dh.TRAIN_STARTS:
        r = dh.run_single({}, tp, start)
        a = dh.extract_attrs(r)
        nets[start[:4]] = a["net"]
        if a["failed"]:
            breached = True
            worst_start = start
            tdds.append(a["max_tdd"]); ddds.append(a["max_ddd"])
            break
        n_survived += 1
        wrs.append(a["win_rate"]); tdds.append(a["max_tdd"]); ddds.append(a["max_ddd"])

    elapsed = round(time.time() - t0)
    if breached:
        maximin = -1_000_000  # sentinel: breached cells sort to bottom
    else:
        maximin = min(nets.values())

    return {
        "entry_fib_level": fib, "entry_limit_offset_atr": offset,
        "maximin": maximin, "worst_start": worst_start,
        "n_survived": n_survived, "breached": breached,
        "min_wr": round(min(wrs), 1) if wrs else 0,
        "max_tdd": round(max(tdds), 2) if tdds else 0,
        "max_ddd": round(max(ddds), 2) if ddds else 0,
        "net_2016": nets.get("2016", ""), "net_2017": nets.get("2017", ""),
        "net_2020": nets.get("2020", ""), "net_2022": nets.get("2022", ""),
        "net_2019": nets.get("2019", ""),
        "elapsed_s": elapsed,
    }


def phase_grid():
    print(f"\n{'='*72}")
    print(f"  Stage 1b — 2D GRID: entry_fib_level × entry_limit_offset_atr")
    print(f"  {len(GRID_FIB)}×{len(GRID_OFFSET)} = {len(GRID_FIB)*len(GRID_OFFSET)} cells"
          f"  |  maximin over {len(dh.TRAIN_STARTS)} starts  |  {WORKERS} workers")
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
                try:
                    row = fut.result()
                except Exception as e:
                    print(f"  ERROR: {e}"); continue
                writer.writerow(row); f.flush()
                tag = (f"BREACH@{row['worst_start'][:7]}" if row["breached"]
                       else f"maximin={row['maximin']:>9,}")
                print(f"  fib={row['entry_fib_level']:.3f} off={row['entry_limit_offset_atr']:.2f}  "
                      f"{tag:<22}  wr={row['min_wr']:>5}%  tdd={row['max_tdd']:>5}%  "
                      f"surv={row['n_survived']}/5  {row['elapsed_s']}s")
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
    print(f"  GRID SUMMARY — {len(survivors)}/{len(rows)} cells survived all 5 starts")
    print(f"{'─'*72}")
    print(f"  Top-10 by maximin (worst-start net P&L):")
    print(f"  {'fib':<7}{'offset':<8}{'maximin':>11}  {'minWR':>6}  {'maxTDD':>7}")
    for r in survivors[:10]:
        print(f"  {r['entry_fib_level']:<7}{r['entry_limit_offset_atr']:<8}"
              f"{int(r['maximin']):>11,}  {r['min_wr']:>5}%  {r['max_tdd']:>6}%")

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
