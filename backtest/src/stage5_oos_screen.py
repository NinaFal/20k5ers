#!/usr/bin/env python3
"""
Stage 5 OOS Screener — run top-N Stage 5 trials through all 6 OOS windows
and report which ones survive DDD/TDD constraints.

Usage:
    python -u backtest/src/stage5_oos_screen.py [--top 20] [--workers 4]

Reads  : backtest/output/doe/stage5.csv
Writes : backtest/output/doe/stage5_oos_screen.json
         backtest/output/doe/stage5_oos_screen_report.txt
"""
import argparse
import concurrent.futures
import csv
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dh)

DOE_DIR     = REPO / "backtest" / "output" / "doe"
CSV_IN      = DOE_DIR / "stage5.csv"
JSON_OUT    = DOE_DIR / "stage5_oos_screen.json"
REPORT_OUT  = DOE_DIR / "stage5_oos_screen_report.txt"

FULL_END   = "2024-12-31"
FULL_START = "2015-01-01"
OOS_STARTS = [
    "2015-02-01",
    "2018-01-01",
    "2021-01-01",
    "2023-01-01",
    "2023-07-01",
]
OOS_TASKS = [(s, FULL_END) for s in OOS_STARTS] + [(FULL_START, FULL_END)]

PARAM_COLS = [
    "RISK_CALM_MULT", "RISK_VOLATILE_MULT", "VOL_REGIME_DD_OFF",
    "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
    "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS",
    "CFG_TDD_WARNING_PCT", "CFG_RISK_CONSERVATIVE",
    "CFG_TDD_EMERGENCY_PCT", "CFG_RISK_ULTRASAFE", "TDD_WALL_SAFETY",
]
FIXED_ENV = {
    "RISK_REGIME_ENABLE": "1",
    "VOL_SIZE_ENABLE":    "0",
    "VOL_REGIME_DD_MULT": "1.0",
}

PINNED_ENTRY = {
    "trend_min_confluence":     6,
    "range_min_confluence":     3,
    "min_quality_factors":      3,
    "atr_min_percentile":       41.0,
    "atr_vol_ratio_range":      1.4,
    "use_fib_filter":           False,
    "fib_zone_type":            "golden_only",
    "entry_limit_offset_atr":   0.0,
    "entry_fib_level":          0.55,
    "entry_fib_level_volatile": 0.80,
    "fib_vol_ratio_threshold":  1.05,
    "use_trend_quality_gate":   False,
    "adx_min_entry":            0.0,
}
WINNER_LADDER = {
    "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.6,  "tp3_r_multiple": 2.8,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.3,
    "tp1_close_pct":  0.10, "tp2_close_pct":  0.30, "tp3_close_pct": 0.20,
    "tp4_close_pct":  0.15, "tp5_close_pct":  0.25,
    "sl_after_tp2_r": 0.70, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.00,
    "risk_per_trade_pct": 1.0,
}
TP_OVER = {**PINNED_ENTRY, **WINNER_LADDER}

