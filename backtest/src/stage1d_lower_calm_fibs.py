#!/usr/bin/env python3
"""
Stage 1d: Lower calm-fib extension sweep (c=0.35, 0.40).

WHY THIS STAGE:
  Stage 1c found c=0.45 as the best calm fib — the bottom of its range.
  A winner at the edge of a grid means the true optimum might sit just
  outside. This targeted sweep closes that gap by testing c=0.35 and 0.40
  with the full volatile fib range at the best threshold (thr=1.15, adx=0).
  ~18 cells, ~1 hour.  Writes to the same stage1c_grid.csv so skip-if-done
  and the validate phase read a single unified result set.

GRID (focused):
  calm fibs:     0.35, 0.40          (the two missing below Stage 1c's floor)
  volatile fibs: full range (0.0 + 0.35–0.80)
  threshold:     1.15 only           (Stage 1c winner; thr for v=0.0 collapsed)
  adx:           0 only              (gate consistently hurt across Stage 1c)

Run after Stage 1c phase grid + validate:
  python -u backtest/src/stage1d_lower_calm_fibs.py
"""
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
GRID_CSV  = DOE_DIR / "stage1c_grid.csv"   # same file — unified result set
WORKERS   = dh.WORKERS_SHORT
WINDOWS   = dh.STAGE1_WINDOWS

MIN_TRADES_PER_WINDOW = 30
PENALTY_PER_TRADE     = 2.0

GRID_FIB_CALM = [0.35, 0.40]
GRID_FIB_VOL  = [0.0, 0.35, 0.40, 0.45, 0.50, 0.65, 0.70, 0.75, 0.78, 0.80]
BEST_THR      = 1.15    # Stage 1c winner threshold
ADX           = 0       # gate consistently hurt in Stage 1c

