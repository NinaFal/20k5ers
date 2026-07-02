#!/usr/bin/env python3
"""
Stage 1c — Entry-Quality Report (multi-objective fib finalist ranking).

WHY THIS REPORT:
  The Stage 1c/1d grid ranks fib entry setups by `score` (avg win-rate minus a
  trade-frequency penalty). For a 5%ers funded account that is necessary but not
  sufficient: a high win-rate that scalps tiny moves leaves the big runners on the
  table, while an entry that routinely gives back R before working is fragile near
  the 5% daily wall. This report re-runs the top-N grid finalists across the five
  STAGE1_WINDOWS and scores each on ENTRY QUALITY, not just net win-rate:

    • TP1-hit%        — how often the entry survives to the first profit rung
    • SL-out%         — complement of TP1-hit% (entries stopped before TP1)
    • MFE_R median/p75 — runner potential (how far price ran IN FAVOR, in R)
    • MAE_R median    — heat taken before working (adverse excursion, in R)
    • per-window net + maximin (worst-window net)
    • breach status   — a HARD veto (any breached window disqualifies)

RANKING (Pareto-style, breach is a hard veto):
  Survivors first (no breached window), then ordered by the tuple
      (tp1_hit_rate, mfe_r_p75, maximin)
  — i.e. prefer setups that most reliably reach TP1, then have the biggest
  runner tail, then the strongest worst-window floor. Breached configs sink to
  the bottom regardless of their other metrics.

Run AFTER the Stage 1c/1d grid (stage1c_grid.csv) has finished:
  python -u backtest/src/stage1c_entry_quality_report.py
  python -u backtest/src/stage1c_entry_quality_report.py --top 12
"""
import argparse
import concurrent.futures
import csv
import importlib.util
import sys
import time
from pathlib import Path

HERE  = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh    = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR   = dh.DOE_DIR
GRID_CSV  = DOE_DIR / "stage1c_grid.csv"   # same unified result set as Stage 1c/1d
REPORT_CSV = DOE_DIR / "stage1c_entry_quality_report.csv"  # checkpoint (skip-if-done)
WORKERS   = dh.WORKERS_SHORT
WINDOWS   = dh.STAGE1_WINDOWS

DEFAULT_TOP_N = 8

# Result-dict fields persisted to the checkpoint CSV. 'nets' is a list →
# pipe-joined on write, split on read. Order defines the CSV column order.
_REPORT_FIELDS = [
    "fib_c", "fib_v", "thr", "adx", "breached", "n_survived",
    "avg_wr", "avg_trades", "total_trades", "tp1_hit_rate", "slout_rate",
    "mfe_r_median", "mfe_r_p75", "mae_r_median", "avg_net", "maximin",
    "nets", "elapsed_s",
]


def _cell_id(fib_c, fib_v, thr, adx) -> str:
    return f"{float(fib_c):.2f}_{float(fib_v):.2f}_{float(thr):.2f}_{float(adx):.0f}"


def _load_done_report() -> dict:
    """Return {cell_id: result_dict} already checkpointed in REPORT_CSV."""
    done = {}
    if not REPORT_CSV.exists():
        return done
    with open(REPORT_CSV) as f:
        for row in csv.DictReader(f):
            try:
                r = dict(row)
                for k in ("fib_c", "fib_v", "thr", "adx", "avg_wr", "avg_trades",
                          "tp1_hit_rate", "slout_rate", "mfe_r_median", "mfe_r_p75",
                          "mae_r_median", "avg_net", "maximin"):
                    r[k] = float(r[k])
                for k in ("n_survived", "total_trades", "elapsed_s"):
                    r[k] = int(float(r[k]))
                r["breached"] = str(r["breached"]).lower() == "true"
                r["nets"] = [float(x) for x in r["nets"].split("|") if x != ""]
                done[_cell_id(r["fib_c"], r["fib_v"], r["thr"], r["adx"])] = r
            except (KeyError, ValueError):
                continue
    return done


