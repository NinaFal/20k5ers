#!/usr/bin/env python3
"""
Stage 1c focused pilot — 25 carefully chosen cells that directly answer:
  1. What calm fib level is best? (sweep around 0.50 with vol disabled)
  2. Shallower or deeper volatile fib?  (both directions vs baseline)
  3. Does ADX gate help?               (gate on vs off at best calm)

Writes to stage1c_grid.csv (same CSV as full grid) — skip-if-done aware.
Runs in ~5-10 minutes with 4 workers.
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

DOE_DIR  = dh.DOE_DIR
GRID_CSV = DOE_DIR / "stage1c_grid.csv"
WORKERS  = dh.WORKERS_SHORT
WINDOWS  = dh.STAGE1_WINDOWS

MIN_TRADES_PER_WINDOW = 30
PENALTY_PER_TRADE     = 2.0

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

# ── Focused 25-cell design ────────────────────────────────────────────────────
# Group A: calm fib sensitivity (vol=0 disabled, adx=0) — what's the best calm fib?
# Group B: volatile shallower vs deeper (calm pinned at 0.50, thr=1.15, adx=0)
# Group C: ADX gate effect (calm=0.50, vol=0, three thresholds)
# Group D: threshold sensitivity for best volatile direction (calm=0.50, adx=0)
PILOT_CELLS = [
    # (calm,   vol,   thr,   adx)   group / label
    # A — calm sweep
    (0.45,  0.0,   1.15,  0),
    (0.50,  0.0,   1.15,  0),   # Stage 1 grid winner — baseline
    (0.55,  0.0,   1.15,  0),
    (0.60,  0.0,   1.15,  0),
    (0.65,  0.0,   1.15,  0),
    # B — shallower volatile (enter early in fast markets)
    (0.50,  0.35,  1.15,  0),
    (0.50,  0.40,  1.15,  0),
    (0.50,  0.45,  1.15,  0),
    # B — deeper volatile (wait for overshoot pullback)
    (0.50,  0.65,  1.15,  0),
    (0.50,  0.70,  1.15,  0),
    (0.50,  0.75,  1.15,  0),
    (0.50,  0.80,  1.15,  0),
    # C — ADX gate on vs off (calm=0.50, vol=0)
    (0.50,  0.0,   1.15,  15),
    (0.50,  0.0,   1.15,  20),
    (0.50,  0.0,   1.15,  25),
    # D — threshold sensitivity (calm=0.50, best shallow vol, adx=0)
    (0.50,  0.40,  1.05,  0),
    (0.50,  0.40,  1.25,  0),
    (0.50,  0.40,  1.35,  0),
    # D — threshold sensitivity (calm=0.50, deeper vol, adx=0)
    (0.50,  0.75,  1.05,  0),
    (0.50,  0.75,  1.25,  0),
    (0.50,  0.75,  1.35,  0),
    # E — ADX gate combined with best volatile (filled after B/C results known)
    (0.50,  0.40,  1.15,  20),
    (0.50,  0.75,  1.15,  20),
    (0.50,  0.40,  1.15,  15),
    (0.50,  0.75,  1.15,  15),
]


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
    for start, end in WINDOWS:
        r = dh.run_single({}, tp, start, end)
        if r is None:
            raise IncompleteCell(f"window {start}->{end} returned None")
        a = dh.extract_attrs(r)
        nets.append(a["net"]); wrs.append(a["win_rate"])
        trades_list.append(a["trades"]); failed_list.append(a["failed"])

    elapsed    = round(time.time() - t0)
    breached   = any(failed_list)
    n_survived = sum(1 for f in failed_list if not f)
    avg_wr     = round(sum(wrs) / len(wrs), 2)           if wrs else 0.0
    min_wr     = round(min(wrs), 2)                       if wrs else 0.0
    avg_trades = round(sum(trades_list) / len(trades_list)) if trades_list else 0
    min_trades = min(trades_list)                          if trades_list else 0
    avg_net    = round(sum(nets) / len(nets))             if nets else 0
    maximin_v  = min(nets) if not breached else -1_000_000 + int(min(nets))
    trade_pen  = PENALTY_PER_TRADE * max(0.0, MIN_TRADES_PER_WINDOW - avg_trades)
    score      = round(avg_wr - trade_pen, 3)

    return {
        "entry_fib_level": fib_c, "entry_fib_level_volatile": fib_v,
        "fib_vol_ratio_threshold": thr, "adx_min_entry": adx,
        "avg_wr": avg_wr, "min_wr": min_wr,
        "avg_trades": avg_trades, "min_trades": min_trades,
        "avg_net": avg_net, "maximin": maximin_v,
        "breached": breached, "n_survived": n_survived,
        "wr_w0": wrs[0], "wr_w1": wrs[1], "wr_w2": wrs[2],
        "wr_w3": wrs[3], "wr_w4": wrs[4],
        "net_w0": nets[0], "net_w1": nets[1], "net_w2": nets[2],
        "net_w3": nets[3], "net_w4": nets[4],
        "trades_w0": trades_list[0], "trades_w1": trades_list[1],
        "trades_w2": trades_list[2], "trades_w3": trades_list[3],
        "trades_w4": trades_list[4],
        "score": score, "elapsed_s": elapsed,
    }


def main():
    done = _load_done()
    todo = [c for c in PILOT_CELLS if _cell_key(*c) not in done]

    print(f"\n{'='*72}")
    print(f"  Stage 1c PILOT — {len(PILOT_CELLS)} cells  |  {len(done)} cached  |  {len(todo)} to run")
    print(f"  Groups: calm sweep | shallower vol | deeper vol | ADX gate | thresholds")
    print(f"  {WORKERS} workers  |  {len(WINDOWS)} windows each")
    print(f"{'='*72}\n")
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
                    print(f"  SKIP  {cell}  — {type(e).__name__}: {e}")
                    sys.stdout.flush(); continue
                writer.writerow(row); f.flush()
                breach_tag = "BREACH" if row["breached"] else "ok"
                print(f"  c={row['entry_fib_level']:.2f} v={row['entry_fib_level_volatile']:.2f}"
                      f" thr={row['fib_vol_ratio_threshold']:.2f} adx={row['adx_min_entry']:>2}"
                      f"  [{breach_tag}]"
                      f"  wr={row['avg_wr']:>5.1f}% (min {row['min_wr']:>5.1f}%)"
                      f"  trades={row['avg_trades']:>3}"
                      f"  net={row['avg_net']:>9,}  score={row['score']:>6.2f}"
                      f"  {row['elapsed_s']}s")
                sys.stdout.flush()

    # Print grouped summary
    rows = []
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            rows.append(row)

    print(f"\n{'─'*72}")
    print(f"  PILOT RESULTS — sorted by score")
    print(f"  {'calm':<6}{'vol':<6}{'thr':<6}{'adx':>4}  {'avg_wr':>7}  {'min_wr':>7}  "
          f"{'trades':>6}  {'avg_net':>10}  {'score':>7}  status")
    print(f"{'─'*72}")

    pilot_keys = {_cell_key(*c) for c in PILOT_CELLS}
    pilot_rows = [r for r in rows if
                  (r["entry_fib_level"], r["entry_fib_level_volatile"],
                   r["fib_vol_ratio_threshold"], r["adx_min_entry"]) in pilot_keys]
    pilot_rows.sort(key=lambda r: float(r["score"]), reverse=True)

    baseline = None
    for r in pilot_rows:
        if (r["entry_fib_level"], r["entry_fib_level_volatile"],
                r["adx_min_entry"]) == ("0.5", "0.0", "0"):
            baseline = r; break

    for r in pilot_rows:
        mark = "← baseline" if r is baseline else ("BREACH" if r["breached"] == "True" else "")
        delta = (f"  Δwr={float(r['avg_wr'])-float(baseline['avg_wr']):+.1f}%"
                 if baseline and r is not baseline else "")
        print(f"  {r['entry_fib_level']:<6}{r['entry_fib_level_volatile']:<6}"
              f"{r['fib_vol_ratio_threshold']:<6}{r['adx_min_entry']:>4}"
              f"  {float(r['avg_wr']):>7.1f}%  {float(r['min_wr']):>7.1f}%"
              f"  {r['avg_trades']:>6}  {int(r['avg_net']):>10,}"
              f"  {float(r['score']):>7.2f}  {mark}{delta}")

    print()
    sys.stdout.flush()


if __name__ == "__main__":
    main()