os.environ.setdefault("RUN_TIMEOUT_S", "999999")


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_top_trials(n: int) -> list[dict]:
    rows = []
    with open(CSV_IN, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("breached", "True").strip().lower() in ("true", "1"):
                continue
            try:
                obj = float(row["objective"])
            except (ValueError, KeyError):
                continue
            rows.append({"obj": obj, "row": row})
    rows.sort(key=lambda x: x["obj"], reverse=True)
    return [r["row"] for r in rows[:n]]


def env_from_row(row: dict) -> dict:
    env = dict(FIXED_ENV)
    for k in PARAM_COLS:
        v = row.get(k, "")
        if v:
            env[k] = str(float(v))
    return env


def run_oos_window(env_over, start, end):
    r = dh.run_single(env_over, TP_OVER, start, end)
    a = dh.extract_attrs(r)
    return {"start": start, "end": end, **a}


def screen_trial(trial_row: dict, workers: int) -> dict:
    trial_id = trial_row.get("trial", "?")
    env_over  = env_from_row(trial_row)
    calm = trial_row.get("RISK_CALM_MULT", "?")
    vol  = trial_row.get("RISK_VOLATILE_MULT", "?")
    obj  = trial_row.get("objective", "?")

    print(f"[{ts()}] [trial {trial_id}] START  obj={float(obj):,.0f}  calm={calm} vol={vol}",
          flush=True)

    def _run(args):
        s, e = args
        r = run_oos_window(env_over, s, e)
        label = "[FULL]" if s == FULL_START else "[OOS ]"
        status = "BREACH" if r.get("failed") else "ok   "
        print(f"[{ts()}] [trial {trial_id}] {label} {s}  {status}"
              f"  net={r.get('net',0):>10,.0f}  tdd={r.get('max_tdd',0):.2f}%"
              f"  ddd={r.get('max_ddd',0):.2f}%", flush=True)
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        windows = list(ex.map(_run, OOS_TASKS))

    oos_wins   = [w for w in windows if w["start"] != FULL_START]
    full_win   = next((w for w in windows if w["start"] == FULL_START), None)
    n_pass_oos = sum(1 for w in oos_wins if not w.get("failed"))
    pass_full  = full_win and not full_win.get("failed")

    all_pass = (n_pass_oos == len(oos_wins)) and pass_full
    verdict  = "PASS" if all_pass else "FAIL"

    max_ddd = max((w.get("max_ddd", 0) or 0) for w in windows)
    max_tdd = max((w.get("max_tdd", 0) or 0) for w in windows)

    print(f"[{ts()}] [trial {trial_id}] {verdict}  "
          f"OOS {n_pass_oos}/{len(oos_wins)}  full={'PASS' if pass_full else 'FAIL'}"
          f"  peak_ddd={max_ddd:.2f}%  peak_tdd={max_tdd:.2f}%", flush=True)

    return {
        "trial":    int(trial_id),
        "obj":      float(obj),
        "calm":     float(calm),
        "vol":      float(vol),
        "verdict":  verdict,
        "oos_pass": n_pass_oos,
        "oos_total": len(oos_wins),
        "full_pass": bool(pass_full),
        "peak_ddd": round(max_ddd, 2),
        "peak_tdd": round(max_tdd, 2),
        "windows":  windows,
        "env":      env_over,
    }


def write_report(results: list[dict], top_n: int):
    lines = [
        f"Stage 5 OOS Screen — top {top_n} trials",
        f"Generated: {ts()}",
        f"OOS windows: {len(OOS_STARTS)} starts + 1 full (2015-2024)",
        "",
        f"{'Rank':<5} {'Trial':<7} {'Verdict':<8} {'OOS pass':<10} {'Full':<6}"
        f"{'peakDDD%':>9} {'peakTDD%':>9} {'Obj':>12} {'calm':>6} {'vol':>6}",
        "-" * 75,
    ]
    for i, r in enumerate(results, 1):
        full_s = "PASS" if r["full_pass"] else "FAIL"
        lines.append(
            f"  {i:<4} {r['trial']:<7} {r['verdict']:<8} "
            f"{r['oos_pass']}/{r['oos_total']}       {full_s:<6}"
            f"{r['peak_ddd']:>8.2f}  {r['peak_tdd']:>8.2f}"
            f"  {r['obj']:>11,.0f}  {r['calm']:>5.2f}  {r['vol']:>5.2f}"
        )

    passing = [r for r in results if r["verdict"] == "PASS"]
    lines += [
        "",
        f"Passing: {len(passing)}/{len(results)}",
    ]
    if passing:
        lines.append("")
        lines.append("── Best passing trial detail ──")
        best = passing[0]
        lines.append(f"  Trial {best['trial']}  obj={best['obj']:,.0f}  calm={best['calm']}  vol={best['vol']}")
        lines.append("  OOS windows:")
        for w in best["windows"]:
            label = "[FULL]" if w["start"] == FULL_START else "[OOS ]"
            status = "BREACH" if w.get("failed") else "ok"
            lines.append(f"    {label} {w['start']}  {status:<8}"
                         f"  net={w.get('net',0):>10,.0f}"
                         f"  tdd={w.get('max_tdd',0):>5.2f}%  ddd={w.get('max_ddd',0):>5.2f}%")
        lines.append("")
        lines.append("  WINNER_ENV:")
        for k, v in best["env"].items():
            lines.append(f"    {k} = {v}")

    lines.append("")
    lines.append("[stage5_oos_screen] STAGE5_OOS_SCREEN_DONE_MARKER")

    text = "\n".join(lines) + "\n"
    REPORT_OUT.write_text(text)
    print(text, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top",     type=int, default=20)
    ap.add_argument("--workers", type=int, default=int(os.getenv("VAL_WORKERS", "4")))
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[{ts()}] Stage 5 OOS screen — top {args.top} trials, {args.workers} workers",
          flush=True)

    trials = load_top_trials(args.top)
    print(f"[{ts()}] Loaded {len(trials)} trials from {CSV_IN}", flush=True)
    if not trials:
        print("No trials found — exiting", flush=True)
        sys.exit(1)

    results = []
    if JSON_OUT.exists():
        try:
            existing = json.loads(JSON_OUT.read_text())
            done_ids = {r["trial"] for r in existing}
            results  = existing
            print(f"[{ts()}] Resuming — {len(done_ids)} already done: {sorted(done_ids)}",
                  flush=True)
        except Exception:
            done_ids = set()
    else:
        done_ids = set()

    for row in trials:
        tid = int(row.get("trial", -1))
        if tid in done_ids:
            print(f"[{ts()}] [trial {tid}] already done — skipping", flush=True)
            continue
        r = screen_trial(row, args.workers)
        results.append(r)
        done_ids.add(tid)
        JSON_OUT.write_text(json.dumps(results, indent=2, default=str))

    results.sort(key=lambda x: (x["verdict"] != "PASS", -x["obj"]))
    JSON_OUT.write_text(json.dumps(results, indent=2, default=str))
    write_report(results, args.top)
    print("[stage5_oos_screen] STAGE5_OOS_SCREEN_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