def _append_report(r: dict):
    """Append one finalist result to the checkpoint CSV (flush per row)."""
    new_file = not REPORT_CSV.exists()
    with open(REPORT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(_REPORT_FIELDS)
        row = []
        for k in _REPORT_FIELDS:
            v = r.get(k)
            row.append("|".join(str(x) for x in v) if k == "nets" else v)
        w.writerow(row)
        f.flush()

# Pinned levers — MUST match the Stage 1c/1d sweep so the re-run reproduces the
# exact same engine config (only the fib/threshold/adx cell varies per finalist).
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


def _read_finalists(top_n: int, survivors_only: bool = True) -> list:
    """Read the top-N grid cells by `score` from stage1c_grid.csv.

    By default only NON-BREACHED cells are considered: breach is a hard veto, so
    a breached cell can never be the entry winner and re-running it only wastes
    compute. Without the filter, high-score breached cells crowd out genuine
    survivors from the top-N.
    """
    if not GRID_CSV.exists():
        print(f"  ERROR: {GRID_CSV} not found — run the Stage 1c/1d grid first.")
        return []
    rows = []
    with open(GRID_CSV) as f:
        for row in csv.DictReader(f):
            if survivors_only and str(row.get("breached")).strip().lower() != "false":
                continue
            try:
                row["_score"] = float(row.get("score") or -1e18)
            except (TypeError, ValueError):
                row["_score"] = -1e18
            rows.append(row)
    if not rows:
        print(f"  WARNING: {GRID_CSV} has no usable rows yet (grid still running?).")
        return []
    rows.sort(key=lambda r: r["_score"], reverse=True)
    return rows[:top_n]


def _cell_from_row(row: dict) -> tuple:
    """Extract the (fib_c, fib_v, thr, adx) cell from a grid CSV row."""
    fib_c = float(row["entry_fib_level"])
    fib_v = float(row["entry_fib_level_volatile"])
    thr   = float(row["fib_vol_ratio_threshold"])
    adx   = float(row["adx_min_entry"])
    return (fib_c, fib_v, thr, adx)


def _run_finalist(args: tuple) -> dict:
    """Worker: re-run one finalist cell across all STAGE1_WINDOWS, gather entry-quality stats."""
    fib_c, fib_v, thr, adx = args
    t0 = time.time()

    tp = dict(PINNED)
    tp["entry_fib_level"]          = fib_c
    tp["entry_fib_level_volatile"] = fib_v
    tp["fib_vol_ratio_threshold"]  = thr
    tp["use_trend_quality_gate"]   = adx > 0
    tp["adx_min_entry"]            = float(adx)

    nets, wrs, trades_list, failed_list = [], [], [], []
    tp1_rates, slout_rates = [], []
    mfe_med_list, mfe_p75_list, mae_med_list = [], [], []
    total_trades = 0
    total_tp1    = 0

    for wi, (start, end) in enumerate(WINDOWS):
        r = dh.run_single({}, tp, start, end)
        if r is None:
            raise RuntimeError(f"window {start}->{end} returned None (infra failure)")
        a = dh.extract_attrs(r)
        nets.append(a["net"])
        wrs.append(a["win_rate"])
        trades_list.append(a["trades"])
        failed_list.append(a["failed"])
        tp1_rates.append(a["tp1_hit_rate"])
        slout_rates.append(100.0 - a["tp1_hit_rate"])
        mfe_med_list.append(a["mfe_r_median"])
        mfe_p75_list.append(a["mfe_r_p75"])
        mae_med_list.append(a["mae_r_median"])
        total_trades += a["trades"]
        total_tp1    += a["tp1_hits"]
        bt = "BREACH" if a["failed"] else "ok"
        print(f"    · c={fib_c:.2f} v={fib_v:.2f} thr={thr:.2f} adx={adx:>2}"
              f"  w{wi+1}/5 [{bt}] wr={a['win_rate']:>5.1f}% tr={a['trades']:>3}"
              f" tp1={a['tp1_hit_rate']:>5.1f}% mfeP75={a['mfe_r_p75']:>4.1f}R"
              f" net={a['net']:>8,}", flush=True)

    breached   = any(failed_list)
    n_survived = sum(1 for f in failed_list if not f)
    maximin    = min(nets)
    avg_net    = sum(nets) / len(nets)
    avg_wr     = sum(wrs) / len(wrs)
    avg_trades = sum(trades_list) / len(trades_list)

    # trade-weighted TP1-hit rate (pooled across windows) is the headline objective
    tp1_hit_rate = (total_tp1 / total_trades * 100.0) if total_trades > 0 else 0.0
    slout_rate   = 100.0 - tp1_hit_rate

    return {
        "fib_c": fib_c, "fib_v": fib_v, "thr": thr, "adx": adx,
        "breached": breached, "n_survived": n_survived,
        "avg_wr": round(avg_wr, 1),
        "avg_trades": round(avg_trades, 0),
        "total_trades": total_trades,
        "tp1_hit_rate": round(tp1_hit_rate, 1),
        "slout_rate": round(slout_rate, 1),
        "mfe_r_median": round(sum(mfe_med_list) / len(mfe_med_list), 2),
        "mfe_r_p75": round(sum(mfe_p75_list) / len(mfe_p75_list), 2),
        "mae_r_median": round(sum(mae_med_list) / len(mae_med_list), 2),
        "avg_net": round(avg_net, 0),
        "maximin": round(maximin, 0),
        "nets": [round(n, 0) for n in nets],
        "elapsed_s": round(time.time() - t0),
    }


def _pareto_key(row: dict) -> tuple:
    """
    Ranking key (Python sorts ascending, so we negate for descending objectives).
    Breach is a HARD veto: breached configs get a leading sentinel that always
    sorts them last regardless of their other metrics.
    """
    breach_veto = 1 if row["breached"] else 0   # 0 sorts before 1 → survivors first
    return (
        breach_veto,
        -row["tp1_hit_rate"],   # prefer higher TP1 survival
        -row["mfe_r_p75"],      # then bigger runner tail
        -row["maximin"],        # then stronger worst-window floor
    )


def _print_report(results: list):
    if not results:
        print("\n  No finalists to report.")
        return
    ranked = sorted(results, key=_pareto_key)

    print(f"\n{'='*108}")
    print("  STAGE 1c — ENTRY-QUALITY REPORT  (multi-objective fib finalist ranking)")
    print("  Pareto order over (tp1_hit_rate ↑, mfe_r_p75 ↑, maximin ↑); breach = hard veto")
    print(f"{'='*108}")
    hdr = (f"  {'#':>2} {'fib_c':>5} {'fib_v':>5} {'thr':>5} {'adx':>4}"
           f"  {'trades':>6} {'TP1%':>6} {'SLout%':>6}"
           f"  {'MFE_med':>7} {'MFE_p75':>7} {'MAE_med':>7}"
           f"  {'avg_net':>10} {'maximin':>10}  {'status':>7}")
    print(hdr)
    print(f"  {'-'*104}")
    for i, r in enumerate(ranked, 1):
        status = "BREACH" if r["breached"] else "ok"
        print(f"  {i:>2} {r['fib_c']:>5.2f} {r['fib_v']:>5.2f} {r['thr']:>5.2f} {r['adx']:>4.0f}"
              f"  {r['total_trades']:>6} {r['tp1_hit_rate']:>6.1f} {r['slout_rate']:>6.1f}"
              f"  {r['mfe_r_median']:>7.2f} {r['mfe_r_p75']:>7.2f} {r['mae_r_median']:>7.2f}"
              f"  {r['avg_net']:>10,.0f} {r['maximin']:>10,.0f}  {status:>7}")

    print(f"  {'-'*104}")
    print("  Per-window net (w1..w5):")
    for i, r in enumerate(ranked, 1):
        nets = "  ".join(f"{n:>9,.0f}" for n in r["nets"])
        print(f"  {i:>2} c={r['fib_c']:.2f} v={r['fib_v']:.2f} thr={r['thr']:.2f} adx={r['adx']:.0f}:  {nets}")

    survivors = [r for r in ranked if not r["breached"]]
    print(f"\n  {len(survivors)}/{len(ranked)} finalists survived all windows.")
    if survivors:
        best = survivors[0]
        print(f"  BEST entry-quality survivor: c={best['fib_c']:.2f} v={best['fib_v']:.2f}"
              f" thr={best['thr']:.2f} adx={best['adx']:.0f}"
              f"  | TP1={best['tp1_hit_rate']:.1f}%  MFE_p75={best['mfe_r_p75']:.2f}R"
              f"  MAE_med={best['mae_r_median']:.2f}R  maximin={best['maximin']:,.0f}")
    print()
    print("  ENTRY-QUALITY REPORT COMPLETE")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description="Stage 1c entry-quality multi-objective report.")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP_N,
                    help=f"number of top-by-score grid finalists to re-run (default {DEFAULT_TOP_N})")
    args = ap.parse_args()

    finalists = _read_finalists(args.top)
    if not finalists:
        return

    all_cells = [_cell_from_row(r) for r in finalists]

    # Skip-if-done: load any finalists already checkpointed, run only the rest.
    done = _load_done_report()
    todo = [c for c in all_cells if _cell_id(*c) not in done]

    print(f"\n{'='*108}")
    print(f"  Stage 1c — Entry-Quality Report")
    print(f"  Top {len(all_cells)} grid finalists (by score) across {len(WINDOWS)} windows")
    print(f"  {WORKERS} workers  |  source: {GRID_CSV}")
    print(f"  checkpoint: {REPORT_CSV}  ({len(done)} done, {len(todo)} to run)")
    print(f"{'='*108}\n")
    for c, row in zip(all_cells, finalists):
        tag = "cached" if _cell_id(*c) in done else "to-run"
        print(f"    finalist [{tag}]: c={c[0]:.2f} v={c[1]:.2f} thr={c[2]:.2f} adx={c[3]:.0f}"
              f"  (grid score={row.get('score')}, avg_wr={row.get('avg_wr')})")
    sys.stdout.flush()

    if todo:
        with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(_run_finalist, c): c for c in todo}
            for fut in concurrent.futures.as_completed(futures):
                cell = futures[fut]
                try:
                    r = fut.result()
                    _append_report(r)   # checkpoint immediately (crash-safe)
                except Exception as e:
                    print(f"  SKIP  c={cell[0]:.2f} v={cell[1]:.2f} thr={cell[2]:.2f}"
                          f" adx={cell[3]:.0f}  — {type(e).__name__}: {e}")
                    sys.stdout.flush()
                    continue

    # Re-read the full set (cached + freshly checkpointed) for the final report.
    results = list(_load_done_report().values())
    _print_report(results)


if __name__ == "__main__":
    main()