PINNED = {
    "trend_min_confluence":   6,
    "range_min_confluence":   3,
    "min_quality_factors":    3,
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
    "entry_limit_offset_atr": 0.0,
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
    cells = []
    for fib_c in GRID_FIB_CALM:
        for fib_v in GRID_FIB_VOL:
            if fib_v != 0.0 and fib_v == fib_c:
                continue
            thr = 1.05 if fib_v == 0.0 else BEST_THR
            cells.append((fib_c, fib_v, thr, ADX))
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
    pass


def _run_cell(args: tuple) -> dict:
    fib_c, fib_v, thr, adx = args
    t0 = time.time()

    tp = dict(PINNED)
    tp["entry_fib_level"]           = fib_c
    tp["entry_fib_level_volatile"]  = fib_v
    tp["fib_vol_ratio_threshold"]   = thr
    tp["use_trend_quality_gate"]    = adx > 0
    tp["adx_min_entry"]             = float(adx)

    nets, wrs, trades_list, failed_list = [], [], [], []

    for wi, (start, end) in enumerate(WINDOWS):
        r = dh.run_single({}, tp, start, end)
        if r is None:
            raise IncompleteCell(f"window {start}->{end} returned None")
        a = dh.extract_attrs(r)
        nets.append(a["net"])
        wrs.append(a["win_rate"])
        trades_list.append(a["trades"])
        failed_list.append(a["failed"])
        bt = "BREACH" if a["failed"] else "ok"
        print(f"    · c={fib_c:.2f} v={fib_v:.2f} thr={thr:.2f} adx={adx:>2}"
              f"  w{wi+1}/5 [{bt}] wr={a['win_rate']:>5.1f}% tr={a['trades']:>3}"
              f" net={a['net']:>8,}", flush=True)

    avg_wr     = sum(wrs) / len(wrs)
    avg_trades = sum(trades_list) / len(trades_list)
    avg_net    = sum(nets) / len(nets)
    breached   = any(failed_list)
    n_survived = sum(1 for f in failed_list if not f)
    maximin    = min(nets)
    min_wr     = min(wrs)
    min_trades = min(trades_list)
    freq_penalty = PENALTY_PER_TRADE * max(0, MIN_TRADES_PER_WINDOW - avg_trades)
    score = avg_wr - freq_penalty

    row = {
        "entry_fib_level":          fib_c,
        "entry_fib_level_volatile": fib_v,
        "fib_vol_ratio_threshold":  thr,
        "adx_min_entry":            adx,
        "avg_wr":    round(avg_wr, 2),
        "min_wr":    round(min_wr, 1),
        "avg_trades": round(avg_trades, 0),
        "min_trades": min_trades,
        "avg_net":   round(avg_net, 0),
        "maximin":   round(maximin, 0),
        "breached":  breached,
        "n_survived": n_survived,
        "wr_w0": round(wrs[0], 1), "wr_w1": round(wrs[1], 1),
        "wr_w2": round(wrs[2], 1), "wr_w3": round(wrs[3], 1),
        "wr_w4": round(wrs[4], 1),
        "net_w0": round(nets[0], 0), "net_w1": round(nets[1], 0),
        "net_w2": round(nets[2], 0), "net_w3": round(nets[3], 0),
        "net_w4": round(nets[4], 0),
        "trades_w0": trades_list[0], "trades_w1": trades_list[1],
        "trades_w2": trades_list[2], "trades_w3": trades_list[3],
        "trades_w4": trades_list[4],
        "score":     round(score, 2),
        "elapsed_s": round(time.time() - t0),
    }
    breach_tag = "BREACH" if breached else "ok"
    print(f"  c={fib_c:.2f} v={fib_v:.2f} thr={thr:.2f} adx={adx:>2}"
          f"  [{breach_tag}]"
          f"  wr={avg_wr:>5.1f}% (min {min_wr:>5.1f}%)"
          f"  trades={avg_trades:>5.0f} (min {min_trades:>3})"
          f"  avg_net={avg_net:>9,.0f}  score={score:>6.2f}"
          f"  {row['elapsed_s']}s", flush=True)
    return row


def _warm_caches():
    print("  Warming 5 window caches sequentially...", flush=True)
    tp = dict(PINNED)
    tp["entry_fib_level"]           = 0.40
    tp["entry_fib_level_volatile"]  = 0.0
    tp["adx_min_entry"]             = 0.0
    tp["use_trend_quality_gate"]    = False
    for i, (start, end) in enumerate(WINDOWS):
        t0 = time.time()
        print(f"    [{i+1}/{len(WINDOWS)}] caching {start} → {end} ...", flush=True)
        r = dh.run_single({}, tp, start, end)
        dt = round(time.time() - t0)
        status = "ok" if r is not None else "FAILED"
        print(f"    [{i+1}/{len(WINDOWS)}] {start} → {end}  {status}  ({dt}s)", flush=True)
    sys.stdout.flush()


def _print_summary():
    if not GRID_CSV.exists():
        return
    rows = []
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Stage 1d cells only (calm ≤ 0.40)
    d_rows = [r for r in rows if float(r["entry_fib_level"]) <= 0.40]
    survivors = [r for r in d_rows if r["breached"] == "False"]
    survivors.sort(key=lambda r: float(r["score"]), reverse=True)
    all_sorted = sorted(d_rows, key=lambda r: float(r["score"]), reverse=True)

    # Compare against Stage 1c best
    all_rows_sorted = sorted(rows, key=lambda r: float(r["score"]), reverse=True)
    overall_best = next((r for r in all_rows_sorted if r["breached"] == "False"), None)

    print(f"\n{'─'*78}")
    print(f"  STAGE 1d SUMMARY — lower calm-fib extension (c=0.35, 0.40)")
    print(f"  {len(survivors)}/{len(d_rows)} new cells survived | "
          f"Overall best across 1c+1d:")
    if overall_best:
        print(f"  c={overall_best['entry_fib_level']} v={overall_best['entry_fib_level_volatile']}"
              f" thr={overall_best['fib_vol_ratio_threshold']} adx={overall_best['adx_min_entry']}"
              f"  wr={float(overall_best['avg_wr']):.1f}%  score={float(overall_best['score']):.2f}")
    print(f"{'─'*78}")
    print(f"  Stage 1d top cells:")
    for r in all_sorted[:8]:
        mark = "" if r["breached"] == "False" else " BREACH"
        print(f"  c={r['entry_fib_level']:<6} v={r['entry_fib_level_volatile']:<6}"
              f" thr={r['fib_vol_ratio_threshold']:<6} adx={r['adx_min_entry']:>3}"
              f"  wr={float(r['avg_wr']):>6.1f}%  min={float(r['min_wr']):>5.1f}%"
              f"  score={float(r['score']):>6.2f}{mark}")
    print()
    sys.stdout.flush()


def main():
    cells = _build_cells()
    done  = _load_done()
    todo  = [c for c in cells if _cell_key(*c) not in done]

    print(f"\n{'='*78}")
    print(f"  Stage 1d — Lower calm-fib extension (c=0.35, 0.40)")
    print(f"  {len(cells)} cells total  |  {len(done) - (len(done) - len(cells) + len(todo))} cached"
          f"  |  {len(todo)} to run")
    print(f"  thr=1.15 (Stage 1c winner)  |  adx=0  |  full vol-fib range")
    print(f"  {WORKERS} workers  |  {len(WINDOWS)} windows per cell")
    print(f"{'='*78}\n")
    sys.stdout.flush()

    if todo:
        _warm_caches()

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
                sys.stdout.flush()

    print(f"\n  Stage 1d complete → {GRID_CSV}")
    _print_summary()


if __name__ == "__main__":
    main()
